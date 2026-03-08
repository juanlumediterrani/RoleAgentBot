import json
import sqlite3
import threading
import os
import stat
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
from agent_logging import get_logger

try:
    logger = get_logger('db_role_news_watcher')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_news_watcher')

from agent_db import get_server_db_path_fallback, get_personality_name

def get_db_path(server_name: str = "default") -> Path:
    """Generate database path for news watcher with personality name."""
    personality_name = get_personality_name()
    db_name = f"watcher_{personality_name}"
    return get_server_db_path_fallback(server_name, db_name)


class DatabaseRoleNewsWatcher:
    """Specialized database for News Watcher.
    Manages read news and sent notifications.
    """
    
    def __init__(self, server_name: str = "default", db_path: Path = None):
        if db_path is None:
            self.db_path = get_db_path(server_name)
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
                self._init_subscriptions_table()
                self._init_feeds_table()
                self._init_subscriptions_categories_table()
                self._init_subscriptions_channels_table()
                self._init_subscriptions_keywords_table()
                self._init_method_config_table()
                self.insert_default_feeds()
                
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
    
    def _generar_title_hash(self, titulo: str) -> str:
        """Generate simple hash of title to avoid duplicates."""
        import hashlib
        return hashlib.md5(titulo.lower().strip().encode('utf-8')).hexdigest()
    
    def noticia_esta_leida(self, titulo: str) -> bool:
        """Check if news was already read."""
        try:
            title_hash = self._generar_title_hash(titulo)
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT 1 FROM read_news WHERE title_hash = ?', (title_hash,))
                    return cursor.fetchone() is not None
        except Exception as e:
            logger.exception(f"Error checking if news was read: {e}")
            return False
    
    def mark_news_as_read(self, titulo: str, source: str = None) -> bool:
        """Mark a news as read."""
        try:
            title_hash = self._generar_title_hash(titulo)
            current_date = datetime.now().isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR IGNORE INTO read_news (titulo, title_hash, read_date, source)
                        VALUES (?, ?, ?, ?)
                    ''', (titulo, title_hash, current_date, source))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error marking news as read: {e}")
            return False
    
    def record_sent_notification(self, titulo: str, analisis: str, notification_type: str = "critical", source: str = None) -> bool:
        """Record a sent notification."""
        try:
            title_hash = self._generar_title_hash(titulo)
            current_date = datetime.now().isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO sent_notifications 
                        (titulo, title_hash, notification_type, analisis, sent_date, source)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (titulo, title_hash, notification_type, analisis, current_date, source))
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
                
                # Last activity
                cursor.execute('SELECT MAX(read_date) FROM read_news')
                last_news = cursor.fetchone()[0]
                
                cursor.execute('SELECT MAX(sent_date) FROM sent_notifications')
                last_notification = cursor.fetchone()[0]
                
                return {
                    'read_news': read_news,
                    'sent_notifications': sent_notifications,
                    'last_news': last_news,
                    'last_notification': last_notification
                }
        except Exception as e:
            logger.exception(f"Error getting statistics: {e}")
            return {}


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
                        is_active INTEGER DEFAULT 1,
                        priority INTEGER DEFAULT 1,
                        keywords TEXT DEFAULT NULL,
                        feed_type TEXT DEFAULT 'especializado',
                        created_at TEXT NOT NULL,
                        updated_at TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_category ON feeds_config (category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_is_active ON feeds_config (is_active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_priority ON feeds_config (priority)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_feed_type ON feeds_config (feed_type)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating feeds_config table: {e}")
    
    def _init_subscriptions_categories_table(self):
        """Initialize category subscriptions table (para suscripciones con IA)."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions_categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        category TEXT NOT NULL,
                        feed_id INTEGER DEFAULT NULL,
                        subscribed_at TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        user_premises TEXT DEFAULT NULL,  -- JSON with user custom premises
                        UNIQUE(user_id, category, feed_id)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_categories_user ON subscriptions_categories (user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_categorys_category ON subscriptions_categories (category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_categorys_is_active ON subscriptions_categories (is_active)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating subscriptions_categories table: {e}")
    
    def _init_subscriptions_channels_table(self):
        """Initialize channel subscriptions table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions_channels (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        channel_id TEXT NOT NULL UNIQUE,
                        channel_name TEXT NOT NULL,
                        server_id TEXT NOT NULL,
                        server_name TEXT NOT NULL,
                        category TEXT NOT NULL,
                        feed_id INTEGER DEFAULT NULL,
                        subscribed_at TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        channel_premises TEXT DEFAULT NULL,
                        UNIQUE(channel_id, category, feed_id)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_channels_channel_id ON subscriptions_channels (channel_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_channels_server_id ON subscriptions_channels (server_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_channels_category ON subscriptions_channels (category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_channels_is_active ON subscriptions_channels (is_active)')
                
                # Add channel_premises column if it doesn't exist (migration)
                cursor.execute('PRAGMA table_info(subscriptions_channels)')
                columns = cursor.fetchall()
                column_names = [col[1] for col in columns]
                if 'channel_premises' not in column_names:
                    cursor.execute('ALTER TABLE subscriptions_channels ADD COLUMN channel_premises TEXT DEFAULT NULL')
                    logger.info("✅ Added channel_premises column to subscriptions_channels table")
                
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating subscriptions_channels table: {e}")
    
    def _init_subscriptions_keywords_table(self):
        """Initialize keyword subscriptions table."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS subscriptions_keywords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        channel_id TEXT DEFAULT NULL,
                        keywords TEXT NOT NULL,
                        category TEXT DEFAULT NULL,
                        feed_id INTEGER DEFAULT NULL,
                        subscribed_at TEXT NOT NULL,
                        is_active INTEGER DEFAULT 1,
                        UNIQUE(user_id, channel_id, keywords, category, feed_id)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_keywords_user ON subscriptions_keywords (user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_keywords_canal ON subscriptions_keywords (channel_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_keywords_is_active ON subscriptions_keywords (is_active)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_keywords_category ON subscriptions_keywords (category)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_subscriptions_keywords_feed ON subscriptions_keywords (feed_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating subscriptions_keywords table: {e}")
    
    def insert_default_feeds(self):
        """Insert default feeds if they don't exist."""
        try:
            default_feeds = [
                # Economy/Finance Feeds
                {
                    'name': 'Reuters Business',
                    'url': 'https://www.reuters.com/rssFeed/businessNews',
                    'category': 'economy',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'market,stock,economy,business,finance',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Financial Times',
                    'url': 'https://www.ft.com/rss/home/economy',
                    'category': 'economy',
                    'country': 'UK',
                    'language': 'en',
                    'keywords': 'economy,finance,markets,trade',
                    'feed_type': 'especializado'
                },
                {
                    'name': 'Bloomberg Markets',
                    'url': 'https://www.bloomberg.com/markets.rss',
                    'category': 'economy',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'markets,stocks,economy,trading',
                    'feed_type': 'general'
                },
                
                # International News Feeds
                {
                    'name': 'Reuters World',
                    'url': 'https://www.reuters.com/rssFeed/worldNews',
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
                    'url': 'https://www.reuters.com/rssFeed/topNews',
                    'category': 'general',
                    'country': 'US',
                    'language': 'en',
                    'keywords': 'breaking,news,world,events',
                    'feed_type': 'general'
                },
                {
                    'name': 'Associated Press News',
                    'url': 'https://feeds.apnews.com/rss/apnews-topnews',
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
                    'url': 'https://www.coindesk.com/arc/outboundfeeds/rss/',
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
                }
            ]
            
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                for feed in default_feeds:
                    cursor.execute('''
                        INSERT OR IGNORE INTO feeds_config 
                        (name, url, category, country, language, keywords, feed_type, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        feed['name'], feed['url'], feed['category'], 
                        feed['country'], feed['language'], feed['keywords'],
                        feed['feed_type'], datetime.now().isoformat()
                    ))
                conn.commit()
                logger.info("✅ Default feeds insertados")
        except Exception as e:
            logger.exception(f"❌ Error insertando feeds por defecto: {e}")
    
    def add_feed(self, name: str, url: str, category: str, country: str = None, 
                   language: str = 'es', keywords: str = None, feed_type: str = 'especializado') -> bool:
        """Add a new configured feed."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO feeds_config 
                        (name, url, category, country, language, keywords, feed_type,
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (name, url, category, country, language, keywords, feed_type,
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
                        WHERE is_active = 1 AND category = ?
                        ORDER BY priority DESC, name
                    ''', (category,))
                else:
                    cursor.execute('''
                        SELECT id, name, url, category, country, language, priority, keywords, feed_type
                        FROM feeds_config 
                        WHERE is_active = 1
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
                    WHERE id = ? AND is_active = 1
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
                    WHERE is_active = 1
                    GROUP BY category
                    ORDER BY category
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting categories: {e}")
            return []
    
    def subscribe_user_category(self, user_id: str, category: str, feed_id: int = None) -> bool:
        """Suscribe usuario a una categoría o feed específico."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions_categories 
                        (user_id, category, feed_id, subscribed_at, is_active)
                        VALUES (?, ?, ?, ?, 1)
                    ''', (user_id, category, feed_id, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error suscribiendo usuario a categoría: {e}")
            return False
    
    def subscribe_user_category_ai(self, user_id: str, category: str, feed_id: int = None, premisas: str = None) -> bool:
        """Suscribe usuario a una categoría con análisis IA."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions_categories 
                        (user_id, category, feed_id, subscribed_at, is_active, user_premises)
                        VALUES (?, ?, ?, ?, 1, ?)
                    ''', (user_id, category, feed_id, datetime.now().isoformat(), premisas))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error suscribiendo usuario a categoría con IA: {e}")
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
                    WHERE user_id = ? AND is_active = 1
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
        """Subscribe user or channel to specific keywords (optionally in category/feed)."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions_keywords 
                        (user_id, channel_id, keywords, category, feed_id, subscribed_at, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                    ''', (user_id, channel_id, keywords, category, feed_id, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error suscribiendo palabras clave: {e}")
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
            suscriptores_palabras = self.get_keyword_subscribers()
            coincidencias = []
            
            titulo_lower = titulo.lower()
            
            for user_id, channel_id, palabras in suscriptores_palabras:
                palabras_lista = [p.strip().lower() for p in palabras.split(',')]
                
                # Check if any keyword is in the title
                if any(palabra in titulo_lower for palabra in palabras_lista):
                    if channel_id:
                        coincidencias.append(f"channel_{channel_id}")
                    else:
                        coincidencias.append(user_id)
            
            return coincidencias
        except Exception as e:
            logger.exception(f"Error checking keywords: {e}")
            return []
    
    def subscribe_channel_category(self, channel_id: str, channel_name: str, server_id: str, 
                                 server_name: str, category: str, feed_id: int = None) -> bool:
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
            logger.exception(f"Error suscribiendo canal a categoría: {e}")
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
                                   server_name: str, category: str, feed_id: int = None, premisas: str = None) -> bool:
        """Suscribe un canal a una categoría con análisis IA."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Add channel to subscriptions_channels table
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions_channels 
                        (channel_id, channel_name, server_id, server_name, category, feed_id, subscribed_at, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ''', (channel_id, channel_name, server_id, server_name, category, feed_id, datetime.now().isoformat()))
                    
                    # Add subscription to subscriptions_categories table
                    cursor.execute('''
                        INSERT OR REPLACE INTO subscriptions_categories 
                        (user_id, category, feed_id, subscribed_at, is_active, user_premises)
                        VALUES (?, ?, ?, ?, 1, ?)
                    ''', (f"channel_{channel_id}", category, feed_id, datetime.now().isoformat(), premisas))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error suscribiendo canal a categoría con IA: {e}")
            return False
    
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
                subscriptions_from_channels_table = cursor.fetchall()
                
                # Get subscriptions from subscriptions_categories table (channel subscriptions)
                cursor.execute('''
                    SELECT category, feed_id, subscribed_at
                    FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1
                ''', (f"channel_{channel_id}",))
                subscriptions_from_categories_table = cursor.fetchall()
                
                # Combine both results
                all_subscriptions = subscriptions_from_channels_table + subscriptions_from_categories_table
                
                return all_subscriptions
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
                channels_from_channels_table = cursor.fetchall()
                
                # Get channels from subscriptions_categories table (channel subscriptions)
                cursor.execute('''
                    SELECT DISTINCT 
                        substr(user_id, 9) as channel_id,  -- Remove 'channel_' prefix
                        substr(user_id, 9) as channel_name,  -- Use channel_id as name
                        '' as server_id
                    FROM subscriptions_categories 
                    WHERE is_active = 1 AND user_id LIKE 'channel_%'
                ''')
                channels_from_categories_table = cursor.fetchall()
                
                # Combine both results
                all_channels = channels_from_channels_table + channels_from_categories_table
                
                # Remove duplicates based on channel_id
                seen_channels = set()
                unique_channels = []
                for channel in all_channels:
                    if channel[0] not in seen_channels:
                        seen_channels.add(channel[0])
                        unique_channels.append(channel)
                
                return unique_channels
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
                
                # Obtener suscriptores individuales
                suscriptores_individuales = []
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
                suscriptores_individuales = [row[0] for row in cursor.fetchall()]
                
                # Obtener canales (marcados con prefijo especial para identificarlos)
                canales = []
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
                canales = [f"channel_{row[0]}" for row in cursor.fetchall()]
                
                return suscriptores_individuales + canales
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
    
    def get_all_active_category_subscriptions(self) -> list:
        """Get all active AI subscriptions (with premises)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT user_id, category, feed_id, subscribed_at
                    FROM subscriptions_categories 
                    WHERE is_active = 1 AND user_premises IS NOT NULL AND user_premises != ''
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all category subscriptions: {e}")
            return []
    
    def get_all_active_keyword_subscriptions(self) -> list:
        """Get all active keyword subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, channel_id, keywords, category, feed_id
                    FROM subscriptions_keywords 
                    WHERE is_active = 1
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all keyword subscriptions: {e}")
            return []
    
    # ===== USER PREMISES MANAGEMENT =====
    
    def get_user_premises(self, user_id: str) -> list:
        """Get customized premises for a user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT user_premises
                    FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1 AND user_premises IS NOT NULL
                ''', (user_id,))
                result = cursor.fetchone()
                
                if result and result[0]:
                    try:
                        # Try to parse as JSON first
                        return json.loads(result[0])
                    except json.JSONDecodeError:
                        # If not JSON, treat as comma-separated plain text
                        premises_text = result[0]
                        if premises_text:
                            return [premise.strip() for premise in premises_text.split(',')]
                        return []
                return []
        except Exception as e:
            logger.exception(f"Error getting user premises: {e}")
            return []
    
    def update_user_premises(self, user_id: str, premisas: list) -> bool:
        """Update customized premises for a user (maximum 7)."""
        try:
            if len(premisas) > 7:
                logger.warning(f"Usuario {user_id} intentó guardar más de 7 premisas")
                return False
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    # Actualizar todas las suscripciones del usuario con las nuevas premisas
                    cursor.execute('''
                        UPDATE subscriptions_categories 
                        SET user_premises = ?
                        WHERE user_id = ? AND is_active = 1
                    ''', (json.dumps(premisas), user_id))
                    conn.commit()
                    
                    logger.info(f"✅ Premisas actualizadas para usuario {user_id}: {len(premisas)} premisas")
                    return True
        except Exception as e:
            logger.exception(f"Error updating user premises: {e}")
            return False
    
    def get_premises_with_context(self, user_id: str) -> tuple:
        """Get user's premises with context (if has custom ones or uses global)."""
        user_premises = self.get_user_premises(user_id)
        
        if user_premises:
            return user_premises, "personalizadas"
        else:
            # Use global premises from premises_manager (that uses the personality)
            try:
                import sys
                import os
                # Add the news_watcher directory path to sys.path
                vigia_path = os.path.dirname(os.path.abspath(__file__))
                if vigia_path not in sys.path:
                    sys.path.insert(0, vigia_path)
                
                from premises_manager import get_premises_manager
                from agent_db import get_active_server_name
                server_name = get_active_server_name() or "default"
                premises_manager = get_premises_manager(server_name)
                return premises_manager.get_active_premises(), "globales"
            except ImportError as e:
                logger.error(f"Error importando premises_manager: {e}")
                return [], "error"
    
    def add_premise_usuario(self, user_id: str, nueva_premisa: str) -> tuple:
        """Add a premise to the user if there's space (maximum 7)."""
        try:
            premisas_actuales = self.get_user_premises(user_id)
            
            if len(premisas_actuales) >= 7:
                return False, "Has alcanzado el máximo de 7 premisas personalizadas"
            
            if nueva_premisa in premisas_actuales:
                return False, "Esa premisa ya existe en tu lista"
            
            premisas_actuales.append(nueva_premisa)
            
            if self.update_user_premises(user_id, premisas_actuales):
                return True, f"Premisa añadida: \"{nueva_premisa}\" ({len(premisas_actuales)}/7)"
            else:
                return False, "Error saving premise"
                
        except Exception as e:
            logger.exception(f"Error adding user premise: {e}")
            return False, "Error adding premise"
    
    def modificar_premisa_usuario(self, user_id: str, indice: int, nueva_premisa: str) -> tuple:
        """Modify a specific premise by its index (1-based)."""
        try:
            premisas_actuales = self.get_user_premises(user_id)
            
            if not premisas_actuales:
                return False, "No tienes premisas personalizadas. Usa !vigia premisas add para crearlas."
            
            if indice < 1 or indice > len(premisas_actuales):
                return False, f"Índice inválido. Debe estar entre 1 y {len(premisas_actuales)}"
            
            # Modificar la premisa
            premisa_anterior = premisas_actuales[indice - 1]
            premisas_actuales[indice - 1] = nueva_premisa
            
            if self.update_user_premises(user_id, premisas_actuales):
                return True, f"Premisa #{indice} actualizada: \"{premisa_anterior}\" → \"{nueva_premisa}\""
            else:
                return False, "Error modifying premise"
                
        except Exception as e:
            logger.exception(f"Error modifying user premise: {e}")
            return False, "Error modifying premise"
    
    # ===== CHANNEL PREMISES METHODS =====
    
    def get_channel_premises(self, channel_id: str) -> list:
        """Get customized premises for a channel."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT user_premises
                    FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1 AND user_premises IS NOT NULL
                ''', (f"channel_{channel_id}",))
                result = cursor.fetchone()
                
                if result and result[0]:
                    premises_str = result[0]
                    try:
                        # Try to parse as JSON first
                        return json.loads(premises_str)
                    except json.JSONDecodeError:
                        # If not JSON, treat as comma-separated string
                        if premises_str:
                            return [p.strip() for p in premises_str.split(',') if p.strip()]
                        return []
                return []
        except Exception as e:
            logger.exception(f"Error obteniendo premisas del canal: {e}")
            return []
    
    def update_channel_premises(self, channel_id: str, premisas: list) -> bool:
        """Update customized premises for a channel (maximum 7)."""
        try:
            if len(premisas) > 7:
                logger.warning(f"Canal {channel_id} intentó guardar más de 7 premisas")
                return False
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    # Actualizar todas las suscripciones del canal con las nuevas premisas
                    cursor.execute('''
                        UPDATE subscriptions_channels 
                        SET channel_premises = ?
                        WHERE channel_id = ? AND is_active = 1
                    ''', (json.dumps(premisas), channel_id))
                    conn.commit()
                    
                    logger.info(f"✅ Premisas actualizadas para canal {channel_id}: {len(premisas)} premisas")
                    return True
        except Exception as e:
            logger.exception(f"Error updating channel premises: {e}")
            return False
    
    def add_premise_canal(self, channel_id: str, nueva_premisa: str) -> tuple:
        """Añade una premisa al canal si hay hueco (máximo 7)."""
        try:
            premisas_actuales = self.get_channel_premises(channel_id)
            
            if len(premisas_actuales) >= 7:
                return False, "El canal ha alcanzado el máximo de 7 premisas personalizadas"
            
            if nueva_premisa in premisas_actuales:
                return False, "Esa premisa ya existe en la lista del canal"
            
            premisas_actuales.append(nueva_premisa)
            
            if self.update_channel_premises(channel_id, premisas_actuales):
                return True, f"Premisa de canal añadida: \"{nueva_premisa}\" ({len(premisas_actuales)}/7)"
            else:
                return False, "Error saving premise del canal"
                
        except Exception as e:
            logger.exception(f"Error adding channel premise: {e}")
            return False, "Error adding premise del canal"
    
    def modificar_premisa_canal(self, channel_id: str, indice: int, nueva_premisa: str) -> tuple:
        """Modifica una premisa específica del canal por su índice (1-based)."""
        try:
            premisas_actuales = self.get_channel_premises(channel_id)
            
            if not premisas_actuales:
                return False, "El canal no tiene premisas personalizadas. Usa !vigiacanal premisas add para crearlas."
            
            if indice < 1 or indice > len(premisas_actuales):
                return False, f"Índice inválido. Debe estar entre 1 y {len(premisas_actuales)}"
            
            # Modificar la premisa
            premisa_anterior = premisas_actuales[indice - 1]
            premisas_actuales[indice - 1] = nueva_premisa
            
            if self.update_channel_premises(channel_id, premisas_actuales):
                return True, f"Premisa de canal #{indice} actualizada: \"{premisa_anterior}\" → \"{nueva_premisa}\""
            else:
                return False, "Error modifying premise del canal"
                
        except Exception as e:
            logger.exception(f"Error modifying channel premise: {e}")
            return False, "Error modifying premise del canal"
    
    def get_channel_premises_with_context(self, channel_id: str) -> tuple:
        """Get channel premises with context (if has custom or uses global)."""
        channel_premises = self.get_channel_premises(channel_id)
        
        if channel_premises:
            return channel_premises, "personalizadas"
        else:
            # Usar premisas globales del premises_manager
            import sys
            import os
            # Añadir el path del directorio vigia_noticias al sys.path
            vigia_path = os.path.dirname(os.path.abspath(__file__))
            if vigia_path not in sys.path:
                sys.path.insert(0, vigia_path)
            
            from premises_manager import get_premises_manager
            from agent_db import get_active_server_name
            server_name = get_active_server_name() or "default"
            premises_manager = get_premises_manager(server_name)
            return premises_manager.get_active_premises(), "globales"

    def check_user_subscription_type(self, user_id: str) -> str:
        """Check what type of subscription a user has (exclusive).
        
        Returns:
            str: 'plana', 'palabras', 'ia', or 'ninguna'
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
                    return 'plana'
                
                # Check if user has keyword subscription
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_keywords 
                    WHERE user_id = ? AND is_active = 1
                ''', (user_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'palabras'
                
                # Check if user has AI subscription (subscriptions_categories with premises)
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1 AND user_premises IS NOT NULL AND user_premises != ''
                ''', (user_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'ia'
                
                return 'ninguna'
                
        except Exception as e:
            logger.exception(f"Error checking user subscription type: {e}")
            return 'ninguna'
    
    def check_channel_subscription_type(self, channel_id: str) -> str:
        """Check what type of subscription a channel has (exclusive).
        
        Returns:
            str: 'plana', 'palabras', 'ia', or 'ninguna'
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
                    return 'plana'
                
                # Check if channel has keyword subscription
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_keywords 
                    WHERE channel_id = ? AND is_active = 1
                ''', (channel_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'palabras'
                
                # Check if channel has AI subscription (channels with premises)
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_channels 
                    WHERE channel_id = ? AND is_active = 1 AND channel_premises IS NOT NULL AND channel_premises != ''
                ''', (channel_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'ia'
                
                return 'ninguna'
                
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
        """Get the configured keywords of a user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT keywords FROM subscriptions_keywords 
                    WHERE user_id = ? AND is_active = 1
                    ORDER BY id DESC LIMIT 1
                ''', (user_id,))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.exception(f"Error getting user keywords: {e}")
            return None
    
    def update_user_keywords(self, user_id: str, palabras: str) -> bool:
        """Update the keywords of a user."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE subscriptions_keywords 
                    SET keywords = ?
                    WHERE user_id = ? AND is_active = 1
                ''', (palabras, user_id))
                conn.commit()
                return cursor.rowcount > 0
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
            logger.exception(f"Error obteniendo suscripciones con palabras: {e}")
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
            logger.exception(f"Error obteniendo suscripciones con IA: {e}")
            return []


    def _init_method_config_table(self):
        """Initialize table for method configuration."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS method_config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_id TEXT NOT NULL,
                        method_type TEXT NOT NULL CHECK(method_type IN ('flat', 'keyword', 'general')),
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(server_id)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_method_config_server ON method_config (server_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_method_config_type ON method_config (method_type)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creating method_config table: {e}")

    def set_method_config(self, server_id: str, method_type: str) -> bool:
        """Set the method configuration for a server."""
        if method_type not in ['flat', 'keyword', 'general']:
            logger.error(f"Invalid method_type: {method_type}")
            return False
        
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO method_config (server_id, method_type, updated_at)
                    VALUES (?, ?, datetime('now'))
                ''', (server_id, method_type))
                conn.commit()
                return True
        except Exception as e:
            logger.exception(f"Error setting method config: {e}")
            return False

    def get_method_config(self, server_id: str) -> str:
        """Get the method configuration for a server."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT method_type FROM method_config WHERE server_id = ?', (server_id,))
                result = cursor.fetchone()
                return result[0] if result else 'general'  # Default to general
        except Exception as e:
            logger.exception(f"Error getting method config: {e}")
            return 'general'  # Default to general on error

    def count_user_subscriptions(self, user_id: str) -> int:
        """Count total active subscriptions for a user across all methods."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Count flat subscriptions
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1
                ''', (user_id,))
                flat_count = cursor.fetchone()[0]
                
                # Count keyword subscriptions
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_keywords 
                    WHERE user_id = ? AND is_active = 1
                ''', (user_id,))
                keyword_count = cursor.fetchone()[0]
                
                # Count AI subscriptions (already counted in flat, but with premises)
                # We need to subtract those already counted in flat to avoid double counting
                cursor.execute('''
                    SELECT COUNT(*) FROM subscriptions_categories 
                    WHERE user_id = ? AND is_active = 1 AND user_premises IS NOT NULL AND user_premises != ''
                ''', (user_id,))
                ai_count = cursor.fetchone()[0]
                
                # Total unique subscriptions = flat (including AI) + keyword
                return flat_count + keyword_count
                
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

    def get_all_user_subscriptions_keywords(self) -> List[tuple]:
        """Get all active keyword user subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, category, feed_id, keywords
                    FROM subscriptions_keywords
                    WHERE is_active = 1 AND user_id IS NOT NULL
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all keyword user subscriptions: {e}")
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

    def get_all_channel_subscriptions_flat(self) -> List[tuple]:
        """Get all active flat channel subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT channel_id, category, feed_id
                    FROM subscriptions_channels
                    WHERE is_active = 1 AND (channel_premises IS NULL OR channel_premises = '')
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all flat channel subscriptions: {e}")
            return []

    def get_all_channel_subscriptions_keywords(self) -> List[tuple]:
        """Get all active keyword channel subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT channel_id, category, feed_id, keywords
                    FROM subscriptions_keywords
                    WHERE is_active = 1 AND channel_id IS NOT NULL
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all keyword channel subscriptions: {e}")
            return []

    def get_all_channel_subscriptions_ai(self) -> List[tuple]:
        """Get all active AI channel subscriptions."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT channel_id, category, feed_id, channel_premises
                    FROM subscriptions_channels
                    WHERE is_active = 1 AND channel_premises IS NOT NULL AND channel_premises != ''
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error getting all AI channel subscriptions: {e}")
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
                return result[0] if result else 1  # Default to 1 hour
        except Exception as e:
            logger.exception(f"Error getting frequency setting: {e}")
            return 1  # Default to 1 hour on error

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


# Dictionary to maintain instances per server
_db_news_watcher_instances = {}

def get_news_watcher_db_instance(server_name: str = "default") -> DatabaseRoleNewsWatcher:
    """Get or create a news watcher database instance for a specific server."""
    if server_name not in _db_news_watcher_instances:
        _db_news_watcher_instances[server_name] = DatabaseRoleNewsWatcher(server_name)
    return _db_news_watcher_instances[server_name]


def get_vigia_db_instance(server_name: str = "default") -> DatabaseRoleNewsWatcher:
    """Backward-compatible alias for legacy imports."""
    return get_news_watcher_db_instance(server_name)
