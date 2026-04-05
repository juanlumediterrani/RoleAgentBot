#!/usr/bin/env python3
"""
Global RSS feed health checker for RoleAgentBot.
Checks feed health once at startup and shares results with all servers.
"""

import sqlite3
from pathlib import Path
from typing import List, Tuple
from agent_logging import get_logger
from agent_db import get_personality_name

logger = get_logger('global_feed_health')

def get_global_feeds_db_path() -> Path:
    """Generate path for global feeds database (shared across all servers)."""
    personality_name = get_personality_name()
    base_dir = Path(__file__).parent.parent.parent
    data_dir = base_dir / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / f"global_feeds_{personality_name}.db"

def initialize_global_feeds_db():
    """Initialize the global feeds database with default feeds."""
    db_path = get_global_feeds_db_path()
    
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        cursor = conn.cursor()
        
        # Create feeds table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                active BOOLEAN DEFAULT 1,
                last_checked TEXT,
                status TEXT DEFAULT 'unknown',
                error_message TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create health check results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS feed_health_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id INTEGER,
                check_time TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                error_message TEXT,
                FOREIGN KEY (feed_id) REFERENCES feeds (id)
            )
        ''')
        
        # Insert default feeds if table is empty
        cursor.execute('SELECT COUNT(*) FROM feeds')
        if cursor.fetchone()[0] == 0:
            logger.info("📡 Initializing global feeds database with default feeds...")
            default_feeds = [
                ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "crypto"),
                ("Cointelegraph", "https://cointelegraph.com/rss", "crypto"),
                ("Decrypt", "https://decrypt.co/feed", "crypto"),
                ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss", "economy"),
                ("Financial Times", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "economy"),
                ("Reuters Business", "https://feeds.feedburner.com/TechCrunch", "economy"),
                ("Associated Press News", "https://www.wired.com/feed/rss", "general"),
                ("Reuters Top News", "https://feeds.macrumors.com/public", "general"),
                ("The Guardian World", "https://www.theguardian.com/world/rss", "general"),
                ("Al Jazeera English", "https://www.aljazeera.com/xml/rss/all.xml", "international"),
                ("BBC World News", "http://rss.cnn.com/rss/edition_world.rss", "international"),
                ("Reuters World", "https://feeds.feedburner.com/oreilly/radar", "international"),
                ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "technology"),
                ("BBC Technology", "https://www.zdnet.com/news/rss.xml", "technology"),
                ("TechCrunch", "https://techcrunch.com/feed/", "technology"),
            ]
            
            cursor.executemany('''
                INSERT INTO feeds (name, url, category) VALUES (?, ?, ?)
            ''', default_feeds)
            
            logger.info(f"✅ Added {len(default_feeds)} default feeds to global database")
        
        conn.commit()

def probe_feed_url(url: str, timeout: int = 10) -> Tuple[bool, str]:
    """Probe a feed URL and return (is_working, error_message)."""
    try:
        from urllib import request as urllib_request, error as urllib_error
        
        request = urllib_request.Request(url, headers={"User-Agent": "RoleAgentBot/1.0"})
        with urllib_request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, 'status', None) or response.getcode()
            if 200 <= status < 300:
                # Read a small chunk to ensure stream works
                response.read(1024)
                return True, None
            return False, f"HTTP {status}"
    except urllib_error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

def check_global_feed_health():
    """Check health of all global feeds and update their status."""
    logger.info("🔍 Starting global RSS feed health check...")
    
    try:
        initialize_global_feeds_db()
        db_path = get_global_feeds_db_path()
        
        with sqlite3.connect(str(db_path), timeout=30) as conn:
            cursor = conn.cursor()
            
            # Get all feeds
            cursor.execute('SELECT id, name, url FROM feeds')
            feeds = cursor.fetchall()
            
            if not feeds:
                logger.warning("📡 No feeds found in global database")
                return
            
            logger.info(f"🔍 Checking health for {len(feeds)} global feeds...")
            healthy = 0
            broken = 0
            
            for feed_id, name, url in feeds:
                is_working, error_message = probe_feed_url(url)
                
                # Update feed status
                cursor.execute('''
                    UPDATE feeds 
                    SET status = ?, error_message = ?, last_checked = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP,
                        active = ?
                    WHERE id = ?
                ''', ('healthy' if is_working else 'broken', error_message, is_working, feed_id))
                
                # Log the health check
                cursor.execute('''
                    INSERT INTO feed_health_log (feed_id, status, error_message)
                    VALUES (?, ?, ?)
                ''', (feed_id, 'healthy' if is_working else 'broken', error_message))
                
                if is_working:
                    healthy += 1
                    logger.debug(f"✅ Feed healthy: {name}")
                else:
                    broken += 1
                    logger.warning(f"⚠️ Feed broken: {name} ({error_message})")
            
            conn.commit()
            logger.info(f"✅ Global feed health check completed: {healthy} healthy, {broken} broken")
            
    except Exception as e:
        logger.exception(f"❌ Error during global feed health check: {e}")

def get_healthy_feeds() -> List[Tuple[int, str, str, str]]:
    """Get list of healthy feeds for use by all servers."""
    try:
        db_path = get_global_feeds_db_path()
        
        with sqlite3.connect(str(db_path), timeout=30) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, name, url, category 
                FROM feeds 
                WHERE active = 1 AND status = 'healthy'
                ORDER BY category, name
            ''')
            return cursor.fetchall()
            
    except Exception as e:
        logger.exception(f"❌ Error getting healthy feeds: {e}")
        return []

def sync_feeds_to_server(server_id: str):
    """Sync healthy global feeds to a specific server's database."""
    try:
        from roles.news_watcher.db_role_news_watcher import DatabaseRoleNewsWatcher
        
        healthy_feeds = get_healthy_feeds()
        if not healthy_feeds:
            logger.warning(f"📡 No healthy feeds to sync to server {server_id}")
            return
        
        logger.info(f"📡 Syncing {len(healthy_feeds)} healthy feeds to server {server_id}...")
        
        server_db = DatabaseRoleNewsWatcher(server_id)
        
        with server_db._lock:
            with sqlite3.connect(str(server_db.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Clear existing feeds
                cursor.execute('DELETE FROM feeds_config')
                
                # Insert healthy feeds
                from datetime import datetime
                feed_data = [(name, url, category, None, 'es', None, 0, 1, 'especializado', datetime.now().isoformat()) 
                           for _, name, url, category in healthy_feeds]
                cursor.executemany('''
                    INSERT INTO feeds_config (name, url, category, country, language, keywords, priority, active, feed_type, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', feed_data)
                
                conn.commit()
                
        logger.info(f"✅ Synced {len(healthy_feeds)} feeds to server {server_id}")
        
    except Exception as e:
        logger.exception(f"❌ Error syncing feeds to server {server_id}: {e}")

if __name__ == "__main__":
    # For manual testing
    check_global_feed_health()
    healthy = get_healthy_feeds()
    print(f"Found {len(healthy)} healthy feeds")
    for feed_id, name, url, category in healthy:
        print(f"  {name} ({category}): {url}")
