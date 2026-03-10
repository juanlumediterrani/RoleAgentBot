"""
Discord commands for the Trickster role (English version).
Standardized command structure: !trickster <action> <target>
Registers: !trickster, !dice (legacy alias), !accuse (legacy alias)
"""

import asyncio
import discord
from datetime import datetime
from agent_logging import get_logger
from discord_bot.discord_utils import is_admin, send_dm_or_channel

logger = get_logger('trickster_discord')

# Forward declarations to avoid NameError
cmd_trickster = None

# Availability flags
try:
    from roles.trickster.subroles.beggar.db_beggar import get_beggar_db_instance
    BEGGAR_DB_AVAILABLE = True
except ImportError:
    BEGGAR_DB_AVAILABLE = False
    get_beggar_db_instance = None

try:
    from roles.trickster.subroles.dice_game.db_dice_game import get_dice_game_db_instance
    DICE_GAME_DB_AVAILABLE = True
except ImportError:
    DICE_GAME_DB_AVAILABLE = False
    get_dice_game_db_instance = None

try:
    from roles.trickster.subroles.dice_game.dice_game import procesar_jugada
    DICE_GAME_AVAILABLE = True
except ImportError:
    DICE_GAME_AVAILABLE = False
    procesar_jugada = None

try:
    from roles.banker.db_role_banker import get_banker_db_instance
    BANKER_DB_AVAILABLE = True
except ImportError:
    BANKER_DB_AVAILABLE = False
    get_banker_db_instance = None

try:
    from roles.trickster.subroles.ring.ring_discord import cmd_trickster_ring, cmd_accuse_ring
    RING_AVAILABLE = True
except ImportError:
    RING_AVAILABLE = False
    cmd_trickster_ring = None
    cmd_accuse_ring = None


def _get_beggar_db(guild):
    """Get beggar database instance for a server."""
    if not BEGGAR_DB_AVAILABLE or get_beggar_db_instance is None:
        return None
    from discord_utils import get_server_key
    return get_beggar_db_instance(get_server_key(guild))


def register_trickster_commands(bot, personality, agent_config):
    """Register trickster commands with beggar, dice game, and ring subroles (idempotent)."""

    # Define subcommand functions first to avoid NameError
    async def cmd_trickster_beggar(ctx, *args):
        """Manage the beggar subrole."""
        if not args:
            await ctx.send("❌ You must specify an action. Use `!trickster beggar enable/disable` or `!trickster beggar frequency <hours>`.")
            return

        action = args[0].lower()
        if action in ["enable", "disable", "on", "off"]:
            await _cmd_trickster_beggar_toggle(ctx, action)
        elif action == "frequency":
            await _cmd_trickster_beggar_frequency(ctx, args[1:])
        elif action == "status":
            await _cmd_trickster_beggar_status(ctx)
        elif action == "help":
            await _cmd_trickster_beggar_help(ctx)
        else:
            await ctx.send(f"❌ Action `{action}` not recognized. Use `enable`, `disable`, `frequency`, `status`, or `help`.")

    # Helper functions for beggar subrole
    async def _cmd_trickster_beggar_toggle(ctx, action):
        """Enable or disable the beggar subrole (administrators only)."""
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send("❌ Only administrators can enable/disable beggar on the server.")
            return

        db_beggar = _get_beggar_db(ctx.guild)
        if not db_beggar:
            await ctx.send("❌ Error accessing the trickster database.")
            return

        server_id = str(ctx.guild.id)
        server_name = ctx.guild.name
        server_user_id = f"server_{server_id}"

        enabled = action in ["enable", "on"]

        if enabled:
            if db_beggar.add_subscription(server_user_id, server_name, server_id):
                await ctx.send(f"🙏 **Beggar enabled for the server** - Now all members will receive periodic beggar requests.")
                logger.info(f"🎭 {ctx.author.name} enabled beggar for {server_name}")
            else:
                await ctx.send("❌ Error enabling beggar. Please try again.")
        else:
            if db_beggar.remove_subscription(server_user_id, server_id):
                await ctx.send(f"🚫 **Beggar disabled for the server** - No more beggar requests will be sent.")
                logger.info(f"🎭 {ctx.author.name} disabled beggar for {server_name}")
            else:
                await ctx.send("❌ Error disabling beggar. Please try again.")

    async def _cmd_trickster_beggar_frequency(ctx, args):
        """Adjust the frequency of beggar requests (administrators only)."""
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send("❌ Only administrators can adjust beggar frequency.")
            return
        if not args:
            await ctx.send("❌ You must specify a number of hours. Example: `!trickster beggar frequency 6`")
            return

        try:
            hours = int(args[0])
            if hours < 1 or hours > 168:
                await ctx.send("❌ Frequency must be between 1 and 168 hours (1 week).")
                return
            await ctx.send(f"⏰ **Frequency adjusted** - Beggar requests will be sent every {hours} hours.")
            logger.info(f"🎭 {ctx.author.name} adjusted beggar frequency to {hours} hours in {ctx.guild.name}")
        except ValueError:
            await ctx.send("❌ You must specify a valid number of hours.")

    async def _cmd_trickster_beggar_status(ctx):
        """Show current beggar status on the server."""
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return

        db_beggar = _get_beggar_db(ctx.guild)
        if not db_beggar:
            await ctx.send("❌ Error accessing the trickster database.")
            return

        server_id = str(ctx.guild.id)
        server_user_id = f"server_{server_id}"
        is_active = db_beggar.is_subscribed(server_user_id, server_id)

        try:
            count_dm = db_beggar.count_requests_type_last_day("BEGGAR_DM", server_id)
            count_public = db_beggar.count_requests_type_last_day("BEGGAR_PUBLIC", server_id)
        except Exception:
            count_dm = 0
            count_public = 0

        status_emoji = "✅" if is_active else "❌"
        status_text = "Enabled" if is_active else "Disabled"

        status_msg = f"📊 **Beggar Status in {ctx.guild.name}**\n\n"
        status_msg += f"{status_emoji} **Status:** {status_text}\n"
        status_msg += f"📈 **Requests today (last 24h):**\n"
        status_msg += f"  • Private: {count_dm}/2\n"
        status_msg += f"  • Public: {count_public}/4\n"
        status_msg += f"🆔 **Server ID:** {server_id}\n"

        if is_active:
            status_msg += f"\n🙏 Beggar is active and working on this server."
        else:
            status_msg += f"\n🚫 Beggar is disabled. Use `!trickster beggar enable` to activate it."

        await ctx.send(status_msg)

    async def _cmd_trickster_beggar_help(ctx):
        """Show specific help for the beggar subrole."""
        help_msg = "🙏 **BEGGAR SUBROLE - HELP** 🙏\n\n"
        help_msg += "**What is Beggar?**\n"
        help_msg += "It's a trickster subrole that sends donation requests and deceptions to server members.\n\n"
        help_msg += "📋 **COMMANDS:** (administrators only)\n"
        help_msg += "• `!trickster beggar enable` - Enable beggar for the entire server\n"
        help_msg += "• `!trickster beggar disable` - Disable beggar for the server\n"
        help_msg += "• `!trickster beggar frequency <hours>` - Adjust frequency (1-168h)\n"
        help_msg += "• `!trickster beggar status` - Show current status\n\n"
        
        help_msg += "💡 **EXAMPLES:**\n"
        help_msg += "• `!trickster beggar enable` → Enable for entire server\n"
        help_msg += "• `!trickster beggar frequency 6` → Every 6 hours\n"
        help_msg += "• `!trickster beggar status` → View status and statistics\n"
        help_msg += "• `!trickster beggar disable` → Disable from server\n\n"
        
        help_msg += "⚠️ **REQUIREMENTS:**\n"
        help_msg += "• Only administrators can use beggar commands\n"
        help_msg += "• Commands only work in server channels\n\n"
        
        help_msg += "⚠️ **LIMITS:**\n"
        help_msg += "• Maximum 2 private messages per server per day\n"
        help_msg += "• Maximum 4 public messages per server per day\n"
        help_msg += "• Don't harass the same user for 12 hours"

        await send_dm_or_channel(ctx, help_msg, "📩 Beggar help sent by private message.")

    # --- !trickster ---
    cmd_trickster = bot.get_command("trickster")
    if cmd_trickster is None:
        @bot.group(name="trickster")
        async def cmd_trickster(ctx):
            """Main trickster command - manages beggar, ring, and dice game subroles."""
            if not BEGGAR_DB_AVAILABLE and not RING_AVAILABLE:
                await ctx.send("❌ The trickster system is not available on this server.")
                return

            if ctx.invoked_subcommand is None:
                await ctx.send("❌ You must specify an action. Use `!trickster help` to see available commands.")
                return

        logger.info("🎭 Trickster command registered")
    else:
        logger.info("🎭 Trickster command already registered, adding subcommands")

    # Register subcommands on the group
    if cmd_trickster is not None and BEGGAR_DB_AVAILABLE:
        try:
            if cmd_trickster.get_command("beggar") is None:
                cmd_trickster.command(name="beggar")(cmd_trickster_beggar)
                logger.info("🎭 Trickster beggar subcommand registered")
        except Exception as e:
            logger.error(f"Error registering trickster beggar: {e}")

    if cmd_trickster is not None and RING_AVAILABLE:
        try:
            if cmd_trickster.get_command("ring") is None:
                cmd_trickster.command(name="ring")(cmd_trickster_ring)
                logger.info("🎭 Trickster ring subcommand registered")
        except Exception as e:
            logger.error(f"Error registering trickster ring: {e}")

    # Register help subcommand
    if cmd_trickster is not None:
        try:
            if cmd_trickster.get_command("help") is None:
                cmd_trickster.command(name="help")(cmd_trickster_help)
                logger.info("🎭 Trickster help subcommand registered")
        except Exception as e:
            logger.error(f"Error registering trickster help: {e}")

    # --- Import and register dice game commands ---
    try:
        from .subroles.dice_game.dice_game_discord import register_dice_commands
        register_dice_commands(
            bot, personality, send_dm_or_channel, is_admin,
            get_banker_db_instance, get_dice_game_db_instance,
            procesar_jugada, DICE_GAME_AVAILABLE, DICE_GAME_DB_AVAILABLE,
            BANKER_DB_AVAILABLE
        )
        logger.info("🎲 Dice game commands imported and registered")
    except ImportError as e:
        logger.error(f"Failed to import dice game commands: {e}")

    logger.info("🎭 Trickster commands registered successfully")

    # --- !accuse (legacy alias for ring accusations) ---
    if RING_AVAILABLE and bot.get_command("accuse") is None:
        @bot.command(name="accuse")
        async def cmd_accuse_wrapper(ctx, target: str = ""):
            """Accuse someone of having the unique ring."""
            await cmd_accuse_ring(ctx, target)

        logger.info("👁️ Accuse command registered")

    # --- MAIN TRICKSTER HELP ---

async def cmd_trickster_help(ctx):
    """Show trickster-specific help."""
    help_msg = "🎭 **TRICKSTER - HELP** 🎭\n\n"
    help_msg += "**Beggar Subrole** - Donation requests and deceptions\n\n"
    help_msg += "📋 **BEGGAR COMMANDS:** (administrators only)\n"
    help_msg += "• `!trickster beggar enable` - Enable beggar for entire server\n"
    help_msg += "• `!trickster beggar disable` - Disable beggar from server\n"
    help_msg += "• `!trickster beggar frequency <hours>` - Adjust frequency (1-168h)\n"
    help_msg += "• `!trickster beggar status` - Show current status\n\n"
    
    if RING_AVAILABLE:
        help_msg += "**Ring Subrole** - Ring accusations\n\n"
        help_msg += "📋 **RING COMMANDS:**\n"
        help_msg += "• `!trickster ring enable` - Enable ring for entire server (admins only)\n"
        help_msg += "• `!trickster ring disable` - Disable ring from server (admins only)\n"
        help_msg += "• `!trickster ring frequency <hours>` - Adjust frequency (1-168h) (admins only)\n"
        help_msg += "• `!trickster ring help` - Show ring subrole help\n"
        help_msg += "• `!accuse @user` - Accuse a user of having the ring\n\n"
    
    help_msg += "**Dice Game Subrole** - Dice game against the bank\n\n"
    help_msg += "📋 **DICE GAME COMMANDS:**\n"
    help_msg += "• `!dice play` - Roll the dice (server channels only)\n"
    help_msg += "• `!dice help` - Show complete dice game help\n"
    help_msg += "• `!dice balance` - Show current pot balance (responds by DM)\n"
    help_msg += "• `!dice stats` - Show your personal statistics (responds by DM)\n"
    help_msg += "• `!dice ranking` - Show server player ranking\n"
    help_msg += "• `!dice history` - Show last games played\n"
    help_msg += "• `!dice config bet <amount>` - Configure fixed bet (admins only)\n"
    help_msg += "• `!dice config announcements on/off` - Enable/disable announcements (admins only)\n\n"
    
    help_msg += "💡 **EXAMPLES:**\n"
    help_msg += "• `!trickster beggar enable` → Enable for entire server\n"
    help_msg += "• `!trickster beggar frequency 6` → Every 6 hours\n"
    help_msg += "• `!trickster beggar status` → View status and statistics\n"
    help_msg += "• `!trickster beggar disable` → Disable from server\n"
    
    if RING_AVAILABLE:
        help_msg += "• `!trickster ring enable` → Enable ring for entire server\n"
        help_msg += "• `!accuse @user` → Accuse someone\n"
    
    help_msg += "• `!dice play` → Play the dice game\n"
    help_msg += "• `!dice config bet 15` → Configure bet to 15 coins\n\n"
    
    help_msg += "⚠️ **REQUIREMENTS:**\n"
    help_msg += "• Only administrators can use beggar and dice game configuration commands"
    if RING_AVAILABLE:
        help_msg += " and ring"
    help_msg += "\n"
    help_msg += "• Beggar and dice game commands only work in server channels\n"
    help_msg += "• Dice game requires Banker role to be active\n\n"
    
    help_msg += "⚠️ **LIMITS:**\n"
    help_msg += "• Maximum 2 private messages per server per day (beggar)\n"
    help_msg += "• Maximum 4 public messages per server per day (beggar)\n"
    help_msg += "• Don't harass the same user for 12 hours (beggar)\n"
    help_msg += "• Fixed single bet for all players (dice game)"

    await send_dm_or_channel(ctx, help_msg, "📩 Trickster help sent by private message.")
