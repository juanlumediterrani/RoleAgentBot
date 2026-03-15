import json
import sqlite3
import threading
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Optional
from agent_logging import get_logger

try:
    logger = get_logger('global_news_db')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('global_news_db')

class GlobalNewsDatabase:
    """Global database for news tracking across all servers.
    Prevents duplicate news processing across different servers.
    """
    
    def __init__(self, db_path: Path = None):
        if db_path is None:
            # Use a global database in the data directory
            from agent_db import get_data_dir
            data_dir = get_data_dir()
            self.db_path = data_dir / "global_news.db"
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_writable_db()
        self._init_db()
    
    def _ensure_writable_db(self):
        """Check that DB is accessible and force correct permissions."""
        try:
            # Ensure directory exists with correct permissions
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._fix_permissions(self.db_path.parent)
            
            # Connect and force file permissions
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=DELETE;')
            conn.close()
            
            # Force DB file permissions
            self._fix_permissions(self.db_path)
            
        except Exception as e:
            logger.error(f"Cannot access global news database at {self.db_path}: {e}")
            raise
    
    def _fix_permissions(self, path: Path):
        """Force current user/group permissions on file/directory."""
        try:
            if path.exists():
                # Get current uid/gid
                uid = os.getuid()
                gid = os.getgid()
                
                # Change owner
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
        """Initialize database with global news tracking tables."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=DELETE;")
                conn.commit()
                
                # Initialize global news tracking table
                self._init_global_news_table()
                
                logger.info(f"✅ Global news database ready at {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error initializing global news database: {e}")
    
    def _init_global_news_table(self):
        """Initialize global news tracking table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS global_news (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title_hash TEXT NOT NULL UNIQUE,
                        title TEXT NOT NULL,
                        first_seen TEXT NOT NULL,
                        source_url TEXT DEFAULT NULL,
                        feed_category TEXT DEFAULT NULL,
                        server_count INTEGER DEFAULT 1,
                        last_processed TEXT NOT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_global_news_hash ON global_news (title_hash)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_global_news_seen ON global_news (first_seen)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_global_news_category ON global_news (feed_category)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating global_news table: {e}")
    
    def _generate_title_hash(self, title: str) -> str:
        """Generate simple hash of title to avoid duplicates."""
        import hashlib
        return hashlib.md5(title.encode('utf-8')).hexdigest()
    
    def is_news_globally_processed(self, title: str) -> bool:
        """Check if news has been processed by any server."""
        try:
            title_hash = self._generate_title_hash(title)
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT 1 FROM global_news WHERE title_hash = ?', (title_hash,))
                    return cursor.fetchone() is not None
        except Exception as e:
            logger.exception(f"Error checking if news is globally processed: {e}")
            return False
    
    def mark_news_globally_processed(self, title: str, source_url: str = None, feed_category: str = None, server_id: str = None):
        """Mark news as processed globally."""
        try:
            title_hash = self._generate_title_hash(title)
            current_date = datetime.now().isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO global_news 
                        (title_hash, title, first_seen, source_url, feed_category, server_count, last_processed)
                        VALUES (?, ?, ?, ?, ?, 
                                COALESCE((SELECT server_count FROM global_news WHERE title_hash = ?), 0) + 1, ?)
                    ''', (title_hash, title, current_date, source_url, feed_category, title_hash, current_date))
                    conn.commit()
                    logger.debug(f"Marked news as globally processed: {title[:50]}...")
        except Exception as e:
            logger.exception(f"Error marking news as globally processed: {e}")
    
    def get_global_news_stats(self) -> dict:
        """Get statistics about globally processed news."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Count total unique news
                cursor.execute('SELECT COUNT(*) FROM global_news')
                total_news = cursor.fetchone()[0]
                
                # Count by category
                cursor.execute('''
                    SELECT feed_category, COUNT(*) 
                    FROM global_news 
                    WHERE feed_category IS NOT NULL
                    GROUP BY feed_category
                ''')
                by_category = dict(cursor.fetchall())
                
                # Last processed
                cursor.execute('SELECT MAX(last_processed) FROM global_news')
                last_processed = cursor.fetchone()[0]
                
                # Most active servers (approximate)
                cursor.execute('SELECT SUM(server_count) FROM global_news')
                total_processing = cursor.fetchone()[0]
                
                return {
                    'total_unique_news': total_news,
                    'by_category': by_category,
                    'last_processed': last_processed,
                    'total_processing_events': total_processing
                }
                
        except Exception as e:
            logger.exception(f"Error getting global news stats: {e}")
            return {
                'total_unique_news': 0,
                'by_category': {},
                'last_processed': None,
                'total_processing_events': 0
            }
    
    def cleanup_old_news(self, days_to_keep: int = 30):
        """Clean up old news entries to prevent database bloat."""
        try:
            date_limit = (datetime.now() - timedelta(days=days_to_keep)).isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM global_news WHERE first_seen < ?', (date_limit,))
                    deleted_count = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"🧹 Cleaned up {deleted_count} old global news entries (older than {days_to_keep} days)")
                    return deleted_count
                    
        except Exception as e:
            logger.exception(f"Error cleaning up old global news: {e}")
            return 0


# Global instance
_global_news_db_instance: Optional[GlobalNewsDatabase] = None

def get_global_news_db() -> GlobalNewsDatabase:
    """Get or create the global news database instance."""
    global _global_news_db_instance
    if _global_news_db_instance is None:
        _global_news_db_instance = GlobalNewsDatabase()
    return _global_news_db_instance
