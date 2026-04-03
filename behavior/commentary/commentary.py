"""
Commentary role - Mission commentary system.
Generates periodic comments about active missions incorporating memories and personality.
"""

from agent_logging import get_logger

# Import bot display name for dynamic replacement
try:
    from discord_bot.discord_core_commands import _bot_display_name
except ImportError:
    # Fallback if discord is not available
    _bot_display_name = "Bot"

logger = get_logger('commentary')

def get_commentary_system_prompt() -> str:
    """Get the system prompt for the commentary role."""
    return "ACTIVE MISSION - COMMENTARY: You are the bot's mission commentator. Your mission is to generate entertaining comments about active missions, incorporating relevant memories and maintaining the character's personality."

def get_commentary_task_prompt(enabled_roles: list[str], memories_context: str = "") -> str:
    """Generate a structured task prompt for mission commentary."""
    roles_text = "\n".join([f"- {role}" for role in enabled_roles]) if enabled_roles else "- No active roles"
    
    return f"""**MISSION COMMENTARY TASK**

Your specific task is: **Make a comment about your active missions**.

Guidelines:
- Be brief and entertaining (1-3 sentences)
- Incorporate relevant memories if you have them
- Mention at least one of your active missions
- Maintain the personality of {_bot_display_name}
- Don't repeat yourself

**ACTIVE ROLES:**
{roles_text}

**MEMORIES CONTEXT:**
{memories_context or "No important recent memories."}

**FINAL INSTRUCTION:** Now produce your comment about the active missions.

Just say the words of {_bot_display_name}:"""

def format_commentary_response(response: str) -> str:
    """Format the commentary response for Discord."""
    if not response or not str(response).strip():
        return f"⚠️ {_bot_display_name} has nothing to say right now..."
    
    # Clean up the response and add some flavor
    cleaned = str(response).strip()
    
    # Add a random emoji if not present
    emojis = ["💬", "🗣️", "📢", "🎭", "🎪"]
    if not any(emoji in cleaned for emoji in emojis):
        import random
        cleaned = f"{random.choice(emojis)} {cleaned}"
    
    return cleaned
