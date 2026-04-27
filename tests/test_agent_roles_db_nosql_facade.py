"""E2E test: agent_roles_db methods delegate correctly to NoSQL facade.

Reproduces and verifies the fix for the production bug:
    sqlite3.OperationalError: no such table: ring_accusations

After Phase E, agent_roles_db.py no longer creates tables for migrated roles.
Its methods must delegate to role_configs_nosql.RoleConfigsNoSQL.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import roles.role_configs_nosql


class AgentRolesDbNoSqlFacadeTests(unittest.TestCase):
    """Verify AgentRolesDatabase delegates migrated methods to NoSQL."""

    def setUp(self):
        self._tmp_dir = Path(tempfile.mkdtemp())
        # Reset module-level instance cache so each test gets its own dir
        role_configs_nosql._instances.clear()
        # Create a RoleConfigsNoSQL directly on tmp path and register it
        nosql = role_configs_nosql.RoleConfigsNoSQL(
            server_id="test_server", db_dir=self._tmp_dir
        )
        role_configs_nosql._instances["test_server"] = nosql
        self.nosql = nosql

    def tearDown(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        role_configs_nosql._instances.clear()

    def _build_roles_db(self):
        """Build a RolesDatabase (NoSQL-backed, no SQLite init needed)."""
        import agent_roles_db
        db = agent_roles_db.RolesDatabase(server_id="test_server")
        return db

    def test_save_ring_accusation_no_longer_crashes(self):
        """The original bug: save_ring_accusation → no such table: ring_accusations."""
        db = self._build_roles_db()
        result = db.save_ring_accusation(
            accuser_id="user1",
            accused_id="user2",
            accusation="stole my cookie",
            evidence="crumbs on keyboard",
        )
        self.assertEqual(result, 0)  # legacy id placeholder

        accusations = db.get_ring_accusations(limit=10)
        self.assertEqual(len(accusations), 1)
        self.assertEqual(accusations[0]["accuser_id"], "user1")
        self.assertEqual(accusations[0]["accused_id"], "user2")

    def test_nordic_runes_cycle(self):
        db = self._build_roles_db()
        db.save_nordic_runes_reading(
            user_id="u1", question="q", runes_drawn=["R1", "R2"],
            interpretation="interp", reading_type="past_present_future",
        )
        readings = db.get_nordic_runes_readings("u1", limit=10)
        self.assertEqual(len(readings), 1)
        stats = db.get_nordic_runes_stats("u1")
        self.assertEqual(stats["total_readings"], 1)
        self.assertEqual(stats["favorite_type"], "past_present_future")

    def test_dice_game_cycle(self):
        db = self._build_roles_db()
        db.save_dice_game_stats(
            user_id="u1", total_plays=5, total_bet=100, total_won=50,
            pots_won=1, biggest_prize=25,
        )
        stats = db.get_dice_game_stats("u1")
        self.assertEqual(stats["total_plays"], 5)

        db.save_dice_game_play(
            user_id="u1", user_name="User1", bet=10, dice="3,4,5",
            combination="straight", prize=20, pot_before=100, pot_after=80,
        )
        history = db.get_dice_game_history(limit=10)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["bet"], 10)

    def test_poe2_subscription_cycle(self):
        db = self._build_roles_db()
        ok = db.save_poe2_subscription(
            user_id="u1", server_id="srv1", league="Standard",
            tracked_items=["Mirror"],
        )
        self.assertTrue(ok)

        sub = db.get_poe2_subscription("u1", "srv1")
        self.assertIsNotNone(sub)
        self.assertEqual(sub["league"], "Standard")

        subs = db.get_poe2_server_subscriptions("srv1")
        self.assertEqual(len(subs), 1)

        self.assertTrue(db.delete_poe2_subscription("u1", "srv1"))
        self.assertIsNone(db.get_poe2_subscription("u1", "srv1"))

    def test_beggar_donation_cycle(self):
        db = self._build_roles_db()
        self.assertTrue(db.update_beggar_donation("u1", "User1", 50, reason="tip"))
        self.assertTrue(db.update_beggar_donation("u1", "User1", 30, reason="tip2"))

        stats = db.get_beggar_user_stats("u1")
        self.assertEqual(stats["total_donated"], 80)
        self.assertEqual(stats["weekly_donated"], 80)
        self.assertEqual(stats["donation_count"], 2)

        weekly = db.get_weekly_donations_summary()
        self.assertEqual(len(weekly), 1)
        self.assertEqual(weekly[0]["weekly_amount"], 80)

        lb = db.get_beggar_leaderboard("srv1", limit=10, weekly_only=True)
        self.assertEqual(len(lb), 1)
        self.assertEqual(lb[0]["total_donated"], 80)

        srv_stats = db.get_beggar_server_stats("srv1", weekly_only=True)
        self.assertEqual(srv_stats["total_donors"], 1)
        self.assertEqual(srv_stats["total_gold"], 80)

        # Reset and verify
        self.assertTrue(db.reset_beggar_weekly_cycle("srv1"))
        stats = db.get_beggar_user_stats("u1")
        self.assertEqual(stats["weekly_donated"], 0)
        self.assertEqual(stats["total_donated"], 80)  # historical preserved

    def test_beggar_request_history(self):
        db = self._build_roles_db()
        db.save_beggar_request("u1", "User1", "begging", "please sir")
        db.save_beggar_request("u1", "User1", "begging", "please sir 2")
        db.save_beggar_request("u1", "User1", "thanking", "thank you")

        begs = db.count_beggar_requests_type_last_day("begging")
        self.assertEqual(begs, 2)
        thx = db.count_beggar_requests_type_last_day("thanking")
        self.assertEqual(thx, 1)


if __name__ == "__main__":
    unittest.main()
