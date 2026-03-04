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

from agent_engine import pensar, get_discord_token, PERSONALIDAD
from agent_db import get_global_db
from agent_logging import get_logger
from discord_http import DiscordHTTP

logger = get_logger('limosna')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "limosna",
    "system_prompt_addition": "MISION ACTIVA - LIMOSNA: Necesitas limosna para traer a tu familia orca contigo. Si ya pediste limosna recientemente, RECUERDALO y mencionalo."
}

# Razones neutrales como fallback
RAZONES_FALLBACK = [
    "para ayudar a tu familia orca",
    "para comprar suministros esenciales",
    "para pagar deudas importantes",
    "para ayudar a otros orcos necesitados",
    "para comprar comida",
    "para reparar tu equipo",
    "para comprar medicinas",
    "para ayudar a tu clan"
]

def obtener_razones_limosna():
    """Obtiene razones de limosna desde la personalidad o usa fallback."""
    try:
        razones_personalidad = PERSONALIDAD.get("discord", {}).get("role_messages", {}).get("limosna_reasons", [])
        if razones_personalidad:
            logger.info(f"📋 Usando {len(razones_personalidad)} razones de limosna desde personalidad")
            return razones_personalidad
        else:
            logger.info("📋 Usando razones fallback de limosna (no hay razones en personalidad)")
            return RAZONES_FALLBACK
    except Exception as e:
        logger.warning(f"⚠️ Error obteniendo razones de personalidad: {e}")
        return RAZONES_FALLBACK


async def tarea_limosna(http: DiscordHTTP = None):
    """Pide limosna por privado o en público, registrando el contexto."""
    logger.info("🙏 Iniciando ronda de peticiones de limosna...")
    
    # Si no se proporciona http, crear una instancia
    if http is None:
        token = get_discord_token()
        http = DiscordHTTP(token)

    guilds = await http.get_guilds()
    for guild_data in guilds:
        es_privado = random.choice([True, False])
        if es_privado:
            await _pedir_limosna_privado(http, guild_data)
        else:
            await _pedir_limosna_publico(http, guild_data)


async def _pedir_limosna_privado(http: DiscordHTTP, guild_data: dict):
    """Pide limosna por mensaje privado."""
    guild_id = int(guild_data["id"])
    miembros = await http.get_guild_members(guild_id)
    miembros_humanos = [m for m in miembros if not m.get("user", {}).get("bot", False)]
    if not miembros_humanos:
        return

    objetivo = random.choice(miembros_humanos)
    user_id = int(objetivo["user"]["id"])
    username = objetivo["user"].get("username", str(user_id))

    # Limitar: max 2 LIMOSNA_DM por servidor al día
    cuenta_dm = await asyncio.to_thread(
        get_global_db().contar_interacciones_tipo_ultimo_dia, "LIMOSNA_DM", guild_id
    )
    if cuenta_dm >= 2:
        logger.info(f"🔕 [Límite] Ya hubo {cuenta_dm} LIMOSNA_DM hoy en servidor {guild_id}, saltando.")
        return

    # Verificar si usuario ha recibido petición recientemente (últimas 12h)
    ha_pedido_recientemente = await asyncio.to_thread(
        get_global_db().usuario_ha_pedido_tipo_recientemente, user_id, "LIMOSNA_DM", 12
    )
    if not ha_pedido_recientemente:
        # Obtener razones dinámicamente
        razones = obtener_razones_limosna()
        razon = random.choice(razones)
        
        # Construir prompt específico para el LLM
        prompt_limosna = f"Pídele limosna a {username}: {razon}. Sé convincente y usa tu personalidad de orco."
        res = await asyncio.to_thread(pensar, prompt_limosna)

        if await http.send_dm(user_id, f"👹 {res}"):
            await asyncio.to_thread(
                get_global_db().registrar_interaccion,
                user_id, username, "LIMOSNA_DM",
                "Te pedí limosna por privado", None, guild_id,
                metadata={"respuesta": res, "rol": "limosna", "razon": razon}
            )
            logger.info(f"✅ LIMOSNA_DM enviado a {username}")
        else:
            logger.warning(f"⚠️ No se pudo enviar LIMOSNA_DM a {username}")


async def _pedir_limosna_publico(http: DiscordHTTP, guild_data: dict):
    """Pide limosna en canal público."""
    guild_id = int(guild_data["id"])

    # Limitar: max 4 LIMOSNA_PUBLICO por servidor al día
    cuenta_publico = await asyncio.to_thread(
        get_global_db().contar_interacciones_tipo_ultimo_dia, "LIMOSNA_PUBLICO", guild_id
    )
    if cuenta_publico >= 4:
        logger.info(f"🔕 [Límite] Ya hubo {cuenta_publico} LIMOSNA_PUBLICO hoy en servidor {guild_id}, saltando.")
        return

    # Buscar canal general
    canales = await http.get_guild_channels(guild_id)
    canal = next((c for c in canales if c.get("name") == "general" and c.get("type") == 0), None)
    if canal is None:
        canal = next((c for c in canales if c.get("type") == 0), None)
    if canal is None:
        return

    canal_id = int(canal["id"])
    
    # Obtener razones dinámicamente
    razones = obtener_razones_limosna()
    razon = random.choice(razones)
    
    # Construir prompt específico para el LLM
    prompt_limosna = f"Estás gritando en el centro del pueblo para que los humanos te den limosna {razon}. Escribe un mensaje para convencerlos, usando tu personalidad de orco."
    res = await asyncio.to_thread(
        pensar,
        prompt_limosna,
        "", [], True
    )

    if await http.send_channel_message(canal_id, f"📢 **DONATIVOS PARA LOS VERDES:** {res}"):
        await asyncio.to_thread(
            get_global_db().registrar_interaccion,
            str(canal_id), "CANAL_PUBLICO", "LIMOSNA_PUBLICO",
            "Grito de limosna en el canal", canal_id, guild_id,
            metadata={"respuesta": res, "rol": "limosna", "razon": razon}
        )
        logger.info(f"✅ LIMOSNA_PUBLICO enviado en canal {canal.get('name', canal_id)}")
    else:
        logger.warning(f"⚠️ No se pudo enviar LIMOSNA_PUBLICO en canal {canal_id}")


async def main():
    logger.info("👹 Pedir limosna iniciado...")
    token = get_discord_token()
    http = DiscordHTTP(token)

    await tarea_limosna(http)

    filas = await asyncio.to_thread(get_global_db().limpiar_interacciones_antiguas, 30)
    logger.info(f"🧹 Limpieza: {filas} registros borrados.")


if __name__ == "__main__":
    asyncio.run(main())
