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
                   question: str = "", server_id: str = None) -> Dict[str, Any]:
        """
        Main entry point for getting a reading.
        
        Args:
            reading_type: Type of reading ('birth', 'moment', 'year', 'integrated')
            input_data: Dictionary with required inputs for the reading type
            question: Optional question for contextual interpretation
            server_id: Server ID for personality-specific messages
        
        Returns:
            Dictionary with calculation data and interpretation
        """
        type_info = get_reading_type(reading_type)
        if not type_info:
            raise ValueError(f"Invalid reading type: {reading_type}")
        
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
            'question': question
        }
    
    def calculate_birth_chart(self, birth_date: datetime, 
                             birth_time: Optional[time] = None) -> Dict[str, Any]:
        """
        Calculate the three-layer birth chart from birth date and time.
        
        Paso 1: Identificar el Elemento del alma (Letra Madre)
        Paso 2: Identificar el Planeta rector (Letra Doble)
        Paso 3: Identificar el Signo zodiacal (Letra Simple)
        """
        logger.info(f"Calculating birth chart for date: {birth_date}, time: {birth_time}")
        
        # Paso 1: Elemento del alma (estación)
        month = birth_date.month
        if month in [3, 4, 9, 10]:  # Primavera u Otoño
            element_letter = get_letter_by_element('Air')
            season = 'Temperada'
        elif month in [6, 7, 8]:  # Verano
            element_letter = get_letter_by_element('Fire')
            season = 'Verano'
        else:  # Invierno
            element_letter = get_letter_by_element('Water')
            season = 'Invierno'
        
        # Paso 2: Planeta rector (día de la semana)
        weekday = birth_date.weekday()
        planet_letter = get_planet_by_day_index(weekday)
        
        # Si se tiene hora, calcular planeta de la hora
        if birth_time:
            planet_letter = get_planet_by_chaldean_hour(birth_time.hour)
            logger.info(f"Using hour-based planet: {planet_letter.get('name')}")
        
        # Paso 3: Signo zodiacal (fecha)
        sign_letter = self._calculate_sign_by_date(birth_date)
        
        return {
            'element': {
                'letter': element_letter,
                'season': season,
                'interpretation': f"Alma de {element_letter['element']}: {element_letter['description']}"
            },
            'planet': {
                'letter': planet_letter,
                'day': birth_date.strftime('%A'),
                'interpretation': f"Planeta rector {planet_letter['planet']}: {planet_letter['description']}"
            },
            'sign': {
                'letter': sign_letter,
                'interpretation': f"Signo {sign_letter['sign']}: {sign_letter['description']}"
            },
            'synthesis': self._synthesize_birth_chart(element_letter, planet_letter, sign_letter)
        }
    
    def calculate_moment_reading(self, question_date: datetime,
                                 question_time: Optional[time] = None) -> Dict[str, Any]:
        """
        Calculate the three-layer moment reading for a specific question.
        
        Paso 1: Leer el entorno elemental
        Paso 2: Identificar el planeta del día
        Paso 3: Analizar el signo del mes
        Paso 4: Identificar tensión entre niveles
        """
        logger.info(f"Calculating moment reading for date: {question_date}, time: {question_time}")
        
        # Paso 1: Entorno elemental
        month = question_date.month
        if month in [3, 4, 9, 10]:
            element_letter = get_letter_by_element('Air')
            season_tone = "equilibrio inestable, puede inclinarse en cualquier dirección"
        elif month in [6, 7, 8]:
            element_letter = get_letter_by_element('Fire')
            season_tone = "urgencia, acción mental, claridad que puede quemar"
        else:
            element_letter = get_letter_by_element('Water')
            season_tone = "paciencia, introversión, descenso hacia lo profundo"
        
        # Paso 2: Planeta del día
        weekday = question_date.weekday()
        planet_letter = get_planet_by_day_index(weekday)
        
        # Paso 3: Signo del mes
        sign_letter = self._calculate_sign_by_date(question_date)
        
        # Paso 4: Análisis de tensión
        tension_analysis = self._analyze_tension(element_letter, planet_letter, sign_letter)
        
        return {
            'element': {
                'letter': element_letter,
                'tone': season_tone,
                'interpretation': f"Elemento {element_letter['element']}: {season_tone}"
            },
            'planet': {
                'letter': planet_letter,
                'nature': self._get_planet_nature(planet_letter['planet']),
                'interpretation': f"Fuerza regente {planet_letter['planet']}: {planet_letter['description']}"
            },
            'sign': {
                'letter': sign_letter,
                'faculty': sign_letter['faculty'],
                'interpretation': f"Facultad activa {sign_letter['faculty']}: {sign_letter['description']}"
            },
            'synthesis': {
                'tension': tension_analysis['is_tension'],
                'interpretation': tension_analysis['interpretation']
            }
        }
    
    def calculate_personal_year(self, birth_year: int, current_year: int) -> Dict[str, Any]:
        """
        Calculate the personal year number and letter.
        
        Paso 1: Calcular número del año de nacimiento
        Paso 2: Calcular número del año en curso
        Paso 3: Calcular número personal (1-22)
        Paso 4: Mapear a letra hebrea
        """
        logger.info(f"Calculating personal year: birth={birth_year}, current={current_year}")
        
        # Paso 1: Año de nacimiento
        birth_sum = self._reduce_to_single_digit(birth_year)
        
        # Paso 2: Año en curso
        current_sum = self._reduce_to_single_digit(current_year)
        
        # Paso 3: Número personal
        personal_number = birth_sum + current_sum
        while personal_number > 22:
            personal_number = self._reduce_to_single_digit(personal_number)
        
        # Paso 4: Letras
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
        
        CAPA 1 (permanente) — Carta natal
        CAPA 2 (cíclica) — Año personal
        CAPA 3 (inmediata) — Momento de la consulta
        """
        logger.info("Calculating integrated reading")
        
        # CAPA 1
        birth_chart = self.calculate_birth_chart(birth_date, birth_time)
        
        # CAPA 2
        current_year = question_date.year
        birth_year = birth_date.year
        personal_year = self.calculate_personal_year(birth_year, current_year)
        
        # CAPA 3
        moment_reading = self.calculate_moment_reading(question_date, question_time)
        
        # SÍNTESIS
        synthesis = self._analyze_integrated_synthesis(birth_chart, personal_year, moment_reading)
        
        return {
            'layer_1_permanent': {
                'name': 'Carta Natal (Permanente)',
                'data': birth_chart
            },
            'layer_2_cyclical': {
                'name': 'Año Personal (Cíclico)',
                'data': personal_year
            },
            'layer_3_immediate': {
                'name': 'Momento de Consulta (Inmediato)',
                'data': moment_reading
            },
            'synthesis': synthesis
        }
    
    # Métodos auxiliares privados
    
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
        **Síntesis de la Carta Natal:**
        
        Elemento: {element_letter['name']} ({element_letter['element']})
        - {element_letter['description']}
        
        Planeta: {planet_letter['name']} ({planet_letter['planet']})
        - {planet_letter['description']}
        
        Signo: {sign_letter['name']} ({sign_letter['sign']})
        - {sign_letter['description']}
        
        **Preguntas para reflexión:**
        - ¿El elemento y el signo se refuerzan o se tensionan?
        - ¿El planeta opera en su cara luminosa o sombría?
        - ¿Dónde está el tikún (corrección espiritual)?
        """
    
    def _get_planet_nature(self, planet: str) -> str:
        """Get the nature of inquiry for each planet."""
        natures = {
            'Saturn': 'Asuntos de límites, tiempo, herencias, karma, restricciones',
            'Jupiter': 'Asuntos de expansión, justicia, abundancia, viajes espirituales',
            'Mars': 'Conflictos, decisiones urgentes, cirugía, competencia',
            'Sun': 'Liderazgo, identidad, salud vital, reconocimiento',
            'Venus': 'Relaciones, arte, dinero, armonía o ruptura',
            'Mercury': 'Comunicación, contratos, estudios, mensajes',
            'Moon': 'Emociones, ciclos, lo doméstico, lo cambiante'
        }
        return natures.get(planet, 'Influencia planetaria general')
    
    def _analyze_tension(self, element_letter, planet_letter, sign_letter) -> Dict[str, Any]:
        """Analyze if levels are aligned or in tension."""
        # Simplificado - se puede expandir
        element = element_letter.get('element', '')
        planet = planet_letter.get('planet', '')
        sign = sign_letter.get('sign', '')
        
        aligned_combinations = [
            ('Fire', 'Sun', 'Leo'),
            ('Water', 'Moon', 'Cancer'),
            ('Air', 'Mercury', 'Gemini'),
        ]
        
        current_combo = (element, planet, sign)
        
        if current_combo in aligned_combinations:
            return {
                'is_tension': False,
                'interpretation': 'Las fuerzas están alineadas. La situación tiene inercia clara.'
            }
        else:
            return {
                'is_tension': True,
                'interpretation': 'Hay contradicción entre niveles. Punto de elección real.'
            }
    
    def _get_year_interpretation(self, personal_letter, collective_letter) -> str:
        """Get interpretation for personal year within collective context."""
        return f"""
        **Año Personal:** {personal_letter['name']} - {personal_letter['description']}
        
        **Clima Colectivo:** {collective_letter['name']} - {collective_letter['description']}
        
        Tu año personal opera dentro del clima colectivo.
        """
    
    def _analyze_integrated_synthesis(self, birth_chart, personal_year, moment_reading) -> Dict[str, Any]:
        """Analyze alignment between three layers."""
        # Simplificado de las 5 preguntas del intérprete
        return {
            'dominant_element': birth_chart['element']['letter']['element'],
            'ruling_planet': {
                'birth': birth_chart['planet']['letter']['planet'],
                'moment': moment_reading['planet']['letter']['planet']
            },
            'active_faculty': f"{birth_chart['sign']['letter']['faculty']} (natal), {moment_reading['sign']['letter']['faculty']} (momento)",
            'alignment': 'Análisis de alineación entre capas',
            'tikun': 'Corrección espiritual indicada por la configuración'
        }
    
    def interpret_with_ai(self, reading_type: str, calculation_data: Dict[str, Any],
                        question: str = "", server_id: str = None) -> str:
        """
        Interpret calculation using AI for precise contextual analysis.
        Similar to nordic_runes.interpret_runes_with_ai()
        """
        logger.info(f"Astrology interpret_with_ai called with reading_type={reading_type}")
        
        if not AI_AVAILABLE:
            logger.warning("AI not available, using fallback for astrology")
            return self._fallback_interpretation(reading_type, calculation_data, question)
        
        try:
            # Step 1: Prepare letter data with translations
            letter_data_text = self._format_letter_data(calculation_data, server_id)
            
            # Step 2: Get guidance data
            guidance_data_text = self._format_guidance_data(server_id)
            
            # Step 3: Get the appropriate interpretation prompt from prompts.json
            interpretation_prompt = self._load_interpretation_prompt(reading_type, server_id)
            
            # Step 4: Format the prompt
            formatted_prompt = interpretation_prompt.format(
                question=question,
                letter_data=letter_data_text,
                guidance_data=guidance_data_text
            )
            
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
            
            text += "**CAPA 1 - CARTA NATAL**\n"
            text += self._format_layer(birth, server_id) + "\n\n"
            
            text += "**CAPA 2 - AÑO PERSONAL**\n"
            text += f"Número Personal: {year['personal_number']}\n"
            text += f"Letra: {year['personal_letter']['hebrew']} {year['personal_letter']['name']}\n"
            translation = get_letter_translations(year['personal_letter']['name'].lower(), server_id)
            if translation:
                text += f"Significado: {translation.get('meaning', year['personal_letter']['description'])}\n"
            text += "\n\n"
            
            text += "**CAPA 3 - MOMENTO**\n"
            text += self._format_layer(moment, server_id)
            
        elif 'element' in calculation_data:  # Birth or Moment reading
            text = self._format_layer(calculation_data, server_id)
            
        elif 'personal_number' in calculation_data:  # Personal year
            text = f"Número Personal: {calculation_data['personal_number']}\n"
            text += f"Letra: {calculation_data['personal_letter']['hebrew']} {calculation_data['personal_letter']['name']}\n"
            translation = get_letter_translations(calculation_data['personal_letter']['name'].lower(), server_id)
            if translation:
                text += f"Significado: {translation.get('meaning', calculation_data['personal_letter']['description'])}\n"
        
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
                    text += f"Significado: {translation.get('meaning', letter.get('description', ''))}\n"
                    text += f"Palabras clave: {translation.get('keywords', '')}\n"
                else:
                    text += f"Descripción: {letter.get('description', '')}\n"
                
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
    
    def _fallback_interpretation(self, reading_type: str, calculation_data: Dict[str, Any], question: str) -> str:
        """Fallback interpretation when AI is not available."""
        text = f"**Interpretación para {reading_type}**\n\n"
        
        if question:
            text += f"**Pregunta:** {question}\n\n"
        
        text += "Esta interpretación es un resumen básico. Para una interpretación más profunda, se requiere disponer de IA.\n\n"
        
        # Add basic interpretation based on calculation data
        if 'element' in calculation_data:
            text += f"Elemento: {calculation_data['element']['letter']['name']} ({calculation_data['element']['letter']['element']})\n"
            text += f"{calculation_data['element']['interpretation']}\n\n"
            
            text += f"Planeta: {calculation_data['planet']['letter']['name']} ({calculation_data['planet']['letter']['planet']})\n"
            text += f"{calculation_data['planet']['interpretation']}\n\n"
            
            text += f"Signo: {calculation_data['sign']['letter']['name']} ({calculation_data['sign']['letter']['sign']})\n"
            text += f"{calculation_data['sign']['interpretation']}\n"
        
        return text
