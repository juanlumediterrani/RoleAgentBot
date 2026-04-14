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
from agent_db import get_server_id
from agent_logging import get_logger
from agent_engine import get_discord_token
from discord_bot.discord_http import DiscordHTTP
from discord_bot import discord_core_commands as core

logger = get_logger('news_watcher')

# Load news_watcher descriptions directly
import json
import os
from pathlib import Path

def _load_news_watcher_descriptions(server_id: str = None) -> dict:
    """Load news_watcher.json descriptions directly."""
    try:
        # Get personality name from configuration
        from agent_engine import PERSONALITY
        personality_name = PERSONALITY.get("name", "putre").lower()
        
        # Get personality directory (server-specific)
        from agent_runtime import get_personality_directory
        personality_dir = get_personality_directory()
        
        # Try to load from the new separate news_watcher.json file
        news_watcher_path = os.path.join(personality_dir, "descriptions", "news_watcher.json")
        if os.path.exists(news_watcher_path):
            with open(news_watcher_path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.exception(f"Error loading news_watcher descriptions: {e}")
        return {}

# Dynamic news_watcher descriptions with server-specific cache
_news_watcher_descriptions_cache = {}
_news_watcher_descriptions_cache_server_id = None

def _get_news_watcher_descriptions(server_id: str = None) -> dict:
    """
    Get news_watcher descriptions with server-specific caching.
    
    This function dynamically loads descriptions based on the active server,
    caching the result to avoid repeated file reads for the same server.
    """
    global _news_watcher_descriptions_cache, _news_watcher_descriptions_cache_server_id
    
    try:
        from agent_db import get_server_id
        current_server_id = server_id or get_server_id()
    except:
        current_server_id = server_id or None
    
    # Check if we need to reload (different server or no cache)
    if current_server_id != _news_watcher_descriptions_cache_server_id or not _news_watcher_descriptions_cache:
        _news_watcher_descriptions_cache = _load_news_watcher_descriptions(current_server_id)
        _news_watcher_descriptions_cache_server_id = current_server_id
        if os.getenv('ROLE_AGENT_PROCESS') != '1':
            logger.info(f"📰 [NEWS_WATCHER DESCRIPTIONS] Loaded for server: {current_server_id}")
    
    return _news_watcher_descriptions_cache


# Create dynamic _personality_descriptions proxy for news_watcher
class _NewsWatcherDescriptionsProxy:
    """Proxy for dynamic news_watcher descriptions loading with server-specific support."""
    def _get_server_id(self):
        """Get current server ID for server-specific loading."""
        try:
            from agent_db import get_server_id
            return get_server_id()
        except:
            return None
    
    def __getitem__(self, key):
        return _get_news_watcher_descriptions(self._get_server_id()).get(key)
    
    def get(self, key, default=None):
        return _get_news_watcher_descriptions(self._get_server_id()).get(key, default)
    
    def __contains__(self, key):
        return key in _get_news_watcher_descriptions(self._get_server_id())
    
    def keys(self):
        return _get_news_watcher_descriptions(self._get_server_id()).keys()
    
    def values(self):
        return _get_news_watcher_descriptions(self._get_server_id()).values()
    
    def items(self):
        return _get_news_watcher_descriptions(self._get_server_id()).items()
    
    def __repr__(self):
        return repr(_get_news_watcher_descriptions(self._get_server_id()))

_personality_descriptions = _NewsWatcherDescriptionsProxy()

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


async def process_subscriptions(http, server_name: str = "default", include_channels: bool = True):
    """Process all subscriptions (or only personal if include_channels=False)."""
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
    from roles.news_watcher.global_news_db import get_global_news_db

    db_watcher = get_news_watcher_db_instance(server_name)
    global_db = get_global_news_db()
    
    try:
        scope = "all" if include_channels else "personal"
        logger.info(f"Starting {scope} subscription processing...")
        
        # Get subscriptions based on scope
        if include_channels:
            # Get all subscriptions (user + channel)
            subscriptions = db_watcher.get_all_active_subscriptions()
        else:
            # Get only user subscriptions (no channels)
            subscriptions = []
            for user_id in db_watcher.get_users_with_active_subscriptions():
                user_subs = db_watcher.get_user_subscriptions(user_id)
                for sub in user_subs:
                    # sub[2] is channel_id - skip if not None
                    if sub[2] is None:
                        subscriptions.append(sub)
        
        logger.info(f"Processing {len(subscriptions)} subscriptions...")
        
        # Process each subscription
        for subscription_id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by in subscriptions:
            category_normalized = category.lower()
            
            # Get server_id from channel_id if available
            subscription_server_id = None
            if channel_id:
                try:
                    channel_info = await http.get_channel(int(channel_id))
                    if channel_info:
                        subscription_server_id = str(channel_info.get('guild_id'))
                        logger.debug(f"Got server_id {subscription_server_id} from channel {channel_id}")
                except Exception as e:
                    logger.warning(f"Failed to get server_id from channel {channel_id}: {e}")
            
            if method == "flat":
                if feed_id:
                    feed_data = db_watcher.get_feed_by_id(feed_id)
                    if feed_data:
                        await _process_feed_unified(http, db_watcher, global_db, feed_data, user_id, channel_id, server_name, "flat", server_id=subscription_server_id)
                else:
                    feeds = db_watcher.get_active_feeds(category_normalized)
                    if feeds:
                        await _process_feed_unified(http, db_watcher, global_db, feeds[0], user_id, channel_id, server_name, "flat", server_id=subscription_server_id)
                    else:
                        logger.warning(f"No feeds found for category '{category}'")
                        
            elif method == "keyword":
                if not keywords:
                    continue
                if feed_id:
                    feed_data = db_watcher.get_feed_by_id(feed_id)
                    if feed_data:
                        await _process_feed_unified(http, db_watcher, global_db, feed_data, user_id, channel_id, server_name, "keyword", keywords, subscription_server_id)
                else:
                    feeds = db_watcher.get_active_feeds(category_normalized)
                    if feeds:
                        target = f"channel {channel_id}" if channel_id else f"user {user_id}"
                        logger.info(f"Processing keywords '{keywords}' for {target} in {category}")
                        await _process_feed_unified(http, db_watcher, global_db, feeds[0], user_id, channel_id, server_name, "keyword", keywords, subscription_server_id)
                    else:
                        logger.warning(f"No feeds found for category '{category}'")
                        
            elif method == "general":
                if not premises:
                    continue
                if feed_id:
                    feed_data = db_watcher.get_feed_by_id(feed_id)
                    if feed_data:
                        await _process_feed_unified(http, db_watcher, global_db, feed_data, user_id, channel_id, server_name, "general", premises, subscription_server_id)
                else:
                    feeds = db_watcher.get_active_feeds(category_normalized)
                    if feeds:
                        await _process_feed_unified(http, db_watcher, global_db, feeds[0], user_id, channel_id, server_name, "general", premises, subscription_server_id)
                    else:
                        logger.warning(f"No feeds found for category '{category}'")
        
        logger.info(f"{scope.capitalize()} subscription processing completed")
        
    except Exception as e:
        logger.exception(f"Error in {scope} subscription processing: {e}")


async def _process_feed_unified(http, db_watcher, global_db, feed_record, user_id, channel_id, server_name: str, method: str = "flat", filter_criteria: str = None, server_id=None):
    """Unified feed processor for flat, keyword, and AI subscriptions."""
    try:
        feed_id, name, url, category = feed_record[0], feed_record[1], feed_record[2], feed_record[3]
        method_emoji = {"flat": "📰", "keyword": "🔍", "general": "🤖"}.get(method, "📰")
        logger.info(f"{method_emoji} Processing {method} feed: {name} (category={category}, id={feed_id})")

        feed_unique_key = f"feed:{feed_id}:{category or 'unknown'}"

        # Check if feed was processed recently (using timestamp-based cooldown)
        # Don't use news title tracking for feed processing cooldown
        # if db_watcher.is_news_read(feed_unique_key):
        #     logger.debug(f"Feed {name} ({category}) already processed recently")
        #     return

        # Note: Feed cooldown tracking should be separate from news title tracking
        # For now, we process feeds every time and rely on global news tracking
        # to prevent duplicate news processing
        
        logger.info(f"📡 About to fetch feed from URL: {url}")

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
                        await _process_feed_ai_batch(http, feed, name, url, global_db, db_watcher, user_id, channel_id, server_name, filter_criteria, server_id)
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
    # Handle both string and list inputs for keywords
    if isinstance(keywords, list):
        keyword_list = [str(k).strip().lower() for k in keywords if k and str(k).strip()]
    elif isinstance(keywords, str):
        keyword_list = [k.strip().lower() for k in keywords.split(',') if k.strip()]
    else:
        logger.warning(f"Invalid keywords type: {type(keywords)} for user {user_id}")
        return
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


async def _process_feed_ai_batch(http, feed, name, url, global_db, db_watcher, user_id, channel_id, server_name, premises, server_id=None):
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
    matching_indices = await _analyze_critical_news_batch(articles_to_analyze, premises, server_id)
    
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
    
    # Get alert title from server-specific personality
    from agent_db import get_server_id
    current_server_id = get_server_id()
    alert_title = _get_alert_title(current_server_id)


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
    server_id: str = None,
) -> str:
    """Build the injected mission prompt for News Watcher opinions."""
    config = prompt_config or {}
    role_prompts = {}
    
    # Try to get golden_rules from server-specific personality, fallback to config or default
    try:
        from agent_engine import _get_personality
        personality = _get_personality(server_id) if server_id else None
        if not personality:
            from agent_engine import PERSONALITY
            personality = PERSONALITY
        role_prompts = personality.get("roles", {})
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
        from agent_db import get_server_id
        
        server_to_use = server_id or get_server_id()
        if not server_to_use:
            logger.warning("⚠️ No active server available for watcher prompt generation")
            return None
        
        # Get server-specific personality for all configuration
        from agent_engine import _get_personality
        server_personality = _get_personality(server_to_use) if server_to_use else None
        if not server_personality:
            from agent_engine import PERSONALITY
            server_personality = PERSONALITY
        
        # Get system prompt from server-specific personality or fallback to English
        try:
            role_prompts = server_personality.get("roles", {})
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
            server_id=server_to_use,
        )
        
        # Build system instruction using server-specific personality
        from agent_engine import _build_system_prompt
        system_instruction = _build_system_prompt(server_personality, server_to_use)
        
        opinion = call_llm(
            system_instruction=system_instruction,
            prompt=prompt,
            async_mode=True,
            call_type="news_watcher",
            critical=False,
            server_id=server_to_use,
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
        # Handle both string and list inputs for keywords
        if isinstance(keywords, list):
            keywords_list = [str(p).strip().lower() for p in keywords if p and str(p).strip()]
        elif isinstance(keywords, str):
            keywords_list = [p.strip().lower() for p in keywords.split(',')]
        else:
            logger.warning(f"Invalid keywords type: {type(keywords)} in headline matching")
            return False
        
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

def _get_alert_title(server_id: str = None) -> str:
    """Get alert title from news_watcher.json descriptions or fallback using server-specific personality."""
    try:
        # Use the same loading mechanism as _personality_descriptions proxy
        news_watcher_descriptions = _get_news_watcher_descriptions(server_id)
        
        # Get alert_title from the loaded news_watcher descriptions
        alert_title = news_watcher_descriptions.get("alert_title")
        
        if alert_title:
            return alert_title
        
        # Fallback to legacy personality structure
        from agent_engine import _get_personality
        personality = _get_personality(server_id) if server_id else None
        if not personality:
            from agent_engine import PERSONALITY
            personality = PERSONALITY
        descriptions = personality.get("discord", {})
        
        # Try legacy watcher messages
        watcher_messages = descriptions.get("watcher_messages", {})
        
        # Look for a title field in watcher messages
        if "critical_alert_title" in watcher_messages:
            return watcher_messages["critical_alert_title"]
        elif "canvas_personal_title" in watcher_messages:
            return watcher_messages["canvas_personal_title"]
        else:
            return "🤖 Watcher"  # Fallback
    except Exception:
        return "🤖 Watcher"  # Fallback


def _get_personality_name(server_id: str = None) -> str:
    """Get personality name from personality.json or fallback using server-specific personality."""
    try:
        from agent_engine import _get_personality
        personality = _get_personality(server_id) if server_id else None
        if not personality:
            from agent_engine import PERSONALITY
            personality = PERSONALITY
        return personality.get("bot_display_name", "Watcher")
    except Exception:
        return "Watcher"  # Fallback


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
        # Account for prefix "N. " (up to 4 chars for numbers 1-25) in the 80 char limit
        prefix_len = len(f"{i}. ")
        max_title_len = 80 - prefix_len
        if len(article_title) > max_title_len:
            article_title = article_title[:max_title_len - 3] + "..."
        
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
                # Truncate to 2000 characters (Discord limit)
                truncated_message = first_message[:2000] if len(first_message) > 2000 else first_message
                await http.send_channel_message(channel_id, truncated_message)
            else:
                logger.info(f"📩 Sending first message to DM for user {user_id}")
                # Truncate to 2000 characters (Discord limit)
                truncated_message = first_message[:2000] if len(first_message) > 2000 else first_message
                await http.send_dm(int(user_id), truncated_message)
            
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
                    buttons_title = _personality_descriptions.get("news_buttons_title", "📰 **Click on any article to open it:**")
                    
                    if channel_id:
                        logger.info(f"📢 Sending buttons to channel {channel_id}")
                        success = await http.send_channel_message(channel_id, buttons_title, components=components)
                    else:
                        logger.info(f"📩 Sending buttons to DM for user {user_id}")
                        success = await http.send_dm(int(user_id), buttons_title, components=components)
                    
                    # If buttons failed (e.g. Discord API error), fall back to plain text
                    if not success and second_message:
                        logger.warning("⚠️ Button send failed, falling back to plain text links")
                        if channel_id:
                            await http.send_channel_message(channel_id, second_message)
                        else:
                            await http.send_dm(int(user_id), second_message)
                else:
                    # No components built - send plain text article list as fallback
                    if second_message:
                        if channel_id:
                            logger.info(f"📢 Sending plain text links to channel {channel_id}")
                            await http.send_channel_message(channel_id, second_message)
                        else:
                            logger.info(f"📩 Sending plain text links to DM for user {user_id}")
                            await http.send_dm(int(user_id), second_message)
            else:
                logger.warning("� Invalid news_data format, expected (articles, method, keywords)")
        else:
            logger.warning(f"� Unsupported message format: {type(messages)} - Expected tuple with 3 elements")
                
    except Exception as e:
        logger.exception(f"Error sending notification: {e}")

async def _analyze_critical_news_batch(articles: list, premises: list | str, server_id: str = None) -> list:
    """Analyze multiple news articles at once against user premises.
    
    Args:
        articles: List of dicts with 'title', 'summary', 'link' keys
        premises: List of user premises (or comma-separated string)
        server_id: Server ID for logging
        
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
        
        # Convert premises to list if it's a string (comma-separated from DB)
        if isinstance(premises, str):
            premises_list = [p.strip() for p in premises.split(',') if p.strip()]
        elif isinstance(premises, list):
            premises_list = [str(p).strip() for p in premises if p and str(p).strip()]
        else:
            logger.warning(f"Invalid premises type: {type(premises)}")
            return []
        
        if not premises_list:
            logger.warning("No valid premises to analyze")
            return []
        
        premises_text = "\n".join([f"{i}. {premise}" for i, premise in enumerate(premises_list, 1)])
        
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
            from agent_db import get_server_id
            
            # Use provided server_id or fall back to get_server_id()
            log_server_id = server_id or get_server_id()
            metadata = {
                "articles_count": len(articles),
                "premises_count": len(premises_list),
                "analysis_type": "batch_critical_news"
            }
            
            log_final_llm_prompt(
                provider="cohere",
                call_type="news_watcher_batch_analysis",
                system_instruction=system_instruction,
                user_prompt=user_prompt,
                role="news_watcher",
                server=log_server_id,
                metadata=metadata,
                server_id=log_server_id
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
            from agent_db import get_server_id
            
            # Use provided server_id or fall back to get_server_id()
            log_server_id = server_id or get_server_id()
            response_metadata = {
                "provider": "cohere",
                "call_type": "news_watcher_batch_analysis_response",
                "role": "news_watcher",
                "server": log_server_id,
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
                server_id=log_server_id
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
        current_server_id = get_server_id()
        if not current_server_id:
            logger.warning("⚠️ No active server configured, skipping News Watcher execution")
            return
        logger.info(f"📡 Server: {current_server_id}")
        
        # Initialize HTTP client for Discord
        discord_token = get_discord_token()
        if not discord_token:
            logger.error("❌ No Discord token configured (neither specific nor generic)")
            return
        
        http = DiscordHTTP(discord_token)
        
        # Process all subscriptions
        await process_subscriptions(http, current_server_id)
        
        logger.info("✅ News Watcher completed")
        
    except Exception as e:
        logger.exception(f"❌ Error in News Watcher main: {e}")


if __name__ == "__main__":
    asyncio.run(main())
