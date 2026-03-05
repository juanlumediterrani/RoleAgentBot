"""
Discord commands for the News Watcher role (English version).
Registers: !watcher, !nowatcher, !watchernotify, !nowatchernotify, !watcherhelp, !watcherchannelhelp, !watcherchannel
"""

import discord
from agent_logging import get_logger
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
    from discord_utils import get_server_name
    server_name = get_server_name(guild)
    return get_news_watcher_db_instance(server_name)


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
                    await ctx.send("📩 Help sent by private message.")
                return

            subcommand = args[0].lower()
            subargs = args[1:] if len(args) > 1 else []

            dispatch = {
                "feeds": watcher_commands.cmd_feeds,
                "categories": watcher_commands.cmd_categories,
                "status": watcher_commands.cmd_status,
                "subscribe": watcher_commands.cmd_subscribe,
                "unsubscribe": watcher_commands.cmd_unsubscribe,
                "general": watcher_commands.cmd_general_subscribe,
                "keywords": watcher_commands.cmd_keywords_subscribe,
                "premises": watcher_commands.cmd_premises,
                "mod": watcher_commands.cmd_premises_mod,
                "reset": watcher_commands.cmd_reset,
            }

            handler = dispatch.get(subcommand)
            if handler:
                try:
                    await handler(ctx, subargs)
                except Exception as e:
                    logger.error(f"Error in watcher command {subcommand}: {e}")
                    await ctx.author.send("❌ Error executing command. Please try again.")
                    if ctx.guild:
                        await ctx.send("📩 Error sent by private message.")
            else:
                await ctx.author.send(f"❌ Subcommand `{subcommand}` not recognized. Use `!watcherhelp` to see help.")
                if ctx.guild:
                    await ctx.send("📩 Help sent by private message.")

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

            watcher_help = _build_watcher_help_text()

            confirm_msg = "📩 Help sent by private message."
            await send_dm_or_channel(ctx, watcher_help, confirm_msg)

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

            help_msg = _build_watcher_channel_help_text()
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
            }

            handler = dispatch.get(subcommand)
            if handler:
                try:
                    await handler(ctx, subargs)
                except Exception as e:
                    logger.error(f"Error in watcher channel command {subcommand}: {e}")
                    await ctx.send("❌ Error executing command. Please try again.")
            elif subcommand == "general":
                try:
                    if len(subargs) > 0 and subargs[0].lower() == "unsubscribe":
                        await watcher_commands.cmd_channel_general_unsubscribe(ctx, subargs[1:] if len(subargs) > 1 else [])
                    else:
                        await watcher_commands.cmd_channel_general_subscribe(ctx, subargs)
                except Exception as e:
                    logger.error(f"Error in watcher channel general command: {e}")
                    await ctx.send("❌ Error executing command. Please try again.")
            else:
                await ctx.send(f"❌ Subcommand `{subcommand}` not recognized. Use `!watcherchannelhelp` to see help.")

        logger.info("📡 Watcher channel command registered")

    
    # Legacy Spanish aliases with deprecation warnings
    if bot.get_command("vigia") is None:
        @bot.command(name="vigia")
        async def cmd_vigia_legacy(ctx, *args):
            """Legacy command - use !watcher instead."""
            await ctx.send("⚠️ `!vigia` is deprecated. Use `!watcher` instead.")
            if args:
                await cmd_watcher.invoke(ctx, args)
            else:
                await ctx.send("Use `!watcherhelp` to see available commands.")

    if bot.get_command("novigia") is None:
        @bot.command(name="novigia")
        async def cmd_no_vigia_legacy(ctx):
            """Legacy command - use !nowatcher instead."""
            await ctx.send("⚠️ `!novigia` is deprecated. Use `!nowatcher` instead.")
            await cmd_no_watcher.invoke(ctx)

    if bot.get_command("avisanoticias") is None:
        @bot.command(name="avisanoticias")
        async def cmd_avisa_noticias_legacy(ctx):
            """Legacy command - use !watchernotify instead."""
            await ctx.send("⚠️ `!avisanoticias` is deprecated. Use `!watchernotify` instead.")
            await cmd_watcher_notify.invoke(ctx)

    if bot.get_command("noavisanoticias") is None:
        @bot.command(name="noavisanoticias")
        async def cmd_no_avisa_noticias_legacy(ctx):
            """Legacy command - use !nowatchernotify instead."""
            await ctx.send("⚠️ `!noavisanoticias` is deprecated. Use `!nowatchernotify` instead.")
            await cmd_no_watcher_notify.invoke(ctx)

    if bot.get_command("vigiaayuda") is None:
        @bot.command(name="vigiaayuda")
        async def cmd_vigia_ayuda_legacy(ctx):
            """Legacy command - use !watcherhelp instead."""
            await ctx.send("⚠️ `!vigiaayuda` is deprecated. Use `!watcherhelp` instead.")
            await cmd_watcher_help.invoke(ctx)

    if bot.get_command("vigiacanalayuda") is None:
        @bot.command(name="vigiacanalayuda")
        async def cmd_vigia_canal_ayuda_legacy(ctx):
            """Legacy command - use !watcherchannelhelp instead."""
            await ctx.send("⚠️ `!vigiacanalayuda` is deprecated. Use `!watcherchannelhelp` instead.")
            await cmd_watcher_channel_help.invoke(ctx)

    if bot.get_command("vigiacanal") is None:
        @bot.command(name="vigiacanal")
        async def cmd_vigia_canal_legacy(ctx, *args):
            """Legacy command - use !watcherchannel instead."""
            await ctx.send("⚠️ `!vigiacanal` is deprecated. Use `!watcherchannel` instead.")
            if args:
                await cmd_watcher_channel.invoke(ctx, args)
            else:
                await ctx.send("Use `!watcherchannelhelp` to see available commands.")

    logger.info("📡 All News Watcher commands registered")


def _build_watcher_help_text():
    """Build News Watcher help text for users."""
    help_text = "📡 **News Watcher Help - Users** 📡\n\n"
    help_text += "⚠️ **IMPORTANT:** You can only have **ONE TYPE** of active subscription at a time\n"
    help_text += "• If you subscribe to a new type, the previous one will be automatically cancelled\n\n"
    help_text += "🎯 **Main Commands:**\n"
    help_text += "• `!watcher feeds` - List available RSS feeds\n"
    help_text += "• `!watcher categories` - Show active categories\n"
    help_text += "• `!watcher status` - Your active subscription type\n\n"
    help_text += "📰 **Flat Subscriptions:**\n"
    help_text += "• `!watcher subscribe <category>` - All news with opinion\n"
    help_text += "• **Example:** `!watcher subscribe economy`\n\n"
    help_text += "🔍 **Keywords:**\n"
    help_text += "• `!watcher keywords \"word1,word2\"` - Direct subscription with keywords\n"
    help_text += "• `!watcher keywords add <word>` - Add word to your list\n"
    help_text += "• `!watcher keywords list` - See all your keywords\n"
    help_text += "• `!watcher keywords mod <num> \"new\"` - Modify specific word\n"
    help_text += "• `!watcher keywords subscribe <category>` - Use already configured keywords\n"
    help_text += "• `!watcher keywords subscriptions` - See keyword subscriptions\n"
    help_text += "• `!watcher keywords unsubscribe <category>` - Cancel subscription\n"
    help_text += "• **Example:** `!watcher keywords \"bitcoin,crypto\"`\n\n"
    help_text += "🤖 **AI Subscriptions:**\n"
    help_text += "• `!watcher general <category>` - Critical news according to your premises\n"
    help_text += "• `!watcher general unsubscribe <category>` - Cancel AI subscription\n"
    help_text += "• **Requires:** Configure premises first (`!watcher premises add`)\n"
    help_text += "• **Example:** `!watcher general international`\n\n"
    help_text += "🎯 **Premise Management:**\n"
    help_text += "• `!watcher premises` / `!watcher premises list` - See your premises\n"
    help_text += "• `!watcher premises add \"text\"` - Add premise (max 7)\n"
    help_text += "• `!watcher mod <num> \"new premise\"` - Modify premise #<num>\n\n"
    help_text += "🔄 **Subscription Reset:**\n"
    help_text += "• `!watcher reset` - See what subscription type you have active\n"
    help_text += "• `!watcher reset confirm` - Delete ALL your subscriptions\n"
    help_text += "• **Use it to change subscription type**\n\n"
    help_text += "📊 **Status and Control:**\n"
    help_text += "• `!watcher status` - See your active subscription type\n"
    help_text += "• `!watcher unsubscribe <category>` - Cancel flat subscription\n\n"
    help_text += "📂 **Categories:** economy, international, technology, society, politics\n\n"
    help_text += "💡 **Quick Examples:**\n"
    help_text += "```\n!watcher keywords add bitcoin           # Add keyword\n!watcher keywords list                  # See keywords\n!watcher keywords subscribe economy   # Subscribe with keywords\n!watcher reset                         # See active type\n!watcher reset confirm                 # Clean everything\n!watcher general international         # Subscribe with AI\n```\n\n"
    help_text += "📢 **For Admins:** Use `!watcherchannelhelp` for channel commands"
    return help_text


def _build_watcher_channel_help_text():
    """Build News Watcher help text for channels (admins)."""
    help_text = "📡 **NEWS WATCHER - CHANNEL COMMANDS HELP** 📡\n\n"
    help_text += "🔧 **Administration Commands:**\n"
    help_text += "```\n"
    help_text += "!watcherchannel subscribe <feed_id>     # Subscribe channel to a feed\n"
    help_text += "!watcherchannel unsubscribe <feed_id>   # Cancel channel subscription\n"
    help_text += "!watcherchannel status                  # See channel subscription status\n"
    help_text += "!watcherchannel keywords add <word>     # Add keyword to channel\n"
    help_text += "!watcherchannel keywords del <word>     # Remove keyword from channel\n"
    help_text += "!watcherchannel premises add <text>     # Add premise to channel\n"
    help_text += "!watcherchannel premises del <id>       # Remove premise from channel\n"
    help_text += "!watcherchannel general <category> [feed_id]     # Subscribe channel with AI\n"
    help_text += "!watcherchannel general unsubscribe <category> [feed_id]  # Cancel AI subscription\n"
    help_text += "```\n\n"
    help_text += "💡 **To see all available feeds:** `!watcher feeds`\n"
    help_text += "📋 **To see categories:** `!watcher categories`\n\n"
    help_text += "⚠️ **IMPORTANT - Mutual Exclusion:**\n"
    help_text += "• A channel can have **ONLY ONE TYPE** of active subscription\n"
    help_text += "• When changing type, the previous one is automatically cancelled\n"
    help_text += "• **Types:** Flat (all), Keywords (filtered), AI (critical)\n"
    help_text += "• Only administrators can manage channel subscriptions"
    return help_text
