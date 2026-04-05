import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.dirname(__file__))

import asyncio
import html
import re
import feedparser
import aiohttp
import logging
import time
import datetime
import discord
from dotenv import load_dotenv
from agent_db import get_active_server_id
from agent_logging import get_logger
from agent_engine import get_discord_token
from discord_bot.discord_http import DiscordHTTP
from discord_bot import discord_core_commands as core

logger = get_logger('news_watcher')

# Load news_watcher descriptions directly
import json
import os
from pathlib import Path

def _load_news_watcher_descriptions():
    """Load news_watcher.json descriptions directly."""
    try:
        # Get personality name from configuration
        from agent_engine import PERSONALITY
        personality_name = PERSONALITY.get("name", "putre").lower()
        
        # Get personality directory
        personality_dir = Path(__file__).parent.parent.parent / "personalities" / personality_name / "descriptions"
        news_watcher_path = personality_dir / "news_watcher.json"
        
        if news_watcher_path.exists():
            with open(news_watcher_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            logger.warning(f"News watcher descriptions not found at {news_watcher_path}")
            return {}
    except Exception as e:
        logger.exception(f"Error loading news_watcher descriptions: {e}")
        return {}

_personality_descriptions = _load_news_watcher_descriptions()

# Personality prompt fallback legacy not normalized
ROL_VIGIA_PERSONALITY = (
    "You are the Tower Watcher, an ancient guardian who watches the world from above. "
    "Your character is wise, direct and sometimes a bit somber. "
    "When you give your opinion about news, be concise but impactful. "
    "Use language that reflects your watchful nature and your long experience observing world events."
)

def _sanitize_feed_description(raw_description: str) -> str:
    """Remove HTML/media noise from feed descriptions and return plain text."""
    if not raw_description:
        return ""

    # Handle truncated HTML by removing incomplete tags at the end
    if raw_description.endswith('<'):
        raw_description = raw_description[:-1]
    
    cleaned = re.sub(r'<img\b[^>]*>', ' ', raw_description, flags=re.IGNORECASE)
    cleaned = re.sub(r'<br\s*/?>', '\n', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'</p\s*>', '\n', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r'https?://\S+', ' ', cleaned)
    cleaned = re.sub(r'\s*\n\s*', '\n', cleaned)
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n{2,}', '\n', cleaned)
    
    # Remove any remaining isolated < characters
    cleaned = cleaned.replace(' <', ' ').replace('< ', ' ').replace('<', '').strip()
    
    return cleaned.strip()


class CohereRateLimiter:
    """Rate limiter for Cohere API calls (5 calls per minute for trial keys)."""
    
    def __init__(self, max_calls_per_minute: int = 5):
        self.max_calls = max_calls_per_minute
        self.calls = []
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self):
        """Wait if we've reached the rate limit."""
        async with self._lock:
            now = time.time()
            # Remove calls older than 1 minute
            self.calls = [call_time for call_time in self.calls if now - call_time < 60]
            
            if len(self.calls) >= self.max_calls:
                # Calculate wait time
                oldest_call = min(self.calls)
                wait_time = 60 - (now - oldest_call)
                if wait_time > 0:
                    logger.info(f"⏳ Rate limit reached, waiting {wait_time:.1f} seconds...")
                    await asyncio.sleep(wait_time)
                    # Clean up old calls after waiting
                    now = time.time()
                    self.calls = [call_time for call_time in self.calls if now - call_time < 60]
            
            # Record this call
            self.calls.append(now)


# Global rate limiter instance
cohere_limiter = CohereRateLimiter()


async def process_subscriptions(http, server_name: str = "default"):
    """Process all subscription types using the correct logic."""
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
    from roles.news_watcher.global_news_db import get_global_news_db

    db_watcher = get_news_watcher_db_instance(server_name)
    global_db = get_global_news_db()
    
    try:
        logger.info("🚀 Starting subscription processing...")
        
        # 1. Process flat subscriptions (all news with opinion) - includes channels
        await process_flat_subscriptions(http, db_watcher, global_db, server_name)
        
        # 2. Process keyword subscriptions (regex) - includes channels
        await process_keyword_subscriptions(http, db_watcher, global_db, server_name)
        
        # 3. Process AI subscriptions (premise detection) - includes channels
        await process_ai_subscriptions(http, db_watcher, global_db, server_name)
        
        logger.info("✅ Subscription processing completed")
        
    except Exception as e:
        logger.exception(f"❌ General error in subscription processing: {e}")


async def process_flat_subscriptions(http, db_watcher, global_db, server_name: str):
    """Process flat subscriptions for both channels and users."""
    try:
        logger.info("📰 Processing flat subscriptions...")
        
        # Get user flat subscriptions
        user_subscriptions = db_watcher.get_all_active_subscriptions()
        
        # Get channel flat subscriptions
        channel_subscriptions = db_watcher.get_all_channel_subscriptions_flat()
        
        # Process user subscriptions
        for user_id, category, feed_id, fecha in user_subscriptions:
            # Convert category to lowercase for database query
            category_normalized = category.lower()
            
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_unified(http, db_watcher, global_db, feed_data, user_id, None, server_name, "flat")
            else:
                # NEW BEHAVIOR: Get only first available feed (highest priority) when feed_id is NULL
                feeds = db_watcher.get_active_feeds(category_normalized)
                if feeds:
                    # Take only the first feed (highest priority)
                    first_feed = feeds[0]
                    logger.info(f"📰 Processing first feed in {category} category for user {user_id}: {first_feed[1]} (id={first_feed[0]})")
                    await _process_feed_unified(http, db_watcher, global_db, first_feed, user_id, None, server_name, "flat")
                else:
                    logger.warning(f"📰 No feeds found for category '{category}' (normalized: '{category_normalized}')")
        
        # Process channel subscriptions
        for channel_id, category, feed_id in channel_subscriptions:
            # Convert category to lowercase for database query
            category_normalized = category.lower()
            
            # Use channel_id as user_id prefix for channel subscriptions
            prefixed_user_id = f"channel_{channel_id}"
            
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_unified(http, db_watcher, global_db, feed_data, prefixed_user_id, channel_id, server_name, "flat")
            else:
                # NEW BEHAVIOR: Get only first available feed (highest priority) when feed_id is NULL
                feeds = db_watcher.get_active_feeds(category_normalized)
                if feeds:
                    # Take only the first feed (highest priority)
                    first_feed = feeds[0]
                    logger.info(f"📰 Processing first feed in {category} category for channel {channel_id}: {first_feed[1]} (id={first_feed[0]})")
                    await _process_feed_unified(http, db_watcher, global_db, first_feed, prefixed_user_id, channel_id, server_name, "flat")
                else:
                    logger.warning(f"📰 No feeds found for category '{category}' (normalized: '{category_normalized}')")
                    
    except Exception as e:
        logger.exception(f"❌ Error processing flat subscriptions: {e}")


async def process_keyword_subscriptions(http, db_watcher, global_db, server_name: str):
    """Process keyword subscriptions for both channels and users."""
    try:
        logger.info("🔍 Processing keyword subscriptions...")
        
        # Get user keyword subscriptions
        user_subscriptions = db_watcher.get_all_active_keyword_subscriptions()
        
        # Get channel keyword subscriptions
        channel_subscriptions = db_watcher.get_all_channel_subscriptions_keywords()
        
        # Process user subscriptions
        for user_id, channel_id, keywords, category, feed_id in user_subscriptions:
            # Convert category to lowercase for database query
            category_normalized = category.lower()
            
            if feed_id:
                # Specific feed - use absolute database ID
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_unified(http, db_watcher, global_db, feed_data, user_id, channel_id, server_name, "keyword", keywords)
                else:
                    logger.warning(f"Feed ID {feed_id} not found. Skipping keyword subscription.")
            else:
                # NEW BEHAVIOR: Get only first available feed (highest priority) when feed_id is NULL
                feeds = db_watcher.get_active_feeds(category_normalized)
                if feeds:
                    # Take only the first feed (highest priority)
                    first_feed = feeds[0]
                    logger.info(f"🔍 Processing first feed for keywords '{keywords}' in {category} category for user {user_id}: {first_feed[1]} (id={first_feed[0]})")
                    await _process_feed_unified(http, db_watcher, global_db, first_feed, user_id, channel_id, server_name, "keyword", keywords)
                else:
                    logger.warning(f"🔍 No feeds found for category '{category}' (normalized: '{category_normalized}')")
        
        # Process channel subscriptions
        for channel_id, category, feed_id, keywords, user_id in channel_subscriptions:
            # Convert category to lowercase for database query
            category_normalized = category.lower()
            
            if feed_id:
                # Specific feed - use absolute database ID
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_unified(http, db_watcher, global_db, feed_data, user_id, channel_id, server_name, "keyword", keywords)
                else:
                    logger.warning(f"Feed ID {feed_id} not found. Skipping keyword subscription.")
            else:
                # NEW BEHAVIOR: Get only first available feed (highest priority) when feed_id is NULL
                feeds = db_watcher.get_active_feeds(category_normalized)
                if feeds:
                    # Take only the first feed (highest priority)
                    first_feed = feeds[0]
                    logger.info(f"🔍 Processing first feed for keywords '{keywords}' in {category} category for channel {channel_id} (created by user {user_id}): {first_feed[1]} (id={first_feed[0]})")
                    await _process_feed_unified(http, db_watcher, global_db, first_feed, user_id, channel_id, server_name, "keyword", keywords)
                else:
                    logger.warning(f"🔍 No feeds found for category '{category}' (normalized: '{category_normalized}')")
                    
    except Exception as e:
        logger.exception(f"❌ Error processing keyword subscriptions: {e}")


async def process_ai_subscriptions(http, db_watcher, global_db, server_name: str):
    """Process AI subscriptions for both channels and users."""
    try:
        logger.info("🤖 Processing AI subscriptions...")
        
        # Get user AI subscriptions
        user_subscriptions = db_watcher.get_all_active_category_subscriptions()
        
        # Get channel AI subscriptions
        channel_subscriptions = db_watcher.get_all_channel_subscriptions_ai()
        
        # Process user subscriptions
        for user_id, category, feed_id, fecha in user_subscriptions:
            # Get user's premises for AI analysis
            user_premises, context = db_watcher.get_premises_with_context(user_id)
            
            if not user_premises:
                logger.info(f"🤖 User {user_id} has no premises, skipping AI subscription")
                continue
                
            logger.info(f"🤖 User {user_id} has {len(user_premises)} premises, context: {context}")
            
            # Convert category to lowercase for database query
            category_normalized = category.lower()
            
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_unified(http, db_watcher, global_db, feed_data, user_id, None, server_name, "general", user_premises)
            else:
                # NEW BEHAVIOR: Get only first available feed (highest priority) when feed_id is NULL
                feeds = db_watcher.get_active_feeds(category_normalized)
                if feeds:
                    # Take only the first feed (highest priority)
                    first_feed = feeds[0]
                    logger.info(f"🤖 Processing first feed in {category} category for user {user_id} with {len(user_premises)} premises: {first_feed[1]} (id={first_feed[0]})")
                    await _process_feed_unified(http, db_watcher, global_db, first_feed, user_id, None, server_name, "general", user_premises)
                else:
                    logger.warning(f"🤖 No feeds found for category '{category}' (normalized: '{category_normalized}')")
        
        # Process channel subscriptions
        for channel_id, category, feed_id, premises, user_id in channel_subscriptions:
            # Channel premises are already provided as comma-separated string
            if premises:
                channel_premises = [p.strip() for p in premises.split(',') if p.strip()]
                logger.info(f"🤖 Channel {channel_id} has {len(channel_premises)} premises from subscription (created by user {user_id})")
            else:
                logger.info(f"🤖 Channel {channel_id} has no premises, skipping AI subscription")
                continue
            
            # Convert category to lowercase for database query
            category_normalized = category.lower()
            
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_unified(http, db_watcher, global_db, feed_data, user_id, channel_id, server_name, "general", channel_premises)
            else:
                # NEW BEHAVIOR: Get only first available feed (highest priority) when feed_id is NULL
                feeds = db_watcher.get_active_feeds(category_normalized)
                if feeds:
                    # Take only the first feed (highest priority)
                    first_feed = feeds[0]
                    logger.info(f"🤖 Processing first feed in {category} category for channel {channel_id} (created by user {user_id}) with {len(channel_premises)} premises: {first_feed[1]} (id={first_feed[0]})")
                    await _process_feed_unified(http, db_watcher, global_db, first_feed, user_id, channel_id, server_name, "general", channel_premises)
                else:
                    logger.warning(f"🤖 No feeds found for category '{category}' (normalized: '{category_normalized}')")
                    
    except Exception as e:
        logger.exception(f"❌ Error processing AI subscriptions: {e}")

async def _process_feed_unified(http, db_watcher, global_db, feed_record, user_id, channel_id, server_name: str, method: str = "flat", filter_criteria: str = None):
    """Unified feed processor for flat, keyword, and AI subscriptions."""
    try:
        feed_id, name, url, category = feed_record[0], feed_record[1], feed_record[2], feed_record[3]
        method_emoji = {"flat": "📰", "keyword": "🔍", "general": "🤖"}.get(method, "📰")
        logger.info(f"{method_emoji} Processing {method} feed: {name} (category={category}, id={feed_id})")

        feed_unique_key = f"feed:{feed_id}:{category or 'unknown'}"

        # Check if already processed recently
        if db_watcher.is_news_read(feed_unique_key):
            logger.debug(f"Feed {name} ({category}) already processed recently")
            return

        # Mark as read to avoid duplicate processing
        db_watcher.mark_news_as_read(feed_unique_key, url)

        # Fetch and process news items
        headers = {"User-Agent": "RoleAgentBot/1.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    raw_data = await response.text()
                    feed = feedparser.parse(raw_data)
                    
                    # Handle different processing methods
                    if method == "general" and filter_criteria:
                        # AI method: batch analysis with Cohere
                        await _process_feed_ai_batch(http, feed, name, url, global_db, db_watcher, user_id, channel_id, server_name, filter_criteria)
                    elif method == "keyword" and filter_criteria:
                        # Keyword method: filter by keywords then generate opinion
                        await _process_feed_keyword_filter(http, feed, name, url, global_db, db_watcher, user_id, channel_id, server_name, filter_criteria)
                    else:
                        # Flat method: all news with opinion
                        await _process_feed_flat_opinion(http, feed, name, url, global_db, db_watcher, user_id, channel_id, server_name)
                        
                else:
                    logger.warning(f"Failed to fetch feed {name}: HTTP {response.status}")
                    
    except Exception as e:
        logger.exception(f"Error processing {method} feed {name}: {e}")


async def _process_feed_flat_opinion(http, feed, name, url, global_db, db_watcher, user_id, channel_id, server_name):
    """Process flat subscription - all news with opinion."""
    pending_articles = []
    for entry in feed.entries[:20]:
        title = entry.get('title', 'No title')
        link = entry.get('link', '')
        summary = entry.get('summary', entry.get('description', ''))

        clean_summary = _sanitize_feed_description(summary)

        if global_db.is_news_globally_processed(title):
            logger.debug(f"News already processed globally: {title[:50]}...")
            continue

        global_db.mark_news_globally_processed(title, link, name, server_name)
        pending_articles.append({
            "title": title,
            "summary": clean_summary,
            "link": link,
        })

    if not pending_articles:
        return

    logger.info(f"💭 Generating shared opinion for {len(pending_articles)} flat articles...")
    opinion = await _generate_personality_opinion(
        pending_articles[0]["title"],
        pending_articles[0]["summary"],
        user_id,
        server_id=server_name,
        news_items=pending_articles,
    )
    rendered_opinion = opinion or "Watcher opinion unavailable"

    message = _build_watcher_notification_message("flat", pending_articles, rendered_opinion, user_id)
    await _send_notification(http, user_id, channel_id, message)

    for article in pending_articles:
        db_watcher.mark_notification_sent(article["title"], "flat", rendered_opinion, article["link"])


async def _process_feed_keyword_filter(http, feed, name, url, global_db, db_watcher, user_id, channel_id, server_name, keywords):
    """Process keyword subscription - filter by keywords then generate opinion."""
    keyword_list = [k.strip().lower() for k in keywords.split(',') if k.strip()]
    matched_articles = []
    
    for entry in feed.entries[:20]:  # Limit to 20 latest items
        title = entry.get('title', 'No title')
        link = entry.get('link', '')
        summary = entry.get('summary', entry.get('description', ''))
        
        # Clean HTML from summary
        clean_summary = _sanitize_feed_description(summary)
        
        # Check if news was already processed globally
        if global_db.is_news_globally_processed(title):
            logger.debug(f"News already processed globally: {title[:50]}...")
            continue
        
        # Check if any keywords match
        content_to_check = f"{title} {clean_summary}".lower()
        if any(keyword.lower() in content_to_check for keyword in keyword_list):
            global_db.mark_news_globally_processed(title, link, name, server_name)
            matched_articles.append({
                "title": title,
                "summary": clean_summary,
                "link": link,
            })

    if matched_articles:
        logger.info(f"🔍 Keywords: Generating shared opinion for {len(matched_articles)} matched articles...")
        opinion = await _generate_personality_opinion(
            matched_articles[0]["title"],
            matched_articles[0]["summary"],
            user_id,
            server_id=server_name,
            news_items=matched_articles,
        )
        rendered_opinion = opinion or "Watcher opinion unavailable"

        message = _build_watcher_notification_message(
            "keyword",
            matched_articles,
            rendered_opinion,
            user_id,
            keywords=keywords,
        )
        await _send_notification(http, user_id, channel_id, message)

        for article in matched_articles:
            db_watcher.mark_notification_sent(article["title"], "keyword", rendered_opinion, article["link"])
    
    logger.info(f"Found {len(matched_articles)} items matching keywords in {name}")


async def _process_feed_ai_batch(http, feed, name, url, global_db, db_watcher, user_id, channel_id, server_name, premises):
    """Process AI subscription - batch analysis with Cohere."""
    # Collect all articles for batch analysis
    articles_to_analyze = []
    for entry in feed.entries[:20]:  # Limit to 20 latest items
        title = entry.get('title', 'No title')
        link = entry.get('link', '')
        summary = entry.get('summary', entry.get('description', ''))
        
        # Clean HTML from summary
        clean_summary = _sanitize_feed_description(summary)
        
        # Skip if already processed globally
        if global_db.is_news_globally_processed(title):
            logger.debug(f"News already processed globally: {title[:50]}...")
            continue
        
        articles_to_analyze.append({
            'title': title,
            'summary': clean_summary,
            'link': link
        })
    
    if not articles_to_analyze:
        logger.info(f"No new articles to analyze in {name}")
        return
    
    logger.info(f"🤖 Analyzing {len(articles_to_analyze)} articles in batch...")
    
    # Batch analysis: check all articles at once against premises
    matching_indices = await _analyze_critical_news_batch(articles_to_analyze, premises)
    
    logger.info(f"🤖 Batch analysis found {len(matching_indices)} matching articles")
    
    matched_articles = []
    for idx in matching_indices:
        if idx < len(articles_to_analyze):
            article = articles_to_analyze[idx]
            title = article['title']
            summary = article['summary']  # Already cleaned from earlier step
            link = article['link']
            
            global_db.mark_news_globally_processed(title, link, name, server_name)
            matched_articles.append({
                "title": title,
                "summary": summary,
                "link": link,
            })

    if not matched_articles:
        return

    logger.info(f"🤖 Generating shared opinion for {len(matched_articles)} critical articles...")
    opinion = await _generate_personality_opinion(
        matched_articles[0]["title"],
        matched_articles[0]["summary"],
        user_id,
        server_id=server_name,
        news_items=matched_articles,
    )
    rendered_opinion = opinion or "Watcher opinion unavailable"

    message = _build_watcher_notification_message("general", matched_articles, rendered_opinion, user_id, channel_id, premises=premises)
    await _send_notification(http, user_id, channel_id, message)

    for article in matched_articles:
        db_watcher.mark_notification_sent(article["title"], "general", rendered_opinion, article["link"])


def _build_watcher_notification_message(method: str, articles: list[dict], rendered_opinion: str, user_id: str, channel_id: str = None, keywords: str | None = None, premises: str | None = None) -> tuple[str, str, str | None]:
    """Build watcher notification message split into two parts with single quote.
    
    Returns:
        tuple: (first_message, second_message, news_data)
        - first_message: Contains title, opinion, and premises
        - second_message: Contains news details and links (fallback)
        - news_data: Tuple with (articles, method, keywords) for components
    """
    if not articles:
        first_message = f"💭 {rendered_opinion}"
        second_message = ""
        news_data = (articles, method, keywords)
        return first_message, second_message, news_data

    # Get premises for the analysis (only for general method)
    premises_info = ""
    if method == "general" and premises:
        # Use premises passed directly as parameter (handle both list and string)
        # Handle both list and string formats
        if isinstance(premises, list):
            premise_list = [str(p).strip() for p in premises if str(p).strip()]
        else:
            premise_list = [p.strip() for p in premises.split(',') if p.strip()]
            
        for i, premise in enumerate(premise_list[:7], start=1):  # Limit to first 7 premises
            premises_info += f"{i}. {premise}\n"
        premises_info += "\n"    
    
    # Get alert title
    alert_title = ""
    alert_title = _personality_descriptions.get("alert_title", "🤖 **Critical News Analysis**")
    from discord_bot.canvas.content import _bot_display_name
    alert_title = alert_title.replace("{_bot_display_name}", _bot_display_name)


    # Build first message with title, premises, and opinion
    separator = "-" * 150
    if method == "general":
        first_message = f"{alert_title}\n{premises_info}💭 {rendered_opinion}\n{separator}"
    elif method == "keyword":
        first_message = f"{alert_title}\n{keywords}\n\n💭 {rendered_opinion}\n{separator}"
    else:
        first_message = f"{alert_title}\n\n💭 {rendered_opinion}\n{separator}"

    # Build second message with news details and links (fallback)
    article_lines = []
    
    # Limit number of articles to prevent exceeding Discord's 2000 character limit
    max_articles = 20 if len(articles) > 20 else len(articles)
    
    for index, article in enumerate(articles[:max_articles], start=1):
        article_lines.append(f"**{article['title']}**")
        if article["summary"]:
            # Reduce summary length for multiple articles
            summary_len = 150 if len(articles) > 3 else 300
            article_lines.append(f"{article['summary'][:summary_len]}...")
        article_lines.append(f"🔗 {article['link']}")
        # Add spacing between articles
        if index < len(articles[:max_articles]):
            article_lines.append("")
    
    # Add note if articles were truncated
    if len(articles) > max_articles:
        article_lines.append(f"... and {len(articles) - max_articles} more articles")
    
    second_message = "\n".join(article_lines)
    
    # Return articles data for components
    news_data = (articles, method, keywords)
    
    # Final safety check - if still too long, truncate further
    if len(second_message) > 1980:  # Leave some margin
        # Keep only titles and links for very long messages
        short_lines = []
        for index, article in enumerate(articles[:3], start=1):
            short_lines.append(f"**{article['title']}**")
            short_lines.append(f"🔗 {article['link']}")
            if index < 3:
                short_lines.append("")
        short_lines.append(f"... and {len(articles) - 3} more critical articles")
        second_message = "\n".join(short_lines)
    
    return first_message, second_message, news_data



#Note: This function should load that prompt from prompt.json and holding a neutral english fallback
def _build_news_watcher_prompt(
    system_prompt: str,
    title: str,
    description: str = "",
    prompt_config: dict | None = None,
    news_items: list[dict] | None = None,
) -> str:
    """Build the injected mission prompt for News Watcher opinions."""
    config = prompt_config or {}
    role_prompts = {}
    
    # Try to get golden_rules from personality, fallback to config or default
    try:
        from agent_engine import PERSONALITY
        role_prompts = PERSONALITY.get("roles", {})
        personality_rules = role_prompts.get("news_watcher", {}).get("golden_rules", [])
        golden_rules = personality_rules if personality_rules else config.get("golden_rules")
    except Exception:
        golden_rules = config.get("golden_rules")
    
    # Fallback to English defaults if no rules found
    if not golden_rules:
        golden_rules = [
            "1. LENGHT: 2-8 sentences (100-500 characters).",
            "2. GRAMMAR: Don't finish a sentence with a free word like \"the\" \"of\" \"with\"",
            "3. EXPRESS YOURSELF as the character's personality would",
        ]
    watcher_prompt_config = role_prompts.get("news_watcher", {})
    title_label = watcher_prompt_config.get("title_label", "Title")
    description_label = watcher_prompt_config.get("description_label", "Description")
    opinion_request = watcher_prompt_config.get("opinion_request", "What is your opinion about this situation?")
    bulletin_label = watcher_prompt_config.get("bulletin_label", "News bulletin")
    bulletin_item_label = watcher_prompt_config.get("bulletin_item_label", "News item")
    bulletin_request = watcher_prompt_config.get(
        "bulletin_request",
        "If there is more than one news item, respond as a short bulletin that groups them into one cohesive commentary.",
    )


    description_text = description.strip() if description else ""
    description_text = description_text[:1000] if description_text else ""
    
    # Clean HTML from description using our optimized function
    if description_text:
        description_text = _sanitize_feed_description(description_text)
    golden_rules_title = watcher_prompt_config.get("golden_rules_title", "## NEWS WATCHER GOLDEN RULES")
    prompt_sections = [
        golden_rules_title,
        *golden_rules,
        "",
        system_prompt,
    ]

    if news_items and len(news_items) > 1:
        prompt_sections.extend([
            f"\n{bulletin_label}:",
        ])
        for index, item in enumerate(news_items, start=1):
            item_summary = (item.get("summary") or "").strip()[:1000]
            if item_summary:
                item_summary = _sanitize_feed_description(item_summary)
            prompt_sections.extend([
                f'{bulletin_item_label} {index} {title_label} "{item.get("title", "No title")}"',
                f'{bulletin_item_label} {index} {description_label} "{item_summary}"',
                "",
            ])
        prompt_sections.append(bulletin_request)
    else:
        prompt_sections.extend([
            f'\n{title_label}: "{title}"',
            f'{description_label}: "{description_text}"',
            opinion_request,
        ])

    return "\n".join(prompt_sections)


async def _generate_personality_opinion(
    title: str,
    description: str,
    user_id: str,
    server_id: str = None,
    news_items: list[dict] | None = None,
) -> str | None:
    """Generate personality opinion about a news headline."""
    try:
        from agent_mind import call_llm
        from agent_db import get_active_server_id
        
        server_to_use = server_id or get_active_server_id()
        if not server_to_use:
            logger.warning("⚠️ No active server available for watcher prompt generation")
            return None
        
        # Get system prompt from personality or fallback to English
        try:
            from agent_engine import PERSONALITY
            role_prompts = PERSONALITY.get("roles", {})
            system_prompt = role_prompts.get("news_watcher", {}).get("prompt", ROL_VIGIA_PERSONALITY)
            prompt_config = role_prompts.get("news_watcher", {})
        except Exception:
            system_prompt = ROL_VIGIA_PERSONALITY
            prompt_config = {}

        prompt = _build_news_watcher_prompt(
            system_prompt=system_prompt,
            title=title,
            description=description,
            prompt_config=prompt_config,
            news_items=news_items,
        )
        
        # Get personality opinion
        # Build system instruction
        from agent_engine import _build_system_prompt
        system_instruction = _build_system_prompt(PERSONALITY)
        
        opinion = call_llm(
            system_instruction=system_instruction,
            prompt=prompt,
            async_mode=False,
            call_type="news_watcher",
            critical=True,
            metadata={
                "interaction_type": "mission",
                "role_context": "news_watcher",
                "server": server_to_use
            }
        )
        
        if opinion and len(opinion.strip()) > 0:
            logger.info(f"💭 Opinion generated: {opinion[:50]}...")
            return opinion.strip()
        else:
            logger.warning("⚠️ Could not generate personality opinion")
            return None
            
    except Exception as e:
        logger.exception(f"Error generating personality opinion: {e}")
        return None


def check_keywords_regex(title: str, keywords: str) -> bool:
    """Check if a news headline matches keywords using regex."""
    try:
        title_lower = title.lower()
        keywords_list = [p.strip().lower() for p in keywords.split(',')]
        
        # Create regex pattern for each keyword
        for keyword in keywords_list:
            # Escape special characters and create pattern that matches the complete word
            pattern = re.escape(keyword)
            if re.search(rf'\b{pattern}\b', title_lower):
                return True
        
        return False
    except Exception as e:
        logger.exception(f"Error checking keywords with regex: {e}")
        return False

# Helper function for RSS feed retrieval - maintained for compatibility
async def get_latest_news(url: str, name_feed: str, limite: int = 5) -> list:
    """Get the latest news from an RSS feed."""
    try:
        headers = {"User-Agent": "RoleAgentBot/1.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.warning(f"⚠️ Feed {name_feed} responded with status {response.status}")
                    return []
                
                content = await response.text()
                root = feedparser.parse(content)
                entries = root.entries[:limite]
                
                # Extract both title and description
                news_data = []
                for entry in entries:
                    if entry.title:
                        title = entry.title
                        # Get description or summary, fallback to empty string
                        description = ""
                        if hasattr(entry, 'description') and entry.description:
                            description = entry.description
                        elif hasattr(entry, 'summary') and entry.summary:
                            description = entry.summary
                        
                        description = _sanitize_feed_description(description)
                        
                        # Get the article link if available
                        link = ""
                        if hasattr(entry, 'link') and entry.link:
                            link = entry.link
                        
                        news_data.append({
                            'title': title,
                            'description': description,
                            'link': link
                        })
                
                logger.info(f"📰 {len(news_data)} news from {name_feed}")
                return news_data
    except Exception as e:
        logger.exception(f"❌ Could not get feed {name_feed}: {e}")
        return []

# Load environment variables from multiple possible locations
_env_candidates = [
    (os.getenv("ROLE_AGENT_ENV_FILE") or "").strip(),
    os.path.expanduser("~/.roleagentbot.env"),
    os.path.join(os.path.dirname(__file__), ".env"),
]

for _p in _env_candidates:
    if _p and os.path.exists(_p):
        load_dotenv(_p, override=False)
        break

logger = get_logger('watcher')



def _get_alert_title() -> str:
    """Get alert title from descriptions.json or fallback."""
    try:
        from agent_engine import PERSONALITY, _bot_display_name
        descriptions = PERSONALITY.get("discord", {})
        
        # Try to get from news_watcher descriptions first
        news_watcher_descriptions = descriptions.get("roles_view_messages", {}).get("news_watcher", {})
        alert_title = news_watcher_descriptions.get("alert_title")
        
        if alert_title:
            # Apply placeholder replacement for bot display name
            return alert_title.replace("{_bot_display_name}", _bot_display_name)
        
        # Fallback to watcher messages
        watcher_messages = descriptions.get("watcher_messages", {})
        
        # Look for a title field in watcher messages
        if "critical_alert_title" in watcher_messages:
            return watcher_messages["critical_alert_title"]
        elif "canvas_personal_title" in watcher_messages:
            return watcher_messages["canvas_personal_title"]
        else:
            return f"🤖 {_bot_display_name} Watcher"  # Fallback with bot name
    except Exception:
        return "🤖 Watcher"  # Fallback


def _get_personality_name() -> str:
    """Get personality name from personality.json or fallback."""
    try:
        from agent_engine import PERSONALITY
        return PERSONALITY.get("bot_display_name", "Watcher")
    except Exception:
        return "Watcher"  # Fallback


def _build_news_embed(article: dict, color: int = 0x3498db) -> dict:
    """Build a Discord embed for a news article.
    
    Args:
        article: Dict with 'title', 'summary', 'link' keys
        color: Embed color (default blue)
        
    Returns:
        Discord embed dict
    """
    embed = {
        "title": article.get('title', 'No title'),
        "description": article.get('summary', '')[:400] + '...' if len(article.get('summary', '')) > 400 else article.get('summary', ''),
        "url": article.get('link', ''),
        "color": color,
        "footer": {
            "text": "🐺 RoleAgentBot News Watcher"
        }
    }
    
    # Try to extract image from article if available
    # Note: This would require additional processing to extract images from the article content
    # For now, Discord will automatically fetch the Open Graph image from the URL
    
    return embed




def _build_news_components(articles: list[dict], method: str = "general", keywords: str = None) -> list:
    """Build Discord components (buttons) for news articles.
    
    Args:
        articles: List of dicts with 'title', 'summary', 'link' keys
        method: News method ('general', 'keyword', 'flat') - affects title formatting
        keywords: Matched keywords (for keyword method)
        
    Returns:
        List of Discord components or empty list if no articles
    """
    if not articles:
        return []
    
    # Limit number of articles for buttons (Discord max is 25 buttons, 5 per row)
    max_articles = min(len(articles), 25)
    
    # Create button components manually in Discord API format
    buttons = []
    for i, article in enumerate(articles[:max_articles], start=1):
        article_title = article.get('title', 'No title')
        if len(article_title) > 80:  # Discord button label limit
            article_title = article_title[:77] + "..."
        
        button = {
            "type": 2,  # Button component type
            "label": f"{i}. {article_title}",
            "style": 5,  # Link button style
            "url": article.get('link', ''),
            "disabled": False
        }
        buttons.append(button)
    
    # Group buttons into rows (max 5 buttons per row)
    rows = []
    for i in range(0, len(buttons), 5):
        row_buttons = buttons[i:i+5]
        action_row = {
            "type": 1,  # Action Row component type
            "components": row_buttons
        }
        rows.append(action_row)
    
    return rows

async def _send_notification(http, user_id: str, channel_id: str, messages: str | tuple[str, str] | tuple[str, str, str]):
    """Send notification to user (DM) or channel.
    
    Args:
        messages: Can be:
            - Single message string
            - Tuple of (first_message, second_message) 
            - Tuple of (first_message, second_message, news_quote)
    """
    try:
        # Only handle tuple with news data for components
        if isinstance(messages, tuple) and len(messages) == 3:
            first_message, second_message, news_data = messages
            logger.info(f"📨 Sending message with news content")
            
            # Send first message (title and opinion)
            if channel_id:
                logger.info(f"📢 Sending first message to channel {channel_id}")
                await http.send_channel_message(channel_id, first_message)
            else:
                logger.info(f"📩 Sending first message to DM for user {user_id}")
                await http.send_dm(user_id, first_message)
            
            # Wait a moment between messages for better UX
            await asyncio.sleep(0.5)
            
            # Check if news_data is a tuple with (articles, method, keywords) for components
            if isinstance(news_data, tuple) and len(news_data) == 3:
                articles, method, keywords = news_data
                logger.info(f"🎨 Building button components for {len(articles)} articles")
                
                # Build components
                components = _build_news_components(articles, method, keywords)
                
                if components:
                    # Send message with components
                    from discord_bot.canvas.content import _bot_display_name
                    buttons_title = _personality_descriptions.get("news_buttons_title", "📰 **Click on any article to open it:**")
                    
                    if channel_id:
                        logger.info(f"📢 Sending buttons to channel {channel_id}")
                        await http.send_channel_message(channel_id, buttons_title, components=components)
                    else:
                        logger.info(f"📩 Sending buttons to DM for user {user_id}")
                        await http.send_dm(user_id, buttons_title, components=components)
                else:
                    # Fallback if components failed
                    fallback_msg = _personality_descriptions.get("news_components_unavailable", "📰 **News components unavailable**\n\nPlease try again later.")
                    if channel_id:
                        logger.info(f"📢 Sending fallback message to channel {channel_id}")
                        await http.send_channel_message(channel_id, fallback_msg)
                    else:
                        logger.info(f"📩 Sending fallback message to DM for user {user_id}")
                        await http.send_dm(user_id, fallback_msg)
            else:
                logger.warning("� Invalid news_data format, expected (articles, method, keywords)")
        else:
            logger.warning(f"� Unsupported message format: {type(messages)} - Expected tuple with 3 elements")
                
    except Exception as e:
        logger.exception(f"Error sending notification: {e}")


async def send_critical_news(http, user_id: str, channel_id: str, title: str, summary: str, link: str, opinion: str = None):
    """Send critical news notification with proper formatting using split messages."""
    try:
        # Clean the summary to remove any remaining HTML
        from news_processor import NewsProcessor
        from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
        db_watcher = get_news_watcher_db_instance()
        processor = NewsProcessor(db_watcher)
        clean_summary = processor._clean_html(summary)
        
        # Get alert title and personality name
        alert_title = _get_alert_title()
        personality_name = _get_personality_name()
        
        # Format the opinion
        rendered_opinion = opinion or "Watcher opinion unavailable"
        
        # Build first message (title and opinion)
        first_message = f"**{alert_title}**\n\n💭 {personality_name}: {rendered_opinion}"
        
        # Build second message (details and links)
        second_message_parts = []
        
        if title:
            second_message_parts.append(f"📰 **{title}**")
        
        if clean_summary:
            # Limit summary length
            max_summary_length = 800
            if len(clean_summary) > max_summary_length:
                clean_summary = clean_summary[:max_summary_length].rsplit(' ', 1)[0] + "..."
            second_message_parts.append(clean_summary)
        
        # Add the link
        second_message_parts.append(f"🔗 {link}")
        
        second_message = "\n\n".join(second_message_parts)
        
        # Send as split messages
        await _send_notification(http, user_id, channel_id, (first_message, second_message))
        
        # Mark as sent in local database
        db_watcher = get_news_watcher_db_instance()
        if db_watcher:
            db_watcher.mark_notification_sent(title, "ai", rendered_opinion, link)
        
        logger.info(f"✅ Critical news found and sent: {title[:50]}...")
        
    except Exception as e:
        logger.exception(f"Error sending critical news: {e}")


async def send_multiple_critical_news(http, user_id: str, channel_id: str, articles: list[dict], opinion: str = None):
    """Send multiple critical news notifications with proper formatting using split messages and components.
    
    Args:
        articles: List of dicts with 'title', 'summary', 'link' keys
        opinion: Shared opinion for all articles
    """
    try:
        if not articles:
            logger.info("📝 No articles to send in send_multiple_critical_news")
            return
        
        # Get alert title and personality name
        alert_title = _get_alert_title()
        personality_name = _get_personality_name()
        
        # Format the opinion
        rendered_opinion = opinion or "Watcher opinion unavailable"
        
        # Build first message (title and opinion)
        if len(articles) == 1:
            first_message = f"**{alert_title}**\n\n💭 {personality_name}: {rendered_opinion}"
        else:
            first_message = f"**{alert_title}** ({len(articles)} news)\n\n💭 {personality_name}: {rendered_opinion}"
        
        # Return articles data for components
        news_data = (articles, "general", None)
        
        # Limit number of articles to prevent exceeding Discord's 2000 character limit
        max_articles = 12 if len(articles) > 12 else len(articles)
        
        for index, article in enumerate(articles[:max_articles], start=1):
            # Clean summary
            from news_processor import NewsProcessor
            from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
            db_watcher = get_news_watcher_db_instance()
            processor = NewsProcessor(db_watcher)
            clean_summary = processor._clean_html(article.get('summary', ''))
            
            # Add article title
            second_message_parts.append(f"📰 **{article['title']}**")
            
            # Add summary if available
            if clean_summary:
                # Limit summary length
                max_summary_length = 300 if len(articles) > 2 else 500
                if len(clean_summary) > max_summary_length:
                    clean_summary = clean_summary[:max_summary_length].rsplit(' ', 1)[0] + "..."
                second_message_parts.append(clean_summary)
            
            # Add link
            second_message_parts.append(f"🔗 {article['link']}")
            
            # Add spacing between articles (except last one)
            if index < len(articles[:max_articles]):
                second_message_parts.append("")
        
        # Add note if articles were truncated
        if len(articles) > max_articles:
            second_message_parts.append(f"... and {len(articles) - max_articles} more news")
        
        second_message = "\n".join(second_message_parts)
        
        # Send as split messages with news data for components
        await _send_notification(http, user_id, channel_id, (first_message, second_message, news_data))
        
        # Mark all as sent in local database
        db_watcher = get_news_watcher_db_instance()
        if db_watcher:
            for article in articles:
                db_watcher.mark_notification_sent(article['title'], "ai", rendered_opinion, article['link'])
        
        logger.info(f"✅ {len(articles)} critical news sent with single quote")
        
    except Exception as e:
        logger.exception(f"Error sending multiple critical news: {e}")


async def _analyze_critical_news_batch(articles: list, premises: list) -> list:
    """Analyze multiple news articles at once against user premises.
    
    Args:
        articles: List of dicts with 'title', 'summary', 'link' keys
        premises: List of user premises
        
    Returns:
        List of indices (0-based) of articles that match premises
    """
    try:
        await cohere_limiter.wait_if_needed()
        
        import cohere
        api_key = (os.getenv("COHERE_API_KEY") or "").strip()
        if not api_key:
            logger.warning("⚠️ COHERE_API_KEY is not configured for batch critical news analysis")
            return []
        
        client = cohere.Client(api_key=api_key, timeout=60)  # Longer timeout for batch
        
        premises_text = "\n".join([f"{i}. {premise}" for i, premise in enumerate(premises, 1)])
        
        # Build articles text for batch analysis
        articles_text = ""
        for i, article in enumerate(articles):
            articles_text += f"\n{i}. Title: \"{article['title']}\"\n"
            articles_text += f"   Description: \"{article['summary'][:300]}\"\n"
        
        # Normalized prompt for logging
        system_instruction = "You are a critical news analyzer. Your task is to identify which news articles strongly match user-defined premises and should be considered critical for notification."
        
        user_prompt = f"""USER PREMISES:
{premises_text}

NEWS ARTICLES TO ANALYZE:
{articles_text}

CRITICAL: Only select articles that STRONGLY match the premises above.
An article is critical only if it directly relates to the user's specific interests.

For each article above, respond with the index number ONLY if it strongly matches ANY premise.
Be very selective - most articles should NOT be considered critical.

Respond only with comma-separated numbers (e.g., "0,2,5") or "NONE" if no articles match."""
        
        # Log the prompt to prompts.log
        try:
            from prompts_logger import log_final_llm_prompt
            from agent_db import get_active_server_id
            
            server_name = get_active_server_id()
            metadata = {
                "articles_count": len(articles),
                "premises_count": len(premises),
                "analysis_type": "batch_critical_news"
            }
            
            log_final_llm_prompt(
                provider="cohere",
                call_type="news_watcher_batch_analysis",
                system_instruction=system_instruction,
                user_prompt=user_prompt,
                role="news_watcher",
                server=server_name,
                metadata=metadata,
                server_id=server_name
            )
        except Exception as e:
            logger.warning(f"Could not log prompt to prompts.log: {e}")
        
        # Send to Cohere
        response = client.chat(
            model="command-a-03-2025",
            message=user_prompt,
            temperature=0.0,
            max_tokens=50,  # Allow for multiple indices
        )
        
        result = (getattr(response, "text", "") or "").strip()
        logger.info(f"🤖 Batch critical analysis result: {result}")
        
        # Log Cohere's response to prompts.log
        try:
            from prompts_logger import log_prompt
            from agent_db import get_active_server_id
            
            server_name = get_active_server_id()
            response_metadata = {
                "provider": "cohere",
                "call_type": "news_watcher_batch_analysis_response",
                "role": "news_watcher",
                "server": server_name,
                "model": "command-a-03-2025",
                "temperature": 0.0,
                "max_tokens": 50,
                "response_length": len(result),
                "parsed_indices": str(result)
            }
            
            log_prompt(
                prompt_type="cohere_response",
                content=result,
                metadata=response_metadata,
                server_id=server_name
            )
        except Exception as e:
            logger.warning(f"Could not log Cohere response to prompts.log: {e}")
        
        if result.upper() == "NONE":
            return []
        
        # Parse comma-separated indices
        try:
            indices = []
            for idx_str in result.split(','):
                idx = int(idx_str.strip())
                if 0 <= idx < len(articles):
                    indices.append(idx)
            return indices
        except ValueError:
            logger.warning(f"Failed to parse batch analysis result: {result}")
            return []
            
    except Exception as e:
        logger.exception(f"Error in batch critical news analysis: {e}")
        return []


async def main():
    """Main function of the News Watcher."""
    try:
        logger.info("🚀 Starting News Watcher...")
        
        # Get server configuration
        server_id = get_active_server_id()
        if not server_id:
            logger.warning("⚠️ No active server configured, skipping News Watcher execution")
            return
        logger.info(f"📡 Server: {server_id}")
        
        # Initialize HTTP client for Discord
        discord_token = get_discord_token()
        if not discord_token:
            logger.error("❌ No Discord token configured (neither specific nor generic)")
            return
        
        http = DiscordHTTP(discord_token)
        
        # Process all subscriptions
        await process_subscriptions(http, server_id)
        
        logger.info("✅ News Watcher completed")
        
    except Exception as e:
        logger.exception(f"❌ Error in News Watcher main: {e}")


if __name__ == "__main__":
    asyncio.run(main())
