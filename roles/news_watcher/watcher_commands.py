import discord
import asyncio
import sys
import os
import sqlite3
import json
from datetime import datetime
from agent_logging import get_logger

from .db_role_news_watcher import get_news_watcher_db_instance
from .watcher_messages import get_message
from discord_bot.discord_utils import send_dm_or_channel

logger = get_logger('watcher_commands')


def _get_watcher_description_text(key: str, fallback: str) -> str:
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "agent_config.json")
        with open(config_path, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        personality_rel = agent_cfg.get("personality", "")
        
        # First try to get from news_watcher descriptions
        news_watcher_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            os.path.dirname(personality_rel),
            "descriptions",
            "news_watcher.json",
        )
        
        try:
            with open(news_watcher_path, encoding="utf-8") as f:
                news_watcher_descriptions = json.load(f)
                value = news_watcher_descriptions.get(key)
                if value:
                    # Apply placeholder replacement for bot display name
                    from discord_bot.canvas.content import _bot_display_name
                    return str(value).replace("{_bot_display_name}", _bot_display_name)
        except FileNotFoundError:
            pass  # Continue to fallback
        
        # Fallback to old descriptions.json
        descriptions_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            os.path.dirname(personality_rel),
            "descriptions.json",
        )
        with open(descriptions_path, encoding="utf-8") as f:
            descriptions = json.load(f).get("discord", {}).get("watcher_messages", {})
        value = descriptions.get(key)
        return str(value) if value else fallback
    except Exception:
        return fallback

class WatcherCommands:
    """Discord commands to manage the News Watcher role."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_watcher = None
    
    def _get_db(self, server_name: str = None):
        """Get (and cache) the watcher DB instance."""
        if not self.db_watcher:
            # Use provided server_name or fall back to active server
            if server_name:
                self.db_watcher = get_news_watcher_db_instance(server_name)
            else:
                from agent_db import get_active_server_name
                server_name = get_active_server_name()
                if not server_name:
                    raise RuntimeError("No active server configured for watcher commands")
                self.db_watcher = get_news_watcher_db_instance(server_name)
        return self.db_watcher

    def _normalize_category(self, category: str | None) -> str | None:
        if category is None:
            return None

        cat = str(category).strip().lower()
        if not cat:
            return cat

        return cat
    
    async def cmd_feeds(self, message, args):
        """Show all available feeds."""
        try:
            db = self._get_db()
            feeds = db.get_active_feeds()
            
            if not feeds:
                await message.channel.send(get_message('error_no_hay_feeds'))
                return
            
            embed = discord.Embed(
                title=_get_watcher_description_text('feeds_available_title', get_message('feeds_available_title')),
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            feeds_by_category = {}
            for feed in feeds:
                feed_id, name, url, category, country, language, priority, keywords, feed_type = feed
                if category not in feeds_by_category:
                    feeds_by_category[category] = []
                feeds_by_category[category].append({
                    'id': feed_id, 'name': name, 'url': url,
                    'country': country, 'language': language, 'priority': priority, 'feed_type': feed_type
                })
            
            for category, feeds_cat in feeds_by_category.items():
                section_value = ""
                for feed in feeds_cat:
                    country_flag = self._get_country_flag(feed['country'])
                    section_value += f"**{feed['name']}** ({feed['id']}) {country_flag}\n"
                    section_value += f"Priority: {feed['priority']} | Language: {feed['language'].upper()}\n\n"
                
                # Direct mapping from Spanish to English
                category_names = {
                    'economy': 'Economy',
                    'technology': 'Technology', 
                    'general': 'General',
                    'international': 'International',
                    'crypto': 'Crypto'
                }
                name = category_names.get(category, category.title())
                embed.add_field(
                    name=f"📂 {name} ({len(feeds_cat)} feeds)",
                    value=section_value,
                    inline=False
                )
            
            embed.set_footer(text=f"Use !watcher subscribe <category> [feed_id|all]\nNo feed_id: first feed | 'all': all feeds")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_feeds: {e}")
            await message.channel.send(get_message('error_general', error=e))
    
    async def cmd_reset(self, message, args):
        """Completely clear all user subscriptions."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Check if has any subscription
            current_type = db.check_user_subscription_type(user_id)
            
            if not current_type:
                await message.channel.send(get_message('error_no_subscriptions'))
                return
            
            # Check if confirmation
            if args and args[0].lower() == "confirm":
                # Execute confirmed reset
                cancelled = 0
                
                if current_type == 'flat':
                    # Cancel flat subscriptions
                    subscriptions = db.get_user_subscriptions(user_id)
                    for category, feed_id, _ in subscriptions:
                        if db.cancel_category_subscription(user_id, category, feed_id):
                            cancelled += 1
                            
                elif current_type == 'keywords':
                    # Cancel keyword subscriptions
                    subscriptions = db.get_user_keyword_subscriptions(user_id)
                    for category, _, _ in subscriptions:
                        if db.cancel_user_keyword_subscription(user_id, category):
                            cancelled += 1
                            
                elif current_type == 'ai':
                    # Cancel AI subscriptions
                    subscriptions = db.get_user_ai_subscriptions(user_id)
                    for category, feed_id, _ in subscriptions:
                        if db.cancel_category_subscription(user_id, category, feed_id):
                            cancelled += 1
                
                if cancelled > 0:
                    await message.channel.send(f"✅ **RESET COMPLETED**\n"
                                             f"Removed {cancelled} subscription(s) of type '{current_type}'.\n"
                                             f"You can now subscribe to a new type of alerts.")
                else:
                    await message.channel.send(get_message('error_no_subscriptions'))
                return
            
            # If not confirmed, show confirmation message
            await message.channel.send(
                f"⚠️ **CONFIRMATION REQUIRED**\n"
                f"You are about to delete ALL of your '{current_type}' subscriptions.\n"
                f"This action cannot be undone.\n"
                f"To confirm, use: `!watcher reset confirm`"
            )
            
        except Exception as e:
            logger.exception(f"Error in cmd_reset: {e}")
            await message.channel.send(get_message('error_general', error="processing reset request"))

    async def cmd_categories(self, message, args):
        """Show available categories."""
        try:
            db = self._get_db()
            categories = db.get_available_categories()
            
            if not categories:
                await message.channel.send(get_message('error_no_hay_categorias'))
                return
            
            embed = discord.Embed(
                title="📂 Available Categories",
                description=f"There are {len(categories)} categories with active feeds:",
                color=discord.Color.blue()
            )
            
            for category, count in categories:
                icon = self._get_category_icon(category)
                # Direct mapping from Spanish to English
                category_names = {
                    'economy': 'Economy',
                    'technology': 'Technology', 
                    'general': 'General',
                    'international': 'International',
                    'crypto': 'Crypto'
                }
                name = category_names.get(category, category.title())
                embed.add_field(
                    name=f"{icon} {name}",
                    value=f"{count} available feeds",
                    inline=True
                )
            
            embed.set_footer(text="Use !watcher subscribe <category> [feed_id|all]\nNo feed_id: first feed | 'all': all feeds")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_categories: {e}")
            await message.channel.send(get_message('error_general', error=e))

    async def cmd_subscribe(self, message, args):
        """Subscribe the user to a category or a specific feed (flat subscription)."""
        if not args:
            await message.channel.send(get_message('uso_suscribir'))
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            category = self._normalize_category(args[0])
            feed_id = None
            
            # Validate category and feed
            feed_id = await self._validate_category_and_feed(message, category, args, db)
            if feed_id is None and len(args) > 1:  # Validation failed
                return
            
            # Handle flat subscription using unified handler
            await self._handle_flat_subscribe(message, user_id, category, feed_id)
                
        except Exception as e:
            logger.exception(f"Error in cmd_subscribe: {e}")
            await message.channel.send(get_message('error_processing_subscription'))

    async def _validate_category_and_feed(self, message, category: str, args: list, db) -> int | None:
        """Validate category and optional feed_id, returns feed_id or None."""
        # Check if it's a specific feed_id or 'all'
        if len(args) > 1:
            if args[1].lower() == 'all':
                # 'all' parameter - subscribe to all feeds in category
                feeds = db.get_active_feeds(category)
                if not feeds:
                    await message.channel.send(f"❌ No feeds found in category '{category}'")
                    return None
                # Return special value to indicate all feeds
                return 'all'
            else:
                try:
                    feed_id = int(args[1])
                    # Get feeds in this category to validate category-relative indexing
                    feeds = db.get_active_feeds(category)
                    if 1 <= feed_id <= len(feeds):
                        # Convert category-relative index to absolute database ID
                        # feed_id is 1-based relative to category, feeds list is 0-based
                        absolute_feed_id = feeds[feed_id - 1][0]  # feeds[0] is the database ID
                        logger.info(f"Converting category-relative feed ID {feed_id} to absolute database ID {absolute_feed_id} for category '{category}'")
                        return absolute_feed_id
                    else:
                        await message.channel.send(f"❌ Feed ID {feed_id} not found in category '{category}'. Available: 1-{len(feeds)}")
                        return None
                except ValueError:
                    await message.channel.send(get_message('feed_id_must_be_number'))
                    return None
        else:
            # Verify category exists
            categories = db.get_available_categories()
            if not any(cat[0] == category for cat in categories):
                await message.channel.send(get_message('error_categoria_no_encontrada', category=category))
                return None
            
            # NEW BEHAVIOR: Subscribe to first available feed instead of all feeds
            feeds = db.get_active_feeds(category)
            if feeds:
                first_feed_id = feeds[0][0]  # Get database ID of first feed (highest priority)
                logger.info(f"No feed specified, subscribing to first available feed {first_feed_id} in category '{category}'")
                return first_feed_id
            else:
                await message.channel.send(f"❌ No feeds available in category '{category}'")
                return None

    async def cmd_unsubscribe(self, message, args):
        """Cancel subscription by number (from list) or by category/feed (legacy)."""
        if not args:
            await message.channel.send(get_message('uso_cancelar'))
            await message.channel.send("💡 Use `!watcher subscriptions` to see numbered list")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Check if first argument is a number (new method)
            try:
                list_number = int(args[0])
                await self._unsubscribe_by_number(message, user_id, list_number)
                return
            except ValueError:
                # Not a number, use legacy category-based method
                await self._unsubscribe_by_category(message, user_id, args)
                
        except Exception as e:
            logger.exception(f"Error in cmd_unsubscribe: {e}")
            await message.channel.send(get_message('error_cancelacion'))

    async def _unsubscribe_by_number(self, message, user_id: str, list_number: int):
        """Unsubscribe by numbered list position."""
        try:
            db = self._get_db()
            
            # Get all subscriptions (same logic as cmd_subscriptions)
            all_subscriptions = []
            
            # Get flat subscriptions
            flat_subs = db.get_user_subscriptions(user_id)
            for category, feed_id, fecha in flat_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'flat',
                    'date': fecha
                })
            
            # Get keyword subscriptions
            keyword_subs = db.get_user_keyword_subscriptions(user_id)
            for category, feed_id, keywords in keyword_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'keyword',
                    'keywords': keywords
                })
            
            # Get AI subscriptions
            ai_subs = db.get_user_ai_subscriptions(user_id)
            for category, feed_id, premises in ai_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'general',
                    'premises': premises
                })
            
            # Validate list number
            if list_number < 1 or list_number > len(all_subscriptions):
                await message.channel.send(f"❌ Invalid number. Use 1-{len(all_subscriptions)} or see list with `!watcher subscriptions`")
                return
            
            # Get subscription to cancel
            sub_to_cancel = all_subscriptions[list_number - 1]
            category = sub_to_cancel['category']
            feed_id = sub_to_cancel['feed_id']
            method = sub_to_cancel['method']
            
            # Cancel based on method type
            success = False
            if method == 'flat':
                success = db.cancel_category_subscription(user_id, category, feed_id)
            elif method == 'keyword':
                success = db.cancel_user_keyword_subscription(user_id, category)
            elif method == 'general':
                success = db.cancel_category_subscription(user_id, category, feed_id)
            
            if success:
                feed_info = f"Feed {feed_id}" if feed_id else "all feeds"
                await message.channel.send(f"✅ Unsubscribed from #{list_number} - {category.title()} ({feed_info})")
            else:
                await message.channel.send(get_message('no_subscription_to_cancel'))
                
        except Exception as e:
            logger.exception(f"Error in _unsubscribe_by_number: {e}")
            await message.channel.send(get_message('error_cancelacion'))

    async def _unsubscribe_by_category(self, message, user_id: str, args):
        """Legacy unsubscribe by category/feed method."""
        category = self._normalize_category(args[0])
        feed_id = None
        
        if len(args) > 1:
            try:
                feed_id = int(args[1])
            except ValueError:
                await message.channel.send(get_message('feed_id_must_be_number'))
                return
        
        db = self._get_db()
        
        if db.cancel_category_subscription(user_id, category, feed_id):
            if feed_id:
                await message.channel.send(f"✅ Unsubscribed from {category} (Feed {feed_id})")
            else:
                await message.channel.send(f"✅ Unsubscribed from {category}")
        else:
            await message.channel.send(get_message('no_suscripcion_cancelar'))
    
    async def cmd_general_unsubscribe(self, message, args):
        """Cancel an AI (premises-based) subscription for a category/feed."""
        if not args:
            await message.channel.send(get_message('uso_general_unsubscribe'))
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            category = self._normalize_category(args[0])
            feed_id = None
            
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send(get_message('feed_id_must_be_number'))
                    return
            
            if db.cancel_category_subscription(user_id, category, feed_id):
                if feed_id:
                    await message.channel.send(get_message('subscription_cancelled_feed', feed_id=feed_id, category=category))
                else:
                    await message.channel.send(get_message('subscription_cancelled_category', category=category))
            else:
                await message.channel.send(get_message('no_active_ai_subscription'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_general_unsubscribe: {e}")
            await message.channel.send(get_message('error_canceling_ai_subscription'))
    
    async def cmd_status(self, message, args):
        """Show the user's active subscription type and details."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Get subscription counts
            user_count = db.count_user_subscriptions(user_id)
            server_count = db.count_server_subscriptions()
            can_user_sub, user_limit_msg = db.can_user_subscribe(user_id)
            
            # Check current subscription type
            current_subscription_type = db.check_user_subscription_type(user_id)
            logger.info(f"DEBUG: Subscription type for {user_id}: {current_subscription_type}")
            
            if not current_subscription_type:
                embed = discord.Embed(
                    title="📊 **Subscription Status**",
                    description="You have no active subscriptions",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="📈 **Your Usage**",
                    value=f"Subscriptions: {user_count}/3\n{user_limit_msg}",
                    inline=False
                )
                embed.add_field(
                    name="🌐 **Server Usage**",
                    value=f"Total subscriptions: {server_count}/15",
                    inline=False
                )
                embed.set_footer(text="Use !watcher subscribe <category> to subscribe")
                await message.channel.send(embed=embed)
                return
            
            # Show information according to type
            if current_subscription_type == 'flat':
                subscriptions = db.get_user_subscriptions(user_id)
                if subscriptions:
                    embed = discord.Embed(
                        title="📰 Active Flat Subscription",
                        description="You receive **all news** (with generated opinion)",
                        color=discord.Color.blue()
                    )
                    
                    for i, (category, feed_id, subscribed_at) in enumerate(subscriptions, 1):
                        if feed_id:
                            embed.add_field(
                                name=f"#{i} - {category}",
                                value=f"Feed ID: {feed_id}\nSince: {subscribed_at}",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"#{i} - {category}",
                                value=f"Entire category\nSince: {subscribed_at}",
                                inline=False
                            )
                    
                    embed.add_field(
                        name="📈 **Your Usage**",
                        value=f"Subscriptions: {user_count}/3\n{user_limit_msg}",
                        inline=False
                    )
                    embed.add_field(
                        name="🌐 **Server Usage**",
                        value=f"Total subscriptions: {server_count}/15",
                        inline=False
                    )
                    embed.set_footer(text="Use !watcher unsubscribe <category> to cancel")
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send(get_message('no_active_flat_subscription'))
                    
            elif current_subscription_type == 'keywords':
                subscriptions = db.get_user_keyword_subscriptions(user_id)
                if subscriptions:
                    embed = discord.Embed(
                        title="🔍 Active Keywords Subscription",
                        description="You receive **filtered news** matching your keywords",
                        color=discord.Color.green()
                    )
                    
                    for i, (category, feed_id, keywords) in enumerate(subscriptions, 1):
                        if feed_id:
                            embed.add_field(
                                name=f"#{i} - {category} (Feed {feed_id})",
                                value=f"Keywords: {keywords}",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"#{i} - {category}",
                                value=f"Keywords: {keywords}",
                                inline=False
                            )
                    
                    embed.add_field(
                        name="📈 **Your Usage**",
                        value=f"Subscriptions: {user_count}/3\n{user_limit_msg}",
                        inline=False
                    )
                    embed.add_field(
                        name="🌐 **Server Usage**",
                        value=f"Total subscriptions: {server_count}/15",
                        inline=False
                    )
                    embed.set_footer(text="Use !watcher unsubscribe <category> to cancel")
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send(get_message('no_active_keyword_subscription'))
                    
            elif current_subscription_type == 'ai':
                subscriptions = db.get_user_ai_subscriptions(user_id)
                logger.info(f"DEBUG: AI subscriptions found: {subscriptions}")
                if subscriptions:
                    embed = discord.Embed(
                        title="🤖 Active AI Subscription",
                        description="You receive **critical news** analyzed using your premises",
                        color=discord.Color.purple()
                    )
                    
                    for i, (category, feed_id, premises) in enumerate(subscriptions, 1):
                        if feed_id:
                            embed.add_field(
                                name=f"#{i} - {category} (Feed {feed_id})",
                                value=f"Premises configured: {len(premises.split(','))}",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"#{i} - {category}",
                                value=f"Premises configured: {len(premises.split(','))}",
                                inline=False
                            )
                    
                    embed.add_field(
                        name="📈 **Your Usage**",
                        value=f"Subscriptions: {user_count}/3\n{user_limit_msg}",
                        inline=False
                    )
                    embed.add_field(
                        name="🌐 **Server Usage**",
                        value=f"Total subscriptions: {server_count}/15",
                        inline=False
                    )
                    embed.set_footer(text="Use !watcher general unsubscribe <category> to cancel")
                    await message.channel.send(embed=embed)
                else:
                    logger.warning(f"DEBUG: Inconsistency detected - type='ai' but no AI subscriptions found for user {user_id}")
                    await message.channel.send(get_message('no_active_ai_subscription'))
                    
        except Exception as e:
            logger.exception(f"Error in cmd_status: {e}")
            await message.channel.send(get_message('error_mostrando_estado'))
    
    async def cmd_categories(self, message, args):
        """Show available categories with active feeds."""
        try:
            db = self._get_db()
            categories = db.get_available_categories()
            
            if not categories:
                await message.channel.send(get_message('error_no_hay_categorias'))
                return
            
            embed = discord.Embed(
                title="📂 Available Categories",
                description=f"There are {len(categories)} categories with active feeds:",
                color=discord.Color.blue()
            )
            
            for category, count in categories:
                icon = self._get_category_icon(category)
                # Direct mapping from category key to display name
                category_names = {
                    'economy': 'Economy',
                    'technology': 'Technology', 
                    'general': 'General',
                    'international': 'International',
                    'crypto': 'Crypto',
                    'gaming': 'Gaming',
                    'patch_notes': 'Patch Notes'
                }
                name = category_names.get(category, category.title())
                embed.add_field(
                    name=f"{icon} {name}",
                    value=f"{count} available feeds",
                    inline=True
                )
            
            embed.set_footer(text="Use !watcher feeds to see feeds in each category")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_categories: {e}")
            await message.channel.send(get_message('error_mostrando_categorys'))
    
    async def cmd_add_feed(self, message, args):
        """Add a new feed (admins only)."""
        if len(args) < 3:
            await message.channel.send(get_message('usage_agregar_feed'))
            return
        
        # Check admin permissions
        if not message.author.guild_permissions.administrator:
            await message.channel.send(get_message('solo_admins_feeds'))
            return
        
        try:
            db = self._get_db()
            name = args[0]
            url = args[1]
            category = args[2].lower()
            country = args[3] if len(args) > 3 else None
            language = args[4] if len(args) > 4 else 'es'
            
            if db.add_feed(name, url, category, country, language):
                await message.channel.send(f"✅ Feed '{name}' added to category '{category}'")
            else:
                await message.channel.send(get_message('error_add_feed'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_add_feed: {e}")
            await message.channel.send(get_message('error_agregar_feed'))
    
    async def cmd_general_subscribe(self, message, args):
        """Subscribe with AI (premises-based) to a category/feed."""
        if not args:
            await message.channel.send(get_message('uso_general'))
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            category = self._normalize_category(args[0])
            
            # Validate category and feed
            feed_id = await self._validate_category_and_feed(message, category, args, db)
            if feed_id is None and len(args) > 1:  # Validation failed
                return
            
            # Handle AI subscription using unified handler
            await self._handle_general_subscribe(message, user_id, category, feed_id)
                
        except Exception as e:
            logger.exception(f"Error in cmd_general_subscribe: {e}")
            await message.channel.send(get_message('error_procesando_suscripcion_ia'))
    
    async def cmd_keywords_subscribe(self, message, args):
        """Keywords command.

        Supported forms:
        - !watcher keywords "kw1,kw2" [category] [feed_id]
        - !watcher keywords add <keyword>
        - !watcher keywords list
        - !watcher keywords mod <number> "new keyword"
        - !watcher keywords subscribe <category> [feed_id]  (use saved keywords)
        - !watcher keywords unsubscribe <category>
        """

        if not args:
            await message.channel.send(
                "📝 Usage: `!watcher keywords \"kw1,kw2\" [category] [feed_id]`\n"
                "Or: `!watcher keywords add|list|mod|subscribe|unsubscribe ...`"
            )
            return

        sub = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []

        if sub == "add":
            await self.cmd_keywords_add(message, subargs)
            return
        if sub == "list":
            await self.cmd_keywords_list(message, subargs)
            return
        if sub == "mod":
            await self.cmd_keywords_mod(message, subargs)
            return
        if sub == "subscribe":
            await self.cmd_keywords_subscribe_existing(message, subargs)
            return
        if sub == "unsubscribe":
            await self.cmd_keywords_unsubscribe(message, subargs)
            return

        # Default: treat first arg as "kw1,kw2" payload
        try:
            db = self._get_db()
            user_id = str(message.author.id)

            keywords = args[0].strip('"\'')
            category = None
            feed_id = None

            if len(args) > 1:
                category = self._normalize_category(args[1])
                if len(args) > 2:
                    try:
                        feed_id = int(args[2])
                        feeds = db.get_active_feeds(category)
                        feed_exists = any(f[0] == feed_id for f in feeds)
                        if not feed_exists:
                            await message.channel.send(get_message('feed_id_not_found', feed_id=feed_id, category=category))
                            return
                    except ValueError:
                        await message.channel.send(get_message('feed_id_must_be_number'))
                        return
                else:
                    categories = db.get_available_categories()
                    if not any(cat[0] == category for cat in categories):
                        await message.channel.send(get_message('error_categoria_no_encontrada', category=category))
                        return

            if not keywords:
                await message.channel.send(get_message('debes_proporcionar_palabras'))
                return

            current_subscription_type = db.check_user_subscription_type(user_id)
            if current_subscription_type == 'keywords':
                await message.channel.send(get_message('already_have_keywords_subscription'))
                return
            if current_subscription_type in ['flat', 'ai']:
                await message.channel.send(
                    f"⚠️ You have an active '{current_subscription_type}' subscription. You can only have ONE subscription type at a time. Use `!watcher reset` to clear all subscriptions."
                )
                return

            if db.subscribe_keywords(user_id, keywords, None, category, feed_id):
                if feed_id:
                    await message.channel.send(f"🔍 **Keywords subscription** to feed {feed_id} in '{category}' - Searching: '{keywords}'")
                elif category:
                    await message.channel.send(f"🔍 **Keywords subscription** to '{category}' - Searching: '{keywords}'")
                else:
                    await message.channel.send(f"🔍 **Global keywords subscription** - Searching: '{keywords}'")
            else:
                await message.channel.send(get_message('error_suscribiendo_palabras_clave'))

        except Exception as e:
            logger.exception(f"Error in cmd_keywords_subscribe: {e}")
            await message.channel.send(get_message('error_suscribiendo_palabras_clave'))
    
    async def cmd_keywords_add(self, message, args):
        """Add a keyword to the user's saved keyword list."""
        if not args:
            await message.channel.send(get_message('uso_keywords_add'))
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            keyword = args[0]
            
            # Get current keywords
            current_keywords = db.get_user_keywords(user_id)
            
            if not current_keywords:
                # If there are no keywords yet, create a new list
                if db.subscribe_keywords(user_id, keyword, None, None, None):
                    await message.channel.send(get_message('keyword_added_list', keyword=keyword, keywords=keyword))
                else:
                    await message.channel.send(get_message('error_adding_keyword'))
            else:
                # Add to the existing list
                keywords_list = current_keywords.split(',')
                if keyword in keywords_list:
                    await message.channel.send(f"ℹ️ Keyword '{keyword}' is already in your list")
                    return
                
                keywords_list.append(keyword)
                updated_keywords = ','.join(keywords_list)
                
                if db.update_user_keywords(user_id, updated_keywords):
                    await message.channel.send(get_message('keyword_added_list', keyword=keyword, keywords=updated_keywords))
                else:
                    await message.channel.send(get_message('error_adding_keyword'))
                    
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_add: {e}")
            await message.channel.send(get_message('error_adding_keyword'))
    
    async def cmd_keywords_add_canvas(self, message, args):
        """Canvas-compatible version of cmd_keywords_add that returns a string."""
        if not args:
            return "❌ No keyword provided"
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            keyword = args[0]
            
            # Get current keywords
            current_keywords = db.get_user_keywords(user_id)
            
            if not current_keywords:
                # If there are no keywords yet, create a new list
                if db.subscribe_keywords(user_id, keyword, None, None, None):
                    return f"✅ Keyword '{keyword}' added. Current list: {keyword}"
                else:
                    return "❌ Error adding keyword"
            else:
                # Add to the existing list
                keywords_list = current_keywords.split(',')
                if keyword in keywords_list:
                    return f"ℹ️ Keyword '{keyword}' is already in your list"
                
                keywords_list.append(keyword)
                updated_keywords = ','.join(keywords_list)
                
                if db.update_user_keywords(user_id, updated_keywords):
                    return f"✅ Keyword '{keyword}' added. Current list: {updated_keywords}"
                else:
                    return "❌ Error adding keyword"
                    
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_add_canvas: {e}")
            return "❌ Error adding keyword"
    
    async def cmd_keywords_list(self, message, args):
        """List the user's saved keywords."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            keywords = db.get_user_keywords(user_id)
            
            if not keywords:
                await message.channel.send(get_message('error_no_hay_palabras_clave'))
                return
            
            keywords_list = keywords.split(',')
            
            embed = discord.Embed(
                title="🔍 Your Keywords",
                description=f"You have {len(keywords_list)} configured keywords:",
                color=discord.Color.blue()
            )
            
            for i, keyword in enumerate(keywords_list, 1):
                embed.add_field(name=f"#{i}", value=keyword, inline=False)
            
            embed.set_footer(text="Use !watcher keywords add <keyword> to add more")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_list: {e}")
            await message.channel.send(get_message('error_obteniendo_palabras_clave'))
    
    async def cmd_keywords_mod(self, message, args):
        """Modify a saved keyword by index."""
        if len(args) < 2:
            await message.channel.send("📝 Usage: `!watcher keywords mod <number> <keyword>`")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            try:
                index = int(args[0]) - 1  # Convert to 0-based index
                if index < 0:
                    raise ValueError
            except ValueError:
                await message.channel.send(get_message('feed_id_must_be_number'))
                return
            
            new_keyword = args[1].strip('"\'')
            
            keywords = db.get_user_keywords(user_id)
            if not keywords:
                await message.channel.send(get_message('error_no_hay_palabras_clave'))
                return
            
            keywords_list = keywords.split(',')
            
            if index >= len(keywords_list):
                await message.channel.send(f"❌ You do not have keyword #{index + 1}. You have {len(keywords_list)} keywords")
                return
            
            old_keyword = keywords_list[index]
            keywords_list[index] = new_keyword
            updated_keywords = ','.join(keywords_list)
            
            if db.update_user_keywords(user_id, updated_keywords):
                await message.channel.send(f"✅ Keyword #{index + 1} updated: '{old_keyword}' → '{new_keyword}'")
            else:
                await message.channel.send(get_message('error_adding_keyword'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_mod: {e}")
            await message.channel.send(get_message('error_adding_keyword'))
    
    async def cmd_keywords_subscribe_existing(self, message, args):
        """Subscribe to a category/feed using the user's existing saved keywords."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher keywords subscribe <category> [feed_id|all]`")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            category = self._normalize_category(args[0])
            
            # Ensure the user has saved keywords
            keywords = db.get_user_keywords(user_id)
            if not keywords:
                await message.channel.send(get_message('error_no_hay_palabras_clave'))
                return
            
            # Validate category and feed using the unified validation function
            feed_id = await self._validate_category_and_feed(message, category, args, db)
            if feed_id is None and len(args) > 1:  # Validation failed
                return
            
            # Check current subscription type of the user
            current_subscription_type = db.check_user_subscription_type(user_id)
            
            # If already has keywords subscription, block
            if current_subscription_type == 'keywords':
                await message.channel.send(get_message('already_have_keywords_subscription'))
                return
            
            # If has other subscription types, block
            if current_subscription_type in ['flat', 'ai']:
                await message.channel.send(
                    f"⚠️ You have an active '{current_subscription_type}' subscription. You can only have ONE subscription type at a time. Use `!watcher reset` to clear all subscriptions."
                )
                return
            
            # Handle keyword subscription using unified handler
            await self._handle_keyword_subscribe(message, user_id, category, feed_id)
                
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_subscribe_existing: {e}")
            await message.channel.send(get_message('error_suscribiendo_palabras_clave'))
    
    async def cmd_keywords_subscriptions(self, message, args):
        """Show active keyword subscriptions."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            subscriptions = db.get_user_keyword_subscriptions(user_id)
            
            if not subscriptions:
                await message.channel.send(get_message('error_no_hay_palabras_clave'))
                return
            
            embed = discord.Embed(
                title="🔍 Keyword Subscriptions",
                description=f"You have {len(subscriptions)} active subscriptions:",
                color=discord.Color.blue()
            )
            
            for i, (category, feed_id, keywords) in enumerate(subscriptions, 1):
                if feed_id:
                    embed.add_field(
                        name=f"#{i} - {category} (Feed {feed_id})",
                        value=f"Keywords: {keywords}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"#{i} - {category}",
                        value=f"Keywords: {keywords}",
                        inline=False
                    )
            
            embed.set_footer(text="Use `!watcher keywords unsubscribe <category>` to cancel")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_subscriptions: {e}")
            await message.channel.send(get_message('error_obteniendo_estado'))
    
    async def cmd_keywords_unsubscribe(self, message, args):
        """Cancel a user's keywords subscription for a category."""
        if not args:
            await message.channel.send(get_message('usage_cancelar_palabras'))
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            category = self._normalize_category(args[0])
            
            if db.cancel_user_keyword_subscription(user_id, category):
                await message.channel.send(get_message('keywords_subscription_cancelled', keywords=category))
            else:
                await message.channel.send(get_message('no_active_keyword_subscription'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_unsubscribe: {e}")
            await message.channel.send(get_message('error_canceling_keywords'))
    
    async def cmd_keywords_cancel(self, message, args):
        """Cancel a keywords subscription."""
        if not args:
            await message.channel.send(get_message('usage_cancelar_palabras'))
            return
        
        try:
            db = self._get_db()
            keywords = " ".join(args).strip('"\'')
            
            if db.cancel_keyword_subscription(str(message.author.id), keywords):
                await message.channel.send(get_message('keywords_subscription_cancelled', keywords=keywords))
            else:
                await message.channel.send(get_message('no_keyword_subscription'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_cancel: {e}")
            await message.channel.send(get_message('error_canceling_keywords'))
    
    async def cmd_mixed_subscribe(self, message, args):
        """Subscribe to specialized + general feeds in a category."""
        if not args:
            await message.channel.send(get_message('usage_mixto'))
            return
        
        try:
            db = self._get_db()
            category = self._normalize_category(args[0])
            
            # Verify that the category exists
            categories = db.get_available_categories()
            if not any(cat[0] == category for cat in categories):
                await message.channel.send(get_message('error_categoria_no_encontrada', category=category))
                return
            
            # Subscribe to specialized feeds (without feed_id)
            if db.subscribe_user_category(str(message.author.id), category):
                # Also subscribe to general feeds if they exist
                feeds = db.get_active_feeds(category)
                general_feeds = [f for f in feeds if f[8] == 'general']
                
                for feed in general_feeds:
                    db.subscribe_user_category(str(message.author.id), category, feed[0])
                
                if general_feeds:
                    await message.channel.send(f"✅ Subscribed to mixed coverage for '{category}' (specialized + general)")
                else:
                    await message.channel.send(f"✅ Subscribed to specialized coverage for '{category}'")
            else:
                await message.channel.send("❌ Error creating mixed subscription")
                
        except Exception as e:
            logger.exception(f"Error in cmd_mixed_subscribe: {e}")
            await message.channel.send("❌ Error subscribing to mixed coverage")
    
    async def cmd_keywords_status(self, message, args):
        """Show the user's keyword subscriptions."""
        try:
            db = self._get_db()
            subscriptions = db.get_keyword_subscriptions(str(message.author.id))
            
            if not subscriptions:
                await message.channel.send(get_message('error_no_hay_palabras_clave'))
                return
            
            embed = discord.Embed(
                title=f"🔍 Your Keywords - {message.author.display_name}",
                color=discord.Color.dark_blue(),
                timestamp=datetime.now()
            )
            
            description = ""
            for keywords, subscribed_at in subscriptions:
                description += f"🔑 **{keywords}**\n"
                description += f"📅 Subscribed: {subscribed_at[:10]}\n\n"
            
            embed.description = description
            embed.set_footer(text="Use `!watcher keywords cancel \"keywords\"` to cancel")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_status: {e}")
            await message.channel.send("❌ Error getting keywords")
    
    async def cmd_channel_keywords(self, message, args):
        """Subscribe the current channel to keywords."""
        if not args:
            await message.channel.send(get_message('usage_canal_palabras'))
            return

        if args and args[0].lower() == "unsubscribe":
            await self.cmd_channel_keywords_unsubscribe(message, args[1:] if len(args) > 1 else [])
            return
        
        # Check permissions
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send(get_message('permisos_gestionar_canales'))
            return
        
        try:
            db = self._get_db()
            keywords = " ".join(args).strip('"\'')
            channel = message.channel
            
            if db.subscribe_keywords(str(message.author.id), keywords, str(channel.id)):
                await message.channel.send(get_message('channel_keywords_subscription_successful', keywords=keywords))
            else:
                await message.channel.send(get_message('error_subscribing_channel_keywords'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_keywords: {e}")
            await message.channel.send(get_message('error_suscribir_canal_palabras'))
    
    async def cmd_channel_keywords_unsubscribe(self, message, args):
        """Cancel a channel keywords subscription."""
        if not args:
            await message.channel.send(get_message('usage_canal_palabras'))
            return
        
        # Check admin permissions
        if not message.author.guild_permissions.administrator:
            await message.channel.send(get_message('permissions_cancel_channel'))
            return
        
        try:
            db = self._get_db()
            channel = message.channel
            keywords = " ".join(args).strip('"\'')
            
            if db.cancel_keyword_subscription(str(channel.id), keywords):
                await message.channel.send(get_message('keywords_subscription_cancelled', keywords=keywords))
            else:
                await message.channel.send(get_message('error_canceling_keywords'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_keywords_unsubscribe: {e}")
            await message.channel.send(get_message('error_canceling_keywords'))
    
    # ===== CHANNEL PREMISES COMMANDS =====
    
    async def cmd_channel_premises(self, message, args):
        """Channel premises management command."""
        if not args:
            # If no subcommand is provided, show the default list
            await self.cmd_channel_premises_list(message, args)
            return
        
        subcommand = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []
        
        if subcommand == 'list':
            await self.cmd_channel_premises_list(message, subargs)
        elif subcommand == 'add':
            await self.cmd_channel_premises_add(message, subargs)
        elif subcommand == 'mod':
            await self.cmd_channel_premises_mod(message, subargs)
        elif subcommand == 'del':
            await self.cmd_channel_premises_del(message, subargs)
        else:
            await message.channel.send(f"❌ Subcommand '{subcommand}' not recognized. Use: list, add, mod, del")
    
    async def cmd_channel_premises_list(self, message, args):
        """List channel premises (custom or global)."""
        # Check admin permissions
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can view channel premises")
            return
        
        try:
            db = self._get_db()
            channel = message.channel
            channel_id = str(channel.id)
            
            # Get premises with context
            premises, context = db.get_channel_premises_with_context(channel_id)
            
            if not premises:
                await message.channel.send(get_message('no_premisas_canal'))
                return
            
            embed = discord.Embed(
                title=f"🎯 Channel Premises #{channel.name} ({context.title()})",
                description="These are the conditions that make news **CRITICAL** for this channel:",
                color=discord.Color.blue() if context == "custom" else discord.Color.red(),
                timestamp=datetime.now()
            )
            
            for i, premise in enumerate(premises, 1):
                embed.add_field(
                    name=f"Premise #{i}",
                    value=f"📍 {premise}",
                    inline=False
                )
            
            if context == "custom":
                embed.set_footer(text="Use !watcherchannel premises add/mod to manage channel premises")
            else:
                embed.set_footer(text="Use !watcherchannel premises add to create custom channel premises")
            
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_list: {e}")
            await message.channel.send(get_message('error_listando_premisas_canal'))
    
    async def cmd_channel_premises_add(self, message, args):
        """Add a new premise to the channel (max 7)."""
        # Check admin permissions
        if not message.author.guild_permissions.administrator:
            await message.channel.send(get_message('error_permisos'))
            return
        
        if not args:
            await message.channel.send(get_message('usage_canal_premises_add'))
            return
        
        try:
            db = self._get_db()
            channel = message.channel
            channel_id = str(channel.id)
            new_premise = " ".join(args).strip('"\'')
            
            if not new_premise:
                await message.channel.send(get_message('debes_proporcionar_premisa'))
                return
            
            success, message_text = db.add_channel_premise(channel_id, new_premise)
            
            if success:
                await message.channel.send(f"✅ {message_text}")
            else:
                await message.channel.send(f"❌ {message_text}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_add: {e}")
            await message.channel.send(get_message('error_agregar_feed'))
    
    async def cmd_channel_premises_mod(self, message, args):
        """Modify a specific channel premise by index."""
        # Check admin permissions
        if not message.author.guild_permissions.administrator:
            await message.channel.send(get_message('error_permisos'))
            return
        
        if len(args) < 2:
            await message.channel.send(get_message('usage_canal_premises_mod'))
            return
        
        try:
            db = self._get_db()
            channel = message.channel
            channel_id = str(channel.id)
            
            # Parse number
            try:
                index = int(args[0])
            except ValueError:
                await message.channel.send("❌ The number must be an integer.")
                return
            
            new_premise = " ".join(args[1:]).strip('"\'')
            
            if not new_premise:
                await message.channel.send("❌ You must provide the new premise text.")
                return
            
            success, message_text = db.modify_channel_premise(channel_id, index, new_premise)
            
            if success:
                await message.channel.send(f"✅ {message_text}")
            else:
                await message.channel.send(f"❌ {message_text}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_mod: {e}")
            await message.channel.send(get_message('error_agregar_feed'))

    async def cmd_channel_premises_del(self, message, args):
        """Delete a specific channel premise by index."""
        if not message.author.guild_permissions.administrator:
            await message.channel.send(get_message('error_permisos'))
            return

        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel premises del <number>`")
            return

        try:
            db = self._get_db()
            channel_id = str(message.channel.id)

            try:
                index = int(args[0])
            except ValueError:
                await message.channel.send("❌ The number must be an integer.")
                return

            success, message_text = db.delete_channel_premise(channel_id, index)

            if success:
                await message.channel.send(f"✅ {message_text}")
            else:
                await message.channel.send(f"❌ {message_text}")

        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_del: {e}")
            await message.channel.send("❌ Error deleting channel premise")

    async def cmd_channel_premises_list_canvas(self, message, args):
        """Canvas-compatible version of channel premises list."""
        try:
            db = self._get_db()
            channel_id = str(message.channel.id)
            premises, context = db.get_channel_premises_with_context(channel_id)

            if not premises:
                return "📭 No premises are configured for this channel."

            lines = [
                f"🎯 Channel Premises ({context.title()}):",
                "These are the conditions that make news **CRITICAL** for this channel:",
                ""
            ]
            for i, premise in enumerate(premises, 1):
                lines.append(f"{i}. {premise}")
            return "\n".join(lines)
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_list_canvas: {e}")
            return "❌ Error listing channel premises"

    async def cmd_channel_premises_add_canvas(self, message, args):
        """Canvas-compatible version of channel premises add."""
        if not args:
            return "❌ No premise text provided"

        try:
            db = self._get_db()
            channel_id = str(message.channel.id)
            new_premise = " ".join(args).strip('"\'')

            if not new_premise:
                return "❌ You must provide premise text"

            success, message_text = db.add_channel_premise(channel_id, new_premise)
            return f"✅ {message_text}" if success else f"❌ {message_text}"
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_add_canvas: {e}")
            return "❌ Error adding channel premise"

    async def cmd_channel_premises_del_canvas(self, message, args):
        """Canvas-compatible version of channel premises delete."""
        if not args:
            return "❌ No premise number provided"

        try:
            all_text = " ".join(args)
            index = None
            for part in all_text.replace(",", " ").split():
                if part.isdigit():
                    index = int(part)
                    break

            if index is None:
                return "❌ Invalid premise number format. Use a single number like: 1"

            db = self._get_db()
            channel_id = str(message.channel.id)
            success, message_text = db.delete_channel_premise(channel_id, index)
            return f"✅ {message_text}" if success else f"❌ {message_text}"
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_del_canvas: {e}")
            return "❌ Error deleting channel premise"

    async def cmd_channel_premises_mod_canvas(self, message, args):
        """Canvas-compatible version of channel premises modify."""
        if len(args) < 2:
            return "❌ Usage: <number> <new premise text>"

        try:
            try:
                index = int(args[0])
            except ValueError:
                return "❌ The number must be an integer."

            new_premise = " ".join(args[1:]).strip('"\'')
            if not new_premise:
                return "❌ You must provide the new premise text."

            db = self._get_db()
            channel_id = str(message.channel.id)
            success, message_text = db.modify_channel_premise(channel_id, index, new_premise)
            return f"✅ {message_text}" if success else f"❌ {message_text}"
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_mod_canvas: {e}")
            return "❌ Error modifying channel premise"
    
    async def cmd_channel_general_subscribe(self, message, args):
        """AI subscription for a channel: analyze news using channel premises."""
        if not args:
            await message.channel.send(get_message('usage_canal_suscribir'))
            return
        
        try:
            # Check admin permissions
            if not message.author.guild_permissions.administrator:
                await message.channel.send(get_message('permisos_gestionar_canales'))
                return
            
            db = self._get_db()
            channel_id = str(message.channel.id)
            channel_name = message.channel.name
            server_id = str(message.guild.id)
            server_name = message.guild.name
            category = self._normalize_category(args[0])
            
            # Validate category and feed using the validation function
            feed_id = await self._validate_category_and_feed(message, category, args, db)
            if feed_id is None and len(args) > 1:  # Validation failed
                return
            
            # Check whether the channel has configured premises
            premises, context = db.get_channel_premises_with_context(channel_id)
            if not premises:
                await message.channel.send(get_message('no_premisas_canal_configuradas'))
                return
            
            # Handle 'all' parameter for channel AI subscriptions
            if feed_id == 'all':
                feeds = db.get_active_feeds(category)
                if not feeds:
                    await message.channel.send(f"❌ No feeds found in category '{category}'")
                    return
                
                success_count = 0
                premises_str = ",".join(premises) if premises else ""
                user_id = str(message.author.id)  # Get the user who is creating the subscription
                for feed in feeds:
                    if db.subscribe_channel_category_ai(channel_id, channel_name, server_id, server_name, category, feed[0], premises_str, user_id):
                        success_count += 1
                
                if success_count > 0:
                    await message.channel.send(f"🤖 **AI channel subscription** to ALL {success_count} feeds in '{category}' - I will analyze critical news based on the channel premises")
                else:
                    await message.channel.send(get_message('error_creando_suscripcion_ia'))
                return
            
            # Create single AI channel subscription
            premises_str = ",".join(premises) if premises else ""
            user_id = str(message.author.id)  # Get the user who is creating the subscription
            if db.subscribe_channel_category_ai(channel_id, channel_name, server_id, server_name, category, feed_id, premises_str, user_id):
                if feed_id:
                    await message.channel.send(f"🤖 **AI channel subscription** to feed {feed_id} in '{category}' - I will analyze critical news based on the channel premises")
                else:
                    await message.channel.send(f"🤖 **AI channel subscription** to '{category}' - I will analyze critical news based on the channel premises")
            else:
                await message.channel.send(get_message('error_creando_suscripcion_ia'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_general_subscribe: {e}")
            await message.channel.send(get_message('error_procesando_suscripcion_ia'))
    
    async def cmd_channel_general_unsubscribe(self, message, args):
        """Cancel a channel AI subscription for category/feed."""
        if not args:
            await message.channel.send(get_message('usage_canal_cancelar'))
            return
        
        try:
            # Check admin permissions
            if not message.author.guild_permissions.administrator:
                await message.channel.send(get_message('permissions_cancel_channel'))
                return
            
            db = self._get_db()
            channel_id = str(message.channel.id)
            category = self._normalize_category(args[0])
            feed_id = None
            
            # If there are more arguments after the category, treat the next one as feed_id
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send(get_message('feed_id_must_be_number'))
                    return
            
            if db.cancel_category_subscription(f"channel_{channel_id}", category, feed_id):
                if feed_id:
                    await message.channel.send(get_message('suscripcion_canal_cancelada_feed', feed_id=feed_id, category=category))
                else:
                    await message.channel.send(get_message('suscripcion_canal_cancelada_categoria', category=category))
            else:
                await message.channel.send(get_message('error_no_suscripciones_canal'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_general_unsubscribe: {e}")
            await message.channel.send(get_message('error_cancelar_suscripcion_canal'))
    
    def _get_category_icon(self, category: str) -> str:
        """Get icon for category."""
        category_icons = {
            'economy': '💰',
            'international': '🌍',
            'technology': '💻',
            'general': '📰',
            'crypto': '₿',
            'gaming': '🎮',
            'patch_notes': '🔧',
            'society': '👥',
            'politics': '🏛️',
            'sports': '⚽',
            'culture': '🎭',
            'science': '🔬'
        }
        return category_icons.get(category, '📰')
    
    async def cmd_channel_subscribe(self, message, args):
        """Subscribe the current channel to a category or feed."""
        if not args:
            await message.channel.send(get_message('usage_canal_suscribir'))
            return
        
        # Check permissions (requires manage channel)
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send(get_message('permisos_gestionar_canales'))
            return
        
        try:
            db = self._get_db(str(message.guild.id))
            category = self._normalize_category(args[0])
            
            # Check subscription limits
            channel_id = str(message.channel.id)
            can_channel_sub, channel_msg = db.can_channel_subscribe(channel_id)
            if not can_channel_sub:
                await message.channel.send(f"❌ {channel_msg}")
                return
            
            can_server_sub, server_msg = db.can_server_accept_subscription()
            if not can_server_sub:
                await message.channel.send(f"❌ {server_msg}")
                return
            
            # Validate category and feed using the validation function
            feed_id = await self._validate_category_and_feed(message, category, args, db)
            if feed_id is None and len(args) > 1:  # Validation failed
                return
            
            # Perform AI channel subscription by default
            channel = message.channel
            server = message.guild
            
            # Use AI subscription with role-specific default premises
            try:
                db_watcher = get_news_watcher_db_instance(str(server.id))
                default_premises_list = db_watcher._get_default_premises()
                default_premises = ", ".join(default_premises_list)
            except Exception:
                # Fallback to generic premises if there's an error
                default_premises = "interesting news, relevant events, important developments"
            
            # Handle 'all' parameter for channel subscriptions
            if feed_id == 'all':
                feeds = db.get_active_feeds(category)
                if not feeds:
                    await message.channel.send(f"❌ No feeds found in category '{category}'")
                    return
                
                success_count = 0
                user_id = str(message.author.id)  # Get the user who is creating the subscription
                for feed in feeds:
                    if db.subscribe_channel_category_ai(
                        str(channel.id), channel.name, str(server.id), server.name, category, feed[0], default_premises, user_id
                    ):
                        success_count += 1
                
                if success_count > 0:
                    await message.channel.send(f"✅ **Channel subscription** to ALL {success_count} feeds in '{category}' - AI analysis enabled")
                else:
                    await message.channel.send(get_message('error_creando_suscripcion_ia'))
                return
            
            # Create single channel subscription
            user_id = str(message.author.id)  # Get the user who is creating the subscription
            if db.subscribe_channel_category_ai(
                str(channel.id), channel.name, str(server.id), server.name, category, feed_id, default_premises, user_id
            ):
                if feed_id:
                    await message.channel.send(get_message('channel_subscription_successful_feed', feed_id=feed_id, category=category))
                else:
                    await message.channel.send(get_message('channel_subscription_successful_category', category=category))
            else:
                await message.channel.send(get_message('error_creando_suscripcion_ia'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_subscribe: {e}")
            await message.channel.send(get_message('error_procesando_suscripcion_ia'))
    
    async def _validate_channel_category_and_feed(self, message, category: str, args: list, db) -> int | None:
        """Validate category and optional feed_id for channel commands, returns feed_id or None."""
        # Check if it's a specific feed_id
        if len(args) > 1:
            try:
                feed_id = int(args[1])
                # Verify that the feed exists and belongs to the category
                feeds = db.get_active_feeds(category)
                feed_exists = any(f[0] == feed_id for f in feeds)
                if not feed_exists:
                    await message.channel.send(get_message('feed_id_not_found', feed_id=feed_id, category=category))
                    return None
                return feed_id
            except ValueError:
                await message.channel.send(get_message('feed_id_must_be_number'))
                return None
        else:
            # Verify category exists
            categories = db.get_available_categories()
            if not any(cat[0] == category for cat in categories):
                await message.channel.send(get_message('error_categoria_no_encontrada', category=category))
                return None
            return None  # No feed_id specified, which is valid

    async def cmd_channel_unsubscribe(self, message, args):
        """Cancel the current channel subscription for a category/feed."""
        if not args:
            await message.channel.send(get_message('usage_canal_cancelar'))
            return
        
        # Check permissions (requires manage channel)
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send(get_message('permissions_cancel_channel'))
            return
        
        try:
            db = self._get_db()
            category = self._normalize_category(args[0])
            
            # Validate category and feed
            feed_id = await self._validate_channel_category_and_feed(message, category, args, db)
            if feed_id is None and len(args) > 1:  # Validation failed
                return
            
            channel = message.channel
            
            if db.cancel_channel_subscription(str(channel.id), category, feed_id):
                if feed_id:
                    await message.channel.send(get_message('suscripcion_canal_cancelada_feed', feed_id=feed_id, category=category))
                else:
                    await message.channel.send(get_message('suscripcion_canal_cancelada_categoria', category=category))
            else:
                await message.channel.send(get_message('no_subscription_to_cancel'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_unsubscribe: {e}")
            await message.channel.send(get_message('error_cancelar_suscripcion_canal'))
    
    async def cmd_channel_status(self, message, args):
        """Show current channel subscription status."""
        try:
            db = self._get_db()
            channel = message.channel
            channel_id = str(channel.id)
            
            # Get all subscription details for this channel
            all_subscription_details = []
            
            # 1. Get flat subscriptions from subscriptions_channels table
            try:
                with sqlite3.connect(str(db.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT category, feed_id, subscribed_at
                        FROM subscriptions_channels 
                        WHERE channel_id = ? AND is_active = 1
                    ''', (channel_id,))
                    flat_subs = cursor.fetchall()
                    for sub in flat_subs:
                        all_subscription_details.append({
                            'type': 'flat',
                            'category': sub[0],
                            'feed_id': sub[1],
                            'date': sub[2],
                            'keywords': None,
                            'premises': None
                        })
            except Exception as e:
                logger.exception(f"Error getting flat channel subscriptions: {e}")
            
            # 2. Get keyword subscriptions from subscriptions_keywords table
            try:
                with sqlite3.connect(str(db.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT category, feed_id, keywords, subscribed_at
                        FROM subscriptions_keywords 
                        WHERE channel_id = ? AND is_active = 1
                    ''', (channel_id,))
                    keyword_subs = cursor.fetchall()
                    for sub in keyword_subs:
                        all_subscription_details.append({
                            'type': 'keywords',
                            'category': sub[0],
                            'feed_id': sub[1],
                            'keywords': sub[2],
                            'date': sub[3],
                            'premises': None
                        })
            except Exception as e:
                logger.exception(f"Error getting keyword channel subscriptions: {e}")
            
            # 3. Get AI subscriptions from subscriptions_categories table
            try:
                with sqlite3.connect(str(db.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT category, feed_id, user_premises, subscribed_at
                        FROM subscriptions_categories 
                        WHERE user_id = ? AND is_active = 1
                    ''', (f"channel_{channel_id}",))
                    ai_subs = cursor.fetchall()
                    for sub in ai_subs:
                        all_subscription_details.append({
                            'type': 'ai',
                            'category': sub[0],
                            'feed_id': sub[1],
                            'premises': sub[2],
                            'date': sub[3],
                            'keywords': None
                        })
            except Exception as e:
                logger.exception(f"Error getting AI channel subscriptions: {e}")
            
            if not all_subscription_details:
                await message.channel.send(get_message('error_no_suscripciones_canal'))
                return
            
            embed = discord.Embed(
                title=f"📊 Channel Subscriptions - #{channel.name}",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            # Group subscriptions by category and type
            subscriptions_by_category = {}
            for sub in all_subscription_details:
                category = sub['category']
                if category not in subscriptions_by_category:
                    subscriptions_by_category[category] = {
                        'flat': [],
                        'keywords': [],
                        'ai': []
                    }
                subscriptions_by_category[category][sub['type']].append(sub)
            
            for category, types in subscriptions_by_category.items():
                icon = self._get_category_icon(category)
                
                # Build description for this category
                category_parts = []
                
                # Flat subscriptions
                if types['flat']:
                    flat_feeds = [s['feed_id'] for s in types['flat'] if s['feed_id']]
                    if flat_feeds:
                        category_parts.append(f"📰 **Flat**: Specific feeds {', '.join(map(str, flat_feeds))}")
                    else:
                        category_parts.append(f"📰 **Flat**: All feeds")
                
                # Keyword subscriptions
                if types['keywords']:
                    keywords_list = []
                    for s in types['keywords']:
                        if s['feed_id']:
                            keywords_list.append(f"Feed {s['feed_id']}: `{s['keywords']}`")
                        else:
                            keywords_list.append(f"All feeds: `{s['keywords']}`")
                    category_parts.append(f"🔍 **Keywords**: {', '.join(keywords_list)}")
                
                # AI subscriptions
                if types['ai']:
                    ai_list = []
                    for s in types['ai']:
                        if s['feed_id']:
                            ai_list.append(f"Feed {s['feed_id']} (AI)")
                        else:
                            ai_list.append(f"All feeds (AI)")
                    category_parts.append(f"🤖 **AI**: {', '.join(ai_list)}")
                
                if category_parts:
                    # Direct mapping from Spanish to English
                    category_names = {
                        'economy': 'Economy',
                        'technology': 'Technology', 
                        'general': 'General',
                        'international': 'International',
                        'crypto': 'Crypto'
                    }
                    name = category_names.get(category, category.title())
                    embed.add_field(
                        name=f"{icon} **{name}**",
                        value="\n".join(category_parts),
                        inline=False
                    )
            
            embed.set_footer(text=get_message('usage_canal_cancelar'))
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_channel_status: {e}")
            await message.channel.send(get_message('error_obteniendo_estado_canal'))
    
    # ===== PREMISES MANAGEMENT COMMANDS (AI SUBSCRIPTIONS) =====
    
    async def cmd_premises(self, ctx, args):
        """Premises management command for AI subscriptions."""
        if not args:
            # If no subcommand is provided, show the default list
            await self.cmd_premises_list(ctx, args)
            return
        
        subcommand = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []
        
        if subcommand == 'list':
            await self.cmd_premises_list(ctx, subargs)
        elif subcommand == 'add':
            await self.cmd_premises_add(ctx, subargs)
        elif subcommand == 'mod':
            await self.cmd_premises_mod(ctx, subargs)
        elif subcommand == 'del':
            await self.cmd_premises_del(ctx, subargs)
        else:
            await send_dm_or_channel(ctx, f"❌ Subcommand '{subcommand}' not recognized. Use: list, add, mod, del")
    
    async def cmd_premises_list(self, ctx, args):
        """List all user premises (custom or global)."""
        try:
            db = self._get_db()
            user_id = str(ctx.author.id)
            
            # Get premises with context
            premises, context = db.get_premises_with_context(user_id)
            
            if not premises:
                await send_dm_or_channel(ctx, "📭 No premises are configured.")
                return
            
            embed = discord.Embed(
                title=f"🎯 Your Premises ({context.title()})",
                description="These are the conditions that make news **CRITICAL** for you:",
                color=discord.Color.blue() if context == "custom" else discord.Color.red(),
                timestamp=datetime.now()
            )
            
            for i, premise in enumerate(premises, 1):
                embed.add_field(
                    name=f"Premise #{i}",
                    value=f"📍 {premise}",
                    inline=False
                )
            
            if context == "custom":
                embed.set_footer(text="Use `!watcher premises add/mod` to manage your premises")
            else:
                embed.set_footer(text="Use `!watcher premises add` to create custom premises")
            
            await send_dm_or_channel(ctx, embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_premises_list: {e}")
            await send_dm_or_channel(ctx, get_message('error_listando_premisas'))
    
    async def cmd_premises_list_canvas(self, message, args):
        """Canvas-compatible version of cmd_premises_list that handles MockMessage objects."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Get premises with context
            premises, context = db.get_premises_with_context(user_id)
            
            if not premises:
                # Check if there are default premises available
                default_premises = db._get_default_premises()
                if default_premises:
                    lines = []
                    lines.append(f"🎯 Your Premises (Global - Not Customized):")
                    lines.append("These are the default premises. Use 'Add Premises' to create your custom versions:")
                    lines.append("")
                    for i, premise in enumerate(default_premises, 1):
                        lines.append(f"{i}. {premise}")
                    lines.append("")
                    lines.append("💡 **No custom premises configured**")
                    lines.append("💡 Use `!watcher premises add 'your premise'` to create custom premises")
                    lines.append("💡 Or use the Canvas interface to add your first premise")
                    return "\n".join(lines)
                else:
                    return "📭 No premises are configured."
            
            # Create a simple text list instead of embed
            lines = []
            lines.append(f"🎯 Your Premises ({context.title()}):")
            lines.append("These are the conditions that make news **CRITICAL** for you:")
            lines.append("")
            
            for i, premise in enumerate(premises, 1):
                lines.append(f"{i}. {premise}")
            
            lines.append("")
            if context == "custom":
                lines.append("💡 Use `!watcher premises add/mod` to manage your premises")
            else:
                lines.append("💡 Use `!watcher premises add` to create custom premises")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.exception(f"Error in cmd_premises_list_canvas: {e}")
            return "❌ Error listing premises"
    
    async def cmd_premises_add(self, ctx, args):
        """Add a new premise (max 7)."""
        if not args:
            await send_dm_or_channel(ctx, get_message('usage_premises_add'))
            return
        
        try:
            db = self._get_db()
            user_id = str(ctx.author.id)
            new_premise = " ".join(args).strip('"\'')
            
            if not new_premise:
                await send_dm_or_channel(ctx, get_message('debes_proporcionar_premisa'))
                return
            
            success, message_text = db.add_user_premise(user_id, new_premise)
            
            if success:
                await send_dm_or_channel(ctx, f"✅ {message_text}")
            else:
                await send_dm_or_channel(ctx, f"❌ {message_text}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_premises_add: {e}")
            await send_dm_or_channel(ctx, get_message('error_agregando_premisa'))
    
    async def cmd_premises_mod(self, ctx, args):
        """Modify a premise by index."""
        if len(args) < 2:
            await send_dm_or_channel(ctx, get_message('usage_premises_mod'))
            return
        
        try:
            db = self._get_db()
            user_id = str(ctx.author.id)
            
            # Parse number
            try:
                index = int(args[0])
            except ValueError:
                await send_dm_or_channel(ctx, "❌ The number must be an integer.")
                return
            
            new_premise = " ".join(args[1:]).strip('"\'')
            
            if not new_premise:
                await send_dm_or_channel(ctx, "❌ You must provide the new premise text.")
                return
            
            success, message_text = db.modify_user_premise(user_id, index, new_premise)
            
            if success:
                await send_dm_or_channel(ctx, f"✅ {message_text}")
            else:
                await send_dm_or_channel(ctx, f"❌ {message_text}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_premises_mod: {e}")
            await send_dm_or_channel(ctx, "❌ Error modifying premise")
    
    async def cmd_premises_del(self, ctx, args):
        """Delete a user premise by index (alias for consistency)."""
        if not args:
            await send_dm_or_channel(ctx, "📝 Usage: `!watcher premises del <number>`")
            return
        
        try:
            db = self._get_db()
            user_id = str(ctx.author.id)
            
            # Parse number
            try:
                index = int(args[0])
            except ValueError:
                await send_dm_or_channel(ctx, "❌ The number must be an integer.")
                return
            
            success, message_text = db.delete_user_premise(user_id, index)
            
            if success:
                await send_dm_or_channel(ctx, f"✅ {message_text}")
            else:
                await send_dm_or_channel(ctx, f"❌ {message_text}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_premises_del: {e}")
            await send_dm_or_channel(ctx, "❌ Error deleting premise")
    
    async def cmd_premises_del_canvas(self, message, args):
        """Canvas-compatible version of cmd_premises_del that handles MockMessage objects."""
        if not args:
            return "❌ No premise number provided"
        
        try:
            # Join all args and split by common delimiters
            all_text = " ".join(args)
            
            # Handle different number formats from Canvas UI
            premise_numbers = []
            if ',' in all_text:
                # Split comma-separated numbers: "1,2,3" -> ["1", "2", "3"]
                premise_numbers = [num.strip() for num in all_text.split(',')]
            elif ' ' in all_text:
                # Split space-separated numbers: "1 2 3" -> ["1", "2", "3"]
                premise_numbers = all_text.split()
            else:
                # Single number
                premise_numbers = [all_text.strip()]
            
            # Parse all valid numbers for multiple deletion
            valid_indices = []
            for num_str in premise_numbers:
                if num_str.isdigit():
                    valid_indices.append(int(num_str))
            
            if not valid_indices:
                return "❌ Invalid premise number format. Use numbers like: 1 or 1,2,3"
            
            # Get user ID from message
            user_id = str(message.author.id)
            
            # Use database directly
            db = self._get_db()
            
            # Check if user has any custom premises
            current_premises, context = db.get_premises_with_context(user_id)
            
            if not current_premises:
                return "❌ You have no premises to delete. Use 'Add Premises' to create your first premise."
            
            # Delete multiple premises (in reverse order to maintain indices)
            deleted_count = 0
            deletion_results = []
            
            # Sort indices in descending order to avoid index shifting issues
            for index in sorted(valid_indices, reverse=True):
                if 1 <= index <= len(current_premises):
                    success, message_text = db.delete_user_premise(user_id, index)
                    if success:
                        deleted_count += 1
                        deletion_results.append(f"Premise #{index}: {message_text}")
                        # Refresh premises list for next deletion
                        current_premises, context = db.get_premises_with_context(user_id)
                    else:
                        deletion_results.append(f"Premise #{index}: Failed - {message_text}")
                else:
                    deletion_results.append(f"Premise #{index}: Invalid index")
            
            if deleted_count > 0:
                result_msg = f"✅ Deleted {deleted_count} premise(s):\n" + "\n".join(deletion_results)
            else:
                result_msg = "❌ No premises deleted. " + "\n".join(deletion_results)
            
            return result_msg
                
        except Exception as e:
            logger.exception(f"Error in cmd_premises_del_canvas: {e}")
            return "❌ Error deleting premise"

    async def cmd_premises_mod_canvas(self, message, args):
        """Canvas-compatible version of cmd_premises_mod that handles MockMessage objects."""
        if len(args) < 2:
            return "❌ Usage: <number> <new premise text>"

        try:
            try:
                index = int(args[0])
            except ValueError:
                return "❌ The number must be an integer."

            new_premise = " ".join(args[1:]).strip('"\'')
            if not new_premise:
                return "❌ You must provide the new premise text."

            db = self._get_db()
            user_id = str(message.author.id)
            success, message_text = db.modify_user_premise(user_id, index, new_premise)
            return f"✅ {message_text}" if success else f"❌ {message_text}"
        except Exception as e:
            logger.exception(f"Error in cmd_premises_mod_canvas: {e}")
            return "❌ Error modifying premise"
    
    async def cmd_premises_add_canvas(self, message, args):
        """Canvas-compatible version of cmd_premises_add that handles MockMessage objects."""
        if not args:
            return "❌ No premise text provided"
        
        try:
            # Get user ID from message
            user_id = str(message.author.id)
            new_premise = " ".join(args).strip('"\'')
            
            if not new_premise:
                return "❌ You must provide premise text"
            
            # Use database directly
            db = self._get_db()
            success, message_text = db.add_user_premise(user_id, new_premise)
            
            if success:
                return f"✅ {message_text}"
            else:
                return f"❌ {message_text}"
                
        except Exception as e:
            logger.exception(f"Error in cmd_premises_add_canvas: {e}")
            return "❌ Error adding premise"
    
    async def cmd_my_premises(self, message, args):
        """Show user's custom premises."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            user_premises = db.get_user_premises(user_id)
            
            if not user_premises:
                await message.channel.send(get_message('no_premisas_personales'))
                return
            
            embed = discord.Embed(
                title=f"🎯 Your Custom Premises",
                description="These are your **personal** conditions for critical news:",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            for i, premise in enumerate(user_premises, 1):
                embed.add_field(
                    name=f"Your Premise #{i}",
                    value=f"📍 {premise}",
                    inline=False
                )
            
            embed.set_footer(text="Maximum 7 custom premises. Use !watcher premises configure to modify them")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_my_premises: {e}")
            await message.channel.send("❌ Error getting your premises")
    
    async def cmd_configure_premises(self, message, args):
        """Configure user's custom premises."""
        if not args:
            await message.channel.send(get_message('usage_premises_configure'))
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Extract and clean premises
            premises_text = " ".join(args).strip('"\'')
            premises_list = [p.strip() for p in premises_text.split(',') if p.strip()]
            
            if len(premises_list) > 7:
                await message.channel.send(get_message('maximo_premisas_personales'))
                return
            
            if not premises_list:
                await message.channel.send(get_message('debes_proporcionar_una_premisa'))
                return
            
            if db.update_user_premises(user_id, premises_list):
                await message.channel.send(f"✅ Your custom premises have been configured ({len(premises_list)} premises).\nUse `!watcher premises my_premises` to see them.")
            else:
                await message.channel.send(get_message('error_configurando_premisas'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_configure_premises: {e}")
            await message.channel.send(get_message('error_configurando_premisas'))
    
    def _get_country_flag(self, country: str) -> str:
        """Get flag for country."""
        country_flags = {
            'US': '🇺🇸',
            'ES': '🇪🇸',
            'UK': '🇬🇧',
            'MX': '🇲🇽',
            'AR': '🇦🇷',
            'FR': '🇫🇷',
            'DE': '🇩🇪',
            'IT': '🇮🇹',
            'BR': '🇧🇷',
            'CA': '🇨🇦'
        }
        return country_flags.get(country, '🌐')

    async def cmd_method(self, message, args):
        """Configure or show the current subscription method for the server."""
        if not message.guild:
            await message.channel.send("❌ This command can only be used on a server, not in direct messages.")
            return
        
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can configure the method.")
            return
        
        try:
            db = self._get_db()
            server_id = str(message.guild.id)
            
            if not args:
                # Show current method
                current_method = db.get_method_config(server_id)
                method_names = {
                    'flat': 'Flat (all news with opinion)',
                    'keyword': 'Keywords (filtered news)',
                    'general': 'AI (critical news analysis)'
                }
                
                embed = discord.Embed(
                    title="⚙️ **Current Method Configuration**",
                    description=f"**Method:** {method_names.get(current_method, current_method)}",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Available Methods:",
                    value="• `flat` - All news with generated opinion\n"
                          "• `keyword` - Filtered news by keywords\n"
                          "• `general` - AI-analyzed critical news",
                    inline=False
                )
                
                embed.add_field(
                    name="Usage:",
                    value="`!watcher method <method>` to change the method",
                    inline=False
                )
                
                embed.set_footer(text="Only administrators can change the method")
                await message.channel.send(embed=embed)
                return
            
            # Set new method
            new_method = args[0].lower()
            if new_method not in ['flat', 'keyword', 'general']:
                await message.channel.send("❌ Invalid method. Use: `flat`, `keyword`, or `general`")
                return
            
            if db.set_method_config(server_id, new_method):
                method_names = {
                    'flat': 'Flat (all news with opinion)',
                    'keyword': 'Keywords (filtered news)',
                    'general': 'AI (critical news analysis)'
                }
                
                embed = discord.Embed(
                    title="✅ **Method Configuration Updated**",
                    description=f"**New Method:** {method_names.get(new_method, new_method)}",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="What this means:",
                    value=self._get_method_description(new_method),
                    inline=False
                )
                
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("❌ Error updating method configuration")
                
        except Exception as e:
            logger.exception(f"Error in cmd_method: {e}")
            await message.channel.send("❌ Error processing method command")

    def _get_method_description(self, method: str) -> str:
        """Get description for a method type."""
        descriptions = {
            'flat': "Users receive ALL news from subscribed categories with AI-generated opinions. No filtering applied.",
            'keyword': "Users receive news that matches their configured keywords. Highly personalized filtering.",
            'general': "Users receive only critical news analyzed by AI according to their premises. Most selective filtering."
        }
        return descriptions.get(method, "Unknown method")

    async def cmd_frequency(self, message, args):
        """Manage news checking frequency (admin only)."""
        if not message.guild:
            await message.channel.send("❌ This command can only be used on servers, not in direct messages.")
            return
        
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can manage frequency settings.")
            return
        
        if not args:
            await message.channel.send("📝 Usage: `!watcher frequency <hours>` or `!watcher frequency status`")
            return
        
        try:
            db = self._get_db()
            
            if args[0].lower() == 'status':
                # Show current frequency
                current_freq = db.get_frequency_setting()
                embed = discord.Embed(
                    title="⏰ **Frequency Settings**",
                    description=f"Current check interval: **{current_freq} hours**",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Next Check",
                    value=f"Every {current_freq} hours",
                    inline=False
                )
                
                embed.add_field(
                    name="Usage",
                    value="`!watcher frequency <hours>` to change (1-24 hours)",
                    inline=False
                )
                
                await message.channel.send(embed=embed)
                return
            
            # Set new frequency
            try:
                new_hours = int(args[0])
            except ValueError:
                await message.channel.send("❌ Invalid format. Use a number between 1 and 24.")
                return
            
            if not 1 <= new_hours <= 24:
                await message.channel.send("❌ Frequency must be between 1 and 24 hours.")
                return
            
            if db.set_frequency_setting(new_hours):
                embed = discord.Embed(
                    title="✅ **Frequency Updated**",
                    description=f"News check interval set to **{new_hours} hours**",
                    color=discord.Color.green()
                )
                
                embed.add_field(
                    name="What this means:",
                    value=f"I will check for news every {new_hours} hours and send updates to all subscribers.",
                    inline=False
                )
                
                embed.add_field(
                    name="Note",
                    value="The new frequency will take effect on the next check cycle.",
                    inline=False
                )
                
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("❌ Error updating frequency setting")
                
        except Exception as e:
            logger.exception(f"Error in cmd_frequency: {e}")
            await message.channel.send("❌ Error processing frequency command")

    async def cmd_subscriptions(self, message, args):
        """Show numbered list of all user subscriptions with category, feed, and method."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Get all subscriptions across all methods
            all_subscriptions = []
            
            # Get flat subscriptions
            flat_subs = db.get_user_subscriptions(user_id)
            for category, feed_id, fecha in flat_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'flat',
                    'date': fecha,
                    'type': 'Flat (All News)'
                })
            
            # Get keyword subscriptions
            keyword_subs = db.get_user_keyword_subscriptions(user_id)
            for category, feed_id, keywords in keyword_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'keyword',
                    'keywords': keywords,
                    'type': 'Keywords (Filtered)'
                })
            
            # Get AI subscriptions
            ai_subs = db.get_user_ai_subscriptions(user_id)
            for category, feed_id, premises in ai_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'general',
                    'premises': premises,
                    'type': 'AI (Critical)'
                })
            
            if not all_subscriptions:
                await message.channel.send("📋 You have no active subscriptions. Use `!watcher subscribe <category>` to start.")
                return
            
            # Create numbered list embed
            embed = discord.Embed(
                title="📋 **Your Subscriptions**",
                description=f"Total: {len(all_subscriptions)} subscriptions",
                color=discord.Color.blue()
            )
            
            for i, sub in enumerate(all_subscriptions, 1):
                feed_info = f"Feed {sub['feed_id']}" if sub['feed_id'] else "All feeds"
                
                if sub['method'] == 'keyword':
                    details = f"Keywords: {sub.get('keywords', 'N/A')}"
                elif sub['method'] == 'general':
                    premise_count = len(sub.get('premises', '').split(',')) if sub.get('premises') else 0
                    details = f"Premises: {premise_count}"
                else:
                    details = "All news with opinions"
                
                field_value = f"**Method:** {sub['type']}\n**Feed:** {feed_info}\n**Details:** {details}"
                
                embed.add_field(
                    name=f"#{i} - {sub['category'].title()}",
                    value=field_value,
                    inline=False
                )
            
            embed.add_field(
                name="🗑️ **How to Unsubscribe**",
                value="Use `!watcher unsubscribe <number>` to remove a subscription\n"
                     "Use `!watcher unsubscribe <category>` (old method still works)",
                inline=False
            )
            
            embed.set_footer(text="Use !watcher unsubscribe <number> to remove any subscription")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_subscriptions: {e}")
            await message.channel.send("❌ Error retrieving subscriptions")

    async def cmd_unified_subscribe(self, message, args):
        """Unified subscribe command with method selection."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher subscribe <method> <category> [feed_id]`")
            await message.channel.send("Methods: `flat`, `keyword`, `general`")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Parse method, category, and optional feed_id
            method = args[0].lower()
            if method not in ['flat', 'keyword', 'general']:
                await message.channel.send("❌ Invalid method. Use: `flat`, `keyword`, or `general`")
                return
            
            if len(args) < 2:
                await message.channel.send("❌ Missing category. Usage: `!watcher subscribe <method> <category> [feed_id]`")
                return
                
            category = self._normalize_category(args[1])
            feed_id = None
            
            # Validate category and feed
            feed_id = await self._validate_category_and_feed(message, category, args[1:], db)
            if feed_id is None and len(args) > 2:  # Validation failed
                return
            
            # Route to appropriate method handler
            if method == 'flat':
                await self._handle_flat_subscribe(message, user_id, category, feed_id)
            elif method == 'keyword':
                await self._handle_keyword_subscribe(message, user_id, category, feed_id)
            elif method == 'general':
                await self._handle_general_subscribe(message, user_id, category, feed_id)
                
        except Exception as e:
            logger.exception(f"Error in cmd_unified_subscribe: {e}")
            await message.channel.send("❌ Error processing subscription")

    async def _handle_flat_subscribe(self, message, user_id: str, category: str, feed_id):
        """Handle flat subscription."""
        try:
            db = self._get_db()
            
            # Check subscription limits
            can_user_sub, user_msg = db.can_user_subscribe(user_id)
            if not can_user_sub:
                await message.channel.send(f"❌ {user_msg}")
                return
            
            # Handle 'all' parameter
            if feed_id == 'all':
                feeds = db.get_active_feeds(category)
                if not feeds:
                    await message.channel.send(f"❌ No feeds found in category '{category}'")
                    return
                
                success_count = 0
                for feed in feeds:
                    if db.subscribe_user_category(user_id, category, feed[0]):
                        success_count += 1
                
                if success_count > 0:
                    await message.channel.send(f"✅ **Flat subscription** to ALL {success_count} feeds in '{category}' - You will receive ALL news with AI opinions")
                else:
                    await message.channel.send("❌ Error creating flat subscriptions")
                return
            
            # Create single subscription
            if db.subscribe_user_category(user_id, category, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ **Flat subscription** to feed {feed_id} in '{category}' - You will receive ALL news with AI opinions")
                else:
                    await message.channel.send(f"✅ **Flat subscription** to '{category}' - You will receive ALL news with AI opinions")
            else:
                await message.channel.send("❌ Error creating flat subscription")
                
        except Exception as e:
            logger.exception(f"Error in flat subscribe: {e}")
            await message.channel.send("❌ Error processing flat subscription")

    async def _handle_keyword_subscribe(self, message, user_id: str, category: str, feed_id):
        """Handle keyword subscription."""
        try:
            db = self._get_db()
            
            # Check if user has keywords configured
            keywords = db.get_user_keywords(user_id)
            if not keywords:
                await message.channel.send("⚠️ You have no keywords configured. Use `!watcher keywords add <keyword>` first.")
                return
            
            # Check subscription limits
            can_user_sub, user_msg = db.can_user_subscribe(user_id)
            if not can_user_sub:
                await message.channel.send(f"❌ {user_msg}")
                return
            
            # Handle 'all' parameter
            if feed_id == 'all':
                feeds = db.get_active_feeds(category)
                if not feeds:
                    await message.channel.send(f"❌ No feeds found in category '{category}'")
                    return
                
                success_count = 0
                for feed in feeds:
                    if db.subscribe_keywords(user_id, keywords, None, category, feed[0]):
                        success_count += 1
                
                if success_count > 0:
                    await message.channel.send(f"✅ **Keyword subscription** to ALL {success_count} feeds in '{category}' - Filtering: '{keywords}'")
                else:
                    await message.channel.send("❌ Error creating keyword subscriptions")
                return
            
            # Create single subscription
            if db.subscribe_keywords(user_id, keywords, None, category, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ **Keyword subscription** to feed {feed_id} in '{category}' - Filtering: '{keywords}'")
                else:
                    await message.channel.send(f"✅ **Keyword subscription** to '{category}' - Filtering: '{keywords}'")
            else:
                await message.channel.send("❌ Error creating keyword subscription")
                
        except Exception as e:
            logger.exception(f"Error in keyword subscribe: {e}")
            await message.channel.send("❌ Error processing keyword subscription")

    async def _handle_general_subscribe(self, message, user_id: str, category: str, feed_id, return_result: bool = False):
        """Handle general (AI) subscription."""
        try:
            db = self._get_db()
            
            # Ensure the user has premises configured
            premises, context = db.get_premises_with_context(user_id)
            if not premises:
                error_msg = "⚠️ You have no premises configured. Use `!watcher premises add <premise>` before subscribing."
                if return_result:
                    return False, error_msg
                await message.channel.send(error_msg)
                return None if return_result else None
            
            # Check subscription limits
            can_user_sub, user_msg = db.can_user_subscribe(user_id)
            if not can_user_sub:
                error_msg = f"❌ {user_msg}"
                if return_result:
                    return False, error_msg
                await message.channel.send(error_msg)
                return None if return_result else None
            
            # Handle 'all' parameter
            if feed_id == 'all':
                feeds = db.get_active_feeds(category)
                if not feeds:
                    error_msg = f"❌ No feeds found in category '{category}'"
                    if return_result:
                        return False, error_msg
                    await message.channel.send(error_msg)
                    return None if return_result else None
                
                success_count = 0
                premises_str = ",".join(premises) if premises else ""
                for feed in feeds:
                    if db.subscribe_user_category_ai(user_id, category, feed[0], premises_str):
                        success_count += 1
                
                if success_count > 0:
                    success_msg = f"🤖 **AI subscription** to ALL {success_count} feeds in '{category}' - I'll analyze critical news using your premises"
                    if return_result:
                        return True, success_msg
                    await message.channel.send(success_msg)
                else:
                    error_msg = "❌ Error creating AI subscriptions"
                    if return_result:
                        return False, error_msg
                    await message.channel.send(error_msg)
                return None if return_result else None
            
            # Create single subscription
            premises_str = ",".join(premises) if premises else ""
            if db.subscribe_user_category_ai(user_id, category, feed_id, premises_str):
                if feed_id:
                    success_msg = f"🤖 **AI subscription** to feed {feed_id} in '{category}' - I'll analyze critical news using your premises"
                else:
                    success_msg = f"🤖 **AI subscription** to '{category}' - I'll analyze critical news using your premises"
                
                if return_result:
                    return True, success_msg
                await message.channel.send(success_msg)
                return None if return_result else None
            else:
                error_msg = get_message('error_creando_suscripcion_ia')
                if return_result:
                    return False, error_msg
                await message.channel.send(error_msg)
                return None if return_result else None
                
        except Exception as e:
            logger.exception(f"Error in general subscribe: {e}")
            error_msg = get_message('error_procesando_suscripcion_ia')
            if return_result:
                return False, error_msg
            await message.channel.send(error_msg)
            return None if return_result else None


