"""
Rune Data Module
Contains rune definitions and reading types for the Nordic Runes system.
"""

from typing import Dict, Any, List

# Elder Futhark runes data
RUNES = {
    'fehu': {
        'symbol': 'ᚠ',
        'name': 'Fehu',
        'meaning': 'Wealth, Cattle, Possessions',
        'keywords': ['wealth', 'abundance', 'success', 'prosperity', 'material gain'],
        'description': 'Represents material wealth, prosperity, and success in financial matters. It signifies new beginnings, opportunities, and the flow of energy.'
    },
    'uruz': {
        'symbol': 'ᚢ',
        'name': 'Uruz',
        'meaning': 'Strength, Power, Primal Energy',
        'keywords': ['strength', 'power', 'energy', 'vitality', 'courage'],
        'description': 'Symbolizes physical strength, primal energy, and the ability to overcome challenges. Represents untamed power and instinctual force.'
    },
    'thurisaz': {
        'symbol': 'ᚦ',
        'name': 'Thurisaz',
        'meaning': 'Thor, Giant, Thorn',
        'keywords': ['protection', 'defense', 'chaos', 'change', 'conflict'],
        'description': 'Represents both protection and conflict. Signifies the power of Thor, defensive strength, and the chaos necessary for change.'
    },
    'ansuz': {
        'symbol': 'ᚨ',
        'name': 'Ansuz',
        'meaning': 'God, Odin, Communication',
        'keywords': ['communication', 'wisdom', 'divine', 'knowledge', 'inspiration'],
        'description': 'Represents divine communication, wisdom, and inspiration. Signifies the power of words, magic, and connection with the gods.'
    },
    'raidho': {
        'symbol': 'ᚱ',
        'name': 'Raidho',
        'meaning': 'Journey, Travel, Movement',
        'keywords': ['journey', 'travel', 'movement', 'change', 'progress'],
        'description': 'Represents physical and spiritual journeys. Signifies movement, change, and the path of life.'
    },
    'kenaz': {
        'symbol': 'ᚲ',
        'name': 'Kenaz',
        'meaning': 'Torch, Knowledge, Vision',
        'keywords': ['knowledge', 'vision', 'creativity', 'insight', 'clarity'],
        'description': 'Represents knowledge, creativity, and illumination. Signifies the light of understanding and creative fire.'
    },
    'gebo': {
        'symbol': 'ᚷ',
        'name': 'Gebo',
        'meaning': 'Gift, Partnership, Exchange',
        'keywords': ['gift', 'partnership', 'exchange', 'balance', 'harmony'],
        'description': 'Represents gifts, partnerships, and balanced exchanges. Signifies harmony, generosity, and fair exchange.'
    },
    'wunjo': {
        'symbol': 'ᚹ',
        'name': 'Wunjo',
        'meaning': 'Joy, Pleasure, Harmony',
        'keywords': ['joy', 'pleasure', 'harmony', 'success', 'fulfillment'],
        'description': 'Represents joy, pleasure, and harmony. Signifies success, fulfillment, and emotional well-being.'
    },
    'hagalaz': {
        'symbol': 'ᚺ',
        'name': 'Hagalaz',
        'meaning': 'Hail, Disruption, Change',
        'keywords': ['disruption', 'change', 'chaos', 'transformation', 'crisis'],
        'description': 'Represents disruptive change and transformation. Signifies the hail that breaks down old patterns to create new ones.'
    },
    'nauthiz': {
        'symbol': 'ᚾ',
        'name': 'Nauthiz',
        'meaning': 'Need, Necessity, Constraint',
        'keywords': ['need', 'necessity', 'constraint', 'discipline', 'survival'],
        'description': 'Represents need, necessity, and constraint. Signifies the discipline required to overcome challenges and survive.'
    },
    'isa': {
        'symbol': 'ᛁ',
        'name': 'Isa',
        'meaning': 'Ice, Stillness, Clarity',
        'keywords': ['ice', 'stillness', 'clarity', 'patience', 'stasis'],
        'description': 'Represents ice, stillness, and clarity. Signifies the need for patience and the power of stillness.'
    },
    'jera': {
        'symbol': 'ᛃ',
        'name': 'Jera',
        'meaning': 'Harvest, Year, Cycle',
        'keywords': ['harvest', 'year', 'cycle', 'reward', 'completion'],
        'description': 'Represents the harvest and the completion of cycles. Signifies reward for effort and natural timing.'
    },
    'eiwaz': {
        'symbol': 'ᛇ',
        'name': 'Eiwaz',
        'meaning': 'Yew Tree, Protection, Endurance',
        'keywords': ['protection', 'endurance', 'transformation', 'death', 'rebirth'],
        'description': 'Represents the yew tree and endurance. Signifies protection, transformation, and the cycle of death and rebirth.'
    },
    'perthro': {
        'symbol': 'ᛈ',
        'name': 'Perthro',
        'meaning': 'Mystery, Fate, Chance',
        'keywords': ['mystery', 'fate', 'chance', 'secrets', 'destiny'],
        'description': 'Represents mystery, fate, and chance. Signifies the unknown, secrets, and the workings of destiny.'
    },
    'algiz': {
        'symbol': 'ᛉ',
        'name': 'Algiz',
        'meaning': 'Protection, Shield, Defense',
        'keywords': ['protection', 'shield', 'defense', 'connection', 'divine'],
        'description': 'Represents protection and divine connection. Signifies the shield of protection and connection with higher powers.'
    },
    'sowilo': {
        'symbol': 'ᛊ',
        'name': 'Sowilo',
        'meaning': 'Sun, Victory, Success',
        'keywords': ['sun', 'victory', 'success', 'honor', 'achievement'],
        'description': 'Represents the sun and victory. Signifies success, honor, and the achievement of goals.'
    },
    'tiwaz': {
        'symbol': 'ᛏ',
        'name': 'Tiwaz',
        'meaning': 'Tyr, Justice, Sacrifice',
        'keywords': ['justice', 'sacrifice', 'honor', 'courage', 'leadership'],
        'description': 'Represents Tyr and justice. Signifies honor, courage, leadership, and the sacrifice required for justice.'
    },
    'berkano': {
        'symbol': 'ᛒ',
        'name': 'Berkano',
        'meaning': 'Birch, Growth, Rebirth',
        'keywords': ['growth', 'rebirth', 'fertility', 'new beginnings', 'family'],
        'description': 'Represents the birch tree and growth. Signifies rebirth, fertility, new beginnings, and family matters.'
    },
    'ehwaz': {
        'symbol': 'ᛖ',
        'name': 'Ehwaz',
        'meaning': 'Horse, Movement, Trust',
        'keywords': ['movement', 'trust', 'cooperation', 'progress', 'partnership'],
        'description': 'Represents the horse and movement. Signifies trust, cooperation, and steady progress toward goals.'
    },
    'mannaz': {
        'symbol': 'ᛗ',
        'name': 'Mannaz',
        'meaning': 'Humanity, Mankind, Self',
        'keywords': ['humanity', 'mankind', 'self', 'community', 'relationships'],
        'description': 'Represents humanity and the self. Signifies community, relationships, and understanding of human nature.'
    },
    'laguz': {
        'symbol': 'ᛚ',
        'name': 'Laguz',
        'meaning': 'Water, Flow, Intuition',
        'keywords': ['water', 'flow', 'intuition', 'emotions', 'healing'],
        'description': 'Represents water and flow. Signifies intuition, emotions, healing, and the power of the unconscious.'
    },
    'ingwaz': {
        'symbol': 'ᛜ',
        'name': 'Ingwaz',
        'meaning': 'Ing, Fertility, Potential',
        'keywords': ['fertility', 'potential', 'growth', 'masculine energy', 'creation'],
        'description': 'Represents Ing and fertility. Signifies potential, growth, masculine energy, and creative power.'
    },
    'dagaz': {
        'symbol': 'ᛞ',
        'name': 'Dagaz',
        'meaning': 'Day, Dawn, Breakthrough',
        'keywords': ['day', 'dawn', 'breakthrough', 'clarity', 'transformation'],
        'description': 'Represents the day and dawn. Signifies breakthrough, clarity, and transformation from darkness to light.'
    },
    'othala': {
        'symbol': 'ᛟ',
        'name': 'Othala',
        'meaning': 'Heritage, Home, Inheritance',
        'keywords': ['heritage', 'home', 'inheritance', 'family', 'tradition'],
        'description': 'Represents heritage and home. Signifies family, tradition, inheritance, and the security of home.'
    }
}

# Reading types configuration
READING_TYPES = {
    'single': {
        'name': 'Single Rune',
        'description': 'One rune for direct guidance on a specific question',
        'runes_count': 1,
        'positions': ['Center']
    },
    'three': {
        'name': 'Three Runes',
        'description': 'Past-Present-Future timeline reading',
        'runes_count': 3,
        'positions': ['Past', 'Present', 'Future']
    },
    'cross': {
        'name': 'Five Rune Cross',
        'description': 'Five-element cross reading for comprehensive analysis',
        'runes_count': 5,
        'positions': ['Center', 'North', 'South', 'East', 'West']
    },
    'runic_cross': {
        'name': 'Seven Rune Runic Cross',
        'description': 'Advanced seven-rune reading for spiritual guidance',
        'runes_count': 7,
        'positions': ['Center', 'North', 'South', 'East', 'West', 'Above', 'Below']
    }
}

def get_rune(rune_key: str) -> Dict[str, Any]:
    """Get rune data by key."""
    return RUNES.get(rune_key, {})

def get_all_runes() -> Dict[str, Dict[str, Any]]:
    """Get all runes data."""
    return RUNES

def get_reading_type(type_key: str) -> Dict[str, Any]:
    """Get reading type configuration by key."""
    return READING_TYPES.get(type_key, {})

def get_all_reading_types() -> Dict[str, Dict[str, Any]]:
    """Get all reading types."""
    return READING_TYPES

def get_random_rune() -> str:
    """Get a random rune key."""
    import random
    return random.choice(list(RUNES.keys()))

def validate_rune_key(rune_key: str) -> bool:
    """Validate if rune key exists."""
    return rune_key in RUNES

def validate_reading_type(type_key: str) -> bool:
    """Validate if reading type exists."""
    return type_key in READING_TYPES
