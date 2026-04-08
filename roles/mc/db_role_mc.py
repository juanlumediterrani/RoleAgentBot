import sqlite3
import threading
import os
import stat
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('db_role_mc')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_mc')

from agent_db import get_server_db_path_fallback, get_personality_name

def get_db_path(server_id: str = "default") -> Path:
    """Generate database path for MC role using centralized roles.db."""
    # MC role now uses the centralized roles.db system with personality-specific naming
    from agent_roles_db import get_roles_db_path
    return get_roles_db_path(server_id)


class DatabaseRoleMC:
    """Specialized database for the MC (Master of Ceremonies).
    Manages music queues, playlists and preferences.
    """
    
    def __init__(self, server_id: str = "default", db_path: Path = None):
        if db_path is None:
            self.db_path = get_db_path(server_id)
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_writable_db()
        self._init_db()
    
    def _ensure_writable_db(self):
        """Verify database is accessible and force correct permissions."""
        try:
            # Ensure directory exists with correct permissions
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._fix_permissions(self.db_path.parent)
            
            # Just verify database file exists and is accessible
            if not self.db_path.exists():
                # Create empty database file
                conn = sqlite3.connect(str(self.db_path), timeout=30.0)
                conn.close()
            
            # Force database file permissions
            self._fix_permissions(self.db_path)
            
        except Exception as e:
            logger.error(f"Cannot access database at {self.db_path}: {e}")
            raise
    
    def _fix_permissions(self, path: Path):
        """Force current user/group permissions on file/directory."""
        try:
            if path.exists():
                # Get current uid/gid
                uid = os.getuid()
                gid = os.getgid()
                
                # Set owner
                os.chown(path, uid, gid)
                
                # Permissions: 664 for files, 775 for directories
                if path.is_file():
                    current_mode = path.stat().st_mode
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP
                    os.chmod(path, new_mode)
                elif path.is_dir():
                    current_mode = path.stat().st_mode  
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP | stat.S_IXUSR | stat.S_IXGRP
                    os.chmod(path, new_mode)
                    
                logger.debug(f"Fixed permissions for {path}: uid={uid}, gid={gid}")
        except Exception as e:
            logger.warning(f"Could not fix permissions for {path}: {e}")
    
    def _init_db(self):
        """Initialize database."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                cursor = conn.cursor()
                
                # Initialize tables
                self._init_playlists_table()
                self._init_queue_table()
                self._init_history_table()
                self._init_preferences_table()
                
                logger.info(f"MC database ready at {self.db_path}")
        except Exception as e:
            logger.exception(f"Error initializing MC database: {e}")
    

    def _init_playlists_table(self):
        """Initialize playlists table."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS mc_playlist (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        user_name TEXT NOT NULL,
                        server_id TEXT NOT NULL,
                        server_name TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT DEFAULT NULL,
                        active INTEGER DEFAULT 1,
                        UNIQUE(user_id, name)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_mc_playlist_user_id ON mc_playlist (user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_mc_playlist_active ON mc_playlist (active)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating mc_playlist table: {e}")
    
    def _init_queue_table(self):
        """Initialize queue table."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS mc_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL,
                        duration TEXT DEFAULT NULL,
                        artist TEXT DEFAULT NULL,
                        position INTEGER NOT NULL,
                        added_at TEXT NOT NULL,
                        active INTEGER DEFAULT 1
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_mc_queue_server_id ON mc_queue (server_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_mc_queue_position ON mc_queue (position)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_mc_queue_active ON mc_queue (active)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating mc_queue table: {e}")
    
    def _init_history_table(self):
        """Initialize history table."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS mc_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL,
                        duration TEXT DEFAULT NULL,
                        artist TEXT DEFAULT NULL,
                        played_at TEXT NOT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_mc_history_server_id ON mc_history (server_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_mc_history_played_at ON mc_history (played_at)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating mc_history table: {e}")
    
    def _init_preferences_table(self):
        """Initialize user preferences table."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS mc_preferences (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL UNIQUE,
                        default_volume INTEGER DEFAULT 100,
                        default_quality TEXT DEFAULT 'medium',
                        autoplay INTEGER DEFAULT 0,
                        updated_at TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_mc_preferences_user_id ON mc_preferences (user_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating mc_preferences table: {e}")
    
    def create_playlist(self, name: str, user_id: str, user_name: str, 
                          server_id: str, server_name: str) -> bool:
        """Create a new playlist."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR IGNORE INTO mc_playlist 
                        (name, user_id, user_name, server_id, server_name, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (name, user_id, user_name, server_id, server_name, 
                          datetime.now().isoformat()))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error creating playlist: {e}")
            return False
    
    def get_user_playlists(self, user_id: str) -> list:
        """Get all playlists for a user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, name, created_at, updated_at
                    FROM mc_playlist 
                    WHERE user_id = ? AND active = 1
                    ORDER BY created_at DESC
                ''', (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting user playlists: {e}")
            return []
    
    def add_song_to_queue(self, server_id: str, channel_id: str, user_id: str,
                           title: str, url: str, duration: str = None, artist: str = None, 
                           position: int = None) -> bool:
        """Add a song to the playback queue.
        
        Args:
            position: If None, add to end. If 0, add to beginning.
        """
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                    cursor = conn.cursor()
                    
                    if position is None or position == -1:
                        # Add to end (default behavior)
                        cursor.execute('''
                            SELECT MAX(position) FROM mc_queue 
                            WHERE server_id = ? AND channel_id = ? AND active = 1
                        ''', (server_id, channel_id))
                        max_pos = cursor.fetchone()[0] or 0
                        new_position = max_pos + 1
                    elif position == 0:
                        # Add to beginning
                        cursor.execute('''
                            UPDATE mc_queue SET position = position + 1
                            WHERE server_id = ? AND channel_id = ? AND active = 1
                        ''', (server_id, channel_id))
                        new_position = 1
                    else:
                        # Specific position
                        cursor.execute('''
                            UPDATE mc_queue SET position = position + 1
                            WHERE server_id = ? AND channel_id = ? AND active = 1 
                            AND position >= ?
                        ''', (server_id, channel_id, position))
                        new_position = position
                    
                    cursor.execute('''
                        INSERT INTO mc_queue 
                        (server_id, channel_id, user_id, title, url, duration, artist, position, added_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (server_id, channel_id, user_id, title, url, duration, artist, 
                          new_position, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error adding song to queue: {e}")
            return False
    
    def get_queue(self, server_id: str, channel_id: str) -> list:
        """Get current playback queue."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT position, title, url, duration, artist, user_id, added_at
                    FROM mc_queue 
                    WHERE server_id = ? AND channel_id = ? AND active = 1
                    ORDER BY position ASC
                ''', (server_id, channel_id))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting queue: {e}")
            return []
    
    def remove_song_from_queue(self, server_id: str, channel_id: str, position: int) -> bool:
        """Remove a specific song from queue."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                    cursor = conn.cursor()
                    
                    # Mark song as inactive
                    cursor.execute('''
                        UPDATE mc_queue SET active = 0 
                        WHERE server_id = ? AND channel_id = ? AND position = ?
                    ''', (server_id, channel_id, position))
                    
                    # Reorder remaining positions
                    cursor.execute('''
                        UPDATE mc_queue SET position = position - 1 
                        WHERE server_id = ? AND channel_id = ? AND position > ? AND active = 1
                    ''', (server_id, channel_id, position))
                    
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error removing song from queue: {e}")
            return False
    
    def clear_queue(self, server_id: str, channel_id: str) -> bool:
        """Clear entire playback queue."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE mc_queue SET active = 0 
                        WHERE server_id = ? AND channel_id = ?
                    ''', (server_id, channel_id))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error clearing queue: {e}")
            return False
    
    def register_history(self, server_id: str, channel_id: str, user_id: str,
                         title: str, url: str, duration: str = None, artist: str = None) -> bool:
        """Register a song in playback history."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO mc_history 
                        (server_id, channel_id, user_id, title, url, duration, artist, played_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (server_id, channel_id, user_id, title, url, duration, artist,
                          datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error registering history: {e}")
            return False
    
    def get_history(self, server_id: str, channel_id: str, limit: int = 10) -> list:
        """Get recent playback history."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT title, url, duration, artist, user_id, played_at
                    FROM mc_history 
                    WHERE server_id = ? AND channel_id = ?
                    ORDER BY played_at DESC
                    LIMIT ?
                ''', (server_id, channel_id, limit))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting history: {e}")
            return []
    
    def get_statistics(self, server_id: str = None) -> dict:
        """Get basic MC statistics."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # General statistics
                cursor.execute('SELECT COUNT(*) FROM mc_playlist WHERE active = 1')
                playlists_total = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM mc_queue WHERE active = 1')
                queue_total = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM mc_history')
                historial_total = cursor.fetchone()[0]
                
                # Server-specific statistics if specified
                if server_id:
                    cursor.execute('SELECT COUNT(*) FROM mc_queue WHERE server_id = ? AND active = 1', (server_id,))
                    queue_server = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT COUNT(*) FROM mc_history WHERE server_id = ?', (server_id,))
                    history_server = cursor.fetchone()[0]
                else:
                    queue_server = 0
                    history_server = 0
                
                return {
                    'playlists_total': playlists_total,
                    'queue_total': queue_total,
                    'historial_total': historial_total,
                    'queue_servidor': queue_server,
                    'historial_servidor': history_server
                }
        except Exception as e:
            logger.exception(f"Error getting statistics: {e}")
            return {}
    
    def clean_old_queue(self, days: int = 7) -> int:
        """Clean old queue entries (older than X days)."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                    cursor = conn.cursor()
                    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
                    
                    cursor.execute('''
                        UPDATE mc_queue SET active = 0 
                        WHERE added_at < ? AND active = 1
                    ''', (cutoff_date,))
                    
                    cleaned_count = cursor.rowcount
                    conn.commit()
                    logger.info(f"Cleaned {cleaned_count} old queue entries older than {days} days")
                    return cleaned_count
        except Exception as e:
            logger.exception(f"Error cleaning old queue: {e}")
            return 0
    
    def clean_old_history(self, days: int = 30) -> int:
        """Clean old history entries (older than X days)."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30.0) as conn:
                    cursor = conn.cursor()
                    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
                    
                    cursor.execute('''
                        DELETE FROM mc_history 
                        WHERE played_at < ?
                    ''', (cutoff_date,))
                    
                    cleaned_count = cursor.rowcount
                    conn.commit()
                    logger.info(f"Cleaned {cleaned_count} old history entries older than {days} days")
                    return cleaned_count
        except Exception as e:
            logger.exception(f"Error cleaning old history: {e}")
            return 0


def get_mc_db_instance(server_id: str = "default") -> DatabaseRoleMC:
    """Get an instance of the MC database."""
    return DatabaseRoleMC(server_id)
