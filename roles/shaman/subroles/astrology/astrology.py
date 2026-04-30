"""
Astrology Core Logic Module
Handles Sefer Yetzirah calculations and interpretations with personality support.
"""

from datetime import datetime, time
from typing import Dict, Any, Optional
import logging

from .astrology_messages import (
    HEBREW_LETTERS, get_letter, get_letter_by_element, get_letter_by_planet,
    get_letter_by_sign, number_to_hebrew_letter, get_planet_by_day_index,
    get_planet_by_chaldean_hour, READING_TYPES, get_message, load_personality_messages,
    get_letter_translations, get_position_translation
)

logger = logging.getLogger(__name__)

# Check AI availability
AI_AVAILABLE = False
try:
    from agent_mind import call_llm
    AI_AVAILABLE = True
except ImportError:
    logger.warning("AI not available, will use fallback interpretations")


class Astrology:
    """Core Sefer Yetzirah astrology logic."""
    
    def __init__(self):
        """Initialize the astrology calculator."""
        pass
    
    def get_reading(self, reading_type: str, input_data: Dict[str, Any],
                   question: str = None, server_id: str = None) -> Dict[str, Any]:
        """
        Main entry point for getting a reading.

        Args:
            reading_type: Type of reading ('birth', 'moment', 'year', 'integrated')
            input_data: Dictionary with required inputs for the reading type
            question: Question for contextual interpretation (required for moment/integrated, rejected for birth/year)
            server_id: Server ID for personality-specific messages

        Returns:
            Dictionary with calculation data and interpretation
        """
        type_info = get_reading_type(reading_type)
        if not type_info:
            raise ValueError(f"Invalid reading type: {reading_type}")

        # Validate question requirement according to reading type
        question_required = type_info.get('question_required', False)
        if question_required:
            if not question:
                raise ValueError(f"Question is required for {reading_type} reading")
        else:
            if question:
                raise ValueError(f"Question is not applicable for {reading_type} reading (out of place)")

        # Validate required inputs
        for required_input in type_info['input_required']:
            if required_input not in input_data:
                raise ValueError(f"Missing required input: {required_input}")

        # Calculate based on reading type
        calc_function = getattr(self, type_info['calculation_function'])
        calculation_data = calc_function(**input_data)

        # Get interpretation (with AI if available)
        interpretation = self.interpret_with_ai(
            reading_type, calculation_data, question, server_id
        )

        return {
            'reading_type': reading_type,
            'calculation_data': calculation_data,
            'interpretation': interpretation,
            'question': question if question_required else None
        }
    
    def calculate_birth_chart(self, birth_date: datetime, 
                             birth_time: Optional[time] = None) -> Dict[str, Any]:
        """
        Calculate the three-layer birth chart from birth date and time.
        
        Step 1: Identify the Soul Element (Mother Letter)
        Step 2: Identify the Ruling Planet (Double Letter)
        Step 3: Identify the Zodiac Sign (Simple Letter)
        """
        logger.info(f"Calculating birth chart for date: {birth_date}, time: {birth_time}")
        
        # Step 1: Soul Element (season)
        month = birth_date.month
        if month in [3, 4, 9, 10]:  # Spring or Autumn
            element_letter = get_letter_by_element('Air')
            season = 'Temperate'
        elif month in [6, 7, 8]:  # Summer
            element_letter = get_letter_by_element('Fire')
            season = 'Summer'
        else:  # Winter
            element_letter = get_letter_by_element('Water')
            season = 'Winter'
        
        # Step 2: Ruling Planet (day of week)
        weekday = birth_date.weekday()
        planet_letter = get_planet_by_day_index(weekday)
        
        # If time is available, calculate planet of the hour
        if birth_time:
            planet_letter = get_planet_by_chaldean_hour(birth_time.hour)
            logger.info(f"Using hour-based planet: {planet_letter.get('name')}")
        
        # Step 3: Zodiac Sign (date)
        sign_letter = self._calculate_sign_by_date(birth_date)
        
        return {
            'element': {
                'letter': element_letter,
                'season': season,
                'interpretation': f"Soul of {element_letter['element']}: {element_letter['description']}"
            },
            'planet': {
                'letter': planet_letter,
                'day': birth_date.strftime('%A'),
                'interpretation': f"Ruling Planet {planet_letter['planet']}: {planet_letter['description']}"
            },
            'sign': {
                'letter': sign_letter,
                'interpretation': f"Sign {sign_letter['sign']}: {sign_letter['description']}"
            },
            'synthesis': self._synthesize_birth_chart(element_letter, planet_letter, sign_letter)
        }
    
    def calculate_moment_reading(self, question_date: datetime,
                                 question_time: Optional[time] = None) -> Dict[str, Any]:
        """
        Calculate the three-layer moment reading for a specific question.
        
        Step 1: Read the elemental environment
        Step 2: Identify the planet of the day
        Step 3: Analyze the sign of the month
        Step 4: Identify tension between levels
        """
        logger.info(f"Calculating moment reading for date: {question_date}, time: {question_time}")
        
        # Step 1: Elemental environment
        month = question_date.month
        if month in [3, 4, 9, 10]:
            element_letter = get_letter_by_element('Air')
            season_tone = "unstable equilibrium, can tilt in any direction"
        elif month in [6, 7, 8]:
            element_letter = get_letter_by_element('Fire')
            season_tone = "urgency, mental action, clarity that can burn"
        else:
            element_letter = get_letter_by_element('Water')
            season_tone = "patience, introversion, descent into the depths"
        
        # Step 2: Planet of the day
        weekday = question_date.weekday()
        planet_letter = get_planet_by_day_index(weekday)
        
        # Step 3: Sign of the month
        sign_letter = self._calculate_sign_by_date(question_date)
        
        # Step 4: Tension analysis
        tension_analysis = self._analyze_tension(element_letter, planet_letter, sign_letter)
        
        return {
            'element': {
                'letter': element_letter,
                'tone': season_tone,
                'interpretation': f"Element {element_letter['element']}: {season_tone}"
            },
            'planet': {
                'letter': planet_letter,
                'nature': self._get_planet_nature(planet_letter['planet']),
                'interpretation': f"Ruling Force {planet_letter['planet']}: {planet_letter['description']}"
            },
            'sign': {
                'letter': sign_letter,
                'faculty': sign_letter['faculty'],
                'interpretation': f"Active Faculty {sign_letter['faculty']}: {sign_letter['description']}"
            },
            'synthesis': {
                'tension': tension_analysis['is_tension'],
                'interpretation': tension_analysis['interpretation']
            }
        }
    
    def calculate_personal_year(self, birth_year: int, current_year: int) -> Dict[str, Any]:
        """
        Calculate the personal year number and letter.
        
        Step 1: Calculate birth year number
        Step 2: Calculate current year number
        Step 3: Calculate personal number (1-22)
        Step 4: Map to Hebrew letter
        """
        logger.info(f"Calculating personal year: birth={birth_year}, current={current_year}")
        
        # Step 1: Birth year
        birth_sum = self._reduce_to_single_digit(birth_year)
        
        # Step 2: Current year
        current_sum = self._reduce_to_single_digit(current_year)
        
        # Step 3: Personal number
        personal_number = birth_sum + current_sum
        while personal_number > 22:
            personal_number = self._reduce_to_single_digit(personal_number)
        
        # Step 4: Letters
        personal_letter = number_to_hebrew_letter(personal_number)
        collective_letter = number_to_hebrew_letter(current_sum)
        
        return {
            'personal_number': personal_number,
            'personal_letter': personal_letter,
            'collective_year': current_sum,
            'collective_letter': collective_letter,
            'interpretation': self._get_year_interpretation(personal_letter, collective_letter)
        }
    
    def calculate_integrated_reading(self, birth_date: datetime, question_date: datetime,
                                     birth_time: Optional[time] = None,
                                     question_time: Optional[time] = None) -> Dict[str, Any]:
        """
        Calculate integrated reading combining birth chart, personal year, and moment.
        
        LAYER 1 (permanent) — Birth Chart
        LAYER 2 (cyclical) — Personal Year
        LAYER 3 (immediate) — Moment of Consultation
        """
        logger.info("Calculating integrated reading")
        
        # LAYER 1
        birth_chart = self.calculate_birth_chart(birth_date, birth_time)
        
        # LAYER 2
        current_year = question_date.year
        birth_year = birth_date.year
        personal_year = self.calculate_personal_year(birth_year, current_year)
        
        # LAYER 3
        moment_reading = self.calculate_moment_reading(question_date, question_time)
        
        # SYNTHESIS
        synthesis = self._analyze_integrated_synthesis(birth_chart, personal_year, moment_reading)
        
        return {
            'layer_1_permanent': {
                'name': 'Birth Chart (Permanent)',
                'data': birth_chart
            },
            'layer_2_cyclical': {
                'name': 'Personal Year (Cyclical)',
                'data': personal_year
            },
            'layer_3_immediate': {
                'name': 'Moment of Consultation (Immediate)',
                'data': moment_reading
            },
            'synthesis': synthesis
        }
    
    # Private helper methods
    
    def _calculate_sign_by_date(self, date: datetime) -> Dict[str, Any]:
        """Calculate zodiac sign from date."""
        day = date.day
        month = date.month
        
        if (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return get_letter_by_sign('Aries')
        elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return get_letter_by_sign('Taurus')
        elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
            return get_letter_by_sign('Gemini')
        elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
            return get_letter_by_sign('Cancer')
        elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return get_letter_by_sign('Leo')
        elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return get_letter_by_sign('Virgo')
        elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
            return get_letter_by_sign('Libra')
        elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
            return get_letter_by_sign('Scorpio')
        elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
            return get_letter_by_sign('Sagittarius')
        elif (month == 12 and day >= 22) or (month == 1 and day <= 19):
            return get_letter_by_sign('Capricorn')
        elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return get_letter_by_sign('Aquarius')
        else:
            return get_letter_by_sign('Pisces')
    
    def _reduce_to_single_digit(self, number: int) -> int:
        """Reduce a number to a single digit by summing its digits."""
        while number > 9:
            number = sum(int(d) for d in str(number))
        return number
    
    def _synthesize_birth_chart(self, element_letter, planet_letter, sign_letter) -> str:
        """Synthesize birth chart interpretation."""
        return f"""
        **Birth Chart Synthesis:**
        
        Element: {element_letter['name']} ({element_letter['element']})
        - {element_letter['description']}
        
        Planet: {planet_letter['name']} ({planet_letter['planet']})
        - {planet_letter['description']}
        
        Sign: {sign_letter['name']} ({sign_letter['sign']})
        - {sign_letter['description']}
        
        **Questions for reflection:**
        - Do the element and sign reinforce or tension each other?
        - Does the planet operate in its luminous or shadow face?
        - Where is the tikun (spiritual correction)?
        """
    
    def _get_planet_nature(self, planet: str) -> str:
        """Get the nature of inquiry for each planet."""
        natures = {
            'Saturn': 'Matters of limits, time, inheritance, karma, restrictions',
            'Jupiter': 'Matters of expansion, justice, abundance, spiritual journeys',
            'Mars': 'Conflicts, urgent decisions, surgery, competition',
            'Sun': 'Leadership, identity, vital health, recognition',
            'Venus': 'Relationships, art, money, harmony or rupture',
            'Mercury': 'Communication, contracts, studies, messages',
            'Moon': 'Emotions, cycles, domestic matters, change'
        }
        return natures.get(planet, 'General planetary influence')
    
    def _analyze_tension(self, element_letter, planet_letter, sign_letter) -> Dict[str, Any]:
        """
        Analyze if levels are aligned or in tension according to Sefer Yetzirah.
        
        According to the guide, tension analysis considers:
        - Element and sign reinforcement or creative tension
        - Planet operating in luminous or shadow face
        - Faculty active or blocked
        """
        element = element_letter.get('element', '')
        planet = planet_letter.get('planet', '')
        sign = sign_letter.get('sign', '')
        
        # Classic elemental alignments (sign shares element with planet)
        aligned_combinations = [
            ('Fire', 'Sun', 'Leo'),
            ('Fire', 'Mars', 'Aries'),
            ('Fire', 'Mars', 'Leo'),
            ('Water', 'Moon', 'Cancer'),
            ('Water', 'Venus', 'Pisces'),
            ('Water', 'Jupiter', 'Pisces'),
            ('Air', 'Mercury', 'Gemini'),
            ('Air', 'Mercury', 'Libra'),
            ('Air', 'Venus', 'Libra'),
        ]
        
        # Elemental tensions (sign element opposite to planet)
        tension_combinations = [
            ('Fire', 'Moon', 'Cancer'),      # Fuego vs Agua
            ('Fire', 'Venus', 'Pisces'),     # Fuego vs Agua
            ('Water', 'Sun', 'Leo'),         # Agua vs Fuego
            ('Water', 'Mars', 'Aries'),      # Agua vs Fuego
            ('Air', 'Moon', 'Cancer'),       # Aire vs Agua
            ('Air', 'Venus', 'Pisces'),     # Aire vs Agua
        ]
        
        current_combo = (element, planet, sign)
        
        # Analysis of alignment between element and sign
        element_sign_alignment = self._check_element_sign_alignment(element, sign)
        
        # Analysis of planet-sign affinity
        planet_sign_affinity = self._check_planet_sign_affinity(planet, sign)
        
        # Determine general tension
        if current_combo in aligned_combinations:
            tension_level = 'none'
            interpretation = 'Forces are aligned. The situation has clear inertia and forces point in the same direction.'
        elif current_combo in tension_combinations:
            tension_level = 'high'
            interpretation = 'Strong contradiction between levels. Real point of choice where free will is operative.'
        elif not element_sign_alignment:
            tension_level = 'medium'
            interpretation = 'Creative tension between element and sign. The soul works with raw material requiring conscious integration.'
        elif not planet_sign_affinity:
            tension_level = 'low'
            interpretation = 'Slight misalignment between planet and sign. The planet can operate in its luminous or shadow face depending on circumstances.'
        else:
            tension_level = 'low'
            interpretation = 'Relatively stable configuration with minor tension nuances.'
        
        return {
            'is_tension': tension_level != 'none',
            'tension_level': tension_level,
            'element_sign_alignment': element_sign_alignment,
            'planet_sign_affinity': planet_sign_affinity,
            'interpretation': interpretation
        }
    
    def _check_element_sign_alignment(self, element: str, sign: str) -> bool:
        """Check if zodiac sign aligns with its traditional element."""
        element_signs = {
            'Fire': ['Aries', 'Leo', 'Sagittarius'],
            'Water': ['Cancer', 'Scorpio', 'Pisces'],
            'Air': ['Gemini', 'Libra', 'Aquarius'],
            'Earth': ['Taurus', 'Virgo', 'Capricorn']
        }
        return sign in element_signs.get(element, [])
    
    def _check_planet_sign_affinity(self, planet: str, sign: str) -> bool:
        """Check if planet has affinity with sign (traditional rulership or exaltation)."""
        planet_affinities = {
            'Sun': ['Leo'],
            'Moon': ['Cancer'],
            'Mercury': ['Gemini', 'Virgo'],
            'Venus': ['Taurus', 'Libra'],
            'Mars': ['Aries', 'Scorpio'],
            'Jupiter': ['Sagittarius', 'Pisces'],
            'Saturn': ['Capricorn', 'Aquarius']
        }
        return sign in planet_affinities.get(planet, [])
    
    def _get_year_interpretation(self, personal_letter, collective_letter) -> str:
        """Get interpretation for personal year within collective context."""
        return f"""
        **Personal Year:** {personal_letter['name']} - {personal_letter['description']}
        
        **Collective Climate:** {collective_letter['name']} - {collective_letter['description']}
        
        Your personal year operates within the collective climate.
        """
    
    def _analyze_integrated_synthesis(self, birth_chart, personal_year, moment_reading) -> Dict[str, Any]:
        """
        Analyze alignment between three layers according to the 5 questions of the interpreter.
        
        According to the guide, the interpreter must answer:
        1. What is the dominant element? (Mother) — Fire, Water, or Air? Is there elemental imbalance?
        2. What is the ruling planet? (Double) — In which face of its duality does it operate: luminous or shadow?
        3. What is the active faculty? (Simple) — What capacity of the soul is being called or blocked?
        4. Is there alignment or tension between the three levels? — Do forces reinforce or contradict?
        5. What is the indicated tikun? — What spiritual correction does the configuration indicate?
        """
        # LAYER 1 - Birth Chart
        birth_element = birth_chart['element']['letter']['element']
        birth_planet = birth_chart['planet']['letter']['planet']
        birth_faculty = birth_chart['sign']['letter']['faculty']
        birth_sign = birth_chart['sign']['letter']['sign']
        
        # LAYER 2 - Personal Year
        personal_letter = personal_year['personal_letter']['name']
        personal_number = personal_year['personal_number']
        collective_letter = personal_year['collective_letter']['name']
        
        # LAYER 3 - Moment
        moment_element = moment_reading['element']['letter']['element']
        moment_planet = moment_reading['planet']['letter']['planet']
        moment_faculty = moment_reading['sign']['letter']['faculty']
        moment_tension = moment_reading['synthesis']
        
        # QUESTION 1: Dominant element
        element_counts = {birth_element: 0, moment_element: 0}
        element_counts[birth_element] += 1
        element_counts[moment_element] += 1
        dominant_element = max(element_counts, key=element_counts.get)
        element_imbalance = birth_element != moment_element
        
        question_1 = {
            'question': 'What is the dominant element?',
            'dominant_element': dominant_element,
            'birth_element': birth_element,
            'moment_element': moment_element,
            'imbalance': element_imbalance,
            'interpretation': self._get_element_dominance_interpretation(dominant_element, element_imbalance)
        }
        
        # QUESTION 2: Ruling planet and its duality
        question_2 = {
            'question': 'What is the ruling planet?',
            'birth_planet': birth_planet,
            'moment_planet': moment_planet,
            'planet_affinity': birth_planet == moment_planet,
            'duality': self._get_planet_duality(birth_planet),
            'interpretation': self._get_planet_ruler_interpretation(birth_planet, moment_planet)
        }
        
        # QUESTION 3: Active faculty
        question_3 = {
            'question': 'What is the active faculty?',
            'birth_faculty': birth_faculty,
            'moment_faculty': moment_faculty,
            'personal_year_faculty': personal_letter,
            'faculty_consistency': birth_faculty == moment_faculty,
            'interpretation': self._get_active_faculty_interpretation(birth_faculty, moment_faculty, personal_letter)
        }
        
        # QUESTION 4: Alignment or tension between levels
        birth_tension = self._analyze_tension(
            birth_chart['element']['letter'],
            birth_chart['planet']['letter'],
            birth_chart['sign']['letter']
        )
        
        question_4 = {
            'question': 'Is there alignment or tension between the three levels?',
            'birth_tension_level': birth_tension['tension_level'],
            'moment_tension_level': moment_tension['tension_level'],
            'cross_layer_alignment': self._check_cross_layer_alignment(birth_chart, moment_reading),
            'interpretation': self._get_alignment_interpretation(birth_tension, moment_tension)
        }
        
        # QUESTION 5: Indicated tikun
        question_5 = {
            'question': 'What is the indicated tikun?',
            'tikun_area': self._identify_tikun_area(birth_chart, personal_year, moment_reading),
            'organ_territory': birth_chart['sign']['letter'].get('organ', ''),
            'somatic_focus': birth_chart['element']['letter'].get('body_part', ''),
            'interpretation': self._get_tikun_interpretation(birth_chart, personal_year, moment_reading)
        }
        
        return {
            'question_1_element': question_1,
            'question_2_planet': question_2,
            'question_3_faculty': question_3,
            'question_4_alignment': question_4,
            'question_5_tikun': question_5,
            'summary': self._generate_synthesis_summary(question_1, question_2, question_3, question_4, question_5)
        }
    
    def _get_element_dominance_interpretation(self, dominant_element: str, imbalance: bool) -> str:
        """Interpret element dominance and imbalance."""
        interpretations = {
            'Fire': 'Fire dominates: mental expansion, clarity, upward orientation. The soul works primarily in the head and mind.',
            'Water': 'Water dominates: emotional depth, receptivity, inward orientation. The soul works primarily in the belly and emotions.',
            'Air': 'Air dominates: mediation, balance, broad intellect. The soul works primarily in the chest and breath.'
        }
        base = interpretations.get(dominant_element, 'Dominant element not identified.')
        if imbalance:
            base += ' There is elemental imbalance between the birth chart and the moment, indicating a period of adjustment and rebalancing.'
        return base
    
    def _get_planet_duality(self, planet: str) -> Dict[str, str]:
        """Get the duality (light/shadow) of a planet."""
        from .astrology_messages import get_letter_by_planet
        planet_letter = get_letter_by_planet(planet)
        return {
            'duality': planet_letter.get('duality', ''),
            'light': planet_letter.get('duality_light', ''),
            'shadow': planet_letter.get('duality_shadow', '')
        }
    
    def _get_planet_ruler_interpretation(self, birth_planet: str, moment_planet: str) -> str:
        """Interpret planet ruler across layers."""
        if birth_planet == moment_planet:
            return f"The ruling planet {birth_planet} remains constant between birth and moment. Its duality is consistently active."
        else:
            return f"The natal planet {birth_planet} meets the moment planet {moment_planet}. This indicates an interaction between two different planetary forces."
    
    def _get_active_faculty_interpretation(self, birth_faculty: str, moment_faculty: str, personal_letter: str) -> str:
        """Interpret active faculty across layers."""
        consistency = birth_faculty == moment_faculty
        if consistency:
            return f"The faculty {birth_faculty} is active both in the birth chart and the moment, reinforced by the personal year {personal_letter}."
        else:
            return f"The natal faculty {birth_faculty} meets the moment faculty {moment_faculty}. The personal year {personal_letter} adds another layer of work with this faculty."
    
    def _check_cross_layer_alignment(self, birth_chart, moment_reading) -> Dict[str, bool]:
        """Check alignment across the three layers."""
        return {
            'element_aligned': birth_chart['element']['letter']['element'] == moment_reading['element']['letter']['element'],
            'planet_aligned': birth_chart['planet']['letter']['planet'] == moment_reading['planet']['letter']['planet'],
            'sign_aligned': birth_chart['sign']['letter']['sign'] == moment_reading['sign']['letter']['sign']
        }
    
    def _get_alignment_interpretation(self, birth_tension: Dict, moment_tension: Dict) -> str:
        """Interpret overall alignment between layers."""
        if birth_tension['tension_level'] == 'none' and moment_tension['tension_level'] == 'none':
            return 'Forces are aligned in all layers. The situation has clear inertia and the path is delineated.'
        elif birth_tension['tension_level'] == 'high' or moment_tension['tension_level'] == 'high':
            return 'There is strong tension in at least one layer. This signals a real point of choice where free will is operative.'
        else:
            return 'There are creative tensions and nuances of misalignment. The soul works with raw material requiring conscious integration.'
    
    def _identify_tikun_area(self, birth_chart, personal_year, moment_reading) -> str:
        """Identify the main area of spiritual correction (tikun)."""
        # The tikun is usually found in the planetary duality that resists most
        birth_planet = birth_chart['planet']['letter']['planet']
        birth_element = birth_chart['element']['letter']['element']
        birth_faculty = birth_chart['sign']['letter']['faculty']
        
        # If there is high tension in birth chart, tikun is in that duality
        birth_tension = self._analyze_tension(
            birth_chart['element']['letter'],
            birth_chart['planet']['letter'],
            birth_chart['sign']['letter']
        )
        
        if birth_tension['tension_level'] == 'high':
            return f"The main correction (tikun) plays out in the duality of planet {birth_planet} and its interaction with element {birth_element}."
        else:
            return f"The tikun is worked primarily through the faculty {birth_faculty} and the corresponding somatic territory."
    
    def _get_tikun_interpretation(self, birth_chart, personal_year, moment_reading) -> str:
        """Get comprehensive tikun interpretation."""
        organ = birth_chart['sign']['letter'].get('organ', '')
        somatic = birth_chart['element']['letter'].get('body_part', '')
        tikun_area = self._identify_tikun_area(birth_chart, personal_year, moment_reading)
        
        return f"{tikun_area} The somatic territory of resonance is {somatic}, with potential vulnerability in {organ}. This area indicates where unresolved spiritual tension accumulates."
    
    def _generate_synthesis_summary(self, q1, q2, q3, q4, q5) -> str:
        """Generate a summary of the integrated analysis."""
        return f"""
**INTEGRATED SYNTHESIS**

**Dominant Element:** {q1['dominant_element']}
{q1['interpretation']}

**Ruling Planet:** {q2['birth_planet']}
{q2['interpretation']}

**Active Faculty:** {q3['birth_faculty']}
{q3['interpretation']}

**Alignment:** {q4['interpretation']}

**Tikun:** {q5['interpretation']}
"""
    
    def interpret_with_ai(self, reading_type: str, calculation_data: Dict[str, Any],
                        question: str = None, server_id: str = None) -> str:
        """
        Interpret calculation using AI for precise contextual analysis.
        Similar to nordic_runes.interpret_runes_with_ai()
        """
        logger.info(f"Astrology interpret_with_ai called with reading_type={reading_type}")

        if not AI_AVAILABLE:
            logger.warning("AI not available, using fallback for astrology")
            return self._fallback_interpretation(reading_type, calculation_data, question)

        try:
            # Check if this reading type requires a question
            type_info = get_reading_type(reading_type)
            question_required = type_info.get('question_required', False)

            # Step 1: Prepare letter data with translations
            letter_data_text = self._format_letter_data(calculation_data, server_id)

            # Step 2: Get guidance data
            guidance_data_text = self._format_guidance_data(server_id)

            # Step 3: Get the appropriate interpretation prompt from prompts.json
            interpretation_prompt = self._load_interpretation_prompt(reading_type, server_id)

            # Step 4: Format the prompt - only include question if required
            if question_required:
                formatted_prompt = interpretation_prompt.format(
                    question=question,
                    letter_data=letter_data_text,
                    guidance_data=guidance_data_text
                )
            else:
                # For types without question, remove {question} placeholder if present
                formatted_prompt = interpretation_prompt.format(
                    letter_data=letter_data_text,
                    guidance_data=guidance_data_text
                )
                # Also remove any stray "question:" references in the prompt
                formatted_prompt = formatted_prompt.replace("{question}", "")
                formatted_prompt = formatted_prompt.replace("question:", "")

            # Step 5: Build system instruction
            from agent_engine import _build_system_prompt, _get_personality
            server_personality = _get_personality(server_id) if server_id else None
            system_instruction = _build_system_prompt(server_personality, server_id)

            # Step 6: Get AI response
            from agent_mind import call_llm
            ai_response = call_llm(
                system_instruction=system_instruction,
                prompt=formatted_prompt,
                background=False,
                call_type="astrology",
                critical=True,
                server_id=server_id,
                metadata={
                    "interaction_type": "role_command",
                    "role_context": "astrology_interpreter",
                    "mission_prompt_key": "astrology"
                }
            )

            logger.info(f"Astrology AI response received, length: {len(ai_response)}")
            return ai_response

        except Exception as e:
            logger.error(f"Error getting AI interpretation: {e}")
            return self._fallback_interpretation(reading_type, calculation_data, question)
    
    def _format_letter_data(self, calculation_data: Dict[str, Any], server_id: str = None) -> str:
        """Format letter data for AI prompt with translations."""
        text = ""
        
        # Extract letters based on reading type
        if 'layer_1_permanent' in calculation_data:  # Integrated reading
            birth = calculation_data['layer_1_permanent']['data']
            year = calculation_data['layer_2_cyclical']['data']
            moment = calculation_data['layer_3_immediate']['data']
            
            text += "**LAYER 1 - BIRTH CHART**\n"
            text += self._format_layer(birth, server_id) + "\n\n"
            
            text += "**LAYER 2 - PERSONAL YEAR**\n"
            text += f"Personal Number: {year['personal_number']}\n"
            text += f"Letter: {year['personal_letter']['hebrew']} {year['personal_letter']['name']}\n"
            translation = get_letter_translations(year['personal_letter']['name'].lower(), server_id)
            if translation:
                text += f"Meaning: {translation.get('meaning', year['personal_letter']['description'])}\n"
            text += "\n\n"
            
            text += "**LAYER 3 - MOMENT**\n"
            text += self._format_layer(moment, server_id)
            
        elif 'element' in calculation_data:  # Birth or Moment reading
            text = self._format_layer(calculation_data, server_id)
            
        elif 'personal_number' in calculation_data:  # Personal year
            text = f"Personal Number: {calculation_data['personal_number']}\n"
            text += f"Letter: {calculation_data['personal_letter']['hebrew']} {calculation_data['personal_letter']['name']}\n"
            translation = get_letter_translations(calculation_data['personal_letter']['name'].lower(), server_id)
            if translation:
                text += f"Meaning: {translation.get('meaning', calculation_data['personal_letter']['description'])}\n"
        
        return text
    
    def _format_layer(self, layer_data: Dict[str, Any], server_id: str = None) -> str:
        """Format a single layer (element, planet, sign) with translations."""
        text = ""
        
        for layer_name in ['element', 'planet', 'sign']:
            if layer_name in layer_data:
                letter = layer_data[layer_name]['letter']
                text += f"**{layer_name.capitalize()}:** {letter['hebrew']} {letter['name']}\n"
                
                # Get translation
                translation = get_letter_translations(letter['name'].lower(), server_id)
                if translation:
                    text += f"Meaning: {translation.get('meaning', letter.get('description', ''))}\n"
                    text += f"Keywords: {translation.get('keywords', '')}\n"
                else:
                    text += f"Description: {letter.get('description', '')}\n"
                
                text += "\n"
        
        return text
    
    def _format_guidance_data(self, server_id: str = None) -> str:
        """Format guidance data for AI prompt."""
        from .astrology_messages import get_guidance_messages
        
        text = "**GUIDANCE DATA:**\n\n"
        
        categories = ['love', 'career', 'health', 'path']
        for category in categories:
            guidance = get_guidance_messages(category, server_id)
            if guidance:
                text += f"**{category.upper()}**:\n"
                for key, value in guidance.items():
                    if key != 'default':
                        text += f"  {key}: {value}\n"
                text += "\n"
        
        return text
    
    def _load_interpretation_prompt(self, reading_type: str, server_id: str = None) -> str:
        """Load interpretation prompt from prompts.json."""
        try:
            import json
            import os
            
            from .astrology_messages import _get_personality_dir
            personality_dir = _get_personality_dir(server_id)
            prompts_path = os.path.join(personality_dir, "prompts.json")
            
            with open(prompts_path, encoding="utf-8") as f:
                prompts_data = json.load(f)
                
                roles = prompts_data.get("roles", {})
                shaman = roles.get("shaman", {})
                subroles = shaman.get("subroles", {})
                astrology = subroles.get("astrology", {})
                interpretation_tasks = astrology.get("interpretation_tasks", {})
                
                prompt_info = interpretation_tasks.get(f"interpret_{reading_type}", {})
                interpretation_prompt = prompt_info.get("prompt", "")
                
                # Extract golden_rules
                golden_rules = astrology.get("golden_rules", [])
                if golden_rules:
                    golden_rules_text = "\n=== GOLDEN RULES ===\n" + "\n".join(golden_rules) + "\n"
                    if interpretation_prompt:
                        interpretation_prompt += "\n\n" + golden_rules_text
                    else:
                        interpretation_prompt = golden_rules_text
                
                if interpretation_prompt:
                    return interpretation_prompt
        except Exception as e:
            logger.error(f"Error loading prompts: {e}")
        
        # Fallback prompt
        return "You are a Sefer Yetzirah interpreter. Interpret the Hebrew letters for the user's question using the provided context and guidance data."
    
    def _fallback_interpretation(self, reading_type: str, calculation_data: Dict[str, Any], question: str = None) -> str:
        """Fallback interpretation when AI is not available."""
        text = f"**Interpretation for {reading_type}**\n\n"

        # Only include question if provided (for types that require it)
        if question:
            text += f"**Question:** {question}\n\n"

        text += "This interpretation is a basic summary. For a deeper interpretation, AI is required.\n\n"

        # Add basic interpretation based on calculation data
        if 'element' in calculation_data:
            text += f"Element: {calculation_data['element']['letter']['name']} ({calculation_data['element']['letter']['element']})\n"
            text += f"{calculation_data['element']['interpretation']}\n\n"

            text += f"Planet: {calculation_data['planet']['letter']['name']} ({calculation_data['planet']['letter']['planet']})\n"
            text += f"{calculation_data['planet']['interpretation']}\n\n"
            
            text += f"Sign: {calculation_data['sign']['letter']['name']} ({calculation_data['sign']['letter']['sign']})\n"
            text += f"{calculation_data['sign']['interpretation']}\n"
        
        return text
