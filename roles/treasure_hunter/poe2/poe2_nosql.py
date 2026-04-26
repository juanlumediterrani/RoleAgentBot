"""NoSQL-based POE2 data storage using JsonStore and JsonlRingBuffer.

Replaces SQLite databases:
- poe2STDpricehistory.db → shared/poe2/prices_latest.json + prices_history.jsonl
- PoE2Standard.db → shared/poe2/items_catalog.json
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from persistence.json_store import JsonStore
from persistence.jsonl_store import JsonlRingBuffer
from agent_logging import get_logger

logger = get_logger("poe2_nosql")


class Poe2NoSQL:
    """NoSQL-based POE2 data storage.

    File structure (global, segmented by league):
    - databases/shared/poe2/
      - items_catalog.json: {item_name: {item_id, name, ...}}
      - prices_latest.json: {league: {item_id: {price, updated_at}}}
      - prices_history_{league}.jsonl: JSON lines of price updates per league (max 720 entries)
    """

    def __init__(self, db_dir: Optional[Path] = None):
        if db_dir is None:
            db_dir = Path(__file__).parent.parent.parent.parent / "databases" / "shared" / "poe2"
            db_dir.mkdir(parents=True, exist_ok=True)
        else:
            db_dir = Path(db_dir)

        self._db_dir = db_dir

        # Initialize stores
        self._items_catalog = JsonStore(
            db_dir / "items_catalog.json",
            default_factory=lambda: {},
            keep_backup=False,
        )

        self._prices_latest = JsonStore(
            db_dir / "prices_latest.json",
            default_factory=lambda: {},
            keep_backup=False,
        )

        # Price history buffers per league (lazy initialization)
        self._price_history_buffers: Dict[str, JsonlRingBuffer] = {}

        logger.info(f"🗄️ [NoSQL POE2] Initialized at {db_dir}")

    # Items Catalog
    def save_item(self, item_name: str, item_data: dict):
        """Save item to catalog."""
        self._items_catalog.set(item_name, item_data)

    def get_item(self, item_name: str) -> Optional[dict]:
        """Get item from catalog."""
        return self._items_catalog.get(item_name)

    def get_all_items(self) -> Dict[str, dict]:
        """Get all items from catalog."""
        return self._items_catalog.load()

    def delete_item(self, item_name: str):
        """Delete item from catalog."""
        self._items_catalog.update(lambda data: data.pop(item_name, None))

    # Latest Prices
    def save_latest_price(self, league: str, item_id: int, price_data: dict):
        """Save latest price for item in league."""
        self._prices_latest.update(lambda data: self._set_nested(data, [league, str(item_id)], price_data))

    def get_latest_price(self, league: str, item_id: int) -> Optional[dict]:
        """Get latest price for item in league."""
        return self._prices_latest.get(f"{league}.{item_id}")

    def get_all_latest_prices(self, league: str) -> Dict[int, dict]:
        """Get all latest prices for league."""
        league_data = self._prices_latest.get(league)
        return {int(k): v for k, v in league_data.items()} if league_data else {}

    # Price History
    def _get_price_history_buffer(self, league: str) -> JsonlRingBuffer:
        """Get or create price history buffer for a specific league."""
        if league not in self._price_history_buffers:
            self._price_history_buffers[league] = JsonlRingBuffer(
                self._db_dir / f"prices_history_{league}.jsonl",
                max_lines=10000,
                max_bytes=50 * 1024 * 1024,
                keep_lines=720,
            )
        return self._price_history_buffers[league]

    def append_price_history(self, entry: dict, league: str):
        """Append price history entry to league-specific buffer."""
        buffer = self._get_price_history_buffer(league)
        buffer.append(entry)

    def get_price_history(self, item_id: int, league: str, limit: int = 100) -> List[dict]:
        """Get price history for item in league."""
        buffer = self._get_price_history_buffer(league)
        predicate = lambda e: e.get("item_id") == item_id
        return buffer.filter_tail(predicate, limit)

    def cleanup_old_history(self, days: int = 30):
        """Cleanup price history older than N days."""
        cutoff = datetime.now().timestamp() - (days * 86400)
        # JsonlRingBuffer handles rotation automatically
        logger.info(f"🧹 [NoSQL POE2] Price history cleanup (retention: {days}d)")

    # Migration helpers
    def migrate_from_sqlite(self, sqlite_path: Path, league: str):
        """Migrate data from SQLite POE2 database."""
        if not sqlite_path.exists():
            logger.warning(f"SQLite database not found: {sqlite_path}")
            return

        logger.info(f"🔄 [NoSQL POE2] Migrating from {sqlite_path} for league {league}")

        try:
            conn = sqlite3.connect(str(sqlite_path))
            cursor = conn.cursor()

            # Migrate items catalog
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='items'")
            if cursor.fetchone():
                cursor.execute("SELECT * FROM items")
                for row in cursor.fetchall():
                    item_data = {
                        "item_id": row[0],
                        "name": row[1],
                        # Add other fields as needed
                    }
                    self.save_item(row[1], item_data)

            # Migrate price history
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='price_history'")
            if cursor.fetchone():
                cursor.execute("SELECT * FROM price_history")
                for row in cursor.fetchall():
                    entry = {
                        "item_id": row[0],
                        "price": row[1],
                        "timestamp": row[2],
                        "league": league,
                    }
                    self.append_price_history(entry, league)
                    # Also save as latest
                    self.save_latest_price(league, row[0], {"price": row[1], "updated_at": row[2]})

            conn.close()
            logger.info(f"✅ [NoSQL POE2] Migration completed for league {league}")

        except Exception as e:
            logger.error(f"❌ [NoSQL POE2] Migration failed: {e}")

    def _set_nested(self, data: dict, keys: list, value: Any):
        """Set nested dictionary value."""
        d = data
        for key in keys[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[keys[-1]] = value
        return data


# Global instance
_poe2_nosql_instance: Optional[Poe2NoSQL] = None


def get_poe2_nosql(db_dir: Optional[Path] = None) -> Poe2NoSQL:
    """Get or create the global Poe2NoSQL instance."""
    global _poe2_nosql_instance
    if _poe2_nosql_instance is None:
        _poe2_nosql_instance = Poe2NoSQL(db_dir)
    return _poe2_nosql_instance
