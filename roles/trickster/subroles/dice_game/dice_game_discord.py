"""
Dice Game Discord Commands
Handles all dice game related Discord commands and subcommands.
"""

import asyncio
import json
import logging
from datetime import datetime
from .dice_game_messages import get_message

# Import roles database
try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None

logger = logging.getLogger(__name__)

# Legacy variables removed - now using roles_db directly

def register_dice_commands(bot, personality, send_dm_or_channel, is_admin, 
                         get_banker_db_instance, 
                         process_play, DICE_GAME_AVAILABLE):
    """
    Register all dice game commands with the Discord bot.
    
    Args:
        bot: Discord bot instance
        personality: Personality configuration
        send_dm_or_channel: Function to send DM or channel message
        is_admin: Function to check admin permissions
        get_banker_db_instance: Function to get banker database
        process_play: Function to process a dice game roll
        DICE_GAME_AVAILABLE: Boolean indicating if dice game is available
    """
    
    # Global variables removed - using roles_db directly
    
    # --- !dice (main dice game command) ---
    if DICE_GAME_AVAILABLE and get_roles_db_instance is not None and get_roles_db_instance is not None:
        if bot.get_command("dice") is None:
            @bot.group(name="dice")
            async def cmd_dice(ctx):
                """Main dice game command."""
                if not ctx.guild:
                    await ctx.send(get_message("error_private_message"))
                    return

                if not DICE_GAME_AVAILABLE or not get_roles_db_instance is not None or not get_roles_db_instance is not None:
                    await ctx.send(get_message("error_game_unavailable"))
                    return

                if ctx.invoked_subcommand is None:
                    await cmd_dice_help(ctx, personality)
                    return

            # Register dice subcommands
            @cmd_dice.command(name="play")
            async def cmd_dice_play_wrapper(ctx):
                await cmd_dice_play(ctx, personality, send_dm_or_channel, is_admin, get_banker_db_instance, process_play)
            
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
        from agent_roles_db import get_roles_db_instance
        server_id = get_server_key(ctx.guild)
        db_banker = get_roles_db_instance(server_id) if get_roles_db_instance else None
        roles_db = get_roles_db_instance(server_id)
        if not db_banker or not roles_db:
            await ctx.send(get_message("error_database_access"))
            return

        # Stats are now updated in the dice_game.py process_play function

        # Get current pot balance from banker database
        pot_balance = 0
        if get_banker_db_instance is not None:
            try:
                db_banker = get_roles_db_instance(server_id) if get_roles_db_instance else None
                if db_banker:
                    try:
                        db_banker.create_wallet("dice_game_pot", "Dice Game Pot", 'system')
                    except Exception:
                        pass
                    pot_balance = db_banker.get_balance("dice_game_pot")
            except Exception as e:
                logger.warning(f"Could not get pot balance: {e}")
                pot_balance = 0

        result = await asyncio.to_thread(
            process_play,
            str(ctx.author.id),
            ctx.author.display_name,
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
    if not _get_roles_db_instance is not None:
        await ctx.send(get_message("error_system_unavailable"))
        return

    try:
        from discord_bot.discord_utils import get_server_key
        from agent_roles_db import get_roles_db_instance
        server_id = get_server_key(ctx.guild)
        db_banker = get_roles_db_instance(server_id) if get_roles_db_instance else None
        roles_db = get_roles_db_instance(server_id)

        # Stats are now updated in the dice_game.py process_play function

        # In dice game implementation, the pot is a special banker wallet
        try:
            db_banker.create_wallet("dice_game_pot", "Dice Game Pot", 'system')
        except Exception:
            pass
        pot_balance = db_banker.get_balance("dice_game_pot")
        config = roles_db.get_role_config('dice_game', str(ctx.guild.id))
        fixed_bet = config.get("bet_fija", 1)

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
        from agent_roles_db import get_roles_db_instance
        server_id = get_server_key(ctx.guild)
        roles_db = get_roles_db_instance(server_id)
        if not roles_db:
            await ctx.send(get_message("error_game_database_access"))
            return

        stats = roles_db.get_dice_game_stats(str(ctx.author.id))
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
        from agent_roles_db import get_roles_db_instance
        server_id = get_server_key(ctx.guild)
        roles_db = get_roles_db_instance(server_id)
        if not roles_db:
            await ctx.send(get_message("error_game_database_access"))
            return

        # Get all player stats and sort by prize
        history = roles_db.get_dice_game_history(1000)
        if not history:
            await ctx.send(get_message("ranking_no_players"))
            return
        
        # Aggregate stats by user
        player_stats = {}
        for play in history:
            user_id = play['user_id']
            user_name = play['user_name']
            if user_id not in player_stats:
                player_stats[user_id] = {
                    'user_name': user_name,
                    'total_won': 0,
                    'biggest_prize': 0
                }
            player_stats[user_id]['total_won'] += play['prize']
            player_stats[user_id]['biggest_prize'] = max(player_stats[user_id]['biggest_prize'], play['prize'])
        
        # Sort by total won
        ranking = sorted(player_stats.items(), key=lambda x: x[1]['total_won'], reverse=True)[:10]

        ranking_msg = get_message("ranking_title", server=ctx.guild.name.upper()) + "\n\n"
        for i, (user_id, stats) in enumerate(ranking, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
            user_name = stats['user_name']
            total_won = stats['total_won']
            biggest_prize = stats['biggest_prize']
            ranking_msg += f"{medal} **{user_name}**\n"
            ranking_msg += f"   🏆 Total won: {total_won:,} coins\n"
            ranking_msg += f"   💎 Biggest prize: {biggest_prize:,} coins\n\n"

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
        from agent_roles_db import get_roles_db_instance
        server_id = get_server_key(ctx.guild)
        roles_db = get_roles_db_instance(server_id)
        if not roles_db:
            await ctx.send(get_message("error_game_database_access"))
            return

        history = roles_db.get_dice_game_history(15)
        if not history:
            await ctx.send(get_message("history_no_games"))
            return

        history_msg = get_message("history_title") + "\n\n"
        for play in history:
            user_name = play['user_name']
            bet = play['bet']
            dice = play['dice']
            combination = play['combination']
            prize = play['prize']
            played_at = play['created_at']
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
        from agent_roles_db import get_roles_db_instance
        server_id = get_server_key(ctx.guild)
        roles_db = get_roles_db_instance(server_id)
        if not roles_db:
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
                if roles_db.save_role_config('dice_game', True, json.dumps({"bet_fija": amount})):
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
            if roles_db.save_role_config('dice_game', True, json.dumps({"announcements_active": announcements_enabled})):
                await ctx.send(get_message("announcements_configured", enabled=announcements_enabled))
                logger.info(f"🎲 {ctx.author.name} {'enabled' if announcements_enabled else 'disabled'} dice game announcements in {ctx.guild.name}")
            else:
                await ctx.send(get_message("error_configuring_announcements"))
        else:
            await ctx.send("❌ Unknown setting. Use `bet` or `announcements`.")
    except Exception as e:
        logger.exception(f"Error in cmd_dice_config: {e}")
        await ctx.send("❌ Could not configure the dice game.")
