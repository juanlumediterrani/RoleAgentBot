"""
Discord bot core — setup, events, automatic tasks and message processing.
Role commands are delegated to roles/*_discord.py.
Dynamic loading is managed from discord_role_loader.py.
"""

import os
import sys
import json
import discord
import asyncio
import random
import time
from discord.ext import commands, tasks

# Add parent directory to Python path to import root modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_engine import PERSONALIDAD, think, get_discord_token, AGENT_CFG
from agent_db import set_current_server, get_active_server_name
from agent_logging import get_logger, update_log_file_path
from discord_bot.discord_utils import (
    get_db_for_server,
    get_greeting_enabled, check_chat_rate_limit,
    set_is_connected, is_role_enabled_check,
)

logger = get_logger('discord')

# --- CONFIGURATION ---

_discord_cfg = PERSONALIDAD.get("discord", {})
_cmd_prefix = _discord_cfg.get("command_prefix", "!")
_bot_display_name = PERSONALIDAD.get("bot_display_name", PERSONALIDAD.get("name", "Bot"))
_personality_name = PERSONALIDAD.get("name", "bot").lower()


def load_agent_config():
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'agent_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading agent_config.json: {e}")
        return {"roles": {}}


agent_config = load_agent_config()

# --- INTENTS (only required ones — security fix: was Intents.all()) ---
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=_cmd_prefix, intents=intents)

# Check POE2 availability for automatic task
try:
    from roles.treasure_hunter.poe2 import get_poe2_db_instance as _get_poe2_db
    _POE2_MODULE_AVAILABLE = True
except ImportError:
    _POE2_MODULE_AVAILABLE = False
    _get_poe2_db = None


def _is_poe2_available():
    if not _POE2_MODULE_AVAILABLE:
        return False
    return is_role_enabled_check("treasure_hunter", agent_config)


# --- AUTOMATIC TASKS ---

@tasks.loop(hours=24)
async def database_cleanup():
    active_server_key = (get_active_server_name() or "").strip()
    target_guild = None
    if active_server_key:
        active_key_lower = active_server_key.lower()
        for g in bot.guilds:
            if str(getattr(g, "id", "")) == active_server_key:
                target_guild = g
                break
            if getattr(g, "name", "").lower() == active_key_lower:
                target_guild = g
                break
    if target_guild is None and bot.guilds:
        target_guild = bot.guilds[0]
    if target_guild is None:
        return
    db_instance = get_db_for_server(target_guild)
    rows = await asyncio.to_thread(db_instance.limpiar_interacciones_antiguas, 30)
    from discord_utils import get_server_key
    server_key = get_server_key(target_guild)
    logger.info(f"🧹 Cleanup in {target_guild.name} ({server_key}): {rows} records deleted.")


@tasks.loop(hours=1)
async def treasure_hunter_task():
    """Run treasure hunter automatically."""
    if not _is_poe2_available():
        return
    roles_config = load_agent_config().get("roles", {})
    interval_hours = roles_config.get("treasure_hunter", {}).get("interval_hours", 1)
    if treasure_hunter_task.hours != interval_hours:
        treasure_hunter_task.change_interval(hours=interval_hours)
        logger.info(f"💎 Treasure hunter frequency updated to {interval_hours}h")
    logger.info("💎 Starting automatic treasure search...")
    for guild in bot.guilds:
        try:
            from discord_utils import get_server_key
            server_name = get_server_key(guild)
            db_poe2 = _get_poe2_db(server_name) if _get_poe2_db else None
            if not db_poe2 or not db_poe2.is_activo():
                continue
            await _ejecutar_buscador_para_servidor(guild)
        except Exception as e:
            logger.exception(f"Error en buscador para {guild.name}: {e}")
    logger.info("💎 Automatic search completed")


async def _ejecutar_buscador_para_servidor(guild):
    """Run treasure hunter logic for a server."""
    try:
        from roles.treasure_hunter.treasure_hunter import main as treasure_hunter_main
        original_server = get_active_server_name()
        from discord_utils import get_server_key
        set_current_server(get_server_key(guild))
        await treasure_hunter_main()
        if original_server:
            set_current_server(original_server)
        logger.info(f"💎 Treasure hunter completed for {guild.name}")
    except Exception as e:
        logger.exception(f"Error running treasure hunter for {guild.name}: {e}")


async def set_mc_presence_if_enabled():
    """Set bot presence status if MC role is active."""
    try:
        if is_role_enabled_check("mc", agent_config):
            mc_cfg = PERSONALIDAD.get("discord", {}).get("mc_messages", {})
            presence_message = mc_cfg.get("presence_status", "🎵 ¡MC disponible! Usa !mc play")
            await bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.listening, name=presence_message)
            )
            logger.info(f"🎵 MC status: {presence_message}")
    except Exception as e:
        logger.error(f"Error setting MC status: {e}")


set_is_connected(False)

# --- EVENTS ---

_commands_registered = False


async def _register_bot_commands():
    """Register core and role commands once during startup."""
    from discord_bot.discord_core_commands import register_core_commands
    from discord_bot.discord_role_loader import register_all_role_commands

    logger.info("� Importing core commands...")
    register_core_commands(bot, agent_config)
    logger.info(f"✅ Core commands registered: {len(bot.commands)}")

    logger.info("📦 Importing role commands...")
    await register_all_role_commands(bot, agent_config, PERSONALIDAD)
    logger.info(f"✅ Role commands registered: {len(bot.commands)}")


@bot.event
async def on_ready():
    """Runs when the bot is ready."""
    global _commands_registered, logger

    logger.info(f"� on_ready called - Current commands: {len(bot.commands)}")
    if bot.commands:
        logger.info(f"🔍 Existing commands: {[cmd.name for cmd in bot.commands]}")

    logger.info("🚀 Initializing bot...")

    if _commands_registered:
        logger.info("� Commands already registered via flag - skipping...")
        return

    logger.info("🚀 Starting command registration...")

    try:
        await _register_bot_commands()
    except Exception as e:
        if "already an existing command" in str(e):
            logger.info("📋 Commands already registered, skipping...")
        else:
            logger.error(f"❌ Error registering commands: {e}")
            return

    logger.info(f"🤖 Total commands registered: {len(bot.commands)}")
    for cmd in bot.commands:
        logger.info(f"  → {cmd.name}")

    _commands_registered = True

    # Choose active server
    preferred_guild = os.getenv("DISCORD_ACTIVE_GUILD", "").strip().lower()
    active_guild = None
    if preferred_guild:
        for g in bot.guilds:
            if g.name.lower() == preferred_guild:
                active_guild = g
                break
    if active_guild is None and bot.guilds:
        active_guild = bot.guilds[0]

    if active_guild is not None:
        from discord_utils import get_server_key
        server_key = get_server_key(active_guild)
        set_current_server(server_key)
        update_log_file_path(server_key, _personality_name)
        logger = get_logger('discord')
        logger.info(f"📁 Active server: '{active_guild.name}' ({server_key})")

    logger.info(f"🤖 Bot {_bot_display_name} conectado como {bot.user}")
    logger.info(f"🤖 Prefijo: {_cmd_prefix} | Intents: members={bot.intents.members}, presences={bot.intents.presences}")

    # Automatic tasks
    if not database_cleanup.is_running():
        database_cleanup.start()
        logger.info("🧹 DB cleanup task started")
    if _is_poe2_available() and not treasure_hunter_task.is_running():
        treasure_hunter_task.start()
        logger.info("💎 Treasure hunter task started")

    await set_mc_presence_if_enabled()


@bot.event
async def on_guild_join(guild):
    """Runs when the bot joins a new server."""
    from discord_utils import get_server_key
    server_key = get_server_key(guild)
    update_log_file_path(server_key, _personality_name)
    logger.info(f"📁 New server: '{guild.name}' ({server_key})")

    if is_role_enabled_check("mc", agent_config):
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                mc_cfg = PERSONALIDAD.get("discord", {}).get("mc_messages", {})
                msg = mc_cfg.get("welcome_message",
                    "🎵 **¡MC ha llegado!** 🎵\n"
                    "• `!mc play <canción>` - Reproduce música\n"
                    "• `!mc help` - Todos los comandos\n"
                    "🎤 **Conéctate a un canal de voz!**")
                await channel.send(msg)
                break


@bot.event
async def on_member_join(member):
    """Runs when a new user joins the server."""
    if member.bot:
        return
    if not get_greeting_enabled(member.guild):
        return

    greeting_cfg = _discord_cfg.get("member_greeting", {})
    if not greeting_cfg.get("enabled", True):
        return

    welcome_channel_name = greeting_cfg.get("welcome_channel", "general")
    welcome_channel = None
    for channel in member.guild.text_channels:
        if channel.name.lower() == welcome_channel_name.lower():
            welcome_channel = channel
            break
    if welcome_channel is None and member.guild.text_channels:
        welcome_channel = member.guild.text_channels[0]
    if welcome_channel is None:
        return

    try:
        from discord_utils import get_server_key
        saludo = await asyncio.to_thread(
            think,
            role_context=member.display_name,
            user_content=member.display_name,
            logger=logger,
            mission_prompt_key="prompt_welcome",
            user_id=member.id,
            user_name=member.name,
            server_name=get_server_key(member.guild),
            interaction_type="welcome",
        )
        await welcome_channel.send(f"🎉 {member.mention} {saludo}")
        logger.info(f"👋 New user {member.name} greeted in {member.guild.name}")
        db_instance = get_db_for_server(member.guild)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            member.id, member.name, "WELCOME",
            "User joined the server",
            welcome_channel.id, member.guild.id,
            metadata={"response": saludo, "greeting": saludo, "respuesta": saludo, "saludo": saludo}
        )
    except Exception as e:
        logger.error(f"Error greeting {member.name}: {e}")
        fallback_msg = greeting_cfg.get("fallback", "¡Bienvenido al servidor!")
        await welcome_channel.send(f"🎉 {member.mention} {fallback_msg}")


@bot.event
async def on_presence_update(before, after):
    """Runs when a member goes from offline to online."""
    if after.bot:
        return
    if not get_greeting_enabled(after.guild):
        return

    presence_cfg = _discord_cfg.get("member_presence", {})
    if not presence_cfg.get("enabled", False):
        logger.info(f"Presence greetings disabled by config for guild={after.guild.name}")
        return

    before_status = before.status if before.status else discord.Status.offline
    after_status = after.status if after.status else discord.Status.offline
    if before_status != discord.Status.offline or after_status != discord.Status.online:
        return

    current_time = time.time()
    last_greeting_key = f"presence_greeting_{after.id}"
    if not hasattr(on_presence_update, '_last_greetings'):
        on_presence_update._last_greetings = {}
    if current_time - on_presence_update._last_greetings.get(last_greeting_key, 0) < 300:
        logger.info(f"Presence greeting skipped due to cooldown for user={after.name} guild={after.guild.name}")
        return

    try:
        from discord_utils import get_server_key
        saludo = await asyncio.to_thread(
            think,
            role_context=after.display_name,
            user_content=after.display_name,
            logger=logger,
            mission_prompt_key="prompt_greet",
            user_id=after.id,
            user_name=after.name,
            server_name=get_server_key(after.guild),
            interaction_type="greet",
        )
        await after.send(f"👋 {saludo}")
        logger.info(f"🔄 Presence DM sent to {after.name}")
        on_presence_update._last_greetings[last_greeting_key] = current_time
        db_instance = get_db_for_server(after.guild)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            after.id, after.name, "PRESENCE_DM",
            "User went from offline to online (DM greeting)",
            None, after.guild.id,
            metadata={"response": saludo, "greeting": saludo, "respuesta": saludo, "saludo": saludo}
        )
    except discord.errors.Forbidden as e:
        logger.warning(f"Cannot DM presence greeting to {after.name} (Forbidden): {e}")
        fallback_msg = presence_cfg.get("fallback", "¡Bienvenido de vuelta!")
        try:
            await after.send(f"👋 {fallback_msg}")
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Error greeting presence of {after.name}: {e}")
        fallback_msg = presence_cfg.get("fallback", "¡Bienvenido de vuelta!")
        try:
            await after.send(f"👋 {fallback_msg}")
        except Exception:
            pass


@bot.event
async def on_voice_state_update(member, before, after):
    """Disconnect the bot from voice if the channel is empty (MC feature)."""
    if member.bot:
        return
    for vc in list(bot.voice_clients):
        if not vc.is_connected():
            continue
        human_users = [m for m in vc.channel.members if not m.bot]
        if len(human_users) == 0:
            await asyncio.sleep(30)
            if vc.is_connected():
                current_users = [m for m in vc.channel.members if not m.bot]
                if len(current_users) == 0:
                    guild = vc.guild
                    await vc.disconnect()
                    try:
                        mc_cfg = PERSONALIDAD.get("discord", {}).get("mc_messages", {})
                        msg = mc_cfg.get("voice_leave_empty", "👋 Canal vacío, me voy!")
                        canal = next(
                            (c for c in guild.text_channels if c.permissions_for(guild.me).send_messages),
                            None
                        )
                        if canal:
                            await canal.send(msg)
                    except Exception:
                        pass


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors."""
    logger.error(f"Command error: {error}")
    if isinstance(error, commands.CommandNotFound):
        logger.warning(f"Command not found: {ctx.message.content}")
        logger.info(f"Available commands: {[cmd.name for cmd in bot.commands]}")
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        return


@bot.event
async def on_message(message):
    """Handle messages: commands (!) and chat (mentions/DMs)."""
    if message.author == bot.user:
        return

    # Debug logging
    if message.content.startswith(bot.command_prefix):
        logger.info(f"🔍 Command detected: {message.content}")
        logger.info(f"🔍 Available commands: {[cmd.name for cmd in bot.commands]}")
        await bot.process_commands(message)
        return

    # Only process if DM or direct mention
    if message.guild is None or bot.user.mentioned_in(message):
        await _process_chat_message(message)


async def _process_chat_message(message):
    """Process normal chat messages (DMs and mentions) with rate limiting."""
    # Rate limiting per user (security fix)
    if check_chat_rate_limit(message.author.id):
        return

    try:
        from agent_engine import think

        is_public = message.guild is not None

        server_context = ""
        server_name = "default"
        if message.guild:
            from discord_utils import get_server_key
            server_name = get_server_key(message.guild)
            server_context = f"Server: {message.guild.name} ({server_name})"

        active_roles = []
        roles_config = AGENT_CFG.get("roles", {})
        # Only show roles that inject prompts for context
        if roles_config.get("beggar", {}).get("enabled", False):
            active_roles.append("beggar")
        if roles_config.get("ring", {}).get("enabled", False):
            active_roles.append("ring")

        # Use dynamic name instead of hardcoded (security/portability fix)
        contextual_role = f"{_bot_display_name}"
        if active_roles:
            contextual_role += f" (active roles: {', '.join(active_roles)})"
        if server_context:
            contextual_role += f" - {server_context}"

        response = think(
            role_context=contextual_role,
            user_content=message.content,
            is_public=is_public,
            logger=logger,
            user_id=message.author.id,
            user_name=message.author.name,
            server_name=server_name,
            interaction_type="mention" if is_public else "chat",
        )

        # Register interaction in database
        db_instance = get_db_for_server(message.guild) if message.guild else get_db_for_server(None)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            message.author.id, message.author.name, "CHAT",
            message.content,
            message.channel.id if message.channel else None,
            message.guild.id if message.guild else None,
            {"respuesta": response, "publico": is_public}
        )

        if response and response.strip():
            await message.channel.send(response)

    except Exception as e:
        logger.exception(f"Error processing chat message: {e}")
        fallbacks = PERSONALIDAD.get("emergency_fallbacks", [])
        if fallbacks:
            await message.channel.send(random.choice(fallbacks))


# --- BOT STARTUP ---
if __name__ == "__main__":
    try:
        bot.run(get_discord_token())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
