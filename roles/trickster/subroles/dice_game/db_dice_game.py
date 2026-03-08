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
                        usuario_id TEXT NOT NULL,
                        usuario_nombre TEXT NOT NULL,
                        servidor_id TEXT NOT NULL,
                        servidor_nombre TEXT NOT NULL,
                        apuesta INTEGER NOT NULL,
                        dados TEXT NOT NULL,
                        combinacion TEXT NOT NULL,
                        premio INTEGER NOT NULL,
                        bote_antes INTEGER NOT NULL,
                        bote_despues INTEGER NOT NULL,
                        fecha TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Server configuration table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS server_config (
                        servidor_id TEXT PRIMARY KEY,
                        apuesta_fija INTEGER DEFAULT 1,
                        anuncios_activos BOOLEAN DEFAULT 1,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Player statistics table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS player_stats (
                        usuario_id TEXT NOT NULL,
                        servidor_id TEXT NOT NULL,
                        total_jugadas INTEGER DEFAULT 0,
                        total_apostado INTEGER DEFAULT 0,
                        total_ganado INTEGER DEFAULT 0,
                        botes_ganados INTEGER DEFAULT 0,
                        mayor_premio INTEGER DEFAULT 0,
                        ultima_jugada DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (usuario_id, servidor_id)
                    )
                ''')
                
                conn.commit()
                logger.info(f"✅ Dice game database initialized at {self.db_path}")
                
        except Exception as e:
            logger.error(f"❌ Error initializing dice game database: {e}")
            raise
    
    def registrar_jugada(self, usuario_id: str, usuario_nombre: str, servidor_id: str, 
                       servidor_nombre: str, apuesta: int, dados: str, combinacion: str, 
                       premio: int, bote_antes: int, bote_despues: int) -> bool:
        """Register a dice game play."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Insert game record
                cursor.execute('''
                    INSERT INTO dice_games 
                    (usuario_id, usuario_nombre, servidor_id, servidor_nombre, 
                     apuesta, dados, combinacion, premio, bote_antes, bote_despues, fecha)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (usuario_id, usuario_nombre, servidor_id, servidor_nombre,
                      apuesta, dados, combinacion, premio, bote_antes, bote_despues,
                      datetime.now().isoformat()))
                
                # Update player statistics
                cursor.execute('''
                    INSERT OR REPLACE INTO player_stats 
                    (usuario_id, servidor_id, total_jugadas, total_apostado, total_ganado, 
                     botes_ganados, mayor_premio, ultima_jugada, updated_at)
                    VALUES (?, ?, 
                           COALESCE((SELECT total_jugadas FROM player_stats WHERE usuario_id=? AND servidor_id=?), 0) + 1,
                           COALESCE((SELECT total_apostado FROM player_stats WHERE usuario_id=? AND servidor_id=?), 0) + ?,
                           COALESCE((SELECT total_ganado FROM player_stats WHERE usuario_id=? AND servidor_id=?), 0) + ?,
                           COALESCE((SELECT botes_ganados FROM player_stats WHERE usuario_id=? AND servidor_id=?), 0) + ?,
                           CASE WHEN ? > COALESCE((SELECT mayor_premio FROM player_stats WHERE usuario_id=? AND servidor_id=?), 0) THEN ? ELSE COALESCE((SELECT mayor_premio FROM player_stats WHERE usuario_id=? AND servidor_id=?), 0) END,
                           ?, CURRENT_TIMESTAMP)
                ''', (usuario_id, servidor_id, usuario_id, servidor_id,
                      usuario_id, servidor_id, apuesta,
                      usuario_id, servidor_id, premio,
                      usuario_id, servidor_id, 1 if premio > 0 else 0,
                      premio, usuario_id, servidor_id, premio,
                      usuario_id, servidor_id, premio,
                      datetime.now().isoformat()))
                
                conn.commit()
                logger.info(f"🎲 Game registered: {usuario_nombre} - {dados} → {combinacion} - Prize: {premio}")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error registering game: {e}")
            return False
    
    def obtener_configuracion_servidor(self, servidor_id: str) -> Dict[str, Any]:
        """Get server configuration."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT apuesta_fija, anuncios_activos 
                    FROM server_config 
                    WHERE servidor_id = ?
                ''', (servidor_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'apuesta_fija': result[0],
                        'anuncios_activos': bool(result[1])
                    }
                else:
                    # Create default config
                    cursor.execute('''
                        INSERT INTO server_config (servidor_id, apuesta_fija, anuncios_activos)
                        VALUES (?, ?, ?)
                    ''', (servidor_id, 1, True))
                    conn.commit()
                    return {'apuesta_fija': 1, 'anuncios_activos': True}
                    
        except Exception as e:
            logger.error(f"❌ Error getting server config: {e}")
            return {'apuesta_fija': 1, 'anuncios_activos': True}
    
    def configurar_servidor(self, servidor_id: str, **kwargs) -> bool:
        """Configure server settings."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                set_clauses = []
                values = []
                
                if 'apuesta_fija' in kwargs:
                    set_clauses.append('apuesta_fija = ?')
                    values.append(kwargs['apuesta_fija'])
                
                if 'anuncios_activos' in kwargs:
                    set_clauses.append('anuncios_activos = ?')
                    values.append(int(kwargs['anuncios_activos']))
                
                if set_clauses:
                    set_clauses.append('updated_at = CURRENT_TIMESTAMP')
                    values.append(servidor_id)
                    
                    cursor.execute(f'''
                        UPDATE server_config 
                        SET {', '.join(set_clauses)}
                        WHERE servidor_id = ?
                    ''', values)
                    
                    if cursor.rowcount == 0:
                        # Insert if not exists
                        cursor.execute('''
                            INSERT INTO server_config (servidor_id, apuesta_fija, anuncios_activos)
                            VALUES (?, ?, ?)
                        ''', (servidor_id, 
                              kwargs.get('apuesta_fija', 1),
                              kwargs.get('anuncios_activos', True)))
                    
                    conn.commit()
                    logger.info(f"🎲 Server {servidor_id} configured: {kwargs}")
                    return True
                    
        except Exception as e:
            logger.error(f"❌ Error configuring server: {e}")
            return False
    
    def obtener_estadisticas_jugador(self, usuario_id: str, servidor_id: str) -> Dict[str, Any]:
        """Get player statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT total_jugadas, total_apostado, total_ganado, botes_ganados, mayor_premio
                    FROM player_stats 
                    WHERE usuario_id = ? AND servidor_id = ?
                ''', (usuario_id, servidor_id))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'total_jugadas': result[0],
                        'total_apostado': result[1],
                        'total_ganado': result[2],
                        'botes_ganados': result[3],
                        'mayor_premio': result[4]
                    }
                else:
                    return {
                        'total_jugadas': 0,
                        'total_apostado': 0,
                        'total_ganado': 0,
                        'botes_ganados': 0,
                        'mayor_premio': 0
                    }
                    
        except Exception as e:
            logger.error(f"❌ Error getting player stats: {e}")
            return {
                'total_jugadas': 0,
                'total_apostado': 0,
                'total_ganado': 0,
                'botes_ganados': 0,
                'mayor_premio': 0
            }
    
    def obtener_ranking_jugadores(self, servidor_id: str, metric: str = 'total_ganado', limit: int = 10) -> List[Tuple]:
        """Get player ranking."""
        valid_metrics = ['total_ganado', 'total_jugadas', 'botes_ganados', 'mayor_premio']
        if metric not in valid_metrics:
            metric = 'total_ganado'
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    SELECT ps.usuario_id, ps.{metric}, ps.total_jugadas, ps.total_ganado, ps.total_apostado
                    FROM player_stats ps
                    WHERE ps.servidor_id = ? AND ps.total_jugadas > 0
                    ORDER BY ps.{metric} DESC
                    LIMIT ?
                ''', (servidor_id, limit))
                
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"❌ Error getting ranking: {e}")
            return []
    
    def obtener_historial_partidas(self, servidor_id: str, limit: int = 15) -> List[Tuple]:
        """Get game history."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, usuario_id, usuario_nombre, servidor_id, servidor_nombre,
                           apuesta, dados, combinacion, premio, bote_antes, bote_despues, fecha
                    FROM dice_games
                    WHERE servidor_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (servidor_id, limit))
                
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
