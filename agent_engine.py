import os
import json
import random
from datetime import date
from google import genai
from google.genai import types
from groq import Groq
from dotenv import load_dotenv
from agent_logging import get_logger
from postprocessor import postprocess_response, consolidate_context, is_blocked_response
from agent_db import get_active_server_name

load_dotenv()
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

def _cargar_personalidad() -> dict:
    with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
        agent_cfg = json.load(f)
    personality_rel = agent_cfg.get("personality", "personalities/default.json")
    personality_path = os.path.join(_BASE_DIR, personality_rel)
    
    # Check if personality is a directory (new split structure)
    personality_dir = os.path.dirname(personality_path)  # Get directory containing the personality file
    if os.path.exists(os.path.join(personality_dir, 'personality.json')) and \
       os.path.exists(os.path.join(personality_dir, 'prompts.json')) and \
       os.path.exists(os.path.join(personality_dir, 'messages.json')):
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
        
        # Load messages.json
        messages_file = os.path.join(personality_dir, 'messages.json')
        if os.path.exists(messages_file):
            with open(messages_file, encoding="utf-8") as f:
                messages_data = json.load(f)
                # Merge messages with existing structure
                for key, value in messages_data.items():
                    if key in merged_personality:
                        if isinstance(merged_personality[key], dict) and isinstance(value, dict):
                            merged_personality[key].update(value)
                        else:
                            merged_personality[key] = value
                    else:
                        merged_personality[key] = value
        
        return merged_personality
    else:
        # Load single file (legacy structure)
        with open(personality_path, encoding="utf-8") as f:
            return json.load(f)

PERSONALIDAD = _cargar_personalidad()
# Only show personality log if not in role subprocess
if os.getenv('ROLE_AGENT_PROCESS') != '1':
    logger.info(f"🎭 [PERSONALITY] Loaded: {PERSONALIDAD.get('name', 'Unknown')} from {AGENT_CFG.get('personality', 'Unknown')}")


def get_discord_token():
    """Get Discord token specific for active personality."""
    personality_name = PERSONALIDAD.get("name", "").upper()
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
    subrole_prompts = PERSONALIDAD.get("role_system_prompts", {}).get("subroles", {})
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
                beggar_reasons = PERSONALIDAD.get("role_system_prompts", {}).get("beggar_reasons", [])
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
                                beggar_reasons = PERSONALIDAD.get("role_system_prompts", {}).get("beggar_reasons", [])
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

# --- CLIENTS AND PATHS ---
client_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

def _get_fatiga_path():
    """Get fatigue file path according to server and personality."""
    # If no active server, use temporary path until connected
    server_name = get_active_server_name()
    if not server_name:
        # Temporary path until bot connects to a server
        return os.path.join(_BASE_DIR, "fatiga_temp.json")
    
    # Sanitize server name
    server_name = server_name.lower().replace(' ', '_').replace('-', '_')
    server_name = ''.join(c for c in server_name if c.isalnum() or c == '_')
    
    personality_name = PERSONALIDAD.get("name", "unknown").lower()
    
    fatiga_dir = os.path.join(_BASE_DIR, "fatiga", server_name)
    
    # Create directory if it doesn't exist
    os.makedirs(fatiga_dir, exist_ok=True)
    
    return os.path.join(fatiga_dir, f"{personality_name}.json")

# If AGENT_SIMULACION=1, counter is not persisted (for simulations)
SIMULACION = os.getenv("AGENT_SIMULATION", os.getenv("ROLE_AGENT_SIMULATION", "")).strip() in ("1", "true", "True", "yes")

logger.info(f"🔧 [CONFIG] Simulation mode: {'ENABLED' if SIMULACION else 'DISABLED'}")
logger.info(f"🔧 [CONFIG] Usage counter (path resolved at runtime)")
logger.info(f"🤖 [IA] Cliente Groq inicializado: {'✅' if os.getenv('GROQ_API_KEY') else '❌'}")
logger.info(f"🤖 [IA] Cliente Gemini: {'✅' if os.getenv('GEMINI_API_KEY') else '❌'}")


def obtener_uso_diario():
    if SIMULACION:
        return 0
    path_contador = _get_fatiga_path()
    hoy = str(date.today())
    if not os.path.exists(path_contador):
        return 0
    try:
        if os.path.getsize(path_contador) == 0:
            return 0
        with open(path_contador, 'r') as f:
            file_content = f.read().strip()
            if not file_content:
                return 0
            data = json.loads(file_content)
            return data.get("peticiones", 0) if data.get("ultima_fecha") == hoy else 0
    except (json.JSONDecodeError, ValueError, KeyError, OSError, IOError) as e:
        print(f"⚠️ Error leyendo {path_contador}: {e}. Reiniciando contador.")
        try:
            if os.path.exists(path_contador):
                os.remove(path_contador)
        except Exception:
            pass
        return 0


def increment_usage():
    if SIMULACION:
        return 1
    path_contador = _get_fatiga_path()
    uso = obtener_uso_diario() + 1
    try:
        with open(path_contador, 'w') as f:
            json.dump({"peticiones": uso, "ultima_fecha": str(date.today())}, f)
    except (OSError, IOError) as e:
        print(f"⚠️ Error writing {path_contador}: {e}")
    return uso


def _fallback_response():
    """Emergency response defined in personality."""
    fallbacks = PERSONALIDAD.get("emergency_fallbacks", [])
    if fallbacks:
        return random.choice(fallbacks)
    return PERSONALIDAD.get("emergency_fallback", "...")


def think(role_context, user_content="", history_list=[], is_public=False, logger=None):
    """
    Unified engine with gemini-3-flash-preview and Fallback to Groq.
    Loads personality from active JSON file.
    """
    import time
    start_time = time.time()
    
    # Use provided logger or default global logger
    if logger is None:
        from agent_logging import get_logger
        logger = get_logger('agent_engine')
    
    current_usage = increment_usage()
    logger.info(f"🚀 [THINK] Iniciando proceso - Uso diario: {current_usage}/20")

    content = (user_content or "").strip()
    is_mission = not bool(content)
    system_instruction, prompt_final = build_prompt(
        role_context, content, history_list, is_public=is_public
    )
    
    prep_time = time.time()
    logger.info(f"⚡ [THINK] Preparation completed in {(prep_time - start_time):.2f}s")
    
    logger.info(f"🧠 [KRONK] RESPONSE GENERATION - Daily usage: {current_usage}/20")
    logger.info(f"📝 Context: {len(system_instruction)} chars system | {len(prompt_final)} chars prompt")
    logger.info(f"💬 History: {len(history_list)} interactions | Public: {is_public}")
    logger.info(f"🎯 Type: {'MISSION' if is_mission else 'CHAT'}")
    logger.info(f"🎯 Role: {role_context[:80]}..." if len(role_context) > 80 else f"🎯 Role: {role_context}")
    if is_mission:
        logger.info(f"📋 Full prompt: {prompt_final[:200]}..." if len(prompt_final) > 200 else f"📋 Full prompt: {prompt_final}")
    logger.info("=" * 60)

    # 1. Try with Gemini. In simulation use only Groq.
    if not SIMULACION and current_usage <= 20:
        try:
            gemini_start = time.time()
            logger.info("🤖 [GEMINI] Starting call to gemini-3-flash-preview")
            logger.info(f"   └─ Temp: {0.9 if is_mission else 0.95} | Max tokens: 1024")
            logger.info("   └─ Top-p: 0.95")

            client_gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            
            # Add more aggressive timeout for Gemini using threading
            import threading
            import queue
            
            result_queue = queue.Queue()
            exception_queue = queue.Queue()
            
            def call_gemini():
                try:
                    thread_start = time.time()
                    logger.info(f"🧵 [GEMINI] Thread started")
                    res = client_gemini.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=prompt_final,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.9 if is_mission else 0.95,  # Increased for variability
                            max_output_tokens=1024,
                            top_p=0.95,  # Increased for creativity
                            safety_settings=[types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE")]
                        )
                    )
                    thread_end = time.time()
                    logger.info(f"🧵 [GEMINI] Thread completed in {(thread_end - thread_start):.2f}s")
                    result_queue.put(res)
                except Exception as e:
                    exception_queue.put(e)
            
            # Start call in separate thread with timeout
            thread_launch_start = time.time()
            gemini_thread = threading.Thread(target=call_gemini)
            gemini_thread.start()
            gemini_thread.join(timeout=5.0)  # 5 seconds timeout for Gemini           
            thread_launch_end = time.time()
            logger.info(f"⏱️ [GEMINI] Thread execution time: {(thread_launch_end - thread_launch_start):.2f}s")
            
            if gemini_thread.is_alive():
                # Thread is still running, timeout reached
                timeout_time = time.time()
                logger.warning(f"⚠️ [GEMINI] Timeout of 5s reached in {(timeout_time - gemini_start):.2f}s total, fallback to Groq")
            elif not exception_queue.empty():
                # There was an exception
                error_time = time.time()
                exception = exception_queue.get()
                logger.error(f"❌ [GEMINI] Error en {(error_time - gemini_start):.2f}s: {exception}")
                raise exception
            else:
                # Successful response
                success_time = time.time()
                logger.info(f"✅ [GEMINI] Response received in {(success_time - gemini_start):.2f}s total")
                res = result_queue.get()
                if res.text:
                    text = res.text.strip()
                    logger.info(f"✅ [GEMINI] Response received: {len(text)} chars")
                    logger.info(f"   └─ Preview: {text[:80]}..." if len(text) > 80 else f"   └─ Preview: {text}")

                    if is_blocked_response(text):
                        logger.warning("🚫 [GEMINI] Response blocked, using emergency fallback")
                        return _fallback_response()

                    if len(text) < 50:
                        logger.warning(f"⚠️ [GEMINI] Very short response ({len(text)} chars), fallback to Groq")
                    else:
                        postprocess_start = time.time()
                        final_response = postprocess_response(text)
                        postprocess_end = time.time()
                        logger.info(f"✨ [GEMINI] Post-processed in {(postprocess_end - postprocess_start):.2f}s: {len(final_response)} chars")
                        
                        total_time = time.time()
                        logger.info(f"🏁 [GEMINI] Process completed in {(total_time - start_time):.2f}s total")
                        logger.info("=" * 60)
                        return final_response
        except Exception as e:
            error_time = time.time()
            error_msg = str(e).lower()
            if "quota" in error_msg or "limit" in error_msg or "429" in error_msg:
                logger.warning(f"⚠️ [GEMINI] Token/quota limit reached in {(error_time - start_time):.2f}s: {e}")
            else:
                logger.error(f"⚠️ [GEMINI] Failure in {(error_time - start_time):.2f}s: {e}")
            logger.info("   └─ Fallback to Groq activated")

    # 2. Groq (always in simulation; if not, fallback after Gemini or after 20 uses)
    try:
        groq_start = time.time()
        if current_usage > 20:
            logger.info(f"🤖 [GROQ] Gemini daily limit reached ({current_usage}/20)")
        logger.info("🤖 [GROQ] Starting call to llama-3.3-70b-versatile")
        logger.info(f"   └─ Temp: {0.95 if is_mission else 1.0} | Max tokens: 600")
        logger.info("   └─ Top-p: 1.0 | Presence: 1.0 | Frequency: 1.0")

        api_call_start = time.time()
        completion = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt_final}
            ],
            temperature=0.95 if is_mission else 1.0,  # Maximum variability
            top_p=1.0,  # Maximum creativity
            max_tokens=600,  # Longer and more varied responses
            presence_penalty=1.0,  # Maximum penalty against repetition
            frequency_penalty=1.0  # Maximum penalty against repetition
        )
        api_call_end = time.time()
        logger.info(f"⚡ [GROQ] API call completed in {(api_call_end - api_call_start):.2f}s")

        text = completion.choices[0].message.content.strip()
        response_time = time.time()
        logger.info(f"✅ [GROQ] Response received in {(response_time - groq_start):.2f}s total: {len(text)} chars")
        logger.info(f"   └─ Preview: {text[:80]}..." if len(text) > 80 else f"   └─ Preview: {text}")

        if is_blocked_response(text):
            logger.warning("🚫 [GROQ] Response blocked, using emergency fallback")
            return _fallback_response()

        postprocess_start = time.time()
        final_response = postprocess_response(text)
        postprocess_end = time.time()
        logger.info(f"✨ [GROQ] Post-processed in {(postprocess_end - postprocess_start):.2f}s: {len(final_response)} chars")
        
        total_time = time.time()
        logger.info(f"🏁 [GROQ] Process completed in {(total_time - start_time):.2f}s total")
        logger.info("=" * 60)
        return final_response
    except Exception as e:
        error_time = time.time()
        logger.error(f"❌ [GROQ] Critical error in {(error_time - start_time):.2f}s: {e}")
        logger.info("   └─ Using emergency fallback")
        logger.info("=" * 60)
        return _fallback_response()


def _build_system_prompt(personalidad: dict) -> str:
    """Assemble system prompt from structured personality sections."""
    sections = []

    # 1. ABSOLUTE IDENTITY (never_break) — always first
    never_break = personalidad.get("never_break", [])
    if never_break:
        never_break_text = "\n".join([f"- {r}" for r in never_break])
        sections.append(f"## ABSOLUTE IDENTITY (NON-NEGOTIABLE)\n{never_break_text}")

    # 2. IDENTIDAD del personaje
    identity = personalidad.get("identity", "")
    if identity:
        sections.append(f"## CHARACTER\n{identity}")

    # 3. GOLDEN RULES (auto-generated from format_rules)
    format_rules = personalidad.get("format_rules", {})
    if format_rules:
        reglas = []
        if format_rules.get("length"):
            reglas.append(f"- ALWAYS write {format_rules['length']}")
        if format_rules.get("no_tildes"):
            reglas.append("- NEVER use tildes (a e i o u, without accent)")
        if format_rules.get("no_dangling"):
            reglas.append("- NEVER end in single words: \"ke\", \"a\", \"de\", \"por\", \"para\"")
        if format_rules.get("end_punctuation"):
            reglas.append(f"- {format_rules['end_punctuation']}")
        if reglas:
            sections.append("## GOLDEN RULES (NEVER BREAK)\n" + "\n".join(reglas))

    # 4. ORCA ORTHOGRAPHY
    orthography = personalidad.get("orthography", [])
    if orthography:
        ortho_text = "\n".join(orthography)
        sections.append(f"## ORCA ORTHOGRAPHY\n{ortho_text}")

    # 5. STYLE
    style = personalidad.get("style", [])
    if style:
        style_text = "\n".join([f"- {s}" for s in style])
        sections.append(f"## STYLE\n{style_text}")

    # 6. EXAMPLES
    examples = personalidad.get("examples", [])
    if examples:
        examples_text = "\n".join([f'"{e}"' for e in examples])
        sections.append(f"## EXAMPLES (learn from these)\n{examples_text}")

    # If there are structured sections, use them; if not, fallback to old system_prompt
    if sections:
        return "\n\n".join(sections)

    system_prompt = personalidad.get("system_prompt", "")
    if isinstance(system_prompt, list):
        system_prompt = "\n".join([str(x) for x in system_prompt])
    if never_break:
        never_break_text = "\n".join([f"- {r}" for r in never_break])
        return f"## ABSOLUTE IDENTITY (NON-NEGOTIABLE)\n{never_break_text}\n\n{system_prompt}"
    return system_prompt


def build_prompt(role_context, user_content="", history_list=[], max_interactions=5, is_public=False):
    """Build and return `(system_instruction, prompt_final)` without calling APIs."""
    history_context = consolidate_context(history_list, max_interactions=max_interactions, personality=PERSONALIDAD)

    bot_name = PERSONALIDAD.get("name", "Bot")
    public_suffix = PERSONALIDAD.get("public_context_suffix", "")
    history_label = PERSONALIDAD.get("context_history_label", "History")

    system_instruction = _build_system_prompt(PERSONALIDAD)
    if is_public and public_suffix:
        system_instruction = f"{system_instruction}\n\nCONTEXT: {public_suffix}"

    content = (user_content or "").strip()
    # Only add active tasks in CHAT mode.
    # If building a MISSION prompt (empty content), don't add tasks
    # to avoid interference between missions.
    if content:
        tasks = _load_active_tasks_system_additions()
        if tasks:
            logger.info(f"📋 [TASKS] Injecting {len(tasks)} active tasks:")
            for i, task in enumerate(tasks):
                logger.info(f"   📋 Task {i+1}: {task}")
            system_instruction = f"{system_instruction}\n\nACTIVE TASKS:\n" + "\n".join(tasks)

    if history_context:
        system_instruction = f"{system_instruction}\n\n{history_label}:\n{history_context}"
    if content:
        cfg = PERSONALIDAD.get("prompt_chat", {})
        ctx_prefix = cfg.get("context_prefix", "CONTEXT")
        msg_prefix = cfg.get("message_prefix", "MESSAGE")
        instructions = cfg.get("instructions", [])
        closing = cfg.get("closing", "Tu respuesta:")

        user_parts = [
            f"{ctx_prefix}: {role_context}",
            f"{msg_prefix}: {content}",
            "",
        ] + instructions + ["", closing]
    else:
        cfg = PERSONALIDAD.get("prompt_mission", {})
        sit_prefix = cfg.get("situation_prefix", "SITUATION")
        instructions = cfg.get("instructions", [])
        closing = cfg.get("closing", "Respond ONLY in character:")

        user_parts = [
            f"{sit_prefix}: {role_context}",
            "",
        ] + instructions + ["", closing]

    prompt_final = "\n".join(user_parts)

    prompt_final = prompt_final.replace("{name}", bot_name)

    return system_instruction, prompt_final
