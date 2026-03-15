"""
Dice Game Discord Commands
Handles all dice game related Discord commands and subcommands.
"""

import asyncio
import logging
from datetime import datetime
from .dice_game_messages import get_message

logger = logging.getLogger(__name__)

# Global variables for database functions (will be set during registration)
_get_banker_db_instance = None
_get_dice_game_db_instance = None
_procesar_jugada = None
_is_admin = None
_BANKER_DB_AVAILABLE = False

def register_dice_commands(bot, personality, send_dm_or_channel, is_admin, 
                         get_banker_db_instance, get_dice_game_db_instance, 
                         procesar_jugada, DICE_GAME_AVAILABLE, DICE_GAME_DB_AVAILABLE, 
                         BANKER_DB_AVAILABLE):
    """
    Register all dice game commands with the Discord bot.
    
    Args:
        bot: Discord bot instance
        personality: Personality configuration
        send_dm_or_channel: Function to send DM or channel message
        is_admin: Function to check admin permissions
        get_banker_db_instance: Function to get banker database
        get_dice_game_db_instance: Function to get dice game database
        procesar_jugada: Function to process dice game roll
        DICE_GAME_AVAILABLE: Boolean indicating if dice game is available
        DICE_GAME_DB_AVAILABLE: Boolean indicating if dice game DB is available
        BANKER_DB_AVAILABLE: Boolean indicating if banker DB is available
    """
    
    # Set global variables for use in command functions
    global _get_banker_db_instance, _get_dice_game_db_instance, _procesar_jugada, _is_admin, _BANKER_DB_AVAILABLE
    _get_banker_db_instance = get_banker_db_instance
    _get_dice_game_db_instance = get_dice_game_db_instance
    _procesar_jugada = procesar_jugada
    _is_admin = is_admin
    _BANKER_DB_AVAILABLE = BANKER_DB_AVAILABLE
    
    # --- !dice (main dice game command) ---
    if DICE_GAME_AVAILABLE and DICE_GAME_DB_AVAILABLE and BANKER_DB_AVAILABLE:
        if bot.get_command("dice") is None:
            @bot.group(name="dice")
            async def cmd_dice(ctx):
                """Main dice game command."""
                if not ctx.guild:
                    await ctx.send(get_message("error_servidor_privado"))
                    return

                if not DICE_GAME_AVAILABLE or not DICE_GAME_DB_AVAILABLE or not BANKER_DB_AVAILABLE:
                    await ctx.send(get_message("error_juego_no_disponible"))
                    return

                if ctx.invoked_subcommand is None:
                    await cmd_dice_help(ctx, personality)
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


# --- DICE GAME SUBCOMMANDS ---

async def cmd_dice_play(ctx):
    """Roll the dice in the dice game."""
    if not ctx.guild:
        await ctx.send(get_message("error_solo_servidores"))
        return
    try:
        from discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_banker = _get_banker_db_instance(server_name) if _get_banker_db_instance else None
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_banker or not db_dice_game:
            await ctx.send(get_message("error_acceso_bd"))
            return

        try:
            if hasattr(db_dice_game, "ensure_player_stats"):
                db_dice_game.ensure_player_stats(str(ctx.author.id), str(ctx.guild.id))
        except Exception as e:
            logger.warning(f"Could not ensure player stats: {e}")

        # Get current pot balance from banker database
        pot_balance = 0
        if _BANKER_DB_AVAILABLE and _get_banker_db_instance:
            try:
                db_banker = _get_banker_db_instance(server_name)
                if db_banker:
                    try:
                        db_banker.create_wallet("dice_game_pot", "Dice Game Pot", str(ctx.guild.id), server_name)
                    except Exception:
                        pass
                    pot_balance = db_banker.get_balance("dice_game_pot", str(ctx.guild.id))
            except Exception as e:
                logger.warning(f"Could not get pot balance: {e}")
                pot_balance = 0

        result = await asyncio.to_thread(
            _procesar_jugada,
            str(ctx.author.id),
            ctx.author.display_name,
            str(ctx.guild.id),
            ctx.guild.name,
            pot_balance,
        )

        if result.get("success"):
            # Update pot balance in banker database (pot should already exist)
            if _BANKER_DB_AVAILABLE and _get_banker_db_instance and result.get('pot_after') is not None:
                try:
                    db_banker = _get_banker_db_instance(server_name)
                    if db_banker:
                        # Get current pot balance
                        current_balance = db_banker.get_balance("dice_game_pot", str(ctx.guild.id))
                        new_balance = result.get('pot_after', current_balance)
                        
                        # Update pot balance
                        balance_diff = new_balance - current_balance
                        if balance_diff != 0:
                            db_banker.update_balance(
                                user_id="dice_game_pot",
                                user_name="Dice Game Pot",
                                server_id=str(ctx.guild.id),
                                server_name=server_name,
                                amount=balance_diff,
                                type="POT_UPDATE",
                                description=f"Pot update after dice game"
                            )
                except Exception as e:
                    logger.warning(f"Could not update pot balance: {e}")
            
            await ctx.send(result.get("mensaje") or "✅ Played.")
            logger.info(f"🎲 {ctx.author.name} played in {ctx.guild.name} - Prize: {result.get('premio', 0)}")
            return

        await ctx.send(f"❌ {result.get('message', 'Error playing dice game')}")
    except Exception as e:
        logger.exception(f"Error in cmd_dice_play: {e}")
        await ctx.send(get_message("error_procesar_tirada"))


async def cmd_dice_help(ctx, personality):
    """Show complete dice game help."""
    help_msg = get_message("help_titulo") + "\n\n"
    help_msg += get_message("help_descripcion")
    help_msg += "**What is Dice Game?**\n"
    help_msg += "It's a dice game where you bet a fixed amount against the bank. "
    help_msg += "Roll 1-1-1 and take the entire accumulated pot.\n\n"
    help_msg += "**🎲 PRIZE TABLE:**\n"
    help_msg += "• **1-1-1** (0.46%) → 🎉 **ENTIRE POT** 🎉\n"
    help_msg += "• **Any triple** (2.78%) → x3 your bet\n"
    help_msg += "• **Straight 4-5-6** (2.78%) → x5 your bet\n"
    help_msg += "• **Pair** (41.67%) → Get your bet back\n"
    help_msg += "• **Nothing** (52.31%) → Lose your bet\n\n"
    help_msg += get_message("help_comandos")
    help_msg += get_message("help_jugar")
    help_msg += get_message("help_saldo")
    help_msg += get_message("help_estadisticas")
    help_msg += get_message("help_ranking")
    help_msg += get_message("help_historial")
    help_msg += get_message("help_config")
    help_msg += get_message("help_anuncios")
    help_msg += get_message("help_premios")
    help_msg += get_message("help_triple_ones")
    help_msg += get_message("help_three_of_a_kind")
    help_msg += get_message("help_straight")
    help_msg += get_message("help_par")
    help_msg += get_message("help_info_adicional")
    help_msg += get_message("help_info_parcial")
    help_msg += get_message("help_info_bote")

    await send_dm_or_channel(ctx, help_msg, get_message("help_sent_private"))


async def cmd_dice_balance(ctx, personality):
    """Show current pot balance."""
    if not _BANKER_DB_AVAILABLE or not _get_dice_game_db_instance:
        await ctx.send(get_message("error_sistema_no_disponible"))
        return

    try:
        from discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_banker = _get_banker_db_instance(server_name) if _get_banker_db_instance else None
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None

        try:
            if db_dice_game is not None and hasattr(db_dice_game, "ensure_player_stats"):
                db_dice_game.ensure_player_stats(str(ctx.author.id), str(ctx.guild.id))
        except Exception as e:
            logger.warning(f"Could not ensure player stats: {e}")

        # In dice game implementation, the pot is a special banker wallet
        try:
            db_banker.create_wallet("dice_game_pot", "Dice Game Pot", str(ctx.guild.id), server_name)
        except Exception:
            pass
        pot_balance = db_banker.get_balance("dice_game_pot", str(ctx.guild.id))
        config = db_dice_game.get_server_config(str(ctx.guild.id))
        fixed_bet = config.get("bet_fija", config.get("apuesta_fija", 1))

        # Use dice_game_balance_messages from personality
        balance_msg = get_message("title", servidor=ctx.guild.name.upper())
        balance_msg += get_message("current_balance", saldo=pot_balance)
        balance_msg += get_message("fixed_bet", apuesta=fixed_bet)
        balance_msg += get_message("possible_plays", jugadas=pot_balance // fixed_bet if fixed_bet > 0 else 0)

        if pot_balance >= 100:
            balance_msg += get_message("big_pot", saldo=pot_balance)
        elif pot_balance >= 50:
            balance_msg += get_message("medium_pot")
        else:
            balance_msg += get_message("small_pot")

        balance_msg += get_message("use_command")
        await ctx.author.send(balance_msg)
        await ctx.send(get_message("sent_private"))
    except Exception as e:
        logger.exception(f"Error in cmd_dice_balance: {e}")
        await ctx.send(get_message("error_obtener_saldo"))


async def cmd_dice_stats(ctx):
    """Show player's personal statistics."""
    if not ctx.guild:
        await ctx.send(get_message("error_solo_servidores"))
        return
    try:
        from discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_dice_game:
            await ctx.send(get_message("error_acceso_bd_juego"))
            return

        stats = db_dice_game.get_player_stats(str(ctx.author.id), str(ctx.guild.id))
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
            stats_msg += get_message("ranking_sin_jugadas") + "\n"

        await ctx.author.send(stats_msg)
        await ctx.send(get_message("estadisticas_enviadas_privado"))
    except Exception as e:
        logger.exception(f"Error in cmd_dice_stats: {e}")
        await ctx.send(get_message("error_obtener_estadisticas"))


async def cmd_dice_ranking(ctx):
    """Show server player ranking."""
    if not ctx.guild:
        await ctx.send("❌ This command only works on servers.")
        return
    try:
        from discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_dice_game:
            await ctx.send("❌ Error accessing dice game database.")
            return

        ranking = db_dice_game.get_player_ranking(str(ctx.guild.id), "total_ganado", 10)
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
        from discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_dice_game:
            await ctx.send("❌ Error accessing dice game database.")
            return

        history = db_dice_game.get_game_history(str(ctx.guild.id), 15)
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


async def cmd_dice_config(ctx, personality):
    """Configure dice game parameters (administrators only)."""
    if not ctx.guild:
        await ctx.send("❌ This command only works on servers.")
        return
    if not _is_admin(ctx):
        await ctx.send("❌ Only administrators can configure the dice game.")
        return
    if len(ctx.args) < 2:
        await ctx.send("❌ You must specify what to configure. Use `!dice config bet <amount>` or `!dice config announcements on/off`.")
        return

    try:
        from discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_dice_game:
            await ctx.send("❌ Error accessing dice game database.")
            return

        param = ctx.args[1].lower()
        if param == "bet":
            if len(ctx.args) < 3:
                await ctx.send("❌ You must specify the amount. Example: `!dice config bet 15`.")
                return
            try:
                amount = int(ctx.args[2])
                if amount < 1 or amount > 1000:
                    await ctx.send("❌ The bet must be between 1 and 1000 coins.")
                    return
                if db_dice_game.configure_server(str(ctx.guild.id), bet_fija=amount):
                    await ctx.send(f"✅ **Fixed bet configured** - All games will now cost {amount:,} coins.")
                    logger.info(f"🎲 {ctx.author.name} configured bet to {amount} in {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error configuring the bet.")
            except ValueError:
                await ctx.send("❌ Invalid amount. Use an integer number.")

        elif param == "announcements":
            if len(ctx.args) < 3:
                await ctx.send("❌ You must specify on/off. Example: `!dice config announcements on`.")
                return
            state = ctx.args[2].lower()
            if state not in ["on", "off"]:
                await ctx.send("❌ Use 'on' or 'off'. Example: `!dice config announcements on`.")
                return
            announcements_enabled = state == "on"
            if db_dice_game.configure_server(str(ctx.guild.id), announcements_active=announcements_enabled):
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
