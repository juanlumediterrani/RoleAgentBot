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
import os
import shutil
import json

logger = get_logger('db_init')


def copy_personality_to_server(server_id: str, personality_name: str = None, language: str = None, update_config: bool = False) -> bool:
    """
    Copy personality files to server-specific directory for first-time initialization.
    
    This function copies the personality folder from the global personalities/ directory
    to a server-specific location under databases/<server_id>/<personality_name>/.
    Each server will then use its own copy, allowing for per-server personality evolution.
    
    New directory structure (with language subdirectories):
        personalities/<personality_name>/<language>/
            ├── personality.json
            ├── prompts.json
            ├── answers.json
            ├── descriptions.json
            └── descriptions/
    
    Copied to:
        databases/<server_id>/<personality_name>/
            ├── personality.json
            ├── prompts.json
            ├── answers.json
            ├── descriptions.json
            └── descriptions/
    
    Args:
        server_id: Discord guild ID
        personality_name: Name of personality folder (e.g., "rab"). 
                          If None, reads from agent_config.json or server_config.json
        language: IETF BCP 47 language code (e.g., "es-ES", "en-US").
                If None, tries to detect from server_config.json or uses "en-US"
        update_config: If True, update server_config.json even if it exists (for personality changes)
        
    Returns:
        bool: True if copy successful or already exists, False on error
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        
        # First, check if server_config.json already exists
        server_config_path = os.path.join(base_dir, 'databases', server_id, 'server_config.json')
        existing_config = {}
        if os.path.exists(server_config_path):
            try:
                with open(server_config_path, encoding='utf-8') as f:
                    existing_config = json.load(f)
            except Exception as e:
                logger.warning(f"Could not read existing server_config.json: {e}")
        
        # Get personality_name from existing config if not provided
        if personality_name is None:
            existing_personality = existing_config.get('active_personality')
            if existing_personality:
                personality_name = existing_personality
                logger.info(f"📋 Using existing personality from server_config.json: {personality_name}")
        
        # Get language from existing config if not provided
        if language is None:
            existing_language = existing_config.get('language')
            if existing_language:
                language = existing_language
                logger.info(f"📋 Using existing language from server_config.json: {language}")
        
        # Fall back to agent_config.json if still no personality
        if personality_name is None:
            config_path = os.path.join(base_dir, 'agent_config.json')
            with open(config_path, encoding='utf-8') as f:
                config = json.load(f)
            
            # Get default personality name from agent_config.json
            personality_name = config.get('default_personality', 'rab')
            
            # Get default language from agent_config.json (new field 'default_language')
            # This is the FINAL fallback language when nothing else is configured
            config_language = config.get('default_language')
            if config_language:
                logger.info(f"📋 Using default_language from agent_config.json: {config_language}")
                # Only override if no language was provided and no existing config
                if language is None or language == 'en-US':
                    language = config_language
            
            logger.info(f"📋 Using system default personality: {personality_name}")
        
        # Default language if still not set (final fallback)
        if language is None:
            language = 'en-US'
            logger.info(f"📋 Using final fallback language: {language}")
        
        # Validate language format
        language = language.strip()
        
        # Paths - new structure: personalities/<name>/<language>/
        source_dir = os.path.join(base_dir, 'personalities', personality_name, language)
        
        # Fallback: if language subdirectory doesn't exist, try old structure (for backward compatibility)
        if not os.path.exists(source_dir):
            old_source_dir = os.path.join(base_dir, 'personalities', personality_name)
            if os.path.exists(old_source_dir):
                logger.warning(f"⚠️ Language subdirectory not found: {source_dir}")
                logger.info(f"📁 Falling back to old structure: {old_source_dir}")
                source_dir = old_source_dir
            else:
                logger.error(f"❌ Source personality directory not found: {source_dir}")
                return False
        
        target_dir = os.path.join(base_dir, 'databases', server_id, personality_name)
        
        # Check if server-specific copy already exists
        if os.path.exists(target_dir):
            logger.info(f"📁 Server-specific personality already exists: {target_dir}")
        else:
            # Create target directory
            os.makedirs(target_dir, exist_ok=True)
            
            # Check if source personality exists
            if not os.path.exists(source_dir):
                logger.error(f"❌ Source personality directory not found: {source_dir}")
                return False
            
            # Copy all files and directories (excluding .db files to preserve renamed databases)
            for item in os.listdir(source_dir):
                # Skip database files - they are managed separately per server
                if item.endswith('.db'):
                    logger.info(f"⏭️ Skipping database file: {item}")
                    continue

                source_item = os.path.join(source_dir, item)
                target_item = os.path.join(target_dir, item)

                if os.path.isdir(source_item):
                    # Copy subdirectory (e.g., descriptions/)
                    shutil.copytree(source_item, target_item)
                    logger.info(f"📂 Copied directory: {item}")
                else:
                    # Copy file (e.g., personality.json, prompts.json)
                    shutil.copy2(source_item, target_item)
                    logger.info(f"📄 Copied file: {item}")
            
            logger.info(f"✅ Personality copied from {source_dir} to {target_dir}")
            
            # Copy avatar files from global personality directory (parent of language subdir)
            global_personality_dir = os.path.join(base_dir, 'personalities', personality_name)
            avatar_extensions = ['.png', '.webp', '.jpg', '.jpeg']
            for ext in avatar_extensions:
                avatar_source = os.path.join(global_personality_dir, f'avatar{ext}')
                avatar_target = os.path.join(target_dir, f'avatar{ext}')
                if os.path.exists(avatar_source):
                    shutil.copy2(avatar_source, avatar_target)
                    logger.info(f"🖼️ Copied global avatar: avatar{ext}")
            
            # Also copy avatarfull if exists
            for ext in avatar_extensions:
                avatarfull_source = os.path.join(global_personality_dir, f'avatarfull{ext}')
                avatarfull_target = os.path.join(target_dir, f'avatarfull{ext}')
                if os.path.exists(avatarfull_source):
                    shutil.copy2(avatarfull_source, avatarfull_target)
                    logger.info(f"🖼️ Copied global avatarfull: avatarfull{ext}")
        
        # Create or update server_config.json
        # If update_config is True, always update; otherwise only create if doesn't exist
        should_update = update_config or not os.path.exists(server_config_path)
        
        if should_update:
            server_config = {
                "active_personality": personality_name,
                "language": language
            }
            with open(server_config_path, 'w', encoding='utf-8') as f:
                json.dump(server_config, f, indent=2, ensure_ascii=False)
            action = "Updated" if update_config and os.path.exists(server_config_path) else "Created"
            logger.info(f"✅ {action} server_config.json with active_personality: {personality_name}, language: {language}")
        else:
            logger.info(f"✅ Preserved existing server_config.json")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error copying personality to server {server_id}: {e}")
        return False


def get_server_personality_dir(server_id: str, personality_name: str = None) -> str:
    """
    Get the server-specific personality directory path.
    
    Returns the path to the server's personality copy if it exists at
    databases/<server_id>/<personality_name>/. This is used for per-server personality evolution.
    
    Args:
        server_id: Discord guild ID
        personality_name: Name of personality folder (e.g., "putre(english)")
        
    Returns:
        str: Path to server-specific personality directory, or None if not exists
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        
        # Get personality name from server-specific config if not provided
        if personality_name is None:
            # First try server-specific config (for runtime personality changes)
            server_config_path = os.path.join(base_dir, 'databases', server_id, 'server_config.json')
            if os.path.exists(server_config_path):
                try:
                    with open(server_config_path, encoding='utf-8') as f:
                        server_config = json.load(f)
                    personality_name = server_config.get('active_personality')
                    if personality_name:
                        logger.debug(f"Using active_personality from server_config: {personality_name}")
                except Exception as e:
                    logger.warning(f"Could not read server_config.json: {e}")
            
            # Fall back to agent_config.json (for initial setup)
            if personality_name is None:
                config_path = os.path.join(base_dir, 'agent_config.json')
                with open(config_path, encoding='utf-8') as f:
                    config = json.load(f)
                personality_path = config.get('personality', 'personalities/putre(english)/personality.json')
                personality_name = os.path.basename(os.path.dirname(personality_path))
        
        # Check the server-specific personality location
        server_dir = os.path.join(base_dir, 'databases', server_id, personality_name)
        if os.path.exists(server_dir) and os.path.exists(os.path.join(server_dir, 'personality.json')):
            return server_dir
        
        return None
        
    except Exception as e:
        logger.warning(f"Could not get server personality directory: {e}")
        return None


def update_personality_files(server_id: str, personality_name: str, language: str = None) -> bool:
    """
    Update JSON config files for an existing server-specific personality.
    
    When changing personalities, call this to refresh descriptions.json,
    personality.json, prompts.json, etc. from the global personality directory.
    
    New structure: copies from personalities/<name>/<language>/
    
    Args:
        server_id: Discord guild ID
        personality_name: Name of the personality folder (e.g., "rab")
        language: IETF BCP 47 language code. If None, reads from server_config.json
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import shutil
        
        base_dir = os.path.dirname(os.path.dirname(__file__))
        
        # Get language from server_config.json if not provided
        if language is None:
            server_config_path = os.path.join(base_dir, 'databases', server_id, 'server_config.json')
            if os.path.exists(server_config_path):
                try:
                    with open(server_config_path, encoding='utf-8') as f:
                        server_config = json.load(f)
                    language = server_config.get('language', 'en-US')
                except Exception as e:
                    logger.warning(f"Could not read language from server_config.json: {e}")
                    language = 'en-US'
            else:
                language = 'en-US'
        
        # New structure: source is personalities/<name>/<language>/
        source_dir = os.path.join(base_dir, 'personalities', personality_name, language)
        target_dir = os.path.join(base_dir, 'databases', server_id, personality_name)
        
        # Fallback: if language subdirectory doesn't exist, try old structure
        if not os.path.exists(source_dir):
            old_source_dir = os.path.join(base_dir, 'personalities', personality_name)
            if os.path.exists(old_source_dir):
                logger.warning(f"⚠️ Language subdirectory not found: {source_dir}")
                logger.info(f"📁 Falling back to old structure: {old_source_dir}")
                source_dir = old_source_dir
            else:
                logger.error(f"❌ Source personality not found: {source_dir}")
                return False
        
        # Check if target exists
        if not os.path.exists(target_dir):
            logger.warning(f"Target directory doesn't exist: {target_dir}")
            return False
        
        # Update JSON and config files (not .db files)
        updated_count = 0
        for item in os.listdir(source_dir):
            # Skip database files and directories
            if item.endswith('.db'):
                continue
                
            source_item = os.path.join(source_dir, item)
            target_item = os.path.join(target_dir, item)
            
            if os.path.isdir(source_item):
                # Remove old directory and copy new one
                if os.path.exists(target_item):
                    shutil.rmtree(target_item)
                shutil.copytree(source_item, target_item)
                logger.info(f"📂 Updated directory: {item}")
                updated_count += 1
            else:
                # Copy file (overwrites if exists)
                shutil.copy2(source_item, target_item)
                logger.info(f"📄 Updated file: {item}")
                updated_count += 1
        
        # Also copy avatar from global personality root (not language subdir)
        global_personality_dir = os.path.join(base_dir, 'personalities', personality_name)
        avatar_extensions = ['.png', '.webp', '.jpg', '.jpeg']
        for ext in avatar_extensions:
            for prefix in ['avatar', 'avatarfull']:
                avatar_source = os.path.join(global_personality_dir, f'{prefix}{ext}')
                avatar_target = os.path.join(target_dir, f'{prefix}{ext}')
                if os.path.exists(avatar_source):
                    shutil.copy2(avatar_source, avatar_target)
                    logger.info(f"🖼️ Updated avatar: {prefix}{ext}")
                    updated_count += 1
        
        logger.info(f"✅ Updated {updated_count} files for personality {personality_name} (language: {language})")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error updating personality files: {e}")
        return False


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


async def initialize_server_complete(guild, agent_config: dict = None, is_startup: bool = False, language: str = None) -> bool:
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
        language: IETF BCP 47 language code (e.g., "es-ES", "en-US") for personality selection
        
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
    
    logger.info(f"🔥 ENTER initialize_server_complete for '{guild_name}' (language={language})")
    
    if is_startup:
        logger.info(f"🚀 Initializing server on startup: '{guild_name}' ({server_key})")
        # Set as active server (only during startup)
        set_current_server(server_key)
    else:
        logger.info(f"🏰 Initializing new guild: '{guild_name}' ({server_key})")
    
    success_count = 0
    total_count = 0
    
    # 0. Copy personality files to server-specific directory (first-time only)
    total_count += 1
    logger.info(f"📁 Setting up server-specific personality for {guild_name}")
    
    # Use provided language or detect from server config
    if language is None:
        try:
            from discord_bot.canvas.server_config import get_server_language
            language = get_server_language(server_key)
            logger.info(f"🌐 Using detected language '{language}' for personality setup")
        except Exception as e:
            logger.warning(f"⚠️ Could not detect language, using default: {e}")
            language = "en-US"
    
    personality_copy_success = copy_personality_to_server(server_key, language=language, update_config=True)
    if personality_copy_success:
        logger.info(f"✅ Server-specific personality ready for {guild_name}")
        success_count += 1
    else:
        logger.warning(f"⚠️ Personality copy failed for {guild_name}, will use global personality")
    
    # 0.5. Sync bot identity (nickname + avatar) to server personality
    try:
        from discord_bot.discord_utils import sync_bot_identity_to_server_personality
        identity_result = await sync_bot_identity_to_server_personality(guild)
        
        if identity_result['success']:
            changes = []
            if identity_result['nickname_changed']:
                changes.append("nickname")
            if identity_result['avatar_changed']:
                changes.append("avatar")
            
            if changes:
                logger.info(f"✅ Bot identity synced for server '{guild_name}': {', '.join(changes)} updated")
            else:
                logger.info(f"✅ Bot identity already correct for server '{guild_name}'")
        else:
            logger.warning(f"⚠️ Could not sync bot identity for '{guild_name}': {', '.join(identity_result['errors'])}")
    except Exception as e:
        logger.warning(f"⚠️ Error syncing bot identity for '{guild_name}': {e}")
    
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
    
    # Delete old personality database files that are no longer needed
    try:
        delete_old_personality_databases(server_key)
    except Exception as e:
        logger.warning(f"⚠️ Could not delete old personality databases for '{guild_name}': {e}")
    
    return success_count == total_count


def delete_old_personality_databases(server_id: str):
    """
    Delete old personality database files for a server.
    
    When a personality changes, the old database file (agent_<old>.db) becomes
    orphaned. This function deletes those orphaned files to prevent confusion
    and wasted disk space.
    
    Args:
        server_id: Discord guild ID
    """
    try:
        from pathlib import Path
        from agent_db import get_personality_name
        
        server_dir = Path("databases") / server_id
        if not server_dir.exists():
            return
        
        # Get current personality name
        current_personality = get_personality_name(server_id).lower()
        current_db_name = f"agent_{current_personality}.db"
        
        # Find all agent_*.db files
        agent_dbs = list(server_dir.glob("agent_*.db"))
        
        deleted_count = 0
        for db_path in agent_dbs:
            if db_path.name == current_db_name:
                continue  # Skip current personality database
            
            # Delete old personality database file
            try:
                db_path.unlink()
                logger.info(
                    f"🗑️ [CLEANUP] Server {server_id}: Deleted old personality database: {db_path.name}"
                )
                deleted_count += 1
            except Exception as e:
                logger.warning(f"⚠️ Could not delete old database {db_path}: {e}")
        
        if deleted_count > 0:
            logger.info(f"🗑️ [CLEANUP] Server {server_id}: Deleted {deleted_count} old personality database(s)")
            
    except Exception as e:
        logger.warning(f"⚠️ Error in delete_old_personality_databases for server {server_id}: {e}")
