"""
Memory role - Personality memory display system.
Displays personality memories (long, recent, relationship) with dropdown selection.
"""

from agent_logging import get_logger

try:
    raise ImportError
except ImportError:
    pass  # Fallback not needed

logger = get_logger('memory')

def get_memory_system_prompt() -> str:
    """Get the system prompt for the memory role."""
    return "ACTIVE MISSION - MEMORY: You are the bot's memory display system. Your mission is to show the personality's memories in different formats (long, recent, relationship)."

def get_memory_task_prompt(memory_type: str, memories_context: str = "") -> str:
    """Generate a structured task prompt for memory display.
    
    Args:
        memory_type: Type of memory to display ('long', 'recent', 'relationship')
        memories_context: The actual memory content to display
    """
    
    type_labels = {
        'long': 'Long Memory (Daily Analysis)',
        'recent': 'Recent Memory (Current Flow)',
        'relationship': 'Relationship Memory (Visitor Profile)'
    }
    
    type_descriptions = {
        'long': 'Shows the comprehensive daily memory and analysis of the personality.',
        'recent': 'Shows recent events and short-term memory of the personality.',
        'relationship': 'Shows the personality\'s perception and relationship with specific users.'
    }
    
    label = type_labels.get(memory_type, 'Memory')
    description = type_descriptions.get(memory_type, 'Memory display')
    
    return f"""**MEMORY DISPLAY TASK**

Your specific task is: **Display the {label}**.

Guidelines:
- Show the memory content exactly as provided
- Maintain the personality's voice and style
- Do not modify or summarize the content
- Display it as a coherent block of text

**MEMORY TYPE:**
{label}

**DESCRIPTION:**
{description}

**MEMORY CONTENT:**
{memories_context or "No memory content available."}

Just show the memory:"""

def format_memory_response(response: str, memory_type: str = "long") -> str:
    """Format the memory response for Discord.
    
    Args:
        response: The memory content to format
        memory_type: Type of memory being displayed
    """
    if not response or not str(response).strip():
        fallback_messages = {
            'long': "📭 No long memory available.",
            'recent': "📭 No recent memory available.",
            'relationship': "📭 No relationship memory available."
        }
        return fallback_messages.get(memory_type, "📭 No memory available.")
    
    # Clean up the response
    cleaned = str(response).strip()
    
    # Add appropriate emoji based on memory type
    emojis = {
        'long': "🗺️",
        'recent': "🧐",
        'relationship': "👞"
    }
    emoji = emojis.get(memory_type, "🧠")
    
    return f"{emoji} {cleaned}"
