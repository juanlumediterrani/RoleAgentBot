"""
Nordic Runes Core Logic Module
Handles rune casting mechanics and interpretations with personality support.
"""

from typing import List, Dict, Any
from datetime import datetime
import logging
import random

from .rune_data import get_rune, get_reading_type, READING_TYPES, get_all_runes
from .nordic_runes_messages import get_guidance_messages, get_message, load_personality_messages
from ..base_role import BaseRole

logger = logging.getLogger(__name__)

try:
    import sys
    import os
    # Add project root to path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from agent_mind import call_llm
    from agent_engine import AGENT_CFG
    # Import bot display name for dynamic replacement
    try:
        from discord_bot.discord_core_commands import _bot_display_name
    except ImportError:
        # Fallback if discord is not available
        _bot_display_name = "Bot"
    AI_AVAILABLE = True
    logger.info("AI system available - rune interpretations will use AI analysis")
except ImportError:
    AI_AVAILABLE = False
    _bot_display_name = "Bot"  # Fallback
    logger.warning("AI system not available, rune interpretations will use fallback method")
    AGENT_CFG = {"personality": "personalities/putre/personality.json"}  # Fallback for testing


def _get_personality_dir() -> str:
    """Get the current personality directory dynamically."""
    try:
        personality_rel = AGENT_CFG.get("personality", "personalities/putre/personality.json")
        personality_path = os.path.join(project_root, personality_rel)
        return os.path.dirname(personality_path)
    except:
        # Fallback to putre if something goes wrong
        return os.path.join(project_root, "personalities", "putre")


class NordicRunes:
    """Core Nordic runes casting logic."""
    
    def __init__(self):
        """Initialize the runes caster."""
        self.rune_keys = list(get_all_runes().keys())
    
    def get_all_runes(self) -> Dict[str, Any]:
        """Get all available runes."""
        return get_all_runes()
    
    def cast_runes(self, reading_type: str) -> List[str]:
        """Cast runes for a specific reading type."""
        type_info = get_reading_type(reading_type)
        if not type_info:
            raise ValueError(f"Invalid reading type: {reading_type}")
        
        num_runes = type_info['runes_count']
        drawn_runes = random.sample(self.rune_keys, num_runes)
        
        logger.info(f"Cast {num_runes} runes for {reading_type} reading")
        return drawn_runes
    
    def interpret_single_rune(self, rune_obj: Dict[str, Any], question: str = "") -> str:
        """Interpret a single rune with AI analysis or fallback."""
        try:
            # Load personality messages from descriptions.json
            messages = load_personality_messages()
            
            # Get labels for display
            labels = messages.get('labels', {
                'meaning': 'Meaning',
                'keywords': 'Keywords',
                'interpretation': 'Interpretation',
                'question': 'Question',
                'guidance': 'Guidance for your question'
            })
            
            # Get translations for this rune
            translations_data = messages.get('translations', {})
            if 'rune_key' in rune_obj:
                translations = translations_data.get(rune_obj['rune_key'], {})
            else:
                translations = {}
            
            # Get guidance data
            guidance_data = messages.get('guidance', {})
        except Exception as e:
            logger.error(f"Error loading personality data: {e}")
            labels = {
                'meaning': 'Meaning',
                'keywords': 'Keywords',
                'interpretation': 'Interpretation',
                'question': 'Question',
                'guidance': 'Guidance for your question'
            }
            translations = {}
            guidance_data = {}
        
        # Get rune data from the object
        if 'rune_key' in rune_obj:
            rune_key = rune_obj['rune_key']
            rune_data = get_rune(rune_key)
        else:
            # Fallback: use rune_obj directly if it has rune data
            rune_data = rune_obj
            rune_key = rune_data.get('key', 'unknown')
        
        if not rune_data:
            return "Unknown rune"
        
        # Merge rune_obj with rune_data
        rune = {**rune_data, **rune_obj}
        
        # Get translations for this specific rune
        translations = translations_data.get(rune_key, {}) if translations_data and rune_key else {}
        
        interpretation = f"**{rune['symbol']} {rune['name']}**\n\n"
        
        # Use translated meaning if available, otherwise use English
        meaning_text = translations.get('meaning', rune.get('meaning', 'Unknown'))
        interpretation += f"**{labels['meaning']}:** {meaning_text}\n"
        
        # Use translated keywords if available, otherwise use English
        keywords_text = translations.get('keywords', ', '.join(rune.get('keywords', [])))
        interpretation += f"**{labels['keywords']}:** {keywords_text}\n\n"
        
        # Use translated interpretation if available, otherwise use English
        interpretation_text = translations.get('interpretation', rune.get('description', 'No description available'))
        interpretation += f"**{labels['interpretation']}:** {interpretation_text}\n\n"
        
        # Add contextual guidance if question provided (simplified fallback)
        if question and guidance_data:
            interpretation += f"**{labels['guidance']}:** "
            
            # Simple fallback guidance for when AI is not available
            general_guidance = guidance_data.get('general', {})
            guidance_text = general_guidance.get('default', "This rune offers ancient wisdom for your current situation.")
            
            interpretation += guidance_text
        
        # Add bot's final analysis (simplified)
        interpretation += f"\n\n**{_bot_display_name}'s Analysis:** GRRR! {rune['name']} tells you that "
        interpretation += f"the energies of {rune['name']} are with you. "
        interpretation += f"UHHH! Listen to the ancient wisdom of the runes, human! {rune['symbol']}"
        
        return interpretation
    
    def interpret_three_runes(self, rune_keys: List[str], question: str = "") -> str:
        """Interpret a three-rune spread (Past, Present, Future) - simplified fallback."""
        positions = ['Past', 'Present', 'Future']
        interpretation = "**Three Rune Spread**\n\n"
        
        # Load personality messages
        try:
            messages = load_personality_messages()
            labels = messages.get('labels', {
                'meaning': 'Meaning',
                'keywords': 'Keywords',
                'interpretation': 'Interpretation'
            })
            translations_data = messages.get('translations', {})
        except:
            labels = {'meaning': 'Meaning', 'keywords': 'Keywords', 'interpretation': 'Interpretation'}
            translations_data = {}
        
        for i, (rune_key, position) in enumerate(zip(rune_keys, positions)):
            rune = get_rune(rune_key)
            interpretation += f"**{position}: {rune['symbol']} {rune['name']}**\n"
            
            # Get translations for this rune
            translations = translations_data.get(rune_key, {}) if translations_data else {}
            
            # Use translated meaning if available, otherwise use English
            meaning_text = translations.get('meaning', rune.get('meaning', 'Unknown'))
            interpretation += f"**{labels['meaning']}:** {meaning_text}\n"
            
            # Use translated keywords if available, otherwise use English
            keywords_text = translations.get('keywords', ', '.join(rune.get('keywords', [])))
            interpretation += f"**{labels['keywords']}:** {keywords_text}\n\n"
            
            # Use translated interpretation if available, otherwise use English
            interpretation_text = translations.get('interpretation', rune.get('description', 'No description'))
            interpretation += f"**{labels['interpretation']}:** {interpretation_text}\n\n"
        
        # Simple overall guidance
        interpretation += "**Overall Guidance:** The three runes show the flow of time in your situation. "
        interpretation += "Consider how the past influences the present and shapes the future."
        
        return interpretation
    
    def interpret_cross(self, rune_keys: List[str], question: str = "") -> str:
        """Interpret a five-rune cross spread - simplified fallback."""
        positions = ['Center', 'North', 'South', 'East', 'West']
        interpretation = "**Five Rune Cross**\n\n"
        
        # Load personality messages
        try:
            messages = load_personality_messages()
            labels = messages.get('labels', {
                'meaning': 'Meaning',
                'keywords': 'Keywords',
                'interpretation': 'Interpretation'
            })
            translations_data = messages.get('translations', {})
        except:
            labels = {'meaning': 'Meaning', 'keywords': 'Keywords', 'interpretation': 'Interpretation'}
            translations_data = {}
        
        for i, (rune_key, position) in enumerate(zip(rune_keys, positions)):
            rune = get_rune(rune_key)
            interpretation += f"**{position}: {rune['symbol']} {rune['name']}**\n"
            
            # Get translations for this rune
            translations = translations_data.get(rune_key, {}) if translations_data else {}
            
            # Use translated meaning if available, otherwise use English
            meaning_text = translations.get('meaning', rune.get('meaning', 'Unknown'))
            interpretation += f"**{labels['meaning']}:** {meaning_text}\n"
            
            # Use translated keywords if available, otherwise use English
            keywords_text = translations.get('keywords', ', '.join(rune.get('keywords', [])))
            interpretation += f"**{labels['keywords']}:** {keywords_text}\n\n"
            
            # Use translated interpretation if available, otherwise use English
            interpretation_text = translations.get('interpretation', rune.get('description', 'No description'))
            interpretation += f"**{labels['interpretation']}:** {interpretation_text}\n\n"
        
        # Simple overall guidance
        interpretation += "**Overall Guidance:** The cross reveals the core issue surrounded by various influences. "
        interpretation += "Consider all aspects carefully before making decisions."
        
        return interpretation
    
    def interpret_runic_cross(self, rune_keys: List[str], question: str = "") -> str:
        """Interpret a traditional seven-rune cross - simplified fallback."""
        positions = ['Center_Present', 'North_Goals', 'South_Past', 'East_Future',
                   'West_External', 'Above', 'Below']
        interpretation = "**Runic Cross - Seven Rune Spread**\n\n"
        
        # Load personality messages
        try:
            messages = load_personality_messages()
            labels = messages.get('labels', {
                'meaning': 'Meaning',
                'keywords': 'Keywords',
                'interpretation': 'Interpretation'
            })
            translations_data = messages.get('translations', {})
        except:
            labels = {'meaning': 'Meaning', 'keywords': 'Keywords', 'interpretation': 'Interpretation'}
            translations_data = {}
        
        for i, (rune_key, position) in enumerate(zip(rune_keys, positions)):
            rune = get_rune(rune_key)
            interpretation += f"**{position}: {rune['symbol']} {rune['name']}**\n"
            
            # Get translations for this rune
            translations = translations_data.get(rune_key, {}) if translations_data else {}
            
            # Use translated meaning if available, otherwise use English
            meaning_text = translations.get('meaning', rune.get('meaning', 'Unknown'))
            interpretation += f"**{labels['meaning']}:** {meaning_text}\n"
            
            # Use translated keywords if available, otherwise use English
            keywords_text = translations.get('keywords', ', '.join(rune.get('keywords', [])))
            interpretation += f"**{labels['keywords']}:** {keywords_text}\n\n"
            
            # Use translated interpretation if available, otherwise use English
            interpretation_text = translations.get('interpretation', rune.get('description', 'No description'))
            interpretation += f"**{labels['interpretation']}:** {interpretation_text}\n\n"
        
        # Simple overall guidance
        interpretation += "**Overall Guidance:** The runic cross provides comprehensive insight into your situation, "
        interpretation += "from spiritual guidance to practical considerations. All aspects are interconnected."
        
        return interpretation
    
    def interpret_runes_with_ai(self, reading_type: str, rune_keys: List[str], question: str = "", server_id: str = None) -> str:
        """Interpret runes using AI for precise contextual analysis."""
        logger.info(f"🔮 [NORDIC_RUNES] interpret_runes_with_ai called with reading_type={reading_type}, rune_keys={rune_keys}, question='{question}'")
        
        if not AI_AVAILABLE:
            logger.warning(f"⚠️ [NORDIC_RUNES] AI not available, using fallback for {reading_type}")
            # Fallback to traditional interpretation
            if reading_type == 'single':
                return self.interpret_single_rune(rune_keys[0], question)
            elif reading_type == 'three':
                return self.interpret_three_runes(rune_keys, question)
            elif reading_type == 'cross':
                return self.interpret_cross(rune_keys, question)
            elif reading_type == 'runic_cross':
                return self.interpret_runic_cross(rune_keys, question)
            else:
                return "Unknown reading type"
        
        try:
            # Step 1: Prepare complete rune data
            rune_data = []
            positions = []
            
            if reading_type == 'single':
                positions = ['Center']
                rune_data.append({
                    'position': 'Center',
                    'rune': get_rune(rune_keys[0]),
                    'key': rune_keys[0]
                })
            elif reading_type == 'three':
                positions = ['Past', 'Present', 'Future']
                for i, rune_key in enumerate(rune_keys):
                    rune_data.append({
                        'position': positions[i],
                        'rune': get_rune(rune_key),
                        'key': rune_key
                    })
            elif reading_type == 'cross':
                positions = ['Center', 'North', 'South', 'East', 'West']
                for i, rune_key in enumerate(rune_keys):
                    rune_data.append({
                        'position': positions[i],
                        'rune': get_rune(rune_key),
                        'key': rune_key
                    })
            elif reading_type == 'runic_cross':
                positions = ['Center_Present', 'North_Goals', 'South_Past', 'East_Future',
                           'West_External', 'Above', 'Below']
                for i, rune_key in enumerate(rune_keys):
                    rune_data.append({
                        'position': positions[i],
                        'rune': get_rune(rune_key),
                        'key': rune_key
                    })
            
            # Step 2: Get ALL guidance data from descriptions.json
            guidance_data = get_guidance_messages('guidance') or {}
            
            # Step 3: Get the appropriate interpretation prompt from prompts.json
            logger.info(f"🔍 [NORDIC_RUNES] Starting to load prompts for {reading_type}")
            try:
                import json
                import os
                
                # Get project root and prompts path
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
                prompts_path = os.path.join(_get_personality_dir(), "prompts.json")
                
                with open(prompts_path, encoding="utf-8") as f:
                    prompts_data = json.load(f)
                    logger.info(f"🔍 [NORDIC_RUNES] Loaded prompts.json from: {prompts_path}")
                    logger.info(f"🔍 [NORDIC_RUNES] Available top-level keys: {list(prompts_data.keys())}")
                    
                    # Navigate to the correct path: roles.trickster.subroles.nordic_runes.interpretation_tasks
                    roles = prompts_data.get("roles", {})
                    logger.info(f"🔍 [NORDIC_RUNES] roles keys: {list(roles.keys())}")
                    
                    trickster = roles.get("trickster", {})
                    logger.info(f"🔍 [NORDIC_RUNES] trickster keys: {list(trickster.keys())}")
                    
                    subroles = trickster.get("subroles", {})
                    logger.info(f"🔍 [NORDIC_RUNES] subroles keys: {list(subroles.keys())}")
                    
                    nordic_runes = subroles.get("nordic_runes", {})
                    logger.info(f"🔍 [NORDIC_RUNES] nordic_runes keys: {list(nordic_runes.keys())}")
                    
                    interpretation_tasks = nordic_runes.get("interpretation_tasks", {})
                    logger.info(f"🔍 [NORDIC_RUNES] interpretation_tasks keys: {list(interpretation_tasks.keys())}")
                    
                    prompt_info = interpretation_tasks.get(f"interpret_{reading_type}", {})
                    interpretation_prompt = prompt_info.get("prompt", "")
                    
                    logger.info(f"🔍 [NORDIC_RUNES] Found prompt for {reading_type}: {bool(interpretation_prompt)}")
                    if interpretation_prompt:
                        logger.info(f"🔍 [NORDIC_RUNES] Preview of prompt (first 100 chars): {interpretation_prompt[:100]}...")
                    
                    # Extract golden_rules from the nordic_runes level and inject into prompt
                    golden_rules = nordic_runes.get("golden_rules", [])
                    logger.info(f"🔍 [NORDIC_RUNES] Found golden_rules: {len(golden_rules)} rules")
                    if golden_rules:
                        golden_rules_text = "\n=== GOLDEN RULES ===\n" + "\n".join(golden_rules) + "\n"
                        # Inject golden_rules at the end of the prompt
                        if interpretation_prompt:
                            interpretation_prompt += "\n\n" + golden_rules_text
                        else:
                            interpretation_prompt = golden_rules_text
                        logger.info(f"🔮 [NORDIC_RUNES] Injected {len(golden_rules)} golden rules into {reading_type} interpretation")
            except Exception as e:
                logger.error(f"❌ [NORDIC_RUNES] Error loading prompts: {e}")
                interpretation_prompt = ""
            
            if not interpretation_prompt:
                # Fallback prompt
                logger.warning(f"⚠️ [NORDIC_RUNES] Using fallback prompt for {reading_type} - specific prompt not found")
                interpretation_prompt = "You are an ancient Nordic runes interpreter. Interpret the runes for the user's question using the provided context and guidance data."
            
            # Step 4: Convert rune data to text format for the prompt
            rune_data_text = ""
            
            # Load labels and translations from descriptions.json for translation
            labels = {}
            positions = {}
            rune_translations = {}
            try:
                import json
                import os
                
                # Get project root and descriptions path
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
                descriptions_path = os.path.join(_get_personality_dir(), "descriptions.json")
                
                with open(descriptions_path, 'r', encoding='utf-8') as f:
                    descriptions = json.load(f)
                    nordic_data = descriptions.get('discord', {}).get('roles_view_messages', {}).get('trickster', {}).get('nordic_runes', {})
                    labels = nordic_data.get('labels', {})
                    
                    # Load translations and positions from separate runesplane.json file
                    runesplane_path = os.path.join(_get_personality_dir(), "descriptions", "runesplane.json")
                    if os.path.exists(runesplane_path):
                        with open(runesplane_path, 'r', encoding='utf-8') as f:
                            runesplane_data = json.load(f)
                            positions = runesplane_data.get('positions', {})
                            rune_translations = runesplane_data.get('translations', {})
                    else:
                        # Fallback to old structure if runesplane.json doesn't exist
                        positions = nordic_data.get('positions', {})
                        rune_translations = nordic_data.get('translations', {})
                    
                    # If no labels found in main descriptions.json, try loading from trickster.json
                    if not labels:
                        trickster_path = os.path.join(_get_personality_dir(), "descriptions", "trickster.json")
                        if os.path.exists(trickster_path):
                            with open(trickster_path, 'r', encoding='utf-8') as f:
                                trickster_data = json.load(f)
                                labels = trickster_data.get('nordic_runes', {}).get('labels', {})
            except Exception as e:
                # Fallback to English if translation fails
                labels = {
                    'position': 'Position',
                    'rune': 'Rune', 
                    'meaning': 'Meaning',
                    'keywords': 'Keywords',
                    'interpretation': 'Interpretation'
                }
                positions = {}
                rune_translations = {}
            
            for rune_info in rune_data:
                rune = rune_info.get('rune', {})
                position_key = rune_info.get('position', 'Unknown')
                rune_key = rune_info.get('key', '')  # Get the key from the rune_info structure
                
                # Translate position name if available
                position_name = positions.get(position_key, position_key)
                
                # Get rune translations if available
                rune_translation = rune_translations.get(rune_key, {}) if rune_key else {}
                
                # Use translated content if available, otherwise use English
                meaning_text = rune_translation.get('meaning', rune.get('meaning', 'Unknown'))
                keywords_text = rune_translation.get('keywords', ', '.join(rune.get('keywords', [])))
                interpretation_text = rune_translation.get('interpretation', rune.get('description', 'Unknown'))
                
                rune_data_text += f"{labels.get('position', 'Position')}: {position_name}\n"
                rune_data_text += f"{labels.get('rune', 'Rune')}: {rune.get('name', 'Unknown')} ({rune.get('symbol', '?')})\n"
                rune_data_text += f"{labels.get('meaning', 'Meaning')}: {meaning_text}\n"
                rune_data_text += f"{labels.get('keywords', 'Keywords')}: {keywords_text}\n"
                rune_data_text += f"{labels.get('interpretation', 'Interpretation')}: {interpretation_text}\n\n"

            # Step 5: Get complete guidance data from descriptions.json
            guidance_data_text = ""
            try:
                import json
                import os
                
                # Get project root and descriptions path
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
                descriptions_path = os.path.join(_get_personality_dir(), "descriptions.json")
                
                with open(descriptions_path, encoding="utf-8") as f:
                    descriptions_data = json.load(f)
                
                # Navigate to guidance data - try runesplane.json first
                runesplane_path = os.path.join(_get_personality_dir(), "descriptions", "runesplane.json")
                if os.path.exists(runesplane_path):
                    with open(runesplane_path, encoding="utf-8") as f:
                        runesplane_data = json.load(f)
                        guidance = runesplane_data.get("guidance", {})
                else:
                    # Fallback to old structure
                    nordic_runes = descriptions_data.get("discord", {}).get("roles_view_messages", {}).get("trickster", {}).get("nordic_runes", {})
                    guidance = nordic_runes.get("guidance", {})
                
                # Format all guidance categories
                for category, category_data in guidance.items():
                    if isinstance(category_data, dict):
                        guidance_data_text += f"\n{category.upper()}:\n"
                        for rune_key, message in category_data.items():
                            if rune_key != 'default':
                                guidance_data_text += f"  {rune_key}: {message}\n"
                            else:
                                guidance_data_text += f"  default: {message}\n"
                    else:
                        guidance_data_text += f"{category}: {category_data}\n"
                        
            except Exception as e:
                logger.error(f"Error loading guidance data: {e}")
                guidance_data_text = "Contextual guidance available for love, career, health, and path categories."

            # Step 6: Format the prompt with the specific template for this reading type
            formatted_prompt = interpretation_prompt.format(
                question=question,
                rune_data=rune_data_text,
                guidance_data=guidance_data_text
            )
            
            # Step 6: Build system instruction first
            from agent_engine import _build_system_prompt, PERSONALITY
            system_instruction = _build_system_prompt(PERSONALITY)
            
            # Step 7: Log the prompt being sent to AI using the proper prompt logging system
            from prompts_logger import log_final_llm_prompt
            from agent_db import get_active_server_id
            
            log_final_llm_prompt(
                provider="gemini",
                call_type="nordic_runes_reading",
                system_instruction=system_instruction,
                user_prompt=formatted_prompt,
                role="nordic_runes",
                server_id=server_id or get_active_server_id(),
                metadata={
                    "reading_type": reading_type,
                    "question": question,
                    "prompt_length": len(formatted_prompt)
                }
            )
            
            # Step 8: Get AI response using call_llm function
            ai_response = call_llm(
                system_instruction=system_instruction,
                prompt=formatted_prompt,
                async_mode=False,
                call_type="nordic_runes",
                critical=True,
                server_id=server_id,
                metadata={
                    "interaction_type": "role_command",
                    "role_context": "nordic_runes_interpreter",
                    "mission_prompt_key": "nordic_runes"
                }
            )
            
            # Log the AI response
            logger.info(f"🔮 [NORDIC_RUNES_AI] AI response received:")
            logger.info(f"Response length: {len(ai_response)} characters")
            logger.info(f"Full response:\n{ai_response}")
            
            return ai_response
            
        except Exception as e:
            logger.error(f"Error getting AI interpretation: {e}")
            # Fallback to traditional interpretation
            if reading_type == 'single':
                return self.interpret_single_rune(rune_keys[0], question)
            elif reading_type == 'three':
                return self.interpret_three_runes(rune_keys, question)
            elif reading_type == 'cross':
                return self.interpret_cross(rune_keys, question)
            elif reading_type == 'runic_cross':
                return self.interpret_runic_cross(rune_keys, question)
            else:
                return "Error in interpretation"
    
    def _get_love_guidance(self, rune_key: str) -> str:
        """Get love/relationship guidance for a rune."""
        guidance_messages = get_guidance_messages('love')
        guidance_map = guidance_messages if guidance_messages else {
            'fehu': "Focus on shared abundance and material harmony in your relationship.",
            'uruz': "Passionate energy and primal connection are highlighted.",
            'thurisaz': "Protect your relationship from negative influences and face challenges together.",
            'ansuz': "Clear communication and honest expression are essential.",
            'raidho': "Your love journey requires movement and exploration of new horizons.",
            'kenaz': "Clarity and vision will illuminate your romantic path.",
            'gebo': "Balance and mutual exchange are key to relationship harmony.",
            'wunjo': "Joy and happiness are flowing in your love life.",
            'hagalaz': "Unexpected changes can transform your relationship for the better.",
            'nauthiz': "Difficulties strengthen bonds and reveal true needs.",
            'isa': "A period of stability and quiet may be needed for your relationship.",
            'jera': "The natural cycle of your relationship will bring rewards in due time.",
            'eiwaz': "Transformation and resistance are necessary for relationship growth.",
            'perthro': "The mysteries of destiny are working in your love life.",
            'algiz': "Protect your relationship with divine energy and spiritual shields.",
            'sowilo': "Success and victory illuminate your romantic path.",
            'tiwaz': "Act with honor and justice in your relationships.",
            'berkano': "Nurturing growth and new beginnings in relationships.",
            'ehwaz': "Cooperative movement and joint progress strengthen your relationship.",
            'mannaz': "Focus on understanding and cooperation with your partner.",
            'laguz': "Trust your intuition and emotional flow in matters of the heart.",
            'ingwaz': "Patient growth and fertile potential in your relationship.",
            'dagaz': "A dawn and new opportunities await in your love life.",
            'othala': "Your heritage and family traditions guide your relationships."
        }
        return guidance_map.get(rune_key, "This rune brings wisdom to your relationship journey.")
    
    def _get_career_guidance(self, rune_key: str) -> str:
        """Get career/work guidance for a rune."""
        guidance_messages = get_guidance_messages('career')
        guidance_map = guidance_messages if guidance_messages else {
            'fehu': "Material success and financial abundance are indicated.",
            'uruz': "Assert your strength and take bold action in your career.",
            'thurisaz': "Protect your interests and face challenges head-on.",
            'ansuz': "Clear communication and essential knowledge will advance your career.",
            'raidho': "Journey and movement in your career path are coming.",
            'kenaz': "Creative solutions and intellectual clarity will guide you.",
            'gebo': "Professional partnerships and mutual exchange will bring success.",
            'wunjo': "Joy and satisfaction are flowing in your work.",
            'hagalaz': "Disruptive changes can create new professional opportunities.",
            'nauthiz': "Work pressures will drive you to find creative solutions.",
            'isa': "A period of pause and reflection may be needed for your career.",
            'jera': "Your efforts will bear fruit in due time.",
            'eiwaz': "Resilience and adaptation are key for professional progress.",
            'perthro': "The mysteries of destiny reveal unexpected professional opportunities.",
            'algiz': "Protect your career with wisdom and strategic defense.",
            'sowilo': "Success and victory in your professional endeavors.",
            'tiwaz': "Act with honor and justice in your workplace.",
            'berkano': "Professional growth and new beginnings are on the way.",
            'ehwaz': "Cooperative movement and teamwork will drive your success.",
            'mannaz': "Cooperation and professional relationships are fundamental.",
            'laguz': "Trust your intuition and creative flow in work decisions.",
            'ingwaz': "Latent potential will gradually develop in your career.",
            'dagaz': "A breakthrough and new opportunities are emerging.",
            'othala': "Your heritage and traditional skills are valuable in your work."
        }
        return guidance_map.get(rune_key, "This rune offers insight for your professional path.")
    
    def _get_health_guidance(self, rune_key: str) -> str:
        """Get health guidance for a rune."""
        guidance_messages = get_guidance_messages('health')
        guidance_map = guidance_messages if guidance_messages else {
            'fehu': "Physical health and material well-being are connected to your vitality.",
            'uruz': "Focus on building physical strength and vitality.",
            'thurisaz': "Protect your health from threats and face medical challenges with strength.",
            'ansuz': "Clear communication with your body and healthcare providers is essential for healing.",
            'raidho': "Your health journey requires movement and positive changes.",
            'kenaz': "Mental clarity and knowledge will illuminate your path to healing.",
            'gebo': "Balance between body and mind is fundamental for your health.",
            'wunjo': "Joy and happiness significantly contribute to your well-being.",
            'hagalaz': "Health changes can be disruptive but necessary for healing.",
            'nauthiz': "Health needs reveal areas requiring immediate attention.",
            'isa': "A period of rest and stillness may be needed for your health.",
            'jera': "Natural healing cycles and gradual recovery.",
            'eiwaz': "Resilience and adaptation are key to overcoming health challenges.",
            'perthro': "The mysteries of healing are working in your body.",
            'algiz': "Protect your health and seek divine healing energy.",
            'sowilo': "Life force energy and healing light are available.",
            'tiwaz': "Act with courage and discipline in your health habits.",
            'berkano': "Growth, renewal, and natural healing processes.",
            'ehwaz': "Movement and natural flow are essential for your health.",
            'mannaz': "Cooperation with healthcare professionals supports your well-being.",
            'laguz': "Emotional healing and cleansing energies.",
            'ingwaz': "Stored energy and gradual restoration of health.",
            'dagaz': "A health breakthrough and new wellness opportunities.",
            'othala': "Your genetic heritage and family traditions influence your health."
        }
        return guidance_map.get(rune_key, "This rune brings healing energy to your situation.")
    
    def _get_path_guidance(self, rune_key: str) -> str:
        """Get life path guidance for a rune."""
        guidance_messages = get_guidance_messages('path')
        guidance_map = guidance_messages if guidance_messages else {
            'fehu': "Your material and financial path is flowing toward abundance.",
            'uruz': "Your path requires primal strength and energy to overcome obstacles.",
            'thurisaz': "Protect your path from negative influences and face challenges with courage.",
            'ansuz': "Divine messages will guide your path forward.",
            'raidho': "Your journey requires movement and exploration on your life path.",
            'kenaz': "Clarity and vision will illuminate your path.",
            'gebo': "Partnerships and mutual exchange will define your path.",
            'wunjo': "Joy and happiness are flowing on your life path.",
            'hagalaz': "Disruptive changes are necessary to evolve on your path.",
            'nauthiz': "Needs and constraints reveal the true direction of your path.",
            'isa': "A period of pause and reflection is necessary for your path.",
            'jera': "The natural cycle of your path will bring rewards in due time.",
            'eiwaz': "Transformation and resistance are necessary on your path.",
            'perthro': "The mysteries and destiny are working on your journey.",
            'algiz': "Protect your path with divine guidance and spiritual shields.",
            'sowilo': "Success and victory illuminate your life path.",
            'tiwaz': "Act with honor and justice in your path decisions.",
            'berkano': "Growth and new beginnings define your current path.",
            'ehwaz': "Cooperative movement and joint progress mark your path.",
            'mannaz': "Your path involves cooperation and community.",
            'laguz': "Trust your intuition and emotional flow on your path.",
            'ingwaz': "Latent potential will gradually develop on your path.",
            'dagaz': "A dawn and a new future await on your path.",
            'othala': "Your heritage and ancestral wisdom guide your path."
        }
        return guidance_map.get(rune_key, "This rune offers guidance for your life journey.")
    
    def _get_general_guidance(self, rune_key: str) -> str:
        """Get general guidance for a rune."""
        rune = get_rune(rune_key)
        return f"This {rune['name']} rune suggests {rune['description'].lower()}"
    
    def _get_three_rune_guidance(self, rune_keys: List[str], question: str) -> str:
        """Get guidance for three-rune spread."""
        return "The runes show a progression from past influences through present circumstances to future outcomes. Trust the journey and remain open to the wisdom revealed."
    
    def _get_cross_guidance(self, rune_keys: List[str], question: str) -> str:
        """Get guidance for five-rune cross."""
        return "The cross reveals the core issue surrounded by various influences. Consider all aspects carefully before making decisions."
    
    def _get_runic_cross_guidance(self, rune_keys: List[str], question: str) -> str:
        """Get guidance for seven-rune cross."""
        return "The runic cross provides comprehensive insight into your situation, from spiritual guidance to practical considerations. All aspects are interconnected."
    
    def get_reading(self, reading_type: str, question: str = "", server_id: str = None) -> Dict[str, Any]:
        """Perform a complete rune reading."""
        try:
            # Cast the runes
            drawn_runes_keys = self.cast_runes(reading_type)
            
            # Convert rune keys to full rune objects
            drawn_runes = []
            reading_info = get_reading_type(reading_type)
            positions = reading_info.get('positions', [])
            
            for i, rune_key in enumerate(drawn_runes_keys):
                position = positions[i] if i < len(positions) else 'Unknown'
                rune_data = get_rune(rune_key)
                # Include the rune key in the rune object for translation lookup
                rune_data_with_key = rune_data.copy()
                rune_data_with_key['key'] = rune_key
                drawn_runes.append({
                    'key': rune_key,
                    'name': rune_data.get('name', 'Unknown'),
                    'symbol': rune_data.get('symbol', '?'),
                    'meaning': rune_data.get('meaning', 'Unknown'),
                    'keywords': rune_data.get('keywords', []),
                    'description': rune_data.get('description', ''),
                    'position': position
                })
            
            # Get interpretation - use AI if available, fallback to traditional
            if AI_AVAILABLE:
                interpretation = self.interpret_runes_with_ai(reading_type, [r['key'] for r in drawn_runes], question, server_id)
            else:
                # Traditional interpretation
                if reading_type == 'single':
                    interpretation = self.interpret_single_rune(drawn_runes[0], question)
                elif reading_type == 'three':
                    interpretation = self.interpret_three_runes([r['key'] for r in drawn_runes], question)
                elif reading_type == 'cross':
                    interpretation = self.interpret_cross([r['key'] for r in drawn_runes], question)
                elif reading_type == 'runic_cross':
                    interpretation = self.interpret_runic_cross([r['key'] for r in drawn_runes], question)
                else:
                    raise ValueError(f"Unknown reading type: {reading_type}")
            
            return {
                'runes_drawn': drawn_runes,
                'interpretation': interpretation,
                'reading_type': reading_type,
                'question': question
            }
            
        except Exception as e:
            logger.error(f"Error in rune reading: {e}")
            raise
