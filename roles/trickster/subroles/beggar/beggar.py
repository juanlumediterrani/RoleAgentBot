"""
Beggar subrole for Trickster.
Handles asking for money/donations from users.
"""

import asyncio
import random
from datetime import datetime, timedelta
from agent_logging import get_logger

logger = get_logger('beggar')

# Mission configuration (fallback if JSON is not available)
MISSION_CONFIG = {
    "name": "beggar",
    "system_prompt_addition": "ACTIVE SUBROLE - BEGGAR: You are always looking for gold and donations. When users mention money, gold, or wealth, you immediately ask for donations. You invent creative reasons why you need the gold and use intimidation or guilt to get donations.",
    "golden_rules": [
        "golden_rules",
        "1. CHARACTER STYLE: Maintain consistent character voice and expressions",
        "2. PERSUASION: Convince users to donate gold for the stated reason", 
        "3. PUBLIC: Speak in public channel so everyone hears your request",
        "4. CONTEXT: Respond to current channel atmosphere if relevant",
        "5. AUTHENTICITY: Act like a real character, not like a bot",
        "6. LENGTH: 3-8 sentences (150-400 characters)",
        "7. DIRECT: Get straight to the point with your gold request",
        "8. EMOTIONAL: Use emotional appeals if necessary"
    ]
}

# Neutral English fallback messages
BEGGAR_MESSAGES = [
    "to support your family",
    "to buy new supplies", 
    "to pay your debts",
    "because you're hungry"
]

# Track last beg time per server to avoid spam
_last_beg_time = {}

async def beggar_task():
    """Execute beggar task - ask for donations in configured channels."""
    logger.info("🥺 Starting beggar task...")
    
    try:
        # This would integrate with Discord to send messages
        # For now, just log that the task ran
        reason = random.choice(BEGGAR_MESSAGES)
        logger.info(f"🥺 Beggar task completed - Reason: {reason}")
        
    except Exception as e:
        logger.error(f"🥺 Error in beggar task: {e}")
    
    logger.info("🥺 Beggar task completed")

def can_beg_in_server(server_id: str, min_hours: int = 6) -> bool:
    """Check if enough time has passed since last beg in this server."""
    now = datetime.now()
    last_time = _last_beg_time.get(server_id)
    
    if last_time is None:
        return True
    
    time_diff = now - last_time
    return time_diff >= timedelta(hours=min_hours)

def update_last_beg_time(server_id: str):
    """Update the last beg time for a server."""
    _last_beg_time[server_id] = datetime.now()

def get_random_beg_message() -> str:
    """Get a random beg message with reason."""
    reason = random.choice(BEGGAR_MESSAGES)
    return f"🥺 I need alms {reason}! Please help a poor orc!"
