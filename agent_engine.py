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

# --- CARGA DE PERSONALIDAD ---
_BASE_DIR = os.path.dirname(__file__)
_AGENT_CONFIG_PATH = os.path.join(_BASE_DIR, "agent_config.json")

with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
    AGENT_CFG = json.load(f)

def _cargar_personalidad() -> dict:
    with open(_AGENT_CONFIG_PATH, encoding="utf-8") as f:
        agent_cfg = json.load(f)
    personality_rel = agent_cfg.get("personality", "personalities/default.json")
    personality_path = os.path.join(_BASE_DIR, personality_rel)
    with open(personality_path, encoding="utf-8") as f:
        return json.load(f)

PERSONALIDAD = _cargar_personalidad()
# Solo mostrar log de personalidad si no estamos en un subproceso de rol
if os.getenv('ROLE_AGENT_PROCESS') != '1':
    logger.info(f"🎭 [PERSONALIDAD] Cargada: {PERSONALIDAD.get('name', 'Unknown')} desde {AGENT_CFG.get('personality', 'Unknown')}")


def get_discord_token():
    """Obtiene el token de Discord específico para la personalidad activa."""
    personality_name = PERSONALIDAD.get("name", "").upper()
    specific_token = os.getenv(f"DISCORD_TOKEN_{personality_name}")
    if specific_token:
        logger.info(f"🔑 Usando token específico: DISCORD_TOKEN_{personality_name}")
        return specific_token
    # Fallback al token genérico
    fallback_token = os.getenv("DISCORD_TOKEN")
    if fallback_token:
        logger.info(f"🔑 Usando token genérico: DISCORD_TOKEN")
    else:
        logger.warning("⚠️ No se encontró ningún token de Discord (ni específico ni genérico)")
    return fallback_token


# Cache para evitar múltiples verificaciones de roles
_roles_verificados = False
_tareas_vigentes_cache = []

def _cargar_tareas_vigentes_system_additions() -> list[str]:
    global _roles_verificados, _tareas_vigentes_cache
    
    # Si ya verificamos, devolver cache
    if _roles_verificados:
        return _tareas_vigentes_cache

    is_role_process = os.getenv('ROLE_AGENT_PROCESS') == '1'
    
    roles = (AGENT_CFG or {}).get("roles", {})
    additions: list[str] = []
    
    if not is_role_process:
        logger.info("🎭 [ROLES] Verificando roles configurados...")
    enabled_roles = []

    for role_name, role_cfg in roles.items():
        if not isinstance(role_cfg, dict):
            continue
        if not role_cfg.get("enabled", False):
            if not is_role_process:
                logger.info(f"   💤 [ROL] '{role_name}' - desactivado")
            continue

        enabled_roles.append(role_name)
        if not is_role_process:
            logger.info(f"   ✅ [ROL] '{role_name}' - activo (cada {role_cfg.get('interval_hours', '?')}h)")

        # Buscar la configuración de misión directamente en el archivo Python
        role_script_path = os.path.join(_BASE_DIR, role_cfg.get("script", ""))
        if not os.path.exists(role_script_path):
            if not is_role_process:
                logger.warning(f"   ⚠️ [ROL] Script no encontrado: {role_script_path}")
            continue
        
        try:
            # Leer el archivo y extraer MISSION_CONFIG con regex para evitar importar
            with open(role_script_path, encoding="utf-8") as f:
                content = f.read()
            
            # Buscar MISSION_CONFIG en el código
            import re
            mission_match = re.search(r'MISSION_CONFIG\s*=\s*{([^}]+)}', content, re.DOTALL)
            if mission_match:
                # Extraer system_prompt_addition del diccionario (manejar comillas escapadas)
                addition_match = re.search(r'"system_prompt_addition"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', mission_match.group(1))
                if addition_match:
                    addition = addition_match.group(1).strip()
                    # Unescape comillas y backslashes
                    addition = addition.replace('\\"', '"').replace('\\\\', '\\')
                    if addition:
                        # Solo añadir contextos de roles que no sean de tipo "pedir_oro" 
                        # para evitar contaminar todas las conversaciones
                        if role_name not in ["pedir_oro", "buscar_anillo", "buscador_tesoros"]:
                            additions.append(addition)
                            if not is_role_process:
                                logger.info(f"   📋 [ROL] '{role_name}' - misión cargada: {addition[:50]}...")
                        else:
                            if not is_role_process:
                                logger.info(f"   🔄 [ROL] '{role_name}' - contexto contextual (no global): {addition[:50]}...")
                        continue
            
            if not is_role_process:
                logger.warning(f"⚠️ No se encontró MISSION_CONFIG válido en {role_name}")
        except Exception as e:
            if not is_role_process:
                logger.warning(f"⚠️ No se pudo cargar MISSION_CONFIG de {role_name}: {e}")

    if not is_role_process:
        if enabled_roles:
            logger.info(f"🎭 [ROLES] Total activos: {len(enabled_roles)} - {', '.join(enabled_roles)}")
        else:
            logger.info("🎭 [ROLES] No hay roles activos configurados")
    
    # Marcar como verificado y guardar cache
    _roles_verificados = True
    _tareas_vigentes_cache = additions
    
    return additions

# --- CLIENTES Y PATHS ---
client_groq = Groq(api_key=os.getenv("GROQ_API_KEY"))

def _get_fatiga_path():
    """Obtiene la ruta del archivo de fatiga según servidor y personalidad."""
    # Si no hay servidor activo, usar ruta temporal hasta que se conecte
    server_name = get_active_server_name()
    if not server_name:
        # Ruta temporal hasta que el bot se conecte a un servidor
        return os.path.join(_BASE_DIR, "fatiga_temp.json")
    
    # Sanitizar el nombre del servidor
    server_name = server_name.lower().replace(' ', '_').replace('-', '_')
    server_name = ''.join(c for c in server_name if c.isalnum() or c == '_')
    
    personality_name = PERSONALIDAD.get("name", "unknown").lower()
    
    fatiga_dir = os.path.join(_BASE_DIR, "fatiga", server_name)
    
    # Crear directorio si no existe
    os.makedirs(fatiga_dir, exist_ok=True)
    
    return os.path.join(fatiga_dir, f"{personality_name}.json")

# Si AGENT_SIMULACION=1, el contador no se persiste (para simulaciones)
SIMULACION = os.getenv("AGENT_SIMULATION", os.getenv("ROLE_AGENT_SIMULATION", "")).strip() in ("1", "true", "True", "yes")

logger.info(f"🔧 [CONFIG] Modo simulación: {'ACTIVADO' if SIMULACION else 'DESACTIVADO'}")
logger.info(f"🔧 [CONFIG] Contador de uso (ruta se resuelve en tiempo de ejecución)")
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
        print(f"⚠️ Error escribiendo {path_contador}: {e}")
    return uso


def _fallback_response():
    """Respuesta de emergencia definida en la personalidad."""
    fallbacks = PERSONALIDAD.get("emergency_fallbacks", [])
    if fallbacks:
        return random.choice(fallbacks)
    return PERSONALIDAD.get("emergency_fallback", "...")


def pensar(rol_contextual, contenido_usuario="", historial_lista=[], es_publico=False, logger=None):
    """
    Motor unificado con gemini-3-flash-preview y Fallback a Groq.
    Carga la personalidad desde el archivo JSON activo.
    """
    import time
    start_time = time.time()
    
    # Usar logger proporcionado o el logger global por defecto
    if logger is None:
        from agent_logging import get_logger
        logger = get_logger('agent_engine')
    
    uso_actual = incrementar_uso()
    logger.info(f"🚀 [PENSAR] Iniciando proceso - Uso diario: {uso_actual}/20")

    contenido = (contenido_usuario or "").strip()
    es_mision = not bool(contenido)
    system_instruction, prompt_final = construir_prompt(
        rol_contextual, contenido, historial_lista, es_publico=es_publico
    )
    
    prep_time = time.time()
    logger.info(f"⚡ [PENSAR] Preparación completada en {(prep_time - start_time):.2f}s")
    
    logger.info(f"🧠 [KRONK] GENERACIÓN DE RESPUESTA - Uso diario: {uso_actual}/20")
    logger.info(f"📝 Contexto: {len(system_instruction)} chars system | {len(prompt_final)} chars prompt")
    logger.info(f"💬 Historial: {len(historial_lista)} interacciones | Público: {es_publico}")
    logger.info(f"🎯 Tipo: {'MISIÓN' if es_mision else 'CHARLA'}")
    logger.info(f"🎯 Rol: {rol_contextual[:80]}..." if len(rol_contextual) > 80 else f"🎯 Rol: {rol_contextual}")
    if es_mision:
        logger.info(f"📋 Prompt completo: {prompt_final[:200]}..." if len(prompt_final) > 200 else f"📋 Prompt completo: {prompt_final}")
    logger.info("=" * 60)

    # 1. Intento con Gemini. En simulación usamos solo Groq.
    if not SIMULACION and uso_actual <= 20:
        try:
            gemini_start = time.time()
            logger.info("🤖 [GEMINI] Iniciando llamada a gemini-3-flash-preview")
            logger.info(f"   └─ Temp: {0.9 if es_mision else 0.95} | Max tokens: 1024")
            logger.info("   └─ Top-p: 0.95")

            client_gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
            
            # Agregar timeout más agresivo para Gemini usando threading
            import threading
            import queue
            
            result_queue = queue.Queue()
            exception_queue = queue.Queue()
            
            def call_gemini():
                try:
                    thread_start = time.time()
                    logger.info(f"🧵 [GEMINI] Thread iniciado")
                    res = client_gemini.models.generate_content(
                        model='gemini-3-flash-preview',
                        contents=prompt_final,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.9 if es_mision else 0.95,  # Aumentado para variabilidad
                            max_output_tokens=1024,
                            top_p=0.95,  # Aumentado para creatividad
                            safety_settings=[types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE")]
                        )
                    )
                    thread_end = time.time()
                    logger.info(f"🧵 [GEMINI] Thread completado en {(thread_end - thread_start):.2f}s")
                    result_queue.put(res)
                except Exception as e:
                    exception_queue.put(e)
            
            # Iniciar llamada en thread separado con timeout
            thread_launch_start = time.time()
            gemini_thread = threading.Thread(target=call_gemini)
            gemini_thread.start()
            gemini_thread.join(timeout=5.0)  # Timeout de 5 segundos para Gemini           
            thread_launch_end = time.time()
            logger.info(f"⏱️ [GEMINI] Thread execution time: {(thread_launch_end - thread_launch_start):.2f}s")
            
            if gemini_thread.is_alive():
                # El thread todavía está corriendo, timeout alcanzado
                timeout_time = time.time()
                logger.warning(f"⚠️ [GEMINI] Timeout de 5s alcanzado en {(timeout_time - gemini_start):.2f}s total, fallback a Groq")
            elif not exception_queue.empty():
                # Hubo una excepción
                error_time = time.time()
                exception = exception_queue.get()
                logger.error(f"❌ [GEMINI] Error en {(error_time - gemini_start):.2f}s: {exception}")
                raise exception
            else:
                # Respuesta exitosa
                success_time = time.time()
                logger.info(f"✅ [GEMINI] Respuesta recibida en {(success_time - gemini_start):.2f}s total")
                res = result_queue.get()
                if res.text:
                    text = res.text.strip()
                    logger.info(f"✅ [GEMINI] Respuesta recibida: {len(text)} chars")
                    logger.info(f"   └─ Preview: {text[:80]}..." if len(text) > 80 else f"   └─ Preview: {text}")

                    if is_blocked_response(text):
                        logger.warning("🚫 [GEMINI] Respuesta bloqueada, usando fallback de emergencia")
                        return _fallback_response()

                    if len(text) < 50:
                        logger.warning(f"⚠️ [GEMINI] Respuesta muy corta ({len(text)} chars), fallback a Groq")
                    else:
                        postprocess_start = time.time()
                        respuesta_final = postprocesar_respuesta(text)
                        postprocess_end = time.time()
                        logger.info(f"✨ [GEMINI] Post-procesado en {(postprocess_end - postprocess_start):.2f}s: {len(respuesta_final)} chars")
                        
                        total_time = time.time()
                        logger.info(f"🏁 [GEMINI] Proceso completado en {(total_time - start_time):.2f}s total")
                        logger.info("=" * 60)
                        return respuesta_final
        except Exception as e:
            error_time = time.time()
            error_msg = str(e).lower()
            if "quota" in error_msg or "limit" in error_msg or "429" in error_msg:
                logger.warning(f"⚠️ [GEMINI] Límite de tokens/cuota alcanzado en {(error_time - start_time):.2f}s: {e}")
            else:
                logger.error(f"⚠️ [GEMINI] Fallo en {(error_time - start_time):.2f}s: {e}")
            logger.info("   └─ Fallback a Groq activado")

    # 2. Groq (siempre en simulación; si no, fallback tras Gemini o después de 20 usos)
    try:
        groq_start = time.time()
        if uso_actual > 20:
            logger.info(f"🤖 [GROQ] Límite diario de Gemini alcanzado ({uso_actual}/20)")
        logger.info("🤖 [GROQ] Iniciando llamada a llama-3.3-70b-versatile")
        logger.info(f"   └─ Temp: {0.95 if es_mision else 1.0} | Max tokens: 600")
        logger.info("   └─ Top-p: 1.0 | Presence: 1.0 | Frequency: 1.0")

        api_call_start = time.time()
        completion = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt_final}
            ],
            temperature=0.95 if es_mision else 1.0,  # Máxima variabilidad
            top_p=1.0,  # Máxima creatividad
            max_tokens=600,  # Respuestas más largas y variadas
            presence_penalty=1.0,  # Máximo penalty contra repetición
            frequency_penalty=1.0  # Máximo penalty contra repetición
        )
        api_call_end = time.time()
        logger.info(f"⚡ [GROQ] Llamada API completada en {(api_call_end - api_call_start):.2f}s")

        text = completion.choices[0].message.content.strip()
        response_time = time.time()
        logger.info(f"✅ [GROQ] Respuesta recibida en {(response_time - groq_start):.2f}s total: {len(text)} chars")
        logger.info(f"   └─ Preview: {text[:80]}..." if len(text) > 80 else f"   └─ Preview: {text}")

        if is_blocked_response(text):
            logger.warning("🚫 [GROQ] Respuesta bloqueada, usando fallback de emergencia")
            return _fallback_response()

        postprocess_start = time.time()
        respuesta_final = postprocesar_respuesta(text)
        postprocess_end = time.time()
        logger.info(f"✨ [GROQ] Post-procesado en {(postprocess_end - postprocess_start):.2f}s: {len(respuesta_final)} chars")
        
        total_time = time.time()
        logger.info(f"🏁 [GROQ] Proceso completado en {(total_time - start_time):.2f}s total")
        logger.info("=" * 60)
        return respuesta_final
    except Exception as e:
        error_time = time.time()
        logger.error(f"❌ [GROQ] Error crítico en {(error_time - start_time):.2f}s: {e}")
        logger.info("   └─ Usando fallback de emergencia")
        logger.info("=" * 60)
        return _fallback_response()


def _construir_system_prompt(personalidad: dict) -> str:
    """Ensambla el system prompt desde las secciones estructuradas de la personalidad."""
    secciones = []

    # 1. IDENTIDAD ABSOLUTA (never_break) — siempre primero
    never_break = personalidad.get("never_break", [])
    if never_break:
        never_break_text = "\n".join([f"- {r}" for r in never_break])
        secciones.append(f"## IDENTIDAD ABSOLUTA (NO NEGOCIABLE)\n{never_break_text}")

    # 2. IDENTIDAD del personaje
    identity = personalidad.get("identity", "")
    if identity:
        secciones.append(f"## PERSONAJE\n{identity}")

    # 3. REGLAS DE ORO (auto-generadas desde format_rules)
    format_rules = personalidad.get("format_rules", {})
    if format_rules:
        reglas = []
        if format_rules.get("length"):
            reglas.append(f"- SIEMPRE escribe {format_rules['length']}")
        if format_rules.get("no_tildes"):
            reglas.append("- NUNCA uses tildes (a e i o u, sin acento)")
        if format_rules.get("no_dangling"):
            reglas.append("- NUNCA termines en palabras sueltas: \"ke\", \"a\", \"de\", \"por\", \"para\"")
        if format_rules.get("end_punctuation"):
            reglas.append(f"- {format_rules['end_punctuation']}")
        if reglas:
            secciones.append("## REGLAS DE ORO (NUNCA ROMPER)\n" + "\n".join(reglas))

    # 4. ORTOGRAFÍA ORCA
    orthography = personalidad.get("orthography", [])
    if orthography:
        ortho_text = "\n".join(orthography)
        secciones.append(f"## ORTOGRAFIA ORCA\n{ortho_text}")

    # 5. ESTILO
    style = personalidad.get("style", [])
    if style:
        style_text = "\n".join([f"- {s}" for s in style])
        secciones.append(f"## ESTILO\n{style_text}")

    # 6. EJEMPLOS
    examples = personalidad.get("examples", [])
    if examples:
        examples_text = "\n".join([f'"{e}"' for e in examples])
        secciones.append(f"## EJEMPLOS (aprende de estos)\n{examples_text}")

    # Si hay secciones estructuradas, usarlas; si no, fallback al viejo system_prompt
    if secciones:
        return "\n\n".join(secciones)

    system_prompt = personalidad.get("system_prompt", "")
    if isinstance(system_prompt, list):
        system_prompt = "\n".join([str(x) for x in system_prompt])
    if never_break:
        never_break_text = "\n".join([f"- {r}" for r in never_break])
        return f"## IDENTIDAD ABSOLUTA (NO NEGOCIABLE)\n{never_break_text}\n\n{system_prompt}"
    return system_prompt


def construir_prompt(rol_contextual, contenido_usuario="", historial_lista=[], max_interacciones=5, es_publico=False):
    """Construye y devuelve `(system_instruction, prompt_final)` sin llamar a APIs."""
    contexto_historial = consolidar_contexto(historial_lista, max_interacciones=max_interacciones, personalidad=PERSONALIDAD)

    bot_name = PERSONALIDAD.get("name", "Bot")
    public_suffix = PERSONALIDAD.get("public_context_suffix", "")
    history_label = PERSONALIDAD.get("context_history_label", "Historial")

    system_instruction = _construir_system_prompt(PERSONALIDAD)
    if es_publico and public_suffix:
        system_instruction = f"{system_instruction}\n\nCONTEXTO: {public_suffix}"

    contenido = (contenido_usuario or "").strip()
    # Solo sumar tareas vigentes en modo CHAT.
    # Si estamos construyendo un prompt de MISIÓN (contenido vacío), no sumamos tareas
    # para evitar interferencias entre misiones.
    if contenido:
        tareas = _cargar_tareas_vigentes_system_additions()
        if tareas:
            system_instruction = f"{system_instruction}\n\nTAREAS VIGENTES:\n" + "\n".join(tareas)

    if contexto_historial:
        system_instruction = f"{system_instruction}\n\n{history_label}:\n{contexto_historial}"
    if contenido:
        cfg = PERSONALIDAD.get("prompt_chat", {})
        ctx_prefix = cfg.get("context_prefix", "CONTEXTO")
        msg_prefix = cfg.get("message_prefix", "MENSAJE")
        instructions = cfg.get("instructions", [])
        closing = cfg.get("closing", "Tu respuesta:")

        partes_user = [
            f"{ctx_prefix}: {rol_contextual}",
            f"{msg_prefix}: {contenido}",
            "",
        ] + instructions + ["", closing]
    else:
        cfg = PERSONALIDAD.get("prompt_mission", {})
        sit_prefix = cfg.get("situation_prefix", "SITUACIÓN")
        instructions = cfg.get("instructions", [])
        closing = cfg.get("closing", "Responde SOLO en personaje:")

        partes_user = [
            f"{sit_prefix}: {rol_contextual}",
            "",
        ] + instructions + ["", closing]

    prompt_final = "\n".join(partes_user)

    prompt_final = prompt_final.replace("{name}", bot_name)

    return system_instruction, prompt_final
