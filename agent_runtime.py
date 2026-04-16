import json
import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from groq import Groq
try:
    from mistralai.client import Mistral
    MISTRAL_AVAILABLE = True
except ImportError:
    MISTRAL_AVAILABLE = False

from agent_db import increment_fatigue_count, get_fatigue_stats
from agent_logging import get_logger

load_dotenv()
logger = get_logger('agent_runtime')

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_AGENT_CONFIG_PATH = os.path.join(_BASE_DIR, "agent_config.json")

with open(_AGENT_CONFIG_PATH, encoding="utf-8") as file_handle:
    AGENT_CFG = json.load(file_handle)

_DEFAULT_PERSONALITY = AGENT_CFG.get("default_personality", "rab")
_DEFAULT_LANGUAGE = AGENT_CFG.get("default_language", "en-US")
PERSONALITY_RELATIVE_PATH = f"personalities/{_DEFAULT_PERSONALITY}/{_DEFAULT_LANGUAGE}/personality.json"
_PERSONALITY_PATH = os.path.join(_BASE_DIR, PERSONALITY_RELATIVE_PATH)
_PERSONALITY_DIR = os.path.dirname(_PERSONALITY_PATH)

_client_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))
_client_mistral = Mistral(api_key=os.getenv("MISTRAL_API_KEY")) if MISTRAL_AVAILABLE and os.getenv("MISTRAL_API_KEY") else None
_SIMULATION_MODE = os.getenv("AGENT_SIMULATION", os.getenv("ROLE_AGENT_SIMULATION", "")).strip() in ("1", "true", "True", "yes")

logger.info(f"🔧 [CONFIG] Simulation mode: {'ENABLED' if _SIMULATION_MODE else 'DISABLED'}")
logger.info("🔧 [CONFIG] Usage counter (path resolved at runtime)")
logger.info(f"🤖 [AI] Groq client initialized: {'✅' if os.getenv('GROQ_API_KEY') else '❌'}")
vertex_ai_disabled = os.getenv('DISABLE_VERTEX_AI', '').strip().lower() in ('1', 'true', 'yes')
logger.info(f"🤖 [AI] Vertex AI available: {'✅' if os.getenv('GOOGLE_CLOUD_PROJECT') and not vertex_ai_disabled else '❌'}")
logger.info(f"🤖 [AI] Mistral client available: {'✅' if _client_mistral else '❌'}")


def get_groq_client():
    return _client_groq


def get_mistral_client():
    return _client_mistral


def is_simulation_mode() -> bool:
    return _SIMULATION_MODE


def get_runtime_base_dir() -> str:
    return _BASE_DIR


def get_personality_directory(server_id: str = None) -> str:
    """
    Get the personality directory, checking for server-specific copy first.

    Args:
        server_id: Optional server ID to use explicitly.

    Returns the server-specific personality directory if it exists,
    otherwise falls back to the global personality directory.
    """
    # If server_id is explicitly provided, check for server-specific config first
    if server_id:
        try:
            # First check server_config.json for active_personality and language
            import json
            server_config_path = os.path.join(_BASE_DIR, "databases", server_id, "server_config.json")
            if os.path.exists(server_config_path):
                with open(server_config_path, encoding="utf-8") as f:
                    server_cfg = json.load(f)
                active_personality = server_cfg.get("active_personality")
                language = server_cfg.get("language", "en-US")
                if active_personality:
                    server_personality_dir = os.path.join(_BASE_DIR, "databases", server_id, active_personality)
                    if os.path.exists(os.path.join(server_personality_dir, "personality.json")):
                        logger.debug(f"Using server-specific personality directory: {server_personality_dir}")
                        return server_personality_dir
            
            # Fall back to get_server_personality_dir from db_init
            from discord_bot.db_init import get_server_personality_dir
            server_dir = get_server_personality_dir(server_id)
            if server_dir:
                return server_dir
        except Exception as e:
            logger.debug(f"Could not get server personality directory for {server_id}: {e}")
    
    # Re-read global config to get current personality (not cached)
    try:
        with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        # Use new fields: default_personality and default_language
        default_personality = agent_cfg.get("default_personality", "rab")
        default_language = agent_cfg.get("default_language", "en-US")
        # Construct path with language subdirectory
        personality_rel = f"personalities/{default_personality}/{default_language}/personality.json"
        current_personality_path = os.path.join(_BASE_DIR, personality_rel)
        if os.path.exists(current_personality_path):
            return os.path.dirname(current_personality_path)
    except Exception as e:
        logger.debug(f"Could not read current personality from config: {e}")
    
    # Fall back to cached personality directory
    return _PERSONALITY_DIR


def get_personality_file_path(filename: str, server_id: str = None) -> str:
    """
    Get the full path to a personality file, checking server-specific copy first.
    
    This is a convenience function for role files that need to access
    personality files like answers.json, descriptions.json, etc.
    
    Args:
        filename: Name of the file (e.g., "answers.json", "descriptions.json")
        server_id: Optional server ID for server-specific files
        
    Returns:
        str: Full path to the personality file
    """
    personality_dir = get_personality_directory(server_id)
    return os.path.join(personality_dir, filename)


def get_daily_usage(personality_name: str, user_id: str = None, user_name: str = None, server_id: str = None) -> int:
    """Get daily usage from database."""
    if _SIMULATION_MODE:
        return 0

    if not server_id:
        return 0

    try:
        if user_id:
            # Get specific user stats
            stats = get_fatigue_stats(server_id, user_id)
            return stats.get('daily_requests', 0)
        else:
            # Get server total stats
            server_user_id = f"server_{server_id}"
            stats = get_fatigue_stats(server_id, server_user_id)
            return stats.get('daily_requests', 0)
    except Exception as e:
        logger.warning(f"Error getting daily usage: {e}")
        return 0


def increment_usage(personality_name: str, user_id: str = None, user_name: str = None, server_id: str = None) -> int:
    """Increment usage counter in database."""
    if _SIMULATION_MODE:
        return 1

    if not server_id:
        return 1

    try:
        # Use server_id if no user_id provided (for backward compatibility)
        target_user_id = user_id or f"server_{server_id}"
        target_user_name = user_name or f"Server_{server_id}"
        
        daily, total = increment_fatigue_count(server_id, target_user_id, target_user_name)
        return daily
    except Exception as e:
        logger.warning(f"Error incrementing usage: {e}")
        return 1


# ============================================================================
# UNIVERSAL PERSONALITY FILE LOADER (Hybrid Solution - V2.0)
# ============================================================================

@lru_cache(maxsize=128)
def _load_personality_file_cached(filename: str, server_id: str) -> Dict[str, Any]:
    """
    Cached loader for personality JSON files by server.
    
    Args:
        filename: Name of the personality file (e.g., "answers.json")
        server_id: Server ID for server-specific files
        
    Returns:
        Dict: Loaded JSON content or empty dict if file not found
    """
    try:
        file_path = Path(get_personality_file_path(filename, server_id))
        
        if not file_path.exists():
            logger.debug(f"Personality file not found: {file_path}")
            return {}
        
        # Use pathlib for modern file handling
        return json.loads(file_path.read_text(encoding="utf-8"))
        
    except json.JSONDecodeError as e:
        logger.error(f"Malformed JSON in {filename} for server {server_id}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error loading personality file {filename}: {e}")
        return {}


def get_personality_message(filename: str, key_path: List[str], server_id: str, default: Any = None) -> Any:
    """
    Get a specific value from personality JSON files with caching.
    
    Args:
        filename: Name of the personality file (e.g., "answers.json")
        key_path: List of keys to navigate the JSON structure (e.g., ["discord", "welcome_message"])
        server_id: Server ID for server-specific files
        default: Default value if key not found
        
    Returns:
        Any: The requested value or default
        
    Example:
        welcome_msg = get_personality_message("answers.json", ["discord", "welcome_message"], server_id, "Hello!")
    """
    if not server_id:
        logger.warning(f"No server_id provided for get_personality_message({filename}, {key_path})")
        return default
    
    # Load cached data for this server
    data = _load_personality_file_cached(filename, server_id)
    
    # Navigate through the key path
    for key in key_path:
        if isinstance(data, dict):
            data = data.get(key, {})
        else:
            return default
    
    # Return the value if we found something non-empty, otherwise default
    return data if data != {} else default


def clear_personality_cache():
    """
    Clear the personality file cache.
    
    Useful for hot-reloading configuration files while the bot is running.
    """
    _load_personality_file_cached.cache_clear()
    logger.info("Personality file cache cleared")
