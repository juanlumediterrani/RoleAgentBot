"""E2E test for news_watcher NoSQL migration.

This test verifies that the news_watcher cycle works correctly with
global_news_nosql.py instead of global_news_db.py.
"""

import asyncio
import tempfile
import unittest
from pathlib import Path

from roles.news_watcher.global_feeds_nosql import GlobalFeedsNoSQL


class NewsWatcherNoSQLE2ETest(unittest.TestCase):
    """E2E test for news_watcher NoSQL migration."""

    def setUp(self):
        """Create a fresh NoSQL instance for testing."""
        self.test_dir = tempfile.mkdtemp()
        self.global_db = GlobalFeedsNoSQL(db_dir=Path(self.test_dir))

    def test_news_tracking_cycle(self):
        """Test the complete news tracking cycle."""
        # Add a feed
        self.global_db.add_feed(1, "Test Feed", "https://example.com/feed", "tech", "en")

        # Verify feed was added
        feed = self.global_db.get_feed(1)
        self.assertEqual(feed["name"], "Test Feed")
        self.assertEqual(feed["category"], "tech")

        # Update feed status
        self.global_db.update_feed_status(1, "healthy")

        # Verify status update
        feed = self.global_db.get_feed(1)
        self.assertEqual(feed["status"], "healthy")

        # Log health check
        self.global_db.log_health_check(1, "healthy")

        # Verify health log
        health_log = self.global_db.get_health_log(1, limit=10)
        self.assertEqual(len(health_log), 1)
        self.assertEqual(health_log[0]["status"], "healthy")

    def test_get_healthy_feeds(self):
        """Test retrieving healthy feeds."""
        # Add multiple feeds with different statuses
        self.global_db.add_feed(1, "Feed 1", "https://example.com/feed1", "tech", "en")
        self.global_db.add_feed(2, "Feed 2", "https://example.com/feed2", "tech", "en")
        self.global_db.add_feed(3, "Feed 3", "https://example.com/feed3", "tech", "en")

        # Update statuses
        self.global_db.update_feed_status(1, "healthy")
        self.global_db.update_feed_status(2, "error")
        self.global_db.update_feed_status(3, "healthy")

        # Get healthy feeds
        healthy_feeds = self.global_db.get_healthy_feeds()
        self.assertEqual(len(healthy_feeds), 2)

    def test_feeds_by_category(self):
        """Test retrieving feeds by category."""
        # Add feeds in different categories
        self.global_db.add_feed(1, "Tech Feed", "https://example.com/tech", "tech", "en")
        self.global_db.add_feed(2, "News Feed", "https://example.com/news", "news", "en")

        # Get feeds by category
        tech_feeds = self.global_db.get_feeds_by_category("tech")
        self.assertEqual(len(tech_feeds), 1)
        self.assertEqual(tech_feeds[0]["category"], "tech")

        news_feeds = self.global_db.get_feeds_by_category("news")
        self.assertEqual(len(news_feeds), 1)
        self.assertEqual(news_feeds[0]["category"], "news")


if __name__ == "__main__":
    unittest.main()
