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
    "system_prompt_addition": "ACTIVE SUBROLE - BEGGAR: You are always looking for gold and donations. When users mention money, gold, or wealth, you immediately ask for donations. You invent creative reasons why you need the gold and use intimidation or guilt to get donations."
}

# Load personality messages
try:
    import json
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    config_path = os.path.join(project_root, "agent_config.json")
    with open(config_path, encoding="utf-8") as f:
        agent_cfg = json.load(f)
    personality_rel = agent_cfg.get("personality", "")
    answers_path = os.path.join(project_root, os.path.dirname(personality_rel), "answers.json")
    with open(answers_path, encoding="utf-8") as f:
        answers_cfg = json.load(f).get("discord", {})
    BEGGAR_MESSAGES = answers_cfg.get("role_messages", {}).get("limosna_reasons", [
        "para traer a tu familia orca contigo",
        "para comprar armas nuevas y hacer la guerra", 
        "para pagar tributo al jefe orco y que no te mate",
        "porque tienes hambre y no quieres comer carne humana otra vez"
    ])
except Exception:
    BEGGAR_MESSAGES = [
        "para traer a tu familia contigo",
        "para comprar armas nuevas",
        "para pagar tributo al jefe",
        "porque tienes hambre"
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
