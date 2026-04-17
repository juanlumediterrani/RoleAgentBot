"""
Nordic Runes Messages Module
Contains rune definitions, interpretations, and messages with personality support.
"""

from agent_logging import get_logger
logger = get_logger('nordic_runes_messages')

# Elder Futhark runes data (English fallback)
RUNES = {
    'fehu':     {'symbol': 'ᚠ', 'name': 'Fehu',     'meaning': 'Wealth, Cattle, Possessions',        'keywords': ['wealth', 'abundance', 'success', 'prosperity', 'material gain'],              'description': 'Represents material wealth, prosperity, and success in financial matters.'},
    'uruz':     {'symbol': 'ᚢ', 'name': 'Uruz',     'meaning': 'Strength, Power, Primal Energy',     'keywords': ['strength', 'power', 'energy', 'vitality', 'courage'],                        'description': 'Symbolizes physical strength, primal energy, and the ability to overcome challenges.'},
    'thurisaz': {'symbol': 'ᚦ', 'name': 'Thurisaz', 'meaning': 'Thor, Giant, Thorn',                 'keywords': ['protection', 'defense', 'chaos', 'change', 'conflict'],                      'description': 'Represents both protection and conflict. Signifies the power of Thor.'},
    'ansuz':    {'symbol': 'ᚨ', 'name': 'Ansuz',    'meaning': 'God, Odin, Communication',           'keywords': ['communication', 'wisdom', 'divine', 'knowledge', 'inspiration'],             'description': 'Represents divine communication, wisdom, and inspiration.'},
    'raidho':   {'symbol': 'ᚱ', 'name': 'Raidho',   'meaning': 'Journey, Travel, Movement',          'keywords': ['journey', 'travel', 'movement', 'change', 'progress'],                       'description': 'Represents physical and spiritual journeys.'},
    'kenaz':    {'symbol': 'ᚲ', 'name': 'Kenaz',    'meaning': 'Torch, Knowledge, Vision',           'keywords': ['knowledge', 'vision', 'creativity', 'insight', 'clarity'],                   'description': 'Represents knowledge, creativity, and illumination.'},
    'gebo':     {'symbol': 'ᚷ', 'name': 'Gebo',     'meaning': 'Gift, Partnership, Exchange',        'keywords': ['gift', 'partnership', 'exchange', 'balance', 'harmony'],                     'description': 'Represents gifts, partnerships, and balanced exchanges.'},
    'wunjo':    {'symbol': 'ᚹ', 'name': 'Wunjo',    'meaning': 'Joy, Pleasure, Harmony',             'keywords': ['joy', 'pleasure', 'harmony', 'success', 'fulfillment'],                      'description': 'Represents joy, pleasure, and harmony.'},
    'hagalaz':  {'symbol': 'ᚺ', 'name': 'Hagalaz',  'meaning': 'Hail, Disruption, Change',           'keywords': ['disruption', 'change', 'chaos', 'transformation', 'crisis'],                 'description': 'Represents disruptive change and transformation.'},
    'nauthiz':  {'symbol': 'ᚾ', 'name': 'Nauthiz',  'meaning': 'Need, Necessity, Constraint',        'keywords': ['need', 'necessity', 'constraint', 'discipline', 'survival'],                 'description': 'Represents need, necessity, and constraint.'},
    'isa':      {'symbol': 'ᛁ', 'name': 'Isa',      'meaning': 'Ice, Stillness, Clarity',            'keywords': ['ice', 'stillness', 'clarity', 'patience', 'stasis'],                        'description': 'Represents ice, stillness, and clarity.'},
    'jera':     {'symbol': 'ᛃ', 'name': 'Jera',     'meaning': 'Harvest, Year, Cycle',               'keywords': ['harvest', 'year', 'cycle', 'reward', 'completion'],                          'description': 'Represents the harvest and the completion of cycles.'},
    'eiwaz':    {'symbol': 'ᛇ', 'name': 'Eiwaz',    'meaning': 'Yew Tree, Protection, Endurance',   'keywords': ['protection', 'endurance', 'transformation', 'death', 'rebirth'],             'description': 'Represents the yew tree and endurance.'},
    'perthro':  {'symbol': 'ᛈ', 'name': 'Perthro',  'meaning': 'Mystery, Fate, Chance',             'keywords': ['mystery', 'fate', 'chance', 'secrets', 'destiny'],                           'description': 'Represents mystery, fate, and chance.'},
    'algiz':    {'symbol': 'ᛉ', 'name': 'Algiz',    'meaning': 'Protection, Shield, Defense',        'keywords': ['protection', 'shield', 'defense', 'connection', 'divine'],                   'description': 'Represents protection and divine connection.'},
    'sowilo':   {'symbol': 'ᛊ', 'name': 'Sowilo',   'meaning': 'Sun, Victory, Success',              'keywords': ['sun', 'victory', 'success', 'honor', 'achievement'],                        'description': 'Represents the sun and victory.'},
    'tiwaz':    {'symbol': 'ᛏ', 'name': 'Tiwaz',    'meaning': 'Tyr, Justice, Sacrifice',            'keywords': ['justice', 'sacrifice', 'honor', 'courage', 'leadership'],                   'description': 'Represents Tyr and justice.'},
    'berkano':  {'symbol': 'ᛒ', 'name': 'Berkano',  'meaning': 'Birch, Growth, Rebirth',             'keywords': ['growth', 'rebirth', 'fertility', 'new beginnings', 'family'],                'description': 'Represents the birch tree and growth.'},
    'ehwaz':    {'symbol': 'ᛖ', 'name': 'Ehwaz',    'meaning': 'Horse, Movement, Trust',             'keywords': ['movement', 'trust', 'cooperation', 'progress', 'partnership'],               'description': 'Represents the horse and movement.'},
    'mannaz':   {'symbol': 'ᛗ', 'name': 'Mannaz',   'meaning': 'Humanity, Mankind, Self',            'keywords': ['humanity', 'mankind', 'self', 'community', 'relationships'],                 'description': 'Represents humanity and the self.'},
    'laguz':    {'symbol': 'ᛚ', 'name': 'Laguz',    'meaning': 'Water, Flow, Intuition',             'keywords': ['water', 'flow', 'intuition', 'emotions', 'healing'],                        'description': 'Represents water and flow.'},
    'ingwaz':   {'symbol': 'ᛜ', 'name': 'Ingwaz',   'meaning': 'Ing, Fertility, Potential',          'keywords': ['fertility', 'potential', 'growth', 'masculine energy', 'creation'],          'description': 'Represents Ing and fertility.'},
    'dagaz':    {'symbol': 'ᛞ', 'name': 'Dagaz',    'meaning': 'Day, Dawn, Breakthrough',            'keywords': ['day', 'dawn', 'breakthrough', 'clarity', 'transformation'],                  'description': 'Represents the day and dawn.'},
    'othala':   {'symbol': 'ᛟ', 'name': 'Othala',   'meaning': 'Heritage, Home, Inheritance',        'keywords': ['heritage', 'home', 'inheritance', 'family', 'tradition'],                    'description': 'Represents heritage and home.'},
}

# Reading types configuration
READING_TYPES = {
    'single':     {'name': 'Single Rune',          'description': 'One rune for direct guidance',            'runes_count': 1, 'positions': ['Center']},
    'three':      {'name': 'Three Runes',           'description': 'Past-Present-Future timeline reading',    'runes_count': 3, 'positions': ['Past', 'Present', 'Future']},
    'cross':      {'name': 'Five Rune Cross',       'description': 'Five-element cross for comprehensive analysis', 'runes_count': 5, 'positions': ['Center', 'North', 'South', 'East', 'West']},
    'runic_cross':{'name': 'Seven Rune Runic Cross','description': 'Advanced seven-rune spiritual guidance',  'runes_count': 7, 'positions': ['Center', 'North', 'South', 'East', 'West', 'Above', 'Below']},
}

def get_rune(rune_key: str) -> dict:
    return RUNES.get(rune_key, {})

def get_all_runes() -> dict:
    return RUNES

def get_reading_type(type_key: str) -> dict:
    return READING_TYPES.get(type_key, {})

def get_all_reading_types() -> dict:
    return READING_TYPES

def validate_rune_key(rune_key: str) -> bool:
    return rune_key in RUNES

def validate_reading_type(type_key: str) -> bool:
    return type_key in READING_TYPES

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
        try:
            from agent_runtime import get_personality_directory
            server_dir = get_personality_directory(server_id)
            if server_dir:
                return server_dir
        except:
            pass
        default_personality = AGENT_CFG.get("default_personality", "rab")
        default_language = AGENT_CFG.get("default_language", "en-US")
        personality_path = os.path.join(project_root, "personalities", default_personality, default_language, "personality.json")
        return os.path.dirname(personality_path)
    except:
        return os.path.join(project_root, "personalities", "putre")


def _get_shaman_path(server_id: str = None) -> str:
    """Return path to databases/{personality}/{language}/descriptions/shaman.json."""
    personality_dir = _get_personality_dir(server_id)
    parts = personality_dir.split(os.sep)
    if 'personalities' in parts:
        parts[parts.index('personalities')] = 'databases'
    return os.path.join(os.sep.join(parts), 'descriptions', 'shaman.json')


def _get_runesplane_path(server_id: str = None) -> str:
    """Return path to databases/{personality}/{language}/descriptions/runesplane.json."""
    personality_dir = _get_personality_dir(server_id)
    parts = personality_dir.split(os.sep)
    if 'personalities' in parts:
        parts[parts.index('personalities')] = 'databases'
    return os.path.join(os.sep.join(parts), 'descriptions', 'runesplane.json')


def _load_shaman_json(server_id: str = None) -> dict:
    """Load databases/{personality}/{language}/descriptions/shaman.json, return {} on missing/error."""
    import json
    path = _get_shaman_path(server_id)
    try:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f'Failed to load shaman.json from {path}: {e}')
    return {}


def _load_runesplane_json(server_id: str = None) -> dict:
    """Load databases/{personality}/{language}/descriptions/runesplane.json, return {} on missing/error."""
    import json
    path = _get_runesplane_path(server_id)
    try:
        if os.path.exists(path):
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        logger.warning(f'runesplane.json not found at {path}, using RUNES fallback')
    except Exception as e:
        logger.error(f'Failed to load runesplane.json from {path}: {e}')
    return {}


def _runes_fallback_data() -> dict:
    """Build runes_data dict from inline RUNES constant (English fallback)."""
    return {
        key: {
            'meaning': info.get('meaning', 'Unknown'),
            'keywords': info.get('keywords', []),
            'interpretation': info.get('description', 'No description'),
        }
        for key, info in RUNES.items()
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
    'runic_cross_cast': "🔮 **SEVEN RUNE RUNIC CROSS CASTING** 🔮",
    'history': "🔮 **ANCIENT RUNES HISTORY** (Last {count}) 🔮",
    'types': "🔮 **RUNE CASTING TYPES** 🔮",
    'runes_list': "🔮 **ELDER FUTHARK RUNES** 🔮",
    'help': "🔮 **NORDIC RUNES WISDOM** 🔮",
    'runes_list_content': 'DYNAMIC_GENERATED',  # This will be replaced by get_runes_list_content()
    'history_empty': "🔮 You have no previous rune readings. Cast your first runes with `!runes cast`!",
    'history_header': "🔮 **YOUR ANCIENT RUNES READINGS** (Last {count})",
    'history_entry': "**ID {id}** - {type}\nQuestion: {question}\nRunes: {runes}\nDate: {date}",
    'stats': "\n**Total Readings:** {total}\n**Favorite Type:** {favorite}",
    'interpretation_header': "**Question:** {question}\n\n",
    'title': "**🔮 Nordic Runes**",
    'description': "Seek guidance through the Elder Futhark runes. Each symbol carries ancient wisdom.",
    'title_available_readings': "🌔 **Reading Types** 🌔\n",
    'available_readings': "- **Single rune** (quick guidance): One symbol pointing to the present situation.\n - **Three runes** (timeline): Past (Urðr), Present (Verðandi) and Future (Skuld).\n - **Five rune cross** (full map): Five dimensions of your current situation.\n - **Seven rune net** (Yggdrasil): The most complete reading, connecting all layers.\n",
    'history': "📓 **Reading History** 📓",
    'error_history': "❌ **No readings found:** No previous readings in memory.",
    'how_to_use': "**How to use:**\n 1. Choose a reading type from the dropdown below.\n 2. Enter your question in the modal that appears.\n 3. Your reading will arrive as a private message.\n",
    'runes_title': "**The 24 Elder Futhark Runes:**",
    'runes_page_1_title': "🔮 **THE ELDER FUTHARK - RUNES I (Fehu to Wunjo)** 🔮",
    'runes_page_2_title': "🔮 **THE ELDER FUTHARK - RUNES II (Hagalaz to Sowilo)** 🔮",
    'runes_page_3_title': "🔮 **THE ELDER FUTHARK - RUNES III (Tiwaz to Othala)** 🔮",
    'types_content': "🔮 **RUNE READING TYPES** 🔮\n\n**single** - Single Rune\n└ Direct answer - Uses 1 rune\n\n**three** - Three Runes\n└ Past, Present, Future - Uses 3 runes\n\n**cross** - Five Rune Cross\n└ Full situation map - Uses 5 runes\n\n**runic_cross** - Runic Cross\n└ Deep seven-rune reading - Uses 7 runes\n",
    'help_content': "🔮 **NORDIC RUNES WISDOM** 🔮\n\nThe Elder Futhark are ancient Norse symbols used for divination and guidance.\n\n**Available readings:**\n• **Single rune** - Direct answer to a specific question\n• **Three runes** - Past, Present, Future\n• **Five rune cross** - Full situation analysis\n• **Seven rune cross** - Deep spiritual guidance\n\nChoose your casting type and ask the ancient runes!",
    # labels for rune fields
    'question': "Question",
    'meaning': "Meaning",
    'keywords': "Keywords",
    'interpretation': "Interpretation",
    'success': "🔮 The ancient runes have spoken!",
    'saved': "🔮 Your rune reading has been saved in the ancient scrolls!"
}

# Personality messages cache
_personality_messages = None

def load_personality_messages(server_id: str = None):
    """Load messages from shaman.json + runesplane.json with English fallbacks."""
    global _personality_messages
    _personality_messages = None

    try:
        import json

        # Primary source: databases/{personality}/{language}/descriptions/shaman.json
        shaman_data = _load_shaman_json(server_id)
        nordic_runes_data = shaman_data.get('nordic_runes', {})

        merged_messages = ENGLISH_MESSAGES.copy()
        for key, value in nordic_runes_data.items():
            if key not in ('translations', 'positions'):
                merged_messages[key] = value
        for key, value in nordic_runes_data.get('labels', {}).items():
            merged_messages[key] = value

        # Load translations/positions/guidance from runesplane.json
        runesplane_data = _load_runesplane_json(server_id)
        merged_messages['translations'] = runesplane_data.get('translations', {})
        merged_messages['positions']    = runesplane_data.get('positions', {})
        merged_messages['guidance']     = runesplane_data.get('guidance', {})

        _personality_messages = merged_messages
        return _personality_messages

    except Exception as e:
        logger.error(f'Failed to load personality messages: {e}')
        _personality_messages = ENGLISH_MESSAGES.copy()
        return _personality_messages

def get_message(message_key: str, page: int = 1, server_id: str = None) -> str:
    """Get message by key with personality support and optional page parameter."""
    messages = load_personality_messages(server_id)
    
    # Special handling for runes_list_content to use dynamic generation with pagination
    if message_key == 'runes_list_content':
        return get_runes_list_content(page, server_id)
    
    result = messages.get(message_key, ENGLISH_MESSAGES.get(message_key, f"Unknown message: {message_key}"))
    
    return result

def clear_message_cache():
    """Clear the personality messages cache to force reload."""
    global _personality_messages
    _personality_messages = None

def get_guidance_messages(category: str, server_id: str = None) -> dict:
    """Get guidance messages for a category from runesplane.json."""
    messages = load_personality_messages(server_id)
    guidance_data = messages.get('guidance', {})
    if isinstance(guidance_data, str) or not guidance_data:
        guidance_data = _load_runesplane_json(server_id).get('guidance', {})
    return guidance_data.get(category, {})

def get_runes_list_content(page: int = 1, server_id: str = None) -> str:
    """Generate runes list content dynamically from runesplane.json with pagination."""
    # Load personality messages for page titles
    messages = load_personality_messages(server_id)

    # Labels from shaman.json
    labels_data = _load_shaman_json(server_id).get('nordic_runes', {}).get('labels', {})

    # Rune translations from runesplane.json, fallback to inline RUNES
    runesplane = _load_runesplane_json(server_id)
    runes_data = runesplane.get('translations') or _runes_fallback_data()
    
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
