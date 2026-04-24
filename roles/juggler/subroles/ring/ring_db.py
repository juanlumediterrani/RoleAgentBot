"""
Ring Database Module for Juggler
Handles storage and retrieval of ring configuration and accusations using centralized roles.db.
"""

from typing import List, Dict, Optional, Any
from agent_logging import get_logger
from agent_roles_db import get_roles_db_instance
import json
from datetime import datetime

logger = get_logger('ring_db')


class RingDB:
    """Database handler for ring using centralized roles.db."""
    
    def __init__(self, server_id: str = "default"):
        """Initialize database connection using centralized roles.db."""
        self.server_id = server_id
        self.roles_db = get_roles_db_instance(server_id)
        self.db_path = self.roles_db.db_path
    
    def save_config(self, enabled: bool, current_accusation: str = None, 
                     accused_user: str = None, config_data: str = None) -> bool:
        """Save ring configuration for a server."""
        try:
            from discord_bot.canvas.server_config import get_role_config_value, set_role_config_value
            
            # Get existing config
            config = get_role_config_value(self.server_id, "ring", "config", default={})
            if config is None:
                config = {}
            
            # Update ring configuration
            if current_accusation is not None:
                config['current_accusation'] = current_accusation
            if accused_user is not None:
                # accused_user now contains user ID, not username
                config['accused_user_id'] = accused_user
                config['accused_at'] = datetime.now().isoformat()
            if config_data is not None:
                try:
                    extra_data = json.loads(config_data)
                    config.update(extra_data)
                except json.JSONDecodeError:
                    config['extra'] = config_data
            
            # Save using server_config
            set_role_config_value(self.server_id, "ring", "config", config)
            set_role_config_value(self.server_id, "ring", "enabled", enabled)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save ring config: {e}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """Get ring configuration for a server."""
        try:
            from discord_bot.canvas.server_config import get_role_config_value
            config = get_role_config_value(self.server_id, "ring", "config", default={})
            return config if isinstance(config, dict) else {}
        except Exception as e:
            logger.error(f"Failed to get ring config: {e}")
            return {}
    
    def save_accusation(self, accuser_id: str, accused_id: str, 
                       accusation: str, evidence: str = None) -> int:
        """Save a ring accusation to the database."""
        return self.roles_db.save_ring_accusation(
            accuser_id, accused_id, accusation, evidence
        )
    
    def get_accusations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent ring accusations for a server."""
        return self.roles_db.get_ring_accusations(limit)


# Global database instance
def get_ring_db_instance(server_id: str = "default") -> RingDB:
    """Get the ring database instance using centralized roles.db."""
    return RingDB(server_id)
