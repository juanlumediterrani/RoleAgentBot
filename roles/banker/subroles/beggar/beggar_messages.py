"""
Beggar Messages and Configuration
Contains all text messages, prompts, and configuration for the beggar subrole.
"""

import random
from typing import List, Dict, Any

# Mission configuration (fallback if JSON is not available)
MISSION_CONFIG = {
    "current_fund":"Current found:",
    "coin":"🪙",
    "donnor":"Donnors:",
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

# Fallback minigame results
MINIGAME_RESULTS_FALLBACK = {
    "nothing": "No gold returns for anyone this time",
    "return": "All participants get their donations back",
    "double": "All participants get double their donations back",
    "triple": "All participants get triple their donations back"
}


def _get_beggar_section(server_id: str = None) -> Dict[str, Any]:
    """Get beggar section from server-specific personality loaded by engine."""
    from agent_engine import _get_personality

    personality = _get_personality(server_id) if server_id else _get_personality()
    return personality.get("roles", {}).get("banker", {}).get("subroles", {}).get("beggar", {})


def _load_personality_reasons(server_id: str = None) -> List[str]:
    """
    Load reasons from personality prompts.json, fallback to BEGGAR_REASONS_FALLBACK.
    
    Args:
        server_id: Server ID for server-specific personality files
        
    Returns:
        List of reason strings
    """
    try:
        beggar_section = _get_beggar_section(server_id)
        reasons = beggar_section.get("reasons", [])
        if isinstance(reasons, list) and reasons:
            return reasons
        return BEGGAR_REASONS_FALLBACK
    except Exception:
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
        beggar_section = _get_beggar_section(server_id)
        task_prompt = beggar_section.get("prompt")
        if task_prompt:
            return task_prompt
        return BEGGAR_TASK_PROMPT_FALLBACK
    except Exception:
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
        beggar_section = _get_beggar_section(server_id)
        labels = beggar_section.get("labels", {})
        if label_key in labels:
            return labels[label_key]
        return BEGGAR_LABELS_FALLBACK.get(label_key, label_key)
    except Exception:
        return BEGGAR_LABELS_FALLBACK.get(label_key, label_key)


# Canvas default fallback neutral english UI Messages
CANVAS_MESSAGES = {
    "title": "🪙 **RECAUDATIONS** 🪙",
    "description": " Keep gold for for different reasons and give the result at the end of the week.\n Maybe you won some gold.",
    "title_campaign":"**Current campaing**",
    "title_reason":"Reason:",
    "title_instructions": "**Instructions**",
    "instructions": " - Click donate in the dropdown menu below.\n - Wait for weekly results at the end of this week.\n - Participate with any amount and Putre will take it into account.\n",
    "title_donations": "📊 **Donations:**",
    "no_donations": "No donations yet. Be the first to contribute!",
    "beggar_donation_success": "Thanks for donating {amount} gold for the cause: {reason}! 🪙",
    "donation_x1_label": "Donate x1 TAE",
    "donation_x3_label": "Donate x3 TAE",
    "donation_custom_label": "Custom Amount",
    "dropdown": {
        "beggar_donate": "Beggar: Donate",
        "beggar_donate_emoji": "🤲",
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


def get_golden_rules(server_id: str = None) -> List[str]:
    """
    Load golden rules from personality prompts.json, fallback to MISSION_CONFIG.
    
    Args:
        server_id: Server ID for server-specific personality files
        
    Returns:
        List of golden rule strings
    """
    try:
        beggar_section = _get_beggar_section(server_id)
        golden_rules = beggar_section.get("golden_rules", [])
        if golden_rules:
            return golden_rules
        return MISSION_CONFIG.get('golden_rules', [])
    except Exception:
        return MISSION_CONFIG.get('golden_rules', [])


def get_memory_interaction_label(interaction_type: str = "recaudation", server_id: str = None) -> str:
    """
    Load memory interaction label from personality prompts.json, fallback to default.
    
    Args:
        interaction_type: Type of interaction (e.g., "recaudation")
        server_id: Server ID for server-specific personality files
        
    Returns:
        Formatted label string: "{beggar_system} /{event} - {recaudation}:"
    """
    try:
        from agent_engine import _get_personality

        personality = _get_personality(server_id) if server_id else _get_personality()
        event_label = personality.get("general", {}).get("event", "Event")
        memory_labels = _get_beggar_section(server_id).get("memory_labels", {})
        beggar_system = memory_labels.get("beggar_system", "Beggar System")
        recaudation = memory_labels.get(interaction_type, interaction_type)
        return f"{beggar_system} /{event_label} - {recaudation}:"
    except Exception:
        return f"Beggar System /Event - {interaction_type}:"


def get_canvas_message(server_db_path: str = None, key: str = None, **kwargs) -> str:
    """Get a canvas UI message from personality JSON or fallback.
    
    Args:
        server_db_path: Path to server personality directory (e.g., 'databases/<server_id>/<personality>')
        key: Message key to retrieve from beggar section
        **kwargs: Optional variables to format into the message
        
    Returns:
        The formatted message string
    """
    message = None
    
    if server_db_path and key:
        try:
            import os
            import json
            json_path = os.path.join(server_db_path, "descriptions", "banker.json")
            if os.path.isfile(json_path):
                with open(json_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                # Look in beggar section first
                beggar_section = raw.get("beggar", {})
                message = beggar_section.get(key)
                # Also check dropdown section inside beggar
                if message is None:
                    dropdown = beggar_section.get("dropdown", {})
                    message = dropdown.get(key)
        except Exception as e:
            pass  # Fall back to CANVAS_MESSAGES
    
    if message is None:
        message = CANVAS_MESSAGES.get(key, key)
    
    if kwargs and isinstance(message, str):
        try:
            return message.format(**kwargs)
        except (KeyError, ValueError):
            pass
    
    return message if message else key
