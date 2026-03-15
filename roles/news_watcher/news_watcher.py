import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.dirname(__file__))

import asyncio
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

logger = get_logger('news_watcher')


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
        
        # 1. Process flat subscriptions (all news with opinion)
        await process_flat_subscriptions(http, db_watcher, global_db, server_name)
        
        # 2. Process keyword subscriptions (regex)
        await process_keyword_subscriptions(http, db_watcher, global_db, server_name)
        
        # 3. Process AI subscriptions (premise detection)
        await process_ai_subscriptions(http, db_watcher, global_db, server_name)
        
        # 4. Process channel subscriptions (admin-configured)
        await process_channel_subscriptions(http, db_watcher, global_db, server_name)
        
        logger.info("✅ Subscription processing completed")
        
    except Exception as e:
        logger.exception(f"❌ General error in subscription processing: {e}")


async def process_flat_subscriptions(http, db_watcher, global_db, server_name: str):
    """Process flat subscriptions (sends all news with opinion)."""
    try:
        logger.info("📰 Processing flat subscriptions...")
        
        subscriptions = db_watcher.get_all_active_subscriptions()
        
        for user_id, categoria, feed_id, fecha in subscriptions:
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_flat_subscription(http, db_watcher, global_db, (feed_data[2], feed_data[1]), user_id, None, server_name)
            else:
                # All feeds in category
                feeds = db_watcher.get_active_feeds(categoria)
                for feed in feeds:
                    await _process_feed_flat_subscription(http, db_watcher, global_db, (feed[2], feed[1]), user_id, None, server_name)
                    
    except Exception as e:
        logger.exception(f"❌ Error processing flat subscriptions: {e}")


async def process_keyword_subscriptions(http, db_watcher, global_db, server_name: str):
    """Process keyword subscriptions (regex)."""
    try:
        logger.info("🔍 Processing keyword subscriptions...")
        
        subscriptions_palabras = db_watcher.get_all_active_keyword_subscriptions()
        
        for user_id, channel_id, keywords, category, feed_id in subscriptions_palabras:
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_keyword_subscription(http, db_watcher, global_db, (feed_data[2], feed_data[1]), user_id, channel_id, keywords, server_name)
            else:
                # All feeds in category
                feeds = db_watcher.get_active_feeds(category)
                for feed in feeds:
                    await _process_feed_keyword_subscription(http, db_watcher, global_db, (feed[2], feed[1]), user_id, channel_id, keywords, server_name)
                    
    except Exception as e:
        logger.exception(f"❌ Error processing keyword subscriptions: {e}")


async def process_ai_subscriptions(http, db_watcher, global_db, server_name: str):
    """Process AI subscriptions (premise detection)."""
    try:
        logger.info("🤖 Processing AI subscriptions...")
        
        subscriptions_ia = db_watcher.get_all_active_category_subscriptions()
        
        for user_id, categoria, feed_id, fecha in subscriptions_ia:
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_ai_subscription(http, db_watcher, global_db, (feed_data[2], feed_data[1]), user_id, None, server_name)
            else:
                # All feeds in category
                feeds = db_watcher.get_active_feeds(categoria)
                for feed in feeds:
                    await _process_feed_ai_subscription(http, db_watcher, global_db, (feed[2], feed[1]), user_id, None, server_name)
                    
    except Exception as e:
        logger.exception(f"❌ Error processing AI subscriptions: {e}")


async def process_channel_subscriptions(http, db_watcher, global_db, server_name: str):
    """Process channel subscriptions (admin-configured)."""
    try:
        logger.info("📢 Processing channel subscriptions...")
        
        # Get all unique channels with active subscriptions
        channels_unique = db_watcher.get_all_channels_with_subscriptions()
        
        for channel_id, canal_name, servidor_id in channels_unique:
            logger.info(f"📢 Processing channel: {canal_name} ({channel_id})")
            
            # Get channel subscriptions
            subscriptions_channel = db_watcher.get_channel_subscriptions(channel_id)
            
            for category, feed_id, date in subscriptions_channel:
                # Check if channel has AI premises
                channel_premises = db_watcher.get_channel_premises(channel_id)
                
                if feed_id:
                    # Specific feed
                    feed_data = db_watcher.get_feed_by_id(feed_id)
                    if feed_data:
                        if channel_premises:
                            await _process_feed_ai_subscription(http, db_watcher, global_db, (feed_data[2], feed_data[1]), f"channel_{channel_id}", channel_premises, servidor_id)
                        else:
                            await _process_feed_flat_subscription(http, db_watcher, global_db, (feed_data[2], feed_data[1]), f"channel_{channel_id}", channel_id, server_name)
                else:
                    # All feeds in category
                    feeds = db_watcher.get_active_feeds(category)
                    for feed in feeds:
                        if channel_premises:
                            await _process_feed_ai_subscription(http, db_watcher, global_db, (feed[2], feed[1]), f"channel_{channel_id}", channel_premises, servidor_id)
                        else:
                            await _process_feed_flat_subscription(http, db_watcher, global_db, (feed[2], feed[1]), f"channel_{channel_id}", channel_id, server_name)
                    
    except Exception as e:
        logger.exception(f"❌ Error processing channel subscriptions: {e}")


async def _process_feed_flat_subscription(http, db_watcher, global_db, feed_data, user_id, channel_id, server_name: str = None):
    """Process a feed for flat subscriptions (sends all news with opinion)."""
    try:
        url, name = feed_data
        logger.info(f"📰 Processing flat feed: {name}")
        
        # Check if already processed recently
        if db_watcher.is_news_read(name):
            logger.debug(f"Feed {name} already processed recently")
            return
        
        # Mark as read to avoid duplicate processing
        db_watcher.mark_news_as_read(name, url)
        
        # Fetch and process news items
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    raw_data = await response.text()
                    feed = feedparser.parse(raw_data)
                    
                    for entry in feed.entries[:10]:  # Limit to 10 latest items
                        title = entry.get('title', 'No title')
                        link = entry.get('link', '')
                        summary = entry.get('summary', entry.get('description', ''))
                        
                        # Check if news was already processed globally
                        if global_db.is_news_globally_processed(title):
                            logger.debug(f"News already processed globally: {title[:50]}...")
                            continue
                        
                        # Mark as processed globally
                        global_db.mark_news_globally_processed(title, link, name, server_name)
                        
                        logger.info(f"💭 Generating opinion for: {title[:50]}...")
                        opinion = await _generate_personality_opinion(
                            title,
                            summary,
                            user_id,
                            server_id=server_name,
                        )
                        rendered_opinion = opinion or "Watcher opinion unavailable"
                        
                        # Send notification
                        message = f"📰 **{title}**\n\n{summary[:300]}...\n\n💭 **Watcher Opinion:** {rendered_opinion}"
                        await _send_notification(http, user_id, channel_id, message)
                        
                        # Mark as sent in local database
                        db_watcher.mark_notification_sent(title, "flat", rendered_opinion, link)
                        
                        # Small delay between processing each news item
                        await asyncio.sleep(1)
                        
                else:
                    logger.warning(f"Failed to fetch feed {name}: HTTP {response.status}")
                    
    except Exception as e:
        logger.exception(f"Error processing flat feed {name}: {e}")


async def _process_feed_keyword_subscription(http, db_watcher, global_db, feed_data, user_id, channel_id, keywords, server_name: str = None):
    """Process a feed for keyword subscriptions (regex)."""
    try:
        url, name = feed_data
        logger.info(f"🔍 Processing keyword feed: {name} for keywords: {keywords}")
        
        # Check if already processed recently
        if db_watcher.is_news_read(name):
            logger.debug(f"Feed {name} already processed recently")
            return
        
        # Mark as read to avoid duplicate processing
        db_watcher.mark_news_as_read(name, url)
        
        # Fetch and process news items
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    raw_data = await response.text()
                    feed = feedparser.parse(raw_data)
                    
                    keyword_list = [k.strip() for k in keywords.split(',')]
                    matched_items = 0
                    
                    for entry in feed.entries[:10]:  # Limit to 10 latest items
                        title = entry.get('title', 'No title')
                        link = entry.get('link', '')
                        summary = entry.get('summary', entry.get('description', ''))
                        
                        # Check if news was already processed globally
                        if global_db.is_news_globally_processed(title):
                            logger.debug(f"News already processed globally: {title[:50]}...")
                            continue
                        
                        # Check if any keywords match
                        content_to_check = f"{title} {summary}".lower()
                        if any(keyword.lower() in content_to_check for keyword in keyword_list):
                            # Mark as processed globally
                            global_db.mark_news_globally_processed(title, link, name, server_name)
                            opinion = await _generate_personality_opinion(
                                title,
                                summary,
                                user_id,
                                server_id=server_name,
                            )
                            rendered_opinion = opinion or "Watcher opinion unavailable"
                            
                            # Send notification
                            message = (
                                f"🔍 **Keyword Match:** {title}\n\n{summary[:300]}...\n\n"
                                f"🎯 **Matched keywords:** {keywords}\n\n"
                                f"💭 **Watcher Opinion:** {rendered_opinion}"
                            )
                            await _send_notification(http, user_id, channel_id, message)
                            
                            # Mark as sent in local database
                            db_watcher.mark_notification_sent(title, "keyword", rendered_opinion, link)
                            
                            matched_items += 1
                    
                    logger.info(f"Found {matched_items} items matching keywords in {name}")
                        
                else:
                    logger.warning(f"Failed to fetch feed {name}: HTTP {response.status}")
                    
    except Exception as e:
        logger.exception(f"Error processing keyword feed {name}: {e}")


async def _process_feed_ai_subscription(http, db_watcher, global_db, feed_data, user_id, channel_id, server_id: str):
    """Process a feed for AI subscriptions (premise detection)."""
    try:
        url, name = feed_data
        logger.info(f"🤖 Processing AI feed: {name}")
        
        # Check if already processed recently
        if db_watcher.is_news_read(name):
            logger.debug(f"Feed {name} already processed recently")
            return
        
        # Mark as read to avoid duplicate processing
        db_watcher.mark_news_as_read(name, url)
        
        # Get user premises
        if user_id.startswith("channel_"):
            # Channel premises
            channel_id = user_id.replace("channel_", "")
            premises, _ = db_watcher.get_premises_with_context(f"channel_{channel_id}")
        else:
            # User premises
            premises, _ = db_watcher.get_premises_with_context(user_id)
        
        if not premises:
            logger.warning(f"No premises found for {user_id}, skipping AI processing")
            return
        
        # Fetch and process news items
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    raw_data = await response.text()
                    feed = feedparser.parse(raw_data)
                    
                    critical_items = 0
                    
                    for entry in feed.entries[:10]:  # Limit to 10 latest items
                        title = entry.get('title', 'No title')
                        link = entry.get('link', '')
                        summary = entry.get('summary', entry.get('description', ''))
                        
                        # Check if news was already processed globally
                        if global_db.is_news_globally_processed(title):
                            logger.debug(f"News already processed globally: {title[:50]}...")
                            continue
                        
                        logger.info(f"🤖 Analyzing news item {critical_items + 1}: {title[:50]}...")
                        
                        is_critical = await _analyze_critical_news(title, summary, premises)
                        
                        if is_critical:
                            # Mark as processed globally
                            global_db.mark_news_globally_processed(title, link, name, server_id)

                            premise_text = ", ".join(premises) if premises else ""
                            opinion = await _generate_premise_opinion(
                                title,
                                summary,
                                premise_text,
                                user_id,
                                server_id=server_id,
                            )
                            rendered_opinion = opinion or "Watcher opinion unavailable"
                            
                            # Send notification with custom format
                            message = _format_critical_news_alert(title, summary, link, rendered_opinion)
                            await _send_notification(http, user_id, channel_id, message)
                            
                            # Mark as sent in local database
                            db_watcher.mark_notification_sent(title, "ai", rendered_opinion, link)
                            
                            critical_items += 1
                            logger.info(f"✅ Critical news found and sent: {title[:50]}...")
                        else:
                            logger.debug(f"❌ News not critical: {title[:50]}...")
                        
                        # Small delay between processing each news item to avoid overwhelming
                        await asyncio.sleep(1)
                    
                    logger.info(f"Found {critical_items} critical items in {name}")
                        
                else:
                    logger.warning(f"Failed to fetch feed {name}: HTTP {response.status}")
                    
    except Exception as e:
        logger.exception(f"Error processing AI feed {name}: {e}")


def _build_news_watcher_prompt(
    system_prompt: str,
    title: str,
    description: str = "",
    premise: str | None = None,
    prompt_config: dict | None = None,
) -> str:
    """Build the injected mission prompt for News Watcher opinions."""
    config = prompt_config or {}
    golden_rules = config.get("golden_rules") or [
        "1. LONGITUD: 2-4 frases (100-250 caracteres).",
        "2. GRAMATICA: Sin tildes. Termina afirmaciones con '!' y preguntas con '?'.",
        "3. No termines frases con palabras sueltas como \"ke\", \"a\", \"de\".",
        "4. EXPRESATE en la LENGUA del personaje, no cambies de registro ni lenguaje.",
    ]
    title_label = config.get("title_label", "Title")
    description_label = config.get("description_label", "Description")
    premise_label = config.get("premise_label", "This news matches the premise")
    opinion_request = config.get("opinion_request", "What is your opinion about this situation?")

    description_text = description.strip() if description else ""
    description_text = description_text[:1000] if description_text else ""

    prompt_sections = [
        "## REGLAS DE ORO VIGIA",
        *golden_rules,
        "",
        system_prompt,
    ]

    if premise:
        prompt_sections.extend([
            f'{premise_label}: "{premise}"',
        ])

    prompt_sections.extend([
        f'{title_label}: "{title}"',
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
        from agent_engine import think
        from agent_db import get_active_server_name
        
        server_to_use = server_id or get_active_server_name()
        if not server_to_use:
            logger.warning("⚠️ No active server available for watcher prompt generation")
            return None
        
        # Get system prompt from personality or fallback to English
        try:
            from agent_engine import PERSONALIDAD
            role_prompts = PERSONALIDAD.get("role_system_prompts", {})
            system_prompt = role_prompts.get("news_watcher", ROL_VIGIA_PERSONALIDAD)
            prompt_config = PERSONALIDAD.get("news_watcher_prompt", {})
        except Exception:
            system_prompt = ROL_VIGIA_PERSONALIDAD
            prompt_config = {}

        prompt = _build_news_watcher_prompt(
            system_prompt=system_prompt,
            title=title,
            description=description,
            prompt_config=prompt_config,
        )
        
        # Get personality opinion
        opinion = think(
            role_context="news_watcher",
            user_content=prompt,
            server_name=server_to_use,
            interaction_type="mission",
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


async def _generate_premise_opinion(title: str, description: str, premisa: str, user_id: str, server_id: str = None) -> str | None:
    """Generate personality opinion about news that matches a premise."""
    try:
        from agent_engine import think
        from agent_db import get_active_server_name
        
        # Use provided server_id or fall back to active server
        if server_id:
            server_to_use = server_id
        else:
            server_to_use = get_active_server_name()
            if not server_to_use:
                logger.warning("⚠️ No active server available for watcher notification analysis")
                return None
        
        # Get system prompt from personality or fallback to English
        try:
            from agent_engine import PERSONALIDAD
            role_prompts = PERSONALIDAD.get("role_system_prompts", {})
            system_prompt = role_prompts.get("news_watcher", ROL_VIGIA_PERSONALIDAD)
            prompt_config = PERSONALIDAD.get("news_watcher_prompt", {})
        except Exception:
            system_prompt = ROL_VIGIA_PERSONALIDAD
            prompt_config = {}

        prompt = _build_news_watcher_prompt(
            system_prompt=system_prompt,
            title=title,
            description=description,
            premise=premisa,
            prompt_config=prompt_config,
        )
        
        # Get personality opinion
        opinion = think(
            role_context="news_watcher",
            user_content=prompt,
            server_name=server_to_use,
            interaction_type="mission",
        )
        
        if opinion and len(opinion.strip()) > 0:
            logger.info(f"💭 Opinion about premise: {opinion[:50]}...")
            return opinion.strip()
        else:
            logger.warning("⚠️ Could not generate opinion about premise")
            return None
            
    except Exception as e:
        logger.exception(f"Error generating opinion about premise: {e}")
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


async def get_latest_news(url: str, name_feed: str, limite: int = 5) -> list:
    """Get the latest news from an RSS feed."""
    try:
        async with aiohttp.ClientSession() as session:
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
                        
                        # Clean description (remove HTML tags if present)
                        import re
                        description = re.sub(r'<[^>]+>', '', description).strip()
                        
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

# Load environment variables
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

# Mission configuration
MISSION_CONFIG = {
    "name": "news_watcher",
    # "system_prompt_addition": "ACTIVE MISSION - NEWS WATCHER: You are the Tower Watcher. Your mission is to detect extremely important news."
}

# Personality prompt (opinion about headlines)
ROL_VIGIA_PERSONALIDAD = (
    "You are the Tower Watcher, an ancient guardian who watches the world from above. "
    "Your character is wise, direct and sometimes a bit somber. "
    "When you give your opinion about news, be concise but impactful. "
    "Use language that reflects your watchful nature and your long experience observing world events."
)

def _format_critical_news_alert(title: str, summary: str, link: str, opinion: str) -> str:
    """Format critical news alert according to the custom specification."""
    try:
        # Get title from descriptions.json or fallback
        alert_title = _get_alert_title()
        
        # Get personality name from descriptions.json or fallback
        personality_name = _get_personality_name()
        
        # Build the formatted message
        separator = "────────────────────────────────────────────────────────────"
        
        message = (
            f"**🚨 {alert_title} : {title}**\n"
            f"*{summary}*\n"  # Full description without truncation
            f"{separator}\n"
            f"💭 {personality_name}: {opinion}"
            f"*{link}*\n"  # Add the news link
        )
        
        return message
        
    except Exception as e:
        logger.exception(f"Error formatting critical news alert: {e}")
        # Fallback to simple format without hardcoded text
        alert_title = _get_alert_title()
        personality_name = _get_personality_name()
        return f"🚨 *{alert_title}*: {title}\n\n{summary}\n\n💭 *{personality_name} Opinion*: {opinion}"


def _get_alert_title() -> str:
    """Get alert title from descriptions.json or fallback."""
    try:
        from agent_engine import PERSONALIDAD
        descriptions = PERSONALIDAD.get("descriptions", {})
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
        from agent_engine import PERSONALIDAD
        return PERSONALIDAD.get("bot_display_name", "Watcher")
    except Exception:
        return "Watcher"  # Fallback


async def _send_notification(http, user_id: str, channel_id: str, message: str):
    """Send notification to user (DM) or channel."""
    try:
        if channel_id:
            # Send to channel
            await http.send_channel_message(channel_id, message)
        else:
            # Send to user DM
            await http.send_dm(user_id, message)
    except Exception as e:
        logger.exception(f"Error sending notification: {e}")


async def _analyze_critical_news(title: str, summary: str, premises: list) -> bool:
    """Analyze if news is critical based on user premises."""
    try:
        await cohere_limiter.wait_if_needed()
        
        import cohere
        api_key = (os.getenv("COHERE_API_KEY") or "").strip()
        if not api_key:
            logger.warning("⚠️ COHERE_API_KEY is not configured for critical news analysis")
            return False
        
        client = cohere.Client(api_key=api_key, timeout=30)
        
        premises_text = "\n".join([f"{i}. {premise}" for i, premise in enumerate(premises, 1)])
        prompt = f"""{premises_text}

Title: "{title}"

Description: "{summary[:500]}"

Does this news match ANY premise strongly enough to be considered critical for notification?
Respond only: TRUE or FALSE"""
        
        response = client.chat(
            model="command-a-03-2025",
            message=prompt,
            temperature=0.0,
            max_tokens=5,
        )
        
        result = (getattr(response, "text", "") or "").strip()
        first_token = (result.split() or [""])[0].strip().upper()
        logger.info(f"🤖 Critical analysis for '{title[:50]}...': {result}")
        
        return first_token == "TRUE"
    except Exception as e:
        logger.exception(f"Error analyzing critical news: {e}")
        return False


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
