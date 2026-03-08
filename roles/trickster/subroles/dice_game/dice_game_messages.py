import os
import json
from agent_logging import get_logger

logger = get_logger('dice_game_messages')

def get_dice_game_messages():
    """Load custom Dice Game messages from personality file."""
    try:
        # Use the centralized personality loading function
        from agent_engine import PERSONALIDAD
        
        # Get specific dice game messages (dice_game_messages for dice game)
        dice_game_messages = PERSONALIDAD.get("discord", {}).get("dice_game_messages", {})
        dice_game_balance_messages = PERSONALIDAD.get("discord", {}).get("dice_game_balance_messages", {})
        dice_game_combinations = PERSONALIDAD.get("discord", {}).get("dice_game_combinations", {})
        
        # Merge dice_game_messages and dice_game_balance_messages
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
        "sin_premio": "😅 {combination} - No prize. Better luck next time!",
        "error_jugada": "❌ Error processing roll: {error}",
        "roll_title": " **YOUR ROLL:**",
        "combination_title": "📊 **COMBINATION:**",
        "prize_title": "💰 **PRIZE:**",
        "current_pot_title": "💎 **CURRENT POT:**",
        "anuncio_bote_grande": "🤑 **MASSIVE POT ALERT!** 🤑 The pot is burning with **{balance:,} gold coins**! Use `!dice play` to win it! 🎲",
        "error_servidor_privado": "❌ This command only works on servers, not in private messages.",
        "error_juego_no_disponible": "❌ The dice game is not available on this server.",
        "error_acceso_bd": "❌ Error accessing game databases.",
        "error_procesar_tirada": "❌ Error processing the roll. Please try again.",
        "help_sent_private": "📩 Dice Game help sent by private message.",
        "error_sistema_no_disponible": "❌ The dice game system is not available on this server.",
        "error_obtener_saldo": "❌ Error getting pot balance.",
        "enviado_privado": "📩 Pot balance sent by private message.",
        "estadisticas_enviadas_privado": "📩 Statistics sent by private message.",
        "error_obtener_estadisticas": "❌ Error getting your statistics.",
        "error_acceso_bd_juego": "❌ Error accessing dice game database.",
        "ranking_sin_jugadores": "📊 **DICE GAME RANKING** - No registered players yet.",
        "error_obtener_ranking": "❌ Error getting ranking.",
        "historial_sin_partidas": "📜 **DICE GAME HISTORY** - No registered games yet.",
        "error_obtener_historial": "❌ Error getting history.",
        "error_solo_servidores": "❌ This command only works on servers.",
        "error_permisos_admin": "❌ Only administrators can configure the dice game.",
        "error_configurar_parametro": "❌ You must specify what to configure. Use `!dice config bet <amount>` or `!dice config announcements on/off`.",
        "error_especificar_cantidad": "❌ You must specify the amount. Example: `!dice config bet 15`.",
        "error_rango_apuesta": "❌ The bet must be between 1 and 1000 coins.",
        "apuesta_fija_configurada": "✅ **Fixed bet configured** - All games will now cost {amount:,} coins.",
        "error_configurar_apuesta": "❌ Error configuring fixed bet.",
        "error_valor_anuncios": "❌ Invalid value. Use 'on' or 'off' for announcements.",
        "anuncios_configurados": "✅ **Announcements configured** - Big wins will {'be announced' if enabled else 'NOT be announced'}.",
        "error_configurar_anuncios": "❌ Error configuring announcements.",
        "titulo_ranking": "🏆 **DICE GAME RANKING - {server}** 🏆",
        "titulo_historial": "📜 **LAST DICE GAMES** 📜",
        "jugada_titulo": "🎲 **Player {player}**",
        "jugada_dados": "🎲 Roll: {dice}",
        "jugada_combinacion": "→ {combination}",
        "jugada_premio": "💰 Prize: {prize:,} coins",
        "jugada_fecha": "📅 {date}",
        "ranking_posicion": "#{position} - **{player}**",
        "ranking_ganado": "💰 Won: {won:,}",
        "ranking_jugadas": "🎲 Games: {games}",
        "ranking_balance": "📈 Balance: {balance} ({profitability:.1f}%)",
        "ranking_sin_jugadas": "🎲 **You haven't played yet** - Use `!dice play` to start!",
        "help_titulo": "🎲 **DICE GAME - HELP** 🎲",
        "help_descripcion": "Test your luck with Kronk's dice game! 🎲\n\n",
        "help_comandos": "**Commands:**\n",
        "help_jugar": "• `!dice play` - Roll the dice (costs fixed bet)\n",
        "help_saldo": "• `!dice balance` - View current pot balance\n",
        "help_estadisticas": "• `!dice stats` - Your personal statistics\n",
        "help_ranking": "• `!dice ranking` - Server player ranking\n",
        "help_historial": "• `!dice history` - Last games played\n",
        "help_config": "• `!dice config bet <amount>` (Admins) - Set fixed bet\n",
        "help_anuncios": "• `!dice config announcements on/off` (Admins) - Toggle big win announcements\n",
        "help_premios": "**Prizes:**\n",
        "help_triple_ones": "• **1-1-1** - Wins the entire pot! 🎰\n",
        "help_three_of_a_kind": "• **Three of a kind** - 3x bet\n",
        "help_straight": "• **4-5-6** - 5x bet\n",
        "help_par": "• **Pair** - 2x bet\n",
        "help_info_adicional": "**Additional Info:**\n",
        "help_info_parcial": "• Partial prizes are paid by the bank\n",
        "help_info_bote": "• 1-1-1 empties the entire accumulated pot!\n"
    }

def get_message(key, **kwargs):
    """Get a custom message with variable formatting."""
    messages = get_dice_game_messages()
    message = messages.get(key)
    
    # If personality doesn't have the message, use English fallback
    if message is None:
        message = get_english_fallback(key)
    
    # Replace variables in message
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
        "sin_premio": "😅 {combination} - No prize. Better luck next time!",
        "error_jugada": "❌ Error processing roll: {error}",
        "roll_title": "🎲 **YOUR ROLL:**",
        "combination_title": "📊 **COMBINATION:**",
        "prize_title": "💰 **PRIZE:**",
        "current_pot_title": "💎 **CURRENT POT:**",
        "anuncio_bote_grande": "🤑 **MASSIVE POT ALERT!** 🤑 The pot is burning with **{balance:,} gold coins**! Use `!dice play` to win it! 🎲",
        # Balance messages
        "title": "💰 **THE POT - {servidor}** 💰\n",
        "current_balance": "🎲 **Gold accumulated:** {saldo:,} coins!\n",
        "fixed_bet": "💎 **Price to roll:** {apuesta:,} coins!\n",
        "possible_plays": "🎯 **Remaining bets:** {jugadas}\n",
        "big_pot": "🔥 **THE POT IS OVERFLOWING WITH GOLD!** 🔥\nA good thief would steal these {saldo:,} coins right now!\n",
        "medium_pot": "📈 **Medium pot** - Already worth the risk, human!\n",
        "small_pot": "📉 **Small pot** - Few dead today, keep growing!\n",
        "use_command": "\n💡 Use `!dice play` to roll the bones, human fool!",
        "sent_private": "📩 Pot balance sent by private message.",
        "error_servidor_privado": "❌ This command only works on servers, not in private messages.",
        "error_juego_no_disponible": "❌ The dice game is not available on this server.",
        "error_acceso_bd": "❌ Error accessing game databases.",
        "error_procesar_tirada": "❌ Error processing the roll. Please try again.",
        "help_sent_private": "📩 Dice Game help sent by private message.",
        "error_sistema_no_disponible": "❌ The dice game system is not available on this server.",
        "error_obtener_saldo": "❌ Error getting pot balance.",
        "enviado_privado": "📩 Pot balance sent by private message.",
        "estadisticas_enviadas_privado": "📩 Statistics sent by private message.",
        "error_obtener_estadisticas": "❌ Error getting your statistics.",
        "error_acceso_bd_juego": "❌ Error accessing dice game database.",
        "ranking_sin_jugadores": "📊 **DICE GAME RANKING** - No registered players yet.",
        "error_obtener_ranking": "❌ Error getting ranking.",
        "historial_sin_partidas": "📜 **DICE GAME HISTORY** - No registered games yet.",
        "error_obtener_historial": "❌ Error getting history.",
        "error_solo_servidores": "❌ This command only works on servers.",
        "error_permisos_admin": "❌ Only administrators can configure the dice game.",
        "error_configurar_parametro": "❌ You must specify what to configure. Use `!dice config bet <amount>` or `!dice config announcements on/off`.",
        "error_especificar_cantidad": "❌ You must specify the amount. Example: `!dice config bet 15`.",
        "error_rango_apuesta": "❌ The bet must be between 1 and 1000 coins.",
        "apuesta_fija_configurada": "✅ **Fixed bet configured** - All games will now cost {amount:,} coins.",
        "error_configurar_apuesta": "❌ Error configuring fixed bet.",
        "error_valor_anuncios": "❌ Invalid value. Use 'on' or 'off' for announcements.",
        "anuncios_configurados": "✅ **Announcements configured** - Big wins will {'be announced' if enabled else 'NOT be announced'}.",
        "error_configurar_anuncios": "❌ Error configuring announcements.",
        "titulo_ranking": "🏆 **DICE GAME RANKING - {server}** 🏆",
        "titulo_historial": "📜 **LAST DICE GAMES** 📜",
        "jugada_titulo": "🎲 **Player {player}**",
        "jugada_dados": "🎲 Roll: {dice}",
        "jugada_combinacion": "→ {combination}",
        "jugada_premio": "💰 Prize: {prize:,} coins",
        "jugada_fecha": "📅 {date}",
        "ranking_posicion": "#{position} - **{player}**",
        "ranking_ganado": "💰 Won: {won:,}",
        "ranking_jugadas": "🎲 Games: {games}",
        "ranking_balance": "📈 Balance: {balance} ({profitability:.1f}%)",
        "ranking_sin_jugadas": "🎲 **You haven't played yet** - Use `!dice play` to start!",
        "help_titulo": "🎲 **DICE GAME - HELP** 🎲",
        "help_descripcion": "Test your luck with Kronk's dice game! 🎲\n\n",
        "help_comandos": "**Commands:**\n",
        "help_jugar": "• `!dice play` - Roll the dice (costs fixed bet)\n",
        "help_saldo": "• `!dice balance` - View current pot balance\n",
        "help_estadisticas": "• `!dice stats` - Your personal statistics\n",
        "help_ranking": "• `!dice ranking` - Server player ranking\n",
        "help_historial": "• `!dice history` - Last games played\n",
        "help_config": "• `!dice config bet <amount>` (Admins) - Set fixed bet\n",
        "help_anuncios": "• `!dice config announcements on/off` (Admins) - Toggle big win announcements\n",
        "help_premios": "**Prizes:**\n",
        "help_triple_ones": "• **1-1-1** - Wins the entire pot! 🎰\n",
        "help_three_of_a_kind": "• **Three of a kind** - 3x bet\n",
        "help_straight": "• **4-5-6** - 5x bet\n",
        "help_par": "• **Pair** - 2x bet\n",
        "help_info_adicional": "**Additional Info:**\n",
        "help_info_parcial": "• Partial prizes are paid by the bank\n",
        "help_info_bote": "• 1-1-1 empties the entire accumulated pot!\n"
    }
    
    return fallbacks.get(key, f"❌ Message not found: {key}")
