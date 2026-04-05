"""
Ring Database Module
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
            # Get existing config
            existing_config = self.roles_db.get_role_config('ring')
            existing_data = existing_config.get('config_data', '{}')
            if existing_data:
                try:
                    data = json.loads(existing_data)
                except json.JSONDecodeError:
                    data = {}
            else:
                data = {}
            
            # Update ring configuration
            if current_accusation is not None:
                data['current_accusation'] = current_accusation
            if accused_user is not None:
                # accused_user now contains user ID, not username
                data['accused_user_id'] = accused_user
                data['accused_at'] = datetime.now().isoformat()
            if config_data is not None:
                try:
                    extra_data = json.loads(config_data)
                    data.update(extra_data)
                except json.JSONDecodeError:
                    data['extra'] = config_data
            
            return self.roles_db.save_role_config('ring', enabled, json.dumps(data))
            
        except Exception as e:
            logger.error(f"Failed to save ring config: {e}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """Get ring configuration for a server."""
        try:
            config = self.roles_db.get_role_config('ring')
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
                'current_accusation': data.get('current_accusation'),
                'accused_user_id': data.get('accused_user_id'),  # Return user ID
                'accused_user_name': data.get('accused_user_name'),  # Also return name
                'accused_at': data.get('accused_at'),
                'config_data': config_data
            }
            
        except Exception as e:
            logger.error(f"Failed to get ring config: {e}")
            return {'enabled': True, 'current_accusation': None, 'accused_user_id': None, 'accused_user_name': None, 'accused_at': None, 'config_data': '{}'}
    
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
