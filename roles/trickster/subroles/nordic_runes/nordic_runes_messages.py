"""
Nordic Runes Messages Module
Contains rune definitions, interpretations, and messages with personality support.
"""

from agent_logging import get_logger
logger = get_logger('nordic_runes_messages')

# Elder Futhark Runes with their meanings
RUNES = {
    'fehu': {
        'name': 'Fehu',
        'symbol': 'ᚠ',
        'meaning': 'Wealth, Cattle, Possessions',
        'keywords': ['wealth', 'abundance', 'success', 'prosperity', 'material gain'],
        'reversed': False,
        'description': 'Represents material wealth, prosperity, and success in financial matters.'
    },
    'uruz': {
        'name': 'Uruz',
        'symbol': 'ᚢ',
        'meaning': 'Aurochs, Strength, Power',
        'keywords': ['strength', 'courage', 'power', 'vitality', 'wild energy'],
        'reversed': False,
        'description': 'Symbolizes untamed strength, courage, and primal energy.'
    },
    'thurisaz': {
        'name': 'Thurisaz',
        'symbol': 'ᚦ',
        'meaning': 'Giant, Thor, Protection',
        'keywords': ['protection', 'defense', 'conflict', 'change', 'catharsis'],
        'reversed': False,
        'description': 'Represents protective forces, conflict resolution, and necessary change.'
    },
    'ansuz': {
        'name': 'Ansuz',
        'symbol': 'ᚨ',
        'meaning': 'God, Odin, Communication',
        'keywords': ['communication', 'wisdom', 'knowledge', 'divine messages', 'inspiration'],
        'reversed': False,
        'description': 'Symbolizes divine communication, wisdom, and inspired speech.'
    },
    'raidho': {
        'name': 'Raidho',
        'symbol': 'ᚱ',
        'meaning': 'Journey, Travel, Movement',
        'keywords': ['journey', 'travel', 'movement', 'change', 'progress'],
        'reversed': False,
        'description': 'Represents physical and spiritual journeys, movement, and life path.'
    },
    'kenaz': {
        'name': 'Kenaz',
        'symbol': 'ᚲ',
        'meaning': 'Torch, Knowledge, Creativity',
        'keywords': ['knowledge', 'creativity', 'inspiration', 'clarity', 'vision'],
        'reversed': False,
        'description': 'Symbolizes illumination, creative fire, and intellectual clarity.'
    },
    'gebo': {
        'name': 'Gebo',
        'symbol': 'ᚷ',
        'meaning': 'Gift, Partnership, Exchange',
        'keywords': ['gift', 'partnership', 'exchange', 'balance', 'harmony'],
        'reversed': False,
        'description': 'Represents gifts, partnerships, and balanced exchanges.'
    },
    'wunjo': {
        'name': 'Wunjo',
        'symbol': 'ᚹ',
        'meaning': 'Joy, Pleasure, Harmony',
        'keywords': ['joy', 'happiness', 'harmony', 'success', 'fulfillment'],
        'reversed': False,
        'description': 'Symbolizes joy, harmony, and the fulfillment of desires.'
    },
    'hagalaz': {
        'name': 'Hagalaz',
        'symbol': 'ᚺ',
        'meaning': 'Hail, Disruption, Change',
        'keywords': ['disruption', 'change', 'crisis', 'transformation', 'chaos'],
        'reversed': False,
        'description': 'Represents disruptive change, crisis, and necessary transformation.'
    },
    'nauthiz': {
        'name': 'Nauthiz',
        'symbol': 'ᚾ',
        'meaning': 'Need, Necessity, Constraint',
        'keywords': ['need', 'necessity', 'constraint', 'discipline', 'delay'],
        'reversed': False,
        'description': 'Symbolizes necessity, constraint, and the need for patience.'
    },
    'isa': {
        'name': 'Isa',
        'symbol': 'ᛁ',
        'meaning': 'Ice, Stillness, Stagnation',
        'keywords': ['ice', 'stillness', 'stagnation', 'delay', 'clarity'],
        'reversed': False,
        'description': 'Represents stillness, delay, and the need for reflection.'
    },
    'jera': {
        'name': 'Jera',
        'symbol': 'ᛃ',
        'meaning': 'Year, Harvest, Cycle',
        'keywords': ['harvest', 'cycle', 'reward', 'patience', 'natural timing'],
        'reversed': False,
        'description': 'Symbolizes the harvest, natural cycles, and deserved rewards.'
    },
    'eiwaz': {
        'name': 'Eiwaz',
        'symbol': 'ᛇ',
        'meaning': 'Yew Tree, Protection, Endurance',
        'keywords': ['protection', 'endurance', 'transformation', 'mysteries', 'life-death'],
        'reversed': False,
        'description': 'Represents the yew tree, endurance, and life-death mysteries.'
    },
    'perthro': {
        'name': 'Perthro',
        'symbol': 'ᛈ',
        'meaning': 'Mystery, Fate, Chance',
        'keywords': ['mystery', 'fate', 'chance', 'secrets', 'destiny'],
        'reversed': False,
        'description': 'Symbolizes mysteries, fate, and the element of chance.'
    },
    'algiz': {
        'name': 'Algiz',
        'symbol': 'ᛉ',
        'meaning': 'Elk, Protection, Divine Connection',
        'keywords': ['protection', 'divine connection', 'higher self', 'spiritual defense'],
        'reversed': False,
        'description': 'Represents protection, divine connection, and spiritual defense.'
    },
    'sowilo': {
        'name': 'Sowilo',
        'symbol': 'ᛊ',
        'meaning': 'Sun, Victory, Success',
        'keywords': ['sun', 'victory', 'success', 'honor', 'achievement'],
        'reversed': False,
        'description': 'Symbolizes the sun, victory, and successful achievement.'
    },
    'tiwaz': {
        'name': 'Tiwaz',
        'symbol': 'ᛏ',
        'meaning': 'Tyr, Justice, Honor',
        'keywords': ['justice', 'honor', 'courage', 'sacrifice', 'leadership'],
        'reversed': False,
        'description': 'Represents justice, honor, and principled leadership.'
    },
    'berkano': {
        'name': 'Berkano',
        'symbol': 'ᛒ',
        'meaning': 'Birch, Growth, Rebirth',
        'keywords': ['growth', 'rebirth', 'fertility', 'new beginnings', 'motherhood'],
        'reversed': False,
        'description': 'Symbolizes growth, rebirth, and nurturing new beginnings.'
    },
    'ehwaz': {
        'name': 'Ehwaz',
        'symbol': 'ᛖ',
        'meaning': 'Horse, Movement, Trust',
        'keywords': ['movement', 'trust', 'cooperation', 'progress', 'partnership'],
        'reversed': False,
        'description': 'Represents movement, trust, and cooperative progress.'
    },
    'mannaz': {
        'name': 'Mannaz',
        'symbol': 'ᛗ',
        'meaning': 'Man, Humanity, Self',
        'keywords': ['humanity', 'self', 'relationships', 'cooperation', 'community'],
        'reversed': False,
        'description': 'Symbolizes humanity, self-awareness, and social relationships.'
    },
    'laguz': {
        'name': 'Laguz',
        'symbol': 'ᛚ',
        'meaning': 'Water, Flow, Intuition',
        'keywords': ['water', 'flow', 'intuition', 'emotions', 'unconscious'],
        'reversed': False,
        'description': 'Represents water, emotional flow, and intuitive wisdom.'
    },
    'ingwaz': {
        'name': 'Ingwaz',
        'symbol': 'ᛜ',
        'meaning': 'Ing, Fertility, Potential',
        'keywords': ['fertility', 'potential', 'growth', 'stored energy', 'completion'],
        'reversed': False,
        'description': 'Symbolizes fertility, potential energy, and gradual growth.'
    },
    'dagaz': {
        'name': 'Dagaz',
        'symbol': 'ᛞ',
        'meaning': 'Day, Dawn, Breakthrough',
        'keywords': ['day', 'dawn', 'breakthrough', 'clarity', 'transformation'],
        'reversed': False,
        'description': 'Represents the dawn, breakthrough moments, and positive transformation.'
    },
    'othala': {
        'name': 'Othala',
        'symbol': 'ᛟ',
        'meaning': 'Heritage, Home, Legacy',
        'keywords': ['heritage', 'home', 'legacy', 'ancestry', 'property'],
        'reversed': False,
        'description': 'Symbolizes heritage, home, and ancestral legacy.'
    }
}

# Reading types and their descriptions
READING_TYPES = {
    'single': {
        'name': 'Single Rune',
        'description': 'A single rune for quick guidance on a specific question',
        'num_runes': 1
    },
    'three': {
        'name': 'Three Rune Spread',
        'description': 'Past, Present, Future - A comprehensive reading for life situations',
        'num_runes': 3
    },
    'cross': {
        'name': 'Five Rune Cross',
        'description': 'A detailed reading covering multiple aspects of your situation',
        'num_runes': 5
    },
    'runic_cross': {
        'name': 'Runic Cross',
        'description': 'Traditional seven-rune spread for deep spiritual guidance',
        'num_runes': 7
    }
}

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
    'saved': "🔮 UHHH! Putre saved your rune reading in the ancient scrolls!"
}

# Personality messages cache
_personality_messages = None

def load_personality_messages():
    """Load messages from personality files with English fallbacks."""
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
        
        descriptions_path = os.path.join(project_root, "personalities", "putre", "descriptions.json")
        
        if os.path.exists(descriptions_path):
            with open(descriptions_path, encoding="utf-8") as f:
                descriptions = json.load(f)
                # Get the nordic_runes section
                nordic_runes_data = descriptions.get("discord", {}).get("roles_view_messages", {}).get("trickster", {}).get("nordic_runes", {})
                
                # Use English messages as base, override with all messages from descriptions
                merged_messages = ENGLISH_MESSAGES.copy()
                
                # Override with all available messages from descriptions.json
                for key, value in nordic_runes_data.items():
                    if key != "translations" and key != "positions":  # Skip special sections
                        merged_messages[key] = value
                
                # Also add labels as individual messages
                labels = nordic_runes_data.get("labels", {})
                for key, value in labels.items():
                    merged_messages[key] = value
                
                # IMPORTANT: Also include translations section
                translations_section = nordic_runes_data.get("translations", {})
                merged_messages["translations"] = translations_section
                merged_messages["positions"] = nordic_runes_data.get("positions", {})
                
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

def get_guidance_messages(category: str) -> dict:
    """Get guidance messages for a category (love, career, health, path)."""
    messages = load_personality_messages()
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
            
            descriptions_path = os.path.join(project_root, "personalities", "putre", "descriptions.json")
            
            if os.path.exists(descriptions_path):
                with open(descriptions_path, encoding="utf-8") as f:
                    descriptions = json.load(f)
                    # Get the actual guidance section
                    nordic_runes_data = descriptions.get("discord", {}).get("roles_view_messages", {}).get("trickster", {}).get("nordic_runes", {})
                    guidance_data = nordic_runes_data.get('guidance', {})
        except:
            guidance_data = {}
    
    return guidance_data.get(category, {})

def get_runes_list_content(page: int = 1) -> str:
    """Generate runes list content dynamically from RUNES data with translations and pagination."""
    # Load personality messages for translations
    messages = load_personality_messages()
    translations = messages.get('translations', {})
    
    # Load labels from descriptions.json - access labels section directly
    try:
        import json
        import os
        
        # Get project root and descriptions path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        descriptions_path = os.path.join(project_root, "personalities", "putre", "descriptions.json")
        
        labels_data = {}
        if os.path.exists(descriptions_path):
            with open(descriptions_path, encoding="utf-8") as f:
                descriptions = json.load(f)
                # Get the labels section directly
                labels_data = descriptions.get("discord", {}).get("roles_view_messages", {}).get("trickster", {}).get("nordic_runes", {}).get("labels", {})
    except:
        labels_data = {}
    
    # Get all runes as list for pagination
    all_runes = list(RUNES.items())
    
    # Calculate pagination - 8 runes per page without keywords
    runes_per_page = 8
    total_pages = 3
    start_idx = (page - 1) * runes_per_page
    end_idx = start_idx + runes_per_page
    page_runes = all_runes[start_idx:end_idx]
    
    # Page titles with rune ranges - get from descriptions.json with fallback
    page_titles = {
        1: messages.get('runes_page_1_title', "🔮 **THE ELDER FUTHARK - RUNES I (Fehu to Wunjo)** 🔮"),
        2: messages.get('runes_page_2_title', "🔮 **THE ELDER FUTHARK - RUNES II ( Hagalaz to Sowilo)** 🔮"), 
        3: messages.get('runes_page_3_title', "🔮 **THE ELDER FUTHARK - RUNES III (Tiwaz to Othala)** 🔮")
    }
    
    content = page_titles.get(page, f"🔮 **THE ELDER FUTHARK - RUNES {page}** 🔮") + "\n\n" + "-"*55 + "\n\n"

    # Generate content for this page without keywords
    for rune_key, rune_data in page_runes:
        symbol = rune_data.get('symbol', '?')
        name = rune_data.get('name', 'Unknown')
        meaning = rune_data.get('meaning', 'Unknown')
        interpretation = rune_data.get('description', 'No description')
        
        # Use translations if available
        rune_translation = translations.get(rune_key, {})
        if rune_translation:
            meaning = rune_translation.get('meaning', meaning)
            interpretation = rune_translation.get('interpretation', interpretation)
        
        title_interpretation = labels_data.get("interpretation", "Interpretation:")
        content += f"**{symbol} {name}** - {meaning}\n"
        content += f"{title_interpretation} {interpretation}\n\n"
    
    return content
