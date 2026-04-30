"""
Astrology Database Module (NoSQL)
Handles storage and retrieval using RoleConfigsNoSQL.
"""

from typing import Dict, Any, List, Optional
from agent_logging import get_logger

logger = get_logger('astrology_db')


class AstrologyDB:
    """Database handler for astrology using NoSQL."""

    def __init__(self, server_id: str = None):
        """Initialize NoSQL-backed astrology database."""
        if server_id is None:
            from agent_db import get_server_id
            server_id = get_server_id()
        self.server_id = server_id
        
        from roles.role_configs_nosql import get_role_configs_nosql
        self._nosql = get_role_configs_nosql(server_id)

    def save_birth_data(self, user_id: str, birth_date: str,
                       birth_time: Optional[str] = None) -> bool:
        """Save user's birth data."""
        return self._nosql.save_astrology_birth_data(user_id, birth_date, birth_time)

    def get_birth_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's birth data."""
        return self._nosql.get_astrology_birth_data(user_id)

    def save_reading(self, user_id: str, reading_type: str,
                    calculation_data: Dict[str, Any],
                    interpretation: str, question: str = "") -> bool:
        """Save an astrology reading."""
        return self._nosql.save_astrology_reading(
            user_id, reading_type, calculation_data, interpretation, question
        )

    def get_user_readings(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent readings for a user."""
        return self._nosql.get_astrology_readings(user_id, limit)

    def get_reading_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics for a user."""
        return self._nosql.get_astrology_stats(user_id)


def get_astrology_db_instance(server_id: str = "default") -> AstrologyDB:
    """Get the astrology database instance."""
    return AstrologyDB(server_id)
