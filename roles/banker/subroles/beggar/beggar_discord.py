"""
Beggar Discord Components
Handles Discord UI components for the beggar subrole: buttons, views, and interactions.
"""

import discord
from discord.ui import View, Button
from typing import Optional
import os
import json
import asyncio

from agent_logging import get_logger
from agent_roles_db import get_roles_db_instance
from agent_runtime import get_personality_directory

from .beggar_db import get_beggar_config

logger = get_logger('beggar_discord')


class DonationButton(discord.ui.Button):
    """Custom button for donation with multiplier."""
    
    def __init__(self, label: str, multiplier: int, style, emoji, view):
        super().__init__(label=label, style=style, emoji=emoji)
        self.multiplier = multiplier
        self.parent_view = view
    
    async def callback(self, interaction: discord.Interaction):
        """Handle donation button click."""
        tae_amount = self.parent_view._calculate_tae_amount(self.multiplier)
        await self.parent_view._handle_donation(interaction, tae_amount)

class CustomButton(discord.ui.Button):
    """Custom button for custom amount donation."""
    
    def __init__(self, label: str, style, emoji, view):
        super().__init__(label=label, style=style, emoji=emoji)
        self.parent_view = view
    
    async def callback(self, interaction: discord.Interaction):
        """Handle custom amount button click."""
        message = self.parent_view._get_message("donation_custom_message")
        await interaction.response.send_message(message, ephemeral=True)

class BeggarDonationView(View):
    """View with donation buttons for beggar messages."""
    
    def __init__(self, current_reason: str, server_id: str):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.current_reason = current_reason
        self.server_id = str(server_id)
        self.config = get_beggar_config(self.server_id)
        
        # Import get_messages from banker_messages
        try:
            from roles.banker.banker_messages import get_messages
            self.get_messages = get_messages
        except ImportError:
            self.get_messages = None
        
        # Get server_db_path for get_messages
        try:
            from discord_bot.db_init import get_server_personality_dir
            server_dir = get_server_personality_dir(self.server_id)
            self.server_db_path = server_dir if server_dir else None
        except Exception:
            self.server_db_path = None
        
        # Get labels and coin from messages
        self.coin = self._get_message("coin")
        self.donate = self._get_message("beggar_donate_emoji")
        self.donation_label = self._get_message("donation_label")
        self.label_custom = self._get_message("donation_custom_label")
        
        # Build labels dynamically
        label_x1 = f"{self.donation_label} {self._calculate_tae_amount(1)} {self.coin}"
        label_x3 = f"{self.donation_label} {self._calculate_tae_amount(3)} {self.coin}"
        
        # Create buttons with dynamic labels and emojis
        self.add_item(DonationButton(label=label_x1, multiplier=1, style=discord.ButtonStyle.primary, emoji=self.donate, view=self))
        self.add_item(DonationButton(label=label_x3, multiplier=3, style=discord.ButtonStyle.primary, emoji=self.donate, view=self))
        self.add_item(CustomButton(label=self.label_custom, style=discord.ButtonStyle.secondary, emoji=self.donate, view=self))
    
    def _get_message(self, key: str) -> str:
        """Get message using get_messages from banker_messages.py."""
        if self.get_messages and self.server_db_path:
            return self.get_messages(self.server_db_path, key)
        return key  # Fallback
    
    def _calculate_tae_amount(self, multiplier: int) -> int:
        """Calculate the donation amount based on TAE multiplier."""
        try:
            from roles.banker.banker_db import get_banker_roles_db_instance as get_banker_db_instance
        except ImportError:
            get_banker_db_instance = None
        
        banker_db = get_banker_db_instance(self.server_id) if get_banker_db_instance else None
        
        if banker_db:
            # Use fixed multiplier amounts
            base_amounts = {1: 1, 3: 3}
            return base_amounts.get(multiplier, 1)
        else:
            # Fallback to fixed amounts
            return multiplier
    
    async def _handle_donation(self, interaction: discord.Interaction, amount: int):
        """Handle the donation process."""
        try:
            user_id = str(interaction.user.id)
            user_name = interaction.user.display_name
            
            from roles.banker.banker_db import get_banker_roles_db_instance as get_banker_db_instance
            
            banker_db = get_banker_db_instance(self.server_id)
            
            if not banker_db:
                await interaction.response.send_message(
                    "❌ Banker system is not available.", ephemeral=True
                )
                return
            
            # Ensure wallets exist
            banker_db.create_wallet(user_id, user_name, 'user')
            banker_db.create_wallet("beggar_fund", "Beggar Fund", 'system')
            
            user_balance = banker_db.get_balance(user_id)
            if user_balance < amount:
                await interaction.response.send_message(
                    f"❌ You don't have enough gold! You have {user_balance} gold but need {amount} gold.",
                    ephemeral=True
                )
                return
            
            # Process the donation
            success = banker_db.update_balance(
                user_id, user_name,
                -amount, "BEGGAR_DONATION", f"Donation: {self.current_reason}"
            )
            
            if not success:
                await interaction.response.send_message(
                    "❌ Error processing donation transaction.", ephemeral=True
                )
                return
            
            # Update beggar fund
            banker_db.update_balance(
                "beggar_fund", "Beggar Fund",
                amount, "BEGGAR_DONATION", f"Donation from {user_name}: {self.current_reason}"
            )
            
            # Update beggar statistics
            roles_db = get_roles_db_instance(self.server_id)
            roles_db.update_beggar_donation(user_id, user_name, amount, self.current_reason)
            roles_db.save_beggar_request(
                user_id=user_id,
                user_name=user_name,
                request_type="BEGGAR_DONATION",
                message=f"Donated {amount} gold",
                channel_id=str(interaction.channel.id) if interaction.channel else None,
                metadata=f"reason:{self.current_reason}",
            )
            
            # Get donation success message from personality descriptions
            donation_msg = self._get_donation_success_message(amount, self.current_reason)
            
            await interaction.response.send_message(donation_msg, ephemeral=True, delete_after=300)
            
            # Register donation as server interaction
            try:
                from discord_bot.discord_utils import get_db_for_server
                db_instance = get_db_for_server(interaction.guild)
                await asyncio.to_thread(
                    db_instance.register_server_interaction,
                    user_id,
                    f"Donated {amount} gold to beggar",
                    str(interaction.channel.id) if interaction.channel else None,
                    str(interaction.guild.id) if interaction.guild else None,
                    interaction.guild.name if interaction.guild else "Unknown"
                )
            except Exception as e:
                logger.error(f"Failed to register donation interaction: {e}")
                
        except Exception as e:
            logger.error(f"Error handling donation: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while processing your donation.", ephemeral=True
            )
    
    def _get_donation_success_message(self, amount: int, reason: str) -> str:
        """Get donation success message from personality descriptions."""
        try:
            personality_dir = get_personality_directory(self.server_id)
            banker_path = os.path.join(personality_dir, "descriptions", "banker.json")
            
            default_msg = f"Thank you for donating {amount} gold to the cause: {reason}! 🪙"
            
            if os.path.exists(banker_path):
                with open(banker_path, encoding="utf-8") as f:
                    banker_data = json.load(f)
                    msg_template = banker_data.get("beggar", {}).get(
                        "beggar_donation_success",
                        default_msg
                    )
                    return msg_template.format(amount=amount, reason=reason)
            
            return default_msg
            
        except Exception as e:
            logger.warning(f"Could not load donation message: {e}")
            return f"Thank you for donating {amount} gold to the cause: {reason}! 🪙"


class BeggarModal(discord.ui.Modal):
    """Modal for custom beggar donation amount."""
    
    def __init__(self, current_reason: str, server_id: str):
        super().__init__(title="Custom Donation")
        self.current_reason = current_reason
        self.server_id = server_id
        
        self.amount_input = discord.ui.TextInput(
            label="Amount",
            placeholder="Enter gold amount to donate",
            required=True,
            max_length=10,
        )
        self.add_item(self.amount_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
            if amount <= 0:
                await interaction.response.send_message(
                    "❌ Donation amount must be positive.", ephemeral=True
                )
                return
            
            view = BeggarDonationView(self.current_reason, self.server_id)
            await view._handle_donation(interaction, amount)
            
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid number.", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Custom donation modal failed: {e}")
            await interaction.response.send_message(
                "❌ Failed to process donation.", ephemeral=True
            )
