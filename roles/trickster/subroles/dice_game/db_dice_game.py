"""
Dice Game Database Module
Handles all database operations for the dice game.
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Optional, Any
from agent_logging import get_logger

logger = get_logger('db_dice_game')


class DatabaseRoleDiceGame:
    """Database class for dice game operations."""
    
    def __init__(self, db_path: str):
        """Initialize the dice game database."""
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Games table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dice_games (
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
                        date TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Server configuration table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS server_config (
                        server_id TEXT PRIMARY KEY,
                        bet_fija INTEGER DEFAULT 1,
                        announcements_active BOOLEAN DEFAULT 1,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Player statistics table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS player_stats (
                        user_id TEXT NOT NULL,
                        server_id TEXT NOT NULL,
                        total_plays INTEGER DEFAULT 0,
                        total_bet INTEGER DEFAULT 0,
                        total_won INTEGER DEFAULT 0,
                        pots_won INTEGER DEFAULT 0,
                        mayor_prize INTEGER DEFAULT 0,
                        last_play DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (user_id, server_id)
                    )
                ''')
                
                # Migration: Check if biggest_prize column exists and rename it to mayor_prize . posible legacy function
                cursor.execute("PRAGMA table_info(player_stats)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'biggest_prize' in columns and 'mayor_prize' not in columns:
                    logger.info("🔄 Migrating database: renaming biggest_prize to mayor_prize")
                    cursor.execute("ALTER TABLE player_stats RENAME COLUMN biggest_prize TO mayor_prize")
                
                conn.commit()
                logger.info(f"✅ Dice game database initialized at {self.db_path}")
                
        except Exception as e:
            logger.error(f"❌ Error initializing dice game database: {e}")
            raise
    
    def register_game(self, user_id: str, user_name: str, server_id: str, 
                       server_name: str, bet: int, dice: str, combination: str, 
                       prize: int, pot_before: int, pot_after: int) -> bool:
        """Register a dice game play."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Insert game record
                cursor.execute('''
                    INSERT INTO dice_games 
                    (user_id, user_name, server_id, server_name, 
                     bet, dice, combination, prize, pot_before, pot_after, date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, user_name, server_id, server_name,
                      bet, dice, combination, prize, pot_before, pot_after,
                      datetime.now().isoformat()))
                
                # Update player statistics
                cursor.execute('''
                    INSERT OR REPLACE INTO player_stats 
                    (user_id, server_id, total_plays, total_bet, total_won, 
                     pots_won, mayor_prize, last_play, updated_at)
                    VALUES (?, ?, 
                           COALESCE((SELECT total_plays FROM player_stats WHERE user_id=? AND server_id=?), 0) + 1,
                           COALESCE((SELECT total_bet FROM player_stats WHERE user_id=? AND server_id=?), 0) + ?,
                           COALESCE((SELECT total_won FROM player_stats WHERE user_id=? AND server_id=?), 0) + ?,
                           COALESCE((SELECT pots_won FROM player_stats WHERE user_id=? AND server_id=?), 0) + ?,
                           CASE WHEN ? > COALESCE((SELECT mayor_prize FROM player_stats WHERE user_id=? AND server_id=?), 0) THEN ? ELSE COALESCE((SELECT mayor_prize FROM player_stats WHERE user_id=? AND server_id=?), 0) END,
                           ?, CURRENT_TIMESTAMP)
                ''', (user_id, server_id, user_id, server_id,
                      user_id, server_id, bet,
                      user_id, server_id, prize,
                      user_id, server_id, 1 if prize > 0 else 0,
                      prize, user_id, server_id, prize,
                      user_id, server_id,
                      datetime.now().isoformat()))
                
                conn.commit()
                logger.info(f"🎲 Game registered: {user_name} - {dice} → {combination} - Prize: {prize}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error registering game: {e}")
            return False

    def ensure_player_stats(self, user_id: str, server_id: str) -> bool:
        """Ensure player stats row exists for a user/server (creates an empty row if missing)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    '''
                    INSERT OR IGNORE INTO player_stats (
                        user_id, server_id, total_plays, total_bet, total_won,
                        pots_won, mayor_prize, last_play, updated_at
                    ) VALUES (?, ?, 0, 0, 0, 0, 0, NULL, CURRENT_TIMESTAMP)
                    ''',
                    (user_id, server_id),
                )
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"❌ Error ensuring player stats: {e}")
            return False
    
    def get_server_config(self, server_id: str) -> Dict[str, Any]:
        """Get server configuration."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT bet_fija, announcements_active 
                    FROM server_config 
                    WHERE server_id = ?
                ''', (server_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'bet_fija': result[0],
                        'apuesta_fija': result[0],
                        'announcements_active': bool(result[1]),
                        'anuncios_activos': bool(result[1])
                    }
                else:
                    # Create default config
                    cursor.execute('''
                        INSERT INTO server_config (server_id, bet_fija, announcements_active)
                        VALUES (?, ?, ?)
                    ''', (server_id, 1, True))
                    conn.commit()
                    return {'bet_fija': 1, 'apuesta_fija': 1, 'announcements_active': True, 'anuncios_activos': True}
                    
        except Exception as e:
            logger.error(f"❌ Error getting server config: {e}")
            return {'bet_fija': 1, 'apuesta_fija': 1, 'announcements_active': True, 'anuncios_activos': True}
    
    def configure_server(self, server_id: str, **kwargs) -> bool:
        """Configure server settings."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                set_clauses = []
                values = []
                
                bet_value = kwargs.get('bet_fija', kwargs.get('apuesta_fija'))
                announcements_value = kwargs.get('announcements_active', kwargs.get('anuncios_activos'))

                if bet_value is not None:
                    set_clauses.append('bet_fija = ?')
                    values.append(bet_value)
                
                if announcements_value is not None:
                    set_clauses.append('announcements_active = ?')
                    values.append(int(announcements_value))
                
                if set_clauses:
                    set_clauses.append('updated_at = CURRENT_TIMESTAMP')
                    values.append(server_id)
                    
                    cursor.execute(f'''
                        UPDATE server_config 
                        SET {', '.join(set_clauses)}
                        WHERE server_id = ?
                    ''', values)
                    
                    if cursor.rowcount == 0:
                        # Insert if not exists
                        cursor.execute('''
                            INSERT INTO server_config (server_id, bet_fija, announcements_active)
                            VALUES (?, ?, ?)
                        ''', (server_id, 
                              bet_value if bet_value is not None else 1,
                              announcements_value if announcements_value is not None else True))
                    
                    conn.commit()
                    logger.info(f"🎲 Server {server_id} configured: {kwargs}")
                    return True
                    
        except Exception as e:
            logger.error(f"❌ Error configuring server: {e}")
            return False
    
    def get_player_stats(self, user_id: str, server_id: str) -> Dict[str, Any]:
        """Get player statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT total_plays, total_bet, total_won, pots_won, mayor_prize
                    FROM player_stats 
                    WHERE user_id = ? AND server_id = ?
                ''', (user_id, server_id))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'total_plays': result[0],
                        'total_bet': result[1],
                        'total_won': result[2],
                        'pots_won': result[3],
                        'mayor_prize': result[4]
                    }
                else:
                    return {
                        'total_plays': 0,
                        'total_bet': 0,
                        'total_won': 0,
                        'pots_won': 0,
                        'mayor_prize': 0
                    }
                    
        except Exception as e:
            logger.error(f"❌ Error getting player stats: {e}")
            return {
                'total_plays': 0,
                'total_bet': 0,
                'total_won': 0,
                'pots_won': 0,
                'mayor_prize': 0
            }
    
    def get_player_ranking(self, server_id: str, metric: str = 'total_won', limit: int = 10) -> List[Tuple]:
        """Get player ranking."""
        valid_metrics = ['total_won', 'total_plays', 'pots_won', 'mayor_prize']
        if metric not in valid_metrics:
            metric = 'total_won'
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    SELECT ps.user_id, ps.{metric}, ps.total_plays, ps.total_won, ps.total_bet
                    FROM player_stats ps
                    WHERE ps.server_id = ? AND ps.total_plays > 0
                    ORDER BY ps.{metric} DESC
                    LIMIT ?
                ''', (server_id, limit))
                
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"❌ Error getting ranking: {e}")
            return []
    
    def get_game_history(self, server_id: str, limit: int = 15) -> List[Tuple]:
        """Get game history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, user_name, server_id, server_name,
                           bet, dice, combination, prize, pot_before, pot_after, date
                    FROM dice_games
                    WHERE server_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (server_id, limit))
                
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"❌ Error getting game history: {e}")
            return []


def get_dice_game_db_instance(server_name: str) -> Optional[DatabaseRoleDiceGame]:
    """Get dice game database instance for a server."""
    try:
        from agent_db import get_database_path
        db_path = get_database_path(server_name, "dice_game")
        return DatabaseRoleDiceGame(db_path)
    except Exception as e:
        logger.error(f"❌ Error creating dice game DB instance: {e}")
        return None
