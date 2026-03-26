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
_process_play = None
_is_admin = None
_BANKER_DB_AVAILABLE = False

def register_dice_commands(bot, personality, send_dm_or_channel, is_admin, 
                         get_banker_db_instance, get_dice_game_db_instance, 
                         process_play, DICE_GAME_AVAILABLE, DICE_GAME_DB_AVAILABLE, 
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
        process_play: Function to process a dice game roll
        DICE_GAME_AVAILABLE: Boolean indicating if dice game is available
        DICE_GAME_DB_AVAILABLE: Boolean indicating if dice game DB is available
        BANKER_DB_AVAILABLE: Boolean indicating if banker DB is available
    """
    
    # Set global variables for use in command functions
    global _get_banker_db_instance, _get_dice_game_db_instance, _process_play, _is_admin, _BANKER_DB_AVAILABLE
    _get_banker_db_instance = get_banker_db_instance
    _get_dice_game_db_instance = get_dice_game_db_instance
    _process_play = process_play
    _is_admin = is_admin
    _BANKER_DB_AVAILABLE = BANKER_DB_AVAILABLE
    
    # --- !dice (main dice game command) ---
    if DICE_GAME_AVAILABLE and DICE_GAME_DB_AVAILABLE and BANKER_DB_AVAILABLE:
        if bot.get_command("dice") is None:
            @bot.group(name="dice")
            async def cmd_dice(ctx):
                """Main dice game command."""
                if not ctx.guild:
                    await ctx.send(get_message("error_private_message"))
                    return

                if not DICE_GAME_AVAILABLE or not DICE_GAME_DB_AVAILABLE or not BANKER_DB_AVAILABLE:
                    await ctx.send(get_message("error_game_unavailable"))
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
                await cmd_dice_stats(ctx)
            
            @cmd_dice.command(name="ranking")
            async def cmd_dice_ranking_wrapper(ctx):
                await cmd_dice_ranking(ctx)
            
            @cmd_dice.command(name="history")
            async def cmd_dice_history_wrapper(ctx):
                await cmd_dice_history(ctx)
            
            @cmd_dice.command(name="config")
            async def cmd_dice_config_wrapper(ctx):
                await cmd_dice_config(ctx, personality)

            logger.info("🎲 Dice command registered")


# --- DICE GAME SUBCOMMANDS ---

async def get_announcement_channel(ctx):
    """Get the best channel for announcements (general channel or current channel)."""
    import discord
    
    # Try to find a general channel first
    for channel in ctx.guild.text_channels:
        if any(name in channel.name.lower() for name in ['general', 'chat', 'principal', 'general-chat']):
            return channel
    
    # If no general channel found, try to find the first channel the bot can read
    for channel in ctx.guild.text_channels:
        if channel.permissions_for(ctx.guild.me).send_messages:
            return channel
    
    # Fallback to current channel
    return ctx.channel


async def cmd_dice_play(ctx):
    """Roll the dice in the dice game."""
    if not ctx.guild:
        await ctx.send(get_message("error_servers_only"))
        return
    try:
        from discord_bot.discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_banker = _get_banker_db_instance(server_name) if _get_banker_db_instance else None
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_banker or not db_dice_game:
            await ctx.send(get_message("error_database_access"))
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
            _process_play,
            str(ctx.author.id),
            ctx.author.display_name,
            str(ctx.guild.id),
            ctx.guild.name,
            pot_balance,
        )

        print(f"DEBUG: Raw result = {result}")
        logger.info(f"🎲 Dice game result: success={result.get('success')}, announcements={len(result.get('announcements', []))}")

        if result.get("success"):
            await ctx.send(result.get("message", "✅ Dice game round completed."))
            announcements = result.get("announcements", [])
            logger.info(f"📢 Processing {len(announcements)} announcements")
            
            try:
                # Get the best channel for announcements
                announcement_channel = await get_announcement_channel(ctx)
                logger.info(f"📢 Using announcement channel: {announcement_channel.name} (ID: {announcement_channel.id})")
                
                for announcement in announcements:
                    if announcement:
                        logger.info(f"📢 Sending announcement: {announcement[:50]}...")
                        await announcement_channel.send(announcement)
                        logger.info(f"📢 Announcement sent to {announcement_channel.name}")
                    else:
                        logger.warning(f"📢 Empty announcement found")
            except Exception as e:
                logger.error(f"❌ Error sending announcements: {e}")
                
            logger.info(f"🎲 {ctx.author.name} played in {ctx.guild.name} - Prize: {result.get('prize', 0)}")
            return

        await ctx.send(f"❌ {result.get('message', 'Error processing the dice game round.')}")
    except Exception as e:
        logger.exception(f"Error in cmd_dice_play: {e}")
        await ctx.send(get_message("error_procesar_tirada"))


async def cmd_dice_help(ctx, _personality):
    """Show the complete dice game help."""
    help_msg = get_message("help_titulo") + "\n\n"
    help_msg += get_message("help_descripcion")
    help_msg += "**What is the Dice Game?**\n"
    help_msg += "Bet a fixed amount and roll against the pot. "
    help_msg += "Roll 1-1-1 to win the entire accumulated pot.\n\n"
    help_msg += "**🎲 PRIZE TABLE:**\n"
    help_msg += "• **1-1-1** (0.46%) → 🎉 **ENTIRE POT** 🎉\n"
    help_msg += "• **Any triple** (2.78%) → x3 your bet\n"
    help_msg += "• **Straight 4-5-6** (2.78%) → x5 your bet\n"
    help_msg += "• **Pair** (41.67%) → Recover your bet\n"
    help_msg += "• **Nothing** (52.31%) → Lose your bet\n\n"
    help_msg += get_message("help_commands")
    help_msg += get_message("help_play")
    help_msg += get_message("help_balance")
    help_msg += get_message("help_stats")
    help_msg += get_message("help_ranking")
    help_msg += get_message("help_history")
    help_msg += get_message("help_config")
    help_msg += get_message("help_announcements")
    help_msg += get_message("help_prizes")
    help_msg += get_message("help_triple_ones")
    help_msg += get_message("help_three_of_a_kind")
    help_msg += get_message("help_straight")
    help_msg += get_message("help_pair")
    help_msg += get_message("help_additional_info")
    help_msg += get_message("help_partial_info")
    help_msg += get_message("help_pot_info")

    await send_dm_or_channel(ctx, help_msg, get_message("help_sent_private"))


async def cmd_dice_balance(ctx, _personality):
    """Show the current pot balance."""
    if not _BANKER_DB_AVAILABLE or not _get_dice_game_db_instance:
        await ctx.send(get_message("error_system_unavailable"))
        return

    try:
        from discord_bot.discord_utils import get_server_key
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
        fixed_bet = config.get("fixed_bet", 1)

        # Use dice_game_balance_messages from personality
        balance_msg = get_message("title", server=ctx.guild.name.upper())
        balance_msg += get_message("current_balance", balance=pot_balance)
        balance_msg += get_message("fixed_bet", amount=fixed_bet)
        balance_msg += get_message("possible_plays", plays=pot_balance // fixed_bet if fixed_bet > 0 else 0)

        if pot_balance >= 100:
            balance_msg += get_message("big_pot", balance=pot_balance)
        elif pot_balance >= 50:
            balance_msg += get_message("medium_pot")
        else:
            balance_msg += get_message("small_pot")

        balance_msg += get_message("use_command")
        await ctx.author.send(balance_msg)
        await ctx.send(get_message("sent_private"))
    except Exception as e:
        logger.exception(f"Error in cmd_dice_balance: {e}")
        await ctx.send(get_message("error_getting_balance"))


async def cmd_dice_stats(ctx):
    """Show the player's personal statistics."""
    if not ctx.guild:
        await ctx.send(get_message("error_servers_only"))
        return
    try:
        from discord_bot.discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_dice_game:
            await ctx.send(get_message("error_game_database_access"))
            return

        stats = db_dice_game.get_player_stats(str(ctx.author.id), str(ctx.guild.id))
        total_plays = stats.get('total_plays', 0)
        total_bet = stats.get('total_bet', 0)
        total_won = stats.get('total_won', 0)
        pots_won = stats.get('pots_won', 0)
        biggest_prize = stats.get('biggest_prize', 0)
        stats_msg = f"📊 **YOUR DICE GAME STATS** 📊\n\n"
        stats_msg += f"👤 **Player:** {ctx.author.display_name}\n"
        stats_msg += f"🎲 **Games played:** {total_plays}\n"
        stats_msg += f"💰 **Total bet:** {total_bet:,} coins\n"
        stats_msg += f"🏆 **Total won:** {total_won:,} coins\n"
        stats_msg += f"💎 **Pots won:** {pots_won}\n"
        stats_msg += f"🎯 **Biggest prize:** {biggest_prize:,} coins\n"
        net_balance = total_won - total_bet
        stats_msg += f"📈 **Net balance:** {net_balance:,} coins\n\n"

        if total_plays > 0:
            profitability = (total_won / max(total_bet, 1)) * 100
            stats_msg += f"📊 **Return rate:** {profitability:.1f}%\n"
            if pots_won > 0:
                stats_msg += f"🎉 **Congratulations!** You have won {pots_won} pot(s).\n"
        else:
            stats_msg += get_message("no_games_played") + "\n"

        await ctx.author.send(stats_msg)
        await ctx.send(get_message("stats_sent_private"))
    except Exception as e:
        logger.exception(f"Error in cmd_dice_stats: {e}")
        await ctx.send(get_message("error_getting_stats"))


async def cmd_dice_ranking(ctx):
    """Show the server player ranking."""
    if not ctx.guild:
        await ctx.send(get_message("error_servers_only"))
        return
    try:
        from discord_bot.discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_dice_game:
            await ctx.send(get_message("error_game_database_access"))
            return

        ranking = db_dice_game.get_player_ranking(str(ctx.guild.id), "prize", 10)
        if not ranking:
            await ctx.send(get_message("ranking_no_players"))
            return

        ranking_msg = get_message("ranking_title", server=ctx.guild.name.upper()) + "\n\n"
        for i, (name, prize, total_plays, total_won, total_bet) in enumerate(ranking, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
            balance = total_won - total_bet
            ranking_msg += f"{medal} **{name}**\n"
            ranking_msg += f"   🏆 Prize: {prize:,} | {get_message('ranking_games', games=total_plays)}\n"
            ranking_msg += f"   {get_message('ranking_balance_line', balance=f'{balance:,}', profitability=(total_won / total_bet * 100) if total_bet > 0 else 0)}\n\n"

        await ctx.send(ranking_msg)
    except Exception as e:
        logger.exception(f"Error in cmd_dice_ranking: {e}")
        await ctx.send(get_message("error_getting_ranking"))


async def cmd_dice_history(ctx):
    """Show the most recent games played."""
    if not ctx.guild:
        await ctx.send(get_message("error_servers_only"))
        return
    try:
        from discord_bot.discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_dice_game:
            await ctx.send(get_message("error_game_database_access"))
            return

        history = db_dice_game.get_game_history(str(ctx.guild.id), 15)
        if not history:
            await ctx.send(get_message("history_no_games"))
            return

        history_msg = get_message("history_title") + "\n\n"
        for _id, _user_id, user_name, _server_id, _server_name, _bet, dice, combination, prize, _pot_before, _pot_after, played_at in history:
            try:
                dt = datetime.fromisoformat(played_at.replace('Z', '+00:00'))
                formatted_date = dt.strftime("%d/%m %H:%M")
            except Exception:
                formatted_date = played_at[:16]
            history_msg += f"{get_message('game_title', player=user_name)} | {get_message('game_date', date=formatted_date)}\n"
            history_msg += f"   {get_message('game_dice', dice=dice)} {get_message('game_combination', combination=combination)}\n"
            history_msg += f"   {get_message('game_prize', prize=prize)}\n\n"

        await ctx.send(history_msg)
    except Exception as e:
        logger.exception(f"Error in cmd_dice_history: {e}")
        await ctx.send(get_message("error_getting_history"))


async def cmd_dice_config(ctx, _personality):
    """Configure dice game parameters (administrators only)."""
    if not ctx.guild:
        await ctx.send(get_message("error_servers_only"))
        return
    if not _is_admin(ctx):
        await ctx.send(get_message("error_admin_only"))
        return
    if len(ctx.args) < 2:
        await ctx.send(get_message("error_config_parameter"))
        return

    try:
        from discord_bot.discord_utils import get_server_key
        server_name = get_server_key(ctx.guild)
        db_dice_game = _get_dice_game_db_instance(server_name) if _get_dice_game_db_instance else None
        if not db_dice_game:
            await ctx.send(get_message("error_game_database_access"))
            return

        param = ctx.args[1].lower()
        if param == "bet":
            if len(ctx.args) < 3:
                await ctx.send(get_message("error_specify_amount"))
                return
            try:
                amount = int(ctx.args[2])
                if amount < 1 or amount > 1000:
                    await ctx.send(get_message("error_bet_range"))
                    return
                if db_dice_game.configure_server(str(ctx.guild.id), fixed_bet=amount):
                    await ctx.send(get_message("fixed_bet_configured", amount=amount))
                    logger.info(f"🎲 {ctx.author.name} configured the fixed bet to {amount} in {ctx.guild.name}")
                else:
                    await ctx.send(get_message("error_configuring_bet"))
            except ValueError:
                await ctx.send("❌ Invalid amount. Use a whole number.")

        elif param == "announcements":
            if len(ctx.args) < 3:
                await ctx.send(get_message("error_announcement_value"))
                return
            state = ctx.args[2].lower()
            if state not in ["on", "off"]:
                await ctx.send(get_message("error_announcement_value"))
                return
            announcements_enabled = state == "on"
            if db_dice_game.configure_server(str(ctx.guild.id), announcements_active=announcements_enabled):
                await ctx.send(get_message("announcements_configured", enabled=announcements_enabled))
                logger.info(f"🎲 {ctx.author.name} {'enabled' if announcements_enabled else 'disabled'} dice game announcements in {ctx.guild.name}")
            else:
                await ctx.send(get_message("error_configuring_announcements"))
        else:
            await ctx.send("❌ Unknown setting. Use `bet` or `announcements`.")
    except Exception as e:
        logger.exception(f"Error in cmd_dice_config: {e}")
        await ctx.send("❌ Could not configure the dice game.")
