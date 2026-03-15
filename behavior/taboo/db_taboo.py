"""
Taboo database management for server-specific forbidden words.
Stores and manages taboo keywords per server.
"""

import sqlite3
import json
from datetime import datetime
from agent_logging import get_logger

logger = get_logger('db_taboo')

class TabooDB:
    """Database manager for taboo keywords per server."""
    
    def __init__(self, server_key: str):
        self.server_key = server_key
        self.db_path = f"databases/{server_key}/taboo.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize the taboo database."""
        try:
            import os
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create taboo_keywords table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS taboo_keywords (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    added_by TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    UNIQUE(keyword)
                )
            ''')
            
            # Create taboo_config table for settings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS taboo_config (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info(f"Taboo database initialized for server: {self.server_key}")
            
        except Exception as e:
            logger.error(f"Failed to initialize taboo database for {self.server_key}: {e}")
    
    def get_taboo_config(self, key: str, default_value=None):
        """Get a taboo configuration value."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT value FROM taboo_config WHERE key = ?", (key,))
            result = cursor.fetchone()
            
            conn.close()
            return result[0] if result else default_value
            
        except Exception as e:
            logger.error(f"Error getting taboo config {key}: {e}")
            return default_value
    
    def set_taboo_config(self, key: str, value: str):
        """Set a taboo configuration value."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO taboo_config (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            
            conn.commit()
            conn.close()
            logger.info(f"Taboo config {key} set for server: {self.server_key}")
            
        except Exception as e:
            logger.error(f"Error setting taboo config {key}: {e}")
    
    def is_enabled(self) -> bool:
        """Check if taboo is enabled for this server."""
        enabled = self.get_taboo_config("enabled", "false")
        return enabled.lower() == "true"
    
    def set_enabled(self, enabled: bool):
        """Enable or disable taboo for this server."""
        self.set_taboo_config("enabled", "true" if enabled else "false")
    
    def get_keywords(self) -> list[str]:
        """Get all active taboo keywords for this server."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT keyword FROM taboo_keywords WHERE is_active = 1 ORDER BY keyword")
            results = cursor.fetchall()
            
            conn.close()
            return [row[0] for row in results]
            
        except Exception as e:
            logger.error(f"Error getting taboo keywords: {e}")
            return []
    
    def add_keyword(self, keyword: str, added_by: str = None) -> bool:
        """Add a taboo keyword."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR IGNORE INTO taboo_keywords (keyword, added_by)
                VALUES (?, ?)
            ''', (keyword.lower().strip(), added_by))
            
            changes = conn.total_changes
            conn.commit()
            conn.close()
            
            if changes > 0:
                logger.info(f"Taboo keyword '{keyword}' added by {added_by} for server: {self.server_key}")
                return True
            else:
                logger.warning(f"Taboo keyword '{keyword}' already exists for server: {self.server_key}")
                return False
                
        except Exception as e:
            logger.error(f"Error adding taboo keyword '{keyword}': {e}")
            return False
    
    def remove_keyword(self, keyword: str) -> bool:
        """Remove a taboo keyword (mark as inactive)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE taboo_keywords SET is_active = 0 
                WHERE keyword = ? AND is_active = 1
            ''', (keyword.lower().strip(),))
            
            changes = cursor.rowcount
            conn.commit()
            conn.close()
            
            if changes > 0:
                logger.info(f"Taboo keyword '{keyword}' removed for server: {self.server_key}")
                return True
            else:
                logger.warning(f"Taboo keyword '{keyword}' not found for server: {self.server_key}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing taboo keyword '{keyword}': {e}")
            return False
    
    def initialize_from_defaults(self, default_keywords: list[str]) -> int:
        """Initialize taboo keywords from defaults if none exist."""
        try:
            current_keywords = self.get_keywords()
            
            if not current_keywords and default_keywords:
                added_count = 0
                for keyword in default_keywords:
                    if self.add_keyword(keyword, "system_defaults"):
                        added_count += 1
                
                logger.info(f"Initialized {added_count} taboo keywords from defaults for server: {self.server_key}")
                return added_count
            
            return 0
            
        except Exception as e:
            logger.error(f"Error initializing taboo defaults: {e}")
            return 0
    
    def get_stats(self) -> dict:
        """Get taboo statistics for this server."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get total keywords
            cursor.execute("SELECT COUNT(*) FROM taboo_keywords WHERE is_active = 1")
            total_keywords = cursor.fetchone()[0]
            
            # Get recent additions
            cursor.execute('''
                SELECT COUNT(*) FROM taboo_keywords 
                WHERE added_at > datetime('now', '-7 days') AND is_active = 1
            ''')
            recent_additions = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "enabled": self.is_enabled(),
                "total_keywords": total_keywords,
                "recent_additions": recent_additions
            }
            
        except Exception as e:
            logger.error(f"Error getting taboo stats: {e}")
            return {
                "enabled": False,
                "total_keywords": 0,
                "recent_additions": 0
            }

# Global instance cache
_taboo_db_instances: dict[str, TabooDB] = {}

def get_taboo_db_instance(server_key: str) -> TabooDB:
    """Get or create a taboo database instance for a server."""
    if server_key not in _taboo_db_instances:
        _taboo_db_instances[server_key] = TabooDB(server_key)
    return _taboo_db_instances[server_key]
