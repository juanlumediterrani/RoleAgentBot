"""Public API for Banker role.

This module provides a stable public API for Canvas and other external callers.
Internal implementations (banker_db, beggar_db, etc.) may change, but this API
should remain stable to avoid breaking canvas_*.py modules.
"""

from roles.banker.banker_messages import get_messages
from roles.banker.subroles.beggar.beggar_messages import get_canvas_message
from roles.banker.banker_db import get_banker_roles_db_instance
from roles.banker.banker_discord import _initialize_dice_game_account
from roles.banker.subroles.beggar.beggar_discord import BeggarDonationView
from roles.banker.subroles.beggar.beggar_db import get_beggar_config
from roles.banker.subroles.beggar.beggar_task import BeggarMinigame

__all__ = [
    "get_messages",
    "get_canvas_message",
    "get_banker_roles_db_instance",
    "_initialize_dice_game_account",
    "BeggarDonationView",
    "get_beggar_config",
    "BeggarMinigame",
]
