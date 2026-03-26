"""
Behavior database management for server-specific behavior settings.
Stores and manages greetings, welcome, commentary, and other behavior states per server.
"""

import sqlite3
import json
from datetime import datetime
from agent_logging import get_logger

logger = get_logger('db_behavior')

class BehaviorDB:
    """Database manager for behavior settings per server."""
    
    def __init__(self, server_key: str):
        self.server_key = server_key
        self.db_path = f"databases/{server_key}/behavior.db"
        self._init_db()
    
    def _init_db(self):
        """Initialize the behavior database."""
        try:
            import os
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create behaviors table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS behaviors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    behavior_name TEXT NOT NULL,
                    setting_key TEXT NOT NULL,
                    setting_value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT,
                    UNIQUE(behavior_name, setting_key)
                )
            ''')
            
            # Create behavior_states table for simple boolean states
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS behavior_states (
                    behavior_name TEXT PRIMARY KEY,
                    enabled BOOLEAN DEFAULT 0,
                    config_data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT
                )
            ''')
            
            # Create behavior_settings table for backward compatibility
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS behavior_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT
                )
            ''')
            
            # Create roles table for server-specific role toggles
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS roles (
                    role_name TEXT PRIMARY KEY,
                    enabled BOOLEAN DEFAULT 0,
                    interval_hours INTEGER DEFAULT 1,
                    config_data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by TEXT
                )
            ''')
            
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
    
    def get_behavior_state(self, behavior_name: str) -> dict:
        """Get behavior state and config."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT enabled, config_data FROM behavior_states WHERE behavior_name = ?", (behavior_name,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                enabled, config_data = result
                config = json.loads(config_data) if config_data else {}
                return {
                    'enabled': bool(enabled),
                    'config': config
                }
            else:
                # Default to True for greetings, False for other behaviors
                default_enabled = behavior_name == 'greetings'
                return {
                    'enabled': default_enabled,
                    'config': {}
                }
            
        except Exception as e:
            logger.error(f"Error getting behavior state {behavior_name}: {e}")
            # Default to True for greetings, False for other behaviors
            default_enabled = behavior_name == 'greetings'
            return {
                'enabled': default_enabled,
                'config': {}
            }

    def get_feature_state(self, feature_name: str) -> dict:
        """Get feature state and config using the shared behavior state table."""
        return self.get_behavior_state(f'feature:{feature_name}')
    
    def set_behavior_state(self, behavior_name: str, enabled: bool, config: dict = None, updated_by: str = None):
        """Set behavior state and config."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            config_data = json.dumps(config) if config else None
            
            cursor.execute('''
                INSERT OR REPLACE INTO behavior_states (behavior_name, enabled, config_data, updated_at, updated_by)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            ''', (behavior_name, enabled, config_data, updated_by))
            
            conn.commit()
            conn.close()
            logger.info(f"Behavior {behavior_name} set to {'enabled' if enabled else 'disabled'} for server: {self.server_key}")
            
        except Exception as e:
            logger.error(f"Error setting behavior state {behavior_name}: {e}")

    def set_feature_state(self, feature_name: str, enabled: bool, config: dict = None, updated_by: str = None):
        """Set feature state and config using the shared behavior state table."""
        self.set_behavior_state(f'feature:{feature_name}', enabled, config, updated_by)
    
    def get_behavior_setting(self, behavior_name: str, setting_key: str, default_value=None):
        """Get a specific behavior setting."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT setting_value FROM behaviors WHERE behavior_name = ? AND setting_key = ?", (behavior_name, setting_key))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                # Try to parse as JSON, fallback to string
                try:
                    return json.loads(result[0])
                except:
                    return result[0]
            return default_value
            
        except Exception as e:
            logger.error(f"Error getting behavior setting {behavior_name}.{setting_key}: {e}")
            return default_value

    def get_feature_setting(self, feature_name: str, setting_key: str, default_value=None):
        """Get a specific feature setting using the shared behavior settings table."""
        return self.get_behavior_setting(f'feature:{feature_name}', setting_key, default_value)
    
    def set_behavior_setting(self, behavior_name: str, setting_key: str, value, updated_by: str = None):
        """Set a specific behavior setting."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Convert value to JSON if it's not a string
            if not isinstance(value, str):
                value_str = json.dumps(value)
            else:
                value_str = value
            
            cursor.execute('''
                INSERT OR REPLACE INTO behaviors (behavior_name, setting_key, setting_value, updated_at, updated_by)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            ''', (behavior_name, setting_key, value_str, updated_by))
            
            conn.commit()
            conn.close()
            logger.info(f"Behavior setting {behavior_name}.{setting_key} set for server: {self.server_key}")
            
        except Exception as e:
            logger.error(f"Error setting behavior setting {behavior_name}.{setting_key}: {e}")

    def set_feature_setting(self, feature_name: str, setting_key: str, value, updated_by: str = None):
        """Set a specific feature setting using the shared behavior settings table."""
        self.set_behavior_setting(f'feature:{feature_name}', setting_key, value, updated_by)
    
    def get_setting(self, key: str, default_value=None):
        """Get a behavior setting value (backward compatibility)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT value FROM behavior_settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                # Try to parse as JSON, fallback to string
                try:
                    return json.loads(result[0])
                except:
                    return result[0]
            return default_value
            
        except Exception as e:
            logger.error(f"Error getting behavior setting {key}: {e}")
            return default_value
    
    def set_setting(self, key: str, value, updated_by: str = None):
        """Set a behavior setting value (backward compatibility)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Convert value to JSON if it's not a string
            if not isinstance(value, str):
                value_str = json.dumps(value)
            else:
                value_str = value
            
            cursor.execute('''
                INSERT OR REPLACE INTO behavior_settings (key, value, updated_at, updated_by)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ''', (key, value_str, updated_by))
            
            conn.commit()
            conn.close()
            logger.info(f"Behavior setting {key} set for server: {self.server_key}")
            
        except Exception as e:
            logger.error(f"Error setting behavior setting {key}: {e}")
    
    # Specific behavior methods
    def get_greetings_enabled(self) -> bool:
        """Get greetings enabled state."""
        state = self.get_behavior_state('greetings')
        return state['enabled']
    
    def set_greetings_enabled(self, enabled: bool, updated_by: str = None):
        """Set greetings enabled state."""
        self.set_behavior_state('greetings', enabled, None, updated_by)
    
    def get_welcome_enabled(self) -> bool:
        """Get welcome enabled state."""
        state = self.get_behavior_state('welcome')
        return state['enabled']
    
    def set_welcome_enabled(self, enabled: bool, updated_by: str = None):
        """Set welcome enabled state."""
        self.set_behavior_state('welcome', enabled, None, updated_by)

    def get_role_enabled(self, role_name: str, default_enabled: bool = False) -> bool:
        """Get persisted enabled state for a role from the dedicated roles table."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT enabled FROM roles WHERE role_name = ?", (role_name,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result is not None:
                return bool(result[0])
            else:
                # If role doesn't exist in database, create it with default value
                self.set_role_enabled(role_name, default_enabled, 'system_auto_create')
                return default_enabled
            
        except Exception as e:
            logger.error(f"Error getting role enabled state for {role_name}: {e}")
            return default_enabled

    def migrate_roles_from_config(self, agent_config: dict) -> bool:
        """Migrate roles from agent_config to database - create new roles and update existing ones."""
        try:
            if not agent_config:
                return False
                
            roles_cfg = agent_config.get("roles", {})
            if not roles_cfg:
                return False
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            migrated = 0
            updated = 0
            for role_name, role_config in roles_cfg.items():
                if not isinstance(role_config, dict):
                    continue
                    
                # Get current role state from database
                cursor.execute("SELECT enabled FROM roles WHERE role_name = ?", (role_name,))
                result = cursor.fetchone()
                
                enabled = role_config.get("enabled", False)
                
                if result is None:
                    # Migrate from agent_config to database (new role)
                    cursor.execute('''
                        INSERT INTO roles (role_name, enabled, updated_at, updated_by)
                        VALUES (?, ?, CURRENT_TIMESTAMP, ?)
                    ''', (role_name, enabled, 'config_migration'))
                    migrated += 1
                    logger.info(f"Migrated role {role_name} from config to database: enabled={enabled}")
                else:
                    # Update existing role if config value differs
                    current_enabled = bool(result[0])
                    if current_enabled != enabled:
                        cursor.execute('''
                            UPDATE roles SET enabled = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                            WHERE role_name = ?
                        ''', (enabled, 'config_sync', role_name))
                        updated += 1
                        logger.info(f"Updated role {role_name} from config: {current_enabled} -> {enabled}")
            
            conn.commit()
            conn.close()
            
            if migrated > 0 or updated > 0:
                logger.info(f"Successfully migrated {migrated} new roles and updated {updated} existing roles from agent_config to database")
            
            return (migrated + updated) > 0
            
        except Exception as e:
            logger.error(f"Error migrating roles from config: {e}")
            return False

    def set_role_enabled(self, role_name: str, enabled: bool, updated_by: str = None):
        """Persist enabled state for a role in the dedicated roles table."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO roles (role_name, enabled, updated_at, updated_by)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ''', (role_name, enabled, updated_by))
            
            conn.commit()
            conn.close()
            logger.info(f"Role {role_name} set to {enabled} for server {self.server_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting role enabled state for {role_name}: {e}")
            return False

    def get_all_roles_status(self) -> dict:
        """Get status of all roles from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT role_name, enabled, interval_hours, updated_at, updated_by
                FROM roles
                ORDER BY role_name
            ''')
            
            roles = {}
            for row in cursor.fetchall():
                role_name, enabled, interval_hours, updated_at, updated_by = row
                roles[role_name] = {
                    'enabled': bool(enabled),
                    'interval_hours': interval_hours,
                    'updated_at': updated_at,
                    'updated_by': updated_by
                }
            
            conn.close()
            return roles
            
        except Exception as e:
            logger.error(f"Error getting all roles status: {e}")
            return {}

    def get_role_interval_hours(self, role_name: str, default_value: int = 1) -> int:
        """Get persisted interval for a role from the dedicated roles table."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT interval_hours FROM roles WHERE role_name = ?", (role_name,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result is not None:
                return int(result[0])
            return default_value
            
        except Exception as e:
            logger.error(f"Error getting role interval for {role_name}: {e}")
            return default_value

    def set_role_interval_hours(self, role_name: str, hours: int, updated_by: str = None):
        """Persist interval for a role in the dedicated roles table."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO roles (role_name, interval_hours, updated_at, updated_by)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            ''', (role_name, hours, updated_by))
            
            conn.commit()
            conn.close()
            logger.info(f"Role {role_name} interval set to {hours}h for server {self.server_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting role interval for {role_name}: {e}")
            return False

    def get_all_roles(self) -> list[dict]:
        """Get all roles with their states from the dedicated roles table."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT role_name, enabled, interval_hours, config_data, updated_at, updated_by
                FROM roles
                ORDER BY role_name
            ''')
            results = cursor.fetchall()
            
            conn.close()
            
            roles = []
            for row in results:
                roles.append({
                    'role_name': row[0],
                    'enabled': bool(row[1]),
                    'interval_hours': row[2],
                    'config_data': row[3],
                    'updated_at': row[4],
                    'updated_by': row[5]
                })
            
            return roles
            
        except Exception as e:
            logger.error(f"Error getting all roles: {e}")
            return []

    def load_default_roles(self, default_roles: list[str], updated_by: str = None):
        """Load default roles if they don't exist."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            for role_name in default_roles:
                cursor.execute("SELECT role_name FROM roles WHERE role_name = ?", (role_name,))
                if cursor.fetchone() is None:
                    cursor.execute('''
                        INSERT INTO roles (role_name, enabled, updated_at, updated_by)
                        VALUES (?, 1, CURRENT_TIMESTAMP, ?)
                    ''', (role_name, updated_by or 'system'))
            
            conn.commit()
            conn.close()
            logger.info(f"Default roles loaded for server {self.server_key}")
            
        except Exception as e:
            logger.error(f"Error loading default roles: {e}")
    
    def get_commentary_state(self) -> dict:
        """Get commentary state with config."""
        return self.get_behavior_state('commentary')
    
    def set_commentary_state(self, enabled: bool, config: dict = None, updated_by: str = None):
        """Set commentary state with config."""
        self.set_behavior_state('commentary', enabled, config, updated_by)
    
    def get_all_behaviors(self) -> dict:
        """Get all behavior states."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT behavior_name, enabled, config_data FROM behavior_states")
            results = cursor.fetchall()
            
            conn.close()
            
            behaviors = {}
            for behavior_name, enabled, config_data in results:
                config = json.loads(config_data) if config_data else {}
                behaviors[behavior_name] = {
                    'enabled': bool(enabled),
                    'config': config
                }
            
            return behaviors
            
        except Exception as e:
            logger.error(f"Error getting all behaviors: {e}")
            return {}
    
    def get_all_settings(self) -> dict:
        """Get all behavior settings (backward compatibility)."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT key, value FROM behavior_settings")
            results = cursor.fetchall()
            
            conn.close()
            
            settings = {}
            for key, value in results:
                try:
                    settings[key] = json.loads(value)
                except:
                    settings[key] = value
            
            return settings
            
        except Exception as e:
            logger.error(f"Error getting all behavior settings: {e}")
            return {}
    
    def get_stats(self) -> dict:
        """Get behavior statistics."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get total behaviors
            cursor.execute("SELECT COUNT(*) FROM behavior_states")
            total_behaviors = cursor.fetchone()[0]
            
            # Get enabled behaviors
            cursor.execute("SELECT COUNT(*) FROM behavior_states WHERE enabled = 1")
            enabled_behaviors = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                'total_behaviors': total_behaviors,
                'enabled_behaviors': enabled_behaviors,
                'disabled_behaviors': total_behaviors - enabled_behaviors
            }
            
        except Exception as e:
            logger.error(f"Error getting behavior stats: {e}")
            return {
                'total_behaviors': 0,
                'enabled_behaviors': 0,
                'disabled_behaviors': 0
            }
    
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
    if server_key not in _behavior_db_instances:
        _behavior_db_instances[server_key] = BehaviorDB(server_key)
    return _behavior_db_instances[server_key]
