import os
import json
from agent_logging import get_logger

logger = get_logger('cubilete_messages')


def get_cubilete_messages(server_id: str = None):
    """Load custom Cubilete messages from trickster.json and answers.json."""
    combined_messages = {}
    
    try:
        from agent_runtime import get_personality_directory
        
        # Load descriptions from trickster.json
        try:
            personality_dir = get_personality_directory()
            trickster_path = os.path.join(get_personality_directory(server_id), "descriptions", "trickster.json")
            if os.path.exists(trickster_path):
                with open(trickster_path, encoding="utf-8") as f:
                    trickster_data = json.load(f)
                desc_cubilete_messages = trickster_data.get("cubilete", {})
                combined_messages.update(desc_cubilete_messages)
                logger.debug("🎲 Loaded cubilete descriptions from trickster.json")
        except Exception as e:
            logger.warning(f"⚠️ Could not load cubilete descriptions from trickster.json: {e}")
        
        # Load responses from answers.json
        try:
            answers_path = os.path.join(get_personality_directory(server_id), "answers.json")
            if os.path.exists(answers_path):
                with open(answers_path, encoding="utf-8") as f:
                    answers_data = json.load(f)
                # Navigate to trickster.cubilete in answers
                trickster_answers = answers_data.get("trickster", {})
                cubilete_answers = trickster_answers.get("cubilete", {})
                combined_messages.update(cubilete_answers)
                logger.debug("🎲 Loaded cubilete responses from answers.json")
        except Exception as e:
            logger.warning(f"⚠️ Could not load cubilete responses from answers.json: {e}")

        if not combined_messages:
            logger.warning("⚠️ No custom cubilete messages found in either file")
            return get_default_messages()
        else:
            logger.debug(f"🎲 Combined cubilete messages loaded: {len(combined_messages)} messages")
            return combined_messages

    except Exception as e:
        logger.error(f"❌ Error loading cubilete messages: {e}")
        return get_default_messages()


def get_default_messages():
    """Default messages if no customization available (English fallback)."""
    return {
        "invitation": "🎲 **CUBILETE!** 🎲 Bet against the progressive pot",
        "winner": "🎉 **WINNER!**",
        "loser": "😅 No luck this time",
        "jackpot": "🎰 **JACKPOT!**",
        "repoker": "🎰 (REPÓKER)",
        "poker": "(PÓKER)",
        "full": "(FULL)",
        "trio": "(TRÍO)",
        "doble_pareja": "(DOBLE PAREJA)",
        "pareja": "(PAREJA)",
        "nada": "(NO PRIZE)",
        "animation": "🎲🎲🎲 **ROLLING THE DICE!** 🎲🎲🎲",
        "insufficient_balance": "❌ Insufficient gold! You need {bet:,} gold to play. Your current balance: {balance:,} gold coins",
        "pot_won": "🎉🎉🎉 **JACKPOT WINNER!** 🎉🎉🎉 You won {prize:,} gold coins!",
        "prize_multiplier": "🎊 **WINNER!** {combination} - Prize: {prize:,} gold coins",
        "no_prize": "😅 {combination} - No prize. Better luck next time!",
        "error_jugada": "❌ Error processing roll: {error}",
        "roll_title": "🎲 **YOUR ROLL:**",
        "combination_title": "📊 **COMBINATION:**",
        "prize_title": "💰 **PRIZE:**",
        "pot_title": "🏆 **CURRENT POT:**",
        "big_pot_announcement": "🔥 **POT ALERT** 🔥 The pot has reached **{balance:,} gold coins** ({threshold:,} = 72x the current bet of {bet:,}). Use `!canvas` → Trickster to try to win it!",
        "jackpot_won_announcement": "🎰 **JACKPOT WON** 🎉 **{player}** has taken the full pot and won **{prize:,} gold coins** in **{server}**!",
        "error_private_message": "❌ This command only works on servers, not in private messages.",
        "error_game_unavailable": "❌ The cubilete game is not available on this server.",
        "error_database_access": "❌ Error accessing game databases.",
        "error_processing_roll": "❌ Error processing the roll. Please try again.",
        "help_sent_private": "📩 Cubilete help sent by private message.",
        "error_system_unavailable": "❌ The cubilete system is not available on this server.",
        "error_getting_balance": "❌ Error getting pot balance.",
        "private_message_sent": "📩 Pot balance sent by private message.",
        "stats_sent_private": "📩 Statistics sent by private message.",
        "error_getting_stats": "❌ Error getting your statistics.",
        "error_game_database_access": "❌ Error accessing cubilete database.",
        "ranking_no_players": "📊 **CUBILETE RANKING** - No registered players yet.",
        "error_getting_ranking": "❌ Error getting ranking.",
        "history_no_games": "📜 **CUBILETE HISTORY** - No registered games yet.",
        "error_getting_history": "❌ Error getting history.",
        "error_servers_only": "❌ This command only works on servers.",
        "error_admin_only": "❌ Only administrators can configure the cubilete game.",
        "error_config_parameter": "❌ You must specify what to configure. Use `!canvas` → Trickster → Admin to configure.",
        "error_specify_amount": "❌ You must specify the amount. Use `!canvas` → Trickster → Admin to configure.",
        "error_bet_range": "❌ The bet multiplier must be between 1 and 10.",
        "bet_multiplier_configured": "✅ **Bet multiplier configured** - All games will now cost {amount}x TAE.",
        "error_configuring_bet": "❌ Error configuring bet multiplier.",
        "error_announcement_value": "❌ Invalid value. Use 'on' or 'off' for announcements.",
        "announcements_configured": "✅ **Announcements configured** - Pot threshold and jackpot win alerts will {'be announced' if enabled else 'NOT be announced'}.",
        "error_configuring_announcements": "❌ Error configuring announcements.",
        "ranking_title": "🏆 **CUBILETE RANKING - {server}** 🏆",
        "history_title": "📜 **LAST CUBILETE GAMES** 📜",
        "game_title": "🎲 **Player {player}**",
        "game_dice": "🎲 Roll: {dice}",
        "game_combination": "→ {combination}",
        "game_prize": "💰 Prize: {prize:,} coins",
        "game_date": "📅 {date}",
        "ranking_position": "#{position} - **{player}**",
        "ranking_won": "💰 Won: {won:,}",
        "ranking_games": "🎲 Games: {games}",
        "ranking_balance_line": "📈 Balance: {balance} ({profitability:.1f}%)",
        "no_games_played": "🎲 **You haven't played yet** - Use `!canvas` → Trickster to start!",
        "help_title": "🎲 **CUBILETE - HELP** 🎲",
        "help_description": "Test your luck with the cubilete game! 🎲\n\n",
        "help_commands": "**Commands:**\n",
        "help_play": "• Use `!canvas` → Trickster → Play to roll the dice\n",
        "help_balance": "• Use `!canvas` → Trickster to view pot balance\n",
        "help_stats": "• Use `!canvas` → Trickster → Stats for your statistics\n",
        "help_ranking": "• Use `!canvas` → Trickster → Ranking for server ranking\n",
        "help_history": "• Use `!canvas` → Trickster → History for last games\n",
        "help_config": "• Use `!canvas` → Trickster → Admin to configure (Admins)\n",
        "help_announcements": "• Use `!canvas` → Trickster → Admin → Announcements to toggle alerts\n",
        "help_prizes": "**Prizes:**\n",
        "help_repoker": "• **Repóker (5 of a kind)** - Wins the entire pot! 🎰\n",
        "help_poker": "• **Póker (4 of a kind)** - 4x bet\n",
        "help_full": "• **Full (3+2)** - 3x bet\n",
        "help_trio": "• **Trío (3 of a kind)** - 1.5x bet\n",
        "help_doble_pareja": "• **Doble Pareja** - 1x bet\n",
        "help_pareja": "• **Pareja** - 0.5x bet\n",
        "help_additional_info": "**Additional Info:**\n",
        "help_partial_info": "• Minor prizes are paid by the bank\n",
        "help_pot_info": "• Repóker empties the entire accumulated pot!\n",
        "help_tae_info": "• The bet is 2x the TAE configured in the server\n"
    }


def get_message(key, server_id: str = None, **kwargs):
    """Get a custom message with variable formatting."""
    messages = get_cubilete_messages(server_id)
    message = messages.get(key)

    if message is None:
        # Use default messages if custom message not found
        default_messages = get_default_messages()
        message = default_messages.get(key, f"❌ Message not found: {key}")

    try:
        return message.format(**kwargs)
    except KeyError as e:
        logger.error(f"❌ Error formatting message '{key}': variable not found {e}")
        return message
    except Exception as e:
        logger.error(f"❌ Error formatting message '{key}': {e}")
        return message
