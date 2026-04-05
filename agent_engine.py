import os
import json
import random
from datetime import datetime, timedelta
from agent_logging import get_logger
from postprocessor import postprocess_response, is_blocked_response
from agent_db import get_active_server_id, get_global_db
from prompts_logger import log_system_prompt, log_agent_response, log_final_llm_prompt
from agent_runtime import increment_usage as runtime_increment_usage
from pathlib import Path
from dotenv import load_dotenv
import logging

# Import bot display name for dynamic replacement
try:
    from discord_bot.discord_core_commands import _bot_display_name
except ImportError:
    # Fallback if discord is not available
    _bot_display_name = "Bot"

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_AGENT_CONFIG_PATH = os.path.join(_BASE_DIR, "agent_config.json")

load_dotenv()
logger = logging.getLogger(__name__)

with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
    AGENT_CFG = json.load(f)


def _replace_bot_display_name_placeholders(obj, bot_display_name: str):
    """Recursively replace {_bot_display_name} placeholders in strings within nested data structures."""
    if isinstance(obj, dict):
        return {key: _replace_bot_display_name_placeholders(value, bot_display_name) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_replace_bot_display_name_placeholders(item, bot_display_name) for item in obj]
    elif isinstance(obj, str):
        return obj.replace("{_bot_display_name}", bot_display_name)
    else:
        return obj


def _load_personality_descriptions() -> dict:
    try:
        personality_rel = AGENT_CFG.get("personality", "")
        personality_path = os.path.join(_BASE_DIR, personality_rel)
        descriptions_path = os.path.join(os.path.dirname(personality_path), "descriptions.json")
        descriptions = {}
        
        # Load main descriptions.json
        if os.path.exists(descriptions_path):
            with open(descriptions_path, encoding="utf-8") as f:
                descriptions = json.load(f).get("discord", {})
        
        # Load news_watcher descriptions from separate file
        news_watcher_descriptions_path = os.path.join(os.path.dirname(personality_path), "descriptions", "news_watcher.json")
        if os.path.exists(news_watcher_descriptions_path):
            with open(news_watcher_descriptions_path, encoding="utf-8") as f:
                news_watcher_descriptions = json.load(f)
                # Merge news_watcher descriptions into roles_view_messages
                if "roles_view_messages" not in descriptions:
                    descriptions["roles_view_messages"] = {}
                descriptions["roles_view_messages"]["news_watcher"] = news_watcher_descriptions
        
        # Load treasure_hunter descriptions from separate file
        treasure_hunter_descriptions_path = os.path.join(os.path.dirname(personality_path), "descriptions", "treasure_hunter.json")
        if os.path.exists(treasure_hunter_descriptions_path):
            with open(treasure_hunter_descriptions_path, encoding="utf-8") as f:
                treasure_hunter_descriptions = json.load(f)
                # Merge treasure_hunter descriptions into roles_view_messages
                if "roles_view_messages" not in descriptions:
                    descriptions["roles_view_messages"] = {}
                descriptions["roles_view_messages"]["treasure_hunter"] = treasure_hunter_descriptions
        
        # Load trickster descriptions from separate file
        trickster_descriptions_path = os.path.join(os.path.dirname(personality_path), "descriptions", "trickster.json")
        if os.path.exists(trickster_descriptions_path):
            with open(trickster_descriptions_path, encoding="utf-8") as f:
                trickster_descriptions = json.load(f)
                # Merge trickster descriptions into roles_view_messages
                if "roles_view_messages" not in descriptions:
                    descriptions["roles_view_messages"] = {}
                descriptions["roles_view_messages"]["trickster"] = trickster_descriptions
        
        # Load banker descriptions from separate file
        banker_descriptions_path = os.path.join(os.path.dirname(personality_path), "descriptions", "banker.json")
        if os.path.exists(banker_descriptions_path):
            with open(banker_descriptions_path, encoding="utf-8") as f:
                banker_descriptions = json.load(f)
                # Merge banker descriptions into roles_view_messages
                if "roles_view_messages" not in descriptions:
                    descriptions["roles_view_messages"] = {}
                descriptions["roles_view_messages"]["banker"] = banker_descriptions
        
        # Load mc descriptions from separate file
        mc_descriptions_path = os.path.join(os.path.dirname(personality_path), "descriptions", "mc.json")
        if os.path.exists(mc_descriptions_path):
            with open(mc_descriptions_path, encoding="utf-8") as f:
                mc_descriptions = json.load(f)
                # Merge mc descriptions into roles_view_messages
                if "roles_view_messages" not in descriptions:
                    descriptions["roles_view_messages"] = {}
                descriptions["roles_view_messages"]["mc"] = mc_descriptions
        
        # Replace {_bot_display_name} placeholder with actual bot name
        bot_display_name = PERSONALITY.get("bot_display_name", PERSONALITY.get("name", "Bot"))
        descriptions = _replace_bot_display_name_placeholders(descriptions, bot_display_name)
        
        return descriptions
    except Exception as e:
        logger.warning(f"Could not load personality descriptions.json: {e}")
    return {}

# --- MC CONFIGURATION FUNCTIONS ---
def get_mc_mode():
    """Get MC execution mode from config."""
    mc_config = AGENT_CFG.get("roles", {}).get("mc", {})
    return mc_config.get("mode", "integrated")  # default: integrated

def is_mc_enabled():
    """Check if MC is enabled."""
    mc_config = AGENT_CFG.get("roles", {}).get("mc", {})
    return mc_config.get("enabled", False)

def get_mc_config():
    """Get complete MC configuration."""
    return AGENT_CFG.get("roles", {}).get("mc", {})

def get_mc_feature(feature_name):
    """Get specific MC feature."""
    mc_config = get_mc_config()
    features = mc_config.get("features", {})
    return features.get(feature_name, False)

def get_mc_voice_settings():
    """Get MC voice configuration."""
    mc_config = get_mc_config()
    return mc_config.get("voice_settings", {})

def get_mc_audio_quality():
    """Get MC audio quality configuration."""
    mc_config = get_mc_config()
    return mc_config.get("audio_quality", {})

def _get_subrole_frequency_from_config(subrole_name: str) -> int:
    """Get subrole frequency from agent_config.json."""
    try:
        # Load agent_config.json
        with open(_AGENT_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Navigate to subrole frequency
        roles_cfg = config.get("roles", {})
        trickster_cfg = roles_cfg.get("trickster", {})
        subroles_cfg = trickster_cfg.get("subroles", {})
        subrole_cfg = subroles_cfg.get(subrole_name, {})
        
        return subrole_cfg.get("frequency_hours", 12)  # Default to 12 hours
        
    except Exception as e:
        logger.warning(f"Could not get frequency for {subrole_name} from config: {e}")
        return 12  # Default fallback

def _cargar_personalidad() -> dict:
    with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
        agent_cfg = json.load(f)
    personality_rel = agent_cfg.get("personality", "personalities/default.json")
    personality_path = os.path.join(_BASE_DIR, personality_rel)
    
    # Check if personality is a directory (new split structure)
    personality_dir = os.path.dirname(personality_path)
    if os.path.exists(os.path.join(personality_dir, 'personality.json')) and \
       os.path.exists(os.path.join(personality_dir, 'prompts.json')):
        # Load split files
        merged_personality = {}
        
        # Load personality.json
        personality_file = os.path.join(personality_dir, 'personality.json')
        if os.path.exists(personality_file):
            with open(personality_file, encoding="utf-8") as f:
                merged_personality.update(json.load(f))
        
        # Load prompts.json
        prompts_file = os.path.join(personality_dir, 'prompts.json')
        if os.path.exists(prompts_file):
            with open(prompts_file, encoding="utf-8") as f:
                merged_personality.update(json.load(f))
        
        # Load descriptions.json
        descriptions_file = os.path.join(personality_dir, 'descriptions.json')
        if os.path.exists(descriptions_file):
            with open(descriptions_file, encoding="utf-8") as f:
                descriptions_data = json.load(f)
                # Merge descriptions data under 'discord' key to match JSON structure
                if 'discord' not in merged_personality:
                    merged_personality['discord'] = {}
                merged_personality['discord'].update(descriptions_data.get('discord', {}))
                # Also store descriptions at root for backward compatibility
                merged_personality['descriptions'] = descriptions_data.get('discord', {})
        
        # Load answers.json
        answers_file = os.path.join(personality_dir, 'answers.json')
        if os.path.exists(answers_file):
            with open(answers_file, encoding="utf-8") as f:
                answers_data = json.load(f)
                # Merge answers data under 'answers' key
                merged_personality['answers'] = answers_data
        
        return merged_personality
    else:
        # Load single file (legacy structure)
        with open(personality_path, encoding="utf-8") as f:
            return json.load(f)

PERSONALITY = _cargar_personalidad()
_personality_descriptions = _load_personality_descriptions()
# Only show personality log if not in role subprocess
if os.getenv('ROLE_AGENT_PROCESS') != '1':
    logger.info(f"🎭 [PERSONALITY] Loaded: {PERSONALITY.get('name', 'Unknown')} from {AGENT_CFG.get('personality', 'Unknown')}")


def get_discord_token():
    """Get Discord token specific for active personality."""
    personality_name = PERSONALITY.get("name", "").upper()
    specific_token = os.getenv(f"DISCORD_TOKEN_{personality_name}")
    if specific_token:
        logger.info(f"🔑 Using specific token: DISCORD_TOKEN_{personality_name}")
        return specific_token
    # Fallback to generic token
    fallback_token = os.getenv("DISCORD_TOKEN")
    if fallback_token:
        logger.info(f"🔑 Using generic token: DISCORD_TOKEN")
    else:
        logger.warning("⚠️ No Discord token found (neither specific nor generic)")
    return fallback_token


# Cache to avoid multiple role verifications
_roles_verified = False
_active_tasks_cache = []

def _get_role_prompt_catalog() -> dict:
    role_system_prompts = PERSONALITY.get("roles", {})
    if not isinstance(role_system_prompts, dict):
        return {}
    return role_system_prompts


def _get_active_duty_text(config: dict, server_id: str = None, subrole_name: str = None) -> str:
    if not isinstance(config, dict):
        return ""
    
    duty_text = str(config.get("active_duty") or config.get("mission_active") or "").strip()
    
    # Handle ring subrole special case: replace <accusated_user> placeholder
    if subrole_name == "ring" and server_id and "<accusated_user>" in duty_text:
        try:
            from roles.trickster.subroles.ring.ring_discord import _get_ring_state
            ring_state = _get_ring_state(server_id)
            target_user_name = ring_state.get("target_user_name", "Unknown bearer")
            duty_text = duty_text.replace("<accusated_user>", target_user_name)
            logger.debug(f"🎭 [RING] Replaced <accusated_user> with '{target_user_name}' in system prompt")
        except Exception as e:
            logger.warning(f"🎭 [RING] Failed to replace <accusated_user> placeholder: {e}")
            # Fallback to a generic name if ring state is not available
            duty_text = duty_text.replace("<accusated_user>", "el usuario sospechoso")
    
    # Handle beggar subrole special case: always append current reason regardless of format
    if subrole_name == "beggar" and server_id:
        try:
            from roles.trickster.subroles.beggar.beggar_config import get_beggar_config
            beggar_config = get_beggar_config(server_id)
            
            if beggar_config.is_enabled():
                current_reason = beggar_config.get_current_reason()
                if current_reason:
                    # Always append the reason, regardless of whether duty_text ends with colon
                    if duty_text.strip():
                        # If duty_text ends with colon, append directly, otherwise add separator
                        if duty_text.rstrip().endswith(":"):
                            duty_text = duty_text + " " + current_reason
                        else:
                            duty_text = duty_text + ": " + current_reason
                    else:
                        # If duty_text is empty, just use the reason
                        duty_text = current_reason
                    
                    logger.debug(f"🎭 [BEGGAR] Injected current reason '{current_reason}' in system prompt")
                else:
                    logger.debug("🎭 [BEGGAR] No current reason available, leaving base line unchanged")
            else:
                logger.debug("🎭 [BEGGAR] Beggar not enabled, leaving base line unchanged")
        except Exception as e:
            logger.debug(f"🎭 [BEGGAR] Failed to inject current reason: {e}")
    
    return duty_text


def _get_role_display_name(role_name: str) -> str:
    """Get Spanish display name from descriptions.json with fallback to technical name."""
    try:
        from pathlib import Path
        
        def _get_personality_dir():
            """Get the current personality directory dynamically."""
            try:
                personality_rel = AGENT_CFG.get("personality", "personalities/putre/personality.json")
                personality_path = Path(__file__).parent / personality_rel
                return personality_path.parent
            except:
                # Fallback to putre if something goes wrong
                return Path(__file__).parent / "personalities" / "putre"
        
        descriptions_path = _get_personality_dir() / "descriptions.json"
        if descriptions_path.exists():
            import json
            descriptions = json.loads(descriptions_path.read_text(encoding='utf-8'))
            discord_roles = descriptions.get("discord", {}).get("roles_view_messages", {})
            
            # Map role names to their Spanish titles
            role_titles = {
                "news_watcher": discord_roles.get("news_watcher", {}).get("title", "").replace("**", "").strip(),
                "treasure_hunter": discord_roles.get("treasure_hunter", {}).get("title", "").replace("**", "").strip(),
                "trickster": discord_roles.get("trickster", {}).get("title", "").replace("**", "").strip(),
                "banker": discord_roles.get("banker", {}).get("title", "").replace("**", "").strip(),
                "mc": discord_roles.get("mc", {}).get("title", "").replace("**", "").strip(),
            }
            
            # Get subrole titles from trickster
            trickster_subroles = discord_roles.get("trickster", {}).get("canvas_trickster_subrole_descriptions", {})
            subrole_titles = {
                "beggar": trickster_subroles.get("beggar", "").split("-")[0].replace("🙏", "").replace("**", "").strip(),
                "nordic_runes": trickster_subroles.get("nordic_runes", "").split("-")[0].replace("🔮", "").replace("**", "").strip(),
                "dice_game": trickster_subroles.get("dice_game", "").split("-")[0].replace("🎲", "").replace("**", "").strip(),
                "ring": trickster_subroles.get("ring", "").split("-")[0].replace("👁️", "").replace("**", "").strip(),
            }
            
            # Return title if found, otherwise fallback to technical name
            if role_name in role_titles and role_titles[role_name]:
                return role_titles[role_name]
            elif role_name in subrole_titles and subrole_titles[role_name]:
                return subrole_titles[role_name]
    except Exception:
        pass  # Silently fall back to technical name if anything fails
    
    # Fallback to technical name
    return role_name


def _get_active_roles_section() -> str:
    roles = (AGENT_CFG or {}).get("roles", {})
    section_cfg = PERSONALITY.get("active_roles_section", {})
    role_sections = PERSONALITY.get("roles", {})

    if not isinstance(role_sections, dict):
        role_sections = {}
    if not isinstance(section_cfg, dict):
        section_cfg = {}

    section_label = str(section_cfg.get("label") or "[ACTIVE ROLES IN THE SERVER]").strip()
    empty_message = str(section_cfg.get("empty") or "- No active role duties are configured right now.").strip()
    line_template = str(section_cfg.get("line_template") or "- {scope}: {duty}").strip()

    lines: list[str] = []
    for role_name, role_cfg in roles.items():
        if not isinstance(role_cfg, dict) or not role_cfg.get("enabled", False):
            continue

        role_prompt_cfg = role_sections.get(role_name, {})
        role_duty = _get_active_duty_text(role_prompt_cfg)
        if role_duty:
            role_display = _get_role_display_name(role_name)
            lines.append(line_template.format(scope=role_display, duty=role_duty))

        subroles = role_cfg.get("subroles", {})
        role_subroles_cfg = role_prompt_cfg.get("subroles", {}) if isinstance(role_prompt_cfg, dict) else {}
        if not isinstance(subroles, dict):
            continue
        if not isinstance(role_subroles_cfg, dict):
            role_subroles_cfg = {}

        for subrole_name, subrole_cfg in subroles.items():
            if not isinstance(subrole_cfg, dict) or not subrole_cfg.get("enabled", False):
                continue
            subrole_prompt_cfg = role_subroles_cfg.get(subrole_name, {})
            
            # Get server_id for subrole injection (ring needs it)
            # Note: We now use runtime context instead of server_id for database operations
            server_id = None
            
            subrole_duty = _get_active_duty_text(subrole_prompt_cfg, server_id, subrole_name)
            
            if subrole_duty:
                subrole_display = _get_role_display_name(subrole_name)
                lines.append(line_template.format(scope=f"{_get_role_display_name(role_name)}/{subrole_display}", duty=subrole_duty))

    if not lines:
        return f"{section_label}\n{empty_message}"
    return f"{section_label}\n" + "\n".join(lines)

def _load_active_tasks_system_additions() -> list[str]:
    global _roles_verified, _active_tasks_cache
    
    # If already verified, return cache
    if _roles_verified:
        return _active_tasks_cache

    is_role_process = os.getenv('ROLE_AGENT_PROCESS') == '1'
    
    roles = (AGENT_CFG or {}).get("roles", {})
    additions: list[str] = []
    
    if not is_role_process:
        logger.info("🎭 [ROLES] Verifying configured roles...")
    enabled_roles = []

    for role_name, role_cfg in roles.items():
        if not isinstance(role_cfg, dict):
            continue
        if not role_cfg.get("enabled", False):
            if not is_role_process:
                logger.info(f"   💤 [Role] '{role_name}' - disabled")
            continue

        enabled_roles.append(role_name)
        if not is_role_process:
            logger.info(f"   ✅ [Role] '{role_name}' - active (every {role_cfg.get('interval_hours', '?')}h)")

        # Skip subroles (beggar, ring) - they will be loaded from JSON
        if role_name in ["beggar", "ring"]:
            continue

        # Search for mission configuration directly in Python file
        script_path = role_cfg.get("script", "")
        if not script_path:
            # Skip roles without script (e.g., integrated roles like mc)
            if not is_role_process:
                logger.info(f"   📋 [ROL] '{role_name}' - integrated mode (no script)")
            continue
            
        role_script_path = os.path.join(_BASE_DIR, script_path)
        if not os.path.exists(role_script_path):
            if not is_role_process:
                logger.warning(f"   ⚠️ [Role] Script not found: {role_script_path}")
                logger.warning(f"   ⚠️ [ROL] Script not found: {role_script_path}")
            continue
        
        try:
            # Read file and extract MISSION_CONFIG with regex to avoid importing
            with open(role_script_path, encoding="utf-8") as f:
                content = f.read()
            
            # Search for MISSION_CONFIG in code
            import re
            mission_match = re.search(r'MISSION_CONFIG\s*=\s*{([^}]+)}', content, re.DOTALL)
            if mission_match:
                # Extract system_prompt_addition from dictionary (handle escaped quotes)
                addition_match = re.search(r'"system_prompt_addition"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', mission_match.group(1))
                if addition_match:
                    addition = addition_match.group(1).strip()
                    # Unescape quotes and backslashes
                    addition = addition.replace('\\"', '"').replace('\\\\', '\\')
                    if addition:
                        # Only inject beggar and ring subroles for gold/ring detection
                        # All other roles should not contaminate global conversations
                        if role_name in ["beggar", "ring"]:
                            additions.append(addition)
                            if not is_role_process:
                                logger.info(f"   📋 [ROL] '{role_name}' - mission loaded: {addition[:50]}...")
                        else:
                            if not is_role_process:
                                logger.info(f"   🔄 [ROL] '{role_name}' - contextual context (not global): {addition[:50]}...")
                        continue
            
            if not is_role_process:
                logger.warning(f"⚠️ No valid MISSION_CONFIG found in {role_name}")
        except Exception as e:
            if not is_role_process:
                logger.warning(f"⚠️ Could not load MISSION_CONFIG from {role_name}: {e}")
        
        # Process enabled subroles (except beggar and ring which are loaded from JSON)
        subroles = role_cfg.get("subroles", {})
        if isinstance(subroles, dict):
            for subrole_name, subrole_cfg in subroles.items():
                if not isinstance(subrole_cfg, dict):
                    continue
                if not subrole_cfg.get("enabled", False):
                    continue
                
                # Skip beggar and ring - loaded from JSON
                if subrole_name in ["beggar", "ring"]:
                    continue
                
                subrole_script_path = subrole_cfg.get("script", "")
                if not subrole_script_path:
                    continue
                
                full_subrole_path = os.path.join(_BASE_DIR, subrole_script_path)
                if not os.path.exists(full_subrole_path):
                    if not is_role_process:
                        logger.warning(f"   ⚠️ [Subrole] Script not found: {full_subrole_path}")
                    continue
                
                try:
                    with open(full_subrole_path, encoding="utf-8") as f:
                        subrole_content = f.read()
                    
                    import re
                    subrole_mission_match = re.search(r'MISSION_CONFIG\s*=\s*{([^}]+)}', subrole_content, re.DOTALL)
                    if subrole_mission_match:
                        addition_match = re.search(r'"system_prompt_addition"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', subrole_mission_match.group(1))
                        if addition_match:
                            addition = addition_match.group(1).strip()
                            addition = addition.replace('\\"', '"').replace('\\\\', '\\')
                            if addition:
                                if not is_role_process:
                                    logger.info(f"   🔄 [Subrole] '{subrole_name}' - contextual context (not global): {addition[:50]}...")
                except Exception as e:
                    if not is_role_process:
                        logger.warning(f"⚠️ Could not load MISSION_CONFIG from subrole {subrole_name}: {e}")

    # Load beggar and ring prompts from JSON
    json_additions = _load_subrole_prompts_from_json()
    additions.extend(json_additions)

    if not is_role_process:
        if enabled_roles:
            logger.info(f"🎭 [ROLES] Total active: {len(enabled_roles)} - {', '.join(enabled_roles)}")
        else:
            logger.info("🎭 [ROLES] No active roles configured")
    
    # Mark as verified and save cache
    _roles_verified = True
    _active_tasks_cache = additions
    
    return additions

#Deprecated
#def _load_subrole_prompts_from_json() -> list[str]:
    """Load subrole prompts from prompts.json with fallback to Python files."""
    is_role_process = os.getenv('ROLE_AGENT_PROCESS') == '1'
    
    # Get subrole prompts from personality JSON
    subrole_prompts = PERSONALITY.get("roles", {}).get("trickster", {}).get("subroles", {})
    additions = []
    
    if not is_role_process:
        logger.info("🎭 [SUBROLES] Loading prompts from JSON...")
    
    # Only inject beggar and ring subroles for gold/ring detection
    for subrole_name in ["beggar", "ring"]:
        # Check if subrole is enabled in agent config
        roles_config = AGENT_CFG.get("roles", {})
        if not roles_config.get(subrole_name, {}).get("enabled", False):
            if not is_role_process:
                logger.info(f"   💤 [Subrole] '{subrole_name}' - disabled")
            continue
        
        # Try to load from JSON first
        json_prompt = subrole_prompts.get(subrole_name)
        if json_prompt:
            additions.append(json_prompt)
            if not is_role_process:
                logger.info(f"   📋 [Subrole] '{subrole_name}' - mission loaded from JSON: {json_prompt[:50]}...")
            
            # Add beggar reasons after the beggar prompt
            if subrole_name == "beggar":
                beggar_reasons = PERSONALITY.get("roles", {}).get("trickster", {}).get("subroles", {}).get("beggar", {}).get("reasons", [])
                if beggar_reasons:
                    reasons_text = "CURRENT PROJECTS (razones para pedir oro): " + " | ".join(beggar_reasons)
                    additions.append(reasons_text)
                    if not is_role_process:
                        logger.info(f"   💰 [Beggar] Added {len(beggar_reasons)} reasons: {reasons_text[:60]}...")
        else:
            # Fallback to Python file
            if not is_role_process:
                logger.warning(f"   ⚠️ [Subrole] '{subrole_name}' not found in JSON, trying Python fallback...")
            
            try:
                # Get script path from config
                subrole_script_path = roles_config.get(subrole_name, {}).get("script", "")
                if not subrole_script_path:
                    if not is_role_process:
                        logger.warning(f"   ⚠️ [Subrole] '{subrole_name}' - no script path in config")
                    continue
                
                full_subrole_path = os.path.join(_BASE_DIR, subrole_script_path)
                if not os.path.exists(full_subrole_path):
                    if not is_role_process:
                        logger.warning(f"   ⚠️ [Subrole] Script not found: {full_subrole_path}")
                    continue
                
                # Load from Python file
                with open(full_subrole_path, encoding="utf-8") as f:
                    subrole_content = f.read()
                
                import re
                subrole_mission_match = re.search(r'MISSION_CONFIG\s*=\s*{([^}]+)}', subrole_content, re.DOTALL)
                if subrole_mission_match:
                    addition_match = re.search(r'"system_prompt_addition"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', subrole_mission_match.group(1))
                    if addition_match:
                        addition = addition_match.group(1).strip()
                        addition = addition.replace('\\"', '"').replace('\\\\', '\\')
                        if addition:
                            additions.append(addition)
                            if not is_role_process:
                                logger.info(f"   📋 [Subrole] '{subrole_name}' - mission loaded from Python fallback: {addition[:50]}...")
                            
                            # Add beggar reasons after the beggar prompt even in fallback
                            if subrole_name == "beggar":
                                beggar_reasons = PERSONALITY.get("roles", {}).get("trickster", {}).get("subroles", {}).get("beggar", {}).get("reasons", [])
                                if beggar_reasons:
                                    reasons_text = "CURRENT PROJECTS (razones para pedir oro): " + " | ".join(beggar_reasons)
                                    additions.append(reasons_text)
                                    if not is_role_process:
                                        logger.info(f"   💰 [Beggar] Added {len(beggar_reasons)} reasons from JSON: {reasons_text[:60]}...")
                        else:
                            if not is_role_process:
                                logger.warning(f"   ⚠️ [Subrole] '{subrole_name}' - no system_prompt_addition found")
                    else:
                        if not is_role_process:
                            logger.warning(f"   ⚠️ [Subrole] '{subrole_name}' - no system_prompt_addition in MISSION_CONFIG")
                else:
                    if not is_role_process:
                        logger.warning(f"   ⚠️ [Subrole] '{subrole_name}' - no MISSION_CONFIG found")
                        
            except Exception as e:
                if not is_role_process:
                    logger.warning(f"   ⚠️ [Subrole] '{subrole_name}' - fallback failed: {e}")
    
    return additions

def increment_usage():
    return runtime_increment_usage(PERSONALITY.get("name", "unknown"))


def _fallback_response():
    """Emergency response defined in personality."""
    fallbacks = PERSONALITY.get("emergency_fallbacks", [])
    if fallbacks:
        return random.choice(fallbacks)
    return PERSONALITY.get("emergency_fallback", "...")


def _get_readme_response_rules_lines() -> list[str]:
    template = _get_user_prompt_template()
    rules = template.get("readme_response_rules", [])
    if isinstance(rules, list) and rules:
        return [str(rule).strip() for rule in rules if str(rule).strip()]
    return [
        "1. OBJECTIVE: Answer the user's question using the provided documentation.",
        "2. COMMANDS: Do not reply only with README. Explain the relevant command directly.",
        "3. LENGTH: 3-7 short useful sentences.",
        "4. CONTENT: Explain purpose, usage, and a small example when helpful.",
        "5. STYLE: Stay in character and be clear."
    ]


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _get_user_prompt_template() -> dict:
    template = PERSONALITY.get("user_prompt_template", {})
    return template if isinstance(template, dict) else {}


def _get_response_rules_lines() -> list[str]:
    template = _get_user_prompt_template()
    rules = template.get("response_rules", [])
    if isinstance(rules, list) and rules:
        return [str(rule).strip() for rule in rules if str(rule).strip()]
    return [
        "1. LENGTH: 1-3 sentences (25-150 characters). Be brief and direct.",
        "2. COMMANDS: If human asks for help with commands or functions, respond ONLY with: README",
        "3. GRAMMAR: No accent marks.",
        "4. Don't end sentences with single words like 'the', 'a', in'.",
    ]

#Deprecated
#def _get_mission_injection(role_context: str, mission_prompt_key: str | None, user_content: str) -> str:
    if not mission_prompt_key:
        logger.info(f"🎯 [MISSION] No mission_prompt_key provided")
        return ""
    
    logger.info(f"🎯 [MISSION] Available keys in PERSONALITY: {list(PERSONALITY.keys())}")
    
    # Try direct lookup first
    cfg = PERSONALITY.get(mission_prompt_key, {})
    logger.info(f"🎯 [MISSION] Direct lookup for {mission_prompt_key}: {bool(cfg)}")
    
    # If not found, try roles.trickster.subroles structure
    if not cfg and 'roles' in PERSONALITY:
        role_system = PERSONALITY['roles']['trickster']['subroles']
        logger.info(f"🎯 [MISSION] Available trickster subroles: {list(role_system.keys())}")
        if 'subroles' in role_system:
            subroles = role_system['subroles']
            logger.info(f"🎯 [MISSION] Available subroles: {list(subroles.keys())}")
            cfg = subroles.get(mission_prompt_key, {})
            logger.info(f"🎯 [MISSION] Found in subroles: {bool(cfg)}")
    
    # If still not found, try prompts section
    if not cfg and 'prompts' in PERSONALITY:
        prompts = PERSONALITY['prompts']
        logger.info(f"🎯 [MISSION] Available prompts: {list(prompts.keys())}")
        cfg = prompts.get(mission_prompt_key, {})
        logger.info(f"🎯 [MISSION] Found in prompts: {bool(cfg)}")
    
    logger.info(f"🎯 [MISSION] Looking for mission key: {mission_prompt_key}")
    logger.info(f"🎯 [MISSION] Found config: {bool(cfg)}")
    if not isinstance(cfg, dict):
        logger.warning(f"🎯 [MISSION] Config is not a dict: {type(cfg)}")
        return ""
    
    # Check for active_duty field first and keep mission_active as fallback
    active_duty = str(cfg.get("active_duty") or cfg.get("mission_active") or "").strip()
    if active_duty:
        logger.info(f"🎯 [MISSION] Using active duty field: {active_duty[:100]}..." if len(active_duty) > 100 else f"🎯 [MISSION] Active duty: {active_duty}")
        return active_duty
    
    # Check for task field (used in prompts section)
    task = cfg.get("task", "")
    if task:
        logger.info(f"🎯 [MISSION] Using task field: {task[:100]}..." if len(task) > 100 else f"🎯 [MISSION] Task: {task}")
        return task
    
    # Fall back to instructions-based system
    instructions = cfg.get("instructions", [])
    if not isinstance(instructions, list):
        instructions = []
    processed = []
    for inst in instructions:
        line = str(inst)
        line = line.replace("{name}", str(role_context or "").strip())
        line = line.replace("{user_message}", str(user_content or "").strip())
        processed.append(line.strip())
    closing = str(cfg.get("closing", "")).strip()
    if closing:
        processed.append(closing)
    result = "\n".join([line for line in processed if line])
    logger.info(f"🎯 [MISSION] Using instructions-based system, final injection length: {len(result)} chars")
    return result


from agent_mind import (
    call_llm,
    generate_daily_memory_summary,
    generate_recent_memory_summary,
    generate_user_relationship_memory_summary,
    refresh_due_recent_memories,
    refresh_due_relationship_memories,
)


def _build_system_prompt(personalidad: dict) -> str:
    """Assemble system prompt from structured personality sections."""
    template = personalidad.get("system_prompt_template", {})
    if isinstance(template, dict) and template:
        sections = []
        identity_title = str(template.get("identity_title", "")).strip()
        identity_body = template.get("identity_body", [])
        style_title = str(template.get("style_title", "")).strip()
        style_body = template.get("style_body", [])
        examples_title = str(template.get("examples_title", "")).strip()
        examples_body = template.get("examples_body", [])

        if identity_title and isinstance(identity_body, list) and identity_body:
            identity_text = "\n".join([str(line).strip() for line in identity_body if str(line).strip()])
            sections.append(f"## {identity_title}\n{identity_text}")
        if style_title and isinstance(style_body, list) and style_body:
            style_text = "\n".join([str(line).strip() for line in style_body if str(line).strip()])
            sections.append(f"## {style_title}\n{style_text}")
        if examples_title and isinstance(examples_body, list) and examples_body:
            examples_text = "\n".join([str(line).strip() for line in examples_body if str(line).strip()])
            sections.append(f"## {examples_title}\n{examples_text}")
        active_roles_section = _get_active_roles_section()
        if active_roles_section:
            sections.append(active_roles_section)
        if sections:
            return "\n\n".join(sections)

# ============================================================================
# SUBROLE INTERNAL TASKS SYSTEM
# ============================================================================

import random
from datetime import datetime, timedelta

_subrole_task_cache = {}

def get_active_subroles():
    """Get active subroles from personality prompts.json."""
    try:
        # Use same path logic as _cargar_personalidad
        personality_rel = AGENT_CFG.get("personality", "personalities/default.json")
        personality_path = os.path.join(_BASE_DIR, personality_rel)
        personality_dir = os.path.dirname(personality_path)
        prompts_path = os.path.join(personality_dir, "prompts.json")
        
        with open(prompts_path, 'r', encoding='utf-8') as f:
            prompts_data = json.load(f)
        
        subroles = prompts_data.get("roles", {}).get("trickster", {}).get("subroles", {})
        active_subroles = {}
        
        for subrole_name, subrole_config in subroles.items():
            if "internal_task" in subrole_config:
                active_subroles[subrole_name] = subrole_config
                
        return active_subroles
    except Exception as e:
        logger.error(f"Error loading subroles: {e}")
        return {}

def should_execute_subrole_task(subrole_name, frequency_hours):
    """Check if subrole task should execute based on frequency."""
    global _subrole_task_cache
    
    now = datetime.now()
    last_run = _subrole_task_cache.get(subrole_name)
    
    if not last_run or (now - last_run) >= timedelta(hours=frequency_hours):
        _subrole_task_cache[subrole_name] = now
        return True
    
    return False

async def execute_subrole_internal_task(subrole_name, subrole_config, bot_instance=None):
    """Execute internal task for a subrole."""
    try:
        # Get frequency from agent_config.json instead of prompts.json
        frequency = _get_subrole_frequency_from_config(subrole_name)
        
        if not should_execute_subrole_task(subrole_name, frequency):
            return
        
        logger.info(f"🎭 [SUBROLE] Executing internal task: {subrole_name} (frequency: {frequency}h)")
        
        # Get system prompt and base mission prompt
        system_instruction = _build_system_prompt(PERSONALITY)
        
        # Try to get server_id for ring subrole to replace accused user placeholder
        # Note: We now use runtime context instead of server_id for database operations
        server_id = None
        
        mission_prompt = _get_active_duty_text(subrole_config, server_id, subrole_name)
        
        # Build the complete prompt with task and reasons at the end
        base_task_prompt = subrole_config.get("internal_task", {}).get("prompt", "")
        
        # Add specific reasons/methods at the end
        task_details = ""
        if subrole_name == "beggar":
            # Use the new beggar task system
            from roles.trickster.subroles.beggar.beggar_task import execute_beggar_task
            
            # Execute the beggar task with runtime context
            try:
                success = await execute_beggar_task(bot_instance=bot_instance)
                if success:
                    logger.info(f"🎭 [BEGGAR] Task executed successfully")
                else:
                    logger.warning(f"🎭 [BEGGAR] Task execution failed")
            except Exception as e:
                logger.error(f"🎭 [BEGGAR] Error in task execution: {e}")
            
            # Don't generate regular response for beggar, we handle it in the task
            return
        elif subrole_name == "ring":
            # For ring, we need to execute an actual accusation
            # Get ring state to find target and check frequency
            from roles.trickster.subroles.ring.ring_discord import _get_ring_state, execute_ring_accusation, _can_make_accusation
            from roles.trickster.subroles.ring.ring_db import RingDB
            
            # Try to get a server context (this is tricky in subprocess mode)
            # For now, we'll use a generic approach - in the future this should be server-aware
            try:
                # Get active server name from runtime
                from agent_runtime import get_active_server_name
                from agent_db import AgentDatabase
                
                server_name = get_active_server_name()
                if server_name:
                    db = AgentDatabase(server_name)
                    
                    # Check if we can make an accusation based on frequency
                    # Note: We pass server_name for now but should migrate to runtime context
                    if not _can_make_accusation(server_name):
                        logger.info(f"🎭 [RING] Frequency check passed - time for next accusation")
                        
                        # Get recent interactions to find a target
                        import sqlite3
                        try:
                            conn = sqlite3.connect(db.db_path)
                            cursor = conn.cursor()
                            cursor.execute('''
                                SELECT usuario_id, usuario_nombre, servidor_id 
                                FROM interacciones 
                                WHERE servidor_id IS NOT NULL 
                                AND fecha > datetime('now', '-24 hours')
                                ORDER BY fecha DESC 
                                LIMIT 5
                            ''')
                            recent_users = cursor.fetchall()
                            
                            if recent_users:
                                # Select a random recent user as target
                                import random
                                target_user_id, target_user_name, server_id = random.choice(recent_users)
                                
                                # Get the original accuser from database
                                accuser_name = "a user"  # default fallback
                                try:
                                    ring_db = RingDB(server_name)
                                    accusations = ring_db.get_accusations(limit=1)
                                    logger.info(f"🔍 [RING DEBUG] Retrieved {len(accusations)} accusations")
                                    if accusations and len(accusations) > 0:
                                        latest_accusation = accusations[0]
                                        accuser_id = latest_accusation.get('accuser_id')
                                        logger.info(f"🔍 [RING DEBUG] accuser_id: {accuser_id} (type: {type(accuser_id)})")
                                        if accuser_id:
                                            # Try to get user name from recent interactions
                                            cursor.execute('''
                                                SELECT usuario_nombre FROM interacciones 
                                                WHERE usuario_id = ? AND servidor_id = ?
                                                ORDER BY fecha DESC LIMIT 1
                                            ''', (accuser_id, server_id))
                                            result = cursor.fetchone()
                                            logger.info(f"🔍 [RING DEBUG] Query result: {result}")
                                            if result:
                                                accuser_name = result[0]
                                                logger.info(f"🔍 [RING DEBUG] Found accuser_name: {accuser_name}")
                                            else:
                                                # If not found in interactions, maybe accuser_id is already a name
                                                if isinstance(accuser_id, str) and not accuser_id.isdigit():
                                                    accuser_name = accuser_id
                                                    logger.info(f"🔍 [RING DEBUG] Using accuser_id as name: {accuser_name}")
                                except Exception as e:
                                    logger.warning(f"Could not get original accuser: {e}")
                                
                                # Execute ring accusation
                                accusation = execute_ring_accusation(None, target_user_id, target_user_name, user_name=accuser_name)
                                logger.info(f"🎭 [RING] Accusation generated for {target_user_name}: {accusation[:100]}...")
                                
                                # Try to send the accusation to a channel
                                try:
                                    # Get a channel where we can send the accusation
                                    # Look for recent interactions to find an active channel
                                    cursor.execute('''
                                        SELECT canal_id, COUNT(*) as message_count
                                        FROM interacciones 
                                        WHERE servidor_id = ? 
                                        AND fecha > datetime('now', '-24 hours')
                                        AND canal_id IS NOT NULL
                                        GROUP BY canal_id
                                        ORDER BY message_count DESC
                                        LIMIT 1
                                    ''', (server_id,))
                                    channel_result = cursor.fetchone()
                                    
                                    if channel_result:
                                        channel_id = channel_result[0]
                                        # Import the bot to send the message
                                        from discord_bot.agent_discord import get_bot_instance
                                        bot = get_bot_instance()
                                        
                                        if bot:
                                            # Send accusation via DM only (not public channel)
                                            try:
                                                target_user = bot.get_user(int(target_user_id))
                                                if target_user:
                                                    await target_user.send(f"👁️ **RING ACCUSATION**\n{accusation}")
                                                    logger.info(f"🎭 [RING] Accusation sent via DM to {target_user_name}")
                                                else:
                                                    logger.warning(f"🎭 [RING] Could not find target user {target_user_id} for DM")
                                            except Exception as dm_error:
                                                logger.error(f"🎭 [RING] Error sending DM: {dm_error}")
                                                # Fallback: try to find a mutual server and send via system channel
                                                channel = bot.get_channel(int(channel_id))
                                                if channel:
                                                    await channel.send(f"⚠️ **RING INVESTIGATION** (DM failed)\n{accusation}")
                                                    logger.info(f"🎭 [RING] Accusation sent to channel {channel_id} as fallback")
                                        else:
                                            logger.warning(f"🎭 [RING] Bot instance not available")
                                    else:
                                        logger.warning(f"🎭 [RING] No active channel found for server {server_id}")
                                except Exception as send_error:
                                    logger.error(f"🎭 [RING] Error sending accusation: {send_error}")
                                    
                            else:
                                logger.warning(f"🎭 [RING] No recent users found for accusation")
                        except Exception as e:
                            logger.error(f"🎭 [RING] Error finding target: {e}")
                    else:
                        logger.info(f"🎭 [RING] Frequency check failed - not time for next accusation yet")
                else:
                    logger.warning(f"🎭 [RING] No active server found")
                    
            except Exception as e:
                logger.error(f"🎭 [RING] Error in ring execution: {e}")
                
            # Also generate the regular response as fallback
            methods = subrole_config.get("internal_task", {}).get("investigation_methods", [])
            if methods:
                selected_method = random.choice(methods)
                task_details = f"\n\nINVESTIGATION METHOD: {selected_method}"
        
        # Construct complete prompt: mission + task + details
        complete_prompt = f"{mission_prompt}\n\n{base_task_prompt}{task_details}\n\nRespond only with what {_bot_display_name} would say, without additional explanations."
        
        # Call LLM
        response = call_llm(
            system_instruction=system_instruction,
            prompt=complete_prompt,
            async_mode=True,
            call_type="subrole_async",
            critical=False
        )
        
        if response and len(response.strip()) > 5:
            # For now, just log the response - we'll integrate with Discord later
            logger.info(f"🎭 [{subrole_name.upper()}] Generated message: {response[:100]}...")
        else:
            logger.warning(f"🎭 [{subrole_name.upper()}] Empty or short response: {response}")
        
    except Exception as e:
        logger.error(f"🎭 [SUBROLE] Error executing task {subrole_name}: {e}")
