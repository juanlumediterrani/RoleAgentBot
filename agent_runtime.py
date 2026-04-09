import json
import os
from datetime import date

from dotenv import load_dotenv
from groq import Groq
try:
    from mistralai.client import Mistral
    MISTRAL_AVAILABLE = True
except ImportError:
    MISTRAL_AVAILABLE = False

from agent_db import get_active_server_id, increment_fatigue_count, get_fatigue_stats
from agent_logging import get_logger

load_dotenv()
logger = get_logger('agent_runtime')

_BASE_DIR = os.path.dirname(__file__)
_AGENT_CONFIG_PATH = os.path.join(_BASE_DIR, "agent_config.json")

with open(_AGENT_CONFIG_PATH, encoding="utf-8") as file_handle:
    AGENT_CFG = json.load(file_handle)

PERSONALITY_RELATIVE_PATH = AGENT_CFG.get("personality", "personalities/default.json")
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


def get_personality_directory() -> str:
    """
    Get the personality directory, checking for server-specific copy first.
    
    Returns the server-specific personality directory if it exists,
    otherwise falls back to the global personality directory.
    """
    server_id = get_active_server_id()
    if server_id:
        try:
            from discord_bot.db_init import get_server_personality_dir
            server_dir = get_server_personality_dir(server_id)
            if server_dir:
                return server_dir
        except Exception as e:
            logger.warning(f"Could not get server personality directory: {e}")
    
    # Fall back to global personality directory
    return _PERSONALITY_DIR


def get_personality_file_path(filename: str) -> str:
    """
    Get the full path to a personality file, checking server-specific copy first.
    
    This is a convenience function for role files that need to access
    personality files like answers.json, descriptions.json, etc.
    
    Args:
        filename: Name of the file (e.g., "answers.json", "descriptions.json")
        
    Returns:
        str: Full path to the personality file
    """
    personality_dir = get_personality_directory()
    return os.path.join(personality_dir, filename)


def get_daily_usage(personality_name: str, user_id: str = None, user_name: str = None) -> int:
    """Get daily usage from database."""
    if _SIMULATION_MODE:
        return 0

    server_id = get_active_server_id()
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


def increment_usage(personality_name: str, user_id: str = None, user_name: str = None) -> int:
    """Increment usage counter in database."""
    if _SIMULATION_MODE:
        return 1

    server_id = get_active_server_id()
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
