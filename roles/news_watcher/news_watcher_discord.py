"""
Discord commands for the News Watcher role.
Registers: !forcewatcher, !testwatcher (admin/debug only).
All user commands removed - use !canvas → News Watcher instead.
"""

import discord
from discord.ext import commands
from agent_logging import get_logger
from agent_engine import PERSONALITY
from discord_bot.discord_utils import send_dm_or_channel

logger = get_logger('news_watcher_discord')

# Import forcewatcher dependencies
try:
    from roles.news_watcher.news_watcher import process_subscriptions
    from roles.news_watcher.global_news_db import get_global_news_db
    from roles.news_watcher.db_role_news_watcher import get_news_watcher_db_instance
    FORCEWATCHER_AVAILABLE = True
except ImportError as e:
    FORCEWATCHER_AVAILABLE = False
    logger.warning(f"Force watcher dependencies not available: {e}")

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

def get_message(key, **kwargs):
    return "✅ I have sent you the help by private message 📩"


def _get_news_watcher_db(guild):
    """Get news watcher database instance for a server."""
    if not WATCHER_COMMANDS_AVAILABLE or get_news_watcher_db_instance is None:
        return None
    from discord_bot.discord_utils import get_server_key
    server_key = get_server_key(guild)
    return get_news_watcher_db_instance(server_key)


def register_news_watcher_commands(bot, personality, agent_config):
    """Register all News Watcher commands (idempotent)."""

    if not WATCHER_COMMANDS_AVAILABLE:
        logger.warning("News Watcher not available, skipping command registration")
        return

    watcher_commands = WatcherCommands(bot)

    # NOTE: All News Watcher user commands have been removed. Use !canvas instead.
    # The WatcherCommands class is kept for Canvas UI integration.

    # --- !forcewatcher (unified command) ---
    if bot.get_command("forcewatcher") is None and FORCEWATCHER_AVAILABLE:
        @bot.command(name="forcewatcher")
        @commands.has_permissions(administrator=True)
        async def cmd_force_watcher(ctx):
            """Force news watcher to check all subscriptions (Admin only)."""
            try:
                # Check permissions first
                if not ctx.author.guild_permissions.administrator:
                    await ctx.send("❌ **Permission denied:** This command requires administrator permissions.")
                    return
                
                logger.info(f"🔄 Force watcher initiated by {ctx.author.name} ({ctx.author.id})")
                await ctx.send("🔄 **Forcing news watcher iteration...**")
                
                # Get database instance
                db = get_news_watcher_db_instance(str(ctx.guild.id))
                global_db = get_global_news_db()
                
                logger.info(f"✅ Database instances ready for server {ctx.guild.id}")
                
                # Use our custom DiscordHTTP client for notifications
                from discord_bot.discord_http import DiscordHTTP
                from agent_engine import get_discord_token
                http = DiscordHTTP(get_discord_token())
                
                logger.info("✅ DiscordHTTP client created")
                
                # Force the watcher to process all subscriptions (channel + user)
                from roles.news_watcher.news_watcher import process_subscriptions
                await process_subscriptions(http, str(ctx.guild.id))
                
                logger.info("✅ All subscriptions processing completed")
                await ctx.send("✅ **News watcher iteration completed!**\n"
                              "📊 Checked all subscriptions (keywords, flat, AI, channel).\n"
                              "📰 Any new articles will be processed and notifications sent.")
                
            except commands.MissingPermissions:
                await ctx.send("❌ **Permission denied:** This command requires administrator permissions.")
            except Exception as e:
                logger.error(f"❌ Error in forcewatcher command: {e}")
                await ctx.send(f"❌ **Error running news watcher:** `{str(e)}`")
                import traceback
                traceback.print_exc()
        
        logger.info("📡 Force watcher command registered")
    elif not FORCEWATCHER_AVAILABLE:
        logger.warning("📡 Force watcher command not available - dependencies missing")
    else:
        logger.info("📡 Force watcher command already registered")
    
    # --- !testwatcher (for debugging without admin permissions) ---
    if bot.get_command("testwatcher") is None and FORCEWATCHER_AVAILABLE:
        @bot.command(name="testwatcher")
        async def cmd_test_watcher(ctx):
            """Test news watcher without admin permissions (for debugging)."""
            try:
                logger.info(f"🔄 Test watcher initiated by {ctx.author.name} ({ctx.author.id})")
                await ctx.send("🔄 **Testing news watcher iteration...**")
                
                # Get database instance
                db = get_news_watcher_db_instance(str(ctx.guild.id))
                global_db = get_global_news_db()
                
                logger.info(f"✅ Database instances ready for server {ctx.guild.id}")
                
                # Use our custom DiscordHTTP client for notifications
                from discord_bot.discord_http import DiscordHTTP
                from agent_engine import get_discord_token
                http = DiscordHTTP(get_discord_token())
                
                logger.info("✅ DiscordHTTP client created")
                
                # Force the watcher to process all subscriptions for this channel
                from roles.news_watcher.news_watcher import process_channel_all_subscriptions
                await process_channel_all_subscriptions(http, db, global_db, str(ctx.guild.id), str(ctx.channel.id))
                
                logger.info("✅ Channel subscriptions processing completed")
                await ctx.send("✅ **Test watcher iteration completed!**\n"
                              "📊 Checked all subscriptions (keywords, flat, AI) for this channel.\n"
                              "📰 Any new articles will be processed and notifications sent.")
                
            except Exception as e:
                logger.error(f"❌ Error in testwatcher command: {e}")
                await ctx.send(f"❌ **Error running test watcher:** `{str(e)}`")
                import traceback
                traceback.print_exc()
        
        logger.info("📡 Test watcher command registered")
    
    logger.info("📡 All News Watcher commands registered")


def _build_watcher_help_text():
    """Build News Watcher help text for users."""
    help_text = "📡 **News Watcher Help - Users** 📡\n\n"
    help_text += "🎨 **Use `!canvas` → News Watcher to manage all subscriptions.**\n\n"
    help_text += "📊 **Subscription Limits:**\n"
    help_text += "• **Users:** Maximum 3 subscriptions per person\n"
    help_text += "• **Channels:** Maximum 3 subscriptions per channel\n"
    help_text += "• **Server:** Maximum 15 total subscriptions\n\n"
    help_text += "🔧 **Available Methods:**\n"
    help_text += "• **Flat** - All news with AI opinions\n"
    help_text += "• **Keywords** - Filtered by your keywords\n"
    help_text += "• **General (AI)** - Critical news analysis\n\n"
    help_text += "📂 **Categories:** economy, international, technology, general, crypto\n\n"
    help_text += "� **For Admins:** Use `!canvas` → News Watcher → Administration for channel management"
    return help_text


def _build_watcher_help_text_method_specific(method_type: str):
    """Build method-specific News Watcher help text for users."""
    help_text = f"📡 **News Watcher Help - {method_type.title()} Method** 📡\n\n"
    help_text += "🎨 **Use `!canvas` → News Watcher to manage all subscriptions.**\n\n"
    
    if method_type == "flat":
        help_text += "📰 **Current Method: Flat (All News)**\n"
        help_text += "You receive ALL news from subscribed categories with AI-generated opinions.\n\n"
    elif method_type == "keyword":
        help_text += "🔍 **Current Method: Keywords (Filtered News)**\n"
        help_text += "You receive news that matches your configured keywords only.\n\n"
    elif method_type == "general":
        help_text += "🤖 **Current Method: AI (Critical News Analysis)**\n"
        help_text += "You receive only critical news analyzed by AI according to your premises.\n\n"
    
    help_text += "📢 **For Admins:** Use `!canvas` → News Watcher → Administration for channel management"
    return help_text


def _build_watcher_channel_help_text():
    """Build News Watcher help text for channels (admins)."""
    help_text = "📡 **NEWS WATCHER - CHANNEL MANAGEMENT** 📡\n\n"
    help_text += "🎨 **Use `!canvas` → News Watcher → Administration to manage channel subscriptions.**\n\n"
    help_text += "⏰ **Frequency:** Default 1 hour | Range: 1-24 hours\n"
    help_text += "• Affects all user and channel subscriptions\n\n"
    help_text += "⚠️ **IMPORTANT - Mutual Exclusion:**\n"
    help_text += "• A channel can have **ONLY ONE TYPE** of active subscription\n"
    help_text += "• When changing type, the previous one is automatically cancelled\n"
    help_text += "• **Types:** Flat (all), Keywords (filtered), AI (critical)\n"
    help_text += "• Only administrators can manage channel subscriptions"
    return help_text


def _build_watcher_channel_help_text_method_specific(method_type: str):
    """Build method-specific News Watcher help text for channels (admins)."""
    help_text = f"📡 **NEWS WATCHER - CHANNEL ({method_type.upper()} METHOD)** 📡\n\n"
    help_text += "🎨 **Use `!canvas` → News Watcher → Administration to manage channel subscriptions.**\n\n"
    
    if method_type == "flat":
        help_text += "📰 **Current Method: Flat (All News)**\n"
        help_text += "Channels receive ALL news from subscribed categories with AI-generated opinions.\n\n"
    elif method_type == "keyword":
        help_text += "🔍 **Current Method: Keywords (Filtered News)**\n"
        help_text += "Channels receive news that matches their configured keywords only.\n\n"
    elif method_type == "general":
        help_text += "🤖 **Current Method: AI (Critical News Analysis)**\n"
        help_text += "Channels receive only critical news analyzed by AI according to channel premises.\n\n"
    
    help_text += "⚠️ **IMPORTANT - Mutual Exclusion:**\n"
    help_text += "• A channel can have **ONLY ONE TYPE** of active subscription\n"
    help_text += "• When changing type, the previous one is automatically cancelled\n"
    help_text += "• Only administrators can manage channel subscriptions"
    
    return help_text
