"""
POE2 subrole for the Treasure Hunter.

This module contains all POE2 subrole functionality:
- Database for configuration and objectives management
- Path of Exile 2 price analysis logic
- Discord bot for notifications
- Integration with poe2scout API
"""

from .poe2_subrole import (
    DatabaseRolePoe2,
    get_poe2_db_instance,
    Poe2SubroleBot,
    get_items_reference
)
from .poe2_subrole_manager import POE2SubroleManager, get_poe2_manager
from .poe2scout_client import Poe2ScoutClient, ResponseFormatError, APIError

__all__ = [
    'DatabaseRolePoe2',
    'get_poe2_db_instance', 
    'Poe2SubroleBot',
    'get_items_reference',
    'POE2SubroleManager',
    'get_poe2_manager',
    'Poe2ScoutClient',
    'ResponseFormatError',
    'APIError'
]

__version__ = "1.0.0"
__author__ = "RoleAgentBot"
