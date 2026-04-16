"""
Beggar Automated Task System
Handles automatic public channel messages for begging
"""

import asyncio
import random
from typing import Optional, List, Dict, Any

import discord
from discord.ui import View
from discord import Interaction

from agent_logging import get_logger
from agent_mind import call_llm
from agent_engine import _build_system_prompt, _get_personality

from .beggar_db import get_beggar_config
from .beggar_discord import BeggarDonationView
from .beggar_messages import get_task_prompt_template, get_label
from agent_roles_db import get_roles_db_instance

logger = get_logger('beggar_task')


class BeggarTask:
    """Automated task system for beggar public messages."""
    
    def __init__(self, server_id: str, bot_instance=None):
        # Get bot instance if not provided
        if bot_instance is None:
            from discord_bot.agent_discord import get_bot_instance
            bot_instance = get_bot_instance()
            if bot_instance:
                guilds_info = [f"{g.name}({g.id})" for g in bot_instance.guilds]
                logger.info(f"Bot instance retrieved with {len(bot_instance.guilds)} guilds: {guilds_info}")
            else:
                logger.warning("Bot instance is None after get_bot_instance()")
        self.bot_instance = bot_instance
        self.server_id = str(server_id)
        
        self.config = get_beggar_config(self.server_id)
        self.roles_db = get_roles_db_instance(self.server_id)
    
    def should_execute(self) -> bool:
        """Check if the beggar task should execute."""
        if not self.config.is_enabled():
            logger.debug(f"Beggar disabled for server {self.server_id}")
            return False
        
        # Check if we need to change the reason
        if self.config.should_change_reason():
            logger.info(f"Changing beggar reason for server {self.server_id}")
            self.config.select_new_reason()
        
        return True
    
    async def execute_task(self) -> bool:
        """Execute the automated begging task."""
        try:
            if not self.should_execute():
                return False
            
            # Get current reason
            current_reason = self.config.get_current_reason() or "the current group project"
            if not current_reason:
                logger.warning(f"No current reason set for beggar in server {self.server_id}")
                return False
            
            # Get target channel
            target_channel = await self._get_target_channel()
            if not target_channel:
                logger.warning(f"No target channel found for server {self.server_id}")
                return False
            
            # Get recent messages from channel for context
            recent_messages = await self._get_recent_channel_messages(target_channel, limit=10)
            
            # Build the prompt
            prompt = self._build_task_prompt(current_reason, recent_messages)

            # Generate message using LLM — offload to thread to avoid blocking the event loop
            server_personality = _get_personality(self.server_id) if self.server_id else _get_personality()
            system_instruction = _build_system_prompt(server_personality, self.server_id)

            response = await asyncio.to_thread(
                call_llm,
                system_instruction=system_instruction,
                prompt=prompt,
                async_mode=False,
                call_type="beggar_task",
                critical=False,
                temperature=0.95,
                server_id=self.server_id
            )
            
            if response and len(response.strip()) > 5:
                # Create donation view
                view = BeggarDonationView(current_reason, self.server_id)
                
                # Send message to channel with buttons
                await target_channel.send(response, view=view)
                
                # Register the task execution
                self.roles_db.save_beggar_request(
                    user_id="system",
                    user_name="Beggar Task",
                    request_type="BEGGAR_PUBLIC",
                    message=response,
                    channel_id=str(target_channel.id),
                    metadata=f"reason:{current_reason}|with_buttons:true",
                )
                
                logger.info(f"Beggar task with donation buttons executed in channel {target_channel.name} for server {self.server_id}")

                # Persist next_run_at so the scheduler knows when to fire next
                try:
                    from agent_engine import mark_subrole_executed
                    from datetime import datetime, timedelta
                    freq = self.config.get_frequency_hours()
                    mark_subrole_executed('beggar', datetime.now() + timedelta(hours=freq), server_id=self.server_id)
                    logger.info(f"🙏 [BEGGAR] next_run_at persisted: +{freq}h from now")
                except Exception as _e:
                    logger.warning(f"🙏 [BEGGAR] Could not persist next_run_at: {_e}")

                return True
            else:
                logger.warning(f"Empty or short response from LLM for beggar task in server {self.server_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing beggar task for server {self.server_id}: {e}")
            return False
    
    async def _get_target_channel(self) -> Optional[Any]:
        """Get the target channel for sending messages."""
        # Check bot instance availability
        if not self.bot_instance:
            logger.warning(f"Bot instance is None for server {self.server_id}")
            return None
        
        # Check if bot is ready/connected
        if not getattr(self.bot_instance, 'is_ready', lambda: False)():
            logger.warning(f"Bot is not connected to Discord yet for server {self.server_id}")
            return None
        
        # Try specific channel first
        channel_id = self.config.get_target_channel_id()
        if channel_id:
            try:
                channel = self.bot_instance.get_channel(int(channel_id))
                if channel and channel.permissions_for(channel.guild.me).send_messages:
                    logger.info(f"Using specific channel {channel.name} (ID: {channel_id})")
                    return channel
            except (ValueError, AttributeError) as e:
                logger.warning(f"Failed to get specific channel {channel_id}: {e}")
        
        # Auto-select channel if enabled
        try:
            logger.info(f"Auto-selecting channel for server {self.server_id}")
            # If we have a specific server_id (numeric), try to get that guild
            if self.server_id and self.server_id != "default" and self.server_id.isdigit():
                guild = self.bot_instance.get_guild(int(self.server_id))
                if not guild:
                    logger.warning(f"Guild {self.server_id} not found in bot's guilds (bot may not be connected yet)")
                    return None
                guilds = [guild]
                logger.info(f"Found guild {guild.name} for server {self.server_id}")
            else:
                # Use all available guilds when server_id is 'default' or not numeric
                guilds = [guild for guild in self.bot_instance.guilds if guild.me.guild_permissions.send_messages]
                logger.info(f"Using {len(guilds)} guilds with send_messages permission")
            
            if not guilds:
                logger.warning(f"No guilds available for server {self.server_id}")
                return None
            
            # For each guild, find suitable channels and pick the best one
            best_channel = None
            best_score = -1
            
            for guild in guilds:
                # Prefer text channels where bot can speak
                text_channels = [
                    channel for channel in guild.text_channels
                    if channel.permissions_for(guild.me).send_messages
                    and not channel.is_nsfw()
                    and channel.name not in ['bot-commands', 'admin', 'moderation', 'staff']
                ]
                
                if not text_channels:
                    continue
                
                # Prioritize general chat channels
                priority_keywords = ['general', 'chat', 'main', 'lobby', 'comunidad', 'hablar']
                
                for channel in text_channels:
                    score = 0
                    # Higher score for priority keywords
                    if any(keyword in channel.name.lower() for keyword in priority_keywords):
                        score += 10
                    # Higher score for more members (assuming more active)
                    if hasattr(channel, 'member_count') and channel.member_count:
                        score += min(channel.member_count // 10, 5)
                    
                    # Update best channel if this one scores higher
                    if score > best_score:
                        best_channel = channel
                        best_score = score
                        # If we found a priority channel, that's probably good enough
                        if score >= 10:
                            break
                
                # If we found a priority channel in this guild, no need to check other guilds
                if best_score >= 10:
                    break
            
            # Return the best channel found, or None if none found
            return best_channel if best_channel else (guilds[0].text_channels[0] if guilds[0].text_channels else None)
            
        except Exception as e:
            logger.error(f"Error auto-selecting channel for server {self.server_id}: {e}")
            return None
    
    async def _get_recent_channel_messages(self, channel, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent messages from channel for context using Discord API directly."""
        try:
            messages = []
            message_count = 0
            logger.info(f"Fetching Discord messages from channel {channel.name}")
            
            async for message in channel.history(limit=20):  # Fetch more to filter
                message_count += 1
                
                # Only include messages from last hour
                import datetime
                message_age = (datetime.datetime.now(datetime.timezone.utc) - message.created_at).total_seconds()
                if message_age > 3600:
                    continue
                    
                # Skip commands
                if message.content.strip().startswith('!'):
                    continue

                # Skip empty bot messages (embeds, reactions, etc.)
                if message.author.bot and not message.content.strip():
                    continue
                    
                # Format message and clean mentions
                content = message.content
                # Replace user mentions with display names
                for mention in message.mentions:
                    content = content.replace(f"<@{mention.id}>", f"@{mention.display_name}")
                
                messages.append({
                    'author': message.author.display_name,
                    'content': content[:200],  # Limit content length
                    'timestamp': message.created_at.isoformat()
                })
            
            logger.info(f"Discord message fetch completed. Processed: {message_count}, Included: {len(messages)}")
            
            # discord_channel.history() returns newest-first; reverse to get chronological order
            # then take the last N (most recent) in chronological order
            messages_chronological = list(reversed(messages))
            
            return messages_chronological[-limit:]  # Return only the requested limit
            
        except Exception as e:
            logger.error(f"Error getting recent messages from channel {channel.name}: {e}")
            return []
    
    def _build_task_prompt(self, reason: str, recent_messages: List[Dict[str, Any]]) -> str:
        """Build the complete prompt for the begging task."""
        # Get task prompt template from beggar_messages.py (loads from personality prompts.json)
        task_prompt_template = get_task_prompt_template(self.server_id)
        task_prompt = task_prompt_template.format(reason=reason)
        
        # Get weekly donations summary
        weekly_donations_context = self._get_weekly_donations_context()
        
        # Build recent messages context
        messages_context = ""
        if recent_messages:
            # Get label from beggar_messages.py (loads from personality prompts.json)
            channel_label = get_label("recent_channel_messages", self.server_id)
            messages_context = f"\n\n{channel_label}\n"
            for msg in recent_messages[-5:]:  # Only last 5 messages
                messages_context += f"[{msg['author']}]: {msg['content']}\n"
        
        # Build golden rules
        golden_rules = self._get_golden_rules()
        
        # Complete prompt
        complete_prompt = f"""{task_prompt}{weekly_donations_context}{messages_context}

{golden_rules}

"""
        
        return complete_prompt
    
    def _get_weekly_donations_context(self) -> str:
        """Get minimal context about users who donated this week using server-specific personality."""
        try:
            weekly_donors = self.roles_db.get_weekly_donations_summary()

            # Get messages from server-specific personality
            personality = _get_personality(self.server_id)
            weekly_messages = personality.get('roles', {}).get('banker', {}).get('subroles', {}).get('beggar', {}).get('weekly_donations', {})
            
            if not weekly_donors:
                return weekly_messages.get('no_donations', '')
            
            total_weekly = sum(donor['weekly_amount'] for donor in weekly_donors)
            donor_count = len(weekly_donors)
            
            # Build context using Putre's messages
            context = weekly_messages.get('with_donations', ' Weekly fund: {total} gold from {count} donors:').format(
                total=total_weekly, 
                count=donor_count
            )
            
            donor_format = weekly_messages.get('donor_format', '{name}({amount}g)')
            
            for donor in weekly_donors[:3]:  # Show top 3 only
                context += f" {donor_format.format(name=donor['donor_name'], amount=donor['weekly_amount'])},"
            
            return context.rstrip(",") + "."
            
        except Exception as e:
            logger.error(f"Error getting weekly donations context: {e}")
            return weekly_messages.get('error', ' Weekly donations: Data unavailable.') if 'weekly_messages' in locals() else " Weekly donations: Data unavailable."
    
    def _get_golden_rules(self) -> str:
        """Get golden rules for the begging task."""
        # Get golden rules from server-specific personality dynamically
        personality = _get_personality(self.server_id)
        golden_rules_list = personality.get('roles', {}).get('banker', {}).get('subroles', {}).get('beggar', {}).get('golden_rules', [])

        if not golden_rules_list:
            # Use neutral English fallback from MISSION_CONFIG
            from .beggar import MISSION_CONFIG
            golden_rules_list = MISSION_CONFIG.get('golden_rules', [
                "1. CHARACTER STYLE: Maintain consistent character voice and expressions",
                "2. PERSUASION: Convince users to donate gold for the stated reason", 
                "3. PUBLIC: Speak in public channel so everyone hears your request",
                "4. CONTEXT: Respond to current channel atmosphere if relevant",
                "5. AUTHENTICITY: Act like a real character, not like a bot",
                "6. LENGTH: 3-8 sentences (150-400 characters)",
                "7. DIRECT: Get straight to the point with your gold request",
                "8. EMOTIONAL: Use emotional appeals if necessary"
            ])
        
        return "\n".join(golden_rules_list)
    
    def get_task_status(self) -> Dict[str, Any]:
        """Get current task status."""
        config = self.config.get_config()
        reason_status = self.config.get_reason_status()
        
        return {
            'enabled': config.get('enabled', False),
            'frequency_hours': config.get('frequency_hours', 24),
            'current_reason': reason_status['current_reason'],
            'reason_days_active': reason_status['days_active'],
            'should_change_reason': reason_status['should_change_reason'],
            'target_channel_id': config.get('target_channel_id'),
            'auto_channel_selection': config.get('auto_channel_selection', True),
            'minigame_enabled': config.get('minigame_enabled', True),
            'last_execution': self._get_last_execution_info()
        }
    
    def _get_last_execution_info(self) -> Dict[str, Any]:
        """Get information about the last task execution."""
        try:
            recent_requests = []
            return {
                'last_execution': None,
                'total_executions': 0,
                'success_rate': 0.0
            }
        except Exception:
            return {
                'last_execution': None,
                'total_executions': 0,
                'success_rate': 0.0
            }


# Task execution interface for agent_engine.py
async def execute_beggar_task(server_id: str, bot_instance=None) -> bool:
    """Interface function for agent_engine.py to execute beggar task."""
    try:
        task = BeggarTask(server_id=server_id, bot_instance=bot_instance)
        return await task.execute_task()
    except Exception as e:
        logger.error(f"Error in execute_beggar_task for server {server_id}: {e}")
        return False


# =============================================================================
# BEGGAR MINIGAME - Moved from beggar_minigame.py
# =============================================================================

import random as _random
from datetime import datetime as _datetime


class BeggarMinigame:
    """Minigame system for beggar reason changes."""

    def __init__(self, server_id: str):
        self.server_id = server_id
        self.config = get_beggar_config(server_id)
        self.roles_db = get_roles_db_instance(server_id)

    async def trigger_reason_change_minigame(self, old_reason: str, new_reason: str) -> bool:
        """Trigger minigame when reason changes."""
        try:
            if not self.config.is_minigame_enabled():
                return False

            fund_balance = self._get_fund_balance()
            if fund_balance <= 0:
                logger.info(f"No gold in beggar fund for minigame in server {self.server_id}")
                return False

            participants = self._get_participants()
            if not participants:
                logger.info(f"No participants for minigame in server {self.server_id}")
                return False

            result = self._execute_minigame(old_reason, new_reason, participants, fund_balance, self.server_id)

            if result['success']:
                await self._process_minigame_results(result)

            return result['success']

        except Exception as e:
            logger.error(f"Error in reason change minigame: {e}")
            return False

    def _get_fund_balance(self) -> int:
        """Get current beggar fund balance."""
        try:
            from roles.banker.banker_db import get_banker_roles_db_instance
            banker_db = get_banker_roles_db_instance(self.server_id)
            if banker_db:
                return banker_db.get_balance("beggar_fund")
        except Exception as e:
            logger.error(f"Error getting fund balance: {e}")
        return 0

    def _get_participants(self) -> List[Dict[str, Any]]:
        """Get list of users who donated to the beggar."""
        try:
            leaderboard = self.roles_db.get_beggar_leaderboard(self.server_id, limit=50, weekly_only=True)
            participants = [p for p in leaderboard if p['total_donated'] > 0]
            return participants
        except Exception as e:
            logger.error(f"Error getting participants: {e}")
            return []

    def _execute_minigame(self, old_reason: str, new_reason: str, participants: List[Dict[str, Any]], fund_balance: int, server_id: str = None) -> Dict[str, Any]:
        """Execute the minigame logic."""
        try:
            total_donations = sum(p['total_donated'] for p in participants)
            general_multiplier = self._calculate_general_multiplier()
            participant_results = self._apply_general_multiplier(participants, general_multiplier)
            narrative = self._generate_minigame_narrative(old_reason, new_reason, participants, general_multiplier, participant_results, server_id)

            return {
                'success': True,
                'old_reason': old_reason,
                'new_reason': new_reason,
                'participants': participants,
                'general_multiplier': general_multiplier,
                'participant_results': participant_results,
                'fund_balance': fund_balance,
                'total_donations': total_donations,
                'narrative': narrative,
                'timestamp': _datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Error executing minigame: {e}")
            return {'success': False}

    def _calculate_general_multiplier(self) -> Dict[str, Any]:
        """Calculate a general multiplier for this minigame runtime."""
        random_choice = _random.random()
        if random_choice < 0.5:
            result_type = "nothing"
            multiplier = 0.0
            description = "No gold returns for anyone this time"
        elif random_choice < 0.8:
            result_type = "return"
            multiplier = 1.0
            description = "All participants get their donations back"
        else:
            result_type = "double"
            multiplier = 2.0
            description = "All participants get double their donations back"

        logger.info(f"General multiplier: {result_type} (x{multiplier}) - {description}")

        return {'multiplier': multiplier, 'result_type': result_type, 'description': description}

    def _apply_general_multiplier(self, participants: List[Dict[str, Any]], general_multiplier: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Apply the general multiplier to all participants."""
        multiplier = general_multiplier['multiplier']
        result_type = general_multiplier['result_type']
        participant_results = []

        for participant in participants:
            user_id = participant['user_id']
            user_name = participant['user_name']
            total_donated = participant['total_donated']
            total_received = int(total_donated * multiplier)

            participant_results.append({
                'user_id': user_id,
                'user_name': user_name,
                'total_donated': total_donated,
                'multiplier': multiplier,
                'total_received': total_received,
                'result_type': result_type
            })

            if total_received > 0:
                logger.info(f"{user_name} receives {total_received} gold (general {result_type})")
            else:
                logger.info(f"{user_name} receives nothing (general {result_type})")

        return participant_results

    def _generate_minigame_narrative(self, old_reason: str, new_reason: str, participants: List[Dict[str, Any]], general_multiplier: Dict[str, Any], participant_results: List[Dict[str, Any]], server_id: str = None) -> str:
        """Generate narrative for the minigame using LLM."""
        server_to_use = server_id or self.server_id
        personality = _get_personality(server_to_use) if server_to_use else _get_personality()

        task_prompt_template = personality.get('roles', {}).get('banker', {}).get('subroles', {}).get('beggar', {}).get('minigame_prompt', '')
        if not task_prompt_template:
            task_prompt_template = "Generate a narrative celebrating the reason change from '{old_reason}' to '{new_reason}'."

        gold = personality.get('general', {}).get('gold', "gold")
        receives = personality.get('general', {}).get('receives', "receives")

        participants_text = "\n".join([f"- {p['user_name']}: {p['total_donated']} {gold}" for p in participants[:10]])
        multiplier_text = f"{general_multiplier['description']}"
        results_text = "\n".join([f"- {r['user_name']}: {receives} {r['total_received']} {gold}" for r in participant_results])

        from agent_mind import _build_prompt_memory_block
        memory_section = _build_prompt_memory_block()

        golden_rules_template = personality.get('roles', {}).get('banker', {}).get('subroles', {}).get('beggar', {}).get('minigame_golden_rules', '')
        if not golden_rules_template:
            golden_rules_template = "Use emotional expressions and character language. Be grateful to participants."

        labels = personality.get('roles', {}).get('banker', {}).get('subroles', {}).get('beggar', {}).get('minigame_labels', {})
        context_label = labels.get('context_label', '=== CONTEXT ===')
        participants_label = labels.get('participants_label', 'PARTICIPANTS:')
        title_multiplier = labels.get('title_multiplier', 'RESULT:')
        participant_results_label = labels.get('participant_results_label', 'RESULTS:')

        prompt = f"""{memory_section}
{task_prompt_template.format(old_reason=old_reason, new_reason=new_reason)}

{context_label}
{participants_label}
{participants_text}

{title_multiplier}
{multiplier_text}

{participant_results_label}
{results_text}

{golden_rules_template}
"""

        system_instruction = _build_system_prompt(personality, self.server_id)

        try:
            from agent_mind import call_llm
            response = call_llm(
                system_instruction=system_instruction,
                prompt=prompt,
                async_mode=False,
                call_type="beggar_minigame",
                critical=False,
                temperature=0.95,
                server_id=server_id
            )

            if response and len(response.strip()) > 10:
                return response
            else:
                logger.warning("Empty or short response from LLM, using fallback")
                return self._get_fallback_narrative(new_reason, participants, general_multiplier)
        except Exception as e:
            logger.error(f"Error generating minigame narrative: {e}")
            return self._get_fallback_narrative(new_reason, participants, general_multiplier)

    async def _process_minigame_results(self, result: Dict[str, Any], fallback_channel: Optional[discord.abc.Messageable] = None) -> None:
        """Process minigame results and update databases."""
        try:
            self._award_gold_from_general_multiplier(result['participant_results'])

            if self.config.is_relationship_improvements_enabled():
                self._update_relationship_improvements(result['participants'], result['old_reason'])

            self.roles_db.reset_beggar_weekly_cycle(self.server_id)
            self._log_minigame_results(result)
            await self.send_narrative_to_channel(result['narrative'], fallback_channel=fallback_channel)

        except Exception as e:
            logger.error(f"Error processing minigame results: {e}")

    def _award_gold_from_general_multiplier(self, participant_results: List[Dict[str, Any]]) -> None:
        """Award gold returns to participants and empty the fund."""
        try:
            from roles.banker.banker_db import get_banker_roles_db_instance
            banker_db = get_banker_roles_db_instance(self.server_id)
            if not banker_db:
                return

            total_distributed = 0
            for result in participant_results:
                user_id = result['user_id']
                user_name = result['user_name']
                total_received = result['total_received']

                if total_received > 0:
                    banker_db.update_balance(
                        "beggar_fund", "Beggar Fund",
                        -total_received, "BEGGAR_MINIGAME_PAYOUT", "Minigame payout"
                    )
                    banker_db.update_balance(
                        user_id, user_name,
                        total_received, "BEGGAR_MINIGAME_PAYOUT", "Minigame winnings"
                    )
                    total_distributed += total_received
                    logger.info(f"Awarded {total_received} gold to {user_name}")

            remaining_balance = banker_db.get_balance("beggar_fund")
            if remaining_balance > 0:
                logger.info(f"Emptying remaining {remaining_balance} gold from beggar fund")
                banker_db.update_balance(
                    "beggar_fund", "Beggar Fund",
                    -remaining_balance, "BEGGAR_FUND_RESET", "Fund emptied on reason change"
                )

        except Exception as e:
            logger.error(f"Error awarding gold: {e}")

    def _update_relationship_improvements(self, participants: List[Dict[str, Any]], reason_context: str) -> None:
        """Update relationship improvements for participants."""
        try:
            from agent_db import get_global_db
            from agent_mind import call_llm, _build_prompt_memory_block

            db_instance = get_global_db(server_id=self.server_id)

            for participant in participants:
                user_id = participant['user_id']
                user_name = participant['user_name']

                try:
                    relationship_state = db_instance.get_user_relationship_memory(user_id)
                    current_summary = relationship_state.get("summary", "")

                    task = self._build_relationship_improvement_task(user_name, current_summary, reason_context)
                    server_personality = _get_personality(self.server_id) if self.server_id else _get_personality()
                    system_instruction = _build_system_prompt(server_personality, self.server_id)

                    response = call_llm(
                        system_instruction=system_instruction,
                        prompt=task,
                        async_mode=False,
                        call_type="relationship_improvement",
                        critical=False,
                        temperature=0.9,
                        server_id=self.server_id
                    )

                    if response and len(response.strip()) > 10:
                        metadata = {
                            "user_name": user_name,
                            "source": "beggar_minigame_improvement",
                            "improvement_level": "flat",
                            "generated_at": _datetime.now().isoformat()
                        }
                        db_instance.upsert_user_relationship_memory(
                            user_id, response,
                            last_interaction_at=_datetime.now().isoformat(),
                            metadata=metadata
                        )
                        logger.info(f"Updated relationship for {user_name}")

                except Exception as e:
                    logger.error(f"Error updating relationship for {user_name}: {e}")

        except Exception as e:
            logger.error(f"Error in relationship improvements: {e}")

    def _build_relationship_improvement_task(self, user_name: str, current_summary: str, reason_context_value: str) -> str:
        """Build task prompt for relationship improvement."""
        from agent_mind import _build_prompt_memory_block
        memory_section = _build_prompt_memory_block()

        if not current_summary or not current_summary.strip():
            current_summary = self._get_relationship_memory_fallback(user_name)

        improvement_task_template = "Update relationship summary based on beggar minigame participation."
        golden_rules_template = "Maintain bot personality. Show gratitude. Keep concise."
        reason_context = f"Collection reason: {reason_context_value}"

        task = f"""{memory_section}
PREVIOUS RELATIONSHIP SUMMARY:
{current_summary}

{reason_context}
{improvement_task_template} {user_name}
{golden_rules_template}
"""
        return task

    def _get_relationship_memory_fallback(self, user_name: str) -> str:
        """Get fallback relationship memory when no previous summary exists."""
        try:
            personality = _get_personality(self.server_id)
            template = personality.get("synthesis_paragraphs", {})
            fallbacks = template.get("fallbacks", {})
            fallback = fallbacks.get("relationship_memory", "")
            if isinstance(fallback, str) and fallback.strip():
                return fallback.replace("{user_name}", user_name or "human").strip()
        except Exception:
            pass

        template = PERSONALITY.get("synthesis_paragraphs", {})
        fallbacks = template.get("fallbacks", {})
        fallback = fallbacks.get("relationship_memory", "")
        if isinstance(fallback, str) and fallback.strip():
            return fallback.replace("{user_name}", user_name or "human").strip()
        return f"The character does not yet have a clear opinion about {user_name or 'this human'}."

    def _log_minigame_results(self, result: Dict[str, Any]) -> None:
        """Log minigame results for historical purposes."""
        try:
            logger.info(f"Minigame completed in server {self.server_id}:")
            logger.info(f"  Reason change: {result['old_reason']} -> {result['new_reason']}")
            logger.info(f"  Participants: {len(result['participants'])}")
            logger.info(f"  Multiplier: {result['general_multiplier']['result_type']} (x{result['general_multiplier']['multiplier']})")
            logger.info(f"  Total bonus: {sum(r['total_received'] for r in result['participant_results'])}")
        except Exception as e:
            logger.error(f"Error logging minigame results: {e}")

    async def send_narrative_to_channel(self, narrative: str, fallback_channel: Optional[discord.abc.Messageable] = None) -> None:
        """Send the minigame narrative to the target channel."""
        try:
            from discord_bot.agent_discord import get_bot_instance
            bot_instance = get_bot_instance()
            beggar_task = BeggarTask(self.server_id, bot_instance)
            target_channel = await beggar_task._get_target_channel()

            if not target_channel and fallback_channel:
                target_channel = fallback_channel

            if target_channel:
                try:
                    await target_channel.send(narrative)
                    logger.info(f"Minigame narrative sent to channel {target_channel.name}")
                except Exception as send_error:
                    logger.error(f"Failed to send narrative: {send_error}")
            else:
                logger.warning(f"No target channel for minigame in server {self.server_id}")

        except Exception as e:
            logger.error(f"Error sending minigame narrative: {e}")

    async def force_weekly_minigame(self, fallback_channel: Optional[discord.abc.Messageable] = None) -> Dict[str, Any]:
        """Force trigger the weekly beggar minigame regardless of reason change."""
        try:
            logger.info(f"Force triggering weekly beggar minigame for server {self.server_id}")

            if not self.config.is_minigame_enabled():
                return {'success': False, 'reason': 'Minigame is disabled', 'message': 'Minigame is disabled in configuration'}

            current_reason = self.config.get_current_reason() or "weekly collection"
            old_reason = current_reason
            new_reason = self.config.select_new_reason()

            fund_balance = self._get_fund_balance()
            if fund_balance <= 0:
                return {'success': False, 'reason': 'No gold', 'message': f'No gold in beggar fund (balance: {fund_balance})'}

            participants = self._get_participants()
            if not participants:
                return {'success': False, 'reason': 'No participants', 'message': 'No donors found in the system'}

            result = self._execute_minigame(old_reason, new_reason, participants, fund_balance, self.server_id)
            result['forced'] = True
            result['force_type'] = 'weekly_manual'

            if result['success']:
                await self._process_minigame_results(result, fallback_channel=fallback_channel)
                general_mult = result['general_multiplier']
                return {
                    'success': True,
                    'message': f'Weekly Beggar Minigame Forced! {old_reason} -> {new_reason}. {len(participants)} participants. {general_mult["description"]} (x{general_mult["multiplier"]})',
                    'details': result
                }
            else:
                return {'success': False, 'reason': 'Execution failed', 'message': 'Failed to execute minigame'}

        except Exception as e:
            logger.error(f"Error forcing weekly beggar minigame: {e}")
            return {'success': False, 'reason': f'Exception: {str(e)}', 'message': f'Error: {str(e)}'}

    def _get_fallback_narrative(self, new_reason: str, participants: List[Dict[str, Any]], general_multiplier: Dict[str, Any]) -> str:
        """Generate a fallback narrative when LLM fails."""
        participant_count = len(participants)
        multiplier_desc = general_multiplier['description']
        return f"Reason changed to '{new_reason}'! Thanks to the {participant_count} donors! {multiplier_desc}. Everyone improved their relationship!"
