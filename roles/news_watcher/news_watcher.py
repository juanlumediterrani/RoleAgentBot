import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.dirname(__file__))

import asyncio
import re
import feedparser
import aiohttp
import logging
from dotenv import load_dotenv
from agent_db import get_active_server_name
from agent_logging import get_logger
from agent_engine import get_discord_token
from discord_bot.discord_http import DiscordHTTP

logger = get_logger('news_watcher')


async def process_subscriptions(http, server_name: str = "default"):
    """Process all subscription types using the correct logic."""
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance

    db_watcher = get_news_watcher_db_instance(server_name)
    
    try:
        logger.info("🚀 Starting subscription processing...")
        
        # 1. Process flat subscriptions (all news with opinion)
        await process_flat_subscriptions(http, db_watcher, server_name)
        
        # 2. Process keyword subscriptions (regex)
        await process_keyword_subscriptions(http, db_watcher, server_name)
        
        # 3. Process AI subscriptions (premise detection)
        await process_ai_subscriptions(http, db_watcher, server_name)
        
        # 4. Process channel subscriptions (admin-configured)
        await process_channel_subscriptions(http, db_watcher, server_name)
        
        logger.info("✅ Subscription processing completed")
        
    except Exception as e:
        logger.exception(f"❌ General error in subscription processing: {e}")


async def process_flat_subscriptions(http, db_watcher, server_name: str):
    """Process flat subscriptions (sends all news with opinion)."""
    try:
        logger.info("📰 Processing flat subscriptions...")
        
        subscriptions = db_watcher.get_all_active_subscriptions()
        
        for user_id, categoria, feed_id, fecha in subscriptions:
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_flat_subscription(http, db_watcher, (feed_data[2], feed_data[1]), user_id, None)
            else:
                # All feeds in category
                feeds = db_watcher.get_active_feeds(categoria)
                for feed in feeds:
                    await _process_feed_flat_subscription(http, db_watcher, (feed[2], feed[1]), user_id, None)
                    
    except Exception as e:
        logger.exception(f"❌ Error processing flat subscriptions: {e}")


async def process_keyword_subscriptions(http, db_watcher, server_name: str):
    """Process keyword subscriptions (regex)."""
    try:
        logger.info("🔍 Processing keyword subscriptions...")
        
        subscriptions_palabras = db_watcher.get_all_active_keyword_subscriptions()
        
        for user_id, channel_id, keywords, category, feed_id in subscriptions_palabras:
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_keyword_subscription(http, db_watcher, (feed_data[2], feed_data[1]), user_id, channel_id, keywords)
            else:
                # All feeds in category
                feeds = db_watcher.get_active_feeds(category)
                for feed in feeds:
                    await _process_feed_keyword_subscription(http, db_watcher, (feed[2], feed[1]), user_id, channel_id, keywords)
                    
    except Exception as e:
        logger.exception(f"❌ Error processing keyword subscriptions: {e}")


async def process_ai_subscriptions(http, db_watcher, server_name: str):
    """Process AI subscriptions (premise detection)."""
    try:
        logger.info("🤖 Processing AI subscriptions...")
        
        subscriptions_ia = db_watcher.get_all_active_category_subscriptions()
        
        for user_id, categoria, feed_id, fecha in subscriptions_ia:
            if feed_id:
                # Specific feed
                feed_data = db_watcher.get_feed_by_id(feed_id)
                if feed_data:
                    await _process_feed_ai_subscription(http, db_watcher, (feed_data[2], feed_data[1]), user_id, None, server_name)
            else:
                # All feeds in category
                feeds = db_watcher.get_active_feeds(categoria)
                for feed in feeds:
                    await _process_feed_ai_subscription(http, db_watcher, (feed[2], feed[1]), user_id, None, server_name)
                    
    except Exception as e:
        logger.exception(f"❌ Error processing AI subscriptions: {e}")


async def process_channel_subscriptions(http, db_watcher, server_name: str):
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
                            await _process_feed_ai_subscription(http, db_watcher, (feed_data[2], feed_data[1]), f"channel_{channel_id}", channel_premises, servidor_id)
                        else:
                            await _process_feed_flat_subscription(http, db_watcher, (feed_data[2], feed_data[1]), f"channel_{channel_id}", channel_id)
                else:
                    # All feeds in category
                    feeds = db_watcher.get_active_feeds(category)
                    for feed in feeds:
                        if channel_premises:
                            await _process_feed_ai_subscription(http, db_watcher, (feed[2], feed[1]), f"channel_{channel_id}", channel_premises, servidor_id)
                        else:
                            await _process_feed_flat_subscription(http, db_watcher, (feed[2], feed[1]), f"channel_{channel_id}", channel_id)
                    
    except Exception as e:
        logger.exception(f"❌ Error processing channel subscriptions: {e}")


async def _process_feed_flat_subscription(http, db_watcher, feed_data, user_id, channel_id):
    """Process a feed for flat subscriptions (sends all news with opinion)."""
    try:
        url, name = feed_data
        logger.info(f"📰 Processing flat feed: {name}")
        
        entries = await get_latest_news(url, name, 5)
        for i, news_item in enumerate(entries[:5], 1):
            title = news_item.get('title', '') if isinstance(news_item, dict) else news_item
            title = title or ''
            if not title:
                continue

            logger.info(f"📄 [{i}/5] {name}: {title[:80]}...")

            if db_watcher.noticia_esta_leida(title):
                logger.info(f"ℹ️ News already read: {title}")
                continue

            # For flat subscriptions, generate personality opinion about the title
            opinion = await _generate_personality_opinion(title, user_id)
            
            if opinion:
                await _send_flat_notification(http, db_watcher, [user_id], title, opinion, name, link)

            db_watcher.mark_news_as_read(title, name)

    except Exception as e:
        logger.exception(f"❌ Error processing flat feed {name}: {e}")


async def _process_feed_keyword_subscription(http, db_watcher, feed_data, user_id, channel_id, keywords):
    """Process a feed for keyword subscriptions (regex)."""
    try:
        url, name = feed_data
        logger.info(f"🔍 Processing keyword feed: {name}")
        
        entries = await get_latest_news(url, name, 5)
        for i, news_item in enumerate(entries[:5], 1):
            title = news_item.get('title', '') if isinstance(news_item, dict) else news_item
            title = title or ''
            if not title:
                continue

            logger.info(f"📄 [{i}/5] {name}: {title[:80]}...")

            if db_watcher.noticia_esta_leida(title):
                logger.info(f"ℹ️ News already read: {title}")
                continue

            # Check keyword match using regex
            if check_keywords_regex(title, keywords):
                logger.info(f"🎯 Keyword match: {title[:60]}...")
                
                # Generate personality opinion about the title
                opinion = await _generate_personality_opinion(title, user_id)
                
                if opinion:
                    await _send_keyword_notification(http, db_watcher, [user_id], title, opinion, name, keywords, link)

            db_watcher.mark_news_as_read(title, name)

    except Exception as e:
        logger.exception(f"❌ Error processing keyword feed {name}: {e}")


async def _process_feed_ai_subscription(http, db_watcher, feed_data, user_id, channel_id, server_id):
    """Process a feed for AI subscriptions (premise detection)."""
    try:
        from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
        
        url, name = feed_data
        logger.info(f"🤖 Processing AI feed: {name}")
        
        entries = await get_latest_news(url, name, 5)
        for i, news_item in enumerate(entries[:5], 1):
            title = news_item.get('title', '') if isinstance(news_item, dict) else news_item
            description = news_item.get('description', '') if isinstance(news_item, dict) else ''
            link = news_item.get('link', '') if isinstance(news_item, dict) else ''
            title = title or ''
            if not title:
                continue

            logger.info(f"📄 [{i}/5] {name}: {title[:80]}...")

            if db_watcher.noticia_esta_leida(title):
                logger.info(f"ℹ️ News already read: {title}")
                continue

            # Analyze with AI according to user's key premises (Cohere WITHOUT personality)
            coincidencia = await _analyze_with_cohere_premises(title, description, user_id, server_id)
            
            if coincidencia:
                logger.info(f"🎯 AI match: {title[:60]}...")
                
                # Get user's premises to display them
                db_watcher_local = get_news_watcher_db_instance(server_id)
                premisas, contexto = db_watcher_local.get_premises_with_context(user_id)
                premisas_texto = ", ".join(premisas[:3])  # Show first 3 premises
                
                # Generate personality opinion about the news and premises
                opinion = await _generate_premise_opinion(title, premisas_texto, user_id, server_id)
                
                if opinion:
                    await _send_ai_notification(http, db_watcher, [user_id], title, opinion, name, premisas_texto, link)

            db_watcher.mark_news_as_read(title, name)

    except Exception as e:
        logger.exception(f"❌ Error processing AI feed {name}: {e}")


async def _analyze_with_cohere_premises(title: str, description: str, user_id: str, server_id: str = None) -> bool:
    """Analiza UN TITULAR con Cohere para detectar coincidencias con premisas (SIN personalidad)."""
    try:
        import cohere
        import os
        from agent_db import get_active_server_name
        from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
        
        api_key = (os.getenv("COHERE_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("COHERE_API_KEY is not configured")

        client = cohere.Client(api_key=api_key, timeout=30)  # Shorter timeout for a headline
        
        # Get user's premises (custom or global)
        if server_id:
            db_watcher = get_news_watcher_db_instance(server_id)
        else:
            server_name = get_active_server_name() or "default"
            db_watcher = get_news_watcher_db_instance(server_name)
        premisas, contexto = db_watcher.get_premises_with_context(user_id)
        
        if not premisas:
            logger.warning(f"⚠️ No premises configured for user {user_id}")
            return False
        
        # Build premises text in ultra concise form
        texto_premisas = "\n".join([f"{i}. {p}" for i, p in enumerate(premisas, 1)])
        
        # Clean description (limit length)
        description_clean = description[:500] if description else ""
        
        # Ultra neutral prompt - only returns TRUE/FALSE for ONE NEWS ITEM
        prompt_analisis = f"""{texto_premisas}

Title: "{title}"

Description: "{description_clean}"

Does this news (title + description) match ANY premise?
Respond only: TRUE or FALSE"""
        
        try:
            res = client.chat(
                model="command-a-03-2025",
                message=prompt_analisis,
                temperature=0.0,  # Maximum objectivity
                max_tokens=5  # Only needs to respond TRUE/FALSE
            )
            
            resultado_raw = getattr(res, "text", "")
            resultado = (resultado_raw or "").strip()

            # Cohere occasionally returns extra tokens/newlines (e.g. "TRUE\n\nThe...")
            # We only care about the first token.
            first_token = (resultado.split() or [""])[0].strip().upper()

            logger.info(f"🤖 HEADLINE: {title[:30]}... → {resultado}")

            # Parse result - only TRUE/FALSE
            return first_token == "TRUE"
                
        except Exception as e:
            logger.exception(f"Error in Cohere call for headline: {e}")
            return False
            
    except Exception as e:
        logger.exception(f"Error analyzing headline with Cohere: {e}")
        return False


async def _generate_personality_opinion(title: str, user_id: str) -> str:
    """Generate personality opinion about a news headline."""
    try:
        from agent_engine import think
        from agent_db import get_active_server_name
        
        server_name = get_active_server_name() or "default"
        
        # Get system prompt from personality or fallback to English
        try:
            from agent_engine import PERSONALIDAD
            role_prompts = PERSONALIDAD.get("role_system_prompts", {})
            system_prompt = role_prompts.get("news_watcher", ROL_VIGIA_PERSONALIDAD)
        except Exception:
            system_prompt = ROL_VIGIA_PERSONALIDAD
        
        # Create prompt for the personality about the news
        prompt = f"{system_prompt}\n\nWhat do you think about this news? \"{title}\""
        
        # Get personality opinion
        opinion = think(prompt, server_name)
        
        if opinion and len(opinion.strip()) > 0:
            logger.info(f"💭 Opinion generated: {opinion[:50]}...")
            return opinion.strip()
        else:
            logger.warning("⚠️ Could not generate personality opinion")
            return None
            
    except Exception as e:
        logger.exception(f"Error generating personality opinion: {e}")
        return None


async def _generate_premise_opinion(title: str, premisa: str, user_id: str, server_id: str = None) -> str | None:
    """Generate personality opinion about news that matches a premise."""
    try:
        from agent_engine import think
        from agent_db import get_active_server_name
        
        # Use provided server_id or fall back to active server
        if server_id:
            server_to_use = server_id
        else:
            server_to_use = get_active_server_name() or "default"
        
        # Get system prompt from personality or fallback to English
        try:
            from agent_engine import PERSONALIDAD
            role_prompts = PERSONALIDAD.get("role_system_prompts", {})
            system_prompt = role_prompts.get("news_watcher", ROL_VIGIA_PERSONALIDAD)
        except Exception:
            system_prompt = ROL_VIGIA_PERSONALIDAD
        
        # Create specific prompt for the premise
        prompt = f"{system_prompt}\n\nThis news matches the premise: \"{premisa}\"\nNews: \"{title}\"\nWhat is your opinion about this situation?"
        
        # Get personality opinion
        opinion = think(prompt, server_to_use)
        
        if opinion and len(opinion.strip()) > 0:
            logger.info(f"💭 Opinion about premise: {opinion[:50]}...")
            return opinion.strip()
        else:
            logger.warning("⚠️ Could not generate opinion about premise")
            return None
            
    except Exception as e:
        logger.exception(f"Error generating opinion about premise: {e}")
        return None


async def _send_flat_notification(http, db_watcher, usuarios, title, opinion, name_feed, link=None):
    """Send flat subscription notification."""
    try:
        # Use the provided real link or fallback to simulated one
        if not link:
            link = f"https://example.com/noticia/{hash(title) % 10000}"
        
        message = (
            f"📰 **New News** - {name_feed}\n\n"
            f"📌 **{title}**\n"
            f"🔗 [Read more]({link})\n\n"
            f"💭 **Opinion:** {opinion}"
        )
        
        for user_id in usuarios:
            channel_id = int(user_id.replace('channel_', '') if isinstance(user_id, str) else str(user_id))
            ok = await http.send_channel_message(channel_id, message)
            if not ok:
                logger.warning(f"❌ Flat notification send failed for channel_id={channel_id}")
            
    except Exception as e:
        logger.exception(f"Error sending flat notification: {e}")


async def _send_keyword_notification(http, db_watcher, usuarios, title, opinion, name_feed, keywords, link=None):
    """Send keyword match notification."""
    try:
        # Use the provided real link or fallback to simulated one
        if not link:
            link = f"https://example.com/noticia/{hash(title) % 10000}"
        
        message = (
            f"🔍 **Keyword Match** - {name_feed}\n\n"
            f"📌 **{title}**\n"
            f"🔗 [Read more]({link})\n"
            f"🎯 **Keywords:** `{keywords}`\n\n"
            f"💭 **Opinion:** {opinion}"
        )
        
        for user_id in usuarios:
            channel_id = int(user_id.replace('channel_', '') if isinstance(user_id, str) else str(user_id))
            ok = await http.send_channel_message(channel_id, message)
            if not ok:
                logger.warning(f"❌ Keyword notification send failed for channel_id={channel_id}")
            
    except Exception as e:
        logger.exception(f"Error sending keyword notification: {e}")


async def _send_ai_notification(http, db_watcher, usuarios, title, opinion, name_feed, premisa, link=None):
    """Send AI match notification with personality formatting."""
    try:
        # Use the provided real link from RSS or fallback to simulated one
        if not link:
            link = f"https://example.com/noticia/{hash(title) % 10000}"
        
        # Get personality messages for styling
        from agent_engine import PERSONALIDAD
        watcher_messages = PERSONALIDAD.get("discord", {}).get("watcher_messages", {})
        
        # Use custom alert title or fallback (remove title part)
        alert_template = watcher_messages.get("notificacion_critica_detectada", "🤖 \"Critical Alert Detected\"")
        # Extract just the first part before the colon
        alert_title = alert_template.split(':')[0].strip() if ':' in alert_template else alert_template
        
        # Format the message with personality style
        message = (
            f"{alert_title} // {name_feed}\n"
            f"📌 {title}\n\n"
            f"💭 {opinion}\n\n"
            f"```\n🎯 Premise: {premisa}\n🔗 Read more: {link}\n```"
        )
        
        for user_id in usuarios:
            channel_id = int(user_id.replace('channel_', '') if isinstance(user_id, str) else str(user_id))
            # Use custom DiscordHTTP client method
            ok = await http.send_channel_message(channel_id, message)
            if ok:
                logger.info(f"✅ AI notification sent to channel_id={channel_id} (feed={name_feed})")
            else:
                logger.warning(f"❌ AI notification send failed for channel_id={channel_id} (feed={name_feed})")
            
    except Exception as e:
        logger.exception(f"Error sending AI notification: {e}")


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

# Neutral prompt for premise analysis with Cohere (WITHOUT personality)
PROMPT_COHERE_ANALISIS = (
    "Objectively analyze if a news headline matches the provided premises. "
    "Respond only according to the given instructions, without adding opinions or personal style."
)


async def main():
    """Main function of the News Watcher."""
    try:
        logger.info("🚀 Starting News Watcher...")
        
        # Get server configuration
        server_name = get_active_server_name() or "default"
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
