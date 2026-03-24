"""
Discord bot module for RoleAgentBot.

This module contains all Discord-related functionality:
- Main Discord bot (agent_discord.py)
- Core commands (discord_core_commands.py)
- Role command loader (discord_role_loader.py)
- Shared utilities (discord_utils.py)
- HTTP client (discord_http.py)
"""

# Note: agent_discord.py is meant to be run as a script, not imported
# from .agent_discord import run_bot

from .discord_core_commands import register_core_commands
from .discord_role_loader import register_all_role_commands, register_single_role
from .discord_utils import (
    get_db_for_server,
    send_dm_or_channel, send_embed_dm_or_channel,
    is_admin, is_duplicate_command, is_role_enabled_check,
    get_greeting_enabled, set_greeting_enabled,
    check_chat_rate_limit, is_already_initialized, mark_as_initialized,
    acquire_connection_lock, acquire_process_lock,
    get_connection_lock, get_is_connected, set_is_connected
)
from .discord_http import DiscordHTTP

__all__ = [
    'register_core_commands',
    'register_all_role_commands',
    'register_single_role',
    'get_db_for_server', 
    'send_dm_or_channel',
    'send_embed_dm_or_channel',
    'is_admin',
    'is_duplicate_command',
    'is_role_enabled_check',
    'get_greeting_enabled',
    'set_greeting_enabled',
    'check_chat_rate_limit',
    'is_already_initialized',
    'mark_as_initialized',
    'acquire_connection_lock',
    'acquire_process_lock',
    'get_connection_lock',
    'get_is_connected',
    'set_is_connected',
    'DiscordHTTP'
]

__version__ = "1.0.0"
__author__ = "RoleAgentBot"
