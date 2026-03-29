"""
Ring subrole for Trickster.
Handles the ring accusation and quest functionality.
"""

import asyncio
import random
from datetime import datetime, timedelta
from agent_logging import get_logger

logger = get_logger('ring')

# Mission configuration (fallback if JSON is not available)
MISSION_CONFIG = {
    "name": "ring",
    "system_prompt_addition": "ACTIVE SUBROLE - RING: You are obsessed with finding the lost ring. When users mention rings, jewelry, or lost items, you become suspicious and may accuse them of having your precious ring. You demand the ring back and offer rewards for its return."
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
    RING_MESSAGES = answers_cfg.get("role_messages", {}).get("ring_accusations", [
        "You have my ring! Give it to me now!",
        "Where is my ring? I know you have it!",
        "Give me back my ring or I'll cut off your hands",
        "That ring you're looking at... it's mine! Give it back!"
    ])
except Exception:
    RING_MESSAGES = [
        "You have my ring! Give it to me now!",
        "Where is my ring? I know you have it!",
        "Give me back my ring or I'll cut off your hands",
        "That ring you're looking at... it's mine! Give it back!"
    ]

# Track last accusation time per server to avoid spam
_last_accusation_time = {}

def can_accuse(server_id: str, cooldown_hours: int = 24) -> bool:
    """Check if enough time has passed since last accusation."""
    if server_id not in _last_accusation_time:
        return True
    
    last_time = _last_accusation_time[server_id]
    return datetime.now() - last_time > timedelta(hours=cooldown_hours)

def mark_accusation(server_id: str):
    """Mark that an accusation was made for this server."""
    _last_accusation_time[server_id] = datetime.now()

def get_ring_accusation():
    """Get a random ring accusation message."""
    return random.choice(RING_MESSAGES)


def extract_accuse_flag(text: str) -> str | None:
    """Extract ACCUSE <USERNAME> flag from LLM response."""
    import re
    
    # Look for ACCUSE <USERNAME> pattern (capture username with optional punctuation)
    match = re.search(r'ACCUSE\s+([^\s!?]+[!?]?)', text, re.IGNORECASE)
    if match:
        # Remove trailing punctuation from username
        username = match.group(1).strip('!?')
        return username
    return None
