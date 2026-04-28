"""Subscription Limit System for News Watcher.

This module provides subscription limit tracking and enforcement
to prevent abuse and manage resources effectively.
Similar to fatigue limits but for news subscriptions.

Storage: databases/news_watcher/global_subscription_limits.json (NoSQL)
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from persistence.json_store import JsonStore
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
    """Global subscription limit tracker across all servers (NoSQL-backed)."""
    
    def __init__(self, store_path: Path = None):
        if store_path is None:
            base_dir = Path(__file__).parent.parent.parent
            news_watcher_dir = base_dir / "databases" / "news_watcher"
            news_watcher_dir.mkdir(parents=True, exist_ok=True)
            store_path = news_watcher_dir / "global_subscription_limits.json"

        self._store = JsonStore(
            store_path,
            default_factory=lambda: {},
            keep_backup=False,
        )
        self._lock = asyncio.Lock()
        logger.info(f"✅ Global subscription limits ready at {store_path}")
    
    async def get_user_subscription_count(self, user_id: str) -> int:
        """Get total subscription count for a user across all servers."""
        try:
            state = self._store.load()
            entry = state.get(str(user_id))
            if entry is None:
                return 0
            return entry.get("subscription_count", 0)
        except Exception as e:
            logger.exception(f"Error getting user subscription count: {e}")
            return 0
    
    def _set_count(self, user_id: str, count: int):
        """Internal: persist count for user_id."""
        now = datetime.now().isoformat()
        def updater(state: Dict) -> Dict:
            state[str(user_id)] = {
                "subscription_count": count,
                "last_updated": now,
            }
            return state
        self._store.update(updater)

    async def increment_user_subscription_count(self, user_id: str) -> bool:
        """Increment subscription count for a user."""
        try:
            async with self._lock:
                current = await self.get_user_subscription_count(user_id)
                new_count = current + 1
                self._set_count(user_id, new_count)
                logger.debug(f"Incremented subscription count for user {user_id}: {current} -> {new_count}")
                return True
        except Exception as e:
            logger.exception(f"Error incrementing user subscription count: {e}")
            return False
    
    async def decrement_user_subscription_count(self, user_id: str) -> bool:
        """Decrement subscription count for a user."""
        try:
            async with self._lock:
                current = await self.get_user_subscription_count(user_id)
                new_count = max(0, current - 1)
                self._set_count(user_id, new_count)
                logger.debug(f"Decremented subscription count for user {user_id}: {current} -> {new_count}")
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
                    if db:
                        # Count all subscriptions for this user (both DM and channel)
                        subscriptions = db.get_all_active_subscriptions()
                        user_subs = [s for s in subscriptions if s[1] == user_id]  # s[1] is user_id
                        total_count += len(user_subs)
                except Exception as e:
                    logger.warning(f"Error counting subscriptions for server {server_id}: {e}")
            
            # Update the global count
            async with self._lock:
                self._set_count(user_id, total_count)
            
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
