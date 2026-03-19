import os
import json
from agent_logging import get_logger

logger = get_logger('dice_game_messages')


def get_dice_game_messages():
    """Load custom Dice Game messages from personality file."""
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        config_path = os.path.join(project_root, "agent_config.json")
        with open(config_path, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        personality_rel = agent_cfg.get("personality", "")
        answers_path = os.path.join(project_root, os.path.dirname(personality_rel), "answers.json")
        with open(answers_path, encoding="utf-8") as f:
            answers_cfg = json.load(f).get("discord", {})

        dice_game_messages = answers_cfg.get("dice_game_messages", {})
        dice_game_balance_messages = answers_cfg.get("dice_game_balance_messages", {})
        dice_game_messages = {**dice_game_messages, **dice_game_balance_messages}

        if not dice_game_messages:
            logger.warning("⚠️ No custom dice game messages found in personality")
            return get_default_messages()

        logger.info("🎲 Custom dice game messages loaded from personality")
        return dice_game_messages

    except Exception as e:
        logger.error(f"❌ Error loading dice game messages: {e}")
        return get_default_messages()


def get_default_messages():
    """Default messages if no customization available."""
    return {
        "invitation": "🎲 **ROLL THE DICE!** 🎲 Bet gold to win the POT!",
        "winner": "🎉 **WINNER!** You won the pot!",
        "loser": "😅 No luck this time! 🎲",
        "big_pot": "🤑 **HUGE POT!** 🤑",
        "animation": "🎲🎲🎲 **ROLLING THE DICE!** 🎲🎲🎲",
        "insufficient_balance": "❌ Insufficient gold! You need {bet:,} gold to play. Your current balance: {balance:,} gold coins",
        "pot_won": "🎉🎉🎉 **JACKPOT WINNER!** 🎉🎉🎉 You won {prize:,} gold coins!",
        "prize_multiplier": "🎊 **WINNER!** {combination} - Prize: {prize:,} gold coins",
        "no_prize": "😅 {combination} - No prize. Better luck next time!",
        "error_jugada": "❌ Error processing roll: {error}",
        "roll_title": " **YOUR ROLL:**",
        "combination_title": "📊 **COMBINATION:**",
        "prize_title": "💰 **PRIZE:**",
        "current_pot_title": "💎 **CURRENT POT:**",
        "anuncio_bote_grande": "🤑 **MASSIVE POT ALERT!** 🤑 The pot is burning with **{balance:,} gold coins**! Use `!dice play` to win it! 🎲",
        "error_private_message": "❌ This command only works on servers, not in private messages.",
        "error_game_unavailable": "❌ The dice game is not available on this server.",
        "error_database_access": "❌ Error accessing game databases.",
        "error_processing_roll": "❌ Error processing the roll. Please try again.",
        "help_sent_private": "📩 Dice Game help sent by private message.",
        "error_system_unavailable": "❌ The dice game system is not available on this server.",
        "error_getting_balance": "❌ Error getting pot balance.",
        "private_message_sent": "📩 Pot balance sent by private message.",
        "stats_sent_private": "📩 Statistics sent by private message.",
        "error_getting_stats": "❌ Error getting your statistics.",
        "error_game_database_access": "❌ Error accessing dice game database.",
        "ranking_no_players": "📊 **DICE GAME RANKING** - No registered players yet.",
        "error_getting_ranking": "❌ Error getting ranking.",
        "history_no_games": "📜 **DICE GAME HISTORY** - No registered games yet.",
        "error_getting_history": "❌ Error getting history.",
        "error_servers_only": "❌ This command only works on servers.",
        "error_admin_only": "❌ Only administrators can configure the dice game.",
        "error_config_parameter": "❌ You must specify what to configure. Use `!dice config bet <amount>` or `!dice config announcements on/off`.",
        "error_specify_amount": "❌ You must specify the amount. Example: `!dice config bet 15`.",
        "error_bet_range": "❌ The bet must be between 1 and 1000 coins.",
        "fixed_bet_configured": "✅ **Fixed bet configured** - All games will now cost {amount:,} coins.",
        "error_configuring_bet": "❌ Error configuring fixed bet.",
        "error_announcement_value": "❌ Invalid value. Use 'on' or 'off' for announcements.",
        "announcements_configured": "✅ **Announcements configured** - Big wins will {'be announced' if enabled else 'NOT be announced'}.",
        "error_configuring_announcements": "❌ Error configuring announcements.",
        "ranking_title": "🏆 **DICE GAME RANKING - {server}** 🏆",
        "history_title": "📜 **LAST DICE GAMES** 📜",
        "game_title": "🎲 **Player {player}**",
        "game_dice": "🎲 Roll: {dice}",
        "game_combination": "→ {combination}",
        "game_prize": "💰 Prize: {prize:,} coins",
        "game_date": "📅 {date}",
        "ranking_position": "#{position} - **{player}**",
        "ranking_won": "💰 Won: {won:,}",
        "ranking_games": "🎲 Games: {games}",
        "ranking_balance_line": "📈 Balance: {balance} ({profitability:.1f}%)",
        "no_games_played": "🎲 **You haven't played yet** - Use `!dice play` to start!",
        "help_title": "🎲 **DICE GAME - HELP** 🎲",
        "help_description": "Test your luck with Kronk's dice game! 🎲\n\n",
        "help_commands": "**Commands:**\n",
        "help_play": "• `!dice play` - Roll the dice (costs fixed bet)\n",
        "help_balance": "• `!dice balance` - View current pot balance\n",
        "help_stats": "• `!dice stats` - Your personal statistics\n",
        "help_ranking": "• `!dice ranking` - Server player ranking\n",
        "help_history": "• `!dice history` - Last games played\n",
        "help_config": "• `!dice config bet <amount>` (Admins) - Set fixed bet\n",
        "help_announcements": "• `!dice config announcements on/off` (Admins) - Toggle big win announcements\n",
        "help_prizes": "**Prizes:**\n",
        "help_triple_ones": "• **1-1-1** - Wins the entire pot! 🎰\n",
        "help_three_of_a_kind": "• **Three of a kind** - 3x bet\n",
        "help_straight": "• **4-5-6** - 5x bet\n",
        "help_pair": "• **Pair** - 1x bet\n",
        "help_additional_info": "**Additional Info:**\n",
        "help_partial_info": "• Partial prizes are paid by the bank\n",
        "help_pot_info": "• 1-1-1 empties the entire accumulated pot!\n"
    }


def get_message(key, **kwargs):
    """Get a custom message with variable formatting."""
    messages = get_dice_game_messages()
    message = messages.get(key)

    if message is None:
        message = get_english_fallback(key)

    try:
        return message.format(**kwargs)
    except KeyError as e:
        logger.error(f"❌ Error formatting message '{key}': variable not found {e}")
        return message
    except Exception as e:
        logger.error(f"❌ Error formatting message '{key}': {e}")
        return message


def get_english_fallback(key):
    """Get English fallback message for when personality doesn't have custom message."""
    fallbacks = {
        "invitation": "🎲 **ROLL THE DICE!** 🎲 Bet gold to win the POT!",
        "winner": "🎉 **WINNER!** You won the pot!",
        "loser": "😅 No luck this time! 🎲",
        "big_pot": "🤑 **HUGE POT!** 🤑",
        "animation": "🎲🎲🎲 **ROLLING THE DICE!** 🎲🎲🎲",
        "insufficient_balance": "❌ Insufficient gold! You need {bet:,} gold to play. Your current balance: {balance:,} gold coins",
        "pot_won": "🎉🎉🎉 **JACKPOT WINNER!** 🎉🎉🎉 You won {prize:,} gold coins!",
        "prize_multiplier": "🎊 **WINNER!** {combination} - Prize: {prize:,} gold coins",
        "no_prize": "😅 {combination} - No prize. Better luck next time!",
        "error_jugada": "❌ Error processing roll: {error}",
        "roll_title": " **YOUR ROLL:**",
        "combination_title": "📊 **COMBINATION:**",
        "prize_title": "💰 **PRIZE:**",
        "current_pot_title": "💎 **CURRENT POT:**",
        "anuncio_bote_grande": "🤑 **MASSIVE POT ALERT!** 🤑 The pot is burning with **{balance:,} gold coins**! Use `!dice play` to win it! 🎲",
        "title": "💰 **THE POT - {server}** 💰\n",
        "current_balance": "🎲 **Gold accumulated:** {balance:,} coins!\n",
        "fixed_bet": "💎 **Price to roll:** {amount:,} coins!\n",
        "possible_plays": "🎯 **Remaining bets:** {plays}\n",
        "big_pot": "🔥 **THE POT IS OVERFLOWING WITH GOLD!** 🔥\nA good thief would steal these {balance:,} coins right now!\n",
        "medium_pot": "📈 **Medium pot** - Already worth the risk, human!\n",
        "small_pot": "📉 **Small pot** - Few dead today, keep growing!\n",
        "use_command": "\n💡 Use `!dice play` to roll the bones, human fool!",
        "sent_private": "📩 Pot balance sent by private message.",
        "error_private_message": "❌ This command only works on servers, not in private messages.",
        "error_game_unavailable": "❌ The dice game is not available on this server.",
        "error_database_access": "❌ Error accessing game databases.",
        "error_processing_roll": "❌ Error processing the roll. Please try again.",
        "help_sent_private": "📩 Dice Game help sent by private message.",
        "error_system_unavailable": "❌ The dice game system is not available on this server.",
        "error_getting_balance": "❌ Error getting pot balance.",
        "private_message_sent": "📩 Pot balance sent by private message.",
        "stats_sent_private": "📩 Statistics sent by private message.",
        "error_getting_stats": "❌ Error getting your statistics.",
        "error_game_database_access": "❌ Error accessing dice game database.",
        "ranking_no_players": "📊 **DICE GAME RANKING** - No registered players yet.",
        "error_getting_ranking": "❌ Error getting ranking.",
        "history_no_games": "📜 **DICE GAME HISTORY** - No registered games yet.",
        "error_getting_history": "❌ Error getting history.",
        "error_servers_only": "❌ This command only works on servers.",
        "error_admin_only": "❌ Only administrators can configure the dice game.",
        "error_config_parameter": "❌ You must specify what to configure. Use `!dice config bet <amount>` or `!dice config announcements on/off`.",
        "error_specify_amount": "❌ You must specify the amount. Example: `!dice config bet 15`.",
        "error_bet_range": "❌ The bet must be between 1 and 1000 coins.",
        "fixed_bet_configured": "✅ **Fixed bet configured** - All games will now cost {amount:,} coins.",
        "error_configuring_bet": "❌ Error configuring fixed bet.",
        "error_announcement_value": "❌ Invalid value. Use 'on' or 'off' for announcements.",
        "announcements_configured": "✅ **Announcements configured** - Big wins will {'be announced' if enabled else 'NOT be announced'}.",
        "error_configuring_announcements": "❌ Error configuring announcements.",
        "ranking_title": "🏆 **DICE GAME RANKING - {server}** 🏆",
        "history_title": "📜 **LAST DICE GAMES** 📜",
        "game_title": "🎲 **Player {player}**",
        "game_dice": "🎲 Roll: {dice}",
        "game_combination": "→ {combination}",
        "game_prize": "💰 Prize: {prize:,} coins",
        "game_date": "📅 {date}",
        "ranking_position": "#{position} - **{player}**",
        "ranking_won": "💰 Won: {won:,}",
        "ranking_games": "🎲 Games: {games}",
        "ranking_balance_line": "📈 Balance: {balance} ({profitability:.1f}%)",
        "no_games_played": "🎲 **You haven't played yet** - Use `!dice play` to start!",
        "help_title": "🎲 **DICE GAME - HELP** 🎲",
        "help_description": "Test your luck with Kronk's dice game! 🎲\n\n",
        "help_commands": "**Commands:**\n",
        "help_play": "• `!dice play` - Roll the dice (costs fixed bet)\n",
        "help_balance": "• `!dice balance` - View current pot balance\n",
        "help_stats": "• `!dice stats` - Your personal statistics\n",
        "help_ranking": "• `!dice ranking` - Server player ranking\n",
        "help_history": "• `!dice history` - Last games played\n",
        "help_config": "• `!dice config bet <amount>` (Admins) - Set fixed bet\n",
        "help_announcements": "• `!dice config announcements on/off` (Admins) - Toggle big win announcements\n",
        "help_prizes": "**Prizes:**\n",
        "help_triple_ones": "• **1-1-1** - Wins the entire pot! 🎰\n",
        "help_three_of_a_kind": "• **Three of a kind** - 3x bet\n",
        "help_straight": "• **4-5-6** - 5x bet\n",
        "help_pair": "• **Pair** - 1x bet\n",
        "help_additional_info": "**Additional Info:**\n",
        "help_partial_info": "• Partial prizes are paid by the bank\n",
        "help_pot_info": "• 1-1-1 empties the entire accumulated pot!\n"
    }

    return fallbacks.get(key, f"❌ Message not found: {key}")
