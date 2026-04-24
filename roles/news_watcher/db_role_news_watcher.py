import json
import sqlite3
import threading
import os
import stat
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

from agent_db import get_server_db_path_fallback, get_personality_name

def get_db_path(server_id: str = "default") -> Optional[Path]:
    """Generate database path for news watcher using roles_<personality>.db.
    
    Returns None if personality cannot be determined to avoid creating
    placeholder databases in server directories.
    """
    personality_name = get_personality_name(server_id)
    
    # Don't create database if personality cannot be determined
    if not personality_name:
        logger.debug(f"[get_db_path] Cannot determine personality for server {server_id}, skipping database creation")
        return None
    
    # Use roles_<personality>.db instead of watcher_<personality>.db
    db_name = f"roles_{personality_name}"
    return get_server_db_path_fallback(server_id, db_name)


class DatabaseRoleNewsWatcher:
    """Specialized database for News Watcher.
    Manages read news and sent notifications.
    """
    
    def __init__(self, server_id: str = "default", db_path: Path = None):
        self.server_id = server_id
        if db_path is None:
            self.db_path = get_db_path(server_id)
            # Don't initialize if db_path is None (personality not found)
            if not self.db_path:
                logger.debug(f"[DatabaseRoleNewsWatcher] Cannot determine database path for server {server_id}, skipping initialization")
                return
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_writable_db()
        self._init_db()
    
    def _ensure_writable_db(self):
        """Check that DB is accessible and force correct permissions."""
        try:
            # Ensure directory exists with correct permissions
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._fix_permissions(self.db_path.parent)
            
            # Connect and force file permissions
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=DELETE;')
            conn.close()
            
            # Force DB file permissions
            self._fix_permissions(self.db_path)
            
        except Exception as e:
            logger.error(f"Cannot access database at {self.db_path}: {e}")
            raise
    
    def _fix_permissions(self, path: Path):
        """Force current user/group permissions on file/directory."""
        try:
            if path.exists():
                # Get current uid/gid
                uid = os.getuid()
                gid = os.getgid()
                
                # Change owner
                os.chown(path, uid, gid)
                
                # Permissions: 664 for files, 775 for directories
                if path.is_file():
                    current_mode = path.stat().st_mode
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP
                    os.chmod(path, new_mode)
                elif path.is_dir():
                    current_mode = path.stat().st_mode  
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP | stat.S_IXUSR | stat.S_IXGRP
                    os.chmod(path, new_mode)
                    
                logger.debug(f"Fixed permissions for {path}: uid={uid}, gid={gid}")
        except Exception as e:
            logger.warning(f"Could not fix permissions for {path}: {e}")
    
    def _init_db(self):
        """Initialize database with DELETE configuration."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=DELETE;")
                conn.commit()
                
                # Initialize only the subscriptions table (legacy tables removed)
                # The watcher_subscriptions table is now in roles_<personality>.db
                # No need to initialize it here - it's initialized in agent_roles_db.py
                
                logger.info(f"✅ News watcher database ready at {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error initializing news watcher database: {e}")
    
    
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
    











# ===== UNIFIED SUBSCRIPTIONS MANAGEMENT =====
    
    async def create_subscription(self, user_id: str = None, channel_id: str = None, 
                          category: str = None, feed_id: int = None,
                          premises: str = None, keywords: str = None,
                          method: str = 'general', created_by: str = None, 
                          increment_global_count: bool = True) -> int:
        """Create a new subscription with unified structure.
        
        Args:
            increment_global_count: If True (default), increment global subscription count.
                                    Set to False if the caller already handles this (e.g., wizard).
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO watcher_subscriptions 
                    (user_id, channel_id, category, feed_id, premises, keywords, method, is_active, subscribed_at, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), ?)
                ''', (user_id, channel_id, category, feed_id, premises, keywords, method, created_by))
                subscription_id = cursor.lastrowid
                
                # Increment global count if requested and user_id is provided
                if subscription_id and increment_global_count and user_id:
                    try:
                        from roles.news_watcher.subscription_limits import increment_user_subscription_count
                        await increment_user_subscription_count(user_id)
                    except Exception as e:
                        logger.warning(f"Error incrementing global subscription count: {e}")
                
                return subscription_id
        except Exception as e:
            logger.exception(f"Error creating subscription: {e}")
            return None
    
    def get_all_active_subscriptions(self) -> list:
        """Get all active subscriptions (unified method)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by
                    FROM watcher_subscriptions 
                    WHERE is_active = 1
                    ORDER BY subscribed_at DESC
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all subscriptions: {e}")
            return []
    
    def get_user_subscriptions(self, user_id: str) -> list:
        """Get all active subscriptions for a specific user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by
                    FROM watcher_subscriptions 
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY subscribed_at DESC
                ''', (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting user subscriptions: {e}")
            return []
    
    def get_channel_subscriptions(self, channel_id: str) -> list:
        """Get all active subscriptions for a specific channel."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by
                    FROM watcher_subscriptions 
                    WHERE channel_id = ? AND is_active = 1
                    ORDER BY subscribed_at DESC
                ''', (channel_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting channel subscriptions: {e}")
            return []

    def get_users_with_active_subscriptions(self) -> list:
        """Get all users who have active personal subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT user_id 
                    FROM watcher_subscriptions 
                    WHERE user_id IS NOT NULL AND channel_id IS NULL AND is_active = 1
                ''')
                results = cursor.fetchall()
                return [row[0] for row in results]
        except Exception as e:
            logger.exception(f"Error getting users with active subscriptions: {e}")
            return []

    def update_subscription(self, subscription_id: int, **kwargs) -> bool:
        """Update subscription fields."""
        try:
            if not kwargs:
                return False
                
            # Build dynamic update query
            set_clauses = []
            values = []
            
            for key, value in kwargs.items():
                if key in ['category', 'feed_id', 'premises', 'keywords', 'method', 'is_active']:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
            
            if not set_clauses:
                return False
                
            values.append(subscription_id)
            
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    UPDATE watcher_subscriptions 
                    SET {', '.join(set_clauses)}
                    WHERE id = ?
                ''', (*values, subscription_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error updating subscription: {e}")
            return False
    
    async def delete_subscription(self, subscription_id: int) -> bool:
        """Delete a subscription (soft delete by setting is_active=0)."""
        # Get user_id before deleting to update global count
        user_id = None
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM watcher_subscriptions WHERE id = ?', (subscription_id,))
                result = cursor.fetchone()
                if result:
                    user_id = result[0]
        except Exception as e:
            logger.warning(f"Error getting user_id before deleting subscription: {e}")
        
        # Delete the subscription
        success = self.update_subscription(subscription_id, is_active=0)
        
        # Decrement global count if successful
        if success and user_id:
            try:
                from roles.news_watcher.subscription_limits import decrement_user_subscription_count
                await decrement_user_subscription_count(user_id)
            except Exception as e:
                logger.warning(f"Error decrementing global subscription count: {e}")
        
        return success
    
    def get_user_keyword_subscriptions(self, user_id: str) -> list:
        """Get all keyword subscriptions of a user (unified system)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT category, feed_id, keywords
                    FROM watcher_subscriptions 
                    WHERE user_id = ? AND is_active = 1 AND method = 'keyword'
                    ORDER BY category, feed_id
                ''', (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting keyword subscriptions: {e}")
            return []
    
    def cancel_user_keyword_subscription(self, user_id: str, category: str) -> bool:
        """Cancel user keyword subscription for a category (unified system)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE watcher_subscriptions 
                    SET is_active = 0
                    WHERE user_id = ? AND category = ? AND is_active = 1 AND method = 'keyword'
                ''', (user_id, category))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error canceling user keyword subscription: {e}")
            return False
    
    def get_user_keywords(self, user_id: str) -> str:
        """Get keywords from user's keyword subscriptions (unified system)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT keywords FROM watcher_subscriptions 
                    WHERE user_id = ? AND is_active = 1 AND method = 'keyword'
                    LIMIT 1
                ''', (user_id,))
                result = cursor.fetchone()
                return result[0] if result and result[0] else None
        except Exception as e:
            logger.exception(f"Error getting user keywords: {e}")
            return None
    
    def update_user_keywords(self, user_id: str, keywords: str) -> bool:
        """Update keywords in user's keyword subscriptions (unified system)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                if keywords:
                    # Update existing keyword subscription or create new one
                    cursor.execute('''
                        UPDATE watcher_subscriptions 
                        SET keywords = ?
                        WHERE user_id = ? AND is_active = 1 AND method = 'keyword'
                    ''', (keywords, user_id))
                    
                    if cursor.rowcount == 0:
                        # No existing keyword subscription, create one with default category
                        cursor.execute('''
                            INSERT INTO watcher_subscriptions 
                            (user_id, category, keywords, method, is_active, last_processed_at, created_at)
                            VALUES (?, ?, ?, 'keyword', 1, datetime('now'), datetime('now'))
                        ''', (user_id, 'general', keywords))
                else:
                    # Remove keywords from keyword subscriptions
                    cursor.execute('''
                        UPDATE watcher_subscriptions 
                        SET keywords = NULL
                        WHERE user_id = ? AND is_active = 1 AND method = 'keyword'
                    ''', (user_id,))
                
                conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error updating user keywords: {e}")
            return False


    def get_premises_with_context(self, user_id: str) -> tuple:
        """Get user premises with context.
        
        Args:
            user_id: User ID
            
        Returns:
            Tuple of (premises_list, context_string)
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT premises, context
                    FROM watcher_premises
                    WHERE user_id = ?
                    ORDER BY id
                ''', (user_id,))
                rows = cursor.fetchall()
                
                premises = [row[0] for row in rows if row[0]]
                contexts = [row[1] for row in rows if row[1]]
                context = contexts[0] if contexts else None
                
                return premises, context
        except Exception as e:
            logger.exception(f"Error getting premises with context: {e}")
            return [], None


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
    
    Returns None if personality cannot be determined.
    """
    # Generate the current database path for this server
    current_db_path = get_db_path(server_id)
    if not current_db_path:
        logger.debug(f"[get_news_watcher_db_instance] Cannot determine database path for server {server_id}")
        return None
    
    cache_key = f"{server_id}:{current_db_path}"
    
    # Check if we have a cached instance with the same database path
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
