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

# Store pending greetings for server selection
_pending_greetings = {}


class ServerSelectionButton(discord.ui.Button):
    """Button for selecting a specific server for greeting."""
    
    def __init__(self, guild: discord.Guild, greeting_data: dict, row: int = 0):
        # Truncate guild name if too long for button label
        label = guild.name[:80] if len(guild.name) > 80 else guild.name
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            emoji="🏠",
            row=row
        )
        self.guild = guild
        self.greeting_data = greeting_data
    
    async def callback(self, interaction: discord.Interaction):
        """Handle server selection and send greeting."""
        user_id = str(interaction.user.id)
        
        # Remove the selection message
        try:
            await interaction.message.delete()
        except Exception as e:
            logger.debug(f"Could not delete server selection message: {e}")
        
        # Send the greeting for selected server
        await _send_greeting_to_user(
            user_id=interaction.user.id,
            user_name=interaction.user.display_name,
            guild=self.guild,
            greeting_data=self.greeting_data,
            bot=self.view.bot
        )
        
        # Clean up pending greeting
        if user_id in _pending_greetings:
            del _pending_greetings[user_id]


class ServerSelectionView(discord.ui.View):
    """View with buttons for selecting which server to greet from."""
    
    def __init__(self, bot: discord.Client, greeting_data: dict, timeout: float = 300.0):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.greeting_data = greeting_data
        self._add_server_buttons()
    
    def _add_server_buttons(self):
        """Add a button for each mutual server."""
        guilds = self.greeting_data.get('mutual_guilds', [])
        
        # Add buttons (max 25 buttons per view, but practically limited by row system)
        for i, guild in enumerate(guilds[:25]):  # Discord limit is 25 buttons
            row = i // 5  # 5 buttons per row
            if row > 4:  # Max 5 rows (0-4)
                break
            self.add_item(ServerSelectionButton(guild, self.greeting_data, row=row))
    
    async def on_timeout(self):
        """Called when the view times out."""
        # Clean up pending greeting
        for user_id, data in list(_pending_greetings.items()):
            if data.get('view') == self:
                del _pending_greetings[user_id]
                break
        
        # Disable all buttons
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        
        # Try to update the message
        if self.message:
            try:
                await self.message.edit(content="⏰ Server selection timed out. Use `!talk` or mention me to chat!", view=self)
            except Exception as e:
                logger.debug(f"Could not update timed out server selection: {e}")


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
        
        # Send greeting with personality embed (server-specific avatar and name)
        await send_dm_with_personality(user, bot, f"👋 {saludo}", guild, server_id)
        logger.info(f"🔄 Presence DM sent to {user_name} (server: {guild.name})")
        
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
    
    # Check if user already has a pending greeting selection
    user_id_str = str(after.id)
    if user_id_str in _pending_greetings:
        logger.info(f"User {after.name} already has a pending server selection")
        return
    
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
        
        # Update tracking immediately to prevent duplicate greetings
        _last_greetings[last_greeting_key] = current_time
        _last_greetings[f"{last_greeting_key}_recent"] = current_time
        
        # If user is only in one eligible server, send greeting directly
        if len(eligible_guilds) == 1:
            guild = eligible_guilds[0]
            greeting_data = {
                'discord_cfg': discord_cfg,
                'presence_cfg': presence_cfg
            }
            await _send_greeting_to_user(after.id, after.display_name, guild, greeting_data, bot)
            return
        
        # User is in multiple servers - show server selection
        logger.info(f"User {after.name} is in {len(eligible_guilds)} servers - showing selection")
        
        # Build server selection embed
        avatar_url = bot.user.display_avatar.url if bot.user.display_avatar else None
        
        selection_embed = discord.Embed(
            title=f"{bot_display_name}",
            description="I see you're in multiple servers with me! Which server should I greet you for?",
            color=discord.Color.blue()
        )
        
        if avatar_url:
            selection_embed.set_thumbnail(url=avatar_url)
        
        # List the servers
        server_list = "\n".join([f"🏠 {g.name}" for g in eligible_guilds[:10]])
        if len(eligible_guilds) > 10:
            server_list += f"\n... and {len(eligible_guilds) - 10} more"
        
        selection_embed.add_field(
            name="Your Servers",
            value=server_list or "No eligible servers",
            inline=False
        )
        
        selection_embed.set_footer(text="Click a button below to choose • You have 5 minutes")
        
        # Create greeting data for the view
        greeting_data = {
            'discord_cfg': discord_cfg,
            'presence_cfg': presence_cfg,
            'mutual_guilds': eligible_guilds,
            'user_name': after.display_name
        }
        
        # Create and store the view
        view = ServerSelectionView(bot, greeting_data, timeout=300.0)
        _pending_greetings[user_id_str] = {
            'view': view,
            'timestamp': current_time
        }
        
        # Send the selection message
        try:
            selection_message = await after.send(embed=selection_embed, view=view)
            view.message = selection_message
            logger.info(f"� Server selection sent to {after.name} for {len(eligible_guilds)} servers")
        except discord.errors.Forbidden:
            logger.warning(f"Cannot send server selection DM to {after.name} (Forbidden)")
        except Exception as e:
            logger.error(f"Error sending server selection to {after.name}: {e}")
            
    except Exception as e:
        logger.error(f"Error in presence greeting for {after.name}: {e}")

def clear_greeting_cache():
    """Clear the greeting cache - useful for testing or resets."""
    global _last_greetings
    _last_greetings.clear()
    logger.info("Greeting cache cleared")
