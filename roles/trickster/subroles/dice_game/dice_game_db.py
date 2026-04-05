"""
Dice Game Database Module (Roles Integration)
Handles storage and retrieval of dice game data using centralized roles.db.
"""

from datetime import datetime
from typing import List, Dict, Optional, Any
import json
from agent_logging import get_logger
from agent_roles_db import get_roles_db_instance

logger = get_logger('dice_game_roles_db')


class DiceGameRolesDB:
    """Database handler for dice game using centralized roles.db."""
    
    def __init__(self, server_id: str = "default"):
        """Initialize database connection using centralized roles.db."""
        self.server_id = server_id
        self.roles_db = get_roles_db_instance(server_id)
        self.db_path = self.roles_db.db_path
    
    def is_enabled(self) -> bool:
        """Check if dice game is enabled for this server."""
        return self.roles_db.is_role_enabled("dice_game", self.server_id)
    
    def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable dice game for this server."""
        return self.roles_db.set_role_enabled("dice_game", self.server_id, enabled)
    
    def save_config(self, enabled: bool, bet_fija: int = 1, 
                   announcements_active: bool = True, config_data: str = None) -> bool:
        """Save dice game configuration for a server."""
        try:
            # Get existing config
            existing_config = self.roles_db.get_role_config('dice_game')
            existing_data = existing_config.get('config_data', '{}')
            if existing_data:
                try:
                    data = json.loads(existing_data)
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}
            
            # Update dice game configuration
            data['bet_fija'] = bet_fija
            data['announcements_active'] = announcements_active
            if config_data:
                try:
                    extra_data = json.loads(config_data)
                    data.update(extra_data)
                except json.JSONDecodeError:
                    data['extra'] = config_data
            
            return self.roles_db.save_role_config('dice_game', enabled, json.dumps(data))
            
        except Exception as e:
            logger.error(f"Failed to save dice game config: {e}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """Get dice game configuration for a server."""
        try:
            config = self.roles_db.get_role_config('dice_game')
            config_data = config.get('config_data', '{}')
            if config_data:
                try:
                    data = json.loads(config_data)
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}
            
            return {
                'enabled': config.get('enabled', True),
                'bet_fija': data.get('bet_fija', 1),
                'announcements_active': data.get('announcements_active', True),
                'config_data': config_data
            }
            
        except Exception as e:
            logger.error(f"Failed to get dice game config: {e}")
            return {'enabled': True, 'bet_fija': 1, 'announcements_active': True}
    
    def save_stats(self, user_id: str, total_plays: int = 0, total_bet: int = 0, 
                  total_won: int = 0, pots_won: int = 0, biggest_prize: int = 0, 
                  last_play: str = None) -> bool:
        """Save or update dice game statistics for a user."""
        return self.roles_db.save_dice_game_stats(
            user_id, total_plays, total_bet, total_won, 
            pots_won, biggest_prize, last_play
        )
    
    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """Get dice game statistics for a user."""
        return self.roles_db.get_dice_game_stats(user_id)
    
    def save_play(self, user_id: str, user_name: str,
                  bet: int, dice: str, combination: str, prize: int, 
                  pot_before: int, pot_after: int) -> int:
        """Save a dice game play to the database."""
        return self.roles_db.save_dice_game_play(
            user_id, user_name,
            bet, dice, combination, prize, pot_before, pot_after
        )
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent dice game plays for a server."""
        return self.roles_db.get_dice_game_history(limit)
    
    def ensure_player_stats(self, user_id: str, server_id: str) -> bool:
        """Ensure player stats exist (create if needed)."""
        try:
            existing_stats = self.get_stats(user_id)
            if not existing_stats.get('created_at'):
                # Create new stats entry
                return self.save_stats(user_id)
            return True
        except Exception as e:
            logger.error(f"Failed to ensure player stats: {e}")
            return False
    
    def update_player_stats(self, user_id: str, bet: int, prize: int, won: bool = False) -> bool:
        """Update player statistics after a game."""
        try:
            stats = self.get_stats(user_id)
            
            # Update statistics
            new_total_plays = stats.get('total_plays', 0) + 1
            new_total_bet = stats.get('total_bet', 0) + bet
            new_total_won = stats.get('total_won', 0) + prize
            new_pots_won = stats.get('pots_won', 0) + (1 if won else 0)
            new_biggest_prize = max(stats.get('biggest_prize', 0), prize)
            
            return self.save_stats(
                user_id=user_id,
                total_plays=new_total_plays,
                total_bet=new_total_bet,
                total_won=new_total_won,
                pots_won=new_pots_won,
                biggest_prize=new_biggest_prize,
                last_play=datetime.now().isoformat()
            )
        except Exception as e:
            logger.error(f"Failed to update player stats: {e}")
            return False


# Global database instance
def get_dice_game_roles_db_instance(server_id: str = "default") -> DiceGameRolesDB:
    """Get the dice game database instance using centralized roles.db."""
    return DiceGameRolesDB(server_id)
