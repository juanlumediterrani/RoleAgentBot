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
try:
    from discord_bot.discord_core_commands import _personality_descriptions
except ImportError:
    # Fallback if not available - use empty dict
    _personality_descriptions = {}

logger = get_logger('dice_game')


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
        rolenamecombinations = _personality_descriptions.get("roles_view_messages", {}).get("dice_game", {})
        triple_ones = rolenamecombinations.get("triple_ones", "(JACKPOT!)")
        triple = rolenamecombinations.get("three_of_a_kind", "(Triple)")
        straight = rolenamecombinations.get("straight", "(Straight)")
        pair = rolenamecombinations.get("pair", "(Pair)")
        nothing = rolenamecombinations.get("nothing", "(No prize)")

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
            if combination_type == 'triple_one':
                # Jackpot - pot is emptied
                new_pot_balance = 0
            elif prize > 0:
                # Partial prize - deduct from pot
                new_pot_balance = pot_balance - prize
            else:
                # No prize - add bet to pot
                new_pot_balance = pot_balance + self.fixed_bet
            
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
        # Get server config to determine fixed bet
        from .db_dice_game import get_dice_game_db_instance
        
        server_name = server_id  # Use server_id directly instead of server name
        db_game = get_dice_game_db_instance(server_name)
        
        if db_game:
            config = db_game.get_server_config(server_id)
            fixed_bet = config.get('fixed_bet', 1)
        else:
            fixed_bet = 1
        
        # Play the game
        game = get_dice_game_instance(fixed_bet)
        result = game.play_game(player_id, player_name, server_id, server_display_name, current_pot)
        
        # Integrate with banker system for gold transactions
        banker_message = ""
        
        try:
            # Import banker database
            from roles.banker.db_role_banker import get_banker_db_instance
            server_name = server_id  # Use server_id directly instead of server name
            banker_db = get_banker_db_instance(server_name)
            
            if banker_db and result['success']:
                # Deduct the bet amount from player's wallet
                bet_deducted = banker_db.update_balance(
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
                        prize_added = banker_db.update_balance(
                            player_id, player_name, server_id, server_display_name,
                            result['prize'], "dice_game_win", 
                            f"Dice game winnings: {result['combination']}", 
                            "dice_game", "Dice Game System"
                        )
                        
                        if not prize_added:
                            banker_message = "⚠️ You won, but the prize could not be added to the wallet."
                        else:
                            banker_message = "💰 Gold transactions completed."
        except Exception as e:
            # If banker integration fails, still allow the game but warn
            banker_message = f"⚠️ Banker integration failed: {str(e)}"
        
        # Register the game in database if available
        if db_game and result['success']:
            db_game.register_game(
                player_id, player_name, server_id, server_display_name,
                result['bet'], result['dice'], result['combination'],
                result['prize'], result['pot_before'], result['pot_after']
            )
        
        if result['success']:
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
