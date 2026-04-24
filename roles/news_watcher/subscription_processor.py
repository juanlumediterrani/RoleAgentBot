#!/usr/bin/env python3
"""
News Watcher Subscription Processor

This module processes subscriptions based on server-specific frequency.
For each subscription, it:
1. Checks category/feed
2. Retrieves news from the configured frequency window
3. Before sending news, checks global feed last_updated timestamp
4. If more time passed than configured frequency, downloads fresh news
5. Applies analysis with method and variables to generate report
6. Sequentially processes subscriptions in background without blocking
"""

import asyncio
import logging
from typing import List
from datetime import datetime, timedelta
import discord
from typing import Dict, List, Optional
from agent_logging import get_logger

logger = get_logger('subscription_processor')


def _build_dm_embed(user: discord.User, method: str, premises: list | str = None, keywords: str = None, server_id: str = None) -> tuple[discord.Embed, discord.File | None]:
    """Build embed for DM with personality avatar, alert header, and premises/keywords.
    
    Args:
        user: Discord user object
        method: Subscription method ('general', 'keyword', 'flat')
        premises: User premises for general method
        keywords: Keywords for keyword method
        server_id: Server ID for alert title
        
    Returns:
        tuple: (discord.Embed, discord.File | None) - embed and optional avatar file
    """
    import os
    from roles.news_watcher.news_watcher import _get_alert_title, _get_news_watcher_descriptions
    from discord_bot.discord_utils import get_server_personality_avatar_path
    
    # Get alert title
    alert_title = _get_alert_title(server_id)
    
    # Get news_watcher descriptions for labels
    descriptions = _get_news_watcher_descriptions(server_id) or {}
    premises_title = descriptions.get("premises_title", "🔍 **Premisas:**")
    keywords_title = descriptions.get("keywords_title", "🔍 **Palabras Clave:**")
    
    # Create embed
    embed = discord.Embed(
        title=alert_title,
        color=discord.Color.blue()
    )
    
    # Add premises or keywords field
    if method == 'general' and premises:
        # Handle both list and string formats
        if isinstance(premises, list):
            premise_list = [str(p).strip() for p in premises if str(p).strip()]
        else:
            premise_list = [p.strip() for p in premises.split(',') if p.strip()]
        
        if premise_list:
            premises_text = "\n".join([f"{i}. {p}" for i, p in enumerate(premise_list[:3], 1)])
            embed.add_field(
                name=premises_title,
                value=premises_text,
                inline=False
            )
    
    elif method == 'keyword' and keywords:
        embed.add_field(
            name=keywords_title,
            value=keywords,
            inline=False
        )
    
    # Get server-specific personality avatar
    avatar_file = None
    if server_id:
        avatar_path = get_server_personality_avatar_path(server_id)
        if avatar_path and os.path.exists(avatar_path):
            avatar_filename = os.path.basename(avatar_path)
            avatar_file = discord.File(avatar_path, filename=avatar_filename)
            embed.set_thumbnail(url=f"attachment://{avatar_filename}")
    
    return embed, avatar_file


def _build_channel_embed(method: str, premises: list | str = None, keywords: str = None, server_id: str = None) -> discord.Embed:
    """Build embed for channel with alert header and premises/keywords (no avatar).

    Args:
        method: Subscription method ('general', 'keyword', 'flat')
        premises: User premises for general method
        keywords: Keywords for keyword method
        server_id: Server ID for alert title

    Returns:
        discord.Embed: embed without avatar
    """
    from roles.news_watcher.news_watcher import _get_alert_title, _get_news_watcher_descriptions

    # Get alert title
    alert_title = _get_alert_title(server_id)

    # Get news_watcher descriptions for labels
    descriptions = _get_news_watcher_descriptions(server_id) or {}
    premises_title = descriptions.get("premises_title", "🔍 **Premisas:**")
    keywords_title = descriptions.get("keywords_title", "🔍 **Palabras Clave:**")

    # Create embed
    embed = discord.Embed(
        title=alert_title,
        color=discord.Color.blue()
    )

    # Add premises or keywords field
    if method == 'general' and premises:
        # Handle both list and string formats
        if isinstance(premises, list):
            premise_list = [str(p).strip() for p in premises if str(p).strip()]
        else:
            premise_list = [p.strip() for p in premises.split(',') if p.strip()]

        if premise_list:
            premises_text = "\n".join([f"{i}. {p}" for i, p in enumerate(premise_list[:3], 1)])
            embed.add_field(
                name=premises_title,
                value=premises_text,
                inline=False
            )

    elif method == 'keyword' and keywords:
        embed.add_field(
            name=keywords_title,
            value=keywords,
            inline=False
        )

    return embed


def _build_dm_second_message(rendered_opinion: str, articles: list[dict]) -> str:
    """Build second DM message with LLM opinion only.
    
    Args:
        rendered_opinion: The LLM-generated opinion
        articles: List of article dictionaries (not used, links come from buttons)
        
    Returns:
        Formatted message string with opinion
    """
    return f"💭 {rendered_opinion}"


async def process_all_server_subscriptions(bot, agent_config: dict):
    """Process all subscriptions for all servers.
    
    This function is called by the global scheduler. It:
    - Iterates through all servers
    - For each server, processes all active subscriptions
    - Downloads fresh news if needed based on feed update frequency
    - Applies analysis and sends reports
    
    Args:
        bot: Discord bot instance
        agent_config: Agent configuration dictionary
    """
    try:
        from agent_db import get_all_server_ids
        from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
        
        # Get all server IDs
        server_ids = get_all_server_ids()
        if not server_ids:
            logger.info("[SUBSCRIPTION_PROCESSOR] No servers found")
            return
        
        logger.info(f"[SUBSCRIPTION_PROCESSOR] Processing subscriptions for {len(server_ids)} servers")
        
        # Process each server
        for server_id in server_ids:
            try:
                await process_server_subscriptions(bot, server_id, agent_config)
                # Yield control between servers to avoid blocking
                await asyncio.sleep(0)
            except Exception as e:
                logger.error(f"[SUBSCRIPTION_PROCESSOR] Error processing server {server_id}: {e}")
                continue
        
        logger.info("[SUBSCRIPTION_PROCESSOR] Completed processing all servers")
        
    except Exception as e:
        logger.exception(f"[SUBSCRIPTION_PROCESSOR] Error in process_all_server_subscriptions: {e}")


async def process_server_subscriptions(bot, server_id: str, agent_config: dict):
    """Process all subscriptions for a specific server.
    
    Args:
        bot: Discord bot instance
        server_id: Server ID
        agent_config: Agent configuration dictionary
    """
    try:
        from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
        from roles.news_watcher.global_news_db import get_global_news_db
        from roles.news_watcher.global_feed_health import get_healthy_feeds
        from discord_bot.canvas.server_config import get_news_watcher_frequency
        
        # Get database instance for this server
        db = get_news_watcher_db_instance(server_id)
        if not db:
            logger.debug(f"[SUBSCRIPTION_PROCESSOR] No DB for server {server_id}, skipping")
            return
        
        # Get all active subscriptions
        subscriptions = db.get_all_active_subscriptions()
        if not subscriptions:
            logger.debug(f"[SUBSCRIPTION_PROCESSOR] No active subscriptions for server {server_id}")
            return
        
        logger.info(f"[SUBSCRIPTION_PROCESSOR] Processing {len(subscriptions)} subscriptions for server {server_id}")
        
        # Get global news DB
        global_db = get_global_news_db()
        
        # Get server-specific frequency from server_config.json
        interval_hours = get_news_watcher_frequency(server_id, default_hours=1)
        
        # Calculate since_date based on server frequency
        since_date = (datetime.now() - timedelta(hours=interval_hours)).isoformat()
        
        # Get healthy feeds
        healthy_feeds = get_healthy_feeds()
        feeds_by_url = {url: (fid, name, cat) for fid, name, url, cat in healthy_feeds}
        
        # Process each subscription
        for sub in subscriptions:
            try:
                subscription_id, user_id, channel_id, category, feed_id, premises, keywords, method, subscribed_at, created_by = sub
                
                # Determine feed URL and info
                feed_url = None
                feed_name = None
                feed_category = category
                
                if feed_id:
                    # Find feed info from healthy feeds
                    for fid, name, url, cat in healthy_feeds:
                        if fid == feed_id:
                            feed_url = url
                            feed_name = name
                            feed_category = cat
                            break
                
                # Check if feed needs update
                needs_update = False
                if feed_url:
                    needs_update = global_db.should_update_feed(feed_url, interval_hours)
                
                # Download fresh news if needed
                if needs_update and feed_url:
                    logger.info(f"[SUBSCRIPTION_PROCESSOR] Downloading fresh news for feed {feed_name}")
                    try:
                        from roles.news_watcher.news_downloader import NewsDownloader
                        downloader = NewsDownloader(global_db)
                        new_items = await downloader.fetch_and_store_news(feed_url, feed_category, feed_name, max_items=50)
                        logger.info(f"[SUBSCRIPTION_PROCESSOR] Downloaded {len(new_items)} new items for {feed_name}")
                    except Exception as e:
                        logger.error(f"[SUBSCRIPTION_PROCESSOR] Error downloading feed {feed_name}: {e}")
                
                # Get news since frequency window
                news_items = []
                
                if feed_url:
                    news_items = global_db.get_news_by_feed(feed_url, since_date=since_date, limit=100)
                else:
                    news_items = global_db.get_news_by_category(feed_category, since_date=since_date, limit=100)
                
                if not news_items:
                    logger.debug(f"[SUBSCRIPTION_PROCESSOR] No new news for subscription {subscription_id}")
                    await asyncio.sleep(0)
                    continue
                
                logger.info(f"[SUBSCRIPTION_PROCESSOR] Found {len(news_items)} news items for subscription {subscription_id}")
                
                # Convert news_items to article format for news_watcher functions
                articles = []
                for news_item in news_items:
                    try:
                        title, source_url, summary, published_date, first_seen = news_item[:5]
                        articles.append({
                            'title': title,
                            'link': source_url,
                            'summary': summary
                        })
                    except Exception as e:
                        logger.error(f"[SUBSCRIPTION_PROCESSOR] Error converting news item: {e}")
                        continue
                
                if not articles:
                    logger.debug(f"[SUBSCRIPTION_PROCESSOR] No valid articles for subscription {subscription_id}")
                    await asyncio.sleep(0)
                    continue
                
                # Apply analysis based on method using news_watcher functions
                if method == 'general' and premises:
                    # Use Cohere batch analysis for general method
                    from roles.news_watcher.news_watcher import _analyze_critical_news_batch
                    matched_indices = await _analyze_critical_news_batch(articles, premises, server_id)
                    filtered_articles = [articles[i] for i in matched_indices if i < len(articles)]
                    
                    if not filtered_articles:
                        logger.debug(f"[SUBSCRIPTION_PROCESSOR] No articles matched premises for subscription {subscription_id}")
                        await asyncio.sleep(0)
                        continue
                    
                    # Generate AI opinion for matched articles
                    from roles.news_watcher.news_watcher import _generate_personality_opinion
                    # Build description from filtered articles for opinion generation
                    articles_text = "\n".join([f"{i+1}. {a['title']}: {a['summary'][:200] if a['summary'] else 'No description'}" for i, a in enumerate(filtered_articles)])
                    rendered_opinion = await _generate_personality_opinion(
                        title=f"News Analysis ({len(filtered_articles)} articles)",
                        description=articles_text,
                        user_id=user_id,
                        server_id=server_id,
                        news_items=filtered_articles
                    )
                    
                    if not rendered_opinion:
                        logger.debug(f"[SUBSCRIPTION_PROCESSOR] Could not generate opinion for subscription {subscription_id}")
                        await asyncio.sleep(0)
                        continue
                    
                    # Send messages
                    if channel_id:
                        channel = bot.get_channel(int(channel_id))
                        if channel:
                            # First message: Embed with alert header and premises (no avatar)
                            embed = _build_channel_embed('general', premises=premises, server_id=server_id)

                            # Build buttons view
                            from roles.news_watcher.news_watcher import _build_news_components
                            components = _build_news_components(filtered_articles, method='general')
                            view = _build_discord_view_from_components(components) if components else None

                            # Send embed + buttons together
                            if view:
                                await channel.send(embed=embed, view=view)
                            else:
                                await channel.send(embed=embed)

                            # Second message: Opinion only
                            second_msg = _build_dm_second_message(rendered_opinion, filtered_articles)
                            await channel.send(second_msg)
                    else:
                        user = bot.get_user(int(user_id))
                        if user:
                            # First message: Embed with personality avatar, alert, premises, AND buttons
                            embed, avatar_file = _build_dm_embed(user, 'general', premises=premises, server_id=server_id)
                            
                            # Build buttons view
                            from roles.news_watcher.news_watcher import _build_news_components
                            components = _build_news_components(filtered_articles, method='general')
                            view = _build_discord_view_from_components(components) if components else None
                            
                            # Send embed + avatar + buttons together
                            if avatar_file and view:
                                await user.send(embed=embed, file=avatar_file, view=view)
                            elif avatar_file:
                                await user.send(embed=embed, file=avatar_file)
                            elif view:
                                await user.send(embed=embed, view=view)
                            else:
                                await user.send(embed=embed)
                            
                            # Second message: Opinion only
                            second_msg = _build_dm_second_message(rendered_opinion, filtered_articles)
                            await user.send(second_msg)
                    
                elif method == 'keyword' and keywords:
                    # Filter by keywords
                    filtered_articles = []
                    for article in articles:
                        if _matches_keywords(article['title'], article['summary'], keywords):
                            filtered_articles.append(article)
                    
                    if not filtered_articles:
                        logger.debug(f"[SUBSCRIPTION_PROCESSOR] No articles matched keywords for subscription {subscription_id}")
                        await asyncio.sleep(0)
                        continue
                    
                    # Generate AI opinion for keyword matches
                    from roles.news_watcher.news_watcher import _generate_personality_opinion
                    articles_text = "\n".join([f"{i+1}. {a['title']}: {a['summary'][:200] if a['summary'] else 'No description'}" for i, a in enumerate(filtered_articles)])
                    rendered_opinion = await _generate_personality_opinion(
                        title=f"Keyword Match: {keywords} ({len(filtered_articles)} articles)",
                        description=articles_text,
                        user_id=user_id,
                        server_id=server_id,
                        news_items=filtered_articles
                    )
                    
                    if not rendered_opinion:
                        logger.debug(f"[SUBSCRIPTION_PROCESSOR] Could not generate opinion for subscription {subscription_id}")
                        await asyncio.sleep(0)
                        continue
                    
                    # Send messages
                    if channel_id:
                        channel = bot.get_channel(int(channel_id))
                        if channel:
                            # First message: Embed with alert header and keywords (no avatar)
                            embed = _build_channel_embed('keyword', keywords=keywords, server_id=server_id)

                            # Build buttons view
                            from roles.news_watcher.news_watcher import _build_news_components
                            components = _build_news_components(filtered_articles, method='keyword', keywords=keywords)
                            view = _build_discord_view_from_components(components) if components else None

                            # Send embed + buttons together
                            if view:
                                await channel.send(embed=embed, view=view)
                            else:
                                await channel.send(embed=embed)

                            # Second message: Opinion only
                            second_msg = _build_dm_second_message(rendered_opinion, filtered_articles)
                            await channel.send(second_msg)
                    else:
                        user = bot.get_user(int(user_id))
                        if user:
                            # First message: Embed with personality avatar, alert, keywords, AND buttons
                            embed, avatar_file = _build_dm_embed(user, 'keyword', keywords=keywords, server_id=server_id)
                            
                            # Build buttons view
                            from roles.news_watcher.news_watcher import _build_news_components
                            components = _build_news_components(filtered_articles, method='keyword', keywords=keywords)
                            view = _build_discord_view_from_components(components) if components else None
                            
                            # Send embed + avatar + buttons together
                            if avatar_file and view:
                                await user.send(embed=embed, file=avatar_file, view=view)
                            elif avatar_file:
                                await user.send(embed=embed, file=avatar_file)
                            elif view:
                                await user.send(embed=embed, view=view)
                            else:
                                await user.send(embed=embed)
                            
                            # Second message: Opinion only
                            second_msg = _build_dm_second_message(rendered_opinion, filtered_articles)
                            await user.send(second_msg)
                    
                elif method == 'flat':
                    # Flat method - all news with AI opinion
                    # Generate AI opinion for all articles
                    from roles.news_watcher.news_watcher import _generate_personality_opinion
                    articles_text = "\n".join([f"{i+1}. {a['title']}: {a['summary'][:200] if a['summary'] else 'No description'}" for i, a in enumerate(articles)])
                    rendered_opinion = await _generate_personality_opinion(
                        title=f"News Summary ({len(articles)} articles)",
                        description=articles_text,
                        user_id=user_id,
                        server_id=server_id,
                        news_items=articles
                    )
                    
                    if not rendered_opinion:
                        logger.debug(f"[SUBSCRIPTION_PROCESSOR] Could not generate opinion for subscription {subscription_id}")
                        await asyncio.sleep(0)
                        continue
                    
                    # Send messages
                    if channel_id:
                        channel = bot.get_channel(int(channel_id))
                        if channel:
                            # First message: Embed with alert header (no avatar, no premises/keywords for flat)
                            embed = _build_channel_embed('flat', server_id=server_id)

                            # Build buttons view
                            from roles.news_watcher.news_watcher import _build_news_components
                            components = _build_news_components(articles, method='flat')
                            view = _build_discord_view_from_components(components) if components else None

                            # Send embed + buttons together
                            if view:
                                await channel.send(embed=embed, view=view)
                            else:
                                await channel.send(embed=embed)

                            # Second message: Opinion only
                            second_msg = _build_dm_second_message(rendered_opinion, articles)
                            await channel.send(second_msg)
                    else:
                        user = bot.get_user(int(user_id))
                        if user:
                            # First message: Embed with personality avatar, alert, AND buttons (no premises/keywords for flat)
                            embed, avatar_file = _build_dm_embed(user, 'flat', server_id=server_id)
                            
                            # Build buttons view
                            from roles.news_watcher.news_watcher import _build_news_components
                            components = _build_news_components(articles, method='flat')
                            view = _build_discord_view_from_components(components) if components else None
                            
                            # Send embed + avatar + buttons together
                            if avatar_file and view:
                                await user.send(embed=embed, file=avatar_file, view=view)
                            elif avatar_file:
                                await user.send(embed=embed, file=avatar_file)
                            elif view:
                                await user.send(embed=embed, view=view)
                            else:
                                await user.send(embed=embed)
                            
                            # Second message: Opinion only
                            second_msg = _build_dm_second_message(rendered_opinion, articles)
                            await user.send(second_msg)
                else:
                    logger.debug(f"[SUBSCRIPTION_PROCESSOR] Unknown method or missing criteria for subscription {subscription_id}")
                    await asyncio.sleep(0)
                    continue
                
                # Yield control between subscriptions
                await asyncio.sleep(0)
                
            except Exception as e:
                logger.error(f"[SUBSCRIPTION_PROCESSOR] Error processing subscription: {e}")
                continue
        
        logger.info(f"[SUBSCRIPTION_PROCESSOR] Completed processing for server {server_id}")
        
    except Exception as e:
        logger.exception(f"[SUBSCRIPTION_PROCESSOR] Error in process_server_subscriptions: {e}")


def _matches_keywords(title: str, summary: str, keywords: str) -> bool:
    """Check if news matches keywords."""
    if not keywords:
        return True
    
    keyword_list = [k.strip().lower() for k in keywords.split(',') if k.strip()]
    text_to_check = f"{title} {summary}".lower()
    
    return any(keyword in text_to_check for keyword in keyword_list)


def _build_discord_view_from_components(components: list) -> discord.ui.View:
    """Convert raw Discord API components to discord.ui.View.
    
    Args:
        components: Raw Discord API components from _build_news_components
        
    Returns:
        discord.ui.View with buttons
    """
    import discord
    
    view = discord.ui.View(timeout=None)
    
    row = 0
    for action_row in components:
        if action_row.get('type') == 1:  # Action Row
            col = 0
            for button_data in action_row.get('components', []):
                if button_data.get('type') == 2:  # Button
                    label = button_data.get('label', '')
                    url = button_data.get('url', '')
                    
                    if url:
                        # Create link button
                        button = discord.ui.Button(
                            label=label,
                            style=discord.ButtonStyle.link,
                            url=url,
                            row=row
                        )
                        view.add_item(button)
                        col += 1
                        # Discord allows max 5 buttons per row
                        if col >= 5:
                            col = 0
                            row += 1
            row += 1  # Move to next row for next action row
    
    return view
