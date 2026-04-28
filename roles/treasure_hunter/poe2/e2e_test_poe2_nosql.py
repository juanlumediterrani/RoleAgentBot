"""E2E test for POE2 NoSQL migration.

This test verifies that the POE2 price tracking cycle works correctly with
poe2_nosql.py instead of SQLite databases.
"""

import tempfile
import unittest
from pathlib import Path

from roles.treasure_hunter.poe2.poe2_nosql import Poe2NoSQL


class Poe2NoSQLE2ETest(unittest.TestCase):
    """E2E test for POE2 NoSQL migration."""

    def setUp(self):
        """Create a fresh NoSQL instance for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.poe2_db = Poe2NoSQL(db_dir=Path(self.test_dir))

    def test_items_catalog_cycle(self):
        """Test the complete items catalog cycle."""
        # Add an item to catalog
        item_data = {"item_id": 123, "name": "Test Item", "base_type": "sword"}
        self.poe2_db.save_item("Test Item", item_data)

        # Verify item was added
        retrieved = self.poe2_db.get_item("Test Item")
        self.assertEqual(retrieved["item_id"], 123)
        self.assertEqual(retrieved["name"], "Test Item")

        # Get all items
        all_items = self.poe2_db.get_all_items()
        self.assertEqual(len(all_items), 1)

        # Delete item
        self.poe2_db.delete_item("Test Item")
        retrieved = self.poe2_db.get_item("Test Item")
        self.assertIsNone(retrieved)

    def test_price_tracking_cycle(self):
        """Test the complete price tracking cycle per league."""
        league = "Standard"
        item_id = 123

        # Save latest price
        price_data = {"price": 100, "updated_at": "2026-04-26T00:00:00Z"}
        self.poe2_db.save_latest_price(league, item_id, price_data)

        # Verify latest price
        retrieved = self.poe2_db.get_latest_price(league, item_id)
        self.assertEqual(retrieved["price"], 100)

        # Get all latest prices for league
        self.poe2_db.save_latest_price(league, 456, {"price": 200, "updated_at": "2026-04-26T00:00:00Z"})
        all_prices = self.poe2_db.get_all_latest_prices(league)
        self.assertEqual(len(all_prices), 2)

    def test_price_history_cycle(self):
        """Test the complete price history cycle per league."""
        league = "Standard"
        item_id = 123

        # Append price history entries
        entry1 = {"item_id": item_id, "price": 100, "timestamp": "2026-04-26T00:00:00Z"}
        entry2 = {"item_id": item_id, "price": 110, "timestamp": "2026-04-26T01:00:00Z"}
        self.poe2_db.append_price_history(entry1, league)
        self.poe2_db.append_price_history(entry2, league)

        # Get price history
        history = self.poe2_db.get_price_history(item_id, league, limit=10)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["price"], 100)
        self.assertEqual(history[1]["price"], 110)

    def test_league_isolation(self):
        """Test that price history is isolated per league."""
        item_id = 123

        # Add price history to Standard league
        entry_standard = {"item_id": item_id, "price": 100, "timestamp": "2026-04-26T00:00:00Z"}
        self.poe2_db.append_price_history(entry_standard, "Standard")

        # Add price history to Hardcore league
        entry_hardcore = {"item_id": item_id, "price": 200, "timestamp": "2026-04-26T00:00:00Z"}
        self.poe2_db.append_price_history(entry_hardcore, "Hardcore")

        # Verify isolation
        standard_history = self.poe2_db.get_price_history(item_id, "Standard")
        hardcore_history = self.poe2_db.get_price_history(item_id, "Hardcore")

        self.assertEqual(len(standard_history), 1)
        self.assertEqual(standard_history[0]["price"], 100)
        self.assertEqual(len(hardcore_history), 1)
        self.assertEqual(hardcore_history[0]["price"], 200)


if __name__ == "__main__":
    unittest.main()
