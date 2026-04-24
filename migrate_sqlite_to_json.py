#!/usr/bin/env python3
"""
Migration script: SQLite (roles_config, behavior_states) → server_config.json

This script migrates role and behavior configuration from SQLite databases to
JSON-based server_config.json files. This reduces I/O overhead on Raspberry Pi
by eliminating SQLite write operations for configuration toggles.

Run this script once per server to migrate existing data:
    python migrate_sqlite_to_json.py

After migration, the SQLite tables can be safely removed.
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agent_logging import get_logger
from discord_bot.canvas.server_config import (
    _load_server_config,
    _save_server_config,
    _get_timestamp
)

logger = get_logger('migrate_sqlite_to_json')


def get_all_server_ids() -> list[str]:
    """Get all server IDs that have databases."""
    try:
        db_dir = project_root / "databases"
        if not db_dir.exists():
            return []
        
        server_ids = []
        for server_dir in db_dir.iterdir():
            if server_dir.is_dir() and server_dir.name.isdigit():
                server_ids.append(server_dir.name)
        
        return sorted(server_ids)
    except Exception as e:
        logger.error(f"Error getting server IDs: {e}")
        return []


def get_roles_db_path(server_id: str) -> Optional[Path]:
    """Get path to roles database for a server."""
    try:
        from agent_db import get_personality_name
        personality_name = get_personality_name(server_id)
        if not personality_name:
            return None
        
        db_dir = project_root / "databases" / server_id
        db_path = db_dir / f"roles_{personality_name}.db"
        
        if db_path.exists():
            return db_path
        return None
    except Exception as e:
        logger.warning(f"Error getting roles DB path for server {server_id}: {e}")
        return None


def get_behavior_db_path(server_id: str) -> Optional[Path]:
    """Get path to behavior database for a server."""
    try:
        from agent_db import get_personality_name
        personality_name = get_personality_name(server_id)
        if not personality_name:
            return None
        
        db_dir = project_root / "databases" / server_id
        db_path = db_dir / f"behavior_{personality_name}.db"
        
        if db_path.exists():
            return db_path
        return None
    except Exception as e:
        logger.warning(f"Error getting behavior DB path for server {server_id}: {e}")
        return None


def migrate_roles_from_sqlite(server_id: str, roles_db_path: Path) -> bool:
    """Migrate roles configuration from SQLite to server_config.json."""
    try:
        logger.info(f"Migrating roles for server {server_id}...")
        
        # Read all roles from SQLite
        with sqlite3.connect(roles_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role_name, enabled, config_data FROM roles_config")
            rows = cursor.fetchall()
        
        if not rows:
            logger.info(f"No roles found in SQLite for server {server_id}")
            return True
        
        # Load existing server config
        config = _load_server_config(server_id)
        
        # Ensure roles section exists
        if "roles" not in config:
            config["roles"] = {}
        
        # Migrate each role
        migrated_count = 0
        for role_name, enabled, config_data in rows:
            # Parse config_data if it's a JSON string
            config_dict = None
            if config_data:
                try:
                    config_dict = json.loads(config_data)
                except json.JSONDecodeError:
                    logger.warning(f"  Failed to parse config_data for {role_name}, storing as-is")
                    config_dict = {"config_data": config_data}
            
            config["roles"][role_name] = {
                "enabled": bool(enabled),
                "config": config_dict,
                "updated_at": _get_timestamp()
            }
            migrated_count += 1
            logger.debug(f"  Migrated role: {role_name} (enabled={enabled}, config_keys={list(config_dict.keys()) if config_dict else []})")
        
        # Save migrated config
        success = _save_server_config(server_id, config)
        if success:
            logger.info(f"✅ Migrated {migrated_count} roles from SQLite to server_config.json for server {server_id}")
        return success
        
    except Exception as e:
        logger.error(f"❌ Error migrating roles from SQLite for server {server_id}: {e}")
        return False


def migrate_behaviors_from_sqlite(server_id: str, behavior_db_path: Path) -> bool:
    """Migrate behaviors configuration from SQLite to server_config.json."""
    try:
        logger.info(f"Migrating behaviors for server {server_id}...")
        
        # Read all behaviors from SQLite
        with sqlite3.connect(behavior_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT behavior_name, enabled, config_data, updated_by FROM behavior_states")
            rows = cursor.fetchall()
        
        if not rows:
            logger.info(f"No behaviors found in SQLite for server {server_id}")
            return True
        
        # Load existing server config
        config = _load_server_config(server_id)
        
        # Ensure behaviors section exists
        if "behaviors" not in config:
            config["behaviors"] = {}
        
        # Migrate each behavior
        migrated_count = 0
        for behavior_name, enabled, config_data, updated_by in rows:
            # Parse config_data if it's a JSON string
            config_dict = None
            if config_data:
                try:
                    config_dict = json.loads(config_data)
                except json.JSONDecodeError:
                    pass
            
            config["behaviors"][behavior_name] = {
                "enabled": bool(enabled),
                "config": config_dict,
                "updated_by": updated_by,
                "migrated_from_sqlite": True,
                "migrated_at": _get_timestamp()
            }
            migrated_count += 1
            logger.debug(f"  Migrated behavior: {behavior_name} (enabled={enabled}, config={config_dict})")
        
        # Save migrated config
        success = _save_server_config(server_id, config)
        if success:
            logger.info(f"✅ Migrated {migrated_count} behaviors from SQLite to server_config.json for server {server_id}")
        return success
        
    except Exception as e:
        logger.error(f"❌ Error migrating behaviors from SQLite for server {server_id}: {e}")
        return False


def migrate_server(server_id: str) -> Dict[str, bool]:
    """Migrate both roles and behaviors for a single server."""
    results = {
        "roles": False,
        "behaviors": False,
        "server_id": server_id
    }
    
    # Migrate roles
    roles_db_path = get_roles_db_path(server_id)
    if roles_db_path:
        results["roles"] = migrate_roles_from_sqlite(server_id, roles_db_path)
    else:
        logger.info(f"No roles database found for server {server_id}, skipping roles migration")
        results["roles"] = True  # Not an error if DB doesn't exist
    
    # Migrate behaviors
    behavior_db_path = get_behavior_db_path(server_id)
    if behavior_db_path:
        results["behaviors"] = migrate_behaviors_from_sqlite(server_id, behavior_db_path)
    else:
        logger.info(f"No behavior database found for server {server_id}, skipping behaviors migration")
        results["behaviors"] = True  # Not an error if DB doesn't exist
    
    return results


def main():
    """Main migration function."""
    logger.info("=" * 60)
    logger.info("Starting SQLite → server_config.json migration")
    logger.info("=" * 60)
    
    server_ids = get_all_server_ids()
    
    if not server_ids:
        logger.warning("No server directories found in databases/")
        return
    
    logger.info(f"Found {len(server_ids)} server(s) to migrate")
    
    results = []
    for server_id in server_ids:
        logger.info(f"\n{'=' * 40}")
        logger.info(f"Processing server: {server_id}")
        logger.info(f"{'=' * 40}")
        
        result = migrate_server(server_id)
        results.append(result)
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 60)
    
    successful = sum(1 for r in results if r["roles"] and r["behaviors"])
    total = len(results)
    
    for result in results:
        status = "✅ SUCCESS" if result["roles"] and result["behaviors"] else "❌ FAILED"
        logger.info(f"Server {result['server_id']}: {status}")
    
    logger.info(f"\nTotal: {successful}/{total} servers migrated successfully")
    
    if successful == total:
        logger.info("\n✅ Migration complete!")
        logger.info("\nNext steps:")
        logger.info("1. Test the bot to ensure roles/behaviors work correctly")
        logger.info("2. If everything works, you can remove the obsolete SQLite tables:")
        logger.info("   - agent_roles_db.py: remove roles_config table methods")
        logger.info("   - behavior/db_behavior.py: remove behavior_states table")
    else:
        logger.warning("\n⚠️ Some migrations failed. Check logs above for details.")


if __name__ == "__main__":
    main()
