"""
Nordic Runes Database Module
Handles storage and retrieval of rune readings.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
import threading
from agent_logging import get_logger
from agent_roles_db import get_roles_db_instance

logger = get_logger('nordic_runes_db')


class NordicRunesDB:
    """Database handler for Nordic runes readings using centralized roles.db."""

    def __init__(self, server_id: str = None):
        """Initialize database connection using centralized roles.db."""
        if server_id is None:
            from agent_db import get_server_id
            server_id = get_server_id()
        self.server_id = server_id
        self.roles_db = get_roles_db_instance(server_id)
        self.db_path = self.roles_db.db_path
    
    def save_reading(self, user_id: str, question: str, runes_drawn: List[str], 
                    interpretation: str, reading_type: str) -> int:
        """Save a rune reading to the database."""
        return self.roles_db.save_nordic_runes_reading(
            user_id, question, runes_drawn, interpretation, reading_type
        )
    
    def get_user_readings(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent rune readings for a user."""
        return self.roles_db.get_nordic_runes_readings(user_id, limit)
    
    def get_reading_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics for a user's rune readings."""
        return self.roles_db.get_nordic_runes_stats(user_id)


# Global database instance
def get_nordic_runes_db_instance(server_id: str = "default") -> NordicRunesDB:
    """Get the Nordic runes database instance using centralized roles.db."""
    return NordicRunesDB(server_id)
