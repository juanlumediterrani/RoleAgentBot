"""
Shared utilities for the Discord bot.
Per-server DB access, permission helpers, and message sending functions.
"""

import os
import sys
import time
import hashlib
from datetime import datetime, timedelta

# Add parent directory to Python path to import root modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_logging import get_logger
from agent_db import get_db_instance, set_current_server, get_active_server_name

logger = get_logger('discord_utils')

# --- PER-SERVER DB ACCESS ---

def get_server_name(guild) -> str:
    """Get a sanitized name for the server."""
    if guild is None:
        active = get_active_server_name()
        if active:
            return active
        return "default"
    return guild.name.lower().replace(' ', '_').replace('-', '_')


def get_server_key(guild) -> str:
    """Get a stable unique server key (Discord guild id) for per-server resources."""
    if guild is None:
        active = get_active_server_name()
        if active:
            return active
        return "default"
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


def _get_behavior_db_for_guild(guild):
    if guild is None or get_behaviors_db_instance is None:
        return None
    try:
        return get_behaviors_db_instance(get_server_key(guild))
    except Exception as e:
        logger.warning(f"Error getting behavior DB for guild: {e}")
        return None


# --- PERMISSION HELPERS ---

def is_admin(ctx) -> bool:
    """Check if the user is an administrator or has manage_guild."""
    if not ctx.guild:
        return False
    # Handle both Context and Interaction objects
    user = ctx.author if hasattr(ctx, 'author') else ctx.user
    perms = user.guild_permissions
    return perms.administrator or perms.manage_guild


def is_role_enabled_check(role_name, agent_config=None, guild=None):
    """Check if a role is enabled using persisted server state with config fallback."""
    default_enabled = False
    if agent_config is not None:
        default_enabled = agent_config.get("roles", {}).get(role_name, {}).get("enabled", False)
    db = _get_behavior_db_for_guild(guild)
    if db is not None:
        try:
            return db.get_role_enabled(role_name, default_enabled)
        except Exception as e:
            logger.warning(f"Error getting persisted role enabled state for {role_name}: {e}")
    return default_enabled


def set_role_enabled(guild, role_name: str, enabled: bool, agent_config=None, updated_by: str = None):
    """Persist role enabled state and keep the in-memory config aligned."""
    if agent_config is not None:
        agent_config.setdefault("roles", {}).setdefault(role_name, {})["enabled"] = enabled
    db = _get_behavior_db_for_guild(guild)
    if db is None:
        return False
    try:
        db.set_role_enabled(role_name, enabled, updated_by)
        return True
    except Exception as e:
        logger.error(f"Error persisting role enabled state for {role_name}: {e}")
        return False


def get_role_interval_hours(role_name: str, agent_config=None, guild=None, default_value: int = 1) -> int:
    """Get persisted role interval with config fallback."""
    fallback = default_value
    if agent_config is not None:
        fallback = agent_config.get("roles", {}).get(role_name, {}).get("interval_hours", default_value)
    db = _get_behavior_db_for_guild(guild)
    if db is not None:
        try:
            return db.get_role_interval_hours(role_name, fallback)
        except Exception as e:
            logger.warning(f"Error getting persisted interval for {role_name}: {e}")
    return fallback


def set_role_interval_hours(guild, role_name: str, hours: int, agent_config=None, updated_by: str = None):
    """Persist role interval and keep the in-memory config aligned."""
    if agent_config is not None:
        agent_config.setdefault("roles", {}).setdefault(role_name, {})["interval_hours"] = hours
    db = _get_behavior_db_for_guild(guild)
    if db is None:
        return False
    try:
        db.set_role_interval_hours(role_name, hours, updated_by)
        return True
    except Exception as e:
        logger.error(f"Error persisting interval for {role_name}: {e}")
        return False


def get_feature_state(guild, feature_name: str, default_enabled: bool = False, default_config: dict | None = None) -> dict:
    """Get persisted feature state with fallback defaults."""
    db = _get_behavior_db_for_guild(guild)
    default_config = dict(default_config or {})
    if db is None:
        return {"enabled": default_enabled, "config": default_config}
    try:
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
    db = _get_behavior_db_for_guild(guild)
    if db is None:
        return False
    try:
        db.set_feature_state(feature_name, enabled, config or {}, updated_by)
        return True
    except Exception as e:
        logger.error(f"Error persisting feature state for {feature_name}: {e}")
        return False


def get_feature_setting(guild, feature_name: str, setting_key: str, default_value=None):
    """Get a persisted feature setting."""
    db = _get_behavior_db_for_guild(guild)
    if db is None:
        return default_value
    try:
        return db.get_feature_setting(feature_name, setting_key, default_value)
    except Exception as e:
        logger.warning(f"Error getting feature setting {feature_name}.{setting_key}: {e}")
        return default_value


def set_feature_setting(guild, feature_name: str, setting_key: str, value, updated_by: str = None):
    """Persist a feature setting."""
    db = _get_behavior_db_for_guild(guild)
    if db is None:
        return False
    try:
        db.set_feature_setting(feature_name, setting_key, value, updated_by)
        return True
    except Exception as e:
        logger.error(f"Error persisting feature setting {feature_name}.{setting_key}: {e}")
        return False


# --- SEND HELPERS ---

async def send_dm_or_channel(ctx, content, confirm_msg="📩 Info sent by private message."):
    """Send content via DM if possible, otherwise to channel. Handles messages >2000 chars."""
    import discord
    try:
        if len(content) > 2000:
            partes = [content[i:i+1900] for i in range(0, len(content), 1900)]
            for parte in partes:
                await ctx.author.send(parte)
        else:
            await ctx.author.send(content)
        if ctx.guild:
            await ctx.send(confirm_msg)
    except discord.errors.Forbidden:
        if len(content) > 2000:
            partes = [content[i:i+1900] for i in range(0, len(content), 1900)]
            for parte in partes:
                await ctx.send(parte)
        else:
            await ctx.send(content[:2000])


async def send_embed_dm_or_channel(ctx, embed, confirm_msg="📩 Info sent by private message."):
    """Send an embed via DM if possible, otherwise to channel."""
    import discord
    try:
        await ctx.author.send(embed=embed)
        if ctx.guild:
            await ctx.send(confirm_msg)
    except discord.errors.Forbidden:
        await ctx.send(embed=embed)


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
    """Determine if greetings should be enabled, checking database first."""
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
            
            logger.info(f"Server {guild.name}: greetings {'enabled' if enabled else 'disabled'} from behaviors database")
            return enabled
        except Exception as e:
            logger.warning(f"Error loading greetings from behaviors database for {guild.name}: {e}")
    
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
    """Manually set greeting state for a server and persist to database."""
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
            logger.info(f"Greetings {'enabled' if enabled else 'disabled'} and saved to behaviors database for {guild.name}")
        except Exception as e:
            logger.error(f"Failed to save greetings state to behaviors database for {guild.name}: {e}")
    else:
        logger.warning(f"Behaviors database not available, greetings state not persisted for {guild.name}")

    logger.info(f"Greetings {'enabled' if enabled else 'disabled'} manually in {guild.name}")


def get_greeting_enabled(guild) -> bool:
    """Get current greeting state for a server."""
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
