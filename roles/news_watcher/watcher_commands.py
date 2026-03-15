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
from .premises_manager import get_premises_manager

logger = get_logger('vigia_commands')


def _get_watcher_description_text(key: str, fallback: str) -> str:
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "agent_config.json")
        with open(config_path, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        personality_rel = agent_cfg.get("personality", "")
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
        self.db_vigia = None
    
    def _get_db(self, server_name: str = None):
        """Get (and cache) the watcher DB instance."""
        if not self.db_vigia:
            # Use provided server_name or fall back to active server
            if server_name:
                self.db_vigia = get_news_watcher_db_instance(server_name)
            else:
                from agent_db import get_active_server_name
                server_name = get_active_server_name()
                if not server_name:
                    raise RuntimeError("No active server configured for watcher commands")
                self.db_vigia = get_news_watcher_db_instance(server_name)
        return self.db_vigia

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
            
            feeds_por_category = {}
            for feed in feeds:
                feed_id, name, url, category, country, language, priority, keywords, feed_type = feed
                if category not in feeds_por_category:
                    feeds_por_category[category] = []
                feeds_por_category[category].append({
                    'id': feed_id, 'name': name, 'url': url,
                    'country': country, 'language': language, 'priority': priority, 'feed_type': feed_type
                })
            
            for category, feeds_cat in feeds_por_category.items():
                valor = ""
                for feed in feeds_cat:
                    bandera = self._get_bandera_pais(feed['country'])
                    valor += f"**{feed['name']}** ({feed['id']}) {bandera}\n"
                    valor += f"Priority: {feed['priority']} | Language: {feed['language'].upper()}\n\n"
                
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
                    value=valor,
                    inline=False
                )
            
            embed.set_footer(text=f"Use !watcher subscribe <category> to receive news")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_feeds: {e}")
            await message.channel.send(get_message('general_error', error=e))
    
    async def cmd_reset(self, message, args):
        """Completely clear all user subscriptions."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Check if has any subscription
            current_type = db.check_user_subscription_type(user_id)
            
            if not current_type:
                await message.channel.send(get_message('error_no_suscripciones'))
                return
            
            # Check if confirmation
            if args and args[0].lower() == "confirm":
                # Execute confirmed reset
                cancelled = 0
                
                if current_type == 'plana':
                    # Cancel flat subscriptions
                    subscriptions = db.get_user_subscriptions(user_id)
                    for category, feed_id, _ in subscriptions:
                        if db.cancel_category_subscription(user_id, category, feed_id):
                            cancelled += 1
                            
                elif current_type == 'palabras':
                    # Cancel keyword subscriptions
                    subscriptions = db.get_user_keyword_subscriptions(user_id)
                    for category, _, _ in subscriptions:
                        if db.cancel_user_keyword_subscription(user_id, category):
                            canceladas += 1
                            
                elif current_type == 'ia':
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
                    await message.channel.send(get_message('error_no_suscripciones'))
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
            await message.channel.send(get_message('general_error', error="processing reset request"))

    async def cmd_categories(self, message, args):
        """Show available categories."""
        try:
            db = self._get_db()
            categorys = db.get_available_categories()
            
            if not categorys:
                await message.channel.send(get_message('error_no_hay_kategorias'))
                return
            
            embed = discord.Embed(
                title="📂 Available Categories",
                description=f"There are {len(categorys)} categories with active feeds:",
                color=discord.Color.blue()
            )
            
            for category, count in categorys:
                icono = self._get_icono_category(category)
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
                    name=f"{icono} {name}",
                    value=f"{count} available feeds",
                    inline=True
                )
            
            embed.set_footer(text="Use !watcher subscribe <category> to receive news from that category")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_categories: {e}")
            await message.channel.send(get_message('general_error', error=e))

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
        # Check if it's a specific feed_id
        if len(args) > 1:
            try:
                feed_id = int(args[1])
                # Verify that the feed exists and belongs to the category
                feeds = db.get_active_feeds(category)
                feed_existente = any(f[0] == feed_id for f in feeds)
                if not feed_existente:
                    await message.channel.send(get_message('feed_not_found', feed_id=feed_id, category=category))
                    return None
                return feed_id
            except ValueError:
                await message.channel.send(get_message('invalid_feed_id'))
                return None
        else:
            # Verify category exists
            categorys = db.get_available_categories()
            if not any(cat[0] == category for cat in categorys):
                await message.channel.send(get_message('error_kategori_no_encontrada', category=category))
                return None
            return None  # No feed_id specified, which is valid

    async def cmd_unsubscribe(self, message, args):
        """Cancel subscription by number (from list) or by category/feed (legacy)."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher unsubscribe <number>` or `!watcher unsubscribe <category> [feed_id]`")
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
            await message.channel.send("❌ Error canceling subscription")

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
            for category, feed_id, palabras in keyword_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'keyword',
                    'keywords': palabras
                })
            
            # Get AI subscriptions
            ai_subs = db.get_user_ai_subscriptions(user_id)
            for category, feed_id, premisas in ai_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'general',
                    'premises': premisas
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
                await message.channel.send("❌ Error canceling subscription")
                
        except Exception as e:
            logger.exception(f"Error in _unsubscribe_by_number: {e}")
            await message.channel.send("❌ Error canceling subscription by number")

    async def _unsubscribe_by_category(self, message, user_id: str, args):
        """Legacy unsubscribe by category/feed method."""
        category = self._normalize_category(args[0])
        feed_id = None
        
        if len(args) > 1:
            try:
                feed_id = int(args[1])
            except ValueError:
                await message.channel.send("❌ Invalid feed ID format")
                return
        
        db = self._get_db()
        
        if db.cancel_category_subscription(user_id, category, feed_id):
            if feed_id:
                await message.channel.send(f"✅ Unsubscribed from {category} (Feed {feed_id})")
            else:
                await message.channel.send(f"✅ Unsubscribed from {category}")
        else:
            await message.channel.send("❌ No matching subscription found")
    
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
                    await message.channel.send(get_message('invalid_feed_id'))
                    return
            
            if db.cancel_category_subscription(user_id, category, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ AI subscription canceled: Feed {feed_id} in '{category}'")
                else:
                    await message.channel.send(f"✅ AI subscription canceled: Category '{category}'")
            else:
                await message.channel.send(get_message('no_tienes_suscripcion_ia'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_general_unsubscribe: {e}")
            await message.channel.send(get_message('error_cancelando_suscripcion_ia'))
    
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
            tipo_actual = db.check_user_subscription_type(user_id)
            logger.info(f"DEBUG: Subscription type for {user_id}: {tipo_actual}")
            
            if not tipo_actual:
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
            if tipo_actual == 'plana':
                suscripciones = db.get_user_subscriptions(user_id)
                if suscripciones:
                    embed = discord.Embed(
                        title="📰 Active Flat Subscription",
                        description="You receive **all news** (with generated opinion)",
                        color=discord.Color.blue()
                    )
                    
                    for i, (category, feed_id, fecha) in enumerate(suscripciones, 1):
                        if feed_id:
                            embed.add_field(
                                name=f"#{i} - {category}",
                                value=f"Feed ID: {feed_id}\nDesde: {fecha}",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"#{i} - {category}",
                                value=f"Entire category\nSince: {fecha}",
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
                    
            elif tipo_actual == 'palabras':
                suscripciones = db.get_user_keyword_subscriptions(user_id)
                if suscripciones:
                    embed = discord.Embed(
                        title="🔍 Active Keywords Subscription",
                        description="You receive **filtered news** matching your keywords",
                        color=discord.Color.green()
                    )
                    
                    for i, (category, feed_id, palabras) in enumerate(suscripciones, 1):
                        if feed_id:
                            embed.add_field(
                                name=f"#{i} - {category} (Feed {feed_id})",
                                value=f"Keywords: {palabras}",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"#{i} - {category}",
                                value=f"Keywords: {palabras}",
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
                    
            elif tipo_actual == 'ia':
                suscripciones = db.get_user_ai_subscriptions(user_id)
                logger.info(f"DEBUG: Suscripciones IA encontradas: {suscripciones}")
                if suscripciones:
                    embed = discord.Embed(
                        title="🤖 Active AI Subscription",
                        description="You receive **critical news** analyzed using your premises",
                        color=discord.Color.purple()
                    )
                    
                    for i, (category, feed_id, premisas) in enumerate(suscripciones, 1):
                        if feed_id:
                            embed.add_field(
                                name=f"#{i} - {category} (Feed {feed_id})",
                                value=f"Premises configured: {len(premisas.split(','))}",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"#{i} - {category}",
                                value=f"Premises configured: {len(premisas.split(','))}",
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
                    logger.warning(f"DEBUG: Inconsistency detected - tipo='ia' pero no suscripciones IA para usuario {user_id}")
                    await message.channel.send(get_message('no_active_ai_subscription'))
                    
        except Exception as e:
            logger.exception(f"Error in cmd_status: {e}")
            await message.channel.send(get_message('error_mostrando_estado'))
    
    async def cmd_categories(self, message, args):
        """Show available categories with active feeds."""
        try:
            db = self._get_db()
            categorys = db.get_available_categories()
            
            if not categorys:
                await message.channel.send(get_message('error_no_hay_kategorias'))
                return
            
            embed = discord.Embed(
                title="📂 Available Categories",
                description=f"There are {len(categorys)} categories with active feeds:",
                color=discord.Color.blue()
            )
            
            for category, count in categorys:
                icono = self._get_icono_category(category)
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
                    name=f"{icono} {name}",
                    value=f"{count} available feeds",
                    inline=True
                )
            
            embed.set_footer(text="Use !watcher feeds to see feeds in each category")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_categories: {e}")
            await message.channel.send(get_message('error_mostrando_categorys'))
    
    async def cmd_add_feed(self, message, args):
        """Agrega nuevo feed (solo admins)."""
        if len(args) < 3:
            await message.channel.send("📝 Uso: `!vigia add_feed <nombre> <url> <categoría> [país] [idioma]`")
            return
        
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can add feeds")
            return
        
        try:
            db = self._get_db()
            name = args[0]
            url = args[1]
            category = args[2].lower()
            country = args[3] if len(args) > 3 else None
            language = args[4] if len(args) > 4 else 'es'
            
            if db.add_feed(name, url, category, country, language):
                await message.channel.send(f"✅ Feed '{name}' agregado a categoría '{category}'")
            else:
                await message.channel.send(get_message('error_add_feed'))
                
        except Exception as e:
            logger.exception(f"Error in cmd_add_feed: {e}")
            await message.channel.send("❌ Error al add feed")
    
    async def cmd_general_subscribe(self, message, args):
        """Subscribe with AI (premises-based) to a category/feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher general <category> [feed_id]`")
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
            await message.channel.send("❌ Error processing AI subscription")
    
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

            palabras_clave = args[0].strip('"\'')
            category = None
            feed_id = None

            if len(args) > 1:
                category = self._normalize_category(args[1])
                if len(args) > 2:
                    try:
                        feed_id = int(args[2])
                        feeds = db.get_active_feeds(category)
                        feed_existente = any(f[0] == feed_id for f in feeds)
                        if not feed_existente:
                            await message.channel.send(f"❌ Feed ID {feed_id} not found in category '{category}'")
                            return
                    except ValueError:
                        await message.channel.send(get_message('invalid_feed_id'))
                        return
                else:
                    categorys = db.get_available_categories()
                    if not any(cat[0] == category for cat in categorys):
                        await message.channel.send(get_message('error_kategori_no_encontrada', category=category))
                        return

            if not palabras_clave:
                await message.channel.send("❌ You must provide keywords")
                return

            tipo_actual = db.check_user_subscription_type(user_id)
            if tipo_actual == 'palabras':
                await message.channel.send(
                    "ℹ️ You already have an active keywords subscription. Use `!watcher keywords unsubscribe <category>` first if you want to change."
                )
                return
            if tipo_actual in ['plana', 'ia']:
                await message.channel.send(
                    f"⚠️ You have an active '{tipo_actual}' subscription. You can only have ONE subscription type at a time. Use `!watcher reset` to clear all subscriptions."
                )
                return

            if db.subscribe_keywords(user_id, palabras_clave, None, category, feed_id):
                if feed_id:
                    await message.channel.send(f"🔍 **Keywords subscription** to feed {feed_id} in '{category}' - Searching: '{palabras_clave}'")
                elif category:
                    await message.channel.send(f"🔍 **Keywords subscription** to '{category}' - Searching: '{palabras_clave}'")
                else:
                    await message.channel.send(f"🔍 **Global keywords subscription** - Searching: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error subscribing to keywords")

        except Exception as e:
            logger.exception(f"Error in cmd_keywords_subscribe: {e}")
            await message.channel.send("❌ Error subscribing to keywords")
    
    async def cmd_keywords_add(self, message, args):
        """Add a keyword to the user's saved keyword list."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher keywords add <keyword>`")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            palabra = args[0]
            
            # Obtener palabras actuales
            palabras_actuales = db.get_user_keywords(user_id)
            
            if not palabras_actuales:
                # Si no tiene palabras, crear nueva lista
                if db.subscribe_keywords(user_id, palabra, None, None, None):
                    await message.channel.send(f"✅ Palabra clave '{palabra}' añadida. Lista: {palabra}")
                else:
                    await message.channel.send("❌ Error al añadir palabra clave")
            else:
                # Añadir a la lista existente
                lista_palabras = palabras_actuales.split(',')
                if palabra in lista_palabras:
                    await message.channel.send(f"ℹ️ La palabra '{palabra}' ya está en tu lista")
                    return
                
                lista_palabras.append(palabra)
                nuevas_palabras = ','.join(lista_palabras)
                
                if db.update_user_keywords(user_id, nuevas_palabras):
                    await message.channel.send(f"✅ Palabra clave '{palabra}' añadida. Lista actual: {nuevas_palabras}")
                else:
                    await message.channel.send("❌ Error al añadir palabra clave")
                    
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_add: {e}")
            await message.channel.send("❌ Error al añadir palabra clave")
    
    async def cmd_keywords_list(self, message, args):
        """List the user's saved keywords."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            palabras = db.get_user_keywords(user_id)
            
            if not palabras:
                await message.channel.send("📝 No tienes palabras clave configuradas")
                return
            
            lista_palabras = palabras.split(',')
            
            embed = discord.Embed(
                title="🔍 Tus Palabras Clave",
                description=f"Tienes {len(lista_palabras)} palabras clave configuradas:",
                color=discord.Color.blue()
            )
            
            for i, palabra in enumerate(lista_palabras, 1):
                embed.add_field(name=f"#{i}", value=palabra, inline=False)
            
            embed.set_footer(text="Use !watcher keywords add <keyword> to add more")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_list: {e}")
            await message.channel.send("❌ Error al mostrar palabras clave")
    
    async def cmd_keywords_mod(self, message, args):
        """Modify a saved keyword by index."""
        if len(args) < 2:
            await message.channel.send("📝 Usage: `!watcher keywords mod <number> \"new keyword\"`")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            try:
                num = int(args[0]) - 1  # Convertir a 0-based index
                if num < 0:
                    raise ValueError
            except ValueError:
                await message.channel.send("❌ El número debe ser un entero positivo")
                return
            
            nueva_palabra = args[1].strip('"\'')
            
            palabras = db.get_user_keywords(user_id)
            if not palabras:
                await message.channel.send("❌ No tienes palabras clave configuradas")
                return
            
            lista_palabras = palabras.split(',')
            
            if num >= len(lista_palabras):
                await message.channel.send(f"❌ No tienes palabra #{num + 1}. Tienes {len(lista_palabras)} palabras")
                return
            
            palabra_antigua = lista_palabras[num]
            lista_palabras[num] = nueva_palabra
            palabras_actualizadas = ','.join(lista_palabras)
            
            if db.update_user_keywords(user_id, palabras_actualizadas):
                await message.channel.send(f"✅ Palabra #{num + 1} modificada: '{palabra_antigua}' → '{nueva_palabra}'")
            else:
                await message.channel.send("❌ Error al modificar palabra clave")
                
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_mod: {e}")
            await message.channel.send("❌ Error al modificar palabra clave")
    
    async def cmd_keywords_subscribe_existing(self, message, args):
        """Subscribe to a category/feed using the user's existing saved keywords."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher keywords subscribe <category> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            category = self._normalize_category(args[0])
            feed_id = None
            
            # Ensure the user has saved keywords
            palabras = db.get_user_keywords(user_id)
            if not palabras:
                await message.channel.send("❌ You have no saved keywords. Use `!watcher keywords add <keyword>` first")
                return
            
            # Check if it's a specific feed_id
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verify that the feed exists and belongs to the category
                    feeds = db.get_active_feeds(category)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(f"❌ Feed ID {feed_id} not found in category '{category}'")
                        return
                except ValueError:
                    await message.channel.send(get_message('invalid_feed_id'))
                    return
            else:
                # Verify category exists
                categorys = db.get_available_categories()
                if not any(cat[0] == category for cat in categorys):
                    await message.channel.send(get_message('error_kategori_no_encontrada', category=category))
                    return
            
            # Check current subscription type of the user
            tipo_actual = db.check_user_subscription_type(user_id)
            
            # If already has keywords subscription, block
            if tipo_actual == 'palabras':
                await message.channel.send("ℹ️ You already have an active keywords subscription. Use `!watcher keywords unsubscribe <category>` first if you want to change.")
                return
            
            # If has other subscription types, block
            if tipo_actual in ['plana', 'ia']:
                await message.channel.send(
                    f"⚠️ You have an active '{tipo_actual}' subscription. You can only have ONE subscription type at a time. Use `!watcher reset` to clear all subscriptions."
                )
                return
            
            # Create keywords subscription
            if db.subscribe_keywords(user_id, palabras, None, category, feed_id):
                if feed_id:
                    await message.channel.send(f"🔍 **Keywords subscription** to feed {feed_id} in '{category}' - Searching: '{palabras}'")
                else:
                    await message.channel.send(f"🔍 **Keywords subscription** to '{category}' - Searching: '{palabras}'")
            else:
                await message.channel.send("❌ Error subscribing to keywords")
                
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_subscribe_existing: {e}")
            await message.channel.send("❌ Error subscribing to keywords")
    
    async def cmd_palabras_suscripciones(self, message, args):
        """Show active keyword subscriptions."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            suscripciones = db.get_user_keyword_subscriptions(user_id)
            
            if not suscripciones:
                await message.channel.send("📝 You have no active keyword subscriptions")
                return
            
            embed = discord.Embed(
                title="🔍 Keyword Subscriptions",
                description=f"You have {len(suscripciones)} active subscriptions:",
                color=discord.Color.blue()
            )
            
            for i, (category, feed_id, palabras) in enumerate(suscripciones, 1):
                if feed_id:
                    embed.add_field(
                        name=f"#{i} - {category} (Feed {feed_id})",
                        value=f"Palabras: {palabras}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"#{i} - {category}",
                        value=f"Palabras: {palabras}",
                        inline=False
                    )
            
            embed.set_footer(text="Usa !vigia palabras desuscribir <categoría> para cancelar")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_suscripciones: {e}")
            await message.channel.send("❌ Error al mostrar suscripciones")
    
    async def cmd_keywords_unsubscribe(self, message, args):
        """Cancel a user's keywords subscription for a category."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher keywords unsubscribe <category>`")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            category = self._normalize_category(args[0])
            
            if db.cancel_user_keyword_subscription(user_id, category):
                await message.channel.send(f"✅ Keywords subscription canceled for '{category}'")
            else:
                await message.channel.send(f"❌ You don't have a keywords subscription in '{category}'")
                
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling subscription")
    
    async def cmd_palabras_cancelar(self, message, args):
        """Cancela suscripción a palabras clave."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia cancelar_palabras \"palabra1,palabra2\"`")
            return
        
        try:
            db = self._get_db()
            palabras_clave = " ".join(args).strip('"\'')
            
            if db.cancel_keyword_subscription(str(message.author.id), palabras_clave):
                await message.channel.send(f"✅ Suscripción cancelada: '{palabras_clave}'")
            else:
                await message.channel.send("❌ No se encontró esa suscripción de palabras clave")
                
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_cancelar: {e}")
            await message.channel.send("❌ Error al cancelar suscripción de palabras clave")
    
    async def cmd_mixto_suscribir(self, message, args):
        """Suscribe a feeds especializados + generales de una categoría."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia mixto <categoría>`")
            return
        
        try:
            db = self._get_db()
            category = self._normalize_category(args[0])
            
            # Verify that the category exists
            categorys = db.get_available_categories()
            if not any(cat[0] == category for cat in categorys):
                await message.channel.send(get_message('category_no_encontrada', category=category))
                return
            
            # Suscribir a feeds especializados (sin feed_id)
            if db.subscribe_user_category(str(message.author.id), category):
                # También suscribir a feeds generales si existen
                feeds = db.get_active_feeds(category)
                feeds_generales = [f for f in feeds if f[8] == 'general']
                
                for feed in feeds_generales:
                    db.subscribe_user_category(str(message.author.id), category, feed[0])
                
                if feeds_generales:
                    await message.channel.send(f"✅ Suscrito a cobertura mixta de '{category}' (especializado + general)")
                else:
                    await message.channel.send(f"✅ Suscrito a cobertura especializada de '{category}'")
            else:
                await message.channel.send("❌ Error al realizar suscripción mixta")
                
        except Exception as e:
            logger.exception(f"Error en cmd_mixto_suscribir: {e}")
            await message.channel.send("❌ Error al suscribirse a cobertura mixta")
    
    async def cmd_estado_palabras(self, message, args):
        """Muestra suscripciones de palabras clave del usuario."""
        try:
            db = self._get_db()
            suscripciones = db.get_keyword_subscriptions(str(message.author.id))
            
            if not suscripciones:
                await message.channel.send(get_message('error_no_hay_palabras_clave'))
                return
            
            embed = discord.Embed(
                title=f"🔍 Tus Palabras Clave - {message.author.display_name}",
                color=discord.Color.dark_blue(),
                timestamp=datetime.now()
            )
            
            valor = ""
            for palabras, fecha in suscripciones:
                valor += f"🔑 **{palabras}**\n"
                valor += f"📅 Suscrito: {fecha[:10]}\n\n"
            
            embed.description = valor
            embed.set_footer(text="Usa !vigia cancelar_palabras \"palabras\" para cancelar")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_estado_palabras: {e}")
            await message.channel.send("❌ Error obteniendo palabras clave")
    
    async def cmd_channel_keywords(self, message, args):
        """Subscribe the current channel to keywords."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel keywords \"kw1,kw2\"`")
            return

        if args and args[0].lower() == "unsubscribe":
            await self.cmd_channel_keywords_unsubscribe(message, args[1:] if len(args) > 1 else [])
            return
        
        # Verificar permisos
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send("❌ You need the 'Manage Channels' permission to subscribe the channel")
            return
        
        try:
            db = self._get_db()
            palabras_clave = " ".join(args).strip('"\'')
            channel = message.channel
            
            if db.subscribe_keywords(str(message.author.id), palabras_clave, str(channel.id)):
                await message.channel.send(f"✅ Channel subscribed to keywords: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error subscribing channel to keywords")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_keywords: {e}")
            await message.channel.send("❌ Error subscribing channel to keywords")
    
    async def cmd_channel_keywords_unsubscribe(self, message, args):
        """Cancel a channel keywords subscription."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel keywords unsubscribe \"kw1,kw2\"`")
            return
        
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can manage channel subscriptions")
            return
        
        try:
            db = self._get_db()
            channel = message.channel
            palabras_clave = " ".join(args).strip('"\'')
            
            if db.cancel_keyword_subscription(str(channel.id), palabras_clave):
                await message.channel.send(f"✅ Channel keywords subscription canceled: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error canceling channel keywords subscription")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_keywords_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling channel keywords subscription")
    
    # ===== COMANDOS DE PREMISAS PARA CANALES =====
    
    async def cmd_channel_premises(self, message, args):
        """Channel premises management command."""
        if not args:
            # Si no subcomando, mostrar lista por defecto
            await self.cmd_channel_premises_list(message, args)
            return
        
        subcomando = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []
        
        if subcomando == 'listar' or subcomando == 'list':
            await self.cmd_channel_premises_list(message, subargs)
        elif subcomando == 'add':
            await self.cmd_channel_premises_add(message, subargs)
        elif subcomando == 'mod':
            await self.cmd_channel_premises_mod(message, subargs)
        else:
            await message.channel.send(f"❌ Subcomando '{subcomando}' not recognized. Usa: list, add, mod")
    
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
            premisas, contexto = db.get_channel_premises_with_context(channel_id)
            
            if not premisas:
                await message.channel.send("📭 No premises configured for this channel.")
                return
            
            embed = discord.Embed(
                title=f"🎯 Channel Premises #{channel.name} ({contexto.title()})",
                description="These are the conditions that make news **CRITICAL** for this channel:",
                color=discord.Color.blue() if contexto == "custom" else discord.Color.red(),
                timestamp=datetime.now()
            )
            
            for i, premisa in enumerate(premisas, 1):
                embed.add_field(
                    name=f"Premisa #{i}",
                    value=f"📍 {premisa}",
                    inline=False
                )
            
            if contexto == "custom":
                embed.set_footer(text="Use !watcherchannel premises add/mod to manage channel premises")
            else:
                embed.set_footer(text="Use !watcherchannel premises add to create custom channel premises")
            
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_list: {e}")
            await message.channel.send("❌ Error listing channel premises")
    
    async def cmd_channel_premises_add(self, message, args):
        """Add a new premise to the channel (max 7)."""
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can manage premisas del channel")
            return
        
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel premises add \"premise text\"`")
            return
        
        try:
            db = self._get_db()
            channel = message.channel
            channel_id = str(channel.id)
            nueva_premisa = " ".join(args).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la premisa.")
                return
            
            success, mensaje = db.add_premise_channel(channel_id, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_add: {e}")
            await message.channel.send("❌ Error adding channel premise")
    
    async def cmd_channel_premises_mod(self, message, args):
        """Modify a specific channel premise by index."""
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can manage premisas del channel")
            return
        
        if len(args) < 2:
            await message.channel.send("📝 Usage: `!watcherchannel premises mod <number> \"new premise\"`")
            return
        
        try:
            db = self._get_db()
            channel = message.channel
            channel_id = str(channel.id)
            
            # Parse number
            try:
                indice = int(args[0])
            except ValueError:
                await message.channel.send("❌ El número debe ser un entero.")
                return
            
            nueva_premisa = " ".join(args[1:]).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la nueva premisa.")
                return
            
            success, mensaje = db.modificar_premisa_channel(channel_id, indice, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_mod: {e}")
            await message.channel.send("❌ Error modifying channel premise")
    
    async def cmd_channel_general_subscribe(self, message, args):
        """AI subscription for a channel: analyze news using channel premises."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel general <category> [feed_id]`")
            return
        
        try:
            # Verificar permisos de admin
            if not message.author.guild_permissions.administrator:
                await message.channel.send("❌ Only administrators can subscribe channels")
                return
            
            db = self._get_db()
            channel_id = str(message.channel.id)
            channel_name = message.channel.name
            server_id = str(message.guild.id)
            server_name = message.guild.name
            category = self._normalize_category(args[0])
            feed_id = None
            
            # Check if it's a specific feed_id
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verify that the feed exists and belongs to the category
                    feeds = db.get_active_feeds(category)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(f"❌ Feed ID {feed_id} no encontrado en categoría '{category}'")
                        return
                except ValueError:
                    await message.channel.send("❌ El feed_id debe ser un número")
                    return
            else:
                # Verify that the category exists
                categorys = db.get_available_categories()
                if not any(cat[0] == category for cat in categorys):
                    await message.channel.send(f"❌ Categoría '{category}' no encontrada")
                    return
            
            # Verificar si el channel tiene premisas configuradas
            premisas, contexto = db.get_premises_with_context(f"channel_{channel_id}")
            if not premisas:
                await message.channel.send("⚠️ This channel has no premises configured. Use `!watcherchannel premises add \"premise\"` before subscribing with AI.")
                return
            
            # Realizar suscripción con IA (agregando premisas del channel)
            premisas_str = ",".join(premisas) if premisas else ""
            if db.subscribe_channel_category_ai(channel_id, channel_name, server_id, server_name, category, feed_id, premisas_str):
                if feed_id:
                    await message.channel.send(f"🤖 **Suscripción con IA del channel** al feed {feed_id} de '{category}' - Analizaré noticias críticas según las premisas del channel")
                else:
                    await message.channel.send(f"🤖 **Suscripción con IA del channel** a '{category}' - Analizaré noticias críticas según las premisas del channel")
            else:
                await message.channel.send("❌ Error al crear suscripción con IA del channel")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_general_subscribe: {e}")
            await message.channel.send("❌ Error processing channel AI subscription")
    
    async def cmd_channel_general_unsubscribe(self, message, args):
        """Cancel a channel AI subscription for category/feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel general unsubscribe <category> [feed_id]`")
            return
        
        try:
            # Verificar permisos de admin
            if not message.author.guild_permissions.administrator:
                await message.channel.send("❌ Only administrators can cancel channel subscriptions")
                return
            
            db = self._get_db()
            channel_id = str(message.channel.id)
            category = self._normalize_category(args[0])
            feed_id = None
            
            # Si hay más argumentos después de la categoría, es el feed_id
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send("❌ El feed_id debe ser un número")
                    return
            
            if db.cancel_category_subscription(f"channel_{channel_id}", category, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ AI subscription for the channel canceled: Feed {feed_id} of '{category}'")
                else:
                    await message.channel.send(f"✅ AI subscription for the channel canceled: Category '{category}'")
            else:
                await message.channel.send("❌ This channel has no active AI subscription in that category/feed")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_general_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling channel AI subscription")
    
    def _get_icono_category(self, category: str) -> str:
        """Get icon for category."""
        iconos = {
            'economy': '💰',
            'international': '🌍',
            'technology': '💻',
            'general': '📰',
            'crypto': '₿',
            'society': '👥',
            'politics': '🏛️',
            'sports': '⚽',
            'culture': '🎭',
            'science': '🔬'
        }
        return iconos.get(category, '📰')
    
    async def cmd_channel_subscribe(self, message, args):
        """Subscribe the current channel to a category or feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel subscribe <category> [feed_id]`")
            return
        
        # Check permissions (requires manage channel)
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send("❌ You need the 'Manage Channels' permission to subscribe the channel")
            return
        
        try:
            db = self._get_db(str(message.guild.id))
            category = self._normalize_category(args[0])
            feed_id = None
            
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
            
            # Check if it's a specific feed_id
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verify that the feed exists and belongs to the category
                    feeds = db.get_active_feeds(category)
                    feed_exists = any(f[0] == feed_id for f in feeds)
                    if not feed_exists:
                        await message.channel.send(get_message('feed_id_not_found', feed_id=feed_id, category=category))
                        return
                except ValueError:
                    await message.channel.send(get_message('feed_id_must_be_number'))
                    return
            else:
                # Verify that the category exists
                categories = db.get_available_categories()
                if not any(cat[0] == category for cat in categories):
                    await message.channel.send(get_message('category_no_encontrada', category=category))
                    return
            
            # Perform AI channel subscription by default
            channel = message.channel
            server = message.guild
            
            # Use AI subscription with role-specific default premises
            try:
                import sys
                import os
                # Add path for premises_manager import
                vigia_path = os.path.dirname(os.path.abspath(__file__))
                if vigia_path not in sys.path:
                    sys.path.insert(0, vigia_path)
                
                from premises_manager import get_premises_manager
                from agent_db import get_active_server_name
                server_name = get_active_server_name()
                if not server_name:
                    raise RuntimeError("No active server configured for premises manager")
                premises_manager = get_premises_manager(server_name)
                default_premises = ", ".join(premises_manager.get_active_premises())
            except:
                # Fallback to generic premises if there's an error
                default_premises = "critical news, important updates, breaking news"
            
            if db.subscribe_channel_category_ai(
                str(channel.id), channel.name, str(server.id), server.name, category, feed_id, default_premises
            ):
                if feed_id:
                    await message.channel.send(get_message('channel_subscription_successful_feed', feed_id=feed_id, category=category))
                else:
                    await message.channel.send(get_message('channel_subscription_successful_category', category=category))
            else:
                await message.channel.send("❌ Error creating channel subscription")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_subscribe: {e}")
            await message.channel.send("❌ Error subscribing the channel")
    
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
                await message.channel.send(get_message('category_no_encontrada', category=category))
                return None
            return None  # No feed_id specified, which is valid

    async def cmd_channel_unsubscribe(self, message, args):
        """Cancel the current channel subscription for a category/feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel unsubscribe <category> [feed_id]`")
            return
        
        # Verificar permisos
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send("❌ You need the 'Manage Channels' permission to cancel subscriptions")
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
                    await message.channel.send(f"✅ Subscription canceled for feed {feed_id} in '{category}'")
                else:
                    await message.channel.send(f"✅ Subscription canceled for category '{category}'")
            else:
                await message.channel.send("❌ No matching subscription found to cancel")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling channel subscription")
    
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
                await message.channel.send("📭 This channel has no active subscriptions.")
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
                icono = self._get_icono_category(category)
                
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
                    name=f"{icono} {name}",
                    value="\n".join(category_parts),
                    inline=False
                )
            
            embed.set_footer(text="Use !watcherchannel unsubscribe <category> to cancel")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_channel_status: {e}")
            await message.channel.send("❌ Error getting channel status")
    
    # ===== PREMISES MANAGEMENT COMMANDS (AI SUBSCRIPTIONS) =====
    
    async def cmd_premises(self, message, args):
        """Premises management command for AI subscriptions."""
        if not args:
            # Si no subcomando, mostrar lista por defecto
            await self.cmd_premises_list(message, args)
            return
        
        subcomando = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []
        
        if subcomando == 'listar' or subcomando == 'list':
            await self.cmd_premises_list(message, subargs)
        elif subcomando == 'add':
            await self.cmd_premises_add(message, subargs)
        elif subcomando == 'mod':
            await self.cmd_premises_mod(message, subargs)
        else:
            await message.channel.send(f"❌ Subcomando '{subcomando}' not recognized. Usa: list, add, mod")
    
    async def cmd_premises_list(self, message, args):
        """List all user premises (custom or global)."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Obtener premisas con contexto
            premisas, contexto = db.get_premises_with_context(user_id)
            
            if not premisas:
                await message.channel.send("📭 No hay premisas configuradas.")
                return
            
            embed = discord.Embed(
                title=f"🎯 Tus Premisas ({contexto.title()})",
                description="Estas son las condiciones que hacen una noticia **CRÍTICA** for you:",
                color=discord.Color.blue() if contexto == "custom" else discord.Color.red(),
                timestamp=datetime.now()
            )
            
            for i, premisa in enumerate(premisas, 1):
                embed.add_field(
                    name=f"Premisa #{i}",
                    value=f"📍 {premisa}",
                    inline=False
                )
            
            if contexto == "custom":
                embed.set_footer(text="Usa !vigia premisas add/mod para manage tus premisas")
            else:
                embed.set_footer(text="Usa !vigia premisas add para crear premisas custom")
            
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_premises_list: {e}")
            await message.channel.send("❌ Error listing your premises")
    
    async def cmd_premises_add(self, message, args):
        """Add a new premise (max 7)."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher premises add \"premise text\"`")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            nueva_premisa = " ".join(args).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la premisa.")
                return
            
            success, mensaje = db.add_premise_usuario(user_id, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_premises_add: {e}")
            await message.channel.send("❌ Error adding premise")
    
    async def cmd_premises_mod(self, message, args):
        """Modify a premise by index."""
        if len(args) < 2:
            await message.channel.send("📝 Usage: `!watcher premises mod <number> \"new premise\"`")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Parse number
            try:
                indice = int(args[0])
            except ValueError:
                await message.channel.send("❌ El número debe ser un entero.")
                return
            
            nueva_premisa = " ".join(args[1:]).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la nueva premisa.")
                return
            
            success, mensaje = db.modificar_premisa_usuario(user_id, indice, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_premises_mod: {e}")
            await message.channel.send("❌ Error modifying premise")
    
    async def cmd_premises_add(self, message, args):
        """Add a new global premise (admins only)."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher premises add \"premise text\"`")
            return
        
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can manage premisas globales")
            return
        
        try:
            from agent_db import get_active_server_name
            server_name = get_active_server_name()
            if not server_name:
                raise RuntimeError("No active server configured for premises manager")
            premises_manager = get_premises_manager(server_name)
            
            nueva_premisa = " ".join(args).strip('"\'')
            
            if premises_manager.add_premise(new_premise):
                await message.channel.send(f"✅ Global premise added: \"{new_premise}\"")
            else:
                await message.channel.send("⚠️ That global premise already exists")
                
        except Exception as e:
            logger.exception(f"Error in cmd_premises_add: {e}")
            await message.channel.send("❌ Error adding global premise")
    
    async def cmd_premises_delete(self, message, args):
        """Delete an existing global premise (admins only)."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher premises delete \"premise text\"`")
            return
        
        # Check admin permissions
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can manage global premises")
            return
        
        try:
            from agent_db import get_active_server_name
            server_name = get_active_server_name()
            if not server_name:
                raise RuntimeError("No active server configured for premises manager")
            premises_manager = get_premises_manager(server_name)
            
            premise_to_delete = " ".join(args).strip('"\'')
            
            if premises_manager.remove_premise(premise_to_delete):
                await message.channel.send(f"🗑️ Global premise deleted: \"{premise_to_delete}\"")
            else:
                await message.channel.send("⚠️ That global premise was not found")
                
        except Exception as e:
            logger.exception(f"Error in cmd_premisas_eliminar: {e}")
            await message.channel.send("❌ Error deleting global premise")
    
    async def cmd_mis_premisas(self, message, args):
        """Show user's custom premises."""
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            user_premises = db.get_user_premises(user_id)
            
            if not user_premises:
                await message.channel.send("📭 You have no custom premises. You will use global premises.\nUse `!watcher premises configure` to create your custom premises.")
                return
            
            embed = discord.Embed(
                title=f"🎯 Your Custom Premises",
                description="These are your **personal** conditions for critical news:",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            for i, premisa in enumerate(user_premises, 1):
                embed.add_field(
                    name=f"Your Premise #{i}",
                    value=f"📍 {premisa}",
                    inline=False
                )
            
            embed.set_footer(text="Maximum 7 custom premises. Use !watcher premises configure to modify them")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_mis_premisas: {e}")
            await message.channel.send("❌ Error getting your premises")
    
    async def cmd_configure_premises(self, message, args):
        """Configure user's custom premises."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher premises configure \"premise1,premise2,premise3\"`\nMaximum 7 premises, separated by commas.")
            return
        
        try:
            db = self._get_db()
            user_id = str(message.author.id)
            
            # Extract and clean premises
            premises_text = " ".join(args).strip('"\'')
            premises_list = [p.strip() for p in premises_text.split(',') if p.strip()]
            
            if len(premises_list) > 7:
                await message.channel.send("❌ You can have maximum 7 custom premises.")
                return
            
            if not premises_list:
                await message.channel.send("❌ You must provide at least one premise.")
                return
            
            if db.update_user_premises(user_id, premises_list):
                await message.channel.send(f"✅ Your custom premises have been configured ({len(premises_list)} premises).\nUse `!watcher premises my_premises` to see them.")
            else:
                await message.channel.send("❌ Error configuring your premises")
                
        except Exception as e:
            logger.exception(f"Error in cmd_configurar_premisas: {e}")
            await message.channel.send("❌ Error configuring your premises")
    
    def _get_bandera_pais(self, pais: str) -> str:
        """Get flag for country."""
        banderas = {
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
        return banderas.get(pais, '🌐')

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
            for category, feed_id, palabras in keyword_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'keyword',
                    'keywords': palabras,
                    'type': 'Keywords (Filtered)'
                })
            
            # Get AI subscriptions
            ai_subs = db.get_user_ai_subscriptions(user_id)
            for category, feed_id, premisas in ai_subs:
                all_subscriptions.append({
                    'category': category,
                    'feed_id': feed_id,
                    'method': 'general',
                    'premises': premisas,
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

    async def _handle_flat_subscribe(self, message, user_id: str, category: str, feed_id: int):
        """Handle flat subscription."""
        try:
            db = self._get_db()
            
            # Check subscription limits
            can_user_sub, user_msg = db.can_user_subscribe(user_id)
            if not can_user_sub:
                await message.channel.send(f"❌ {user_msg}")
                return
            
            # Create flat subscription
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

    async def _handle_keyword_subscribe(self, message, user_id: str, category: str, feed_id: int):
        """Handle keyword subscription."""
        try:
            db = self._get_db()
            
            # Check if user has keywords configured
            palabras = db.get_user_keywords(user_id)
            if not palabras:
                await message.channel.send("⚠️ You have no keywords configured. Use `!watcher keywords add <keyword>` first.")
                return
            
            # Check subscription limits
            can_user_sub, user_msg = db.can_user_subscribe(user_id)
            if not can_user_sub:
                await message.channel.send(f"❌ {user_msg}")
                return
            
            # Create keyword subscription
            if db.subscribe_keywords(user_id, palabras, None, category, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ **Keyword subscription** to feed {feed_id} in '{category}' - Filtering: '{palabras}'")
                else:
                    await message.channel.send(f"✅ **Keyword subscription** to '{category}' - Filtering: '{palabras}'")
            else:
                await message.channel.send("❌ Error creating keyword subscription")
                
        except Exception as e:
            logger.exception(f"Error in keyword subscribe: {e}")
            await message.channel.send("❌ Error processing keyword subscription")

    async def _handle_general_subscribe(self, message, user_id: str, category: str, feed_id: int):
        """Handle general (AI) subscription."""
        try:
            db = self._get_db()
            
            # Ensure the user has premises configured
            premisas, contexto = db.get_premises_with_context(user_id)
            if not premisas:
                await message.channel.send("⚠️ You have no premises configured. Use `!watcher premises add <premise>` before subscribing.")
                return
            
            # Check subscription limits
            can_user_sub, user_msg = db.can_user_subscribe(user_id)
            if not can_user_sub:
                await message.channel.send(f"❌ {user_msg}")
                return
            
            # Create AI subscription
            premisas_str = ",".join(premisas) if premisas else ""
            if db.subscribe_user_category_ai(user_id, category, feed_id, premisas_str):
                if feed_id:
                    await message.channel.send(f"🤖 **AI subscription** to feed {feed_id} in '{category}' - I'll analyze critical news using your premises")
                else:
                    await message.channel.send(f"🤖 **AI subscription** to '{category}' - I'll analyze critical news using your premises")
            else:
                await message.channel.send("❌ Error creating AI subscription")
                
        except Exception as e:
            logger.exception(f"Error in general subscribe: {e}")
            await message.channel.send("❌ Error processing AI subscription")


