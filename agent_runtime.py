import json
import os
from datetime import date

from dotenv import load_dotenv
from groq import Groq

from agent_db import get_active_server_name
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
_SIMULATION_MODE = os.getenv("AGENT_SIMULATION", os.getenv("ROLE_AGENT_SIMULATION", "")).strip() in ("1", "true", "True", "yes")

logger.info(f"🔧 [CONFIG] Simulation mode: {'ENABLED' if _SIMULATION_MODE else 'DISABLED'}")
logger.info("🔧 [CONFIG] Usage counter (path resolved at runtime)")
logger.info(f"🤖 [AI] Groq client initialized: {'✅' if os.getenv('GROQ_API_KEY') else '❌'}")
logger.info(f"🤖 [AI] Gemini client available: {'✅' if os.getenv('GEMINI_API_KEY') else '❌'}")


def get_groq_client():
    return _client_groq


def is_simulation_mode() -> bool:
    return _SIMULATION_MODE


def get_runtime_base_dir() -> str:
    return _BASE_DIR


def get_personality_directory() -> str:
    return _PERSONALITY_DIR


def get_fatigue_path(personality_name: str) -> str:
    """Get the fatigue counter path according to server and personality."""
    server_name = get_active_server_name()
    if not server_name:
        return os.path.join(_BASE_DIR, "fatiga_temp.json")

    normalized_server_name = server_name.lower().replace(' ', '_').replace('-', '_')
    normalized_server_name = ''.join(char for char in normalized_server_name if char.isalnum() or char == '_')
    normalized_personality_name = (personality_name or "unknown").lower()

    fatigue_dir = os.path.join(_BASE_DIR, "fatiga", normalized_server_name)
    os.makedirs(fatigue_dir, exist_ok=True)
    return os.path.join(fatigue_dir, f"{normalized_personality_name}.json")


def get_daily_usage(personality_name: str) -> int:
    if _SIMULATION_MODE:
        return 0

    counter_path = get_fatigue_path(personality_name)
    today = str(date.today())
    if not os.path.exists(counter_path):
        return 0

    try:
        if os.path.getsize(counter_path) == 0:
            return 0
        with open(counter_path, 'r', encoding='utf-8') as file_handle:
            file_content = file_handle.read().strip()
            if not file_content:
                return 0
            data = json.loads(file_content)
            return data.get("peticiones", 0) if data.get("ultima_fecha") == today else 0
    except (json.JSONDecodeError, ValueError, KeyError, OSError, IOError) as e:
        print(f"⚠️ Error reading {counter_path}: {e}. Resetting counter.")
        try:
            if os.path.exists(counter_path):
                os.remove(counter_path)
        except Exception:
            pass
        return 0


def increment_usage(personality_name: str) -> int:
    if _SIMULATION_MODE:
        return 1

    counter_path = get_fatigue_path(personality_name)
    usage = get_daily_usage(personality_name) + 1
    try:
        with open(counter_path, 'w', encoding='utf-8') as file_handle:
            json.dump({"peticiones": usage, "ultima_fecha": str(date.today())}, file_handle)
    except (OSError, IOError) as e:
        print(f"⚠️ Error writing {counter_path}: {e}")
    return usage
