"""
Entitlement Manager for Discord Premium SKUs

This module handles Discord entitlement (subscription/consumable) management for premium features.
It provides functions to check user and guild entitlements for premium SKUs.
"""

import os
import logging
from typing import Optional, Dict, Any
import discord

logger = logging.getLogger(__name__)

# SKU IDs from environment variables for security
# These should be set in your environment or .env file
FATIGUE_RESET_SKU_ID = os.getenv('DISCORD_FATIGUE_RESET_SKU_ID')
PREMIUM_GUILD_SKU_ID = os.getenv('DISCORD_PREMIUM_GUILD_SKU_ID')

if not FATIGUE_RESET_SKU_ID:
    logger.warning("DISCORD_FATIGUE_RESET_SKU_ID not set - Fatigue Reset feature disabled")
if not PREMIUM_GUILD_SKU_ID:
    logger.warning("DISCORD_PREMIUM_GUILD_SKU_ID not set - premium guild features disabled")


class EntitlementManager:
    """Manages Discord entitlement checks for premium features"""
    
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._entitlement_cache: Dict[str, Dict[str, bool]] = {}
        
    async def check_user_entitlement(self, user_id: int, sku_id: str) -> bool:
        """
        Check if a user has a specific SKU entitlement.

        Args:
            user_id: Discord user ID
            sku_id: SKU ID to check

        Returns:
            True if user has the entitlement, False otherwise
        """
        if not sku_id:
            logger.warning("SKU ID not configured, cannot check entitlement")
            return False

        try:
            # Check cache first
            cache_key = f"user_{user_id}_{sku_id}"
            if cache_key in self._entitlement_cache:
                return self._entitlement_cache[cache_key]

            # Use HTTP API to check entitlements
            entitlements = await self.bot.http.get_entitlements(
                application_id=self.bot.application_id,
                user_id=str(user_id)
            )

            # Check if any entitlement matches the SKU ID
            # For consumables (type 2), check if it exists and is not consumed
            # For subscriptions (type 1), check if it's active
            for entitlement in entitlements:
                if entitlement.get('sku_id') == sku_id:
                    entitlement_type = entitlement.get('type')
                    ends_at = entitlement.get('ends_at')

                    # Consumable (type 2) - exists and not consumed
                    if entitlement_type == 2 and ends_at is None:
                        self._entitlement_cache[cache_key] = True
                        logger.info(f"User {user_id} has consumable entitlement for SKU {sku_id}")
                        return True
                    # Subscription (type 1) - active subscription
                    elif entitlement_type == 1 and ends_at is None:
                        self._entitlement_cache[cache_key] = True
                        logger.info(f"User {user_id} has subscription entitlement for SKU {sku_id}")
                        return True

            self._entitlement_cache[cache_key] = False
            return False

        except Exception as e:
            logger.error(f"Error checking user entitlement: {e}")
            return False
    
    async def check_guild_entitlement(self, guild_id: int, sku_id: str) -> bool:
        """
        Check if a guild has a specific SKU entitlement.
        
        Args:
            guild_id: Discord guild ID
            sku_id: SKU ID to check
            
        Returns:
            True if guild has the entitlement, False otherwise
        """
        if not sku_id:
            logger.warning("SKU ID not configured, cannot check entitlement")
            return False
            
        try:
            # Check cache first
            cache_key = f"guild_{guild_id}_{sku_id}"
            if cache_key in self._entitlement_cache:
                return self._entitlement_cache[cache_key]
            
            # Use HTTP API to check entitlements
            entitlements = await self.bot.http.get_entitlements(
                application_id=self.bot.application_id,
                guild_id=str(guild_id)
            )
            
            # Check if any entitlement matches the SKU ID and is active
            for entitlement in entitlements:
                if (entitlement.get('sku_id') == sku_id and 
                    entitlement.get('type') == 1 and  # 1 = Subscription
                    entitlement.get('ends_at') is None):  # Active subscription
                    self._entitlement_cache[cache_key] = True
                    logger.info(f"Guild {guild_id} has premium entitlement for SKU {sku_id}")
                    return True
            
            self._entitlement_cache[cache_key] = False
            return False
            
        except Exception as e:
            logger.error(f"Error checking guild entitlement: {e}")
            return False
    
    async def has_fatigue_reset(self, user_id: int) -> bool:
        """Check if user has Fatigue Reset consumable"""
        return await self.check_user_entitlement(user_id, FATIGUE_RESET_SKU_ID)

    async def consume_fatigue_reset(self, user_id: int, entitlement_id: str) -> bool:
        """
        Consume a Fatigue Reset consumable after use.

        Args:
            user_id: Discord user ID
            entitlement_id: The entitlement ID to consume

        Returns:
            True if consumption successful, False otherwise
        """
        if not FATIGUE_RESET_SKU_ID:
            logger.warning("FATIGUE_RESET_SKU_ID not configured, cannot consume")
            return False

        try:
            # Consume the entitlement via Discord API
            await self.bot.http.consume_entitlement(
                application_id=self.bot.application_id,
                entitlement_id=entitlement_id
            )

            # Clear cache for this user
            cache_key = f"user_{user_id}_{FATIGUE_RESET_SKU_ID}"
            if cache_key in self._entitlement_cache:
                del self._entitlement_cache[cache_key]

            logger.info(f"Consumed Fatigue Reset entitlement {entitlement_id} for user {user_id}")
            return True

        except Exception as e:
            logger.error(f"Error consuming Fatigue Reset entitlement: {e}")
            return False
    
    async def has_premium_guild(self, guild_id: int) -> bool:
        """Check if guild has Premium Server subscription"""
        return await self.check_guild_entitlement(guild_id, PREMIUM_GUILD_SKU_ID)
    
    async def has_any_premium(self, user_id: int, guild_id: Optional[int] = None) -> bool:
        """
        Check if user has Fatigue Reset OR guild has premium subscription.

        Args:
            user_id: Discord user ID
            guild_id: Optional Discord guild ID

        Returns:
            True if user has fatigue reset OR guild has premium guild
        """
        has_fatigue_reset = await self.has_fatigue_reset(user_id)

        if guild_id:
            has_guild_premium = await self.has_premium_guild(guild_id)
            return has_fatigue_reset or has_guild_premium

        return has_fatigue_reset
    
    def handle_entitlement_create(self, entitlement: discord.Entitlement):
        """Handle new entitlement creation - clear cache for affected user/guild"""
        user_id = entitlement.user_id
        guild_id = entitlement.guild_id
        sku_id = entitlement.sku_id
        
        # Clear relevant cache entries
        keys_to_remove = []
        for key in self._entitlement_cache:
            if user_id and f"user_{user_id}" in key:
                keys_to_remove.append(key)
            if guild_id and f"guild_{guild_id}" in key:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._entitlement_cache[key]
        
        logger.info(f"Entitlement created: User={user_id}, Guild={guild_id}, SKU={sku_id}")
    
    def handle_entitlement_update(self, entitlement: discord.Entitlement):
        """Handle entitlement update - clear cache for affected user/guild"""
        user_id = entitlement.user_id
        guild_id = entitlement.guild_id
        sku_id = entitlement.sku_id
        
        # Clear relevant cache entries
        keys_to_remove = []
        for key in self._entitlement_cache:
            if user_id and f"user_{user_id}" in key:
                keys_to_remove.append(key)
            if guild_id and f"guild_{guild_id}" in key:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._entitlement_cache[key]
        
        logger.info(f"Entitlement updated: User={user_id}, Guild={guild_id}, SKU={sku_id}, Ends={entitlement.ends_at}")
    
    def handle_entitlement_delete(self, entitlement: discord.Entitlement):
        """Handle entitlement deletion - clear cache for affected user/guild"""
        user_id = entitlement.user_id
        guild_id = entitlement.guild_id
        sku_id = entitlement.sku_id
        
        # Clear relevant cache entries
        keys_to_remove = []
        for key in self._entitlement_cache:
            if user_id and f"user_{user_id}" in key:
                keys_to_remove.append(key)
            if guild_id and f"guild_{guild_id}" in key:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self._entitlement_cache[key]
        
        logger.info(f"Entitlement deleted: User={user_id}, Guild={guild_id}, SKU={sku_id}")
    
    def clear_cache(self):
        """Clear entire entitlement cache"""
        self._entitlement_cache.clear()
        logger.info("Entitlement cache cleared")


# Global instance (will be initialized in agent_discord.py)
entitlement_manager: Optional[EntitlementManager] = None


def get_entitlement_manager() -> Optional[EntitlementManager]:
    """Get the global entitlement manager instance"""
    return entitlement_manager


def set_entitlement_manager(manager: EntitlementManager):
    """Set the global entitlement manager instance"""
    global entitlement_manager
    entitlement_manager = manager
