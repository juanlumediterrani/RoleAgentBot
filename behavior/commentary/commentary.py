"""
Commentary role - Mission commentary system.
Generates periodic comments about active missions incorporating memories and personality.
"""

from agent_logging import get_logger

logger = get_logger('commentary')

def get_commentary_system_prompt() -> str:
    """Get the system prompt for the commentary role."""
    return "MISION ACTIVA - COMMENTARY: Eres el comentarista de misiones del bot. Tu misión es generar comentarios entretenidos sobre las misiones activas, incorporando recuerdos relevantes y manteniendo la personalidad del personaje."

def get_commentary_task_prompt(enabled_roles: list[str], memories_context: str = "") -> str:
    """Generate a structured task prompt for mission commentary."""
    roles_text = "\n".join([f"- {role}" for role in enabled_roles]) if enabled_roles else "- Ningún rol activo"
    
    return f"""**TAREA DE COMENTARIO DE MISIONES**

Tu tarea específica es: **Haz un comentario sobre tus misiones activas**.

Directrices:
- Sé breve y entretenido (1-3 frases)
- Incorpora recuerdos relevantes si los tienes
- Menciona al menos una de tus misiones activas
- Mantén la personalidad de Putre
- No te repitas

**ROLES ACTIVOS:**
{roles_text}

**CONTEXTO DE RECUERDOS:**
{memories_context or "Sin recuerdos importantes recientes."}

**INSTRUCCIÓN FINAL:** Ahora produce tu comentario sobre las misiones activas.

Solo di las palabras de Putre:"""

def format_commentary_response(response: str) -> str:
    """Format the commentary response for Discord."""
    if not response or not str(response).strip():
        return "⚠️ Putre no tener nada ke decir ahora mismo..."
    
    # Clean up the response and add some flavor
    cleaned = str(response).strip()
    
    # Add a random emoji if not present
    emojis = ["💬", "🗣️", "📢", "🎭", "🎪"]
    if not any(emoji in cleaned for emoji in emojis):
        import random
        cleaned = f"{random.choice(emojis)} {cleaned}"
    
    return cleaned
