"""
Módulo simplificado de postprocesamiento para respuestas del agente.
Contiene funciones esenciales para limpiar y formatear las respuestas generadas.
"""

from agent_logging import get_logger

logger = get_logger('postprocessor')

# Preposiciones esenciales del español
PREPOSICIONES_ESSENCIALES = {
    "a", "ante", "bajo", "cabe", "con", "contra", "de", "desde", "durante", "en", "entre", 
    "hacia", "hasta", "mediante", "para", "por", "segun", "sin", "so", "sobre", "tras",
    "al", "del", "pa", "pel"
}

def is_response_cut_off(text):
    """Detecta si una respuesta está cortada o incompleta."""
    if not text or len(text.strip()) < 10:
        return False
    
    s = text.strip()
    
    # Descartar si contiene metadatos
    if ("(" in s and ")" in s and any(c.isdigit() for c in s)) or "Total:" in s:
        return False
    
    # Indicadores claros de corte
    cut_off_indicators = [
        "..." in s or "…" in s,
        s.endswith((" y ", " o ", " pero ", " que ", " para ", " por ", " con ", " de ", " en ", " a ")),
        len(s) > 15 and s[-1].islower() and s[-1] not in ".!?,"
    ]
    
    return any(cut_off_indicators)

def ends_dangling(frase: str) -> bool:
    """Detecta si una frase termina con una preposición colgante."""
    if not frase:
        return False
    
    last = frase.rstrip(".!?").strip().split(" ")[-1].lower() if frase.strip() else ""
    return last in PREPOSICIONES_ESSENCIALES or len(last) == 1

def postprocesar_respuesta(text, max_chars=280):
    """
    Post-procesa una respuesta del LLM de forma simplificada.
    
    Args:
        text: Texto original generado por el LLM
        max_chars: Límite máximo de caracteres permitidos
        
    Returns:
        Texto limpio y formateado
    """
    if not text:
        return ""
    
    s = " ".join(text.strip().split())
    
    # Corregir respuesta cortada
    if is_response_cut_off(s):
        last_end = max(s.rfind("."), s.rfind("!"), s.rfind("?"))
        if last_end >= 30:
            s = s[:last_end + 1].rstrip()
        else:
            last_space = s.rfind(" ")
            s = (s[:last_space] if last_space >= 30 else s).rstrip()
    
    # Limitar longitud
    if len(s) > max_chars:
        recorte = s[:max_chars]
        last_end = max(recorte.rfind("."), recorte.rfind("!"), recorte.rfind("?"))
        if last_end >= 30:
            s = recorte[:last_end + 1].rstrip()
        else:
            last_space = recorte.rfind(" ")
            s = (recorte[:last_space] if last_space >= 30 else recorte).rstrip()
    
    # Asegurar puntuación final solo si es necesario
    if s and s[-1] not in ".!?,":
        s = s + "!"
    
    # Eliminar frases colgantes
    if ends_dangling(s):
        base = s.rstrip(".!?").strip()
        last_end = max(base.rfind("."), base.rfind("!"), base.rfind("?"))
        if last_end >= 20:
            base = base[:last_end + 1].rstrip(".!? ")
        else:
            # Eliminar últimas palabras hasta que no quede colgante
            for _ in range(3):
                if not ends_dangling(base + "!"):
                    break
                cut = base.rfind(" ")
                if cut < 0:
                    base = ""
                    break
                base = base[:cut].rstrip()
        
        s = base.strip()
        if s and s[-1] not in ".!?,":
            s = s + "!"
    
    return s

def consolidar_contexto(historial_lista, max_interacciones=5, personalidad=None):
    """Consolida el historial de forma simplificada."""
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
    """Detecta mensajes de rechazo del LLM."""
    if not text:
        return False
    
    s = " ".join(str(text).lower().split())
    blocked_phrases = [
        "soy un asistente virtual",
        "no puedo ayudar",
        "no puedo hacer",
        "no estoy autorizado",
        "i cannot",
        "cannot help",
        "i'm sorry, i can't"
    ]
    
    return any(phrase in s for phrase in blocked_phrases)
