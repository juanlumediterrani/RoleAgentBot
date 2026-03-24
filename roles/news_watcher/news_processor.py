#!/usr/bin/env python3
"""
News Watcher - Optimized News Processing Architecture

This module implements efficient news processing with caching to avoid
redundant downloads and processing when multiple subscriptions use
the same feed and similar filtering criteria.
"""

import asyncio
import hashlib
import logging
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from urllib import request as urllib_request, error as urllib_error
import feedparser
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def generate_premises_hash(premises: str) -> str:
    """
    Generate a consistent hash for premises string.
    
    Args:
        premises: Comma-separated premises string
        
    Returns:
        SHA256 hash of normalized premises
    """
    if not premises:
        return ""
    
    # Normalize premises: sort, lowercase, remove extra whitespace
    premise_list = [p.strip().lower() for p in premises.split(',') if p.strip()]
    premise_list.sort()  # Sort for consistent ordering
    normalized = ",".join(premise_list)
    
    # Generate hash
    return hashlib.sha256(normalized.encode()).hexdigest()

def generate_keywords_hash(keywords: str) -> str:
    """
    Generate a consistent hash for keywords string.
    
    Args:
        keywords: Comma-separated keywords string
        
    Returns:
        SHA256 hash of normalized keywords
    """
    if not keywords:
        return ""
    
    # Normalize keywords: sort, lowercase, remove extra whitespace
    keyword_list = [k.strip().lower() for k in keywords.split(',') if k.strip()]
    keyword_list.sort()  # Sort for consistent ordering
    normalized = ",".join(keyword_list)
    
    # Generate hash
    return hashlib.sha256(normalized.encode()).hexdigest()

@dataclass
class NewsItem:
    """Represents a single news item from RSS feed."""
    title: str
    link: str
    description: str
    published: str
    content: str
    feed_id: int
    category: str
    guid: str  # Unique identifier for the news item
    
    def get_hash(self) -> str:
        """Generate unique hash for this news item."""
        content = f"{self.title}{self.link}{self.feed_id}"
        return hashlib.md5(content.encode()).hexdigest()

@dataclass
class ProcessingCache:
    """Cache for processed news to avoid redundant processing."""
    news_hash: str
    method: str
    filter_hash: str  # Hash of keywords or premises
    result: str  # processed output
    timestamp: datetime
    user_id: str
    channel_id: Optional[str] = None

@dataclass
class PremisesCache:
    """Cache for premises analysis results."""
    premises_hash: str
    news_hash: str
    analysis_result: str
    timestamp: datetime

@dataclass
class KeywordsCache:
    """Cache for keyword matching results."""
    keywords_hash: str
    news_hash: str
    matched_keywords: List[str]
    timestamp: datetime

class NewsProcessor:
    """Optimized news processing with caching and deduplication."""
    
    def __init__(self, db_instance):
        self.db = db_instance
        self.news_cache: Dict[str, NewsItem] = {}  # news_hash -> NewsItem
        self.processing_cache: Dict[str, ProcessingCache] = {}  # cache_key -> ProcessingCache
        self.premises_cache: Dict[str, PremisesCache] = {}  # premises_key -> PremisesCache
        self.keywords_cache: Dict[str, KeywordsCache] = {}  # keywords_key -> KeywordsCache
        self.feed_cache_time: Dict[str, datetime] = {}  # feed_id -> last_fetch_time
        self.cache_duration = timedelta(minutes=30)  # Cache news for 30 minutes
        
    async def process_all_subscriptions(self, server_id: str) -> List[Tuple[str, str, str]]:
        """
        Process all active subscriptions and return messages to send.
        
        Returns:
            List of tuples (user_id/channel_id, message, delivery_type)
            where delivery_type is 'user' or 'channel'
        """
        messages_to_send = []
        
        # Get all active subscriptions
        user_subscriptions = self._get_all_user_subscriptions()
        channel_subscriptions = self._get_all_channel_subscriptions()
        
        # Group subscriptions by feed_id to avoid redundant downloads
        feed_groups = self._group_subscriptions_by_feed(user_subscriptions + channel_subscriptions)
        
        # Process each feed group
        for feed_id, subscriptions in feed_groups.items():
            try:
                # Download news once for this feed
                news_items = await self._download_feed_news(feed_id)
                if not news_items:
                    continue
                
                # Process each subscription with the same news
                for sub in subscriptions:
                    messages = await self._process_subscription(sub, news_items)
                    messages_to_send.extend(messages)
                    
            except Exception as e:
                logger.exception(f"Error processing feed {feed_id}: {e}")
                continue
        
        return messages_to_send
    
    def _get_all_user_subscriptions(self) -> List[Dict]:
        """Get all active user subscriptions across all methods."""
        all_subscriptions = []
        
        try:
            # Get flat subscriptions
            flat_subs = self.db.get_all_user_subscriptions_flat()
            for user_id, category, feed_id in flat_subs:
                all_subscriptions.append({
                    'user_id': user_id,
                    'channel_id': None,
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'flat',
                    'filter_criteria': None
                })
            
            # Get keyword subscriptions
            keyword_subs = self.db.get_all_user_subscriptions_keywords()
            for user_id, category, feed_id, keywords in keyword_subs:
                all_subscriptions.append({
                    'user_id': user_id,
                    'channel_id': None,
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'keyword',
                    'filter_criteria': keywords
                })
            
            # Get AI subscriptions
            ai_subs = self.db.get_all_user_subscriptions_ai()
            for user_id, category, feed_id, premises in ai_subs:
                all_subscriptions.append({
                    'user_id': user_id,
                    'channel_id': None,
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'general',
                    'filter_criteria': premises
                })
                
        except Exception as e:
            logger.exception(f"Error getting user subscriptions: {e}")
        
        return all_subscriptions
    
    def _get_all_channel_subscriptions(self) -> List[Dict]:
        """Get all active channel subscriptions across all methods."""
        all_subscriptions = []
        
        try:
            # Get flat channel subscriptions
            flat_subs = self.db.get_all_channel_subscriptions_flat()
            for channel_id, category, feed_id in flat_subs:
                all_subscriptions.append({
                    'user_id': None,
                    'channel_id': channel_id,
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'flat',
                    'filter_criteria': None
                })
            
            # Get keyword channel subscriptions
            keyword_subs = self.db.get_all_channel_subscriptions_keywords()
            for channel_id, category, feed_id, keywords in keyword_subs:
                all_subscriptions.append({
                    'user_id': None,
                    'channel_id': channel_id,
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'keyword',
                    'filter_criteria': keywords
                })
            
            # Get AI channel subscriptions
            ai_subs = self.db.get_all_channel_subscriptions_ai()
            for channel_id, category, feed_id, premises in ai_subs:
                all_subscriptions.append({
                    'user_id': None,
                    'channel_id': channel_id,
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'general',
                    'filter_criteria': premises
                })
                
        except Exception as e:
            logger.exception(f"Error getting channel subscriptions: {e}")
        
        return all_subscriptions
    
    def _group_subscriptions_by_feed(self, subscriptions: List[Dict]) -> Dict[int, List[Dict]]:
        """Group subscriptions by feed_id to optimize downloads."""
        feed_groups = {}
        
        for sub in subscriptions:
            feed_id = sub['feed_id']
            if feed_id not in feed_groups:
                feed_groups[feed_id] = []
            feed_groups[feed_id].append(sub)
        
        return feed_groups
    
    async def _download_feed_news(self, feed_id: int) -> List[NewsItem]:
        """
        Download latest 5 news items from a feed with caching.
        
        Args:
            feed_id: The feed ID to download from
            
        Returns:
            List of NewsItem objects
        """
        cache_key = f"feed_{feed_id}"
        now = datetime.now()
        
        # Check if we have recent cached news for this feed
        if (cache_key in self.feed_cache_time and 
            now - self.feed_cache_time[cache_key] < self.cache_duration):
            
            # Return cached news items
            cached_items = [item for item in self.news_cache.values() 
                           if item.feed_id == feed_id]
            if cached_items:
                logger.info(f"Using cached news for feed {feed_id}: {len(cached_items)} items")
                return cached_items[:5]  # Return latest 5
        
        # Download fresh news
        try:
            feed_info = self.db.get_feed_info(feed_id)
            if not feed_info:
                logger.error(f"Feed {feed_id} not found in database")
                return []
            
            feed_url = feed_info['url']
            logger.info(f"Downloading news from feed {feed_id}: {feed_url}")
            
            # Download RSS feed with proper User-Agent to avoid 403 errors
            try:
                request = urllib_request.Request(feed_url, headers={"User-Agent": "RoleAgentBot/1.0"})
                with urllib_request.urlopen(request, timeout=30) as response:
                    if response.getcode() == 200:
                        raw_data = response.read().decode('utf-8')
                        feed = feedparser.parse(raw_data)
                    else:
                        logger.error(f"HTTP {response.getcode()} error fetching feed {feed_id}: {feed_url}")
                        return []
            except urllib_error.HTTPError as e:
                logger.error(f"HTTP {e.code} error fetching feed {feed_id}: {feed_url}")
                return []
            except Exception as e:
                logger.error(f"Error fetching feed {feed_id}: {e}")
                return []
            
            if feed.bozo:
                logger.warning(f"Feed {feed_id} has parsing issues: {feed.bozo_exception}")
            
            # Process latest 5 items
            news_items = []
            for entry in feed.entries[:5]:
                try:
                    # Clean HTML content
                    content = self._clean_html(entry.get('description', ''))
                    if not content:
                        content = self._clean_html(entry.get('content', [{}])[0].get('value', ''))
                    
                    news_item = NewsItem(
                        title=entry.get('title', 'No title'),
                        link=entry.get('link', ''),
                        description=content[:200],  # Truncate description
                        published=entry.get('published', ''),
                        content=content,
                        feed_id=feed_id,
                        category=feed_info['category'],
                        guid=entry.get('id', entry.get('link', ''))
                    )
                    
                    # Cache the news item
                    self.news_cache[news_item.get_hash()] = news_item
                    news_items.append(news_item)
                    
                except Exception as e:
                    logger.warning(f"Error processing news item: {e}")
                    continue
            
            # Update cache timestamp
            self.feed_cache_time[cache_key] = now
            
            # Clean old cache entries
            self._cleanup_old_cache()
            
            logger.info(f"Downloaded {len(news_items)} news items from feed {feed_id}")
            return news_items
            
        except Exception as e:
            logger.exception(f"Error downloading feed {feed_id}: {e}")
            return []
    
    def _clean_html(self, html_content: str) -> str:
        """Clean HTML content and extract text."""
        if not html_content:
            return ""
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove all script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Remove all img tags completely
            for img in soup.find_all('img'):
                img.decompose()
            
            # Remove all link tags but keep their text
            for a in soup.find_all('a'):
                a.replace_with(a.get_text())
            
            # Remove all other HTML tags
            for tag in soup.find_all():
                if tag.name not in ['p', 'br', 'span']:
                    tag.replace_with(tag.get_text())
            
            # Get clean text with proper spacing
            text = soup.get_text(separator=' ', strip=True)
            
            # Remove extra whitespace and normalize
            text = ' '.join(text.split())
            
            # Remove any remaining HTML entities
            import html
            text = html.unescape(text)
            
            return text
        except Exception as e:
            logger.warning(f"Error cleaning HTML: {e}")
            # Fallback: remove basic HTML tags manually
            import re
            import html
            # Remove img tags completely
            text = re.sub(r'<img[^>]*>', '', html_content, flags=re.IGNORECASE)
            # Remove script and style tags
            text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.IGNORECASE | re.DOTALL)
            # Remove all other HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            # Clean up whitespace
            text = ' '.join(text.split())
            # Unescape HTML entities
            text = html.unescape(text)
            return text
    
    async def _process_subscription(self, subscription: Dict, news_items: List[NewsItem]) -> List[Tuple[str, str, str]]:
        """
        Process a subscription with news items and return messages to send.
        
        Args:
            subscription: Subscription dictionary
            news_items: List of NewsItem objects
            
        Returns:
            List of tuples (recipient_id, message, delivery_type)
        """
        messages = []
        method = subscription['method']
        filter_criteria = subscription['filter_criteria']
        recipient_id = subscription['user_id'] or subscription['channel_id']
        delivery_type = 'channel' if subscription['channel_id'] else 'user'
        
        # Process each news item
        for news_item in news_items:
            try:
                # Check if we have cached processing result
                cache_key = self._get_cache_key(news_item, method, filter_criteria, recipient_id)
                
                if cache_key in self.processing_cache:
                    # Use cached result
                    cached = self.processing_cache[cache_key]
                    if cached.result:  # Only send if there's content to send
                        messages.append((recipient_id, cached.result, delivery_type))
                    continue
                
                # Process news item based on method
                processed_result = await self._apply_method(news_item, method, filter_criteria)
                
                # Cache the result
                cache_entry = ProcessingCache(
                    news_hash=news_item.get_hash(),
                    method=method,
                    filter_criteria=filter_criteria or "",
                    result=processed_result,
                    timestamp=datetime.now(),
                    user_id=subscription['user_id'] or "",
                    channel_id=subscription['channel_id']
                )
                self.processing_cache[cache_key] = cache_entry
                
                # Add to messages if there's content to send
                if processed_result:
                    messages.append((recipient_id, processed_result, delivery_type))
                
            except Exception as e:
                logger.exception(f"Error processing news item {news_item.title}: {e}")
                continue
        
        return messages
    
    def _get_cache_key(self, news_item: NewsItem, method: str, filter_criteria: Optional[str], recipient_id: str) -> str:
        """Generate cache key for processed news using hash-based optimization."""
        news_hash = news_item.get_hash()
        
        if method == 'keyword':
            filter_hash = generate_keywords_hash(filter_criteria or "")
        elif method == 'general':
            filter_hash = generate_premises_hash(filter_criteria or "")
        else:
            filter_hash = "flat"
        
        key_parts = [
            news_hash,
            method,
            filter_hash,
            recipient_id
        ]
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()
    
    def _get_premises_cache_key(self, news_item: NewsItem, premises: str) -> str:
        """Generate cache key for premises analysis."""
        news_hash = news_item.get_hash()
        premises_hash = generate_premises_hash(premises)
        return f"{news_hash}:{premises_hash}"
    
    def _get_keywords_cache_key(self, news_item: NewsItem, keywords: str) -> str:
        """Generate cache key for keyword matching."""
        news_hash = news_item.get_hash()
        keywords_hash = generate_keywords_hash(keywords)
        return f"{news_hash}:{keywords_hash}"
    
    async def _apply_method(self, news_item: NewsItem, method: str, filter_criteria: Optional[str]) -> str:
        """
        Apply the appropriate method to a news item.
        
        Args:
            news_item: The news item to process
            method: Processing method ('flat', 'keyword', 'general')
            filter_criteria: Keywords or premises for filtering
            
        Returns:
            Processed content or empty string if filtered out
        """
        if method == 'flat':
            return await self._process_flat(news_item)
        
        elif method == 'keyword':
            return await self._process_keyword(news_item, filter_criteria)
        
        elif method == 'general':
            return await self._process_general(news_item, filter_criteria)
        
        else:
            logger.warning(f"Unknown method: {method}")
            return ""
    
    async def _process_flat(self, news_item: NewsItem) -> str:
        """Process flat subscription - all news with AI opinion."""
        # TODO: Implement AI opinion generation
        title = news_item.title
        content = news_item.content[:500]  # Limit content length
        
        # Generate AI opinion (placeholder for now)
        ai_opinion = f"[AI Opinion on {news_item.category} news: This appears to be significant for market analysis.]"
        
        message = f"📰 **{title}**\n\n{content}\n\n🤖 {ai_opinion}\n\n🔗 [Read more]({news_item.link})"
        return message
    
    async def _process_keyword(self, news_item: NewsItem, keywords: str) -> str:
        """Process keyword subscription - filter by keywords with hash-based caching."""
        if not keywords:
            return ""
        
        # Check if we have cached keyword matching results
        cache_key = self._get_keywords_cache_key(news_item, keywords)
        if cache_key in self.keywords_cache:
            cached = self.keywords_cache[cache_key]
            if not cached.matched_keywords:
                return ""  # Filtered out (no matches)
            
            # Return filtered news with cached matches
            title = news_item.title
            content = news_item.content[:500]
            
            message = f"🔍 **Keyword Match: {', '.join(cached.matched_keywords)}**\n\n📰 **{title}**\n\n{content}\n\n🔗 [Read more]({news_item.link})"
            return message
        
        # Perform keyword matching
        keyword_list = [k.strip().lower() for k in keywords.split(',')]
        text_to_check = f"{news_item.title} {news_item.content}".lower()
        
        matched_keywords = [k for k in keyword_list if k in text_to_check]
        
        # Cache the result
        cache_entry = KeywordsCache(
            keywords_hash=generate_keywords_hash(keywords),
            news_hash=news_item.get_hash(),
            matched_keywords=matched_keywords,
            timestamp=datetime.now()
        )
        self.keywords_cache[cache_key] = cache_entry
        
        if not matched_keywords:
            return ""  # Filtered out
        
        # Return filtered news
        title = news_item.title
        content = news_item.content[:500]
        
        message = f"🔍 **Keyword Match: {', '.join(matched_keywords)}**\n\n📰 **{title}**\n\n{content}\n\n🔗 [Read more]({news_item.link})"
        return message
    
    async def _process_general(self, news_item: NewsItem, premises: str) -> str:
        """Process general subscription - AI analysis based on premises with hash-based caching."""
        # This function is deprecated - use news_watcher.py _analyze_critical_news_batch instead
        logger.warning("_process_general is deprecated. Use news_watcher.py implementation.")
        return ""
    
    def _cleanup_old_cache(self):
        """Remove old cache entries to prevent memory leaks."""
        now = datetime.now()
        cutoff_time = now - self.cache_duration
        
        # Clean news cache
        old_news_keys = [key for key, item in self.news_cache.items() 
                        if item.feed_id in self.feed_cache_time and 
                        self.feed_cache_time[f"feed_{item.feed_id}"] < cutoff_time]
        
        for key in old_news_keys:
            del self.news_cache[key]
        
        # Clean processing cache
        old_processing_keys = [key for key, cache in self.processing_cache.items() 
                              if cache.timestamp < cutoff_time]
        
        for key in old_processing_keys:
            del self.processing_cache[key]
        
        # Clean premises cache
        old_premises_keys = [key for key, cache in self.premises_cache.items() 
                            if cache.timestamp < cutoff_time]
        
        for key in old_premises_keys:
            del self.premises_cache[key]
        
        # Clean keywords cache
        old_keywords_keys = [key for key, cache in self.keywords_cache.items() 
                           if cache.timestamp < cutoff_time]
        
        for key in old_keywords_keys:
            del self.keywords_cache[key]
        
        # Clean feed cache timestamps
        old_feed_keys = [key for key, timestamp in self.feed_cache_time.items() 
                        if timestamp < cutoff_time]
        
        for key in old_feed_keys:
            del self.feed_cache_time[key]
        
        total_cleaned = len(old_news_keys) + len(old_processing_keys) + len(old_premises_keys) + len(old_keywords_keys) + len(old_feed_keys)
        if total_cleaned > 0:
            logger.info(f"Cleaned {len(old_news_keys)} news items, {len(old_processing_keys)} processing results, {len(old_premises_keys)} premises analyses, {len(old_keywords_keys)} keyword matches, {len(old_feed_keys)} feed timestamps from cache")
