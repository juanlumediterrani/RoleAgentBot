"""
Poetry Messages Module
Personality-aware messages for the Poetry subrole.
"""

import discord
from agent_logging import get_logger
from agent_engine import _get_personality_descriptions

logger = get_logger('juggler_poetry_messages')


def get_poetry_message(server_id: str, key: str, **kwargs) -> str:
    """
    Get a poetry-related message from personality descriptions.

    Args:
        server_id: Server ID for server-specific personality
        key: Message key (e.g., 'title', 'description', 'error_target_invalid')
        **kwargs: Format parameters for the message

    Returns:
        Message string with placeholders filled, or fallback if not found
    """
    try:
        descriptions = _get_personality_descriptions(server_id)
        poetry_messages = descriptions.get("role_descriptions", {}).get("juggler", {}).get("poetry", {})
        
        message = poetry_messages.get(key, "")
        
        if message:
            try:
                return message.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing format key {e} in poetry message '{key}'")
                return message
        
        # Fallback messages
        fallbacks = {
            "title": "📝 Poetry",
            "description": "Request a poem dedicated to another user.",
            "personality_embed_description": "A special dedication has been crafted for you.",
            "error_target_invalid": "❌ Invalid target user",
            "error_dedication_too_long": "❌ Dedication too long (max 150 chars)",
            "error_fatigue_limit": "❌ Fatigue limit reached",
            "error_banker_charge": "❌ Insufficient balance (1xTAE required)",
            "error_llm_failed": "❌ Failed to generate poem",
            "preview_title": "📝 Poem Preview",
            "preview_description": "Review the poem before sending",
            "button_confirm": "✅ Send",
            "button_cancel": "❌ Cancel",
            "success_sent": "✅ Poem sent to {target}",
            "success_cancelled": "❌ Poem cancelled",
            "dm_disabled_notice": "⚠️ Target has DMs disabled. Here is the poem to send manually:",
            "dm_disabled_offer": "You can copy and send it to them yourself.",
            "error_modal_belongs_to_another": "❌ This modal belongs to another user.",
            "error_failed_preview_dm": "❌ Failed to send preview DM.",
            "error_server_only": "❌ This option is only available in a server.",
            "error_unknown_action": "❌ Unknown action: {action}",
            "error_generic": "❌ Error: {error}"
        }
        
        fallback = fallbacks.get(key, "")
        if fallback:
            try:
                return fallback.format(**kwargs)
            except KeyError:
                return fallback
        
        return key
        
    except Exception as e:
        logger.error(f"Error getting poetry message '{key}': {e}")
        return key


def format_poem_embed(poem: str, sender_name: str, target_name: str, personality_name: str) -> discord.Embed:
    """
    Format the poem embed for Discord.

    Args:
        poem: The generated poem text
        sender_name: Name of the sender
        target_name: Name of the target user
        personality_name: Name of the personality

    Returns:
        Discord embed object
    """
    embed = discord.Embed(
        title=f"📝 A Poem for {target_name}",
        description=poem
    )
    embed.set_footer(text=f"From: {sender_name}")
    return embed


def format_personality_embed(personality_name: str, avatar_url: str = None, server_id: str = None) -> discord.Embed:
    """
    Format the personality embed with nickname and avatar.

    Args:
        personality_name: Name of the personality
        avatar_url: URL of the personality's avatar
        server_id: Server ID for server-specific personality descriptions

    Returns:
        Discord embed object
    """
    description = get_poetry_message(server_id, "personality_embed_description") if server_id else "A special dedication has been crafted for you."
    embed = discord.Embed(description=description)
    embed.set_author(name=personality_name)
    
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    
    return embed
