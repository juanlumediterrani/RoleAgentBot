"""
Módulo de comunicación con Discord via REST API.
Permite enviar mensajes, DMs y obtener datos de servidores
SIN establecer una conexión WebSocket, evitando conflictos de token
con el bot principal (agent_discord.py).
"""

import asyncio
import aiohttp
from agent_logging import get_logger

logger = get_logger('discord_http')

BASE = "https://discord.com/api/v10"


class DiscordHTTP:
    """Cliente REST de Discord que no requiere WebSocket."""

    def __init__(self, token: str):
        self._token = token
        self._headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "RoleAgentBot/1.0 (github.com/roleagentbot)",
        }

    async def get_guilds(self) -> list[dict]:
        """Obtiene la lista de servidores donde está el bot."""
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{BASE}/users/@me/guilds", headers=self._headers) as r:
                if r.status >= 400:
                    logger.warning(f"get_guilds error {r.status}: {await r.text()}")
                    return []
                return await r.json()

    async def get_guild_members(self, guild_id: int, limit: int = 1000) -> list[dict]:
        """Obtiene los miembros de un servidor (requiere GUILD_MEMBERS intent habilitado)."""
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{BASE}/guilds/{guild_id}/members?limit={limit}",
                headers=self._headers,
            ) as r:
                if r.status >= 400:
                    logger.warning(f"get_guild_members({guild_id}) error {r.status}: {await r.text()}")
                    return []
                return await r.json()

    async def get_guild_channels(self, guild_id: int) -> list[dict]:
        """Obtiene los canales de un servidor."""
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{BASE}/guilds/{guild_id}/channels",
                headers=self._headers,
            ) as r:
                if r.status >= 400:
                    logger.warning(f"get_guild_channels({guild_id}) error {r.status}: {await r.text()}")
                    return []
                return await r.json()

    async def fetch_user(self, user_id: int) -> dict | None:
        """Obtiene información de un usuario por ID."""
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{BASE}/users/{user_id}", headers=self._headers) as r:
                if r.status >= 400:
                    return None
                return await r.json()

    async def send_dm(self, user_id: int, content: str) -> bool:
        """Crea un canal DM y envía un mensaje privado a un usuario."""
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{BASE}/users/@me/channels",
                headers=self._headers,
                json={"recipient_id": str(user_id)},
            ) as r:
                if r.status >= 400:
                    logger.warning(f"send_dm: no se pudo crear canal DM para {user_id} ({r.status})")
                    return False
                dm_data = await r.json()
                channel_id = dm_data.get("id")

            if not channel_id:
                return False

            async with s.post(
                f"{BASE}/channels/{channel_id}/messages",
                headers=self._headers,
                json={"content": content},
            ) as r:
                if r.status >= 400:
                    logger.warning(f"send_dm: error enviando mensaje a {user_id} ({r.status})")
                    return False
                return True

    async def send_channel_message(self, channel_id: int, content: str) -> bool:
        """Envía un mensaje a un canal de texto."""
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{BASE}/channels/{channel_id}/messages",
                headers=self._headers,
                json={"content": content},
            ) as r:
                if r.status >= 400:
                    logger.warning(f"send_channel_message({channel_id}) error {r.status}: {await r.text()}")
                    return False
                return True
