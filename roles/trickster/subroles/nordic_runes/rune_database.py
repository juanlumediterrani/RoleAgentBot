"""
Rune Database Module
Handles database operations for the Nordic Runes system.
"""

import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class RuneDatabase:
    """Database handler for rune readings and user data."""
    
    def __init__(self, db_path: str):
        """Initialize the database."""
        self.db_path = db_path
        self._initialize_database()
    
    def _initialize_database(self):
        """Create database tables if they don't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create readings table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS rune_readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        server_id TEXT,
                        question TEXT NOT NULL,
                        reading_type TEXT NOT NULL,
                        runes_drawn TEXT NOT NULL,
                        interpretation TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        ai_used BOOLEAN DEFAULT 0
                    )
                ''')
                
                # Create user stats table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS rune_user_stats (
                        user_id TEXT PRIMARY KEY,
                        total_readings INTEGER DEFAULT 0,
                        favorite_type TEXT,
                        last_reading TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                ''')
                
                # Create rune frequency table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS rune_frequency (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        rune_key TEXT NOT NULL,
                        draw_count INTEGER DEFAULT 0,
                        last_drawn TEXT,
                        updated_at TEXT NOT NULL
                    )
                ''')
                
                conn.commit()
                logger.info("Rune database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing rune database: {e}")
            raise
    
    def save_reading(self, user_id: str, server_id: Optional[str], question: str, 
                    reading_type: str, runes_drawn: List[Dict], interpretation: str, 
                    ai_used: bool = False) -> int:
        """Save a rune reading to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Convert runes data to JSON
                runes_json = json.dumps(runes_drawn)
                timestamp = datetime.now().isoformat()
                
                # Insert reading
                cursor.execute('''
                    INSERT INTO rune_readings 
                    (user_id, server_id, question, reading_type, runes_drawn, 
                     interpretation, timestamp, ai_used)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (user_id, server_id, question, reading_type, runes_json, 
                      interpretation, timestamp, ai_used))
                
                reading_id = cursor.lastrowid
                
                # Update user stats
                self._update_user_stats(cursor, user_id, reading_type, timestamp)
                
                # Update rune frequency
                self._update_rune_frequency(cursor, runes_drawn, timestamp)
                
                conn.commit()
                logger.info(f"Rune reading saved: {reading_id}")
                return reading_id
                
        except Exception as e:
            logger.error(f"Error saving rune reading: {e}")
            raise
    
    def _update_user_stats(self, cursor, user_id: str, reading_type: str, timestamp: str):
        """Update user statistics."""
        # Check if user exists
        cursor.execute("SELECT * FROM rune_user_stats WHERE user_id = ?", (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing user
            cursor.execute('''
                UPDATE rune_user_stats 
                SET total_readings = total_readings + 1,
                    last_reading = ?,
                    updated_at = ?
                WHERE user_id = ?
            ''', (reading_type, timestamp, user_id))
        else:
            # Insert new user
            cursor.execute('''
                INSERT INTO rune_user_stats 
                (user_id, total_readings, favorite_type, last_reading, 
                 created_at, updated_at)
                VALUES (?, 1, ?, ?, ?, ?)
            ''', (user_id, reading_type, reading_type, timestamp, timestamp))
    
    def _update_rune_frequency(self, cursor, runes_drawn: List[Dict], timestamp: str):
        """Update rune draw frequency."""
        for rune_data in runes_drawn:
            rune_key = rune_data.get('key', '')
            if rune_key:
                # Check if rune exists
                cursor.execute("SELECT * FROM rune_frequency WHERE rune_key = ?", (rune_key,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing rune
                    cursor.execute('''
                        UPDATE rune_frequency 
                        SET draw_count = draw_count + 1,
                            last_drawn = ?,
                            updated_at = ?
                        WHERE rune_key = ?
                    ''', (timestamp, timestamp, rune_key))
                else:
                    # Insert new rune
                    cursor.execute('''
                        INSERT INTO rune_frequency 
                        (rune_key, draw_count, last_drawn, updated_at)
                        VALUES (?, 1, ?, ?)
                    ''', (rune_key, timestamp, timestamp))
    
    def get_user_readings(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get recent readings for a user."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT id, question, reading_type, runes_drawn, interpretation,
                           timestamp, ai_used
                    FROM rune_readings 
                    WHERE user_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                ''', (user_id, limit))
                
                readings = []
                for row in cursor.fetchall():
                    reading = {
                        'id': row[0],
                        'question': row[1],
                        'reading_type': row[2],
                        'runes_drawn': json.loads(row[3]),
                        'interpretation': row[4],
                        'timestamp': row[5],
                        'ai_used': bool(row[6])
                    }
                    readings.append(reading)
                
                return readings
                
        except Exception as e:
            logger.error(f"Error getting user readings: {e}")
            return []
    
    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT total_readings, favorite_type, last_reading,
                           created_at, updated_at
                    FROM rune_user_stats
                    WHERE user_id = ?
                ''', (user_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        'total_readings': result[0],
                        'favorite_type': result[1],
                        'last_reading': result[2],
                        'created_at': result[3],
                        'updated_at': result[4]
                    }
                else:
                    return {
                        'total_readings': 0,
                        'favorite_type': None,
                        'last_reading': None,
                        'created_at': None,
                        'updated_at': None
                    }
                    
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return {}
    
    def get_server_stats(self, server_id: str) -> Dict[str, Any]:
        """Get server statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Total readings
                cursor.execute('''
                    SELECT COUNT(*) FROM rune_readings 
                    WHERE server_id = ?
                ''', (server_id,))
                total_readings = cursor.fetchone()[0]
                
                # Unique users
                cursor.execute('''
                    SELECT COUNT(DISTINCT user_id) FROM rune_readings 
                    WHERE server_id = ?
                ''', (server_id,))
                unique_users = cursor.fetchone()[0]
                
                # Most popular reading type
                cursor.execute('''
                    SELECT reading_type, COUNT(*) as count
                    FROM rune_readings 
                    WHERE server_id = ?
                    GROUP BY reading_type
                    ORDER BY count DESC
                    LIMIT 1
                ''', (server_id,))
                popular_type = cursor.fetchone()
                
                return {
                    'total_readings': total_readings,
                    'unique_users': unique_users,
                    'popular_type': popular_type[0] if popular_type else None,
                    'popular_type_count': popular_type[1] if popular_type else 0
                }
                
        except Exception as e:
            logger.error(f"Error getting server stats: {e}")
            return {}
    
    def get_rune_frequency(self, limit: int = 10) -> List[Dict]:
        """Get most frequently drawn runes."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT rune_key, draw_count, last_drawn
                    FROM rune_frequency
                    ORDER BY draw_count DESC
                    LIMIT ?
                ''', (limit,))
                
                frequency = []
                for row in cursor.fetchall():
                    frequency.append({
                        'rune_key': row[0],
                        'draw_count': row[1],
                        'last_drawn': row[2]
                    })
                
                return frequency
                
        except Exception as e:
            logger.error(f"Error getting rune frequency: {e}")
            return []
    
    def cleanup_old_readings(self, days: int = 30):
        """Clean up readings older than specified days."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cutoff_date = datetime.now().replace(day=1).isoformat()
                
                cursor.execute('''
                    DELETE FROM rune_readings 
                    WHERE timestamp < ?
                ''', (cutoff_date,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                logger.info(f"Cleaned up {deleted_count} old rune readings")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Error cleaning up old readings: {e}")
            return 0
