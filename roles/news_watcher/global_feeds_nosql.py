"""NoSQL-based global feeds health storage using JsonStore.

Replaces global_feeds.db with JSON storage for RSS feed configuration and health checks.
"""

from pathlib import Path
from typing import List, Dict, Optional, Any

from persistence.json_store import JsonStore
from agent_logging import get_logger

logger = get_logger("global_feeds_nosql")


class GlobalFeedsNoSQL:
    """NoSQL-based global feeds health storage.

    File structure:
    - databases/news_watcher/feeds_health.json: {feeds: [...], health_log: [...]}
    """

    def __init__(self, db_dir: Optional[Path] = None):
        if db_dir is None:
            db_dir = Path(__file__).parent.parent.parent / "databases" / "news_watcher"
            db_dir.mkdir(parents=True, exist_ok=True)
        else:
            db_dir = Path(db_dir)

        self._store = JsonStore(
            db_dir / "feeds_health.json",
            default_factory=lambda: {"feeds": {}, "health_log": []},
            keep_backup=False,
        )

        logger.info(f"🗄️ [NoSQL Global Feeds] Initialized at {db_dir}")

    # Feeds management
    def add_feed(self, feed_id: int, name: str, url: str, category: str, language: str = "en"):
        """Add or update a feed."""
        self._store.update(lambda data: data["feeds"].update({
            str(feed_id): {
                "id": feed_id,
                "name": name,
                "url": url,
                "category": category,
                "language": language,
                "active": True,
                "status": "unknown",
                "error_message": None,
            }
        }))

    def get_feed(self, feed_id: int) -> Optional[Dict]:
        """Get a feed by ID."""
        return self._store.get(f"feeds.{feed_id}")

    def get_all_feeds(self) -> List[Dict]:
        """Get all feeds."""
        feeds_data = self._store.get("feeds") or {}
        return list(feeds_data.values())

    def get_feeds_by_category(self, category: str) -> List[Dict]:
        """Get feeds by category."""
        all_feeds = self.get_all_feeds()
        return [f for f in all_feeds if f.get("category") == category]

    def update_feed_status(self, feed_id: int, status: str, error_message: str = None):
        """Update feed health status."""
        self._store.update(lambda data: self._update_nested(data, ["feeds", str(feed_id), "status"], status))
        if error_message:
            self._store.update(lambda data: self._update_nested(data, ["feeds", str(feed_id), "error_message"], error_message))

    def get_healthy_feeds(self) -> List[tuple]:
        """Get healthy feeds as tuples (id, name, url, category)."""
        all_feeds = self.get_all_feeds()
        return [(f["id"], f["name"], f["url"], f["category"]) for f in all_feeds if f.get("active") and f.get("status") != "error"]

    # Health log
    def log_health_check(self, feed_id: int, status: str, error_message: str = None):
        """Log a health check result."""
        entry = {
            "feed_id": feed_id,
            "check_time": None,  # Could add timestamp
            "status": status,
            "error_message": error_message,
        }
        self._store.update(lambda data: data["health_log"].append(entry))
        # Keep only last 1000 entries
        health_log = self._store.get("health_log")
        if len(health_log) > 1000:
            self._store.update(lambda data: data.update({"health_log": health_log[-1000:]}))

    def get_health_log(self, feed_id: int, limit: int = 100) -> List[Dict]:
        """Get health log for a feed."""
        health_log = self._store.get("health_log") or []
        return [e for e in health_log if e.get("feed_id") == feed_id][-limit:]

    def _update_nested(self, data: dict, keys: list, value: Any):
        """Update nested dictionary value."""
        d = data
        for key in keys[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[keys[-1]] = value
        return data


# Global instance
_global_feeds_nosql_instance: Optional[GlobalFeedsNoSQL] = None


def get_global_feeds_nosql(db_dir: Optional[Path] = None) -> GlobalFeedsNoSQL:
    """Get or create the global GlobalFeedsNoSQL instance."""
    global _global_feeds_nosql_instance
    if _global_feeds_nosql_instance is None:
        _global_feeds_nosql_instance = GlobalFeedsNoSQL(db_dir)
    return _global_feeds_nosql_instance
