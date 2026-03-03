import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
import random
from dotenv import load_dotenv

_env_candidates = [
    (os.getenv("ROLE_AGENT_ENV_FILE") or "").strip(),
    os.path.expanduser("~/.roleagentbot.env"),
    os.path.join(os.path.dirname(__file__), ".env"),
]
for _p in _env_candidates:
    if _p and os.path.exists(_p):
        load_dotenv(_p, override=False)
        break

from agent_engine import pensar, get_discord_token
from agent_db import get_global_db
from agent_logging import get_logger
from discord_http import DiscordHTTP

logger = get_logger('anillo')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "buscar_anillo",
    "system_prompt_addition": "MISION ACTIVA - BUSCAR ANILLO: Buscas el \"anillo uniko\" para tu jefe. Si ya acusaste a alguien de tener el anillo, RECUERDALO y mencionalo."
}


async def buscar_anillo_automatico(http: DiscordHTTP):
    """Búsqueda automática del anillo: acusa a un miembro aleatorio por servidor."""
    logger.info("🔍 Iniciando búsqueda automática del anillo...")

    guilds = await http.get_guilds()
    for guild_data in guilds:
        guild_id = int(guild_data["id"])

        # Limitar: max 2 ANILLO por servidor al día
        cuenta_anillo = await asyncio.to_thread(
            get_global_db().contar_interacciones_tipo_ultimo_dia, "ANILLO", guild_id
        )
        if cuenta_anillo >= 2:
            logger.info(f"🔕 [Límite] Ya hubo {cuenta_anillo} ANILLO hoy en servidor {guild_id}, saltando.")
            continue

        miembros = await http.get_guild_members(guild_id)
        miembros_humanos = [m for m in miembros if not m.get("user", {}).get("bot", False)]
        if not miembros_humanos:
            continue

        objetivo = random.choice(miembros_humanos)
        user_id = int(objetivo["user"]["id"])
        username = objetivo["user"].get("username", str(user_id))

        res = await asyncio.to_thread(
            pensar,
            f"Acusa a {username} de tener el Anillo unico. Intimidale para que te lo entregue, usando tu personalidad de orco."
        )

        if await http.send_dm(user_id, f"👁️ **EL OJO QUE TODO LO VE...**\n{res}"):
            await asyncio.to_thread(
                get_global_db().registrar_interaccion,
                user_id, username, "ANILLO",
                "Búsqueda del anillo", None, guild_id,
                metadata={"respuesta": res, "rol": "buscar_anillo"}
            )
            logger.info(f"✅ ANILLO enviado a {username}")
        else:
            logger.warning(f"⚠️ No se pudo enviar ANILLO a {username}")


async def main():
    logger.info("�️ Buscar anillo iniciado...")
    token = get_discord_token()
    http = DiscordHTTP(token)

    await buscar_anillo_automatico(http)

    filas = await asyncio.to_thread(get_global_db().limpiar_interacciones_antiguas, 30)
    logger.info(f"🧹 Limpieza: {filas} registros borrados.")


if __name__ == "__main__":
    asyncio.run(main())
