import sys
import os
import json
import importlib.util
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from agent_logging import get_logger
from agent_engine import PERSONALITY

logger = get_logger('trickster')

# Mission configuration
MISSION_CONFIG = {
    "name": "trickster",
    "system_prompt_addition": "ACTIVE ROLE - TRICKSTER: You are a master of deception and manipulation. You use your skills to get gold and resources through tricks and scams."
}

# Role configuration
ROLE_CONFIG = {
    "name": "trickster",
    "description": "Role specialized in scams and deceptions to get resources",
    "subroles": ["beggar", "dice_game"]
}

_TRICKSTER_DIR = os.path.dirname(os.path.abspath(__file__))


def get_trickster_system_prompt():
    """Get system prompt from personality or fallback to English."""
    try:
        role_prompts = PERSONALITY.get("roles", {})
        return role_prompts.get("trickster", {}).get("active_duty", "ACTIVE ROLE - TRICKSTER: You are a master of deception and manipulation. You use your skills to get gold and resources through tricks and scams.")
    except Exception:
        return "ACTIVE ROLE - TRICKSTER: You are a master of deception and manipulation. You use your skills to get gold and resources through tricks and scams."


def get_trickster_message(key):
    """Get customized messages for the trickster role from personality."""
    try:
        from agent_runtime import get_personality_file_path
        answers_path = get_personality_file_path("answers.json")
        with open(answers_path, encoding="utf-8") as f:
            messages = json.load(f).get("discord", {}).get("role_messages", {})
        return messages.get(key, f"🎭 {key}")
    except Exception:
        return f"🎭 {key}"


def _load_subrole_function(module_file, func_name):
    """Load a function from a subrole module using importlib.util (no sys.path hacks)."""
    if not os.path.isfile(module_file):
        logger.warning(f"⚠️ Subrole module not found: {module_file}")
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            os.path.splitext(os.path.basename(module_file))[0],
            module_file
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        func = getattr(mod, func_name, None)
        if func is None:
            logger.warning(f"⚠️ Function '{func_name}' not found in {module_file}")
        return func
    except Exception as e:
        logger.warning(f"⚠️ Error loading subrole from {module_file}: {e}")
        return None


# Load subrole task functions
_beggar_task = _load_subrole_function(
    os.path.join(_TRICKSTER_DIR, "subroles", "beggar", "beggar.py"),
    "beggar_task"
)
_dice_game_task = _load_subrole_function(
    os.path.join(_TRICKSTER_DIR, "subroles", "dice_game", "dice_game.py"),
    "dice_game_task"
)


async def trickster_task():
    """Execute all trickster role tasks."""
    logger.info("🎭 Starting trickster role tasks...")

    if _beggar_task:
        try:
            await _beggar_task()
        except Exception as e:
            logger.exception(f"❌ Error in beggar task: {e}")
    else:
        logger.warning("⚠️ Beggar task not available, skipping")

    if _dice_game_task:
        try:
            await _dice_game_task()
        except Exception as e:
            logger.exception(f"❌ Error in dice game task: {e}")
    else:
        logger.warning("⚠️ Dice game task not available, skipping")

    logger.info("✅ Trickster role tasks completed")


async def main():
    logger.info("🎭 Trickster started...")
    await trickster_task()


if __name__ == "__main__":
    asyncio.run(main())
