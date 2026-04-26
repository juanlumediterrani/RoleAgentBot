"""Tests for role_configs_nosql module."""

import tempfile
import unittest

from role_configs_nosql import RoleConfigsNoSQL


class RoleConfigsNoSQLTests(unittest.TestCase):
    def _get_configs(self):
        """Create a fresh configs instance with independent directory."""
        test_dir = tempfile.mkdtemp()
        return RoleConfigsNoSQL("test", db_dir=test_dir)

    # --- POE2 Subscriptions ---

    def test_poe2_subscription(self):
        configs = self._get_configs()
        configs.save_poe2_subscription("123", "456", league="Standard", tracked_items=["item1"])
        sub = configs.get_poe2_subscription("123", "456")
        self.assertIsNotNone(sub)
        self.assertEqual(sub["league"], "Standard")
        self.assertEqual(sub["tracked_items"], ["item1"])

    def test_poe2_server_subscriptions(self):
        configs = self._get_configs()
        configs.save_poe2_subscription("123", "456", league="Standard")
        configs.save_poe2_subscription("789", "456", league="Hardcore")
        subs = configs.get_poe2_server_subscriptions("456")
        self.assertEqual(len(subs), 2)

    def test_delete_poe2_subscription(self):
        configs = self._get_configs()
        configs.save_poe2_subscription("123", "456")
        configs.delete_poe2_subscription("123", "456")
        sub = configs.get_poe2_subscription("123", "456")
        self.assertIsNone(sub)

    # --- Watcher Subscriptions ---

    def test_watcher_subscription(self):
        configs = self._get_configs()
        configs.save_watcher_subscription("123", "789", "tech")
        subs = configs.get_watcher_subscriptions(user_id="123", channel_id="789", category="tech")
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0]["category"], "tech")

    def test_watcher_subscription_filters(self):
        configs = self._get_configs()
        configs.save_watcher_subscription("123", "789", "tech")
        configs.save_watcher_subscription("123", "789", "news")
        configs.save_watcher_subscription("456", "789", "tech")

        # Filter by user
        subs = configs.get_watcher_subscriptions(user_id="123")
        self.assertEqual(len(subs), 2)

        # Filter by category
        subs = configs.get_watcher_subscriptions(category="tech")
        self.assertEqual(len(subs), 2)

    def test_delete_watcher_subscription(self):
        configs = self._get_configs()
        configs.save_watcher_subscription("123", "789", "tech")
        configs.delete_watcher_subscription("123", "789", "tech")
        subs = configs.get_watcher_subscriptions(user_id="123", channel_id="789", category="tech")
        self.assertEqual(len(subs), 0)

    # --- Dice Game Stats ---

    def test_dice_game_stats(self):
        configs = self._get_configs()
        configs.save_dice_game_stats("123", total_plays=10, total_won=500)
        stats = configs.get_dice_game_stats("123")
        self.assertEqual(stats["total_plays"], 10)
        self.assertEqual(stats["total_won"], 500)

    def test_dice_game_stats_default(self):
        configs = self._get_configs()
        stats = configs.get_dice_game_stats("nonexistent")
        self.assertEqual(stats["total_plays"], 0)

    # --- Dice Game History ---

    def test_dice_game_history(self):
        configs = self._get_configs()
        configs.save_dice_game_play("123", "Alice", 100, "1,2,3", "straight", 200, 1000, 800)
        history = configs.get_dice_game_history(limit=10)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["user_id"], "123")

    def test_dice_game_history_retention(self):
        configs = self._get_configs()
        for i in range(250):
            configs.save_dice_game_play(str(i), f"User{i}", 100, "1,2,3", "straight", 200, 1000, 800)
        history = configs.get_dice_game_history(limit=300)
        self.assertLessEqual(len(history), 200)

    # --- Nordic Runes ---

    def test_nordic_runes_reading(self):
        configs = self._get_configs()
        configs.save_nordic_runes_reading("123", "What is my fate?", ["fehu", "uruz"], "Strength", "single")
        readings = configs.get_nordic_runes_readings("123")
        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0]["runes_drawn"], ["fehu", "uruz"])

    def test_nordic_runes_retention(self):
        configs = self._get_configs()
        for i in range(150):
            configs.save_nordic_runes_reading("123", f"Question {i}", ["fehu"], "Answer", "single")
        readings = configs.get_nordic_runes_readings("123")
        self.assertLessEqual(len(readings), 100)

    # --- Ring Accusations ---

    def test_ring_accusation(self):
        configs = self._get_configs()
        configs.save_ring_accusation("123", "456", "Stole the ring", "Witness testimony")
        accusations = configs.get_ring_accusations()
        self.assertEqual(len(accusations), 1)
        self.assertEqual(accusations[0]["accuser_id"], "123")

    def test_ring_accusations_retention(self):
        configs = self._get_configs()
        for i in range(150):
            configs.save_ring_accusation(str(i), str(i+1), f"Accusation {i}")
        accusations = configs.get_ring_accusations()
        self.assertLessEqual(len(accusations), 100)

    # --- Beggar Subrole ---

    def test_beggar_subrole(self):
        configs = self._get_configs()
        configs.save_beggar_subrole("123", "Alice", total_donated=1000, donation_count=5)
        subrole = configs.get_beggar_subrole("123")
        self.assertIsNotNone(subrole)
        self.assertEqual(subrole["total_donated"], 1000)
        self.assertEqual(subrole["donation_count"], 5)

    def test_beggar_subrole_default(self):
        configs = self._get_configs()
        subrole = configs.get_beggar_subrole("nonexistent")
        self.assertIsNone(subrole)

    def test_all_beggar_subroles(self):
        configs = self._get_configs()
        configs.save_beggar_subrole("123", "Alice", total_donated=1000)
        configs.save_beggar_subrole("456", "Bob", total_donated=500)
        subroles = configs.get_all_beggar_subroles()
        self.assertEqual(len(subroles), 2)
        # Should be sorted by total_donated descending
        self.assertEqual(subroles[0]["user_id"], "123")
        self.assertEqual(subroles[1]["user_id"], "456")


if __name__ == "__main__":
    unittest.main()
