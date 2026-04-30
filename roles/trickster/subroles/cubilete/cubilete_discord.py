"""
Cubilete Discord Commands
Handles all cubilete related Discord commands and subcommands.
"""

import asyncio
import logging
from datetime import datetime
from .cubilete_messages import get_message

# Import roles database
try:
    from agent_roles_db import get_roles_db_instance
except ImportError:
    get_roles_db_instance = None

logger = logging.getLogger(__name__)


def register_cubilete_commands(bot, personality, send_dm_or_channel, is_admin, 
                                 get_banker_db_instance, 
                                 process_play, CUBILETE_AVAILABLE):
    """
    Register all cubilete commands with the Discord bot.
    
    NOTE: !cubilete command has been removed. Use !canvas → Trickster instead.
    Helper functions are kept for Canvas UI integration.
    
    Args:
        bot: Discord bot instance
        personality: Personality configuration
        send_dm_or_channel: Function to send DM or channel message
        is_admin: Function to check admin permissions
        get_banker_db_instance: Function to get banker database
        process_play: Function to process a cubilete play
        CUBILETE_AVAILABLE: Boolean indicating if cubilete is available
    """
    
    # NOTE: !cubilete command registration removed - use Canvas UI instead
    logger.info("🎲 Cubilete commands registration skipped - moved to Canvas UI")


# --- CUBILETE HELPER FUNCTIONS (for Canvas UI) ---

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


async def cmd_cubilete_play(ctx):
    """Play cubilete - roll 5 dice against the pot."""
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

        # Get current pot balance from banker database
        pot_balance = 0
        if get_banker_db_instance is not None:
            try:
                db_banker = get_roles_db_instance(server_id) if get_roles_db_instance else None
                if db_banker:
                    try:
                        db_banker.create_wallet("cubilete_pot", "Cubilete Pot", 'system')
                    except Exception:
                        pass
                    pot_balance = db_banker.get_balance("cubilete_pot")
            except Exception as e:
                logger.warning(f"Could not get pot balance: {e}")
                pot_balance = 0

        result = await asyncio.to_thread(
            process_play,
            str(ctx.author.id),
            ctx.author.display_name,
            ctx.guild.name,
            pot_balance,
            str(ctx.guild.id),
        )

        logger.info(f"🎲 Cubilete result: success={result.get('success')}, announcements={len(result.get('announcements', []))}")

        if result.get("success"):
            await ctx.send(result.get("message", "✅ Cubilete round completed."))
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
                
            logger.info(f"🎲 {ctx.author.name} played cubilete in {ctx.guild.name} - Prize: {result.get('prize', 0)}")
            return

        await ctx.send(f"❌ {result.get('message', 'Error processing the cubilete round.')}")
    except Exception as e:
        logger.exception(f"Error in cmd_cubilete_play: {e}")
        await ctx.send(get_message("error_processing_roll"))


async def cmd_cubilete_balance(ctx, _personality):
    """Show the current pot balance."""
    if get_roles_db_instance is None:
        await ctx.send(get_message("error_system_unavailable"))
        return

    try:
        from discord_bot.discord_utils import get_server_key
        from agent_roles_db import get_roles_db_instance
        server_id = get_server_key(ctx.guild)
        db_banker = get_roles_db_instance(server_id) if get_roles_db_instance else None
        roles_db = get_roles_db_instance(server_id)

        # Get pot balance
        try:
            db_banker.create_wallet("cubilete_pot", "Cubilete Pot", 'system')
        except Exception:
            pass
        pot_balance = db_banker.get_balance("cubilete_pot")
        
        try:
            from discord_bot.canvas.server_config import get_role_config_value
            config = get_role_config_value(str(ctx.guild.id), "cubilete", "config", default={})
            bet_multiplier = config.get("bet_multiplier_tae", 2)
        except Exception as e:
            logger.warning(f"Error getting cubilete config from server_config: {e}")
            bet_multiplier = 2
        
        # Get TAE
        tae = db_banker.get_tae(server_id)
        bet = tae * bet_multiplier

        balance_msg = get_message("pot_title", server=ctx.guild.name.upper())
        balance_msg += get_message("current_balance", balance=pot_balance)
        balance_msg += f"🎲 **Bet:** {bet:,} coins ({bet_multiplier}x TAE)\n"
        balance_msg += f"📊 **Possible plays:** {pot_balance // bet if bet > 0 else 0}\n"

        if pot_balance >= bet * 72:
            balance_msg += get_message("big_pot", balance=pot_balance)
        elif pot_balance >= bet * 36:
            balance_msg += "🔥 **Medium pot**\n"
        else:
            balance_msg += "💧 **Small pot**\n"

        balance_msg += get_message("use_command")
        await ctx.author.send(balance_msg)
        await ctx.send(get_message("private_message_sent"))
    except Exception as e:
        logger.exception(f"Error in cmd_cubilete_balance: {e}")
        await ctx.send(get_message("error_getting_balance"))


async def cmd_cubilete_stats(ctx):
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

        stats = roles_db.get_cubilete_stats(str(ctx.author.id))
        total_plays = stats.get('total_plays', 0)
        total_bet = stats.get('total_bet', 0)
        total_won = stats.get('total_won', 0)
        pots_won = stats.get('pots_won', 0)
        biggest_prize = stats.get('biggest_prize', 0)
        stats_msg = f"📊 **YOUR CUBILETE STATS** 📊\n\n"
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
        logger.exception(f"Error in cmd_cubilete_stats: {e}")
        await ctx.send(get_message("error_getting_stats"))


async def cmd_cubilete_ranking(ctx):
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
        history = roles_db.get_cubilete_history(1000)
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
        logger.exception(f"Error in cmd_cubilete_ranking: {e}")
        await ctx.send(get_message("error_getting_ranking"))


async def cmd_cubilete_history(ctx):
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

        history = roles_db.get_cubilete_history(15)
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
        logger.exception(f"Error in cmd_cubilete_history: {e}")
        await ctx.send(get_message("error_getting_history"))
