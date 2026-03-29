"""
Roles Database Module
Centralized database management for all roles and subroles configuration.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
import threading
from agent_logging import get_logger
from agent_db import get_server_db_path_fallback

logger = get_logger('agent_roles_db')


def get_roles_db_path(server_name: str = "default") -> Path:
    """Generate database path for roles configuration."""
    db_name = "roles"
    return get_server_db_path_fallback(server_name, db_name)


class RolesDatabase:
    """Centralized database handler for all roles configuration."""
    
    def __init__(self, server_name: str = "default"):
        """Initialize database connection using roles.db."""
        self.server_name = server_name
        self.db_path = get_roles_db_path(server_name)
        self._lock = threading.RLock()
        self._init_tables()
    
    def _init_tables(self):
        """Initialize roles configuration tables."""
        try:
            # Ensure database directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL;")
                    
                    # Nordic Runes table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS nordic_runes (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id TEXT NOT NULL,
                            server_id TEXT,
                            question TEXT,
                            runes_drawn TEXT NOT NULL,
                            interpretation TEXT NOT NULL,
                            reading_type TEXT NOT NULL,
                            created_at TEXT NOT NULL
                        )
                    """)
                    
                    # Ring accusations history table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS ring_accusations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            server_id TEXT NOT NULL,
                            accuser_id TEXT,
                            accused_id TEXT,
                            accusation TEXT,
                            evidence TEXT,
                            created_at TEXT NOT NULL
                        )
                    """)
                    
                    # Dice Game statistics table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS dice_game_stats (
                            user_id TEXT NOT NULL,
                            server_id TEXT NOT NULL,
                            total_plays INTEGER DEFAULT 0,
                            total_bet INTEGER DEFAULT 0,
                            total_won INTEGER DEFAULT 0,
                            pots_won INTEGER DEFAULT 0,
                            biggest_prize INTEGER DEFAULT 0,
                            last_play TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            PRIMARY KEY (user_id, server_id)
                        )
                    """)
                    
                    # Banker wallets and transactions table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS banker_wallets (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            wallet_id TEXT NOT NULL,
                            user_id TEXT NOT NULL,
                            user_name TEXT NOT NULL,
                            server_id TEXT NOT NULL,
                            server_name TEXT NOT NULL,
                            balance INTEGER DEFAULT 0,
                            wallet_type TEXT DEFAULT 'user',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE(wallet_id, server_id)
                        )
                    """)
                    
                    # Banker transactions table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS banker_transactions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            from_wallet TEXT NOT NULL,
                            to_wallet TEXT NOT NULL,
                            amount INTEGER NOT NULL,
                            transaction_type TEXT NOT NULL,
                            description TEXT,
                            server_id TEXT NOT NULL,
                            created_by TEXT,
                            created_at TEXT NOT NULL
                        )
                    """)
                    
                    # Roles and subroles configuration table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS roles_config (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            role_name TEXT NOT NULL,
                            server_id TEXT NOT NULL,
                            enabled BOOLEAN DEFAULT 1,
                            config_data TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE(role_name, server_id)
                        )
                    """)
                    
                    # Dice Game games history table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS dice_game_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id TEXT NOT NULL,
                            user_name TEXT NOT NULL,
                            server_id TEXT NOT NULL,
                            server_name TEXT NOT NULL,
                            bet INTEGER NOT NULL,
                            dice TEXT NOT NULL,
                            combination TEXT NOT NULL,
                            prize INTEGER NOT NULL,
                            pot_before INTEGER NOT NULL,
                            pot_after INTEGER NOT NULL,
                            created_at TEXT NOT NULL
                        )
                    """)
                    
                    # Create indexes for nordic_runes
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nordic_runes_user_id ON nordic_runes(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nordic_runes_created_at ON nordic_runes(created_at)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nordic_runes_server_id ON nordic_runes(server_id)")
                    
                    # Create indexes for ring tables
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ring_accusations_server_id ON ring_accusations(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ring_accusations_created_at ON ring_accusations(created_at)")
                    
                    # Create indexes for dice game tables
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dice_game_history_server_id ON dice_game_history(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dice_game_history_user_id ON dice_game_history(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dice_game_history_created_at ON dice_game_history(created_at)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dice_game_stats_server_id ON dice_game_stats(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dice_game_stats_user_id ON dice_game_stats(user_id)")
                    
                    # Create indexes for roles config table
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_roles_config_server_id ON roles_config(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_roles_config_role_name ON roles_config(role_name)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_roles_config_enabled ON roles_config(enabled)")
                    
                    # Create indexes for banker tables
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_wallets_server_id ON banker_wallets(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_wallets_user_id ON banker_wallets(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_wallets_wallet_id ON banker_wallets(wallet_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_transactions_server_id ON banker_transactions(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_transactions_from_wallet ON banker_transactions(from_wallet)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_transactions_to_wallet ON banker_transactions(to_wallet)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_transactions_created_at ON banker_transactions(created_at)")
                    
                    conn.commit()
                    logger.info(f"Roles database initialized at: {self.db_path}")
                    
        except Exception as e:
            logger.error(f"Failed to initialize roles database: {e}")
            raise
    
    def save_nordic_runes_reading(self, user_id: str, server_id: Optional[str], 
                                 question: str, runes_drawn: List[str], 
                                 interpretation: str, reading_type: str) -> int:
        """Save a rune reading to the database."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT INTO nordic_runes 
                        (user_id, server_id, question, runes_drawn, interpretation, reading_type, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id, server_id, question, 
                        json.dumps(runes_drawn), interpretation, 
                        reading_type, datetime.now().isoformat()
                    ))
                    
                    reading_id = cursor.lastrowid
                    conn.commit()
                    
                    logger.info(f"Saved nordic runes reading {reading_id} for user {user_id}")
                    return reading_id
                    
        except Exception as e:
            logger.error(f"Failed to save nordic runes reading: {e}")
            raise
    
    def get_nordic_runes_readings(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent rune readings for a user."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT id, question, runes_drawn, interpretation, reading_type, created_at
                        FROM nordic_runes
                        WHERE user_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (user_id, limit))
                    
                    readings = []
                    for row in cursor.fetchall():
                        readings.append({
                            'id': row[0],
                            'question': row[1],
                            'runes_drawn': json.loads(row[2]),
                            'interpretation': row[3],
                            'reading_type': row[4],
                            'created_at': row[5]
                        })
                    
                    return readings
                    
        except Exception as e:
            logger.error(f"Failed to get user readings: {e}")
            return []
    
    def get_nordic_runes_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics for a user's rune readings."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # Total readings
                    cursor.execute("SELECT COUNT(*) FROM nordic_runes WHERE user_id = ?", (user_id,))
                    total_readings = cursor.fetchone()[0]
                    
                    # Most common reading type
                    cursor.execute("""
                        SELECT reading_type, COUNT(*) as count
                        FROM nordic_runes
                        WHERE user_id = ?
                        GROUP BY reading_type
                        ORDER BY count DESC
                        LIMIT 1
                    """, (user_id,))
                    result = cursor.fetchone()
                    favorite_type = result[0] if result else None
                    
                    return {
                        'total_readings': total_readings,
                        'favorite_type': favorite_type
                    }
                    
        except Exception as e:
            logger.error(f"Failed to get reading stats: {e}")
            return {'total_readings': 0, 'favorite_type': None}
    
    def save_ring_accusation(self, server_id: str, accuser_id: str, accused_id: str, 
                           accusation: str, evidence: str = None) -> int:
        """Save a ring accusation to the database."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT INTO ring_accusations 
                        (server_id, accuser_id, accused_id, accusation, evidence, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        server_id, accuser_id, accused_id, accusation, 
                        evidence, datetime.now().isoformat()
                    ))
                    
                    accusation_id = cursor.lastrowid
                    conn.commit()
                    
                    logger.info(f"Saved ring accusation {accusation_id} for server {server_id}")
                    return accusation_id
                    
        except Exception as e:
            logger.error(f"Failed to save ring accusation: {e}")
            raise
    
    def get_ring_accusations(self, server_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent ring accusations for a server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT id, accuser_id, accused_id, accusation, evidence, created_at
                        FROM ring_accusations
                        WHERE server_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (server_id, limit))
                    
                    accusations = []
                    for row in cursor.fetchall():
                        accusations.append({
                            'id': row[0],
                            'accuser_id': row[1],
                            'accused_id': row[2],
                            'accusation': row[3],
                            'evidence': row[4],
                            'created_at': row[5]
                        })
                    
                    return accusations
                    
        except Exception as e:
            logger.error(f"Failed to get ring accusations: {e}")
            return []
    
    def save_dice_game_stats(self, user_id: str, server_id: str, total_plays: int = 0, 
                            total_bet: int = 0, total_won: int = 0, pots_won: int = 0, 
                            biggest_prize: int = 0, last_play: str = None) -> bool:
        """Save or update dice game statistics for a user."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO dice_game_stats 
                        (user_id, server_id, total_plays, total_bet, total_won, pots_won, 
                         biggest_prize, last_play, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id, server_id, total_plays, total_bet, total_won, 
                        pots_won, biggest_prize, last_play, 
                        datetime.now().isoformat(), datetime.now().isoformat()
                    ))
                    
                    conn.commit()
                    logger.info(f"Saved dice game stats for user {user_id} in server {server_id}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to save dice game stats: {e}")
            return False
    
    def get_dice_game_stats(self, user_id: str, server_id: str) -> Dict[str, Any]:
        """Get dice game statistics for a user."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT total_plays, total_bet, total_won, pots_won, biggest_prize, last_play, created_at, updated_at
                        FROM dice_game_stats
                        WHERE user_id = ? AND server_id = ?
                    """, (user_id, server_id))
                    
                    result = cursor.fetchone()
                    if result:
                        return {
                            'total_plays': result[0],
                            'total_bet': result[1],
                            'total_won': result[2],
                            'pots_won': result[3],
                            'biggest_prize': result[4],
                            'last_play': result[5],
                            'created_at': result[6],
                            'updated_at': result[7]
                        }
                    else:
                        return {
                            'total_plays': 0,
                            'total_bet': 0,
                            'total_won': 0,
                            'pots_won': 0,
                            'biggest_prize': 0,
                            'last_play': None,
                            'created_at': None,
                            'updated_at': None
                        }
                    
        except Exception as e:
            logger.error(f"Failed to get dice game stats: {e}")
            return {}
    
    def save_dice_game_play(self, user_id: str, user_name: str, server_id: str, server_name: str,
                           bet: int, dice: str, combination: str, prize: int, 
                           pot_before: int, pot_after: int) -> int:
        """Save a dice game play to the database."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT INTO dice_game_history 
                        (user_id, user_name, server_id, server_name, bet, dice, combination, 
                         prize, pot_before, pot_after, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id, user_name, server_id, server_name, bet, dice, 
                        combination, prize, pot_before, pot_after, datetime.now().isoformat()
                    ))
                    
                    play_id = cursor.lastrowid
                    conn.commit()
                    
                    logger.info(f"Saved dice game play {play_id} for user {user_id}")
                    return play_id
                    
        except Exception as e:
            logger.error(f"Failed to save dice game play: {e}")
            raise
    
    def get_dice_game_history(self, server_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent dice game plays for a server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT id, user_id, user_name, server_id, server_name, bet, dice, 
                               combination, prize, pot_before, pot_after, created_at
                        FROM dice_game_history
                        WHERE server_id = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (server_id, limit))
                    
                    plays = []
                    for row in cursor.fetchall():
                        plays.append({
                            'id': row[0],
                            'user_id': row[1],
                            'user_name': row[2],
                            'server_id': row[3],
                            'server_name': row[4],
                            'bet': row[5],
                            'dice': row[6],
                            'combination': row[7],
                            'prize': row[8],
                            'pot_before': row[9],
                            'pot_after': row[10],
                            'created_at': row[11]
                        })
                    
                    return plays
                    
        except Exception as e:
            logger.error(f"Failed to get dice game history: {e}")
            return []
    
    def save_role_config(self, role_name: str, server_id: str, enabled: bool, config_data: str = None) -> bool:
        """Save role configuration and toggle status - same pattern as behavior.db."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO roles_config 
                        (role_name, server_id, enabled, config_data, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        role_name, server_id, enabled, config_data,
                        datetime.now().isoformat(), datetime.now().isoformat()
                    ))
                    
                    conn.commit()
                    logger.info(f"Saved role config for {role_name} in server {server_id}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to save role config: {e}")
            return False
    
    def get_role_config(self, role_name: str, server_id: str, default_enabled: bool = False) -> Dict[str, Any]:
        """Get role configuration and toggle status - same pattern as behavior.db."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT enabled, config_data, created_at, updated_at
                        FROM roles_config
                        WHERE role_name = ? AND server_id = ?
                    """, (role_name, server_id))
                    
                    result = cursor.fetchone()
                    if result is not None:
                        return {
                            'enabled': bool(result[0]),
                            'config_data': result[1],
                            'created_at': result[2],
                            'updated_at': result[3]
                        }
                    else:
                        # If role doesn't exist in database, create it with default value
                        self.save_role_config(role_name, server_id, default_enabled, '{}')
                        return {
                            'enabled': default_enabled,
                            'config_data': '{}',
                            'created_at': datetime.now().isoformat(),
                            'updated_at': datetime.now().isoformat()
                        }
                    
        except Exception as e:
            logger.error(f"Failed to get role config: {e}")
            return {
                'enabled': default_enabled,
                'config_data': '{}',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
    
    def is_role_enabled(self, role_name: str, server_id: str) -> bool:
        """Check if a role is enabled for a server."""
        config = self.get_role_config(role_name, server_id)
        return config.get('enabled', True)
    
    def set_role_enabled(self, role_name: str, server_id: str, enabled: bool) -> bool:
        """Enable or disable a role for a server."""
        return self.save_role_config(role_name, server_id, enabled)
    
    def migrate_roles_from_behavior(self, server_id: str) -> bool:
        """Migrate roles from behavior.db to roles_config - create new roles and update existing ones."""
        try:
            from behavior.db_behavior import get_behavior_db_instance
            behavior_db = get_behavior_db_instance(server_id)
            
            # Get all roles from behavior.db
            conn_behavior = sqlite3.connect(behavior_db.db_path)
            cursor_behavior = conn_behavior.cursor()
            
            cursor_behavior.execute("SELECT role_name, enabled FROM roles ORDER BY role_name")
            behavior_roles = cursor_behavior.fetchall()
            
            conn_behavior.close()
            
            if not behavior_roles:
                logger.info(f"No roles found in behavior.db for server {server_id}")
                return False
            
            migrated = 0
            updated = 0
            
            for role_name, enabled in behavior_roles:
                # Check if role already exists in roles_config
                existing_config = self.get_role_config(role_name, server_id)
                
                if existing_config and existing_config.get('created_at'):
                    # Role exists, update if different
                    if existing_config.get('enabled') != bool(enabled):
                        config_data = existing_config.get('config_data', '{}')
                        if not config_data:
                            config_data = '{}'
                        
                        # Add migration info to config_data
                        try:
                            import json
                            data = json.loads(config_data) if config_data else {}
                        except:
                            data = {}
                        
                        data['migrated_from_behavior'] = True
                        data['migration_date'] = datetime.now().isoformat()
                        data['original_enabled'] = bool(enabled)
                        
                        success = self.save_role_config(role_name, server_id, bool(enabled), json.dumps(data))
                        if success:
                            updated += 1
                            logger.info(f"Updated role {role_name} from behavior.db: enabled={bool(enabled)}")
                        else:
                            logger.error(f"Failed to update role {role_name} from behavior.db")
                    else:
                        logger.info(f"Role {role_name} already exists with same state")
                else:
                    # Role doesn't exist, create it
                    config_data = {
                        'migrated_from_behavior': True,
                        'migration_date': datetime.now().isoformat(),
                        'original_enabled': bool(enabled)
                    }
                    
                    success = self.save_role_config(role_name, server_id, bool(enabled), json.dumps(config_data))
                    if success:
                        migrated += 1
                        logger.info(f"Migrated role {role_name} from behavior.db: enabled={bool(enabled)}")
                    else:
                        logger.error(f"Failed to migrate role {role_name} from behavior.db")
            
            logger.info(f"Migration completed: {migrated} new roles, {updated} updated roles from behavior.db to roles_config")
            return (migrated + updated) > 0
            
        except Exception as e:
            logger.error(f"Error migrating roles from behavior.db: {e}")
            return False
    
    def ensure_default_roles(self, server_id: str) -> bool:
        """Ensure all default roles exist in roles_config."""
        try:
            default_roles = {
                'banker': True,
                'news_watcher': True,
                'treasure_hunter': True,
                'trickster': True,
                'mc': True,
                'ring': True,
                'dice_game': True
            }
            
            created = 0
            for role_name, default_enabled in default_roles.items():
                config = self.get_role_config(role_name, server_id, default_enabled)
                if config and config.get('created_at'):
                    # Role exists
                    continue
                else:
                    # Role was created by get_role_config with default
                    created += 1
            
            if created > 0:
                logger.info(f"Ensured {created} default roles exist in roles_config for server {server_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error ensuring default roles: {e}")
            return False
    
    def migrate_roles_from_agent_config(self, server_id: str, agent_config_path: str = None) -> bool:
        """Migrate roles from agent_config.json to roles_config - first time initialization."""
        try:
            import json
            import os
            
            # Default path to agent_config.json
            if agent_config_path is None:
                agent_config_path = os.path.join(os.path.dirname(__file__), '..', 'agent_config.json')
            
            if not os.path.exists(agent_config_path):
                logger.info(f"agent_config.json not found at {agent_config_path}")
                return False
            
            # Load agent_config.json
            with open(agent_config_path, 'r', encoding='utf-8') as f:
                agent_config = json.load(f)
            
            roles_cfg = agent_config.get("roles", {})
            if not roles_cfg:
                logger.info("No roles found in agent_config.json")
                return False
            
            logger.info(f"Found {len(roles_cfg)} roles in agent_config.json")
            
            migrated = 0
            updated = 0
            
            for role_name, role_config in roles_cfg.items():
                if not isinstance(role_config, dict):
                    continue
                
                # Extract enabled state and additional config
                enabled = role_config.get("enabled", False)
                
                # Prepare config_data with all role information
                config_data = {
                    'source': 'agent_config_migration',
                    'migration_date': datetime.now().isoformat(),
                    'original_enabled': enabled,
                    'agent_config': role_config  # Preserve full original config
                }
                
                # Add specific configurations for different roles
                if role_name == 'trickster' and 'subroles' in role_config:
                    # Handle trickster subroles
                    subroles = role_config.get('subroles', {})
                    config_data['subroles'] = subroles
                    
                    # Create separate entries for subroles
                    for subrole_name, subrole_config in subroles.items():
                        if isinstance(subrole_config, dict):
                            subrole_enabled = subrole_config.get('enabled', False)
                            subrole_data = {
                                'source': 'agent_config_migration',
                                'migration_date': datetime.now().isoformat(),
                                'parent_role': role_name,
                                'subrole_config': subrole_config,
                                'original_enabled': subrole_enabled
                            }
                            
                            success = self.save_role_config(subrole_name, server_id, subrole_enabled, json.dumps(subrole_data))
                            if success:
                                migrated += 1
                                logger.info(f"Migrated subrole {subrole_name} from agent_config: enabled={subrole_enabled}")
                
                # Check if role already exists
                existing_config = self.get_role_config(role_name, server_id)
                if existing_config and existing_config.get('created_at'):
                    # Role exists, update if different
                    if existing_config.get('enabled') != enabled:
                        # Preserve existing config_data but update enabled
                        existing_config_data = existing_config.get('config_data', '{}')
                        try:
                            existing_data = json.loads(existing_config_data) if existing_config_data else {}
                        except:
                            existing_data = {}
                        
                        # Update with agent_config data
                        existing_data.update(config_data)
                        existing_data['updated_from_agent_config'] = True
                        
                        success = self.save_role_config(role_name, server_id, enabled, json.dumps(existing_data))
                        if success:
                            updated += 1
                            logger.info(f"Updated role {role_name} from agent_config: enabled={enabled}")
                    else:
                        logger.info(f"Role {role_name} already exists with same enabled state")
                else:
                    # Role doesn't exist, create it
                    success = self.save_role_config(role_name, server_id, enabled, json.dumps(config_data))
                    if success:
                        migrated += 1
                        logger.info(f"Migrated role {role_name} from agent_config: enabled={enabled}")
            
            logger.info(f"Migration from agent_config completed: {migrated} new roles, {updated} updated roles")
            return (migrated + updated) > 0
            
        except Exception as e:
            logger.error(f"Error migrating roles from agent_config: {e}")
            return False
    
    def save_banker_wallet(self, wallet_id: str, user_id: str, user_name: str, 
                           server_id: str, server_name: str, balance: int = 0, 
                           wallet_type: str = 'user') -> bool:
        """Save or update a banker wallet."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO banker_wallets 
                        (wallet_id, user_id, user_name, server_id, server_name, balance, 
                         wallet_type, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        wallet_id, user_id, user_name, server_id, server_name, 
                        balance, wallet_type, datetime.now().isoformat(), datetime.now().isoformat()
                    ))
                    
                    conn.commit()
                    logger.info(f"Saved banker wallet {wallet_id} for user {user_name}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to save banker wallet: {e}")
            return False
    
    def get_banker_wallet(self, wallet_id: str, server_id: str) -> Dict[str, Any]:
        """Get a banker wallet by ID and server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT wallet_id, user_id, user_name, server_id, server_name, 
                               balance, wallet_type, created_at, updated_at
                        FROM banker_wallets
                        WHERE wallet_id = ? AND server_id = ?
                    """, (wallet_id, server_id))
                    
                    result = cursor.fetchone()
                    if result:
                        return {
                            'wallet_id': result[0],
                            'user_id': result[1],
                            'user_name': result[2],
                            'server_id': result[3],
                            'server_name': result[4],
                            'balance': result[5],
                            'wallet_type': result[6],
                            'created_at': result[7],
                            'updated_at': result[8]
                        }
                    else:
                        return None
                    
        except Exception as e:
            logger.error(f"Failed to get banker wallet: {e}")
            return None
    
    def update_banker_balance(self, wallet_id: str, server_id: str, new_balance: int) -> bool:
        """Update banker wallet balance."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        UPDATE banker_wallets 
                        SET balance = ?, updated_at = ?
                        WHERE wallet_id = ? AND server_id = ?
                    """, (new_balance, datetime.now().isoformat(), wallet_id, server_id))
                    
                    conn.commit()
                    logger.info(f"Updated balance for wallet {wallet_id} to {new_balance}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to update banker balance: {e}")
            return False
    
    def save_banker_transaction(self, from_wallet: str, to_wallet: str, amount: int, 
                                transaction_type: str, server_id: str, 
                                description: str = None, created_by: str = None) -> int:
        """Save a banker transaction."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT INTO banker_transactions 
                        (from_wallet, to_wallet, amount, transaction_type, description, 
                         server_id, created_by, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        from_wallet, to_wallet, amount, transaction_type, description,
                        server_id, created_by, datetime.now().isoformat()
                    ))
                    
                    transaction_id = cursor.lastrowid
                    conn.commit()
                    
                    logger.info(f"Saved banker transaction {transaction_id}: {from_wallet} -> {to_wallet}, {amount} coins")
                    return transaction_id
                    
        except Exception as e:
            logger.error(f"Failed to save banker transaction: {e}")
            raise
    
    def get_banker_transactions(self, server_id: str, wallet_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get banker transactions for a server (optionally filtered by wallet)."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    if wallet_id:
                        cursor.execute("""
                            SELECT id, from_wallet, to_wallet, amount, transaction_type, 
                                   description, server_id, created_by, created_at
                            FROM banker_transactions
                            WHERE server_id = ? AND (from_wallet = ? OR to_wallet = ?)
                            ORDER BY created_at DESC
                            LIMIT ?
                        """, (server_id, wallet_id, wallet_id, limit))
                    else:
                        cursor.execute("""
                            SELECT id, from_wallet, to_wallet, amount, transaction_type, 
                                   description, server_id, created_by, created_at
                            FROM banker_transactions
                            WHERE server_id = ?
                            ORDER BY created_at DESC
                            LIMIT ?
                        """, (server_id, limit))
                    
                    transactions = []
                    for row in cursor.fetchall():
                        transactions.append({
                            'id': row[0],
                            'from_wallet': row[1],
                            'to_wallet': row[2],
                            'amount': row[3],
                            'transaction_type': row[4],
                            'description': row[5],
                            'server_id': row[6],
                            'created_by': row[7],
                            'created_at': row[8]
                        })
                    
                    return transactions
                    
        except Exception as e:
            logger.error(f"Failed to get banker transactions: {e}")
            return []
    
    def get_all_banker_wallets(self, server_id: str) -> List[Dict[str, Any]]:
        """Get all banker wallets for a server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT wallet_id, user_id, user_name, server_id, server_name, 
                               balance, wallet_type, created_at, updated_at
                        FROM banker_wallets
                        WHERE server_id = ?
                        ORDER BY created_at DESC
                    """, (server_id,))
                    
                    wallets = []
                    for row in cursor.fetchall():
                        wallets.append({
                            'wallet_id': row[0],
                            'user_id': row[1],
                            'user_name': row[2],
                            'server_id': row[3],
                            'server_name': row[4],
                            'balance': row[5],
                            'wallet_type': row[6],
                            'created_at': row[7],
                            'updated_at': row[8]
                        })
                    
                    return wallets
                    
        except Exception as e:
            logger.error(f"Failed to get all banker wallets: {e}")
            return []


# Global database instance
_roles_db_instance = None

def get_roles_db_instance(server_name: str = "default") -> RolesDatabase:
    """Get the roles database instance for a specific server."""
    global _roles_db_instance
    if _roles_db_instance is None or _roles_db_instance.server_name != server_name:
        _roles_db_instance = RolesDatabase(server_name)
    return _roles_db_instance
