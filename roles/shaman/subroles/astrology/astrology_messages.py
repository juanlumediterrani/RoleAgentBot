"""
Astrology Messages Module
Contains Hebrew letter definitions, reading types, and messages.
Fallback messages are in English. Translations are loaded from:
- personalities/{personality}/{language}/descriptions/shaman.json (UI messages)
- manuals/{language}/astrologyplane.json (letter data, positions, guidance)
"""

import json
import os
from agent_logging import get_logger

logger = get_logger('astrology_messages')

# ============================================================================
# ENGLISH FALLBACK MESSAGES (in code)
# ============================================================================

ENGLISH_MESSAGES = {
    'welcome': "✨ Welcome to Sefer Yetzirah Astrology! I can interpret the 32 paths of wisdom through Hebrew letters.",
    'birth_title': "🌟 BIRTH CHART (MAZAL HA'LEIDA) 🌟",
    'moment_title': "⏰ MOMENT READING (SHA'AT HA'SHE'ELA) ⏰",
    'year_title': "📅 PERSONAL YEAR (SHANAH PERATIT) 📅",
    'integrated_title': "🔮 INTEGRATED READING 🔮",
    'letters_title': "📜 THE 22 HEBREW LETTERS 📜",
    'history': "📓 **ASTROLOGY READING HISTORY** (Last {count}) 📓",
    'stats': "\n**Total Readings:** {total}\n**Favorite Type:** {favorite}",
    'help_content': "The Sefer Yetzirah system reveals the 32 paths of wisdom through 22 Hebrew letters (3 Mothers, 7 Doubles, 12 Simples). Each reading interprets the spiritual forces at work in a situation.",
    'invalid_command': "Invalid command. Use `!astrology help` for available commands.",
    'missing_birth_date': "Please provide your birth date in format YYYY-MM-DD.",
    'missing_birth_year': "Please provide your birth year or save your birth data first with `!astrology save_birth`.",
    'no_birth_data_saved': "No birth data saved. Please save your birth data first with `!astrology save_birth YYYY-MM-DD`.",
    'invalid_date_format': "Invalid date format. Please use YYYY-MM-DD for dates and HH:MM for times.",
    'birth_data_saved': "✨ Your birth data has been saved successfully!",
    'history_empty': "📓 You have no previous astrology readings. Start with `!astrology birth`!",
    'error': "An error occurred. Please try again.",
    # Labels for UI fields
    'question': "Question",
    'element': "Element",
    'planet': "Planet",
    'sign': "Sign",
    'meaning': "Meaning",
    'keywords': "Keywords",
    'interpretation': "Interpretation",
    # Hebrew letters page titles
    'hebrew_letters_page_1_title': "📜 THE 22 HEBREW LETTERS - MOTHER LETTERS (I) 📜",
    'hebrew_letters_page_2_title': "📜 THE 22 HEBREW LETTERS - DOUBLE LETTERS (II) 📜",
    'hebrew_letters_page_3_title': "📜 THE 22 HEBREW LETTERS - SIMPLE LETTERS (III) 📜",
    'nav_page': "Page",
}

# ============================================================================
# READING TYPES
# ============================================================================

READING_TYPES = {
    'birth': {
        'name': 'Birth Chart (Mazal Ha\'Leida)',
        'description': 'Permanent soul pattern from birth date and time',
        'input_required': ['birth_date'],
        'input_optional': ['birth_time'],
        'question_required': False,
        'output_layers': ['element', 'planet', 'sign'],
        'positions': ['Elemento Natal', 'Planeta Rector', 'Signo Zodiacal'],
        'calculation_function': 'calculate_birth_chart'
    },
    'moment': {
        'name': 'Moment Reading (Sha\'at HaShe\'ela)',
        'description': 'Analysis of a specific moment for a question',
        'input_required': ['question_date'],
        'input_optional': ['question_time'],
        'question_required': True,
        'output_layers': ['element', 'planet', 'sign'],
        'positions': ['Elemento del Momento', 'Planeta del Día', 'Signo del Mes'],
        'calculation_function': 'calculate_moment_reading'
    },
    'year': {
        'name': 'Personal Year (Shanah Peratit)',
        'description': 'Annual cycle analysis based on birth year and current year',
        'input_required': ['birth_year'],
        'input_optional': [],
        'question_required': False,
        'output_layers': ['personal_number', 'personal_letter', 'collective_year'],
        'positions': ['Número Personal', 'Letra del Año', 'Año Colectivo'],
        'calculation_function': 'calculate_personal_year'
    },
    'integrated': {
        'name': 'Integrated Reading',
        'description': 'Combined analysis of birth, year, and moment',
        'input_required': ['birth_date', 'question_date'],
        'input_optional': ['birth_time', 'question_time'],
        'question_required': True,
        'output_layers': ['birth_chart', 'personal_year', 'moment_reading'],
        'positions': ['Carta Natal (Permanente)', 'Año Personal (Cíclico)', 'Momento (Inmediato)'],
        'calculation_function': 'calculate_integrated_reading'
    }
}

# ============================================================================
# HEBREW LETTER DATA (English fallback - translations in astrologyplane.json)
# ============================================================================

HEBREW_LETTERS = {
    # 3 Mother Letters
    'alef': {
        'hebrew': 'א',
        'name': 'Alef',
        'gematria': 1,
        'category': 'mother',
        'element': 'Air',
        'season': 'Temperate (spring/autumn)',
        'months': [3, 4, 9, 10],
        'body_part': 'Chest / Breathing',
        'world': 'Intermediate space',
        'soul_nature': 'Mediating, balancing, broad intellectual',
        'meaning': 'Balance, mediation, broad intellect',
        'keywords': ['balance', 'mediation', 'intellect', 'breathing', 'connection', 'air'],
        'description': 'The mediating soul that connects and balances. Substrate of the soul that allows broad intellectual understanding. Work in the chest and breathing.',
        'interpretation_guidance': 'An Air soul has its main correction in the chest and breathing. It is mediating by nature.',
    },
    'mem': {
        'hebrew': 'מ',
        'name': 'Mem',
        'gematria': 40,
        'category': 'mother',
        'element': 'Water',
        'season': 'Winter',
        'months': [12, 1, 2],
        'body_part': 'Belly / Fluids',
        'world': 'The earth',
        'soul_nature': 'Deep, emotional, receptive, inward-oriented',
        'meaning': 'Emotional depth, receptivity, interiority',
        'keywords': ['depth', 'emotion', 'receptivity', 'interior', 'fluidity', 'water'],
        'description': 'The deep and receptive soul. Oriented toward the interior and emotions. Work in the belly and emotions. Descent, inner gestation.',
        'interpretation_guidance': 'A Water soul has its main correction in the belly and emotions. It is receptive and deep.',
    },
    'shin': {
        'hebrew': 'ש',
        'name': 'Shin',
        'gematria': 300,
        'category': 'mother',
        'element': 'Fire',
        'season': 'Summer',
        'months': [6, 7, 8],
        'body_part': 'Head / Mind',
        'world': 'The heavens',
        'soul_nature': 'Expansive, mental, fiery, upward-oriented',
        'meaning': 'Expansion, fiery mind, upward orientation',
        'keywords': ['expansion', 'mind', 'fire', 'transformation', 'clarity', 'fire'],
        'description': 'The expansive and mental soul. Oriented toward the heights and intellectual clarity. Work in the head and mind. Great mental changes.',
        'interpretation_guidance': 'A Fire soul has its main correction in the head and mind. It is expansive and fiery.',
    },
    # 7 Double Letters
    'bet': {
        'hebrew': 'ב',
        'name': 'Bet',
        'gematria': 2,
        'category': 'double',
        'planet': 'Saturn',
        'symbol': '♄',
        'day': 'Saturday',
        'day_index': 5,
        'chaldean_order': 0,
        'duality': 'Wisdom / Foolishness',
        'duality_light': 'Deep wisdom, patience, discipline',
        'duality_shadow': 'Stubborn foolishness, rigidity, pessimism',
        'sensory_gate': 'Right eye',
        'meaning': 'Limits, time, deep wisdom',
        'keywords': ['limits', 'time', 'wisdom', 'restriction', 'karma', 'discipline'],
        'description': 'Planet of limits and wisdom trials. Brings deep wisdom or stubborn foolishness depending on tikún. You harvest what you sow.',
        'interpretation_guidance': 'Saturn rules limits and time. The duality wisdom/foolishness depends on spiritual work.',
        'nature_of_inquiry': 'Asuntos de límites, tiempo, herencias, karma, restricciones'
    },
    'gimel': {
        'hebrew': 'ג',
        'name': 'Gimel',
        'gematria': 3,
        'category': 'double',
        'planet': 'Jupiter',
        'symbol': '♃',
        'day': 'Thursday',
        'day_index': 3,
        'chaldean_order': 1,
        'duality': 'Wealth / Poverty',
        'duality_light': 'Abundance, generosity, expansion',
        'duality_shadow': 'Poverty, avarice, excess',
        'sensory_gate': 'Left eye',
        'meaning': 'Expansion, justice, abundance',
        'keywords': ['expansion', 'justice', 'abundance', 'spiritual journeys', 'teaching', 'learning'],
        'description': 'Planet of expansion and abundance. Possible wealth or poverty depending on how its duality is worked. Spiritual journeys.',
        'interpretation_guidance': 'Jupiter brings expansion. The duality wealth/poverty depends on resource use.',
        'nature_of_inquiry': 'Asuntos de expansión, justicia, abundancia, viajes espirituales'
    },
    'dalet': {
        'hebrew': 'ד',
        'name': 'Dalet',
        'gematria': 4,
        'category': 'double',
        'planet': 'Mars',
        'symbol': '♂',
        'day': 'Tuesday',
        'day_index': 1,
        'chaldean_order': 2,
        'duality': 'Fertility / Desolation',
        'duality_light': 'Fertility, productive action, courage',
        'duality_shadow': 'Desolation, aggression, exhaustion',
        'sensory_gate': 'Right ear',
        'meaning': 'Action, conflict, active energy',
        'keywords': ['action', 'conflict', 'energy', 'decision', 'surgery', 'competition'],
        'description': 'Planet of active energy and conflicts. Fertility or desolation depending on challenge resolution. Urgent decisions.',
        'interpretation_guidance': 'Mars is the planet of action. The duality fertility/desolation depends on conflict management.',
        'nature_of_inquiry': 'Conflictos, decisiones urgentes, cirugía, competencia'
    },
    'kaf': {
        'hebrew': 'כ',
        'name': 'Kaf',
        'gematria': 20,
        'category': 'double',
        'planet': 'Sun',
        'symbol': '☉',
        'day': 'Sunday',
        'day_index': 6,
        'chaldean_order': 3,
        'duality': 'Life / Death',
        'duality_light': 'Full life, vitality, identity',
        'duality_shadow': 'Symbolic death, exhaustion, identity loss',
        'sensory_gate': 'Left ear',
        'meaning': 'Identity, vitality, leadership',
        'keywords': ['identity', 'vitality', 'leadership', 'visibility', 'recognition', 'life'],
        'description': 'Planet of identity and full life. The self is exposed to the world. Life or death depending on soul vitality. Leadership.',
        'interpretation_guidance': 'The Sun rules identity. The duality life/death is symbolic: soul vitality vs exhaustion.',
        'nature_of_inquiry': 'Liderazgo, identidad, salud vital, reconocimiento'
    },
    'pe': {
        'hebrew': 'פ',
        'name': 'Pe',
        'gematria': 80,
        'category': 'double',
        'planet': 'Venus',
        'symbol': '♀',
        'day': 'Friday',
        'day_index': 4,
        'chaldean_order': 4,
        'duality': 'Dominion / Servitude',
        'duality_light': 'Constructive dominance, harmony, healthy relationships',
        'duality_shadow': 'Servitude, dependency, toxic relationships',
        'sensory_gate': 'Right nostril',
        'meaning': 'Relationships, art, harmony',
        'keywords': ['relationships', 'art', 'harmony', 'money', 'affection', 'power'],
        'description': 'Planet of relationships and art. Dominion or servitude depending on affective and power choices. Harmony or rupture.',
        'interpretation_guidance': 'Venus rules relationships. The duality dominion/servitude plays out in affective power dynamics.',
        'nature_of_inquiry': 'Relaciones, arte, dinero, armonía o ruptura'
    },
    'resh': {
        'hebrew': 'ר',
        'name': 'Resh',
        'gematria': 200,
        'category': 'double',
        'planet': 'Mercury',
        'symbol': '☿',
        'day': 'Wednesday',
        'day_index': 2,
        'chaldean_order': 5,
        'duality': 'Peace / War',
        'duality_light': 'Peace through communication, understanding',
        'duality_shadow': 'War through deception, verbal conflict',
        'sensory_gate': 'Left nostril',
        'meaning': 'Communication, contracts, movement',
        'keywords': ['communication', 'contracts', 'studies', 'messages', 'movement', 'exchange'],
        'description': 'Planet of communication and movement. Peace or war depending on honest or deceptive language use. Studies and messages.',
        'interpretation_guidance': 'Mercury rules communication. The duality peace/war depends on honest vs deceptive language use.',
        'nature_of_inquiry': 'Comunicación, contratos, estudios, mensajes'
    },
    'tav': {
        'hebrew': 'ת',
        'name': 'Tav',
        'gematria': 400,
        'category': 'double',
        'planet': 'Moon',
        'symbol': '☽',
        'day': 'Monday',
        'day_index': 0,
        'chaldean_order': 6,
        'duality': 'Grace / Ugliness',
        'duality_light': 'Grace, sensitivity, intuition',
        'duality_shadow': 'Emotional ugliness, instability, confusion',
        'sensory_gate': 'The mouth',
        'meaning': 'Cycles, emotions, the domestic',
        'keywords': ['cycles', 'emotions', 'domestic', 'changing', 'feminine', 'intuition'],
        'description': 'Planet of cycles and emotions. What flows and changes ceaselessly. Grace or ugliness depending on sensitivity. The domestic.',
        'interpretation_guidance': 'The Moon rules emotional cycles. The duality grace/ugliness depends on sensitivity and emotional management.',
        'nature_of_inquiry': 'Emociones, ciclos, lo doméstico, lo cambiante'
    },
    # 12 Simple Letters
    'he': {
        'hebrew': 'ה',
        'name': 'He',
        'gematria': 5,
        'category': 'simple',
        'sign': 'Aries',
        'symbol': '♈',
        'hebrew_month': 'Nisán',
        'civil_months': [3, 4],
        'faculty': 'Speech',
        'organ': 'Right foot',
        'direction': 'East',
        'meaning': 'Speech, expression, initiation',
        'keywords': ['speech', 'expression', 'initiation', 'communication', 'word', 'beginning'],
        'description': 'The faculty of speech as soul instrument. What is said or not said defines the course of situations. Initiation and beginnings.',
        'interpretation_guidance': 'Aries/Speech: The word is the soul instrument. What is said or not said defines the course.',
        'somatic_territory': 'Right foot - territory of movement and initiation'
    },
    'vav': {
        'hebrew': 'ו',
        'name': 'Vav',
        'gematria': 6,
        'category': 'simple',
        'sign': 'Taurus',
        'symbol': '♉',
        'hebrew_month': 'Iyar',
        'civil_months': [4, 5],
        'faculty': 'Thought',
        'organ': 'Left foot',
        'direction': 'Southeast',
        'meaning': 'Thought, reflection, rooting',
        'keywords': ['thought', 'reflection', 'rooting', 'consolidation', 'slowness', 'stability'],
        'description': 'Thought as primary action mode. Year of slow reflection and mental consolidation. Rooting and stability.',
        'interpretation_guidance': 'Taurus/Thought: Thought rules. Year of slow reflection, mental consolidation, rooting.',
        'somatic_territory': 'Left foot - territory of stability and rooting'
    },
    'zayin': {
        'hebrew': 'ז',
        'name': 'Zayin',
        'gematria': 7,
        'category': 'simple',
        'sign': 'Gemini',
        'symbol': '♊',
        'hebrew_month': 'Siván',
        'civil_months': [5, 6],
        'faculty': 'Movement',
        'organ': 'Right hand',
        'direction': 'Southwest',
        'meaning': 'Movement, change, duality',
        'keywords': ['movement', 'change', 'duality', 'displacement', 'versatility', 'adaptation'],
        'description': 'Movement dominates the soul. Year of displacements, changes, and active dualities. Versatility and adaptation.',
        'interpretation_guidance': 'Gemini/Movement: Movement dominates. Year of displacements, changes, active dualities.',
        'somatic_territory': 'Right hand - territory of action and change'
    },
    'jet': {
        'hebrew': 'ח',
        'name': 'Jet',
        'gematria': 8,
        'category': 'simple',
        'sign': 'Cancer',
        'symbol': '♋',
        'hebrew_month': 'Tamuz',
        'civil_months': [6, 7],
        'faculty': 'Vision',
        'organ': 'Left hand',
        'direction': 'North',
        'meaning': 'Vision, perception, illusion',
        'keywords': ['vision', 'perception', 'illusion', 'revelation', 'intuition', 'clarity'],
        'description': 'Vision as key faculty. Year of perception, visual revelations or illusions. Clarity or visual confusion.',
        'interpretation_guidance': 'Cancer/Vision: Vision is key. Year of perception, visual revelations or illusions.',
        'somatic_territory': 'Left hand - territory of perception and reception'
    },
    'tet': {
        'hebrew': 'ט',
        'name': 'Tet',
        'gematria': 9,
        'category': 'simple',
        'sign': 'Leo',
        'symbol': '♌',
        'hebrew_month': 'Av',
        'civil_months': [7, 8],
        'faculty': 'Hearing',
        'organ': 'Right kidney',
        'direction': 'Northeast',
        'meaning': 'Hearing, listening, leadership',
        'keywords': ['hearing', 'listening', 'leadership', 'visibility', 'revelation', 'authority'],
        'description': 'Hearing leads the soul. Listening (or not) is the axis of the year and situations. Visibility and leadership.',
        'interpretation_guidance': 'Leo/Hearing: Hearing leads. Listening (or not) is the axis of the year.',
        'somatic_territory': 'Right kidney - territory of authority and leadership'
    },
    'yod': {
        'hebrew': 'י',
        'name': 'Yod',
        'gematria': 10,
        'category': 'simple',
        'sign': 'Virgo',
        'symbol': '♍',
        'hebrew_month': 'Elul',
        'civil_months': [8, 9],
        'faculty': 'Action',
        'organ': 'Left kidney',
        'direction': 'West',
        'meaning': 'Action, work, detail',
        'keywords': ['action', 'work', 'detail', 'service', 'method', 'perfection'],
        'description': 'Concrete action defines the soul. Year of methodical work, service, and attention to detail. Perfection and method.',
        'interpretation_guidance': 'Virgo/Action: Concrete action defines. Year of methodical work, service, detail.',
        'somatic_territory': 'Left kidney - territory of service and detail'
    },
    'lamed': {
        'hebrew': 'ל',
        'name': 'Lamed',
        'gematria': 30,
        'category': 'simple',
        'sign': 'Libra',
        'symbol': '♎',
        'hebrew_month': 'Tishré',
        'civil_months': [9, 10],
        'faculty': 'Union / Coitus',
        'organ': 'Liver',
        'direction': 'East',
        'meaning': 'Union, relationships, alliances',
        'keywords': ['union', 'relationships', 'alliances', 'contracts', 'balance', 'partnership'],
        'description': 'Union is central to the soul. Relationships, alliances, and life contracts define the course. Balance and harmony.',
        'interpretation_guidance': 'Libra/Union: Union is central. Relationships, alliances, life contracts.',
        'somatic_territory': 'Liver - territory of processing and emotional balance'
    },
    'nun': {
        'hebrew': 'נ',
        'name': 'Nun',
        'gematria': 50,
        'category': 'simple',
        'sign': 'Scorpio',
        'symbol': '♏',
        'hebrew_month': 'Jeshván',
        'civil_months': [10, 11],
        'faculty': 'Smell',
        'organ': 'Spleen',
        'direction': 'North',
        'meaning': 'Smell, instinct, the hidden',
        'keywords': ['smell', 'instinct', 'hidden', 'depth', 'transformation', 'mystery'],
        'description': 'Smell-instinct guides the soul. Year of deep perception where the hidden comes to light. Transformation and mystery.',
        'interpretation_guidance': 'Scorpio/Smell: Smell-instinct guides. Year of deep perception, hidden comes to light.',
        'somatic_territory': 'Spleen - territory of instinct and transformation'
    },
    'samej': {
        'hebrew': 'ס',
        'name': 'Samej',
        'gematria': 60,
        'category': 'simple',
        'sign': 'Sagittarius',
        'symbol': '♐',
        'hebrew_month': 'Kislev',
        'civil_months': [11, 12],
        'faculty': 'Dream',
        'organ': 'Gallbladder',
        'direction': 'Southwest',
        'meaning': 'Dream, vision, direction',
        'keywords': ['dream', 'vision', 'direction', 'spirituality', 'travel', 'expansion'],
        'description': 'Dream orients the soul. Inner visions and sense of spiritual direction guide the year. Travels and expansion.',
        'interpretation_guidance': 'Sagittarius/Dream: Dream orients. Inner visions, sense of spiritual direction.',
        'somatic_territory': 'Gallbladder - territory of vision and spiritual direction'
    },
    'ayin': {
        'hebrew': 'ע',
        'name': 'Ayin',
        'gematria': 70,
        'category': 'simple',
        'sign': 'Capricorn',
        'symbol': '♑',
        'hebrew_month': 'Tevet',
        'civil_months': [12, 1],
        'faculty': 'Anger',
        'organ': 'Stomach',
        'direction': 'Northeast',
        'meaning': 'Anger, authority, trial',
        'keywords': ['anger', 'authority', 'trial', 'discipline', 'mastery', 'structure'],
        'description': 'Anger or its mastery is the soul theme. Year of emotional trial and authority development. Discipline and structure.',
        'interpretation_guidance': 'Capricorn/Anger: Anger or its mastery is the theme. Year of emotional trial and authority.',
        'somatic_territory': 'Stomach - territory of emotional digestion and authority'
    },
    'tzadi': {
        'hebrew': 'צ',
        'name': 'Tzadi',
        'gematria': 90,
        'category': 'simple',
        'sign': 'Aquarius',
        'symbol': '♒',
        'hebrew_month': 'Shvat',
        'civil_months': [1, 2],
        'faculty': 'Swallowing',
        'organ': 'Esophagus',
        'direction': 'West',
        'meaning': 'Swallowing, assimilation, acceptance',
        'keywords': ['swallowing', 'assimilation', 'acceptance', 'rejection', 'processing', 'integration'],
        'description': 'Swallowing/asimilation defines the soul. What is accepted or rejected from life marks the path. Integration of experiences.',
        'interpretation_guidance': 'Aquarius/Swallowing: Swallowing/asimilation defines. What is accepted or rejected from life.',
        'somatic_territory': 'Esophagus - territory of assimilation and experience processing'
    },
    'kof': {
        'hebrew': 'ק',
        'name': 'Kof',
        'gematria': 100,
        'category': 'simple',
        'sign': 'Pisces',
        'symbol': '♓',
        'hebrew_month': 'Adar',
        'civil_months': [2, 3],
        'faculty': 'Laughter',
        'organ': 'Intestine',
        'direction': 'Northwest',
        'meaning': 'Laughter, humor, dissolution',
        'keywords': ['laughter', 'humor', 'dissolution', 'detachment', 'grace', 'compassion'],
        'description': 'Laughter/cosmic humor guides the soul. Year of dissolution, detachment, and divine grace. Compassion and surrender.',
        'interpretation_guidance': 'Pisces/Laughter: Laughter/cosmic humor guides. Year of dissolution, detachment, grace.',
        'somatic_territory': 'Intestine - territory of final assimilation and detachment'
    }
}

# Number to letter mapping for personal year calculation
NUMBER_TO_LETTER = {
    1: 'alef', 2: 'bet', 3: 'gimel', 4: 'dalet', 5: 'he',
    6: 'vav', 7: 'zayin', 8: 'jet', 9: 'tet', 10: 'yod',
    11: 'kaf', 12: 'lamed', 13: 'mem', 14: 'nun', 15: 'samej',
    16: 'ayin', 17: 'pe', 18: 'tzadi', 19: 'kof', 20: 'resh',
    21: 'shin', 22: 'tav'
}

# ============================================================================
# LOADER FUNCTIONS
# ============================================================================

def _get_personality_dir(server_id: str = None) -> str:
    """Get the current personality directory."""
    try:
        from agent_runtime import get_personality_directory
        server_dir = get_personality_directory(server_id)
        if server_dir:
            return server_dir
    except:
        pass
    
    # Fallback to project root personalities directory
    try:
        from agent_engine import AGENT_CFG
        default_personality = AGENT_CFG.get("default_personality", "rab")
        default_language = AGENT_CFG.get("default_language", "en-US")
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        personality_rel = f"personalities/{default_personality}/{default_language}"
        return os.path.join(project_root, personality_rel)
    except:
        pass
    
    # Final fallback
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(project_root, "personalities", "putre")


def _load_shaman_json(server_id: str = None) -> dict:
    """Load personalities/{personality}/{language}/descriptions/shaman.json."""
    try:
        personality_dir = _get_personality_dir(server_id)
        shaman_path = os.path.join(personality_dir, "descriptions", "shaman.json")
        
        if os.path.exists(shaman_path):
            with open(shaman_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Could not load shaman.json: {e}")
    
    return {}


def _load_astrologyplane_json(server_id: str = None) -> dict:
    """Load manuals/{language}/astrologyplane.json with fallback to en-US."""
    try:
        from agent_engine import AGENT_CFG
        language = AGENT_CFG.get("default_language", "en-US")
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
        
        # Try personality-specific language first
        personality_dir = _get_personality_dir(server_id)
        personality_language = os.path.basename(personality_dir)
        astrologyplane_path = os.path.join(project_root, "manuals", personality_language, "astrologyplane.json")
        
        if os.path.exists(astrologyplane_path):
            with open(astrologyplane_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        # Fallback to en-US
        fallback_path = os.path.join(project_root, "manuals", "en-US", "astrologyplane.json")
        if os.path.exists(fallback_path):
            with open(fallback_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.debug(f"Could not load astrologyplane.json: {e}")
    
    return {}


# ============================================================================
# PERSONALITY MESSAGES CACHE
# ============================================================================

_personality_messages = None


def load_personality_messages(server_id: str = None) -> dict:
    """
    Load messages from shaman.json + astrologyplane.json with English fallbacks.
    
    Priority:
    1. personalities/{personality}/{language}/descriptions/shaman.json (UI messages)
    2. Fallback to ENGLISH_MESSAGES in code
    
    For letter data (positions, translations, guidance):
    1. manuals/{language}/astrologyplane.json
    2. Fallback to manuals/en-US/astrologyplane.json
    """
    global _personality_messages
    _personality_messages = None

    try:
        # Load UI messages from shaman.json
        shaman_data = _load_shaman_json(server_id)
        astrology_data = shaman_data.get('astrology', {})

        # Merge with English fallback
        merged_messages = ENGLISH_MESSAGES.copy()
        for key, value in astrology_data.items():
            if key not in ('translations', 'positions', 'guidance'):
                merged_messages[key] = value
        for key, value in astrology_data.get('labels', {}).items():
            merged_messages[key] = value

        # Load letter data from astrologyplane.json
        astrologyplane_data = _load_astrologyplane_json(server_id)
        merged_messages['translations'] = astrologyplane_data.get('translations', {})
        merged_messages['positions'] = astrologyplane_data.get('positions', {})
        merged_messages['guidance'] = astrologyplane_data.get('guidance', {})

        _personality_messages = merged_messages
        return _personality_messages

    except Exception as e:
        logger.error(f'Failed to load personality messages: {e}')
        _personality_messages = ENGLISH_MESSAGES.copy()
        return _personality_messages


def get_message(message_key: str, server_id: str = None, **kwargs) -> str:
    """Get message by key with personality support."""
    messages = load_personality_messages(server_id)
    result = messages.get(message_key, ENGLISH_MESSAGES.get(message_key, f"Unknown message: {message_key}"))
    
    if kwargs:
        return result.format(**kwargs)
    return result


def get_guidance_messages(category: str, server_id: str = None) -> dict:
    """Get guidance messages for a category from astrologyplane.json."""
    messages = load_personality_messages(server_id)
    guidance_data = messages.get('guidance', {})
    if isinstance(guidance_data, str) or not guidance_data:
        guidance_data = _load_astrologyplane_json(server_id).get('guidance', {})
    return guidance_data.get(category, {})


def get_letter_translations(letter_key: str, server_id: str = None) -> dict:
    """Get letter translations from astrologyplane.json."""
    messages = load_personality_messages(server_id)
    translations = messages.get('translations', {})
    # Normalize to lowercase for case-insensitive lookup
    return translations.get(letter_key.lower(), {})


def get_position_translation(position_key: str, server_id: str = None) -> str:
    """Get position translation from astrologyplane.json."""
    messages = load_personality_messages(server_id)
    positions = messages.get('positions', {})
    return positions.get(position_key, position_key)


def get_all_position_translations(server_id: str = None) -> dict:
    """Get all position translations as a dict from astrologyplane.json."""
    messages = load_personality_messages(server_id)
    return messages.get('positions', {})


def clear_message_cache():
    """Clear the personality messages cache to force reload."""
    global _personality_messages
    _personality_messages = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_letter(letter_key: str) -> dict:
    """Get letter data by key (English fallback)."""
    return HEBREW_LETTERS.get(letter_key, {})


def get_reading_type(type_key: str) -> dict:
    """Get reading type configuration by key."""
    return READING_TYPES.get(type_key, {})


def get_mother_letters() -> dict:
    """Get the 3 Mother letters."""
    return {k: v for k, v in HEBREW_LETTERS.items() if v['category'] == 'mother'}


def get_double_letters() -> dict:
    """Get the 7 Double letters."""
    return {k: v for k, v in HEBREW_LETTERS.items() if v['category'] == 'double'}


def get_simple_letters() -> dict:
    """Get the 12 Simple letters."""
    return {k: v for k, v in HEBREW_LETTERS.items() if v['category'] == 'simple'}


def get_letter_by_element(element: str) -> dict:
    """Get letter by element (for Mother letters)."""
    return next((v for k, v in HEBREW_LETTERS.items() if v.get('element') == element), {})


def get_letter_by_planet(planet: str) -> dict:
    """Get letter by planet (for Double letters)."""
    return next((v for k, v in HEBREW_LETTERS.items() if v.get('planet') == planet), {})


def get_letter_by_sign(sign: str) -> dict:
    """Get letter by zodiac sign (for Simple letters)."""
    return next((v for k, v in HEBREW_LETTERS.items() if v.get('sign') == sign), {})


def number_to_hebrew_letter(number: int) -> dict:
    """Map a number (1-22) to its corresponding Hebrew letter."""
    key = NUMBER_TO_LETTER.get(number, 'alef')
    return HEBREW_LETTERS.get(key, {})


def get_planet_by_day_index(day_index: int) -> dict:
    """Get planet by day index (0=Monday, 6=Sunday)."""
    for letter in get_double_letters().values():
        if letter.get('day_index') == day_index:
            return letter
    return {}


def get_planet_by_chaldean_hour(hour: int) -> dict:
    """Get planet by hour using Chaldean order."""
    chaldean_order = ['Saturn', 'Jupiter', 'Mars', 'Sun', 'Venus', 'Mercury', 'Moon']
    planet_index = hour % 7
    planet_name = chaldean_order[planet_index]
    return get_letter_by_planet(planet_name)


# ============================================================================
# HEBREW LETTERS PAGINATION (similar to RUNES pagination)
# ============================================================================

_HEBREW_LETTER_ORDER = [
    # Mother Letters (3)
    ('alef', 'א', 'Alef'),
    ('mem', 'מ', 'Mem'),
    ('shin', 'ש', 'Shin'),
    # Double Letters (7)
    ('bet', 'ב', 'Bet'),
    ('gimel', 'ג', 'Gimel'),
    ('dalet', 'ד', 'Dalet'),
    ('kaf', 'כ', 'Kaf'),
    ('pe', 'פ', 'Pe'),
    ('resh', 'ר', 'Resh'),
    ('tav', 'ת', 'Tav'),
    # Simple Letters (12)
    ('he', 'ה', 'He'),
    ('vav', 'ו', 'Vav'),
    ('zayin', 'ז', 'Zayin'),
    ('jet', 'ח', 'Jet'),
    ('tet', 'ט', 'Tet'),
    ('yod', 'י', 'Yod'),
    ('lamed', 'ל', 'Lamed'),
    ('nun', 'נ', 'Nun'),
    ('samej', 'ס', 'Samej'),
    ('ayin', 'ע', 'Ayin'),
    ('tzadi', 'צ', 'Tzadi'),
    ('kof', 'ק', 'Kof'),
]

HEBREW_LETTERS_PER_PAGE = 8


def get_hebrew_letters_page_data(page: int = 1, server_id: str = None) -> list:
    """Return structured Hebrew letter data for the given page as a list of dicts."""
    messages = load_personality_messages(server_id)
    labels_data = _load_shaman_json(server_id).get('astrology', {}).get('labels', {})
    astrologyplane = _load_astrologyplane_json(server_id)
    letters_data = astrologyplane.get('translations', {})

    logger.debug(f"get_hebrew_letters_page_data: page={page}, server_id={server_id}, letters_data keys={list(letters_data.keys())[:5]}")

    start_idx = (page - 1) * HEBREW_LETTERS_PER_PAGE
    page_letters = _HEBREW_LETTER_ORDER[start_idx:start_idx + HEBREW_LETTERS_PER_PAGE]

    logger.debug(f"get_hebrew_letters_page_data: page_letters={page_letters}")

    result = []
    for letter_key, hebrew_symbol, name in page_letters:
        letter_info = letters_data.get(letter_key, {})
        fallback_letter = HEBREW_LETTERS.get(letter_key, {})
        result.append({
            'key': letter_key,
            'symbol': hebrew_symbol,
            'name': name,
            'meaning': letter_info.get('meaning', fallback_letter.get('meaning', 'Unknown')),
            'keywords': letter_info.get('keywords', fallback_letter.get('keywords', [])),
            'interpretation': letter_info.get('interpretation', fallback_letter.get('description', 'No description')),
            'labels': labels_data,
        })

    logger.debug(f"get_hebrew_letters_page_data: result_count={len(result)}")

    return result


def get_hebrew_letters_list_content(page: int = 1, server_id: str = None) -> str:
    """Generate Hebrew letters list content dynamically from astrologyplane.json with pagination.

    Format per letter:
        **hebrew_symbol name**: meaning
        keyword_label: kw1, kw2, …
    """
    shaman_data = _load_shaman_json(server_id)
    labels_data = shaman_data.get('astrology', {}).get('labels', {})

    astrologyplane = _load_astrologyplane_json(server_id)
    letters_data = astrologyplane.get('translations', {})

    logger.debug(f"get_hebrew_letters_list_content: page={page}, server_id={server_id}, letters_data keys={list(letters_data.keys())[:5]}")

    start_idx = (page - 1) * HEBREW_LETTERS_PER_PAGE
    page_letters = _HEBREW_LETTER_ORDER[start_idx:start_idx + HEBREW_LETTERS_PER_PAGE]

    logger.debug(f"get_hebrew_letters_list_content: page_letters={page_letters}")

    content = "─" * 45 + "\n\n"

    for letter_key, hebrew_symbol, name in page_letters:
        letter_info = letters_data.get(letter_key, {})
        fallback_letter = HEBREW_LETTERS.get(letter_key, {})
        meaning = letter_info.get('meaning', fallback_letter.get('meaning', 'Unknown'))
        # Add LTR mark to force left-to-right direction for mixed Hebrew/English text
        content += f"\u200E**{hebrew_symbol} {name}**: \u200E\n"
        content += f"\u200E{meaning}\u200E\n"

    logger.debug(f"get_hebrew_letters_list_content: content_length={len(content)}, content_preview={content[:200]}")

    return content
