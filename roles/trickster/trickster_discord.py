"""
Discord commands for the Trickster role.
NOTE: All commands have been removed. Use !canvas → Trickster instead.
"""

import json
from agent_logging import get_logger

logger = get_logger('trickster_discord')

# Availability flags - kept for Canvas UI integration
try:
    from roles.trickster.subroles.dice_game.dice_game import process_play
    DICE_GAME_AVAILABLE = True
except ImportError:
    process_play = None
    DICE_GAME_AVAILABLE = False

try:
    from roles.banker.banker_db import get_banker_roles_db_instance as get_banker_db_instance
except ImportError:
    get_banker_db_instance = None


def register_trickster_commands(bot, personality, agent_config):
    """Register trickster commands (idempotent).
    
    NOTE: All !trickster, !dice, !runes commands have been removed.
    Use !canvas → Trickster instead.
    The subrole modules are still available for Canvas UI integration.
    """
    logger.info("🎭 Trickster commands registration skipped - all commands moved to Canvas UI")
