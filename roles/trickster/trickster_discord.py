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
    from roles.trickster.subroles.dice_game.bote.db_bote import get_bote_db_instance
    DICE_GAME_DB_AVAILABLE = True
except ImportError:
    DICE_GAME_DB_AVAILABLE = False
    get_bote_db_instance = None

try:
    from roles.trickster.subroles.dice_game.bote.bote import procesar_jugada
    DICE_GAME_AVAILABLE = True
except ImportError:
    DICE_GAME_AVAILABLE = False
    procesar_jugada = None

try:
    from roles.banker.db_role_banker import get_banquero_db_instance
    BANKER_DB_AVAILABLE = True
except ImportError:
    BANKER_DB_AVAILABLE = False
    get_banquero_db_instance = None

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
    from discord_utils import get_server_name
    return get_beggar_db_instance(get_server_name(guild))


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

    # --- !dice (main dice game command) ---
    if DICE_GAME_AVAILABLE and DICE_GAME_DB_AVAILABLE and BANKER_DB_AVAILABLE:
        if bot.get_command("dice") is None:
            @bot.group(name="dice")
            async def cmd_dice(ctx):
                """Main dice game command."""
                if not ctx.guild:
                    await ctx.send("❌ This command only works on servers, not in private messages.")
                    return

                if not DICE_GAME_AVAILABLE or not DICE_GAME_DB_AVAILABLE or not BANKER_DB_AVAILABLE:
                    await ctx.send("❌ The dice game is not available on this server.")
                    return

                if ctx.invoked_subcommand is None:
                    await _cmd_dice_help(ctx, personality)
                    return

            # Register dice subcommands
            @cmd_dice.command(name="play")
            async def cmd_dice_play_wrapper(ctx):
                await cmd_dice_play(ctx)
            
            @cmd_dice.command(name="help")
            async def cmd_dice_help_wrapper(ctx):
                await cmd_dice_help(ctx, personality)
            
            @cmd_dice.command(name="balance")
            async def cmd_dice_balance_wrapper(ctx):
                await cmd_dice_balance(ctx, personality)
            
            @cmd_dice.command(name="stats")
            async def cmd_dice_stats_wrapper(ctx):
                await cmd_dice_stats(ctx, personality)
            
            @cmd_dice.command(name="ranking")
            async def cmd_dice_ranking_wrapper(ctx):
                await cmd_dice_ranking(ctx, personality)
            
            @cmd_dice.command(name="history")
            async def cmd_dice_history_wrapper(ctx):
                await cmd_dice_history(ctx, personality)
            
            @cmd_dice.command(name="config")
            async def cmd_dice_config_wrapper(ctx):
                await cmd_dice_config(ctx, personality)

            logger.info("🎲 Dice command registered")

    # Convenience alias: !dicehelp -> !dice help
    if bot.get_command("dicehelp") is None and bot.get_command("dice") is not None:
        @bot.command(name="dicehelp")
        async def cmd_dicehelp_alias(ctx):
            dice_cmd = bot.get_command("dice")
            if dice_cmd is None:
                await ctx.send("❌ `!dice` is not available on this server.")
                return
            await dice_cmd(ctx, "help")
    else:
        logger.warning("🎲 Dice game system not fully available - skipping registration")

    logger.info("🎭 Trickster commands registered successfully")

    # --- !accuse (legacy alias for ring accusations) ---
    if RING_AVAILABLE and bot.get_command("accuse") is None:
        @bot.command(name="accuse")
        async def cmd_accuse_wrapper(ctx, target: str = ""):
            """Accuse someone of having the unique ring."""
            await cmd_accuse_ring(ctx, target)

        logger.info("👁️ Accuse command registered")

    # --- Legacy Spanish aliases with deprecation warnings ---
    if bot.get_command("trilero") is None:
        @bot.command(name="trilero")
        async def cmd_trilero_legacy(ctx, *args):
            """Legacy command - use !trickster instead."""
            await ctx.send("⚠️ `!trilero` is deprecated. Use `!trickster` instead.")
            # Redirect to new command
            if args:
                await cmd_trickster.invoke(ctx, args)
            else:
                await ctx.send("Use `!trickster help` to see available commands.")

    if bot.get_command("bote") is None and DICE_GAME_AVAILABLE:
        @bot.command(name="bote")
        async def cmd_bote_legacy(ctx, *args):
            """Legacy command - use !dice instead."""
            await ctx.send("⚠️ `!bote` is deprecated. Use `!dice` instead.")
            # Redirect to new command
            if args:
                await cmd_dice.invoke(ctx, args)
            else:
                await ctx.send("Use `!dice help` to see available commands.")

    if bot.get_command("acusaranillo") is None and RING_AVAILABLE:
        @bot.command(name="acusaranillo")
        async def cmd_acusar_anillo_legacy(ctx, target: str = ""):
            """Legacy command - use !accuse instead."""
            await ctx.send("⚠️ `!acusaranillo` is deprecated. Use `!accuse` instead.")
            await cmd_accuse_ring(ctx, target)


# --- DICE GAME SUBCOMMANDS ---

async def cmd_dice_play(ctx):
    """Roll the dice in the dice game."""
    if not ctx.guild:
        await ctx.send("❌ This command only works on servers.")
        return
    try:
        from discord_utils import get_server_name
        server_name = get_server_name(ctx.guild)
        db_banker = get_banquero_db_instance(server_name)
        db_dice_game = get_bote_db_instance(server_name)
        if not db_banker or not db_dice_game:
            await ctx.send("❌ Error accessing game databases.")
            return

        result = await asyncio.to_thread(
            procesar_jugada,
            str(ctx.author.id),
            ctx.author.display_name,
            str(ctx.guild.id),
            ctx.guild.name,
            None,
        )

        if result.get("success"):
            await ctx.send(result.get("mensaje") or "✅ Played.")
            logger.info(f"🎲 {ctx.author.name} played in {ctx.guild.name} - Prize: {result.get('premio', 0)}")
            return

        await ctx.send(f"❌ {result.get('message', 'Error playing dice game')}")
    except Exception as e:
        logger.exception(f"Error in cmd_dice_play: {e}")
        await ctx.send("❌ Error processing the roll. Please try again.")


async def cmd_dice_help(ctx, personality):
    """Show complete dice game help."""
    help_msg = "🎲 **DICE GAME - HELP** 🎲\n\n"
    help_msg += "**What is Dice Game?**\n"
    help_msg += "It's a dice game where you bet a fixed amount against the bank. "
    help_msg += "Roll 1-1-1 and take the entire accumulated pot.\n\n"
    help_msg += "**🎲 PRIZE TABLE:**\n"
    help_msg += "• **1-1-1** (0.46%) → 🎉 **ENTIRE POT** 🎉\n"
    help_msg += "• **Any triple** (2.78%) → x3 your bet\n"
    help_msg += "• **Straight 4-5-6** (2.78%) → x5 your bet\n"
    help_msg += "• **Pair** (41.67%) → Get your bet back\n"
    help_msg += "• **Any other** (52.31%) → No prize\n\n"
    help_msg += "**📋 COMMANDS:**\n"
    help_msg += "• `!dice play` - Roll the dice\n"
    help_msg += "• `!dice balance` - Show current pot balance (DM)\n"
    help_msg += "• `!dice stats` - Your personal statistics (DM)\n"
    help_msg += "• `!dice ranking` - Server player ranking\n"
    help_msg += "• `!dice history` - Last games played\n"
    help_msg += "• `!dice config bet <amount>` - Configure bet (admins)\n"
    help_msg += "• `!dice config announcements on/off` - Auto announcements (admins)\n\n"
    help_msg += "**💡 EXAMPLES:**\n"
    help_msg += "• `!dice play` → Roll the dice\n"
    help_msg += "• `!dice config bet 15` → Fixed bet of 15 coins\n\n"
    help_msg += "**⚠️ REQUIREMENTS:**\n"
    help_msg += "• Only works in server channels\n"
    help_msg += "• Requires Banker role to be active\n"
    help_msg += "• Fixed single bet for all players\n\n"
    help_msg += "**🏦 ECONOMY:**\n"
    help_msg += "• The pot grows with each non-winning roll\n"
    help_msg += "• Partial prizes are paid by the bank\n"
    help_msg += "• 1-1-1 empties the entire accumulated pot!"

    await send_dm_or_channel(ctx, help_msg, "📩 Dice Game help sent by private message.")


async def cmd_dice_balance(ctx, personality):
    """Show current pot balance."""
    if not BANKER_DB_AVAILABLE or not DICE_GAME_DB_AVAILABLE:
        await ctx.send("❌ The dice game system is not available on this server.")
        return

    try:
        balance_messages = personality.get("discord", {}).get("dice_balance_messages", {})
        if not balance_messages:
            balance_messages = {
                "title": "💰 **DICE GAME STATUS - {server}** 💰\n\n",
                "current_balance": "🎲 **Current pot balance:** {balance:,} coins\n",
                "fixed_bet": "💎 **Fixed bet:** {bet:,} coins\n",
                "possible_plays": "🎯 **Possible plays:** {plays}\n\n",
                "pot_big": "🔥 **THE POT IS BIG!** 🔥\nGreat time to try winning {balance:,} coins!\n",
                "pot_medium": "📈 **Medium pot** - Good to play\n",
                "pot_small": "📉 **Small pot** - Keep growing\n",
                "use_command": "\n💡 Use `!dice play` to try your luck!",
                "sent_private": "📩 Pot balance sent by private message.",
                "error_balance": "❌ Error getting pot balance."
            }

        from discord_utils import get_server_name
        server_name = get_server_name(ctx.guild)
        db_banker = get_banquero_db_instance(server_name)
        db_dice_game = get_bote_db_instance(server_name)

        # In bote implementation, the pot is a special banker wallet
        pot_balance = db_banker.obtener_saldo("bote_banca", str(ctx.guild.id))
        config = db_dice_game.obtener_configuracion_servidor(str(ctx.guild.id))
        fixed_bet = config.get("apuesta_fija", 10)

        balance_msg = balance_messages.get("title", "💰 **DICE GAME STATUS - {server}** 💰\n\n").format(server=ctx.guild.name.upper())
        balance_msg += balance_messages.get("current_balance", "🎲 **Current pot balance:** {balance:,} coins\n").format(balance=pot_balance)
        balance_msg += balance_messages.get("fixed_bet", "💎 **Fixed bet:** {bet:,} coins\n").format(bet=fixed_bet)
        balance_msg += balance_messages.get("possible_plays", "🎯 **Possible plays:** {plays}\n\n").format(plays=pot_balance // fixed_bet if fixed_bet > 0 else 0)

        if pot_balance >= 100:
            balance_msg += balance_messages.get("pot_big", "🔥 **THE POT IS BIG!** 🔥\n").format(balance=pot_balance)
        elif pot_balance >= 50:
            balance_msg += balance_messages.get("pot_medium", "📈 **Medium pot** - Good to play\n")
        else:
            balance_msg += balance_messages.get("pot_small", "📉 **Small pot** - Keep growing\n")

        balance_msg += balance_messages.get("use_command", "\n💡 Use `!dice play` to try your luck!")
        await ctx.author.send(balance_msg)
        await ctx.send(balance_messages.get("sent_private", "📩 Pot balance sent by private message."))
    except Exception as e:
        logger.exception(f"Error in cmd_dice_balance: {e}")
        await ctx.send("❌ Error getting pot balance.")


async def cmd_dice_stats(ctx):
    """Show player's personal statistics."""
    if not ctx.guild:
        await ctx.send("❌ This command only works on servers.")
        return
    try:
        from discord_utils import get_server_name
        server_name = get_server_name(ctx.guild)
        db_dice_game = get_bote_db_instance(server_name)
        if not db_dice_game:
            await ctx.send("❌ Error accessing dice game database.")
            return

        stats = db_dice_game.obtener_estadisticas_jugador(str(ctx.author.id), str(ctx.guild.id))
        stats_msg = f"📊 **YOUR DICE GAME STATS** 📊\n\n"
        stats_msg += f"👤 **Player:** {ctx.author.display_name}\n"
        stats_msg += f"🎲 **Games played:** {stats.get('total_jugadas', 0)}\n"
        stats_msg += f"💰 **Total bet:** {stats.get('total_apostado', 0):,} coins\n"
        stats_msg += f"🏆 **Total won:** {stats.get('total_ganado', 0):,} coins\n"
        stats_msg += f"💎 **Pots won:** {stats.get('botes_ganados', 0)}\n"
        stats_msg += f"🎯 **Biggest prize:** {stats.get('mayor_premio', 0):,} coins\n"
        stats_msg += f"📈 **Net balance:** {(stats.get('total_ganado', 0) - stats.get('total_apostado', 0)):,} coins\n\n"

        if stats.get('total_jugadas', 0) > 0:
            profitability = (stats.get('total_ganado', 0) / max(stats.get('total_apostado', 1), 1)) * 100
            stats_msg += f"📊 **Profitability:** {profitability:.1f}%\n"
            if stats.get('botes_ganados', 0) > 0:
                stats_msg += f"🎉 **CONGRATULATIONS!** You've won {stats.get('botes_ganados', 0)} pot(s)!\n"
        else:
            stats_msg += f"🎲 **You haven't played yet** - Use `!dice play` to start!\n"

        await ctx.author.send(stats_msg)
        await ctx.send("📩 Statistics sent by private message.")
    except Exception as e:
        logger.exception(f"Error in cmd_dice_stats: {e}")
        await ctx.send("❌ Error getting your statistics.")


async def cmd_dice_ranking(ctx):
    """Show server player ranking."""
    if not ctx.guild:
        await ctx.send("❌ This command only works on servers.")
        return
    try:
        from discord_utils import get_server_name
        server_name = get_server_name(ctx.guild)
        db_dice_game = get_bote_db_instance(server_name)
        if not db_dice_game:
            await ctx.send("❌ Error accessing dice game database.")
            return

        ranking = db_dice_game.obtener_ranking_jugadores(str(ctx.guild.id), "total_ganado", 10)
        if not ranking:
            await ctx.send("📊 **DICE GAME RANKING** - No registered players yet.")
            return

        ranking_msg = f"🏆 **DICE GAME RANKING - {ctx.guild.name.upper()}** 🏆\n\n"
        # db_bote returns: (usuario_nombre, metric_value, total_jugadas, total_ganado, total_apostado)
        for i, (name, metric_value, total_jugadas, total_ganado, total_apostado) in enumerate(ranking, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
            balance = total_ganado - total_apostado
            profitability = (total_ganado / total_apostado * 100) if total_apostado > 0 else 0
            ranking_msg += f"{medal} **{name}**\n"
            ranking_msg += f"   💰 Won: {total_ganado:,} | 🎲 Games: {total_jugadas}\n"
            ranking_msg += f"   📈 Balance: {balance:,} ({profitability:.1f}%)\n\n"

        await ctx.send(ranking_msg)
    except Exception as e:
        logger.exception(f"Error in cmd_dice_ranking: {e}")
        await ctx.send("❌ Error getting ranking.")


async def cmd_dice_history(ctx):
    """Show last games played."""
    if not ctx.guild:
        await ctx.send("❌ This command only works on servers.")
        return
    try:
        from discord_utils import get_server_name
        server_name = get_server_name(ctx.guild)
        db_dice_game = get_bote_db_instance(server_name)
        if not db_dice_game:
            await ctx.send("❌ Error accessing dice game database.")
            return

        history = db_dice_game.obtener_historial_partidas(str(ctx.guild.id), 15)
        if not history:
            await ctx.send("📜 **DICE GAME HISTORY** - No registered games yet.")
            return

        history_msg = f"📜 **LAST DICE GAMES** 📜\n\n"
        for _id, usuario_id, usuario_nombre, servidor_id, servidor_nombre, apuesta, dados, combinacion, premio, bote_antes, bote_despues, fecha in history:
            try:
                dt = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
                formatted_date = dt.strftime("%d/%m %H:%M")
            except Exception:
                formatted_date = fecha[:16]
            prize_emoji = "🎉" if premio > 0 else "😅"
            history_msg += f"👤 **{usuario_nombre}** | {formatted_date}\n"
            history_msg += f"   🎲 {dados} → {combinacion}\n"
            history_msg += f"   {prize_emoji} Prize: {premio:,} coins\n\n"

        await ctx.send(history_msg)
    except Exception as e:
        logger.exception(f"Error in cmd_dice_history: {e}")
        await ctx.send("❌ Error getting history.")


async def cmd_dice_config(ctx, *args):
    """Configure dice game parameters (administrators only)."""
    if not ctx.guild:
        await ctx.send("❌ This command only works on servers.")
        return
    if not is_admin(ctx):
        await ctx.send("❌ Only administrators can configure the dice game.")
        return
    if not args:
        await ctx.send("❌ You must specify what to configure. Use `!dice config bet <amount>` or `!dice config announcements on/off`.")
        return

    try:
        from discord_utils import get_server_name
        server_name = get_server_name(ctx.guild)
        db_dice_game = get_bote_db_instance(server_name)
        if not db_dice_game:
            await ctx.send("❌ Error accessing dice game database.")
            return

        param = args[0].lower()
        if param == "bet":
            if len(args) < 2:
                await ctx.send("❌ You must specify the amount. Example: `!dice config bet 15`.")
                return
            try:
                amount = int(args[1])
                if amount < 1 or amount > 1000:
                    await ctx.send("❌ The bet must be between 1 and 1000 coins.")
                    return
                if db_dice_game.configurar_servidor(str(ctx.guild.id), apuesta_fija=amount):
                    await ctx.send(f"✅ **Fixed bet configured** - All games will now cost {amount:,} coins.")
                    logger.info(f"🎲 {ctx.author.name} configured bet to {amount} in {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error configuring the bet.")
            except ValueError:
                await ctx.send("❌ Invalid amount. Use an integer number.")

        elif param == "announcements":
            if len(args) < 2:
                await ctx.send("❌ You must specify on/off. Example: `!dice config announcements on`.")
                return
            state = args[1].lower()
            if state not in ["on", "off"]:
                await ctx.send("❌ Use 'on' or 'off'. Example: `!dice config announcements on`.")
                return
            announcements_enabled = state == "on"
            if db_dice_game.configurar_servidor(str(ctx.guild.id), anuncios_activos=announcements_enabled):
                state_msg = "enabled" if announcements_enabled else "disabled"
                await ctx.send(f"✅ **Announcements {state_msg}** - Dice game auto announcements have been {state_msg}.")
                logger.info(f"🎲 {ctx.author.name} {state_msg} announcements in {ctx.guild.name}")
            else:
                await ctx.send("❌ Error configuring announcements.")
        else:
            await ctx.send("❌ Parameter not recognized. Use `bet` or `announcements`.")
    except Exception as e:
        logger.exception(f"Error in cmd_dice_config: {e}")
        await ctx.send("❌ Error configuring dice game.")


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
