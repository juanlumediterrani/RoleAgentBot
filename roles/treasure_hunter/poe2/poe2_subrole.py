import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import threading
import os as os_module
import stat
from pathlib import Path
from datetime import datetime, timedelta
import discord
import asyncio
import json
from dotenv import load_dotenv

try:
    from agent_logging import get_logger
    logger = get_logger('poe2_subrole')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('poe2_subrole')

from agent_db import get_server_db_path_fallback
from agent_engine import get_discord_token
from agent_mind import call_llm
from agent_db import get_server_id
from .poe2scout_client import Poe2ScoutClient, ResponseFormatError, APIError

load_dotenv()

# Subrole configuration
SUBROLE_CONFIG = {
    "name": "poe2_subrole",
    # "system_prompt_addition": "ACTIVE SUBROLE - POE2 TREASURE HUNTER: Search for treasures in Path of Exile 2. Monitor specific item prices and alert on buying and selling opportunities."
}

MI_ID = 235796491988369408
ENTRADAS_POR_DIA = 24
UMBRAL_COMPRA = 0.15
UMBRAL_VENTA = 0.15

# --- POE2 DATABASE ---

class DatabaseRolePoe2:
    """Database for the Treasure Hunter POE2 subrole.
    
    Manages server-specific configuration (league, targets, active state)
    using the roles_*.db database.
    """

    def __init__(self, server_name: str = None, db_path: Path = None):
        if server_name is None:
            from agent_db import get_server_id
            server_name = get_server_id()
        self.server_name = server_name
        # Use RolesDatabase for POE2 configuration
        from agent_roles_db import get_roles_db_instance
        self._roles_db = get_roles_db_instance(server_name)
        self._lock = threading.Lock()
    
    def set_league(self, league: str) -> bool:
        """Set the current league."""
        try:
            with self._lock:
                config = self._roles_db.get_role_config('poe2_subrole')
                if not config:
                    config = {'enabled': True, 'config_data': {}}
                
                config_data = config.get('config_data', {})
                config_data['league'] = league
                config['config_data'] = config_data
                
                self._roles_db.save_role_config('poe2_subrole', config)
                
                # Clear the item cache from the previous league
                from .poe2scout_client import Poe2ScoutClient
                scout = Poe2ScoutClient()
                scout.clear_items_cache()
                logger.info("🗑️ Item cache cleared after league change")

                logger.info(f"✅ League updated to: {league}")
                return True
        except Exception as e:
            logger.exception(f"⚠️ Error updating league: {e}")
            return False
    
    def get_league(self) -> str:
        """Get the current league."""
        try:
            config = self._roles_db.get_role_config('poe2_subrole')
            if config and config.get('config_data'):
                return config['config_data'].get('league', 'Standard')
            return "Standard"
        except Exception as e:
            logger.exception(f"⚠️ Error getting league: {e}")
            return "Standard"
    
    def set_active(self, is_active: bool) -> bool:
        """Enable or disable the subrole."""
        try:
            with self._lock:
                config = self._roles_db.get_role_config('poe2_subrole')
                if not config:
                    config = {'enabled': True, 'config_data': {}}
                
                config['enabled'] = is_active
                self._roles_db.save_role_config('poe2_subrole', config)
                
                status = "enabled" if is_active else "disabled"
                logger.info(f"✅ POE2 subrole {status}")
                return True
        except Exception as e:
            logger.exception(f"⚠️ Error changing subrole state: {e}")
            return False
    
    def is_active(self) -> bool:
        """Check whether the subrole is active."""
        try:
            config = self._roles_db.get_role_config('poe2_subrole')
            if config:
                return config.get('enabled', False)
            return False
        except Exception as e:
            logger.exception(f"⚠️ Error checking subrole state: {e}")
            return False
    
    def add_target(self, item_name: str, item_id: int = None) -> bool:
        """Add an item to the target list."""
        try:
            with self._lock:
                config = self._roles_db.get_role_config('poe2_subrole')
                if not config:
                    config = {'enabled': True, 'config_data': {}}
                
                config_data = config.get('config_data', {})
                targets = config_data.get('targets', [])
                
                if item_name not in targets:
                    targets.append(item_name)
                    config_data['targets'] = targets
                    config['config_data'] = config_data
                    self._roles_db.save_role_config('poe2_subrole', config)
                    logger.info(f"✅ Target added: {item_name}")
                    return True
                else:
                    logger.warning(f"⚠️ Target already exists: {item_name}")
                    return False
        except Exception as e:
            logger.exception(f"⚠️ Error adding target {item_name}: {e}")
            return False
    
    def remove_target(self, item_name: str) -> bool:
        """Remove an item from the target list."""
        try:
            with self._lock:
                config = self._roles_db.get_role_config('poe2_subrole')
                if not config:
                    logger.warning(f"⚠️ No configuration found, cannot remove: {item_name}")
                    return False
                
                config_data = config.get('config_data', {})
                targets = config_data.get('targets', [])
                
                if item_name in targets:
                    targets.remove(item_name)
                    config_data['targets'] = targets
                    config['config_data'] = config_data
                    self._roles_db.save_role_config('poe2_subrole', config)
                    logger.info(f"✅ Target removed: {item_name}")
                    return True
                else:
                    logger.warning(f"⚠️ Target not found: {item_name}")
                    return False
        except Exception as e:
            logger.exception(f"⚠️ Error removing target {item_name}: {e}")
            return False
    
    def get_targets(self) -> list:
        """Get the configured targets."""
        try:
            with self._lock:
                config = self._roles_db.get_role_config('poe2_subrole')
                if config and config.get('config_data'):
                    targets = config['config_data'].get('targets', [])
                    # Return as list of tuples for compatibility: (item_name, None, 1, timestamp)
                    return [(item, None, 1, datetime.now().isoformat()) for item in targets]
                return []
        except Exception as e:
            logger.exception(f"⚠️ Error getting targets: {e}")
            return []
    
    def get_active_targets(self) -> list:
        """Get the active targets."""
        try:
            with self._lock:
                config = self._roles_db.get_role_config('poe2_subrole')
                if config and config.get('config_data'):
                    targets = config['config_data'].get('targets', [])
                    # Return as list of tuples for compatibility: (item_name, None)
                    return [(item, None) for item in targets]
                return []
        except Exception as e:
            logger.exception(f"⚠️ Error getting active targets: {e}")
            return []

# Dictionary to keep instances per server
_db_poe2_instances = {}

def get_poe2_db_instance(server_name: str = "default") -> DatabaseRolePoe2:
    """Get or create a POE2 database instance for a specific server."""
    # Use server_name as cache key since we now use RolesDatabase
    if server_name not in _db_poe2_instances:
        _db_poe2_instances[server_name] = DatabaseRolePoe2(server_name)
    
    return _db_poe2_instances[server_name]

def invalidate_poe2_db_instance(server_name: str = None):
    """Invalidate cached POE2 database instance for a server or all servers.
    
    NOTE: This function is kept for backward compatibility but is now a no-op
    since POE2Subrole uses RolesDatabase which has its own cache invalidation.
    """
    global _db_poe2_instances
    if server_name:
        if server_name in _db_poe2_instances:
            del _db_poe2_instances[server_name]
            logger.info(f"🗄️ [POE2] Invalidated cached db instance for server: {server_name}")
    else:
        _db_poe2_instances.clear()
        logger.info("🗄️ [POE2] Invalidated all cached db instances")

# English alias for consistency
def get_treasure_hunter_db_instance(server_name: str = "default") -> DatabaseRolePoe2:
    """Get or create a POE2 database instance for a specific server."""
    return get_poe2_db_instance(server_name)

# --- POE2 SUBROLE LOGIC ---

class Poe2SubroleBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.db_poe2 = None
        self.client = Poe2ScoutClient()
    
    async def on_ready(self):
        logger.info("🔮 Starting POE2 subrole...")
        
        try:
            user = await self.fetch_user(MI_ID)
            
            # Get DB instance for the active server
            server_name = get_server_id()
            if not server_name:
                logger.warning("⚠️ No active server configured for POE2 subrole startup")
                await self.close()
                return
            self.db_poe2 = get_poe2_db_instance(server_name)
            
            # Check whether the subrole is active
            if not self.db_poe2.is_active():
                logger.info("💤 POE2 subrole is inactive, shutting down...")
                await self.close()
                return
            
            # Get current configuration
            current_league = self.db_poe2.get_league()
            targets = self.db_poe2.get_active_targets()
            
            if not targets:
                logger.info("📝 No POE2 targets configured")
                await user.send("⚠️ **POE2**: No target items are configured. Use `!poe2add \"item name\"` to add them.")
                await self.close()
                return
            
            logger.info(f"🎯 POE2 active in league '{current_league}' with {len(targets)} targets")
            
            # Process each target
            for item_name, item_id in targets:
                try:
                    await self._process_item(item_name, item_id, current_league, user)
                except Exception as e:
                    logger.exception(f"Error processing item {item_name}: {e}")
                    continue
            
            logger.info("✅ POE2 process completed")
            
        except Exception as e:
            logger.exception(f"Error in POE2 on_ready: {e}")
        
        await self.close()
    
    async def _process_item(self, item_name: str, item_id: int, league: str, user):
        """Process a specific item: fetch data and analyze opportunities."""
        try:
            logger.info(f"🔍 Analyzing {item_name} in league {league}")
            
            # Get price history
            entries = self.client.get_item_history(item_name, league=league)
            
            if not entries:
                logger.warning(f"No data available for {item_name}")
                return
            
            # Get current price
            current_price = entries[0].price if entries else None
            if not current_price:
                logger.warning(f"Could not get current price for {item_name}")
                return
            
            # Analyze opportunity
            signal = self._analyze_opportunity(entries, current_price)
            
            if signal:
                logger.info(f"🚨 SIGNAL DETECTED: {item_name} - {signal} at {current_price:.2f} Div")
                
                # Send notification
                await self._send_notification(item_name, signal, current_price, user)
            else:
                logger.info(f"📊 {item_name}: Current price {current_price:.2f} Div - no signal")
                
        except Exception as e:
            logger.exception(f"Error processing {item_name}: {e}")
    
    def _analyze_opportunity(self, entries: list, current_price: float) -> str:
        """Analyze whether there is a buy/sell opportunity based on history."""
        if len(entries) < 10:
            return None
        
        prices = [entry.price for entry in entries]
        min_price = min(prices)
        max_price = max(prices)
        
        logger.info(f"{entries[0].time if entries[0].time else 'N/A'}: Price={current_price:.2f}, Min={min_price:.2f}, Max={max_price:.2f}")
        
        # Buy rule: price <= historical minimum * 1.15
        if current_price <= min_price * (1 + UMBRAL_COMPRA):
            return "COMPRA"
        
        # Sell rule: price >= historical maximum * 0.85
        if current_price >= max_price * (1 - UMBRAL_VENTA):
            return "VENTA"
        
        return None
    
    async def _send_notification(self, item_name: str, signal: str, price: float, user):
        """Send notification about detected opportunity."""
        try:
            # Get complete system prompt using the proper builder function
            from agent_engine import _build_system_prompt, _get_personality
            server_id = get_server_id()
            server_personality = _get_personality(server_id) if server_id else PERSONALITY
            system_instruction = _build_system_prompt(server_personality, server_id)
            
            # Get treasure hunter configuration from personality
            personality_config = server_personality
            
            # Get active duty and task configuration
            role_prompt = personality_config.get("treasure_hunter", {})
            active_duty = role_prompt.get("active_duty", role_prompt.get("mission_active", 
                "CURRENT DUTY - TREASURE HUNTER: You are a treasure hunter specializing in Path of Exile 2 market analysis. Focus on spotting strong buy or sell opportunities from price history and give clear, direct market advice."))
            
            # Get task-specific prompt with fallback
            notification_tasks = personality_config.get("treasure_hunter", {}).get("notification_task", {})
            if signal == "COMPRA":
                task_prompt = notification_tasks.get("buy_prompt", 
                    f"TASK - BUY OPPORTUNITY: A buy opportunity has been detected for {item_name} at {price:.2f} Divines. This price is low according to historical data. Generate a motivational message indicating it's time to buy. Be direct and concise.")
            else:
                task_prompt = notification_tasks.get("sell_prompt", 
                    f"TASK - SELL OPPORTUNITY: A sell opportunity has been detected for {item_name} at {price:.2f} Divines. This price is high according to historical data. Generate a message indicating it's time to sell for profit. Be direct and concise.")
            
            # Format task prompt with actual values
            task_prompt = task_prompt.format(item_name=item_name, price=price)
            
            # Get golden rules with fallback
            golden_rules = personality_config.get("treasure_hunter", {}).get("golden_rules", [
                "1. BE CONCISE: Keep messages short, 2-4 sentences maximum (100-200 characters)",
                "2. CLEAR ACTION: Clearly indicate if it's a BUY or SELL signal",
                "3. PRICE MENTION: Include the current price prominently",
                "4. EXPERT ADVICE: Demonstrate market knowledge and expertise",
                "5. STRONG ENDING: Use decisive tone and clear recommendations",
                "6. NO EXPLANATIONS: Provide only the alert message, no additional context"
            ])
            
            # Build complete prompt
            golden_rules_text = "\n".join(golden_rules)
            complete_prompt = f"{active_duty}\n\n{task_prompt}\n\nGOLDEN RULES:\n{golden_rules_text}\n\nRespond only with the alert message, no additional explanations."
            
            # Call LLM with complete configuration
            res = await asyncio.to_thread(call_llm, system_instruction, complete_prompt, False, "treasure_hunter_notification")
            
            await user.send(f"🔮 **POE2 TREASURE**: {res}")
            logger.info(f"✅ POE2 notification sent for {item_name} - {signal}")
            
        except Exception as e:
            logger.exception(f"Error sending POE2 notification: {e}")

def initialize_default_items(db_instance: DatabaseRolePoe2) -> bool:
    """Initialize default items if none are configured and download their data."""
    try:
        from .poe2scout_client import Poe2ScoutClient
        from ..db_role_treasure_hunter import DatabaseRolePoe
        
        current_objectives = db_instance.get_targets()
        
        # If there are already items, do nothing
        if current_objectives:
            logger.info(f"📋 {len(current_objectives)} items already configured, skipping initialization")
            return True
        
        # Default items
        default_items = {
            "ancient rib": 4379,
            "ancient collarbone": 4385,
            "ancient jawbone": 4373,
        }
        
        logger.info("📋 Initializing default items for POE2...")
        
        # Get necessary configuration to download data
        current_league = db_instance.get_league()
        server_name = db_instance.server_name if hasattr(db_instance, 'server_name') else "default"
        
        # Create DatabaseRolePoe instance to download data
        db_role_treasure_hunter = DatabaseRolePoe(server_name, current_league)
        scout = Poe2ScoutClient()
        
        items_added = []
        
        for item_name, item_id in default_items.items():
            if db_instance.add_target(item_name, item_id):
                logger.info(f"✅ Default item added: {item_name}")
                items_added.append(item_name)
                
                # Download history and current price
                try:
                    logger.info(f"📥 Downloading history for {item_name}...")
                    entries = scout.get_item_history(item_name, league=current_league)
                    
                    if entries:
                        inserted = db_role_treasure_hunter.insert_prices_bulk(item_name, entries, current_league)
                        logger.info(f"📊 {item_name}: {len(entries)} data points received, {inserted} newly inserted")
                        
                        # Get current price
                        current_price = db_role_treasure_hunter.get_current_price(item_name, current_league)
                        if current_price:
                            logger.info(f"💰 Current price of {item_name}: {current_price} Div")
                        else:
                            logger.warning(f"⚠️ Could not get current price for {item_name}")
                    else:
                        logger.warning(f"⚠️ No data available for {item_name}")
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error downloading data for {item_name}: {e}")
            else:
                logger.warning(f"⚠️ Could not add default item: {item_name}")
        
        if items_added:
            logger.info(f"✅ Initialization completed. Items added and data downloaded: {', '.join(items_added)}")
        else:
            logger.warning("⚠️ Could not add any default item")
            
        return True
        
    except Exception as e:
        logger.exception(f"❌ Error initializing default items: {e}")
        return False

# --- ITEM REFERENCE FUNCTION ---

def get_items_reference():
    """Get reference of available items using the getItems method from the scraper."""
    try:
        client = Poe2ScoutClient()
        
        # Try to get items from the API
        # Note: This would need to be implemented in the client if the API supports it
        # For now, we return a dictionary with known items
        known_items = {
            "ancient rib": 4379,
            "ancient collarbone": 4385,
            "ancient jawbone": 4373,
            "fracturing orb": 294,
            "igniferis": 25,
            "idol of uldurn": 24,
        }
        
        logger.info(f"📋 Items reference loaded: {len(known_items)} items")
        return known_items
        
    except Exception as e:
        logger.exception(f"Error getting items reference: {e}")
        return {}

# --- MAIN EXECUTION ---

if __name__ == "__main__":
    Poe2SubroleBot().run(get_discord_token())
