"""
POE2 Subrole Manager - Enhanced management for POE2 treasure hunting.
Handles admin activation, item lists, league-specific databases, and user commands.
"""

import json
import sqlite3
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from agent_logging import get_logger
    logger = get_logger('poe2_subrole_manager')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('poe2_subrole_manager')

from .poe2scout_client import Poe2ScoutClient


class POE2SubroleManager:
    """Enhanced POE2 subrole management with admin controls and shared databases."""
    
    def __init__(self):
        self.client = Poe2ScoutClient()
        self._activation_status = {}  # {server_id: bool} - Server activation
        self._active_leagues = {}     # {server_id: league} - Server league
        self._user_subscriptions = {} # {user_id: bool} - User alert subscriptions
        self._user_preferences = {}  # {user_id: {league: str, objectives: []}} - User preferences
        self._lock = threading.Lock()
        
        # Ensure databases directory exists
        self.databases_dir = Path("databases")
        self.databases_dir.mkdir(exist_ok=True)
        
        # Default objectives for each league
        self._default_objectives = {
            "Standard": ["Ancient Rib", "Ancient Collarbone", "Ancient Jawbone"],
            "Fate of the Vaal": ["Ancient Rib", "Ancient Collarbone", "Ancient Jawbone"],
            "Hardcore": ["Ancient Rib", "Ancient Collarbone", "Ancient Jawbone"],
            "Hardcore Fate of the Vaal": ["Ancient Rib", "Ancient Collarbone", "Ancient Jawbone"]
        }
    
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
    
    def is_activated(self, server_id: str) -> bool:
        """Check if POE2 is activated on a server."""
        with self._lock:
            return self._activation_status.get(server_id, False)
    
    def activate_subrole(self, server_id: str) -> bool:
        """Activate POE2 subrole on a server."""
        with self._lock:
            self._activation_status[server_id] = True
            if server_id not in self._active_leagues:
                self._active_leagues[server_id] = "Standard"  # Default league
            
            logger.info(f"🏆 POE2 subrole activated on server {server_id}")
            return True
    
    def deactivate_subrole(self, server_id: str) -> bool:
        """Deactivate POE2 subrole on a server."""
        with self._lock:
            self._activation_status[server_id] = False
            logger.info(f"❌ POE2 subrole deactivated on server {server_id}")
            return True
    
    def get_active_league(self, server_id: str) -> str:
        """Get the active league for a server."""
        with self._lock:
            return self._active_leagues.get(server_id, "Standard")
    
    def set_league(self, server_id: str, league: str) -> bool:
        """Set the active league for a server."""
        with self._lock:
            if self._activation_status.get(server_id, False):
                self._active_leagues[server_id] = league
                logger.info(f"🏆 League changed to {league} for server {server_id}")
                
                # Add default objectives for new league
                self._add_default_objectives(server_id, league)
                
                # Download price history for default objectives
                self._download_default_objectives_history(server_id, league)
                
                return True
            return False
    
    def get_user_league(self, user_id: str, server_id: str) -> str:
        """Get league for a user, using server league as default."""
        with self._lock:
            # Check if user has personal preference
            if user_id in self._user_preferences:
                server_league = self._active_leagues.get(server_id, "Standard")
                return self._user_preferences[user_id].get('league', server_league)
            return self._active_leagues.get(server_id, "Standard")
    
    def set_user_league(self, user_id: str, league: str, server_id: str = None) -> bool:
        """Set personal league preference for a user."""
        with self._lock:
            if user_id not in self._user_preferences:
                self._user_preferences[user_id] = {}
            self._user_preferences[user_id]['league'] = league
            if server_id:
                self._user_preferences[user_id]['server_id'] = server_id
            logger.info(f"🏆 User {user_id} set personal league to {league} on server {server_id}")
            return True
    
    def get_user_active_server(self, user_id: str) -> str:
        """Get the server where POE2 is activated for this user."""
        with self._lock:
            # First check if user has a preferred server
            if user_id in self._user_preferences and 'server_id' in self._user_preferences[user_id]:
                server_id = self._user_preferences[user_id]['server_id']
                if self._activation_status.get(server_id, False):
                    return server_id
            
            # If no preferred server or not active, find any active server
            for server_id, activated in self._activation_status.items():
                if activated:
                    # Store this as user's preferred server
                    if user_id not in self._user_preferences:
                        self._user_preferences[user_id] = {}
                    self._user_preferences[user_id]['server_id'] = server_id
                    return server_id
            
            return None
    
    def is_user_authorized(self, user_id: str) -> bool:
        """Check if user is authorized to use POE2 commands (has access to an activated server)."""
        return self.get_user_active_server(user_id) is not None
    
    def _add_default_objectives(self, user_id: str, league: str):
        """Add default objectives for a league."""
        default_items = self._default_objectives.get(league, [])
        
        # Get items from item list to find item IDs
        items = self.load_item_list(league)
        
        try:
            conn = self.init_price_history_db(league)
            cursor = conn.cursor()
            
            # Add default items if not already present
            for item_name in default_items:
                item_id = items.get(item_name.lower())
                if item_id:
                    cursor.execute('''
                        INSERT OR IGNORE INTO objectives (item_name, item_id, league, active, user_id)
                        VALUES (?, ?, ?, 1, ?)
                    ''', (item_name, item_id, league, user_id))
                else:
                    logger.warning(f"Item ID not found for default objective: {item_name}")
            
            conn.commit()
            conn.close()
            logger.info(f"Added {len(default_items)} default objectives for {league} on user {user_id}")
            
        except Exception as e:
            logger.error(f"Error adding default objectives: {e}")
    
    def _download_default_objectives_history(self, user_id: str, league: str):
        """Download price history for default objectives."""
        default_items = self._default_objectives.get(league, [])
        
        # Get item list to find item IDs
        items = self.load_item_list(league)
        
        for item_name in default_items:
            item_id = items.get(item_name.lower())
            if item_id:
                try:
                    self._download_item_history(item_name, league, item_id)
                    logger.info(f"Downloaded history for default objective: {item_name}")
                except Exception as e:
                    logger.error(f"Failed to download history for {item_name}: {e}")
            else:
                logger.warning(f"Item ID not found for default objective: {item_name}")
    
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
        """Download and save item list for a league."""
        try:
            logger.info(f"🔄 Downloading item list for {league}...")
            
            # Load items using the client
            self.client._load_items_database(league)
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
        """Initialize price history database for a league."""
        db_path = self.get_price_history_path(league)
        conn = sqlite3.connect(str(db_path))
        
        # Create tables if they don't exist
        conn.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                league TEXT NOT NULL,
                price REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                quantity INTEGER,
                raw_data TEXT
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS objectives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                league TEXT NOT NULL,
                active INTEGER DEFAULT 1,
                user_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        return conn
    
    def add_objective(self, server_id: str, user_id: str, item_name: str) -> Tuple[bool, str]:
        """Add an item to objectives for a user on a server."""
        if not self.is_activated(server_id):
            return False, "POE2 subrole is not activated on this server."
        
        league = self.get_user_league(user_id, server_id)
        
        # Get item ID from item list
        items = self.load_item_list(league)
        item_id = items.get(item_name.lower())
        
        if not item_id:
            return False, f"Item '{item_name}' not found in {league} league."
        
        try:
            conn = self.init_price_history_db(league)
            cursor = conn.cursor()
            
            # Check if already exists for this user
            cursor.execute('''
                SELECT id FROM objectives 
                WHERE item_name = ? AND league = ? AND user_id = ?
            ''', (item_name, league, user_id))
            
            if cursor.fetchone():
                conn.close()
                return False, f"Item '{item_name}' is already in objectives."
            
            # Add to objectives
            cursor.execute('''
                INSERT INTO objectives (item_name, item_id, league, active, user_id)
                VALUES (?, ?, ?, 1, ?)
            ''', (item_name, item_id, league, user_id))
            
            conn.commit()
            
            # Download price history for this item
            try:
                self._download_item_history(item_name, league, item_id)
                logger.info(f"Downloaded price history for {item_name} in {league}")
            except Exception as e:
                logger.error(f"Failed to download price history for {item_name}: {e}")
            
            conn.close()
            return True, f"Added '{item_name}' to objectives."
            
        except Exception as e:
            logger.error(f"Error adding objective {item_name}: {e}")
            return False, f"Error adding item '{item_name}'."
    
    def _download_item_history(self, item_name: str, league: str, item_id: int):
        """Download and store price history for an item."""
        try:
            # Get price history from API
            history = self.client.get_item_history(item_name, league=league, days=30)
            
            if not history:
                logger.warning(f"No price history found for {item_name} in {league}")
                return
            
            # Store in database
            db_path = self.get_price_history_path(league)
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            for entry in history:
                cursor.execute('''
                    INSERT OR REPLACE INTO price_history 
                    (item_name, item_id, league, price, timestamp, quantity, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    item_name,
                    item_id,
                    league,
                    entry.price,
                    entry.time or datetime.now().isoformat(),
                    entry.quantity,
                    str(entry.raw) if entry.raw else None
                ))
            
            conn.commit()
            conn.close()
            logger.info(f"Stored {len(history)} price entries for {item_name} in {league}")
        
        except Exception as e:
            logger.error(f"Error downloading history for {item_name}: {e}")
            raise
    
    def remove_objective(self, server_id: str, user_id: str, item_name: str) -> Tuple[bool, str]:
        """Remove an item from objectives for a user on a server."""
        if not self.is_activated(server_id):
            return False, "POE2 subrole is not activated on this server."
        
        league = self.get_user_league(user_id, server_id)
        
        try:
            conn = self.init_price_history_db(league)
            cursor = conn.cursor()
            
            # Try by name first
            cursor.execute('''
                DELETE FROM objectives 
                WHERE item_name = ? AND league = ? AND user_id = ?
            ''', (item_name, league, user_id))
            
            if cursor.rowcount > 0:
                conn.commit()
                conn.close()
                return True, f"Removed '{item_name}' from objectives."
            
            # Try by number
            try:
                item_num = int(item_name)
                cursor.execute('''
                    SELECT item_name FROM objectives 
                    WHERE league = ? AND user_id = ? ORDER BY id
                ''', (league, user_id))
                
                objectives = cursor.fetchall()
                if 1 <= item_num <= len(objectives):
                    item_to_remove = objectives[item_num - 1][0]
                    cursor.execute('''
                        DELETE FROM objectives 
                        WHERE item_name = ? AND league = ? AND user_id = ?
                    ''', (item_to_remove, league, user_id))
                    
                    conn.commit()
                    conn.close()
                    logger.info(f"➖ Removed objective #{item_num}: {item_to_remove} for user {user_id}")
                    return True, f"Removed objective #{item_num}: '{item_to_remove}'"
                else:
                    conn.close()
                    return False, f"Invalid number. There are {len(objectives)} objectives."
                    
            except ValueError:
                conn.close()
                return False, f"Item '{item_name}' not found in objectives."
                
        except Exception as e:
            logger.error(f"❌ Error removing objective: {e}")
            return False, f"Error removing objective: {e}"
    
    def list_objectives(self, server_id: str, user_id: str) -> Tuple[bool, str]:
        """List all objectives for a user with current prices."""
        if not self.is_activated(server_id):
            return False, "POE2 subrole is not activated on this server."
        
        league = self.get_user_league(user_id, server_id)
        
        try:
            conn = self.init_price_history_db(league)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT item_name, item_id, active, created_at 
                FROM objectives 
                WHERE league = ? AND user_id = ?
                ORDER BY id
            ''', (league, user_id))
            
            objectives = cursor.fetchall()
            
            if not objectives:
                conn.close()
                return True, "No objectives configured."
            
            response = f"🔮 **POE2 Objectives - {league}**\n\n"
            
            for i, (name, item_id, active, created_at) in enumerate(objectives, 1):
                status = "✅" if active else "❌"
                
                # Get latest price
                cursor.execute('''
                    SELECT price FROM price_history 
                    WHERE item_name = ? AND league = ?
                    ORDER BY timestamp DESC 
                    LIMIT 1
                ''', (name, league))
                
                price_result = cursor.fetchone()
                current_price = price_result[0] if price_result else None
                
                if current_price:
                    response += f"  {i}. {status} {name} - **{current_price:.2f} Div**\n"
                else:
                    response += f"  {i}. {status} {name} - *No data*\n"
            
            conn.close()
            return True, response
            
        except Exception as e:
            logger.error(f"❌ Error listing objectives: {e}")
            return False, f"Error listing objectives: {e}"


# Global instance
_poe2_manager = None

def get_poe2_manager() -> POE2SubroleManager:
    """Get the global POE2 manager instance."""
    global _poe2_manager
    if _poe2_manager is None:
        _poe2_manager = POE2SubroleManager()
    return _poe2_manager
