"""
Core del bot de Discord — setup, eventos, tareas automáticas y procesamiento de mensajes.
Los comandos de cada rol están delegados a roles/*_discord.py.
La carga dinámica se gestiona desde discord_role_loader.py.
"""

import os
import json
import discord
import asyncio
import random
import time
from discord.ext import commands, tasks
from agent_engine import PERSONALIDAD, pensar, get_discord_token, AGENT_CFG
from agent_db import get_db_instance, set_current_server, get_active_server_name
from agent_logging import get_logger, update_log_file_path
from discord_utils import (
    get_server_name, get_db_for_server,
    get_greeting_enabled, check_chat_rate_limit,
    is_already_initialized, mark_as_initialized,
    acquire_connection_lock, acquire_process_lock,
    get_connection_lock, get_is_connected, set_is_connected,
    is_role_enabled_check,
)

logger = get_logger('discord')

# --- CONFIGURACIÓN ---

_discord_cfg = PERSONALIDAD.get("discord", {})
_cmd_prefix = _discord_cfg.get("command_prefix", "!")
_bot_display_name = PERSONALIDAD.get("bot_display_name", PERSONALIDAD.get("name", "Bot"))
_personality_name = PERSONALIDAD.get("name", "bot").lower()


def load_agent_config():
    config_path = os.path.join(os.path.dirname(__file__), 'agent_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando agent_config.json: {e}")
        return {"roles": {}}


agent_config = load_agent_config()

# --- INTENTS (solo los necesarios — fix seguridad: antes era Intents.all()) ---
intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix=_cmd_prefix, intents=intents)

# Verificar disponibilidad de POE2 para tarea automática
try:
    from roles.buscador_tesoros.poe2 import get_poe2_db_instance as _get_poe2_db
    _POE2_MODULE_AVAILABLE = True
except ImportError:
    _POE2_MODULE_AVAILABLE = False
    _get_poe2_db = None


def _is_poe2_available():
    if not _POE2_MODULE_AVAILABLE:
        return False
    return is_role_enabled_check("buscador_tesoros", agent_config)


# --- TAREAS AUTOMÁTICAS ---

@tasks.loop(hours=24)
async def limpieza_db():
    active_name = (get_active_server_name() or "").strip().lower()
    target_guild = None
    if active_name:
        for g in bot.guilds:
            if g.name.lower() == active_name:
                target_guild = g
                break
    if target_guild is None and bot.guilds:
        target_guild = bot.guilds[0]
    if target_guild is None:
        return
    db_instance = get_db_for_server(target_guild)
    filas = await asyncio.to_thread(db_instance.limpiar_interacciones_antiguas, 30)
    logger.info(f"🧹 Limpieza en {target_guild.name}: {filas} registros borrados.")


@tasks.loop(hours=1)
async def buscador_tesoros_task():
    """Ejecuta el buscador de tesoros automáticamente."""
    if not _is_poe2_available():
        return
    roles_config = load_agent_config().get("roles", {})
    interval_hours = roles_config.get("buscador_tesoros", {}).get("interval_hours", 1)
    if buscador_tesoros_task.hours != interval_hours:
        buscador_tesoros_task.change_interval(hours=interval_hours)
        logger.info(f"💎 Frecuencia buscador actualizada a {interval_hours}h")
    logger.info("💎 Iniciando búsqueda automática de tesoros...")
    for guild in bot.guilds:
        try:
            server_name = get_server_name(guild)
            db_poe2 = _get_poe2_db(server_name) if _get_poe2_db else None
            if not db_poe2 or not db_poe2.is_activo():
                continue
            await _ejecutar_buscador_para_servidor(guild)
        except Exception as e:
            logger.exception(f"Error en buscador para {guild.name}: {e}")
    logger.info("💎 Búsqueda automática completada")


async def _ejecutar_buscador_para_servidor(guild):
    """Ejecuta la lógica del buscador para un servidor."""
    try:
        from roles.buscador_tesoros.buscador_tesoros import main as buscador_main
        original_server = get_active_server_name()
        set_current_server(guild.name)
        await buscador_main()
        if original_server:
            set_current_server(original_server)
        logger.info(f"💎 Buscador completado para {guild.name}")
    except Exception as e:
        logger.exception(f"Error ejecutando buscador para {guild.name}: {e}")


async def set_mc_presence_if_enabled():
    """Establece el estado del bot si el rol MC está activo."""
    try:
        if is_role_enabled_check("mc", agent_config):
            mc_cfg = PERSONALIDAD.get("discord", {}).get("mc_messages", {})
            presence_message = mc_cfg.get("presence_status", "🎵 ¡MC disponible! Usa !mc play")
            await bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.listening, name=presence_message)
            )
            logger.info(f"🎵 Estado MC: {presence_message}")
    except Exception as e:
        logger.error(f"Error estableciendo estado MC: {e}")


# --- EVENTOS ---

_initialization_complete = False


@bot.event
async def on_ready():
    """Se ejecuta cuando el bot está listo."""
    global _initialization_complete, logger

    if is_already_initialized(_personality_name):
        logger.warning("Bot ya inicializado, ignorando on_ready duplicado")
        return

    process_sock = acquire_process_lock(_personality_name)
    if process_sock is None:
        return

    if is_already_initialized(_personality_name):
        process_sock.close()
        return

    lock_fd = acquire_connection_lock(_personality_name)
    if lock_fd is None:
        process_sock.close()
        return

    if is_already_initialized(_personality_name):
        lock_fd.close()
        process_sock.close()
        return

    with get_connection_lock():
        if get_is_connected():
            lock_fd.close()
            process_sock.close()
            return
        set_is_connected(True)

    mark_as_initialized(_personality_name)
    _initialization_complete = True
    await asyncio.sleep(0.2)

    if not get_is_connected():
        lock_fd.close()
        process_sock.close()
        return

    template = _discord_cfg.get("on_ready_message", "✅ {bot_name} operativo: {bot_user}")
    print(template.format(bot_name=_bot_display_name, bot_user=bot.user))

    # Elegir servidor activo
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
        set_current_server(active_guild.name)
        update_log_file_path(active_guild.name, _personality_name)
        logger = get_logger('discord')
        logger.info(f"📁 Servidor activo: '{active_guild.name}'")

    logger.info(f"🤖 Bot {_bot_display_name} conectado como {bot.user}")
    logger.info(f"🤖 Prefijo: {_cmd_prefix} | Intents: members={bot.intents.members}, presences={bot.intents.presences}")

    # Registrar comandos core (ayuda, saludos, insulto, test, rolekronk)
    from discord_core_commands import register_core_commands
    register_core_commands(bot, agent_config)

    # Registrar comandos de roles activados (MC, vigía, trilero, banquero, etc.)
    from discord_role_loader import register_all_role_commands
    await register_all_role_commands(bot, agent_config, PERSONALIDAD)

    logger.info(f"🤖 Total comandos registrados: {len(bot.commands)}")
    for cmd in bot.commands:
        logger.info(f"  → {cmd.name}")

    # Tareas automáticas
    if not limpieza_db.is_running():
        limpieza_db.start()
        logger.info("🧹 Tarea de limpieza iniciada")
    if _is_poe2_available() and not buscador_tesoros_task.is_running():
        buscador_tesoros_task.start()
        logger.info("💎 Tarea buscador de tesoros iniciada")

    await set_mc_presence_if_enabled()


@bot.event
async def on_guild_join(guild):
    """Se ejecuta cuando el bot se une a un nuevo servidor."""
    update_log_file_path(guild.name, _personality_name)
    logger.info(f"📁 Nuevo servidor: '{guild.name}'")

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
    """Se ejecuta cuando un nuevo usuario se une al servidor."""
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

    greeting_prompt = greeting_cfg.get("prompt",
        "Saluda brevemente al nuevo miembro {member_name} en el servidor {server_name}. Sé amigable.")
    greeting_context = greeting_prompt.format(member_name=member.display_name, server_name=member.guild.name)

    try:
        saludo = await asyncio.to_thread(pensar, greeting_context)
        await welcome_channel.send(f"🎉 {member.mention} {saludo}")
        logger.info(f"👋 Nuevo usuario {member.name} saludado en {member.guild.name}")
        db_instance = get_db_for_server(member.guild)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            member.id, member.name, "BIENVENIDA",
            "Usuario se unió al servidor",
            welcome_channel.id, member.guild.id,
            metadata={"saludo": saludo}
        )
    except Exception as e:
        logger.error(f"Error al saludar a {member.name}: {e}")
        fallback_msg = greeting_cfg.get("fallback", "¡Bienvenido al servidor!")
        await welcome_channel.send(f"🎉 {member.mention} {fallback_msg}")


@bot.event
async def on_presence_update(before, after):
    """Se ejecuta cuando un miembro cambia de offline a online."""
    if after.bot:
        return
    if not get_greeting_enabled(after.guild):
        return

    presence_cfg = _discord_cfg.get("member_presence", {})
    if not presence_cfg.get("enabled", False):
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
        return

    presence_prompt = presence_cfg.get("prompt",
        "Saluda brevemente a {member_name} que se acaba de conectar. Sé orco pero breve.")
    presence_context = presence_prompt.format(member_name=after.display_name)

    try:
        saludo = await asyncio.to_thread(pensar, presence_context)
        await after.send(f"👋 {saludo}")
        logger.info(f"🔄 DM de presencia enviado a {after.name}")
        on_presence_update._last_greetings[last_greeting_key] = current_time
        db_instance = get_db_for_server(after.guild)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            after.id, after.name, "PRESENCIA_DM",
            "Usuario pasó de offline a online (saludo por DM)",
            None, after.guild.id,
            metadata={"saludo": saludo}
        )
    except Exception as e:
        logger.error(f"Error al saludar presencia de {after.name}: {e}")
        fallback_msg = presence_cfg.get("fallback", "¡Bienvenido de vuelta!")
        try:
            await after.send(f"👋 {fallback_msg}")
        except Exception:
            pass


@bot.event
async def on_voice_state_update(member, before, after):
    """Desconecta al bot de voz si el canal queda vacío (funcionalidad MC)."""
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
    """Maneja errores de comandos."""
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        return
    logger.error(f"Error en comando: {error}")


@bot.event
async def on_message(message):
    """Maneja mensajes: comandos (!) y chat (menciones/DMs)."""
    if message.author == bot.user:
        return

    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # Solo procesar si es DM o mención directa
    if message.guild is None or bot.user.mentioned_in(message):
        await _process_chat_message(message)


async def _process_chat_message(message):
    """Procesa mensajes de chat normales (DMs y menciones) con rate limiting."""
    # Rate limiting por usuario (fix seguridad)
    if check_chat_rate_limit(message.author.id):
        return

    try:
        from agent_engine import pensar, incrementar_uso

        es_publico = message.guild is not None

        contexto_servidor = ""
        if message.guild:
            server_name = get_server_name(message.guild)
            contexto_servidor = f"Servidor: {message.guild.name} ({server_name})"

        roles_activos = []
        roles_config = AGENT_CFG.get("roles", {})
        if roles_config.get("buscar_anillo", {}).get("enabled", False):
            roles_activos.append("buscar_anillo")
        if roles_config.get("trilero", {}).get("enabled", False):
            roles_activos.append("trilero")

        # Usar nombre dinámico en vez de hardcoded "Kronk" (fix seguridad/portabilidad)
        rol_contextual = f"{_bot_display_name}"
        if roles_activos:
            rol_contextual += f" (roles activos: {', '.join(roles_activos)})"
        if contexto_servidor:
            rol_contextual += f" - {contexto_servidor}"

        historial_lista = []

        respuesta = pensar(
            rol_contextual=rol_contextual,
            contenido_usuario=message.content,
            historial_lista=historial_lista,
            es_publico=es_publico,
            logger=logger
        )

        incrementar_uso()

        if respuesta and respuesta.strip():
            await message.channel.send(respuesta)

    except Exception as e:
        logger.exception(f"Error procesando mensaje de chat: {e}")
        fallbacks = PERSONALIDAD.get("emergency_fallbacks", [])
        if fallbacks:
            await message.channel.send(random.choice(fallbacks))


# --- INICIO DEL BOT ---
if __name__ == "__main__":
    try:
        bot.run(get_discord_token())
    except KeyboardInterrupt:
        logger.info("👋 Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
