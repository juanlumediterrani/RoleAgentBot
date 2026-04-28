"""NoSQL-based global news tracking using JsonStore.

Replaces SQLite tables for global news with JSON storage:
- databases/shared/news/seen.json
  - seen_news: {title_hash: {title, first_seen, source_url, feed_category, feed_url, summary, published_date, server_count, last_processed}}
  - feed_last_updated: {feed_url: {last_updated, feed_name, feed_category}}
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from persistence.json_store import JsonStore
from agent_logging import get_logger

logger = get_logger("global_news_nosql")


class GlobalNewsNoSQL:
    """NoSQL-based global news tracking with retention limits.

    File structure:
    - databases/shared/news/seen.json
      - seen_news: {title_hash: {...news entry...}} (retention: 30 days)
      - feed_last_updated: {feed_url: {last_updated, feed_name, feed_category}}
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            base_dir = Path(__file__).parent / "databases" / "shared" / "news"
            base_dir.mkdir(parents=True, exist_ok=True)
            db_path = base_dir / "seen.json"

        self._store = JsonStore(
            db_path,
            default_factory=self._default_state,
            schema_version=1,
            keep_backup=True,
        )
        logger.info(f"🗄️ [NoSQL Global News] Initialized at {db_path}")

    def _default_state(self) -> Dict[str, Dict]:
        """Default empty state structure."""
        return {
            "seen_news": {},
            "feed_last_updated": {},
        }

    def _generate_title_hash(self, title: str) -> str:
        """Generate MD5 hash of title to avoid duplicates."""
        return hashlib.md5(title.encode("utf-8")).hexdigest()

    # --- News Tracking ---

    def is_news_globally_processed(self, title: str) -> bool:
        """Check if news has been processed by any server."""
        try:
            title_hash = self._generate_title_hash(title)
            state = self._store.load()
            seen_news = state.get("seen_news", {})
            return title_hash in seen_news
        except Exception as e:
            logger.exception(f"Error checking if news is globally processed: {e}")
            return False

    def mark_news_globally_processed(
        self,
        title: str,
        source_url: Optional[str] = None,
        feed_category: Optional[str] = None,
        server_id: Optional[str] = None,
        feed_url: Optional[str] = None,
        summary: Optional[str] = None,
        published_date: Optional[str] = None,
    ) -> bool:
        """Mark news as processed globally with full content."""
        try:
            title_hash = self._generate_title_hash(title)
            current_date = datetime.now().isoformat()

            def updater(state: Dict[str, Dict]) -> Dict[str, Dict]:
                seen_news = state.get("seen_news", {})
                existing = seen_news.get(title_hash, {})
                seen_news[title_hash] = {
                    "title": title,
                    "first_seen": existing.get("first_seen", current_date),
                    "source_url": source_url,
                    "feed_category": feed_category,
                    "feed_url": feed_url,
                    "summary": summary,
                    "published_date": published_date,
                    "server_count": existing.get("server_count", 0) + 1,
                    "last_processed": current_date,
                }
                state["seen_news"] = seen_news
                # Cleanup old entries (retention: 30 days)
                state["seen_news"] = self._cleanup_old_news(state["seen_news"], days_to_keep=30)
                return state

            self._store.update(updater)
            logger.debug(f"Marked news as globally processed: {title[:50]}...")
            return True
        except Exception as e:
            logger.exception(f"Error marking news as globally processed: {e}")
            return False

    def store_news_content(
        self,
        title: str,
        source_url: str,
        feed_category: str,
        feed_url: str,
        summary: Optional[str] = None,
        published_date: Optional[str] = None,
    ) -> bool:
        """Store news content in global database."""
        try:
            title_hash = self._generate_title_hash(title)
            current_date = datetime.now().isoformat()

            def updater(state: Dict[str, Dict]) -> Dict[str, Dict]:
                seen_news = state.get("seen_news", {})
                seen_news[title_hash] = {
                    "title": title,
                    "first_seen": current_date,
                    "source_url": source_url,
                    "feed_category": feed_category,
                    "feed_url": feed_url,
                    "summary": summary,
                    "published_date": published_date,
                    "server_count": 1,
                    "last_processed": current_date,
                }
                state["seen_news"] = seen_news
                # Cleanup old entries (retention: 30 days)
                state["seen_news"] = self._cleanup_old_news(state["seen_news"], days_to_keep=30)
                return state

            self._store.update(updater)
            logger.debug(f"Stored news content: {title[:50]}...")
            return True
        except Exception as e:
            logger.exception(f"Error storing news content: {e}")
            return False

    def get_news_by_feed(self, feed_url: str, since_date: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get news from a specific feed, optionally filtered by date."""
        try:
            state = self._store.load()
            seen_news = state.get("seen_news", {})
            results = []

            cutoff = None
            if since_date:
                try:
                    cutoff = datetime.fromisoformat(since_date)
                except ValueError:
                    logger.warning(f"Invalid since_date format: {since_date}")

            for entry in seen_news.values():
                if entry.get("feed_url") != feed_url:
                    continue
                if cutoff:
                    try:
                        first_seen = datetime.fromisoformat(entry.get("first_seen", ""))
                        if first_seen < cutoff:
                            continue
                    except ValueError:
                        continue
                
                # Skip entries without valid description (false positives)
                summary = entry.get("summary", "")
                if not summary or summary.strip() == '' or summary.strip() == 'No description':
                    continue
                
                results.append({
                    "title": entry.get("title"),
                    "source_url": entry.get("source_url"),
                    "summary": entry.get("summary"),
                    "published_date": entry.get("published_date"),
                    "first_seen": entry.get("first_seen"),
                })
                if len(results) >= limit:
                    break

            # Sort by first_seen descending
            results.sort(key=lambda x: x.get("first_seen", ""), reverse=True)
            return results
        except Exception as e:
            logger.exception(f"Error getting news by feed: {e}")
            return []

    def get_news_by_category(self, category: str, since_date: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get news from a specific category, optionally filtered by date."""
        try:
            state = self._store.load()
            seen_news = state.get("seen_news", {})
            results = []

            cutoff = None
            if since_date:
                try:
                    cutoff = datetime.fromisoformat(since_date)
                except ValueError:
                    logger.warning(f"Invalid since_date format: {since_date}")

            for entry in seen_news.values():
                if entry.get("feed_category") != category:
                    continue
                if cutoff:
                    try:
                        first_seen = datetime.fromisoformat(entry.get("first_seen", ""))
                        if first_seen < cutoff:
                            continue
                    except ValueError:
                        continue
                
                # Skip entries without valid description (false positives)
                summary = entry.get("summary", "")
                if not summary or summary.strip() == '' or summary.strip() == 'No description':
                    continue
                
                results.append({
                    "title": entry.get("title"),
                    "source_url": entry.get("source_url"),
                    "summary": entry.get("summary"),
                    "published_date": entry.get("published_date"),
                    "first_seen": entry.get("first_seen"),
                    "feed_url": entry.get("feed_url"),
                })
                if len(results) >= limit:
                    break

            # Sort by first_seen descending
            results.sort(key=lambda x: x.get("first_seen", ""), reverse=True)
            return results
        except Exception as e:
            logger.exception(f"Error getting news by category: {e}")
            return []

    def get_global_news_stats(self) -> Dict:
        """Get statistics about globally processed news."""
        try:
            state = self._store.load()
            seen_news = state.get("seen_news", {})

            # Count total unique news
            total_news = len(seen_news)

            # Count by category
            by_category: Dict[str, int] = {}
            for entry in seen_news.values():
                cat = entry.get("feed_category")
                if cat:
                    by_category[cat] = by_category.get(cat, 0) + 1

            # Last processed
            last_processed = None
            if seen_news:
                last_processed = max(
                    (entry.get("last_processed") for entry in seen_news.values()),
                    default=None,
                )

            # Total processing events
            total_processing = sum(entry.get("server_count", 0) for entry in seen_news.values())

            return {
                "total_unique_news": total_news,
                "by_category": by_category,
                "last_processed": last_processed,
                "total_processing_events": total_processing,
            }
        except Exception as e:
            logger.exception(f"Error getting global news stats: {e}")
            return {
                "total_unique_news": 0,
                "by_category": {},
                "last_processed": None,
                "total_processing_events": 0,
            }

    def _cleanup_old_news(self, seen_news: Dict[str, Dict], days_to_keep: int = 30) -> Dict[str, Dict]:
        """Remove news entries older than days_to_keep."""
        try:
            cutoff = datetime.now() - timedelta(days=days_to_keep)
            cleaned = {}
            for title_hash, entry in seen_news.items():
                try:
                    first_seen = datetime.fromisoformat(entry.get("first_seen", ""))
                    if first_seen >= cutoff:
                        cleaned[title_hash] = entry
                except ValueError:
                    # Keep entries with invalid dates
                    cleaned[title_hash] = entry

            removed = len(seen_news) - len(cleaned)
            if removed > 0:
                logger.info(f"🧹 Cleaned up {removed} old global news entries (older than {days_to_keep} days)")

            return cleaned
        except Exception as e:
            logger.exception(f"Error cleaning up old news: {e}")
            return seen_news

    def cleanup_old_news(self, days_to_keep: int = 30) -> int:
        """Clean up old news entries to prevent database bloat."""
        try:
            def updater(state: Dict[str, Dict]) -> Dict[str, Dict]:
                seen_news = state.get("seen_news", {})
                cleaned = self._cleanup_old_news(seen_news, days_to_keep)
                state["seen_news"] = cleaned
                return state

            old_state = self._store.load()
            old_count = len(old_state.get("seen_news", {}))
            self._store.update(updater)
            new_state = self._store.load()
            new_count = len(new_state.get("seen_news", {}))

            removed = old_count - new_count
            logger.info(f"🧹 Cleaned up {removed} old global news entries (older than {days_to_keep} days)")
            return removed
        except Exception as e:
            logger.exception(f"Error cleaning up old global news: {e}")
            return 0

    # --- Feed Tracking ---

    def update_feed_last_updated(
        self,
        feed_url: str,
        feed_name: Optional[str] = None,
        feed_category: Optional[str] = None,
    ) -> bool:
        """Update the last updated timestamp for a feed."""
        try:
            current_date = datetime.now().isoformat()

            def updater(state: Dict[str, Dict]) -> Dict[str, Dict]:
                feed_updates = state.get("feed_last_updated", {})
                feed_updates[feed_url] = {
                    "last_updated": current_date,
                    "feed_name": feed_name,
                    "feed_category": feed_category,
                }
                state["feed_last_updated"] = feed_updates
                return state

            self._store.update(updater)
            logger.debug(f"Updated feed_last_updated for {feed_name or feed_url}")
            return True
        except Exception as e:
            logger.exception(f"Error updating feed_last_updated: {e}")
            return False

    def get_feed_last_updated(self, feed_url: str) -> Optional[str]:
        """Get the last updated timestamp for a feed."""
        try:
            state = self._store.load()
            feed_updates = state.get("feed_last_updated", {})
            entry = feed_updates.get(feed_url)
            return entry.get("last_updated") if entry else None
        except Exception as e:
            logger.exception(f"Error getting feed_last_updated: {e}")
            return None

    def should_update_feed(self, feed_url: str, interval_hours: int = 1) -> bool:
        """Check if a feed should be updated based on its last update time and the configured interval."""
        try:
            last_updated = self.get_feed_last_updated(feed_url)
            if not last_updated:
                return True  # Never updated, should update

            last_updated_dt = datetime.fromisoformat(last_updated)
            time_since_update = datetime.now() - last_updated_dt

            return time_since_update.total_seconds() >= (interval_hours * 3600)
        except Exception as e:
            logger.exception(f"Error checking if feed should update: {e}")
            return True  # On error, allow update


# Global instance
_global_news_nosql_instance: Optional[GlobalNewsNoSQL] = None


def get_global_news_nosql() -> GlobalNewsNoSQL:
    """Get or create the global news NoSQL instance."""
    global _global_news_nosql_instance
    if _global_news_nosql_instance is None:
        _global_news_nosql_instance = GlobalNewsNoSQL()
    return _global_news_nosql_instance
