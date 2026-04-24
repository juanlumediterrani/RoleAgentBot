#!/usr/bin/env python3
"""
Initialize server_config.json with default roles.
This script ensures that server_config.json is always populated with default roles.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_logging import get_logger
from agent_engine import AGENT_CFG

logger = get_logger('init_roles_config')

def init_roles_config_for_server(server_id: str):
    """Initialize server_config.json for a specific server.
    
    Migration from agent_config.json only happens ONCE on first initialization,
    not on every server startup.
    """
    try:
        logger.info(f"Initializing server_config.json for server {server_id}")
        
        # Import server_config functions
        from discord_bot.canvas.server_config import get_all_roles_config, set_role_config_value
        
        # Get current roles from server_config
        roles_config = get_all_roles_config(server_id)
        
        # Get roles from agent_config.json
        agent_roles_cfg = AGENT_CFG.get("roles", {})
        
        # Initialize roles that are enabled in agent_config.json
        initialized_count = 0
        for role_name, cfg in agent_roles_cfg.items():
            if isinstance(cfg, dict) and cfg.get("enabled", False):
                # Only initialize if not already in server_config
                if role_name not in roles_config:
                    set_role_config_value(server_id, role_name, "enabled", True)
                    initialized_count += 1
                    logger.info(f"✅ Initialized role {role_name} in server_config.json")
                else:
                    logger.debug(f"ℹ️ Role {role_name} already in server_config.json")
        
        if initialized_count > 0:
            logger.info(f"🎉 Initialized {initialized_count} roles in server_config.json")
        else:
            logger.info("ℹ️ All roles already initialized in server_config.json")
        
        # Verify final state
        roles_config = get_all_roles_config(server_id)
        count = len(roles_config)
        
        logger.info(f"📊 Final state: {count} roles in server_config.json")
        for role_name, role_config in sorted(roles_config.items()):
            enabled = role_config.get("enabled", False)
            logger.info(f"   • {role_name}: enabled={enabled}")
        
        return count > 0
        
    except Exception as e:
        logger.error(f"❌ Error initializing server_config.json for server {server_id}: {e}")
        return False

def main():
    """Initialize server_config.json for specified server or all known servers."""
    try:
        # Get server ID from command line argument or use default
        if len(sys.argv) > 1:
            default_server_id = sys.argv[1]
        else:
            default_server_id = "0"
        
        logger.info(f"🚀 Starting server_config.json initialization for server {default_server_id}")
        
        success = init_roles_config_for_server(default_server_id)
        
        if success:
            logger.info("🎉 server_config.json initialization completed successfully")
            return True
        else:
            logger.error("❌ server_config.json initialization failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Fatal error in server_config.json initialization: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
