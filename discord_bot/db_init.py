"""
Database initialization utilities for RoleAgentBot.
Handles comprehensive database creation when bot joins new servers.
"""

from agent_logging import get_logger
from agent_db import get_db_instance
from agent_roles_db import get_roles_db_instance
from behavior.db_behavior import get_behavior_db_instance
import asyncio
import sqlite3

logger = get_logger('db_init')


async def _bootstrap_daily_memory_if_missing(server_key: str, guild_name: str, log, context_label: str) -> None:
    from agent_db import get_db_instance
    from agent_mind import generate_daily_memory_summary

    try:
        db_instance = get_db_instance(server_key)
        with db_instance._lock:
            conn = sqlite3.connect(db_instance.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT summary FROM daily_memory
                WHERE summary IS NOT NULL AND summary != '' AND summary != '[Error in internal task]'
                ORDER BY updated_at DESC LIMIT 1
            """)
            result = cursor.fetchone()
            conn.close()

        if result and result[0] and result[0].strip():
            log.info(f"🧠 Daily memory already exists for '{guild_name}': {result[0][:50]}...")
            return

        log.info(f"🧠 {context_label} for '{guild_name}', scheduling daily memory bootstrap...")

        async def _generate() -> None:
            try:
                summary = await asyncio.to_thread(generate_daily_memory_summary, server_key)
                if summary:
                    log.info(f"✅ Daily memory bootstrap completed for '{guild_name}': {summary[:50]}...")
                else:
                    log.warning(f"⚠️ Daily memory bootstrap produced no summary for '{guild_name}'")
            except Exception as e:
                log.error(f"❌ Error generating bootstrap daily memory for '{guild_name}': {e}")

        asyncio.create_task(_generate())
    except Exception as e:
        log.warning(f"⚠️ Could not bootstrap daily memory for '{guild_name}': {e}")


def initialize_all_databases_for_server(server_id: str, agent_config: dict = None) -> bool:
    """
    Initialize all required databases for a new server.
    
    This function creates and initializes all database instances that the bot needs:
    - Main agent database (conversations, memory, etc.)
    - Roles database (role configurations, subrole data)
    - Behavior database (greetings, interactions, etc.)
    - All role-specific databases (banker, news_watcher, etc.)
    
    Args:
        server_id: Discord guild ID for the new server
        agent_config: Agent configuration dictionary (optional)
        
    Returns:
        bool: True if all databases initialized successfully, False otherwise
    """
    success_count = 0
    total_count = 0
    
    logger.info(f"🗄️ Initializing all databases for server {server_id}")
    
    # 1. Main Agent Database
    total_count += 1
    try:
        agent_db = get_db_instance(server_id)
        logger.info(f"✅ Agent database initialized for server {server_id}")
        success_count += 1
    except Exception as e:
        logger.error(f"❌ Failed to initialize agent database for server {server_id}: {e}")
    
    # 2. Roles Database (centralized)
    total_count += 1
    try:
        roles_db = get_roles_db_instance(server_id)
        # Ensure default roles exist
        roles_db.ensure_default_roles()
        logger.info(f"✅ Roles database initialized for server {server_id}")
        success_count += 1
    except Exception as e:
        logger.error(f"❌ Failed to initialize roles database for server {server_id}: {e}")
    
    # 3. Behavior Database
    total_count += 1
    try:
        behavior_db = get_behavior_db_instance(server_id)
        logger.info(f"✅ Behavior database initialized for server {server_id}")
        success_count += 1
    except Exception as e:
        logger.error(f"❌ Failed to initialize behavior database for server {server_id}: {e}")
    
    # 4. Role-specific Databases
    role_databases = [
        ("banker", "roles.banker.banker_db", "BankerRolesDB"),
        ("news_watcher", "roles.news_watcher.db_role_news_watcher", "DatabaseRoleNewsWatcher"),
        ("treasure_hunter", "roles.treasure_hunter.db_role_treasure_hunter", "DatabaseRolePoe"),
        ("mc", "roles.mc.db_role_mc", "DatabaseRoleMC"),
        ("dice_game", "roles.trickster.subroles.dice_game.dice_game_db", "DiceGameRolesDB"),
    ]
    
    # Note: Some trickster subroles use centralized roles.db instead of separate databases
    # ring, nordic_runes, beggar are handled through the centralized roles system
    
    for role_name, module_path, class_name in role_databases:
        total_count += 1
        try:
            # Import the database class
            module = __import__(module_path, fromlist=[class_name])
            db_class = getattr(module, class_name)
            
            # Initialize the database with special handling for treasure_hunter
            if role_name == "treasure_hunter":
                role_db = db_class(server_id, liga="Standard")  # Default league
            else:
                role_db = db_class(server_id)
            logger.info(f"✅ {role_name} database initialized for server {server_id}")
            success_count += 1
            
        except ImportError as e:
            logger.warning(f"⚠️ Could not import {role_name} database ({module_path}): {e}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize {role_name} database for server {server_id}: {e}")
    
    # 5. Summary
    success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
    logger.info(f"📊 Database initialization complete for server {server_id}: {success_count}/{total_count} ({success_rate:.1f}%)")
    
    return success_count == total_count


async def initialize_server_complete(guild, agent_config: dict = None, is_startup: bool = False) -> bool:
    """
    Complete server initialization - unified method for both startup and new guild joins.
    
    This function handles all server initialization tasks:
    - Database initialization (all databases)
    - Role configuration setup
    - Default roles loading
    - News watcher feeds initialization
    - Logging configuration
    - Server activation
    
    Args:
        guild: Discord guild object
        agent_config: Agent configuration dictionary (optional)
        is_startup: True if this is during bot startup, False for new guild joins
        
    Returns:
        bool: True if all initialization completed successfully, False otherwise
    """
    from discord_bot.discord_utils import get_server_key
    from agent_db import set_current_server
    from agent_logging import update_log_file_path
    from agent_engine import PERSONALITY
    
    server_key = get_server_key(guild)
    guild_name = guild.name
    
    # Set up logging for this server
    personality_name = PERSONALITY.get('name', 'Bot')
    update_log_file_path(server_key, personality_name)
    logger = get_logger('discord')
    
    if is_startup:
        logger.info(f"🚀 Initializing server on startup: '{guild_name}' ({server_key})")
        # Set as active server (only during startup)
        set_current_server(server_key)
    else:
        logger.info(f"🏰 Initializing new guild: '{guild_name}' ({server_key})")
    
    success_count = 0
    total_count = 0
    
    # 1. Initialize all databases
    total_count += 1
    logger.info(f"🗄️ Initializing databases for {guild_name}")
    db_success = initialize_all_databases_for_server(server_key, agent_config)
    if db_success:
        logger.info(f"✅ All databases initialized successfully for {guild_name}")
        success_count += 1
        bootstrap_label = "First time initialization" if is_startup else "New guild initialization"
        await _bootstrap_daily_memory_if_missing(server_key, guild_name, logger, bootstrap_label)
    else:
        logger.warning(f"⚠️ Some databases failed to initialize for {guild_name}")
    
    # 2. Load default roles configuration
    total_count += 1
    try:
        from agent_roles_db import RolesDatabase
        roles_db = RolesDatabase(server_key)
        default_roles = ["news_watcher", "treasure_hunter", "trickster", "banker"]
        for role_name in default_roles:
            # Enable each default role if not already configured
            roles_db.save_role_config(role_name, True, '{}')
        logger.info(f"� Default roles loaded for server '{guild_name}'")
        success_count += 1
    except Exception as e:
        logger.warning(f"Failed to load default roles for server '{guild_name}': {e}")
    
    # 3. Sync healthy global feeds if news watcher is enabled
    if agent_config:
        from discord_bot.discord_utils import is_role_enabled_check
        if is_role_enabled_check("news_watcher", agent_config):
            total_count += 1
            try:
                from roles.news_watcher.global_feed_health import sync_feeds_to_server
                sync_feeds_to_server(server_key)
                logger.info(f"📡 Healthy global feeds synced to server {guild_name}")
                success_count += 1
            except Exception as e:
                logger.error(f"❌ Error syncing feeds to server {guild_name}: {e}")
    
    # 4. Initialize roles configuration (migration and defaults)
    total_count += 1
    try:
        from init_roles_config import init_roles_config_for_server
        roles_success = init_roles_config_for_server(server_key)
        if roles_success:
            logger.info(f"⚙️ Roles configuration initialized for server {guild_name}")
            success_count += 1
        else:
            logger.warning(f"⚠️ Roles configuration failed for server {guild_name}")
    except Exception as e:
        logger.error(f"❌ Error initializing roles configuration for server {guild_name}: {e}")
    
    # Summary
    success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
    if is_startup:
        logger.info(f"📊 Server startup initialization complete for '{guild_name}': {success_count}/{total_count} ({success_rate:.1f}%)")
    else:
        logger.info(f"📊 New guild initialization complete for '{guild_name}': {success_count}/{total_count} ({success_rate:.1f}%)")
    
    return success_count == total_count
