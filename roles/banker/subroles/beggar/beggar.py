"""
Beggar subrole for Banker.
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
    "system_prompt_addition": "ACTIVE SUBROLE - BEGGAR: You are always looking for gold and donations for server proyects.",
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

# Track last beg time per server to avoid spam
_last_beg_time = {}

async def beggar_task():
    """Execute beggar task - ask for donations in configured channels."""
    logger.info("🥺 Starting beggar task...")
    
    try:
        # This would integrate with Discord to send messages
        # For now, just log that the task ran
        from .beggar_messages import get_random_reason
        reason = get_random_reason()
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

def get_random_beg_message(server_id: str = None) -> str:
    """Get a random beg message with reason."""
    from .beggar_messages import get_random_reason
    reason = get_random_reason(server_id)
    return f"🥺 I need alms {reason}! Please help!"
