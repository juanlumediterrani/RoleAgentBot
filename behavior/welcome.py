"""
Welcome behavior module - handles member join greetings.
Extracted from agent_discord.py for better modularity.
"""

import asyncio
import time
import discord
from agent_logging import get_logger
from agent_mind import call_llm, _build_prompt_memory_block, _build_prompt_relationship_block, _build_prompt_last_interactions_block
from agent_engine import _build_system_prompt, _get_personality
from discord_bot.discord_utils import get_server_key, get_db_for_server
from behavior.db_behavior import get_behavior_db_instance

logger = get_logger('welcome_behavior')

# Global rate limiting for Vertex AI - shared with greet.py
# Minimum seconds between any greeting/welcome LLM calls
_LAST_GLOBAL_WELCOME_TIME = 0
_MIN_SECONDS_BETWEEN_WELCOMES = 3  # Minimum 3 seconds between LLM calls


async def _wait_for_welcome_rate_limit():
    """Ensure minimum delay between welcome messages to avoid Vertex AI saturation."""
    global _LAST_GLOBAL_WELCOME_TIME
    
    current_time = time.time()
    time_since_last = current_time - _LAST_GLOBAL_WELCOME_TIME
    
    if time_since_last < _MIN_SECONDS_BETWEEN_WELCOMES:
        wait_time = _MIN_SECONDS_BETWEEN_WELCOMES - time_since_last
        logger.debug(f"Welcome rate limit: waiting {wait_time:.1f}s before next welcome")
        await asyncio.sleep(wait_time)
    
    _LAST_GLOBAL_WELCOME_TIME = time.time()


async def handle_member_join(member, discord_cfg):
    """
    Handle a new member joining the server - send a welcome message.
    
    Args:
        member: discord.Member - the member who joined
        discord_cfg: discord configuration from personality
    """
    # Apply global rate limiting to prevent Vertex AI saturation
    await _wait_for_welcome_rate_limit()
    
    try:
        # Get welcome channel
        welcome_info = await get_welcome_channel_info(member.guild, discord_cfg)
        if not welcome_info:
            logger.warning(f"No welcome channel found for guild {member.guild.name}")
            return
        
        welcome_channel = welcome_info["channel"]
        server_id = str(member.guild.id)
        server_name = get_server_key(member.guild)
        
        # Check if welcome is enabled
        greeting_cfg = discord_cfg.get("member_greeting", {})
        if not greeting_cfg.get("enabled", True):
            logger.info(f"Welcome messages disabled for guild {member.guild.name}")
            return
        
        # Build welcome prompt
        welcome_prompt = build_welcome_prompt(member.display_name, str(member.id), member.guild)
        
        # Build system instruction
        personality = _get_personality(server_id) if server_id else _get_personality()
        system_instruction = _build_system_prompt(personality, server_id)
        
        # Generate welcome message
        saludo = await asyncio.to_thread(
            call_llm,
            system_instruction=system_instruction,
            prompt=welcome_prompt,
            async_mode=False,
            call_type="think",
            critical=True,
            logger=logger,
        )
        
        # Send welcome message
        await welcome_channel.send(f"🎉 {member.mention} {saludo}")
        logger.info(f"Welcome message sent to {member.name} in {member.guild.name}")
        
        # Record greeting in behavior database (databases/<server_id>/behavior_*.db)
        try:
            behavior_db = get_behavior_db_instance(server_name)
            await asyncio.to_thread(
                behavior_db.record_greeting_sent,
                member.id, member.display_name, member.guild.id, saludo, 'welcome'
            )
        except Exception as behavior_error:
            logger.warning(f"Could not record greeting in behavior database: {behavior_error}")

        # Register interaction in agent database (databases/<server_id>/agent_*.db)
        try:
            db_instance = get_db_for_server(member.guild)
            interaction_message = greeting_cfg.get("interaction_message", "User joined the server")
            await asyncio.to_thread(
                db_instance.register_interaction,
                member.id, member.name, "WELCOME",
                interaction_message,
                welcome_channel.id, member.guild.id,
                metadata={"response": saludo, "greeting": saludo}
            )
        except Exception as db_error:
            logger.warning(f"Could not register interaction in database: {db_error}")
            
    except Exception as e:
        logger.error(f"Error in welcome handler for {member.name}: {e}")
        # Send fallback message
        try:
            welcome_info = await get_welcome_channel_info(member.guild, discord_cfg)
            if welcome_info:
                welcome_channel = welcome_info["channel"]
                greeting_cfg = discord_cfg.get("member_greeting", {})
                fallback_msg = greeting_cfg.get("fallback", "Welcome to the server!")
                fallback_msg = fallback_msg.format(user_name=member.display_name)
                await welcome_channel.send(f"🎉 {member.mention} {fallback_msg}")
        except Exception as fallback_error:
            logger.error(f"Fallback welcome also failed: {fallback_error}")


def build_welcome_prompt(user_display_name: str, user_id: str, guild) -> str:
    """
    Build a comprehensive contextual prompt for member welcome messages.
    
    Args:
        user_display_name: Display name of the user being welcomed
        user_id: Discord user ID
        guild: Discord guild object
        
    Returns:
        Comprehensive contextual prompt with memory, relationship, and interaction history
    """
    server_name = get_server_key(guild)

    # Get welcome configuration from server-specific personality
    server_id = str(guild.id) if guild else None
    personality = _get_personality(server_id) if server_id else _get_personality()
    greetings_cfg = personality.get("behaviors", {}).get("greetings", {})
    task_template = greetings_cfg.get("task", "Welcome {username} to the server.")
    golden_rules = greetings_cfg.get("golden_rules", [])
    response_title = greetings_cfg.get("response_title", "## WRITE ONLY THE WELCOME IN THE WORDS OF THE PERSONALITY:")
    
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

async def get_welcome_channel_info(guild, discord_cfg):
    """
    Get information about the welcome channel for a guild.
    Searches for appropriate channel based on keywords configured in descriptions.json.
    Tests if bot can send messages to channel before saving it.
    Stores the chosen channel in database for future use.
    
    Args:
        guild: discord.Guild
        discord_cfg: discord configuration from personality
        
    Returns:
        dict with channel info or None if not found
    """
    server_name = get_server_key(guild)
    behavior_db = get_behavior_db_instance(server_name)
    
    # First, check if we have a stored welcome channel in database
    stored_channel_id = behavior_db.get_welcome_channel()
    if stored_channel_id:
        # Verify the stored channel still exists
        stored_channel = guild.get_channel(int(stored_channel_id))
        if stored_channel and stored_channel.type == discord.ChannelType.text:
            # Test if we can send messages to this channel
            try:
                # Try to send a test message (will be deleted immediately)
                test_msg = await stored_channel.send("🔍 Testing channel permissions...")
                await test_msg.delete()
                logger.info(f"Using stored welcome channel: {stored_channel.name} ({stored_channel.id})")
                return {
                    "channel": stored_channel,
                    "name": stored_channel.name,
                    "id": stored_channel.id
                }
            except discord.Forbidden:
                logger.warning(f"Cannot send messages to stored channel {stored_channel.name} ({stored_channel.id}), searching for new channel")
            except Exception as e:
                logger.warning(f"Error testing stored channel {stored_channel.name} ({stored_channel.id}): {e}")
        else:
            logger.warning(f"Stored welcome channel {stored_channel_id} no longer exists, searching for new channel")
    
    # No stored channel or it's invalid, search for appropriate channel
    personality = _get_personality(str(guild.id))
    descriptions = personality.get("descriptions", {})
    welcome_keywords = descriptions.get("welcome_channel_keywords", {})
    
    # Search with language-specific keywords first
    language_specific_keywords = welcome_keywords.get("language_specific", [])
    general_keywords = welcome_keywords.get("general", ["general"])
    
    # Combine keywords: language-specific first, then general
    all_keywords = language_specific_keywords + general_keywords
    
    for keyword in all_keywords:
        for channel in guild.text_channels:
            if keyword.lower() in channel.name.lower():
                logger.info(f"Found welcome channel by keyword '{keyword}': {channel.name} ({channel.id})")
                # Test if we can send messages to this channel
                try:
                    # Try to send a test message (will be deleted immediately)
                    test_msg = await channel.send("🔍 Testing channel permissions...")
                    await test_msg.delete()
                    # Store this channel for future use
                    behavior_db.set_welcome_channel(str(channel.id), updated_by='system')
                    return {
                        "channel": channel,
                        "name": channel.name,
                        "id": channel.id
                    }
                except discord.Forbidden:
                    logger.warning(f"Cannot send messages to channel {channel.name} ({channel.id}), trying next channel")
                    continue
                except Exception as e:
                    logger.warning(f"Error testing channel {channel.name} ({channel.id}): {e}")
                    continue
    
    # No keyword match found, fallback to first text channel
    if guild.text_channels:
        channel = guild.text_channels[0]
        logger.info(f"No keyword match found, trying first text channel: {channel.name} ({channel.id})")
        # Test if we can send messages to this channel
        try:
            # Try to send a test message (will be deleted immediately)
            test_msg = await channel.send("🔍 Testing channel permissions...")
            await test_msg.delete()
            # Store this channel for future use
            behavior_db.set_welcome_channel(str(channel.id), updated_by='system')
            return {
                "channel": channel,
                "name": channel.name,
                "id": channel.id
            }
        except discord.Forbidden:
            logger.error(f"Cannot send messages to first text channel {channel.name} ({channel.id}) either")
        except Exception as e:
            logger.error(f"Error testing first text channel {channel.name} ({channel.id}): {e}")
    
    logger.warning(f"No suitable welcome channel found in guild {guild.name} - bot lacks permissions to send messages")
    return None
