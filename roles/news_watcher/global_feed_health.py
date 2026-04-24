#!/usr/bin/env python3
"""
Global RSS feed health checker for RoleAgentBot.
Checks feed health once at startup and shares results with all servers.
"""

import sqlite3
from pathlib import Path
from typing import List, Tuple
from agent_logging import get_logger

logger = get_logger('global_feed_health')

def get_global_feeds_db_path() -> Path:
    """Generate path for global feeds database (shared across all servers)."""
    base_dir = Path(__file__).parent.parent.parent
    news_watcher_db_dir = base_dir / "databases" / "news_watcher"
    news_watcher_db_dir.mkdir(parents=True, exist_ok=True)
    return news_watcher_db_dir / "global_feeds.db"

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
                language TEXT DEFAULT 'en',
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
                # Crypto - Español
                ("Economía Digital", "https://www.economia3.com/feed/", "crypto", "es"),
                ("Investing.com ES", "https://es.investing.com/rss/news.rss", "crypto", "es"),
                # BitcoinEspaña - REMOVED: Domain expired, redirects to legendarynames.com
                # Crypto - Inglés
                ("Cointelegraph", "https://cointelegraph.com/rss", "crypto", "en"),
                ("Decrypt", "https://decrypt.co/feed", "crypto", "en"),
                ("The Block", "https://www.theblock.co/rss.xml", "crypto", "en"),
                # Crypto - Chino
                # Odaily Starry - REMOVED: Not an RSS feed, returns HTML page
                # The Block CN - REMOVED: Empty feed
                # Decrypt CN - REMOVED: Empty feed
                
                # Economy - Español
                ("El País Economía", "https://elpais.com/rss/feed.html?section=economia", "economy", "es"),
                ("Investing.com ES Economy", "https://es.investing.com/rss/news_301.rss", "economy", "es"),
                ("El Mundo Economía", "https://e00-elmundo.uecdn.es/elmundo/rss/economia.xml", "economy", "es"),
                # Economy - Inglés
                ("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss", "economy", "en"),
                ("CNBC Markets", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "economy", "en"),
                ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/", "economy", "en"),
                # Economy - Chino
                ("36Kr Economy", "https://36kr.com/feed", "economy", "zh"),
                # Sina Finance - REMOVED: Not an RSS feed, redirects with JavaScript
                
                # General - Español
                ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "general", "es"),
                ("20minutos", "https://www.20minutos.es/rss/", "general", "es"),
                ("El Mundo", "https://elmundo.es/rss/portada.xml", "general", "es"),
                # General - Inglés
                ("BBC News", "http://feeds.bbci.co.uk/news/rss.xml", "general", "en"),
                ("The Guardian", "https://www.theguardian.com/world/rss", "general", "en"),
                ("ABC News", "https://feeds.abcnews.com/abcnews/topstories", "general", "en"),
                # General - Chino
                ("China Daily", "http://www.chinadaily.com.cn/rss/china_rss.xml", "general", "zh"),
                # Sina News - REMOVED: Page not found (404)
                ("Xinhua News", "http://www.xinhuanet.com/english/rss/chinarss.xml", "general", "zh"),
                
                # International - Español
                # El País Internacional - REMOVED: Redirects to general feed, no specific international feed
                ("ABC Internacional", "https://www.abc.es/rss/feeds/abc_internacional.xml", "international", "es"),
                ("El Mundo Internacional", "https://e00-elmundo.uecdn.es/elmundo/rss/internacional.xml", "international", "es"),
                # International - Inglés
                ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "international", "en"),
                ("Al Jazeera English", "https://www.aljazeera.com/xml/rss/all.xml", "international", "en"),
                ("CNN World", "http://rss.cnn.com/rss/edition_world.rss", "international", "en"),
                # International - Chino
                ("China Daily World", "http://www.chinadaily.com.cn/rss/world_rss.xml", "international", "zh"),
                # CCTV World - REMOVED: Encoding error (UTF-8 decode error)
                ("Xinhua World", "http://www.xinhuanet.com/english/rss/worldrss.xml", "international", "zh"),
                
                # Technology - Español
                ("Hipertextual", "https://hipertextual.com/feed", "technology", "es"),
                ("ABC Tecnología", "https://www.abc.es/rss/feeds/abc_Tecnologia.xml", "technology", "es"),
                ("20minutos Tecnología", "https://www.20minutos.es/rss/tecnologia.xml", "technology", "es"),
                # Technology - Inglés
                ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "technology", "en"),
                ("TechCrunch", "https://techcrunch.com/feed/", "technology", "en"),
                ("The Verge", "https://www.theverge.com/rss/index.xml", "technology", "en"),
                # Technology - Chino
                ("TechNode", "https://technode.com/feed/", "technology", "zh"),
                # Sina Tech - REMOVED: Page not found (404)
                # PingWest - REMOVED: Page not found (404)
            ]
            
            cursor.executemany('''
                INSERT INTO feeds (name, url, category, language) VALUES (?, ?, ?, ?)
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

def get_healthy_feeds(language: str = None) -> List[Tuple[int, str, str, str]]:
    """Get list of healthy feeds for use by all servers.
    
    Args:
        language: Optional language code (e.g., 'en', 'es') to filter feeds by language.
                  If None, returns all healthy feeds regardless of language.
    
    Returns:
        List of tuples (id, name, url, category) for healthy feeds.
    """
    try:
        db_path = get_global_feeds_db_path()
        
        with sqlite3.connect(str(db_path), timeout=30) as conn:
            cursor = conn.cursor()
            
            if language:
                cursor.execute('''
                    SELECT id, name, url, category 
                    FROM feeds 
                    WHERE active = 1 AND status = 'healthy' AND language = ?
                    ORDER BY category, name
                ''', (language,))
            else:
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


if __name__ == "__main__":
    # For manual testing
    check_global_feed_health()
    healthy = get_healthy_feeds()
    print(f"Found {len(healthy)} healthy feeds")
    for feed_id, name, url, category in healthy:
        print(f"  {name} ({category}): {url}")
