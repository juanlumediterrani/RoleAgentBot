"""E2E test: db_role_news_watcher methods delegate correctly to NoSQL facade.

Reproduces and verifies the fix for the production bug:
    sqlite3.OperationalError: no such table: watcher_subscriptions

After Phase E, the watcher_subscriptions table no longer exists in SQLite.
Methods in db_role_news_watcher.py must delegate to role_configs_nosql.
"""

import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import roles.role_configs_nosql


class DbRoleNewsWatcherNoSqlFacadeTests(unittest.IsolatedAsyncioTestCase):
    """Verify DatabaseRoleNewsWatcher delegates watcher methods to NoSQL."""

    def setUp(self):
        self._tmp_dir = Path(tempfile.mkdtemp())
        role_configs_nosql._instances.clear()
        nosql = role_configs_nosql.RoleConfigsNoSQL(
            server_id="test_server", db_dir=self._tmp_dir
        )
        role_configs_nosql._instances["test_server"] = nosql
        self.nosql = nosql

    def tearDown(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        role_configs_nosql._instances.clear()

    def _build_db(self):
        """Build a DatabaseRoleNewsWatcher with mocked SQLite init."""
        from roles.news_watcher.db_role_news_watcher import DatabaseRoleNewsWatcher
        with mock.patch.object(DatabaseRoleNewsWatcher, "_ensure_writable_db", lambda self: None), \
             mock.patch.object(DatabaseRoleNewsWatcher, "_init_db", lambda self: None):
            db = DatabaseRoleNewsWatcher(server_id="test_server")
        # Force the db to use the same NoSQL instance as the test
        db._nosql_cache = self.nosql
        return db

    async def test_create_subscription_no_longer_crashes(self):
        """The original bug: create_subscription → no such table: watcher_subscriptions."""
        db = self._build_db()
        result = await db.create_subscription(
            user_id="user1",
            channel_id=None,
            category="tech",
            feed_id=123,
            premises="AI analysis",
            keywords=None,
            method="general",
            created_by="user1",
            increment_global_count=False,
        )
        # Returns 0 as placeholder ID
        self.assertEqual(result, 0)

        subs = db.get_user_subscriptions("user1")
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0][1], "user1")  # user_id in tuple
        self.assertEqual(subs[0][3], "tech")  # category in tuple

    async def test_get_all_active_subscriptions(self):
        db = self._build_db()
        await db.create_subscription(
            user_id="u1", channel_id=None, category="tech", method="general", increment_global_count=False,
        )
        await db.create_subscription(
            user_id="u2", channel_id=None, category="science", method="general", increment_global_count=False,
        )
        all_subs = db.get_all_active_subscriptions()
        self.assertEqual(len(all_subs), 2)

    async def test_get_channel_subscriptions(self):
        db = self._build_db()
        await db.create_subscription(
            user_id=None, channel_id="ch1", category="tech", method="keyword", increment_global_count=False,
        )
        ch_subs = db.get_channel_subscriptions("ch1")
        self.assertEqual(len(ch_subs), 1)
        self.assertEqual(ch_subs[0][2], "ch1")  # channel_id in tuple

    async def test_get_users_with_active_subscriptions(self):
        db = self._build_db()
        await db.create_subscription(
            user_id="u1", channel_id=None, category="tech", method="general", increment_global_count=False,
        )
        await db.create_subscription(
            user_id="u2", channel_id=None, category="science", method="general", increment_global_count=False,
        )
        users = db.get_users_with_active_subscriptions()
        self.assertEqual(len(users), 2)
        self.assertIn("u1", users)
        self.assertIn("u2", users)

    async def test_get_user_keyword_subscriptions(self):
        db = self._build_db()
        await db.create_subscription(
            user_id="u1", channel_id=None, category="tech", keywords="AI, ML", method="keyword", increment_global_count=False,
        )
        kw_subs = db.get_user_keyword_subscriptions("u1")
        self.assertEqual(len(kw_subs), 1)
        self.assertEqual(kw_subs[0][0], "tech")  # category
        self.assertEqual(kw_subs[0][2], "AI, ML")  # keywords

    async def test_get_user_keywords(self):
        db = self._build_db()
        await db.create_subscription(
            user_id="u1", channel_id=None, category="tech", keywords="AI, ML", method="keyword", increment_global_count=False,
        )
        kw = db.get_user_keywords("u1")
        self.assertEqual(kw, "AI, ML")

    async def test_update_user_keywords(self):
        db = self._build_db()
        await db.create_subscription(
            user_id="u1", channel_id=None, category="tech", keywords="AI", method="keyword", increment_global_count=False,
        )
        ok = db.update_user_keywords("u1", "AI, ML, Robotics")
        self.assertTrue(ok)
        kw = db.get_user_keywords("u1")
        self.assertEqual(kw, "AI, ML, Robotics")

    async def test_cancel_user_keyword_subscription(self):
        db = self._build_db()
        await db.create_subscription(
            user_id="u1", channel_id=None, category="tech", keywords="AI", method="keyword", increment_global_count=False,
        )
        ok = db.cancel_user_keyword_subscription("u1", "tech")
        self.assertTrue(ok)
        kw_subs = db.get_user_keyword_subscriptions("u1")
        self.assertEqual(len(kw_subs), 0)


if __name__ == "__main__":
    unittest.main()
