"""Tests for global_news_nosql module."""

import tempfile
import unittest

from global_news_nosql import GlobalNewsNoSQL


class GlobalNewsNoSQLTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = self.tmpdir.name + "/seen.json"
        self.news = GlobalNewsNoSQL(db_path=db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_mark_and_check_processed(self):
        self.assertFalse(self.news.is_news_globally_processed("Test Title"))
        self.news.mark_news_globally_processed("Test Title")
        self.assertTrue(self.news.is_news_globally_processed("Test Title"))

    def test_store_news_content(self):
        self.news.store_news_content(
            title="Test Title",
            source_url="https://example.com",
            feed_category="tech",
            feed_url="https://example.com/feed",
            summary="Test summary",
        )
        self.assertTrue(self.news.is_news_globally_processed("Test Title"))

    def test_get_news_by_feed(self):
        self.news.store_news_content(
            title="Title 1",
            source_url="https://example.com/1",
            feed_category="tech",
            feed_url="https://example.com/feed",
            summary="Summary 1",
        )
        self.news.store_news_content(
            title="Title 2",
            source_url="https://example.com/2",
            feed_category="news",
            feed_url="https://example.com/feed2",
            summary="Summary 2",
        )

        results = self.news.get_news_by_feed("https://example.com/feed")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Title 1")

    def test_get_news_by_category(self):
        self.news.store_news_content(
            title="Title 1",
            source_url="https://example.com/1",
            feed_category="tech",
            feed_url="https://example.com/feed",
            summary="Summary 1",
        )
        self.news.store_news_content(
            title="Title 2",
            source_url="https://example.com/2",
            feed_category="news",
            feed_url="https://example.com/feed2",
            summary="Summary 2",
        )

        results = self.news.get_news_by_category("tech")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Title 1")

    def test_feed_last_updated(self):
        self.assertTrue(self.news.should_update_feed("https://example.com/feed", interval_hours=1))  # Never updated
        self.news.update_feed_last_updated("https://example.com/feed", feed_name="Test Feed", feed_category="tech")
        self.assertTrue(self.news.should_update_feed("https://example.com/feed", interval_hours=0))  # 0 hours = always
        self.assertFalse(self.news.should_update_feed("https://example.com/feed", interval_hours=1))  # Just updated

        last_updated = self.news.get_feed_last_updated("https://example.com/feed")
        self.assertIsNotNone(last_updated)

    def test_cleanup_old_news(self):
        # Add news entries (cleanup will happen automatically on mark/store)
        for i in range(50):
            self.news.mark_news_globally_processed(f"Title {i}")

        stats = self.news.get_global_news_stats()
        self.assertGreater(stats["total_unique_news"], 0)

    def test_get_stats(self):
        self.news.mark_news_globally_processed("Title 1", feed_category="tech")
        self.news.mark_news_globally_processed("Title 2", feed_category="news")

        stats = self.news.get_global_news_stats()
        self.assertEqual(stats["total_unique_news"], 2)
        self.assertEqual(stats["by_category"]["tech"], 1)
        self.assertEqual(stats["by_category"]["news"], 1)


if __name__ == "__main__":
    unittest.main()
