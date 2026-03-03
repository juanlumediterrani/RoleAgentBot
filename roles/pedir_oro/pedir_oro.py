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

logger = get_logger('oro')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "pedir_oro",
    "system_prompt_addition": "MISION ACTIVA - PEDIR ORO: Necesitas oro para traer a tu familia orca contigo. Si ya pediste oro recientemente, RECUERDALO y mencionalo."
}

# Lista de razones variadas para pedir oro
RAZONES_PEDIR_ORO = [
    "para traer a tu familia orca contigo",
    "para komprar armas nuevas y aser la guerra",
    "para pagar tributo al jefe orko y ke no te mate",
    "porke tienes ambre y no keres komer karne umana otra ves",
    "para komprar armadura nueva porke la tuya esta rota",
    "porke perdiste todo tu oro jugando kon otros orkos",
    "para komprar un lobo gigante ke te ayude en batallas",
    "porke keres aser una fiesta orca kon komida y bebida",
    "para arreglar tu kasa ke se esta kayendo",
    "porke otros orkos te robaron y nesesitas rekuperar",
    "para komprar veneno para tus flechas",
    "porke keres impresionar a una orka ke te gusta",
    "para pagar deudas kon orkos peligrosos",
    "porke keres komprar un jabalí de guerra"
]


async def tarea_pedir_oro(http: DiscordHTTP):
    """Pide oro por privado o en público, registrando el contexto."""
    logger.info("💰 Iniciando ronda de peticiones de oro...")

    guilds = await http.get_guilds()
    for guild_data in guilds:
        es_privado = random.choice([True, False])
        if es_privado:
            await _pedir_oro_privado(http, guild_data)
        else:
            await _pedir_oro_publico(http, guild_data)


async def _pedir_oro_privado(http: DiscordHTTP, guild_data: dict):
    """Pide oro por mensaje privado."""
    guild_id = int(guild_data["id"])
    miembros = await http.get_guild_members(guild_id)
    miembros_humanos = [m for m in miembros if not m.get("user", {}).get("bot", False)]
    if not miembros_humanos:
        return

    objetivo = random.choice(miembros_humanos)
    user_id = int(objetivo["user"]["id"])
    username = objetivo["user"].get("username", str(user_id))

    # Limitar: max 2 ORO_DM por servidor al día
    cuenta_dm = await asyncio.to_thread(
        get_global_db().contar_interacciones_tipo_ultimo_dia, "ORO_DM", guild_id
    )
    if cuenta_dm >= 2:
        logger.info(f"🔕 [Límite] Ya hubo {cuenta_dm} ORO_DM hoy en servidor {guild_id}, saltando.")
        return

    # Verificar si usuario ha recibido petición recientemente (últimas 12h)
    ha_pedido_recientemente = await asyncio.to_thread(
        get_global_db().usuario_ha_pedido_tipo_recientemente, user_id, "ORO_DM", 12
    )
    if not ha_pedido_recientemente:
        razon = random.choice(RAZONES_PEDIR_ORO)
        res = await asyncio.to_thread(pensar, f"Pídele oro a {username}: {razon}, convencele.")

        if await http.send_dm(user_id, f"👹 {res}"):
            await asyncio.to_thread(
                get_global_db().registrar_interaccion,
                user_id, username, "ORO_DM",
                "Te pedí oro por privado", None, guild_id,
                metadata={"respuesta": res, "rol": "pedir_oro"}
            )
            logger.info(f"✅ ORO_DM enviado a {username}")
        else:
            logger.warning(f"⚠️ No se pudo enviar ORO_DM a {username}")


async def _pedir_oro_publico(http: DiscordHTTP, guild_data: dict):
    """Pide oro en canal público."""
    guild_id = int(guild_data["id"])

    # Limitar: max 4 ORO_PUBLICO por servidor al día
    cuenta_publico = await asyncio.to_thread(
        get_global_db().contar_interacciones_tipo_ultimo_dia, "ORO_PUBLICO", guild_id
    )
    if cuenta_publico >= 4:
        logger.info(f"🔕 [Límite] Ya hubo {cuenta_publico} ORO_PUBLICO hoy en servidor {guild_id}, saltando.")
        return

    # Buscar canal general
    canales = await http.get_guild_channels(guild_id)
    canal = next((c for c in canales if c.get("name") == "general" and c.get("type") == 0), None)
    if canal is None:
        canal = next((c for c in canales if c.get("type") == 0), None)
    if canal is None:
        return

    canal_id = int(canal["id"])
    razon = random.choice(RAZONES_PEDIR_ORO)
    res = await asyncio.to_thread(
        pensar,
        f"Estas gritando en el centro del pueblo para que los humanos te den oro {razon}. Escribe un mensaje para convencerlos, usando tu personalidad de orco.",
        "", [], True
    )

    if await http.send_channel_message(canal_id, f"📢 **DONATIVOS PARA LOS VERDES:** {res}"):
        await asyncio.to_thread(
            get_global_db().registrar_interaccion,
            str(canal_id), "CANAL_PUBLICO", "ORO_PUBLICO",
            "Grito de oro en el canal", canal_id, guild_id,
            metadata={"respuesta": res, "rol": "pedir_oro"}
        )
        logger.info(f"✅ ORO_PUBLICO enviado en canal {canal.get('name', canal_id)}")
    else:
        logger.warning(f"⚠️ No se pudo enviar ORO_PUBLICO en canal {canal_id}")


async def main():
    logger.info("👹 Pedir oro iniciado...")
    token = get_discord_token()
    http = DiscordHTTP(token)

    await tarea_pedir_oro(http)

    filas = await asyncio.to_thread(get_global_db().limpiar_interacciones_antiguas, 30)
    logger.info(f"🧹 Limpieza: {filas} registros borrados.")


if __name__ == "__main__":
    asyncio.run(main())
