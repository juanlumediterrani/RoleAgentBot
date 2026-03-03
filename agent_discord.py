import os
import json
import discord
import asyncio
import re
import time
import threading
from collections import defaultdict
from discord.ext import commands, tasks
from agent_engine import PERSONALIDAD, pensar, get_discord_token
from agent_db import get_db_instance
from agent_logging import get_logger, update_log_file_path
from agent_db import set_current_server, get_active_server_name

# Importar sistema de mensajes del vigía
try:
    from roles.vigia_noticias.vigia_messages import get_message
except ImportError:
    # Fallback si no está disponible
    def get_message(key, **kwargs):
        return "✅ Te he enviado la ayuda por mensaje privado 📩"

# Cargar configuración de roles
def load_agent_config():
    config_path = os.path.join(os.path.dirname(__file__), 'agent_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando agent_config.json: {e}")
        return {"roles": {}}

agent_config = load_agent_config()

# Importar base de datos del vigía
try:
    from roles.vigia_noticias.db_role_vigia import get_vigia_db_instance
    module_available = True
except ImportError:
    module_available = False
    get_vigia_db_instance = None

# Importar base de datos de POE2
try:
    from roles.buscador_tesoros.poe2 import get_poe2_db_instance
    poe2_module_available = True
except ImportError:
    poe2_module_available = False
    get_poe2_db_instance = None

# Verificar si el rol vigia_noticias está activado (prioridad a variables de entorno)
import os
vigia_role_enabled = os.getenv("VIGIA_NOTICIAS_ENABLED", "false").lower() == "true"
if not vigia_role_enabled:
    # Fallback a configuración JSON si no hay variable de entorno
    vigia_role_enabled = agent_config.get("roles", {}).get("vigia_noticias", {}).get("enabled", False)

# VIGIA_AVAILABLE solo es True si el módulo se puede importar Y el rol está activado
VIGIA_AVAILABLE = module_available and vigia_role_enabled

# Verificar si el rol buscador_tesoros está activado
buscador_role_enabled = os.getenv("BUSCADOR_TESOROS_ENABLED", "false").lower() == "true"
if not buscador_role_enabled:
    # Fallback a configuración JSON si no hay variable de entorno
    buscador_role_enabled = agent_config.get("roles", {}).get("buscador_tesoros", {}).get("enabled", False)

# POE2_AVAILABLE solo es True si el módulo se puede importar Y el rol buscador_tesoros está activado
POE2_AVAILABLE = poe2_module_available and buscador_role_enabled

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

def get_vigia_db_for_server(guild):
    """Obtiene instancia de BD del vigía para un servidor específico."""
    if not VIGIA_AVAILABLE:
        return None
    server_name = get_server_name(guild)
    return get_vigia_db_instance(server_name)

def get_poe2_db_for_server(guild):
    """Obtiene instancia de BD de POE2 para un servidor específico."""
    if not POE2_AVAILABLE:
        return None
    server_name = get_server_name(guild)
    return get_poe2_db_instance(server_name)

def get_oro_db_for_server(guild):
    """Obtiene instancia de BD de oro para un servidor específico."""
    if not ORO_DB_AVAILABLE:
        return None
    server_name = get_server_name(guild)
    return get_oro_db_instance(server_name)

logger = get_logger('discord')

# Importar clases del Vigía si está disponible
try:
    from roles.vigia_noticias.vigia_commands import VigiaCommands, COMANDOS_VIGIA, COMANDOS_VIGIA_CANAL
    VIGIA_COMMANDS_AVAILABLE = True
    logger.info("📡 [DISCORD] Comandos del Vigía importados correctamente")
except ImportError as e:
    VIGIA_COMMANDS_AVAILABLE = False
    logger.warning(f"⚠️ [DISCORD] No se pudieron importar comandos del Vigía: {e}")

# Importar clases del MC si están disponibles (requiere yt_dlp y PyNaCl)
try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "roles", "mc"))
    from roles.mc.mc_commands import MCCommands, COMANDOS_MC
    MC_COMMANDS_AVAILABLE = True
    logger.info("🎵 [DISCORD] Comandos del MC importados correctamente")
except ImportError as e:
    MC_COMMANDS_AVAILABLE = False
    MCCommands = None
    COMANDOS_MC = {}
    logger.warning(f"⚠️ [DISCORD] No se pudieron importar comandos del MC (yt_dlp/PyNaCl no instalados): {e}")

# Importar base de datos de oro
try:
    from roles.trilero.subroles.pedir_oro.db_oro import get_oro_db_instance
    ORO_DB_AVAILABLE = True
    logger.info("💰 [DISCORD] Base de datos de oro importada correctamente")
except ImportError as e:
    ORO_DB_AVAILABLE = False
    logger.warning(f"⚠️ [DISCORD] No se pudo importar base de datos de oro: {e}")

intents = discord.Intents.all()

_discord_cfg = PERSONALIDAD.get("discord", {})
_cmd_prefix = _discord_cfg.get("command_prefix", "!")
_insult_cfg = _discord_cfg.get("insult_command", {})
_insult_name = _insult_cfg.get("name", "insulta")
_bot_display_name = PERSONALIDAD.get("bot_display_name", PERSONALIDAD.get("name", "Bot"))
_personality_name = PERSONALIDAD.get("name", "bot").lower()

bot = commands.Bot(command_prefix=_cmd_prefix, intents=intents)

# --- TAREAS AUTOMÁTICAS ---

@tasks.loop(hours=24)
async def limpieza_db():
    # Limpiar base de datos SOLO del servidor activo
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

# --- CONFIGURACIÓN DINÁMICA DE SALUDOS ---
# Variable global para tracking de configuración por servidor
if not hasattr(bot, '_greeting_config'):
    bot._greeting_config = {}

def should_enable_greetings(guild) -> bool:
    """Determina si los saludos deben estar activados según tamaño del servidor."""
    # Si ya hay configuración guardada para este servidor, usarla
    guild_id = str(guild.id)
    if guild_id in bot._greeting_config:
        return bot._greeting_config[guild_id].get('enabled', False)
    
    # Si no, decidir según tamaño del servidor
    member_count = len([m for m in guild.members if not m.bot])
    auto_enable = member_count <= 30
    
    # Guardar configuración inicial
    bot._greeting_config[guild_id] = {
        'enabled': auto_enable,
        'auto_detected': True,
        'member_count': member_count
    }
    
    logger.info(f"🔧 [DISCORD] Servidor {guild.name}: {member_count} miembros, saludos {'activados' if auto_enable else 'desactivados'} por tamaño")
    return auto_enable

def set_greeting_enabled(guild, enabled: bool):
    """Establece manualmente el estado de los saludos para un servidor."""
    guild_id = str(guild.id)
    if guild_id not in bot._greeting_config:
        bot._greeting_config[guild_id] = {}
    
    bot._greeting_config[guild_id]['enabled'] = enabled
    bot._greeting_config[guild_id]['auto_detected'] = False
    bot._greeting_config[guild_id]['manual_override'] = True
    
    logger.info(f"🔧 [DISCORD] Saludos {'activados' if enabled else 'desactivados'} manualmente en {guild.name}")

def get_greeting_enabled(guild) -> bool:
    """Obtiene el estado actual de los saludos para un servidor."""
    return should_enable_greetings(guild)

# --- COMANDOS DE CONTROL DE SALUDOS ---

async def _cmd_saluda_toggle(ctx, enabled: bool):
    """Comando genérico para activar/desactivar saludos de presencia."""
    # Obtener mensajes personalizados
    role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
    
    # Verificar permisos (solo admins o mods)
    if not ctx.author.guild_permissions.administrator and not ctx.author.guild_permissions.manage_guild:
        await ctx.send(role_cfg.get("admin_permission", "❌ Solo administradores pueden modificar los saludos de presencia."))
        return
    
    set_greeting_enabled(ctx.guild, enabled)
    
    # Obtener mensajes personalizados desde la personalidad
    greeting_cfg = PERSONALIDAD.get("discord", {}).get("greeting_messages", {})
    mensaje_activado = greeting_cfg.get("saludos_activados", "GRRR Kronk vigilará llegada de umanos! Kronk saludar cuando umanos aparecer!")
    mensaje_desactivado = greeting_cfg.get("saludos_desactivados", "BRRR Kronk ya no vigilar umanos! Kronk dejar de saludar, demasiado trabajo!")
    
    mensaje = mensaje_activado if enabled else mensaje_desactivado
    
    await ctx.send(mensaje)
    
    action = "activados" if enabled else "desactivados"
    logger.info(f"🔧 [DISCORD] {ctx.author.name} {action} los saludos de presencia en {ctx.guild.name}")

async def _cmd_bienvenida_toggle(ctx, enabled: bool):
    """Comando genérico para activar/desactivar saludos de bienvenida."""
    # Obtener mensajes personalizados
    role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
    
    # Verificar permisos (solo admins o mods)
    if not ctx.author.guild_permissions.administrator and not ctx.author.guild_permissions.manage_guild:
        await ctx.send(role_cfg.get("admin_permission", "❌ Solo administradores pueden modificar los saludos de bienvenida."))
        return
    
    # Obtener configuración actual
    greeting_cfg = _discord_cfg.get("member_greeting", {})
    greeting_cfg["enabled"] = enabled
    
    # Obtener mensaje personalizado desde la personalidad
    greeting_messages_cfg = PERSONALIDAD.get("discord", {}).get("greeting_messages", {})
    
    if enabled:
        mensaje = greeting_messages_cfg.get("bienvenida_activados", "✅ Saludos de bienvenida activados en este servidor.")
    else:
        mensaje = greeting_messages_cfg.get("bienvenida_desactivados", "✅ Saludos de bienvenida desactivados en este servidor.")
    
    # Actualizar configuración (esto requeriría persistencia en un archivo real)
    logger.info(f"🔧 [DISCORD] {ctx.author.name} {'activó' if enabled else 'desactivó'} los saludos de bienvenida en {ctx.guild.name}")
    
    await ctx.send(mensaje)

# Registrar comandos dinámicos para saludos de presencia con formato estándar
# Usar _personality_name para consistencia con el resto del archivo
saluda_command_name = f"saluda{_personality_name}"

@bot.command(name=saluda_command_name)
async def cmd_saluda_enable(ctx):
    await _cmd_saluda_toggle(ctx, True)

# Comando para desactivar saludos de presencia: !nosaludes[nombre]
nosaludes_command_name = f"nosaludes{_personality_name}"

@bot.command(name=nosaludes_command_name)
async def cmd_saluda_disable(ctx):
    await _cmd_saluda_toggle(ctx, False)

# Comandos para bienvenida de nuevos miembros
bienvenida_command_name = f"bienvenida{_personality_name}"

@bot.command(name=bienvenida_command_name)
async def cmd_bienvenida_enable(ctx):
    await _cmd_bienvenida_toggle(ctx, True)

nobienvenida_command_name = f"nobienvenida{_personality_name}"

@bot.command(name=nobienvenida_command_name)
async def cmd_bienvenida_disable(ctx):
    await _cmd_bienvenida_toggle(ctx, False)

# Comando de insulto (definido aquí para estar disponible en la ayuda)
insulta_command_name = f"insulta{_personality_name}"

# Comando de prueba
@bot.command(name="test")
async def cmd_test(ctx):
    """Comando de prueba para verificar si funciona."""
    # Obtener mensajes personalizados
    role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
    
    logger.info(f"🧪 Comando test ejecutado por {ctx.author.name}")
    await ctx.send(role_cfg.get("test_command", "✅ Comando test funciona!"))

# Comando de prueba del Vigía
@bot.command(name="vigiatest")
async def cmd_vigia_test(ctx):
    """Comando de prueba para el Vigía."""
    # Obtener mensajes personalizados
    role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
    
    logger.info(f"📡 Comando vigiatest ejecutado por {ctx.author.name}")
    await ctx.send(role_cfg.get("vigia_test_command", "📡 ✅ Comando vigiatest funciona - el Vigía está respondiendo!"))

# --- CONTROL DE EVENTOS (NUEVO PARADIGMA) ---
import hashlib
from datetime import datetime, timedelta

# Cache para evitar procesamiento duplicado de eventos
_event_cache = {}
_cache_ttl = timedelta(seconds=5)

def _get_event_key(event_type, ctx_or_message):
    """Genera una clave única para cada evento."""
    if hasattr(ctx_or_message, 'id'):  # Message
        key_data = f"{event_type}_{ctx_or_message.id}_{ctx_or_message.author.id}"
    else:  # Otros eventos
        key_data = f"{event_type}_{str(ctx_or_message)}"
    return hashlib.md5(key_data.encode()).hexdigest()

def _is_event_processed(event_key):
    """Verifica si un evento ya fue procesado."""
    now = datetime.now()
    if event_key in _event_cache:
        if now - _event_cache[event_key] < _cache_ttl:
            return True
        else:
            del _event_cache[event_key]
    return False

def _mark_event_processed(event_key):
    """Marca un evento como procesado."""
    _event_cache[event_key] = datetime.now()

# --- CONTROL DE COMANDOS (MEJORADO) ---
_command_cache = {}
_command_cooldown = timedelta(seconds=2)

def is_duplicate_command(ctx, command_name):
    """Verificación mejorada de comandos duplicados."""
    user_id = ctx.author.id
    guild_id = ctx.guild.id
    now = datetime.now()
    
    # Clave del comando
    cmd_key = f"{guild_id}_{user_id}_{command_name}"
    
    # Verificar cooldown
    if cmd_key in _command_cache:
        if now - _command_cache[cmd_key] < _command_cooldown:
            logger.warning(f"🚫 [DISCORD] Comando duplicado bloqueado: {command_name} por {ctx.author.name}")
            return True
    
    # Marcar como procesado
    _command_cache[cmd_key] = now
    
    # Limpiar cache antigua
    _cleanup_command_cache()
    
    return False

def _cleanup_command_cache():
    """Limpia entradas antiguas del cache."""
    now = datetime.now()
    expired = [k for k, v in _command_cache.items() if now - v > timedelta(minutes=5)]
    for k in expired:
        del _command_cache[k]

# Bloqueo global para evitar múltiples conexiones del mismo bot
import fcntl
import tempfile
_connection_lock = threading.Lock()
_is_connected = False
_commands_registered = False
_lock_file_path = None

def acquire_connection_lock():
    """Adquiere un bloqueo a nivel de sistema para evitar múltiples instancias."""
    global _lock_file_path
    
    try:
        _lock_file_path = tempfile.NamedTemporaryFile(delete=False, prefix='discord_bot_lock_')
        _lock_file_path.close()
        
        # Intentar adquirir bloqueo exclusivo
        lock_fd = open(_lock_file_path.name, 'w')
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        
        logger.info(f"🔒 [DISCORD] Bloqueo adquirido: {_lock_file_path.name}")
        return lock_fd
    except (IOError, OSError) as e:
        if e.errno == 11:  # Resource temporarily unavailable
            logger.warning("🚫 [DISCORD] Otra instancia del bot ya está corriendo")
            if _lock_file_path and os.path.exists(_lock_file_path.name):
                os.unlink(_lock_file_path.name)
            return None
        logger.error(f"❌ [DISCORD] Error adquiriendo bloqueo: {e}")
        return None


# Comando de ayuda
ayuda_command_name = f"ayuda{_personality_name}"

@bot.command(name=ayuda_command_name)
async def cmd_ayuda(ctx):
    """Muestra todos los comandos activos para este agente."""
    
    # Verificar duplicados
    if is_duplicate_command(ctx, "ayuda"):
        return
    
    # Obtener configuración de roles activos
    from agent_engine import AGENT_CFG
    roles_config = AGENT_CFG.get("roles", {})
    
    ayuda_msg = f"🤖 **Comandos disponibles para {bot.user.name}** 🤖\n\n"
    
    # Comandos de control
    ayuda_msg += "🎛️ **COMANDOS DE CONTROL**\n"
    ayuda_msg += f"• `!{saluda_command_name}` - Activar saludos de presencia (DM)\n"
    ayuda_msg += f"• `!{nosaludes_command_name}` - Desactivar saludos de presencia\n"
    ayuda_msg += f"• `!{bienvenida_command_name}` - Activar bienvenida de nuevos miembros\n"
    ayuda_msg += f"• `!{nobienvenida_command_name}` - Desactivar bienvenida de nuevos miembros\n"
    ayuda_msg += f"• `!{insulta_command_name}` - Lanzar insulto orco\n"
    ayuda_msg += "• `!rolekronk <rol> <on/off>` - Activar/desactivar roles dinámicamente\n"
    ayuda_msg += f"• `!{ayuda_command_name}` - Mostrar esta ayuda\n\n"
    
    # Comandos disponibles por rol
    ayuda_msg += "🎭 **COMANDOS DISPONIBLES POR ROL**\n"
    
    # Vigía de noticias
    if os.getenv("VIGIA_NOTICIAS_ENABLED", "false").lower() == "true" or roles_config.get("vigia_noticias", {}).get("enabled", False):
        interval = roles_config.get("vigia_noticias", {}).get("interval_hours", 1)
        ayuda_msg += f"📡 **Vigía de Noticias** - ` Ej: !vigia suscribir economia` | `!vigiafrecuencia <h>` (cada {interval}h) | `!vigiaayuda` para ayuda específica\n"
    
    # Buscador de tesoros
    if os.getenv("BUSCADOR_TESOROS_ENABLED", "false").lower() == "true" or roles_config.get("buscador_tesoros", {}).get("enabled", False):
        interval = roles_config.get("buscador_tesoros", {}).get("interval_hours", 1)
        ayuda_msg += f"💎 **Buscador de Tesoros** - `!buscartesoros` / `!nobuscartesoros` | `!tesorosfrecuencia <h>` (cada {interval}h) | `!poe2ayuda` para ayuda específica\n"
    
    # Trilero (incluye pedir oro)
    if os.getenv("TRILERO_ENABLED", "false").lower() == "true" or roles_config.get("trilero", {}).get("enabled", False):
        interval = roles_config.get("trilero", {}).get("interval_hours", 12)
        ayuda_msg += f"🎭 **Trilero** - `!trilero` / `!notrilero` | `!trilerofrecuencia <h>` (cada {interval}h)\n"
    
    # Buscar anillo
    if os.getenv("BUSCAR_ANILLO_ENABLED", "false").lower() == "true" or roles_config.get("buscar_anillo", {}).get("enabled", False):
        interval = roles_config.get("buscar_anillo", {}).get("interval_hours", 24)
        ayuda_msg += f"👁️ **Buscar Anillo** - `!acusaranillo` <@usuario> | `!anillofrecuencia <h>` (cada {interval}h)\n"
    
    # Música (siempre disponible, independiente de roles)
    music_help_msg = PERSONALIDAD.get("discord", {}).get("role_messages", {}).get("music_help", "🎵 **Música** - `!mc play <canción>` / `!mc queue` | `!mc help` para ayuda completa (siempre disponible)")
    ayuda_msg += f"{music_help_msg}\n\n"
    
    # Descripción básica de conversación
    ayuda_msg += "💬 **DESCRIPCIÓN BÁSICA DE CONVERSACIÓN**\n"
    ayuda_msg += "• Menciona al bot para conversar\n"
    ayuda_msg += "• Responde usando la personalidad del agente\n"
    ayuda_msg += "• El bot responderá como su personaje (Kronk/Putre)\n\n"
    
    # Roles activos y desactivados
    ayuda_msg += "🎭 **ROLES ACTIVOS Y DESACTIVADOS**\n"
    
    # Verificar estado de cada rol
    roles_estado = []
    for role_name, role_cfg in roles_config.items():
        enabled = False
        # Verificar variable de entorno primero
        env_enabled = os.getenv(f"{role_name.upper()}_ENABLED", "false").lower() == "true"
        if env_enabled:
            enabled = True
        else:
            enabled = role_cfg.get("enabled", False)
        
        status_emoji = "✅" if enabled else "❌"
        role_display_name = role_name.replace("_", " ").title()
        
        if role_name == "vigia_noticias":
            ayuda_msg += f"• {status_emoji} **Vigía de Noticias** - Alertas de noticias críticas\n"
        elif role_name == "buscador_tesoros":
            ayuda_msg += f"• {status_emoji} **Buscador de Tesoros** - Alertas de oportunidades de compra\n"
        elif role_name == "trilero":
            ayuda_msg += f"• {status_emoji} **Trilero** - Estafas y manipulación para conseguir recursos\n"
        elif role_name == "buscar_anillo":
            ayuda_msg += f"• {status_emoji} **Buscar Anillo** - Acusaciones por el anillo\n"
        elif role_name == "mc":
            ayuda_msg += f"• ✅ **Música** - Siempre disponible (no requiere activación)\n"
    
    try:
        await ctx.author.send(ayuda_msg)
        await ctx.send(get_message('ayuda_enviada_privado'))
    except discord.errors.Forbidden:
        await ctx.send(ayuda_msg[:2000])

# Comando de ayuda específico para POE2
@bot.command(name="poe2ayuda")
async def cmd_poe2_ayuda(ctx):
    """Muestra ayuda específica para el subrol POE2."""
    
    ayuda_poe2 = "🔮 **Ayuda del Subrol POE2** 🔮\n\n"
    ayuda_poe2 += "📋 **Control del Subrol:**\n"
    ayuda_poe2 += "• `!buscartesoros poe2` - Activa el subrol POE2\n"
    ayuda_poe2 += "• `!nobuscartesoros poe2` - Desactiva el subrol POE2\n\n"
    
    ayuda_poe2 += "🏆 **Gestión de Liga:**\n"
    ayuda_poe2 += "• `!poe2liga` - Muestra la liga actual\n"
    ayuda_poe2 += "• `!poe2liga Standard` - Establece liga Standard\n"
    ayuda_poe2 += "• `!poe2liga Fate of the Vaal` - Establece liga Fate of the Vaal\n\n"
    
    ayuda_poe2 += "🎯 **Gestión de Objetivos:**\n"
    ayuda_poe2 += "• `!poe2add \"Nombre del Item\"` - Añade item a objetivos\n"
    ayuda_poe2 += "• `!poe2del \"Nombre del Item\"` - Elimina item de objetivos\n"
    ayuda_poe2 += "• `!poe2list` - Muestra configuración y objetivos actuales\n\n"
    
    ayuda_poe2 += "📊 **Items Conocidos:**\n"
    ayuda_poe2 += "• Ancient Rib • Ancient Collarbone • Ancient Jawbone\n"
    ayuda_poe2 += "• Fracturing Orb • Igniferis • Idol of Uldurn\n\n"
    
    ayuda_poe2 += "⚡ **Análisis Automático:**\n"
    ayuda_poe2 += "• **COMPRA**: Precio ≤ mínimo histórico × 1.15\n"
    ayuda_poe2 += "• **VENTA**: Precio ≥ máximo histórico × 0.85\n\n"
    
    ayuda_poe2 += "💡 **Ejemplos de Uso:**\n"
    ayuda_poe2 += "```\n!buscartesoros poe2\n!poe2liga Fate of the Vaal\n!poe2add \"Ancient Rib\"\n!poe2add \"Fracturing Orb\"\n!poe2list\n```"
    
    try:
        await ctx.author.send(ayuda_poe2)
        # Usar mensaje personalizado desde role_messages
        role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
        poe2_privado_msg = role_cfg.get("poe2_help_sent", "✅ Te he enviado la ayuda de POE2 por mensaje privado 📩")
        await ctx.send(poe2_privado_msg)
    except discord.errors.Forbidden:
        await ctx.send(ayuda_poe2[:2000])

# Comando de ayuda específico para Vigía de Noticias
@bot.command(name="vigiaayuda")
async def cmd_vigia_ayuda(ctx):
    """Muestra ayuda específica para el Vigía de Noticias."""
    
    # Obtener mensaje personalizado desde la personalidad
    ayuda_cfg = PERSONALIDAD.get("discord", {}).get("general_messages", {})
    mensaje_privado = ayuda_cfg.get("help_sent_private", "GRRR Kronk enviar ayuda por mensaje privado umano!")
    
    ayuda_vigia = "📡 **Ayuda del Vigía de Noticias** 📡\n\n"
    
    ayuda_vigia += "🎯 **Comandos Principales:**\n"
    ayuda_vigia += "• `!vigia feeds` - Lista feeds RSS disponibles\n"
    ayuda_vigia += "• `!vigia categorias` - Muestra categorías activas\n"
    ayuda_vigia += "• `!vigia estado` - Tus suscripciones activas\n\n"
    
    ayuda_vigia += "🎯 **Suscripciones Especializadas:**\n"
    ayuda_vigia += "• `!vigia suscribir <categoría> [feed_id]` - Suscribirse a feeds\n"
    ayuda_vigia += "• `!vigia cancelar <categoría> [feed_id]` - Cancelar suscripción\n"
    ayuda_vigia += "• **Ejemplo:** `!vigia suscribir economia`\n\n"
    
    ayuda_vigia += "🤖 **Suscripciones con IA:**\n"
    ayuda_vigia += "• `!vigia general <categoría>` - Feeds con clasificación IA\n"
    ayuda_vigia += "• `!vigia mixto <categoría>` - Cobertura mixta (máxima)\n"
    ayuda_vigia += "• **Ejemplo:** `!vigia general internacional`\n\n"
    
    ayuda_vigia += "🔍 **Palabras Clave:**\n"
    ayuda_vigia += "• `!vigia palabras \"palabra1,palabra2\"` - Suscribir a palabras\n"
    ayuda_vigia += "• `!vigia cancelar_palabras \"palabras\"` - Cancelar suscripción\n"
    ayuda_vigia += "• `!vigia estado_palabras` - Ver palabras suscritas\n\n"
    
    ayuda_vigia += "📢 **Comandos de Canal:**\n"
    ayuda_vigia += "• `!vigiacanal suscribir <categoría> [feed_id]` - Suscribir canal\n"
    ayuda_vigia += "• `!vigiacanal cancelar <categoría> [feed_id]` - Cancelar canal\n"
    ayuda_vigia += "• `!vigiacanal estado` - Ver suscripciones del canal\n"
    ayuda_vigia += "• `!vigiacanal palabras \"palabras\"` - Palabras clave para canal\n\n"
    
    ayuda_vigia += "⚙️ **Administración:**\n"
    ayuda_vigia += "• `!vigia agregar_feed <nombre> <url> <categoría> [tipo]` - Agregar feed\n\n"
    
    ayuda_vigia += "📂 **Categorías:** economia, internacional, tecnologia, sociedad, politica\n\n"
    
    ayuda_vigia += "🔔 **Alertas Críticas:**\n"
    ayuda_vigia += "• `!avisanoticias` - Suscribirse a alertas críticas\n"
    ayuda_vigia += "• `!noavisanoticias` - Cancelar suscripción a alertas\n\n"
    
    ayuda_vigia += "🌐 **Fuentes por Defecto:**\n"
    ayuda_vigia += "• CNBC (economia) • El País (internacional) • Reuters (internacional)\n"
    ayuda_vigia += "• BBC (tecnologia) • CNN (general) • Crypto News (cripto)\n\n"
    
    ayuda_vigia += "💡 **Ejemplos:**\n"
    ayuda_vigia += "```\n!vigia feeds                    # Ver feeds\n!vigia suscribir economia         # Noticias económicas\n!vigia general internacional      # Noticias con IA\n!vigia palabras \"bitcoin,crypto\"  # Alertas crypto\n!vigiacanal suscribir politica     # Suscribir canal\n```\n\n"
    
    ayuda_vigia += "⚡ **Características:** Monitorización 24/7, IA, clasificación automática, notificaciones instantáneas, filtrado por palabras clave, detección de eventos críticos."
    
    try:
        await ctx.author.send(ayuda_vigia)
        await ctx.send(mensaje_privado)
    except discord.errors.Forbidden:
        await ctx.send(ayuda_vigia[:2000])


async def _cmd_insulta(ctx, obj=""):
    target = obj if obj else ctx.author.mention

    if "@everyone" in target or "@here" in target:
        prompt = _insult_cfg.get("prompt_everyone", "Lanza un insulto breve a TODO EL MUNDO, maximo 1 frase")
    else:
        prompt = _insult_cfg.get("prompt_target", "Lanza un insulto breve a una persona especifica, maximo 1 frase")

    res = await asyncio.to_thread(pensar, prompt, logger=logger)
    await ctx.send(f"{target} {res}")


# Registrar el comando de insulto dinámicamente
bot.command(name=insulta_command_name)(_cmd_insulta)

logger.info(f"🤖 [DISCORD] Comandos registrados:")
logger.info(f"🤖 [DISCORD] - {saluda_command_name} (activar saludos de presencia)")
logger.info(f"🤖 [DISCORD] - {nosaludes_command_name} (desactivar saludos de presencia)")
logger.info(f"🤖 [DISCORD] - {bienvenida_command_name} (activar bienvenida)")
logger.info(f"🤖 [DISCORD] - {nobienvenida_command_name} (desactivar bienvenida)")
logger.info(f"🤖 [DISCORD] - {insulta_command_name} (insultos)")
logger.info(f"🤖 [DISCORD] - {ayuda_command_name} (mostrar ayuda)")

# --- EVENTOS Y COMANDOS ---

# Variable global para controlar inicialización única
_initialization_complete = False
_state_file_path = "/tmp/discord_bot_initialized.flag"
_socket_lock_path = "/tmp/discord_bot.sock"

def is_already_initialized():
    """Verifica si el bot ya fue inicializado usando archivo de estado."""
    try:
        return os.path.exists(_state_file_path)
    except:
        return False

def mark_as_initialized():
    """Marca el bot como inicializado."""
    try:
        with open(_state_file_path, 'w') as f:
            f.write("initialized")
        logger.info("🔒 [DISCORD] Bot marcado como inicializado")
    except Exception as e:
        logger.error(f"❌ [DISCORD] Error marcando inicialización: {e}")

def acquire_process_lock():
    """Adquiere bloqueo a nivel de proceso usando socket Unix."""
    import socket
    try:
        # Intentar crear socket Unix para exclusión mutua
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(_socket_lock_path)
        logger.info(f"🔒 [DISCORD] Bloqueo de proceso adquirido: {_socket_lock_path}")
        return sock
    except (OSError, socket.error) as e:
        if e.errno == 98:  # Address already in use
            logger.warning("🚫 [DISCORD] Bot ya está corriendo (bloqueo de proceso)")
            return None
        logger.error(f"❌ [DISCORD] Error adquiriendo bloqueo de proceso: {e}")
        return None

@bot.event
async def on_ready():
    """Se ejecuta cuando el bot está listo."""
    global _is_connected, _initialization_complete, logger
    
    # Log inicial para debugging
    print(f"🔍 [DEBUG] on_ready llamado, _initialization_complete={_initialization_complete}")
    
    # Ensure logger is available
    if 'logger' not in globals():
        global logger
        logger = get_logger('discord')
    
    # Verificación inmediata con archivo de estado
    if is_already_initialized():
        logger.warning("🚫 [DISCORD] Bot ya inicializado (verificación inmediata), ignorando...")
        return
    
    # Bloqueo a nivel de proceso (más rápido que archivo)
    process_sock = acquire_process_lock()
    if process_sock is None:
        logger.warning("🚫 [DISCORD] No se pudo adquirir bloqueo de proceso, saliendo...")
        return
    
    # Verificación doble después de bloqueo de proceso
    if is_already_initialized():
        logger.warning("🚫 [DISCORD] Bot ya inicializado (post-process-lock), ignorando...")
        process_sock.close()
        return
    
    # Bloqueo a nivel de sistema como respaldo
    lock_fd = acquire_connection_lock()
    if lock_fd is None:
        logger.warning("🚫 [DISCORD] No se pudo adquirir bloqueo de sistema, saliendo...")
        process_sock.close()
        return
    
    # Verificación triple después de todos los bloqueos
    if is_already_initialized():
        logger.warning("🚫 [DISCORD] Bot ya inicializado (post-all-locks), ignorando...")
        lock_fd.close()
        process_sock.close()
        return
    
    # Bloqueo adicional para evitar múltiples threads
    with _connection_lock:
        if _is_connected:
            logger.warning("🚫 [DISCORD] Segunda conexión detectada, ignorando...")
            lock_fd.close()
            process_sock.close()
            return
        
        _is_connected = True
    
    # Marcar como inicializado INMEDIATAMENTE
    mark_as_initialized()
    _initialization_complete = True
    
    print(f"🔍 [DEBUG] Bloqueos adquiridos, inicialización completada")
    
    # Esperar un momento para asegurar que solo una instancia procese
    await asyncio.sleep(0.2)
    
    # Verificación final
    if not _is_connected:
        logger.warning("🚫 [DISCORD] Conexión cancelada por otra instancia")
        lock_fd.close()
        process_sock.close()
        return
    
    template = _discord_cfg.get("on_ready_message", "✅ {bot_name} operativo: {bot_user}")
    print(template.format(bot_name=_bot_display_name, bot_user=bot.user))
    
    # Elegir UN servidor activo (si el bot está en varios guilds)
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
        # Persistir servidor activo para que roles/subprocesos usen la misma carpeta
        set_current_server(active_guild.name)

        _personality_name = PERSONALIDAD.get("name", "agent").lower()
        update_log_file_path(active_guild.name, _personality_name)
        
        # FORZAR reconfiguración completa del logger
        logger = get_logger('discord')  # Re-obtener logger con nueva configuración
        
        # Re-registrar comandos MC si el bot no está completamente inicializado
        # Esto asegura que los comandos MC persistan después de que el bot esté listo
        # OMITIR - ahora se maneja en register_commands_for_enabled_roles
        if not _initialization_complete:
            logger.info("🎵 [DISCORD] Omitiendo registro MC en on_ready - ahora manejado por register_commands_for_enabled_roles")
        
        # Verificar si el logger tiene file handler
        from logging.handlers import RotatingFileHandler
        has_file_handler = any(isinstance(h, RotatingFileHandler) for h in logger.handlers)
        print(f"🔍 [DEBUG] Logger tiene file handler: {has_file_handler}")
        print(f"🔍 [DEBUG] Logger handlers: {len(logger.handlers)}")
        
        server_name = active_guild.name.lower().replace(' ', '_').replace('-', '_')
        server_name = ''.join(c for c in server_name if c.isalnum() or c == '_')
        logger.info(f"📁 [DISCORD] Servidor activo: '{active_guild.name}'")
        logger.info(f"📁 [DISCORD] Logs: logs/{server_name}/{_personality_name}.log")
        
        # Forzar un test de escritura
        logger.info("🔍 [DEBUG] Test de escritura de logger")
    
    # Ahora sí escribir los logs de conexión
    logger.info(f"🤖 [DISCORD] Bot {_bot_display_name} conectado como {bot.user}")
    logger.info(f"🤖 [DISCORD] Comando prefijo: {_cmd_prefix}")
    logger.info(f"🤖 [DISCORD] Comando insulto: {_insult_name}")
    
    logger.info(f"🤖 [DISCORD] Bot KRONK conectado como {bot.user}")
    logger.info(f"🤖 [DISCORD] Comando prefijo: {bot.command_prefix}")
    logger.info(f"🤖 [DISCORD] Comando insulto: {insulta_command_name}")
    logger.info(f"🤖 [DISCORD] Intents - members: {bot.intents.members}")
    logger.info(f"🤖 [DISCORD] Intents - presences: {bot.intents.presences}")
    logger.info(f"🤖 [DISCORD] Total de comandos registrados: {len(bot.commands)}")
    for cmd in bot.commands:
        logger.info(f"🤖 [DISCORD] Comando registrado: {cmd.name}")
    
    if not limpieza_db.is_running():
        limpieza_db.start()
        logger.info("🧹 [DISCORD] Tarea de limpieza automática iniciada")
    
    # Registrar comandos de roles activados según agent_config.json
    await register_commands_for_enabled_roles()


@bot.event
async def on_guild_join(guild):
    """Se ejecuta cuando el bot se une a un nuevo servidor."""
    _personality_name = PERSONALIDAD.get("name", "agent").lower()
    update_log_file_path(guild.name, _personality_name)
    get_logger('discord')
    logger.info(f"📁 [DISCORD] Nuevo servidor '{guild.name}': logs/{guild.name.lower().replace(' ', '_').replace('-', '_')}/{_personality_name}.log")
    
    # Enviar mensaje de bienvenida del MC solo si el rol está activo
    def is_role_enabled(role_name):
        env_var = os.getenv(f"{role_name.upper()}_ENABLED", "").lower()
        if env_var:
            logger.info(f"🔍 Verificando {role_name}: env_var={env_var} -> {env_var == 'true'}")
        return env_var == 'true'
    
    if is_role_enabled("mc"):
        logger.info(f"🎵 [DISCORD] Rol MC activado, enviando mensaje de bienvenida")
        # Buscar canal general para dar la bienvenida
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                # Obtener mensaje personalizado desde la personalidad
                mc_cfg = PERSONALIDAD.get("discord", {}).get("mc_messages", {})
                mensaje_bienvenida = mc_cfg.get("welcome_message", 
                    "🎵 **¡MC ha llegado para rockear!** 🎵\n\n"
                    "Soy tu DJ personal y estoy aquí para poner la mejor música.\n\n"
                    "**Comandos básicos:**\n"
                    "• `!mc play <canción>` - Reproduce o agrega música\n"
                    "• `!mc queue` - Muestra la cola de reproducción\n"
                    "• `!mc help` - Muestra todos los comandos\n\n"
                    "🎤 **Conéctate a un canal de voz y empieza la fiesta!**")
                await channel.send(mensaje_bienvenida)
                break
    else:
        logger.info(f"🎵 [DISCORD] Rol MC no está activado, omitiendo mensaje de bienvenida")


@bot.event
async def on_member_join(member):
    """Se ejecuta cuando un nuevo usuario se une al servidor."""
    if member.bot:
        return  # Ignorar bots
    
    # Verificar si los saludos están activados para este servidor
    if not get_greeting_enabled(member.guild):
        return  # Saludos desactivados
    
    # Obtener configuración de saludo
    greeting_cfg = _discord_cfg.get("member_greeting", {})
    if not greeting_cfg.get("enabled", True):
        return  # Saludo desactivado en configuración
    
    # Determinar canal de bienvenida
    welcome_channel_name = greeting_cfg.get("welcome_channel", "general")
    welcome_channel = None
    
    # Buscar canal de bienvenida
    for channel in member.guild.text_channels:
        if channel.name.lower() == welcome_channel_name.lower():
            welcome_channel = channel
            break
    
    # Si no se encuentra el canal específico, usar el primer canal disponible
    if welcome_channel is None and member.guild.text_channels:
        welcome_channel = member.guild.text_channels[0]
    
    if welcome_channel is None:
        logger.warning(f"⚠️ [DISCORD] No se encontró canal de bienvenida para {member.name} en {member.guild.name}")
        return
    
    # Generar saludo personalizado usando la personalidad del bot
    greeting_prompt = greeting_cfg.get("prompt", "Saluda brevemente al nuevo miembro {member_name} en el servidor {server_name}. Sé amigable y da la bienvenida.")
    greeting_context = greeting_prompt.format(member_name=member.display_name, server_name=member.guild.name)
    
    try:
        # Generar respuesta usando el motor de IA
        saludo = await asyncio.to_thread(pensar, greeting_context)
        
        # Enviar saludo al canal
        await welcome_channel.send(f"🎉 {member.mention} {saludo}")
        
        # Registrar en el log
        logger.info(f"👋 [DISCORD] Nuevo usuario {member.name} ({member.id}) saludado en {member.guild.name}")
        
        # Registrar interacción en la base de datos
        db_instance = get_db_for_server(member.guild)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            member.id,
            member.name,
            "BIENVENIDA",
            f"Usuario se unió al servidor",
            welcome_channel.id,
            member.guild.id,
            metadata={"saludo": saludo}
        )
        
    except Exception as e:
        logger.error(f"❌ [DISCORD] Error al saludar a {member.name}: {e}")
        # Saludo de emergencia si falla la IA
        fallback_msg = greeting_cfg.get("fallback", "¡Bienvenido al servidor!")
        await welcome_channel.send(f"🎉 {member.mention} {fallback_msg}")


@bot.event
async def on_presence_update(before, after):
    """Se ejecuta cuando el estado de presencia de un miembro cambia (offline a online, etc.)."""
    if after.bot:
        return  # Ignorar bots
    
    # Verificar si los saludos están activados para este servidor
    if not get_greeting_enabled(after.guild):
        return  # Saludos desactivados
    
    # Obtener configuración de saludo de reconexión
    presence_cfg = _discord_cfg.get("member_presence", {})
    if not presence_cfg.get("enabled", False):
        return  # Saludo de presencia desactivado
    
    # Verificar si cambió de offline a online
    before_status = before.status if before.status else discord.Status.offline
    after_status = after.status if after.status else discord.Status.offline
    
    # Solo procesar si pasó de offline a online
    if before_status != discord.Status.offline or after_status != discord.Status.online:
        return
    
    # Evitar spam por reconexiones frecuentes (mínimo 5 minutos entre saludos)
    import time
    current_time = time.time()
    last_greeting_key = f"presence_greeting_{after.id}"
    
    # Usar una variable global simple para tracking (se reinicia con el bot)
    if not hasattr(on_presence_update, '_last_greetings'):
        on_presence_update._last_greetings = {}
    
    last_greeting_time = on_presence_update._last_greetings.get(last_greeting_key, 0)
    if current_time - last_greeting_time < 300:  # 5 minutos
        return
    
    # Generar saludo de presencia
    presence_prompt = presence_cfg.get("prompt", "Saluda brevemente a {member_name} que se acaba de conectar. Sé orco pero breve.")
    presence_context = presence_prompt.format(member_name=after.display_name)
    
    try:
        # Generar respuesta usando el motor de IA
        saludo = await asyncio.to_thread(pensar, presence_context)
        
        # Enviar saludo por DM
        await after.send(f"👋 {saludo}")
        
        # Registrar en el log
        logger.info(f"🔄 [DISCORD] DM enviado a {after.name} ({after.id})")
        
        # Actualizar timestamp para evitar spam
        on_presence_update._last_greetings[last_greeting_key] = current_time
        
        # Registrar interacción en la base de datos (sin canal específico por ser DM)
        db_instance = get_db_for_server(after.guild)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            after.id,
            after.name,
            "PRESENCIA_DM",
            f"Usuario pasó de offline a online (saludo por DM)",
            None,  # No hay canal por ser DM
            after.guild.id,
            metadata={"saludo": saludo}
        )
        
    except Exception as e:
        logger.error(f"❌ [DISCORD] Error al saludar presencia de {after.name}: {e}")
        # Saludo de emergencia si falla la IA
        fallback_msg = presence_cfg.get("fallback", "¡Bienvenido de vuelta!")
        await after.send(f"👋 {fallback_msg}")


@bot.event
async def on_voice_state_update(member, before, after):
    """Desconecta al bot de un canal de voz si se queda sin usuarios humanos (funcionalidad MC)."""
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


# --- COMANDOS DE CONTROL DE ROLES ---

async def _cmd_role_toggle(ctx, role_name: str, enabled: bool):
    """Comando genérico para activar/desactivar roles dinámicamente."""
    # Obtener mensajes personalizados
    role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
    
    # Verificar permisos (solo admins)
    if not ctx.author.guild_permissions.administrator and not ctx.author.guild_permissions.manage_guild:
        await ctx.send(role_cfg.get("role_no_permission", "❌ Solo administradores pueden modificar los roles."))
        return
    
    # Lista de roles válidos
    valid_roles = ["vigia_noticias", "buscador_tesoros", "trilero", "buscar_anillo"]
    
    if role_name not in valid_roles:
        await ctx.send(role_cfg.get("role_not_found", "❌ Rol '{role}' no válido.").format(role=role_name))
        return
    
    # Variable de entorno
    env_var_name = f"{role_name.upper()}_ENABLED"
    env_value = "true" if enabled else "false"
    
    logger.info(f"🎭 [DISCORD] Actualizando rol {role_name}: enabled={enabled}, env_var={env_var_name}, env_value={env_value}")
    
    # Establecer variable de entorno (solo para esta sesión)
    os.environ[env_var_name] = env_value
    logger.info(f"🎭 [DISCORD] Variable de entorno {env_var_name} establecida a: {os.environ.get(env_var_name)}")
    
    # Actualizar configuración en tiempo de ejecución
    if "roles" not in agent_config:
        agent_config["roles"] = {}
    
    if role_name not in agent_config["roles"]:
        agent_config["roles"][role_name] = {}
    
    agent_config["roles"][role_name]["enabled"] = enabled
    logger.info(f"🎭 [DISCORD] Config actualizada: {agent_config['roles'][role_name]}")
    
    # Registrar comandos del rol si se está activando
    if enabled:
        await register_specific_role_commands(role_name)
    else:
        # Desregistrar comandos del rol (opcional, complicado)
        logger.info(f"🎭 [DISCORD] Rol {role_name} desactivado (comandos permanecen registrados)")
    
    # Mensaje personalizado según acción
    if enabled:
        await ctx.send(role_cfg.get("role_activated", "✅ Rol '{role}' activado correctamente.").format(role=role_name))
        logger.info(f"🎭 [DISCORD] {ctx.author.name} activó el rol {role_name} en {ctx.guild.name}")
    else:
        await ctx.send(role_cfg.get("role_deactivated", "✅ Rol '{role}' desactivado correctamente.").format(role=role_name))
        logger.info(f"🎭 [DISCORD] {ctx.author.name} desactivó el rol {role_name} en {ctx.guild.name}")

async def _cmd_role_frequency(ctx, role_name: str, hours: str):
    """Comando genérico para configurar frecuencia de roles."""
    # Obtener mensajes personalizados
    role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
    
    # Verificar permisos (solo admins)
    if not ctx.author.guild_permissions.administrator and not ctx.author.guild_permissions.manage_guild:
        await ctx.send(role_cfg.get("role_no_permission", "❌ Solo administradores pueden modificar la frecuencia."))
        return
    
    # Validar que el rol existe
    valid_roles = ["vigia_noticias", "buscador_tesoros", "trilero", "buscar_anillo"]
    if role_name not in valid_roles:
        await ctx.send(role_cfg.get("role_not_found", "❌ Rol '{role}' no válido.").format(role=role_name))
        return
    
    # Validar horas
    try:
        hours_int = int(hours)
        if hours_int < 1 or hours_int > 168:  # Máximo 1 semana
            await ctx.send(role_cfg.get("frequency_invalid", "❌ Las horas deben estar entre 1 y 168."))
            return
    except ValueError:
        await ctx.send(role_cfg.get("frequency_invalid", "❌ Debes especificar un número válido de horas."))
        return
    
    # Actualizar configuración
    if "roles" not in agent_config:
        agent_config["roles"] = {}
    
    if role_name not in agent_config["roles"]:
        agent_config["roles"][role_name] = {}
    
    agent_config["roles"][role_name]["interval_hours"] = hours_int
    
    # Mensaje de confirmación
    await ctx.send(role_cfg.get("frequency_updated", "✅ Frecuencia de '{role}' actualizada a {hours} horas.").format(role=role_name, hours=hours_int))
    logger.info(f"🎭 [DISCORD] {ctx.author.name} actualizó frecuencia de {role_name} a {hours_int} horas en {ctx.guild.name}")

async def register_commands_for_enabled_roles():
    """Registra comandos para todos los roles activados en agent_config.json."""
    logger.info("🎭 [DISCORD] Verificando roles activados en agent_config.json")
    
    # Registrar comandos MC primero (siempre disponibles)
    register_mc_commands()
    
    # Obtener configuración de roles
    roles_config = agent_config.get("roles", {})
    
    # Lista de roles que tienen comandos Discord
    roles_with_commands = ["vigia_noticias", "buscador_tesoros", "trilero", "buscar_anillo"]
    
    for role_name in roles_with_commands:
        role_config = roles_config.get(role_name, {})
        is_enabled = role_config.get("enabled", False)
        
        if is_enabled:
            logger.info(f"🎭 [DISCORD] Rol {role_name} está activado, registrando TODOS los comandos...")
            await register_specific_role_commands(role_name)
        else:
            logger.info(f"🎭 [DISCORD] Rol {role_name} no está activado, omitiendo registro de comandos")


async def register_specific_role_commands(role_name: str):
    """Registra TODOS los comandos para un rol específico (idempotente)."""
    logger.info(f"🎭 [DISCORD] Registrando comandos para rol: {role_name}")
    
    if role_name == "vigia_noticias":
        # Importar comandos del Vigía
        from roles.vigia_noticias.vigia_commands import VigiaCommands
        
        # Crear instancia de comandos
        vigia_commands = VigiaCommands(bot)
        
        # Comandos del Vigía de Noticias (funcionan por DM)
        if bot.get_command("vigia") is None:
            logger.info("📡 [DISCORD] Registrando comando vigia")
            
            @bot.command(name="vigia")
            async def cmd_vigia(ctx, *args):
                """Comando principal del Vigía de Noticias (funciona por DM)."""
                if not VIGIA_COMMANDS_AVAILABLE:
                    await ctx.send("❌ El Vigía de Noticias no está disponible en este servidor.")
                    return
                
                # Permitir uso por DM y en servidor
                server_name = ctx.guild.name if ctx.guild else "DM"
                db_vigia_instance = get_vigia_db_for_server(ctx.guild) if ctx.guild else get_vigia_db_for_server(None)
                
                if not db_vigia_instance:
                    await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                    return
                
                # Si no hay argumentos, mostrar ayuda
                if not args:
                    await ctx.author.send("📡 **Vigía de Noticias** - Usa `!vigiaayuda` para ver todos los comandos disponibles.")
                    if ctx.guild:
                        await ctx.send("📩 Ayuda enviada por mensaje privado.")
                    return
                
                # Procesar subcomandos
                subcommand = args[0].lower()
                subargs = args[1:] if len(args) > 1 else []
                
                try:
                    if subcommand == "feeds":
                        await vigia_commands.cmd_feeds(ctx, subargs)
                    elif subcommand == "categorias":
                        await vigia_commands.cmd_categorias(ctx, subargs)
                    elif subcommand == "estado":
                        await vigia_commands.cmd_estado(ctx, subargs)
                    elif subcommand == "suscribir":
                        await vigia_commands.cmd_suscribir(ctx, subargs)
                    elif subcommand == "cancelar":
                        await vigia_commands.cmd_cancelar(ctx, subargs)
                    elif subcommand == "general":
                        await vigia_commands.cmd_general(ctx, subargs)
                    elif subcommand == "mixto":
                        await vigia_commands.cmd_mixto(ctx, subargs)
                    elif subcommand == "palabras":
                        await vigia_commands.cmd_palabras(ctx, subargs)
                    elif subcommand == "cancelar_palabras":
                        await vigia_commands.cmd_cancelar_palabras(ctx, subargs)
                    elif subcommand == "estado_palabras":
                        await vigia_commands.cmd_estado_palabras(ctx, subargs)
                    elif subcommand == "agregar_feed":
                        await vigia_commands.cmd_agregar_feed(ctx, subargs)
                    else:
                        await ctx.author.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!vigiaayuda` para ver ayuda.")
                        if ctx.guild:
                            await ctx.send("📩 Ayuda enviada por mensaje privado.")
                except Exception as e:
                    logger.error(f"Error en comando vigia {subcommand}: {e}")
                    await ctx.author.send("❌ Error al ejecutar el comando. Inténtalo de nuevo.")
                    if ctx.guild:
                        await ctx.send("📩 Error enviado por mensaje privado.")
        
        if bot.get_command("novigia") is None:
            logger.info("📡 [DISCORD] Registrando comando novigia")
            
            @bot.command(name="novigia")
            async def cmd_no_vigia(ctx):
                """Desactiva el rol Vigía de Noticias (funciona por DM)."""
                if not VIGIA_COMMANDS_AVAILABLE:
                    await ctx.send("❌ El Vigía de Noticias no está disponible en este servidor.")
                    return
                
                db_vigia_instance = get_vigia_db_for_server(ctx.guild) if ctx.guild else get_vigia_db_for_server(None)
                if not db_vigia_instance:
                    await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                    return
                
                usuario_id = str(ctx.author.id)
                usuario_nombre = ctx.author.name
                
                if not db_vigia_instance.esta_suscrito(usuario_id):
                    await ctx.author.send("🛡️ No estás suscrito a las alertas del Vigía de la Torre.")
                    if ctx.guild:
                        await ctx.send("📩 Respuesta enviada por mensaje privado.")
                    return
                
                if db_vigia_instance.eliminar_suscripcion(usuario_id):
                    await ctx.author.send("✅ Te has desuscrito de las alertas del Vigía de la Torre. Ya no recibirás noticias críticas.")
                    if ctx.guild:
                        await ctx.send("📩 Respuesta enviada por mensaje privado.")
                    logger.info(f"📡 [VIGÍA] {usuario_nombre} ({usuario_id}) se desuscribió de las alertas")
                else:
                    await ctx.send("❌ Error al desuscribirte de las alertas. Inténtalo de nuevo.")
        
        if bot.get_command("avisanoticias") is None:
            logger.info("📡 [DISCORD] Registrando comando avisanoticias (alias)")
            
            @bot.command(name="avisanoticias")
            async def cmd_avisa_noticias(ctx):
                """Alias para suscribirse a alertas críticas del Vigía (funciona por DM)."""
                if not VIGIA_AVAILABLE:
                    await ctx.send("❌ El Vigía de la Torre no está disponible en este servidor.")
                    return
                
                db_vigia_instance = get_vigia_db_for_server(ctx.guild) if ctx.guild else get_vigia_db_for_server(None)
                if not db_vigia_instance:
                    await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                    return
                
                usuario_id = str(ctx.author.id)
                usuario_nombre = ctx.author.name
                
                if db_vigia_instance.esta_suscrito(usuario_id):
                    await ctx.author.send("🛡️ Ya estás suscrito a las alertas del Vigía de la Torre.")
                    if ctx.guild:
                        await ctx.send("📩 Respuesta enviada por mensaje privado.")
                    return
                
                if db_vigia_instance.agregar_suscripcion(usuario_id, usuario_nombre):
                    await ctx.author.send("✅ Te has suscrito a las alertas del Vigía de la Torre. Recibirás noticias críticas cuando ocurran.")
                    await ctx.author.send("💡 Usa `!vigiaayuda` para ver todos los comandos disponibles del Vigía.")
                    if ctx.guild:
                        await ctx.send("📩 Respuesta enviada por mensaje privado.")
                    logger.info(f"📡 [VIGÍA] {usuario_nombre} ({usuario_id}) se suscribió a las alertas")
                else:
                    await ctx.send("❌ Error al suscribirte a las alertas. Inténtalo de nuevo.")
        
        if bot.get_command("noavisanoticias") is None:
            logger.info("📡 [DISCORD] Registrando comando noavisanoticias (alias)")
            
            @bot.command(name="noavisanoticias")
            async def cmd_no_avisa_noticias(ctx):
                """Alias para desuscribirse de alertas críticas del Vigía (funciona por DM)."""
                if not VIGIA_AVAILABLE:
                    await ctx.send("❌ El Vigía de la Torre no está disponible en este servidor.")
                    return
                
                db_vigia_instance = get_vigia_db_for_server(ctx.guild) if ctx.guild else get_vigia_db_for_server(None)
                if not db_vigia_instance:
                    await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                    return
                
                usuario_id = str(ctx.author.id)
                usuario_nombre = ctx.author.name
                
                if not db_vigia_instance.esta_suscrito(usuario_id):
                    await ctx.author.send("🛡️ No estás suscrito a las alertas del Vigía de la Torre.")
                    if ctx.guild:
                        await ctx.send("📩 Respuesta enviada por mensaje privado.")
                    return
                
                if db_vigia_instance.eliminar_suscripcion(usuario_id):
                    await ctx.author.send("✅ Te has desuscrito de las alertas del Vigía de la Torre. Ya no recibirás noticias críticas.")
                    await ctx.author.send("💡 Usa `!vigiaayuda` para ver todos los comandos disponibles del Vigía.")
                    if ctx.guild:
                        await ctx.send("📩 Respuesta enviada por mensaje privado.")
                    logger.info(f"📡 [VIGÍA] {usuario_nombre} ({usuario_id}) se desuscribió de las alertas")
                else:
                    await ctx.send("❌ Error al desuscribirte de las alertas. Inténtalo de nuevo.")
        
        if bot.get_command("vigiaayuda") is None:
            logger.info("📡 [DISCORD] Registrando comando vigiaayuda")
            
            @bot.command(name="vigiaayuda")
            async def cmd_vigia_ayuda(ctx):
                """Muestra ayuda específica para el Vigía de Noticias (funciona por DM)."""
                ayuda_cfg = PERSONALIDAD.get("discord", {}).get("general_messages", {})
                mensaje_privado = ayuda_cfg.get("help_sent_private", "GRRR Kronk enviar ayuda por mensaje privado umano!")
                
                ayuda_vigia = "📡 **Ayuda del Vigía de Noticias** 📡\n\n"
                
                ayuda_vigia += "🎯 **Comandos Principales:**\n"
                ayuda_vigia += "• `!vigia feeds` - Lista feeds RSS disponibles\n"
                ayuda_vigia += "• `!vigia categorias` - Muestra categorías activas\n"
                ayuda_vigia += "• `!vigia estado` - Tus suscripciones activas\n\n"
                
                ayuda_vigia += "🎯 **Suscripciones Especializadas:**\n"
                ayuda_vigia += "• `!vigia suscribir <categoría> [feed_id]` - Suscribirse a feeds\n"
                ayuda_vigia += "• `!vigia cancelar <categoría> [feed_id]` - Cancelar suscripción\n"
                ayuda_vigia += "• **Ejemplo:** `!vigia suscribir economia`\n\n"
                
                ayuda_vigia += "🤖 **Suscripciones con IA:**\n"
                ayuda_vigia += "• `!vigia general <categoría>` - Feeds con clasificación IA\n"
                ayuda_vigia += "• `!vigia mixto <categoría>` - Cobertura mixta (máxima)\n"
                ayuda_vigia += "• **Ejemplo:** `!vigia general internacional`\n\n"
                
                ayuda_vigia += "🔍 **Palabras Clave:**\n"
                ayuda_vigia += "• `!vigia palabras \"palabra1,palabra2\"` - Suscribir a palabras\n"
                ayuda_vigia += "• `!vigia cancelar_palabras \"palabras\"` - Cancelar suscripción\n"
                ayuda_vigia += "• `!vigia estado_palabras` - Ver palabras suscritas\n\n"
                
                ayuda_vigia += "📢 **Comandos de Canal:**\n"
                ayuda_vigia += "• `!vigiacanal suscribir <categoría> [feed_id]` - Suscribir canal\n"
                ayuda_vigia += "• `!vigiacanal cancelar <categoría> [feed_id]` - Cancelar canal\n"
                ayuda_vigia += "• `!vigiacanal estado` - Ver suscripciones del canal\n"
                ayuda_vigia += "• `!vigiacanal palabras \"palabras\"` - Palabras clave para canal\n\n"
                
                ayuda_vigia += "⚙️ **Administración:**\n"
                ayuda_vigia += "• `!vigia agregar_feed <nombre> <url> <categoría> [tipo]` - Agregar feed\n\n"
                
                ayuda_vigia += "📂 **Categorías:** economia, internacional, tecnologia, sociedad, politica\n\n"
                
                ayuda_vigia += "🔔 **Alertas Críticas:**\n"
                ayuda_vigia += "• `!avisanoticias` - Suscribirse a alertas críticas\n"
                ayuda_vigia += "• `!noavisanoticias` - Cancelar suscripción a alertas\n\n"
                
                ayuda_vigia += "🌐 **Fuentes por Defecto:**\n"
                ayuda_vigia += "• CNBC (economia) • El País (internacional) • Reuters (internacional)\n"
                ayuda_vigia += "• BBC (tecnologia) • CNN (general) • Crypto News (cripto)\n\n"
                
                ayuda_vigia += "💡 **Ejemplos:**\n"
                ayuda_vigia += "```\n!vigia feeds                    # Ver feeds\n!vigia suscribir economia         # Noticias económicas\n!vigia general internacional      # Noticias con IA\n!vigia palabras \"bitcoin,crypto\"  # Alertas crypto\n!vigiacanal suscribir politica     # Suscribir canal\n```\n\n"
                
                ayuda_vigia += "⚡ **Características:** Monitorización 24/7, IA, clasificación automática, notificaciones instantáneas, filtrado por palabras clave, detección de eventos críticos."
                
                try:
                    await ctx.author.send(ayuda_vigia)
                    if ctx.guild:
                        await ctx.send(mensaje_privado)
                except discord.errors.Forbidden:
                    await ctx.send(ayuda_vigia[:2000])
        
        # Comandos de canal (solo en servidor)
        if bot.get_command("vigiacanal") is None:
            logger.info("📡 [DISCORD] Registrando comando vigiacanal")
            
            @bot.command(name="vigiacanal")
            async def cmd_vigia_canal(ctx, *args):
                """Comandos del Vigía para el canal (solo en servidor)."""
                if not VIGIA_COMMANDS_AVAILABLE:
                    await ctx.send("❌ El Vigía de Noticias no está disponible en este servidor.")
                    return
                
                if ctx.guild is None:
                    await ctx.send("❌ Este comando solo se puede usar en un servidor, no en mensajes directos.")
                    return
                
                if not args:
                    await ctx.send("❌ Debes especificar una acción. Usa `!vigiaayuda` para ver ayuda.")
                    return
                
                # Procesar subcomandos de canal
                subcommand = args[0].lower()
                subargs = args[1:] if len(args) > 1 else []
                
                try:
                    if subcommand == "suscribir":
                        await vigia_commands.cmd_canal_suscribir(ctx, subargs)
                    elif subcommand == "cancelar":
                        await vigia_commands.cmd_canal_cancelar(ctx, subargs)
                    elif subcommand == "estado":
                        await vigia_commands.cmd_canal_estado(ctx, subargs)
                    elif subcommand == "palabras":
                        await vigia_commands.cmd_canal_palabras(ctx, subargs)
                    else:
                        await ctx.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!vigiaayuda` para ver ayuda.")
                except Exception as e:
                    logger.error(f"Error en comando vigiacanal {subcommand}: {e}")
                    await ctx.send("❌ Error al ejecutar el comando. Inténtalo de nuevo.")
    
    elif role_name == "buscador_tesoros":
        # Importar pensar para el subrol POE2
        from agent_engine import pensar
        
        # Comandos del subrol POE2
        if bot.get_command("buscartesoros") is None:
            logger.info("🔮 [DISCORD] Registrando comando buscartesoros")
            
            @bot.command(name="buscartesoros")
            async def cmd_buscar_tesoros(ctx, subrol: str = ""):
                if not subrol or subrol.lower() != "poe2":
                    role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
                    subrol_msg = role_cfg.get("subrol_required", "❌ Debes especificar el subrol. Ejemplo: !buscartesoros poe2")
                    await ctx.send(subrol_msg.format(command="buscartesoros"))
                    return
                
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                if db_poe2_instance.set_activo(True):
                    await ctx.send(f"✅ {ctx.author.mention} Subrol POE2 activado. Ahora buscaré tesoros en Path of Exile 2.")
                    logger.info(f"🔮 [POE2] {ctx.author.name} activó el subrol en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al activar el subrol POE2. Inténtalo de nuevo.")
        
        if bot.get_command("nobuscartesoros") is None:
            logger.info("🔮 [DISCORD] Registrando comando nobuscartesoros")
            
            @bot.command(name="nobuscartesoros")
            async def cmd_no_buscar_tesoros(ctx, subrol: str = ""):
                if not subrol or subrol.lower() != "poe2":
                    role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
                    subrol_msg = role_cfg.get("subrol_required", "❌ Debes especificar el subrol. Ejemplo: !nobuscartesoros poe2")
                    await ctx.send(subrol_msg.format(command="nobuscartesoros"))
                    return
                
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                if db_poe2_instance.set_activo(False):
                    await ctx.send(f"✅ {ctx.author.mention} Subrol POE2 desactivado. Ya no buscaré tesoros en Path of Exile 2.")
                    logger.info(f"🔮 [POE2] {ctx.author.name} desactivó el subrol en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al desactivar el subrol POE2. Inténtalo de nuevo.")
        
        if bot.get_command("poe2liga") is None:
            logger.info("🔮 [DISCORD] Registrando comando poe2liga")
            
            @bot.command(name="poe2liga")
            async def cmd_poe2_liga(ctx, liga: str = ""):
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                if not liga:
                    db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                    if not db_poe2_instance:
                        await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                        return
                    
                    liga_actual = db_poe2_instance.get_liga()
                    await ctx.send(f"🔮 **Liga POE2 actual**: {liga_actual}")
                    return
                
                liga_lower = liga.lower()
                if liga_lower not in ["standard", "fate of the vaal"]:
                    await ctx.send("❌ Liga no válida. Las ligas disponibles son: `Standard` y `Fate of the Vaal`")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                liga_formateada = "Fate of the Vaal" if liga_lower == "fate of the vaal" else "Standard"
                if db_poe2_instance.set_liga(liga_formateada):
                    await ctx.send(f"✅ {ctx.author.mention} Liga POE2 establecida a: {liga_formateada}")
                    logger.info(f"🔮 [POE2] {ctx.author.name} cambió liga a {liga_formateada} en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al cambiar la liga. Inténtalo de nuevo.")
        
        if bot.get_command("poe2add") is None:
            logger.info("🔮 [DISCORD] Registrando comando poe2add")
            
            @bot.command(name="poe2add")
            async def cmd_poe2_add(ctx, item_name: str = ""):
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                if not item_name:
                    await ctx.send("❌ Debes especificar el nombre del item. Ejemplo: !poe2add \"Ancient Rib\"")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                if db_poe2_instance.add_objetivo(item_name):
                    await ctx.send(f"✅ {ctx.author.mention} Item añadido a objetivos: {item_name}")
                    logger.info(f"🔮 [POE2] {ctx.author.name} añadió objetivo {item_name} en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al añadir el item. Inténtalo de nuevo.")
        
        if bot.get_command("poe2del") is None:
            logger.info("🔮 [DISCORD] Registrando comando poe2del")
            
            @bot.command(name="poe2del")
            async def cmd_poe2_del(ctx, item_name: str = ""):
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                if not item_name:
                    await ctx.send("❌ Debes especificar el nombre del item. Ejemplo: !poe2del \"Ancient Rib\"")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                if db_poe2_instance.remove_objetivo(item_name):
                    await ctx.send(f"✅ {ctx.author.mention} Item eliminado de objetivos: {item_name}")
                    logger.info(f"🔮 [POE2] {ctx.author.name} eliminó objetivo {item_name} en {ctx.guild.name}")
                else:
                    await ctx.send(f"❌ No se encontró el item '{item_name}' en la lista de objetivos.")
        
        if bot.get_command("poe2list") is None:
            logger.info("🔮 [DISCORD] Registrando comando poe2list")
            
            @bot.command(name="poe2list")
            async def cmd_poe2_list(ctx):
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                liga_actual = db_poe2_instance.get_liga()
                activo = db_poe2_instance.is_activo()
                objetivos = db_poe2_instance.get_objetivos()
                
                estado = "🟢 Activo" if activo else "🔴 Inactivo"
                
                response = f"🔮 **Configuración POE2**\n"
                response += f"📊 **Estado**: {estado}\n"
                response += f"🏆 **Liga**: {liga_actual}\n"
                response += f"🎯 **Objetivos** ({len(objetivos)} items):\n"
                
                if objetivos:
                    for i, (nombre, item_id, activo_item, fecha) in enumerate(objetivos, 1):
                        estado_item = "✅" if activo_item else "❌"
                        response += f"  {i}. {estado_item} {nombre}\n"
                else:
                    response += "  *No hay items configurados*\n"
                
                await ctx.send(response)
        
        if bot.get_command("poe2ayuda") is None:
            logger.info("🔮 [DISCORD] Registrando comando poe2ayuda")
            
            @bot.command(name="poe2ayuda")
            async def cmd_poe2_ayuda(ctx):
                """Muestra ayuda específica para el subrol POE2."""
                ayuda_poe2 = "🔮 **AYUDA DEL BUSCADOR DE TESOROS - POE2**\n\n"
                ayuda_poe2 += "🎯 **Activación:**\n"
                ayuda_poe2 += "• `!buscartesoros poe2` - Activa el subrol POE2\n"
                ayuda_poe2 += "• `!nobuscartesoros poe2` - Desactiva el subrol POE2\n\n"
                ayuda_poe2 += "🏆 **Gestión de Liga:**\n"
                ayuda_poe2 += "• `!poe2liga` - Muestra la liga actual\n"
                ayuda_poe2 += "• `!poe2liga Standard` - Establece liga Standard\n"
                ayuda_poe2 += "• `!poe2liga Fate of the Vaal` - Establece liga Fate of the Vaal\n\n"
                ayuda_poe2 += "🎯 **Gestión de Objetivos:**\n"
                ayuda_poe2 += "• `!poe2add \"Nombre del Item\"` - Añade item a objetivos\n"
                ayuda_poe2 += "• `!poe2del \"Nombre del Item\"` - Elimina item de objetivos\n"
                ayuda_poe2 += "• `!poe2list` - Muestra configuración y objetivos actuales\n\n"
                ayuda_poe2 += "📊 **Items Conocidos:**\n"
                ayuda_poe2 += "• Ancient Rib • Ancient Collarbone • Ancient Jawbone\n"
                ayuda_poe2 += "• Fracturing Orb • Chaos Orb • Divine Orb\n\n"
                ayuda_poe2 += "⚖️ **Lógica de Compra/Venta:**\n"
                ayuda_poe2 += "• **COMPRA**: Precio ≤ mínimo histórico × 1.15\n"
                ayuda_poe2 += "• **VENTA**: Precio ≥ máximo histórico × 0.85\n\n"
                ayuda_poe2 += "💡 **Ejemplos de Uso:**\n"
                ayuda_poe2 += "```\n!buscartesoros poe2\n!poe2liga Fate of the Vaal\n!poe2add \"Ancient Rib\"\n!poe2add \"Fracturing Orb\"\n!poe2list\n```"
                
                try:
                    await ctx.author.send(ayuda_poe2)
                    await ctx.send("📩 Ayuda enviada por mensaje privado.")
                except discord.errors.Forbidden:
                    await ctx.send(ayuda_poe2)
    
    elif role_name == "buscar_anillo":
        if bot.get_command("acusaranillo") is None:
            logger.info("👁️ [DISCORD] Registrando comando acusaranillo")
            
            @bot.command(name="acusaranillo")
            async def cmd_acusar_anillo(ctx, target: str = ""):
                if not target:
                    await ctx.send("❌ Debes mencionar a alguien para acusar. Ejemplo: !acusaranillo @usuario")
                    return
                
                db_instance = get_db_for_server(ctx.guild)
                
                mentioned_user = None
                for user in ctx.message.mentions:
                    if not user.bot and user.id != ctx.author.id:
                        mentioned_user = user
                        break
                
                if not mentioned_user:
                    await ctx.send("❌ No se encontró un usuario válido para acusar.")
                    return
                
                accusation_prompt = f"Acusa brevemente a {mentioned_user.display_name} de tener el anillo uniko. Sé orco y directo."
                accusation = await asyncio.to_thread(pensar, accusation_prompt)
                
                await ctx.send(f"👁️ {mentioned_user.mention} {accusation}")
                
                await asyncio.to_thread(
                    db_instance.registrar_interaccion,
                    ctx.author.id,
                    ctx.author.name,
                    "ACUSACION_ANILLO",
                    f"Acusó a {mentioned_user.name} por el anillo",
                    ctx.channel.id,
                    ctx.guild.id,
                    metadata={"acusado": mentioned_user.id, "acusacion": accusation}
                )
                
                logger.info(f"👁️ [ANILLO] {ctx.author.name} acusó a {mentioned_user.name} en {ctx.guild.name}")
    
    elif role_name == "trilero":
        if bot.get_command("trilero") is None:
            logger.info("🎭 [DISCORD] Registrando comando trilero")
            
            @bot.command(name="trilero")
            async def cmd_trilero(ctx):
                """Activa el rol trilero."""
                if not ORO_DB_AVAILABLE:
                    await ctx.send("❌ El sistema del trilero no está disponible en este servidor.")
                    return
                
                db_oro_instance = get_oro_db_for_server(ctx.guild)
                if not db_oro_instance:
                    await ctx.send("❌ Error al acceder a la base de datos del trilero.")
                    return
                
                usuario_id = str(ctx.author.id)
                usuario_nombre = ctx.author.name
                
                if not db_oro_instance.esta_suscrito(usuario_id, str(ctx.guild.id)):
                    await ctx.send(f"{get_message('trilero_not_subscribed')} {ctx.author.mention}")
                    return
                
                if db_oro_instance.agregar_suscripcion(usuario_id, usuario_nombre, str(ctx.guild.id)):
                    await ctx.send(f"{get_message('trilero_subscribe')} {ctx.author.mention}")
                    logger.info(f"🎭 [TRILERO] {usuario_nombre} ({usuario_id}) se suscribió al rol trilero en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al suscribirte al rol trilero. Inténtalo de nuevo.")
        
        if bot.get_command("notrilero") is None:
            logger.info("🎭 [DISCORD] Registrando comando notrilero")
            
            @bot.command(name="notrilero")
            async def cmd_no_trilero(ctx):
                """Desactiva el rol trilero."""
                if not ORO_DB_AVAILABLE:
                    await ctx.send("❌ El sistema del trilero no está disponible en este servidor.")
                    return
                
                db_oro_instance = get_oro_db_for_server(ctx.guild)
                if not db_oro_instance:
                    await ctx.send("❌ Error al acceder a la base de datos del trilero.")
                    return
                
                usuario_id = str(ctx.author.id)
                usuario_nombre = ctx.author.name
                
                if not db_oro_instance.esta_suscrito(usuario_id, str(ctx.guild.id)):
                    await ctx.send(f"{get_message('trilero_not_subscribed')} {ctx.author.mention}")
                    return
                
                if db_oro_instance.eliminar_suscripcion(usuario_id, str(ctx.guild.id)):
                    await ctx.send(f"{get_message('trilero_unsubscribe')} {ctx.author.mention}")
                    logger.info(f"🎭 [TRILERO] {usuario_nombre} ({usuario_id}) se desuscrito del rol trilero en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al desuscribirte del rol trilero. Inténtalo de nuevo.")
        
        if bot.get_command("trato") is None:
            logger.info("🎭 [DISCORD] Registrando comando trato")
            
            @bot.command(name="trato")
            async def cmd_trato(ctx, target: str = "", amount: str = ""):
                """Ofrece un trato sospechoso."""
                if not ORO_DB_AVAILABLE:
                    await ctx.send("❌ El sistema del trilero no está disponible en este servidor.")
                    return
                
                if not target or not amount:
                    await ctx.send("❌ Debes mencionar a alguien y una cantidad. Ejemplo: !trato @usuario 100")
                    return
                
                db_oro_instance = get_oro_db_for_server(ctx.guild)
                if not db_oro_instance:
                    await ctx.send("❌ Error al acceder a la base de datos del trilero.")
                    return
                
                mentioned_user = None
                for user in ctx.message.mentions:
                    if not user.bot and user.id != ctx.author.id:
                        mentioned_user = user
                        break
                
                if not mentioned_user:
                    await ctx.send("❌ No se encontró un usuario válido para el trato.")
                    return
                
                try:
                    amount_int = int(amount)
                    if amount_int <= 0:
                        await ctx.send("❌ La cantidad debe ser un número positivo.")
                        return
                except ValueError:
                    await ctx.send("❌ La cantidad debe ser un número válido.")
                    return
                
                trato_prompt = f"Ofrece un trato sospechoso y tentador a {mentioned_user.display_name} por {amount_int} de oro. Sé manipulador y persuasivo, como un trilero."
                trato = await asyncio.to_thread(pensar, trato_prompt)
                
                await ctx.send(f"🎭 {mentioned_user.mention} {trato}")
                
                await asyncio.to_thread(
                    db_oro_instance.registrar_interaccion,
                    ctx.author.id,
                    ctx.author.name,
                    "TRATO_OFRECIDO",
                    f"Ofreció trato a {mentioned_user.name} por {amount_int} de oro",
                    ctx.channel.id,
                    ctx.guild.id,
                    metadata={"objetivo": mentioned_user.id, "cantidad": amount_int, "trato": trato}
                )
                
                logger.info(f"🎭 [TRILERO] {ctx.author.name} ofreció trato a {mentioned_user.name} por {amount_int} en {ctx.guild.name}")
        
        if bot.get_command("pediroro") is None:
            logger.info("🎭 [DISCORD] Registrando comando pediroro")
            
            @bot.command(name="pediroro")
            async def cmd_pedir_oro(ctx, amount: str = ""):
                """Pide oro de forma sospechosa."""
                if not ORO_DB_AVAILABLE:
                    await ctx.send("❌ El sistema del trilero no está disponible en este servidor.")
                    return
                
                if not amount:
                    await ctx.send("❌ Debes especificar una cantidad. Ejemplo: !pediroro 50")
                    return
                
                try:
                    amount_int = int(amount)
                    if amount_int <= 0:
                        await ctx.send("❌ La cantidad debe ser un número positivo.")
                        return
                except ValueError:
                    await ctx.send("❌ La cantidad debe ser un número válido.")
                    return
                
                oro_prompt = f"Pide {amount_int} de oro de forma sospechosa y manipuladora. Inventa una excusa convincente pero dudosa. Sé un trilero experto."
                peticion = await asyncio.to_thread(pensar, oro_prompt)
                
                await ctx.send(f"💰 {peticion}")
                
                db_oro_instance = get_oro_db_for_server(ctx.guild)
                await asyncio.to_thread(
                    db_oro_instance.registrar_interaccion,
                    ctx.author.id,
                    ctx.author.name,
                    "ORO_PEDIDO",
                    f"Pidió {amount_int} de oro",
                    ctx.channel.id,
                    ctx.guild.id,
                    metadata={"cantidad": amount_int, "peticion": peticion}
                )
                
                logger.info(f"🎭 [TRILERO] {ctx.author.name} pidió {amount_int} de oro en {ctx.guild.name}")
    
    logger.info(f"🎭 [DISCORD] Comandos registrados para rol: {role_name}")

# Comandos dinámicos para control de roles
@bot.command(name="rolekronk")
async def cmd_role_kronk(ctx, role_name: str, action: str = ""):
    """Control de roles para KRONK. Uso: !rolekronk <rol> <on/off>"""
    if not role_name:
        await ctx.send("❌ Debes especificar un rol. Ejemplo: !rolekronk vigia_noticias on")
        return
    
    if not action:
        await ctx.send("❌ Debes especificar una acción. Ejemplo: !rolekronk vigia_noticias on")
        return
    
    action_lower = action.lower()
    if action_lower in ["on", "true", "1", "activar", "enable"]:
        await _cmd_role_toggle(ctx, role_name, True)
    elif action_lower in ["off", "false", "0", "desactivar", "disable"]:
        await _cmd_role_toggle(ctx, role_name, False)
    else:
        await ctx.send("❌ Acción no válida. Usa: on/off, true/false, 1/0, activar/desactivar")

logger.info(f"🤖 [DISCORD] Comando de roles registrado: rolekronk")

# --- FUNCIONES DE REGISTRO DE COMANDOS MC ---
def register_mc_commands():
    """Registra comandos MC según el modo configurado."""
    from agent_engine import is_mc_enabled, get_mc_mode, get_mc_feature
    
    if not is_mc_enabled():
        logger.info("🎵 [DISCORD] MC desactivado en configuración")
        return
    
    mc_mode = get_mc_mode()
    logger.info(f"🎵 [DISCORD] MC modo: '{mc_mode}'")
    
    if mc_mode == "integrated":
        register_mc_integrated()
    elif mc_mode == "standalone":
        register_mc_standalone()
    else:
        logger.warning(f"🎵 [DISCORD] MC modo '{mc_mode}' no reconocido")

def register_mc_integrated():
    """Registra comandos MC integrados en el bot principal."""
    from agent_engine import get_mc_feature, get_mc_voice_settings, get_mc_audio_quality
    
    if not MC_COMMANDS_AVAILABLE:
        logger.warning("🎵 [DISCORD] MC integrado requiere yt-dlp y PyNaCl")
        @bot.command(name="mc")
        async def mc_unavailable(ctx):
            await ctx.send("🎵 El MC no está disponible (requiere `yt-dlp` y `PyNaCl`).")
        return
    
    logger.info("🎵 [DISCORD] Registrando MC integrado")
    mc_commands_instance = MCCommands(bot)
    
    @bot.group(name="mc")
    async def mc_group(ctx):
        """Comandos del MC (música)."""
        # Verificar duplicados
        if is_duplicate_command(ctx, "mc"):
            return
        if ctx.invoked_subcommand is None:
            music_help = PERSONALIDAD.get("discord", {}).get("role_messages", {}).get("music_help", "🎵 Usa `!mc help` para ver los comandos disponibles")
            await ctx.send(music_help)
    
    # Registrar comandos según features activadas
    if get_mc_feature("voice_commands"):
        for cmd_name, cmd_func in COMANDOS_MC.items():
            if cmd_name in ["play", "skip", "stop", "pause", "resume", "volume", "nowplaying", "np", "history", "leave", "disconnect"]:
                try:
                    def make_mc_command(name, func):
                        async def command(ctx, *args):
                            # Verificar duplicados
                            if is_duplicate_command(ctx, f"mc_{name}"):
                                return
                            return await func(mc_commands_instance, ctx.message, list(args))
                        return command
                    mc_group.command(name=cmd_name)(make_mc_command(cmd_name, cmd_func))
                    logger.info(f"🎵 [DISCORD] Comando mc {cmd_name} registrado")
                except Exception as e:
                    logger.error(f"Error registrando comando mc {cmd_name}: {e}")
    
    # Registrar comando help (siempre disponible)
    try:
        def make_mc_command(name, func):
            async def command(ctx, *args):
                # Verificar duplicados
                if is_duplicate_command(ctx, f"mc_{name}"):
                    return
                return await func(mc_commands_instance, ctx.message, list(args))
            return command
        mc_group.command(name="help")(make_mc_command("help", MCCommands.cmd_help))
        mc_group.command(name="commands")(make_mc_command("commands", MCCommands.cmd_help))
        logger.info("🎵 [DISCORD] Comando mc help registrado")
    except Exception as e:
        logger.error(f"Error registrando comando mc help: {e}")
    
    if get_mc_feature("queue_management"):
        for cmd_name, cmd_func in COMANDOS_MC.items():
            if cmd_name in ["queue", "clear", "shuffle", "remove", "add"]:
                try:
                    def make_mc_command(name, func):
                        async def command(ctx, *args):
                            if is_duplicate_command(ctx, f"mc_{name}"):
                                return
                            return await func(mc_commands_instance, ctx.message, list(args))
                        return command
                    mc_group.command(name=cmd_name)(make_mc_command(cmd_name, cmd_func))
                    logger.info(f"🎵 [DISCORD] Comando mc {cmd_name} registrado")
                except Exception as e:
                    logger.error(f"Error registrando comando mc {cmd_name}: {e}")
    
    logger.info(f"🎵 [DISCORD] MC integrado registrado con {len(mc_group.commands)} comandos")

def register_mc_standalone():
    """Mantiene MC como proceso separado (comportamiento actual)."""
    logger.info("🎵 [DISCORD] MC modo standalone - delegando a proceso separado")
    # No registrar comandos aquí, los maneja el proceso MC separado

# --- FUNCIÓN PRINCIPAL DE REGISTRO ---
def register_role_commands():
    """Registra comandos de roles (idempotente: omite comandos ya registrados)."""
    global _commands_registered
    
    if _commands_registered:
        logger.info("🎭 [DISCORD] Comandos ya registrados, omitiendo registro duplicado")
        return
    
    import os
    
    def is_role_enabled(role_name):
        env_var = os.getenv(f"{role_name.upper()}_ENABLED", "").lower()
        if env_var:
            logger.info(f"🔍 Verificando {role_name}: env_var={env_var} -> {env_var == 'true'}")
            return env_var == "true"
        enabled = agent_config.get("roles", {}).get(role_name, {}).get("enabled", False)
        logger.info(f"🔍 Verificando {role_name}: config={enabled}")
        return enabled

    # --- Comandos del Vigía de Noticias ---
    # OMITIR este registro - ahora se maneja en register_specific_role_commands
    logger.info("📡 [DISCORD] Omitiendo registro antiguo del Vigía - ahora manejado por register_commands_for_enabled_roles")

    # --- MC (Master of Ceremonies): registrar según configuración dinámica ---
    # OMITIR - ahora se maneja en register_commands_for_enabled_roles
    logger.info("🎵 [DISCORD] Omitiendo registro MC - ahora manejado por register_commands_for_enabled_roles en on_ready")

    # --- Comandos del trilero: siempre registrar si está disponible ---
    if ORO_DB_AVAILABLE and bot.get_command("trilero") is None:
        logger.info("🎭 [DISCORD] Registrando comandos del trilero")
        
        @bot.command(name="trilero")
        async def cmd_trilero(ctx):
            """Activa el rol trilero."""
            if not ORO_DB_AVAILABLE:
                await ctx.send("❌ El sistema del trilero no está disponible en este servidor.")
                return
            
            db_oro_instance = get_oro_db_for_server(ctx.guild)
            if not db_oro_instance:
                await ctx.send("❌ Error al acceder a la base de datos del trilero.")
                return
            
            usuario_id = str(ctx.author.id)
            usuario_nombre = ctx.author.name
            
            if not db_oro_instance.esta_suscrito(usuario_id, str(ctx.guild.id)):
                await ctx.send(f"{get_message('trilero_not_subscribed')} {ctx.author.mention}")
                return
            
            if db_oro_instance.agregar_suscripcion(usuario_id, usuario_nombre, str(ctx.guild.id)):
                await ctx.send(f"{get_message('trilero_subscribe')} {ctx.author.mention}")
                logger.info(f"🎭 [TRILERO] {usuario_nombre} ({usuario_id}) se suscribió al rol trilero en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al suscribirte al rol trilero. Inténtalo de nuevo.")
        
        @bot.command(name="notrilero")
        async def cmd_no_trilero(ctx):
            """Desactiva el rol trilero."""
            if not ORO_DB_AVAILABLE:
                await ctx.send("❌ El sistema del trilero no está disponible en este servidor.")
                return
            
            db_oro_instance = get_oro_db_for_server(ctx.guild)
            if not db_oro_instance:
                await ctx.send("❌ Error al acceder a la base de datos del trilero.")
                return
            
            usuario_id = str(ctx.author.id)
            usuario_nombre = ctx.author.name
            
            if not db_oro_instance.esta_suscrito(usuario_id, str(ctx.guild.id)):
                await ctx.send(f"{get_message('trilero_not_subscribed')} {ctx.author.mention}")
                return
            
            if db_oro_instance.eliminar_suscripcion(usuario_id, str(ctx.guild.id)):
                await ctx.send(f"{get_message('trilero_unsubscribe')} {ctx.author.mention}")
                logger.info(f"🎭 [TRILERO] {usuario_nombre} ({usuario_id}) se desuscrito del rol trilero en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al desuscribirte del rol trilero. Inténtalo de nuevo.")
    else:
        logger.info("🎭 [DISCORD] Comandos del trilero ya registrados, omitiendo")
    
    # Marcar como registrado para evitar duplicaciones
    _commands_registered = True
    logger.info("🎭 [DISCORD] Registro de comandos completado")

# --- INICIO DEL BOT ---
if __name__ == "__main__":
    try:
        # Registrar comandos condicionales antes de iniciar el bot
        try:
            # OMITIR register_role_commands - ahora se maneja en on_ready
            logger.info("📡 [DISCORD] Omitiendo register_role_commands - ahora manejado por register_commands_for_enabled_roles en on_ready")
            logger.info(f"✅ [DISCORD] Total de comandos registrados: {len(bot.commands)}")
        except Exception as e:
            logger.error(f"❌ Error en registro de comandos: {e}")
            import traceback
            traceback.print_exc()

        bot.run(get_discord_token())
    except KeyboardInterrupt:
        logger.info("👋 [DISCORD] Bot detenido por el usuario")
    except Exception as e:
        logger.error(f"❌ [DISCORD] Error fatal: {e}")
        import traceback
        traceback.print_exc()
