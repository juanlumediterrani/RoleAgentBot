import os
import json
from agent_logging import get_logger

logger = get_logger('dice_game_messages')


def get_dice_game_messages(server_id: str = None):
    """Load custom Dice Game messages from descriptions.json."""
    combined_messages = {}
    
    try:
        from agent_runtime import get_personality_directory
        
        # Load from descriptions.json
        try:
            personality_dir = get_personality_directory()
            # First try to load from the new separate trickster.json file
            trickster_path = os.path.join(get_personality_directory(server_id), "descriptions", "trickster.json")
            if os.path.exists(trickster_path):
                with open(trickster_path, encoding="utf-8") as f:
                    trickster_data = json.load(f)
                desc_dice_messages = trickster_data.get("dice_game", {})
                logger.info("🎲 Loaded dice game messages from trickster.json")
            else:
                # Fallback to old descriptions.json structure
                descriptions_path = get_personality_file_path("descriptions.json", server_id)
                with open(descriptions_path, encoding="utf-8") as f:
                    descriptions_cfg = json.load(f).get("discord", {})
                
                # Navigate to the correct path: discord.roles_view_messages.trickster.dice_game
                roles_view = descriptions_cfg.get("roles_view_messages", {})
                trickster = roles_view.get("trickster", {})
                desc_dice_messages = trickster.get("dice_game", {})
                logger.info("🎲 Loaded dice game messages from descriptions.json (fallback)")
            
            combined_messages.update(desc_dice_messages)
        except Exception as e:
            logger.warning(f"⚠️ Could not load dice game messages from descriptions: {e}")

        if not combined_messages:
            logger.warning("⚠️ No custom dice game messages found in either file")
            return get_default_messages()
        else:
            logger.info(f"🎲 Combined dice game messages loaded: {len(combined_messages)} messages")
            return combined_messages

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
        # Dice combination fallback messages in English
        "triple_ones": "🎰 (JACKPOT!)",
        "three_of_a_kind": "(Three of a Kind)",
        "straight": "(Straight)",
        "pair": "(Pair)",
        "nothing": "(No Prize)",
        "big_pot_announcement": "🔥 **POT ALERT** 🔥 The pot has reached **{balance:,} gold coins** ({threshold:,} = 72x the current bet of {bet:,}). Use `!canvas` → Trickster to try to win it!",
        "jackpot_won_announcement": "� **JACKPOT WON** 🎉 **{player}** has taken the full pot and won **{prize:,} gold coins** in **{server}**!",
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
        "error_config_parameter": "❌ You must specify what to configure. Use `!canvas` → Trickster → Admin to configure.",
        "error_specify_amount": "❌ You must specify the amount. Use `!canvas` → Trickster → Admin to configure.",
        "error_bet_range": "❌ The bet must be between 1 and 1000 coins.",
        "fixed_bet_configured": "✅ **Fixed bet configured** - All games will now cost {amount:,} coins.",
        "error_configuring_bet": "❌ Error configuring fixed bet.",
        "error_announcement_value": "❌ Invalid value. Use 'on' or 'off' for announcements.",
        "announcements_configured": "✅ **Announcements configured** - Pot threshold and jackpot win alerts will {'be announced' if enabled else 'NOT be announced'}.",
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
        "no_games_played": "🎲 **You haven't played yet** - Use `!canvas` → Trickster to start!",
        "help_title": "🎲 **DICE GAME - HELP** 🎲",
        "help_description": "Test your luck with Kronk's dice game! 🎲\n\n",
        "help_commands": "**Commands:**\n",
        "help_play": "• Use `!canvas` → Trickster → Play to roll the dice\n",
        "help_balance": "• Use `!canvas` → Trickster to view pot balance\n",
        "help_stats": "• Use `!canvas` → Trickster → Stats for your statistics\n",
        "help_ranking": "• Use `!canvas` → Trickster → Ranking for server ranking\n",
        "help_history": "• Use `!canvas` → Trickster → History for last games\n",
        "help_config": "• Use `!canvas` → Trickster → Admin to configure (Admins)\n",
        "help_announcements": "• Use `!canvas` → Trickster → Admin → Announcements to toggle alerts\n",
        "help_prizes": "**Prizes:**\n",
        "help_triple_ones": "• **1-1-1** - Wins the entire pot! 🎰\n",
        "help_three_of_a_kind": "• **Three of a kind** - 3x bet\n",
        "help_straight": "• **4-5-6** - 5x bet\n",
        "help_pair": "• **Pair** - 1x bet\n",
        "help_additional_info": "**Additional Info:**\n",
        "help_partial_info": "• Partial prizes are paid by the bank\n",
        "help_pot_info": "• 1-1-1 empties the entire accumulated pot!\n"
    }


def get_message(key, server_id: str = None, **kwargs):
    """Get a custom message with variable formatting."""
    messages = get_dice_game_messages(server_id)
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
