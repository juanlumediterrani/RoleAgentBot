"""Server configuration management for per-server settings (language, personality).

This module integrates with the existing server_config.json system used by the bot.
The server_config.json is stored in: databases/{server_id}/server_config.json

It manages:
- Language/locale preferences (new)
- Active personality (existing, integrated for compatibility)
"""

import json
import os
import threading
from pathlib import Path
from typing import Dict, Optional, Any

from agent_logging import get_logger
from datetime import datetime

logger = get_logger('server_config')

# Thread-safe lock for file operations
_lock = threading.Lock()

def _get_timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.utcnow().isoformat()

# Available languages
AVAILABLE_LANGUAGES = {
    "es-ES": "Español (España)",
    "en-US": "English (United States)",
    "zh-CN": "中文 (简体)",
}

# Default language
DEFAULT_LANGUAGE = "en-US"


def _get_server_config_path(server_id: str) -> Path:
    """Get the path to server_config.json for a specific server.
    
    Uses the same location as the existing system: databases/{server_id}/server_config.json
    """
    base_dir = Path(__file__).parent.parent.parent
    return base_dir / "databases" / server_id / "server_config.json"


def _load_server_config(server_id: str) -> Dict[str, Any]:
    """Load configuration for a specific server from its server_config.json.
    
    Args:
        server_id: Discord server/guild ID
        
    Returns:
        Dict containing server config, or empty dict if not exists
    """
    if not server_id or server_id == "0":
        return {}
    
    config_path = _get_server_config_path(server_id)
    
    if not config_path.exists():
        return {}
    
    try:
        with _lock:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Error loading server_config.json for {server_id}: {e}")
        return {}


def _save_server_config(server_id: str, config: Dict[str, Any]) -> bool:
    """Save configuration for a specific server to its server_config.json.
    
    Args:
        server_id: Discord server/guild ID
        config: Configuration dict to save
        
    Returns:
        True if successful, False otherwise
    """
    if not server_id or server_id == "0":
        logger.warning("Cannot save config for invalid server_id")
        return False
    
    config_path = _get_server_config_path(server_id)
    
    # Ensure directory exists
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"Error creating directory for server {server_id}: {e}")
        return False
    
    try:
        with _lock:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving server_config.json for {server_id}: {e}")
        return False


def get_server_language(server_id: str) -> str:
    """Get the configured language for a server.
    
    Reads from databases/{server_id}/server_config.json
    Falls back to DEFAULT_LANGUAGE if not set.
    
    Args:
        server_id: Discord server/guild ID
        
    Returns:
        Language code (e.g., 'es-ES', 'en-US', 'zh-CN')
    """
    config = _load_server_config(server_id)
    language = config.get("language", DEFAULT_LANGUAGE)
    
    # Validate language is in available list
    if language not in AVAILABLE_LANGUAGES:
        logger.warning(f"Invalid language '{language}' for server {server_id}, using default")
        return DEFAULT_LANGUAGE
    
    return language


def set_server_language(server_id: str, language: str) -> bool:
    """Set the language for a server.
    
    Saves to databases/{server_id}/server_config.json alongside existing data
    like active_personality.
    
    Args:
        server_id: Discord server/guild ID
        language: Language code (must be in AVAILABLE_LANGUAGES)
        
    Returns:
        True if successful, False otherwise
    """
    if language not in AVAILABLE_LANGUAGES:
        logger.error(f"Cannot set invalid language '{language}'")
        return False
    
    if not server_id or server_id == "0":
        logger.warning("Cannot set language for invalid server_id")
        return False
    
    # Load existing config (to preserve other fields like active_personality)
    config = _load_server_config(server_id)
    
    # Update language
    config["language"] = language
    
    # Save back
    success = _save_server_config(server_id, config)
    if success:
        logger.info(f"Updated server {server_id} language to: {language}")
    return success


def get_available_languages() -> Dict[str, str]:
    """Get list of available languages.
    
    Returns:
        Dict mapping language codes to display names
    """
    return AVAILABLE_LANGUAGES.copy()


def detect_and_set_default_language(server_id: str, guild=None) -> str:
    """Detect server language from Discord and return it. Does NOT create server_config.json.
    
    This function uses discord_utils.detect_server_language() to detect the
    server's preferred language. It only updates server_config.json if it already exists.
    The server_config.json creation with both active_personality and language is handled
    exclusively by copy_personality_to_server() during server initialization.
    
    Args:
        server_id: Discord server/guild ID
        guild: Discord guild object (optional, for detection)
        
    Returns:
        The detected language code (does not modify server_config.json if it doesn't exist)
    """
    from pathlib import Path
    
    # Check if server_config.json exists
    config_path = _get_server_config_path(server_id)
    config_exists = config_path.exists()
    
    # Get current language if config exists
    current_lang = DEFAULT_LANGUAGE
    if config_exists:
        current_lang = get_server_language(server_id)
        # If already set to non-default, don't override
        if current_lang != DEFAULT_LANGUAGE:
            logger.debug(f"Server {server_id} already has language set to {current_lang}, preserving")
            return current_lang
    
    # Try to detect from guild
    detected_language = None
    if guild is not None:
        try:
            from discord_bot.discord_utils import detect_server_language
            detected = detect_server_language(guild)

            # Defensive: detect_server_language may, in some discord.py versions,
            # return a Locale enum instead of a str. Coerce before any str op.
            detected_lower = str(detected).lower()
            if "es" in detected_lower:
                detected_language = "es-ES"
            elif "zh" in detected_lower or "cn" in detected_lower:
                detected_language = "zh-CN"
            elif "en" in detected_lower:
                detected_language = "en-US"
            else:
                # Default to en-US for unsupported locales
                detected_language = DEFAULT_LANGUAGE
            
            logger.info(f"Detected language '{detected}' for server {server_id}, mapped to '{detected_language}'")
        except Exception as e:
            logger.warning(f"Error detecting server language: {e}")
    
    # Only update server_config.json if it already exists AND detected language is different from default
    if detected_language and detected_language in AVAILABLE_LANGUAGES:
        if config_exists and detected_language != DEFAULT_LANGUAGE:
            set_server_language(server_id, detected_language)
        return detected_language
    
    return DEFAULT_LANGUAGE


def get_server_config(server_id: str) -> Dict[str, Any]:
    """Get full configuration for a server.
    
    Args:
        server_id: Discord server/guild ID
        
    Returns:
        Dict with all config values (includes active_personality if set)
    """
    return _load_server_config(server_id)


def set_server_config_value(server_id: str, key: str, value: Any) -> bool:
    """Set a specific configuration value for a server.
    
    Generic method to set any config value while preserving existing ones.
    
    Args:
        server_id: Discord server/guild ID
        key: Configuration key
        value: Value to set
        
    Returns:
        True if successful
    """
    if not server_id or server_id == "0":
        return False
    
    config = _load_server_config(server_id)
    config[key] = value
    
    success = _save_server_config(server_id, config)
    if success:
        logger.info(f"Updated server {server_id} config: {key} = {value}")
    return success


# ==================== Roles Configuration ====================

def get_role_config(server_id: str, role_name: str, default_enabled: bool = True) -> Optional[Dict[str, Any]]:
    """Get configuration for a specific role.
    
    Reads from server_config.json["roles"][role_name]
    Falls back to default if not found.
    
    Args:
        server_id: Discord server/guild ID
        role_name: Name of the role
        default_enabled: Default enabled state if role not found
        
    Returns:
        Dict with 'enabled' and 'config' (or 'config_data' for legacy), or None if error
    """
    if not server_id or server_id == "0":
        return None
    
    config = _load_server_config(server_id)
    roles = config.get("roles", {})
    
    if role_name in roles:
        return roles[role_name]
    
    # Return default if role not found
    return {"enabled": default_enabled, "config": None}


def set_role_config(server_id: str, role_name: str, enabled: bool, config_data: Optional[str] = None, role_config_dict: Optional[Dict] = None) -> bool:
    """Set configuration for a specific role.
    
    Saves to server_config.json["roles"][role_name]
    
    Args:
        server_id: Discord server/guild ID
        role_name: Name of the role
        enabled: Whether the role is enabled
        config_data: Optional JSON string with additional config (legacy, for backward compatibility)
        role_config_dict: Optional dict with additional config (preferred, NoSQL structure)
        
    Returns:
        True if successful
    """
    if not server_id or server_id == "0":
        logger.warning("Cannot set role config for invalid server_id")
        return False
    
    config = _load_server_config(server_id)
    
    # Ensure roles section exists
    if "roles" not in config:
        config["roles"] = {}
    
    # Set role configuration
    role_config = {
        "enabled": enabled,
        "updated_at": _get_timestamp()
    }
    
    # Handle config_data (legacy JSON string) or role_config_dict (dict)
    if role_config_dict is not None:
        role_config["config"] = role_config_dict
    elif config_data is not None:
        try:
            # Parse legacy JSON string to dict
            role_config["config"] = json.loads(config_data)
        except json.JSONDecodeError:
            # If parsing fails, keep as string for backward compatibility
            role_config["config_data"] = config_data
    
    config["roles"][role_name] = role_config
    
    success = _save_server_config(server_id, config)
    if success:
        logger.info(f"Updated role {role_name} for server {server_id}: enabled={enabled}")
    return success


def get_all_roles_config(server_id: str) -> Dict[str, Dict[str, Any]]:
    """Get configuration for all roles.
    
    Args:
        server_id: Discord server/guild ID
        
    Returns:
        Dict mapping role names to their config dicts
    """
    if not server_id or server_id == "0":
        return {}
    
    config = _load_server_config(server_id)
    return config.get("roles", {})


def is_role_enabled(server_id: str, role_name: str, default_enabled: bool = True) -> bool:
    """Check if a role is enabled.
    
    Convenience function that returns just the enabled boolean.
    
    Args:
        server_id: Discord server/guild ID
        role_name: Name of the role
        default_enabled: Default if role not found
        
    Returns:
        True if role is enabled
    """
    role_config = get_role_config(server_id, role_name, default_enabled)
    if role_config is None:
        return default_enabled
    return role_config.get("enabled", default_enabled)


def get_role_config_value(server_id: str, role_name: str, key: str, default: Any = None) -> Any:
    """Get a specific value from role config.
    
    Convenience function for accessing nested config values.
    
    Args:
        server_id: Discord server/guild ID
        role_name: Name of the role
        key: Config key to retrieve (supports dot notation for nested keys, e.g., "config.tae")
        default: Default value if key not found
        
    Returns:
        The config value, or default if not found
    """
    role_config = get_role_config(server_id, role_name)
    if role_config is None:
        return default
    
    # Handle dot notation for nested keys
    if "." in key:
        parts = key.split(".")
        value = role_config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        return value
    
    # Simple key lookup
    return role_config.get(key, default)


def set_role_config_value(server_id: str, role_name: str, key: str, value: Any) -> bool:
    """Set a specific value in role config.
    
    Convenience function for updating nested config values.
    
    Args:
        server_id: Discord server/guild ID
        role_name: Name of the role
        key: Config key to set (supports dot notation for nested keys, e.g., "config.tae")
        value: Value to set
        
    Returns:
        True if successful
    """
    if not server_id or server_id == "0":
        logger.warning("Cannot set role config value for invalid server_id")
        return False
    
    config = _load_server_config(server_id)
    
    # Ensure roles section exists
    if "roles" not in config:
        config["roles"] = {}
    
    # Ensure role exists
    if role_name not in config["roles"]:
        config["roles"][role_name] = {"enabled": True, "config": {}, "updated_at": _get_timestamp()}
    
    # Handle dot notation for nested keys
    if "." in key:
        parts = key.split(".")
        target = config["roles"][role_name]
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value
    else:
        config["roles"][role_name][key] = value
    
    # Update timestamp
    config["roles"][role_name]["updated_at"] = _get_timestamp()
    
    success = _save_server_config(server_id, config)
    if success:
        logger.info(f"Updated role config {role_name}.{key} for server {server_id}")
    return success


# ==================== News Watcher Frequency Configuration ====================

def get_news_watcher_frequency(server_id: str, default_hours: int = 1) -> int:
    """Get the configured frequency (in hours) for news watcher on a server.
    
    Reads from server_config.json["roles"]["news_watcher"]["config"]["frequency_hours"]
    Falls back to default if not found.
    
    Args:
        server_id: Discord server/guild ID
        default_hours: Default frequency in hours if not configured
        
    Returns:
        Frequency in hours (integer)
    """
    frequency = get_role_config_value(server_id, "news_watcher", "config.frequency_hours", default=default_hours)
    try:
        return int(frequency)
    except (ValueError, TypeError):
        return default_hours


def set_news_watcher_frequency(server_id: str, frequency_hours: int) -> bool:
    """Set the frequency (in hours) for news watcher on a server.
    
    Saves to server_config.json["roles"]["news_watcher"]["config"]["frequency_hours"]
    
    Args:
        server_id: Discord server/guild ID
        frequency_hours: Frequency in hours (must be positive integer)
        
    Returns:
        True if successful
    """
    if not isinstance(frequency_hours, int) or frequency_hours < 1:
        logger.error(f"Invalid frequency_hours: {frequency_hours} (must be positive integer)")
        return False
    
    return set_role_config_value(server_id, "news_watcher", "config.frequency_hours", frequency_hours)


# ==================== Behaviors Configuration ====================

def get_behavior_config(server_id: str, behavior_name: str, default_enabled: bool = False) -> Optional[Dict[str, Any]]:
    """Get configuration for a specific behavior.
    
    Reads from server_config.json["behaviors"][behavior_name]
    Falls back to default if not found.
    
    Args:
        server_id: Discord server/guild ID
        behavior_name: Name of the behavior (e.g., 'greetings', 'welcome', 'memory')
        default_enabled: Default enabled state if behavior not found
        
    Returns:
        Dict with 'enabled' and 'config', or None if error
    """
    if not server_id or server_id == "0":
        return None
    
    config = _load_server_config(server_id)
    behaviors = config.get("behaviors", {})
    
    if behavior_name in behaviors:
        return behaviors[behavior_name]
    
    # Return default if behavior not found
    return {"enabled": default_enabled, "config": None}


def set_behavior_config(server_id: str, behavior_name: str, enabled: bool, config: Optional[Dict] = None, updated_by: Optional[str] = None) -> bool:
    """Set configuration for a specific behavior.
    
    Saves to server_config.json["behaviors"][behavior_name]
    
    Args:
        server_id: Discord server/guild ID
        behavior_name: Name of the behavior
        enabled: Whether the behavior is enabled
        config: Optional dict with additional config
        updated_by: Optional identifier of who made the change
        
    Returns:
        True if successful
    """
    if not server_id or server_id == "0":
        logger.warning("Cannot set behavior config for invalid server_id")
        return False
    
    config_dict = _load_server_config(server_id)
    
    # Ensure behaviors section exists
    if "behaviors" not in config_dict:
        config_dict["behaviors"] = {}
    
    # Set behavior configuration
    config_dict["behaviors"][behavior_name] = {
        "enabled": enabled,
        "config": config,
        "updated_at": _get_timestamp(),
        "updated_by": updated_by
    }
    
    success = _save_server_config(server_id, config_dict)
    if success:
        logger.info(f"Updated behavior {behavior_name} for server {server_id}: enabled={enabled}")
    return success


def is_behavior_enabled(server_id: str, behavior_name: str, default_enabled: bool = False) -> bool:
    """Check if a behavior is enabled.
    
    Convenience function that returns just the enabled boolean.
    
    Args:
        server_id: Discord server/guild ID
        behavior_name: Name of the behavior
        default_enabled: Default if behavior not found
        
    Returns:
        True if behavior is enabled
    """
    behavior_config = get_behavior_config(server_id, behavior_name, default_enabled)
    if behavior_config is None:
        return default_enabled
    return behavior_config.get("enabled", default_enabled)


def get_all_behaviors_config(server_id: str) -> Dict[str, Dict[str, Any]]:
    """Get configuration for all behaviors.
    
    Args:
        server_id: Discord server/guild ID
        
    Returns:
        Dict mapping behavior names to their config dicts
    """
    if not server_id or server_id == "0":
        return {}
    
    config = _load_server_config(server_id)
    return config.get("behaviors", {})


# ==================== Welcome Helper Functions ====================

def get_welcome_enabled(server_id: str) -> bool:
    """Check if welcome is enabled.
    
    Args:
        server_id: Discord server/guild ID
        
    Returns:
        True if welcome is enabled
    """
    return is_behavior_enabled(server_id, "welcome", default_enabled=False)


def set_welcome_enabled(server_id: str, enabled: bool, updated_by: str = None) -> bool:
    """Set welcome enabled state.
    
    Args:
        server_id: Discord server/guild ID
        enabled: Whether welcome is enabled
        updated_by: Optional identifier of who made the change
        
    Returns:
        True if successful
    """
    config = get_behavior_config(server_id, "welcome")
    existing_config = config.get("config", {}) if config else {}
    return set_behavior_config(server_id, "welcome", enabled, existing_config, updated_by)


def get_welcome_channel(server_id: str) -> Optional[str]:
    """Get the stored welcome channel ID.
    
    Args:
        server_id: Discord server/guild ID
        
    Returns:
        Channel ID string, or None if not set
    """
    config = get_behavior_config(server_id, "welcome")
    if config and config.get("config"):
        return config["config"].get("channel_id")
    return None


def set_welcome_channel(server_id: str, channel_id: str, updated_by: str = None) -> bool:
    """Set the welcome channel ID.
    
    Args:
        server_id: Discord server/guild ID
        channel_id: Discord channel ID
        updated_by: Optional identifier of who made the change
        
    Returns:
        True if successful
    """
    config = get_behavior_config(server_id, "welcome")
    existing_config = config.get("config", {}) if config else {}
    existing_config["channel_id"] = channel_id
    enabled = is_behavior_enabled(server_id, "welcome", default_enabled=False)
    return set_behavior_config(server_id, "welcome", enabled, existing_config, updated_by)


# ==================== Migration Helpers ====================
# Note: SQLite migration helpers removed - all data migrated to NoSQL (role_configs_nosql.py)

def migrate_behaviors_from_sqlite(server_id: str, behavior_db) -> bool:
    """Migrate behaviors configuration from SQLite to server_config.json.
    
    LEGACY: behavior_states table no longer exists (removed).
    Behavior toggles are now managed by server_config.json directly.
    This function is kept for backward compatibility but does nothing.
    
    Args:
        server_id: Discord server/guild ID
        behavior_db: BehaviorDB instance to read from
        
    Returns:
        True (no-op, migration not needed)
    """
    logger.info(f"Behavior migration skipped for server {server_id} - behavior_states table removed, toggles now in server_config.json")
    return True
