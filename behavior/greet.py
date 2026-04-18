"""
Greet behavior module - handles presence-based greetings when users come online.
Extracted from agent_discord.py for better modularity.
"""

import time
import discord
import asyncio
from agent_logging import get_logger
from agent_mind import call_llm, _build_conversation_user_prompt, _build_prompt_memory_block, _build_prompt_relationship_block, _build_prompt_last_interactions_block
from agent_engine import _build_system_prompt, _get_personality
from discord_bot.discord_utils import get_greeting_enabled, get_server_key, get_db_for_server, send_dm_with_personality
from behavior.db_behavior import get_behavior_db_instance

logger = get_logger('greet_behavior')

# Track last greetings per user to avoid spam
_last_greetings = {}

# Global rate limiting for Vertex AI - minimum seconds between any greetings
_LAST_GLOBAL_GREETING_TIME = 0
_MIN_SECONDS_BETWEEN_GREETINGS = 3  # Minimum 3 seconds between LLM calls for greetings


async def _wait_for_greeting_rate_limit():
    """Ensure minimum delay between greetings to avoid Vertex AI saturation."""
    global _LAST_GLOBAL_GREETING_TIME
    import time
    import asyncio
    
    current_time = time.time()
    time_since_last = current_time - _LAST_GLOBAL_GREETING_TIME
    
    if time_since_last < _MIN_SECONDS_BETWEEN_GREETINGS:
        wait_time = _MIN_SECONDS_BETWEEN_GREETINGS - time_since_last
        logger.debug(f"Greeting rate limit: waiting {wait_time:.1f}s before next greeting")
        await asyncio.sleep(wait_time)
    
    _LAST_GLOBAL_GREETING_TIME = time.time()


class ReplyButton(discord.ui.Button):
    """Button to reply to a greeting and set the conversation context to this server."""
    
    def __init__(self, guild: discord.Guild, server_id: str, row: int = 0):
        # Get reply button config from personality descriptions with English fallback
        personality = _get_personality(server_id) if server_id else _get_personality()
        descriptions = personality.get("descriptions", {}).get("discord", {})
        reply_button_cfg = descriptions.get("reply_button", {})
        
        # Use config values or English fallbacks
        label = reply_button_cfg.get("label", "Reply")
        emoji = reply_button_cfg.get("emoji", "💬")
        
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            emoji=emoji,
            row=row
        )
        self.guild = guild
        self.server_id = server_id
    
    async def callback(self, interaction: discord.Interaction):
        """Handle reply button click - pin this server and show confirmation."""
        try:
            from agent_db import pin_dm_session
            pin_dm_session(interaction.user.id, self.server_id)
            logger.info(f"ReplyButton: DM pinned user={interaction.user.id} → server={self.server_id}")

            # Get confirmation message from personality descriptions with English fallback
            personality = _get_personality(self.server_id) if self.server_id else _get_personality()
            descriptions = personality.get("descriptions", {}).get("discord", {})
            reply_button_cfg = descriptions.get("reply_button", {})
            
            # Use config message or English fallback
            confirmation_template = reply_button_cfg.get("confirmation_message", 
                "💬 You are now talking to me as if you were in **{server_name}**. All your responses will use this personality until you select another server.")
            confirmation_message = confirmation_template.format(server_name=self.guild.name)
            
            # Disable the button after clicking
            self.disabled = True
            self.label = "✓ Active"
            self.style = discord.ButtonStyle.success
            
            # Update the message to show the button was clicked
            await interaction.response.edit_message(view=self.view)
            
            # Send a confirmation message
            await interaction.followup.send(
                confirmation_message,
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error in ReplyButton callback: {e}")
            try:
                await interaction.response.send_message(
                    "❌ No se pudo iniciar la conversación. Intenta enviarme un mensaje directamente.",
                    ephemeral=True
                )
            except Exception:
                pass


class ReplyButtonView(discord.ui.View):
    """View containing the reply button for a greeting."""
    
    def __init__(self, guild: discord.Guild, server_id: str, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.guild = guild
        self.server_id = server_id
        self.message = None
        self.add_item(ReplyButton(guild, server_id, row=0))
    
    async def on_timeout(self):
        """Called when the view times out."""
        # Disable the button
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
                child.label = "⏰ Expirado"
        
        # Try to update the message
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception as e:
                logger.debug(f"Could not update timed out reply button: {e}")


async def _send_greeting_to_user(user_id: int, user_name: str, guild, greeting_data: dict, bot: discord.Client):
    """
    Send the actual greeting to a user for a specific server.
    
    Args:
        user_id: Discord user ID
        user_name: User display name
        guild: Discord guild object
        greeting_data: Dictionary with greeting configuration
        bot: Discord bot client
    """
    # Apply global rate limiting to prevent Vertex AI saturation
    await _wait_for_greeting_rate_limit()
    
    try:
        server_id = str(guild.id)
        server_name = get_server_key(guild)
        
        # Build greeting prompt
        greeting_prompt = build_greeting_prompt(user_name, user_id, guild)
        
        # Build system instruction
        server_personality = _get_personality(server_id) if server_id else _get_personality()
        system_instruction = _build_system_prompt(server_personality, server_id)
        
        # Generate greeting
        saludo = await asyncio.to_thread(
            call_llm,
            system_instruction=system_instruction,
            prompt=greeting_prompt,
            async_mode=False,
            call_type="think",
            critical=True,
            logger=logger,
        )
        
        # Get user object
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        if not user:
            logger.error(f"Could not find user {user_id} for greeting")
            return
        
        # Send personality embed first (server-specific avatar and name)
        from discord_bot.discord_utils import send_personality_embed_dm
        await send_personality_embed_dm(user, bot, guild, server_id)
        
        # Create the reply button view for this server
        view = ReplyButtonView(guild, server_id, timeout=300.0)
        
        # Send greeting message with the reply button
        greeting_message = await user.send(f"👋 {saludo}", view=view)
        view.message = greeting_message
        
        logger.info(f"🔄 Presence DM sent to {user_name} (server: {guild.name}) with reply button")
        
        # Update tracking
        current_time = time.time()
        last_greeting_key = f"presence_greeting_{user_id}"
        _last_greetings[last_greeting_key] = current_time
        _last_greetings[f"{last_greeting_key}_recent"] = current_time
        
        # Record greeting in database
        behavior_db = get_behavior_db_instance(server_name)
        await asyncio.to_thread(
            behavior_db.record_greeting_sent,
            user_id, user_name, guild.id, saludo, 'presence'
        )
        
        # Register interaction
        try:
            db_instance = get_db_for_server(guild)
            personality = _get_personality(server_id) if server_id else _get_personality()
            greetings_cfg = personality.get("behaviors", {}).get("greetings", {})
            interaction_message = greetings_cfg.get("interaction_message", "User went from offline to online (DM greeting)")
            await asyncio.to_thread(
                db_instance.register_interaction,
                user_id, user_name, "PRESENCE_DM",
                interaction_message,
                None, guild.id,
                metadata={"response": saludo, "greeting": saludo, "respuesta": saludo, "saludo": saludo}
            )
        except Exception as db_error:
            logger.warning(f"Could not register interaction in database: {db_error}")
            
    except Exception as e:
        logger.error(f"Error sending greeting to {user_name}: {e}")
        # Send fallback
        try:
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            if user:
                discord_cfg = greeting_data.get('discord_cfg', {})
                presence_cfg = discord_cfg.get("member_presence", {})
                fallback_msg = presence_cfg.get("fallback", "Welcome back!")
                fallback_msg = fallback_msg.format(user_name=user_name)
                # Send fallback with server-specific personality embed
                await send_dm_with_personality(user, bot, f"👋 {fallback_msg}", guild, server_id)
        except Exception as fallback_error:
            logger.error(f"Fallback greeting also failed: {fallback_error}")


def _get_user_mutual_guilds(bot: discord.Client, user_id: int) -> list[discord.Guild]:
    """
    Get all guilds where both the bot and user are members.
    
    Args:
        bot: Discord bot client
        user_id: User ID to check
        
    Returns:
        List of mutual guilds
    """
    mutual_guilds = []
    for guild in bot.guilds:
        member = guild.get_member(user_id)
        if member:
            mutual_guilds.append(guild)
    return mutual_guilds

async def _has_unreplied_greeting_any_server(user_id: str) -> bool:
    """
    Check if user has an unreplied greeting in ANY server database.
    
    Args:
        user_id: Discord user ID to check
        
    Returns:
        True if user has unreplied greeting in any server, False otherwise
    """
    try:
        # Import here to avoid circular imports
        from agent_db import get_all_server_keys
        from behavior.db_behavior import get_behavior_db_instance
        
        # Get all server keys
        server_keys = await asyncio.to_thread(get_all_server_keys)
        
        # Check each server's behavior database
        for server_key in server_keys:
            behavior_db = get_behavior_db_instance(server_key)
            greeting_status = await asyncio.to_thread(
                behavior_db.get_last_greeting_status, 
                user_id, 
                "any_guild"  # Use special marker to check across all guilds in this server
            )
            
            if greeting_status.get('has_unreplied_greeting', False):
                logger.info(f"Found unreplied greeting for user {user_id} in server {server_key}")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking unreplied greetings across servers for {user_id}: {e}")
        # If we can't check properly, err on the side of not sending duplicate greetings
        return False

def build_greeting_prompt(user_display_name: str, user_id: str, guild) -> str:
    """
    Build a comprehensive contextual prompt for user greetings.
    
    Args:
        user_display_name: Display name of the user being greeted
        user_id: Discord user ID
        guild: Discord guild object
        
    Returns:
        Comprehensive contextual prompt with memory, relationship, and interaction history
    """
    server_name = get_server_key(guild)

    # Get greeting configuration from server-specific personality
    server_id = str(guild.id) if guild else None
    personality = _get_personality(server_id) if server_id else _get_personality()
    greetings_cfg = personality.get("behaviors", {}).get("greetings", {})
    task_template = greetings_cfg.get("task", "Greet {username} that is already connected to the server.")
    golden_rules = greetings_cfg.get("golden_rules", [])
    response_title = greetings_cfg.get("response_title", "## WRITE ONLY THE GREET IN THE WORDS OF THE PERSONALITY:")
    
    # Build individual blocks using specific functions
    memory_block = _build_prompt_memory_block(server=server_name)
    relationship_block = _build_prompt_relationship_block(
        user_id=user_id,
        user_name=user_display_name,
        server=server_name
    )
    interactions_block = _build_prompt_last_interactions_block(
        user_id=user_id,
        server=server_name
    )
    
    # Format the task with username
    task = task_template.format(username=user_display_name)
    
    # Build the complete prompt structure
    prompt_sections = [
        memory_block,
        relationship_block,
        interactions_block,
        "---",  # Separator
        task,  # Task from prompts.json
        "\n".join(golden_rules),  # Golden rules from prompts.json
        response_title  # Response title from prompts.json
    ]
    
    # Filter out empty sections
    non_empty_sections = [section for section in prompt_sections if section and section.strip()]
    
    return "\n\n".join(non_empty_sections)

async def handle_presence_update(before, after, discord_cfg, bot_display_name, bot=None):
    """
    Handle presence updates - greet users when they come online.
    
    For users in multiple servers, shows a server selection interface
    to let them choose which server context to use for the greeting.
    
    Args:
        before: discord.Member before state
        after: discord.Member after state  
        discord_cfg: discord configuration from personality
        bot_display_name: bot's display name
        bot: Discord bot client instance (for personality embed and server selection)
    """
    global _last_greetings
    
    if after.bot:
        return
    
    # Skip if no bot instance provided (needed for multi-server handling)
    if not bot:
        logger.warning(f"No bot instance provided for presence greeting of {after.name}")
        return
    
    if not get_greeting_enabled(after.guild):
        return
    
    presence_cfg = discord_cfg.get("member_presence", {})
    if not presence_cfg.get("enabled", True):
        logger.info(f"Presence greetings disabled by config for guild={after.guild.name}")
        return
    
    before_status = before.status if before.status else discord.Status.offline
    after_status = after.status if after.status else discord.Status.offline
    
    # Only greet when going from offline to online
    if before_status != discord.Status.offline or after_status != discord.Status.online:
        return
    
    # Rate limiting - 1 hour between greetings per user (across all servers)
    current_time = time.time()
    last_greeting_key = f"presence_greeting_{after.id}"
    
    # Check both in-memory cache for recent greetings
    if current_time - _last_greetings.get(last_greeting_key, 0) < 3600:
        logger.info(f"Presence greeting skipped due to cooldown for user={after.name}")
        return
    
    # Additional check: prevent multiple greetings within 10 seconds
    if current_time - _last_greetings.get(f"{last_greeting_key}_recent", 0) < 10:
        logger.info(f"Presence greeting skipped due to recent duplicate prevention for user={after.name}")
        return
    
    # CRITICAL: Update tracking IMMEDIATELY before any async operations
    # This prevents duplicate greetings if Discord sends multiple presence updates rapidly
    _last_greetings[last_greeting_key] = current_time
    _last_greetings[f"{last_greeting_key}_recent"] = current_time
    
    try:
        # Check if user has an unreplied greeting from ANY server
        if await _has_unreplied_greeting_any_server(after.id):
            logger.info(f"Presence greeting skipped for {after.name} - user has unreplied greeting")
            return
        
        # Get all mutual guilds with the user
        mutual_guilds = _get_user_mutual_guilds(bot, after.id)
        
        # Filter to only guilds where greetings are enabled
        eligible_guilds = [g for g in mutual_guilds if get_greeting_enabled(g)]
        
        if not eligible_guilds:
            logger.info(f"No eligible guilds for greeting user {after.name}")
            return
        
        # Send greetings from ALL eligible servers
        logger.info(f"User {after.name} is in {len(eligible_guilds)} servers - sending greetings from all")
        
        for guild in eligible_guilds:
            try:
                greeting_data = {
                    'discord_cfg': discord_cfg,
                    'presence_cfg': presence_cfg
                }
                await _send_greeting_to_user(after.id, after.display_name, guild, greeting_data, bot)
            except Exception as e:
                logger.error(f"Error sending greeting to {after.name} from server {guild.name}: {e}")
                # Continue with other servers even if one fails
            
    except Exception as e:
        logger.error(f"Error in presence greeting for {after.name}: {e}")

def clear_greeting_cache():
    """Clear the greeting cache - useful for testing or resets."""
    global _last_greetings
    _last_greetings.clear()
    logger.info("Greeting cache cleared")
