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

# Fallback task prompt template
BEGGAR_TASK_PROMPT_FALLBACK = "INTERNAL TASK - BEGGAR: You are raising gold on the server for {reason}. Be convincing but maintain your rough orc style."

# Fallback labels
BEGGAR_LABELS_FALLBACK = {
    "recent_channel_messages": "=== RECENT CHANNEL MESSAGES ===",
}


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


def get_task_prompt_template(server_id: str = None) -> str:
    """
    Load task prompt template from personality prompts.json, fallback to BEGGAR_TASK_PROMPT_FALLBACK.
    
    Args:
        server_id: Server ID for server-specific personality files
        
    Returns:
        Task prompt template string with {reason} placeholder
    """
    try:
        from agent_runtime import get_personality_file_path, _load_personality_file_cached
        
        # Try to load task prompt from personality prompts.json
        prompts_data = _load_personality_file_cached("prompts.json", server_id)
        
        # Check if task prompt exists in the prompts
        if prompts_data:
            # Look for task prompt in the beggar subrole section
            task_prompt = prompts_data.get("roles", {}).get("banker", {}).get("subroles", {}).get("beggar", {}).get("prompt")
            if task_prompt:
                return task_prompt
        
        # Fallback to BEGGAR_TASK_PROMPT_FALLBACK
        return BEGGAR_TASK_PROMPT_FALLBACK
        
    except Exception:
        # If anything fails, return fallback
        return BEGGAR_TASK_PROMPT_FALLBACK


def get_label(label_key: str, server_id: str = None) -> str:
    """
    Load a label from personality prompts.json, fallback to BEGGAR_LABELS_FALLBACK.
    
    Args:
        label_key: Key for the label (e.g., "recent_channel_messages")
        server_id: Server ID for server-specific personality files
        
    Returns:
        Label string
    """
    try:
        from agent_runtime import get_personality_file_path, _load_personality_file_cached
        
        # Try to load labels from personality prompts.json
        prompts_data = _load_personality_file_cached("prompts.json", server_id)
        
        # Check if labels exist in the prompts
        if prompts_data:
            # Look for labels in the beggar subrole section
            labels = prompts_data.get("roles", {}).get("banker", {}).get("subroles", {}).get("beggar", {}).get("labels", {})
            if label_key in labels:
                return labels[label_key]
        
        # Fallback to BEGGAR_LABELS_FALLBACK
        return BEGGAR_LABELS_FALLBACK.get(label_key, label_key)
        
    except Exception:
        # If anything fails, return fallback
        return BEGGAR_LABELS_FALLBACK.get(label_key, label_key)


# Canvas default fallback neutral english UI Messages
CANVAS_MESSAGES = {
    "title": "🪙 **RECAUDATIONS** 🪙",
    "description": " Keep gold for for different reasons and give the result at the end of the week.\n Maybe you won some gold.",
    "current_fund":"Current found:",
    "title_campaign":"**Current campaing**",
    "title_reason":"Reason:",
    "title_instructions": "**Instructions**",
    "instructions": " - Click donate in the dropdown menu below.\n - Wait for weekly results at the end of this week.\n - Participate with any amount and Putre will take it into account.\n",
    "title_donations": "📊 **Donations:**",
    "no_donations": "No donations yet. Be the first to contribute!",
    "beggar_donation_success": "Thanks for donating {amount} gold for the cause: {reason}! 🪙",
    "dropdown": {
        "beggar_donate": "Beggar: Donate",
        "beggar_donate_description": "Make a donation for clan projects",
        "beggar_on": "Beggar: Enable",
        "beggar_on_description": "Enable beggar system",
        "beggar_off": "Beggar: Disable",
        "beggar_off_description": "Disable beggar system",
        "beggar_frequency": "Beggar: Frequency",
        "beggar_frequency_description": "Set request frequency",
        "beggar_force_minigame": "Beggar: Force Minigame",
        "beggar_force_minigame_description": "Force minigame execution"
    }
}


def get_canvas_message(key: str, **kwargs) -> str:
    """Get a canvas UI message with optional formatting."""
    message = CANVAS_MESSAGES.get(key, key)
    if kwargs:
        message = message.format(**kwargs)
    return message
