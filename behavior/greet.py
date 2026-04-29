"""
Greet behavior module - handles presence-based greetings when users come online.
Extracted from agent_discord.py for better modularity.
"""

import time
import discord
import asyncio
from agent_logging import get_logger
from agent_mind import call_llm_async, _build_conversation_user_prompt, _build_prompt_memory_block, _build_prompt_relationship_block, _build_prompt_last_interactions_block
from agent_engine import _build_system_prompt, _get_personality
from discord_bot.discord_utils import get_greeting_enabled, get_server_key, get_db_for_server, send_dm_with_personality

logger = get_logger('greet_behavior')

# Track last greetings per user to avoid spam
_last_greetings = {}

# In-memory tracking of DM greetings pending a user reply.
# Structure: { user_id_str: { server_key: greeting_sent_ts } }
# When a user replies (DM or in guild), their entry is cleared so a new presence greeting
# can be sent later. Previously persisted in behavior.db; now ephemeral.
_pending_greeting_replies: dict[str, dict[str, float]] = {}


def record_pending_greeting(user_id, server_key: str):
    """Mark that a greeting was sent to user and is awaiting a reply."""
    try:
        uid = str(user_id)
        _pending_greeting_replies.setdefault(uid, {})[server_key] = time.time()
    except Exception as e:
        logger.warning(f"Could not record pending greeting for {user_id}/{server_key}: {e}")


def mark_user_replied(user_id, server_key: str | None = None) -> bool:
    """Clear pending greeting(s) for a user.

    Args:
        user_id: Discord user id.
        server_key: Specific server to clear; if None clears all servers for that user.

    Returns:
        True if any pending entry was cleared.
    """
    try:
        uid = str(user_id)
        if uid not in _pending_greeting_replies:
            return False
        if server_key is None:
            _pending_greeting_replies.pop(uid, None)
            return True
        entry = _pending_greeting_replies.get(uid, {})
        if server_key in entry:
            entry.pop(server_key, None)
            if not entry:
                _pending_greeting_replies.pop(uid, None)
            return True
        return False
    except Exception as e:
        logger.warning(f"Could not mark user replied {user_id}/{server_key}: {e}")
        return False


def has_unreplied_greeting(user_id) -> bool:
    """Check if user has any pending (unreplied) greeting in any server."""
    return str(user_id) in _pending_greeting_replies and bool(_pending_greeting_replies[str(user_id)])

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
            from agent_runtime import get_personality_message
            pin_dm_session(interaction.user.id, self.server_id)
            logger.info(f"ReplyButton: DM pinned user={interaction.user.id} → server={self.server_id}")

            # Get confirmation message from answers.json with English fallback
            confirmation_template = get_personality_message(
                "answers.json",
                ["dm_messages", "reply_button_confirmation"],
                self.server_id,
                "💬 You are now talking to me as if you were in **{server_name}**. All your responses will use this personality until you select another server."
            )
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
        saludo = await call_llm_async(
            system_instruction=system_instruction,
            prompt=greeting_prompt,
            background=False,
            call_type="think",
            critical=True,
            logger=logger,
            server_id=server_id,
        )
        
        # Get user object
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        if not user:
            logger.error(f"Could not find user {user_id} for greeting")
            return
        
        # Create unified message with personality embed + greeting + reply button
        from discord_bot.discord_utils import get_server_personality_display_name, get_server_personality_avatar_path
        import os
        
        # Get personality display name (server-specific priority)
        display_name = None
        if server_id:
            personality_name = get_server_personality_display_name(server_id)
            if personality_name:
                display_name = personality_name
        
        # Fallback to guild nickname or global display name
        if not display_name and guild:
            bot_member = guild.me
            if bot_member and bot_member.nick:
                display_name = bot_member.nick
        if not display_name:
            display_name = bot.user.display_name
        
        # Get local personality avatar file (server-specific)
        avatar_file = None
        avatar_attachment_name = None
        if server_id:
            local_avatar_path = get_server_personality_avatar_path(server_id)
            if local_avatar_path and os.path.exists(local_avatar_path):
                avatar_attachment_name = os.path.basename(local_avatar_path)
                avatar_file = discord.File(local_avatar_path, filename=avatar_attachment_name)
        
        # Fallback: global bot avatar URL if no local file
        fallback_avatar_url = None
        if not avatar_file:
            fallback_avatar_url = bot.user.display_avatar.url if bot.user.display_avatar else None
        
        # Create personality embed with greeting as description
        embed = discord.Embed(
            title=f"{display_name}",
            description=f"👋 {saludo}",
            color=discord.Color.blue()
        )
        
        if avatar_file:
            embed.set_thumbnail(url=f"attachment://{avatar_attachment_name}")
        elif fallback_avatar_url:
            embed.set_thumbnail(url=fallback_avatar_url)
        
        # Create the reply button view for this server
        view = ReplyButtonView(guild, server_id, timeout=300.0)
        
        # Send unified message with embed, avatar (if local), and reply button
        if avatar_file:
            greeting_message = await user.send(embed=embed, file=avatar_file, view=view)
        else:
            greeting_message = await user.send(embed=embed, view=view)
        view.message = greeting_message
        
        logger.info(f"🔄 Presence DM sent to {user_name} (server: {guild.name}) with reply button")
        
        # Update tracking
        current_time = time.time()
        last_greeting_key = f"presence_greeting_{user_id}"
        _last_greetings[last_greeting_key] = current_time
        _last_greetings[f"{last_greeting_key}_recent"] = current_time
        
        # Record greeting in memory so we don't spam the user until they reply
        record_pending_greeting(user_id, server_name)
        
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
        # Send fallback with unified message (embed + greeting + button)
        try:
            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            if user:
                discord_cfg = greeting_data.get('discord_cfg', {})
                presence_cfg = discord_cfg.get("member_presence", {})
                fallback_msg = presence_cfg.get("fallback", "Welcome back!")
                fallback_msg = fallback_msg.format(user_name=user_name)
                
                # Create unified message with personality embed + fallback + reply button
                from discord_bot.discord_utils import get_server_personality_display_name, get_server_personality_avatar_path
                import os
                
                # Get personality display name (server-specific priority)
                display_name = None
                if server_id:
                    personality_name = get_server_personality_display_name(server_id)
                    if personality_name:
                        display_name = personality_name
                
                # Fallback to guild nickname or global display name
                if not display_name and guild:
                    bot_member = guild.me
                    if bot_member and bot_member.nick:
                        display_name = bot_member.nick
                if not display_name:
                    display_name = bot.user.display_name
                
                # Get local personality avatar file (server-specific)
                avatar_file = None
                avatar_attachment_name = None
                if server_id:
                    local_avatar_path = get_server_personality_avatar_path(server_id)
                    if local_avatar_path and os.path.exists(local_avatar_path):
                        avatar_attachment_name = os.path.basename(local_avatar_path)
                        avatar_file = discord.File(local_avatar_path, filename=avatar_attachment_name)
                
                # Fallback: global bot avatar URL if no local file
                fallback_avatar_url = None
                if not avatar_file:
                    fallback_avatar_url = bot.user.display_avatar.url if bot.user.display_avatar else None
                
                # Create personality embed with fallback as description
                embed = discord.Embed(
                    title=f"{display_name}",
                    description=f"👋 {fallback_msg}",
                    color=discord.Color.blue()
                )
                
                if avatar_file:
                    embed.set_thumbnail(url=f"attachment://{avatar_attachment_name}")
                elif fallback_avatar_url:
                    embed.set_thumbnail(url=fallback_avatar_url)
                
                # Create the reply button view for this server
                view = ReplyButtonView(guild, server_id, timeout=300.0)
                
                # Send unified message with embed, avatar (if local), and reply button
                if avatar_file:
                    await user.send(embed=embed, file=avatar_file, view=view)
                else:
                    await user.send(embed=embed, view=view)
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
        if has_unreplied_greeting(user_id):
            logger.info(f"Found unreplied greeting for user {user_id} in memory tracker")
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking unreplied greetings for {user_id}: {e}")
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
    
    result = "\n\n".join(non_empty_sections)
    
    # Validate result is not empty
    if not result or not result.strip():
        logger.warning(f"🧠 [GREET] build_greeting_prompt returning empty prompt (server={server_name}, user={user_display_name}, user_id={user_id})")
        # Fallback to minimal prompt
        result = f"{task}\n\n{response_title}"
    
    return result

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
                # Get user's display name for this specific server
                member = guild.get_member(after.id)
                if member:
                    user_display_name = member.display_name
                else:
                    # Fallback to global name if member not found in guild
                    user_display_name = after.global_name or after.name
                
                greeting_data = {
                    'discord_cfg': discord_cfg,
                    'presence_cfg': presence_cfg
                }
                await _send_greeting_to_user(after.id, user_display_name, guild, greeting_data, bot)
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
