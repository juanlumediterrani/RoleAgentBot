"""
Nordic Runes Database Module
Handles storage and retrieval of rune readings.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from agent_logging import get_logger

logger = get_logger('nordic_runes_db')


class NordicRunesDB:
    """Database handler for Nordic runes readings."""
    
    def __init__(self, db_path: str = "roleagentbot.db"):
        """Initialize database connection."""
        self.db_path = db_path
        self._init_tables()
    
    def _init_tables(self):
        """Initialize database tables."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create rune readings table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS rune_readings (
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
                
                # Create indexes separately
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_rune_readings_user_id ON rune_readings(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_rune_readings_created_at ON rune_readings(created_at)")
                
                conn.commit()
                logger.info("Nordic runes database tables initialized")
                
        except Exception as e:
            logger.error(f"Failed to initialize rune database: {e}")
            raise
    
    def save_reading(self, user_id: str, server_id: Optional[str], 
                    question: str, runes_drawn: List[str], 
                    interpretation: str, reading_type: str) -> int:
        """Save a rune reading to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO rune_readings 
                    (user_id, server_id, question, runes_drawn, interpretation, reading_type, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, server_id, question, 
                    json.dumps(runes_drawn), interpretation, 
                    reading_type, datetime.now().isoformat()
                ))
                
                reading_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"Saved rune reading {reading_id} for user {user_id}")
                return reading_id
                
        except Exception as e:
            logger.error(f"Failed to save rune reading: {e}")
            raise
    
    def get_user_readings(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent rune readings for a user."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT id, question, runes_drawn, interpretation, reading_type, created_at
                    FROM rune_readings
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
    
    def get_reading_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics for a user's rune readings."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Total readings
                cursor.execute("SELECT COUNT(*) FROM rune_readings WHERE user_id = ?", (user_id,))
                total_readings = cursor.fetchone()[0]
                
                # Most common reading type
                cursor.execute("""
                    SELECT reading_type, COUNT(*) as count
                    FROM rune_readings
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


# Global database instance
_db_instance = None

def get_nordic_runes_db_instance() -> NordicRunesDB:
    """Get the global Nordic runes database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = NordicRunesDB()
    return _db_instance
