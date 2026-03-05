"""
Dynamic loading of Discord commands for roles.
Each role exposes a register_*_commands(bot, personality) function in its *_discord.py file.
"""

import importlib
import os
import sys

# Add parent directory to Python path to import root modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_logging import get_logger
from discord_bot.discord_utils import is_role_enabled_check

logger = get_logger('role_loader')

# Role module registry — canonical English names only
ROLE_REGISTRY = {
    "news_watcher": ("roles.news_watcher.news_watcher_discord", "register_news_watcher_commands"),
    "treasure_hunter": ("roles.treasure_hunter.treasure_hunter_discord", "register_treasure_hunter_commands"),
    "trickster": ("roles.trickster.trickster_discord", "register_trickster_commands"),
    "banker": ("roles.banker.banker_discord", "register_banker_commands"),
}

# MC is always registered (does not depend on enabled in the same way)
MC_REGISTRY = ("roles.mc.mc_discord", "register_mc_commands")


def _try_register_role(bot, module_path, func_name, personality, agent_config):
    """Try to import and register a role. Returns True on success."""
    try:
        module = importlib.import_module(module_path)
        register_func = getattr(module, func_name)
        register_func(bot, personality, agent_config)
        return True
    except ImportError as e:
        logger.warning(f"Module {module_path} not available: {e}")
        return False
    except Exception as e:
        logger.error(f"Error registering {module_path}: {e}")
        return False


async def register_all_role_commands(bot, agent_config, personality):
    """Register commands for all enabled roles in agent_config.json."""
    logger.info("Checking enabled roles for command registration")

    # MC is always registered first
    mc_module, mc_func = MC_REGISTRY
    if _try_register_role(bot, mc_module, mc_func, personality, agent_config):
        logger.info("🎵 MC registered successfully")
    else:
        logger.warning("🎵 MC not available")

    # Register enabled roles
    registered = []
    for role_name, (module_path, func_name) in ROLE_REGISTRY.items():
        if is_role_enabled_check(role_name, agent_config):
            logger.info(f"🎭 Role {role_name} enabled, registering commands...")
            if _try_register_role(bot, module_path, func_name, personality, agent_config):
                registered.append(role_name)
            else:
                logger.warning(f"🎭 Role {role_name} enabled but commands could not be registered")
        else:
            logger.info(f"💤 Role {role_name} disabled")

    logger.info(f"Registration complete: {len(registered)} active roles — {', '.join(registered) if registered else 'none'}")


async def register_single_role(bot, role_name, agent_config, personality):
    """Register commands for a specific role (for dynamic activation)."""
    if role_name not in ROLE_REGISTRY:
        logger.warning(f"Role {role_name} has no Discord command registry")
        return False

    module_path, func_name = ROLE_REGISTRY[role_name]
    if _try_register_role(bot, module_path, func_name, personality, agent_config):
        logger.info(f"🎭 Commands for {role_name} registered dynamically")
        return True
    return False
