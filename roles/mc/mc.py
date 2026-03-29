import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from agent_logging import get_logger
from agent_engine import PERSONALITY
from db_role_mc import get_mc_db_instance
from agent_db import get_active_server_name

logger = get_logger('mc')

# Mission configuration
MISSION_CONFIG = {
    "name": "mc"
}

def get_mc_system_prompt():
    """Get system prompt from personality or fallback to English."""
    try:
        role_prompts = PERSONALITY.get("roles", {})
        return role_prompts.get("mc", {}).get("active_duty", "ACTIVE MISSION - MC (MASTER OF CEREMONIES): You are the MC, the Master of Ceremonies for music. Your mission is to control music on Discord servers. You are an expert DJ who knows all genres and always keeps the party active with the best songs.")
    except Exception:
        return "ACTIVE MISSION - MC (MASTER OF CEREMONIES): You are the MC, the Master of Ceremonies for music. Your mission is to control music on Discord servers. You are an expert DJ who knows all genres and always keeps the party active with the best songs."

# English fallback role description
MC_ROLE_ENGLISH = (
    "You are the MC (Master of Ceremonies), the ultimate Discord DJ. Your mission is to control the music on the server, "
    "keeping the energy high and the party active. You are an expert in all musical genres and always know which song to play next. "
    "You manage the queue, handle requests, and keep the dance floor packed. You speak with enthusiasm and energy, "
    "using music emojis 🎵🎧🎶. Your main objective is to maintain the perfect atmosphere and keep everyone entertained."
)

# Use English fallback by default
MC_ROLE_DEFAULT = MC_ROLE_ENGLISH


async def mc_task():
    """Execute MC role tasks."""
    logger.info("🎵 Starting MC role tasks...")
    
    # Get active server from environment or fallback
    server_name = get_active_server_name()
    if not server_name:
        logger.warning("🎵 No active server found, MC tasks limited")
        return
    
    try:
        db_mc = get_mc_db_instance(server_name)
        
        # Clean up old queue entries (maintenance task)
        cleaned_count = db_mc.limpiar_cola_antigua()
        if cleaned_count > 0:
            logger.info(f"🎵 Cleaned {cleaned_count} old queue entries")
        
        # Clean up old history entries (maintenance task)
        cleaned_history = db_mc.limpiar_historial_antiguo()
        if cleaned_history > 0:
            logger.info(f"🎵 Cleaned {cleaned_history} old history entries")
        
        # Get current statistics
        stats = db_mc.obtener_estadisticas()
        logger.info(f"📊 MC Stats - Playlists: {stats.get('playlists_total', 0)}, "
                   f"Queue: {stats.get('queue_total', 0)}, History: {stats.get('historial_total', 0)}")
        
    except Exception as e:
        logger.exception(f"🎵 Error in MC maintenance tasks: {e}")
    
    logger.info("✅ MC role tasks completed")


async def main():
    logger.info("🎵 MC started...")
    await mc_task()


if __name__ == "__main__":
    asyncio.run(main())
