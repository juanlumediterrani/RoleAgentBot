"""
Beggar subrole package for Banker role.
Handles asking for money/donations from users.

Consolidated structure (5 files):
- beggar_db.py: Configuration and database operations
- beggar_task.py: Task execution and minigame system
- beggar_discord.py: Discord UI components (buttons, modals, views)
- beggar_messages.py: Text messages and prompts
- beggar.py: Main entry point and utility functions
"""

__version__ = "2.0.0"

# Database and Configuration (fused into beggar_db.py)
from .beggar_db import (
    get_beggar_config,
    BeggarConfig,
    get_beggar_db,
    BeggarDatabase,
    invalidate_beggar_config_cache,
)

# Discord UI Components
from .beggar_discord import BeggarDonationView, BeggarModal

# Messages and Prompts
from .beggar_messages import (
    get_random_reason,
    get_canvas_message,
    MISSION_CONFIG,
    BEGGAR_REASONS_FALLBACK,
    CANVAS_MESSAGES,
)

# Task Execution and Minigame (fused into beggar_task.py)
from .beggar_task import (
    BeggarTask,
    execute_beggar_task,
    BeggarMinigame,
)

# Main entry point
from .beggar import (
    beggar_task,
    can_beg_in_server,
    update_last_beg_time,
    get_random_beg_message as get_simple_beg_message,
)

__all__ = [
    # Config & Database
    'get_beggar_config',
    'BeggarConfig',
    'get_beggar_db',
    'BeggarDatabase',
    'invalidate_beggar_config_cache',
    # Discord UI
    'BeggarDonationView',
    'BeggarModal',
    # Messages
    'get_random_reason',
    'get_canvas_message',
    'get_simple_beg_message',
    'MISSION_CONFIG',
    'BEGGAR_REASONS_FALLBACK',
    'CANVAS_MESSAGES',
    # Task & Minigame
    'BeggarTask',
    'execute_beggar_task',
    'BeggarMinigame',
    # Utilities
    'beggar_task',
    'can_beg_in_server',
    'update_last_beg_time',
]
