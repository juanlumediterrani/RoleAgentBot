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
            "scheduled_tasks": {},
        }

    # --- Per-server scheduled tasks (stagger) ---

    def get_next_scheduled_at(self, task_name: str) -> Optional[str]:
        """Return ISO timestamp of next scheduled execution for task_name, or None."""
        try:
            state = self._state.load()
            tasks = state.get("scheduled_tasks") or {}
            entry = tasks.get(task_name)
            if not entry:
                return None
            return entry.get("next_run_at")
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error reading scheduled task {task_name}: {e}")
            return None

    def set_next_scheduled_at(self, task_name: str, next_run_iso: str) -> bool:
        """Persist next_run_at for task_name."""
        try:
            def updater(state):
                tasks = state.get("scheduled_tasks") or {}
                tasks[task_name] = {
                    "next_run_at": next_run_iso,
                    "updated_at": datetime.now().isoformat(),
                }
                state["scheduled_tasks"] = tasks
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error writing scheduled task {task_name}: {e}")
            return False

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

    # --- Interaction queries (matching AgentDatabase API) ---

    def get_daily_interactions_since(self, since_iso: Optional[str] = None, limit: int = 25, target_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return day-scoped general interactions after a given timestamp."""
        from datetime import date as _date
        day_value = target_date or _date.today().isoformat()
        try:
            all_records = list(self._interactions.iter_records())
            filtered = []
            for r in all_records:
                fecha = r.get("fecha", "")
                if not fecha:
                    continue
                # Day filter
                if fecha[:10] != day_value:
                    continue
                # Since filter
                if since_iso and fecha <= since_iso:
                    continue
                filtered.append(r)
            # If since_iso, order ASC; else DESC then reverse
            if since_iso:
                filtered.sort(key=lambda x: x.get("fecha", ""))
                filtered = filtered[:limit]
            else:
                filtered.sort(key=lambda x: x.get("fecha", ""), reverse=True)
                filtered = list(reversed(filtered[:limit]))
            result = []
            for r in filtered:
                meta_str = r.get("metadata")
                metadata = {}
                if meta_str:
                    try:
                        metadata = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
                    except (json.JSONDecodeError, TypeError):
                        pass
                result.append({
                    "usuario_id": r.get("usuario_id", ""),
                    "usuario_nombre": r.get("usuario_nombre", ""),
                    "tipo_interaccion": r.get("tipo_interaccion", ""),
                    "contexto": r.get("contexto", ""),
                    "respuesta": metadata.get("response", "") or metadata.get("respuesta", "") or metadata.get("greeting", "") or metadata.get("saludo", ""),
                    "fecha": r.get("fecha", ""),
                })
            return result
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving daily interactions since: {e}")
            return []

    def get_user_interactions_since(self, user_id: str, since_iso: Optional[str] = None, limit: int = 25) -> List[Dict[str, Any]]:
        """Return user interactions after a given timestamp."""
        try:
            all_records = list(self._interactions.iter_records())
            uid = str(user_id)
            filtered = [r for r in all_records if r.get("usuario_id") == uid]
            if since_iso:
                filtered = [r for r in filtered if r.get("fecha", "") > since_iso]
                filtered.sort(key=lambda x: x.get("fecha", ""))
                filtered = filtered[:limit]
            else:
                filtered.sort(key=lambda x: x.get("fecha", ""), reverse=True)
                filtered = list(reversed(filtered[:limit]))
            result = []
            for r in filtered:
                meta_str = r.get("metadata")
                metadata = {}
                if meta_str:
                    try:
                        metadata = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
                    except (json.JSONDecodeError, TypeError):
                        pass
                result.append({
                    "humano": r.get("contexto", ""),
                    "bot": metadata.get("response", "") or metadata.get("greeting", "") or metadata.get("respuesta", "") or metadata.get("saludo", "") or "",
                    "fecha": r.get("fecha", ""),
                    "tipo_interaccion": r.get("tipo_interaccion", ""),
                    "usuario_nombre": r.get("usuario_nombre", ""),
                })
            return result
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving user interactions since: {e}")
            return []

    def get_recent_channel_interactions(self, channel_id, within_minutes: int = 60, max_interactions: int = 10) -> List[Dict[str, Any]]:
        """Return recent messages from a specific channel for prompt injection."""
        try:
            cutoff = (datetime.now() - timedelta(minutes=within_minutes)).isoformat()
            all_records = list(self._interactions.iter_records())
            ch = str(channel_id)
            filtered = []
            for r in all_records:
                if r.get("canal_id") != ch:
                    continue
                if r.get("fecha", "") < cutoff:
                    continue
                filtered.append(r)
            filtered.sort(key=lambda x: x.get("fecha", ""), reverse=True)
            filtered = filtered[:max_interactions]
            messages = []
            for r in filtered:
                meta_str = r.get("metadata")
                meta = {}
                if meta_str:
                    try:
                        meta = json.loads(meta_str) if isinstance(meta_str, str) else meta_str
                    except (json.JSONDecodeError, TypeError):
                        pass
                messages.append({
                    "user_id": r.get("usuario_id", ""),
                    "user_name": r.get("usuario_nombre", ""),
                    "content": r.get("contexto", ""),
                    "response": meta.get("response", "") or "",
                    "timestamp": r.get("fecha", ""),
                    "type": r.get("tipo_interaccion", ""),
                })
            return messages
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving recent channel interactions: {e}")
            return []

    def get_user_name_by_id(self, user_id: str) -> Optional[str]:
        """Look up a username from interactions by user_id."""
        try:
            all_records = list(self._interactions.iter_records())
            uid = str(user_id)
            for r in reversed(all_records):
                if r.get("usuario_id") == uid and r.get("usuario_nombre"):
                    return r["usuario_nombre"]
            return None
        except Exception:
            return None

    # --- Daily Memory ---

    def add_daily_memory(self, summary: str, memory_date: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Add a daily memory entry (retention: max 14)."""
        try:
            target_date = memory_date or datetime.now().date().isoformat()
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                daily = state.get("daily_memory", [])
                daily.append({
                    "memory_date": target_date,
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

    def get_daily_memory_entries(self, days: int = 14) -> List[Dict[str, Any]]:
        """Get daily memory entries from last N days (list of dicts)."""
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
            logger.exception(f"⚠️ [NoSQL] Error retrieving daily memory entries: {e}")
            return []

    def get_daily_memory(self, memory_date: Optional[str] = None) -> str:
        """Get daily memory summary string for a date (latest entry). Matches AgentDatabase API."""
        try:
            target_date = memory_date or datetime.now().date().isoformat()
            state = self._state.load()
            daily = state.get("daily_memory", [])
            # Find latest entry for target_date
            candidates = [e for e in daily if e.get("memory_date") == target_date]
            if candidates:
                return candidates[-1].get("summary", "") or ""
            return ""
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving daily memory: {e}")
            return ""

    def get_most_recent_daily_memory_record(self) -> Optional[Dict[str, Any]]:
        """Return the most recent daily memory entry with non-empty summary."""
        try:
            state = self._state.load()
            daily = state.get("daily_memory", [])
            for entry in reversed(daily):
                summary = (entry.get("summary") or "").strip()
                if summary:
                    return {
                        "memory_date": entry.get("memory_date"),
                        "summary": summary,
                        "metadata": json.loads(entry["metadata"]) if entry.get("metadata") else {},
                        "updated_at": entry.get("updated_at"),
                    }
            return None
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving most recent daily memory record: {e}")
            return None

    def get_last_7_days_daily_memory(self) -> List[Dict[str, Any]]:
        """Return the last 7 days of daily memory summaries for weekly personality evolution."""
        try:
            state = self._state.load()
            daily = state.get("daily_memory", [])
            cutoff = (datetime.now() - timedelta(days=7)).date()
            # Deduplicate by date (keep latest per date)
            by_date: Dict[str, Dict[str, Any]] = {}
            for entry in daily:
                md = entry.get("memory_date", "")
                summary = (entry.get("summary") or "").strip()
                if not summary or summary == "[Error in internal task]":
                    continue
                try:
                    if datetime.fromisoformat(md).date() >= cutoff:
                        by_date[md] = entry
                except (ValueError, TypeError):
                    continue
            result = []
            for md in sorted(by_date.keys()):
                e = by_date[md]
                result.append({
                    "memory_date": md,
                    "summary": (e.get("summary") or "").strip(),
                    "metadata": json.loads(e["metadata"]) if e.get("metadata") else {},
                    "updated_at": e.get("updated_at"),
                })
            return result[-7:]
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving last 7 days daily memory: {e}")
            return []

    # --- Recent Memory ---

    def set_recent_memory(self, summary: str, memory_date: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None, last_interaction_at: Optional[str] = None) -> bool:
        """Set recent memory (single entry, keyed by memory_date)."""
        try:
            target_date = memory_date or datetime.now().date().isoformat()
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                state["recent_memory"] = {
                    "memory_date": target_date,
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
        """Get recent memory entry (raw dict with parsed metadata)."""
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

    def get_recent_memory_record(self, memory_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return recent memory record for a specific date. Matches AgentDatabase API."""
        try:
            target_date = memory_date or datetime.now().date().isoformat()
            state = self._state.load()
            recent = state.get("recent_memory")
            if not recent:
                return None
            if recent.get("memory_date") != target_date:
                return None
            return {
                "memory_date": recent.get("memory_date"),
                "summary": recent.get("summary", "") or "",
                "metadata": json.loads(recent["metadata"]) if recent.get("metadata") else {},
                "updated_at": recent.get("updated_at"),
                "last_interaction_at": recent.get("last_interaction_at"),
            }
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving recent memory record: {e}")
            return None

    def get_most_recent_memory_record(self) -> Optional[Dict[str, Any]]:
        """Return the most recent stored recent memory, regardless of date."""
        try:
            state = self._state.load()
            recent = state.get("recent_memory")
            if not recent:
                return None
            return {
                "memory_date": recent.get("memory_date"),
                "summary": recent.get("summary", "") or "",
                "metadata": json.loads(recent["metadata"]) if recent.get("metadata") else {},
                "updated_at": recent.get("updated_at"),
                "last_interaction_at": recent.get("last_interaction_at"),
            }
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving most recent memory record: {e}")
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

    def get_relationship_daily_for_date(self, user_id: str, memory_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the daily relationship summary for a user on a specific date. Matches AgentDatabase API."""
        try:
            from datetime import date as _date
            target_date = memory_date or _date.today().isoformat()
            state = self._state.load()
            user_daily = state.get("relationship_daily", {}).get(str(user_id), {})
            entry = user_daily.get(target_date)
            if not entry:
                return None
            return {
                "summary": entry.get("summary", "") or "",
                "metadata": json.loads(entry["metadata"]) if entry.get("metadata") else {},
                "updated_at": entry.get("updated_at"),
            }
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving daily relationship for date: {e}")
            return None

    def get_latest_user_relationship_daily_memory(self, user_id: str, before_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Return the most recent daily relationship snapshot for a user."""
        try:
            state = self._state.load()
            user_daily = state.get("relationship_daily", {}).get(str(user_id), {})
            if not user_daily:
                return None
            dates = sorted(user_daily.keys(), reverse=True)
            for d in dates:
                if before_date and d > before_date:
                    continue
                entry = user_daily[d]
                return {
                    "memory_date": d,
                    "summary": entry.get("summary", "") or "",
                    "metadata": json.loads(entry["metadata"]) if entry.get("metadata") else {},
                    "updated_at": entry.get("updated_at"),
                }
            return None
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving latest daily relationship memory: {e}")
            return None

    def clear_stale_relationship_memory_states(self, keep_date: Optional[str] = None) -> int:
        """Delete temporary relationship states that belong to older days."""
        try:
            from datetime import date as _date
            target_date = keep_date or _date.today().isoformat()
            state = self._state.load()
            relationships = state.get("relationships", {})
            to_delete = []
            for uid, data in relationships.items():
                lia = data.get("last_interaction_at")
                if lia and lia[:10] < target_date:
                    to_delete.append(uid)
            if not to_delete:
                return 0
            def updater(s: Dict[str, Any]) -> Dict[str, Any]:
                rels = s.get("relationships", {})
                for uid in to_delete:
                    rels.pop(uid, None)
                s["relationships"] = rels
                return s
            self._state.update(updater)
            return len(to_delete)
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error clearing stale relationship states: {e}")
            return 0

    # --- Notable Recollections ---

    def add_recollection(
        self,
        recollection_text: str,
        memory_date: Optional[str] = None,
        source_paragraph: Optional[str] = None,
    ) -> int:
        """Add a notable recollection (retention: max 50). Returns index as ID."""
        try:
            from datetime import date as _date
            target_date = memory_date or _date.today().isoformat()
            rec_id = 0
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                nonlocal rec_id
                recollections = state.get("notable_recollections", [])
                recollections.append({
                    "memory_date": target_date,
                    "recollection_text": recollection_text,
                    "source_paragraph": source_paragraph,
                    "extracted_at": datetime.now().isoformat(),
                    "used_count": 0,
                    "last_used_at": None,
                })
                rec_id = len(recollections)
                # Keep only last 50
                state["notable_recollections"] = recollections[-50:]
                return state
            self._state.update(updater)
            return rec_id
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error adding recollection: {e}")
            return 0

    def get_recollections(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get notable recollections."""
        try:
            state = self._state.load()
            recs = state.get("notable_recollections", [])
            return recs[-limit:]
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving recollections: {e}")
            return []

    def count_notable_recollections(self) -> int:
        """Count total notable recollections for this server."""
        try:
            state = self._state.load()
            return len(state.get("notable_recollections", []))
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error counting notable recollections: {e}")
            return 0

    def get_random_notable_recollection(self) -> Optional[Dict[str, Any]]:
        """Get a random notable recollection for injection into synthesis."""
        import random
        try:
            state = self._state.load()
            recs = state.get("notable_recollections", [])
            if not recs:
                return None
            rec = random.choice(recs)
            idx = recs.index(rec)
            return {
                "id": idx,
                "recollection_text": rec.get("recollection_text"),
                "memory_date": rec.get("memory_date"),
                "used_count": rec.get("used_count", 0),
            }
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving random notable recollection: {e}")
            return None

    def increment_recollection_usage(self, recollection_id: int) -> bool:
        """Increment the usage counter for a recollection by index."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                recs = state.get("notable_recollections", [])
                if 0 <= recollection_id < len(recs):
                    recs[recollection_id]["used_count"] = recs[recollection_id].get("used_count", 0) + 1
                    recs[recollection_id]["last_used_at"] = datetime.now().isoformat()
                state["notable_recollections"] = recs
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error incrementing recollection usage: {e}")
            return False

    def get_notable_recollections_for_date(self, memory_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all notable recollections extracted on a specific date."""
        try:
            from datetime import date as _date
            target_date = memory_date or _date.today().isoformat()
            state = self._state.load()
            recs = state.get("notable_recollections", [])
            return [
                {
                    "id": i,
                    "recollection_text": r.get("recollection_text"),
                    "source_paragraph": r.get("source_paragraph"),
                    "extracted_at": r.get("extracted_at"),
                }
                for i, r in enumerate(recs)
                if r.get("memory_date") == target_date
            ]
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving notable recollections for date: {e}")
            return []

    def mark_recollection_used(self, recollection_text: str) -> bool:
        """Mark a recollection as used (by text match)."""
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

    def schedule_relationship_update(self, user_id: str, delay_minutes: int = 5) -> Optional[str]:
        """Schedule a relationship memory update. Returns scheduled_for ISO string."""
        try:
            scheduled_for = (datetime.now() + timedelta(minutes=delay_minutes)).isoformat()
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                pending = state.get("pending_relationship_updates", {})
                existing = pending.get(str(user_id))
                # Don't overwrite if already pending (same logic as SQLite ON CONFLICT)
                if existing and existing.get("status") == "pending":
                    return state
                pending[str(user_id)] = {
                    "scheduled_for": scheduled_for,
                    "status": "pending",
                    "updated_at": datetime.now().isoformat(),
                }
                state["pending_relationship_updates"] = pending
                return state
            self._state.update(updater)
            return scheduled_for
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error scheduling relationship update: {e}")
            return None

    def get_pending_relationship_updates(self) -> Dict[str, Dict[str, Any]]:
        """Get pending relationship updates (raw dict)."""
        try:
            state = self._state.load()
            return state.get("pending_relationship_updates", {})
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving pending relationship updates: {e}")
            return {}

    def get_due_pending_relationship_refreshes(self, now_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all pending relationship refreshes that are due. Matches AgentDatabase API."""
        current_time = now_iso or datetime.now().isoformat()
        try:
            state = self._state.load()
            pending = state.get("pending_relationship_updates", {})
            result = []
            for uid, data in pending.items():
                if data.get("status") == "pending" and data.get("scheduled_for", "") <= current_time:
                    result.append({
                        "usuario_id": uid,
                        "scheduled_for": data["scheduled_for"],
                        "status": data["status"],
                        "updated_at": data.get("updated_at"),
                    })
            result.sort(key=lambda x: x.get("scheduled_for", ""))
            return result
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving due relationship refreshes: {e}")
            return []

    def mark_relationship_refresh_completed(self, user_id: str) -> bool:
        """Mark a pending relationship refresh as completed."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                pending = state.get("pending_relationship_updates", {})
                if str(user_id) in pending:
                    pending[str(user_id)]["status"] = "completed"
                    pending[str(user_id)]["updated_at"] = datetime.now().isoformat()
                state["pending_relationship_updates"] = pending
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error completing relationship refresh: {e}")
            return False

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

    def schedule_recent_memory_update(self, delay_minutes: int = 60) -> Optional[str]:
        """Schedule a recent memory update. Returns scheduled_for ISO string."""
        try:
            scheduled_for = (datetime.now() + timedelta(minutes=delay_minutes)).isoformat()
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                pending = state.get("pending_recent_memory_updates", {})
                # Don't overwrite existing pending
                for k, v in pending.items():
                    if v.get("status") == "pending":
                        return state
                pending[scheduled_for] = {
                    "status": "pending",
                    "updated_at": datetime.now().isoformat(),
                }
                state["pending_recent_memory_updates"] = pending
                return state
            self._state.update(updater)
            return scheduled_for
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error scheduling recent memory update: {e}")
            return None

    def get_pending_recent_memory_updates(self) -> Dict[str, Dict[str, Any]]:
        """Get pending recent memory updates (raw dict)."""
        try:
            state = self._state.load()
            return state.get("pending_recent_memory_updates", {})
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving pending recent memory updates: {e}")
            return {}

    def get_due_pending_recent_memory_refreshes(self, now_iso: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return all pending recent memory refreshes that are due. Matches AgentDatabase API."""
        current_time = now_iso or datetime.now().isoformat()
        try:
            state = self._state.load()
            pending = state.get("pending_recent_memory_updates", {})
            result = []
            for sched_for, data in pending.items():
                if data.get("status") == "pending" and sched_for <= current_time:
                    result.append({
                        "scheduled_for": sched_for,
                        "status": data["status"],
                        "updated_at": data.get("updated_at"),
                    })
            return result
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error retrieving due recent memory refreshes: {e}")
            return []

    def mark_recent_memory_refresh_completed(self) -> bool:
        """Mark all pending recent memory refreshes as completed."""
        try:
            def updater(state: Dict[str, Any]) -> Dict[str, Any]:
                pending = state.get("pending_recent_memory_updates", {})
                for k in pending:
                    pending[k]["status"] = "completed"
                    pending[k]["updated_at"] = datetime.now().isoformat()
                state["pending_recent_memory_updates"] = pending
                return state
            self._state.update(updater)
            return True
        except Exception as e:
            logger.exception(f"⚠️ [NoSQL] Error completing recent memory refresh: {e}")
            return False

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
