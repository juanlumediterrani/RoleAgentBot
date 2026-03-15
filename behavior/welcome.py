"""
Welcome behavior module - handles new member welcome messages.
Extracted from agent_discord.py for better modularity.
"""

import discord
import asyncio
from agent_logging import get_logger
from agent_engine import think
from discord_bot.discord_utils import get_greeting_enabled, get_server_key, get_db_for_server

logger = get_logger('welcome_behavior')

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
        saludo = await asyncio.to_thread(
            think,
            role_context=member.display_name,
            user_content=member.display_name,
            logger=logger,
            mission_prompt_key="prompt_welcome",
            user_id=member.id,
            user_name=member.name,
            server_name=server_name,
            interaction_type="welcome",
        )
        
        await welcome_channel.send(f"🎉 {member.mention} {saludo}")
        logger.info(f"👋 New user {member.name} greeted in {member.guild.name}")
        
        # Register interaction in database
        db_instance = get_db_for_server(member.guild)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            member.id, member.name, "WELCOME",
            "User joined the server",
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
