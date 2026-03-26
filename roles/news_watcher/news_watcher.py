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
from dotenv import load_dotenv
from agent_db import get_active_server_name
from agent_logging import get_logger
from agent_engine import get_discord_token
from discord_bot.discord_http import DiscordHTTP
from discord_bot import discord_core_commands as core
_personality_descriptions = core._personality_descriptions

logger = get_logger('news_watcher')

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
        for user_id, category, feed_id, channel_id, fecha in channel_subscriptions:
            # Convert category to lowercase for database query
            category_normalized = category.lower()
            
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_unified(http, db_watcher, global_db, feed_data, f"channel_{channel_id}", channel_id, server_name, "flat")
            else:
                # NEW BEHAVIOR: Get only first available feed (highest priority) when feed_id is NULL
                feeds = db_watcher.get_active_feeds(category_normalized)
                if feeds:
                    # Take only the first feed (highest priority)
                    first_feed = feeds[0]
                    logger.info(f"📰 Processing first feed in {category} category for channel {channel_id}: {first_feed[1]} (id={first_feed[0]})")
                    await _process_feed_unified(http, db_watcher, global_db, first_feed, f"channel_{channel_id}", channel_id, server_name, "flat")
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
        for user_id, channel_id, keywords, category, feed_id in channel_subscriptions:
            # Convert category to lowercase for database query
            category_normalized = category.lower()
            
            if feed_id:
                # Specific feed - use absolute database ID
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_unified(http, db_watcher, global_db, feed_data, f"channel_{channel_id}", channel_id, server_name, "keyword", keywords)
                else:
                    logger.warning(f"Feed ID {feed_id} not found. Skipping keyword subscription.")
            else:
                # NEW BEHAVIOR: Get only first available feed (highest priority) when feed_id is NULL
                feeds = db_watcher.get_active_feeds(category_normalized)
                if feeds:
                    # Take only the first feed (highest priority)
                    first_feed = feeds[0]
                    logger.info(f"🔍 Processing first feed for keywords '{keywords}' in {category} category for channel {channel_id}: {first_feed[1]} (id={first_feed[0]})")
                    await _process_feed_unified(http, db_watcher, global_db, first_feed, f"channel_{channel_id}", channel_id, server_name, "keyword", keywords)
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
        for user_id, category, feed_id, channel_id, fecha in channel_subscriptions:
            # Get channel's premises for AI analysis
            channel_premises, context = db_watcher.get_channel_premises_with_context(channel_id)
            
            if not channel_premises:
                logger.info(f"🤖 Channel {channel_id} has no premises, skipping AI subscription")
                continue
                
            logger.info(f"🤖 Channel {channel_id} has {len(channel_premises)} premises, context: {context}")
            
            # Convert category to lowercase for database query
            category_normalized = category.lower()
            
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_unified(http, db_watcher, global_db, feed_data, f"channel_{channel_id}", channel_id, server_name, "general", channel_premises)
            else:
                # NEW BEHAVIOR: Get only first available feed (highest priority) when feed_id is NULL
                feeds = db_watcher.get_active_feeds(category_normalized)
                if feeds:
                    # Take only the first feed (highest priority)
                    first_feed = feeds[0]
                    logger.info(f"🤖 Processing first feed in {category} category for channel {channel_id} with {len(channel_premises)} premises: {first_feed[1]} (id={first_feed[0]})")
                    await _process_feed_unified(http, db_watcher, global_db, first_feed, f"channel_{channel_id}", channel_id, server_name, "general", channel_premises)
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
        
        # Mark as processed globally
        global_db.mark_news_globally_processed(title, link, name, server_name)
        
        logger.info(f"💭 Generating opinion for: {title[:50]}...")
        opinion = await _generate_personality_opinion(
            title,
            clean_summary,
            user_id,
            server_id=server_name,
        )
        rendered_opinion = opinion or "Watcher opinion unavailable"
        
        # Send notification
        message = f"📰 **{title}**\n\n{clean_summary[:500]}...\n\n💭 **Watcher Opinion:** {rendered_opinion}\n\n🔗 **Read more:** {link}"
        await _send_notification(http, user_id, channel_id, message)
        
        # Mark as sent in local database
        db_watcher.mark_notification_sent(title, "flat", rendered_opinion, link)


async def _process_feed_keyword_filter(http, feed, name, url, global_db, db_watcher, user_id, channel_id, server_name, keywords):
    """Process keyword subscription - filter by keywords then generate opinion."""
    keyword_list = [k.strip().lower() for k in keywords.split(',') if k.strip()]
    matched_items = 0
    
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
            # Mark as processed globally
            global_db.mark_news_globally_processed(title, link, name, server_name)
            logger.info(f"🔍 Keywords: Using _generate_personality_opinion() for: {title[:50]}...")
            opinion = await _generate_personality_opinion(
                title,
                clean_summary,
                user_id,
                server_id=server_name,
            )
            rendered_opinion = opinion or "Watcher opinion unavailable"
            
            # Send notification
            message = (
                f"🔍 **Keyword Match:** {title}\n\n{clean_summary[:500]}...\n\n"
                f"🎯 **Matched keywords:** {keywords}\n\n"
                f"💭 **Watcher Opinion:** {rendered_opinion}\n\n"
                f"🔗 **Read more:** {link}"
            )
            await _send_notification(http, user_id, channel_id, message)
            
            # Mark as sent in local database
            db_watcher.mark_notification_sent(title, "keyword", rendered_opinion, link)
            
            matched_items += 1
    
    logger.info(f"Found {matched_items} items matching keywords in {name}")


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
    
    # Process matching articles
    for idx in matching_indices:
        if idx < len(articles_to_analyze):
            article = articles_to_analyze[idx]
            title = article['title']
            summary = article['summary']  # Already cleaned from earlier step
            link = article['link']
            
            # Mark as processed globally
            global_db.mark_news_globally_processed(title, link, name, server_name)
            
            # Generate opinion for matching article
            logger.info(f"🤖 Generating opinion for critical article: {title[:50]}...")
            opinion = await _generate_personality_opinion(
                title,
                summary,
                user_id,
                server_id=server_name,
            )
            rendered_opinion = opinion or "Watcher opinion unavailable"
            
            # Send critical news alert
            watcher_alert_messages = _personality_descriptions.get("roles_view_messages", {}).get("news_watcher", {})
            alert_title = watcher_alert_messages.get("alert_title", "🤖 **Critical News Analysis**" )
            message = f"{alert_title}\n **{title}**\n\n:speech_left: {rendered_opinion}\n\n🔗 {link}"
            await _send_notification(http, user_id, channel_id, message)
            
            # Mark as sent in local database
            db_watcher.mark_notification_sent(title, "general", rendered_opinion, link)



#Note: This function should load that prompt from prompt.json and holding a neutral english fallback
def _build_news_watcher_prompt(
    system_prompt: str,
    title: str,
    description: str = "",
    prompt_config: dict | None = None,
) -> str:
    """Build the injected mission prompt for News Watcher opinions."""
    config = prompt_config or {}
    
    # Try to get golden_rules from personality, fallback to config or default
    try:
        from agent_engine import PERSONALITY
        role_prompts = PERSONALITY.get("role_system_prompts", {})
        personality_rules = role_prompts.get("roles", {}).get("watcher", {}).get("golden_rules", [])
        golden_rules = personality_rules if personality_rules else config.get("golden_rules")
    except Exception:
        golden_rules = config.get("golden_rules")
    
    # Fallback to English defaults if no rules found
    if not golden_rules:
        golden_rules = [
            "1. LENGHT: 2-4 sentences (100-250 characters).",
            "2. GRAMMAR: Don't finish a sentence with a free word like \"the\" \"of\" \"with\"",
            "3. EXPRESS YOURSELF as the character's personality would",
        ]
    title_label = role_prompts.get("watcher", {}).get("title_label", "Title")
    description_label = role_prompts.get("watcher", {}).get("description_label", "Description")
    opinion_request = role_prompts.get("watcher", {}).get("opinion_request", "What is your opinion about this situation?")


    description_text = description.strip() if description else ""
    description_text = description_text[:1000] if description_text else ""
    
    # Clean HTML from description using our optimized function
    if description_text:
        description_text = _sanitize_feed_description(description_text)
    golden_rules_title = role_prompts.get("watcher", {}).get("golden_rules_title", "## NEWS WATCHER GOLDEN RULES")
    prompt_sections = [
        golden_rules_title,
        *golden_rules,
        "",
        system_prompt,
    ]

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
) -> str | None:
    """Generate personality opinion about a news headline."""
    try:
        from agent_mind import call_llm
        from agent_db import get_active_server_name
        
        server_to_use = server_id or get_active_server_name()
        if not server_to_use:
            logger.warning("⚠️ No active server available for watcher prompt generation")
            return None
        
        # Get system prompt from personality or fallback to English
        try:
            from agent_engine import PERSONALITY
            role_prompts = PERSONALITY.get("role_system_prompts", {})
            system_prompt = role_prompts.get("roles", {}).get("watcher", {}).get("prompt", ROL_VIGIA_PERSONALITY)
            prompt_config = PERSONALITY.get("news_watcher_prompt", {})
        except Exception:
            system_prompt = ROL_VIGIA_PERSONALITY
            prompt_config = {}

        prompt = _build_news_watcher_prompt(
            system_prompt=system_prompt,
            title=title,
            description=description,
            prompt_config=prompt_config,
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

# Legacy helper kept for reference. Unused callers should prefer the newer pipeline.
async def get_latest_news(url: str, name_feed: str, limite: int = 5) -> list:
    """Get the latest news from an RSS feed (legacy path)."""
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

# Load environment variables // Legacy?
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



def _sanitize_summary_for_alert(summary: str) -> str:
    """Remove legacy analysis markers and trim whitespace for the alert body."""
    if not summary:
        return ""
    text = summary.strip()
    markers_to_remove = [
        "🤖 Critical News Analysis",
    ]
    for marker in markers_to_remove:
        text = text.replace(marker, "")
    analysis_marker = "🎯 Analysis:"
    marker_index = text.find(analysis_marker)
    if marker_index != -1:
        text = text[:marker_index]
    return text.strip()


def _format_critical_news_alert(title: str, summary: str, link: str, opinion: str) -> str:
    """Format the critical news alert using the new presentation layout."""
    try:
        alert_title = _get_alert_title()
        personality_name = _get_personality_name()
        separator = "────────────────────────────────────────────────────────────"

        cleaned_summary = _sanitize_summary_for_alert(summary)

        max_summary_length = 800
        if len(cleaned_summary) > max_summary_length:
            cleaned_summary = cleaned_summary[:max_summary_length].rsplit(' ', 1)[0] + "..."

        max_opinion_length = 400
        if len(opinion) > max_opinion_length:
            opinion = opinion[:max_opinion_length].rsplit(' ', 1)[0] + "..."

        message_parts = [
            f"**{alert_title}**",
            separator,
        ]

        if title:
            message_parts.append(f"📰 {title}")
        message_parts.append(separator)
        message_parts.append(f"💭 {personality_name}: {opinion}")
        message_parts.append(separator)

        message = "\n".join(part for part in message_parts if part)

        if len(message) > 1990:
            excess = len(message) - 1990
            if cleaned_summary and len(cleaned_summary) > excess + 10:
                cleaned_summary = cleaned_summary[:-(excess + 10)].rsplit(' ', 1)[0] + "..."
            else:
                opinion = opinion[:-(excess + 10)].rsplit(' ', 1)[0] + "..."

            message_parts = [
                f"**{alert_title}**",
                separator,
            ]
            if title:
                message_parts.append(f"📰 {title}")
            if cleaned_summary:
                message_parts.append(cleaned_summary)
            message_parts.append(separator)
            message_parts.append(f"💭 {personality_name}: {opinion}")
            message_parts.append(separator)
            message = "\n".join(part for part in message_parts if part)

        return message

    except Exception as e:
        logger.exception(f"Error formatting critical news alert: {e}")
        alert_title = _get_alert_title()
        personality_name = _get_personality_name()

        fallback_summary = _sanitize_summary_for_alert(summary)
        max_summary_length = 800
        if len(fallback_summary) > max_summary_length:
            fallback_summary = fallback_summary[:max_summary_length].rsplit(' ', 1)[0] + "..."

        max_opinion_length = 400
        if len(opinion) > max_opinion_length:
            opinion = opinion[:max_opinion_length].rsplit(' ', 1)[0] + "..."

        fallback_parts = [
            f"**{alert_title}**",
            separator,
        ]
        if title:
            fallback_parts.append(f"� {title}")
        if fallback_summary:
            fallback_parts.append(fallback_summary)
        fallback_parts.append(separator)
        fallback_parts.append(f"💭 {personality_name}: {opinion}")
        fallback_parts.append(separator)
        fallback_message = "\n".join(part for part in fallback_parts if part)

        if len(fallback_message) > 1990:
            excess = len(fallback_message) - 1990
            opinion = opinion[:-(excess + 10)].rsplit(' ', 1)[0] + "..."
            fallback_parts[-2] = f"💭 {personality_name}: {opinion}"
            fallback_message = "\n".join(part for part in fallback_parts if part)

        return fallback_message


def _get_alert_title() -> str:
    """Get alert title from descriptions.json or fallback."""
    try:
        from agent_engine import PERSONALITY
        descriptions = PERSONALITY.get("descriptions", {})
        watcher_messages = descriptions.get("watcher_messages", {})
        
        # Look for a title field in watcher messages
        if "critical_alert_title" in watcher_messages:
            return watcher_messages["critical_alert_title"]
        elif "canvas_personal_title" in watcher_messages:
            return watcher_messages["canvas_personal_title"]
        else:
            return "Watcher"  # Fallback
    except Exception:
        return "Watcher"  # Fallback


def _get_personality_name() -> str:
    """Get personality name from personality.json or fallback."""
    try:
        from agent_engine import PERSONALITY
        return PERSONALITY.get("bot_display_name", "Watcher")
    except Exception:
        return "Watcher"  # Fallback


async def _send_notification(http, user_id: str, channel_id: str, message: str):
    """Send notification to user (DM) or channel."""
    try:
        # Debug logs
        logger.info(f"🔍 _send_notification called:")
        logger.info(f"  - user_id: {user_id} (type: {type(user_id)})")
        logger.info(f"  - channel_id: {channel_id} (type: {type(channel_id)})")
        logger.info(f"  - channel_id is truthy: {bool(channel_id)}")
        logger.info(f"  - channel_id is not None: {channel_id is not None}")
        logger.info(f"  - channel_id is not empty: {channel_id != ''}")
        
        if channel_id:
            # Send to channel
            logger.info(f"📢 Sending to channel {channel_id}")
            await http.send_channel_message(channel_id, message)
        else:
            # Send to user DM
            logger.info(f"📩 Sending to DM for user {user_id}")
            await http.send_dm(user_id, message)
    except Exception as e:
        logger.exception(f"Error sending notification: {e}")


async def send_critical_news(http, user_id: str, channel_id: str, title: str, summary: str, link: str, opinion: str = None):
    """Send critical news notification with proper formatting."""
    try:
        # Clean the summary to remove any remaining HTML
        from news_processor import NewsProcessor
        from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
        db_watcher = get_news_watcher_db_instance()
        processor = NewsProcessor(db_watcher)
        clean_summary = processor._clean_html(summary)
        
        # Format the message
        rendered_opinion = opinion or "Watcher opinion unavailable"
        message = _format_critical_news_alert(title, clean_summary, link, rendered_opinion)
        
        # Send notification with link to generate Discord embed
        full_message = f"{message} {link}"
        await _send_notification(http, user_id, channel_id, full_message)
        
        # Mark as sent in local database
        db_watcher = get_news_watcher_db_instance()
        if db_watcher:
            db_watcher.mark_notification_sent(title, "ai", rendered_opinion, link)
        
        logger.info(f"✅ Critical news found and sent: {title[:50]}...")
        
    except Exception as e:
        logger.exception(f"Error sending critical news: {e}")


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
            from agent_db import get_active_server_name
            
            server_name = get_active_server_name()
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
                metadata=metadata
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
            from agent_db import get_active_server_name
            
            server_name = get_active_server_name()
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
                metadata=response_metadata
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
        server_name = get_active_server_name()
        if not server_name:
            logger.warning("⚠️ No active server configured, skipping News Watcher execution")
            return
        logger.info(f"📡 Server: {server_name}")
        
        # Initialize HTTP client for Discord
        discord_token = get_discord_token()
        if not discord_token:
            logger.error("❌ No Discord token configured (neither specific nor generic)")
            return
        
        http = DiscordHTTP(discord_token)
        
        # Process all subscriptions
        await process_subscriptions(http, server_name)
        
        logger.info("✅ News Watcher completed")
        
    except Exception as e:
        logger.exception(f"❌ Error in News Watcher main: {e}")


if __name__ == "__main__":
    asyncio.run(main())
