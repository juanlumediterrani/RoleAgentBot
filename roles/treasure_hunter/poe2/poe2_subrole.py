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
from agent_db import get_active_server_name
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

def get_db_path(server_name: str = "default") -> Path:
    """Generate the database path for the POE2 subrole."""
    return get_server_db_path_fallback(server_name, "PoE2Subrole.db")

class DatabaseRolePoe2:
    """Database for the Treasure Hunter POE2 subrole.
    Manages league configuration, targets, and preferences.
    """
    
    def __init__(self, server_name: str = "default", db_path: Path = None):
        if db_path is None:
            self.db_path = get_db_path(server_name)
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_writable_db()
        self._init_db()
    
    def _ensure_writable_db(self):
        """Ensure the database is accessible and enforce valid permissions."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._fix_permissions(self.db_path.parent)
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=DELETE;')
            conn.close()
            
            self._fix_permissions(self.db_path)
            
        except Exception as e:
            logger.error(f"Cannot access database at {self.db_path}: {e}")
            raise
    
    def _fix_permissions(self, path: Path):
        """Enforce current user/group permissions on a file or directory."""
        try:
            if path.exists():
                uid = os_module.getuid()
                gid = os_module.getgid()
                
                os_module.chown(path, uid, gid)
                
                if path.is_file():
                    current_mode = path.stat().st_mode
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP
                    os_module.chmod(path, new_mode)
                elif path.is_dir():
                    current_mode = path.stat().st_mode  
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP | stat.S_IXUSR | stat.S_IXGRP
                    os_module.chmod(path, new_mode)
                    
                logger.debug(f"Fixed permissions for {path}: uid={uid}, gid={gid}")
        except Exception as e:
            logger.warning(f"Could not fix permissions for {path}: {e}")
    
    def _init_db(self):
        """Initialize the database."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=DELETE;")
                conn.commit()
                
                # Configuration table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS configuracion (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        liga_actual TEXT NOT NULL DEFAULT 'Standard',
                        activo INTEGER NOT NULL DEFAULT 0,
                        fecha_actualizacion TEXT NOT NULL
                    )
                ''')
                
                # Targets table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS objetivos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre_item TEXT NOT NULL UNIQUE,
                        item_id INTEGER,
                        activo INTEGER NOT NULL DEFAULT 1,
                        fecha_agregado TEXT NOT NULL
                    )
                ''')
                
                # Insert initial configuration if it does not exist
                cursor.execute('SELECT COUNT(*) FROM configuracion')
                if cursor.fetchone()[0] == 0:
                    cursor.execute('''
                        INSERT INTO configuracion (id, liga_actual, activo, fecha_actualizacion)
                        VALUES (1, 'Standard', 0, ?)
                    ''', (datetime.now().isoformat(),))
                
                conn.commit()
                logger.info(f"✅ POE2 database ready at {self.db_path}")

                # Initialize default items if none exist yet
                initialize_default_items(self)
        except Exception as e:
            logger.exception(f"❌ Error initializing POE2 database: {e}")
    
    def set_league(self, league: str) -> bool:
        """Set the current league."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE configuracion 
                        SET liga_actual = ?, fecha_actualizacion = ?
                        WHERE id = 1
                    ''', (league, datetime.now().isoformat()))
                    conn.commit()
                    
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
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT liga_actual FROM configuracion WHERE id = 1')
                    result = cursor.fetchone()
                    return result[0] if result else "Standard"
        except Exception as e:
            logger.exception(f"⚠️ Error getting league: {e}")
            return "Standard"
    
    def set_active(self, is_active: bool) -> bool:
        """Enable or disable the subrole."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE configuracion 
                        SET activo = ?, fecha_actualizacion = ?
                        WHERE id = 1
                    ''', (1 if is_active else 0, datetime.now().isoformat()))
                    conn.commit()
                    status = "enabled" if is_active else "disabled"
                    logger.info(f"✅ POE2 subrole {status}")
                    return True
        except Exception as e:
            logger.exception(f"⚠️ Error changing subrole state: {e}")
            return False
    
    def is_active(self) -> bool:
        """Check whether the subrole is active."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT activo FROM configuracion WHERE id = 1')
                    result = cursor.fetchone()
                    return bool(result[0]) if result else False
        except Exception as e:
            logger.exception(f"⚠️ Error checking subrole state: {e}")
            return False
    
    def add_target(self, item_name: str, item_id: int = None) -> bool:
        """Add an item to the target list."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO objetivos (nombre_item, item_id, activo, fecha_agregado)
                        VALUES (?, ?, 1, ?)
                    ''', (item_name.strip(), item_id, datetime.now().isoformat()))
                    conn.commit()
                    logger.info(f"✅ Target added: {item_name}")
                    return True
        except Exception as e:
            logger.exception(f"⚠️ Error adding target {item_name}: {e}")
            return False
    
    def remove_target(self, item_name: str) -> bool:
        """Remove an item from the target list."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM objetivos WHERE nombre_item = ?', (item_name.strip(),))
                    conn.commit()
                    if cursor.rowcount > 0:
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
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT nombre_item, item_id, activo, fecha_agregado
                        FROM objetivos
                        ORDER BY fecha_agregado DESC
                    ''')
                    return cursor.fetchall()
        except Exception as e:
            logger.exception(f"⚠️ Error getting targets: {e}")
            return []
    
    def get_active_targets(self) -> list:
        """Get the active targets."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT nombre_item, item_id
                        FROM objetivos
                        WHERE activo = 1
                        ORDER BY fecha_agregado DESC
                    ''')
                    return cursor.fetchall()
        except Exception as e:
            logger.exception(f"⚠️ Error getting active targets: {e}")
            return []

# Dictionary to keep instances per server
_db_poe2_instances = {}

def get_poe2_db_instance(server_name: str = "default") -> DatabaseRolePoe2:
    """Get or create a POE2 database instance for a specific server."""
    if server_name not in _db_poe2_instances:
        _db_poe2_instances[server_name] = DatabaseRolePoe2(server_name)
    return _db_poe2_instances[server_name]

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
            server_name = get_active_server_name()
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
            if signal == "COMPRA":
                message_text = f"POE2 Mission: Purchase opportunity detected. The item {item_name} is cheap ({price:.2f} Div). Time to buy!"
            else:
                message_text = f"POE2 Mission: Sale opportunity detected. The item {item_name} is expensive ({price:.2f} Div). Time to sell!"
            
            res = await asyncio.to_thread(think, message_text)
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
