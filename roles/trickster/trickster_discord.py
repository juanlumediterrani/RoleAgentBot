"""
Discord commands for the Trickster role (English version).
Standardized command structure: !trickster <action> <target>
Registers: !trickster, !dice
"""

import asyncio
import json
import os
import discord
from datetime import datetime
from agent_logging import get_logger
from agent_engine import PERSONALITY
from discord_bot.discord_utils import is_admin, send_dm_or_channel, get_server_key

logger = get_logger('trickster_discord')


def _load_subrole_messages() -> dict:
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        config_path = os.path.join(project_root, "agent_config.json")
        with open(config_path, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        personality_rel = agent_cfg.get("personality", "")
        answers_path = os.path.join(project_root, os.path.dirname(personality_rel), "answers.json")
        with open(answers_path, encoding="utf-8") as f:
            return json.load(f).get("discord", {}).get("subrole_messages", {})
    except Exception:
        return {}


_subrole_messages = _load_subrole_messages()

# Forward declarations to avoid NameError
cmd_trickster = None

# Availability flags
BEGGAR_DB_AVAILABLE = True

try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None

try:
    from roles.trickster.subroles.dice_game.dice_game_db import get_dice_game_roles_db_instance as get_dice_game_db_instance
    DICE_GAME_DB_AVAILABLE = True
except ImportError:
    get_dice_game_db_instance = None
    DICE_GAME_DB_AVAILABLE = False

try:
    from roles.trickster.subroles.dice_game.dice_game import process_play
    DICE_GAME_AVAILABLE = True
except ImportError:
    process_play = None
    DICE_GAME_AVAILABLE = False

try:
    from roles.banker.banker_db import get_banker_roles_db_instance as get_banker_db_instance
except ImportError:
    get_banker_db_instance = None

try:
    from roles.trickster.subroles.ring.ring_discord import cmd_trickster_ring, cmd_accuse_ring
    RING_AVAILABLE = True
except ImportError:
    RING_AVAILABLE = False
    cmd_trickster_ring = None
    cmd_accuse_ring = None

try:
    from roles.trickster.subroles.nordic_runes.nordic_runes_discord import cmd_runes, cmd_runes_cast, cmd_runes_history, cmd_runes_types
    NORDIC_RUNES_AVAILABLE = True
except ImportError:
    NORDIC_RUNES_AVAILABLE = False
    cmd_runes = None
    cmd_runes_cast = None
    cmd_runes_history = None
    cmd_runes_types = None


def _get_banker_db(guild):
    """Get banker database instance for a server."""
    if get_banker_db_instance is None:
        return None
    try:
        return get_banker_db_instance(str(guild.id))
    except Exception:
        return None


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
        elif action == "donate":
            await _cmd_trickster_beggar_donate(ctx, args[1:])
        elif action == "admin":
            await _cmd_trickster_beggar_admin(ctx, args[1:])
        elif action == "help":
            await _cmd_trickster_beggar_help(ctx)
        else:
            await ctx.send(f"❌ Action `{action}` not recognized. Use `enable`, `disable`, `frequency`, `status`, `donate`, `admin`, or `help`.")

    # Helper functions for beggar subrole
    async def _cmd_trickster_beggar_toggle(ctx, action):
        """Enable or disable the beggar subrole (administrators only)."""
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send("❌ Only administrators can enable or disable beggar on this server.")
            return

        from .subroles.beggar.beggar_config import get_beggar_config
        
        server_id = str(ctx.guild.id)
        beggar_config = get_beggar_config(server_id)
        
        enabled = action in ["enable", "on"]
        
        if beggar_config.set_enabled(enabled):
            if enabled:
                # Select a random reason automatically
                selected_reason = beggar_config.select_new_reason()
                
                # Send first message immediately
                try:
                    from .subroles.beggar.beggar_task import execute_beggar_task
                    success = await execute_beggar_task(server_id=server_id, bot_instance=ctx.bot)
                    if success:
                        await ctx.send(f"🙏 **Beggar enabled for the server** - First message sent with reason: '{selected_reason}'")
                        logger.info(f"🎭 {ctx.author.name} enabled beggar for {ctx.guild.name} - Reason: {selected_reason} - First message sent")
                    else:
                        await ctx.send(f"🙏 **Beggar enabled for the server** - Reason selected: '{selected_reason}' (First message will be sent on next cycle)")
                        logger.info(f"🎭 {ctx.author.name} enabled beggar for {ctx.guild.name} - Reason: {selected_reason} - First message failed")
                except Exception as e:
                    await ctx.send(f"🙏 **Beggar enabled for the server** - Reason selected: '{selected_reason}' (First message failed: {str(e)})")
                    logger.error(f"🎭 Error sending first beggar message: {e}")
            else:
                await ctx.send(f"🚫 **Beggar disabled for the server** - No more periodic beggar requests.")
                logger.info(f"🎭 {ctx.author.name} disabled beggar for {ctx.guild.name}")
        else:
            await ctx.send("❌ Error updating beggar configuration.") 

    async def _cmd_trickster_beggar_frequency(ctx, args):
        """Adjust the frequency of beggar requests (administrators only)."""
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send("❌ Only administrators can adjust beggar frequency.")
            return
        if not args:
            await ctx.send("❌ You must specify a number of hours. Example: `!trickster beggar frequency 6`.")
            return

        try:
            hours = int(args[0])
            if hours < 1 or hours > 168:
                await ctx.send("❌ Frequency must be between 1 and 168 hours (1 week).")
                return
            
            from .subroles.beggar.beggar_config import get_beggar_config
            
            server_id = str(ctx.guild.id)
            beggar_config = get_beggar_config(server_id)
            
            if beggar_config.set_frequency_hours(hours):
                await ctx.send(f"⏰ **Frequency adjusted** - Beggar requests will be sent every {hours} hours.")
                logger.info(f"🎭 {ctx.author.name} adjusted beggar frequency to {hours} hours in {ctx.guild.name}")
            else:
                await ctx.send("❌ Could not update beggar frequency.")
                
        except ValueError:
            await ctx.send("❌ You must specify a valid number of hours.")

    async def _cmd_trickster_beggar_status(ctx):
        """Show current beggar status on the server."""
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return

        from .subroles.beggar.beggar_config import get_beggar_config
        from agent_roles_db import get_roles_db_instance
        
        server_id = str(ctx.guild.id)
        beggar_config = get_beggar_config(server_id)
        roles_db = get_roles_db_instance(server_id)

        is_active = beggar_config.is_enabled()
        config = beggar_config.get_config()
        reason_status = beggar_config.get_reason_status()

        try:
            # Get stats from roles database
            server_stats = roles_db.get_beggar_server_stats(server_id)
            leaderboard = roles_db.get_beggar_leaderboard(server_id, limit=5)
            
            # Get fund balance from banker
            from roles.banker.banker_db import get_banker_db_instance
            banker_db = get_banker_db_instance(server_id)
            fund_balance = banker_db.get_balance("beggar_fund") if banker_db else 0

            status_msg = f"📊 **Beggar Status in {ctx.guild.name}**\n\n"
            status_msg += f"🔧 **Status:** {'✅ Enabled' if is_active else '❌ Disabled'}\n"
            status_msg += f"⏰ **Frequency:** Every {config.get('frequency_hours', 24)} hours\n"
            status_msg += f"🎯 **Current reason:** {reason_status['current_reason'] or 'No reason set'}\n"
            status_msg += f"📅 **Reason active for:** {reason_status['days_active']} days\n"
            status_msg += f"� **Current fund:** {fund_balance:,} gold\n"
            status_msg += f"👥 **Total donors:** {server_stats.get('total_donors', 0)}\n"
            status_msg += f"💵 **Total donated:** {server_stats.get('total_gold', 0):,} gold\n"

            if leaderboard:
                status_msg += f"\n� **Top Donors (Last 5):**\n"
                for i, donor in enumerate(leaderboard[:3], 1):
                    medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                    status_msg += f"  {medal} {donor['user_name']}: {donor['total_donated']:,} gold ({donor['donation_count']} donations)\n"
            
            await ctx.send(status_msg)
            
        except Exception as e:
            logger.error(f"Error showing beggar status: {e}")
            await ctx.send("❌ Error retrieving beggar status.")

    async def _cmd_trickster_beggar_donate(ctx, args):
        """Donate gold to beggar from a user wallet."""
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not args:
            await ctx.send("❌ You must specify an amount. Example: `!trickster beggar donate 25`")
            return
        try:
            amount = int(str(args[0]).strip())
        except ValueError:
            await ctx.send("❌ You must specify a valid number of gold coins.")
            return
        if amount <= 0:
            await ctx.send("❌ Donation amount must be positive.")
            return

        from .subroles.beggar.beggar_config import get_beggar_config
        from agent_roles_db import get_roles_db_instance
        
        db_banker = _get_banker_db(ctx.guild)
        if not db_banker:
            await ctx.send("❌ Beggar donation systems are not available.")
            return

        server_id = str(ctx.guild.id)
        server_id = ctx.guild.name
        donor_id = str(ctx.author.id)
        donor_name = ctx.author.display_name
        
        # Get beggar config for current reason
        beggar_config = get_beggar_config(server_id)
        roles_db = get_roles_db_instance(server_id)

        db_banker.create_wallet(donor_id, donor_name)
        db_banker.create_wallet("beggar_fund", "Beggar Fund", wallet_type='system')

        current_balance = db_banker.get_balance(donor_id)
        if current_balance < amount:
            await ctx.send(f"❌ You only have {current_balance:,} gold available.")
            return

        reason = beggar_config.get_current_reason() or "the current group project"
        
        # Process donation
        db_banker.update_balance(donor_id, donor_name, -amount, "BEGGAR_DONATION_OUT", "Donation sent to beggar")
        db_banker.update_balance("beggar_fund", "Beggar Fund", amount, "BEGGAR_DONATION_IN", f"Donation received from {donor_name}")
        
        # Update user donation record in roles database
        roles_db.update_beggar_donation(donor_id, donor_name, amount, reason)
        
        roles_db.save_beggar_request(
            user_id=donor_id,
            user_name=donor_name,
            request_type="BEGGAR_DONATION",
            message=f"Donated {amount} gold",
            channel_id=str(ctx.channel.id),
            metadata=json.dumps({"amount": amount, "reason": reason}),
        )
        
        fund_balance = db_banker.get_balance("beggar_fund")
        await ctx.send(
            f"🙏 **Donation accepted** - {amount:,} gold sent to beggar.\n"
            f"🪙 Current fund: {fund_balance:,} gold\n"
            f"📣 Current reason: {reason}"
        )

    async def _cmd_trickster_beggar_help(ctx):
        """Show specific help for the beggar subrole."""
        help_msg = "🙏 **BEGGAR SUBROLE - HELP** 🙏\n\n"
        help_msg += "**What is Beggar?**\n"
        help_msg += "It's a trickster subrole that sends donation requests and trickery to server members.\n\n"
        help_msg += "📋 **BEGGAR COMMANDS:** (administrators only)\n"
        help_msg += "• `!trickster beggar enable` - Enable beggar on this server\n"
        help_msg += "• `!trickster beggar disable` - Disable beggar on this server\n"
        help_msg += "• `!trickster beggar frequency <hours>` - Adjust frequency (1-168 hours)\n"
        help_msg += "• `!trickster beggar status` - Show current status\n"
        help_msg += "• `!trickster beggar admin forceminigame` - Force weekly minigame\n\n"
        help_msg += "📋 **USER COMMANDS:**\n"
        help_msg += "• `!trickster beggar donate <gold>` - Donate gold to the current beggar fund\n\n"
        
        help_msg += "💡 **EXAMPLES:**\n"
        help_msg += "• `!trickster beggar enable` → Enable on this server\n"
        help_msg += "• `!trickster beggar frequency 6` → Every 6 hours\n"
        help_msg += "• `!trickster beggar status` → View status and statistics\n"
        help_msg += "• `!trickster beggar disable` → Disable on this server\n\n"
        
        help_msg += "⚠️ **REQUIREMENTS:**\n"
        help_msg += "• Only administrators can use beggar commands\n"
        help_msg += "• Commands only work in server channels\n\n"
        
        help_msg += "⚠️ **LIMITS:**\n"
        help_msg += "• Maximum 2 private messages per server per day\n"
        help_msg += "• Maximum 4 public messages per server per day\n"
        help_msg += "• Avoid targeting the same user for 12 hours"

        await send_dm_or_channel(ctx, help_msg, "📩 Beggar help sent by private message.")

    async def _cmd_trickster_beggar_admin(ctx, args):
        """Admin commands for beggar subrole (administrators only)."""
        if not ctx.guild:
            await ctx.send("❌ This command only works on servers, not in private messages.")
            return
        if not is_admin(ctx):
            await ctx.send("❌ Only administrators can use beggar admin commands.")
            return
        
        if not args:
            await ctx.send("❌ You must specify an admin action. Use `!trickster beggar admin forceminigame` or `!trickster beggar admin help`.")
            return
        
        action = args[0].lower()
        
        if action == "forceminigame" or action == "force":
            await _cmd_trickster_beggar_force_minigame(ctx)
        elif action == "help":
            await _cmd_trickster_beggar_admin_help(ctx)
        else:
            await ctx.send(f"❌ Admin action `{action}` not recognized. Use `forceminigame` or `help`.")
    
    async def _cmd_trickster_beggar_force_minigame(ctx):
        """Force trigger the weekly beggar minigame (administrators only)."""
        try:
            from .subroles.beggar.beggar_minigame import BeggarMinigame
            
            server_id = str(ctx.guild.id)
            minigame = BeggarMinigame(server_id)
            
            # Send initial message
            await ctx.send("🎲 **Forcing Weekly Beggar Minigame...**\n⏳ Checking system requirements...")
            
            # Force the minigame
            result = await minigame.force_weekly_minigame()
            
            if result['success']:
                await ctx.send(result['message'])
                logger.info(f"🎭 {ctx.author.name} forced weekly beggar minigame in {ctx.guild.name}")
            else:
                await ctx.send(result['message'])
                logger.warning(f"🎭 {ctx.author.name} failed to force weekly beggar minigame in {ctx.guild.name}: {result['reason']}")
                
        except Exception as e:
            logger.error(f"Error in force minigame command: {e}")
            await ctx.send(f"❌ Error forcing minigame: {str(e)}")
    
    async def _cmd_trickster_beggar_admin_help(ctx):
        """Show admin-specific help for beggar subrole."""
        help_msg = "🔧 **BEGGAR ADMIN - HELP** 🔧\n\n"
        help_msg += "**Admin Commands for Beggar Management:**\n\n"
        help_msg += "📋 **ADMIN COMMANDS:**\n"
        help_msg += "• `!trickster beggar admin forceminigame` - Force trigger weekly minigame\n"
        help_msg += "• `!trickster beggar admin help` - Show this admin help\n\n"
        
        help_msg += "🎲 **FORCED MINIGAME:**\n"
        help_msg += "• Triggers the weekly minigame immediately\n"
        help_msg += "• Uses current reason for the minigame\n"
        help_msg += "• Requires: Enabled minigame, fund balance > 0, participants\n"
        help_msg += "• Distributes gold to donors and updates relationships\n\n"
        
        help_msg += "⚠️ **REQUIREMENTS:**\n"
        help_msg += "• Administrator permissions required\n"
        help_msg += "• Minigame must be enabled in config\n"
        help_msg += "• Gold must be available in beggar fund\n"
        help_msg += "• At least one donor must exist\n\n"
        
        help_msg += "💡 **EXAMPLES:**\n"
        help_msg += "• `!trickster beggar admin forceminigame` → Force minigame now\n"
        
        await send_dm_or_channel(ctx, help_msg, "📩 Beggar admin help sent by private message.")

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
            get_banker_db_instance,
            process_play, DICE_GAME_AVAILABLE
        )
        logger.info("🎲 Dice game commands imported and registered")
    except ImportError as e:
        logger.error(f"Failed to import dice game commands: {e}")

    # --- Register Nordic Runes commands ---
    if NORDIC_RUNES_AVAILABLE:
        try:
            # Register main runes command
            if bot.get_command("runes") is None:
                bot.command(name="runes")(cmd_runes)
                logger.info("🔮 Runes command registered")
            else:
                logger.info("🔮 Runes command already registered")
        except Exception as e:
            logger.error(f"Error registering runes command: {e}")

    logger.info("🎭 Trickster commands registered successfully")

    # --- MAIN TRICKSTER HELP ---

async def cmd_trickster_help(ctx):
    """Show trickster-specific help."""
    help_msg = "🎭 **TRICKSTER - HELP** 🎭\n\n"
    help_msg += "**Beggar Subrole** - Donation requests and trickery\n\n"
    help_msg += "📋 **BEGGAR COMMANDS:** (administrators only)\n"
    help_msg += "• `!trickster beggar enable` - Enable beggar on this server\n"
    help_msg += "• `!trickster beggar disable` - Disable beggar on this server\n"
    help_msg += "• `!trickster beggar frequency <hours>` - Adjust frequency (1-168 hours)\n"
    help_msg += "• `!trickster beggar status` - Show current status\n"
    help_msg += "• `!trickster beggar admin forceminigame` - Force weekly minigame\n\n"
    
    if RING_AVAILABLE:
        help_msg += "**Ring Subrole** - Ring accusations\n\n"
        help_msg += "📋 **RING COMMANDS:**\n"
        help_msg += "• `!trickster ring enable` - Enable ring on this server (admins only)\n"
        help_msg += "• `!trickster ring disable` - Disable ring on this server (admins only)\n"
        help_msg += "• `!trickster ring frequency <hours>` - Adjust frequency (1-168 hours) (admins only)\n"
        help_msg += "• `!trickster ring target @user` - Set the current ring investigation target (admins only)\n"
        help_msg += "• `!trickster ring help` - Show ring subrole help\n"
        help_msg += "• Ring investigations act on the current configured target\n\n"
    
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
    
    if NORDIC_RUNES_AVAILABLE:
        help_msg += "**Nordic Runes Subrole** - Elder Futhark rune casting\n\n"
        help_msg += "📋 **RUNES COMMANDS:**\n"
        help_msg += "• `!runes cast [type] <question>` - Cast runes for guidance\n"
        help_msg += "• `!runes history [limit]` - View your reading history\n"
        help_msg += "• `!runes types` - Show available reading types\n"
        help_msg += "• `!runes help` - Show runes help\n\n"
    
    help_msg += "💡 **EXAMPLES:**\n"
    help_msg += "• `!trickster beggar enable` → Enable on this server\n"
    help_msg += "• `!trickster beggar frequency 6` → Every 6 hours\n"
    help_msg += "• `!trickster beggar status` → View status and statistics\n"
    help_msg += "• `!trickster beggar disable` → Disable on this server\n"
    help_msg += "• `!trickster beggar donate 25` → Donate gold to the beggar fund\n"
    
    if RING_AVAILABLE:
        help_msg += "• `!trickster ring enable` → Enable ring on this server\n"
        help_msg += "• `!trickster ring target @user` → Change the current investigation target\n"
    
    help_msg += "• `!dice play` → Play the dice game\n"
    help_msg += "• `!dice config bet 15` → Configure bet to 15 coins\n"
    
    if NORDIC_RUNES_AVAILABLE:
        help_msg += "• `!runes cast single What should I focus on today?` → Single rune reading\n"
        help_msg += "• `!runes cast three What does my future hold?` → Three rune spread\n\n"
    
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
    help_msg += "• Avoid targeting the same user for 12 hours (beggar)\n"
    help_msg += "• Fixed single bet for all players (dice game)"

    await send_dm_or_channel(ctx, help_msg, "📩 Trickster help sent by private message.")
