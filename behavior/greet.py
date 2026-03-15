"""
Greet behavior module - handles presence-based greetings when users come online.
Extracted from agent_discord.py for better modularity.
"""

import time
import discord
import asyncio
from agent_logging import get_logger
from agent_engine import think
from discord_bot.discord_utils import get_greeting_enabled, get_server_key, get_db_for_server

logger = get_logger('greet_behavior')

# Track last greetings per user to avoid spam
_last_greetings = {}

async def handle_presence_update(before, after, discord_cfg, bot_display_name):
    """
    Handle presence updates - greet users when they come online.
    
    Args:
        before: discord.Member before state
        after: discord.Member after state  
        discord_cfg: discord configuration from personality
        bot_display_name: bot's display name
    """
    global _last_greetings
    
    if after.bot:
        return
    
    if not get_greeting_enabled(after.guild):
        return
    
    presence_cfg = discord_cfg.get("member_presence", {})
    if not presence_cfg.get("enabled", True):
        logger.info(f"Presence greetings disabled by config for guild={after.guild.name}")
        return
    
    before_status = before.status if before.status else discord.Status.offline
    after_status = after.status if after.status else discord.Status.offline
    
    # Only greet when going from offline to online
    if before_status != discord.Status.offline or after_status != discord.Status.online:
        return
    
    # Rate limiting - 5 minutes between greetings per user
    current_time = time.time()
    last_greeting_key = f"presence_greeting_{after.id}"
    if current_time - _last_greetings.get(last_greeting_key, 0) < 300:
        logger.info(f"Presence greeting skipped due to cooldown for user={after.name} guild={after.guild.name}")
        return
    
    try:
        server_name = get_server_key(after.guild)
        saludo = await asyncio.to_thread(
            think,
            role_context=after.display_name,
            user_content=after.display_name,
            logger=logger,
            mission_prompt_key="prompt_greet",
            user_id=after.id,
            user_name=after.name,
            server_name=server_name,
            interaction_type="greet",
        )
        
        await after.send(f"👋 {saludo}")
        logger.info(f"🔄 Presence DM sent to {after.name}")
        _last_greetings[last_greeting_key] = current_time
        
        # Register interaction in database
        db_instance = get_db_for_server(after.guild)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            after.id, after.name, "PRESENCE_DM",
            "User went from offline to online (DM greeting)",
            None, after.guild.id,
            metadata={"response": saludo, "greeting": saludo, "respuesta": saludo, "saludo": saludo}
        )
        
    except discord.errors.Forbidden as e:
        logger.warning(f"Cannot DM presence greeting to {after.name} (Forbidden): {e}")
        fallback_msg = presence_cfg.get("fallback", "¡Bienvenido de vuelta!")
        try:
            await after.send(f"👋 {fallback_msg}")
        except Exception:
            pass
    
    except Exception as e:
        logger.error(f"Error greeting presence of {after.name}: {e}")
        fallback_msg = presence_cfg.get("fallback", "¡Bienvenido de vuelta!")
        try:
            await after.send(f"👋 {fallback_msg}")
        except Exception:
            pass

def clear_greeting_cache():
    """Clear the greeting cache - useful for testing or resets."""
    global _last_greetings
    _last_greetings.clear()
    logger.info("Greeting cache cleared")
