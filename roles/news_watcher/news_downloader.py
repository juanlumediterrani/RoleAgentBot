"""News downloader - fetches and stores news in global database."""

import asyncio
import os
from http.cookiejar import MozillaCookieJar
from curl_cffi import requests
import feedparser
from datetime import datetime, timedelta
from agent_logging import get_logger

logger = get_logger('news_downloader')


class NewsDownloader:
    """Downloads news from RSS feeds and stores in global database."""
    
    def __init__(self, global_db):
        self.global_db = global_db
        self.session = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        self._load_cookies()
    
    def _load_cookies(self):
        """Load cookies from cookies.txt file if it exists."""
        self.cookies = None
        cookies_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cookies.txt")
        if os.path.exists(cookies_path):
            try:
                cookie_jar = MozillaCookieJar(cookies_path)
                cookie_jar.load(ignore_discard=True, ignore_expires=True)
                self.cookies = cookie_jar
                logger.info(f"Loaded {len(cookie_jar)} cookies from {cookies_path}")
            except Exception as e:
                logger.warning(f"Failed to load cookies from {cookies_path}: {e}")
    
    def _get_session(self):
        """Get or create curl_cffi session with Chrome impersonation."""
        if self.session is None:
            self.session = requests.AsyncSession(
                impersonate="chrome",
                headers=self.headers,
                cookies=self.cookies
            )
        return self.session
    
    async def fetch_and_store_news(self, feed_url: str, feed_category: str, feed_name: str, max_items: int = 50, retry_count: int = 0) -> list:
        """
        Fetch news from a feed and store new items in global database.
        Also updates the feed's last_updated timestamp.
        
        Returns list of new news items (title, link, summary, published_date).
        """
        try:
            session = self._get_session()
            response = await session.get(feed_url, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"Failed to fetch feed {feed_name}: HTTP {response.status_code}")
                
                # Retry on 429, 403, 500 with backoff
                if response.status_code in [429, 403, 500, 502, 503, 504] and retry_count < 2:
                    backoff = 2 ** retry_count
                    logger.info(f"Retrying {feed_name} in {backoff}s (attempt {retry_count + 1}/2)")
                    await asyncio.sleep(backoff)
                    return await self.fetch_and_store_news(feed_url, feed_category, feed_name, max_items, retry_count + 1)
                
                return []
            
            raw_data = response.text
            feed = feedparser.parse(raw_data)
                    
            # Get feed title for comparison (to avoid using feed title as article title)
            feed_title = feed.get('feed', {}).get('title', '') if hasattr(feed, 'feed') else ''
            
            # Log suspicious empty feeds (HTTP 200 but 0 entries - possible blocking)
            if len(feed.entries) == 0:
                logger.warning(f"[SUSPICIOUS] Feed {feed_name} returned HTTP 200 but 0 entries - possible bot protection blocking")
            
            new_items = []
            for entry in feed.entries[:max_items]:
                title = entry.get('title', 'No title')
                link = entry.get('link', '')
                summary = entry.get('summary', entry.get('description', ''))
                published_date = entry.get('published')

                # Skip entries without valid title
                if not title or title.strip() == '' or title == 'No title':
                    logger.debug(f"[FEED SKIP] Skipping entry without valid title from {feed_name}")
                    continue

                # Check if entry title is same as feed title (indicates malformed feed)
                if title == feed_title and title:
                    logger.warning(f"[FEED WARNING] Entry title matches feed title for {feed_name}: '{title[:50]}...'. Skipping malformed entry.")
                    continue

                # Skip entries without valid description (false positives)
                if not summary or summary.strip() == '' or summary.strip() == 'No description':
                    logger.debug(f"[FEED SKIP] Skipping entry without valid description from {feed_name}: '{title[:50]}...'")
                    continue

                # Debug logging to check title extraction
                logger.debug(f"[FEED DEBUG] Feed: {feed_name}, Entry title: '{title[:50]}...', Link: '{link[:50]}...'")

                # Check if already in global database
                if self.global_db.is_news_globally_processed(title):
                    logger.debug(f"News already in global DB: {title[:50]}...")
                    continue

                # Store in global database
                self.global_db.store_news_content(
                    title=title,
                    source_url=link,
                    feed_category=feed_category,
                    feed_url=feed_url,
                    summary=summary,
                    published_date=published_date
                )

                new_items.append({
                    'title': title,
                    'link': link,
                    'summary': summary,
                    'published_date': published_date,
                    'feed_name': feed_name
                })

            # Update feed last_updated timestamp if we got any items
            if new_items or feed.entries:
                self.global_db.update_feed_last_updated(feed_url, feed_name, feed_category)

            logger.info(f"📥 Downloaded {len(new_items)} new items from {feed_name}")
            return new_items
                    
        except requests.TimeoutError:
            logger.warning(f"Timeout fetching news from {feed_name} (30s)")
            if retry_count < 2:
                backoff = 2 ** retry_count
                logger.info(f"Retrying {feed_name} in {backoff}s (attempt {retry_count + 1}/2)")
                await asyncio.sleep(backoff)
                return await self.fetch_and_store_news(feed_url, feed_category, feed_name, max_items, retry_count + 1)
            return []
        except Exception as e:
            logger.exception(f"Error fetching news from {feed_name}: {e}")
            if retry_count < 2 and "blocked" in str(e).lower() or "forbidden" in str(e).lower():
                backoff = 2 ** retry_count
                logger.info(f"Retrying {feed_name} in {backoff}s (attempt {retry_count + 1}/2)")
                await asyncio.sleep(backoff)
                return await self.fetch_and_store_news(feed_url, feed_category, feed_name, max_items, retry_count + 1)
            return []
    
    async def get_news_for_subscription(self, feed_url: str, feed_category: str, since_hours: int = 24) -> list:
        """
        Get news from global database for a subscription within the frequency window.
        
        Returns list of news items (title, source_url, summary, published_date, first_seen).
        """
        try:
            since_date = (datetime.now() - timedelta(hours=since_hours)).isoformat()
            
            if feed_url:
                # Get news from specific feed
                news = self.global_db.get_news_by_feed(feed_url, since_date=since_date, limit=100)
            else:
                # Get news from category (all feeds)
                news = self.global_db.get_news_by_category(feed_category, since_date=since_date, limit=100)
            
            logger.info(f"📰 Found {len(news)} news items for subscription (last {since_hours}h)")
            return news
            
        except Exception as e:
            logger.exception(f"Error getting news for subscription: {e}")
            return []
    
    async def download_all_feeds(self, feeds: list) -> dict:
        """
        Download news from multiple feeds.
        
        Args:
            feeds: List of tuples (feed_id, name, url, category)
        
        Returns:
            Dict with feed_url as key and list of new items as value
        """
        results = {}
        
        for feed_id, name, url, category in feeds:
            new_items = await self.fetch_and_store_news(url, category, name)
            if new_items:
                results[url] = new_items
        
        total_new = sum(len(items) for items in results.values())
        logger.info(f"📥 Total downloaded: {total_new} new items from {len(results)} feeds")
        
        return results


async def download_news_for_category(global_db, category: str, limit_per_feed: int = 50) -> list:
    """
    Download news from all feeds in a category.
    
    Returns list of all new items across all feeds in the category.
    """
    try:
        from roles.news_watcher.global_feed_health import get_healthy_feeds
        
        healthy_feeds = get_healthy_feeds()
        category_feeds = [(fid, name, url, cat) for fid, name, url, cat in healthy_feeds if cat == category]
        
        if not category_feeds:
            logger.warning(f"No healthy feeds found for category: {category}")
            return []
        
        downloader = NewsDownloader(global_db)
        results = await downloader.download_all_feeds(category_feeds)
        
        all_items = []
        for items in results.values():
            all_items.extend(items)
        
        return all_items
        
    except Exception as e:
        logger.exception(f"Error downloading news for category {category}: {e}")
        return []


async def download_all_feeds_global(feeds: list) -> dict:
    """
    Download news from all feeds globally in background with control yielding.
    
    This function is designed to be run as a background task by the global scheduler.
    It yields control between each feed download to avoid blocking the event loop.
    
    Args:
        feeds: List of tuples (feed_id, name, url, category)
    
    Returns:
        Dict with feed_url as key and list of new items as value
    """
    try:
        from .global_news_nosql import get_global_news_nosql

        global_db = get_global_news_nosql()
        downloader = NewsDownloader(global_db)
        
        results = {}
        total_new = 0
        
        logger.info(f"📥 Starting background download for {len(feeds)} feeds...")
        
        for i, (feed_id, name, url, category) in enumerate(feeds):
            try:
                # Download news for this feed
                new_items = await downloader.fetch_and_store_news(url, category, name, max_items=50)
                
                if new_items:
                    results[url] = new_items
                    total_new += len(new_items)
                    logger.info(f"📥 Feed {i+1}/{len(feeds)}: {name} - {len(new_items)} new items")
                else:
                    logger.debug(f"📥 Feed {i+1}/{len(feeds)}: {name} - no new items")
                
                # Yield control between feeds to avoid blocking
                await asyncio.sleep(0)
                
            except Exception as e:
                logger.error(f"Error downloading from {name}: {e}")
                # Continue with next feed even if one fails
                await asyncio.sleep(0)
        
        logger.info(f"📥 Background download completed: {total_new} new items from {len(results)} feeds")
        return results
        
    except Exception as e:
        logger.exception(f"Error in download_all_feeds_global: {e}")
        return {}
