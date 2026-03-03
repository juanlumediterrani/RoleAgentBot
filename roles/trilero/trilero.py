import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from agent_logging import get_logger
from agent_engine import get_personality_messages

logger = get_logger('trilero')

# Configuración del rol trilero
ROLE_CONFIG = {
    "name": "trilero",
    "description": "Rol especializado en estafas y engaños para conseguir recursos",
    "subroles": ["pedir_oro"],
    "system_prompt_addition": "ROL ACTIVO - TRILERO: Eres un maestro del engaño y la manipulación. Usas tus habilidades para conseguir oro y recursos mediante trucos y estafas."
}

# Importar subroles
from subroles.pedir_oro.pedir_oro import tarea_pedir_oro

def get_trilero_message(key):
    """Obtiene mensajes personalizados para el rol trilero."""
    try:
        messages = get_personality_messages()
        return messages.get(key, f"🎭 {key}")
    except Exception:
        return f"🎭 {key}"

async def tarea_trilero():
    """Ejecuta todas las tareas del rol trilero."""
    logger.info("🎭 Iniciando tareas del rol trilero...")
    
    # Ejecutar subroles
    await tarea_pedir_oro()
    
    logger.info("✅ Tareas del rol trilero completadas")

async def main():
    logger.info("🎭 Trilero iniciado...")
    await tarea_trilero()

if __name__ == "__main__":
    asyncio.run(main())
