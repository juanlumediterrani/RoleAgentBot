"""NoSQL fatigue tracking using JsonStore.

Replaces SQLite fatigue database with atomic JSON document storage.
"""

from __future__ import annotations

import datetime
import threading
from pathlib import Path
from typing import Dict, Optional, Any

from persistence.json_store import JsonStore
from agent_logging import get_logger

logger = get_logger("fatigue_store")

# Module-level cache of FatigueStore instances per server
_fatigue_instances: Dict[str, "FatigueStore"] = {}
_fatigue_lock = threading.Lock()


def get_fatigue_store(server_id: str, base_dir: Path | str | None = None) -> "FatigueStore":
    """Get or create a FatigueStore for a server."""
    global _fatigue_instances
    with _fatigue_lock:
        if server_id not in _fatigue_instances:
            _fatigue_instances[server_id] = FatigueStore(server_id, base_dir)
        return _fatigue_instances[server_id]


def invalidate_fatigue_store(server_id: str | None = None) -> None:
    """Invalidate cached FatigueStore instance(s)."""
    global _fatigue_instances
    with _fatigue_lock:
        if server_id:
            _fatigue_instances.pop(server_id, None)
        else:
            _fatigue_instances.clear()


class FatigueStore:
    """Thread-safe NoSQL store for per-user and per-server fatigue counters."""

    def __init__(self, server_id: str, base_dir: Path | str | None = None):
        self.server_id = server_id
        self._lock = threading.Lock()
        if base_dir is None:
            base_dir = Path(__file__).parent.parent / "databases" / server_id
        else:
            base_dir = Path(base_dir) / server_id
        base_dir.mkdir(parents=True, exist_ok=True)

        self._store = JsonStore(
            base_dir / "fatigue.json",
            default_factory=lambda: {"users": {}, "server_id": server_id, "version": 1},
            keep_backup=False,
        )

    # ── public API ───────────────────────────────────────────────────────

    def increment(self, user_id: str, user_name: str | None = None) -> tuple[int, int]:
        """Increment fatigue for a user and also the server total.

        Returns (daily_requests, total_requests) after increment.
        """
        today = str(datetime.date.today())
        now = datetime.datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0).isoformat()
        five_min_ago = (now - datetime.timedelta(minutes=5)).isoformat()

        def _mutate(doc: dict) -> dict:
            users = doc.setdefault("users", {})
            user = users.setdefault(user_id, {})

            # Reset daily if date changed
            last_date = user.get("last_request_date", "")
            if last_date != today:
                user["daily_requests"] = 1
                user["last_request_date"] = today
            else:
                user["daily_requests"] = user.get("daily_requests", 0) + 1

            # Reset hourly if hour changed
            last_hour = user.get("last_hour_timestamp", "")
            if last_hour != current_hour:
                user["hourly_requests"] = 1
                user["last_hour_timestamp"] = current_hour
            else:
                user["hourly_requests"] = user.get("hourly_requests", 0) + 1

            # Reset burst if > 5 min since last burst
            last_burst = user.get("last_burst_timestamp", "")
            if last_burst and last_burst > five_min_ago:
                user["burst_requests"] = user.get("burst_requests", 0) + 1
            else:
                user["burst_requests"] = 1
            user["last_burst_timestamp"] = now.isoformat()

            user["total_requests"] = user.get("total_requests", 0) + 1
            if user_name:
                user["user_name"] = user_name
            elif "user_name" not in user:
                user["user_name"] = f"User_{user_id}"

            # Also increment server total
            server_id_key = f"server_{self.server_id}"
            server_user = users.setdefault(server_id_key, {})
            srv_last_date = server_user.get("last_request_date", "")
            if srv_last_date != today:
                server_user["daily_requests"] = 1
                server_user["last_request_date"] = today
            else:
                server_user["daily_requests"] = server_user.get("daily_requests", 0) + 1

            srv_last_hour = server_user.get("last_hour_timestamp", "")
            if srv_last_hour != current_hour:
                server_user["hourly_requests"] = 1
                server_user["last_hour_timestamp"] = current_hour
            else:
                server_user["hourly_requests"] = server_user.get("hourly_requests", 0) + 1

            srv_last_burst = server_user.get("last_burst_timestamp", "")
            if srv_last_burst and srv_last_burst > five_min_ago:
                server_user["burst_requests"] = server_user.get("burst_requests", 0) + 1
            else:
                server_user["burst_requests"] = 1
            server_user["last_burst_timestamp"] = now.isoformat()

            server_user["total_requests"] = server_user.get("total_requests", 0) + 1
            server_user["user_name"] = f"Server_{self.server_id}"

            return doc

        self._store.update(_mutate)

        doc = self._store.load()
        user = doc["users"].get(user_id, {})
        return user.get("daily_requests", 0), user.get("total_requests", 0)

    def get_stats(self, user_id: str | None = None) -> dict:
        """Get fatigue stats for one user or all users."""
        doc = self._store.load()
        users = doc.get("users", {})

        if user_id:
            user = users.get(user_id, {})
            if not user:
                return {}
            return {
                "user_id": user_id,
                "user_name": user.get("user_name", ""),
                "daily_requests": user.get("daily_requests", 0),
                "total_requests": user.get("total_requests", 0),
                "last_request_date": user.get("last_request_date", ""),
                "hourly_requests": user.get("hourly_requests", 0),
                "last_hour_timestamp": user.get("last_hour_timestamp", ""),
                "burst_requests": user.get("burst_requests", 0),
                "last_burst_timestamp": user.get("last_burst_timestamp", ""),
            }

        stats = []
        for uid, user in users.items():
            stats.append({
                "user_id": uid,
                "user_name": user.get("user_name", ""),
                "daily_requests": user.get("daily_requests", 0),
                "total_requests": user.get("total_requests", 0),
                "last_request_date": user.get("last_request_date", ""),
                "hourly_requests": user.get("hourly_requests", 0),
                "last_hour_timestamp": user.get("last_hour_timestamp", ""),
                "burst_requests": user.get("burst_requests", 0),
                "last_burst_timestamp": user.get("last_burst_timestamp", ""),
            })
        stats.sort(key=lambda x: x["total_requests"], reverse=True)
        return {"users": stats}

    def reset_user(self, user_id: str) -> None:
        """Reset a single user's fatigue counters."""
        def _mutate(doc: dict) -> dict:
            users = doc.setdefault("users", {})
            if user_id in users:
                users[user_id]["daily_requests"] = 0
                users[user_id]["hourly_requests"] = 0
                users[user_id]["burst_requests"] = 0
                users[user_id]["total_requests"] = 0
            return doc

        self._store.update(_mutate)

    def reset_daily(self) -> int:
        """Reset daily counters for all users. Returns number of users reset."""
        count = 0

        def _mutate(doc: dict) -> dict:
            nonlocal count
            users = doc.setdefault("users", {})
            for user in users.values():
                if user.get("daily_requests", 0) > 0:
                    user["daily_requests"] = 0
                    count += 1
            return doc

        self._store.update(_mutate)
        return count

    def cleanup_old(self, days_to_keep: int = 30) -> int:
        """Remove inactive users with no activity for specified days."""
        cutoff_date = (datetime.date.today() - datetime.timedelta(days=days_to_keep)).isoformat()
        removed = 0

        def _mutate(doc: dict) -> dict:
            nonlocal removed
            users = doc.setdefault("users", {})
            to_remove = []
            for uid, user in users.items():
                if uid.startswith("server_"):
                    continue
                last_date = user.get("last_request_date", "")
                total = user.get("total_requests", 0)
                if last_date < cutoff_date and total < 10:
                    to_remove.append(uid)
            for uid in to_remove:
                del users[uid]
                removed += 1
            return doc

        self._store.update(_mutate)
        return removed

    def forget_user(self, user_id: str) -> bool:
        """GDPR — remove a user from fatigue store."""
        def _mutate(doc: dict) -> dict:
            users = doc.setdefault("users", {})
            if user_id in users:
                del users[user_id]
            return doc

        self._store.update(_mutate)
        return True
