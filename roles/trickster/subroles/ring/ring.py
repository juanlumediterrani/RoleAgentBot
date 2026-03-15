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
        "¡Tienes mi anillo! ¡Dámelo ahora!",
        "¿Dónde está mi anillo? ¡Sé que lo tienes!",
        "Devuélveme mi anillo o te cortaré las manos",
        "Ese anillo que ves... ¡es mío! ¡Devuélvemelo!"
    ])
except Exception:
    RING_MESSAGES = [
        "¡Tienes mi anillo! ¡Dámelo ahora!",
        "¿Dónde está mi anillo? ¡Sé que lo tienes!",
        "Devuélveme mi anillo o te cortaré las manos",
        "Ese anillo que ves... ¡es mío! ¡Devuélvemelo!"
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

async def process_ring_mention(server_id: str, user_name: str) -> str:
    """Process when someone mentions rings or jewelry."""
    if not can_accuse(server_id):
        return None
    
    mark_accusation(server_id)
    accusation = get_ring_accusation()
    
    return f"GRRR {user_name}! {accusation} ¡Ese anillo es de la Horda y yo lo perdí en batalla! ¡Devuélvemelo o te arranco los dedos GRAAAH!"

def is_ring_related(text: str) -> bool:
    """Check if text mentions rings or related items."""
    ring_keywords = [
        "anillo", "ring", "joya", "jewelry", "aro", "circulo",
        "dedo", "finger", "mano", "hand", "oro", "gold"
    ]
    
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in ring_keywords)
