"""NoSQL-based agent memory using JsonStore and JsonlRingBuffer.

Replaces SQLite tables for volatile agent data with JSON/JSONL storage:
- interactions.jsonl: Append-only ring buffer (max 250)
- state.json: Structured document with retention limits
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from persistence.json_store import JsonStore
from persistence.jsonl_store import JsonlRingBuffer
from agent_logging import get_logger

logger = get_logger("agent_memory_nosql")


class AgentMemoryNoSQL:
    """NoSQL-based agent memory with retention limits.

    File structure:
    - databases/{server_id}/state.json
      - daily_memory: list of {date, summary, metadata, updated_at} (max 14)
      - recent_memory: {summary, metadata, updated_at, last_interaction_at}
      - relationships: {user_id: {summary, metadata, updated_at, last_interaction_at}} (max 200)
      - relationship_daily: {user_id: {date: {summary, metadata, updated_at}}} (max 14 per user)
      - notable_recollections: list of {memory_date, recollection_text, source_paragraph, extracted_at, used_count, last_used_at} (max 50)
      - pending_relationship_updates: {user_id: {scheduled_for, status, updated_at}}
      - pending_recent_memory_updates: {scheduled_for: {status, updated_at}}

    - databases/{server_id}/interactions.jsonl
      - JSON lines: {usuario_id, usuario_nombre, canal_id, tipo_interaccion, contexto, metadata, fecha, servidor_id}
      - Rotated to keep max 250 entries
    """

    def __init__(self, server_id: str, db_dir: Optional[Path | str] = None):
        self.server_id = str(server_id)
        self.db_dir = Path(db_dir) if db_dir else Path(__file__).parent / "databases" / self.server_id
        self.db_dir.mkdir(parents=True, exist_ok=True)

        # Initialize stores
        self._state = JsonStore(
            self.db_dir / "state.json",
            default_factory=self._default_state,
            schema_version=1,
            keep_backup=True,
        )

        self._interactions = JsonlRingBuffer(
            self.db_dir / "interactions.jsonl",
            max_lines=250,
            max_bytes=500 * 1024,  # 500KB
            keep_lines=200,
        )

        logger.info(f"🗄️ [NoSQL Memory] Initialized for server {server_id} at {self.db_dir}")

    def _default_state(self) -> Dict[str, Any]:
        """Default empty state structure."""
        return {
            "daily_memory": [],
            "recent_memory": None,
            "relationships": {},
            "relationship_daily": {},
            "notable_recollections": [],
            "pending_relationship_updates": {},
            "pending_recent_memory_updates": {},
        }

    # --- Interactions (JSONL) ---

    def register_interaction(
        self,
        user_id: str,
        user_name: str,
        interaction_type: str,
        context: str,
        channel_id: Optional[str] = None,
        server_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Register an interaction (append to JSONL)."""
        try:
            record = {
                "usuario_id": str(user_id),
                "usuario_nombre": user_name,
                "canal_id": str(channel_id) if channel_id else None,
                "tipo_interaccion": interaction_type,
                "contexto": context,
                "metadata": json.dumps(metadata) if metadata else None,
                "fecha": datetime.now().isoformat(),
                "servidor_id": str(server_id) if server_id else None,
            }
            self._interactions.append(record)
            logger.debug(f"✅ [NoSQL] Interaction registered: user_id={user_id}, type={interaction_type}")
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error registering interaction: {e}")
            return False

    def get_user_history(self, user_id: str, limit: int = 5) -> List[Dict[str, str]]:
        """Get last N interactions for a user (reversed)."""
        try:
            # Filter by user_id and take last N
            records = list(
                self._interactions.filter_tail(
                    lambda r: r.get("usuario_id") == str(user_id),
                    limit=limit,
                )
            )
            # Reverse to chronological order
            records = list(reversed(records))
            return [
                {
                    "humano": r.get("contexto", ""),
                    "bot": self._extract_response(r.get("metadata")),
                }
                for r in records
            ]
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving user history: {e}")
            return []

    def get_recent_user_history(self, user_id: str, minutes: int = 3) -> List[Dict[str, str]]:
        """Get history from last N minutes for temporal context."""
        try:
            cutoff = datetime.now() - timedelta(minutes=minutes)
            records = []
            for r in self._interactions.iter_records():
                if r.get("usuario_id") != str(user_id):
                    continue
                try:
                    fecha = datetime.fromisoformat(r.get("fecha", ""))
                    if fecha >= cutoff:
                        records.append(r)
                except (ValueError, TypeError):
                    continue
                if len(records) >= 100:  # Safety limit
                    break
            # Reverse to chronological order
            records = list(reversed(records))
            return [
                {
                    "humano": r.get("contexto", ""),
                    "bot": self._extract_response(r.get("metadata")),
                }
                for r in records
            ]
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving recent user history: {e}")
            return []

    def get_last_dialogue_window(self, user_id: str, max_messages: int = 10) -> List[Dict[str, str]]:
        """Return last N human/bot dialogue pairs regardless of time window."""
        try:
            records = list(
                self._interactions.filter_tail(
                    lambda r: r.get("usuario_id") == str(user_id),
                    limit=max_messages * 2,  # Get enough for pairs
                )
            )
            # Reverse to chronological order
            records = list(reversed(records))
            return [
                {
                    "humano": r.get("contexto", ""),
                    "bot": self._extract_response(r.get("metadata")),
                    "fecha": r.get("fecha", ""),
                }
                for r in records
            ]
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving dialogue window: {e}")
            return []

    def _extract_response(self, metadata_str: Optional[str]) -> str:
        """Extract response from metadata JSON string."""
        if not metadata_str:
            return ""
        try:
            meta = json.loads(metadata_str)
            return (
                meta.get("response", "")
                or meta.get("greeting", "")
                or meta.get("respuesta", "")
                or meta.get("saludo", "")
            )
        except (json.JSONDecodeError, TypeError):
            return ""

    # --- Daily Memory ---

    def add_daily_memory(self, summary: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Add a daily memory entry (retention: max 14)."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                daily = state.get("daily_memory", [])
                daily.append({
                    "memory_date": datetime.now().date().isoformat(),
                    "summary": summary,
                    "metadata": json.dumps(metadata) if metadata else None,
                    "updated_at": datetime.now().isoformat(),
                })
                # Keep only last 14
                state["daily_memory"] = daily[-14:]
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error adding daily memory: {e}")
            return False

    def get_daily_memory(self, days: int = 14) -> List[Dict[str, Any]]:
        """Get daily memory entries from last N days."""
        try:
            state = self._state.load()
            daily = state.get("daily_memory", [])
            cutoff = (datetime.now() - timedelta(days=days)).date()
            return [
                {
                    **entry,
                    "metadata": json.loads(entry["metadata"]) if entry.get("metadata") else None,
                }
                for entry in daily
                if datetime.fromisoformat(entry["memory_date"]).date() >= cutoff
            ]
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving daily memory: {e}")
            return []

    # --- Recent Memory ---

    def set_recent_memory(self, summary: str, metadata: Optional[Dict[str, Any]] = None, last_interaction_at: Optional[str] = None) -> bool:
        """Set recent memory (single entry)."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                state["recent_memory"] = {
                    "memory_date": datetime.now().date().isoformat(),
                    "summary": summary,
                    "metadata": json.dumps(metadata) if metadata else None,
                    "updated_at": datetime.now().isoformat(),
                    "last_interaction_at": last_interaction_at or datetime.now().isoformat(),
                }
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error setting recent memory: {e}")
            return False

    def get_recent_memory(self) -> Optional[Dict[str, Any]]:
        """Get recent memory entry."""
        try:
            state = self._state.load()
            recent = state.get("recent_memory")
            if not recent:
                return None
            return {
                **recent,
                "metadata": json.loads(recent["metadata"]) if recent.get("metadata") else None,
            }
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving recent memory: {e}")
            return None

    # --- User Relationships ---

    def set_relationship(
        self,
        user_id: str,
        summary: str,
        metadata: Optional[Dict[str, Any]] = None,
        last_interaction_at: Optional[str] = None,
    ) -> bool:
        """Set relationship for a user (retention: max 200 users)."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                relationships = state.get("relationships", {})
                relationships[str(user_id)] = {
                    "summary": summary,
                    "metadata": json.dumps(metadata) if metadata else None,
                    "updated_at": datetime.now().isoformat(),
                    "last_interaction_at": last_interaction_at or datetime.now().isoformat(),
                }
                # Keep only last 200 users
                if len(relationships) > 200:
                    # Sort by updated_at and keep newest
                    sorted_users = sorted(
                        relationships.items(),
                        key=lambda x: x[1]["updated_at"],
                        reverse=True,
                    )
                    state["relationships"] = dict(sorted_users[:200])
                else:
                    state["relationships"] = relationships
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error setting relationship: {e}")
            return False

    def get_relationship(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get relationship for a user."""
        try:
            state = self._state.load()
            rel = state.get("relationships", {}).get(str(user_id))
            if not rel:
                return None
            return {
                **rel,
                "metadata": json.loads(rel["metadata"]) if rel.get("metadata") else None,
            }
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving relationship: {e}")
            return None

    def get_all_relationships(self) -> Dict[str, Dict[str, Any]]:
        """Get all relationships."""
        try:
            state = self._state.load()
            rels = state.get("relationships", {})
            return {
                uid: {
                    **data,
                    "metadata": json.loads(data["metadata"]) if data.get("metadata") else None,
                }
                for uid, data in rels.items()
            }
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving all relationships: {e}")
            return {}

    # --- User Daily Relationships ---

    def set_relationship_daily(
        self,
        user_id: str,
        summary: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Set daily relationship entry for a user (retention: max 14 per user)."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                rel_daily = state.get("relationship_daily", {})
                user_daily = rel_daily.get(str(user_id), {})
                user_daily[datetime.now().date().isoformat()] = {
                    "summary": summary,
                    "metadata": json.dumps(metadata) if metadata else None,
                    "updated_at": datetime.now().isoformat(),
                }
                # Keep only last 14 per user
                if len(user_daily) > 14:
                    sorted_dates = sorted(user_daily.keys(), reverse=True)
                    user_daily = {d: user_daily[d] for d in sorted_dates[:14]}
                rel_daily[str(user_id)] = user_daily
                state["relationship_daily"] = rel_daily
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error setting daily relationship: {e}")
            return False

    def get_relationship_daily(self, user_id: str, days: int = 14) -> List[Dict[str, Any]]:
        """Get daily relationship entries for a user from last N days."""
        try:
            state = self._state.load()
            user_daily = state.get("relationship_daily", {}).get(str(user_id), {})
            cutoff = (datetime.now() - timedelta(days=days)).date()
            return [
                {
                    "memory_date": date,
                    **entry,
                    "metadata": json.loads(entry["metadata"]) if entry.get("metadata") else None,
                }
                for date, entry in user_daily.items()
                if datetime.fromisoformat(date).date() >= cutoff
            ]
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving daily relationship: {e}")
            return []

    # --- Notable Recollections ---

    def add_recollection(
        self,
        recollection_text: str,
        source_paragraph: Optional[str] = None,
    ) -> bool:
        """Add a notable recollection (retention: max 50)."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                recollections = state.get("notable_recollections", [])
                recollections.append({
                    "memory_date": datetime.now().date().isoformat(),
                    "recollection_text": recollection_text,
                    "source_paragraph": source_paragraph,
                    "extracted_at": datetime.now().isoformat(),
                    "used_count": 0,
                    "last_used_at": None,
                })
                # Keep only last 50
                state["notable_recollections"] = recollections[-50:]
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error adding recollection: {e}")
            return False

    def get_recollections(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get notable recollections."""
        try:
            state = self._state.load()
            recs = state.get("notable_recollections", [])
            return recs[-limit:]
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving recollections: {e}")
            return []

    def mark_recollection_used(self, recollection_text: str) -> bool:
        """Mark a recollection as used."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                recollections = state.get("notable_recollections", [])
                for rec in recollections:
                    if rec.get("recollection_text") == recollection_text:
                        rec["used_count"] = rec.get("used_count", 0) + 1
                        rec["last_used_at"] = datetime.now().isoformat()
                state["notable_recollections"] = recollections
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error marking recollection used: {e}")
            return False

    # --- Pending Updates ---

    def schedule_relationship_update(self, user_id: str, delay_minutes: int = 5) -> bool:
        """Schedule a relationship memory update."""
        try:
            scheduled_for = (datetime.now() + timedelta(minutes=delay_minutes)).isoformat()
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                pending = state.get("pending_relationship_updates", {})
                pending[str(user_id)] = {
                    "scheduled_for": scheduled_for,
                    "status": "pending",
                    "updated_at": datetime.now().isoformat(),
                }
                state["pending_relationship_updates"] = pending
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error scheduling relationship update: {e}")
            return False

    def get_pending_relationship_updates(self) -> Dict[str, Dict[str, Any]]:
        """Get pending relationship updates."""
        try:
            state = self._state.load()
            return state.get("pending_relationship_updates", {})
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving pending relationship updates: {e}")
            return {}

    def clear_relationship_update(self, user_id: str) -> bool:
        """Clear a pending relationship update."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                pending = state.get("pending_relationship_updates", {})
                if str(user_id) in pending:
                    del pending[str(user_id)]
                state["pending_relationship_updates"] = pending
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error clearing relationship update: {e}")
            return False

    def schedule_recent_memory_update(self, delay_minutes: int = 60) -> bool:
        """Schedule a recent memory update."""
        try:
            scheduled_for = (datetime.now() + timedelta(minutes=delay_minutes)).isoformat()
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                pending = state.get("pending_recent_memory_updates", {})
                pending[scheduled_for] = {
                    "status": "pending",
                    "updated_at": datetime.now().isoformat(),
                }
                state["pending_recent_memory_updates"] = pending
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error scheduling recent memory update: {e}")
            return False

    def get_pending_recent_memory_updates(self) -> Dict[str, Dict[str, Any]]:
        """Get pending recent memory updates."""
        try:
            state = self._state.load()
            return state.get("pending_recent_memory_updates", {})
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving pending recent memory updates: {e}")
            return {}

    def clear_recent_memory_update(self, scheduled_for: str) -> bool:
        """Clear a pending recent memory update."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                pending = state.get("pending_recent_memory_updates", {})
                if scheduled_for in pending:
                    del pending[scheduled_for]
                state["pending_recent_memory_updates"] = pending
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error clearing recent memory update: {e}")
            return False
