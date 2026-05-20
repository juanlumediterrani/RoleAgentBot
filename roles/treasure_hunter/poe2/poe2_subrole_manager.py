"""
POE2 Subrole Manager - Enhanced management for POE2 treasure hunting.
Handles admin activation, item lists, league-specific databases, and user commands.
"""

import json
import sqlite3
import os
import threading
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

try:
    from agent_logging import get_logger
    logger = get_logger('poe2_subrole_manager')
except Exception:
    import logging
    # logging.basicConfig removed - using centralized logging
    logger = logging.getLogger('poe2_subrole_manager')

from .poe2scout_client import Poe2ScoutClient
from agent_db import get_data_dir
from agent_roles_db import get_roles_db_instance


class POE2SubroleManager:
    """Enhanced POE2 subrole management with admin controls and shared databases."""
    
    # Default objectives for each league
    DEFAULT_OBJECTIVES = {
        "Standard": ["Ancient Rib", "Ancient Collarbone", "Ancient Jawbone"],
        "Fate of the Vaal": ["Ancient Rib", "Ancient Collarbone", "Ancient Jawbone"],
        "Hardcore": ["Ancient Rib", "Ancient Collarbone", "Ancient Jawbone"],
        "Hardcore Fate of the Vaal": ["Ancient Rib", "Ancient Collarbone", "Ancient Jawbone"]
    }
    
    def __init__(self):
        self.client = Poe2ScoutClient()
        self._activation_status = {}  # {server_id: bool} - Server activation
        self._active_leagues = {}     # {server_id: league} - Server league
        self._user_subscriptions = {} # {user_id: bool} - User alert subscriptions
        self._user_preferences = {}  # {user_id: {league: str, objectives: []}} - User preferences
        self._lock = threading.Lock()
        
        # Background tasks tracking
        self._background_tasks = set()  # Track active asyncio tasks
        self._pending_downloads = {}  # {(league, item_name): asyncio.Task}
        self._initialized_leagues = set()  # Leagues with initialized default items
        
        # Placeholder items waiting for download completion
        # {user_id: [{"item_name": str, "league": str, "status": str}]}
        self._placeholder_items = {}
        
        # Ensure shared market data directory exists
        self.databases_dir = get_data_dir() / "shared_poe2"
        self.databases_dir.mkdir(parents=True, exist_ok=True)
        
        # Default objectives for each league
        self._default_objectives = dict(self.DEFAULT_OBJECTIVES)
    
    def is_admin(self, ctx) -> bool:
        """Check if user has admin permissions."""
        # If in DM, check against admin ID list
        if ctx.guild is None:
            return ctx.author.id in self._get_admin_ids()
        
        # If in guild, check permissions
        return ctx.author.guild_permissions.administrator
    
    def is_admin_dm(self, ctx) -> bool:
        """Check if command is sent via DM by admin."""
        if ctx.guild is None and ctx.author.id in self._get_admin_ids():
            return True
        return False
    
    def _get_admin_ids(self) -> List[int]:
        """Get list of admin user IDs (you can configure this)."""
        # For now, return the bot owner ID - you can expand this
        return [235796491988369408, 1162828262908645376]  # Add user ID for testing

    def _get_roles_db(self, server_id: str):
        return get_roles_db_instance(server_id)
    
    def is_activated(self, server_id: str) -> bool:
        """Check if POE2 is activated on a server."""
        if not server_id:
            return False
        try:
            roles_db = self._get_roles_db(server_id)
            if not roles_db:
                logger.warning(f"⚠️ Cannot access roles database for server {server_id} - POE2 activation check skipped")
                return False
            enabled = roles_db.is_role_enabled("poe2", server_id)
            with self._lock:
                self._activation_status[server_id] = enabled
            return enabled
        except Exception as e:
            logger.error(f"❌ Failed to check POE2 activation on server {server_id}: {e}")
            return False
    
    def get_active_servers(self) -> list[str]:
        """Get list of servers where POE2 is activated."""
        with self._lock:
            return [server_id for server_id, active in self._activation_status.items() if active]
    
    def activate_subrole(self, server_id: str) -> bool:
        """Activate POE2 subrole on a server."""
        try:
            roles_db = self._get_roles_db(server_id)
            success = roles_db.set_role_enabled("poe2", server_id, True)
            if not success:
                return False
            
            with self._lock:
                self._activation_status[server_id] = True
            
            logger.info(f"🏆 POE2 subrole activated on server {server_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to activate POE2 subrole on server {server_id}: {e}")
            return False
    
    async def activate_subrole_async(self, server_id: str) -> Tuple[bool, str]:
        """Activate POE2 subrole on a server with async initialization.
        
        This version initializes the default league the first time the subrol is activated.
        Non-blocking - runs downloads in background.
        """
        try:
            # Check if this is the first activation (Standard league not initialized)
            is_first_activation = "Standard" not in self._initialized_leagues
            
            # Activate the subrol
            success = self.activate_subrole(server_id)
            if not success:
                return False, "Failed to activate POE2 subrole"
            
            # If first activation, initialize default league
            if is_first_activation:
                logger.info(f"🚀 First activation of POE2 on server {server_id}, initializing default league...")
                await self.initialize_default_league_on_startup()
                return True, "POE2 activated and default league initialized with background downloads"
            
            return True, "POE2 activated successfully"
            
        except Exception as e:
            logger.error(f"❌ Failed to activate POE2 subrole async on server {server_id}: {e}")
            return False, f"Error activating POE2: {e}"
    
    def deactivate_subrole(self, server_id: str) -> bool:
        """Deactivate POE2 subrole on a server."""
        try:
            roles_db = self._get_roles_db(server_id)
            success = roles_db.set_role_enabled("poe2", server_id, False)
            if not success:
                return False
            
            with self._lock:
                self._activation_status[server_id] = False
            
            logger.info(f"❌ POE2 subrole deactivated on server {server_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to deactivate POE2 subrole on server {server_id}: {e}")
            return False
    
    def get_active_league(self, user_id: str, server_id: str) -> str:
        """Get the active league for a user on a server."""
        try:
            roles_db = self._get_roles_db(server_id)
            subscription = roles_db.get_poe2_subscription(user_id, server_id)
            if subscription:
                return subscription.get('league', 'Standard')
        except Exception as e:
            logger.error(f"❌ Failed to get user league: {e}")
        
        with self._lock:
            if user_id in self._user_preferences:
                return self._user_preferences[user_id].get('league', 'Standard')
            return 'Standard'
    
    def get_user_league(self, user_id: str, server_id: str) -> str:
        """Get league for a user - now user-specific only."""
        return self.get_active_league(user_id, server_id)
    
    def get_server_leagues(self, server_id: str) -> List[str]:
        """Get all unique leagues used by users in a server."""
        try:
            roles_db = self._get_roles_db(server_id)
            subscriptions = roles_db.get_poe2_server_subscriptions(server_id)
            leagues = sorted({subscription.get('league', 'Standard') for subscription in subscriptions})
            return leagues if leagues else ['Standard']
        except Exception as e:
            logger.error(f"❌ Failed to get server leagues: {e}")
            return ['Standard']
    
    def set_user_league(self, user_id: str, league: str, server_id: str = None) -> bool:
        """Set personal league preference for a user."""
        if not server_id:
            server_id = self.get_user_active_server(user_id)
            if not server_id:
                return False
        
        try:
            roles_db = self._get_roles_db(server_id)
            current_subscription = roles_db.get_poe2_subscription(user_id, server_id)
            tracked_items = current_subscription.get('tracked_items', []) if current_subscription else []
            purchases = current_subscription.get('purchases', []) if current_subscription else []
            if not roles_db.save_poe2_subscription(user_id, server_id, league, tracked_items, purchases):
                return False
            
            with self._lock:
                if user_id not in self._user_preferences:
                    self._user_preferences[user_id] = {}
                self._user_preferences[user_id]['league'] = league
                self._user_preferences[user_id]['server_id'] = server_id
            
            logger.info(f"🏆 User {user_id} set personal league to {league} on server {server_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to set user league for {user_id}: {e}")
            return False
    
    def get_user_active_server(self, user_id: str) -> str:
        """Get the server where POE2 is activated for this user."""
        with self._lock:
            if user_id in self._user_preferences and 'server_id' in self._user_preferences[user_id]:
                server_id = self._user_preferences[user_id]['server_id']
                if self.is_activated(server_id):
                    return server_id

            for server_id, activated in self._activation_status.items():
                if activated or self.is_activated(server_id):
                    if user_id not in self._user_preferences:
                        self._user_preferences[user_id] = {}
                    self._user_preferences[user_id]['server_id'] = server_id
                    return server_id
            
            return None
    
    def is_user_authorized(self, user_id: str) -> bool:
        """Check if user is authorized to use POE2 commands (has access to an activated server)."""
        return self.get_user_active_server(user_id) is not None
    
    def get_league_abbreviation(self, league: str) -> str:
        """Get league abbreviation for file names."""
        league_mapping = {
            "Standard": "STD",
            "Fate of the Vaal": "FOV",
            "Hardcore": "HC",
            "Hardcore Fate of the Vaal": "HFOV"
        }
        return league_mapping.get(league, "STD")
    
    def get_item_list_path(self, league: str) -> Path:
        """Get path for item list JSON file."""
        abbrev = self.get_league_abbreviation(league)
        return self.databases_dir / f"poe2itemlist{abbrev}.json"
    
    def get_price_history_path(self, league: str) -> Path:
        """Get path for price history database."""
        abbrev = self.get_league_abbreviation(league)
        return self.databases_dir / f"poe2{abbrev}pricehistory.db"
    
    def should_refresh_item_list(self, league: str) -> bool:
        """Check if item list should be refreshed (older than 1 week)."""
        item_list_path = self.get_item_list_path(league)
        if not item_list_path.exists():
            return True
        
        file_mtime = datetime.fromtimestamp(item_list_path.stat().st_mtime)
        return datetime.now() - file_mtime > timedelta(days=7)
    
    async def download_item_list(self, league: str) -> bool:
        """Download and save item list for a league (non-blocking)."""
        try:
            logger.info(f"🔄 Downloading item list for {league}...")

            # Load items using the client in background thread
            await asyncio.to_thread(self.client._load_items_database, league)
            items_cache = self.client._items_cache.get(league, {})

            # Save to JSON file
            item_list_path = self.get_item_list_path(league)
            with open(item_list_path, 'w', encoding='utf-8') as f:
                json.dump(items_cache, f, indent=2, ensure_ascii=False)

            logger.info(f"✅ Item list saved for {league}: {len(items_cache)} items")
            return True

        except Exception as e:
            logger.error(f"❌ Error downloading item list for {league}: {e}")
            return False
    
    def load_item_list(self, league: str) -> Dict[str, int]:
        """Load item list from JSON file."""
        item_list_path = self.get_item_list_path(league)
        
        if not item_list_path.exists():
            return {}
        
        try:
            with open(item_list_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Error loading item list for {league}: {e}")
            return {}
    
    def init_price_history_db(self, league: str) -> sqlite3.Connection:
        """Initialize price history database for a league with per-item table structure."""
        db_path = self.get_price_history_path(league)
        conn = sqlite3.connect(str(db_path))
        
        # Create items registry to track which items have tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS items_registry (
                item_id INTEGER PRIMARY KEY,
                item_name TEXT NOT NULL,
                league TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(item_id, league)
            )
        ''')
        
        # Create index on items_registry
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_items_registry_league 
            ON items_registry(league)
        ''')
        
        conn.commit()
        return conn
    
    def _get_item_table_name(self, item_id: int) -> str:
        """Generate table name for an item."""
        return f"prices_item_{item_id}"
    
    def create_item_price_table(self, conn: sqlite3.Connection, item_id: int, item_name: str, league: str) -> None:
        """Create a price table for a specific item if it doesn't exist."""
        table_name = self._get_item_table_name(item_id)
        
        # Create the price table for this item (no raw_data column)
        conn.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                price REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                quantity INTEGER,
                UNIQUE(timestamp)
            )
        ''')
        
        # Create index on timestamp for efficient queries
        conn.execute(f'''
            CREATE INDEX IF NOT EXISTS idx_{table_name}_timestamp 
            ON {table_name}(timestamp)
        ''')
        
        # Register the item
        conn.execute('''
            INSERT OR IGNORE INTO items_registry (item_id, item_name, league)
            VALUES (?, ?, ?)
        ''', (item_id, item_name, league))
        
        conn.commit()
    
    def get_registered_items(self, league: str) -> List[Dict]:
        """Get all registered items for a league."""
        conn = None
        try:
            conn = self.init_price_history_db(league)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT item_id, item_name, created_at 
                FROM items_registry 
                WHERE league = ?
                ORDER BY item_name
            ''', (league,))
            
            items = [
                {
                    'item_id': row[0],
                    'item_name': row[1],
                    'created_at': row[2]
                }
                for row in cursor.fetchall()
            ]
            
            return items
        except Exception as e:
            logger.error(f"❌ Error getting registered items for {league}: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def insert_price_for_item(self, league: str, item_id: int, item_name: str,
                              price: float, quantity: int = None,
                              timestamp: datetime = None) -> bool:
        """Insert a price entry for a specific item."""
        conn = None
        try:
            conn = self.init_price_history_db(league)

            # Ensure table exists
            self.create_item_price_table(conn, item_id, item_name, league)

            table_name = self._get_item_table_name(item_id)

            if timestamp is None:
                timestamp = datetime.now()

            conn.execute(f'''
                INSERT INTO {table_name} (price, timestamp, quantity)
                VALUES (?, ?, ?)
            ''', (price, timestamp, quantity))

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Error inserting price for item {item_id} in {league}: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    def insert_prices_bulk_for_item(self, league: str, item_id: int, item_name: str,
                                    price_entries: List[Dict]) -> int:
        """Insert multiple price entries for an item efficiently."""
        conn = None
        try:
            conn = self.init_price_history_db(league)

            # Ensure table exists
            self.create_item_price_table(conn, item_id, item_name, league)

            table_name = self._get_item_table_name(item_id)
            inserted = 0

            for entry in price_entries:
                try:
                    conn.execute(f'''
                        INSERT OR IGNORE INTO {table_name} (price, timestamp, quantity)
                        VALUES (?, ?, ?)
                    ''', (
                        entry.get('price'),
                        entry.get('timestamp', datetime.now()),
                        entry.get('quantity')
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f"⚠️ Error inserting price entry for {item_name}: {e}")
                    continue

            conn.commit()
            return inserted
        except Exception as e:
            logger.error(f"❌ Error in bulk insert for item {item_id} in {league}: {e}")
            return 0
        finally:
            if conn:
                conn.close()
    
    def get_latest_price_for_item(self, league: str, item_id: int) -> Optional[Dict]:
        """Get the latest price for a specific item."""
        conn = None
        try:
            conn = self.init_price_history_db(league)
            table_name = self._get_item_table_name(item_id)

            cursor = conn.cursor()
            cursor.execute(f'''
                SELECT price, timestamp, quantity
                FROM {table_name}
                ORDER BY timestamp DESC
                LIMIT 1
            ''')

            row = cursor.fetchone()

            if row:
                return {
                    'price': row[0],
                    'timestamp': row[1],
                    'quantity': row[2]
                }
            return None
        except sqlite3.OperationalError as e:
            # Table doesn't exist yet - this is normal during initialization
            # when background downloads haven't completed yet
            if "no such table" in str(e).lower():
                logger.debug(f"[BG] Price table for item {item_id} not ready yet (background download in progress)")
            else:
                logger.error(f"❌ Database error getting latest price for item {item_id} in {league}: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Error getting latest price for item {item_id} in {league}: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def get_price_history_for_item(self, league: str, item_id: int,
                                   days: int = 30) -> List[Dict]:
        """Get price history for a specific item."""
        conn = None
        try:
            conn = self.init_price_history_db(league)
            table_name = self._get_item_table_name(item_id)

            cutoff_date = datetime.now() - timedelta(days=days)

            cursor = conn.cursor()
            cursor.execute(f'''
                SELECT price, timestamp, quantity
                FROM {table_name}
                WHERE timestamp > ?
                ORDER BY timestamp ASC
            ''', (cutoff_date,))

            history = [
                {
                    'price': row[0],
                    'timestamp': row[1],
                    'quantity': row[2]
                }
                for row in cursor.fetchall()
            ]

            return history
        except sqlite3.OperationalError as e:
            # Table doesn't exist yet - this is normal during initialization
            if "no such table" in str(e).lower():
                logger.debug(f"[BG] Price table for item {item_id} not ready yet (background download in progress)")
            else:
                logger.error(f"❌ Database error getting price history for item {item_id} in {league}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Error getting price history for item {item_id} in {league}: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def get_price_statistics_for_item(self, league: str, item_id: int, 
                                       days: int = 30) -> Tuple[Optional[float], Optional[float]]:
        """Get min and max price for an item over specified days."""
        try:
            history = self.get_price_history_for_item(league, item_id, days)
            if not history:
                return None, None
            
            prices = [h['price'] for h in history if h['price'] is not None]
            if not prices:
                return None, None
            
            return min(prices), max(prices)
        except Exception as e:
            logger.error(f"❌ Error getting price statistics for item {item_id}: {e}")
            return None, None
    
    def add_objective(self, server_id: str, user_id: str, item_name: str) -> Tuple[bool, str]:
        """Add an item to objectives for a user on a server using NoSQL."""
        if not server_id or not self.is_activated(server_id):
            active_servers = self.get_active_servers()
            if not active_servers:
                return False, "POE2 subrole is not activated on any server."
            server_id = active_servers[0]
        
        league = self.get_user_league(user_id, server_id)
        
        # Get item ID from item list
        items = self.load_item_list(league)
        item_id = items.get(item_name.lower())
        
        if not item_id:
            return False, f"Item '{item_name}' not found in {league} league."
        
        try:
            roles_db = self._get_roles_db(server_id)
            subscription = roles_db.get_poe2_subscription(user_id, server_id)
            tracked_items = subscription.get('tracked_items', []) if subscription else []
            purchases = subscription.get('purchases', []) if subscription else []
            
            # Check if item already tracked (by name)
            existing = next((item for item in tracked_items if isinstance(item, dict) and item.get('item_name') == item_name), None)
            if existing:
                return False, f"Item '{item_name}' is already in objectives."
            
            # Add item with item_id
            tracked_items.append({
                'item_name': item_name,
                'item_id': item_id
            })
            
            if not roles_db.save_poe2_subscription(user_id, server_id, league, tracked_items, purchases):
                return False, f"Error saving subscription for '{item_name}'."
            
            try:
                self._download_item_history(item_name, league, item_id)
                logger.info(f"Downloaded price history for {item_name} in {league}")
            except Exception as e:
                logger.error(f"Failed to download price history for {item_name}: {e}")
            
            return True, f"Added '{item_name}' to objectives."
            
        except Exception as e:
            logger.error(f"Error adding objective {item_name}: {e}")
            return False, f"Error adding item '{item_name}'."
    
    def _download_item_history(self, item_name: str, league: str, item_id: int):
        """Download and store price history for an item using per-item table structure."""
        try:
            # Get price history from API
            history = self.client.get_item_history(item_name, league=league, days=30)
            
            if not history:
                logger.warning(f"No price history found for {item_name} in {league}")
                return
            
            # Convert entries to dict format for bulk insert
            price_entries = []
            for entry in history:
                price_entries.append({
                    'price': entry.price,
                    'timestamp': entry.time or datetime.now().isoformat(),
                    'quantity': entry.quantity
                })
            
            # Store using new per-item table structure (no raw_data)
            inserted = self.insert_prices_bulk_for_item(league, item_id, item_name, price_entries)
            logger.info(f"Stored {inserted}/{len(history)} price entries for {item_name} (ID: {item_id}) in {league}")
        
        except Exception as e:
            logger.error(f"Error downloading history for {item_name}: {e}")
            raise
    
    def remove_objective(self, server_id: str, user_id: str, item_name: str) -> Tuple[bool, str]:
        """Remove an item from objectives for a user on a server using NoSQL."""
        if not server_id or not self.is_activated(server_id):
            active_servers = self.get_active_servers()
            if not active_servers:
                return False, "POE2 subrole is not activated on any server."
            server_id = active_servers[0]
        
        league = self.get_user_league(user_id, server_id)
        
        try:
            roles_db = self._get_roles_db(server_id)
            subscription = roles_db.get_poe2_subscription(user_id, server_id)
            tracked_items = subscription.get('tracked_items', []) if subscription else []
            purchases = subscription.get('purchases', []) if subscription else []
            
            # Try by name first
            existing = next((item for item in tracked_items if isinstance(item, dict) and item.get('item_name') == item_name), None)
            if existing:
                tracked_items = [item for item in tracked_items if item.get('item_name') != item_name]
                if tracked_items:
                    roles_db.save_poe2_subscription(user_id, server_id, league, tracked_items, purchases)
                else:
                    roles_db.delete_poe2_subscription(user_id, server_id)
                return True, f"Removed '{item_name}' from objectives."
            
            # Try by number
            try:
                item_num = int(item_name)
                if 1 <= item_num <= len(tracked_items):
                    item_to_remove = tracked_items[item_num - 1]
                    tracked_items.pop(item_num - 1)
                    if tracked_items:
                        roles_db.save_poe2_subscription(user_id, server_id, league, tracked_items, purchases)
                    else:
                        roles_db.delete_poe2_subscription(user_id, server_id)
                    logger.info(f"➖ Removed objective #{item_num}: {item_to_remove.get('item_name')} for user {user_id}")
                    return True, f"Removed objective #{item_num}: '{item_to_remove.get('item_name')}'"
                else:
                    return False, f"Invalid number. There are {len(tracked_items)} objectives."
                    
            except ValueError:
                return False, f"Item '{item_name}' not found in objectives."
                
        except Exception as e:
            logger.error(f"❌ Error removing objective: {e}")
            return False, f"Error removing objective: {e}"
    
    def list_objectives(self, server_id: str, user_id: str) -> Tuple[bool, str]:
        """List all objectives for a user with current prices using NoSQL."""
        if not server_id or not self.is_activated(server_id):
            active_servers = self.get_active_servers()
            if not active_servers:
                return False, "POE2 subrole is not activated on any server."
            server_id = active_servers[0]
        
        league = self.get_user_league(user_id, server_id)
        
        try:
            roles_db = self._get_roles_db(server_id)
            subscription = roles_db.get_poe2_subscription(user_id, server_id)
            tracked_items = subscription.get('tracked_items', []) if subscription else []
            
            if not tracked_items:
                return True, "No objectives configured."
            
            response = f"🔮 **POE2 Objectives - {league}**\n\n"
            
            for i, item in enumerate(tracked_items, 1):
                item_name = item.get('item_name', 'Unknown')
                item_id = item.get('item_id')
                
                # Get latest price using per-item table
                price_data = self.get_latest_price_for_item(league, item_id) if item_id else None
                current_price = price_data['price'] if price_data else None
                
                if current_price:
                    response += f"  {i}. ✅ {item_name} - **{current_price:.2f} Div**\n"
                else:
                    response += f"  {i}. ✅ {item_name} - *No data*\n"
            
            return True, response
            
        except Exception as e:
            logger.error(f"❌ Error listing objectives: {e}")
            return False, f"Error listing objectives: {e}"

    def get_all_server_subscriptions(self, server_id: str) -> List[Dict[str, object]]:
        """Get all POE2 subscriptions for a server."""
        try:
            roles_db = self._get_roles_db(server_id)
            return roles_db.get_poe2_server_subscriptions(server_id)
        except Exception as e:
            logger.error(f"❌ Failed to get all POE2 subscriptions for server {server_id}: {e}")
            return []

    # ─── Background Task Management ─────────────────────────────────────────
    
    def _register_background_task(self, task: asyncio.Task) -> asyncio.Task:
        """Register a background task and clean up completed tasks."""
        self._background_tasks.discard(task)
        task.add_done_callback(self._background_tasks.discard)
        self._background_tasks.add(task)
        return task
    
    async def _download_item_history_async(self, item_name: str, league: str, item_id: int) -> bool:
        """Async wrapper for downloading item history in background."""
        try:
            await asyncio.to_thread(self._download_item_history, item_name, league, item_id)
            logger.info(f"✅ Background download completed: {item_name} in {league}")
            return True
        except Exception as e:
            logger.error(f"❌ Background download failed for {item_name} in {league}: {e}")
            return False
        finally:
            # Clear pending download tracking
            key = (league, item_name)
            if key in self._pending_downloads:
                del self._pending_downloads[key]
    
    def start_item_download_background(self, item_name: str, league: str, item_id: int) -> asyncio.Task:
        """Start a background task to download item history without blocking."""
        key = (league, item_name)
        
        # Check if already downloading
        if key in self._pending_downloads:
            logger.info(f"⏳ Download already in progress for {item_name} in {league}")
            return self._pending_downloads[key]
        
        # Create new background task
        task = asyncio.create_task(
            self._download_item_history_async(item_name, league, item_id)
        )
        self._pending_downloads[key] = task
        self._register_background_task(task)
        
        logger.info(f"🔄 Background download started: {item_name} in {league}")
        return task
    
    # ─── League Initialization ──────────────────────────────────────────────
    
    async def initialize_league_if_needed(self, league: str) -> bool:
        """Initialize a league with default items if not already initialized.
        
        This downloads the item list and default objectives for the league.
        Non-blocking - runs downloads in background.
        """
        if league in self._initialized_leagues:
            logger.info(f"✅ League {league} already initialized")
            return True
        
        logger.info(f"🚀 Initializing league: {league}")
        
        try:
            # Download item list for the league
            if self.should_refresh_item_list(league):
                success = await self.download_item_list(league)
                if not success:
                    logger.warning(f"⚠️ Failed to download item list for {league}")
                    return False
            
            # Initialize price history database
            conn = self.init_price_history_db(league)
            conn.close()

            # Start background downloads for default items
            items = self.load_item_list(league)
            default_items = self._default_objectives.get(league, self._default_objectives["Standard"])
            
            for item_name in default_items:
                item_id = items.get(item_name.lower())
                if item_id:
                    self.start_item_download_background(item_name, league, item_id)
                    logger.info(f"🔄 Started background download for default item: {item_name}")
                else:
                    logger.warning(f"⚠️ Item ID not found for default item: {item_name}")
            
            self._initialized_leagues.add(league)
            logger.info(f"✅ League {league} initialization started (background downloads running)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error initializing league {league}: {e}")
            return False
    
    async def initialize_default_league_on_startup(self) -> bool:
        """Initialize the default league (Standard) on bot startup if treasure_hunter is enabled in agent_config."""
        try:
            default_league = "Standard"
            logger.info(f"🚀 Startup initialization of default league: {default_league}")
            return await self.initialize_league_if_needed(default_league)
        except Exception as e:
            logger.error(f"❌ Error during startup league initialization: {e}")
            return False
    
    # ─── User Subscription with Default Items ─────────────────────────────────
    
    async def create_user_subscription(self, user_id: str, server_id: str, league: str) -> Tuple[bool, str]:
        """Create a new user subscription with default items copied to their account.
        
        Initializes the league if needed, then copies default items to user's subscription.
        """
        try:
            # First ensure the league is initialized
            await self.initialize_league_if_needed(league)
            
            # Get roles database
            roles_db = self._get_roles_db(server_id)
            
            # Get default items for this league
            default_items = self._default_objectives.get(league, self._default_objectives["Standard"])
            
            # Build tracked items list with item_ids
            items = self.load_item_list(league)
            tracked_items = []
            
            for item_name in default_items:
                item_id = items.get(item_name.lower())
                if item_id:
                    tracked_items.append({
                        'item_name': item_name,
                        'item_id': item_id,
                        'source': 'default'  # Mark as default item
                    })
            
            # Save subscription
            success = roles_db.save_poe2_subscription(user_id, server_id, league, tracked_items)
            if not success:
                return False, "Failed to save subscription"
            
            logger.info(f"✅ Created subscription for user {user_id} in {league} with {len(tracked_items)} default items")
            return True, f"Subscription created with {len(tracked_items)} default items"
            
        except Exception as e:
            logger.error(f"❌ Error creating user subscription: {e}")
            return False, f"Error creating subscription: {e}"
    
    # ─── Placeholder Management ───────────────────────────────────────────────
    
    def add_placeholder_item(self, user_id: str, item_name: str, league: str) -> None:
        """Add a placeholder item for a user while waiting for download."""
        if user_id not in self._placeholder_items:
            self._placeholder_items[user_id] = []
        
        self._placeholder_items[user_id].append({
            'item_name': item_name,
            'league': league,
            'status': 'downloading',
            'added_at': datetime.now().isoformat()
        })
        logger.info(f"⏳ Added placeholder for {item_name} in {league} for user {user_id}")
    
    def remove_placeholder_item(self, user_id: str, item_name: str, league: str) -> None:
        """Remove a placeholder item when download completes."""
        if user_id in self._placeholder_items:
            self._placeholder_items[user_id] = [
                p for p in self._placeholder_items[user_id]
                if not (p['item_name'] == item_name and p['league'] == league)
            ]
            logger.info(f"✅ Removed placeholder for {item_name} in {league} for user {user_id}")
    
    def get_placeholder_items(self, user_id: str, league: str = None) -> List[Dict]:
        """Get placeholder items for a user, optionally filtered by league."""
        placeholders = self._placeholder_items.get(user_id, [])
        if league:
            return [p for p in placeholders if p['league'] == league]
        return placeholders
    
    def is_item_downloading(self, item_name: str, league: str) -> bool:
        """Check if an item is currently being downloaded."""
        key = (league, item_name)
        if key in self._pending_downloads:
            task = self._pending_downloads[key]
            return not task.done()
        return False
    
    # ─── Enhanced Add Objective with Background Download ──────────────────────
    
    async def add_objective_async(self, server_id: str, user_id: str, item_name: str) -> Tuple[bool, str]:
        """Add an item to objectives with non-blocking background download and placeholder support using NoSQL."""
        # Check activation
        if not server_id or not self.is_activated(server_id):
            active_servers = self.get_active_servers()
            if not active_servers:
                return False, "POE2 subrole is not activated on any server."
            server_id = active_servers[0]
        
        league = self.get_user_league(user_id, server_id)
        
        # Get item ID from item list
        items = self.load_item_list(league)
        item_id = items.get(item_name.lower())
        
        if not item_id:
            return False, f"Item '{item_name}' not found in {league} league."
        
        try:
            # Check if item is already in user's subscription for this server
            roles_db = self._get_roles_db(server_id)
            subscription = roles_db.get_poe2_subscription(user_id, server_id)
            tracked_items = subscription.get('tracked_items', []) if subscription else []
            purchases = subscription.get('purchases', []) if subscription else []

            # Check if item is already in tracked_items for this server
            already_in_subscription = any(
                isinstance(item, dict) and item.get('item_name') == item_name
                for item in tracked_items
            )

            if already_in_subscription:
                return False, f"Item '{item_name}' is already in your tracking list."

            # Add placeholder immediately
            self.add_placeholder_item(user_id, item_name, league)

            # Update subscription for this server
            tracked_items.append({
                'item_name': item_name,
                'item_id': item_id
            })

            if not roles_db.save_poe2_subscription(user_id, server_id, league, tracked_items, purchases):
                self.remove_placeholder_item(user_id, item_name, league)
                return False, f"Error saving subscription for '{item_name}'."

            # Start background download
            task = self.start_item_download_background(item_name, league, item_id)

            # Set up callback to remove placeholder when done
            def on_download_done(t):
                self.remove_placeholder_item(user_id, item_name, league)

            task.add_done_callback(on_download_done)

            return True, f"Added '{item_name}' to objectives (downloading price data...)"
            
        except Exception as e:
            logger.error(f"Error in async add_objective: {e}")
            self.remove_placeholder_item(user_id, item_name, league)
            return False, f"Error adding item '{item_name}'."
    
    def get_user_tracked_items_with_status(self, user_id: str, server_id: str) -> List[Dict]:
        """Get tracked items for a user including placeholders and download status using NoSQL."""
        try:
            league = self.get_user_league(user_id, server_id)
            
            # Get tracked items from NoSQL subscription
            roles_db = self._get_roles_db(server_id)
            subscription = roles_db.get_poe2_subscription(user_id, server_id)
            tracked_items = subscription.get('tracked_items', []) if subscription else []
            
            objectives = []
            for item in tracked_items:
                item_name = item.get('item_name')
                item_id = item.get('item_id')
                
                # Check if item is still downloading
                is_downloading = self.is_item_downloading(item_name, league)
                
                objectives.append({
                    'item_name': item_name,
                    'item_id': item_id,
                    'active': True,
                    'created_at': subscription.get('created_at'),
                    'is_placeholder': False,
                    'is_downloading': is_downloading,
                    'status': 'downloading' if is_downloading else 'ready'
                })
            
            # Add placeholder items
            placeholders = self.get_placeholder_items(user_id, league)
            for ph in placeholders:
                objectives.append({
                    'item_name': ph['item_name'],
                    'item_id': None,
                    'active': True,
                    'created_at': ph['added_at'],
                    'is_placeholder': True,
                    'is_downloading': True,
                    'status': ph['status']
                })
            
            return objectives
            
        except Exception as e:
            logger.error(f"Error getting tracked items with status: {e}")
            return []
    
    # ─── Price Update Task Methods ──────────────────────────────────────────
    
    async def update_all_registered_item_prices(self, league: str) -> Dict[int, Dict]:
        """Update prices for all registered items in a league with cooperative multitasking.
        
        This downloads the latest price for each item and stores it.
        Yields control between items to avoid blocking the main runtime.
        Returns a dict mapping item_id to price data.
        """
        import asyncio
        updated_items = {}
        
        try:
            # Get all registered items for this league
            registered_items = self.get_registered_items(league)
            
            if not registered_items:
                logger.info(f"[BG] No registered items found for league {league}")
                return updated_items
            
            logger.info(f"[BG] 🔄 Updating prices for {len(registered_items)} items in {league}")
            
            # Ensure item list is loaded
            items_catalog = self.load_item_list(league)
            
            for i, item in enumerate(registered_items):
                item_id = item['item_id']
                item_name = item['item_name']
                
                try:
                    # Yield control every few items to avoid blocking
                    if i % 3 == 0:
                        await asyncio.sleep(0)

                    # Download latest price from API (non-blocking)
                    history_entries = await self.client.get_item_history_async(item_name, league=league, days=1)
                    
                    if not history_entries:
                        logger.debug(f"[BG] No recent price data for {item_name} in {league}")
                        continue
                    
                    # Store the new price entries
                    price_entries = []
                    for entry in history_entries:
                        price_entries.append({
                            'price': entry.price,
                            'timestamp': entry.time or datetime.now().isoformat(),
                            'quantity': entry.quantity
                        })
                    
                    # Run DB operations in thread pool to avoid blocking
                    inserted = await asyncio.to_thread(
                        self.insert_prices_bulk_for_item, 
                        league, item_id, item_name, price_entries
                    )
                    
                    # Get latest price and statistics (also in thread pool)
                    latest = await asyncio.to_thread(
                        self.get_latest_price_for_item, league, item_id
                    )
                    min_price, max_price = await asyncio.to_thread(
                        self.get_price_statistics_for_item, league, item_id, 30
                    )
                    
                    if latest:
                        updated_items[item_id] = {
                            'item_name': item_name,
                            'item_id': item_id,
                            'current_price': latest['price'],
                            'timestamp': latest['timestamp'],
                            'min_price': min_price,
                            'max_price': max_price,
                            'entries_inserted': inserted
                        }
                        logger.debug(f"[BG] ✅ Updated {item_name}: {latest['price']:.2f} Div")
                    
                except Exception as e:
                    logger.error(f"[BG] ❌ Error updating price for {item_name} (ID: {item_id}): {e}")
                    continue
            
            logger.info(f"[BG] ✅ Price update completed for {league}: {len(updated_items)} items updated")
            return updated_items
            
        except Exception as e:
            logger.error(f"[BG] ❌ Error in update_all_registered_item_prices for {league}: {e}")
            return updated_items
    
    async def run_price_update_task(self) -> Dict[str, Dict[int, Dict]]:
        """Run the scheduled price update task for all initialized leagues with low priority.
        
        This is called by the treasure_hunter role at configured intervals.
        Yields control between leagues to avoid blocking the main runtime.
        Returns updated price data for all leagues.
        """
        import asyncio
        all_updates = {}
        
        try:
            logger.info("[BG] 🚀 Starting scheduled price update task for POE2")
            
            # Yield control immediately
            await asyncio.sleep(0)
            
            # Update prices for all initialized leagues
            for league in self._initialized_leagues:
                try:
                    # Yield control before processing each league
                    await asyncio.sleep(0)
                    
                    updated = await self.update_all_registered_item_prices(league)
                    all_updates[league] = updated
                    
                    # Small delay between leagues to prevent blocking
                    await asyncio.sleep(0.01)  # 10ms
                except Exception as e:
                    logger.error(f"[BG] ❌ Error updating prices for league {league}: {e}")
                    continue
            
            total_items = sum(len(items) for items in all_updates.values())
            logger.info(f"[BG] ✅ Scheduled price update completed: {total_items} items across {len(all_updates)} leagues")
            return all_updates
            
        except Exception as e:
            logger.error(f"[BG] ❌ Error in run_price_update_task: {e}")
            return all_updates
    
    def check_price_signal(self, current_price: float, min_price: float, max_price: float) -> Optional[str]:
        """Check if current price is in buy or sell zone.
        
        Returns 'COMPRA' if price is near minimum (good buy opportunity)
        Returns 'VENTA' if price is near maximum (good sell opportunity)
        Returns None if price is in neutral zone
        """
        UMBRAL_COMPRA = 0.15  # 15% above minimum
        UMBRAL_VENTA = 0.15   # 15% below maximum
        
        if min_price is None or max_price is None or current_price is None:
            return None
        
        if current_price <= min_price * (1 + UMBRAL_COMPRA):
            return "COMPRA"
        if current_price >= max_price * (1 - UMBRAL_VENTA):
            return "VENTA"
        return None


# Global instance
_poe2_manager = None

def get_poe2_manager() -> POE2SubroleManager:
    """Get the global POE2 manager instance."""
    global _poe2_manager
    if _poe2_manager is None:
        _poe2_manager = POE2SubroleManager()
    return _poe2_manager
