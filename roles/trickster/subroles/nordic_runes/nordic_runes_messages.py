"""
Nordic Runes Messages Module
Contains rune definitions, interpretations, and messages with personality support.
"""

from agent_logging import get_logger
logger = get_logger('nordic_runes_messages')

# Import rune data from rune_data.py (English fallback)
from .rune_data import RUNES, READING_TYPES

# Dynamic personality loading
try:
    import sys
    import os
    # Add project root to path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from agent_engine import AGENT_CFG
except ImportError:
    AGENT_CFG = {"personality": "personalities/putre/personality.json"}  # Fallback for testing


def _get_personality_dir(server_id: str = None) -> str:
    """Get the current personality directory dynamically using server_id."""
    try:
        # Try to get server-specific directory first
        try:
            from agent_runtime import get_personality_directory
            server_dir = get_personality_directory(server_id)
            if server_dir:
                return server_dir
        except:
            pass

        # Fall back to global personality directory
        default_personality = AGENT_CFG.get("default_personality", "rab")
        default_language = AGENT_CFG.get("default_language", "en-US")
        personality_rel = f"personalities/{default_personality}/{default_language}/personality.json"
        personality_path = os.path.join(project_root, personality_rel)
        return os.path.dirname(personality_path)
    except:
        # Fallback to putre if something goes wrong
        return os.path.join(project_root, "personalities", "putre")

# English fallback messages
ENGLISH_MESSAGES = {
    'welcome': "🔮 Welcome to Nordic Runes! I can cast the Elder Futhark runes for guidance and insight.",
    'question_prompt': "What question or situation would you like guidance on?",
    'reading_types': "Available reading types: single, three, cross, runic_cross",
    'invalid_type': "Invalid reading type. Please choose: single, three, cross, runic_cross",
    'no_question': "Please provide a question for your rune reading.",
    'reading_saved': "Your rune reading has been saved to your personal journal.",
    'error': "An error occurred while casting the runes. Please try again.",
    'single_cast': "🔮 **SINGLE RUNE CASTING** 🔮",
    'three_cast': "🔮 **THREE RUNE CASTING** 🔮",
    'cross_cast': "🔮 **FIVE RUNE CROSS CASTING** 🔮",
    'runic_cross_cast': "🔮 **SEVEN RUNE RUNIC CROSS CASTING** 🔮",
    'history': "🔮 **ANCIENT RUNES HISTORY** (Last {count}) 🔮",
    'types': "🔮 **RUNE CASTING TYPES** 🔮",
    'runes_list': "🔮 **ELDER FUTHARK RUNES** 🔮",
    'help': "🔮 **NORDIC RUNES WISDOM** 🔮",
    'help_content': """🔮 **NORDIC RUNES WISDOM** 🔮


Choose your casting type and ask the ancient runes!""",
    'runes_list_content': 'DYNAMIC_GENERATED',  # This will be replaced by get_runes_list_content()
    'history_empty': "🔮 You have no previous rune readings. Cast your first runes with `!runes cast`!",
    'history_header': "🔮 **YOUR ANCIENT RUNES READINGS** (Last {count})",
    'history_entry': "**ID {id}** - {type}\nQuestion: {question}\nRunes: {runes}\nDate: {date}",
    'stats': "\n**Total Readings:** {total}\n**Favorite Type:** {favorite}",
    'interpretation_header': "**Question:** {question}\n\n",
    # Added missing labels for rune fields
    'question': "Question",
    'meaning': "Meaning",
    'keywords': "Keywords",
    'interpretation': "Interpretation",
    'success': "🔮 UHHH! The ancient runes have spoken, human!",
    'saved': "🔮 UHHH! Your rune reading is saved in the ancient scrolls!"
}

# Personality messages cache
_personality_messages = None

def load_personality_messages(server_id: str = None):
    """Load messages from personality files with English fallbacks using server_id."""
    global _personality_messages
    
    # Always reload to ensure fresh messages from descriptions.json
    _personality_messages = None
    
    try:
        import json
        import os
        
        # Get project root and descriptions path
        # Current file: /home/mtx/Documentos/RoleAgentBot/roles/trickster/subroles/nordic_runes/nordic_runes_messages.py
        # Project root: /home/mtx/Documentos/RoleAgentBot
        # Need to go up 5 levels: nordic_runes -> subroles -> trickster -> roles -> RoleAgentBot
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        
        descriptions_path = os.path.join(_get_personality_dir(server_id), "descriptions.json")

        if os.path.exists(descriptions_path):
            with open(descriptions_path, encoding="utf-8") as f:
                descriptions = json.load(f)
                # Get the nordic_runes section
                nordic_runes_data = descriptions.get("discord", {}).get("roles_view_messages", {}).get("trickster", {}).get("nordic_runes", {})

                # If no nordic_runes data found in main descriptions.json, try loading from trickster.json
                if not nordic_runes_data:
                    trickster_path = os.path.join(_get_personality_dir(server_id), "descriptions", "trickster.json")
                    if os.path.exists(trickster_path):
                        with open(trickster_path, encoding="utf-8") as f:
                            trickster_data = json.load(f)
                            nordic_runes_data = trickster_data.get("nordic_runes", {})
                
                # Use English messages as base, override with all messages from descriptions
                merged_messages = ENGLISH_MESSAGES.copy()
                
                # Override with all available messages from descriptions.json
                for key, value in nordic_runes_data.items():
                    if key != "translations" and key != "positions":  # Skip special sections
                        merged_messages[key] = value
                
                # Also add labels as individual messages
                labels = nordic_runes_data.get("labels", {})
                
                # If no labels found in main descriptions.json, try loading from trickster.json
                if not labels:
                    trickster_path = os.path.join(_get_personality_dir(server_id), "descriptions", "trickster.json")
                    if os.path.exists(trickster_path):
                        with open(trickster_path, encoding="utf-8") as f:
                            trickster_data = json.load(f)
                            labels = trickster_data.get("nordic_runes", {}).get("labels", {})
                
                for key, value in labels.items():
                    merged_messages[key] = value
                
                # IMPORTANT: Also include translations section from separate runesplane.json file
                # Load from databases/{personality}/{language}/descriptions/runesplane.json
                personality_dir = _get_personality_dir(server_id)
                path_parts = personality_dir.split(os.sep)
                if 'personalities' in path_parts:
                    personalities_idx = path_parts.index('personalities')
                    path_parts[personalities_idx] = 'databases'
                    database_dir = os.sep.join(path_parts)
                    runesplane_path = os.path.join(database_dir, "descriptions", "runesplane.json")
                else:
                    # Fallback to personality directory if structure is unexpected
                    runesplane_path = os.path.join(personality_dir, "descriptions", "runesplane.json")
                
                if os.path.exists(runesplane_path):
                    with open(runesplane_path, encoding="utf-8") as f:
                        runesplane_data = json.load(f)
                        translations_section = runesplane_data.get("translations", {})
                        positions_section = runesplane_data.get("positions", {})
                        guidance_section = runesplane_data.get("guidance", {})
                else:
                    # Fallback to old structure if runesplane.json doesn't exist
                    translations_section = nordic_runes_data.get("translations", {})
                    positions_section = nordic_runes_data.get("positions", {})
                    guidance_section = nordic_runes_data.get("guidance", {})
                
                merged_messages["translations"] = translations_section
                merged_messages["positions"] = positions_section
                merged_messages["guidance"] = guidance_section
                
                _personality_messages = merged_messages
                return _personality_messages
        else:
            # If descriptions.json doesn't exist, use English fallbacks
            _personality_messages = ENGLISH_MESSAGES.copy()
            return _personality_messages
        
    except Exception as e:
        # If loading fails, return English fallbacks
        logger.error(f"Failed to load personality messages: {e}")
        _personality_messages = ENGLISH_MESSAGES.copy()
        return _personality_messages

def get_rune(rune_key: str) -> dict:
    """Get rune information by key."""
    return RUNES.get(rune_key, {})

def get_reading_type(type_key: str) -> dict:
    """Get reading type information by key."""
    return READING_TYPES.get(type_key, {})

def get_message(message_key: str, page: int = 1) -> str:
    """Get message by key with personality support and optional page parameter."""
    messages = load_personality_messages()
    
    # Special handling for runes_list_content to use dynamic generation with pagination
    if message_key == 'runes_list_content':
        return get_runes_list_content(page)
    
    result = messages.get(message_key, ENGLISH_MESSAGES.get(message_key, f"Unknown message: {message_key}"))
    
    return result

def clear_message_cache():
    """Clear the personality messages cache to force reload."""
    global _personality_messages
    _personality_messages = None

def get_guidance_messages(category: str, server_id: str = None) -> dict:
    """Get guidance messages for a category (love, career, health, path) using server_id."""
    messages = load_personality_messages(server_id)
    guidance_data = messages.get('guidance', {})

    # If guidance_data is a string (from labels section), load the actual guidance
    if isinstance(guidance_data, str):
        # Load the actual guidance from descriptions.json
        try:
            import json
            import os

            # Get project root and descriptions path
            # Current file: /home/mtx/Documentos/RoleAgentBot/roles/trickster/subroles/nordic_runes/nordic_runes_messages.py
            # Project root: /home/mtx/Documentos/RoleAgentBot
            # Need to go up 5 levels: nordic_runes -> subroles -> trickster -> roles -> RoleAgentBot
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

            descriptions_path = os.path.join(_get_personality_dir(server_id), "descriptions.json")

            if os.path.exists(descriptions_path):
                with open(descriptions_path, encoding="utf-8") as f:
                    descriptions = json.load(f)

                    # Try to load guidance from runesplane.json first
                    # Load from databases/{personality}/{language}/descriptions/runesplane.json
                    personality_dir = _get_personality_dir(server_id)
                    path_parts = personality_dir.split(os.sep)
                    if 'personalities' in path_parts:
                        personalities_idx = path_parts.index('personalities')
                        path_parts[personalities_idx] = 'databases'
                        database_dir = os.sep.join(path_parts)
                        runesplane_path = os.path.join(database_dir, "descriptions", "runesplane.json")
                    else:
                        # Fallback to personality directory if structure is unexpected
                        runesplane_path = os.path.join(personality_dir, "descriptions", "runesplane.json")
                    
                    if os.path.exists(runesplane_path):
                        with open(runesplane_path, encoding="utf-8") as f:
                            runesplane_data = json.load(f)
                            guidance_data = runesplane_data.get("guidance", {})
                    else:
                        # Fallback to old structure
                        nordic_runes_data = descriptions.get("discord", {}).get("roles_view_messages", {}).get("trickster", {}).get("nordic_runes", {})
                        guidance_data = nordic_runes_data.get('guidance', {})
        except:
            guidance_data = {}

    return guidance_data.get(category, {})

def get_runes_list_content(page: int = 1, server_id: str = None) -> str:
    """Generate runes list content dynamically from runesplane.json with pagination using server_id."""
    import json
    import os
    
    # Get project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    
    # Load personality messages for labels
    messages = load_personality_messages(server_id)
    
    # Load labels from descriptions.json
    labels_data = {}
    try:
        descriptions_path = os.path.join(_get_personality_dir(server_id), "descriptions.json")
        if os.path.exists(descriptions_path):
            with open(descriptions_path, encoding="utf-8") as f:
                descriptions = json.load(f)
                labels_data = descriptions.get("discord", {}).get("roles_view_messages", {}).get("trickster", {}).get("nordic_runes", {}).get("labels", {})
        
        # If no labels found in main descriptions.json, try loading from trickster.json
        if not labels_data:
            trickster_path = os.path.join(_get_personality_dir(server_id), "descriptions", "trickster.json")
            if os.path.exists(trickster_path):
                with open(trickster_path, encoding="utf-8") as f:
                    trickster_data = json.load(f)
                    labels_data = trickster_data.get("nordic_runes", {}).get("labels", {})
    except:
        labels_data = {}
    
    # Load rune data from runesplane.json
    runes_data = {}
    try:
        # Load from databases/{personality}/{language}/descriptions/runesplane.json
        personality_dir = _get_personality_dir(server_id)
        # Extract personality and language from the path
        # personality_dir is like: /home/.../personalities/{personality}/{language}
        # We need to change it to: /home/.../databases/{personality}/{language}
        path_parts = personality_dir.split(os.sep)
        # Find the 'personalities' directory and replace with 'databases'
        if 'personalities' in path_parts:
            personalities_idx = path_parts.index('personalities')
            path_parts[personalities_idx] = 'databases'
            database_dir = os.sep.join(path_parts)
            runesplane_path = os.path.join(database_dir, "descriptions", "runesplane.json")
        else:
            # Fallback to personality directory if structure is unexpected
            runesplane_path = os.path.join(personality_dir, "descriptions", "runesplane.json")
        
        if os.path.exists(runesplane_path):
            with open(runesplane_path, encoding="utf-8") as f:
                runesplane_data = json.load(f)
                runes_data = runesplane_data.get("translations", {})
        else:
            # Fallback to English RUNES from rune_data.py if runesplane.json doesn't exist
            logger.warning(f"runesplane.json not found at {runesplane_path}, using fallback RUNES from rune_data.py")
            for rune_key, rune_info in RUNES.items():
                runes_data[rune_key] = {
                    'meaning': rune_info.get('meaning', 'Unknown'),
                    'keywords': rune_info.get('keywords', []),
                    'interpretation': rune_info.get('description', 'No description')
                }
    except Exception as e:
        logger.error(f"Failed to load runesplane.json: {e}, using fallback RUNES from rune_data.py")
        # Fallback to English RUNES from rune_data.py
        for rune_key, rune_info in RUNES.items():
            runes_data[rune_key] = {
                'meaning': rune_info.get('meaning', 'Unknown'),
                'keywords': rune_info.get('keywords', []),
                'interpretation': rune_info.get('description', 'No description')
            }
    
    # Define rune symbols and names (Elder Futhark order)
    rune_order = [
        ('fehu', 'ᚠ', 'Fehu'),
        ('uruz', 'ᚢ', 'Uruz'),
        ('thurisaz', 'ᚦ', 'Thurisaz'),
        ('ansuz', 'ᚨ', 'Ansuz'),
        ('raidho', 'ᚱ', 'Raidho'),
        ('kenaz', 'ᚲ', 'Kenaz'),
        ('gebo', 'ᚷ', 'Gebo'),
        ('wunjo', 'ᚹ', 'Wunjo'),
        ('hagalaz', 'ᚺ', 'Hagalaz'),
        ('nauthiz', 'ᚾ', 'Nauthiz'),
        ('isa', 'ᛁ', 'Isa'),
        ('jera', 'ᛃ', 'Jera'),
        ('eiwaz', 'ᛇ', 'Eiwaz'),
        ('perthro', 'ᛈ', 'Perthro'),
        ('algiz', 'ᛉ', 'Algiz'),
        ('sowilo', 'ᛊ', 'Sowilo'),
        ('tiwaz', 'ᛏ', 'Tiwaz'),
        ('berkano', 'ᛒ', 'Berkano'),
        ('ehwaz', 'ᛖ', 'Ehwaz'),
        ('mannaz', 'ᛗ', 'Mannaz'),
        ('laguz', 'ᛚ', 'Laguz'),
        ('ingwaz', 'ᛜ', 'Ingwaz'),
        ('dagaz', 'ᛞ', 'Dagaz'),
        ('othala', 'ᛟ', 'Othala')
    ]
    
    # Calculate pagination - 8 runes per page
    runes_per_page = 8
    start_idx = (page - 1) * runes_per_page
    end_idx = start_idx + runes_per_page
    page_runes = rune_order[start_idx:end_idx]
    
    # Page titles with rune ranges - get from descriptions.json with fallback
    page_titles = {
        1: messages.get('runes_page_1_title', "🔮 **THE ELDER FUTHARK - RUNES I (Fehu to Wunjo)** 🔮"),
        2: messages.get('runes_page_2_title', "🔮 **THE ELDER FUTHARK - RUNES II (Hagalaz to Sowilo)** 🔮"), 
        3: messages.get('runes_page_3_title', "🔮 **THE ELDER FUTHARK - RUNES III (Tiwaz to Othala)** 🔮")
    }
    
    content = page_titles.get(page, f"🔮 **THE ELDER FUTHARK - RUNES {page}** 🔮") + "\n\n" + "-"*55 + "\n\n"

    # Generate content for this page by looping through runesplane.json data
    title_meaning = labels_data.get("meaning", "Significado:")
    title_keywords = labels_data.get("keywords", "Palabras Clave:")
    title_interpretation = labels_data.get("interpretation", "Interpretación:")
    
    for rune_key, symbol, name in page_runes:
        rune_info = runes_data.get(rune_key, {})
        meaning = rune_info.get('meaning', 'Unknown')
        keywords = rune_info.get('keywords', [])
        interpretation = rune_info.get('interpretation', 'No description')
        
        content += f"**{symbol} {name}**\n"
        content += f"{title_meaning} {meaning}\n"
        content += f"{title_keywords} {keywords}\n"
        content += f"{title_interpretation} {interpretation}\n\n"
    
    return content
