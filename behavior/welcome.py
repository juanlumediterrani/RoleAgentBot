server (lo recibiste)")
        await asyncio.to_thread(
            db_instance.register_interaction,
            member.id, member.name, behavior_cfg.get("welcome", True),
            interaction_message,
            welcome_channel.id, member.guild.id,
            metadata={"response": saludo, "greeting": saludo, "respuesta": saludo, "saludo": saludo}
        )
        
        server!")
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
