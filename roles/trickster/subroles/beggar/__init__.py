"""
Beggar subrole package.
Restructured system with centralized configuration in roles.db/roles_config.
"""

__version__ = "2.0.0"

# Import main components for easy access
from .beggar_config import get_beggar_config, BeggarConfig
from .beggar_task import BeggarTask, execute_beggar_task
from .beggar_minigame import BeggarMinigame

__all__ = [
    'get_beggar_config',
    'BeggarConfig',
    'BeggarTask', 
    'execute_beggar_task',
    'BeggarMinigame'
]
