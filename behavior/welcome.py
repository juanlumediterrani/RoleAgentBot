"""
Welcome behavior module - handles new member welcome messages.
Extracted from agent_discord.py for better modularity.
"""

import discord
import asyncio
from agent_logging import get_logger
from agent_mind import call_llm, _build_prompt_memory_block
from agent_engine import _build_system_prompt, PERSONALITY
from discord_bot.discord_utils import get_greeting_enabled, get_server_key, get_db_for_server

logger = get_logger('welcome_behavior')

def build_welcome_prompt(user_display_name: str, server_name: str, guild) -> str:
    """
    Build a comprehensive contextual prompt for user welcome messages.
    
    Args:
        user_display_name: Display name of the user being welcomed
        server_name: Server name
        guild: Discord guild object
        
    Returns:
        Comprehensive contextual prompt with memory block and welcome configuration
    """
    # Get welcome configuration from personality
    welcome_cfg = PERSONALITY.get("behaviors", {}).get("welcome", {})
    task_template = welcome_cfg.get("task", "Welcome {username} to the server {server_name}!")
    golden_rules = welcome_cfg.get("golden_rules", [])
    response_title = welcome_cfg.get("response_title", "## WELCOME RESPONSE:")
    
    # Build memory block using specific function
    memory_block = _build_prompt_memory_block(server=get_server_key(guild))
    
    # Format the task with username and server name
    task = task_template.format(username=user_display_name, server_name=server_name)
    
    # Build the complete prompt structure
    prompt_sections = [
        memory_block,  # Memory block only
        "---",  # Separator
        task,  # Task from prompts.json
        "\n".join(golden_rules),  # Golden rules from prompts.json
        response_title  # Response title from prompts.json
    ]
    
    # Filter out empty sections
    non_empty_sections = [section for section in prompt_sections if section and section.strip()]
    
    return "\n\n".join(non_empty_sections)

async def handle_member_join(member, discord_cfg):
    """
    Handle new member join events - send welcome messages.
    
    Args:
        member: discord.Member who joined
        discord_cfg: discord configuration from personality
    """
    if member.bot:
        return
    
    if not get_greeting_enabled(member.guild):
        return
    
    greeting_cfg = discord_cfg.get("member_greeting", {})
    if not greeting_cfg.get("enabled", True):
        return
    
    # Find welcome channel
    welcome_channel_name = greeting_cfg.get("welcome_channel", "general")
    welcome_channel = None
    
    for channel in member.guild.text_channels:
        if channel.name.lower() == welcome_channel_name.lower():
            welcome_channel = channel
            break
    
    if welcome_channel is None and member.guild.text_channels:
        welcome_channel = member.guild.text_channels[0]
    
    if welcome_channel is None:
        logger.warning(f"No suitable welcome channel found for {member.guild.name}")
        return
    
    try:
        server_name = get_server_key(member.guild)
        
        # Build welcome prompt using the new structure
        welcome_prompt = build_welcome_prompt(member.display_name, member.guild.name, member.guild)
        
        # Build system instruction for call_llm
        from agent_engine import _build_system_prompt, PERSONALITY
        system_instruction = _build_system_prompt(PERSONALITY)
        
        # Add public context if needed
        public_suffix = PERSONALITY.get("public_context_suffix", "")
        system_instruction = f"{system_instruction}\n\n {public_suffix}"
        
        saludo = await asyncio.to_thread(
            call_llm,
            system_instruction=system_instruction,
            prompt=welcome_prompt,
            async_mode=False,
            call_type="think",
            critical=True,
            logger=logger,
        )
        
        await welcome_channel.send(f"🎉 {member.mention} {saludo}")
        logger.info(f"👋 New user {member.name} greeted in {member.guild.name}")
        
        # Register interaction in database
        db_instance = get_db_for_server(member.guild)
        welcome_cfg = PERSONALITY.get("behaviors", {}).get("welcome", {})
        interaction_message = welcome_cfg.get("interaction_message", "El usuario se unio al servidor (lo recibiste)")
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            member.id, member.name, "WELCOME",
            interaction_message,
            welcome_channel.id, member.guild.id,
            metadata={"response": saludo, "greeting": saludo, "respuesta": saludo, "saludo": saludo}
        )
        
    except Exception as e:
        logger.error(f"Error greeting {member.name}: {e}")
        fallback_msg = greeting_cfg.get("fallback", "¡Bienvenido al servidor!")
        await welcome_channel.send(f"🎉 {member.mention} {fallback_msg}")

def get_welcome_channel_info(guild, discord_cfg):
    """
    Get information about the welcome channel for a guild.
    
    Args:
        guild: discord.Guild
        discord_cfg: discord configuration from personality
        
    Returns:
        dict with channel info or None if not found
    """
    greeting_cfg = discord_cfg.get("member_greeting", {})
    welcome_channel_name = greeting_cfg.get("welcome_channel", "general")
    
    for channel in guild.text_channels:
        if channel.name.lower() == welcome_channel_name.lower():
            return {
                "channel": channel,
                "name": channel.name,
                "id": channel.id
            }
    
    if guild.text_channels:
        channel = guild.text_channels[0]
        return {
            "channel": channel,
            "name": channel.name,
            "id": channel.id
        }
    
    return None
