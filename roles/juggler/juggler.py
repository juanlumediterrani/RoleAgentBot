import sys
import os
import json
import importlib.util
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from agent_logging import get_logger
from agent_engine import PERSONALITY

logger = get_logger('juggler')

# Role configuration
ROLE_CONFIG = {
    "name": "juggler",
    "description": "Role specialized in juggling multiple tasks and entertaining the clan",
    "subroles": []  # Subroles will be loaded dynamically
}

_JUGGLER_DIR = os.path.dirname(os.path.abspath(__file__))


def get_juggler_system_prompt():
    """Get system prompt from personality or fallback to English."""
    try:
        role_prompts = PERSONALITY.get("roles", {})
        return role_prompts.get("juggler", {}).get("active_duty", "ACTIVE ROLE - JUGGLER: You are the juggler of the camp, keeping multiple tasks in balance and entertaining the clan with your skills.")
    except Exception:
        return "ACTIVE ROLE - JUGGLER: You are the juggler of the camp, keeping multiple tasks in balance and entertaining the clan with your skills."


def get_juggler_message(key):
    """Get customized messages for the juggler role from personality."""
    return f"🤹 {key}"


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


# Load subrole task functions dynamically
_subrole_tasks = {}

def load_juggler_subroles():
    """Load all available subroles for juggler."""
    global _subrole_tasks
    
    subroles_dir = os.path.join(_JUGGLER_DIR, "subroles")
    if not os.path.exists(subroles_dir):
        logger.info("🤹 No subroles directory found for juggler")
        return
    
    for subrole_name in os.listdir(subroles_dir):
        subrole_path = os.path.join(subroles_dir, subrole_name)
        if os.path.isdir(subrole_path):
            # Load the subrole task function
            task_file = os.path.join(subrole_path, f"{subrole_name}.py")
            task_func = _load_subrole_function(task_file, f"{subrole_name}_task")
            if task_func:
                _subrole_tasks[subrole_name] = task_func
                logger.info(f"🤹 Loaded subrole: {subrole_name}")


async def juggler_task():
    """Execute all juggler subrole tasks."""
    logger.info("🤹 Starting juggler role tasks...")
    
    # Load subroles dynamically
    load_juggler_subroles()
    
    # Execute each loaded subrole task
    for subrole_name, task_func in _subrole_tasks.items():
        try:
            await task_func()
        except Exception as e:
            logger.exception(f"❌ Error in {subrole_name} task: {e}")
    
    logger.info("✅ Juggler role tasks completed")
