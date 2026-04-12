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

logger = get_logger('server_config')

# Thread-safe lock for file operations
_lock = threading.Lock()

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
            
            # Map detected locale to available languages
            detected_lower = detected.lower()
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
