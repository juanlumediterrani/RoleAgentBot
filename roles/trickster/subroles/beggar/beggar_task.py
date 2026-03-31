"""
Beggar Automated Task System
Handles automatic public channel messages for begging
"""

import random
from typing import Optional, List, Dict, Any

import discord
from discord.ui import View
from discord import Interaction

from agent_logging import get_logger
from agent_mind import call_llm
from agent_engine import _build_system_prompt, PERSONALITY

from .beggar_config import get_beggar_config
from agent_roles_db import get_roles_db_instance

logger = get_logger('beggar_task')


class BeggarDonationView(View):
    """View with donation buttons for beggar messages."""
    
    def __init__(self, server_id: str, current_reason: str):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.server_id = server_id
        self.current_reason = current_reason
        self.config = get_beggar_config(server_id)
        
    @discord.ui.button(label="Donate x1 tae", style=discord.ButtonStyle.primary, emoji="🪙")
    async def donate_x1(self, interaction: Interaction, button: discord.ui.Button):
        # Calculate x1 TAE amount (base amount)
        tae_amount = self._calculate_tae_amount(1)
        await self._handle_donation(interaction, tae_amount)
    
    @discord.ui.button(label="Donate x3 tae", style=discord.ButtonStyle.primary, emoji="🪙")
    async def donate_x3(self, interaction: Interaction, button: discord.ui.Button):
        # Calculate x3 TAE amount
        tae_amount = self._calculate_tae_amount(3)
        await self._handle_donation(interaction, tae_amount)
    
    @discord.ui.button(label="Custom Amount", style=discord.ButtonStyle.secondary, emoji="💰")
    async def donate_custom(self, interaction: Interaction, button: discord.ui.Button):
        # This would open a modal for custom amount
        await interaction.response.send_message(
            "Use `!trickster beggar donate <amount>` to donate a custom amount!",
            ephemeral=True
        )
    
    def _calculate_tae_amount(self, multiplier: int) -> int:
        """Calculate the donation amount based on TAE multiplier."""
        try:
            # Get current TAE from banker system
            try:
                from roles.banker.banker_db import get_banker_roles_db_instance as get_banker_db_instance
            except ImportError:
                get_banker_db_instance = None
                
            banker_db = get_banker_db_instance(self.server_id) if get_banker_db_instance else None
            
            if banker_db:
                # For now, use fixed amounts since get_current_tae doesn't exist
                # TODO: Implement TAE rate system in banker_db if needed
                base_amounts = {1: 1, 3: 3}
                return base_amounts.get(multiplier, 1)
            else:
                # Fallback to fixed amounts if banker not available
                base_amounts = {1: 1, 3: 3}
                return base_amounts.get(multiplier, 1)
                
        except Exception as e:
            logger.error(f"Error calculating TAE amount: {e}")
            # Fallback amounts
            return 1 * multiplier
    
    async def _handle_donation(self, interaction: Interaction, amount: int):
        """Handle the donation process."""
        try:
            user_id = str(interaction.user.id)
            user_name = interaction.user.display_name
            server_name = interaction.guild.name if interaction.guild else "Unknown Server"
            
            # Check if user has enough gold (this would need banker integration)
            try:
                from roles.banker.banker_db import get_banker_roles_db_instance as get_banker_db_instance
            except ImportError:
                get_banker_db_instance = None
                
            banker_db = get_banker_db_instance(self.server_id) if get_banker_db_instance else None
            
            if banker_db:
                # Ensure user wallet exists
                banker_db.create_wallet(user_id, user_name, self.server_id, server_name)
                banker_db.create_wallet("beggar_fund", "Beggar Fund", self.server_id, server_name)
                
                user_balance = banker_db.get_balance(user_id, self.server_id)
                if user_balance < amount:
                    await interaction.response.send_message(
                        f"You don't have enough gold! You have {user_balance} gold but need {amount} gold.",
                        ephemeral=True
                    )
                    return
                
                # Process the donation
                success = banker_db.update_balance(
                    user_id, user_name, self.server_id, server_name,
                    -amount, "BEGGAR_DONATION", f"Donation to Putre: {self.current_reason}"
                )
                
                if success:
                    banker_db.update_balance(
                        "beggar_fund", "Beggar Fund", self.server_id, server_name,
                        amount, "BEGGAR_DONATION", f"Donation from {user_name}: {self.current_reason}"
                    )
                else:
                    await interaction.response.send_message(
                        "Error processing donation transaction.",
                        ephemeral=True
                    )
                    return
                
                # Update beggar statistics
                from agent_roles_db import get_roles_db_instance
                roles_db = get_roles_db_instance(self.server_id)
                roles_db.update_beggar_donation(self.server_id, user_id, user_name, amount, self.current_reason)
                roles_db.save_beggar_request(
                    server_id=self.server_id,
                    user_id=user_id,
                    user_name=user_name,
                    request_type="BEGGAR_DONATION",
                    message=f"Donated {amount} gold",
                    channel_id=str(interaction.channel.id) if interaction.channel else None,
                    metadata=f"reason:{self.current_reason}",
                )
                 
                # Get donation success message from personality
                from agent_mind import PERSONALITY
                donation_msg_template = PERSONALITY.get('discord', {}).get('subrole_messages', {}).get('beggar_donation_success', 
                    "Thank you for donating {amount} gold to the cause: {reason}! 🪙")
                
                await interaction.response.send_message(
                    donation_msg_template.format(amount=amount, reason=self.current_reason),
                    ephemeral=True
                )
                
                logger.info(f"{user_name} donated {amount} gold to beggar fund in server {self.server_id}")
                
            else:
                await interaction.response.send_message(
                    "Banker system not available for donations.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error processing donation: {e}", exc_info=True)
            await interaction.response.send_message(
                "Error processing donation. Please try again later.",
                ephemeral=True
            )


class BeggarTask:
    """Automated task system for beggar public messages."""
    
    def __init__(self, server_id: str, bot_instance=None):
        self.server_id = server_id
        self.bot_instance = bot_instance
        self.config = get_beggar_config(server_id)
        self.roles_db = get_roles_db_instance(server_id)
    
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
            
            # Generate message using LLM
            system_instruction = _build_system_prompt(PERSONALITY)
            
            response = call_llm(
                system_instruction=system_instruction,
                prompt=prompt,
                async_mode=True,
                call_type="beggar_task",
                critical=False,
                temperature=0.95
            )
            
            if response and len(response.strip()) > 5:
                # Create donation view
                view = BeggarDonationView(self.server_id, current_reason)
                
                # Send message to channel with buttons
                await target_channel.send(response, view=view)
                
                # Register the task execution
                self.roles_db.save_beggar_request(
                    server_id=self.server_id,
                    user_id="system",
                    user_name="Beggar Task",
                    request_type="BEGGAR_PUBLIC",
                    message=response,
                    channel_id=str(target_channel.id),
                    metadata=f"reason:{current_reason}|with_buttons:true",
                )
                
                logger.info(f"Beggar task with donation buttons executed in channel {target_channel.name} for server {self.server_id}")
                return True
            else:
                logger.warning(f"Empty or short response from LLM for beggar task in server {self.server_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing beggar task for server {self.server_id}: {e}")
            return False
    
    async def _get_target_channel(self) -> Optional[Any]:
        """Get the target channel for sending messages."""
        # Try specific channel first
        channel_id = self.config.get_target_channel_id()
        if channel_id and self.bot_instance:
            try:
                channel = self.bot_instance.get_channel(int(channel_id))
                if channel and channel.permissions_for(channel.guild.me).send_messages:
                    return channel
            except (ValueError, AttributeError):
                pass
        
        # Auto-select channel if enabled
        if self.config.is_auto_channel_selection() and self.bot_instance:
            return await self._auto_select_channel()
        
        return None
    
    async def _auto_select_channel(self) -> Optional[Any]:
        """Automatically select the best channel for begging."""
        try:
            guild = self.bot_instance.get_guild(int(self.server_id))
            if not guild:
                return None
            
            # Prefer text channels where bot can speak
            text_channels = [
                channel for channel in guild.text_channels
                if channel.permissions_for(guild.me).send_messages
                and not channel.is_nsfw()
                and channel.name not in ['bot-commands', 'admin', 'moderation', 'staff']
            ]
            
            if not text_channels:
                return None
            
            # Prioritize general chat channels
            priority_keywords = ['general', 'chat', 'main', 'lobby', 'comunidad', 'hablar']
            
            for channel in text_channels:
                if any(keyword in channel.name.lower() for keyword in priority_keywords):
                    return channel
            
            # Fallback to first available channel
            return text_channels[0]
            
        except Exception as e:
            logger.error(f"Error auto-selecting channel for server {self.server_id}: {e}")
            return None
    
    async def _get_recent_channel_messages(self, channel, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent messages from channel for context."""
        try:
            messages = []
            async for message in channel.history(limit=limit):
                # Skip bot messages and system messages
                if not message.author.bot and not message.system_content:
                    messages.append({
                        'author': message.author.display_name,
                        'content': message.content[:200],  # Limit content length
                        'timestamp': message.created_at.isoformat()
                    })
            
            return messages
            
        except Exception as e:
            logger.error(f"Error getting recent messages from channel {channel.name}: {e}")
            return []
    
    def _build_task_prompt(self, reason: str, recent_messages: List[Dict[str, Any]]) -> str:
        """Build the complete prompt for the begging task."""
        # Get task prompt from personality dynamically
        task_prompt_template = PERSONALITY.get('roles', {}).get('trickster', {}).get('subroles', {}).get('beggar', {}).get('prompt', '')
        
        if not task_prompt_template:
            task_prompt_template = "INTERNAL TASK - BEGGAR: You are raising gold on the server for {reason}. Be convincing but maintain your rough orc style."
        
        task_prompt = task_prompt_template.format(reason=reason)
        
        # Build recent messages context
        messages_context = ""
        if recent_messages:
            messages_context = "\n\n=== RECENT CHANNEL MESSAGES ===\n"
            for msg in recent_messages[-5:]:  # Only last 5 messages
                messages_context += f"[{msg['author']}]: {msg['content']}\n"
        
        # Build golden rules
        golden_rules = self._get_golden_rules()
        
        # Complete prompt
        complete_prompt = f"""{task_prompt}{messages_context}

{golden_rules}

"""
        
        return complete_prompt
    
    def _get_golden_rules(self) -> str:
        """Get golden rules for the begging task."""
        # Get golden rules from personality dynamically
        golden_rules_list = PERSONALITY.get('roles', {}).get('trickster', {}).get('subroles', {}).get('beggar', {}).get('golden_rules', [])
        
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
        task = BeggarTask(server_id, bot_instance)
        return await task.execute_task()
    except Exception as e:
        logger.error(f"Error in execute_beggar_task for server {server_id}: {e}")
        return False
