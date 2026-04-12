import json
import sqlite3
import threading
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple
from agent_logging import get_logger

try:
    logger = get_logger('db_role_news_watcher')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_news_watcher')

from agent_db import get_server_db_path_fallback, get_personality_name

def get_db_path(server_id: str = "default") -> Path:
    """Generate database path for news watcher with personality name."""
    personality_name = get_personality_name(server_id)
    db_name = f"watcher_{personality_name}"
    return get_server_db_path_fallback(server_id, db_name)


class DatabaseRoleNewsWatcher:
    """Specialized database for News Watcher.
    Manages read news and sent notifications.
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
            logger.error(f"Cannot access database at {self.db_path}: {e}")
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
        """Initialize database with DELETE configuration."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=DELETE;")
                conn.commit()
                
                # Initialize tables
                self._init_read_news_table()
                self._init_sent_notifications_table()
                self._init_unified_subscriptions_table()  # New unified table
                self._init_feeds_table()
                self._init_user_premises_table()
                self._init_configuracion_table()
                self.insert_default_feeds()
                # Feed health check moved to on_guild_join event to avoid running on every !canvas command
                
                logger.info(f"✅ News watcher database ready at {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error initializing news watcher database: {e}")
    
    def _init_read_news_table(self):
        """Initialize read news table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS read_news (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        titulo TEXT NOT NULL UNIQUE,
                        title_hash TEXT NOT NULL UNIQUE,
                        read_date TEXT NOT NULL,
                        source TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_read_news_hash ON read_news (title_hash)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_read_news_date ON read_news (read_date)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating read_news table: {e}")
    
    def _init_sent_notifications_table(self):
        """Initialize sent notifications table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS sent_notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        titulo TEXT NOT NULL,
                        title_hash TEXT NOT NULL,
                        notification_type TEXT NOT NULL,
                        analisis TEXT NOT NULL,
                        sent_date TEXT NOT NULL,
                        source TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notificaciones_hash ON sent_notifications (title_hash)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notificaciones_fecha ON sent_notifications (sent_date)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notificaciones_tipo ON sent_notifications (notification_type)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating sent_notifications table: {e}")
    
    def _generate_title_hash(self, title: str) -> str:
        """Generate simple hash of title to avoid duplicates."""
        import hashlib
        return hashlib.md5(title.lower().strip().encode('utf-8')).hexdigest()
    
    def is_news_read(self, title: str) -> bool:
        """Check if news was already read."""
        try:
            title_hash = self._generate_title_hash(title)
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT 1 FROM read_news WHERE title_hash = ?', (title_hash,))
                    return cursor.fetchone() is not None
        except Exception as e:
            logger.exception(f"Error checking if news was read: {e}")
            return False
    
    def mark_news_as_read(self, title: str, source: str = None) -> bool:
        """Mark a news as read."""
        try:
            title_hash = self._generate_title_hash(title)
            current_date = datetime.now().isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR IGNORE INTO read_news (titulo, title_hash, read_date, source)
                        VALUES (?, ?, ?, ?)
                    ''', (title, title_hash, current_date, source))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error marking news as read: {e}")
            return False
    
    def mark_notification_sent(self, title: str, notification_type: str, analysis: str, source: str = None) -> bool:
        """Record a sent notification."""
        try:
            title_hash = self._generate_title_hash(title)
            current_date = datetime.now().isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO sent_notifications 
                        (titulo, title_hash, notification_type, analisis, sent_date, source)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (title, title_hash, notification_type, analysis, current_date, source))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error recording sent notification: {e}")
            return False
    
    def clean_old_news(self, dias: int = 30) -> bool:
        """Clean news older than N days."""
        try:
            date_limit = (datetime.now() - timedelta(days=dias)).isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Clean read news
                    cursor.execute('DELETE FROM read_news WHERE read_date < ?', (date_limit,))
                    news_deleted = cursor.rowcount
                    
                    # Clean sent notifications
                    cursor.execute('DELETE FROM sent_notifications WHERE sent_date < ?', (date_limit,))
                    notifications_deleted = cursor.rowcount
                    
                    conn.commit()
                    logger.info(f"🧹 Cleanup: {news_deleted} news and {notifications_deleted} old notifications")
                    return True
        except Exception as e:
            logger.exception(f"Error cleaning old news: {e}")
            return False
    
    def get_statistics(self) -> dict:
        """Get basic database statistics."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Count read news
                cursor.execute('SELECT COUNT(*) FROM read_news')
                read_news = cursor.fetchone()[0]
                
                # Count sent notifications
                cursor.execute('SELECT COUNT(*) FROM sent_notifications')
                sent_notifications = cursor.fetchone()[0]
                
                # Count active subscriptions
                cursor.execute('SELECT COUNT(*) FROM subscriptions WHERE is_active = 1')
                active_subscriptions = cursor.fetchone()[0]
                
                # Count subscriptions by method
                cursor.execute('SELECT method, COUNT(*) FROM subscriptions WHERE is_active = 1 GROUP BY method')
                subscriptions_by_method = dict(cursor.fetchall())
                
                # Last activity
                cursor.execute('SELECT MAX(read_date) FROM read_news')
                last_news = cursor.fetchone()[0]
                
                cursor.execute('SELECT MAX(sent_date) FROM sent_notifications')
                last_notification = cursor.fetchone()[0]
                
                return {
                    'read_news': read_news,
                    'sent_notifications': sent_notifications,
                    'active_subscriptions': active_subscriptions,
                    'subscriptions_by_method': subscriptions_by_method,
                    'last_news': last_news,
                    'last_notification': last_notification
                }
        except Exception as e:
            logger.exception(f"Error getting statistics: {e}")
            return {}


    def _init_unified_subscriptions_table(self):
        """Initialize unified subscriptions table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions (
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
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions (user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_channel ON subscriptions (channel_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_category ON subscriptions (category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_method ON subscriptions (method)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_active ON subscriptions (is_active)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating unified subscriptions table: {e}")

    def _init_subscriptions_table(self):
        """Initialize watcher subscriptions table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions_watcher (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL UNIQUE,
                        user_name TEXT NOT NULL,
                        subscribed_at TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions_watcher (user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_is_active ON subscriptions_watcher (is_active)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating subscriptions_watcher table: {e}")
    
    def _init_feeds_table(self):
        """Initialize configurable feeds table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS feeds_config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        url TEXT NOT NULL UNIQUE,
                        category TEXT NOT NULL,
                        country TEXT DEFAULT NULL,
                        language TEXT DEFAULT 'es',
                        keywords TEXT DEFAULT NULL,
                        priority INTEGER DEFAULT 0,
                        active INTEGER DEFAULT 1,
                        feed_type TEXT DEFAULT 'especializado',
                        created_at TEXT NOT NULL,
                        updated_at TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_category ON feeds_config (category)')
                
                # Migration: Add missing columns for legacy databases
                cursor.execute('PRAGMA table_info(feeds_config)')
                columns = cursor.fetchall()
                column_names = {col[1] for col in columns}
                
                migrations = [
                    ('country', 'TEXT DEFAULT NULL'),
                    ('language', "TEXT DEFAULT 'es'"),
                    ('keywords', 'TEXT DEFAULT NULL'),
                    ('priority', 'INTEGER DEFAULT 0'),
                    ('active', 'INTEGER DEFAULT 1')
                ]
                
                for col_name, col_def in migrations:
                    if col_name not in column_names:
                        cursor.execute(f'ALTER TABLE feeds_config ADD COLUMN {col_name} {col_def}')
                        logger.info(f"🔄 Migrated feeds_config: added {col_name} column")
                
                # Create indexes after ensuring columns exist
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_active ON feeds_config (active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_priority ON feeds_config (priority)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_feed_type ON feeds_config (feed_type)')
                
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating feeds_config table: {e}")

    def _init_user_premises_table(self):
        """Initialize user premises table for standalone premise storage."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_premises (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        premise_text TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(user_id, premise_text)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_premises_user_id ON user_premises (user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_premises_created_at ON user_premises (created_at)')
                
                # Table to track user initializations
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_initializations (
                        user_id TEXT PRIMARY KEY,
                        initialized_at TEXT NOT NULL,
                        guild_id TEXT NOT NULL
                    )
                ''')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating user_premises table: {e}")

    def _init_channel_premises_table(self):
        """Initialize channel premises table for standalone premise storage."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS channel_premises (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id TEXT NOT NULL,
                        premise_text TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(channel_id, premise_text)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_channel_premises_channel_id ON channel_premises (channel_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_channel_premises_created_at ON channel_premises (created_at)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating channel_premises table: {e}")
    
    def insert_default_feeds(self):
        """Insert default feeds if they don't exist."""
        try:
            default_feeds = [
                # Economy/Finance Feeds
                {
                    'name': 'Reuters Business',
                    'url': 'https://feeds.bloomberg.com/markets/news.rss',
                    'category': 'economy',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'market,stock,economy,business,finance',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Financial Times',
                    'url': 'https://www.cnbc.com/id/100003114/device/rss/rss.html',
                    'category': 'economy',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'economy,finance,markets,trade',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Bloomberg Markets',
                    'url': 'https://feeds.macrumors.com/public',
                    'category': 'economy',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'markets,stocks,economy,trading',
                    'feed_type': 'general'
                },
                
                # International News Feeds
                {
                    'name': 'Reuters World',
                    'url': 'http://rss.cnn.com/rss/edition_world.rss',
                    'category': 'international',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'war,conflict,crisis,government,politics',
                    'feed_type': 'general'
                },
                {
                    'name': 'BBC World News',
                    'url': 'https://feeds.bbci.co.uk/news/world/rss.xml',
                    'category': 'international',
                    'country': 'UK',
                    'language': 'en',
                    'keywords': 'world,conflict,diplomacy,crisis',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Al Jazeera English',
                    'url': 'https://www.aljazeera.com/xml/rss/all.xml',
                    'category': 'international',
                    'country': 'QA',
                    'language': 'en',
                    'keywords': 'middle-east,conflict,politics,diplomacy',
                    'feed_type': 'general'
                },
                
                # Technology Feeds
                {
                    'name': 'BBC Technology',
                    'url': 'https://feeds.bbci.co.uk/news/technology/rss.xml',
                    'category': 'technology',
                    'country': 'UK',
                    'language': 'en',
                    'keywords': 'ai,technology,cybersecurity,innovation',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'TechCrunch',
                    'url': 'https://techcrunch.com/feed/',
                    'category': 'technology',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'startups,ai,technology,innovation',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Ars Technica',
                    'url': 'https://feeds.arstechnica.com/arstechnica/index',
                    'category': 'technology',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'technology,science,gadgets,security',
                    'feed_type': 'general'
                },
                
                # General News Feeds
                {
                    'name': 'Reuters Top News',
                    'url': 'https://feeds.feedburner.com/TechCrunch',
                    'category': 'general',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'breaking,news,world,events',
                    'feed_type': 'general'
                },
                {
                    'name': 'Associated Press News',
                    'url': 'https://www.wired.com/feed/rss',
                    'category': 'general',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'breaking,news,us,world',
                    'feed_type': 'general'
                },
                {
                    'name': 'The Guardian World',
                    'url': 'https://www.theguardian.com/world/rss',
                    'category': 'general',
                    'country': 'UK',
                    'language': 'en',
                    'keywords': 'world,politics,society,culture',
                    'feed_type': 'general'
                },
                
                # Crypto/Blockchain Feeds
                {
                    'name': 'Cointelegraph',
                    'url': 'https://cointelegraph.com/rss',
                    'category': 'crypto',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'bitcoin,cryptocurrency,blockchain,ethereum',
                    'feed_type': 'keywords'
                },
                {
                    'name': 'CoinDesk',
                    'url': 'https://www.zdnet.com/news/rss.xml',
                    'category': 'crypto',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'bitcoin,crypto,defi,nft,trading',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Decrypt',
                    'url': 'https://decrypt.co/feed',
                    'category': 'crypto',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'cryptocurrency,blockchain,web3,defi',
                    'feed_type': 'general'
                },
                
                # Gaming Feeds
                {
                    'name': 'IGN Games',
                    'url': 'http://feeds.feedburner.com/ign/games-all',
                    'category': 'gaming',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'gaming,video-games,game-reviews,game-news',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'GameSpot',
                    'url': 'https://www.gamespot.com/feeds/mashup',
                    'category': 'gaming',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'gaming,video-games,reviews,news',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Kotaku',
                    'url': 'https://kotaku.com/rss',
                    'category': 'gaming',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'gaming,video-games,culture,reviews',
                    'feed_type': 'general'
                },
                {
                    'name': 'PC Gamer',
                    'url': 'https://www.pcgamer.com/rss/',
                    'category': 'gaming',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'pc-gaming,gaming,hardware,reviews',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Polygon',
                    'url': 'https://www.polygon.com/rss/index.xml',
                    'category': 'gaming',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'gaming,video-games,culture,reviews',
                    'feed_type': 'general'
                },
                {
                    'name': 'Eurogamer',
                    'url': 'https://www.eurogamer.net/feed',
                    'category': 'gaming',
                    'country': 'UK',
                    'language': 'en',
                    'keywords': 'gaming,video-games,reviews,news',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Rock Paper Shotgun',
                    'url': 'https://www.rockpapershotgun.com/feed',
                    'category': 'gaming',
                    'country': 'UK',
                    'language': 'en',
                    'keywords': 'pc-gaming,gaming,reviews,indie',
                    'feed_type': 'general'
                },
                {
                    'name': 'Game Informer',
                    'url': 'https://gameinformer.com/rss.xml',
                    'category': 'gaming',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'gaming,video-games,reviews,previews',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'The Verge Games',
                    'url': 'https://www.theverge.com/rss/games/index.xml',
                    'category': 'gaming',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'gaming,video-games,tech,culture',
                    'feed_type': 'general'
                },
                
                # Patch Notes Feeds
                {
                    'name': 'Steam News',
                    'url': 'https://store.steampowered.com/feeds/news.xml',
                    'category': 'patch_notes',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'steam,patch,updates,pc-gaming,valve',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'PlayStation Blog',
                    'url': 'https://blog.playstation.com/feed',
                    'category': 'patch_notes',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'playstation,ps5,ps4,updates,patch-notes',
                    'feed_type': 'especializado'
                }
            ]
            
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                for feed in default_feeds:
                    cursor.execute('''
                        INSERT OR IGNORE INTO feeds_config 
                        (name, url, category, country, language, keywords, feed_type, active, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        feed['name'], feed['url'], feed['category'], 
                        feed['country'], feed['language'], feed['keywords'],
                        feed['feed_type'], 1, datetime.now().isoformat()
                    ))
                conn.commit()
                logger.info("✅ Default feeds inserted")
        except Exception as e:
            logger.exception(f"❌ Error inserting default feeds: {e}")
    
    def add_feed(self, name: str, url: str, category: str, country: str = None, 
                   language: str = 'es', keywords: str = None, feed_type: str = 'especializado') -> bool:
        """Add a new configured feed."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO feeds_config 
                        (name, url, category, country, language, keywords, feed_type, active,
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (name, url, category, country, language, keywords, feed_type, 1,
                         datetime.now().isoformat(), datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error adding feed: {e}")
            return False
    
    def get_active_feeds(self, category: str = None) -> list:
        """Get active feeds, optionally filtered by category."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                if category:
                    cursor.execute('''
                        SELECT id, name, url, category, country, language, priority, keywords, feed_type
                        FROM feeds_config 
                        WHERE active = 1 AND category = ?
                        ORDER BY priority DESC, name
                    ''', (category,))
                else:
                    cursor.execute('''
                        SELECT id, name, url, category, country, language, priority, keywords, feed_type
                        FROM feeds_config 
                        WHERE active = 1
                        ORDER BY priority DESC, name
                    ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting active feeds: {e}")
            return []
    
    def get_feed_by_id(self, feed_id: int) -> list:
        """Get a specific feed by its ID."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, name, url, category, country, language, priority, keywords, feed_type
                    FROM feeds_config 
                    WHERE id = ? AND active = 1
                ''', (feed_id,))
                result = cursor.fetchone()
                return result if result else None
        except Exception as e:
            logger.exception(f"Error getting feed by ID: {e}")
            return None
    
    def get_available_categories(self) -> list:
        """Get available categories with active feeds."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT category, COUNT(*) as count
                    FROM feeds_config 
                    WHERE active = 1
                    GROUP BY category
                    ORDER BY category
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting categories: {e}")
            return []
    
    def subscribe_user_category(self, user_id: str, category: str, feed_id: int = None) -> bool:
        """Subscribe a user to a category or a specific feed."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions_categories 
                        (user_id, category, feed_id, subscribed_at, is_active)
                        VALUES (?, ?, ?, ?, 1)
                    ''', (user_id, category.lower(), feed_id, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error subscribing user to category: {e}")
            return False
    
    def subscribe_user_category_ai(self, user_id: str, category: str, feed_id: int = None, premises: str = None) -> bool:
        """Subscribe a user to a category with AI analysis using unified system."""
        try:
            # Use the unified create_subscription method
            result = self.create_subscription(
                user_id=user_id,
                channel_id=None,
                category=category.lower(),
                feed_id=feed_id,
                premises=premises,
                method="general",
                created_by=user_id
            )
            return result is not None
        except Exception as e:
            logger.exception(f"Error subscribing user to category with AI analysis: {e}")
            return False
    
    def cancel_category_subscription(self, user_id: str, category: str, feed_id: int = None) -> bool:
        """Cancel user subscription to category/feed."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    if feed_id:
                        cursor.execute('''
                            UPDATE subscriptions_categories SET is_active = 0 
                            WHERE user_id = ? AND category = ? AND feed_id = ?
                        ''', (user_id, category, feed_id))
                    else:
                        cursor.execute('''
                            UPDATE subscriptions_categories SET is_active = 0 
                            WHERE user_id = ? AND category = ? AND feed_id IS NULL
                        ''', (user_id, category))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error canceling subscription: {e}")
            return False
    
    def get_user_subscriptions(self, user_id: str) -> list:
        """Get active subscriptions of a user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT category, feed_id, subscribed_at
                    FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1 AND (user_premises IS NULL OR user_premises = '')
                ''', (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting user subscriptions: {e}")
            return []
    
    def get_subscribers_by_category(self, category: str, feed_id: int = None) -> list:
        """Get users subscribed to a specific category or feed."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                if feed_id:
                    cursor.execute('''
                        SELECT DISTINCT sc.user_id
                        FROM subscriptions_categories sc
                        WHERE sc.category = ? AND sc.feed_id = ? AND sc.is_active = 1
                        UNION
                        SELECT DISTINCT sv.user_id
                        FROM subscriptions_watcher sv
                        WHERE sv.is_active = 1
                    ''', (category, feed_id))
                else:
                    cursor.execute('''
                        SELECT DISTINCT sc.user_id
                        FROM subscriptions_categories sc
                        WHERE sc.category = ? AND sc.feed_id IS NULL AND sc.is_active = 1
                        UNION
                        SELECT DISTINCT sv.user_id
                        FROM subscriptions_watcher sv
                        WHERE sv.is_active = 1
                    ''', (category,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.exception(f"Error getting subscribers by category: {e}")
            return []
    
    def subscribe_keywords(self, user_id: str, keywords: str, channel_id: str = None, category: str = None, feed_id: int = None) -> bool:
        """Subscribe user or channel to specific keywords (optionally in category/feed) using unified system."""
        try:
            # Require category for keyword subscriptions - no more global_keywords
            if category is None:
                logger.warning(f"subscribe_keywords called without category for user {user_id} - rejecting")
                return False
            
            # Use the unified create_subscription method
            result = self.create_subscription(
                user_id=user_id if not channel_id else None,
                channel_id=channel_id,
                category=category,
                feed_id=feed_id,
                keywords=keywords,
                method="keyword",
                created_by=user_id
            )
            return result is not None
        except Exception as e:
            logger.exception(f"Error subscribing keywords: {e}")
            return False
    
    def cancel_keyword_subscription(self, user_id: str, keywords: str, channel_id: str = None) -> bool:
        """Cancel keyword subscription."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE subscriptions_keywords SET is_active = 0 
                        WHERE user_id = ? AND keywords = ? AND channel_id = ?
                    ''', (user_id, keywords, channel_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error canceling keyword subscription: {e}")
            return False
    
    def get_keyword_subscriptions(self, user_id: str, channel_id: str = None) -> list:
        """Get keyword subscriptions of a user or channel."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT keywords, subscribed_at
                    FROM subscriptions_keywords 
                    WHERE user_id = ? AND channel_id = ? AND is_active = 1
                ''', (user_id, channel_id))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting keyword subscriptions: {e}")
            return []
    
    def get_keyword_subscribers(self) -> list:
        """Get all active keyword subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, channel_id, keywords
                    FROM subscriptions_keywords 
                    WHERE is_active = 1
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting keyword subscribers: {e}")
            return []
    
    def check_news_keywords_match(self, titulo: str) -> list:
        """Check if a news headline matches keyword subscriptions."""
        try:
            keyword_subscribers = self.get_keyword_subscribers()
            matches = []

            title_lower = titulo.lower()

            for user_id, channel_id, keywords in keyword_subscribers:
                # Handle both string and list inputs for keywords
                if isinstance(keywords, list):
                    keyword_list = [str(p).strip().lower() for p in keywords if p and str(p).strip()]
                elif isinstance(keywords, str):
                    keyword_list = [p.strip().lower() for p in keywords.split(',')]
                else:
                    logger.warning(f"Invalid keywords type: {type(keywords)} for user {user_id}")
                    continue
                
                # Check if any keyword is in the title
                if any(keyword in title_lower for keyword in keyword_list):
                    if channel_id:
                        matches.append(f"channel_{channel_id}")
                    else:
                        matches.append(user_id)

            return matches
        except Exception as e:
            logger.exception(f"Error checking keywords: {e}")
            return []
    
    def subscribe_channel_category(self, channel_id: str, channel_name: str, server_id: str, 
                                 category: str, feed_id: int = None) -> bool:
        """Subscribe a channel to a specific category or feed."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions_channels 
                        (channel_id, channel_name, server_id, server_name, category, feed_id, subscribed_at, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ''', (channel_id, channel_name, server_id, server_name, category, 
                         feed_id, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error subscribing channel to category: {e}")
            return False
    
    def subscribe_channel_category_keywords(self, channel_id: str, channel_name: str, server_id: str, 
                                       category: str, feed_id: int = None, keywords: str = None, user_id: str = None) -> bool:
        """Subscribe a channel to keywords in a specific category or feed."""
        try:
            # Use the unified create_subscription method
            result = self.create_subscription(
                user_id=None,
                channel_id=channel_id,
                category=category,
                feed_id=feed_id,
                keywords=keywords,
                method="keyword",
                created_by=user_id
            )
            return result is not None
        except Exception as e:
            logger.exception(f"Error subscribing channel to keywords: {e}")
            return False
    
    def cancel_channel_subscription(self, channel_id: str, category: str, feed_id: int = None) -> bool:
        """Cancel channel subscription to category/feed."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    if feed_id:
                        cursor.execute('''
                            UPDATE subscriptions_channels SET is_active = 0 
                            WHERE channel_id = ? AND category = ? AND feed_id = ?
                        ''', (channel_id, category, feed_id))
                    else:
                        cursor.execute('''
                            UPDATE subscriptions_channels SET is_active = 0 
                            WHERE channel_id = ? AND category = ? AND feed_id IS NULL
                        ''', (channel_id, category))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error canceling channel subscription: {e}")
            return False
    
    def subscribe_channel_category_ai(self, channel_id: str, channel_name: str, server_id: str, 
                                   category: str, feed_id: int = None, premises: str = None, user_id: str = None) -> bool:
        """Subscribe a channel to a category with AI analysis."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Add channel to subscriptions_channels table only
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions_channels 
                        (channel_id, channel_name, server_id, server_name, category, feed_id, subscribed_at, is_active, channel_premises, user_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    ''', (channel_id, channel_name, server_id, server_id, category, feed_id, datetime.now().isoformat(), premises, user_id))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error subscribing channel to category with AI analysis: {e}")
            return False
    
    def get_user_with_premises_for_server(self, guild_id: str) -> str:
        """Get a user ID that has premises for this server."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Try to find users with premises in user_premises table
                cursor.execute('''
                    SELECT DISTINCT user_id 
                    FROM user_premises 
                    LIMIT 1
                ''')
                result = cursor.fetchone()
                
                if result:
                    return result[0]
                
                return None
        except Exception as e:
            logger.exception(f"Error getting user with premises: {e}")
            return None
    
    def get_channel_subscriptions(self, channel_id: str) -> list:
        """Get active subscriptions for a channel."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Get subscriptions from subscriptions_channels table
                cursor.execute('''
                    SELECT category, feed_id, subscribed_at
                    FROM subscriptions_channels 
                    WHERE channel_id = ? AND is_active = 1
                ''', (channel_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting channel subscriptions: {e}")
            return []
    
        
    def get_all_channels_with_subscriptions(self) -> list:
        """Get all channels with active subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Get channels from subscriptions_channels table
                cursor.execute('''
                    SELECT DISTINCT channel_id, channel_name, server_id
                    FROM subscriptions_channels 
                    WHERE is_active = 1
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all channels with subscriptions: {e}")
            return []
    
    def get_subscribed_channels_by_category(self, category: str, feed_id: int = None) -> list:
        """Get channels subscribed to a specific category or feed."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                if feed_id:
                    cursor.execute('''
                        SELECT DISTINCT channel_id, channel_name, server_id
                        FROM subscriptions_channels
                        WHERE category = ? AND feed_id = ? AND is_active = 1
                    ''', (category, feed_id))
                else:
                    cursor.execute('''
                        SELECT DISTINCT channel_id, channel_name, server_id
                        FROM subscriptions_channels
                        WHERE category = ? AND feed_id IS NULL AND is_active = 1
                    ''', (category,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting subscribed channels by category: {e}")
            return []
    
    def get_all_subscribers_by_category(self, category: str, feed_id: int = None) -> list:
        """Get users subscribed to a specific category or feed (including channels)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Get individual subscribers
                individual_subscribers = []
                if feed_id:
                    cursor.execute('''
                        SELECT DISTINCT sc.user_id
                        FROM subscriptions_categories sc
                        WHERE sc.category = ? AND sc.feed_id = ? AND sc.is_active = 1
                        UNION
                        SELECT DISTINCT sv.user_id
                        FROM subscriptions_watcher sv
                        WHERE sv.is_active = 1
                    ''', (category, feed_id))
                else:
                    cursor.execute('''
                        SELECT DISTINCT sc.user_id
                        FROM subscriptions_categories sc
                        WHERE sc.category = ? AND sc.feed_id IS NULL AND sc.is_active = 1
                        UNION
                        SELECT DISTINCT sv.user_id
                        FROM subscriptions_watcher sv
                        WHERE sv.is_active = 1
                    ''', (category,))
                individual_subscribers = [row[0] for row in cursor.fetchall()]
                
                # Get channels (marked with a special prefix for identification)
                channels = []
                if feed_id:
                    cursor.execute('''
                        SELECT DISTINCT channel_id
                        FROM subscriptions_channels
                        WHERE category = ? AND feed_id = ? AND is_active = 1
                    ''', (category, feed_id))
                else:
                    cursor.execute('''
                        SELECT DISTINCT channel_id
                        FROM subscriptions_channels
                        WHERE category = ? AND feed_id IS NULL AND is_active = 1
                    ''', (category,))
                channels = [f"channel_{row[0]}" for row in cursor.fetchall()]
                
                return individual_subscribers + channels
        except Exception as e:
            logger.exception(f"Error getting subscribers by category: {e}")
            return []
    
    def add_subscription(self, user_id: str, user_name: str) -> bool:
        """Add a user subscription to the watcher."""
        try:
            current_date = datetime.now().isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions_watcher 
                        (user_id, user_name, subscribed_at, is_active)
                        VALUES (?, ?, ?, 1)
                    ''', (user_id, user_name, current_date))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error adding subscription: {e}")
            return False
    
    def remove_subscription(self, user_id: str) -> bool:
        """Remove a user subscription from the watcher."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE subscriptions_watcher SET is_active = 0 
                        WHERE user_id = ?
                    ''', (user_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error removing subscription: {e}")
            return False
    
    def get_active_subscribers(self) -> list:
        """Get list of active subscribers."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, user_name, subscribed_at 
                    FROM subscriptions_watcher 
                    WHERE is_active = 1
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting subscribers: {e}")
            return []
    
    def is_subscribed(self, user_id: str) -> bool:
        """Check if a user is subscribed."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 1 FROM subscriptions_watcher 
                    WHERE user_id = ? AND is_active = 1
                ''', (user_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.exception(f"Error checking subscription: {e}")
            return False
    
    def get_all_active_keyword_subscriptions(self) -> list:
        """Get all active keyword subscriptions (user subscriptions only)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, channel_id, keywords, category, feed_id
                    FROM subscriptions_keywords 
                    WHERE is_active = 1 AND (channel_id IS NULL OR channel_id = '')
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all keyword subscriptions: {e}")
            return []
    
    # ===== USER PREMISES MANAGEMENT =====
    
    def get_user_premises(self, user_id: str) -> list:
        """Get customized premises for a user."""
        try:
            # Only get from the new dedicated table - skip old subscription premises
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT premise_text 
                    FROM user_premises 
                    WHERE user_id = ? 
                    ORDER BY created_at ASC
                ''', (user_id,))
                results = cursor.fetchall()
                
                if results:
                    return [row[0] for row in results]
                
                # OLD CODE: Fallback to old method (subscriptions_categories) - COMMENTED OUT
                # This was causing the issue with old global premises being used
                # with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                #     cursor = conn.cursor()
                #     cursor.execute('''
                #         SELECT DISTINCT user_premises
                #         FROM subscriptions_categories 
                #         WHERE user_id = ? AND is_active = 1 AND user_premises IS NOT NULL
                #     ''', (user_id,))
                #     result = cursor.fetchone()
                #     
                #     if result and result[0]:
                #         try:
                #             # Try to parse as JSON first
                #             return json.loads(result[0])
                #         except json.JSONDecodeError:
                #             # If not JSON, treat as comma-separated plain text
                #             premises_text = result[0]
                #             if premises_text:
                #                 return [premise.strip() for premise in premises_text.split(',')]
                #             return []
                return []
        except Exception as e:
            logger.exception(f"Error getting user premises: {e}")
            return []
    
    def update_user_premises(self, user_id: str, premises: list) -> bool:
        """Update customized premises for a user."""
        try:
            limit = self._get_premises_limit()
            if len(premises) > limit:
                logger.warning(f"User {user_id} tried to save more than {limit} premises")
                return False
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM user_premises WHERE user_id = ?', (user_id,))

                    for premise in premises:
                        cursor.execute('''
                            INSERT INTO user_premises (user_id, premise_text, created_at)
                            VALUES (?, ?, ?)
                        ''', (user_id, premise, datetime.now().isoformat()))

                    serialized_premises = json.dumps(premises) if premises else None
                    cursor.execute('''
                        UPDATE subscriptions_categories 
                        SET user_premises = ?
                        WHERE user_id = ? AND is_active = 1
                    ''', (serialized_premises, user_id))
                    conn.commit()
                    
                    logger.info(f"✅ Premises updated for user {user_id}: {len(premises)} premises")
                    return True
        except Exception as e:
            logger.exception(f"Error updating user premises: {e}")
            return False
    
    def get_premises_with_context(self, user_id: str) -> tuple:
        """Get user's premises with context (always returns user premises)."""
        user_premises = self.get_user_premises(user_id)
        
        if user_premises:
            return user_premises, "custom"
        else:
            # If user has no premises, return empty list - never use global
            return [], "empty"
    
    def _get_default_premises(self) -> list:
        """Get default premises from personality file."""
        try:
            from agent_engine import PERSONALITY
            # Look for premises in the news_watcher section of roles
            if ('roles' in PERSONALITY and 
                'news_watcher' in PERSONALITY['roles'] and
                'premises' in PERSONALITY['roles']['news_watcher']):
                return PERSONALITY['roles']['news_watcher']['premises']
            return []
        except Exception as e:
            logger.error(f"Error getting default premises: {e}")
            return []

    def _get_premises_limit(self) -> int:
        """Get the effective premises limit."""
        return max(7, len(self._get_default_premises()))
    
    def _insert_user_premise(self, user_id: str, premise_text: str) -> bool:
        """Directly insert a premise for user (bypassing checks)."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR IGNORE INTO user_premises (user_id, premise_text, created_at)
                        VALUES (?, ?, ?)
                    ''', (user_id, premise_text, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Error inserting user premise: {e}")
            return False
    
    def initialize_user_premises(self, user_id: str, guild_id: str = None) -> tuple:
        """Initialize user premises with default premises (one-time only)."""
        try:
            current_premises = self.get_user_premises(user_id)
            
            # Only initialize if user has no premises
            if current_premises:
                return True, f"User already has {len(current_premises)} premises"
            
            # Copy default premises
            default_premises = self._get_default_premises()
            if not default_premises:
                return False, "No default premises available to copy"
            
            logger.info(f"Initializing premises for user {user_id} with {len(default_premises)} defaults")
            
            for premise in default_premises:
                self._insert_user_premise(user_id, premise)
            
            # Record the initialization
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO user_initializations (user_id, initialized_at, guild_id)
                        VALUES (?, ?, ?)
                    ''', (user_id, datetime.now().isoformat(), guild_id or 'unknown'))
                    conn.commit()
            
            updated_premises = self.get_user_premises(user_id)
            return True, f"Initialized with {len(updated_premises)} default premises"
            
        except Exception as e:
            logger.exception(f"Error initializing user premises: {e}")
            return False, "Error initializing premises"
    
    def has_user_initialized(self, user_id: str) -> bool:
        """Check if user has ever initialized premises."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT user_id FROM user_initializations WHERE user_id = ?', (user_id,))
                    return cursor.fetchone() is not None
        except Exception as e:
            logger.exception(f"Error checking user initialization: {e}")
            return False
    
    def add_user_premise(self, user_id: str, new_premise: str) -> tuple:
        """Add a premise to the user if there's space and user already has premises."""
        try:
            current_premises = self.get_user_premises(user_id)
            limit = self._get_premises_limit()
            
            # User must have initialized at some point (via !canvas)
            if not current_premises and not self.has_user_initialized(user_id):
                return False, "You must initialize your premises first using !canvas"
            
            # Check if we can add the new premise
            if len(current_premises) >= limit:
                return False, f"You have reached the maximum of {limit} premises"
            
            if new_premise in current_premises:
                return False, "That premise already exists in your list"
            
            # Insert the new premise
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO user_premises (user_id, premise_text, created_at)
                        VALUES (?, ?, ?)
                    ''', (user_id, new_premise, datetime.now().isoformat()))
                    conn.commit()
                    
                    logger.info(f"✅ Premise added for user {user_id}: {new_premise}")
                    updated_count = len(self.get_user_premises(user_id))
                    return True, f"Premise added: \"{new_premise}\" ({updated_count}/{limit})"
                
        except Exception as e:
            logger.exception(f"Error adding user premise: {e}")
            return False, "Error adding premise"
    
    def modify_user_premise(self, user_id: str, index: int, new_premise: str) -> tuple:
        """Modify a specific premise by its index (1-based)."""
        try:
            current_premises = self.get_user_premises(user_id)
            
            if not current_premises:
                return False, "You do not have custom premises. Use `!watcher premises add` to create them."
            
            if index < 1 or index > len(current_premises):
                return False, f"Invalid index. It must be between 1 and {len(current_premises)}"
            
            # Get the premise to modify
            premise_to_modify = current_premises[index - 1]
            
            # Update in the new dedicated table
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE user_premises 
                        SET premise_text = ?, created_at = ?
                        WHERE user_id = ? AND premise_text = ?
                    ''', (new_premise, datetime.now().isoformat(), user_id, premise_to_modify))
                    conn.commit()
                    
                    if cursor.rowcount > 0:
                        return True, f"Premise #{index} updated: \"{premise_to_modify}\" → \"{new_premise}\""
                    else:
                        return False, "Error modifying premise"
                
        except Exception as e:
            logger.exception(f"Error modifying user premise: {e}")
            return False, "Error modifying premise"
    
    def delete_user_premise(self, user_id: str, index: int) -> tuple:
        """Delete a specific premise by its index (1-based)."""
        try:
            current_premises = self.get_user_premises(user_id)
            limit = self._get_premises_limit()
            
            if not current_premises:
                return False, "You do not have custom premises to delete."
            
            if index < 1 or index > len(current_premises):
                return False, f"Invalid index. It must be between 1 and {len(current_premises)}"
            
            # Get the premise to delete
            premise_to_delete = current_premises[index - 1]
            
            # Delete from the new dedicated table
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        DELETE FROM user_premises 
                        WHERE user_id = ? AND premise_text = ?
                    ''', (user_id, premise_to_delete))
                    conn.commit()
                    
                    if cursor.rowcount > 0:
                        return True, f"Premise #{index} deleted: \"{premise_to_delete}\" ({len(current_premises) - 1}/{limit})"
                    else:
                        return False, "Error deleting premise"
                
        except Exception as e:
            logger.exception(f"Error deleting user premise: {e}")
            return False, "Error deleting premise"
    
    # ===== CHANNEL PREMISES METHODS =====
    
    def get_channel_premises(self, channel_id: str) -> list:
        """Get customized premises for a channel."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # First, check if channel has personalized premises in channel_premises table
                cursor.execute('''
                    SELECT premise_text
                    FROM channel_premises
                    WHERE channel_id = ?
                    ORDER BY created_at ASC
                ''', (channel_id,))
                results = cursor.fetchall()
                if results:
                    return [row[0] for row in results]

                # If no personalized channel premises, check for user who might own this channel
                # For now, we'll skip the old subscription-based premises and return empty
                # to force using user premises instead
                return []
                
                # OLD CODE: Check subscription premises (commented out to avoid conflicts)
                # cursor.execute('''
                #     SELECT DISTINCT channel_premises
                #     FROM subscriptions_channels
                #     WHERE channel_id = ? AND is_active = 1 AND channel_premises IS NOT NULL AND channel_premises != ''
                # ''', (channel_id,))
                # result = cursor.fetchone()
                # 
                # if result and result[0]:
                #     premises_str = result[0]
                #     try:
                #         return json.loads(premises_str)
                #     except json.JSONDecodeError:
                #         if premises_str:
                #             return [p.strip() for p in premises_str.split(',') if p.strip()]
                
                return []
        except Exception as e:
            logger.exception(f"Error getting channel premises: {e}")
            return []
    
    def update_channel_premises(self, channel_id: str, premises: list) -> bool:
        """Update customized premises for a channel."""
        try:
            limit = self._get_premises_limit()
            if len(premises) > limit:
                logger.warning(f"Channel {channel_id} tried to save more than {limit} premises")
                return False
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM channel_premises WHERE channel_id = ?', (channel_id,))

                    for premise in premises:
                        cursor.execute('''
                            INSERT INTO channel_premises (channel_id, premise_text, created_at)
                            VALUES (?, ?, ?)
                        ''', (channel_id, premise, datetime.now().isoformat()))

                    serialized_premises = json.dumps(premises) if premises else None
                    cursor.execute('''
                        UPDATE subscriptions_channels 
                        SET channel_premises = ?
                        WHERE channel_id = ? AND is_active = 1
                    ''', (serialized_premises, channel_id))
                    conn.commit()
                    
                    logger.info(f"✅ Premises updated for channel {channel_id}: {len(premises)} premises")
                    return True
        except Exception as e:
            logger.exception(f"Error updating channel premises: {e}")
            return False
    
    def initialize_channel_premises(self, channel_id: str) -> tuple:
        """Initialize channel premises with default premises (one-time only)."""
        try:
            current_premises = self.get_channel_premises(channel_id)
            
            # Only initialize if channel has no premises
            if current_premises:
                return True, f"Channel already has {len(current_premises)} premises"
            
            # Copy default premises
            default_premises = self._get_default_premises()
            if not default_premises:
                return False, "No default premises available to copy"
            
            logger.info(f"Initializing premises for channel {channel_id} with {len(default_premises)} defaults")
            
            # Save to channel premises table
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    for premise in default_premises:
                        cursor.execute('''
                            INSERT INTO channel_premises (channel_id, premise_text, created_at)
                            VALUES (?, ?, ?)
                        ''', (channel_id, premise, datetime.now().isoformat()))
                    conn.commit()
            
            updated_premises = self.get_channel_premises(channel_id)
            return True, f"Initialized with {len(updated_premises)} default premises"
            
        except Exception as e:
            logger.exception(f"Error initializing channel premises: {e}")
            return False, "Error initializing premises"
    
    def add_channel_premise(self, channel_id: str, new_premise: str) -> tuple:
        """Add a premise to the channel if there is space and channel already has premises."""
        try:
            current_premises = self.get_channel_premises(channel_id)
            limit = self._get_premises_limit()

            # Channel must have premises to add (initialized via !canvas)
            if not current_premises:
                return False, "This channel must initialize premises first using !canvas"
            
            # Check if we can add the new premise
            if len(current_premises) >= limit:
                return False, f"The channel has reached the maximum of {limit} premises"
            
            if new_premise in current_premises:
                return False, "That premise already exists in the channel list"
            
            current_premises.append(new_premise)
            
            if self.update_channel_premises(channel_id, current_premises):
                return True, f"Channel premise added: \"{new_premise}\" ({len(current_premises)}/{limit})"
            else:
                return False, "Error saving channel premise"
                
        except Exception as e:
            logger.exception(f"Error adding channel premise: {e}")
            return False, "Error adding channel premise"

    def delete_channel_premise(self, channel_id: str, index: int) -> tuple:
        """Delete a specific channel premise by its index (1-based)."""
        try:
            current_premises = self.get_channel_premises(channel_id)
            limit = self._get_premises_limit()

            if not current_premises:
                return False, "This channel has no custom premises to delete. Use 'Add Premises' to create custom premises first."

            if index < 1 or index > len(current_premises):
                return False, f"Invalid index. It must be between 1 and {len(current_premises)}"

            premise_to_delete = current_premises[index - 1]
            current_premises.pop(index - 1)

            if self.update_channel_premises(channel_id, current_premises):
                return True, f"Channel premise #{index} deleted: \"{premise_to_delete}\" ({len(current_premises)}/{limit})"
            return False, "Error deleting channel premise"

        except Exception as e:
            logger.exception(f"Error deleting channel premise: {e}")
            return False, "Error deleting channel premise"
    
    def modify_channel_premise(self, channel_id: str, index: int, new_premise: str) -> tuple:
        """Modify a specific channel premise by its index (1-based)."""
        try:
            current_premises = self.get_channel_premises(channel_id)
            
            if not current_premises:
                return False, "The channel has no custom premises. Use `!watcherchannel premises add` to create them."
            
            if index < 1 or index > len(current_premises):
                return False, f"Invalid index. It must be between 1 and {len(current_premises)}"
            
            # Modify the premise
            previous_premise = current_premises[index - 1]
            current_premises[index - 1] = new_premise
            
            if self.update_channel_premises(channel_id, current_premises):
                return True, f"Channel premise #{index} updated: \"{previous_premise}\" → \"{new_premise}\""
            else:
                return False, "Error modifying channel premise"
                
        except Exception as e:
            logger.exception(f"Error modifying channel premise: {e}")
            return False, "Error modifying channel premise"
    
    def get_channel_premises_with_context(self, channel_id: str) -> tuple:
        """Get channel premises with context. Never uses global premises directly."""
        channel_premises = self.get_channel_premises(channel_id)
        
        if channel_premises:
            return channel_premises, "custom"
        
        # If no custom channel premises, check subscription-based premises (old method)
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT channel_premises
                    FROM subscriptions_channels
                    WHERE channel_id = ? AND channel_premises IS NOT NULL AND channel_premises != ''
                ''', (channel_id,))
                result = cursor.fetchone()
                if result and result[0]:
                    premise_list = [p.strip() for p in result[0].split(',') if p.strip()]
                    if premise_list:
                        # For AI subscriptions, allow use of default premises
                        # Check if these are just copies of global premises
                        global_premises = self._get_default_premises()
                        if premise_list == global_premises:
                            # These are global copies, but allow them for AI subscriptions
                            return premise_list, "default"
                        else:
                            # These are actual channel-specific premises
                            return premise_list, "subscription"
        except Exception as e:
            logger.warning(f"Error checking subscription premises for channel {channel_id}: {e}")
        
        # If no valid channel premises, return empty - NEVER use global directly
        return [], "empty"

    def check_user_subscription_type(self, user_id: str) -> str:
        """Check what type of subscription a user has (exclusive).
        
        Returns:
            str: 'flat', 'keywords', 'ai', or 'none'
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Check if user has flat subscription (subscriptions_categories without AI)
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1 AND (user_premises IS NULL OR user_premises = '')
                ''', (user_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'flat'
                
                # Check if user has keyword subscription
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_keywords 
                    WHERE user_id = ? AND is_active = 1
                ''', (user_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'keywords'
                
                # Check if user has AI subscription (subscriptions_categories with premises)
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1 AND user_premises IS NOT NULL AND user_premises != ''
                ''', (user_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'ai'
                
                return 'none'
                
        except Exception as e:
            logger.exception(f"Error checking user subscription type: {e}")
            return 'none'
    
    def check_channel_subscription_type(self, channel_id: str) -> str:
        """Check what type of subscription a channel has (exclusive).
        
        Returns:
            str: 'flat', 'keywords', 'ai', or 'none'
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Check if channel has flat subscription
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_channels 
                    WHERE channel_id = ? AND is_active = 1 AND (channel_premises IS NULL OR channel_premises = '')
                ''', (channel_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'flat'
                
                # Check if channel has keyword subscription
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_keywords 
                    WHERE channel_id = ? AND is_active = 1
                ''', (channel_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'keywords'
                
                # Check if channel has AI subscription (channels with premises)
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_channels 
                    WHERE channel_id = ? AND is_active = 1 AND channel_premises IS NOT NULL AND channel_premises != ''
                ''', (channel_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'ai'
                
                return 'none'
                
        except Exception as e:
            logger.exception(f"Error checking channel subscription type: {e}")
            return 'none'
    
    def cancel_other_user_subscriptions(self, user_id: str, subscription_type_to_keep: str):
        """Cancel all user subscriptions except the specified type.
        
        Args:
            user_id: User ID
            subscription_type_to_keep: Type to keep ('flat', 'keywords', 'ai')
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Cancel flat subscriptions if not to be kept
                if subscription_type_to_keep != 'flat':
                    cursor.execute('''
                        UPDATE subscriptions_categories 
                        SET is_active = 0 
                        WHERE user_id = ? AND is_active = 1 AND (user_premises IS NULL OR user_premises = '')
                    ''', (user_id,))
                
                # Cancel keyword subscriptions if not to be kept
                if subscription_type_to_keep != 'keywords':
                    cursor.execute('''
                        UPDATE subscriptions_keywords 
                        SET is_active = 0 
                        WHERE user_id = ? AND is_active = 1
                    ''', (user_id,))
                
                # Cancel AI subscriptions if not to be kept
                if subscription_type_to_keep != 'ai':
                    cursor.execute('''
                        UPDATE subscriptions_categories 
                        SET is_active = 0 
                        WHERE user_id = ? AND is_active = 1 AND user_premises IS NOT NULL AND user_premises != ''
                    ''', (user_id,))
                
                conn.commit()
                logger.info(f"✅ Cancelled previous user subscriptions for user {user_id}")
                
        except Exception as e:
            logger.exception(f"Error cancelling other user subscriptions: {e}")
    
    def cancel_other_channel_subscriptions(self, channel_id: str, subscription_type_to_keep: str):
        """Cancel all channel subscriptions except the specified type.
        
        Args:
            channel_id: Channel ID
            subscription_type_to_keep: Type to keep ('flat', 'keywords', 'ai')
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Cancel flat subscriptions if not to be kept
                if subscription_type_to_keep != 'flat':
                    cursor.execute('''
                        UPDATE subscriptions_channels 
                        SET is_active = 0 
                        WHERE channel_id = ? AND is_active = 1 AND (channel_premises IS NULL OR channel_premises = '')
                    ''', (channel_id,))
                
                # Cancel keyword subscriptions if not to be kept
                if subscription_type_to_keep != 'keywords':
                    cursor.execute('''
                        UPDATE subscriptions_keywords 
                        SET is_active = 0 
                        WHERE channel_id = ? AND is_active = 1
                    ''', (channel_id,))
                
                # Cancel AI subscriptions if not to be kept
                if subscription_type_to_keep != 'ai':
                    cursor.execute('''
                        UPDATE subscriptions_channels 
                        SET is_active = 0 
                        WHERE channel_id = ? AND is_active = 1 AND channel_premises IS NOT NULL AND channel_premises != ''
                    ''', (channel_id,))
                
                conn.commit()
                logger.info(f"✅ Cancelled previous channel subscriptions for channel {channel_id}")
                
        except Exception as e:
            logger.exception(f"Error canceling other channel subscriptions: {e}")
    
    def get_all_active_subscriptions(self):
        """Get all active flat subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, category, feed_id, subscribed_at
                    FROM subscriptions_categories 
                    WHERE is_active = 1 AND (user_premises IS NULL OR user_premises = '')
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting active subscriptions: {e}")
            return []
    
    def get_user_keywords(self, user_id: str) -> str:
        """Get the configured keywords of a user from user_premises table."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT premise_text FROM user_premises 
                    WHERE user_id = ? AND premise_text LIKE 'KEYWORDS:%'
                    ORDER BY created_at DESC LIMIT 1
                ''', (user_id,))
                result = cursor.fetchone()
                if result and result[0]:
                    # Extract keywords from "KEYWORDS:iran,crypto" format
                    return result[0].replace('KEYWORDS:', '', 1)
                return None
        except Exception as e:
            logger.exception(f"Error getting user keywords: {e}")
            return None
    
    def update_user_keywords(self, user_id: str, keywords: str) -> bool:
        """Update the keywords of a user in the user_premises table (renamed for keywords)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                if keywords:
                    # Store keywords in user_premises table (reuse existing infrastructure)
                    cursor.execute('''
                        INSERT OR REPLACE INTO user_premises 
                        (user_id, premise_text, created_at)
                        VALUES (?, ?, ?)
                    ''', (user_id, f"KEYWORDS:{keywords}", datetime.now().isoformat()))
                else:
                    # Remove keywords if empty
                    cursor.execute('''
                        DELETE FROM user_premises 
                        WHERE user_id = ? AND premise_text LIKE 'KEYWORDS:%'
                    ''', (user_id,))
                
                conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error updating user keywords: {e}")
            return False
    
    def get_user_keyword_subscriptions(self, user_id: str) -> list:
        """Get all keyword subscriptions of a user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT category, feed_id, keywords 
                    FROM subscriptions_keywords 
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY category, feed_id
                ''', (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting keyword subscriptions: {e}")
            return []
    
    def cancel_user_keyword_subscription(self, user_id: str, category: str) -> bool:
        """Cancel user keyword subscription for a category."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE subscriptions_keywords 
                    SET is_active = 0
                    WHERE user_id = ? AND category = ? AND is_active = 1
                ''', (user_id, category))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error canceling user keyword subscription: {e}")
            return False
    
    def get_user_ai_subscriptions(self, user_id: str) -> list:
        """Get all AI subscriptions of a user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT category, feed_id, user_premises 
                    FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1 AND user_premises IS NOT NULL AND user_premises != ''
                    ORDER BY category, feed_id
                ''', (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting AI subscriptions: {e}")
            return []


    
    def _init_configuracion_table(self):
        """Initialize configuration table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS configuracion (
                        clave TEXT PRIMARY KEY,
                        valor TEXT NOT NULL,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_configuracion_clave ON configuracion (clave)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating configuracion table: {e}")

    def count_user_subscriptions(self, user_id: str) -> int:
        """Count total active subscriptions for a user across all methods using unified system."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Count all active user subscriptions from unified table
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions 
                    WHERE user_id = ? AND channel_id IS NULL AND is_active = 1
                ''', (user_id,))
                total_count = cursor.fetchone()[0]
                
                return total_count
        except Exception as e:
            logger.exception(f"Error counting user subscriptions: {e}")
            return 0

    def count_channel_subscriptions(self, channel_id: str) -> int:
        """Count total active subscriptions for a channel across all methods."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Count flat subscriptions
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_channels 
                    WHERE channel_id = ? AND is_active = 1
                ''', (channel_id,))
                flat_count = cursor.fetchone()[0]
                
                # Count keyword subscriptions
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_keywords 
                    WHERE channel_id = ? AND is_active = 1
                ''', (channel_id,))
                keyword_count = cursor.fetchone()[0]
                
                # Count AI subscriptions (already counted in flat, but with premises)
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_channels 
                    WHERE channel_id = ? AND is_active = 1
                ''', (channel_id,))
                ai_count = cursor.fetchone()[0]
                
                # Total unique subscriptions = flat (including AI) + keyword
                return flat_count + keyword_count
                
        except Exception as e:
            logger.exception(f"Error counting channel subscriptions: {e}")
            return 0

    def count_server_subscriptions(self) -> int:
        """Count total active subscriptions for the server (users + channels)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Count all user subscriptions (flat + keyword)
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_categories 
                    WHERE is_active = 1
                ''')
                user_flat_count = cursor.fetchone()[0]
                
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_keywords 
                    WHERE is_active = 1
                ''')
                user_keyword_count = cursor.fetchone()[0]
                
                # Count all channel subscriptions (flat + keyword)
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_channels 
                    WHERE is_active = 1
                ''')
                channel_flat_count = cursor.fetchone()[0]
                
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_keywords 
                    WHERE channel_id IS NOT NULL AND is_active = 1
                ''')
                channel_keyword_count = cursor.fetchone()[0]
                
                # Total = user (flat + keyword) + channel (flat + keyword)
                return (user_flat_count + user_keyword_count + 
                       channel_flat_count + channel_keyword_count)
                
        except Exception as e:
            logger.exception(f"Error counting server subscriptions: {e}")
            return 0

    def can_user_subscribe(self, user_id: str) -> tuple[bool, str]:
        """Check if user can subscribe (max 3 subscriptions)."""
        current_count = self.count_user_subscriptions(user_id)
        max_user_subs = 3
        
        if current_count >= max_user_subs:
            return False, f"You have reached the maximum of {max_user_subs} subscriptions. Use `!watcher reset confirm` to clear all subscriptions."
        
        return True, f"You have {current_count}/{max_user_subs} subscriptions available."

    def can_channel_subscribe(self, channel_id: str) -> tuple[bool, str]:
        """Check if channel can subscribe (max 3 subscriptions)."""
        current_count = self.count_channel_subscriptions(channel_id)
        max_channel_subs = 3
        
        if current_count >= max_channel_subs:
            return False, f"This channel has reached the maximum of {max_channel_subs} subscriptions."
        
        return True, f"This channel has {current_count}/{max_channel_subs} subscriptions available."

    def can_server_accept_subscription(self) -> tuple[bool, str]:
        """Check if server can accept more subscriptions (max 15 total)."""
        current_count = self.count_server_subscriptions()
        max_server_subs = 15
        
        if current_count >= max_server_subs:
            return False, f"This server has reached the maximum of {max_server_subs} total subscriptions."
        
        return True, f"This server has {current_count}/{max_server_subs} subscriptions available."

    def get_feed_info(self, feed_id: int) -> Optional[dict]:
        """Get feed information including URL and category."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, url, name, category, is_active
                    FROM feeds_config 
                    WHERE id = ? AND is_active = 1
                ''', (feed_id,))
                result = cursor.fetchone()
                
                if result:
                    return {
                        'id': result[0],
                        'url': result[1],
                        'name': result[2],
                        'category': result[3],
                        'is_active': result[4]
                    }
                return None
                
        except Exception as e:
            logger.exception(f"Error getting feed info: {e}")
            return None

    def get_all_user_subscriptions_flat(self) -> List[tuple]:
        """Get all active flat user subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, category, feed_id
                    FROM subscriptions_categories
                    WHERE is_active = 1 AND (user_premises IS NULL OR user_premises = '')
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all flat user subscriptions: {e}")
            return []

    
    def get_all_user_subscriptions_ai(self) -> List[tuple]:
        """Get all active AI user subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, category, feed_id, user_premises
                    FROM subscriptions_categories
                    WHERE is_active = 1 AND user_premises IS NOT NULL AND user_premises != ''
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all AI user subscriptions: {e}")
            return []

    
    def get_frequency_setting(self) -> int:
        """Get the frequency setting in hours."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT valor FROM configuracion 
                    WHERE clave = 'frequency_hours'
                ''')
                result = cursor.fetchone()
                return result[0] if result else 4  # Default to 4 hours
        except Exception as e:
            logger.exception(f"Error getting frequency setting: {e}")
            return 4  # Default to 4 hours on error

    def set_frequency_setting(self, hours: int) -> bool:
        """Set the frequency setting in hours."""
        if not 1 <= hours <= 24:
            logger.error(f"Invalid frequency setting: {hours}. Must be between 1 and 24.")
            return False
        
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO configuracion (clave, valor, updated_at)
                    VALUES ('frequency_hours', ?, datetime('now'))
                ''', (hours,))
                conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error setting frequency: {e}")
            return False


# ===== UNIFIED SUBSCRIPTIONS MANAGEMENT =====
    
    def create_subscription(self, user_id: str = None, channel_id: str = None, 
                          category: str = None, feed_id: int = None,
                          premises: str = None, keywords: str = None,
                          method: str = 'general', created_by: str = None) -> int:
        """Create a new subscription with unified structure."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO subscriptions 
                    (user_id, channel_id, category, feed_id, premises, keywords, method, is_active, subscribed_at, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, datetime('now'), ?)
                ''', (user_id, channel_id, category, feed_id, premises, keywords, method, created_by))
                return cursor.lastrowid
        except Exception as e:
            logger.exception(f"Error creating subscription: {e}")
            return None
    
    def get_all_active_subscriptions(self) -> list:
        """Get all active subscriptions (unified method)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by
                    FROM subscriptions 
                    WHERE is_active = 1
                    ORDER BY subscribed_at DESC
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all subscriptions: {e}")
            return []
    
    def get_user_subscriptions(self, user_id: str) -> list:
        """Get all active subscriptions for a specific user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by
                    FROM subscriptions 
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY subscribed_at DESC
                ''', (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting user subscriptions: {e}")
            return []
    
    def get_channel_subscriptions(self, channel_id: str) -> list:
        """Get all active subscriptions for a specific channel."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by
                    FROM subscriptions 
                    WHERE channel_id = ? AND is_active = 1
                    ORDER BY subscribed_at DESC
                ''', (channel_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting channel subscriptions: {e}")
            return []

    def get_users_with_active_subscriptions(self) -> list:
        """Get all users who have active personal subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT user_id 
                    FROM subscriptions 
                    WHERE user_id IS NOT NULL AND channel_id IS NULL AND is_active = 1
                ''')
                results = cursor.fetchall()
                return [row[0] for row in results]
        except Exception as e:
            logger.exception(f"Error getting users with active subscriptions: {e}")
            return []

    def update_subscription(self, subscription_id: int, **kwargs) -> bool:
        """Update subscription fields."""
        try:
            if not kwargs:
                return False
                
            # Build dynamic update query
            set_clauses = []
            values = []
            
            for key, value in kwargs.items():
                if key in ['category', 'feed_id', 'premises', 'keywords', 'method', 'is_active']:
                    set_clauses.append(f"{key} = ?")
                    values.append(value)
            
            if not set_clauses:
                return False
                
            values.append(subscription_id)
            
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    UPDATE subscriptions 
                    SET {', '.join(set_clauses)}
                    WHERE id = ?
                ''', values)
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error updating subscription: {e}")
            return False
    
    def delete_subscription(self, subscription_id: int) -> bool:
        """Delete a subscription (soft delete by setting is_active=0)."""
        return self.update_subscription(subscription_id, is_active=0)


# Dictionary to maintain instances per server
_db_news_watcher_instances = {}

def get_news_watcher_db_instance(server_id: str = "default") -> DatabaseRoleNewsWatcher:
    """Get or create a news watcher database instance for a specific server."""
    # Generate the current database path for this server
    current_db_path = get_db_path(server_id)
    cache_key = f"{server_id}:{current_db_path}"
    
    # Check if we have a cached instance with the same database path
    if cache_key not in _db_news_watcher_instances:
        _db_news_watcher_instances[cache_key] = DatabaseRoleNewsWatcher(server_id)
    
    return _db_news_watcher_instances[cache_key]

def invalidate_news_watcher_db_instance(server_id: str = None):
    """Invalidate cached news watcher database instance for a server or all servers."""
    global _db_news_watcher_instances
    if server_id:
        # Invalidate all instances for this server (any personality)
        keys_to_remove = [k for k in _db_news_watcher_instances.keys() if k.startswith(f"{server_id}:")]
        for key in keys_to_remove:
            del _db_news_watcher_instances[key]
            logger.info(f"🗄️ [NEWS_WATCHER] Invalidated cached db instance for server: {server_id}")
    else:
        # Invalidate all instances
        _db_news_watcher_instances.clear()
        logger.info("🗄️ [NEWS_WATCHER] Invalidated all cached db instances")
