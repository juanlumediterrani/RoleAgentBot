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


def get_db_for_server(guild):
    """Get DB instance for a specific server."""
    server_name = get_server_name(guild)
    return get_db_instance(server_name)


def get_role_db_for_server(guild, get_db_func, available_flag):
    """Generic helper to get a role's DB for a server."""
    if not available_flag:
        return None
    server_name = get_server_name(guild)
    return get_db_func(server_name)


# --- PERMISSION HELPERS ---

def is_admin(ctx) -> bool:
    """Check if the user is an administrator or has manage_guild."""
    if not ctx.guild:
        return False
    perms = ctx.author.guild_permissions
    return perms.administrator or perms.manage_guild


def is_role_enabled_check(role_name, agent_config):
    """Check if a role is enabled using agent_config.json as single source of truth."""
    return agent_config.get("roles", {}).get(role_name, {}).get("enabled", False)


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

_greeting_config = {}


def should_enable_greetings(guild) -> bool:
    """Determine if greetings should be enabled based on server size."""
    guild_id = str(guild.id)
    if guild_id in _greeting_config:
        return _greeting_config[guild_id].get('enabled', False)

    member_count = len([m for m in guild.members if not m.bot])
    auto_enable = member_count <= 30

    _greeting_config[guild_id] = {
        'enabled': auto_enable,
        'auto_detected': True,
        'member_count': member_count
    }

    logger.info(f"Server {guild.name}: {member_count} members, greetings {'enabled' if auto_enable else 'disabled'} by size")
    return auto_enable


def set_greeting_enabled(guild, enabled: bool):
    """Manually set greeting state for a server."""
    guild_id = str(guild.id)
    if guild_id not in _greeting_config:
        _greeting_config[guild_id] = {}

    _greeting_config[guild_id]['enabled'] = enabled
    _greeting_config[guild_id]['auto_detected'] = False
    _greeting_config[guild_id]['manual_override'] = True

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
