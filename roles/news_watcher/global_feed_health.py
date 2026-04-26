#!/usr/bin/env python3
"""
Global RSS feed health checker for RoleAgentBot (NoSQL-backed).
Checks feed health once at startup and shares results with all servers.

Storage: databases/news_watcher/feeds_health.json
"""

from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict

from persistence.json_store import JsonStore
from agent_logging import get_logger

logger = get_logger('global_feed_health')


# Default feed catalog — seeded on first init
_DEFAULT_FEEDS = [
    # Crypto - Español
    ("Economía Digital", "https://www.economia3.com/feed/", "crypto", "es"),
    ("Investing.com ES", "https://es.investing.com/rss/news.rss", "crypto", "es"),
    # Crypto - Inglés
    ("Cointelegraph", "https://cointelegraph.com/rss", "crypto", "en"),
    ("Decrypt", "https://decrypt.co/feed", "crypto", "en"),
    ("The Block", "https://www.theblock.co/rss.xml", "crypto", "en"),

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
    ("Xinhua News", "http://www.xinhuanet.com/english/rss/chinarss.xml", "general", "zh"),

    # International - Español
    ("ABC Internacional", "https://www.abc.es/rss/feeds/abc_internacional.xml", "international", "es"),
    ("El Mundo Internacional", "https://e00-elmundo.uecdn.es/elmundo/rss/internacional.xml", "international", "es"),
    # International - Inglés
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "international", "en"),
    ("Al Jazeera English", "https://www.aljazeera.com/xml/rss/all.xml", "international", "en"),
    ("CNN World", "http://rss.cnn.com/rss/edition_world.rss", "international", "en"),
    # International - Chino
    ("China Daily World", "http://www.chinadaily.com.cn/rss/world_rss.xml", "international", "zh"),
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
]


def _get_store() -> JsonStore:
    """Get or create the global feeds JsonStore."""
    base_dir = Path(__file__).parent.parent.parent
    news_watcher_dir = base_dir / "databases" / "news_watcher"
    news_watcher_dir.mkdir(parents=True, exist_ok=True)
    return JsonStore(
        news_watcher_dir / "global_feeds.json",
        default_factory=lambda: {"feeds": {}, "health_log": []},
        keep_backup=False,
    )


_store: Optional[JsonStore] = None


def _get_global_store() -> JsonStore:
    global _store
    if _store is None:
        _store = _get_store()
    return _store


def initialize_global_feeds_db():
    """Initialize the global feeds store with default feeds if empty."""
    store = _get_global_store()
    state = store.load()
    feeds = state.get("feeds", {})

    if not feeds:
        logger.info("📡 Initializing global feeds with default feed catalog...")
        def updater(data: Dict) -> Dict:
            for idx, (name, url, category, language) in enumerate(_DEFAULT_FEEDS, start=1):
                data["feeds"][str(idx)] = {
                    "id": idx,
                    "name": name,
                    "url": url,
                    "category": category,
                    "language": language,
                    "active": True,
                    "status": "unknown",
                    "error_message": None,
                    "last_checked": None,
                }
            return data
        store.update(updater)
        logger.info(f"✅ Added {len(_DEFAULT_FEEDS)} default feeds to global store")


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
    """Check health of all global feeds and update their status (NoSQL-backed)."""
    logger.info("🔍 Starting global RSS feed health check...")

    try:
        initialize_global_feeds_db()
        store = _get_global_store()
        state = store.load()
        feeds = state.get("feeds", {})

        if not feeds:
            logger.warning("📡 No feeds found in global store")
            return

        logger.info(f"🔍 Checking health for {len(feeds)} global feeds...")
        healthy = 0
        broken = 0

        for feed_id, feed in feeds.items():
            name = feed.get("name", "?")
            url = feed.get("url", "")
            is_working, error_message = probe_feed_url(url)

            feed["status"] = "healthy" if is_working else "broken"
            feed["error_message"] = error_message
            feed["active"] = is_working
            feed["last_checked"] = datetime.now().isoformat()

            if is_working:
                healthy += 1
                logger.debug(f"✅ Feed healthy: {name}")
            else:
                broken += 1
                logger.warning(f"⚠️ Feed broken: {name} ({error_message})")

        # Persist updated statuses
        def updater(data: Dict) -> Dict:
            data["feeds"] = feeds
            return data
        store.update(updater)

        logger.info(f"✅ Global feed health check completed: {healthy} healthy, {broken} broken")

    except Exception as e:
        logger.exception(f"❌ Error during global feed health check: {e}")


def get_healthy_feeds(language: str = None) -> List[Tuple[int, str, str, str]]:
    """Get list of healthy feeds for use by all servers (NoSQL-backed).
    
    Args:
        language: Optional language code (e.g., 'en', 'es') to filter feeds by language.
                  If None, returns all healthy feeds regardless of language.
    
    Returns:
        List of tuples (id, name, url, category) for healthy feeds.
    """
    try:
        store = _get_global_store()
        state = store.load()
        feeds = state.get("feeds", {})
        results = []

        for feed in feeds.values():
            if not feed.get("active", True):
                continue
            if feed.get("status") == "broken":
                continue
            if language and feed.get("language") != language:
                continue
            results.append((
                feed.get("id", 0),
                feed.get("name", ""),
                feed.get("url", ""),
                feed.get("category", ""),
            ))

        # Sort by category, name
        results.sort(key=lambda x: (x[3], x[1]))
        return results

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
