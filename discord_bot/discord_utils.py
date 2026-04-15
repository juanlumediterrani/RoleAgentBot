"""
Shared utilities for the Discord bot.
Per-server DB access, permission helpers, and message sending functions.
"""

import os
import time
import hashlib
import json
from datetime import datetime, timedelta

import discord
from agent_logging import get_logger
from agent_db import get_db_instance, set_current_server, get_server_id

logger = get_logger('discord_utils')

# --- PER-SERVER DB ACCESS ---



def get_server_key(guild) -> str:
    """Get a stable unique server key (Discord guild id) for per-server resources."""
    if guild is None:
        # Always use the active server ID from .active_server file
        active = get_server_id()
        if active and active.isdigit():
            return active  # Return the guild ID
        return "0"  # Fallback to default server ID
    return str(guild.id)


def get_db_for_server(guild):
    """Get DB instance for a specific server."""
    server_key = get_server_key(guild)
    return get_db_instance(server_key)


def get_role_db_for_server(guild, get_db_func, available_flag):
    """Generic helper to get a role's DB for a server."""
    if not available_flag:
        return None
    server_key = get_server_key(guild)
    return get_db_func(server_key)


# --- PERMISSION HELPERS ---

def is_admin(ctx) -> bool:
    """Check if the user is an administrator or has manage_guild."""
    if not ctx.guild:
        return False
    # Handle both Context and Interaction objects
    user = ctx.author if hasattr(ctx, 'author') else ctx.user
    perms = user.guild_permissions
    return perms.administrator or perms.manage_guild


def initialize_roles_from_database(agent_config=None, guild=None) -> bool:
    """Initialize roles system - PRIMARY: roles_config, SECONDARY: behavior table."""
    try:
        logger.info("Initializing roles system - database is primary source")
        
        # PRIMARY: Initialize roles_config from agent_config.json
        try:
            from agent_roles_db import get_roles_db_instance
            # Use guild-specific server_id if available, otherwise default to "0"
            server_id = str(guild.id) if guild else "0"
            roles_db = get_roles_db_instance(server_id)
            
            # First, migrate from agent_config.json if available
            if agent_config:
                logger.info("Migrating roles from agent_config to roles_config")
                # Create a temporary agent_config file for migration
                import json
                import tempfile
                import os
                
                temp_config_path = None
                try:
                    # Create temporary file with agent_config data
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                        json.dump(agent_config, f, indent=2)
                        temp_config_path = f.name
                    
                    # Migrate from agent_config to roles_config
                    migrated = roles_db.migrate_roles_from_agent_config(temp_config_path)
                    if migrated:
                        logger.info("Successfully migrated roles from agent_config to roles_config")
                finally:
                    # Clean up temporary file
                    if temp_config_path and os.path.exists(temp_config_path):
                        os.unlink(temp_config_path)
            
            # Then ensure all default roles exist
            roles_db.ensure_default_roles()
            
        except Exception as e:
            logger.error(f"Error initializing roles_config: {e}")
        
        # Verify roles_config is working by checking all roles
        try:
            from agent_roles_db import get_roles_db_instance
            # Use the same server_id as above for verification
            roles_db = get_roles_db_instance(server_id)
            
            all_roles = ["news_watcher", "treasure_hunter", "trickster", "banker", "mc", "ring", "dice_game"]
            for role_name in all_roles:
                try:
                    # Get enabled state from agent_config if available, otherwise default to True for MC
                    default_enabled = False
                    if agent_config:
                        default_enabled = agent_config.get("roles", {}).get(role_name, {}).get("enabled", False)
                    elif role_name == "mc":
                        # MC should always default to enabled as per user requirement
                        default_enabled = True
                    
                    # This will create role in roles_config if it doesn't exist
                    config = roles_db.get_role_config(role_name, default_enabled)
                except Exception as e:
                    logger.error(f"Error verifying role {role_name} in roles_config: {e}")
                    
        except Exception as e:
            logger.error(f"Error verifying roles_config: {e}")
        
        logger.info("Roles system initialized successfully - roles_config is primary source")
        return True
        
    except Exception as e:
        logger.error(f"Error initializing roles from database: {e}")
        return False


def is_role_enabled_check(role_name, agent_config=None, guild=None):
    """Check if a role is enabled - PRIMARY source: roles table, fallback: agent_config."""
    # SPECIAL CASE: MC is always enabled (does not depend on database state like other roles)
    if role_name == "mc":
        return True
    
    # PRIMARY: Try to get from roles_config with auto-creation
    try:
        from agent_roles_db import get_roles_db_instance
        from agent_db import get_server_id
        server_id = str(guild.id) if guild else get_server_id()
        roles_db = get_roles_db_instance(server_id)

        # Use default_enabled=True for auto-creation (like behavior.db)
        config = roles_db.get_role_config(role_name, default_enabled=True)
        if config:
            return config.get('enabled', True)
    except Exception as e:
        logger.warning(f"Error getting role enabled state from roles_config for {role_name}: {e}")
    
    # FALLBACK: Use agent_config only if database fails
    logger.info(f"Using agent_config fallback for role {role_name} (database unavailable)")
    default_enabled = False
    if agent_config is not None:
        default_enabled = agent_config.get("roles", {}).get(role_name, {}).get("enabled", False)
    return default_enabled


def set_role_enabled(guild, role_name: str, enabled: bool, agent_config=None, updated_by: str = None):
    """Persist role enabled state - PRIMARY: roles_config only."""
    import json
    
    # PRIMARY: Save to roles_config
    success = False
    try:
        from agent_roles_db import get_roles_db_instance
        from agent_db import get_server_id
        server_id = str(guild.id) if guild else get_server_id()
        roles_db = get_roles_db_instance(server_id)

        # Get existing config or create new one
        try:
            existing_config = roles_db.get_role_config(role_name)
            if existing_config and existing_config.get('config_data'):
                config_data = json.loads(existing_config['config_data'])
            else:
                config_data = {}
        except:
            config_data = {}
        
        # Update enabled state
        config_data['updated_by'] = updated_by
        config_data['updated_at'] = '2026-03-28T01:28:00'
        
        success = roles_db.save_role_config(role_name, enabled, json.dumps(config_data))
        if success:
            logger.info(f"Role {role_name} set to {enabled} in roles_config for server {getattr(guild, 'name', 'unknown')}")
    except Exception as e:
        logger.error(f"Error saving role enabled state to roles_config for {role_name}: {e}")
    
    # SECONDARY: Keep agent_config aligned (for backwards compatibility)
    if agent_config is not None:
        agent_config.setdefault("roles", {}).setdefault(role_name, {})["enabled"] = enabled
        logger.debug(f"Synced agent_config for role {role_name} = {enabled}")
    
    return success


def get_feature_state(guild, feature_name: str, default_enabled: bool = False, default_config: dict | None = None) -> dict:
    """Get persisted feature state with fallback defaults."""
    from behavior.db_behavior import get_behavior_db_instance
    
    default_config = dict(default_config or {})
    try:
        db = get_behavior_db_instance(get_server_key(guild))
        if db is None:
            return {"enabled": default_enabled, "config": default_config}
        state = db.get_feature_state(feature_name)
        enabled = bool(state.get("enabled", default_enabled))
        config = dict(default_config)
        config.update(state.get("config") or {})
        return {"enabled": enabled, "config": config}
    except Exception as e:
        logger.warning(f"Error getting feature state for {feature_name}: {e}")
        return {"enabled": default_enabled, "config": default_config}


def set_feature_state(guild, feature_name: str, enabled: bool, config: dict | None = None, updated_by: str = None):
    """Persist feature state."""
    from behavior.db_behavior import get_behavior_db_instance
    
    try:
        db = get_behavior_db_instance(get_server_key(guild))
        if db is None:
            return False
        db.set_feature_state(feature_name, enabled, config or {}, updated_by)
        return True
    except Exception as e:
        logger.error(f"Error setting feature state for {feature_name}: {e}")
        return False


def get_feature_setting(guild, feature_name: str, setting_key: str, default_value=None):
    """Get a persisted feature setting."""
    from behavior.db_behavior import get_behavior_db_instance
    
    try:
        db = get_behavior_db_instance(get_server_key(guild))
        if db is None:
            return default_value
        return db.get_behavior_setting(feature_name, setting_key, default_value)
    except Exception as e:
        logger.warning(f"Error getting feature setting {feature_name}.{setting_key}: {e}")
        return default_value


def set_feature_setting(guild, feature_name: str, setting_key: str, value, updated_by: str = None):
    """Persist a feature setting."""
    from behavior.db_behavior import get_behavior_db_instance
    
    try:
        db = get_behavior_db_instance(get_server_key(guild))
        if db is None:
            return False
        db.set_behavior_setting(feature_name, setting_key, value, updated_by)
        return True
    except Exception as e:
        logger.error(f"Error setting feature setting {feature_name}.{setting_key}: {e}")
        return False


# --- SEND HELPERS ---

async def send_dm_or_channel(ctx, content, confirm_msg="📩 Message sent by direct message."):
    """Send content by direct message when possible, otherwise send it to the channel. Handles messages longer than 2000 characters."""
    import discord
    try:
        if len(content) > 2000:
            dm_chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
            for chunk in dm_chunks:
                await ctx.author.send(chunk)
        else:
            await ctx.author.send(content)
        if ctx.guild:
            await ctx.send(confirm_msg)
    except discord.errors.Forbidden:
        if len(content) > 2000:
            channel_chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
            for chunk in channel_chunks:
                await ctx.send(chunk)
        else:
            await ctx.send(content[:2000])


async def send_embed_dm_or_channel(ctx, embed, confirm_msg="📩 Message sent by direct message."):
    """Send an embed by direct message when possible, otherwise send it to the channel."""
    import discord
    try:
        await ctx.author.send(embed=embed)
        if ctx.guild:
            await ctx.send(confirm_msg)
    except discord.errors.Forbidden:
        await ctx.send(embed=embed)


async def send_personality_embed_dm(target, bot: discord.Client, guild: discord.Guild = None, server_id: str = None):
    """
    Send an embed with the bot's server-specific avatar and personality name before DM content.
    
    This function creates a "header" embed showing the bot's personality identity
    specific to the server where the interaction originated.
    
    Args:
        target: The target user (discord.Member or discord.User) to send DM to
        bot: The Discord bot client instance
        guild: Optional Discord guild to get server-specific nickname and avatar
        server_id: Optional server ID (used if guild not provided)
        
    Returns:
        bool: True if embed was sent successfully, False otherwise
    """
    try:
        # Determine effective server_id - prioritize passed server_id over guild.id
        # This ensures DM sessions use the pinned server_id even if guild resolution fails
        effective_server_id = server_id if server_id else (str(guild.id) if guild else None)
        logger.info(f"📨 send_personality_embed_dm: passed server_id={server_id}, guild={guild.name if guild else 'None'}, effective_server_id={effective_server_id}")

        # Get personality display name (server-specific priority)
        display_name = None
        if effective_server_id:
            # First try: server-specific personality.json bot_display_name
            personality_name = get_server_personality_display_name(effective_server_id)
            if personality_name:
                display_name = personality_name
                logger.info(f"📨 Got display_name from server-specific: {display_name}")
        
        # Second try: guild nickname
        if not display_name and guild:
            bot_member = guild.me
            if bot_member and bot_member.nick:
                display_name = bot_member.nick
        
        # Third try: global display name
        if not display_name:
            display_name = bot.user.display_name
        
        # Get local personality avatar file (server-specific, NOT global bot avatar)
        avatar_file = None
        avatar_attachment_name = None
        if effective_server_id:
            local_avatar_path = get_server_personality_avatar_path(effective_server_id)
            if local_avatar_path and os.path.exists(local_avatar_path):
                avatar_attachment_name = os.path.basename(local_avatar_path)
                avatar_file = discord.File(local_avatar_path, filename=avatar_attachment_name)
                logger.info(f"📨 Got avatar from server-specific: {local_avatar_path}")
        
        # Fallback: global bot avatar URL if no local file
        fallback_avatar_url = None
        if not avatar_file:
            fallback_avatar_url = bot.user.display_avatar.url if bot.user.display_avatar else None
        
        # Create personality embed
        embed = discord.Embed(
            title=f"{display_name}",
            description="*Sending you a message...*",
            color=discord.Color.blue()
        )
        
        if avatar_file:
            embed.set_thumbnail(url=f"attachment://{avatar_attachment_name}")
        elif fallback_avatar_url:
            embed.set_thumbnail(url=fallback_avatar_url)
        
        # Send the personality embed
        if avatar_file:
            await target.send(embed=embed, file=avatar_file)
        else:
            await target.send(embed=embed)
        logger.info(f"📨 Personality embed → {target.name} | server_id={effective_server_id} | name={display_name} | avatar={'local:'+avatar_attachment_name if avatar_file else 'fallback'}")
        return True
        
    except discord.errors.Forbidden:
        logger.warning(f"Cannot send personality embed DM to {target.name} (Forbidden)")
        return False
    except Exception as e:
        logger.error(f"Error sending personality embed to {target.name}: {e}")
        return False


async def send_dm_with_personality(target, bot: discord.Client, content: str, guild: discord.Guild = None, server_id: str = None):
    """
    Send a DM with personality embed header followed by the message content.
    
    This is a convenience function that sends the personality embed first,
    then sends the actual message content. The embed uses server-specific
    avatar and nickname from the provided guild.
    
    Args:
        target: The target user (discord.Member or discord.User) to send DM to
        bot: The Discord bot client instance
        content: The message content to send
        guild: Optional Discord guild to get server-specific nickname and avatar
        server_id: Optional server ID (used if guild not provided)
        
    Returns:
        bool: True if both messages were sent successfully, False otherwise
    """
    # Send personality embed first with server-specific identity
    embed_sent = await send_personality_embed_dm(target, bot, guild, server_id)
    
    try:
        # Send the actual message content
        await target.send(content)
        logger.debug(f"Sent DM content to {target.name}")
        return True
        
    except discord.errors.Forbidden:
        logger.warning(f"Cannot send DM to {target.name} (Forbidden)")
        return False
    except Exception as e:
        logger.error(f"Error sending DM to {target.name}: {e}")
        return False


# --- EVENT AND DUPLICATE CONTROL ---

_event_cache = {}
_cache_ttl = timedelta(seconds=5)
_last_command_time = {}

# Rate limiting for LLM chat
_chat_rate_limit = {}
CHAT_COOLDOWN_SECONDS = 3


def get_event_key(event_type, ctx_or_message):
    """Generate a unique key for each event."""
    if hasattr(ctx_or_message, 'id'):
        key_data = f"{event_type}_{ctx_or_message.id}_{ctx_or_message.author.id}"
    else:
        key_data = f"{event_type}_{str(ctx_or_message)}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:16]


def is_event_processed(event_key):
    """Check if an event was already processed."""
    now = datetime.now()
    if event_key in _event_cache:
        if now - _event_cache[event_key] < _cache_ttl:
            return True
        else:
            del _event_cache[event_key]
    return False


def mark_event_processed(event_key):
    """Mark an event as processed."""
    _event_cache[event_key] = datetime.now()


def is_duplicate_command(ctx, command_name):
    """Check if the command was already executed recently to avoid duplicates."""
    try:
        if ctx.guild is None:
            channel_id = ctx.channel.id
        else:
            channel_id = ctx.guild.id

        key = f"{command_name}_{channel_id}"
        now = time.time()

        if key in _last_command_time:
            if now - _last_command_time[key] < 1.0:
                return True

        _last_command_time[key] = now
        return False
    except Exception as e:
        logger.error(f"Error checking duplicate command: {e}")
        return False


def check_chat_rate_limit(user_id):
    """Check rate limit for LLM chat messages. Returns True if rate limited."""
    now = time.time()
    if user_id in _chat_rate_limit:
        if now - _chat_rate_limit[user_id] < CHAT_COOLDOWN_SECONDS:
            return True
    _chat_rate_limit[user_id] = now
    return False


# --- DYNAMIC GREETING CONFIGURATION ---

try:
    from behavior.db_behavior import get_behavior_db_instance as get_behaviors_db_instance
except Exception:
    get_behaviors_db_instance = None

_greeting_config = {}


def should_enable_greetings(guild) -> bool:
    """Determine whether greetings should be enabled by checking the database first."""
    guild_id = str(guild.id)
    
    # Check cache first
    if guild_id in _greeting_config:
        return _greeting_config[guild_id].get('enabled', False)
    
    # Try to get from behaviors database
    if get_behaviors_db_instance is not None:
        try:
            db = get_behaviors_db_instance(guild_id)
            enabled = db.get_greetings_enabled()
            
            # Cache the result
            _greeting_config[guild_id] = {
                'enabled': enabled,
                'auto_detected': False,
                'manual_override': True,
                'from_db': True
            }
            
            logger.info(f"Server {guild.name}: greetings {'enabled' if enabled else 'disabled'} loaded from the behavior database")
            return enabled
        except Exception as e:
            logger.warning(f"Error loading greetings from the behavior database for server {guild.name}: {e}")
    
    # Default to enabled - let runtime control decide
    member_count = len([m for m in guild.members if not m.bot])
    auto_enable = True  # Enabled by default

    _greeting_config[guild_id] = {
        'enabled': auto_enable,
        'auto_detected': True,
        'member_count': member_count,
        'from_db': False
    }

    logger.info(f"Server {guild.name}: {member_count} members, greetings {'enabled' if auto_enable else 'disabled'} by default")
    return auto_enable


def set_greeting_enabled(guild, enabled: bool):
    """Manually set the greeting state for a server and persist it to the database."""
    guild_id = str(guild.id)
    if guild_id not in _greeting_config:
        _greeting_config[guild_id] = {}

    # Update cache
    _greeting_config[guild_id]['enabled'] = enabled
    _greeting_config[guild_id]['auto_detected'] = False
    _greeting_config[guild_id]['manual_override'] = True

    # Save to behaviors database
    if get_behaviors_db_instance is not None:
        try:
            db = get_behaviors_db_instance(guild_id)
            db.set_greetings_enabled(enabled, "admin_command")
            logger.info(f"Greetings {'enabled' if enabled else 'disabled'} and persisted to the behavior database for server {guild.name}")
        except Exception as e:
            logger.error(f"Failed to save greetings state to the behavior database for server {guild.name}: {e}")
    else:
        logger.warning(f"Behavior database not available; greeting state was not persisted for server {guild.name}")

    logger.info(f"Greetings {'enabled' if enabled else 'disabled'} manually for server {guild.name}")


def get_greeting_enabled(guild) -> bool:
    """Return whether greetings are currently enabled for a server."""
    return should_enable_greetings(guild)


# --- PROCESS LOCKING ---

import threading
import fcntl
import tempfile

_connection_lock = threading.Lock()
_is_connected = False
_lock_file_path = None


def acquire_connection_lock(personality_name="bot"):
    """Acquire a system-level lock to prevent multiple instances."""
    global _lock_file_path

    try:
        _lock_file_path = tempfile.NamedTemporaryFile(
            delete=False, prefix=f'discord_bot_lock_{personality_name}_'
        )
        _lock_file_path.close()

        lock_fd = open(_lock_file_path.name, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        logger.info(f"Lock acquired: {_lock_file_path.name}")
        return lock_fd
    except (IOError, OSError) as e:
        if e.errno == 11:
            logger.warning("Another bot instance is already running")
            if _lock_file_path and os.path.exists(_lock_file_path.name):
                os.unlink(_lock_file_path.name)
            return None
        logger.error(f"Error acquiring lock: {e}")
        return None


def acquire_process_lock(personality_name="bot"):
    """Acquire process-level lock using Unix socket."""
    import socket
    socket_path = f"/tmp/discord_bot_{personality_name}.sock"
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(socket_path)
        logger.info(f"Process lock acquired: {socket_path}")
        return sock
    except (OSError, socket.error) as e:
        if e.errno == 98:
            logger.warning("Bot is already running (process lock)")
            return None
        logger.error(f"Error acquiring process lock: {e}")
        return None


def is_already_initialized(personality_name="bot"):
    """Check if the bot was already initialized using state file."""
    state_file = f"/tmp/discord_bot_{personality_name}_initialized.flag"
    try:
        return os.path.exists(state_file)
    except Exception:
        return False


def mark_as_initialized(personality_name="bot"):
    """Mark the bot as initialized."""
    state_file = f"/tmp/discord_bot_{personality_name}_initialized.flag"
    try:
        with open(state_file, 'w') as f:
            f.write("initialized")
        logger.info("Bot marked as initialized")
    except Exception as e:
        logger.error(f"Error marking initialization: {e}")


def get_connection_lock():
    """Return the threading connection lock."""
    return _connection_lock


def get_is_connected():
    global _is_connected
    return _is_connected


def set_is_connected(value):
    global _is_connected
    _is_connected = value


# --- SERVER LANGUAGE DETECTION ---

def detect_server_language(guild) -> str:
    """
    Detect the preferred language of a Discord server.
    
    Method 1 (Primary): Use guild.preferred_locale if available
    Method 2 (Fallback): Analyze member locales to infer predominant language
    
    Returns:
        str: Language code in IETF BCP 47 format (e.g., 'en-US', 'es-ES', 'de')
              Defaults to 'en-US' if detection fails
    """
    if guild is None:
        return 'en-US'
    
    # Method 1: Try guild.preferred_locale (only available for DISCOVERABLE servers)
    if hasattr(guild, 'preferred_locale') and guild.preferred_locale:
        locale = guild.preferred_locale
        logger.info(f"Server '{guild.name}' preferred_locale detected: {locale}")
        return locale
    
    # Method 2: Fallback - analyze member locales
    try:
        from collections import Counter
        member_locales = []
        
        # Collect locales from members who have them set
        for member in guild.members:
            if hasattr(member, 'locale') and member.locale:
                member_locales.append(member.locale)
        
        if member_locales:
            # Find most common locale
            most_common = Counter(member_locales).most_common(1)[0][0]
            logger.info(f"Server '{guild.name}' language inferred from members: {most_common} (based on {len(member_locales)} members)")
            return most_common
        else:
            logger.info(f"Server '{guild.name}' no member locales available, using default 'en-US'")
    except Exception as e:
        logger.warning(f"Error analyzing member locales for server '{guild.name}': {e}")
    
    # Default fallback
    return 'en-US'


# --- SERVER-SPECIFIC BOT IDENTITY ---

async def update_server_identity(guild: discord.Guild, nickname: str = None, avatar_bytes: bytes = None) -> bool:
    """
    Update bot's server-specific identity (nickname + avatar) in a single API call.
    
    Uses PATCH /guilds/{guild.id}/members/@me with both nick and avatar fields
    to minimize rate limit risk.
    
    Args:
        guild: Discord guild object
        nickname: New nickname (None to keep current)
        avatar_bytes: Avatar image bytes (None to keep current, empty bytes to remove)
    
    Returns:
        bool: True if successful
    """
    try:
        bot_member = guild.me
        
        # Build kwargs for combined edit
        edit_kwargs = {}
        if nickname is not None:
            edit_kwargs['nick'] = nickname if nickname else None
        if avatar_bytes is not None:
            # Empty bytes means remove avatar, otherwise set new avatar
            edit_kwargs['avatar'] = avatar_bytes if avatar_bytes else None
        
        if not edit_kwargs:
            logger.debug(f"No identity changes needed for '{guild.name}'")
            return True
        
        # Single API call for both nickname and avatar
        await bot_member.edit(**edit_kwargs)
        
        changes = []
        if 'nick' in edit_kwargs:
            changes.append(f"nick='{nickname}'")
        if 'avatar' in edit_kwargs:
            changes.append(f"avatar={'updated' if avatar_bytes else 'removed'}")
        
        logger.info(f"✅ Identity updated in '{guild.name}': {', '.join(changes)}")
        return True
        
    except discord.Forbidden:
        logger.warning(f"⚠️ No permission to change identity in '{guild.name}' (need 'Change Nickname' permission)")
        return False
    except discord.HTTPException as e:
        if e.status == 429:
            logger.error(f"❌ Rate limited while updating identity in '{guild.name}': {e}")
        else:
            logger.error(f"❌ Failed to update identity in '{guild.name}': {e}")
        return False


async def update_server_nickname(guild: discord.Guild, nickname: str = None) -> bool:
    """
    Update bot's nickname in a specific server.
    
    Wrapper around update_server_identity for backward compatibility.
    Uses single API call optimized approach.
    
    Args:
        guild: Discord guild object
        nickname: New nickname (None to reset to default)
    
    Returns:
        bool: True if successful
    """
    return await update_server_identity(guild, nickname=nickname, avatar_bytes=None)


def _get_server_personality_directory(server_id: str) -> tuple[str, str] | None:
    """
    Get server-specific personality directory path and name.
    
    Helper function to avoid code duplication between display name
    and avatar retrieval functions.
    
    Args:
        server_id: Discord guild ID
        
    Returns:
        tuple[str, str] | None: (directory_path, personality_name) or None
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        server_config_path = os.path.join(base_dir, 'databases', server_id, 'server_config.json')
        
        if not os.path.exists(server_config_path):
            return None
        
        with open(server_config_path, encoding='utf-8') as f:
            server_config = json.load(f)
        
        personality_name = server_config.get('active_personality')
        if not personality_name:
            return None
        
        personality_dir = os.path.join(base_dir, 'databases', server_id, personality_name)
        if not os.path.exists(personality_dir):
            return None
        
        return (personality_dir, personality_name)
        
    except Exception:
        return None


def get_server_personality_display_name(server_id: str) -> str | None:
    """
    Get bot_display_name from server-specific personality.json.
    
    Reads from: databases/<server_id>/<personality>/personality.json
    Returns the 'bot_display_name' field or None if not found.
    
    Args:
        server_id: Discord guild ID
        
    Returns:
        str | None: The display name or None if not found
    """
    result = _get_server_personality_directory(server_id)
    if not result:
        return None
    
    personality_dir, _ = result
    personality_path = os.path.join(personality_dir, 'personality.json')
    
    if not os.path.exists(personality_path):
        return None
    
    try:
        with open(personality_path, encoding='utf-8') as f:
            personality_data = json.load(f)
        
        bot_display_name = personality_data.get('bot_display_name')
        if bot_display_name:
            logger.debug(f"Found bot_display_name '{bot_display_name}' for server {server_id}")
        return bot_display_name
        
    except Exception as e:
        logger.warning(f"Could not read personality display name for {server_id}: {e}")
        return None


def get_server_personality_avatar_path(server_id: str) -> str | None:
    """
    Get path to avatar image from server-specific personality directory.
    
    Avatar is copied to databases/<server_id>/<personality>/avatar.<ext>
    during personality initialisation and updates.
    Falls back to personalities/<name>/avatar.<ext> if the copy is missing.
    
    Args:
        server_id: Discord guild ID
        
    Returns:
        str | None: Full path to avatar file or None if not found
    """
    result = _get_server_personality_directory(server_id)
    if not result:
        return None
    
    personality_dir, personality_name = result
    base_dir = os.path.dirname(os.path.dirname(__file__))
    avatar_extensions = ['.png', '.webp', '.jpg', '.jpeg']
    
    # 1. Server-specific copy (databases/<server_id>/<personality>/)
    for ext in avatar_extensions:
        avatar_path = os.path.join(personality_dir, f'avatar{ext}')
        if os.path.exists(avatar_path):
            logger.debug(f"Found avatar in databases/ for server {server_id}: {avatar_path}")
            return avatar_path
    
    # 2. Fallback: source personalities/<name>/
    personalities_dir = os.path.join(base_dir, 'personalities', personality_name)
    for ext in avatar_extensions:
        avatar_path = os.path.join(personalities_dir, f'avatar{ext}')
        if os.path.exists(avatar_path):
            logger.debug(f"Found avatar in personalities/ for server {server_id}: {avatar_path}")
            return avatar_path
    
    logger.debug(f"No avatar found for server {server_id} (personality: {personality_name})")
    return None


def read_avatar_bytes(avatar_path: str) -> bytes | None:
    """
    Read avatar image file as bytes for Discord API upload.
    
    Args:
        avatar_path: Full path to avatar file
        
    Returns:
        bytes | None: File contents or None if error
    """
    try:
        with open(avatar_path, 'rb') as f:
            avatar_bytes = f.read()
        logger.debug(f"Read avatar file: {avatar_path} ({len(avatar_bytes)} bytes)")
        return avatar_bytes
    except Exception as e:
        logger.error(f"Could not read avatar file {avatar_path}: {e}")
        return None


def translate_dice_combination(combination: str, trickster_messages: dict) -> str:
    """Translate dice combination from stored format to personality-specific text.
    
    The database stores combinations with English fallback (e.g., "6-1-6 (Pair)").
    This function translates the combination name to the current personality's language.
    
    Args:
        combination: The combination string from the database (e.g., "6-1-6 (Pair)")
        trickster_messages: Dictionary of personality-specific trickster messages
        
    Returns:
        str: The combination with personality-specific text instead of English fallback
    """
    if not combination:
        return combination
    
    # Mapping of English fallback names to message keys
    combination_map = {
        "(JACKPOT!)": "triple_ones",
        "(Three of a Kind)": "three_of_a_kind",
        "(Straight)": "straight",
        "(Pair)": "pair",
        "(No Prize)": "nothing",
    }
    
    # Check if the combination contains any of the English fallback names
    for english_name, message_key in combination_map.items():
        if english_name in combination:
            # Get the personality-specific translation
            localized_name = trickster_messages.get(message_key)
            if localized_name:
                # Replace the English name with the localized version
                return combination.replace(english_name, localized_name)
    
    return combination


async def sync_bot_identity_to_server_personality(guild: discord.Guild) -> dict:
    """
    Synchronize bot's server identity (nickname + avatar) with server personality.
    
    This function reads the bot_display_name and avatar from the server-specific 
    personality configuration and updates both in a single API call to minimize 
    rate limit risk.
    
    Args:
        guild: Discord guild object
        
    Returns:
        dict: Status with keys 'success' (bool), 'nickname_changed' (bool), 
              'avatar_changed' (bool), 'errors' (list)
    """
    server_id = str(guild.id)
    
    # Get desired name from personality
    desired_name = get_server_personality_display_name(server_id)
    
    # Get avatar path and read bytes
    avatar_path = get_server_personality_avatar_path(server_id)
    avatar_bytes = None
    if avatar_path:
        avatar_bytes = read_avatar_bytes(avatar_path)
    
    # Check current state
    current_nick = guild.me.nick
    needs_nick_update = desired_name and current_nick != desired_name
    needs_avatar_update = avatar_bytes is not None
    
    if not needs_nick_update and not needs_avatar_update:
        if not desired_name and not avatar_path:
            logger.info(f"No identity configuration for server '{guild.name}', skipping update")
        else:
            logger.debug(f"Identity already correct in '{guild.name}'")
        return {
            'success': True,
            'nickname_changed': False,
            'avatar_changed': False,
            'errors': []
        }
    
    # Prepare parameters for combined update
    new_nick = desired_name if needs_nick_update else None
    new_avatar = avatar_bytes if needs_avatar_update else None
    
    # Log changes
    changes = []
    if needs_nick_update:
        changes.append(f"nick: '{current_nick}' → '{desired_name}'")
    if needs_avatar_update:
        changes.append(f"avatar: updated ({len(avatar_bytes)} bytes)")
    logger.info(f"🔄 Updating bot identity in '{guild.name}': {', '.join(changes)}")
    
    # Single API call for both nickname and avatar
    success = await update_server_identity(guild, new_nick, new_avatar)
    
    if success:
        return {
            'success': True,
            'nickname_changed': needs_nick_update,
            'avatar_changed': needs_avatar_update,
            'errors': []
        }
    else:
        return {
            'success': False,
            'nickname_changed': False,
            'avatar_changed': False,
            'errors': ['Failed to update identity (check permissions)']
        }
