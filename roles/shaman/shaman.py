import os
import sys

# Ensure project root imports work
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from agent_logging import get_logger
from agent_engine import PERSONALITY
from agent_db import get_server_id

logger = get_logger('shaman')


def get_shaman_system_prompt():
    """Get system prompt from personality or fallback to English."""
    try:
        role_prompts = PERSONALITY.get("roles", {})
        return role_prompts.get("shaman", {}).get("active_duty", "ACTIVE MISSION - SHAMAN: You are the Shaman of the server, the mystical guide. Your mission is to interpret the ancient Nordic runes and provide spiritual guidance to those who seek it.")
    except Exception:
        return ""


async def shaman_task():
    """Execute shaman role tasks."""
    logger.info("🔮 Shaman task started...")


async def main():
    logger.info("🔮 Shaman started...")
    await shaman_task()


if __name__ == "__main__":
    asyncio.run(main())
