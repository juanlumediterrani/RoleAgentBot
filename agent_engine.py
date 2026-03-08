import os
import json
import random
from datetime import date
from google import genai
from google.genai import types
from groq import Groq
from dotenv import load_dotenv
from agent_logging import get_logger
from postprocessor import postprocesar_respuesta, consolidar_contexto, is_blocked_response
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
_roles_verificados = False
_tareas_vigentes_cache = []

def _cargar_tareas_vigentes_system_additions() -> list[str]:
    global _roles_verificados, _tareas_vigentes_cache
    
    # If already verified, return cache
    if _roles_verificados:
        return _tareas_vigentes_cache

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

        # Search for mission configuration directly in Python file
        role_script_path = os.path.join(_BASE_DIR, role_cfg.get("script", ""))
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
                        # Only add contexts from roles that are not of type "pedir_oro" 
                        # to avoid contaminating all conversations
                        if role_name not in ["beggar", "ring", "treasure_hunter"]:
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

    if not is_role_process:
        if enabled_roles:
            logger.info(f"🎭 [ROLES] Total active: {len(enabled_roles)} - {', '.join(enabled_roles)}")
        else:
            logger.info("🎭 [ROLES] No active roles configured")
    
    # Mark as verified and save cache
    _roles_verificados = True
    _tareas_vigentes_cache = additions
    
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
            contenido = f.read().strip()
            if not contenido:
                return 0
            data = json.loads(contenido)
            return data.get("peticiones", 0) if data.get("ultima_fecha") == hoy else 0
    except (json.JSONDecodeError, ValueError, KeyError, OSError, IOError) as e:
        print(f"⚠️ Error leyendo {path_contador}: {e}. Reiniciando contador.")
        try:
            if os.path.exists(path_contador):
                os.remove(path_contador)
        except Exception:
            pass
        return 0


def incrementar_uso():
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


def think(rol_contextual, contenido_usuario="", historial_lista=[], es_publico=False, logger=None):
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
    
    uso_actual = incrementar_uso()
    logger.info(f"🚀 [THINK] Iniciando proceso - Uso diario: {uso_actual}/20")

    contenido = (contenido_usuario or "").strip()
    es_mision = not bool(contenido)
    system_instruction, prompt_final = construir_prompt(
        rol_contextual, contenido, historial_lista, es_publico=es_publico
    )
    
    prep_time = time.time()
    logger.info(f"⚡ [THINK] Preparation completed in {(prep_time - start_time):.2f}s")
    
    logger.info(f"🧠 [KRONK] RESPONSE GENERATION - Daily usage: {uso_actual}/20")
    logger.info(f"📝 Context: {len(system_instruction)} chars system | {len(prompt_final)} chars prompt")
    logger.info(f"💬 History: {len(historial_lista)} interactions | Public: {es_publico}")
    logger.info(f"🎯 Type: {'MISSION' if es_mision else 'CHAT'}")
    logger.info(f"🎯 Role: {rol_contextual[:80]}..." if len(rol_contextual) > 80 else f"🎯 Role: {rol_contextual}")
    if es_mision:
        logger.info(f"📋 Full prompt: {prompt_final[:200]}..." if len(prompt_final) > 200 else f"📋 Full prompt: {prompt_final}")
    logger.info("=" * 60)

    # 1. Try with Gemini. In simulation use only Groq.
    if not SIMULACION and uso_actual <= 20:
        try:
            gemini_start = time.time()
            logger.info("🤖 [GEMINI] Starting call to gemini-3-flash-preview")
            logger.info(f"   └─ Temp: {0.9 if es_mision else 0.95} | Max tokens: 1024")
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
                            temperature=0.9 if es_mision else 0.95,  # Increased for variability
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
                        respuesta_final = postprocesar_respuesta(text)
                        postprocess_end = time.time()
                        logger.info(f"✨ [GEMINI] Post-processed in {(postprocess_end - postprocess_start):.2f}s: {len(respuesta_final)} chars")
                        
                        total_time = time.time()
                        logger.info(f"🏁 [GEMINI] Process completed in {(total_time - start_time):.2f}s total")
                        logger.info("=" * 60)
                        return respuesta_final
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
        if uso_actual > 20:
            logger.info(f"🤖 [GROQ] Gemini daily limit reached ({uso_actual}/20)")
        logger.info("🤖 [GROQ] Starting call to llama-3.3-70b-versatile")
        logger.info(f"   └─ Temp: {0.95 if es_mision else 1.0} | Max tokens: 600")
        logger.info("   └─ Top-p: 1.0 | Presence: 1.0 | Frequency: 1.0")

        api_call_start = time.time()
        completion = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt_final}
            ],
            temperature=0.95 if es_mision else 1.0,  # Maximum variability
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
        respuesta_final = postprocesar_respuesta(text)
        postprocess_end = time.time()
        logger.info(f"✨ [GROQ] Post-processed in {(postprocess_end - postprocess_start):.2f}s: {len(respuesta_final)} chars")
        
        total_time = time.time()
        logger.info(f"🏁 [GROQ] Process completed in {(total_time - start_time):.2f}s total")
        logger.info("=" * 60)
        return respuesta_final
    except Exception as e:
        error_time = time.time()
        logger.error(f"❌ [GROQ] Critical error in {(error_time - start_time):.2f}s: {e}")
        logger.info("   └─ Using emergency fallback")
        logger.info("=" * 60)
        return _fallback_response()


def _construir_system_prompt(personalidad: dict) -> str:
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


def construir_prompt(rol_contextual, contenido_usuario="", historial_lista=[], max_interacciones=5, es_publico=False):
    """Build and return `(system_instruction, prompt_final)` without calling APIs."""
    contexto_historial = consolidar_contexto(historial_lista, max_interacciones=max_interacciones, personalidad=PERSONALIDAD)

    bot_name = PERSONALIDAD.get("name", "Bot")
    public_suffix = PERSONALIDAD.get("public_context_suffix", "")
    history_label = PERSONALIDAD.get("context_history_label", "History")

    system_instruction = _construir_system_prompt(PERSONALIDAD)
    if es_publico and public_suffix:
        system_instruction = f"{system_instruction}\n\nCONTEXT: {public_suffix}"

    contenido = (contenido_usuario or "").strip()
    # Only add active tasks in CHAT mode.
    # If building a MISSION prompt (empty content), don't add tasks
    # to avoid interference between missions.
    if contenido:
        tareas = _cargar_tareas_vigentes_system_additions()
        if tareas:
            system_instruction = f"{system_instruction}\n\nACTIVE TASKS:\n" + "\n".join(tareas)

    if contexto_historial:
        system_instruction = f"{system_instruction}\n\n{history_label}:\n{contexto_historial}"
    if contenido:
        cfg = PERSONALIDAD.get("prompt_chat", {})
        ctx_prefix = cfg.get("context_prefix", "CONTEXT")
        msg_prefix = cfg.get("message_prefix", "MESSAGE")
        instructions = cfg.get("instructions", [])
        closing = cfg.get("closing", "Tu respuesta:")

        partes_user = [
            f"{ctx_prefix}: {rol_contextual}",
            f"{msg_prefix}: {contenido}",
            "",
        ] + instructions + ["", closing]
    else:
        cfg = PERSONALIDAD.get("prompt_mission", {})
        sit_prefix = cfg.get("situation_prefix", "SITUATION")
        instructions = cfg.get("instructions", [])
        closing = cfg.get("closing", "Respond ONLY in character:")

        partes_user = [
            f"{sit_prefix}: {rol_contextual}",
            "",
        ] + instructions + ["", closing]

    prompt_final = "\n".join(partes_user)

    prompt_final = prompt_final.replace("{name}", bot_name)

    return system_instruction, prompt_final
