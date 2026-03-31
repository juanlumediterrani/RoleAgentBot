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
from agent_db import get_server_db_path_fallback, get_database_path

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

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS poe2_subscriptions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id TEXT NOT NULL,
                            server_id TEXT NOT NULL,
                            league TEXT NOT NULL DEFAULT 'Standard',
                            tracked_items TEXT DEFAULT '[]',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE(user_id, server_id)
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
                    
                    # Beggar subrole table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS beggar_subrole (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            server_id TEXT NOT NULL,
                            user_id TEXT NOT NULL,
                            user_name TEXT NOT NULL,
                            total_donated INTEGER DEFAULT 0,
                            weekly_donated INTEGER DEFAULT 0,
                            donation_count INTEGER DEFAULT 0,
                            weekly_donation_count INTEGER DEFAULT 0,
                            first_donation TEXT,
                            last_donation TEXT,
                            last_donation_amount INTEGER DEFAULT 0,
                            last_reason TEXT DEFAULT '',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL,
                            UNIQUE(server_id, user_id)
                        )
                    """)
                    
                    # Beggar request history table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS beggar_request_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            server_id TEXT NOT NULL,
                            user_id TEXT NOT NULL,
                            user_name TEXT NOT NULL,
                            request_type TEXT NOT NULL,
                            message TEXT NOT NULL,
                            channel_id TEXT,
                            metadata TEXT,
                            created_at TEXT NOT NULL
                        )
                    """)
                    
                    for migration_sql in [
                        "ALTER TABLE beggar_subrole ADD COLUMN weekly_donated INTEGER DEFAULT 0",
                        "ALTER TABLE beggar_subrole ADD COLUMN weekly_donation_count INTEGER DEFAULT 0",
                        "ALTER TABLE beggar_subrole ADD COLUMN last_donation_amount INTEGER DEFAULT 0",
                        "ALTER TABLE beggar_subrole ADD COLUMN last_reason TEXT DEFAULT ''",
                    ]:
                        try:
                            cursor.execute(migration_sql)
                        except sqlite3.OperationalError as migration_error:
                            if "duplicate column name" not in str(migration_error).lower():
                                raise
                    
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
                    
                    # Create indexes for beggar subrole table
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_subrole_server_id ON beggar_subrole(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_subrole_user_id ON beggar_subrole(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_subrole_total_donated ON beggar_subrole(total_donated)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_subrole_weekly_donated ON beggar_subrole(weekly_donated)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_subrole_created_at ON beggar_subrole(created_at)")
                    
                    # Create indexes for beggar request history table
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_request_history_server_id ON beggar_request_history(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_request_history_request_type ON beggar_request_history(request_type)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_request_history_created_at ON beggar_request_history(created_at)")
                    
                    # Create indexes for roles config table
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_roles_config_server_id ON roles_config(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_roles_config_role_name ON roles_config(role_name)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_roles_config_enabled ON roles_config(enabled)")

                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poe2_subscriptions_server_id ON poe2_subscriptions(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poe2_subscriptions_user_id ON poe2_subscriptions(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poe2_subscriptions_league ON poe2_subscriptions(league)")
                    
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

    def save_poe2_subscription(self, user_id: str, server_id: str, league: str = "Standard", tracked_items: Optional[List[str]] = None) -> bool:
        """Create or update a POE2 subscription for a user on a server."""
        try:
            tracked_items_json = json.dumps(tracked_items or [])
            now = datetime.now().isoformat()
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO poe2_subscriptions
                        (user_id, server_id, league, tracked_items, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, server_id) DO UPDATE SET
                            league = excluded.league,
                            tracked_items = excluded.tracked_items,
                            updated_at = excluded.updated_at
                    ''', (user_id, server_id, league, tracked_items_json, now, now))
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Failed to save POE2 subscription for user {user_id} in server {server_id}: {e}")
            return False

    def get_poe2_subscription(self, user_id: str, server_id: str) -> Optional[Dict[str, Any]]:
        """Get a POE2 subscription for a user on a server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT user_id, server_id, league, tracked_items, created_at, updated_at
                        FROM poe2_subscriptions
                        WHERE user_id = ? AND server_id = ?
                    ''', (user_id, server_id))
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    return {
                        'user_id': row[0],
                        'server_id': row[1],
                        'league': row[2],
                        'tracked_items': json.loads(row[3] or '[]'),
                        'created_at': row[4],
                        'updated_at': row[5],
                    }
        except Exception as e:
            logger.error(f"Failed to get POE2 subscription for user {user_id} in server {server_id}: {e}")
            return None

    def get_poe2_server_subscriptions(self, server_id: str) -> List[Dict[str, Any]]:
        """Get all POE2 subscriptions for a server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT user_id, server_id, league, tracked_items, created_at, updated_at
                        FROM poe2_subscriptions
                        WHERE server_id = ?
                        ORDER BY updated_at DESC, user_id ASC
                    ''', (server_id,))
                    rows = cursor.fetchall()
                    subscriptions = []
                    for row in rows:
                        subscriptions.append({
                            'user_id': row[0],
                            'server_id': row[1],
                            'league': row[2],
                            'tracked_items': json.loads(row[3] or '[]'),
                            'created_at': row[4],
                            'updated_at': row[5],
                        })
                    return subscriptions
        except Exception as e:
            logger.error(f"Failed to get POE2 subscriptions for server {server_id}: {e}")
            return []

    def delete_poe2_subscription(self, user_id: str, server_id: str) -> bool:
        """Delete a POE2 subscription for a user on a server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        DELETE FROM poe2_subscriptions
                        WHERE user_id = ? AND server_id = ?
                    ''', (user_id, server_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete POE2 subscription for user {user_id} in server {server_id}: {e}")
            return False

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
                            existing_subrole_config = self.get_role_config(subrole_name, server_id)
                            if existing_subrole_config and existing_subrole_config.get('created_at'):
                                if existing_subrole_config.get('enabled') != subrole_enabled:
                                    existing_subrole_config_data = existing_subrole_config.get('config_data', '{}')
                                    try:
                                        existing_subrole_data = json.loads(existing_subrole_config_data) if existing_subrole_config_data else {}
                                    except Exception:
                                        existing_subrole_data = {}

                                    existing_subrole_data.update(subrole_data)
                                    existing_subrole_data['updated_from_agent_config'] = True

                                    success = self.save_role_config(subrole_name, server_id, subrole_enabled, json.dumps(existing_subrole_data))
                                    if success:
                                        updated += 1
                                        logger.info(f"Updated subrole {subrole_name} from agent_config: enabled={subrole_enabled}")

                                        if subrole_name == 'beggar' and subrole_enabled:
                                            try:
                                                from roles.trickster.subroles.beggar.beggar_config import get_beggar_config
                                                beggar_config = get_beggar_config(server_id)

                                                if not beggar_config.get_current_reason():
                                                    selected_reason = beggar_config.select_new_reason()
                                                    logger.info(f"Initialized beggar reason during subrole update: {selected_reason}")
                                            except Exception as e:
                                                logger.warning(f"Failed to initialize beggar reason during subrole update: {e}")
                                else:
                                    logger.info(f"Subrole {subrole_name} already exists with same enabled state")
                            else:
                                success = self.save_role_config(subrole_name, server_id, subrole_enabled, json.dumps(subrole_data))
                                if success:
                                    migrated += 1
                                    logger.info(f"Migrated subrole {subrole_name} from agent_config: enabled={subrole_enabled}")
                                    
                                    # Special initialization for beggar subrole
                                    if subrole_name == 'beggar' and subrole_enabled:
                                        try:
                                            from roles.trickster.subroles.beggar.beggar_config import get_beggar_config
                                            beggar_config = get_beggar_config(server_id)
                                            
                                            # Check if reason is not already set
                                            if not beggar_config.get_current_reason():
                                                # Select initial reason for migrated beggar
                                                selected_reason = beggar_config.select_new_reason()
                                                logger.info(f"Initialized beggar reason during migration: {selected_reason}")
                                        except Exception as e:
                                            logger.warning(f"Failed to initialize beggar reason during migration: {e}")
                
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
                            
                            # Special initialization for beggar role when updated
                            if role_name == 'beggar' and enabled:
                                try:
                                    from roles.trickster.subroles.beggar.beggar_config import get_beggar_config
                                    beggar_config = get_beggar_config(server_id)
                                    
                                    # Check if reason is not already set
                                    if not beggar_config.get_current_reason():
                                        # Select initial reason for updated beggar
                                        selected_reason = beggar_config.select_new_reason()
                                        logger.info(f"Initialized beggar reason during update: {selected_reason}")
                                except Exception as e:
                                    logger.warning(f"Failed to initialize beggar reason during update: {e}")
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
    
    def migrate_legacy_beggar_data(self, server_id: str) -> bool:
        """Migrate legacy beggar data from the dedicated beggar database into roles.db."""
        legacy_path = Path(get_database_path(server_id, 'beggar'))
        if not legacy_path.exists():
            return False
        
        try:
            migrated_any = False
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    with sqlite3.connect(legacy_path) as legacy_conn:
                        legacy_cursor = legacy_conn.cursor()
                        
                        legacy_cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                        legacy_tables = {row[0] for row in legacy_cursor.fetchall()}
                        
                        if 'beggar_requests' in legacy_tables:
                            legacy_cursor.execute("""
                                SELECT user_id, user_name, request_type, message, channel_id, server_id, metadata, created_at
                                FROM beggar_requests
                                WHERE server_id = ?
                            """, (server_id,))
                            for row in legacy_cursor.fetchall():
                                cursor.execute("""
                                    INSERT INTO beggar_request_history
                                    (server_id, user_id, user_name, request_type, message, channel_id, metadata, created_at)
                                    SELECT ?, ?, ?, ?, ?, ?, ?, ?
                                    WHERE NOT EXISTS (
                                        SELECT 1
                                        FROM beggar_request_history
                                        WHERE server_id = ?
                                          AND user_id = ?
                                          AND request_type = ?
                                          AND message = ?
                                          AND created_at = ?
                                    )
                                """, (
                                    row[5] or server_id,
                                    row[0],
                                    row[1],
                                    row[2],
                                    row[3],
                                    row[4],
                                    row[6],
                                    row[7],
                                    row[5] or server_id,
                                    row[0],
                                    row[2],
                                    row[3],
                                    row[7],
                                ))
                                migrated_any = migrated_any or cursor.rowcount > 0
                        
                        if 'beggar_config' in legacy_tables:
                            legacy_cursor.execute("""
                                SELECT frequency_hours, last_reason, target_gold
                                FROM beggar_config
                                WHERE server_id = ?
                            """, (server_id,))
                            config_row = legacy_cursor.fetchone()
                            if config_row:
                                role_config = self.get_role_config('beggar', server_id)
                                config_data_raw = role_config.get('config_data') or '{}'
                                try:
                                    config_data = json.loads(config_data_raw)
                                except Exception:
                                    config_data = {}
                                if 'frequency_hours' not in config_data:
                                    config_data['frequency_hours'] = config_row[0]
                                if not config_data.get('current_reason') and config_row[1]:
                                    config_data['current_reason'] = config_row[1]
                                if 'target_gold' not in config_data:
                                    config_data['target_gold'] = config_row[2] or 0
                                enabled = role_config.get('enabled', False)
                                if not enabled and 'beggar_subscriptions' in legacy_tables:
                                    legacy_cursor.execute("""
                                        SELECT COUNT(*)
                                        FROM beggar_subscriptions
                                        WHERE server_id = ?
                                    """, (server_id,))
                                    enabled = (legacy_cursor.fetchone() or [0])[0] > 0
                                self.save_role_config('beggar', server_id, enabled, json.dumps(config_data))
                                migrated_any = True
                    conn.commit()
            if migrated_any:
                logger.info(f"Migrated legacy beggar data into roles.db for server {server_id}")
            return migrated_any
        except Exception as e:
            logger.error(f"Failed to migrate legacy beggar data: {e}")
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
                        (from_wallet, to_wallet, amount, transaction_type, server_id, 
                         description, created_by, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        from_wallet, to_wallet, amount, transaction_type, server_id,
                        description, created_by, datetime.now().isoformat()
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
    
    # Beggar subrole methods
    def update_beggar_donation(self, server_id: str, user_id: str, user_name: str, amount: int, reason: str = "") -> bool:
        """Update beggar donation record for a user."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # Check if user exists
                    cursor.execute("""
                        SELECT total_donated, weekly_donated, donation_count, weekly_donation_count
                        FROM beggar_subrole
                        WHERE server_id = ? AND user_id = ?
                    """, (server_id, user_id))
                    
                    result = cursor.fetchone()
                    now = datetime.now().isoformat()
                    
                    if result:
                        # Update existing record
                        new_total = result[0] + amount
                        new_weekly_total = result[1] + amount
                        new_count = result[2] + 1
                        new_weekly_count = result[3] + 1
                        
                        cursor.execute("""
                            UPDATE beggar_subrole 
                            SET total_donated = ?, weekly_donated = ?, donation_count = ?, weekly_donation_count = ?,
                                user_name = ?, last_donation = ?, last_donation_amount = ?, last_reason = ?, updated_at = ?
                            WHERE server_id = ? AND user_id = ?
                        """, (new_total, new_weekly_total, new_count, new_weekly_count, user_name, now, amount, reason, now, server_id, user_id))
                        
                        logger.info(f"Updated beggar donation for {user_name}: +{amount} (weekly: {new_weekly_total}, total: {new_total})")
                    else:
                        # Insert new record
                        cursor.execute("""
                            INSERT INTO beggar_subrole 
                            (server_id, user_id, user_name, total_donated, weekly_donated, donation_count,
                             weekly_donation_count, first_donation, last_donation, last_donation_amount, last_reason,
                             created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (server_id, user_id, user_name, amount, amount, 1, 1, now, now, amount, reason, now, now))
                        
                        logger.info(f"Created beggar record for {user_name}: {amount}")
                    
                    conn.commit()
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to update beggar donation: {e}")
            return False
    
    def save_beggar_request(self, server_id: str, user_id: str, user_name: str, request_type: str,
                            message: str, channel_id: Optional[str] = None,
                            metadata: Optional[str] = None) -> bool:
        """Save a beggar request event to roles.db."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT INTO beggar_request_history
                        (server_id, user_id, user_name, request_type, message, channel_id, metadata, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            server_id,
                            user_id,
                            user_name,
                            request_type,
                            message,
                            channel_id,
                            metadata,
                            datetime.now().isoformat(),
                        ),
                    )
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Failed to save beggar request: {e}")
            return False
    
    def count_beggar_requests_type_last_day(self, request_type: str, server_id: Optional[str] = None) -> int:
        """Count beggar request events of a specific type during the last 24 hours."""
        since_iso = datetime.fromtimestamp(datetime.now().timestamp() - 86400).isoformat()
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    if server_id:
                        cursor.execute(
                            """
                            SELECT COUNT(*)
                            FROM beggar_request_history
                            WHERE request_type = ? AND server_id = ? AND created_at > ?
                            """,
                            (request_type, server_id, since_iso),
                        )
                    else:
                        cursor.execute(
                            """
                            SELECT COUNT(*)
                            FROM beggar_request_history
                            WHERE request_type = ? AND created_at > ?
                            """,
                            (request_type, since_iso),
                        )
                    result = cursor.fetchone()
                    return int(result[0]) if result else 0
        except Exception as e:
            logger.error(f"Failed to count beggar requests: {e}")
            return 0
    
    def get_beggar_user_stats(self, server_id: str, user_id: str) -> Dict[str, Any]:
        """Get beggar statistics for a specific user."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT total_donated, weekly_donated, donation_count, weekly_donation_count,
                               first_donation, last_donation, last_donation_amount, last_reason,
                               created_at, updated_at
                        FROM beggar_subrole
                        WHERE server_id = ? AND user_id = ?
                    """, (server_id, user_id))
                    
                    result = cursor.fetchone()
                    if result:
                        return {
                            'total_donated': result[0],
                            'weekly_donated': result[1],
                            'donation_count': result[2],
                            'weekly_donation_count': result[3],
                            'first_donation': result[4],
                            'last_donation': result[5],
                            'last_donation_amount': result[6],
                            'last_reason': result[7],
                            'created_at': result[8],
                            'updated_at': result[9]
                        }
                    else:
                        return {
                            'total_donated': 0,
                            'weekly_donated': 0,
                            'donation_count': 0,
                            'weekly_donation_count': 0,
                            'first_donation': None,
                            'last_donation': None,
                            'last_donation_amount': 0,
                            'last_reason': '',
                            'created_at': None,
                            'updated_at': None
                        }
                    
        except Exception as e:
            logger.error(f"Failed to get beggar user stats: {e}")
            return {}
    
    def get_recent_beggar_donations(self, server_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get most recent beggar donations for a server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT user_id, user_name, last_donation_amount, donation_count, last_donation, last_reason,
                               weekly_donated, weekly_donation_count, total_donated
                        FROM beggar_subrole
                        WHERE server_id = ? AND (weekly_donated > 0 OR total_donated > 0)
                        ORDER BY datetime(last_donation) DESC, id DESC
                        LIMIT ?
                    """, (server_id, limit))
                    
                    recent_donations = []
                    for row in cursor.fetchall():
                        recent_donations.append({
                            'user_id': row[0],
                            'donor_name': row[1],
                            'amount': row[2],
                            'donation_count': row[3],
                            'last_donation': row[4],
                            'reason': row[5],
                            'weekly_donated': row[6],
                            'weekly_donation_count': row[7],
                            'total_donated': row[8],
                        })
                    
                    return recent_donations
                    
        except Exception as e:
            logger.error(f"Failed to get recent beggar donations: {e}")
            return []
    
    def get_beggar_leaderboard(self, server_id: str, limit: int = 10, weekly_only: bool = False) -> List[Dict[str, Any]]:
        """Get top beggar donors for a server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    donated_field = 'weekly_donated' if weekly_only else 'total_donated'
                    count_field = 'weekly_donation_count' if weekly_only else 'donation_count'
                    
                    cursor.execute(f"""
                        SELECT user_id, user_name, {donated_field}, {count_field},
                               last_donation, created_at, total_donated, weekly_donated, last_reason
                        FROM beggar_subrole
                        WHERE server_id = ? AND {donated_field} > 0
                        ORDER BY {donated_field} DESC
                        LIMIT ?
                    """, (server_id, limit))
                    
                    leaderboard = []
                    for row in cursor.fetchall():
                        leaderboard.append({
                            'user_id': row[0],
                            'user_name': row[1],
                            'total_donated': row[2],
                            'donation_count': row[3],
                            'last_donation': row[4],
                            'created_at': row[5],
                            'historical_total_donated': row[6],
                            'weekly_donated': row[7],
                            'last_reason': row[8]
                        })
                    
                    return leaderboard
                    
        except Exception as e:
            logger.error(f"Failed to get beggar leaderboard: {e}")
            return []
    
    def get_beggar_server_stats(self, server_id: str, weekly_only: bool = False) -> Dict[str, Any]:
        """Get overall beggar statistics for a server."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    donated_field = 'weekly_donated' if weekly_only else 'total_donated'
                    count_field = 'weekly_donation_count' if weekly_only else 'donation_count'
                    
                    # Total stats
                    cursor.execute(f"""
                        SELECT COUNT(*) as donors, 
                               COALESCE(SUM({donated_field}), 0) as total_gold,
                               COALESCE(SUM({count_field}), 0) as total_donations,
                               COALESCE(SUM(total_donated), 0) as historical_total_gold
                        FROM beggar_subrole
                        WHERE server_id = ? AND {donated_field} > 0
                    """, (server_id,))
                    
                    result = cursor.fetchone()
                    if result:
                        return {
                            'total_donors': result[0] or 0,
                            'total_gold': result[1] or 0,
                            'total_donations': result[2] or 0,
                            'historical_total_gold': result[3] or 0,
                            'period': 'weekly' if weekly_only else 'historical'
                        }
                    else:
                        return {
                            'total_donors': 0,
                            'total_gold': 0,
                            'total_donations': 0,
                            'historical_total_gold': 0,
                            'period': 'weekly' if weekly_only else 'historical'
                        }
                    
        except Exception as e:
            logger.error(f"Failed to get beggar server stats: {e}")
            return {
                'total_donors': 0,
                'total_gold': 0,
                'total_donations': 0,
                'historical_total_gold': 0,
                'period': 'weekly' if weekly_only else 'historical'
            }

    def reset_beggar_weekly_cycle(self, server_id: str) -> bool:
        """Reset weekly beggar donation counters for a server while preserving historical totals."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE beggar_subrole
                        SET weekly_donated = 0,
                            weekly_donation_count = 0,
                            updated_at = ?
                        WHERE server_id = ?
                    """, (datetime.now().isoformat(), server_id))
                    conn.commit()
                    logger.info(f"Reset beggar weekly cycle for server {server_id}: {cursor.rowcount} donor rows updated")
                    return True
        except Exception as e:
            logger.error(f"Failed to reset beggar weekly cycle: {e}")
            return False


# Global database instance
_roles_db_instance = None

def get_roles_db_instance(server_name: str = "default") -> RolesDatabase:
    """Get the roles database instance for a specific server."""
    global _roles_db_instance
    if _roles_db_instance is None or _roles_db_instance.server_name != server_name:
        _roles_db_instance = RolesDatabase(server_name)
    return _roles_db_instance
