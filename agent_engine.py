import os
import json
import random
from datetime import datetime, timedelta
from agent_logging import get_logger
from postprocessor import postprocess_response, is_blocked_response
from agent_db import get_active_server_name, get_global_db
from prompts_logger import log_system_prompt, log_agent_response, log_final_llm_prompt
from agent_runtime import increment_usage as runtime_increment_usage

logger = get_logger('agent_engine')

# --- PERSONALITY LOADING ---
_BASE_DIR = os.path.dirname(__file__)
_AGENT_CONFIG_PATH = os.path.join(_BASE_DIR, "agent_config.json")

with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
    AGENT_CFG = json.load(f)

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
        
        return merged_personality
    else:
        # Load single file (legacy structure)
        with open(personality_path, encoding="utf-8") as f:
            return json.load(f)

PERSONALITY = _cargar_personalidad()
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

def _load_subrole_prompts_from_json() -> list[str]:
    """Load subrole prompts from prompts.json with fallback to Python files."""
    is_role_process = os.getenv('ROLE_AGENT_PROCESS') == '1'
    
    # Get subrole prompts from personality JSON
    subrole_prompts = PERSONALITY.get("role_system_prompts", {}).get("subroles", {})
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
                beggar_reasons = PERSONALITY.get("role_system_prompts", {}).get("beggar_reasons", [])
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
                                beggar_reasons = PERSONALITY.get("role_system_prompts", {}).get("beggar_reasons", [])
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
        "3. LENGTH: 2-5 short useful sentences.",
        "4. CONTENT: Explain purpose, usage, and a small example when helpful.",
        "5. STYLE: Stay in character and be clear."
    ]


def _get_mission_injection(role_context: str, mission_prompt_key: str | None, user_content: str) -> str:
    return None


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
        "1. LONGITUD: 1-3 frases (25-150 caracteres). Se breve y violento.",
        "2. COMANDOS: Si el humano pide ayuda con coomando o funciones, responde UNICAMENTE: README",
        "3. GRAMATICA: Sin tildes. Termina afirmaciones con '!' y preguntas con '?'.",
        '4. No termines frases con palabras sueltas como "ke", "a", "de".',
    ]


def _get_mission_injection(role_context: str, mission_prompt_key: str | None, user_content: str) -> str:
    if not mission_prompt_key:
        return ""
    cfg = PERSONALITY.get(mission_prompt_key, {})
    if not isinstance(cfg, dict):
        return ""
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
    return "\n".join([line for line in processed if line])


from agent_mind import (
    _build_prompt_context,
    _call_llm_async,
    _render_user_prompt,
    generate_daily_memory_summary,
    generate_recent_memory_summary,
    generate_user_relationship_memory_summary,
    refresh_due_relationship_memories,
    think,
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
        if sections:
            return "\n\n".join(sections)

    sections = []

    section_titles = personalidad.get("system_prompt_section_titles", {})
    if not isinstance(section_titles, dict):
        section_titles = {}

    title_absolute_identity = section_titles.get("absolute_identity", "ABSOLUTE IDENTITY (NON-NEGOTIABLE)")
    title_character = section_titles.get("character", "CHARACTER")
    title_golden_rules = section_titles.get("golden_rules", "GOLDEN RULES (NEVER BREAK)")
    title_orca_orthography = section_titles.get("orca_orthography", "ORCA ORTHOGRAPHY")
    title_style = section_titles.get("style", "STYLE")
    title_examples = section_titles.get("examples", "EXAMPLES (learn from these)")

    # 1. ABSOLUTE IDENTITY (never_break) — always first
    never_break = personalidad.get("never_break", [])
    if never_break:
        never_break_text = "\n".join([f"- {r}" for r in never_break])
        sections.append(f"## {title_absolute_identity}\n{never_break_text}")

    # 2. IDENTIDAD del personaje
    identity = personalidad.get("identity", "")
    if identity:
        sections.append(f"## {title_character}\n{identity}")

    # 3. GOLDEN RULES
    # Prefer plain-text rules if provided by personality; fallback to legacy format_rules.
    golden_rules = personalidad.get("golden_rules")
    reglas = []
    if isinstance(golden_rules, list):
        reglas = [str(r).strip() for r in golden_rules if str(r).strip()]
    elif isinstance(golden_rules, str) and golden_rules.strip():
        reglas = [line.strip() for line in golden_rules.splitlines() if line.strip()]

    if not reglas:
        # Legacy format_rules (kept for other personalities)
        format_rules = personalidad.get("format_rules", {})
        if isinstance(format_rules, dict) and format_rules:
            if format_rules.get("length"):
                reglas.append(f"ALWAYS write {format_rules['length']}")
            if format_rules.get("no_tildes"):
                reglas.append("NEVER use tildes (a e i o u, without accent)")
            if format_rules.get("no_dangling"):
                reglas.append("NEVER end in single words: \"ke\", \"a\", \"de\", \"por\", \"para\"")
            if format_rules.get("end_punctuation"):
                reglas.append(f"{format_rules['end_punctuation']}")

    if reglas:
        reglas_text = "\n".join([f"- {r}" for r in reglas])
        sections.append(f"## {title_golden_rules}\n" + reglas_text)

    # 4. ORCA ORTHOGRAPHY
    orthography = personalidad.get("orthography", [])
    if orthography:
        ortho_text = "\n".join(orthography)
        sections.append(f"## {title_orca_orthography}\n{ortho_text}")

    # 5. STYLE
    style = personalidad.get("style", [])
    if style:
        style_text = "\n".join([f"- {s}" for s in style])
        sections.append(f"## {title_style}\n{style_text}")

    # 6. EXAMPLES
    examples = personalidad.get("examples", [])
    if examples:
        examples_text = "\n".join([f'"{e}"' for e in examples])
        sections.append(f"## {title_examples}\n{examples_text}")

    # If there are structured sections, use them; if not, fallback to old system_prompt
    if sections:
        return "\n\n".join(sections)

    system_prompt = personalidad.get("system_prompt", "")
    if isinstance(system_prompt, list):
        system_prompt = "\n".join([str(x) for x in system_prompt])
    if never_break:
        never_break_text = "\n".join([f"- {r}" for r in never_break])
        return f"## {title_absolute_identity}\n{never_break_text}\n\n{system_prompt}"
    return system_prompt


def build_prompt(
    role_context,
    user_content="",
    history_list=None,
    max_interactions=5,
    is_public=False,
    server=None,
    mission_prompt_key: str | None = None,
    user_id=None,
    user_name=None,
    interaction_type="chat",
):
    """Build and return `(system_instruction, prompt_final)` without calling APIs."""
    public_suffix = PERSONALITY.get("public_context_suffix", "")
    system_instruction = _build_system_prompt(PERSONALITY)
    if is_public and public_suffix:
        system_instruction = f"{system_instruction}\n\nCONTEXT: {public_suffix}"
    prompt_context = _build_prompt_context(
        role_context=role_context,
        user_content=user_content,
        is_public=is_public,
        server=server,
        mission_prompt_key=mission_prompt_key,
        user_id=user_id,
        user_name=user_name,
        interaction_type=interaction_type,
    )
    prompt_final = _render_user_prompt(prompt_context)

    return system_instruction, prompt_final


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
        
        subroles = prompts_data.get("role_system_prompts", {}).get("subroles", {})
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
        mission_prompt = subrole_config.get("mission_active", "")
        
        # Build the complete prompt with task and reasons at the end
        base_task_prompt = subrole_config.get("internal_task", {}).get("prompt", "")
        
        # Add specific reasons/methods at the end
        task_details = ""
        if subrole_name == "beggar":
            reasons = subrole_config.get("internal_task", {}).get("reasons", [])
            if reasons:
                selected_reason = random.choice(reasons)
                task_details = f"\n\nRAZÓN ESPECÍFICA: {selected_reason}"
        elif subrole_name == "ring":
            methods = subrole_config.get("internal_task", {}).get("investigation_methods", [])
            if methods:
                selected_method = random.choice(methods)
                task_details = f"\n\nMÉTODO DE INVESTIGACIÓN: {selected_method}"
        
        # Construct complete prompt: mission + task + details
        complete_prompt = f"{mission_prompt}\n\n{base_task_prompt}{task_details}\n\nResponde únicamente con lo que diría Putre, sin explicaciones adicionales."
        
        # Call LLM
        response = await _call_llm_async(system_instruction, complete_prompt)
        
        if response and len(response.strip()) > 5:
            # For now, just log the response - we'll integrate with Discord later
            logger.info(f"🎭 [{subrole_name.upper()}] Generated message: {response[:100]}...")
        else:
            logger.warning(f"🎭 [{subrole_name.upper()}] Empty or short response: {response}")
        
    except Exception as e:
        logger.error(f"🎭 [SUBROLE] Error executing task {subrole_name}: {e}")
