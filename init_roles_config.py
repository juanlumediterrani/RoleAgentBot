#!/usr/bin/env python3
"""
Initialize roles_config with default roles and migrate from behavior.db
This script ensures that roles_config is always populated and never empty.
"""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_roles_db import get_roles_db_instance
from agent_logging import get_logger

logger = get_logger('init_roles_config')

def init_roles_config_for_server(server_id: str):
    """Initialize roles_config for a specific server."""
    try:
        logger.info(f"Initializing roles_config for server {server_id}")
        
        # Get roles database instance
        roles_db = get_roles_db_instance(server_id)
        
        # First, ensure default roles exist
        success = roles_db.ensure_default_roles()
        if success:
            logger.info("✅ Default roles ensured")
        else:
            logger.error("❌ Failed to ensure default roles")
        
        # Then, migrate from agent_config.json to get subroles and full config
        migrated = roles_db.migrate_roles_from_agent_config()
        if migrated:
            logger.info("✅ Roles migrated from agent_config.json")
        else:
            logger.info("ℹ️ No new roles to migrate from agent_config.json")
        
        # Verify final state
        import sqlite3
        conn = sqlite3.connect(roles_db.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM roles_config")
        count = cursor.fetchone()[0]
        
        cursor.execute("SELECT role_name, enabled FROM roles_config ORDER BY role_name")
        roles = cursor.fetchall()
        
        conn.close()
        
        logger.info(f"📊 Final state: {count} roles in roles_config")
        for role_name, enabled in roles:
            logger.info(f"   • {role_name}: enabled={enabled}")
        
        return count > 0
        
    except Exception as e:
        logger.error(f"❌ Error initializing roles_config for server {server_id}: {e}")
        return False

def main():
    """Initialize roles_config for specified server or all known servers."""
    try:
        # Get server ID from command line argument or use default
        if len(sys.argv) > 1:
            default_server_id = sys.argv[1]
        else:
            default_server_id = "0"
        
        logger.info(f"🚀 Starting roles_config initialization for server {default_server_id}")
        
        success = init_roles_config_for_server(default_server_id)
        
        if success:
            logger.info("🎉 roles_config initialization completed successfully")
            return True
        else:
            logger.error("❌ roles_config initialization failed")
            return False
            
    except Exception as e:
        logger.error(f"❌ Fatal error in roles_config initialization: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
