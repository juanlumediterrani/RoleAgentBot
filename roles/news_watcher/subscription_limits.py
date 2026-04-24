"""Subscription Limit System for News Watcher.

This module provides subscription limit tracking and enforcement
to prevent abuse and manage resources effectively.
Similar to fatigue limits but for news subscriptions.
"""

import sqlite3
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict
from agent_logging import get_logger

logger = get_logger('subscription_limits')


class SubscriptionLimitResult:
    """Result of subscription limit check."""
    def __init__(self, allowed: bool, reason: str = None, current_count: int = 0, limit: int = 5):
        self.allowed = allowed
        self.reason = reason
        self.current_count = current_count
        self.limit = limit


def get_subscription_limits_config() -> Dict:
    """Get subscription limits from agent_config.json."""
    try:
        import json
        import os
        
        _BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        _AGENT_CONFIG_PATH = os.path.join(_BASE_DIR, "agent_config.json")
        
        with open(_AGENT_CONFIG_PATH, encoding="utf-8") as file_handle:
            config = json.load(file_handle)
        
        news_watcher_config = config.get('roles', {}).get('news_watcher', {})
        return news_watcher_config.get('subscription_limits', {
            'max_per_user': 5,
            'exemptions': {'admin_users': []}
        })
    except Exception as e:
        logger.warning(f"Error loading subscription limits config: {e}")
        # Return default limits
        return {
            'max_per_user': 5,
            'exemptions': {'admin_users': []}
        }


class GlobalSubscriptionLimits:
    """Global subscription limit tracker across all servers."""
    
    def __init__(self, db_path: Path = None):
        if db_path is None:
            # Use a global database in the databases/news_watcher directory
            base_dir = Path(__file__).parent.parent.parent
            news_watcher_db_dir = base_dir / "databases" / "news_watcher"
            news_watcher_db_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = news_watcher_db_dir / "global_subscription_limits.db"
        else:
            self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize global subscription limits database."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('PRAGMA journal_mode=DELETE;')
                conn.commit()
                
                # Initialize subscription count table
                self._init_subscription_count_table()
                
                logger.info(f"✅ Global subscription limits database ready at {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error initializing global subscription limits database: {e}")
    
    def _init_subscription_count_table(self):
        """Initialize subscription count tracking table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_subscription_counts (
                        user_id TEXT PRIMARY KEY,
                        subscription_count INTEGER DEFAULT 0,
                        last_updated TEXT NOT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_subscription_user ON user_subscription_counts (user_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating user_subscription_counts table: {e}")
    
    async def get_user_subscription_count(self, user_id: str) -> int:
        """Get total subscription count for a user across all servers."""
        try:
            async with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT subscription_count FROM user_subscription_counts WHERE user_id = ?', (user_id,))
                    result = cursor.fetchone()
                    return result[0] if result else 0
        except Exception as e:
            logger.exception(f"Error getting user subscription count: {e}")
            return 0
    
    async def increment_user_subscription_count(self, user_id: str) -> bool:
        """Increment subscription count for a user."""
        try:
            async with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    current_count = await self.get_user_subscription_count(user_id)
                    new_count = current_count + 1
                    current_date = datetime.now().isoformat()
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO user_subscription_counts 
                        (user_id, subscription_count, last_updated)
                        VALUES (?, ?, ?)
                    ''', (user_id, new_count, current_date))
                    conn.commit()
                    logger.debug(f"Incremented subscription count for user {user_id}: {current_count} -> {new_count}")
                    return True
        except Exception as e:
            logger.exception(f"Error incrementing user subscription count: {e}")
            return False
    
    async def decrement_user_subscription_count(self, user_id: str) -> bool:
        """Decrement subscription count for a user."""
        try:
            async with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    current_count = await self.get_user_subscription_count(user_id)
                    new_count = max(0, current_count - 1)
                    current_date = datetime.now().isoformat()
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO user_subscription_counts 
                        (user_id, subscription_count, last_updated)
                        VALUES (?, ?, ?)
                    ''', (user_id, new_count, current_date))
                    conn.commit()
                    logger.debug(f"Decremented subscription count for user {user_id}: {current_count} -> {new_count}")
                    return True
        except Exception as e:
            logger.exception(f"Error decrementing user subscription count: {e}")
            return False
    
    async def recalculate_user_subscription_count(self, user_id: str) -> int:
        """Recalculate subscription count from all server databases."""
        try:
            from agent_db import get_all_server_ids
            from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
            
            total_count = 0
            server_ids = get_all_server_ids()
            
            for server_id in server_ids:
                try:
                    db = get_news_watcher_db_instance(server_id)
                    if db and db.db_path.exists():
                        # Count all subscriptions for this user (both DM and channel)
                        subscriptions = db.get_all_active_subscriptions()
                        user_subs = [s for s in subscriptions if s[1] == user_id]  # s[1] is user_id
                        total_count += len(user_subs)
                except Exception as e:
                    logger.warning(f"Error counting subscriptions for server {server_id}: {e}")
            
            # Update the global count
            async with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    current_date = datetime.now().isoformat()
                    cursor.execute('''
                        INSERT OR REPLACE INTO user_subscription_counts 
                        (user_id, subscription_count, last_updated)
                        VALUES (?, ?, ?)
                    ''', (user_id, total_count, current_date))
                    conn.commit()
            
            logger.info(f"Recalculated subscription count for user {user_id}: {total_count}")
            return total_count
            
        except Exception as e:
            logger.exception(f"Error recalculating user subscription count: {e}")
            return 0
    
    async def check_subscription_limit(self, user_id: str, is_admin: bool = False) -> SubscriptionLimitResult:
        """Check if user can create another subscription."""
        try:
            config = get_subscription_limits_config()
            limit = config.get('max_per_user', 5)
            exemptions = config.get('exemptions', {}).get('admin_users', [])
            
            # Check if user is in configured exemptions list (not server admin)
            if str(user_id) in exemptions:
                logger.debug(f"User {user_id} is in exemptions list, exempt from subscription limits")
                current_count = await self.get_user_subscription_count(user_id)
                return SubscriptionLimitResult(allowed=True, reason="User exempt from limits", current_count=current_count, limit=limit)
            
            # Check premium guild exemption (SKU purchased)
            try:
                from discord_bot.entitlement_manager import get_entitlement_manager
                entitlement_mgr = get_entitlement_manager()
                if entitlement_mgr:
                    has_premium = await entitlement_mgr.has_premium_guild(int(user_id))
                    if has_premium:
                        logger.debug(f"User {user_id} has premium guild (SKU), exempt from limits")
                        current_count = await self.get_user_subscription_count(user_id)
                        return SubscriptionLimitResult(allowed=True, reason="Premium guild (SKU) exempt from limits", current_count=current_count, limit=limit)
            except Exception as e:
                logger.debug(f"Could not check premium status: {e}")
            
            # Get current count
            current_count = await self.get_user_subscription_count(user_id)
            
            # Recalculate if needed (first time or stale)
            if current_count == 0:
                current_count = await self.recalculate_user_subscription_count(user_id)
            
            # Check limit
            if current_count >= limit:
                return SubscriptionLimitResult(
                    allowed=False,
                    reason=f"You have reached the maximum of {limit} subscriptions. Please unsubscribe from one before creating a new one.",
                    current_count=current_count,
                    limit=limit
                )
            
            return SubscriptionLimitResult(
                allowed=True,
                reason=f"You have {current_count}/{limit} subscriptions used.",
                current_count=current_count,
                limit=limit
            )
            
        except Exception as e:
            logger.exception(f"Error checking subscription limit: {e}")
            # Allow by default on error to not block legitimate users
            return SubscriptionLimitResult(allowed=True, reason="Error checking limits, allowing by default")


# Global instance
_global_subscription_limits_instance: Optional[GlobalSubscriptionLimits] = None

def get_global_subscription_limits() -> GlobalSubscriptionLimits:
    """Get or create the global subscription limits instance."""
    global _global_subscription_limits_instance
    if _global_subscription_limits_instance is None:
        _global_subscription_limits_instance = GlobalSubscriptionLimits()
    return _global_subscription_limits_instance


async def check_user_subscription_limit(user_id: str, is_admin: bool = False) -> SubscriptionLimitResult:
    """Check if user can create another subscription (convenience function)."""
    limits = get_global_subscription_limits()
    return await limits.check_subscription_limit(user_id, is_admin)


async def increment_user_subscription_count(user_id: str) -> bool:
    """Increment user's subscription count (convenience function)."""
    limits = get_global_subscription_limits()
    return await limits.increment_user_subscription_count(user_id)


async def decrement_user_subscription_count(user_id: str) -> bool:
    """Decrement user's subscription count (convenience function)."""
    limits = get_global_subscription_limits()
    return await limits.decrement_user_subscription_count(user_id)
