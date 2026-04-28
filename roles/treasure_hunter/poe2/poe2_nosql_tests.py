"""Unit tests for poe2_nosql.py"""

import json
import tempfile
import unittest

from roles.treasure_hunter.poe2.poe2_nosql import Poe2NoSQL


class Poe2NoSQLTests(unittest.TestCase):
    def _get_nosql(self):
        """Create a fresh NoSQL instance with independent directory."""
        test_dir = tempfile.mkdtemp()
        return Poe2NoSQL(db_dir=test_dir)

    def test_save_and_get_item(self):
        nosql = self._get_nosql()
        item_data = {"item_id": 123, "name": "Test Item"}
        nosql.save_item("Test Item", item_data)
        retrieved = nosql.get_item("Test Item")
        self.assertEqual(retrieved["item_id"], 123)
        self.assertEqual(retrieved["name"], "Test Item")

    def test_get_all_items(self):
        nosql = self._get_nosql()
        nosql.save_item("Item1", {"item_id": 1, "name": "Item1"})
        nosql.save_item("Item2", {"item_id": 2, "name": "Item2"})
        all_items = nosql.get_all_items()
        self.assertEqual(len(all_items), 2)

    def test_delete_item(self):
        nosql = self._get_nosql()
        nosql.save_item("Item1", {"item_id": 1, "name": "Item1"})
        nosql.delete_item("Item1")
        retrieved = nosql.get_item("Item1")
        self.assertIsNone(retrieved)

    def test_save_and_get_latest_price(self):
        nosql = self._get_nosql()
        price_data = {"price": 100, "updated_at": "2026-04-25T00:00:00Z"}
        nosql.save_latest_price("Standard", 123, price_data)
        retrieved = nosql.get_latest_price("Standard", 123)
        self.assertEqual(retrieved["price"], 100)

    def test_get_all_latest_prices(self):
        nosql = self._get_nosql()
        nosql.save_latest_price("Standard", 123, {"price": 100, "updated_at": "2026-04-25T00:00:00Z"})
        nosql.save_latest_price("Standard", 456, {"price": 200, "updated_at": "2026-04-25T00:00:00Z"})
        all_prices = nosql.get_all_latest_prices("Standard")
        self.assertEqual(len(all_prices), 2)

    def test_append_and_get_price_history(self):
        nosql = self._get_nosql()
        entry1 = {"item_id": 123, "price": 100, "timestamp": "2026-04-25T00:00:00Z", "league": "Standard"}
        entry2 = {"item_id": 123, "price": 110, "timestamp": "2026-04-25T01:00:00Z", "league": "Standard"}
        nosql.append_price_history(entry1, "Standard")
        nosql.append_price_history(entry2, "Standard")
        history = nosql.get_price_history(123, "Standard")
        self.assertEqual(len(history), 2)

    def test_price_history_filter_by_league(self):
        nosql = self._get_nosql()
        entry1 = {"item_id": 123, "price": 100, "timestamp": "2026-04-25T00:00:00Z", "league": "Standard"}
        entry2 = {"item_id": 123, "price": 110, "timestamp": "2026-04-25T01:00:00Z", "league": "Hardcore"}
        nosql.append_price_history(entry1, "Standard")
        nosql.append_price_history(entry2, "Hardcore")
        history = nosql.get_price_history(123, "Standard")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["league"], "Standard")


if __name__ == "__main__":
    unittest.main()
