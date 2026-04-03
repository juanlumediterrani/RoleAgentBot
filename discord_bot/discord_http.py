"""
Discord REST API communication module.
Allows sending messages, DMs, and reading guild data
without establishing a WebSocket connection, avoiding token conflicts
with the main bot (`agent_discord.py`).
"""

import asyncio
import aiohttp

from agent_logging import get_logger

logger = get_logger('discord_http')

BASE = "https://discord.com/api/v10"


class DiscordHTTP:
    """Discord REST client that does not require a WebSocket connection."""

    def __init__(self, token: str):
        self._token = token
        self._headers = {
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "RoleAgentBot/1.0 (github.com/roleagentbot)",
        }

    async def get_guilds(self) -> list[dict]:
        """Return the list of guilds where the bot is present."""
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{BASE}/users/@me/guilds", headers=self._headers) as r:
                if r.status >= 400:
                    logger.warning(f"get_guilds error {r.status}: {await r.text()}")
                    return []
                return await r.json()

    async def get_guild_members(self, guild_id: int, limit: int = 1000) -> list[dict]:
        """Return guild members (requires the GUILD_MEMBERS intent to be enabled)."""
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
        """Return the channels of a guild."""
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
        """Return user information by ID."""
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{BASE}/users/{user_id}", headers=self._headers) as r:
                if r.status >= 400:
                    return None
                return await r.json()

    async def send_dm(self, user_id: int, content: str, embed: dict = None, components: list = None) -> bool:
        """Create a DM channel and send a private message to a user."""
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{BASE}/users/@me/channels",
                headers=self._headers,
                json={"recipient_id": str(user_id)},
            ) as r:
                if r.status >= 400:
                    logger.warning(f"send_dm: could not create DM channel for {user_id} ({r.status})")
                    return False
                dm_data = await r.json()
                channel_id = dm_data.get("id")

            if not channel_id:
                return False

            # Build message payload
            payload = {}
            if content:
                payload["content"] = content
            if embed:
                payload["embeds"] = [embed]
            if components:
                payload["components"] = components
            
            if not payload:  # Nothing to send
                return False

            async with s.post(
                f"{BASE}/channels/{channel_id}/messages",
                headers=self._headers,
                json=payload,
            ) as r:
                if r.status >= 400:
                    logger.warning(f"send_dm: error sending message to {user_id} ({r.status})")
                    return False
                return True

    async def send_channel_message(self, channel_id: int, content: str, embed: dict = None, components: list = None) -> bool:
        """Send a message to a text channel."""
        async with aiohttp.ClientSession() as s:
            # Build message payload
            payload = {}
            if content:
                payload["content"] = content
            if embed:
                payload["embeds"] = [embed]
            if components:
                payload["components"] = components
            
            if not payload:  # Nothing to send
                return False

            async with s.post(
                f"{BASE}/channels/{channel_id}/messages",
                headers=self._headers,
                json=payload,
            ) as r:
                if r.status >= 400:
                    logger.warning(f"send_channel_message({channel_id}) error {r.status}: {await r.text()}")
                    return False
                return True
