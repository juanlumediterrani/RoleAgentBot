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
        """Get persisted enabled state for a role."""
        state = self.get_feature_state(f'role:{role_name}')
        config = state.get('config') or {}
        if not state.get('enabled') and not config and default_enabled:
            return True
        return bool(state.get('enabled', default_enabled))

    def set_role_enabled(self, role_name: str, enabled: bool, updated_by: str = None):
        """Persist enabled state for a role."""
        self.set_feature_state(f'role:{role_name}', enabled, None, updated_by)

    def get_role_interval_hours(self, role_name: str, default_value: int = 1) -> int:
        """Get persisted interval for a role."""
        value = self.get_feature_setting(f'role:{role_name}', 'interval_hours', default_value)
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default_value)

    def set_role_interval_hours(self, role_name: str, hours: int, updated_by: str = None):
        """Persist interval for a role."""
        self.set_feature_setting(f'role:{role_name}', 'interval_hours', int(hours), updated_by)
    
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

# Global instance cache
_behavior_db_instances: dict[str, BehaviorDB] = {}

def get_behavior_db_instance(server_key: str) -> BehaviorDB:
    """Get or create a behavior database instance for a server."""
    if server_key not in _behavior_db_instances:
        _behavior_db_instances[server_key] = BehaviorDB(server_key)
    return _behavior_db_instances[server_key]
