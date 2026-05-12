"""NoSQL fatigue counter store (global per-user).

Uses a hybrid approach:
- ``fatigue_servers.json`` - JsonStore for server buckets (small, loadable)
- ``fatigue_users.jsonl`` - JsonlKVStore for user buckets (scalable, O(1) per-user access)

Atomicity is provided by :class:`persistence.json_store.JsonStore` (tmp+fsync+
os.replace, plus a per-path RLock) — sufficient (quasi-ACID) for the
single-process bot model described in ARCHITECTURE.md §3.1.

Server document schema (version 2)::
    {
      "version": 2,
      "servers": {
        "<server_id>": {
          "user_id": "server_<id>",
          "user_name": "Server_<id>",
          "daily_requests": 0,
          "hourly_requests": 0,
          "burst_requests": 0,
          "total_requests": 0,
          "last_request_date": "YYYY-MM-DD",
          "last_hour_timestamp": "ISO",
          "last_burst_timestamp": "ISO",
          "updated_at": "ISO"
        }
      }
    }

User line schema (JSONL, one line per user)::
    {
      "user_id": "<user_id>",
      "user_name": "...",
      "daily_requests": 0,
      "hourly_requests": 0,
      "burst_requests": 0,
      "total_requests": 0,
      "last_request_date": "YYYY-MM-DD",
      "last_hour_timestamp": "ISO",
      "last_burst_timestamp": "ISO",
      "updated_at": "ISO"
    }

Global per-user fatigue:
- User buckets are shared across ALL servers — a user's quota is global.
- Server buckets track per-server usage (for admin stats / server-wide limits).
- System / server interactions (no ``user_id`` or ``user_id`` starting with
  ``server_``) only increment the server bucket.
"""

from __future__ import annotations

import datetime
import json
import os
import threading
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from persistence.json_store import JsonStore
from agent_logging import get_logger

logger = get_logger("fatigue_store")


_BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# JsonlKVStore - Key-Value store on top of JSONL (for users)
# ---------------------------------------------------------------------------

class JsonlKVStore:
    """Key-value store using JSONL format.

    Each line is a JSON object with a ``user_id`` key. Operations:
    - ``get(key)`` - scan file for key, return value (O(n) but cheap for typical usage)
    - ``set(key, value)`` - atomically replace line with key, or append if new
    - ``delete(key)`` - remove line with key
    - ``iter_all()`` - iterate all records lazily

    Atomicity: uses tmp+fsync+os.replace pattern (same as JsonStore).
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _lock_for(self, path: Path) -> threading.RLock:
        """Get or create a per-path lock."""
        return self._lock

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get record by key (user_id)."""
        with self._lock:
            if not self.path.exists():
                return None
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            if isinstance(obj, dict) and obj.get("user_id") == key:
                                return obj
                        except json.JSONDecodeError:
                            continue
            except OSError as exc:
                logger.warning(f"[JsonlKVStore] get failed for {key}: {exc}")
        return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        """Set record by key (user_id). Atomically replaces existing or appends."""
        with self._lock:
            # Ensure value has user_id
            value["user_id"] = key

            # Build new content
            lines = []
            found = False
            if self.path.exists():
                try:
                    with self.path.open("r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                obj = json.loads(line)
                                if isinstance(obj, dict) and obj.get("user_id") == key:
                                    lines.append(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
                                    found = True
                                else:
                                    lines.append(line)
                            except json.JSONDecodeError:
                                # Skip corrupted lines
                                continue
                except OSError as exc:
                    logger.warning(f"[JsonlKVStore] read failed before set: {exc}")

            if not found:
                lines.append(json.dumps(value, ensure_ascii=False, separators=(",", ":")))

            # Atomic write
            fd, tmp_name = tempfile.mkstemp(
                prefix=self.path.name + ".",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as out:
                    out.write("\n".join(lines))
                    out.write("\n")
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp_path, self.path)
            except Exception:
                # Close fd first if still open
                try:
                    os.close(fd)
                except OSError:
                    pass
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                raise

    def delete(self, key: str) -> bool:
        """Delete record by key. Returns True if found and deleted."""
        with self._lock:
            if not self.path.exists():
                return False

            lines = []
            found = False
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            if isinstance(obj, dict) and obj.get("user_id") == key:
                                found = True
                            else:
                                lines.append(line)
                        except json.JSONDecodeError:
                            # Skip corrupted lines but keep others
                            lines.append(line)
            except OSError as exc:
                logger.warning(f"[JsonlKVStore] read failed before delete: {exc}")
                return False

            if not found:
                return False

            # Atomic write
            fd, tmp_name = tempfile.mkstemp(
                prefix=self.path.name + ".",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as out:
                    out.write("\n".join(lines))
                    out.write("\n")
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp_path, self.path)
            except Exception:
                # Close fd first if still open
                try:
                    os.close(fd)
                except OSError:
                    pass
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                raise
            return True

    def iter_all(self) -> Iterator[Dict[str, Any]]:
        """Iterate all records lazily."""
        with self._lock:
            if not self.path.exists():
                return
            try:
                with self.path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                            if isinstance(obj, dict):
                                yield obj
                        except json.JSONDecodeError:
                            continue
            except OSError as exc:
                logger.warning(f"[JsonlKVStore] iter_all failed: {exc}")

    def count(self) -> int:
        """Count total records."""
        with self._lock:
            if not self.path.exists():
                return 0
            try:
                n = 0
                with self.path.open("r", encoding="utf-8") as f:
                    for _ in f:
                        n += 1
                return n
            except OSError:
                return 0


def _empty_bucket(bucket_id: str, user_name: Optional[str] = None) -> Dict[str, Any]:
    return {
        "user_id": bucket_id,
        "user_name": user_name or bucket_id,
        "daily_requests": 0,
        "hourly_requests": 0,
        "burst_requests": 0,
        "total_requests": 0,
        "last_request_date": None,
        "last_hour_timestamp": None,
        "last_burst_timestamp": None,
        "updated_at": None,
    }


def _rotate_bucket(bucket: Dict[str, Any], now: datetime.datetime) -> None:
    """Reset daily/hourly/burst counters in-place if their windows rolled over.

    Mutates ``bucket`` so that subsequent increments land in the correct slot.
    Idempotent for a given ``now``.
    """
    today = now.date().isoformat()
    current_hour = now.replace(minute=0, second=0, microsecond=0).isoformat()
    five_min_ago_iso = (now - datetime.timedelta(minutes=5)).isoformat()

    if bucket.get("last_request_date") != today:
        bucket["daily_requests"] = 0
    if bucket.get("last_hour_timestamp") != current_hour:
        bucket["hourly_requests"] = 0
    last_burst_ts = bucket.get("last_burst_timestamp")
    if not last_burst_ts or last_burst_ts <= five_min_ago_iso:
        bucket["burst_requests"] = 0


def _apply_increment(bucket: Dict[str, Any], now: datetime.datetime,
                     user_name: Optional[str] = None) -> None:
    """Apply a single increment to a bucket (after :func:`_rotate_bucket`)."""
    today = now.date().isoformat()
    current_hour = now.replace(minute=0, second=0, microsecond=0).isoformat()
    now_iso = now.isoformat()

    bucket["daily_requests"] = int(bucket.get("daily_requests", 0)) + 1
    bucket["hourly_requests"] = int(bucket.get("hourly_requests", 0)) + 1
    bucket["burst_requests"] = int(bucket.get("burst_requests", 0)) + 1
    bucket["total_requests"] = int(bucket.get("total_requests", 0)) + 1
    bucket["last_request_date"] = today
    bucket["last_hour_timestamp"] = current_hour
    bucket["last_burst_timestamp"] = now_iso
    bucket["updated_at"] = now_iso
    if user_name:
        bucket["user_name"] = user_name


class FatigueStore:
    """Atomic JSON-backed global fatigue counter (per-user across all servers).

    One global document at ``databases/fatigue_global.json`` with:
    - ``users``: global per-user buckets (shared across all servers)
    - ``servers``: per-server buckets (for stats and server-wide limits)
    """

    _DEFAULT_VERSION = 2

    def __init__(self, db_dir: Optional[Path | str] = None):
        base = Path(db_dir) if db_dir else _BASE_DIR / "databases"
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / "fatigue_global.json"
        self._store = JsonStore(
            self.path,
            default_factory=self._default_doc,
            schema_version=self._DEFAULT_VERSION,
            keep_backup=False,
        )

    # ---- defaults --------------------------------------------------------

    def _default_doc(self) -> Dict[str, Any]:
        return {
            "version": self._DEFAULT_VERSION,
            "users": {},
            "servers": {},
        }

    # ---- core API --------------------------------------------------------

    def incr(self, user_id: Optional[str] = None, user_name: Optional[str] = None,
             server_id: Optional[str] = None) -> Tuple[int, int]:
        """Atomically increment the appropriate buckets.

        - If ``user_id`` is None or starts with ``server_``: only the server
          bucket is incremented (system/server interaction).
        - Otherwise: both the global user bucket AND the server bucket increment
          in the same on-disk transaction.

        Returns ``(user_daily, user_total)`` for the user bucket (or
        ``(server_daily, server_total)`` for server-only calls).
        """
        now = datetime.datetime.now()
        is_server_call = (user_id is None) or str(user_id).startswith("server_")
        sid = str(server_id) if server_id else "unknown"

        def mutator(doc: Dict[str, Any]) -> None:
            # Always increment server bucket (for stats)
            servers = doc.setdefault("servers", {})
            server_bucket = servers.get(sid)
            if server_bucket is None:
                server_bucket = _empty_bucket(sid, f"Server_{sid}")
                servers[sid] = server_bucket
            _rotate_bucket(server_bucket, now)
            _apply_increment(server_bucket, now)

            # If user call, also increment global user bucket
            if not is_server_call:
                users = doc.setdefault("users", {})
                uid = str(user_id)
                user_bucket = users.get(uid)
                if user_bucket is None:
                    user_bucket = _empty_bucket(uid, user_name)
                    users[uid] = user_bucket
                _rotate_bucket(user_bucket, now)
                _apply_increment(user_bucket, now, user_name=user_name)

        try:
            self._store.update(mutator)
            doc = self._store.load()
            if is_server_call:
                srv = (doc.get("servers") or {}).get(sid) or {}
                return int(srv.get("daily_requests", 0)), int(srv.get("total_requests", 0))
            else:
                usr = (doc.get("users") or {}).get(str(user_id)) or {}
                return int(usr.get("daily_requests", 0)), int(usr.get("total_requests", 0))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FatigueStore] incr failed: {exc}")
            return 0, 0

    def stats(self, user_id: Optional[str] = None, server_id: Optional[str] = None) -> Dict[str, Any]:
        """Return a snapshot of stats for ``user_id`` (global) or ``server_id``.

        - If ``user_id`` provided: returns the global user bucket.
        - If only ``server_id`` provided: returns the server bucket.
        - If both None: returns empty dict.
        """
        now = datetime.datetime.now()
        try:
            doc = self._store.snapshot()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FatigueStore] stats failed: {exc}")
            return {}

        bucket: Optional[Dict[str, Any]]
        if user_id is not None:
            bucket = (doc.get("users") or {}).get(str(user_id))
        elif server_id is not None:
            bucket = (doc.get("servers") or {}).get(str(server_id))
        else:
            return {}
        if not bucket:
            return {}
        # Lazy rotation for read consistency
        rotated = dict(bucket)
        _rotate_bucket(rotated, now)
        return rotated

    def all_users(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return every user bucket sorted by total requests (optional limit)."""
        try:
            doc = self._store.snapshot()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FatigueStore] all_users failed: {exc}")
            return []
        out: List[Dict[str, Any]] = list((doc.get("users") or {}).values())
        out.sort(key=lambda b: int(b.get("total_requests", 0)), reverse=True)
        if limit:
            out = out[:limit]
        return out

    def all_servers(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return every server bucket sorted by total requests (optional limit)."""
        try:
            doc = self._store.snapshot()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FatigueStore] all_servers failed: {exc}")
            return []
        out: List[Dict[str, Any]] = list((doc.get("servers") or {}).values())
        out.sort(key=lambda b: int(b.get("total_requests", 0)), reverse=True)
        if limit:
            out = out[:limit]
        return out

    # ---- mutation helpers ------------------------------------------------

    def reset_user(self, user_id: str) -> bool:
        """Zero out the counters for a global user bucket.

        Returns True if the bucket existed and was reset.
        """
        uid = str(user_id)

        def mutator(doc: Dict[str, Any]) -> None:
            users = doc.setdefault("users", {})
            if uid in users:
                users[uid] = _empty_bucket(uid, users[uid].get("user_name"))

        try:
            self._store.update(mutator)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FatigueStore] reset_user failed for {uid}: {exc}")
            return False

    def reset_server(self, server_id: str) -> bool:
        """Zero out the counters for a server bucket.

        Returns True if the bucket existed and was reset.
        """
        sid = str(server_id)

        def mutator(doc: Dict[str, Any]) -> None:
            servers = doc.setdefault("servers", {})
            if sid in servers:
                servers[sid] = _empty_bucket(sid, servers[sid].get("user_name"))

        try:
            self._store.update(mutator)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FatigueStore] reset_server failed for {sid}: {exc}")
            return False

    def reset_daily(self) -> int:
        """Reset the daily counter on every bucket (users + servers). Returns affected count."""
        affected = 0

        def mutator(doc: Dict[str, Any]) -> None:
            nonlocal affected
            for user_bucket in (doc.get("users") or {}).values():
                if int(user_bucket.get("daily_requests", 0)) > 0:
                    user_bucket["daily_requests"] = 0
                    affected += 1
            for server_bucket in (doc.get("servers") or {}).values():
                if int(server_bucket.get("daily_requests", 0)) > 0:
                    server_bucket["daily_requests"] = 0
                    affected += 1

        try:
            self._store.update(mutator)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FatigueStore] reset_daily failed: {exc}")
        return affected

    def cleanup_inactive(self, days_to_keep: int = 30,
                         min_total_to_keep: int = 10) -> int:
        """Remove user buckets inactive for ``days_to_keep`` with low totals."""
        cutoff = (datetime.date.today() - datetime.timedelta(days=days_to_keep)).isoformat()
        removed = 0

        def mutator(doc: Dict[str, Any]) -> None:
            nonlocal removed
            users = doc.get("users") or {}
            doomed: List[str] = []
            for uid, bucket in users.items():
                last = bucket.get("last_request_date") or ""
                total = int(bucket.get("total_requests", 0))
                if last < cutoff and total < min_total_to_keep:
                    doomed.append(uid)
            for uid in doomed:
                users.pop(uid, None)
            removed = len(doomed)
            doc["users"] = users

        try:
            self._store.update(mutator)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FatigueStore] cleanup_inactive failed: {exc}")
        return removed

    def delete_user(self, user_id: str) -> bool:
        """Remove a user bucket entirely (GDPR / forget_me)."""
        uid = str(user_id)

        def mutator(doc: Dict[str, Any]) -> None:
            users = doc.get("users") or {}
            users.pop(uid, None)
            doc["users"] = users

        try:
            self._store.update(mutator)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[FatigueStore] delete_user failed: {exc}")
            return False


# --- module-level instance cache --------------------------------------------

_GLOBAL_INSTANCE: Optional[FatigueStore] = None
_INSTANCE_LOCK = threading.Lock()


def get_fatigue_store(db_dir: Optional[Path | str] = None) -> FatigueStore:
    """Return the process-wide global :class:`FatigueStore`.

    Sharing a single instance keeps the in-memory cache of the underlying
    :class:`JsonStore` consistent with disk across all callers.
    """
    with _INSTANCE_LOCK:
        global _GLOBAL_INSTANCE
        if _GLOBAL_INSTANCE is None:
            _GLOBAL_INSTANCE = FatigueStore(db_dir=db_dir)
        return _GLOBAL_INSTANCE


def invalidate_fatigue_store() -> None:
    """Drop the cached global instance (for testing)."""
    with _INSTANCE_LOCK:
        global _GLOBAL_INSTANCE
        _GLOBAL_INSTANCE = None
