"""Facade for agent state using NoSQL backend.

Provides the same API as AgentDatabase but internally uses agent_memory_nosql.py
for JSON/JSONL storage instead of SQLite. This allows gradual migration.
"""

from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime

from agent_memory_nosql import AgentMemoryNoSQL
from agent_logging import get_logger

logger = get_logger("agent_state")


class AgentState:
    """Facade for agent state using NoSQL backend.

    Provides the same API as AgentDatabase but internally uses AgentMemoryNoSQL.
    This allows gradual migration from SQLite to NoSQL.
    """

    def __init__(self, server_id: str, db_dir: Optional[Path] = None):
        self.server_id = str(server_id)
        self._memory = AgentMemoryNoSQL(server_id, db_dir=db_dir)
        logger.info(f"🗄️ [AgentState] Initialized for server {server_id} (NoSQL backend)")

    # Interactions
    def add_interaction(self, user_id: str, message: str, response: str, channel_id: str, **kwargs):
        """Add an interaction to the log."""
        self._memory.register_interaction(
            user_id=user_id,
            user_message=message,
            bot_response=response,
            channel_id=channel_id,
            **kwargs
        )

    def get_interactions(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get recent interactions."""
        interactions = self._memory.get_recent_interactions(limit)
        return interactions[offset:offset + limit]

    # Daily Memory
    def get_daily_memory(self) -> Optional[str]:
        """Get current daily memory summary."""
        return self._memory.get_daily_memory()

    def upsert_daily_memory(self, summary: str):
        """Update or insert daily memory summary."""
        self._memory.save_daily_memory(summary)

    # Recent Memory
    def get_recent_memory(self) -> Optional[str]:
        """Get current recent memory summary."""
        return self._memory.get_recent_memory()

    def upsert_recent_memory(self, summary: str):
        """Update or insert recent memory summary."""
        self._memory.save_recent_memory(summary)

    # Relationships
    def get_user_relationship(self, user_id: str) -> Optional[str]:
        """Get relationship summary for a user."""
        return self._memory.get_relationship(user_id)

    def upsert_user_relationship(self, user_id: str, summary: str):
        """Update or insert user relationship summary."""
        self._memory.save_relationship(user_id, summary)

    def get_all_relationships(self) -> Dict[str, str]:
        """Get all user relationship summaries."""
        return self._memory.get_all_relationships()

    # Recollections
    def add_recollection(self, recollection: str, source: str = "user"):
        """Add a notable recollection."""
        self._memory.add_recollection(recollection, source=source)

    def get_recollections(self, limit: int = 50) -> List[Dict]:
        """Get notable recollections."""
        return self._memory.get_recollections(limit)

    def mark_recollection_used(self, recollection_id: str):
        """Mark a recollection as used."""
        self._memory.mark_recollection_used(recollection_id)

    # Pending Updates
    def has_pending_recent_memory_update(self) -> bool:
        """Check if there's a pending recent memory update."""
        return self._memory.has_pending_recent_memory_update()

    def get_pending_recent_memory_update(self) -> Optional[Dict]:
        """Get pending recent memory update."""
        return self._memory.get_pending_recent_memory_update()

    def clear_pending_recent_memory_update(self):
        """Clear pending recent memory update."""
        self._memory.clear_pending_recent_memory_update()

    def has_pending_relationship_update(self, user_id: str) -> bool:
        """Check if there's a pending relationship update for a user."""
        return self._memory.has_pending_relationship_update(user_id)

    def get_pending_relationship_update(self, user_id: str) -> Optional[Dict]:
        """Get pending relationship update for a user."""
        return self._memory.get_pending_relationship_update(user_id)

    def clear_pending_relationship_update(self, user_id: str):
        """Clear pending relationship update for a user."""
        self._memory.clear_pending_relationship_update(user_id)

    # Cleanup
    def clean_old_interactions(self, days: int = 90) -> int:
        """Clean interactions older than N days."""
        # JsonlRingBuffer handles rotation automatically
        # This is a no-op for the NoSQL backend
        logger.debug(f"[AgentState] Interactions cleanup (retention: {days}d) - auto-handled by JsonlRingBuffer")
        return 0

    # Compatibility methods for AgentDatabase API
    def get_db_path(self) -> Path:
        """Get database path (for compatibility)."""
        return self._memory.db_dir

    def is_active(self) -> bool:
        """Check if database is active."""
        return True


# Global instance cache (similar to AgentDatabase)
_agent_state_instances: Dict[str, AgentState] = {}


def get_agent_state(server_id: str, db_dir: Optional[Path] = None) -> AgentState:
    """Get or create AgentState instance for a server."""
    server_id = str(server_id)
    if server_id not in _agent_state_instances:
        _agent_state_instances[server_id] = AgentState(server_id, db_dir)
    return _agent_state_instances[server_id]


def invalidate_agent_state(server_id: str):
    """Invalidate cached AgentState instance."""
    server_id = str(server_id)
    _agent_state_instances.pop(server_id, None)
