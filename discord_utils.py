"""
Utilidades compartidas para el bot de Discord.
Funciones de acceso a BD por servidor, helpers de permisos y envío de mensajes.
"""

import os
import time
import hashlib
from datetime import datetime, timedelta
from agent_logging import get_logger
from agent_db import get_db_instance, set_current_server, get_active_server_name

logger = get_logger('discord_utils')

# --- ACCESO A BD POR SERVIDOR ---

def get_server_name(guild) -> str:
    """Obtiene un nombre sanitizado para el servidor."""
    if guild is None:
        active = get_active_server_name()
        if active:
            return active
        return "default"
    return guild.name.lower().replace(' ', '_').replace('-', '_')


def get_db_for_server(guild):
    """Obtiene instancia de BD para un servidor específico."""
    server_name = get_server_name(guild)
    return get_db_instance(server_name)


def get_role_db_for_server(guild, get_db_func, available_flag):
    """Helper genérico para obtener BD de un rol para un servidor."""
    if not available_flag:
        return None
    server_name = get_server_name(guild)
    return get_db_func(server_name)


# --- HELPERS DE PERMISOS ---

def is_admin(ctx) -> bool:
    """Verifica si el usuario es administrador o tiene manage_guild."""
    if not ctx.guild:
        return False
    perms = ctx.author.guild_permissions
    return perms.administrator or perms.manage_guild


def is_role_enabled_check(role_name, agent_config):
    """Verifica si un rol está activado (env var > config JSON)."""
    env_var = os.getenv(f"{role_name.upper()}_ENABLED", "").lower()
    if env_var:
        return env_var == "true"
    return agent_config.get("roles", {}).get(role_name, {}).get("enabled", False)


# --- HELPERS DE ENVÍO ---

async def send_dm_or_channel(ctx, content, confirm_msg="📩 Información enviada por mensaje privado."):
    """Envía contenido por DM si es posible, si no al canal. Maneja mensajes >2000 chars."""
    import discord
    try:
        if len(content) > 2000:
            partes = [content[i:i+1900] for i in range(0, len(content), 1900)]
            for parte in partes:
                await ctx.author.send(parte)
        else:
            await ctx.author.send(content)
        if ctx.guild:
            await ctx.send(confirm_msg)
    except discord.errors.Forbidden:
        if len(content) > 2000:
            partes = [content[i:i+1900] for i in range(0, len(content), 1900)]
            for parte in partes:
                await ctx.send(parte)
        else:
            await ctx.send(content[:2000])


async def send_embed_dm_or_channel(ctx, embed, confirm_msg="📩 Información enviada por mensaje privado."):
    """Envía un embed por DM si es posible, si no al canal."""
    import discord
    try:
        await ctx.author.send(embed=embed)
        if ctx.guild:
            await ctx.send(confirm_msg)
    except discord.errors.Forbidden:
        await ctx.send(embed=embed)


# --- CONTROL DE EVENTOS Y DUPLICADOS ---

_event_cache = {}
_cache_ttl = timedelta(seconds=5)
_last_command_time = {}

# Rate limiting para chat LLM
_chat_rate_limit = {}
CHAT_COOLDOWN_SECONDS = 3


def get_event_key(event_type, ctx_or_message):
    """Genera una clave única para cada evento."""
    if hasattr(ctx_or_message, 'id'):
        key_data = f"{event_type}_{ctx_or_message.id}_{ctx_or_message.author.id}"
    else:
        key_data = f"{event_type}_{str(ctx_or_message)}"
    return hashlib.sha256(key_data.encode()).hexdigest()[:16]


def is_event_processed(event_key):
    """Verifica si un evento ya fue procesado."""
    now = datetime.now()
    if event_key in _event_cache:
        if now - _event_cache[event_key] < _cache_ttl:
            return True
        else:
            del _event_cache[event_key]
    return False


def mark_event_processed(event_key):
    """Marca un evento como procesado."""
    _event_cache[event_key] = datetime.now()


def is_duplicate_command(ctx, command_name):
    """Verifica si el comando ya fue ejecutado recientemente para evitar duplicados."""
    try:
        if ctx.guild is None:
            channel_id = ctx.channel.id
        else:
            channel_id = ctx.guild.id

        key = f"{command_name}_{channel_id}"
        now = time.time()

        if key in _last_command_time:
            if now - _last_command_time[key] < 1.0:
                return True

        _last_command_time[key] = now
        return False
    except Exception as e:
        logger.error(f"Error verificando comando duplicado: {e}")
        return False


def check_chat_rate_limit(user_id):
    """Verifica rate limit para mensajes de chat LLM. Retorna True si está limitado."""
    now = time.time()
    if user_id in _chat_rate_limit:
        if now - _chat_rate_limit[user_id] < CHAT_COOLDOWN_SECONDS:
            return True
    _chat_rate_limit[user_id] = now
    return False


# --- CONFIGURACIÓN DINÁMICA DE SALUDOS ---

_greeting_config = {}


def should_enable_greetings(guild) -> bool:
    """Determina si los saludos deben estar activados según tamaño del servidor."""
    guild_id = str(guild.id)
    if guild_id in _greeting_config:
        return _greeting_config[guild_id].get('enabled', False)

    member_count = len([m for m in guild.members if not m.bot])
    auto_enable = member_count <= 30

    _greeting_config[guild_id] = {
        'enabled': auto_enable,
        'auto_detected': True,
        'member_count': member_count
    }

    logger.info(f"Servidor {guild.name}: {member_count} miembros, saludos {'activados' if auto_enable else 'desactivados'} por tamaño")
    return auto_enable


def set_greeting_enabled(guild, enabled: bool):
    """Establece manualmente el estado de los saludos para un servidor."""
    guild_id = str(guild.id)
    if guild_id not in _greeting_config:
        _greeting_config[guild_id] = {}

    _greeting_config[guild_id]['enabled'] = enabled
    _greeting_config[guild_id]['auto_detected'] = False
    _greeting_config[guild_id]['manual_override'] = True

    logger.info(f"Saludos {'activados' if enabled else 'desactivados'} manualmente en {guild.name}")


def get_greeting_enabled(guild) -> bool:
    """Obtiene el estado actual de los saludos para un servidor."""
    return should_enable_greetings(guild)


# --- BLOQUEO DE PROCESO ---

import threading
import fcntl
import tempfile

_connection_lock = threading.Lock()
_is_connected = False
_lock_file_path = None


def acquire_connection_lock(personality_name="bot"):
    """Adquiere un bloqueo a nivel de sistema para evitar múltiples instancias."""
    global _lock_file_path

    try:
        _lock_file_path = tempfile.NamedTemporaryFile(
            delete=False, prefix=f'discord_bot_lock_{personality_name}_'
        )
        _lock_file_path.close()

        lock_fd = open(_lock_file_path.name, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

        logger.info(f"Bloqueo adquirido: {_lock_file_path.name}")
        return lock_fd
    except (IOError, OSError) as e:
        if e.errno == 11:
            logger.warning("Otra instancia del bot ya está corriendo")
            if _lock_file_path and os.path.exists(_lock_file_path.name):
                os.unlink(_lock_file_path.name)
            return None
        logger.error(f"Error adquiriendo bloqueo: {e}")
        return None


def acquire_process_lock(personality_name="bot"):
    """Adquiere bloqueo a nivel de proceso usando socket Unix."""
    import socket
    socket_path = f"/tmp/discord_bot_{personality_name}.sock"
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(socket_path)
        logger.info(f"Bloqueo de proceso adquirido: {socket_path}")
        return sock
    except (OSError, socket.error) as e:
        if e.errno == 98:
            logger.warning("Bot ya está corriendo (bloqueo de proceso)")
            return None
        logger.error(f"Error adquiriendo bloqueo de proceso: {e}")
        return None


def is_already_initialized(personality_name="bot"):
    """Verifica si el bot ya fue inicializado usando archivo de estado."""
    state_file = f"/tmp/discord_bot_{personality_name}_initialized.flag"
    try:
        return os.path.exists(state_file)
    except Exception:
        return False


def mark_as_initialized(personality_name="bot"):
    """Marca el bot como inicializado."""
    state_file = f"/tmp/discord_bot_{personality_name}_initialized.flag"
    try:
        with open(state_file, 'w') as f:
            f.write("initialized")
        logger.info("Bot marcado como inicializado")
    except Exception as e:
        logger.error(f"Error marcando inicialización: {e}")


def get_connection_lock():
    """Retorna el lock de conexión threading."""
    return _connection_lock


def get_is_connected():
    global _is_connected
    return _is_connected


def set_is_connected(value):
    global _is_connected
    _is_connected = value
