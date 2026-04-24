"""
Roles Database Module
Centralized database management for all roles and subroles configuration.
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Any
from pathlib import Path
import threading
from agent_logging import get_logger
from agent_db import get_server_db_path_fallback, get_database_path

logger = get_logger('agent_roles_db')


def _get_config_hash(config_content: str) -> str:
    """Calculate MD5 hash of config content for caching."""
    return hashlib.md5(config_content.encode('utf-8')).hexdigest()


def get_roles_db_path(server_id: str = "default") -> Optional[Path]:
    """Generate database path for roles configuration.
    
    Returns None if personality cannot be determined to avoid creating
    placeholder databases in server directories.
    """
    from agent_db import get_personality_name
    personality_name = get_personality_name(server_id)
    logger.debug(f"[get_roles_db_path] server_id={server_id}, personality_name={personality_name}")
    
    # Don't create database if personality cannot be determined
    if not personality_name:
        logger.debug(f"[get_roles_db_path] Cannot determine personality for server {server_id}, skipping database creation")
        return None
    
    db_name = f"roles_{personality_name}"
    return get_server_db_path_fallback(server_id, db_name)


class RolesDatabase:
    """Centralized database handler for all roles configuration."""
    
    def __init__(self, server_id: str = None):
        """Initialize database connection using roles.db.
        
        Args:
            server_id: Server ID. Must be a valid server ID, not None or 'default'.
        
        Raises:
            ValueError: If server_id is None, 'default', or personality cannot be determined.
        """
        if not server_id or server_id == "default":
            raise ValueError(f"RolesDatabase requires a valid server_id, got: {server_id}")
        
        self.server_id = server_id
        db_path = get_roles_db_path(server_id)
        
        if not db_path:
            raise ValueError(f"Cannot determine database path for server {server_id} - personality not found")
        
        self.db_path = db_path
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
                            user_id TEXT NOT NULL PRIMARY KEY,
                            total_plays INTEGER DEFAULT 0,
                            total_bet INTEGER DEFAULT 0,
                            total_won INTEGER DEFAULT 0,
                            pots_won INTEGER DEFAULT 0,
                            biggest_prize INTEGER DEFAULT 0,
                            last_play TEXT,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )
                    """)
                    
                    # Banker wallets and transactions table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS banker_wallets (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            wallet_id TEXT NOT NULL UNIQUE,
                            user_name TEXT NOT NULL,
                            balance INTEGER DEFAULT 0,
                            wallet_type TEXT DEFAULT 'user',
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
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
                            created_by TEXT,
                            created_at TEXT NOT NULL
                        )
                    """)
                    
                    # News Watcher subscriptions table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS watcher_subscriptions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id TEXT,
                            channel_id TEXT,
                            category TEXT NOT NULL,
                            feed_id INTEGER,
                            premises TEXT,
                            keywords TEXT,
                            method TEXT NOT NULL DEFAULT 'general',
                            is_active INTEGER DEFAULT 1,
                            subscribed_at TEXT NOT NULL,
                            created_by TEXT,
                            UNIQUE(user_id, channel_id, category, method)
                        )
                    """)
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watcher_subscriptions_user ON watcher_subscriptions (user_id)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watcher_subscriptions_channel ON watcher_subscriptions (channel_id)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watcher_subscriptions_category ON watcher_subscriptions (category)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watcher_subscriptions_method ON watcher_subscriptions (method)')
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_watcher_subscriptions_active ON watcher_subscriptions (is_active)')
                    
                    # Migration: add created_by column to banker_transactions if it doesn't exist
                    cursor.execute("PRAGMA table_info(banker_transactions)")
                    columns = [row[1] for row in cursor.fetchall()]
                    if "created_by" not in columns:
                        cursor.execute("ALTER TABLE banker_transactions ADD COLUMN created_by TEXT")

                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS poe2_subscriptions (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id TEXT NOT NULL,
                            server_id TEXT NOT NULL,
                            league TEXT NOT NULL DEFAULT 'Standard',
                            tracked_items TEXT DEFAULT '[]',
                            purchases TEXT DEFAULT '[]',
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
                            user_id TEXT NOT NULL PRIMARY KEY,
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
                            updated_at TEXT NOT NULL
                        )
                    """)
                    
                    # Beggar request history table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS beggar_request_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                        "ALTER TABLE poe2_subscriptions ADD COLUMN purchases TEXT DEFAULT '[]'",
                    ]:
                        try:
                            cursor.execute(migration_sql)
                        except sqlite3.OperationalError as migration_error:
                            if "duplicate column name" not in str(migration_error).lower():
                                raise
                    
                    # Create indexes for nordic_runes
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nordic_runes_user_id ON nordic_runes(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nordic_runes_created_at ON nordic_runes(created_at)")
                    
                    # Create indexes for ring tables
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ring_accusations_created_at ON ring_accusations(created_at)")
                    
                    # Create indexes for dice game tables
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dice_game_history_user_id ON dice_game_history(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dice_game_history_created_at ON dice_game_history(created_at)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dice_game_stats_user_id ON dice_game_stats(user_id)")
                    
                    # Create indexes for beggar subrole table
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_subrole_user_id ON beggar_subrole(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_subrole_total_donated ON beggar_subrole(total_donated)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_subrole_weekly_donated ON beggar_subrole(weekly_donated)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_subrole_created_at ON beggar_subrole(created_at)")
                    
                    # Create indexes for beggar request history table
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_request_history_request_type ON beggar_request_history(request_type)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_beggar_request_history_created_at ON beggar_request_history(created_at)")

                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poe2_subscriptions_server_id ON poe2_subscriptions(server_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poe2_subscriptions_user_id ON poe2_subscriptions(user_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_poe2_subscriptions_league ON poe2_subscriptions(league)")
                    
                    # Create indexes for banker tables
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_wallets_wallet_id ON banker_wallets(wallet_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_transactions_from_wallet ON banker_transactions(from_wallet)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_transactions_to_wallet ON banker_transactions(to_wallet)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_banker_transactions_created_at ON banker_transactions(created_at)")
                    
                    conn.commit()
                    logger.info(f"Roles database initialized at: {self.db_path}")
                    
        except Exception as e:
            logger.error(f"Failed to initialize roles database: {e}")
            raise
    
    def save_nordic_runes_reading(self, user_id: str, question: str, runes_drawn: List[str], 
                                 interpretation: str, reading_type: str) -> int:
        """Save a rune reading to the database."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT INTO nordic_runes 
                        (user_id, question, runes_drawn, interpretation, reading_type, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        user_id, question, 
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
    
    def save_ring_accusation(self, accuser_id: str, accused_id: str, 
                           accusation: str, evidence: str = None) -> int:
        """Save a ring accusation to the database."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT INTO ring_accusations 
                        (accuser_id, accused_id, accusation, evidence, created_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        accuser_id, accused_id, accusation, evidence, 
                        datetime.now().isoformat()
                    ))
                    
                    accusation_id = cursor.lastrowid
                    conn.commit()
                    
                    logger.info(f"Saved ring accusation {accusation_id} for accuser {accuser_id}")
                    return accusation_id
                    
        except Exception as e:
            logger.error(f"Failed to save ring accusation: {e}")
            raise
    
    def get_ring_accusations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent ring accusations."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT id, accuser_id, accused_id, accusation, evidence, created_at
                        FROM ring_accusations
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (limit,))
                    
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
    
    def save_dice_game_stats(self, user_id: str, total_plays: int = 0, 
                            total_bet: int = 0, total_won: int = 0, pots_won: int = 0, 
                            biggest_prize: int = 0, last_play: str = None) -> bool:
        """Save or update dice game statistics for a user."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO dice_game_stats 
                        (user_id, total_plays, total_bet, total_won, pots_won, 
                         biggest_prize, last_play, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id, total_plays, total_bet, total_won, 
                        pots_won, biggest_prize, last_play, 
                        datetime.now().isoformat(), datetime.now().isoformat()
                    ))
                    
                    conn.commit()
                    logger.info(f"Saved dice game stats for user {user_id}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to save dice game stats: {e}")
            return False
    
    def get_dice_game_stats(self, user_id: str) -> Dict[str, Any]:
        """Get dice game statistics for a user."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT total_plays, total_bet, total_won, pots_won, biggest_prize, last_play, created_at, updated_at
                        FROM dice_game_stats
                        WHERE user_id = ?
                    """, (user_id,))
                    
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
    
    def save_dice_game_play(self, user_id: str, user_name: str, bet: int, 
                            dice: str, combination: str, prize: int, 
                            pot_before: int, pot_after: int) -> int:
        """Save a dice game play to the database."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT INTO dice_game_history 
                        (user_id, user_name, bet, dice, combination, 
                         prize, pot_before, pot_after, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        user_id, user_name, bet, dice, 
                        combination, prize, pot_before, pot_after, datetime.now().isoformat()
                    ))
                    
                    play_id = cursor.lastrowid
                    conn.commit()
                    
                    logger.info(f"Saved dice game play {play_id} for user {user_id}")
                    return play_id
                    
        except Exception as e:
            logger.error(f"Failed to save dice game play: {e}")
            raise
    
    def get_dice_game_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent dice game plays."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT id, user_id, user_name, bet, dice, 
                               combination, prize, pot_before, pot_after, created_at
                        FROM dice_game_history
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (limit,))
                    
                    plays = []
                    for row in cursor.fetchall():
                        plays.append({
                            'id': row[0],
                            'user_id': row[1],
                            'user_name': row[2],
                            'bet': row[3],
                            'dice': row[4],
                            'combination': row[5],
                            'prize': row[6],
                            'pot_before': row[7],
                            'pot_after': row[8],
                            'created_at': row[9]
                        })
                    
                    return plays
                    
        except Exception as e:
            logger.error(f"Failed to get dice game history: {e}")
            return []
    
    def is_role_enabled(self, role_name: str, server_id: str) -> bool:
        """Check if a role is enabled for a server - DEPRECATED: Use server_config.is_role_enabled instead."""
        from discord_bot.canvas.server_config import is_role_enabled as server_is_role_enabled
        return server_is_role_enabled(server_id, role_name, default_enabled=True)
    
    def set_role_enabled(self, role_name: str, server_id: str, enabled: bool) -> bool:
        """Enable or disable a role for a server - DEPRECATED: Use server_config.set_role_config instead."""
        from discord_bot.canvas.server_config import set_role_config as server_set_role_config
        return server_set_role_config(server_id, role_name, enabled)

    def get_all_roles_with_subroles(self) -> Dict[str, Any]:
        """Get all roles with subroles from server_config.json.
        
        Returns:
            Dict containing roles configuration from server_config.json
        """
        try:
            import os
            import json
            _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            server_config_path = os.path.join(_BASE_DIR, "databases", self.server_id, "server_config.json")
            with open(server_config_path, encoding="utf-8") as f:
                config = json.load(f)
            return config.get("roles", {})
        except Exception as e:
            logger.error(f"Failed to load roles from server_config.json for server {self.server_id}: {e}")
            return {}

    def save_poe2_subscription(self, user_id: str, server_id: str, league: str = "Standard", tracked_items: Optional[List[str]] = None, purchases: Optional[List[Dict]] = None) -> bool:
        """Create or update a POE2 subscription for a user on a server."""
        try:
            tracked_items_json = json.dumps(tracked_items or [])
            purchases_json = json.dumps(purchases or [])
            now = datetime.now().isoformat()
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO poe2_subscriptions
                        (user_id, server_id, league, tracked_items, purchases, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(user_id, server_id) DO UPDATE SET
                            league = excluded.league,
                            tracked_items = excluded.tracked_items,
                            purchases = excluded.purchases,
                            updated_at = excluded.updated_at
                    ''', (user_id, server_id, league, tracked_items_json, purchases_json, now, now))
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
                        SELECT user_id, server_id, league, tracked_items, purchases, created_at, updated_at
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
                        'purchases': json.loads(row[4] or '[]'),
                        'created_at': row[5],
                        'updated_at': row[6],
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
                        SELECT user_id, server_id, league, tracked_items, purchases, created_at, updated_at
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
                            'purchases': json.loads(row[4] or '[]'),
                            'created_at': row[5],
                            'updated_at': row[6],
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
    
    def migrate_legacy_beggar_data(self, server_id: str) -> bool:
        """Migrate beggar data from the dedicated beggar database into roles.db."""
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
                                role_config = self.get_role_config('beggar')
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
                                self.save_role_config('beggar', enabled, json.dumps(config_data))
                                migrated_any = True
                    conn.commit()
            if migrated_any:
                logger.info(f"Migrated legacy beggar data into roles.db for server {server_id}")
            return migrated_any
        except Exception as e:
            logger.error(f"Failed to migrate legacy beggar data: {e}")
            return False
    
    def save_banker_wallet(self, wallet_id: str, user_name: str, 
                           balance: int = 0, wallet_type: str = 'user') -> bool:
        """Save or update a banker wallet."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT OR REPLACE INTO banker_wallets 
                        (wallet_id, user_name, balance, wallet_type, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        wallet_id, user_name, balance, wallet_type, 
                        datetime.now().isoformat(), datetime.now().isoformat()
                    ))
                    
                    conn.commit()
                    logger.info(f"Saved banker wallet {wallet_id} for user {user_name}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to save banker wallet: {e}")
            return False
    
    def get_banker_wallet(self, wallet_id: str) -> Dict[str, Any]:
        """Get a banker wallet by ID."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT wallet_id, user_name, balance, wallet_type, created_at, updated_at
                        FROM banker_wallets
                        WHERE wallet_id = ?
                    """, (wallet_id,))
                    
                    result = cursor.fetchone()
                    if result:
                        return {
                            'wallet_id': result[0],
                            'user_name': result[1],
                            'balance': result[2],
                            'wallet_type': result[3],
                            'created_at': result[4],
                            'updated_at': result[5]
                        }
                    else:
                        return None
                    
        except Exception as e:
            logger.error(f"Failed to get banker wallet: {e}")
            return None
    
    def update_banker_balance(self, wallet_id: str, new_balance: int) -> bool:
        """Update banker wallet balance."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        UPDATE banker_wallets 
                        SET balance = ?, updated_at = ?
                        WHERE wallet_id = ?
                    """, (new_balance, datetime.now().isoformat(), wallet_id))
                    
                    conn.commit()
                    logger.info(f"Updated balance for wallet {wallet_id} to {new_balance}")
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to update banker balance: {e}")
            return False
    
    def save_banker_transaction(self, from_wallet: str, to_wallet: str, amount: int, 
                                transaction_type: str, description: str = None, created_by: str = None) -> int:
        """Save a banker transaction."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        INSERT INTO banker_transactions 
                        (from_wallet, to_wallet, amount, transaction_type, description, created_by, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        from_wallet, to_wallet, amount, transaction_type, description, created_by, datetime.now().isoformat()
                    ))
                    
                    transaction_id = cursor.lastrowid
                    conn.commit()
                    
                    logger.info(f"Saved banker transaction {transaction_id}: {from_wallet} -> {to_wallet}, {amount} coins")
                    return transaction_id
                    
        except Exception as e:
            logger.error(f"Failed to save banker transaction: {e}")
            raise
    
    def get_banker_transactions(self, wallet_id: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Get banker transactions (optionally filtered by wallet)."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    if wallet_id:
                        cursor.execute("""
                            SELECT id, from_wallet, to_wallet, amount, transaction_type, 
                                   description, created_by, created_at
                            FROM banker_transactions
                            WHERE from_wallet = ? OR to_wallet = ?
                            ORDER BY created_at DESC
                            LIMIT ?
                        """, (wallet_id, wallet_id, limit))
                    else:
                        cursor.execute("""
                            SELECT id, from_wallet, to_wallet, amount, transaction_type, 
                                   description, created_by, created_at
                            FROM banker_transactions
                            ORDER BY created_at DESC
                            LIMIT ?
                        """, (limit,))
                    
                    transactions = []
                    for row in cursor.fetchall():
                        transactions.append({
                            'id': row[0],
                            'from_wallet': row[1],
                            'to_wallet': row[2],
                            'amount': row[3],
                            'transaction_type': row[4],
                            'description': row[5],
                            'created_by': row[6],
                            'created_at': row[7]
                        })
                    
                    return transactions
                    
        except Exception as e:
            logger.error(f"Failed to get banker transactions: {e}")
            return []
    
    def get_all_banker_wallets(self) -> List[Dict[str, Any]]:
        """Get all banker wallets."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT wallet_id, user_name, balance, wallet_type, created_at, updated_at
                        FROM banker_wallets
                        ORDER BY created_at DESC
                    """)
                    
                    wallets = []
                    for row in cursor.fetchall():
                        wallets.append({
                            'wallet_id': row[0],
                            'user_name': row[1],
                            'balance': row[2],
                            'wallet_type': row[3],
                            'created_at': row[4],
                            'updated_at': row[5]
                        })
                    
                    return wallets
                    
        except Exception as e:
            logger.error(f"Failed to get all banker wallets: {e}")
            return []
    
    # Beggar subrole methods
    def update_beggar_donation(self, user_id: str, user_name: str, amount: int, reason: str = "") -> bool:
        """Update beggar donation record for a user."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    # Check if user exists
                    cursor.execute("""
                        SELECT total_donated, weekly_donated, donation_count, weekly_donation_count
                        FROM beggar_subrole
                        WHERE user_id = ?
                    """, (user_id,))
                    
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
                            WHERE user_id = ?
                        """, (new_total, new_weekly_total, new_count, new_weekly_count, user_name, now, amount, reason, now, user_id))
                        
                        logger.info(f"Updated beggar donation for {user_name}: +{amount} (weekly: {new_weekly_total}, total: {new_total})")
                    else:
                        # Insert new record
                        cursor.execute("""
                            INSERT INTO beggar_subrole 
                            (user_id, user_name, total_donated, weekly_donated, donation_count,
                             weekly_donation_count, first_donation, last_donation, last_donation_amount, last_reason,
                             created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (user_id, user_name, amount, amount, 1, 1, now, now, amount, reason, now, now))
                        
                        logger.info(f"Created beggar record for {user_name}: {amount}")
                    
                    conn.commit()
                    return True
                    
        except Exception as e:
            logger.error(f"Failed to update beggar donation: {e}")
            return False
    
    def save_beggar_request(self, user_id: str, user_name: str, request_type: str,
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
                        (user_id, user_name, request_type, message, channel_id, metadata, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            user_id,
                            user_name,
                            request_type,
                            message,
                            channel_id,
                            metadata,
                            datetime.now().isoformat(),
                        )
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
    
    def get_beggar_user_stats(self, user_id: str) -> Dict[str, Any]:
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
                        WHERE user_id = ?
                    """, (user_id,))
                    
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
    
    def get_weekly_donations_summary(self) -> List[Dict[str, Any]]:
        """Get summary of users who donated this week with their amounts."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT user_id, user_name, weekly_donated, weekly_donation_count, last_donation
                        FROM beggar_subrole
                        WHERE weekly_donated > 0
                        ORDER BY weekly_donated DESC, datetime(last_donation) DESC
                    """)
                    
                    weekly_donors = []
                    for row in cursor.fetchall():
                        weekly_donors.append({
                            'user_id': row[0],
                            'donor_name': row[1],
                            'weekly_amount': row[2],
                            'weekly_count': row[3],
                            'last_donation': row[4],
                        })
                    
                    return weekly_donors
                    
        except Exception as e:
            logger.error(f"Failed to get weekly donations summary: {e}")
            return []

    def get_recent_beggar_donations(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent beggar donations."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        SELECT user_id, user_name, last_donation_amount, donation_count, last_donation, last_reason,
                               weekly_donated, weekly_donation_count, total_donated
                        FROM beggar_subrole
                        WHERE (weekly_donated > 0 OR total_donated > 0)
                        ORDER BY datetime(last_donation) DESC, user_id DESC
                        LIMIT ?
                    """, (limit,))
                    
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
                        WHERE {donated_field} > 0
                        ORDER BY {donated_field} DESC
                        LIMIT ?
                    """, (limit,))
                    
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
                    """, (datetime.now().isoformat(),))
                    conn.commit()
                    logger.info(f"Reset beggar weekly cycle for server {server_id}: {cursor.rowcount} donor rows updated")
                    return True
        except Exception as e:
            logger.error(f"Failed to reset beggar weekly cycle: {e}")
            return False


# Global database instance cache
_roles_db_instances: Dict[str, RolesDatabase] = {}

def get_roles_db_instance(server_id: str = None) -> Optional[RolesDatabase]:
    """Get the roles database instance for a specific server.
    
    Args:
        server_id: Server ID. If None or "default", returns None instead of creating placeholder.
    
    Returns:
        RolesDatabase instance or None if server_id is not valid.
    """
    global _roles_db_instances
    
    # Don't create database during module import - require explicit valid server_id
    if not server_id or server_id == "default":
        logger.debug("get_roles_db_instance called without valid server_id - skipping database creation")
        return None
    
    # Generate the current database path for this server
    current_db_path = get_roles_db_path(server_id)
    cache_key = f"{server_id}:{current_db_path}"
    
    # Check if we have a cached instance with the same database path
    if cache_key not in _roles_db_instances:
        _roles_db_instances[cache_key] = RolesDatabase(server_id)
    else:
        # Verify that the cached instance still points to the correct database path
        # This handles personality changes where the cache might have stale paths
        cached_instance = _roles_db_instances[cache_key]
        if str(cached_instance.db_path) != str(current_db_path):
            logger.warning(f"🔄 Database path changed for server {server_id}: {cached_instance.db_path} -> {current_db_path}")
            del _roles_db_instances[cache_key]
            _roles_db_instances[cache_key] = RolesDatabase(server_id)
    
    return _roles_db_instances[cache_key]

def invalidate_roles_db_instance(server_id: str = None):
    """Invalidate cached roles database instance for a server or all servers.
    
    Call this after personality change so the next get_roles_db_instance()
    creates a new RolesDatabase pointing to the correct personality db file.
    
    Args:
        server_id: Server ID to invalidate, or None to clear all.
    """
    global _roles_db_instances
    if server_id:
        # Invalidate all instances for this server (any personality)
        keys_to_remove = [k for k in _roles_db_instances.keys() if k.startswith(f"{server_id}:")]
        for key in keys_to_remove:
            del _roles_db_instances[key]
            logger.info(f"🗄️ [ROLES] Invalidated cached db instance for server: {server_id}")
    else:
        _roles_db_instances.clear()
        logger.info("🗄️ [ROLES] Invalidated all cached db instances")
