"""
Cubilete Database Module (Roles Integration)
Handles storage and retrieval of cubilete data using centralized roles.db.
"""

from datetime import datetime
from typing import List, Dict, Optional, Any
import json
from agent_logging import get_logger
from agent_roles_db import get_roles_db_instance

logger = get_logger('cubilete_roles_db')


class CubileteRolesDB:
    """Database handler for cubilete using centralized roles.db."""

    def __init__(self, server_id: str = None):
        """Initialize database connection using centralized roles.db."""
        if server_id is None:
            from agent_db import get_server_id
            server_id = get_server_id()
        self.server_id = server_id
        self.roles_db = get_roles_db_instance(server_id)
        self.db_path = self.roles_db.db_path
    
    def is_enabled(self) -> bool:
        """Check if cubilete is enabled for this server."""
        return self.roles_db.is_role_enabled("cubilete", self.server_id)
    
    def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable cubilete for this server."""
        return self.roles_db.set_role_enabled("cubilete", self.server_id, enabled)
    
    def save_config(self, enabled: bool, bet_multiplier_tae: int = 2, 
                   announcements_active: bool = True, pot_refill_multiplier: int = 15,
                   config_data: str = None) -> bool:
        """Save cubilete configuration for a server."""
        try:
            from discord_bot.canvas.server_config import set_role_config_value
            
            # Build config dict
            config = {
                'bet_multiplier_tae': bet_multiplier_tae,
                'announcements_active': announcements_active,
                'pot_refill_multiplier': pot_refill_multiplier
            }
            
            # Merge extra config if provided
            if config_data:
                try:
                    extra_data = json.loads(config_data)
                    config.update(extra_data)
                except json.JSONDecodeError:
                    config['extra'] = config_data
            
            # Save using server_config
            set_role_config_value(self.server_id, "cubilete", "config", config)
            set_role_config_value(self.server_id, "cubilete", "enabled", enabled)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save cubilete config: {e}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """Get cubilete configuration for a server."""
        try:
            from discord_bot.canvas.server_config import get_role_config_value
            config = get_role_config_value(self.server_id, "cubilete", "config", default={})
            return config
        except Exception as e:
            logger.error(f"Failed to get cubilete config: {e}")
            return {'bet_multiplier_tae': 2, 'announcements_active': True, 'pot_refill_multiplier': 15}
    
    def save_stats(self, user_id: str, total_plays: int = 0, total_bet: int = 0, 
                  total_won: int = 0, pots_won: int = 0, biggest_prize: int = 0, 
                  last_play: str = None) -> bool:
        """Save or update cubilete statistics for a user."""
        return self.roles_db.save_cubilete_stats(
            user_id, total_plays, total_bet, total_won, 
            pots_won, biggest_prize, last_play
        )
    
    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """Get cubilete statistics for a user."""
        return self.roles_db.get_cubilete_stats(user_id)
    
    def save_play(self, user_id: str, user_name: str,
                  bet: int, dice: str, combination: str, prize: int, 
                  pot_before: int, pot_after: int) -> int:
        """Save a cubilete play to the database."""
        return self.roles_db.save_cubilete_play(
            user_id, user_name,
            bet, dice, combination, prize, pot_before, pot_after
        )
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent cubilete plays for a server."""
        return self.roles_db.get_cubilete_history(limit)
    
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
def get_cubilete_roles_db_instance(server_id: str = "default") -> CubileteRolesDB:
    """Get the cubilete database instance using centralized roles.db."""
    return CubileteRolesDB(server_id)
