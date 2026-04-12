"""
Greet behavior module - handles presence-based greetings when users come online.
Extracted from agent_discord.py for better modularity.
"""

import time
import discord
import asyncio
from agent_logging import get_logger
from agent_mind import call_llm, _build_conversation_user_prompt, _build_prompt_memory_block, _build_prompt_relationship_block, _build_prompt_last_interactions_block
from agent_engine import _build_system_prompt, _get_personality
from discord_bot.discord_utils import get_greeting_enabled, get_server_key, get_db_for_server
from behavior.db_behavior import get_behavior_db_instance

logger = get_logger('greet_behavior')

# Track last greetings per user to avoid spam
_last_greetings = {}

async def _has_unreplied_greeting_any_server(user_id: str) -> bool:
    """
    Check if user has an unreplied greeting in ANY server database.
    
    Args:
        user_id: Discord user ID to check
        
    Returns:
        True if user has unreplied greeting in any server, False otherwise
    """
    try:
        # Import here to avoid circular imports
        from agent_db import get_all_server_keys
        from behavior.db_behavior import get_behavior_db_instance
        
        # Get all server keys
        server_keys = await asyncio.to_thread(get_all_server_keys)
        
        # Check each server's behavior database
        for server_key in server_keys:
            behavior_db = get_behavior_db_instance(server_key)
            greeting_status = await asyncio.to_thread(
                behavior_db.get_last_greeting_status, 
                user_id, 
                "any_guild"  # Use special marker to check across all guilds in this server
            )
            
            if greeting_status.get('has_unreplied_greeting', False):
                logger.info(f"Found unreplied greeting for user {user_id} in server {server_key}")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error checking unreplied greetings across servers for {user_id}: {e}")
        # If we can't check properly, err on the side of not sending duplicate greetings
        return False

def build_greeting_prompt(user_display_name: str, user_id: str, guild) -> str:
    """
    Build a comprehensive contextual prompt for user greetings.
    
    Args:
        user_display_name: Display name of the user being greeted
        user_id: Discord user ID
        guild: Discord guild object
        
    Returns:
        Comprehensive contextual prompt with memory, relationship, and interaction history
    """
    server_name = get_server_key(guild)

    # Get greeting configuration from server-specific personality
    server_id = str(guild.id) if guild else None
    personality = _get_personality(server_id) if server_id else _get_personality()
    greetings_cfg = personality.get("behaviors", {}).get("greetings", {})
    task_template = greetings_cfg.get("task", "Greet {username} that is already connected to the server.")
    golden_rules = greetings_cfg.get("golden_rules", [])
    response_title = greetings_cfg.get("response_title", "## WRITE ONLY THE GREET IN THE WORDS OF THE PERSONALITY:")
    
    # Build individual blocks using specific functions
    memory_block = _build_prompt_memory_block(server=server_name)
    relationship_block = _build_prompt_relationship_block(
        user_id=user_id,
        user_name=user_display_name,
        server=server_name
    )
    interactions_block = _build_prompt_last_interactions_block(
        user_id=user_id,
        server=server_name
    )
    
    # Format the task with username
    task = task_template.format(username=user_display_name)
    
    # Build the complete prompt structure
    prompt_sections = [
        memory_block,
        relationship_block,
        interactions_block,
        "---",  # Separator
        task,  # Task from prompts.json
        "\n".join(golden_rules),  # Golden rules from prompts.json
        response_title  # Response title from prompts.json
    ]
    
    # Filter out empty sections
    non_empty_sections = [section for section in prompt_sections if section and section.strip()]
    
    return "\n\n".join(non_empty_sections)

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
    
    # Rate limiting - 1 hour between greetings per user (across all servers)
    current_time = time.time()
    last_greeting_key = f"presence_greeting_{after.id}"  # User-only key for cross-server tracking
    
    # Check both in-memory cache and database for recent greetings
    if current_time - _last_greetings.get(last_greeting_key, 0) < 3600:
        logger.info(f"Presence greeting skipped due to cooldown for user={after.name} guild={after.guild.name}")
        return
    
    # Additional check: prevent multiple greetings within 10 seconds
    if current_time - _last_greetings.get(f"{last_greeting_key}_recent", 0) < 10:
        logger.info(f"Presence greeting skipped due to recent duplicate prevention for user={after.name}")
        return
    
    try:
        # Check if user has an unreplied greeting from ANY server
        server_name = get_server_key(after.guild)
        
        # Check across all server databases for unreplied greetings
        if await _has_unreplied_greeting_any_server(after.id):
            logger.info(f"Presence greeting skipped for {after.name} - user has unreplied greeting from another server")
            return
        
        # Build comprehensive contextual prompt for greeting
        greeting_prompt = build_greeting_prompt(after.display_name, after.id, after.guild)

        # Build system instruction for call_llm (server-specific personality)
        from agent_engine import _build_system_prompt
        server_id = str(after.guild.id) if after.guild else None
        server_personality = _get_personality(server_id) if server_id else _get_personality()
        system_instruction = _build_system_prompt(server_personality, server_id)
        
        saludo = await asyncio.to_thread(
            call_llm,
            system_instruction=system_instruction,
            prompt=greeting_prompt,
            async_mode=False,
            call_type="think",
            critical=True,
            logger=logger,
        )
        
        await after.send(f"👋 {saludo}")
        logger.info(f"🔄 Presence DM sent to {after.name}")
        _last_greetings[last_greeting_key] = current_time
        _last_greetings[f"{last_greeting_key}_recent"] = current_time
        
        # Record greeting in behavior database for reply tracking
        behavior_db = get_behavior_db_instance(server_name)
        await asyncio.to_thread(
            behavior_db.record_greeting_sent,
            after.id, after.name, after.guild.id, saludo, 'presence'
        )
        
        # Register interaction in database
        try:
            db_instance = get_db_for_server(after.guild)
            personality = _get_personality(server_id) if server_id else _get_personality()
            greetings_cfg = personality.get("behaviors", {}).get("greetings", {})
            interaction_message = greetings_cfg.get("interaction_message", "User went from offline to online (DM greeting)")
            await asyncio.to_thread(
                db_instance.register_interaction,
                after.id, after.name, "PRESENCE_DM",
                interaction_message,
                None, after.guild.id,
                metadata={"response": saludo, "greeting": saludo, "respuesta": saludo, "saludo": saludo}
            )
        except Exception as db_error:
            logger.warning(f"Could not register interaction in database: {db_error}")
            # Don't send fallback greeting - we already sent the main greeting
            pass
        
        return  # Exit after successful greeting to prevent fallback
        
    except discord.errors.Forbidden as e:
        logger.warning(f"Cannot DM presence greeting to {after.name} (Forbidden): {e}")
        fallback_msg = presence_cfg.get("fallback", "Welcome back!")
        # Replace placeholder in fallback message
        fallback_msg = fallback_msg.format(user_name=after.display_name)
        try:
            await after.send(f"👋 {fallback_msg}")
            # Set cooldown and record greeting for fallback too
            _last_greetings[last_greeting_key] = current_time
            _last_greetings[f"{last_greeting_key}_recent"] = current_time
            behavior_db = get_behavior_db_instance(server_name)
            await asyncio.to_thread(
                behavior_db.record_greeting_sent,
                after.id, after.name, after.guild.id, fallback_msg, 'presence'
            )
        except Exception:
            pass
    
    except Exception as e:
        logger.error(f"Error greeting presence of {after.name}: {e}")
        fallback_msg = presence_cfg.get("fallback", "Welcome back!")
        # Replace placeholder in fallback message
        fallback_msg = fallback_msg.format(user_name=after.display_name)
        try:
            await after.send(f"👋 {fallback_msg}")
            # Set cooldown and record greeting for fallback too
            _last_greetings[last_greeting_key] = current_time
            _last_greetings[f"{last_greeting_key}_recent"] = current_time
            behavior_db = get_behavior_db_instance(server_name)
            await asyncio.to_thread(
                behavior_db.record_greeting_sent,
                after.id, after.name, after.guild.id, fallback_msg, 'presence'
            )
        except Exception:
            pass

def clear_greeting_cache():
    """Clear the greeting cache - useful for testing or resets."""
    global _last_greetings
    _last_greetings.clear()
    logger.info("Greeting cache cleared")
