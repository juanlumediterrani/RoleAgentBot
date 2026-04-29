"""
Cubilete Game Logic Module
Handles the core cubilete (dice poker) mechanics and prize calculations.
"""

import random
from typing import Any, Dict, Tuple, Optional, List
from agent_logging import get_logger

try:
    from .cubilete_messages import get_message
except ImportError:
    # Fallback for direct loading - use absolute import
    import sys
    import os
    cubilete_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, cubilete_dir)
    try:
        from cubilete_messages import get_message
    finally:
        sys.path.remove(cubilete_dir)

logger = get_logger('cubilete')

# Dice value mapping (Cubilete uses specific values)
DICE_VALUES = {
    1: '⭐',  # As
    2: '👑',  # Rey
    3: '💍',  # Reina
    4: '🎭',  # Jota (máscara)
    5: '🔴',  # Roja
    6: '⚫'   # Negra
}

# Prize multipliers
PRIZE_TABLE = {
    'repoker': 'BOTE',  # Jackpot - entire pot
    'poker': 4,
    'full': 3,
    'trio': 1.5,
    'doble_pareja': 1,
    'pareja': 0.5,
    'nada': 0
}

# Pot multiplier for announcements
MEDIUM_HIGH_POT_MULTIPLIER = 72


class CubileteGame:
    """Core cubilete game logic."""
    
    def __init__(self, bet_multiplier_tae: int = 2):
        """Initialize cubilete game with bet multiplier."""
        self.bet_multiplier_tae = bet_multiplier_tae
        self.fixed_bet = None  # Will be calculated based on TAE
    
    def roll_dice(self, count: int = 5) -> List[int]:
        """Roll specified number of dice (default 5)."""
        return [random.randint(1, 6) for _ in range(count)]
    
    def dice_to_emoji(self, die_value: int) -> str:
        """Convert die value to emoji representation."""
        return f"🎲{DICE_VALUES.get(die_value, die_value)}"
    
    def dice_to_display(self, dice: List[int]) -> str:
        """Convert dice list to display string with emojis."""
        return " ".join([self.dice_to_emoji(d) for d in dice])
    
    def analyze_combination(self, dice: List[int], server_id: str = None) -> Tuple[str, str, float]:
        """Analyze dice combination and return type, description, and multiplier."""
        # Count occurrences of each value
        counts = {}
        for d in dice:
            counts[d] = counts.get(d, 0) + 1
        
        count_values = sorted(counts.values(), reverse=True)
        
        # Get combination descriptions
        repoker_msg = get_message("repoker", server_id=server_id)
        poker_msg = get_message("poker", server_id=server_id)
        full_msg = get_message("full", server_id=server_id)
        trio_msg = get_message("trio", server_id=server_id)
        doble_pareja_msg = get_message("doble_pareja", server_id=server_id)
        pareja_msg = get_message("pareja", server_id=server_id)
        nada_msg = get_message("nada", server_id=server_id)
        
        # Check combinations
        if count_values[0] == 5:
            # Repóker (5 of a kind)
            return 'repoker', repoker_msg, PRIZE_TABLE['repoker']
        elif count_values[0] == 4:
            # Póker (4 of a kind)
            return 'poker', poker_msg, PRIZE_TABLE['poker']
        elif count_values[0] == 3 and count_values[1] == 2:
            # Full (3 + 2)
            return 'full', full_msg, PRIZE_TABLE['full']
        elif count_values[0] == 3:
            # Trío (3 of a kind)
            return 'trio', trio_msg, PRIZE_TABLE['trio']
        elif count_values[0] == 2 and count_values[1] == 2:
            # Doble Pareja (2 + 2)
            return 'doble_pareja', doble_pareja_msg, PRIZE_TABLE['doble_pareja']
        elif count_values[0] == 2:
            # Pareja (pair)
            return 'pareja', pareja_msg, PRIZE_TABLE['pareja']
        else:
            # Nada (no combination)
            return 'nada', nada_msg, PRIZE_TABLE['nada']
    
    def calculate_prize(self, combination_type: str, pot_balance: int, bet: int) -> int:
        """Calculate prize based on combination and current pot."""
        multiplier = PRIZE_TABLE[combination_type]
        
        if multiplier == 'BOTE':
            # Jackpot - entire pot
            return pot_balance
        else:
            # Calculate prize from bet * multiplier
            return int(bet * multiplier)
    
    def play_game(self, player_id: str, player_name: str, server_id: str, 
                  pot_balance: int, bet: int) -> Dict[str, any]:
        """Play a complete cubilete game round (single roll version)."""
        try:
            # Roll 5 dice
            dice = self.roll_dice(5)
            dice_display = self.dice_to_display(dice)
            
            # Analyze combination
            combination_type, combination_desc, multiplier = self.analyze_combination(dice, server_id)
            
            # Calculate prize
            prize = self.calculate_prize(combination_type, pot_balance, bet)
            
            # Calculate new pot balance
            if combination_type == 'repoker':
                # Jackpot - player gets entire pot, pot becomes 0
                new_pot_balance = 0
            else:
                # Add bet to pot, then subtract prize if any
                new_pot_balance = pot_balance + bet - prize
            
            # Prepare result
            result = {
                'success': True,
                'dice': dice_display,
                'dice_values': dice,
                'combination': combination_desc,
                'combination_type': combination_type,
                'prize': prize,
                'bet': bet,
                'pot_before': pot_balance,
                'pot_after': new_pot_balance,
                'jackpot': combination_type == 'repoker',
                'message': self._format_result_message(dice_display, combination_desc, prize, new_pot_balance, server_id)
            }
            
            logger.info(f"🎲 {player_name} rolled {dice_display} → {combination_desc} - Prize: {prize}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error playing cubilete game: {e}")
            return {
                'success': False,
                'message': f"Error while playing cubilete: {str(e)}"
            }
    
    def _format_result_message(self, dice: str, combination: str, prize: int, new_pot: int, server_id: str = None) -> str:
        """Format the result message for display."""
        # Build the complete message with all sections
        message = f"{get_message('roll_title', server_id=server_id)}\n{dice}\n"
        message += f"{get_message('combination_title', server_id=server_id)} {combination}\n"
        message += f"{get_message('prize_title', server_id=server_id)} "
        
        if prize == 0:
            message += get_message("no_prize", combination=dice, server_id=server_id)
        elif "JACKPOT" in combination or "REPÓKER" in combination:
            message += get_message("pot_won", prize=prize, server_id=server_id)
        else:
            message += get_message("prize_multiplier", combination=combination, prize=prize, server_id=server_id)
        
        message += f"\n{get_message('pot_title', server_id=server_id)} {new_pot:,} coins"
        
        # Add winner/loser summary message
        if prize > 0:
            message += f"\n\n{get_message('winner', server_id=server_id)}"
        else:
            message += f"\n\n{get_message('loser', server_id=server_id)}"
        
        return message


# Global game instance
_game_instance = None

def get_cubilete_game_instance(bet_multiplier_tae: int = 2) -> CubileteGame:
    """Get or create cubilete game instance."""
    global _game_instance
    if _game_instance is None or _game_instance.bet_multiplier_tae != bet_multiplier_tae:
        _game_instance = CubileteGame(bet_multiplier_tae)
    return _game_instance


def process_play(player_id: str, player_name: str, server_display_name: str, current_pot: int, server_id: str = None) -> Dict[str, Any]:
    """Process a cubilete play request."""
    try:
        # server_id is always passed from Discord context (ctx.guild.id)
        if server_id is None:
            from agent_db import get_server_id
            server_id = get_server_id()
            logger.warning(f"process_play called without server_id, using active server: {server_id}")

        # Get TAE from banker to calculate bet
        try:
            from roles.banker.banker_db import get_banker_roles_db_instance
            banker_db = get_banker_roles_db_instance(server_id)
            tae = banker_db.get_tae(server_id)
        except Exception as e:
            logger.warning(f"Error getting TAE from banker: {e}")
            tae = 1
        
        # Get cubilete config
        try:
            from discord_bot.canvas.server_config import get_role_config_value
            config = get_role_config_value(server_id, "cubilete", "config", default={})
            bet_multiplier = config.get('bet_multiplier_tae', 2)
            announcements_active = config.get('announcements_active', True)
            logger.info(f"🔧 Cubilete Config - Server: {server_id}, Bet Multiplier: {bet_multiplier}x TAE, Announcements: {announcements_active}")
        except Exception as e:
            logger.warning(f"Error getting cubilete config from server_config: {e}")
            bet_multiplier = 2
            announcements_active = True
        
        # Calculate bet
        bet = tae * bet_multiplier
        logger.info(f"💰 Calculated bet: {bet} (TAE: {tae} × Multiplier: {bet_multiplier})")
        
        # Get current pot balance from banker database for consistency
        actual_current_pot = current_pot
        try:
            from roles.banker.banker_db import get_banker_roles_db_instance
            banker_roles_db = get_banker_roles_db_instance(server_id)
            banker_roles_db.create_wallet("cubilete_pot", "Cubilete Pot", 'system')
            actual_current_pot = banker_roles_db.get_balance("cubilete_pot")
        except Exception:
            pass
        
        # Play the game with actual pot balance
        game = get_cubilete_game_instance(bet_multiplier)
        result = game.play_game(player_id, player_name, server_id, actual_current_pot, bet)
        result['announcements'] = []
        
        # Integrate with banker system for gold transactions
        banker_message = ""
        
        if result['success']:
            try:
                from roles.banker.banker_db import get_banker_roles_db_instance
                banker_roles_db = get_banker_roles_db_instance(server_id)
                banker_roles_db.create_wallet("cubilete_pot", "Cubilete Pot", 'system')
                banker_roles_db.create_wallet(player_id, player_name, 'user')
                
                # Use the actual_current_pot we already obtained
                result['pot_before'] = actual_current_pot
                prize = result.get('prize', 0)
                
                if prize > 0 and actual_current_pot < prize:
                    result['success'] = False
                    result['message'] = "❌ The pot does not have enough gold to pay that prize."
                    return result
                
                result['pot_after'] = 0 if result.get('jackpot') else (actual_current_pot + bet - prize)
                result['message'] = game._format_result_message(result['dice'], result['combination'], prize, result['pot_after'], server_id)

                # Deduct the bet amount from player's wallet
                bet_deducted = banker_roles_db.update_balance(
                    player_id, player_name,
                    -bet, "cubilete_bet", 
                    f"Cubilete bet: {result['dice']}", 
                    "cubilete", "Cubilete System"
                )
                
                if not bet_deducted:
                    banker_message = "❌ Not enough gold to place the bet."
                    result['success'] = False
                    result['message'] = banker_message
                else:
                    # If player won, add the prize to their wallet
                    if result['prize'] > 0:
                        prize_added = banker_roles_db.update_balance(
                            player_id, player_name,
                            result['prize'], "cubilete_win", 
                            f"Cubilete winnings: {result['combination']}", 
                            "cubilete", "Cubilete System"
                        )
                        
                        if not prize_added:
                            banker_message = "⚠️ You won, but the prize could not be added to the wallet."
                            result['success'] = False
                            result['message'] = banker_message
                        else:
                            banker_message = "💰 Gold transactions completed."
                    else:
                        banker_message = "💰 Gold transactions completed."

                    if result['success']:
                        pot_delta = result['pot_after'] - result['pot_before']
                        pot_updated = banker_roles_db.update_balance(
                            "cubilete_pot", "Cubilete Pot",
                            pot_delta, "cubilete_pot_update",
                            f"Cubilete pot update: {result['dice']}",
                            "cubilete", "Cubilete System"
                        )
                        if not pot_updated:
                            banker_message = "⚠️ The pot could not be updated."
                            result['success'] = False
                            result['message'] = banker_message
                        elif result.get('jackpot'):
                            # Jackpot won - refill pot with banker bonus (15x TAE)
                            try:
                                pot_refill_multiplier = config.get('pot_refill_multiplier', 15)
                                opening_bonus = tae * pot_refill_multiplier
                            except:
                                opening_bonus = tae * 15
                            
                            if opening_bonus > 0:
                                refill_result = banker_roles_db.update_balance(
                                    "cubilete_pot", "Cubilete Pot",
                                    opening_bonus, "cubilete_pot_refill",
                                    f"Jackpot refill with opening bonus ({pot_refill_multiplier}x TAE)",
                                    "cubilete", "Cubilete System"
                                )
                                if refill_result:
                                    result['pot_after'] = opening_bonus
                                    banker_message += f"\n🎉 Jackpot won! Pot refilled with {opening_bonus:,} gold from banker bonus ({pot_refill_multiplier}x TAE)."
                                else:
                                    banker_message += "\n⚠️ Jackpot won but pot refill failed."
                            else:
                                banker_message += "\n🎉 Jackpot won! No banker bonus configured for refill."
            except Exception as e:
                # If banker integration fails, still allow the game but warn
                banker_message = f"⚠️ Banker integration failed: {str(e)}"
        
        if result['success']:
            # Update player statistics
            try:
                from agent_roles_db import get_roles_db_instance
                roles_db = get_roles_db_instance(server_id)
                if roles_db:
                    # Get current stats
                    current_stats = roles_db.get_cubilete_stats(player_id)
                    
                    # Calculate new stats
                    new_total_plays = current_stats.get('total_plays', 0) + 1
                    new_total_bet = current_stats.get('total_bet', 0) + result['bet']
                    new_total_won = current_stats.get('total_won', 0) + result['prize']
                    new_pots_won = current_stats.get('pots_won', 0) + (1 if result.get('jackpot') else 0)
                    new_biggest_prize = max(current_stats.get('biggest_prize', 0), result['prize'])
                    last_play_info = f"{result['dice']} → {result['combination']} | {'💰' if result['prize'] > 0 else '💸'} {result['prize']}"
                    
                    # Update stats
                    stats_updated = roles_db.save_cubilete_stats(
                        player_id, 
                        new_total_plays,
                        new_total_bet, 
                        new_total_won, 
                        new_pots_won, 
                        new_biggest_prize, 
                        last_play_info
                    )
                    
                    if stats_updated:
                        logger.info(f"📊 Updated cubilete stats for {player_name}: plays={new_total_plays}, won={new_total_won}, biggest={new_biggest_prize}")
                    else:
                        logger.warning(f"⚠️ Failed to update cubilete stats for {player_name}")
                else:
                    logger.warning("⚠️ Could not update cubilete stats - no database connection")
            except Exception as e:
                logger.error(f"❌ Failed to update cubilete stats: {e}")
            
            # Save the game to database
            try:
                from agent_roles_db import get_roles_db_instance
                roles_db = get_roles_db_instance(server_id)
                if roles_db:
                    play_id = roles_db.save_cubilete_play(
                        player_id, player_name,
                        result['bet'], result['dice'], result['combination'], 
                        result['prize'], result['pot_before'], result['pot_after']
                    )
                    logger.info(f"💾 Saved cubilete play {play_id} to database")
                else:
                    logger.warning("⚠️ Could not save cubilete play - no database connection")
            except Exception as e:
                logger.error(f"❌ Failed to save cubilete play: {e}")
            
            # Check for announcements
            if announcements_active:
                logger.info(f"📢 Announcements are ACTIVE, checking thresholds...")
                announcement_messages = []
                threshold_balance = bet * MEDIUM_HIGH_POT_MULTIPLIER
                logger.info(f"📢 Threshold: {threshold_balance} (bet: {bet} × {MEDIUM_HIGH_POT_MULTIPLIER})")

                if result.get('jackpot'):
                    logger.info(f"🎰 Jackpot detected!")
                    announcement_messages.append(
                        get_message(
                            'jackpot_won_announcement',
                            player=player_name,
                            prize=result['prize'],
                            server=server_display_name,
                        )
                    )

                logger.info(f"📢 Checking pot crossing: {result['pot_before']} < {threshold_balance} <= {result['pot_after']} = {result['pot_before'] < threshold_balance <= result['pot_after']}")
                if not result.get('jackpot') and result['pot_before'] < threshold_balance <= result['pot_after']:
                    logger.info(f"🔥 Big pot threshold crossed! {result['pot_before']} → {result['pot_after']} (threshold: {threshold_balance})")
                    announcement_messages.append(
                        get_message(
                            'big_pot_announcement',
                            balance=result['pot_after']
                        )
                    )
                    logger.info(f"🔥 Big pot announcement added: {len(announcement_messages)} announcements")
                else:
                    logger.info(f"📢 No threshold crossed, no announcement needed")
            else:
                logger.warning(f"📢 Announcements are DISABLED in config")
                announcement_messages = []

            result['announcements'] = announcement_messages
            logger.info(f"📢 Final announcements count: {len(announcement_messages)}")

            if banker_message:
                result['message'] += f"\n{banker_message}"
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Error processing cubilete play request: {e}")
        return {
            'success': False,
            'message': f"Error processing cubilete: {str(e)}"
        }


async def cubilete_task():
    """Execute cubilete task - periodic maintenance and announcements."""
    logger.info("🎲 Starting cubilete task...")
    
    try:
        # This would handle periodic cubilete maintenance
        # For now, just log that the task ran
        logger.info("🎲 Cubilete task completed - the game is ready for players")
        
    except Exception as e:
        logger.error(f"🎲 Error in cubilete task: {e}")
