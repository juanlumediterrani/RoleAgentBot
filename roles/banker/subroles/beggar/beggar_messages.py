"""
Beggar Messages and Configuration
Contains all text messages, prompts, and configuration for the beggar subrole.
"""

import random
import os
import sys
from typing import List, Dict, Any
from pathlib import Path

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

# Neutral English fallback messages for random reasons
BEGGAR_REASONS_FALLBACK = [
    "to support your family",
    "to buy new supplies", 
    "to pay your debts",
    "because you're hungry",
    "to fix your broken axe",
    "to buy armor for battle",
]


def _load_personality_reasons(server_id: str = None) -> List[str]:
    """
    Load reasons from personality prompts.json, fallback to BEGGAR_REASONS_FALLBACK.
    
    Args:
        server_id: Server ID for server-specific personality files
        
    Returns:
        List of reason strings
    """
    try:
        # Add project root to path for imports
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        from agent_runtime import get_personality_file_path, _load_personality_file_cached
        
        # Try to load reasons from personality prompts.json
        prompts_path = get_personality_file_path("prompts.json", server_id)
        prompts_data = _load_personality_file_cached("prompts.json", server_id)
        
        # Check if reasons exist in the prompts
        if prompts_data and "reasons" in prompts_data:
            reasons = prompts_data["reasons"]
            if isinstance(reasons, list) and reasons:
                return reasons
        
        # Fallback to BEGGAR_REASONS_FALLBACK
        return BEGGAR_REASONS_FALLBACK
        
    except Exception:
        # If anything fails, return fallback
        return BEGGAR_REASONS_FALLBACK


def get_random_reason(server_id: str = None) -> str:
    """
    Get a random beg reason from personality prompts.json or fallback.
    
    Args:
        server_id: Server ID for server-specific personality files
        
    Returns:
        Random reason string
    """
    reasons = _load_personality_reasons(server_id)
    return random.choice(reasons)


# Canvas default fallback neutral english UI Messages
CANVAS_MESSAGES = {
    "title": ":coin: **FUNDRAISING** :coin:",
    "description": "The bot collects gold for clan projects. Donate gold regularly and the bot will appreciate it each week.",
    "current_fund": "Current fund:",
    "title_campaign": "**Current campaign**",
    "title_reason": "Reason:",
    "title_instructions": "**Instructions**",
    "instructions": " - Click donate in the dropdown menu below.\n - Wait for weekly results at the end of this week.\n - Participate with any amount and the bot will take it into account.",
    "title_donations": "📊 **Donations:**",
    "no_donations": "No donations yet. Be the first to contribute!",
    "donation_success": "Thanks for donating {amount} gold for the cause: {reason}! 🪙",
}


def get_canvas_message(key: str, **kwargs) -> str:
    """Get a canvas UI message with optional formatting."""
    message = CANVAS_MESSAGES.get(key, key)
    if kwargs:
        message = message.format(**kwargs)
    return message
