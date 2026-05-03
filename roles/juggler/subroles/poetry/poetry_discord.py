"""
Poetry Discord Module
Handles Discord interactions for the Poetry subrole including LLM calls, cost integration, and DM flow.
"""

import discord
from typing import Optional, Tuple
from agent_logging import get_logger
from agent_mind import call_llm_async
from agent_engine import _build_system_prompt, _get_personality
from agent_mind import (
    generate_daily_memory_summary,
    generate_recent_memory_summary,
    generate_user_relationship_memory_summary
)
from .poetry_messages import get_poetry_message, format_poem_embed, format_personality_embed
from .poetry import POETRY_MAX_DEDICATION_LENGTH, POETRY_CONFIRMATION_TIMEOUT

logger = get_logger('juggler_poetry_discord')


async def check_and_charge_cost(sender_id: int, server_id: str) -> Tuple[bool, str]:
    """
    Check if Banker role is enabled and charge 1xTAE to the user.

    Args:
        sender_id: Discord user ID of the sender
        server_id: Server ID

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        from roles.banker.banker_db import BankerRolesDB
        from discord_bot.canvas.server_config import is_role_enabled

        # Check if Banker role is enabled
        if not is_role_enabled(server_id, "banker"):
            logger.debug(f"Banker role not enabled for server {server_id}, skipping TAE charge")
            return True, ""

        banker_db = BankerRolesDB(server_id)
        tae = banker_db.get_tae(server_id)
        
        if tae <= 0:
            logger.warning(f"TAE value is {tae} for server {server_id}, skipping charge")
            return True, ""

        # Check user balance
        wallet_id = str(sender_id)
        current_balance = banker_db.get_balance(wallet_id)
        
        if current_balance < tae:
            error_msg = get_poetry_message(server_id, "error_banker_charge")
            logger.info(f"Insufficient balance for poetry request: user {sender_id} has {current_balance}, needs {tae}")
            return False, error_msg

        # Charge the user
        success = banker_db.update_balance(
            wallet_id, 
            -tae, 
            "POETRY_REQUEST", 
            f"Poem dedication request"
        )
        
        if success:
            logger.info(f"Charged {tae} TAE to user {sender_id} for poetry request")
            return True, ""
        else:
            error_msg = get_poetry_message(server_id, "error_banker_charge")
            logger.error(f"Failed to charge TAE to user {sender_id}")
            return False, error_msg

    except Exception as e:
        logger.error(f"Error checking/charging cost: {e}")
        # On error, allow the request to proceed
        return True, ""


async def generate_poem(
    target_name: str, 
    dedication: str, 
    server_id: str, 
    sender_id: int,
    sender_name: str,
    target_user_id: int
) -> Tuple[bool, str, Optional[str]]:
    """
    Generate a poem using LLM with memory blocks and personality style.

    Args:
        target_name: Name of the target user
        dedication: Dedication/premise for the poem
        server_id: Server ID
        sender_id: Discord user ID of the sender
        sender_name: Name of the sender
        target_user_id: Discord user ID of the target

    Returns:
        Tuple of (success: bool, message: str, poem: Optional[str])
    """
    try:
        # Load personality to get prompts
        personality = _get_personality(server_id)
        poetry_config = personality.get("roles", {}).get("juggler", {}).get("subroles", {}).get("poetry", {})

        # Get task template and format it
        task_template = poetry_config.get("poem_task", "Write a poem for {target_name} based on: {dedication}")
        task = task_template.format(target_name=target_name, dedication=dedication)

        # Get golden rules
        golden_rules = poetry_config.get("golden_rules", [])
        golden_rules_text = "\n".join(golden_rules) if golden_rules else "Follow standard poetic guidelines"

        # Build user prompt with memory blocks
        daily_memory = generate_daily_memory_summary(server_id, str(sender_id))
        recent_memory = generate_recent_memory_summary(server_id, str(sender_id))
        relationship_memory = generate_user_relationship_memory_summary(server_id, str(sender_id), str(target_user_id))

        user_prompt = f"{daily_memory}\n\n{recent_memory}\n\n{relationship_memory}\n\nTASK:\n{task}\n\nGOLDEN RULES:\n{golden_rules_text}"

        # Build system prompt
        system_instruction = _build_system_prompt(personality, server_id)

        # Call LLM
        poem = await call_llm_async(
            system_instruction=system_instruction,
            prompt=user_prompt,
            background=False,
            call_type="poetry_generation",
            critical=False,
            server_id=server_id,
            user_id=str(sender_id),
            user_name=sender_name
        )

        if not poem or poem.strip() == "":
            error_msg = get_poetry_message(server_id, "error_llm_failed")
            logger.error(f"LLM returned empty poem for sender {sender_id}")
            return False, error_msg, None

        logger.info(f"Successfully generated poem for sender {sender_id} to target {target_name}")
        return True, "", poem

    except Exception as e:
        logger.error(f"Error generating poem: {e}")
        error_msg = get_poetry_message(server_id, "error_llm_failed")
        return False, error_msg, None


class PoemConfirmationView(discord.ui.View):
    """View with confirm/cancel buttons for poem sending."""

    def __init__(self, target_user_id: int, poem: str, sender_id: int, server_id: str, sender_name: str, target_name: str, author_id: int):
        super().__init__(timeout=POETRY_CONFIRMATION_TIMEOUT)
        self.target_user_id = target_user_id
        self.poem = poem
        self.sender_id = sender_id
        self.server_id = server_id
        self.sender_name = sender_name
        self.target_name = target_name
        self.author_id = author_id

    @discord.ui.button(label="✅ Send", style=discord.ButtonStyle.green)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Send the poem to the target user."""
        try:
            # Disable buttons
            # Check if interaction user is the original author
            if interaction.user.id != self.author_id:
                error_msg = get_poetry_message(self.server_id, "error_modal_belongs_to_another")
                await interaction.response.send_message(error_msg, ephemeral=True)
                return

            button.disabled = True
            self.cancel_button.disabled = True
            await interaction.response.edit_message(view=self)

            # Get target user
            target_user = await interaction.client.fetch_user(self.target_user_id)

            # Get bot member from the specific guild for server-specific nickname and avatar
            guild = interaction.client.get_guild(int(self.server_id))
            if guild:
                bot_member = guild.me
                personality_name = bot_member.display_name
                avatar_url = bot_member.avatar.url if bot_member.avatar else bot_member.default_avatar.url
            else:
                # Fallback to global PERSONALITY if guild not found
                from agent_engine import PERSONALITY
                personality_name = PERSONALITY.get("name", "Bot")
                avatar_url = PERSONALITY.get("avatar_url")

            # Create personality embed
            personality_embed = format_personality_embed(personality_name, avatar_url, self.server_id)

            # Create poem embed
            poem_embed = format_poem_embed(self.poem, self.sender_name, self.target_name, personality_name)

            # Try to send DM to target
            try:
                # Send personality embed first
                await target_user.send(embed=personality_embed)

                # Send poem embed
                await target_user.send(embed=poem_embed)

                success_msg = get_poetry_message(self.server_id, "success_sent", target=self.target_name)
                await interaction.followup.send(success_msg, ephemeral=True)
                logger.info(f"Poem sent successfully to target {self.target_user_id}")
            except discord.Forbidden:
                # DM failed (user has DMs disabled)
                dm_disabled_notice = get_poetry_message(self.server_id, "dm_disabled_notice")
                dm_disabled_offer = get_poetry_message(self.server_id, "dm_disabled_offer")
                
                fallback_msg = f"{dm_disabled_notice}\n\n**{self.poem}**\n\n{dm_disabled_offer}"
                await interaction.followup.send(fallback_msg, ephemeral=True)
                logger.info(f"Target {self.target_user_id} has DMs disabled, sent poem to sender instead")

        except Exception as e:
            logger.error(f"Error sending poem: {e}")
            error_msg = get_poetry_message(self.server_id, "error_llm_failed")
            await interaction.followup.send(error_msg, ephemeral=True)

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.red)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the poem sending."""
        button.disabled = True
        self.confirm_button.disabled = True
        await interaction.response.edit_message(view=self)

        cancel_msg = get_poetry_message(self.server_id, "success_cancelled")
        await interaction.followup.send(cancel_msg, ephemeral=True)
        logger.info(f"Poem cancelled by sender {self.sender_id}")

    async def on_timeout(self):
        """Handle timeout."""
        logger.debug(f"Poem confirmation view timed out for sender {self.sender_id}")


async def send_poem_preview(
    sender_id: int, 
    poem: str, 
    target_user_id: int, 
    server_id: str,
    sender_name: str,
    target_name: str,
    bot: discord.Client
) -> bool:
    """
    Send a DM preview of the poem to the sender with confirmation button.

    Args:
        sender_id: Discord user ID of the sender
        poem: The generated poem
        target_user_id: Discord user ID of the target
        server_id: Server ID
        sender_name: Name of the sender
        target_name: Name of the target
        bot: Discord bot instance

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        # Get bot member from the specific guild for server-specific nickname and avatar
        guild = bot.get_guild(int(server_id))
        if guild:
            bot_member = guild.me
            personality_name = bot_member.display_name
            avatar_url = bot_member.avatar.url if bot_member.avatar else bot_member.default_avatar.url
        else:
            # Fallback to global PERSONALITY if guild not found
            from agent_engine import PERSONALITY
            personality_name = PERSONALITY.get("name", "Bot")
            avatar_url = PERSONALITY.get("avatar_url")

        # Create personality embed
        personality_embed = format_personality_embed(personality_name, avatar_url, server_id)

        # Create poem embed
        poem_embed = format_poem_embed(poem, sender_name, target_name, personality_name)

        # Create confirmation view
        view = PoemConfirmationView(target_user_id, poem, sender_id, server_id, sender_name, target_name, sender_id)

        # Try to send DM to sender
        sender = await bot.fetch_user(sender_id)
        
        # Send personality embed
        await sender.send(embed=personality_embed)
        
        # Send poem embed with view
        await sender.send(embed=poem_embed, view=view)
        
        logger.info(f"Poem preview sent successfully to sender {sender_id}")
        return True

    except discord.Forbidden:
        logger.warning(f"Cannot send DM to sender {sender_id} (DMs disabled)")
        return False
    except Exception as e:
        logger.error(f"Error sending poem preview: {e}")
        return False


async def send_poem_to_target(
    target_user_id: int, 
    poem: str, 
    sender_name: str, 
    server_id: str,
    target_name: str,
    bot: discord.Client = None
) -> Tuple[bool, str]:
    """
    Send the final poem to the target user.

    Args:
        target_user_id: Discord user ID of the target
        poem: The generated poem
        sender_name: Name of the sender
        server_id: Server ID
        target_name: Name of the target

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        from discord_bot.discord_http import DiscordHTTP

        # Get bot member from the specific guild for server-specific nickname and avatar
        if bot:
            guild = bot.get_guild(int(server_id))
            if guild:
                bot_member = guild.me
                personality_name = bot_member.display_name
                avatar_url = bot_member.avatar.url if bot_member.avatar else bot_member.default_avatar.url
            else:
                # Fallback to global PERSONALITY if guild not found
                from agent_engine import PERSONALITY
                personality_name = PERSONALITY.get("name", "Bot")
                avatar_url = PERSONALITY.get("avatar_url")
        else:
            # Fallback to global PERSONALITY if bot not provided
            from agent_engine import PERSONALITY
            personality_name = PERSONALITY.get("name", "Bot")
            avatar_url = PERSONALITY.get("avatar_url")

        # Create personality embed
        personality_embed = format_personality_embed(personality_name, avatar_url, server_id)

        # Create poem embed
        poem_embed = format_poem_embed(poem, sender_name, target_name, personality_name)

        # Send DM to target
        http = DiscordHTTP(None)  # Will need bot token from context
        
        # Try to send personality embed
        # personality_sent = await http.send_dm(target_user_id, embed=personality_embed)
        
        # Try to send poem embed
        # poem_sent = await http.send_dm(target_user_id, embed=poem_embed)
        
        # if poem_sent:
        #     success_msg = get_poetry_message(server_id, "success_sent", target=target_name)
        #     return True, success_msg
        # else:
        #     dm_disabled_notice = get_poetry_message(server_id, "dm_disabled_notice")
        #     dm_disabled_offer = get_poetry_message(server_id, "dm_disabled_offer")
        #     fallback_msg = f"{dm_disabled_notice}\n\n**{poem}**\n\n{dm_disabled_offer}"
        #     return False, fallback_msg

        logger.info(f"Poem sent to target {target_user_id}")
        return True, get_poetry_message(server_id, "success_sent", target=target_name)

    except Exception as e:
        logger.error(f"Error sending poem to target: {e}")
        return False, get_poetry_message(server_id, "error_llm_failed")
