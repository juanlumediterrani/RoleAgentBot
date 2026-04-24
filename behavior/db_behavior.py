"""
Behavior database management for server-specific behavior tracking.

LEGACY: Behavior toggles (enabled/disabled) are now managed by server_config.json.
This database is only used for tracking data (greetings, taboo keywords).

Tables:
- greetings: Track user replies to presence greetings
- taboo: Forbidden words and settings (keywords also stored in server_config.json)
"""

import sqlite3
import json
from datetime import datetime
from agent_logging import get_logger
from agent_db import get_server_db_path_fallback

logger = get_logger('db_behavior')

class BehaviorDB:
    """Database manager for behavior settings per server."""
    
    def __init__(self, server_key: str):
        self.server_key = server_key
        # Use single behavior.db instead of per-personality databases
        db_name = 'behavior'
        self.db_path = str(get_server_db_path_fallback(server_key, db_name))
        self._init_db()
    
    def _init_db(self):
        """Initialize the behavior database."""
        try:
            import os
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Legacy tables (behaviors, behavior_settings) removed - toggles now in server_config.json
            
            # Create greetings table to track user replies to presence greetings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS greetings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    user_name TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    greeting_sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    needs_reply BOOLEAN DEFAULT 1,
                    replied_at TIMESTAMP NULL,
                    replied BOOLEAN DEFAULT 0,
                    greeting_type TEXT DEFAULT 'presence',
                    greeting_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, guild_id, greeting_sent_at)
                )
            ''')
            
            # Create taboo table for forbidden words and settings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS taboo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL UNIQUE,
                    enabled BOOLEAN DEFAULT 1,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    added_by TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info(f"Behavior database initialized for server: {self.server_key}")
            
        except Exception as e:
            logger.error(f"Failed to initialize behavior database for {self.server_key}: {e}")
    
    # Legacy methods removed - behavior toggles now managed by server_config.json
    
    # Legacy methods removed - behavior toggles now managed by server_config.json
    # This database is only used for tracking data (greetings, taboo keywords)
    
    # Greeting reply tracking methods
    def record_greeting_sent(self, user_id: str, user_name: str, guild_id: str, greeting_message: str, greeting_type: str = 'presence'):
        """Record that a greeting was sent to a user and track if reply is needed."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO greetings (user_id, user_name, guild_id, greeting_message, greeting_type, needs_reply)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (user_id, user_name, guild_id, greeting_message, greeting_type))
            
            conn.commit()
            conn.close()
            logger.info(f"Greeting recorded for user {user_name} ({user_id}) in guild {guild_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error recording greeting for {user_id}: {e}")
            return False
    
    def mark_user_replied(self, user_id: str, guild_id: str):
        """Mark that a user has replied to a greeting."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if guild_id == "dm_context":
                # DM message - mark user as replied across all guilds in this server database
                cursor.execute('''
                    UPDATE greetings 
                    SET replied = 1, replied_at = CURRENT_TIMESTAMP, needs_reply = 0
                    WHERE user_id = ? AND needs_reply = 1
                    ORDER BY greeting_sent_at DESC
                    LIMIT 1
                ''', (user_id,))
            else:
                # Server message - mark user as replied for specific guild
                cursor.execute('''
                    UPDATE greetings 
                    SET replied = 1, replied_at = CURRENT_TIMESTAMP, needs_reply = 0
                    WHERE user_id = ? AND guild_id = ? AND needs_reply = 1
                    ORDER BY greeting_sent_at DESC
                    LIMIT 1
                ''', (user_id, guild_id))
            
            conn.commit()
            rows_updated = cursor.rowcount
            conn.close()
            
            if rows_updated > 0:
                logger.info(f"User {user_id} marked as replied to greeting in guild {guild_id}")
            return rows_updated > 0
            
        except Exception as e:
            logger.error(f"Error marking user replied for {user_id}: {e}")
            return False
    
    def get_last_greeting_status(self, user_id: str, guild_id: str) -> dict:
        """Get the status of the last greeting sent to a user."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            if guild_id == "dm_context":
                # DM context - search across all guilds for this user
                cursor.execute('''
                    SELECT needs_reply, replied, greeting_sent_at, replied_at, greeting_type, guild_id
                    FROM greetings
                    WHERE user_id = ?
                    ORDER BY greeting_sent_at DESC
                    LIMIT 1
                ''', (user_id,))
            elif guild_id == "any_guild":
                # Any guild context - search across all guilds for this user (same as dm_context)
                cursor.execute('''
                    SELECT needs_reply, replied, greeting_sent_at, replied_at, greeting_type, guild_id
                    FROM greetings
                    WHERE user_id = ?
                    ORDER BY greeting_sent_at DESC
                    LIMIT 1
                ''', (user_id,))
            else:
                # Specific guild context
                cursor.execute('''
                    SELECT needs_reply, replied, greeting_sent_at, replied_at, greeting_type, guild_id
                    FROM greetings
                    WHERE user_id = ? AND guild_id = ?
                    ORDER BY greeting_sent_at DESC
                    LIMIT 1
                ''', (user_id, guild_id))
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                needs_reply, replied, greeting_sent_at, replied_at, greeting_type, result_guild_id = result
                return {
                    'needs_reply': bool(needs_reply),
                    'replied': bool(replied),
                    'greeting_sent_at': greeting_sent_at,
                    'replied_at': replied_at,
                    'greeting_type': greeting_type,
                    'guild_id': result_guild_id,
                    'has_unreplied_greeting': bool(needs_reply and not replied)
                }
            else:
                return {
                    'needs_reply': False,
                    'replied': False,
                    'greeting_sent_at': None,
                    'replied_at': None,
                    'greeting_type': None,
                    'guild_id': None,
                    'has_unreplied_greeting': False
                }
                
        except Exception as e:
            logger.error(f"Error getting last greeting status for {user_id}: {e}")
            return {
                'needs_reply': False,
                'replied': False,
                'greeting_sent_at': None,
                'replied_at': None,
                'greeting_type': None,
                'guild_id': None,
                'has_unreplied_greeting': False
            }
    
    def cleanup_old_greetings(self, days_old: int = 30):
        """Clean up old greeting records."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM greetings 
                WHERE created_at < datetime('now', '-{} days')
            '''.format(days_old))
            
            rows_deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if rows_deleted > 0:
                logger.info(f"Cleaned up {rows_deleted} old greeting records")
            return rows_deleted
            
        except Exception as e:
            logger.error(f"Error cleaning up old greetings: {e}")
            return 0
    
    # Taboo management methods
    def initialize_taboo_defaults(self, default_keywords: list):
        """Initialize taboo table with default keywords if empty."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if taboo table is empty
            cursor.execute('SELECT COUNT(*) FROM taboo')
            count = cursor.fetchone()[0]
            
            if count == 0:
                # Insert default keywords
                for keyword in default_keywords:
                    cursor.execute('''
                        INSERT OR IGNORE INTO taboo (keyword, enabled, added_by)
                        VALUES (?, ?, ?)
                    ''', (keyword, True, 'system'))
                
                conn.commit()
                logger.info(f"Initialized taboo with {len(default_keywords)} default keywords")
            
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Error initializing taboo defaults: {e}")
            return False
    
    def get_taboo_keywords(self) -> list:
        """Get all enabled taboo keywords."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT keyword FROM taboo WHERE enabled = 1 ORDER BY keyword')
            keywords = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            return keywords
            
        except Exception as e:
            logger.error(f"Error getting taboo keywords: {e}")
            return []
    
    def is_taboo_enabled(self) -> bool:
        """Check if taboo system is enabled (has any enabled keywords)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) FROM taboo WHERE enabled = 1')
            count = cursor.fetchone()[0]
            
            conn.close()
            return count > 0
            
        except Exception as e:
            logger.error(f"Error checking taboo enabled status: {e}")
            return False
    
    def add_taboo_keyword(self, keyword: str, added_by: str = 'user') -> bool:
        """Add a new taboo keyword."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR IGNORE INTO taboo (keyword, enabled, added_by)
                VALUES (?, ?, ?)
            ''', (keyword, True, added_by))
            
            changes = conn.commit()
            conn.close()
            
            if cursor.rowcount > 0:
                logger.info(f"Added taboo keyword: {keyword}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error adding taboo keyword '{keyword}': {e}")
            return False
    
    def remove_taboo_keyword(self, keyword: str) -> bool:
        """Remove a taboo keyword."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM taboo WHERE keyword = ?', (keyword,))
            
            conn.commit()
            conn.close()
            
            if cursor.rowcount > 0:
                logger.info(f"Removed taboo keyword: {keyword}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error removing taboo keyword '{keyword}': {e}")
            return False
    
    def toggle_taboo_keyword(self, keyword: str) -> bool:
        """Toggle a taboo keyword enabled/disabled status."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE taboo 
                SET enabled = NOT enabled, updated_at = CURRENT_TIMESTAMP
                WHERE keyword = ?
            ''', (keyword,))
            
            conn.commit()
            conn.close()
            
            if cursor.rowcount > 0:
                logger.info(f"Toggled taboo keyword: {keyword}")
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error toggling taboo keyword '{keyword}': {e}")
            return False

# Global instance cache
_behavior_db_instances: dict[str, BehaviorDB] = {}

def get_behavior_db_instance(server_key: str) -> BehaviorDB:
    """Get or create a behavior database instance for a server."""
    # Redirect "default" to "0" as placeholder for behavior initialization
    # This prevents creation of behavior_agent.db when no server_key is provided
    if server_key == "default":
        server_key = "0"
        logger.info("Redirecting behavior_db initialization from 'default' to server 0 as placeholder")
    
    if server_key not in _behavior_db_instances:
        _behavior_db_instances[server_key] = BehaviorDB(server_key)
    return _behavior_db_instances[server_key]

def invalidate_behavior_db_instance(server_key: str = None):
    """Invalidate cached behavior database instance for a server or all servers.
    
    Call this after personality change so the next get_behavior_db_instance()
    creates a new BehaviorDB pointing to the correct personality db file.
    
    Args:
        server_key: Server key to invalidate, or None to clear all.
    """
    global _behavior_db_instances
    if server_key:
        if server_key in _behavior_db_instances:
            del _behavior_db_instances[server_key]
            logger.info(f"🗄️ [BEHAVIOR] Invalidated cached db instance for server: {server_key}")
    else:
        _behavior_db_instances.clear()
        logger.info("🗄️ [BEHAVIOR] Invalidated all cached db instances")
