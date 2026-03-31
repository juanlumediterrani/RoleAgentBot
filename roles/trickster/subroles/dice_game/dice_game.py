"""
Dice Game Logic Module
Handles the core dice game mechanics and prize calculations.
"""

import random
from typing import Any, Dict, Tuple, Optional
from agent_logging import get_logger

try:
    from .dice_game_messages import get_message
except ImportError:
    # Fallback for direct loading - use absolute import
    import sys
    import os
    dice_game_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, dice_game_dir)
    try:
        from dice_game_messages import get_message
    finally:
        sys.path.remove(dice_game_dir)

# Import personality descriptions for dice game combinations
# Note: We now use the local dice_game_messages system instead of direct imports

logger = get_logger('dice_game')

MEDIUM_HIGH_POT_MULTIPLIER = 72


class DiceGame:
    """Core dice game logic."""
    
    # Prize multipliers
    PRIZE_TABLE = {
        'triple_one': 0,  # Special case - takes entire pot
        'any_triple': 3,
        'straight_456': 5,
        'pair': 1,  # Returns bet
        'nothing': 0
    }
    
    def __init__(self, fixed_bet: int = 1):
        """Initialize dice game with fixed bet amount."""
        self.fixed_bet = fixed_bet
    
    def roll_dice(self) -> Tuple[int, int, int]:
        """Roll three dice."""
        return (random.randint(1, 6), random.randint(1, 6), random.randint(1, 6))
    
    def analyze_roll(self, dice: Tuple[int, int, int]) -> Tuple[str, str, int]:
        """Analyze dice roll and return combination type, description, and prize multiplier."""
        sorted_dice = sorted(dice)
        dice_str = '-'.join(map(str, dice))
        
        # Get combination descriptions from the message system
        triple_ones = get_message("triple_ones")
        triple = get_message("three_of_a_kind")
        straight = get_message("straight")
        pair = get_message("pair")
        nothing = get_message("nothing")

        # Check for triple ones (jackpot)
        if dice == (1, 1, 1):
            return 'triple_one', triple_ones, 0
        
        # Check for any triple
        if dice[0] == dice[1] == dice[2]:
            return 'any_triple', f'{dice_str} {triple}', self.PRIZE_TABLE['any_triple']
        
        # Check for straight 4-5-6
        if sorted_dice == [4, 5, 6]:
            return 'straight_456', straight, self.PRIZE_TABLE['straight_456']
        
        # Check for any pair
        if len(set(dice)) == 2:
            return 'pair', f'{dice_str} {pair}', self.PRIZE_TABLE['pair']
        
        # No prize
        return 'nothing', f'{dice_str} {nothing}', self.PRIZE_TABLE['nothing']
    
    def calculate_prize(self, combination_type: str, pot_balance: int) -> int:
        """Calculate prize based on combination and current pot."""
        if combination_type == 'triple_one':
            # Jackpot - entire pot
            return pot_balance
        elif combination_type == 'any_triple':
            return self.fixed_bet * self.PRIZE_TABLE['any_triple']
        elif combination_type == 'straight_456':
            return self.fixed_bet * self.PRIZE_TABLE['straight_456']
        elif combination_type == 'pair':
            return self.fixed_bet * self.PRIZE_TABLE['pair']
        else:
            return 0
    
    def play_game(self, player_id: str, player_name: str, server_id: str, 
                  server_name: str, pot_balance: int) -> Dict[str, any]:
        """Play a complete dice game round."""
        try:
            # Roll dice
            dice = self.roll_dice()
            dice_str = '-'.join(map(str, dice))
            
            # Analyze roll
            combination_type, combination_desc, multiplier = self.analyze_roll(dice)
            
            # Calculate prize
            prize = self.calculate_prize(combination_type, pot_balance)
            
            # Calculate new pot balance
            # Bet is always added to pot first, then prize is deducted if player wins
            if combination_type == 'triple_one':
                # Jackpot - player gets entire pot, pot becomes 0
                new_pot_balance = 0
            else:
                # Add bet to pot, then subtract prize if any
                new_pot_balance = pot_balance + self.fixed_bet - prize
            
            # Prepare result
            result = {
                'success': True,
                'dice': dice_str,
                'combination': combination_desc,
                'combination_type': combination_type,
                'prize': prize,
                'bet': self.fixed_bet,
                'pot_before': pot_balance,
                'pot_after': new_pot_balance,
                'jackpot': combination_type == 'triple_one',
                'message': self._format_result_message(dice_str, combination_desc, prize, new_pot_balance)
            }
            
            logger.info(f"🎲 {player_name} rolled {dice_str} → {combination_desc} - Prize: {prize}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error playing dice game: {e}")
            return {
                'success': False,
                'message': f"Error while playing the dice game: {str(e)}"
            }
    
    def _format_result_message(self, dice: str, combination: str, prize: int, new_pot: int) -> str:
        """Format the result message for display."""
        # Format individual dice with dice emojis
        dice_display = " ".join([f"🎲{d}" for d in dice.split("-")])
        
        # Build the complete message with all sections
        message = f"{get_message('roll_title')}\n{dice_display}\n"
        message += f"{get_message('combination_title')} {combination}\n"
        message += f"{get_message('prize_title')} "
        
        if prize == 0:
            message += get_message("no_prize", combination=dice)
        elif "JACKPOT" in combination:
            message += get_message("pot_won", prize=prize)
        else:
            message += get_message("prize_multiplier", combination=combination, prize=prize)
        
        message += f"\n{get_message('current_pot_title')} {new_pot:,} coins"
        
        return message


# Global game instance
_game_instance = None

def get_dice_game_instance(fixed_bet: int = 1) -> DiceGame:
    """Get or create dice game instance."""
    global _game_instance
    if _game_instance is None or _game_instance.fixed_bet != fixed_bet:
        _game_instance = DiceGame(fixed_bet)
    return _game_instance

def process_play(player_id: str, player_name: str, server_id: str,
                 server_display_name: str, current_pot: int) -> Dict[str, Any]:
    try:
        # Try to get banker database
        try:
            from agent_roles_db import get_roles_db_instance
            roles_db = get_roles_db_instance(server_id)  # Use server_id directly instead of server name
        except ImportError:
            from roles.banker.banker_db import get_banker_roles_db_instance
            roles_db = get_banker_roles_db_instance(server_id)
        
        if roles_db:
            config = roles_db.get_role_config('dice_game', server_id)
            fixed_bet = config.get('fixed_bet', 1)
            announcements_active = config.get('announcements_active', True)
            logger.info(f"🔧 DB Config - Server: {server_id}, Bet: {fixed_bet}, Announcements: {announcements_active}")
        else:
            fixed_bet = 1
            announcements_active = True
            logger.warning(f"⚠️ No DB config found, using defaults - Bet: {fixed_bet}, Announcements: {announcements_active}")
        
        # Play the game
        game = get_dice_game_instance(fixed_bet)
        result = game.play_game(player_id, player_name, server_id, server_display_name, current_pot)
        result['announcements'] = []
        
        # Integrate with banker system for gold transactions
        banker_message = ""
        
        try:
            from agent_roles_db import get_roles_db_instance
            banker_db = get_roles_db_instance(server_id)
        except ImportError:
            banker_db = None
            
        if banker_db and result['success']:
            try:
                # Use BankerRolesDB for wallet operations
                from roles.banker.banker_db import get_banker_roles_db_instance
                banker_roles_db = get_banker_roles_db_instance(server_id)
                banker_roles_db.create_wallet("dice_game_pot", "Dice Game Pot", server_id, server_display_name)
                banker_roles_db.create_wallet(player_id, player_name, server_id, server_display_name, 'user')
                current_pot = banker_roles_db.get_balance("dice_game_pot", server_id)
                result['pot_before'] = current_pot
                prize = result.get('prize', 0)
                if prize > 0 and current_pot < prize:
                    result['success'] = False
                    result['message'] = "❌ The pot does not have enough gold to pay that prize."
                    return result
                result['pot_after'] = 0 if result.get('jackpot') else (current_pot + result['bet'] - prize)
                result['message'] = game._format_result_message(result['dice'], result['combination'], prize, result['pot_after'])

                # Deduct the bet amount from player's wallet
                bet_deducted = banker_roles_db.update_balance(
                    player_id, player_name, server_id, server_display_name,
                    -result['bet'], "dice_game_bet", 
                    f"Dice game bet: {result['dice']}", 
                    "dice_game", "Dice Game System"
                )
                
                if not bet_deducted:
                    banker_message = "❌ Not enough gold to place the bet."
                    result['success'] = False
                    result['message'] = banker_message
                else:
                    # If player won, add the prize to their wallet
                    if result['prize'] > 0:
                        prize_added = banker_roles_db.update_balance(
                            player_id, player_name, server_id, server_display_name,
                            result['prize'], "dice_game_win", 
                            f"Dice game winnings: {result['combination']}", 
                            "dice_game", "Dice Game System"
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
                            "dice_game_pot", "Dice Game Pot", server_id, server_display_name,
                            pot_delta, "dice_game_pot_update",
                            f"Dice game pot update: {result['dice']}",
                            "dice_game", "Dice Game System"
                        )
                        if not pot_updated:
                            banker_message = "⚠️ The pot could not be updated."
                            result['success'] = False
                            result['message'] = banker_message
                        elif result.get('jackpot'):
                            # Jackpot won - refill pot with banker opening bonus (15x TAE)
                            tae = banker_roles_db.get_tae(server_id)
                            opening_bonus = tae * 15
                            if opening_bonus > 0:
                                refill_result = banker_roles_db.update_balance(
                                    "dice_game_pot", "Dice Game Pot", server_id, server_display_name,
                                    opening_bonus, "dice_game_pot_refill",
                                    f"Jackpot refill with opening bonus (15x TAE)",
                                    "dice_game", "Dice Game System"
                                )
                                if refill_result:
                                    result['pot_after'] = opening_bonus
                                    banker_message += f"\n🎉 Jackpot won! Pot refilled with {opening_bonus:,} gold from banker bonus (15x TAE)."
                                else:
                                    banker_message += "\n⚠️ Jackpot won but pot refill failed."
                            else:
                                banker_message += "\n🎉 Jackpot won! No banker bonus configured for refill."
            except Exception as e:
                # If banker integration fails, still allow the game but warn
                banker_message = f"⚠️ Banker integration failed: {str(e)}"
        
        if result['success']:
            # Save the game to database
            try:
                from agent_roles_db import get_roles_db_instance
                roles_db = get_roles_db_instance(server_id)
                if roles_db:
                    play_id = roles_db.save_dice_game_play(
                        player_id, player_name, server_id, server_display_name,
                        result['bet'], result['dice'], result['combination'], 
                        result['prize'], result['pot_before'], result['pot_after']
                    )
                    logger.info(f"💾 Saved dice game play {play_id} to database")
                else:
                    logger.warning("⚠️ Could not save dice game - no database connection")
            except Exception as e:
                logger.error(f"❌ Failed to save dice game play: {e}")
            
            if announcements_active:
                logger.info(f"📢 Announcements are ACTIVE, checking thresholds...")
                announcement_messages = []
                threshold_balance = fixed_bet * MEDIUM_HIGH_POT_MULTIPLIER
                logger.info(f"📢 Threshold: {threshold_balance} (fixed_bet: {fixed_bet} × {MEDIUM_HIGH_POT_MULTIPLIER})")

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
        logger.error(f"❌ Error processing dice game play request: {e}")
        return {
            'success': False,
            'message': f"Error processing the dice game: {str(e)}"
        }




async def dice_game_task():
    """Execute dice game task - periodic maintenance and announcements."""
    logger.info("🎲 Starting dice game task...")
    
    try:
        # This would handle periodic dice game maintenance
        # For now, just log that the task ran
        logger.info("🎲 Dice game task completed - the game is ready for players")
        
    except Exception as e:
        logger.error(f"🎲 Error in dice game task: {e}")
