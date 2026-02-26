"""
Módulo de postprocesamiento para respuestas del agente.
Contiene funciones para limpiar y formatear las respuestas generadas.
"""

from agent_logging import get_logger

logger = get_logger('postprocessor')

# Lista completa de preposiciones del español y sus variantes comunes
PREPOSICIONES = {
    # Preposiciones formales principales
    "a", "ante", "bajo", "cabe", "con", "contra", "de", "desde", "durante", "en", "entre", 
    "hacia", "hasta", "mediante", "para", "por", "segun", "sin", "so", "sobre", "tras",
    
    # Contracciones y variantes comunes
    "al", "del", "pa", "pel",
    
    # Variantes coloquiales y dialectales
    "ke", "k", "kon", "pa", "para", "por", "sin", "y", "o",
    "kuando", "kien", "kienes", "komo", "dilo", "dime",
    
    # Preposiciones compuestas y locuciones comunes
    "acerca", "adentro", "afuera", "alrededor", "antes", "apenas", "a traves", "cerca", 
    "conforme", "cuanto", "debajo", "delante", "dentro", "despues", "detras", "encima", 
    "enfrente", "excepto", "fuera", "frente", "gracias", "hasta", "inclusive", "incluso", 
    "lejos", "menos", "mediante", "respecto", "salvo", "segun", "siempre", "sobre", 
    "tocante", "versus", "via",
    
    # Conjunciones comunes que funcionan como preposiciones
    "aunque", "como", "cuando", "donde", "mientras", "porque", "pues", "que", "si"
}


def is_response_cut_off(text):
    """Detecta si una respuesta está cortada o incompleta."""
    if not text or len(text.strip()) < 10:
        return False
    
    s = text.strip()
    
    # Si contiene metadatos como "(49)" o "Total:", no es una respuesta cortada
    if "(" in s and ")" in s and any(char.isdigit() for char in s):
        logger.debug(f"   └─ [CORTADA] Descartada por metadatos: {s[:50]}...")
        return False
    if "Total:" in s or "characters" in s:
        logger.debug(f"   └─ [CORTADA] Descartada por metadatos (Total): {s[:50]}...")
        return False
    
    # Indicadores de corte abrupto
    cut_off_indicators = [
        "..." in s or "…" in s,  # Elipsis
        s.endswith("...") or s.endswith("…"),
    ]
    
    # Verificar si termina en medio de una palabra (sin puntuación final)
    has_final_punctuation = s[-1] in ".!?"
    if not has_final_punctuation:
        last_word = s.split()[-1] if s.split() else ""
        # Si la última palabra es muy corta y no es preposición, podría estar cortada
        # pero solo si no parece una palabra completa válida
        if len(last_word) <= 3 and last_word.lower() not in PREPOSICIONES:
            # Excluir palabras comunes cortas que no son preposiciones
            common_short_words = {"grr", "ugh", "bah", "uf", "eh", "oh", "ah", "il", "si", "no", "ya", "ke", "komprar", "tu", "div"}
            if last_word.lower() not in common_short_words:
                logger.debug(f"   └─ [CORTADA] Detectada por palabra corta '{last_word}': {s[:50]}...")
                return True
    
    # Verificar patrones comunes de respuestas cortadas
    cut_off_patterns = [
        s.endswith((" y ", " o ", " pero ", " sino ", " aunque ", " cuando ", " donde ", " como ")),
        s.endswith((" que ", " para ", " por ", " con ", " sin ", " de ", " en ", " a ")),
        # Solo detectar como cortada si termina en minúscula Y tiene más de 15 caracteres
        # (para evitar detectar respuestas cortas y válidas como cortadas)
        len(s) > 15 and s[-1].islower() and not has_final_punctuation and not s.endswith("?"),
    ]
    
    is_cut = any(cut_off_indicators) or any(cut_off_patterns)
    if is_cut:
        logger.debug(f"   └─ [CORTADA] Detectada: {s[:50]}...")
    
    return is_cut


def ends_dangling(frase: str) -> bool:
    """Detecta si una frase termina con una preposición o palabra colgante."""
    if not frase:
        return False
    last = frase.rstrip(".!?").strip().split(" ")[-1].lower() if frase.strip() else ""
    if not last:
        return False
    return last in PREPOSICIONES or len(last) == 1


def postprocesar_respuesta(text, max_chars=280):
    """
    Post-procesa una respuesta del LLM para asegurar calidad y coherencia.
    
    Args:
        text: Texto original generado por el LLM
        max_chars: Límite máximo de caracteres permitidos
        
    Returns:
        Texto limpio y formateado
    """
    logger.debug("🔧 [POST-PROC] Iniciando post-procesamiento")
    logger.debug(f"   └─ Input: {len(text)} chars")

    s = (text or "").strip()
    if not s:
        logger.debug("   └─ Texto vacío, retornando sin cambios")
        return s

    s = " ".join(s.split())
    logger.debug(f"   └─ Después de normalizar espacios: {len(s)} chars")

    # Verificar si la respuesta está cortada
    if is_response_cut_off(s):
        logger.warning("   └─ ⚠️ Respuesta detectada como cortada, aplicando corrección")
        # Recortar hasta la frase anterior completa
        last_end = max(s.rfind("."), s.rfind("!"), s.rfind("?"))
        if last_end >= 30:
            s = s[: last_end + 1].rstrip()
            logger.debug(f"   └─ Recortado hasta frase anterior (pos {last_end}): {len(s)} chars")
        else:
            # Si no hay frase anterior completa, recortar en espacio
            last_space = s.rfind(" ")
            s = (s[:last_space] if last_space >= 30 else s).rstrip()
            logger.debug(f"   └─ Recortado en espacio (pos {last_space}): {len(s)} chars")

    if len(s) > max_chars:
        logger.debug(f"   └─ ⚠️ Texto excede {max_chars} chars, recortando...")
        recorte = s[:max_chars]
        last_end = max(recorte.rfind("."), recorte.rfind("!"), recorte.rfind("?"))
        if last_end >= 30:
            s = recorte[: last_end + 1].rstrip()
            logger.debug(f"   └─ Recortado en puntuación (pos {last_end}): {len(s)} chars")
        else:
            last_space = recorte.rfind(" ")
            s = (recorte[:last_space] if last_space >= 30 else recorte).rstrip()
            logger.debug(f"   └─ Recortado en espacio (pos {last_space}): {len(s)} chars")

    if s and s[-1] not in ".!?":
        if s[-1] in ",;:-":
            s = s[:-1].rstrip()
        s = s + "!"

    if ends_dangling(s):
        logger.debug("   └─ ⚠️ Detectada frase colgante, corrigiendo...")
        logger.debug(f"   └─ Antes: '{s[-30:]}'")
        base = s.rstrip(".!?").strip()
        last_end = max(base.rfind("."), base.rfind("!"), base.rfind("?"))
        if last_end >= 20:
            base = base[: last_end + 1].rstrip(".!? ")
            logger.debug(f"   └─ Recortado en puntuación anterior (pos {last_end})")
        else:
            tries = 0
            while tries < 3 and base:
                if not ends_dangling(base + "!"):
                    break
                cut = base.rfind(" ")
                if cut < 0:
                    base = ""
                    break
                base = base[:cut].rstrip()
                tries += 1
            logger.debug(f"   └─ Recortado {tries} palabras colgantes")

        s = base.strip()
        if s and s[-1] not in ".!?":
            s = s + "!"
        logger.debug(f"   └─ Después: '{s[-30:]}'")

    logger.debug(f"   └─ Output final: {len(s)} chars")
    return s


def consolidar_contexto(historial_lista, max_interacciones=5, personalidad=None):
    """Consolida el historial de forma inteligente, priorizando lo más relevante."""
    if not historial_lista:
        return ""

    def _sanitize(text, limit=240):
        s = (text or "").strip()
        s = " ".join(s.split())
        if len(s) > limit:
            return s[:limit].rstrip() + "..."
        return s

    # Usar la personalidad proporcionada o valores por defecto
    if personalidad is None:
        personalidad = {}
    
    keywords = personalidad.get("history_keywords", [])
    important_label = personalidad.get("context_important_label", "CONTEXTO IMPORTANTE")
    human_label = personalidad.get("context_labels", {}).get("human", "Humano")
    bot_label = personalidad.get("context_labels", {}).get("bot", "Bot")

    interacciones_importantes = []
    interacciones_normales = []

    for h in historial_lista:
        bot_text = (h.get("bot", "") or "").lower()
        humano_text = (h.get("humano", "") or "").lower()

        es_importante = any(kw in bot_text or kw in humano_text for kw in keywords)

        if es_importante:
            interacciones_importantes.append(h)
        else:
            interacciones_normales.append(h)

    entries = []

    if interacciones_importantes:
        h = interacciones_importantes[-1]
        humano = _sanitize(h.get("humano", ""), limit=240)
        bot = _sanitize(h.get("bot", ""), limit=240)
        if humano or bot:
            parts = [f"[{important_label}]"]
            if humano:
                parts.append(f"{human_label}: {humano}")
            if bot:
                parts.append(f"{bot_label}: {bot}")
            entries.append("\n".join(parts))

    ultimas_normales = (
        interacciones_normales[-(max_interacciones - 1):]
        if interacciones_importantes
        else interacciones_normales[-max_interacciones:]
    )

    for h in ultimas_normales:
        humano = _sanitize(h.get("humano", ""), limit=240)
        bot = _sanitize(h.get("bot", ""), limit=240)
        if humano or bot:
            parts = []
            if humano:
                parts.append(f"{human_label}: {humano}")
            if bot:
                parts.append(f"{bot_label}: {bot}")
            entries.append("\n".join(parts))

    return "\n\n".join(entries) if entries else ""


def is_blocked_response(text):
    """Detecta mensajes de rechazo del LLM (off-role, no puede ayudar, etc.)."""
    if not text:
        return False

    s = " ".join(str(text).lower().split())
    blocked_phrases = [
        "soy un asistente virtual",
        "no puedo ayudar",
        "no puedo hacer",
        "no estoy autorizado",
        "no puedo ayudar con eso",
        "no puedo ayudarle",
        "i cannot",
        "cannot help",
        "i'm sorry, i can't",
        "i'm sorry i can't",
    ]
    for p in blocked_phrases:
        if p in s:
            return True
    return False
