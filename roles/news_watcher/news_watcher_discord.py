"""
Discord commands for the News Watcher role (English version).
Registers: !watcher, !nowatcher, !watchernotify, !nowatchernotify, !watcherhelp, !watcherchannelhelp, !watcherchannel
"""

import discord
from discord.ext import commands
from agent_logging import get_logger
from agent_engine import PERSONALIDAD
from discord_bot.discord_utils import send_dm_or_channel

logger = get_logger('news_watcher_discord')

# Availability flags (evaluated on import)
try:
    from roles.news_watcher.watcher_commands import WatcherCommands
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
    WATCHER_COMMANDS_AVAILABLE = True
except ImportError as e:
    WATCHER_COMMANDS_AVAILABLE = False
    WatcherCommands = None
    get_news_watcher_db_instance = None
    logger.warning(f"News Watcher dependencies not available: {e}")

try:
    from roles.news_watcher.watcher_messages import get_message
except ImportError:
    def get_message(key, **kwargs):
        return "✅ I have sent you the help by private message 📩"


def _get_news_watcher_db(guild):
    """Get news watcher database instance for a server."""
    if not WATCHER_COMMANDS_AVAILABLE or get_news_watcher_db_instance is None:
        return None
    from discord_utils import get_server_key
    server_key = get_server_key(guild)
    return get_news_watcher_db_instance(server_key)


def register_news_watcher_commands(bot, personality, agent_config):
    """Register all News Watcher commands (idempotent)."""

    if not WATCHER_COMMANDS_AVAILABLE:
        logger.warning("News Watcher not available, skipping command registration")
        return

    watcher_commands = WatcherCommands(bot)

    # --- !watcher ---
    if bot.get_command("watcher") is None:
        @bot.command(name="watcher")
        async def cmd_watcher(ctx, *args):
            """Main News Watcher command (works by DM)."""
            db_watcher = _get_news_watcher_db(ctx.guild)
            if not db_watcher:
                await ctx.send("❌ Error accessing News Watcher database.")
                return

            if not args:
                await ctx.author.send("📡 **News Watcher** - Use `!watcherhelp` to see all available commands.")
                if ctx.guild:
                    help_sent_msg = get_message("help_sent_private")
                    await ctx.send(help_sent_msg)
                return

            subcommand = args[0].lower()
            subargs = args[1:] if len(args) > 1 else []

            dispatch = {
                "feeds": watcher_commands.cmd_feeds,
                "categories": watcher_commands.cmd_categories,
                "status": watcher_commands.cmd_status,
                "subscribe": watcher_commands.cmd_unified_subscribe,
                "unsubscribe": watcher_commands.cmd_unsubscribe,
                "subscriptions": watcher_commands.cmd_subscriptions,
                "frequency": watcher_commands.cmd_frequency,
                "premises": watcher_commands.cmd_premises,
                "mod": watcher_commands.cmd_premises_mod,
                "reset": watcher_commands.cmd_reset,
                "method": watcher_commands.cmd_method,
                "keywords": watcher_commands.cmd_keywords_subscribe,  # Keep for keyword management
                "general": watcher_commands.cmd_general_subscribe,    # Keep for general management
                # Additional commands that should be available
                "add_feed": watcher_commands.cmd_add_feed,
                "categories": watcher_commands.cmd_categories,  # English command for categories
                "categorias": watcher_commands.cmd_categories,  # Spanish alias for backward compatibility
            }

            handler = dispatch.get(subcommand)
            if handler:
                try:
                    await handler(ctx, subargs)
                except Exception as e:
                    logger.error(f"Error in watcher command {subcommand}: {e}")
                    await ctx.author.send("❌ Error executing command. Please try again.")
                    if ctx.guild:
                        error_msg = "📩 Error sent by private message."
                        await ctx.send(error_msg)
            else:
                await ctx.author.send(f"❌ Subcommand `{subcommand}` not recognized. Use `!watcherhelp` to see help.")
                if ctx.guild:
                    help_sent_msg = get_message("help_sent_private")
                    await ctx.send(help_sent_msg)

        logger.info("📡 Watcher command registered")

    # --- !nowatcher ---
    if bot.get_command("nowatcher") is None:
        @bot.command(name="nowatcher")
        async def cmd_no_watcher(ctx):
            """Deactivate News Watcher role (works by DM)."""
            db_watcher = _get_news_watcher_db(ctx.guild)
            if not db_watcher:
                await ctx.send("❌ Error accessing News Watcher database.")
                return

            user_id = str(ctx.author.id)
            if not db_watcher.is_subscribed(user_id):
                await ctx.author.send("🛡️ You are not subscribed to Tower Watcher alerts.")
                if ctx.guild:
                    await ctx.send("📩 Response sent by private message.")
                return

            if db_watcher.remove_subscription(user_id):
                await ctx.author.send("✅ You have unsubscribed from Tower Watcher alerts. You will no longer receive critical news.")
                if ctx.guild:
                    await ctx.send("📩 Response sent by private message.")
                logger.info(f"📡 {ctx.author.name} ({user_id}) unsubscribed from alerts")
            else:
                await ctx.send("❌ Error unsubscribing from alerts. Please try again.")

        logger.info("📡 No watcher command registered")

    # --- !watchernotify ---
    if bot.get_command("watchernotify") is None:
        @bot.command(name="watchernotify")
        async def cmd_watcher_notify(ctx):
            """Alias to subscribe to critical Watcher alerts (works by DM)."""
            db_watcher = _get_news_watcher_db(ctx.guild)
            if not db_watcher:
                await ctx.send("❌ Error accessing News Watcher database.")
                return

            user_id = str(ctx.author.id)
            user_name = ctx.author.name

            if db_watcher.is_subscribed(user_id):
                await ctx.author.send("🛡️ You are already subscribed to Tower Watcher alerts.")
                if ctx.guild:
                    await ctx.send("📩 Response sent by private message.")
                return

            if db_watcher.add_subscription(user_id, user_name):
                await ctx.author.send("✅ You have subscribed to Tower Watcher alerts. You will receive critical news when they occur.")
                await ctx.author.send("💡 Use `!watcherhelp` to see all available Watcher commands.")
                if ctx.guild:
                    await ctx.send("📩 Response sent by private message.")
                logger.info(f"📡 {user_name} ({user_id}) subscribed to alerts")
            else:
                await ctx.send("❌ Error subscribing to alerts. Please try again.")

        logger.info("📡 Watcher notify command registered")

    # --- !nowatchernotify ---
    if bot.get_command("nowatchernotify") is None:
        @bot.command(name="nowatchernotify")
        async def cmd_no_watcher_notify(ctx):
            """Alias to unsubscribe from critical Watcher alerts (works by DM)."""
            db_watcher = _get_news_watcher_db(ctx.guild)
            if not db_watcher:
                await ctx.send("❌ Error accessing News Watcher database.")
                return

            user_id = str(ctx.author.id)
            user_name = ctx.author.name

            if not db_watcher.is_subscribed(user_id):
                await ctx.author.send("🛡️ You are not subscribed to Tower Watcher alerts.")
                if ctx.guild:
                    await ctx.send("📩 Response sent by private message.")
                return

            if db_watcher.remove_subscription(user_id):
                await ctx.author.send("✅ You have unsubscribed from Tower Watcher alerts. You will no longer receive critical news.")
                await ctx.author.send("💡 Use `!watcherhelp` to see all available Watcher commands.")
                if ctx.guild:
                    await ctx.send("📩 Response sent by private message.")
                logger.info(f"📡 {user_name} ({user_id}) unsubscribed from alerts")
            else:
                await ctx.send("❌ Error unsubscribing from alerts. Please try again.")

        logger.info("📡 No watcher notify command registered")

    # --- !watcherhelp ---
    if bot.get_command("watcherhelp") is None:
        @bot.command(name="watcherhelp")
        async def cmd_watcher_help(ctx):
            """Show News Watcher specific help (users)."""
            # Prevent duplication
            message_id = f"{ctx.message.id}_{ctx.author.id}"
            if hasattr(bot, '_processed_help_messages'):
                if message_id in bot._processed_help_messages:
                    return
            else:
                bot._processed_help_messages = set()
            bot._processed_help_messages.add(message_id)

            # Get method-specific help if on a server
            if ctx.guild:
                db_watcher = _get_news_watcher_db(ctx.guild)
                if db_watcher:
                    server_id = str(ctx.guild.id)
                    current_method = db_watcher.get_method_config(server_id)
                    watcher_help = _build_watcher_help_text_method_specific(current_method)
                else:
                    watcher_help = _build_watcher_help_text()
            else:
                watcher_help = _build_watcher_help_text()

            # Use personality-specific message with fallback
            help_sent_msg = get_message("help_sent_private")
            await send_dm_or_channel(ctx, watcher_help, help_sent_msg)

        logger.info("📡 Watcher help command registered")

    # --- !watcherchannelhelp ---
    if bot.get_command("watcherchannelhelp") is None:
        @bot.command(name="watcherchannelhelp")
        async def cmd_watcher_channel_help(ctx):
            """Show News Watcher specific help for channels (admins only)."""
            if not ctx.guild:
                await ctx.send("❌ This command only works on servers, not in private messages.")
                return
            if not ctx.author.guild_permissions.administrator:
                await ctx.send("❌ Only administrators can use this command.")
                return

            db_watcher = _get_news_watcher_db(ctx.guild)
            if not db_watcher:
                await ctx.send("❌ Error accessing News Watcher database.")
                return

            # Get method-specific help
            server_id = str(ctx.guild.id)
            current_method = db_watcher.get_method_config(server_id)
            help_msg = _build_watcher_channel_help_text_method_specific(current_method)
            await ctx.send(help_msg[:2000])

        logger.info("📡 Watcher channel help command registered")

    # --- !watcherchannel ---
    if bot.get_command("watcherchannel") is None:
        @bot.command(name="watcherchannel")
        async def cmd_watcher_channel(ctx, *args):
            """Watcher commands for channel (server only)."""
            if ctx.guild is None:
                await ctx.send("❌ This command can only be used on a server, not in direct messages.")
                return
            if not args:
                await ctx.send("❌ You must specify an action. Use `!watcherchannelhelp` to see help.")
                return

            subcommand = args[0].lower()
            subargs = args[1:] if len(args) > 1 else []

            dispatch = {
                "subscribe": watcher_commands.cmd_channel_subscribe,
                "unsubscribe": watcher_commands.cmd_channel_unsubscribe,
                "status": watcher_commands.cmd_channel_status,
                "keywords": watcher_commands.cmd_channel_keywords,
                "premises": watcher_commands.cmd_channel_premises,
                "general": watcher_commands.cmd_channel_general_subscribe,
            }

            handler = dispatch.get(subcommand)
            if handler:
                try:
                    # Special handling for general unsubscribe
                    if subcommand == "general" and len(subargs) > 0 and subargs[0].lower() == "unsubscribe":
                        await watcher_commands.cmd_channel_general_unsubscribe(ctx, subargs[1:] if len(subargs) > 1 else [])
                    else:
                        await handler(ctx, subargs)
                except Exception as e:
                    logger.error(f"Error in watcher channel command {subcommand}: {e}")
                    await ctx.send("❌ Error executing command. Please try again.")
            else:
                await ctx.send(f"❌ Subcommand `{subcommand}` not recognized. Use `!watcherchannelhelp` to see help.")

        logger.info("📡 Watcher channel command registered")

    # --- !forcewatcher ---
    if bot.get_command("forcewatcher") is None:
        @bot.command(name="forcewatcher")
        @commands.has_permissions(administrator=True)
        async def cmd_force_watcher(ctx):
            """Force news watcher to check subscriptions (Admin only)."""
            from roles.news_watcher.news_watcher import process_channel_subscriptions
            from roles.news_watcher.global_news_db import get_global_news_db
            from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
            
            try:
                await ctx.send("🔄 **Forcing news watcher iteration...**")
                
                # Get database instance
                db = get_news_watcher_db_instance(str(ctx.guild.id))
                global_db = get_global_news_db()
                
                # Use our custom DiscordHTTP client for notifications
                from discord_bot.discord_http import DiscordHTTP
                from agent_engine import get_discord_token
                http = DiscordHTTP(get_discord_token())
                
                # Force the watcher to process all channel subscriptions
                await process_channel_subscriptions(http, db, global_db, str(ctx.guild.id))
                
                await ctx.send("✅ **News watcher iteration completed!**\n"
                              "📊 Checked all channel subscriptions for new articles.\n"
                              "📰 Any new articles will be processed and notifications sent.")
                
            except Exception as e:
                await ctx.send(f"❌ **Error running news watcher:** `{str(e)}`")
                import traceback
                traceback.print_exc()
    
    logger.info("📡 All News Watcher commands registered")


def _build_watcher_help_text():
    """Build News Watcher help text for users."""
    help_text = "📡 **News Watcher Help - Users** 📡\n\n"
    help_text += "⚠️ **IMPORTANT:** Each subscription can have its own method (flat, keyword, or general)\n"
    help_text += "• You can have up to 3 subscriptions with different methods\n"
    help_text += "• Each subscription is independent and has its own configuration\n\n"
    help_text += "📊 **Subscription Limits:**\n"
    help_text += "• **Users:** Maximum 3 subscriptions per person\n"
    help_text += "• **Channels:** Maximum 3 subscriptions per channel\n"
    help_text += "• **Server:** Maximum 15 total subscriptions\n\n"
    help_text += "🎯 **Main Commands:**\n"
    help_text += "• `!watcher subscribe <method> <category> [feed_id]` - Subscribe with specific method\n"
    help_text += "• `!watcher unsubscribe <number>` - Cancel subscription by list number\n"
    help_text += "• `!watcher subscriptions` - Show numbered list of all subscriptions\n"
    help_text += "• `!watcher status` - Your subscription count and limits\n"
    help_text += "• `!watcher feeds` - List available RSS feeds\n"
    help_text += "• `!watcher categories` - Show active categories\n\n"
    help_text += "🔧 **Method Selection:**\n"
    help_text += "• `!watcher subscribe flat <category>` - All news with AI opinions\n"
    help_text += "• `!watcher subscribe keyword <category>` - Filtered by your keywords\n"
    help_text += "• `!watcher subscribe general <category>` - AI critical analysis\n\n"
    help_text += "⚙️ **Configuration Commands:**\n"
    help_text += "• `!watcher premises add \"text\"` - Add premise (for general method)\n"
    help_text += "• `!watcher premises list` - See your premises\n"
    help_text += "• `!watcher keywords add <word>` - Add keyword (for keyword method)\n"
    help_text += "• `!watcher keywords list` - See your keywords\n\n"
    help_text += "🔄 **Subscription Management:**\n"
    help_text += "• `!watcher reset confirm` - Delete ALL your subscriptions\n"
    help_text += "• **Use unsubscribe to remove individual subscriptions**\n\n"
    help_text += "📂 **Categories:** economy, international, technology, general, crypto\n\n"
    help_text += "💡 **Quick Examples:**\n"
    help_text += "```\n!watcher subscribe flat economy           # All economy news with opinions\n!watcher subscribe keyword tech 5          # Tech feed filtered by keywords\n!watcher subscribe general international   # AI-analyzed critical international news\n!watcher subscriptions                    # See all your subscriptions numbered\n!watcher unsubscribe 2                    # Cancel subscription #2 from list\n!watcher status                           # See your subscription count\n!watcher premises add \"I care about AI\"  # Add premise for general method\n!watcher keywords add blockchain          # Add keyword for keyword method\n```\n\n"
    help_text += "📢 **For Admins:** Use `!watcherchannelhelp` for channel commands"
    return help_text


def _build_watcher_help_text_method_specific(method_type: str):
    """Build method-specific News Watcher help text for users."""
    help_text = f"📡 **News Watcher Help - {method_type.title()} Method** 📡\n\n"
    help_text += "⚠️ **IMPORTANT:** You can only have **ONE TYPE** of active subscription at a time\n"
    help_text += "• If you subscribe to a new type, the previous one will be automatically cancelled\n\n"
    
    if method_type == "flat":
        help_text += "📰 **Current Method: Flat (All News)**\n"
        help_text += "You receive ALL news from subscribed categories with AI-generated opinions.\n\n"
        help_text += "🎯 **Available Commands:**\n"
        help_text += "• `!watcher subscribe <category> [feed_id]` - Subscribe to all news\n"
        help_text += "• `!watcher unsubscribe <category> [feed_id]` - Cancel subscription\n"
        help_text += "• `!watcher status` - See your subscriptions\n"
        help_text += "• **Example:** `!watcher subscribe economy`\n"
        help_text += "• **Example:** `!watcher subscribe economy 5` (specific feed)\n\n"
        
    elif method_type == "keyword":
        help_text += "🔍 **Current Method: Keywords (Filtered News)**\n"
        help_text += "You receive news that matches your configured keywords only.\n\n"
        help_text += "🎯 **Available Commands:**\n"
        help_text += "• `!watcher subscribe <category> [feed_id]` - Subscribe with keywords\n"
        help_text += "• `!watcher unsubscribe <category> [feed_id]` - Cancel subscription\n"
        help_text += "• `!watcher keywords add <word>` - Add keyword to your list\n"
        help_text += "• `!watcher keywords list` - See your keywords\n"
        help_text += "• `!watcher status` - See your subscriptions\n"
        help_text += "• **Example:** `!watcher subscribe economy`\n"
        help_text += "• **Example:** `!watcher keywords add bitcoin`\n\n"
        
    elif method_type == "general":
        help_text += "🤖 **Current Method: AI (Critical News Analysis)**\n"
        help_text += "You receive only critical news analyzed by AI according to your premises.\n\n"
        help_text += "🎯 **Available Commands:**\n"
        help_text += "• `!watcher subscribe <category> [feed_id]` - Subscribe with AI analysis\n"
        help_text += "• `!watcher unsubscribe <category> [feed_id]` - Cancel subscription\n"
        help_text += "• `!watcher premises add \"text\"` - Add premise (required first)\n"
        help_text += "• `!watcher premises list` - See your premises\n"
        help_text += "• `!watcher status` - See your subscriptions\n"
        help_text += "• **Example:** `!watcher subscribe economy`\n"
        help_text += "• **Example:** `!watcher premises add \"I care about market trends\"`\n\n"
    
    help_text += "🔄 **Common Commands:**\n"
    help_text += "• `!watcher reset` - See active subscription type\n"
    help_text += "• `!watcher reset confirm` - Delete all subscriptions\n"
    help_text += "• `!watcher feeds` - List available feeds\n"
    help_text += "• `!watcher categories` - Show categories\n\n"
    help_text += "📢 **For Admins:** Use `!watcherchannelhelp` for channel commands"
    return help_text


def _build_watcher_channel_help_text():
    """Build News Watcher help text for channels (admins)."""
    help_text = "📡 **NEWS WATCHER - CHANNEL COMMANDS HELP** 📡\n\n"
    help_text += "🔧 **Administration Commands:**\n"
    help_text += "```\n"
    help_text += "!watcher method - Show current method (admins only)\n\n"
    help_text += "!watcherchannel status                  # See channel subscription status\n"
    help_text += "!watcherchannel subscribe <category> <feed_id>     # Flat subscription for the channel to a feed\n"
    help_text += "!watcherchannel unsubscribe <category>   # Cancel channel flat subscription\n"
    help_text += "!watcherchannel keywords add <word>     # Add keyword to channel\n"
    help_text += "!watcherchannel keywords del <word>     # Remove keyword from channel\n"
    help_text += "!watcherchannel premises add <text>     # Add premise to channel\n"
    help_text += "!watcherchannel premises del <id>       # Remove premise from channel\n"
    help_text += "!watcherchannel general <category> [feed_id]     # Subscribe channel with AI\n"
    help_text += "!watcherchannel general unsubscribe <category> [feed_id]  # Cancel AI subscription\n"
    help_text += "```\n\n"
    help_text += "⏰ **Frequency Management:**\n"
    help_text += "```\n"
    help_text += "!watcher frequency <hours>              # Set check interval (1-24 hours)\n"
    help_text += "!watcher frequency status              # Show current frequency setting\n"
    help_text += "```\n"
    help_text += "• **Default:** 1 hour | **Range:** 1-24 hours\n"
    help_text += "• Affects all user and channel subscriptions\n\n"
    help_text += "💡 **To see all available feeds:** `!watcher feeds`\n"
    help_text += "📋 **To see categories:** `!watcher categories`\n\n"
    help_text += "⚠️ **IMPORTANT - Mutual Exclusion:**\n"
    help_text += "• A channel can have **ONLY ONE TYPE** of active subscription\n"
    help_text += "• When changing type, the previous one is automatically cancelled\n"
    help_text += "• **Types:** Flat (all), Keywords (filtered), AI (critical)\n"
    help_text += "• Only administrators can manage channel subscriptions"
    return help_text


def _build_watcher_channel_help_text_method_specific(method_type: str):
    """Build method-specific News Watcher help text for channels (admins)."""
    help_text = f"📡 **NEWS WATCHER - CHANNEL COMMANDS ({method_type.upper()} METHOD)** 📡\n\n"
    
    if method_type == "flat":
        help_text += "📰 **Current Method: Flat (All News)**\n"
        help_text += "Channels receive ALL news from subscribed categories with AI-generated opinions.\n\n"
        help_text += "🔧 **Available Channel Commands:**\n"
        help_text += "```\n"
        help_text += "!watcherchannel subscribe <category> [feed_id]    # Subscribe to all news\n"
        help_text += "!watcherchannel unsubscribe <category>           # Cancel subscription\n"
        help_text += "!watcherchannel status                          # See subscription status\n"
        help_text += "```\n\n"
        
    elif method_type == "keyword":
        help_text += "🔍 **Current Method: Keywords (Filtered News)**\n"
        help_text += "Channels receive news that matches their configured keywords only.\n\n"
        help_text += "🔧 **Available Channel Commands:**\n"
        help_text += "```\n"
        help_text += "!watcherchannel subscribe <category> [feed_id]    # Subscribe with keywords\n"
        help_text += "!watcherchannel unsubscribe <category>           # Cancel subscription\n"
        help_text += "!watcherchannel keywords add <word>              # Add keyword to channel\n"
        help_text += "!watcherchannel keywords del <word>              # Remove keyword from channel\n"
        help_text += "!watcherchannel status                          # See subscription status\n"
        help_text += "```\n\n"
        
    elif method_type == "general":
        help_text += "🤖 **Current Method: AI (Critical News Analysis)**\n"
        help_text += "Channels receive only critical news analyzed by AI according to channel premises.\n\n"
        help_text += "🔧 **Available Channel Commands:**\n"
        help_text += "```\n"
        help_text += "!watcherchannel subscribe <category> [feed_id]    # Subscribe with AI analysis\n"
        help_text += "!watcherchannel unsubscribe <category>           # Cancel AI subscription\n"
        help_text += "!watcherchannel premises add <text>              # Add premise to channel\n"
        help_text += "!watcherchannel premises del <id>                # Remove premise from channel\n"
        help_text += "!watcherchannel status                          # See subscription status\n"
        help_text += "```\n\n"
    
    help_text += "⏰ **Frequency Management:**\n"
    help_text += "```\n"
    help_text += "!watcher frequency <hours>              # Set check interval (1-24 hours)\n"
    help_text += "!watcher frequency status              # Show current frequency setting\n"
    help_text += "```\n"
    help_text += "• **Default:** 1 hour | **Range:** 1-24 hours\n\n"
    help_text += "💡 **To see all available feeds:** `!watcher feeds`\n"
    help_text += "📋 **To see categories:** `!watcher categories`\n\n"
    help_text += "⚠️ **IMPORTANT - Mutual Exclusion:**\n"
    help_text += "• A channel can have **ONLY ONE TYPE** of active subscription\n"
    help_text += "• When changing type, the previous one is automatically cancelled\n"
    help_text += "• Only administrators can manage channel subscriptions"
    
    return help_text
