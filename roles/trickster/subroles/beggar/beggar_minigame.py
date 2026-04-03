"""
Beggar Minigame System
Handles minigames when reason changes, including relationship improvements and gold returns
"""

import random
from typing import Dict, List, Any, Optional
from datetime import datetime

import discord

from agent_logging import get_logger
from agent_mind import call_llm
from agent_engine import _build_system_prompt, PERSONALITY
from agent_roles_db import get_roles_db_instance

# Import bot display name for dynamic replacement
try:
    from discord_bot.discord_core_commands import _bot_display_name
except ImportError:
    # Fallback if discord is not available
    _bot_display_name = "Bot"

from .beggar_config import get_beggar_config

logger = get_logger('beggar_minigame')


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
            
            # Get current fund from banker
            fund_balance = self._get_fund_balance()
            
            if fund_balance <= 0:
                logger.info(f"No gold in beggar fund for minigame in server {self.server_id}")
                return False
            
            # Get participants (users who donated)
            participants = self._get_participants()
            
            if not participants:
                logger.info(f"No participants for minigame in server {self.server_id}")
                return False
            
            # Execute minigame
            result = self._execute_minigame(old_reason, new_reason, participants, fund_balance)
            
            # Process results
            if result['success']:
                await self._process_minigame_results(result)
            
            return result['success']
            
        except Exception as e:
            logger.error(f"Error in reason change minigame: {e}")
            return False
    
    def _get_fund_balance(self) -> int:
        """Get current beggar fund balance."""
        try:
            # Import banker to get fund balance
            from roles.banker.banker_db import get_banker_roles_db_instance
            
            banker_db = get_banker_roles_db_instance(self.server_id)
            if banker_db:
                return banker_db.get_balance("beggar_fund", self.server_id)
        except Exception as e:
            logger.error(f"Error getting fund balance: {e}")
        
        return 0
    
    def _get_participants(self) -> List[Dict[str, Any]]:
        """Get list of users who donated to the beggar."""
        try:
            # Get leaderboard from roles database
            leaderboard = self.roles_db.get_beggar_leaderboard(self.server_id, limit=50, weekly_only=True)
            
            # Filter users with meaningful donations
            participants = [
                participant for participant in leaderboard
                if participant['total_donated'] > 0
            ]
            
            return participants
            
        except Exception as e:
            logger.error(f"Error getting participants: {e}")
            return []
    
    def _execute_minigame(self, old_reason: str, new_reason: str, participants: List[Dict[str, Any]], fund_balance: int) -> Dict[str, Any]:
        """Execute the minigame logic."""
        try:
            # Calculate minigame parameters
            total_donations = sum(p['total_donated'] for p in participants)
            
            # Calculate general multiplier for this minigame runtime
            general_multiplier = self._calculate_general_multiplier()
            
            # Apply general multiplier to all participants
            participant_results = self._apply_general_multiplier(participants, general_multiplier)
            
            # Generate narrative (all participants get flat relationship improvement)
            narrative = self._generate_minigame_narrative(old_reason, new_reason, participants, general_multiplier, participant_results)
            
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
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error executing minigame: {e}")
            return {'success': False}
    
    def _calculate_general_multiplier(self) -> Dict[str, Any]:
        """Calculate a general multiplier for this minigame runtime that applies to all participants."""
        # Probability distribution for general multiplier:
        # 50% nothing, 30% return donation, 20% double donation
        random_choice = random.random()
        if random_choice < 0.5:
            # 50% chance - give nothing to all participants
            result_type = "nothing"
            multiplier = 0.0
            description = self._get_minigame_description("nothing")
        elif random_choice < 0.8:
            # 30% chance - return donated amount to all participants
            result_type = "return"
            multiplier = 1.0
            description = self._get_minigame_description("return")
        else:
            # 20% chance - return double the donated amount to all participants
            result_type = "double"
            multiplier = 2.0
            description = self._get_minigame_description("double")
        
        logger.info(f"General multiplier for this minigame: {result_type} (multiplier: {multiplier}) - {description}")
        
        return {
            'multiplier': multiplier,
            'result_type': result_type,
            'description': description
        }
    
    def _apply_general_multiplier(self, participants: List[Dict[str, Any]], general_multiplier: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Apply the general multiplier to all participants."""
        multiplier = general_multiplier['multiplier']
        result_type = general_multiplier['result_type']
        
        participant_results = []
        
        for participant in participants:
            user_id = participant['user_id']
            user_name = participant['user_name']
            total_donated = participant['total_donated']
            
            # Apply the general multiplier to this participant
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
                logger.info(f"{user_name} receives {total_received} gold (general {result_type} multiplier applied)")
            else:
                logger.info(f"{user_name} receives nothing (general {result_type} multiplier applied)")
        
        return participant_results
    
    def _generate_minigame_narrative(self, old_reason: str, new_reason: str, participants: List[Dict[str, Any]], general_multiplier: Dict[str, Any], participant_results: List[Dict[str, Any]]) -> str:
        """Generate narrative for the minigame using LLM."""
        # Get task prompt from personality dynamically
        task_prompt_template = PERSONALITY.get('roles', {}).get('trickster', {}).get('subroles', {}).get('beggar', {}).get('minigame_prompt', '')
        gold = PERSONALITY.get('general', {}).get('gold', "gold")
        receives = PERSONALITY.get('general', {}).get('receives', "receives")
        if not task_prompt_template:
            task_prompt_template = "You are beggar recaudation. You just changed your reason for asking for gold from '{old_reason}' to '{new_reason}'. Generate a narrative message celebrating this change with participants and the general multiplier applied to everyone."
        
        # Build context for LLM
        participants_text = "\n".join([
            f"- {p['user_name']}: {p['total_donated']} {gold}"
            for p in participants[:10]  # Limit to top 10
        ])
        
        # Build general multiplier text
        multiplier_text = f"{general_multiplier['description']})"
        
        # Build participant results text
        results_text = "\n".join([
            f"- {r['user_name']}: {receives} {r['total_received']} {gold}"
            for r in participant_results
        ])
        
        # Get memory section
        from agent_mind import _build_prompt_memory_block
        memory_section = _build_prompt_memory_block()
        
        # Get golden rules from personality
        golden_rules_template = PERSONALITY.get('roles', {}).get('trickster', {}).get('subroles', {}).get('beggar', {}).get('minigame_golden_rules', '')
        
        if not golden_rules_template:
            golden_rules_template = """
            === GOLDEN RULES ===
- Use emotional expressions and character language
- Be grateful and appreciative to participants
- Mention the reason change clearly
- Announce the general multiplier result applied to everyone
- Be between 150-400 characters
                """.strip()
        
        # Get labels from prompts.json
        labels = PERSONALITY.get('roles', {}).get('trickster', {}).get('subroles', {}).get('beggar', {}).get('minigame_labels', {})
        
        context_label = labels.get('context_label', '=== CONTEXT ===')
        participants_label = labels.get('participants_label', 'PARTICIPANTS (donors):')
        title_multiplier = labels.get('title_multiplier', 'PROJECT RESULT:')
        participant_results_label = labels.get('participant_results_label', 'PARTICIPANT RESULTS:')
        
        # Build complete prompt
        prompt = f"""
{memory_section}
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
        
        system_instruction = _build_system_prompt(PERSONALITY)
        
        try:
            response = call_llm(
                system_instruction=system_instruction,
                prompt=prompt,
                async_mode=False,
                call_type="beggar_minigame",
                critical=False,
                temperature=0.95
            )
            
            if response and len(response.strip()) > 10:
                return response
            else:
                logger.warning("Empty or too short response from LLM, using fallback")
                return self._get_fallback_narrative(new_reason, participants, general_multiplier)
                
        except Exception as e:
            logger.error(f"Error generating minigame narrative: {e}")
            return self._get_fallback_narrative(new_reason, participants, general_multiplier)
    
    async def _process_minigame_results(self, result: Dict[str, Any], fallback_channel: Optional[discord.abc.Messageable] = None) -> None:
        """Process minigame results and update databases."""
        try:
            # Award gold to participants based on general multiplier
            self._award_gold_from_general_multiplier(result['participant_results'])
            
            # Update relationship paragraphs if enabled (all participants get flat improvement)
            if self.config.is_relationship_improvements_enabled():
                self._update_relationship_improvements(result['participants'], result['old_reason'])
            
            self.roles_db.reset_beggar_weekly_cycle(self.server_id)
            
            # Log the minigame results
            self._log_minigame_results(result)
            
            # Send narrative to channel after all processing is complete
            await self.send_narrative_to_channel(result['narrative'], fallback_channel=fallback_channel)
            
        except Exception as e:
            logger.error(f"Error processing minigame results: {e}")
    
    def _award_gold_from_general_multiplier(self, participant_results: List[Dict[str, Any]]) -> None:
        """Award gold returns to participants based on the general multiplier and empty the fund completely."""
        try:
            from roles.banker.banker_db import get_banker_roles_db_instance
            
            banker_db = get_banker_roles_db_instance(self.server_id)
            if not banker_db:
                return
            
            # First, award the gold based on general multiplier
            total_distributed = 0
            for result in participant_results:
                user_id = result['user_id']
                user_name = result['user_name']
                total_received = result['total_received']
                result_type = result['result_type']
                
                if total_received > 0:
                    # Transfer gold from beggar_fund to user
                    banker_db.update_balance(
                        "beggar_fund", "Beggar Fund", self.server_id, "Server",
                        -total_received, "BEGGAR_MINIGAME_PAYOUT", "Minigame payout to user"
                    )
                    
                    banker_db.update_balance(
                        user_id, user_name, self.server_id, "Server",
                        total_received, "BEGGAR_MINIGAME_PAYOUT", "Minigame winnings"
                    )
                    
                    total_distributed += total_received
                    logger.info(f"Awarded {total_received} gold to {user_name} (general {result_type} multiplier)")
                else:
                    logger.info(f"{user_name} received nothing (general {result_type} multiplier)")
            
            # Now empty the remaining fund balance completely
            remaining_balance = banker_db.get_balance("beggar_fund", self.server_id)
            if remaining_balance > 0:
                logger.info(f"Emptying remaining {remaining_balance} gold from beggar fund (reason change reset)")
                
                # Remove all remaining gold from the fund (it disappears from the system)
                banker_db.update_balance(
                    "beggar_fund", "Beggar Fund", self.server_id, "Server",
                    -remaining_balance, "BEGGAR_FUND_RESET", "Fund emptied on reason change"
                )
                
                logger.info(f"Beggar fund emptied: {remaining_balance} gold removed from system")
                
                # Verify fund is empty
                final_balance = banker_db.get_balance("beggar_fund", self.server_id)
                logger.info(f"Final beggar fund balance after reset: {final_balance}")
                
        except Exception as e:
            logger.error(f"Error awarding gold from general multiplier: {e}")
    
    def _update_relationship_improvements(self, participants: List[Dict[str, Any]], reason_context: str) -> None:
        """Update relationship improvements for participants."""
        try:
            from agent_mind import call_llm
            from agent_engine import _build_system_prompt, PERSONALITY
            from agent_db import get_global_db
            from agent_runtime import get_active_server_name
            
            server_name = get_active_server_name()
            if not server_name:
                logger.warning("No server context available for relationship updates")
                return
            
            db_instance = get_global_db(server_name=server_name)
            
            for participant in participants:
                user_id = participant['user_id']
                user_name = participant['user_name']
                
                try:
                    # Get current relationship summary
                    relationship_state = db_instance.get_user_relationship_memory(user_id)
                    current_summary = relationship_state.get("summary", "")
                    
                    # Build improvement task (flat improvement for all)
                    task = self._build_relationship_improvement_task(
                        user_name, 
                        current_summary,
                        reason_context
                    )
                    
                    # Get system instruction
                    system_instruction = _build_system_prompt(PERSONALITY)
                    
                    # Call LLM to update relationship
                    response = call_llm(
                        system_instruction=system_instruction,
                        prompt=task,
                        async_mode=False,
                        call_type="relationship_improvement",
                        critical=False,
                        temperature=0.9
                    )
                    
                    if response and len(response.strip()) > 10:
                        # Update relationship memory with new summary
                        metadata = {
                            "user_name": user_name,
                            "source": "beggar_minigame_improvement",
                            "improvement_level": "flat",
                            "is_winner": False,
                            "generated_at": datetime.now().isoformat()
                        }
                        
                        db_instance.upsert_user_relationship_memory(
                            user_id,
                            response,
                            last_interaction_at=datetime.now().isoformat(),
                            metadata=metadata
                        )
                        
                        logger.info(f"Updated relationship for {user_name}: flat improvement")
                    else:
                        logger.warning(f"Failed to generate relationship improvement for {user_name}")
                        
                except Exception as e:
                    logger.error(f"Error updating relationship for {user_name}: {e}")
                    
        except Exception as e:
            logger.error(f"Error in relationship improvements system: {e}")
    
    def _build_relationship_improvement_task(self, user_name: str, current_summary: str, reason_context_value: str) -> str:
        """Build task prompt for relationship improvement."""
        # Get the correct label for previous relationship summary
        synthesis_labels = PERSONALITY.get('synthesis_paragraphs', {})
        previous_relationship_label = synthesis_labels.get('previous_relationship_summary', 'PREVIOUS RELATIONSHIP SUMMARY:')
        
        from agent_mind import _build_prompt_memory_block
        memory_section = _build_prompt_memory_block()

        # Handle case when there's no previous summary - create initial one
        if not current_summary or not current_summary.strip():
            current_summary = self._get_relationship_memory_fallback(user_name)
        
        # Get improvement task from personality
        improvement_task_template = PERSONALITY.get('roles', {}).get('trickster', {}).get('subroles', {}).get('beggar', {}).get('relationship_improvement_task', '')
        
        if not improvement_task_template:
            improvement_task_template = "Update relationship summary based on beggar minigame participation."
        
        # Get golden rules for relationship improvements
        golden_rules_template = PERSONALITY.get('roles', {}).get('trickster', {}).get('subroles', {}).get('beggar', {}).get('relationship_improvement_rules', '')
        
        if not golden_rules_template:
            golden_rules_template = """
=== GOLDEN RULES ===
- Maintain the bot personality
- Show gratitude for participation
- Keep summary concise and meaningful
- Use authentic personality language 
            """.strip()
        
        # Get reason context from prompts.json with English fallback
        reason_context_template = PERSONALITY.get('roles', {}).get('trickster', {}).get('subroles', {}).get('beggar', {}).get('relationship_reason_context', '')
        
        if not reason_context_template:
            reason_context_template = f"=== BEGGAR COLLECTION REASON ===\nThis week {_bot_display_name} was collecting money for: {{reason}}"
        
        # Format the reason context with the previous weekly reason
        reason_context = reason_context_template.format(reason=reason_context_value)
        
        # Build complete task
        task = f"""
{memory_section}

{previous_relationship_label}
{current_summary}

{reason_context}
{improvement_task_template}{user_name}
{golden_rules_template}
"""
        
        return task
    
    def _get_relationship_memory_fallback(self, user_name: str) -> str:
        """Get fallback relationship memory when no previous summary exists."""
        template = PERSONALITY.get("synthesis_paragraphs", {})
        fallbacks = template.get("fallbacks", {})
        fallback = fallbacks.get("relationship_memory", "")
        if isinstance(fallback, str) and fallback.strip():
            return fallback.replace("{user_name}", user_name or "human").strip()
        return f"The character does not yet have a clear opinion about {user_name or 'this human'}."
    
    def _log_minigame_results(self, result: Dict[str, Any]) -> None:
        """Log minigame results for historical purposes."""
        try:
            # This could store results in a database for future reference
            logger.info(f"Minigame completed in server {self.server_id}:")
            logger.info(f"  Reason change: {result['old_reason']} -> {result['new_reason']}")
            logger.info(f"  Participants: {len(result['participants'])}")
            logger.info(f"  General multiplier: {result['general_multiplier']['result_type']} (x{result['general_multiplier']['multiplier']})")
            logger.info(f"  Total bonus gold: {sum(r['total_received'] for r in result['participant_results'])}")
            
        except Exception as e:
            logger.error(f"Error logging minigame results: {e}")
    
    async def send_narrative_to_channel(self, narrative: str, fallback_channel: Optional[discord.abc.Messageable] = None) -> None:
        """Send the minigame narrative to the target channel."""
        try:
            # Import here to avoid circular imports
            from .beggar_task import BeggarTask
            from discord_bot.agent_discord import get_bot_instance
            
            # Get bot instance
            bot_instance = get_bot_instance()
            
            # Get target channel from beggar task
            beggar_task = BeggarTask(self.server_id, bot_instance)
            target_channel = await beggar_task._get_target_channel()
            if not target_channel and fallback_channel:
                target_channel = fallback_channel
            
            if target_channel:
                # Send the narrative to the channel
                try:
                    await target_channel.send(narrative)
                    logger.info(f"Minigame narrative sent to channel {target_channel.name}: {narrative[:100]}...")
                except Exception as send_error:
                    logger.error(f"Failed to send narrative to channel {target_channel.name}: {send_error}")
            else:
                logger.warning(f"No target channel available for minigame narrative in server {self.server_id}")
                
        except Exception as e:
            logger.error(f"Error sending minigame narrative to channel: {e}")
    
    def get_minigame_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get history of recent minigames."""
        # TODO: Implement minigame history storage and retrieval
        return []
    
    async def force_weekly_minigame(self, fallback_channel: Optional[discord.abc.Messageable] = None) -> Dict[str, Any]:
        """Force trigger the weekly beggar minigame regardless of reason change.
        
        This method manually triggers the minigame system for administrative purposes,
        using the current reason as both old and new reason to simulate a weekly cycle.
        
        Returns:
            Dict with success status and details about the forced minigame
        """
        try:
            logger.info(f"Force triggering weekly beggar minigame for server {self.server_id}")
            
            # Check if minigame is enabled
            if not self.config.is_minigame_enabled():
                return {
                    'success': False,
                    'reason': 'Minigame is disabled in configuration',
                    'message': '❌ Beggar minigame is disabled. Enable it first with !trickster beggar minigame enable'
                }
            
            # Get current reason and select a new one
            current_reason = self.config.get_current_reason() or "weekly collection"
            old_reason = current_reason
            new_reason = self.config.select_new_reason()
            
            logger.info(f"Force minigame reason change: '{old_reason}' -> '{new_reason}'")
            
            # Check if reason actually changed
            if old_reason == new_reason:
                logger.warning(f"Reason did not change: still '{new_reason}'. This may indicate only one reason available or selection issue.")
            
            # Get fund balance
            fund_balance = self._get_fund_balance()
            
            if fund_balance <= 0:
                return {
                    'success': False,
                    'reason': 'No gold in beggar fund',
                    'message': f'❌ No gold available in beggar fund (current balance: {fund_balance})'
                }
            
            # Get participants
            participants = self._get_participants()
            
            if not participants:
                return {
                    'success': False,
                    'reason': 'No participants available',
                    'message': '❌ No donors found in the system. Need participants for minigame.'
                }
            
            # Execute minigame with the new reason (actual reason change)
            result = self._execute_minigame(old_reason, new_reason, participants, fund_balance)
            
            # Add forced flag to result
            result['forced'] = True
            result['force_type'] = 'weekly_manual'
            
            # Process results if successful
            if result['success']:
                await self._process_minigame_results(result, fallback_channel=fallback_channel)
                
                general_mult = result['general_multiplier']
                
                return {
                    'success': True,
                    'message': f'✅ **Weekly Beggar Minigame Forced Successfully!**\n\n'
                             f'🔄 **Reason Change:** {old_reason} → {new_reason}\n'
                             f'👥 **Participants:** {len(participants)}\n'
                             f'💰 **Fund Balance:** {fund_balance:,} gold\n'
                             f'🎲 **General Multiplier:** {general_mult["description"]} (x{general_mult["multiplier"]})\n'
                             f'📊 **Results Processed:** Fund completely emptied (reason change reset)',
                    'details': result
                }
            else:
                return {
                    'success': False,
                    'reason': 'Minigame execution failed',
                    'message': '❌ Failed to execute the minigame. Check logs for details.'
                }
                
        except Exception as e:
            logger.error(f"Error forcing weekly beggar minigame: {e}")
            return {
                'success': False,
                'reason': f'Exception: {str(e)}',
                'message': f'❌ Error forcing minigame: {str(e)}'
            }

    def _get_fallback_narrative(self, new_reason: str, participants: List[Dict[str, Any]], general_multiplier: Dict[str, Any]) -> str:
        """Generate a fallback narrative when LLM fails."""
        participant_count = len(participants)
        multiplier_desc = general_multiplier['description']
        
        # Try to get message from answers.json
        try:
            fallback_message = PERSONALITY.get('answers', {}).get('discord', {}).get('beggar_messages', {}).get('minigame_fallback')
            if fallback_message:
                return fallback_message.format(new_reason=new_reason, participant_count=participant_count, multiplier=multiplier_desc)
        except Exception as e:
            logger.warning(f"Could not load minigame fallback from answers.json: {e}")
        
        # Neutral English fallback
        return f"Reason changed to '{new_reason}'! Thanks to the {participant_count} donors! {multiplier_desc}. Everyone improved their relationship!"

    def _get_minigame_description(self, result_type: str) -> str:
        """Get minigame result description from prompts.json with English fallback."""
        # Try to get description from prompts.json
        try:
            minigame_results = PERSONALITY.get('roles', {}).get('trickster', {}).get('subroles', {}).get('beggar', {}).get('minigame_results', {})
            if minigame_results and result_type in minigame_results:
                return minigame_results[result_type]
        except Exception as e:
            logger.warning(f"Could not load minigame description from prompts.json: {e}")
        
        # English fallbacks
        fallback_descriptions = {
            "nothing": "No gold returns for anyone this time",
            "return": "All participants get their donations back", 
            "double": "All participants get double their donations back"
        }
        
        return fallback_descriptions.get(result_type, "Unknown result")
