import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple
from agent_logging import get_logger

try:
    logger = get_logger('db_role_news_watcher')
except Exception:
    import logging
    # logging.basicConfig removed - using centralized logging
    logger = logging.getLogger('db_role_news_watcher')

from agent_db import get_personality_name


class DatabaseRoleNewsWatcher:
    """Specialized database for News Watcher.
    Manages read news and sent notifications.
    """
    
    def __init__(self, server_id: str = "default", db_path: Path = None):
        self.server_id = server_id
        self.db_path = None  # No longer uses SQLite
        self._lock = threading.Lock()
        self._nosql_cache = None
        # No longer initializes SQLite - fully NoSQL-backed

    @property
    def _nosql(self):
        """Lazy accessor for the NoSQL role-configs facade (per server)."""
        if self._nosql_cache is None:
            from roles.role_configs_nosql import get_role_configs_nosql
            self._nosql_cache = get_role_configs_nosql(self.server_id)
        return self._nosql_cache
    
    
    def subscribe_user_category_ai(self, user_id: str, category: str, feed_id: int = None, premises: str = None) -> bool:
        """Subscribe a user to a category with AI analysis using unified system."""
        try:
            # Use the unified create_subscription method
            result = self.create_subscription(
                user_id=user_id,
                channel_id=None,
                category=category.lower(),
                feed_id=feed_id,
                premises=premises,
                method="general",
                created_by=user_id
            )
            return result is not None
        except Exception as e:
            logger.exception(f"Error subscribing user to category with AI analysis: {e}")
            return False
    
    
    def subscribe_keywords(self, user_id: str, keywords: str, channel_id: str = None, category: str = None, feed_id: int = None) -> bool:
        """Subscribe user or channel to specific keywords (optionally in category/feed) using unified system."""
        try:
            # Require category for keyword subscriptions - no more global_keywords
            if category is None:
                logger.warning(f"subscribe_keywords called without category for user {user_id} - rejecting")
                return False
            
            # Use the unified create_subscription method
            result = self.create_subscription(
                user_id=user_id if not channel_id else None,
                channel_id=channel_id,
                category=category,
                feed_id=feed_id,
                keywords=keywords,
                method="keyword",
                created_by=user_id
            )
            return result is not None
        except Exception as e:
            logger.exception(f"Error subscribing keywords: {e}")
            return False
    
    
    def subscribe_channel_category_keywords(self, channel_id: str, channel_name: str, server_id: str, 
                                       category: str, feed_id: int = None, keywords: str = None, user_id: str = None) -> bool:
        """Subscribe a channel to keywords in a specific category or feed."""
        try:
            # Use the unified create_subscription method
            result = self.create_subscription(
                user_id=None,
                channel_id=channel_id,
                category=category,
                feed_id=feed_id,
                keywords=keywords,
                method="keyword",
                created_by=user_id
            )
            return result is not None
        except Exception as e:
            logger.exception(f"Error subscribing channel to keywords: {e}")
            return False
    
    
    def _get_default_premises(self) -> list:
        """Get default premises from server-specific news_watcher.json file."""
        try:
            from roles.news_watcher.news_watcher import _get_news_watcher_descriptions
            descriptions = _get_news_watcher_descriptions(self.server_id)
            return descriptions.get("premises", [])
        except Exception as e:
            logger.error(f"Error getting default premises for server {self.server_id}: {e}")
            return []

    def _get_premises_limit(self) -> int:
        """Get the effective premises limit."""
        return max(3, len(self._get_default_premises()))
    











# ===== UNIFIED SUBSCRIPTIONS MANAGEMENT (NoSQL-backed) =====

    async def create_subscription(self, user_id: str = None, channel_id: str = None,
                          category: str = None, feed_id: int = None,
                          premises: str = None, keywords: str = None,
                          method: str = 'general', created_by: str = None,
                          increment_global_count: bool = True) -> int:
        """Create a new subscription with unified structure (NoSQL-backed).

        Args:
            increment_global_count: If True (default), increment global subscription count.
                                    Set to False if the caller already handles this (e.g., wizard).
        """
        try:
            ok = self._nosql.save_watcher_subscription(
                user_id=user_id,
                channel_id=channel_id,
                category=category,
                feed_id=feed_id,
                premises=premises,
                keywords=keywords,
                method=method,
                is_active=True,
                created_by=created_by,
            )
            if not ok:
                return None

            # Increment global count if requested and user_id is provided
            if increment_global_count and user_id:
                try:
                    from roles.news_watcher.subscription_limits import increment_user_subscription_count
                    await increment_user_subscription_count(user_id)
                except Exception as e:
                    logger.warning(f"Error incrementing global subscription count: {e}")

            return True  # Success indicator
        except Exception as e:
            logger.exception(f"Error creating subscription: {e}")
            return None

    def get_all_active_subscriptions(self) -> list:
        """Get all active subscriptions (NoSQL-backed). Returns list of tuples for compatibility."""
        try:
            subs = self._nosql.get_watcher_subscriptions()
            # Filter is_active and convert to legacy tuple format
            active = [s for s in subs if s.get("is_active", True)]
            # Sort by subscribed_at DESC
            active.sort(key=lambda x: x.get("subscribed_at", ""), reverse=True)
            # Return as tuples: (id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by)
            # NoSQL doesn't have numeric IDs, use placeholder
            return [
                (
                    0,  # placeholder id
                    s.get("user_id"),
                    s.get("channel_id"),
                    s.get("category"),
                    s.get("feed_id"),
                    s.get("premises"),
                    s.get("keywords"),
                    s.get("method"),
                    s.get("subscribed_at"),
                    s.get("created_by"),
                )
                for s in active
            ]
        except Exception as e:
            logger.exception(f"Error getting all subscriptions: {e}")
            return []

    def get_user_subscriptions(self, user_id: str) -> list:
        """Get all active subscriptions for a specific user (NoSQL-backed)."""
        try:
            subs = self._nosql.get_watcher_subscriptions(user_id=user_id)
            active = [s for s in subs if s.get("is_active", True)]
            active.sort(key=lambda x: x.get("subscribed_at", ""), reverse=True)
            return [
                (
                    0,
                    s.get("user_id"),
                    s.get("channel_id"),
                    s.get("category"),
                    s.get("feed_id"),
                    s.get("premises"),
                    s.get("keywords"),
                    s.get("method"),
                    s.get("subscribed_at"),
                    s.get("created_by"),
                )
                for s in active
            ]
        except Exception as e:
            logger.exception(f"Error getting user subscriptions: {e}")
            return []

    def get_channel_subscriptions(self, channel_id: str) -> list:
        """Get all active subscriptions for a specific channel (NoSQL-backed)."""
        try:
            subs = self._nosql.get_watcher_subscriptions(channel_id=channel_id)
            active = [s for s in subs if s.get("is_active", True)]
            active.sort(key=lambda x: x.get("subscribed_at", ""), reverse=True)
            return [
                (
                    0,
                    s.get("user_id"),
                    s.get("channel_id"),
                    s.get("category"),
                    s.get("feed_id"),
                    s.get("premises"),
                    s.get("keywords"),
                    s.get("method"),
                    s.get("subscribed_at"),
                    s.get("created_by"),
                )
                for s in active
            ]
        except Exception as e:
            logger.exception(f"Error getting channel subscriptions: {e}")
            return []

    def get_users_with_active_subscriptions(self) -> list:
        """Get all users who have active personal subscriptions (NoSQL-backed)."""
        try:
            # NoSQL helper returns user_ids directly
            return self._nosql.get_watcher_users_with_active_subscriptions()
        except Exception as e:
            logger.exception(f"Error getting users with active subscriptions: {e}")
            return []

    def update_subscription(self, subscription_id: int, **kwargs) -> bool:
        """Update subscription fields (NoSQL-backed).

        Note: subscription_id is ignored in NoSQL (no numeric IDs).
        Updates are performed by re-saving with new values.
        """
        try:
            if not kwargs:
                return False

            # NoSQL doesn't have numeric IDs, so we can't update by ID directly.
            # For now, this is a no-op - the caller should use delete + create.
            # This method is rarely used in practice.
            logger.warning(f"update_subscription called with ID {subscription_id} - not supported in NoSQL mode")
            return False
        except Exception as e:
            logger.exception(f"Error updating subscription: {e}")
            return False

    async def delete_subscription(self, subscription_id: int) -> bool:
        """Delete a subscription (soft delete by setting is_active=0) (NoSQL-backed).

        Note: subscription_id is ignored. This method requires user_id/channel_id/category
        to be passed via kwargs or retrieved from context. For now, this is a no-op.
        """
        # NoSQL doesn't have numeric IDs, so we can't delete by ID directly.
        # The caller should use delete_watcher_subscription(user_id, channel_id, category) instead.
        logger.warning(f"delete_subscription called with ID {subscription_id} - not supported in NoSQL mode")
        return False

    def get_user_keyword_subscriptions(self, user_id: str) -> list:
        """Get all keyword subscriptions of a user (NoSQL-backed)."""
        try:
            subs = self._nosql.get_watcher_subscriptions(user_id=user_id)
            keyword_subs = [s for s in subs if s.get("method") == "keyword" and s.get("is_active", True)]
            keyword_subs.sort(key=lambda x: (x.get("category", ""), x.get("feed_id") or 0))
            return [(s.get("category"), s.get("feed_id"), s.get("keywords")) for s in keyword_subs]
        except Exception as e:
            logger.exception(f"Error getting keyword subscriptions: {e}")
            return []

    def cancel_user_keyword_subscription(self, user_id: str, category: str) -> bool:
        """Cancel user keyword subscription for a category (NoSQL-backed)."""
        try:
            # Find the channel_id for this user's keyword subscription in this category
            subs = self._nosql.get_watcher_subscriptions(user_id=user_id)
            for s in subs:
                if s.get("category") == category and s.get("method") == "keyword":
                    ch_id = s.get("channel_id")
                    if ch_id:
                        return self._nosql.soft_delete_watcher_subscription(user_id, ch_id, category)
            return False
        except Exception as e:
            logger.exception(f"Error canceling user keyword subscription: {e}")
            return False

    def get_user_keywords(self, user_id: str) -> str:
        """Get keywords from user's keyword subscriptions (NoSQL-backed)."""
        try:
            subs = self._nosql.get_watcher_subscriptions(user_id=user_id)
            keyword_subs = [s for s in subs if s.get("method") == "keyword" and s.get("is_active", True)]
            if keyword_subs:
                return keyword_subs[0].get("keywords")
            return None
        except Exception as e:
            logger.exception(f"Error getting user keywords: {e}")
            return None

    def update_user_keywords(self, user_id: str, keywords: str) -> bool:
        """Update keywords in user's keyword subscriptions (NoSQL-backed)."""
        try:
            subs = self._nosql.get_watcher_subscriptions(user_id=user_id)
            keyword_subs = [s for s in subs if s.get("method") == "keyword" and s.get("is_active", True)]

            if keywords:
                if keyword_subs:
                    # Update existing
                    for s in keyword_subs:
                        self._nosql.save_watcher_subscription(
                            user_id=user_id,
                            channel_id=s.get("channel_id"),
                            category=s.get("category"),
                            feed_id=s.get("feed_id"),
                            premises=s.get("premises"),
                            keywords=keywords,
                            method="keyword",
                            is_active=True,
                            created_by=s.get("created_by"),
                        )
                else:
                    # Create new with default category
                    self._nosql.save_watcher_subscription(
                        user_id=user_id,
                        channel_id=None,
                        category="general",
                        keywords=keywords,
                        method="keyword",
                        is_active=True,
                    )
            else:
                # Remove keywords from existing subscriptions
                for s in keyword_subs:
                    self._nosql.save_watcher_subscription(
                        user_id=user_id,
                        channel_id=s.get("channel_id"),
                        category=s.get("category"),
                        feed_id=s.get("feed_id"),
                        premises=s.get("premises"),
                        keywords=None,
                        method="keyword",
                        is_active=True,
                        created_by=s.get("created_by"),
                    )
            return True
        except Exception as e:
            logger.exception(f"Error updating user keywords: {e}")
            return False


    def get_premises_with_context(self, user_id: str) -> tuple:
        """Get user premises with context (NoSQL-backed).

        Args:
            user_id: User ID

        Returns:
            Tuple of (premises_list, context_string)
        """
        try:
            return self._nosql.get_watcher_premises(user_id)
        except Exception as e:
            logger.exception(f"Error getting premises with context: {e}")
            return [], None

    def add_user_premise(self, user_id: str, premise: str) -> tuple:
        """Add a premise for a user (NoSQL-backed). Returns (success, message)."""
        try:
            max_premises = self._get_premises_limit()
            return self._nosql.add_watcher_premise(user_id, premise, max_premises)
        except Exception as e:
            logger.exception(f"Error adding user premise: {e}")
            return False, str(e)

    def modify_user_premise(self, user_id: str, index: int, new_premise: str) -> tuple:
        """Modify a premise by 1-based index (NoSQL-backed). Returns (success, message)."""
        try:
            return self._nosql.modify_watcher_premise(user_id, index, new_premise)
        except Exception as e:
            logger.exception(f"Error modifying user premise: {e}")
            return False, str(e)

    def delete_user_premise(self, user_id: str, index: int) -> tuple:
        """Delete a premise by 1-based index (NoSQL-backed). Returns (success, message)."""
        try:
            return self._nosql.delete_watcher_premise(user_id, index)
        except Exception as e:
            logger.exception(f"Error deleting user premise: {e}")
            return False, str(e)


    def get_available_categories(self) -> list:
        """Get available categories with feed counts.
        
        Returns:
            List of tuples (category, feed_count)
        """
        try:
            from roles.news_watcher.global_feed_health import get_healthy_feeds
            healthy_feeds = get_healthy_feeds()
            
            # Count feeds by category
            category_counts = {}
            for feed_id, feed_name, feed_url, category in healthy_feeds:
                if category:
                    category_counts[category] = category_counts.get(category, 0) + 1
            
            # Return as list of tuples
            return [(category, count) for category, count in category_counts.items()]
        except Exception as e:
            logger.exception(f"Error getting available categories: {e}")
            return []


# Dictionary to maintain instances per server
_db_news_watcher_instances = {}

def get_news_watcher_db_instance(server_id: str = "default") -> Optional[DatabaseRoleNewsWatcher]:
    """Get or create a news watcher database instance for a specific server.
    
    Returns None if server_id is not valid.
    """
    # Don't create database without valid server_id
    if not server_id or server_id == "default":
        logger.debug("[get_news_watcher_db_instance] Called without valid server_id - skipping database creation")
        return None
    
    # Use server_id as cache key (NoSQL-backed, no personality-specific paths)
    cache_key = server_id
    
    # Check if we have a cached instance for this server
    if cache_key not in _db_news_watcher_instances:
        _db_news_watcher_instances[cache_key] = DatabaseRoleNewsWatcher(server_id)
    
    return _db_news_watcher_instances[cache_key]

def invalidate_news_watcher_db_instance(server_id: str = None):
    """Invalidate cached news watcher database instance for a server or all servers."""
    global _db_news_watcher_instances
    if server_id:
        # Invalidate all instances for this server (any personality)
        keys_to_remove = [k for k in _db_news_watcher_instances.keys() if k.startswith(f"{server_id}:")]
        for key in keys_to_remove:
            del _db_news_watcher_instances[key]
            logger.info(f"🗄️ [NEWS_WATCHER] Invalidated cached db instance for server: {server_id}")
    else:
        # Invalidate all instances
        _db_news_watcher_instances.clear()
        logger.info("🗄️ [NEWS_WATCHER] Invalidated all cached db instances")
