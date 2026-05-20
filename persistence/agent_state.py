"""Facade for agent state using NoSQL backend.

Provides the same API as AgentDatabase but internally uses agent_memory_nosql.py
for JSON/JSONL storage instead of SQLite. This allows gradual migration.
"""

import hashlib
import threading
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

from agent_memory_nosql import AgentMemoryNoSQL
from agent_logging import get_logger

logger = get_logger("agent_state")

# Default database directory
DEFAULT_DB_DIR = Path(__file__).parent.parent / "databases"

# DM sessions file path
DM_SESSIONS_FILE = DEFAULT_DB_DIR / "dm_sessions.json"


def stagger_offset_seconds(server_id: str, window_seconds: int) -> int:
    """Deterministic per-server offset within a window (seconds).

    Distributes load of periodic tasks across the window to avoid thundering
    herd when many servers share the same schedule. The offset is stable for
    a given server_id, so restarts don't cause bursts.
    """
    h = hashlib.md5(str(server_id).encode("utf-8")).hexdigest()
    return int(h, 16) % max(1, int(window_seconds))


class AgentState:
    """Facade for agent state using NoSQL backend.

    Provides the same API as AgentDatabase but internally uses AgentMemoryNoSQL.
    This allows gradual migration from SQLite to NoSQL.
    """

    def __init__(self, server_id: str, db_dir: Optional[Path] = None):
        self.server_id = str(server_id)
        self._memory = AgentMemoryNoSQL(server_id, db_dir=db_dir)
        self._lock = threading.Lock()
        self.db_path = self._memory.db_dir / "state.json"
        logger.info(f"🗄️ [AgentState] Initialized for server {server_id} (NoSQL backend)")

    # --- Per-server scheduled tasks (stagger) ---

    def is_scheduled_task_due(self, task_name: str, interval_hours: float,
                              stagger_window_hours: float = 1.0) -> bool:
        """Return True if the periodic task is due for this server.

        On first call (no persisted timestamp), schedules a first run at
        now + hash-offset within the stagger window (not immediately) so that
        a fresh deployment doesn't burst all servers at once.
        """
        next_iso = self._memory.get_next_scheduled_at(task_name)
        now = datetime.now()
        if not next_iso:
            offset = stagger_offset_seconds(self.server_id, int(stagger_window_hours * 3600))
            first_run = now + timedelta(seconds=offset)
            self._memory.set_next_scheduled_at(task_name, first_run.isoformat())
            return False
        try:
            next_dt = datetime.fromisoformat(next_iso)
        except Exception:
            # Corrupt timestamp — reset deterministically
            offset = stagger_offset_seconds(self.server_id, int(stagger_window_hours * 3600))
            self._memory.set_next_scheduled_at(
                task_name, (now + timedelta(seconds=offset)).isoformat()
            )
            return False
        return now >= next_dt

    def mark_scheduled_task_done(self, task_name: str, interval_hours: float,
                                  stagger_window_hours: float = 1.0) -> None:
        """Persist next_run_at = now + interval + per-server hash offset."""
        offset = stagger_offset_seconds(self.server_id, int(stagger_window_hours * 3600))
        next_run = datetime.now() + timedelta(hours=interval_hours, seconds=offset)
        self._memory.set_next_scheduled_at(task_name, next_run.isoformat())

    # --- Interactions ---

    def register_interaction(self, user_id, user_name="", interaction_type="", context="",
                              channel_id=None, server_id=None, metadata=None, **kwargs):
        """Register an interaction (NoSQL-backed)."""
        self._memory.register_interaction(
            user_id=user_id,
            user_name=user_name,
            interaction_type=interaction_type,
            context=context,
            channel_id=channel_id,
            server_id=server_id or self.server_id,
            metadata=metadata,
        )

    def registrar_interaccion(self, usuario_id, usuario_nombre="", tipo_interaccion="", contexto="",
                               canal_id=None, metadata=None, servidor_id=None):
        """Register an interaction (legacy Spanish API)."""
        self.register_interaction(
            user_id=usuario_id,
            user_name=usuario_nombre,
            interaction_type=tipo_interaccion,
            context=contexto,
            channel_id=canal_id,
            server_id=servidor_id,
            metadata=metadata,
        )

    def get_daily_interactions_since(self, since_iso=None, limit=25, target_date=None):
        """Return day-scoped general interactions after a given timestamp."""
        return self._memory.get_daily_interactions_since(since_iso, limit, target_date)

    def get_user_interactions_since(self, user_id, since_iso=None, limit=25):
        """Return user interactions after a given timestamp."""
        return self._memory.get_user_interactions_since(user_id, since_iso, limit)

    def get_recent_channel_interactions(self, channel_id, within_minutes=60, max_interactions=10):
        """Return recent messages from a specific channel for prompt injection."""
        return self._memory.get_recent_channel_interactions(channel_id, within_minutes, max_interactions)

    def get_last_dialogue_window(self, user_id, max_messages=10):
        """Return last N human/bot dialogue pairs regardless of time window."""
        return self._memory.get_last_dialogue_window(user_id, max_messages)

    def get_user_history(self, user_id, limit=5):
        """Get last N interactions for a user."""
        return self._memory.get_user_history(user_id, limit)

    def execute_query(self, query, params=None):
        """Compatibility shim for raw SQL queries. Returns matching rows from interactions."""
        # Only used for username lookup by user_id in agent_mind.py
        if "usuario_nombre" in query and "usuario_id" in query and params:
            user_id = params[0] if params else None
            if user_id:
                name = self._memory.get_user_name_by_id(user_id)
                if name:
                    return [(name,)]
        return []

    # --- Daily Memory ---

    def get_daily_memory(self, memory_date=None):
        """Return the daily memory summary string for a date."""
        return self._memory.get_daily_memory(memory_date)

    def upsert_daily_memory(self, summary, memory_date=None, metadata=None):
        """Insert a new daily memory summary."""
        return self._memory.add_daily_memory(summary, memory_date=memory_date, metadata=metadata)

    def get_daily_memory_record(self, memory_date=None):
        """Return the most recent daily memory record for a specific date."""
        return self._memory.get_most_recent_daily_memory_record()

    def get_most_recent_daily_memory_record(self):
        """Return the most recent daily memory entry with non-empty summary."""
        return self._memory.get_most_recent_daily_memory_record()

    def get_last_7_days_daily_memory(self):
        """Return the last 7 days of daily memory summaries."""
        return self._memory.get_last_7_days_daily_memory()

    # --- Recent Memory ---

    def get_recent_memory_record(self, memory_date=None):
        """Return the stored recent memory row for a date."""
        return self._memory.get_recent_memory_record(memory_date)

    def get_most_recent_memory_record(self):
        """Return the most recent stored recent memory, regardless of date."""
        return self._memory.get_most_recent_memory_record()

    def upsert_recent_memory(self, summary, memory_date=None, last_interaction_at=None, metadata=None):
        """Create or update the recent memory summary."""
        return self._memory.set_recent_memory(summary, memory_date=memory_date, metadata=metadata, last_interaction_at=last_interaction_at)

    def schedule_recent_memory_refresh(self, delay_minutes=60):
        """Schedule a recent memory refresh."""
        return self._memory.schedule_recent_memory_update(delay_minutes)

    def get_due_pending_recent_memory_refreshes(self, now_iso=None):
        """Return all pending recent memory refreshes that are due."""
        return self._memory.get_due_pending_recent_memory_refreshes(now_iso)

    def mark_recent_memory_refresh_completed(self):
        """Mark all pending recent memory refreshes as completed."""
        return self._memory.mark_recent_memory_refresh_completed()

    # --- User Relationships ---

    def get_user_relationship_memory(self, user_id):
        """Return the stored relationship summary for a user."""
        rel = self._memory.get_relationship(user_id)
        if not rel:
            return {"summary": "", "updated_at": None, "last_interaction_at": None, "metadata": {}}
        return {
            "summary": rel.get("summary", ""),
            "updated_at": rel.get("updated_at"),
            "last_interaction_at": rel.get("last_interaction_at"),
            "metadata": rel.get("metadata") or {},
        }

    def upsert_user_relationship_memory(self, user_id, summary, last_interaction_at=None, metadata=None):
        """Create or update temporary relationship memory state for a user."""
        return self._memory.set_relationship(user_id, summary, metadata=metadata, last_interaction_at=last_interaction_at)

    def get_user_relationship_daily_memory(self, user_id, memory_date=None):
        """Return the stored daily relationship summary for a user on a date."""
        return self._memory.get_relationship_daily_for_date(user_id, memory_date)

    def upsert_user_relationship_daily_memory(self, user_id, summary, memory_date=None, metadata=None):
        """Create or update daily relationship memory snapshot for a user."""
        return self._memory.set_relationship_daily(user_id, summary, metadata=metadata)

    def get_latest_user_relationship_daily_memory(self, user_id, before_date=None):
        """Return the most recent daily relationship snapshot for a user."""
        return self._memory.get_latest_user_relationship_daily_memory(user_id, before_date)

    def clear_stale_relationship_memory_states(self, keep_date=None):
        """Delete temporary relationship states that belong to older days."""
        return self._memory.clear_stale_relationship_memory_states(keep_date)

    def schedule_relationship_refresh(self, user_id, delay_minutes=60):
        """Mark a user relationship summary for refresh after inactivity."""
        return self._memory.schedule_relationship_update(user_id, delay_minutes)

    def get_due_pending_relationship_refreshes(self, now_iso=None):
        """Return all pending relationship refreshes that are due."""
        return self._memory.get_due_pending_relationship_refreshes(now_iso)

    def mark_relationship_refresh_completed(self, user_id):
        """Mark a pending relationship refresh as completed."""
        return self._memory.mark_relationship_refresh_completed(user_id)

    # --- GDPR and Retention ---

    def forget_user(self, user_id, user_name: str = None, extra_names=None) -> dict:
        """GDPR — right to erasure (Art. 17).

        Two-phase wipe:
        1. Drop every row directly keyed by this user_id (interactions, relationships, etc.)
        2. When user_name (and optional aliases) is provided, redact mentions in memory tables.

        Returns a per-section report of rows deleted / rewritten.
        """
        return self._memory.forget_user(user_id, user_name, extra_names)

    def apply_retention(self, interactions_days: int = 90) -> dict:
        """Purge data older than the retention thresholds.

        Args:
            interactions_days: Hard limit for raw interactions rows (default 90 days).

        Returns a per-section count of what was deleted.
        """
        return self._memory.apply_retention(interactions_days)

    # --- Notable Recollections ---

    def add_notable_recollection(self, recollection_text, memory_date=None, source_paragraph=None):
        """Add a new notable recollection. Returns recollection ID (index)."""
        return self._memory.add_recollection(recollection_text, memory_date=memory_date, source_paragraph=source_paragraph)

    def count_notable_recollections(self):
        """Count total notable recollections for this server."""
        return self._memory.count_notable_recollections()

    def get_random_notable_recollection(self):
        """Get a random notable recollection for injection into synthesis."""
        return self._memory.get_random_notable_recollection()

    def increment_recollection_usage(self, recollection_id):
        """Increment the usage counter for a recollection."""
        return self._memory.increment_recollection_usage(recollection_id)

    def get_notable_recollections_for_date(self, memory_date=None):
        """Get all notable recollections extracted on a specific date."""
        return self._memory.get_notable_recollections_for_date(memory_date)

    # --- Cleanup ---

    def clean_old_interactions(self, days: int = 90) -> int:
        """Clean interactions older than N days."""
        logger.debug(f"[AgentState] Interactions cleanup (retention: {days}d) - auto-handled by JsonlRingBuffer")
        return 0

    # --- Compatibility ---

    def get_db_path(self) -> Path:
        """Get database path (for compatibility)."""
        return self._memory.db_dir

    def is_active(self) -> bool:
        """Check if database is active."""
        return True


# Global instance cache (similar to AgentDatabase)
_agent_state_instances: Dict[str, AgentState] = {}
_agent_state_lock = threading.Lock()


def get_agent_state(server_id: str, db_dir: Optional[Path] = None) -> AgentState:
    """Get or create AgentState instance for a server."""
    server_id = str(server_id)
    with _agent_state_lock:
        if server_id not in _agent_state_instances:
            _agent_state_instances[server_id] = AgentState(server_id, db_dir)
        return _agent_state_instances[server_id]


def invalidate_agent_state(server_id: str = None):
    """Invalidate cached AgentState instance."""
    with _agent_state_lock:
        if server_id:
            server_id = str(server_id)
            _agent_state_instances.pop(server_id, None)
        else:
            _agent_state_instances.clear()


# --- Cross-server utilities (replacing global functions from agent_db.py) ---

def get_all_server_ids(db_dir: Optional[Path] = None) -> List[str]:
    """Return list of all server IDs that have NoSQL databases (state.json exists).

    Replaces SQLite-based get_all_server_ids from agent_db.py.
    """
    db_dir = db_dir or DEFAULT_DB_DIR
    if not db_dir.exists():
        return []

    server_ids = []
    for server_dir in db_dir.iterdir():
        if not server_dir.is_dir():
            continue

        # Check if state.json exists (indicates NoSQL database)
        state_path = server_dir / "state.json"
        if state_path.exists():
            server_ids.append(server_dir.name)

    return server_ids


def get_active_servers(db_dir: Optional[Path] = None) -> List[str]:
    """Return list of server IDs with active NoSQL databases.

    Replaces AgentDatabase.get_active_servers() from agent_db.py.
    """
    return get_all_server_ids(db_dir)


def get_user_last_server_id(user_id: str, db_dir: Optional[Path] = None) -> Optional[str]:
    """Find the most recent server where a user had an interaction.

    Scans all NoSQL databases (interactions.jsonl) to find the most recent
    interaction for the given user_id across all servers.

    Replaces SQLite-based get_user_last_server_id from agent_db.py.

    Args:
        user_id: User ID to search for
        db_dir: Database directory (defaults to DEFAULT_DB_DIR)

    Returns:
        Server ID string or None if no interactions found
    """
    db_dir = db_dir or DEFAULT_DB_DIR
    if not db_dir.exists():
        return None

    uid = str(user_id)
    most_recent_server = None
    most_recent_time = None

    # Look through all server directories
    for server_dir in db_dir.iterdir():
        if not server_dir.is_dir():
            continue

        server_id = server_dir.name
        # Check if interactions.jsonl exists
        interactions_path = server_dir / "interactions.jsonl"
        if not interactions_path.exists():
            continue

        try:
            # Read interactions to find most recent for this user
            from persistence.jsonl_store import JsonlRingBuffer
            interactions = JsonlRingBuffer(interactions_path)

            for record in interactions.iter_records():
                if record.get("usuario_id") == uid:
                    interaction_time = record.get("fecha", "")
                    if interaction_time and (most_recent_time is None or interaction_time > most_recent_time):
                        most_recent_time = interaction_time
                        # Use servidor_id from record if available, else server_id from directory
                        most_recent_server = record.get("servidor_id") or server_id

        except Exception as e:
            logger.debug(f"Could not check server {server_id} for user {uid}: {e}")
            continue

    return most_recent_server


def forget_user_across_servers(user_id, user_name: str = None, extra_names=None, db_dir: Optional[Path] = None) -> Dict[str, dict]:
    """GDPR deletion across all NoSQL databases.

    Calls forget_user on every server's AgentState.

    Replaces SQLite-based forget_user_across_servers from agent_db.py.

    Returns:
        Dict mapping server_id to deletion report
    """
    db_dir = db_dir or DEFAULT_DB_DIR
    server_ids = get_all_server_ids(db_dir)
    results = {}

    for server_id in server_ids:
        try:
            agent_state = get_agent_state(server_id, db_dir)
            report = agent_state.forget_user(user_id, user_name, extra_names)
            results[server_id] = report
        except Exception as e:
            logger.exception(f"Error forgetting user {user_id} on server {server_id}: {e}")
            results[server_id] = {"error": str(e)}

    total_ops = sum(sum(report.values()) for report in results.values() if isinstance(report, dict))
    logger.info(f"🧹 [GDPR] forget_user_across_servers({user_id}): {len(results)} servers processed, total_ops={total_ops}")
    return results


def apply_retention_across_servers(interactions_days: int = 90, db_dir: Optional[Path] = None) -> Dict[str, dict]:
    """Apply retention policy across all NoSQL databases.

    Calls apply_retention on every server's AgentState.

    Replaces SQLite-based apply_retention_across_servers from agent_db.py.

    Returns:
        Dict mapping server_id to deletion report
    """
    db_dir = db_dir or DEFAULT_DB_DIR
    server_ids = get_all_server_ids(db_dir)
    results = {}

    for server_id in server_ids:
        try:
            agent_state = get_agent_state(server_id, db_dir)
            report = agent_state.apply_retention(interactions_days)
            results[server_id] = report
        except Exception as e:
            logger.exception(f"Error applying retention on server {server_id}: {e}")
            results[server_id] = {"error": str(e)}

    total_ops = sum(sum(report.values()) for report in results.values() if isinstance(report, dict))
    logger.info(f"🗑️ [Retention] apply_retention_across_servers: {len(results)} servers processed, total_ops={total_ops}")
    return results


# --- DM Sessions (cross-server DM routing) ---

def _load_dm_sessions() -> Dict[str, str]:
    """Load DM sessions from JSON file."""
    if not DM_SESSIONS_FILE.exists():
        return {}
    try:
        with open(DM_SESSIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.exception(f"Error loading DM sessions: {e}")
        return {}


def _save_dm_sessions(sessions: Dict[str, str]) -> None:
    """Save DM sessions to JSON file."""
    try:
        DM_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DM_SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(sessions, f, indent=2)
    except Exception as e:
        logger.exception(f"Error saving DM sessions: {e}")


def pin_dm_session(user_id: int, server_id: str) -> None:
    """Pin a user's DM to a specific server for consistent routing.

    Replaces SQLite-based pin_dm_session from agent_db.py.
    """
    sessions = _load_dm_sessions()
    sessions[str(user_id)] = str(server_id)
    _save_dm_sessions(sessions)
    logger.debug(f"DM session pinned: user={user_id} → server={server_id}")


def get_pinned_dm_server(user_id: int) -> Optional[str]:
    """Return the pinned server_id for a user's DM, or None if not set.

    Replaces SQLite-based get_pinned_dm_server from agent_db.py.
    """
    return _load_dm_sessions().get(str(user_id))
