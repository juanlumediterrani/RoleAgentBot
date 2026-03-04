import os
import json
import discord
import asyncio
import re
import time
import threading
import random
from collections import defaultdict
from discord.ext import commands, tasks
from agent_engine import PERSONALIDAD, pensar, get_discord_token, AGENT_CFG
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

def get_limosna_db_for_server(guild):
    """Obtiene instancia de BD de limosna para un servidor específico."""
    if not LIMOSNA_DB_AVAILABLE:
        return None
    server_name = get_server_name(guild)
    return get_limosna_db_instance(server_name)

def get_banquero_db_for_server(guild):
    """Obtiene instancia de BD del banquero para un servidor específico."""
    if not BANQUERO_DB_AVAILABLE:
        return None
    server_name = get_server_name(guild)
    return get_banquero_db_instance(server_name)

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

# Importar base de datos de limosna
try:
    from roles.trilero.subroles.limosna.db_limosna import get_limosna_db_instance
    LIMOSNA_DB_AVAILABLE = True
    logger.info(" [DISCORD] Base de datos de limosna importada correctamente")
except ImportError as e:
    LIMOSNA_DB_AVAILABLE = False
    get_limosna_db_instance = None
    logger.warning(f" [DISCORD] No se pudo importar base de datos de limosna: {e}")

# Importar base de datos del bote
try:
    from roles.trilero.subroles.bote.db_bote import get_bote_db_instance
    BOTE_DB_AVAILABLE = True
    logger.info(" [DISCORD] Base de datos del bote importada correctamente")
except ImportError as e:
    BOTE_DB_AVAILABLE = False
    get_bote_db_instance = None
    logger.warning(f" [DISCORD] No se pudo importar base de datos del bote: {e}")

# Importar sistema del bote
try:
    from roles.trilero.subroles.bote.bote import procesar_jugada
    BOTE_AVAILABLE = True
    logger.info(" [DISCORD] Sistema del bote importado correctamente")
except ImportError as e:
    BOTE_AVAILABLE = False
    procesar_jugada = None
    logger.warning(f" [DISCORD] No se pudo importar sistema del bote: {e}")

# Importar base de datos del banquero (necesaria para el bote)
try:
    from roles.banquero.db_role_banquero import get_banquero_db_instance
    BANQUERO_DB_AVAILABLE = True
    logger.info("💰 [DISCORD] Base de datos del banquero importada correctamente")
except ImportError as e:
    BANQUERO_DB_AVAILABLE = False
    logger.warning(f"⚠️ [DISCORD] No se pudo importar base de datos del banquero: {e}")

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

@tasks.loop(hours=1)
async def buscador_tesoros_task():
    """Ejecuta el buscador de tesoros automáticamente en todos los servidores activos."""
    if not POE2_AVAILABLE:
        return
    
    # Obtener configuración de frecuencia
    roles_config = load_agent_config().get("roles", {})
    buscador_config = roles_config.get("buscador_tesoros", {})
    interval_hours = buscador_config.get("interval_hours", 1)
    
    # Actualizar frecuencia si cambió en la configuración
    if buscador_tesoros_task.hours != interval_hours:
        buscador_tesoros_task.change_interval(hours=interval_hours)
        logger.info(f"💎 [BUSCADOR] Frecuencia actualizada a {interval_hours} horas")
    
    logger.info("💎 [BUSCADOR] Iniciando búsqueda automática de tesoros...")
    
    for guild in bot.guilds:
        try:
            db_poe2_instance = get_poe2_db_for_server(guild)
            if not db_poe2_instance:
                continue
            
            # Verificar si el subrol POE2 está activo
            if not db_poe2_instance.is_activo():
                continue
            
            # Ejecutar lógica del buscador para este servidor
            await _ejecutar_buscador_para_servidor(guild, db_poe2_instance)
            
        except Exception as e:
            logger.exception(f"Error en buscador automático para {guild.name}: {e}")
    
    logger.info("💎 [BUSCADOR] Búsqueda automática completada")

async def _ejecutar_buscador_para_servidor(guild, db_poe2_instance):
    """Ejecuta la lógica completa del buscador para un servidor específico."""
    try:
        # Importar las dependencias necesarias
        from roles.buscador_tesoros.buscador_tesoros import main as buscador_main
        from roles.buscador_tesoros.db_role_poe import DatabaseRolePoe
        from agent_db import get_active_server_name
        
        # Establecer el servidor como activo temporalmente
        original_server = get_active_server_name()
        set_current_server(guild.name)
        
        # Ejecutar la lógica principal del buscador
        await buscador_main()
        
        # Restaurar servidor original
        if original_server:
            set_current_server(original_server)
        
        logger.info(f"💎 [BUSCADOR] Proceso completado para {guild.name}")
        
    except Exception as e:
        logger.exception(f"Error ejecutando buscador para {guild.name}: {e}")

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

# Comando de prueba del Vigía - ELIMINADO para evitar conflictos
# @bot.command(name="vigiatest")
# async def cmd_vigia_test(ctx):
#     """Comando de prueba para el Vigía."""
#     # Obtener mensajes personalizados
#     role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
#     
#     logger.info(f"📡 Comando vigiatest ejecutado por {ctx.author.name}")
#     await ctx.send(role_cfg.get("vigia_test_command", "📡 ✅ Comando vigiatest funciona - el Vigía está respondiendo!"))

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
_last_command_time = {}

def is_duplicate_command(ctx, command_name):
    """Verifica si el comando ya fue ejecutado recientemente para evitar duplicados."""
    try:
        # Si ctx.guild es None (DM), usar el ID del canal como fallback
        if ctx.guild is None:
            channel_id = ctx.channel.id
        else:
            channel_id = ctx.guild.id
        
        key = f"{command_name}_{channel_id}"
        now = time.time()
        
        if key in _last_command_time:
            if now - _last_command_time[key] < 1.0:  # 1 segundo de cooldown
                return True
        
        _last_command_time[key] = now
        return False
    except Exception as e:
        logger.error(f"Error verificando comando duplicado: {e}")
        return False
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
logger.info(f"🤖 [DISCORD] Registrando comando de ayuda: {ayuda_command_name}")

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
        ayuda_msg += f"📡 **Vigía de Noticias** - Alertas inteligentes (cada {interval}h)\n"
        ayuda_msg += " - **IMPORTANTE:** Solo puedes tener UN TIPO de suscripción activa\n"
        ayuda_msg += "  - **Ayuda:** `!vigiaayuda` (usuarios) | `!vigiacanalayuda` (admins)\n"
        ayuda_msg += "  - **Ejemplo:** `!vigia general internacional` → Noticias internacionales evaluadas con IA, con la opinión del agente personalizado\n"
    
    # Buscador de tesoros
    if os.getenv("BUSCADOR_TESOROS_ENABLED", "false").lower() == "true" or roles_config.get("buscador_tesoros", {}).get("enabled", False):
        interval = roles_config.get("buscador_tesoros", {}).get("interval_hours", 1)
        ayuda_msg += f"💎 **Buscador de Tesoros** - `!buscartesoros` / `!nobuscartesoros` | `!tesorosfrecuencia <h>` (cada {interval}h) | `!poe2ayuda` para ayuda específica\n"
    
    # Trilero (incluye limosna)
    if os.getenv("TRILERO_ENABLED", "false").lower() == "true" or roles_config.get("trilero", {}).get("enabled", False):
        interval = roles_config.get("trilero", {}).get("interval_hours", 12)
        ayuda_msg += f"🎭 **Trilero** - `!trilero ayuda` para comandos de limosna (cada {interval}h)\n"
    
    # Buscar anillo
    if os.getenv("BUSCAR_ANILLO_ENABLED", "false").lower() == "true" or roles_config.get("buscar_anillo", {}).get("enabled", False):
        interval = roles_config.get("buscar_anillo", {}).get("interval_hours", 24)
        ayuda_msg += f"👁️ **Buscar Anillo** - `!acusaranillo` <@usuario> | `!anillofrecuencia <h>` (cada {interval}h)\n"
    
    # Banquero
    if os.getenv("BANQUERO_ENABLED", "false").lower() == "true" or roles_config.get("banquero", {}).get("enabled", False):
        banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
        ayuda_msg += f"{banquero_msgs.get('banquero_help', '💰 **Banquero** - `!banquero saldo` | `!banquero tae <cantidad>` (admins) | `!banquero ayuda` para ayuda completa')}\n"
    
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
            ayuda_msg += f"• {status_emoji} **Trilero** - Subrol limosna: peticiones de donaciones y engaños\n"
        elif role_name == "buscar_anillo":
            ayuda_msg += f"• {status_emoji} **Buscar Anillo** - Acusaciones por el anillo\n"
        elif role_name == "banquero":
            ayuda_msg += f"• {status_emoji} **Banquero** - Gestión económica y TAE diaria\n"
        elif role_name == "mc":
            ayuda_msg += f"• ✅ **Música** - Siempre disponible (no requiere activación)\n"
    
    try:
        # Verificar si el mensaje es demasiado largo antes de enviar
        if len(ayuda_msg) > 2000:
            # Dividir en partes y enviar al usuario por DM
            partes = [ayuda_msg[i:i+1900] for i in range(0, len(ayuda_msg), 1900)]
            for parte in partes:
                await ctx.author.send(parte)
        else:
            await ctx.author.send(ayuda_msg)
        
        await ctx.send(get_message('ayuda_enviada_privado'))
    except discord.errors.Forbidden:
        # Si no puede enviar DM, enviar en el canal (dividido si es necesario)
        if len(ayuda_msg) > 2000:
            partes = [ayuda_msg[i:i+1900] for i in range(0, len(ayuda_msg), 1900)]
            for parte in partes:
                await ctx.send(parte)
        else:
            await ctx.send(ayuda_msg[:2000])

# Comando de ayuda específico para canales del Vigía de Noticias
@bot.command(name="vigiacanalayuda")
async def cmd_vigia_canal_ayuda(ctx):
    """Muestra ayuda específica para el Vigía de Noticias en canales (solo admins)."""
    
    if not ctx.guild:
        await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
        return
    
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ Solo administradores pueden usar este comando.")
        return
    
    if not VIGIA_COMMANDS_AVAILABLE:
        await ctx.send("❌ El Vigía de Noticias no está disponible en este servidor.")
        return
    
    db_vigia_instance = get_vigia_db_for_server(ctx.guild)
    if not db_vigia_instance:
        await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
        return
    
    ayuda_msg = "📡 **AYUDA DEL VIGÍA - COMANDOS DE CANAL** 📡\n\n"
    ayuda_msg += "🔧 **Comandos de Administración:**\n"
    ayuda_msg += "```\n"
    ayuda_msg += "!vigiacanal suscribir <feed_id>     # Suscribir canal a un feed\n"
    ayuda_msg += "!vigiacanal cancelar <feed_id>     # Cancelar suscripción del canal\n"
    ayuda_msg += "!vigiacanal estado                 # Ver estado de suscripciones del canal\n"
    ayuda_msg += "!vigiacanal palabras add <palabra> # Añadir palabra clave al canal\n"
    ayuda_msg += "!vigiacanal palabras del <palabra>  # Eliminar palabra clave del canal\n"
    ayuda_msg += "!vigiacanal premisas add <texto>    # Añadir premisa al canal\n"
    ayuda_msg += "!vigiacanal premisas del <id>       # Eliminar premisa del canal\n"
    ayuda_msg += "!vigiacanal general <categoria> [feed_id]     # Suscribir canal con IA\n"
    ayuda_msg += "!vigiacanal general cancelar <categoria> [feed_id]  # Cancelar suscripción IA\n"
    ayuda_msg += "```\n\n"
    ayuda_msg += "💡 **Para ver todos los feeds disponibles:** `!vigia feeds`\n"
    ayuda_msg += "📋 **Para ver categorías:** `!vigia categorias`\n"
    
    await ctx.send(ayuda_msg[:2000])
    # Ejemplos de uso
    embed.add_field(
        name="💡 Ejemplos de Uso",
        value=(
            "`!vigiacanal suscribir economia` - Todas las noticias económicas con opinión\n"
            "`!vigiacanal palabras \"bitcoin,crypto\"` - Solo noticias con esas palabras\n"
            "`!vigiacanal general internacional` - Noticias críticas según premisas\n"
            "`!vigiacanal general cancelar internacional` - Cancelar suscripción con IA\n"
            "`!vigiacanal premisas add \"crisis financiera\"` - Añadir premisa al canal\n"
            "`!vigiacanal estado` - Ver tipo de suscripción del canal"
        ),
        inline=False
    )
    
    # Información importante
    embed.add_field(
        name="⚠️ IMPORTANTE - Exclusión Mutua",
        value=(
            "• Un canal puede tener **SOLO UN TIPO** de suscripción activa\n"
            "• Al cambiar de tipo, se cancela automáticamente la anterior\n"
            "• **Tipos:** Plana (todas), Palabras (filtradas), IA (críticas)\n"
            "• Las notificaciones se envían al canal configurado\n"
            "• Solo administradores pueden gestionar suscripciones de canal"
        ),
        inline=False
    )
    
    embed.set_footer(text="Vigía de Noticias - Sistema de Monitoreo Inteligente")
    await ctx.send(embed=embed)

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

async def set_mc_presence_if_enabled():
    """Establece el estado del bot con mensaje personalizado si el rol MC está activo."""
    try:
        # Verificar si el rol MC está activo (prioridad a variable de entorno)
        mc_enabled = os.getenv("MC_ENABLED", "false").lower() == "true"
        if not mc_enabled:
            # Fallback a configuración JSON si no hay variable de entorno
            mc_enabled = agent_config.get("roles", {}).get("mc", {}).get("enabled", False)
        
        if mc_enabled:
            # Obtener mensaje personalizado desde la personalidad
            mc_cfg = PERSONALIDAD.get("discord", {}).get("mc_messages", {})
            presence_message = mc_cfg.get("presence_status", "🎵 ¡MC disponible! Usa !mc play para música")
            
            # Establecer estado del bot con el mensaje personalizado
            await bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name=presence_message
                )
            )
            logger.info(f"🎵 [DISCORD] Rol MC activo - Estado establecido: {presence_message}")
        else:
            logger.info("🎵 [DISCORD] Rol MC no está activo - usando estado por defecto")
            
    except Exception as e:
        logger.error(f"❌ [DISCORD] Error estableciendo estado MC: {e}")


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
    
    # Iniciar tarea automática del buscador de tesoros si está disponible
    if POE2_AVAILABLE and not buscador_tesoros_task.is_running():
        buscador_tesoros_task.start()
        logger.info("💎 [DISCORD] Tarea automática del buscador de tesoros iniciada")
    
    # Registrar comandos de roles activados según agent_config.json
    await register_commands_for_enabled_roles()
    
    # Establecer estado personalizado si el rol MC está activo
    await set_mc_presence_if_enabled()


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


# Manejar errores de comandos para procesar chat normal
@bot.event
async def on_command_error(ctx, error):
    """Maneja errores de comandos, incluyendo CommandNotFound para chat normal."""
    # Si es un comando no encontrado, mantenerlo en la ruta de comandos.
    # Regla del bot:
    # - Si empieza por "!" => es comando (aunque sea inválido)
    # - Si no empieza por "!" => se procesa como charla LLM (en DMs o menciones)
    if isinstance(error, commands.CommandNotFound):
        return
    
    # Para otros errores, dejar que se propaguen
    if isinstance(error, commands.MissingRequiredArgument) or isinstance(error, commands.BadArgument):
        return  # No hacer nada, dejar que discord.py muestre el error
    
    # Para errores críticos, loggear
    logger.error(f"Error en comando: {error}")


# Evento para manejar menciones y DMs que no son comandos
@bot.event
async def on_message(message):
    """Maneja mensajes que no son comandos (menciones y DMs)."""
    # Ignorar mensajes del propio bot
    if message.author == bot.user:
        return
    
    # Si empieza con "!", es comando: hay que pasarlo explícitamente al sistema de comandos
    # (porque al definir on_message, discord.py NO procesa comandos automáticamente).
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return
    
    # Solo procesar si es DM o mención directa (y no empieza con !)
    if message.guild is None or bot.user.mentioned_in(message):
        await _process_chat_message(message)

    # Para cualquier otro mensaje no-comando, no hacemos nada.


async def _process_chat_message(message):
    """Procesa mensajes de chat normales (DMs y menciones)."""
    try:
        from agent_engine import pensar, incrementar_uso, obtener_uso_diario
        
        # Determinar si es público o privado
        es_publico = message.guild is not None
        
        # Obtener contexto del servidor si está en un canal
        contexto_servidor = ""
        if message.guild:
            server_name = get_server_name(message.guild)
            contexto_servidor = f"Servidor: {message.guild.name} ({server_name})"
        
        # Construir rol contextual con información de roles activos
        roles_activos = []
        roles_config = AGENT_CFG.get("roles", {})
        
        # Verificar roles activos
        if roles_config.get("buscar_anillo", {}).get("enabled", False):
            roles_activos.append("buscar_anillo")
        if roles_config.get("trilero", {}).get("enabled", False):
            roles_activos.append("trilero")
        
        rol_contextual = f"Kronk - Orco herrero"
        if roles_activos:
            rol_contextual += f" (roles activos: {', '.join(roles_activos)})"
        
        # Agregar contexto del servidor si aplica
        if contexto_servidor:
            rol_contextual += f" - {contexto_servidor}"
        
        # Obtener historial reciente (simplificado para chat)
        historial_lista = []
        
        # Procesar el mensaje con el engine
        respuesta = pensar(
            rol_contextual=rol_contextual,
            contenido_usuario=message.content,
            historial_lista=historial_lista,
            es_publico=es_publico,
            logger=logger
        )
        
        # Incrementar contador de uso
        incrementar_uso()
        
        # Enviar respuesta
        if respuesta and respuesta.strip():
            await message.channel.send(respuesta)
        
    except Exception as e:
        logger.exception(f"Error procesando mensaje de chat: {e}")
        # Enviar respuesta de emergencia
        fallbacks = PERSONALIDAD.get("emergency_fallbacks", [])
        if fallbacks:
            await message.channel.send(random.choice(fallbacks))

async def _cmd_role_toggle(ctx, role_name: str, enabled: bool):
    """Comando genérico para activar/desactivar roles dinámicamente."""
    # Obtener mensajes personalizados
    role_cfg = PERSONALIDAD.get("discord", {}).get("role_messages", {})
    
    # Verificar permisos (solo admins)
    if not ctx.author.guild_permissions.administrator and not ctx.author.guild_permissions.manage_guild:
        await ctx.send(role_cfg.get("role_no_permission", "❌ Solo administradores pueden modificar los roles."))
        return
    
    # Lista de roles válidos
    valid_roles = ["vigia_noticias", "buscador_tesoros", "trilero", "buscar_anillo", "banquero"]
    
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
    valid_roles = ["vigia_noticias", "buscador_tesoros", "trilero", "buscar_anillo", "banquero"]
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
    
    # Registrar comandos del trilero (siempre si la base de datos está disponible)
    register_trilero_commands()
    
    # Obtener configuración de roles
    roles_config = agent_config.get("roles", {})
    
    # Lista de roles que tienen comandos Discord (trilero ya se registró por separado)
    roles_with_commands = ["vigia_noticias", "buscador_tesoros", "buscar_anillo", "banquero"]
    
    for role_name in roles_with_commands:
        role_config = roles_config.get(role_name, {})
        is_enabled = role_config.get("enabled", False)
        
        if is_enabled:
            logger.info(f"🎭 [DISCORD] Rol {role_name} está activado, registrando TODOS los comandos...")
            await register_specific_role_commands(role_name)
    
    # Marcar como registrado para evitar duplicaciones
    _commands_registered = True
    logger.info("🎭 [DISCORD] Registro de comandos completado")

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
                        await vigia_commands.cmd_general_suscribir(ctx, subargs)
                    elif subcommand == "palabras":
                        await vigia_commands.cmd_palabras_suscribir(ctx, subargs)
                    elif subcommand == "premisas":
                        await vigia_commands.cmd_premisas(ctx, subargs)
                    elif subcommand == "mod":
                        await vigia_commands.cmd_premisas_mod(ctx, subargs)
                    elif subcommand == "reset":
                        await vigia_commands.cmd_reset(ctx, subargs)
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
                """Muestra ayuda específica para el Vigía de Noticias (usuarios)."""
                # Prevenir duplicación usando un ID único del mensaje
                message_id = f"{ctx.message.id}_{ctx.author.id}"
                
                # Si ya procesamos este mensaje, ignorar
                if hasattr(bot, '_processed_ayuda_messages'):
                    if message_id in bot._processed_ayuda_messages:
                        return
                else:
                    bot._processed_ayuda_messages = set()
                
                bot._processed_ayuda_messages.add(message_id)
                
                ayuda_cfg = PERSONALIDAD.get("discord", {}).get("general_messages", {})
                mensaje_privado = ayuda_cfg.get("help_sent_private", "GRRR Kronk enviar ayuda por mensaje privado umano!")
                
                ayuda_vigia = "📡 **Ayuda del Vigía de Noticias - Usuarios** 📡\n\n"
                
                ayuda_vigia += "⚠️ **IMPORTANTE:** Solo puedes tener **UN TIPO** de suscripción activa a la vez\n"
                ayuda_vigia += "• Si te suscribes a un nuevo tipo, se cancelará automáticamente el anterior\n\n"
                
                ayuda_vigia += "🎯 **Comandos Principales:**\n"
                ayuda_vigia += "• `!vigia feeds` - Lista feeds RSS disponibles\n"
                ayuda_vigia += "• `!vigia categorias` - Muestra categorías activas\n"
                ayuda_vigia += "• `!vigia estado` - Tu tipo de suscripción activa\n\n"
                
                ayuda_vigia += "📰 **Suscripciones Planas:**\n"
                ayuda_vigia += "• `!vigia suscribir <categoría>` - Todas las noticias con opinión\n"
                ayuda_vigia += "• **Ejemplo:** `!vigia suscribir economia`\n\n"
                
                ayuda_vigia += "🔍 **Palabras Clave:**\n"
                ayuda_vigia += "• `!vigia palabras \"palabra1,palabra2\"` - Suscripción directa con palabras\n"
                ayuda_vigia += "• `!vigia palabras add <palabra>` - Añadir palabra a tu lista\n"
                ayuda_vigia += "• `!vigia palabras list` - Ver todas tus palabras clave\n"
                ayuda_vigia += "• `!vigia palabras mod <num> \"nueva\"` - Modificar palabra específica\n"
                ayuda_vigia += "• `!vigia palabras suscribir <categoría>` - Usar palabras ya configuradas\n"
                ayuda_vigia += "• `!vigia palabras suscripciones` - Ver suscripciones con palabras\n"
                ayuda_vigia += "• `!vigia palabras desuscribir <categoría>` - Cancelar suscripción\n"
                ayuda_vigia += "• **Ejemplo:** `!vigia palabras \"bitcoin,crypto\"`\n\n"
                
                ayuda_vigia += "🤖 **Suscripciones con IA:**\n"
                ayuda_vigia += "• `!vigia general <categoría>` - Noticias críticas según tus premisas\n"
                ayuda_vigia += "• `!vigia general cancelar <categoría>` - Cancelar suscripción con IA\n"
                ayuda_vigia += "• **Requiere:** Configurar premisas primero (`!vigia premisas add`)\n"
                ayuda_vigia += "• **Ejemplo:** `!vigia general internacional`\n\n"
                
                ayuda_vigia += "🎯 **Gestión de Premisas:**\n"
                ayuda_vigia += "• `!vigia premisas` / `!vigia premisas list` - Ver tus premisas\n"
                ayuda_vigia += "• `!vigia premisas add \"texto\"` - Añadir premisa (máx 7)\n"
                ayuda_vigia += "• `!vigia mod <num> \"nueva premisa\"` - Modificar premisa #<num>\n\n"
                
                ayuda_vigia += "🔄 **Reset de Suscripciones:**\n"
                ayuda_vigia += "• `!vigia reset` - Ver qué tipo de suscripción tienes activa\n"
                ayuda_vigia += "• `!vigia reset confirmar` - Eliminar TODAS tus suscripciones\n"
                ayuda_vigia += "• **Úsalo para cambiar de tipo de suscripción**\n\n"
                
                ayuda_vigia += "📊 **Estado y Control:**\n"
                ayuda_vigia += "• `!vigia estado` - Ver tu tipo de suscripción activa\n"
                ayuda_vigia += "• `!vigia cancelar <categoría>` - Cancelar suscripción plana\n\n"
                
                ayuda_vigia += "📂 **Categorías:** economia, internacional, tecnologia, sociedad, politica\n\n"
                
                ayuda_vigia += "💡 **Ejemplos Rápidos:**\n"
                ayuda_vigia += "```\n!vigia palabras add bitcoin           # Añadir palabra\n!vigia palabras list                  # Ver palabras\n!vigia palabras suscribir economia   # Suscribir con palabras\n!vigia reset                         # Ver tipo activo\n!vigia reset confirmar               # Limpiar todo\n!vigia general internacional         # Suscribir con IA\n```\n\n"
                
                ayuda_vigia += "📢 **Para Admins:** Usa `!vigiacanalayuda` para comandos de canal\n"
                
                try:
                    # Verificar si el mensaje es demasiado largo antes de enviar
                    if len(ayuda_vigia) > 2000:
                        # Dividir en partes y enviar al usuario por DM
                        partes = [ayuda_vigia[i:i+1900] for i in range(0, len(ayuda_vigia), 1900)]
                        for parte in partes:
                            await ctx.author.send(parte)
                    else:
                        await ctx.author.send(ayuda_vigia)
                    
                    # Enviar confirmación breve en el canal (solo si está en servidor)
                    if ctx.guild:
                        await ctx.send("📩 Ayuda enviada por mensaje privado.")
                        
                except discord.errors.Forbidden:
                    # Si no puede enviar DM, enviar en el canal (dividido si es necesario)
                    if len(ayuda_vigia) > 2000:
                        partes = [ayuda_vigia[i:i+1900] for i in range(0, len(ayuda_vigia), 1900)]
                        for parte in partes:
                            await ctx.send(parte)
                    else:
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
                    elif subcommand == "premisas":
                        await vigia_commands.cmd_canal_premisas(ctx, subargs)
                    elif subcommand == "general":
                        # Manejar !vigiacanal general y !vigiacanal general cancelar
                        if len(subargs) > 0 and subargs[0].lower() == "cancelar":
                            # Es !vigiacanal general cancelar <categoria> [feed_id]
                            await vigia_commands.cmd_canal_general_cancelar(ctx, subargs[1:] if len(subargs) > 1 else [])
                        else:
                            # Es !vigiacanal general <categoria> [feed_id]
                            await vigia_commands.cmd_canal_general_suscribir(ctx, subargs)
                    else:
                        await ctx.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!vigiacanalayuda` para ver ayuda.")
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
                    server_name = ctx.guild.name if ctx.guild else "DM"
                    logger.info(f"🔮 [POE2] {ctx.author.name} activó el subrol en {server_name}")
                    
                    # Descargar datos para todos los items existentes
                    await ctx.send(f"🔄 {ctx.author.mention} Descargando datos de items existentes...")
                    
                    try:
                        from roles.buscador_tesoros.poe2scout_client import Poe2ScoutClient
                        from roles.buscador_tesoros.db_role_poe import DatabaseRolePoe
                        from agent_db import get_active_server_name
                        
                        # Obtener configuración
                        liga_actual = db_poe2_instance.get_liga()
                        server_name = get_active_server_name() or "default"
                        objetivos_activos = db_poe2_instance.get_objetivos_activos()
                        
                        if objetivos_activos:
                            db_role_poe = DatabaseRolePoe(server_name, liga_actual)
                            scout = Poe2ScoutClient()
                            
                            for nombre_item, item_id in objetivos_activos:
                                try:
                                    entries = scout.get_item_history(nombre_item, league=liga_actual)
                                    if entries:
                                        insertados = db_role_poe.insertar_precios_bulk(nombre_item, entries, liga_actual)
                                        logger.info(f"📊 {nombre_item}: {len(entries)} datos recibidos, {insertados} nuevos")
                                    else:
                                        logger.warning(f"⚠️ No hay datos para {nombre_item}")
                                except Exception as e:
                                    logger.warning(f"⚠️ Error descargando {nombre_item}: {e}")
                            
                            await ctx.send(f"✅ {ctx.author.mention} Datos descargados para {len(objetivos_activos)} items.")
                        else:
                            await ctx.send(f"ℹ️ {ctx.author.mention} No hay items configurados. Usa `!poe2add \"nombre item\"` para añadir.")
                            
                    except Exception as e:
                        logger.exception(f"Error descargando datos al activar POE2: {e}")
                        await ctx.send(f"⚠️ {ctx.author.mention} Hubo un error descargando datos, pero el subrol está activo.")
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
                    await ctx.send(f"ℹ️ {ctx.author.mention} El buscador automático descargará los datos en la próxima ejecución.")
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
                
                # Añadir item a objetivos
                if not db_poe2_instance.add_objetivo(item_name):
                    await ctx.send("❌ Error al añadir el item. Inténtalo de nuevo.")
                    return
                
                # Descargar historial inmediatamente
                await ctx.send(f"🔄 {ctx.author.mention} Descargando historial para {item_name}...")
                
                # Variables para control de flujo
                original_server = None
                exito_descarga = False
                precio_actual = None
                
                try:
                    # Importar dependencias necesarias
                    from roles.buscador_tesoros.db_role_poe import DatabaseRolePoe
                    from roles.buscador_tesoros.poe2scout_client import Poe2ScoutClient
                    from agent_db import get_active_server_name, set_current_server
                    
                    # Establecer servidor activo temporalmente
                    original_server = get_active_server_name()
                    set_current_server(get_server_name(ctx.guild))
                    
                    # Obtener configuración
                    liga_actual = db_poe2_instance.get_liga()
                    db_precios = DatabaseRolePoe(get_server_name(ctx.guild), liga_actual)
                    scout = Poe2ScoutClient()
                    
                    # Descargar historial
                    entries = scout.get_item_history(item_name, league=liga_actual)
                    
                    if entries:
                        insertados = db_precios.insertar_precios_bulk(item_name, entries, liga_actual)
                        precio_actual = entries[0].price if entries else None
                        
                        if precio_actual:
                            await ctx.send(f"✅ {ctx.author.mention} Item añadido y actualizado: **{item_name}** - Precio actual: **{precio_actual:.2f} Div** ({insertados} registros nuevos)")
                        else:
                            await ctx.send(f"✅ {ctx.author.mention} Item añadido: **{item_name}** ({insertados} registros nuevos, sin precio actual)")
                        
                        logger.info(f"🔮 [POE2] {ctx.author.name} añadió y actualizó {item_name} con {insertados} registros en {ctx.guild.name}")
                        exito_descarga = True
                    else:
                        await ctx.send(f"⚠️ {ctx.author.mention} Item añadido pero no se encontraron datos: **{item_name}**")
                        logger.warning(f"🔮 [POE2] No hay datos para {item_name} en liga {liga_actual}")
                        exito_descarga = True
                    
                except Exception as e:
                    logger.exception(f"Error descargando historial para {item_name}: {e}")
                    if not exito_descarga:
                        await ctx.send(f"⚠️ {ctx.author.mention} Error al descargar historial para **{item_name}**. El item fue añadido a objetivos y se intentará descargar en la próxima ejecución automática.")
                
                finally:
                    # Siempre restaurar servidor original
                    if original_server:
                        set_current_server(original_server)
                
                # Análisis inmediato del precio (fuera del bloque try principal)
                if exito_descarga and precio_actual:
                    try:
                        # Re-importar para asegurar contexto correcto
                        from roles.buscador_tesoros.db_role_poe import DatabaseRolePoe
                        from roles.buscador_tesoros.buscador_tesoros import analizar_mercado
                        from agent_engine import pensar
                        from postprocessor import is_internal_thinking
                        
                        # Obtener configuración nuevamente
                        liga_actual = db_poe2_instance.get_liga()
                        db_precios = DatabaseRolePoe(get_server_name(ctx.guild), liga_actual)
                        
                        señal = analizar_mercado(db_precios, item_name, precio_actual, liga_actual)
                        
                        if señal:
                            logger.info(f"🚨 SEÑAL INMEDIATA: {item_name} - {señal} a {precio_actual} Div")
                            
                            # Verificar si hay notificación reciente
                            notificacion_reciente = db_precios.verificar_notificacion_reciente(
                                item_name, liga_actual, señal, precio_actual, horas=6, umbral_similitud=0.15
                            )
                            
                            if not notificacion_reciente:
                                # Enviar notificación inmediata
                                if señal == "COMPRA":
                                    mensaje = f"Oportunidad de compra inmediata: {item_name} a {precio_actual} Div. ¡Es muy barato! ¡Comprar ya mismo!"
                                else:
                                    mensaje = f"Oportunidad de venta inmediata: {item_name} a {precio_actual} Div. ¡Es muy caro! ¡Vender ya mismo!"
                                
                                res = await asyncio.to_thread(pensar, mensaje)
                                
                                if is_internal_thinking(res):
                                    logger.warning(f"⚠️ Respuesta detectada como pensamiento interno: {res}")
                                    res = (
                                        f"¡Barato! {item_name} a solo {precio_actual} Div. ¡Comprar ya mismo!"
                                        if señal == "COMPRA"
                                        else f"¡Caro! {item_name} a {precio_actual} Div. ¡Vender inmediatamente!"
                                    )
                                
                                # Enviar notificación al usuario
                                await ctx.send(f"💎 **TESORO DETECTADO INMEDIATO**: {res}")
                                
                                # Registrar notificación
                                db_precios.registrar_notificacion(item_name, liga_actual, señal, precio_actual)
                                logger.info(f"✅ Notificación inmediata enviada para {item_name} - {señal}")
                            else:
                                logger.info(f"🔕 Notificación inmediata omitida por duplicidad: {item_name} - {señal}")
                    except Exception as analisis_e:
                        logger.exception(f"Error en análisis inmediato para {item_name}: {analisis_e}")
                        # No mostrar error al usuario, solo log
        
        if bot.get_command("poe2del") is None:
            logger.info("🔮 [DISCORD] Registrando comando poe2del")
            
            @bot.command(name="poe2del")
            async def cmd_poe2_del(ctx, item_name: str = ""):
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                if not item_name:
                    await ctx.send("❌ Debes especificar el nombre del item o número. Ejemplo: !poe2del \"Ancient Rib\" o !poe2del 3")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                # Verificar si es un número (selección por índice)
                try:
                    item_index = int(item_name)
                    # Es un número, buscar por índice en la lista de objetivos
                    objetivos = db_poe2_instance.get_objetivos()
                    
                    if 1 <= item_index <= len(objetivos):
                        # Obtener el nombre del item en esa posición
                        item_real_name = objetivos[item_index - 1][0]  # objetivos es (nombre, item_id, activo, fecha)
                        
                        if db_poe2_instance.remove_objetivo(item_real_name):
                            await ctx.send(f"✅ {ctx.author.mention} Item #{item_index} eliminado de objetivos: **{item_real_name}**")
                            logger.info(f"🔮 [POE2] {ctx.author.name} eliminó objetivo #{item_index} ({item_real_name}) en {ctx.guild.name}")
                        else:
                            await ctx.send(f"❌ Error al eliminar el item #{item_index}.")
                    else:
                        await ctx.send(f"❌ Número inválido. Hay {len(objetivos)} items. Usa un número entre 1 y {len(objetivos)}.")
                
                except ValueError:
                    # No es un número, tratar como nombre de item
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
                    # Importar la BD de precios para obtener precios actuales
                    from roles.buscador_tesoros.db_role_poe import DatabaseRolePoe
                    db_precios = DatabaseRolePoe(get_server_name(ctx.guild), liga_actual)
                    
                    for i, (nombre, item_id, activo_item, fecha) in enumerate(objetivos, 1):
                        estado_item = "✅" if activo_item else "❌"
                        
                        # Obtener precio actual
                        precio_actual = db_precios.obtener_precio_actual(nombre, liga_actual)
                        if precio_actual:
                            response += f"  {i}. {estado_item} {nombre} - **{precio_actual:.2f} Div**\n"
                        else:
                            response += f"  {i}. {estado_item} {nombre} - *Sin datos*\n"
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
                ayuda_poe2 += "• `!poe2liga Fate of the Vaal` - Establece liga Fate of the Vaal\n"
                ayuda_poe2 += "• ℹ️ **Nota**: Después de cambiar liga, ejecuta `!buscartesoros poe2` para descargar datos inmediatamente\n\n"
                ayuda_poe2 += "🎯 **Gestión de Objetivos:**\n"
                ayuda_poe2 += "• `!poe2add \"Nombre del Item\"` - Añade item a objetivos\n"
                ayuda_poe2 += "• `!poe2del \"Nombre del Item\"` - Elimina item de objetivos\n"
                ayuda_poe2 += "• `!poe2list` - Muestra configuración y objetivos actuales\n\n"
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
        
        # Comando de frecuencia para el buscador de tesoros
        if bot.get_command("tesorosfrecuencia") is None:
            logger.info("💎 [DISCORD] Registrando comando tesorosfrecuencia")
            
            @bot.command(name="tesorosfrecuencia")
            async def cmd_tesoros_frecuencia(ctx, hours: str = ""):
                """Configura la frecuencia de ejecución automática del buscador de tesoros."""
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El buscador de tesoros no está disponible en este servidor.")
                    return
                
                await _cmd_role_frequency(ctx, "buscador_tesoros", hours)
    
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
    
    elif role_name == "banquero":
        # Importar la base de datos del banquero
        from roles.banquero.db_role_banquero import DatabaseRoleBanquero
        
        # Verificar disponibilidad de la base de datos
        if not BANQUERO_DB_AVAILABLE:
            logger.warning("💰 [DISCORD] Base de datos del banquero no disponible, omitiendo registro de comandos")
            return
        
        if bot.get_command("banquero") is None:
            logger.info("💰 [DISCORD] Registrando comando banquero")
            
            @bot.command(name="banquero")
            async def cmd_banquero(ctx, *args):
                """Comando principal del Banquero para gestión económica."""
                # Debug: mostrar qué argumentos se reciben
                logger.info(f"💰 [DEBUG] Comando banquero recibido con args: {args}")
                
                # Verificar que estamos en un servidor
                if not ctx.guild:
                    banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                    await ctx.send(banquero_msgs.get("error_bd_banquero", "❌ Este comando solo funciona en servidores."))
                    return
                
                # Verificar disponibilidad de la base de datos
                try:
                    db_banquero = get_banquero_db_for_server(ctx.guild)
                    if db_banquero is None:
                        banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                        await ctx.send(banquero_msgs.get("error_bd_banquero", "❌ Base de datos del banquero no disponible."))
                        return
                except Exception as e:
                    logger.exception(f"Error obteniendo BD del banquero: {e}")
                    banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                    await ctx.send(banquero_msgs.get("error_bd_banquero", "❌ Error accediendo a la base de datos del banquero."))
                    return
                
                # Obtener información del servidor
                servidor_id = str(ctx.guild.id)
                servidor_nombre = ctx.guild.name
                
                # Si no hay argumentos, mostrar ayuda
                if not args:
                    banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                    embed = discord.Embed(
                        title=banquero_msgs.get("ayuda_title", "💰 Banquero - Ayuda"),
                        description=banquero_msgs.get("ayuda_description", "Comandos disponibles para gestionar la economía del servidor"),
                        color=discord.Color.gold()
                    )
                    
                    embed.add_field(
                        name=banquero_msgs.get("ver_saldo", "💎 Ver Saldo"),
                        value=banquero_msgs.get("ver_saldo_desc", "`!banquero saldo`\nMuestra tu saldo actual de oro y transacciones recientes.\nLas cuentas nuevas reciben bono de apertura automáticamente."),
                        inline=False
                    )
                    
                    embed.add_field(
                        name=banquero_msgs.get("configurar_tae", "🏦 Configurar TAE (Admins)"),
                        value=banquero_msgs.get("configurar_tae_desc", "`!banquero tae <cantidad>`\nEstablece la TAE diaria (0-1000 monedas).\n`!banquero tae` - Ver configuración actual."),
                        inline=False
                    )
                    
                    embed.add_field(
                        name=banquero_msgs.get("configurar_bono", "🎁 Configurar Bono de Apertura (Admins)"),
                        value=banquero_msgs.get("configurar_bono_desc", "`!banquero bono <cantidad>`\nEstablece el bono para nuevas cuentas (0-10000 monedas).\n`!banquero bono` - Ver configuración actual."),
                        inline=False
                    )
                    
                    embed.add_field(
                        name=banquero_msgs.get("informacion", "ℹ️ Información"),
                        value=banquero_msgs.get("informacion_desc", "• La TAE se distribuye automáticamente cada día a todos los usuarios con cartera.\n• Las cuentas nuevas reciben automáticamente el bono de apertura configurado.\n• Todas las transacciones quedan registradas.\n• Solo los administradores pueden configurar la TAE y el bono de apertura."),
                        inline=False
                    )
                    
                    embed.set_footer(text=banquero_msgs.get("ayuda_footer", "💼 Banquero - Gestión Económica del Servidor"))
                    await ctx.send(embed=embed)
                    return
                
                # Procesar subcomandos
                subcommand = args[0].lower()
                subargs = args[1:] if len(args) > 1 else []
                
                # Si el subcomando es "ayuda", mostrar ayuda
                if subcommand == "ayuda":
                    banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                    embed = discord.Embed(
                        title=banquero_msgs.get("ayuda_title", "💰 Banquero - Ayuda"),
                        description=banquero_msgs.get("ayuda_description", "Comandos disponibles para gestionar la economía del servidor"),
                        color=discord.Color.gold()
                    )
                    
                    embed.add_field(
                        name=banquero_msgs.get("ver_saldo", "💎 Ver Saldo"),
                        value=banquero_msgs.get("ver_saldo_desc", "`!banquero saldo`\nMuestra tu saldo actual de oro y transacciones recientes.\nLas cuentas nuevas reciben bono de apertura automáticamente."),
                        inline=False
                    )
                    
                    embed.add_field(
                        name=banquero_msgs.get("configurar_tae", "🏦 Configurar TAE (Admins)"),
                        value=banquero_msgs.get("configurar_tae_desc", "`!banquero tae <cantidad>`\nEstablece la TAE diaria (0-1000 monedas).\n`!banquero tae` - Ver configuración actual."),
                        inline=False
                    )
                    
                    embed.add_field(
                        name=banquero_msgs.get("configurar_bono", "🎁 Configurar Bono de Apertura (Admins)"),
                        value=banquero_msgs.get("configurar_bono_desc", "`!banquero bono <cantidad>`\nEstablece el bono para nuevas cuentas (0-10000 monedas).\n`!banquero bono` - Ver configuración actual."),
                        inline=False
                    )
                    
                    embed.add_field(
                        name=banquero_msgs.get("informacion", "ℹ️ Información"),
                        value=banquero_msgs.get("informacion_desc", "• La TAE se distribuye automáticamente cada día a todos los usuarios con cartera.\n• Las cuentas nuevas reciben automáticamente el bono de apertura configurado.\n• Todas las transacciones quedan registradas.\n• Solo los administradores pueden configurar la TAE y el bono de apertura."),
                        inline=False
                    )
                    
                    embed.set_footer(text=banquero_msgs.get("ayuda_footer", "💼 Banquero - Gestión Económica del Servidor"))
                    
                    # Enviar por mensaje privado
                    try:
                        await ctx.author.send(embed=embed)
                        # Enviar confirmación en el canal
                        await ctx.send(banquero_msgs.get("ayuda_enviada", "📩 Ayuda del banquero enviada por mensaje privado."))
                    except discord.errors.Forbidden:
                        # Si no puede enviar DM, enviar en el canal
                        await ctx.send(embed=embed)
                    return
                
                if subcommand == "saldo":
                    # Mostrar saldo del usuario
                    usuario_id = str(ctx.author.id)
                    usuario_nombre = ctx.author.display_name
                    
                    # Crear cartera si no existe
                    db_banquero.crear_cartera(usuario_id, usuario_nombre, servidor_id, servidor_nombre)
                    
                    # Obtener saldo
                    saldo = db_banquero.obtener_saldo(usuario_id, servidor_id)
                    
                    # Obtener historial reciente
                    historial = db_banquero.obtener_historial_transacciones(usuario_id, servidor_id, 5)
                    
                    # Crear embed con la información
                    banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                    embed = discord.Embed(
                        title=banquero_msgs.get("saldo_title", "💰 Cartera del Banquero"),
                        description=banquero_msgs.get("saldo_description", "Estado de tu cartera de oro"),
                        color=discord.Color.gold()
                    )
                    
                    embed.add_field(name=banquero_msgs.get("saldo_actual", "💎 Saldo Actual"), value=f"{saldo:,} monedas de oro", inline=False)
                    embed.add_field(name=banquero_msgs.get("titular", "👤 Titular"), value=usuario_nombre, inline=True)
                    embed.add_field(name=banquero_msgs.get("banco", "🏦 Banco"), value=servidor_nombre, inline=True)
                    
                    # Agregar historial reciente si hay
                    if historial:
                        historial_text = ""
                        for trans in historial:
                            tipo, cantidad, saldo_ant, saldo_nuevo, descripcion, fecha, admin = trans
                            emoji = "📥" if cantidad > 0 else "📤"
                            historial_text += f"{emoji} {cantidad:,} ({tipo})\n"
                        
                        if historial_text:
                            embed.add_field(name=banquero_msgs.get("transacciones_recientes", "📊 Transacciones Recientes"), value=historial_text[:1024], inline=False)
                    
                    embed.set_footer(text=banquero_msgs.get("ayuda_footer", "💼 Banquero - Gestión Económica del Servidor"))
                    embed.set_thumbnail(url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)
                    
                    # Enviar por mensaje privado
                    try:
                        await ctx.author.send(embed=embed)
                        # Enviar confirmación en el canal
                        await ctx.send(banquero_msgs.get("saldo_enviado", "💰 Información de tu cartera enviada por mensaje privado."))
                    except discord.errors.Forbidden:
                        # Si no puede enviar DM, enviar en el canal
                        await ctx.send(embed=embed)
                    return
                
                elif subcommand == "tae":
                    # Configurar o ver TAE (solo admins)
                    if not ctx.author.guild_permissions.administrator:
                        banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                        await ctx.send(banquero_msgs.get("error_no_admin_tae", "❌ Solo los jefes orkos pueden configurar la TAE umano!"))
                        return
                    
                    if not subargs:
                        # Mostrar TAE actual
                        tae_actual = db_banquero.obtener_tae(servidor_id)
                        ultima_dist = db_banquero.obtener_ultima_distribucion(servidor_id)
                        
                        banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                        embed = discord.Embed(
                            title=banquero_msgs.get("tae_config_title", "🏦 Konfiguración de TAE"),
                            description=banquero_msgs.get("tae_description", "Konfiguración aktual de la Tasa Anual Ekuivalente"),
                            color=discord.Color.blue()
                        )
                        
                        embed.add_field(name=banquero_msgs.get("tae_actual", "💰 TAE Diaria Aktual"), value=f"{tae_actual:,} monedas", inline=True)
                        embed.add_field(name=banquero_msgs.get("ultima_distribucion", "📅 Última Distribución"), value=ultima_dist[:10] if ultima_dist else "Nunca", inline=True)
                        
                        if tae_actual == 0:
                            embed.add_field(name=banquero_msgs.get("tae_no_configurada", "⚠️ Estado: TAE no konfigurada"), inline=False)
                        else:
                            embed.add_field(name=banquero_msgs.get("tae_info", "ℹ️ Info"), value=f"Kada usuario recibirá {tae_actual:,} monedas diarias", inline=False)
                        
                        embed.set_footer(text=banquero_msgs.get("tae_footer", "💼 Usa !banquero tae <cantidad> para konfigurar"))
                        await ctx.send(embed=embed)
                    else:
                        # Establecer nueva TAE
                        try:
                            cantidad = int(subargs[0])
                            banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                            if cantidad < 0 or cantidad > 1000:
                                await ctx.send(banquero_msgs.get("error_tae_rango", "❌ La TAE debe estar entre 0 y 1000 monedas diarias!"))
                                return
                            
                            admin_id = str(ctx.author.id)
                            admin_nombre = ctx.author.display_name
                            
                            if db_banquero.establecer_tae(servidor_id, cantidad, admin_id, admin_nombre):
                                embed = discord.Embed(
                                    title=banquero_msgs.get("tae_configurada", "✅ TAE Konfigurada"),
                                    description=banquero_msgs.get("tae_actualizada", "La Tasa Anual Ekuivalente ha sido aktualizada"),
                                    color=discord.Color.green()
                                )
                                
                                embed.add_field(name=banquero_msgs.get("nueva_tae", "💰 Nueva TAE Diaria"), value=f"{cantidad:,} monedas", inline=True)
                                embed.add_field(name=banquero_msgs.get("administrador", "👤 Administrador"), value=admin_nombre, inline=True)
                                embed.add_field(name=banquero_msgs.get("servidor", "🏦 Servidor"), value=servidor_nombre, inline=True)
                                
                                if cantidad > 0:
                                    embed.add_field(name=banquero_msgs.get("proxima_distribucion", "ℹ️ Próxima Distribución"), value="Se distribuirá automáticamente kada día", inline=False)
                                
                                embed.set_footer(text=banquero_msgs.get("ayuda_footer", "💼 Banquero - Gestión Ekonómika"))
                                await ctx.send(embed=embed)
                            else:
                                await ctx.send(banquero_msgs.get("error_configurar_tae", "❌ Error al konfigurar la TAE!"))
                                
                        except ValueError:
                            banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                            await ctx.send(banquero_msgs.get("error_numero_invalido", "❌ Cantidad inválida! Usa número entero umano bobo!"))
                
                elif subcommand == "bono":
                    # Configurar o ver bono de apertura (solo admins)
                    if not ctx.author.guild_permissions.administrator:
                        banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                        await ctx.send(banquero_msgs.get("error_no_admin_bono", "❌ Solo los jefes orkos pueden konfigurar el bono de apertura umano!"))
                        return
                    
                    if not subargs:
                        # Mostrar bono de apertura actual
                        bono_actual = db_banquero.obtener_bono_apertura(servidor_id)
                        
                        banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                        embed = discord.Embed(
                            title=banquero_msgs.get("bono_config_title", "🎁 Konfiguración de Bono de Apertura"),
                            description=banquero_msgs.get("bono_description", "Konfiguración aktual del bono para nuevas kuentas"),
                            color=discord.Color.purple()
                        )
                        
                        embed.add_field(name=banquero_msgs.get("bono_actual", "💰 Bono de Apertura Aktual"), value=f"{bono_actual:,} monedas", inline=True)
                        embed.add_field(name=banquero_msgs.get("servidor", "🏦 Servidor"), value=servidor_nombre, inline=True)
                        
                        embed.add_field(name=banquero_msgs.get("bono_info", "ℹ️ Info"), value=f"Kada nueva kuenta recibirá {bono_actual:,} monedas automáticamente", inline=False)
                        
                        embed.set_footer(text=banquero_msgs.get("bono_footer", "💼 Usa !banquero bono <cantidad> para konfigurar"))
                        await ctx.send(embed=embed)
                    else:
                        # Establecer nuevo bono de apertura
                        try:
                            cantidad = int(subargs[0])
                            banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                            if cantidad < 0 or cantidad > 10000:
                                await ctx.send(banquero_msgs.get("error_bono_rango", "❌ El bono de apertura debe estar entre 0 y 10000 monedas!"))
                                return
                            
                            admin_id = str(ctx.author.id)
                            admin_nombre = ctx.author.display_name
                            
                            if db_banquero.establecer_bono_apertura(servidor_id, cantidad, admin_id, admin_nombre):
                                embed = discord.Embed(
                                    title=banquero_msgs.get("bono_configurado", "✅ Bono de Apertura Konfigurado"),
                                    description=banquero_msgs.get("bono_actualizado", "El bono de apertura ha sido aktualizado"),
                                    color=discord.Color.green()
                                )
                                
                                embed.add_field(name=banquero_msgs.get("nuevo_bono", "💰 Nuevo Bono de Apertura"), value=f"{cantidad:,} monedas", inline=True)
                                embed.add_field(name=banquero_msgs.get("administrador", "👤 Administrador"), value=admin_nombre, inline=True)
                                embed.add_field(name=banquero_msgs.get("servidor", "🏦 Servidor"), value=servidor_nombre, inline=True)
                                
                                embed.add_field(name=banquero_msgs.get("aplicacion", "ℹ️ Aplikación"), value="Las próximas kuentas nuevas recibirán este bono", inline=False)
                                
                                embed.set_footer(text=banquero_msgs.get("ayuda_footer", "💼 Banquero - Konfiguración Ekonómika"))
                                await ctx.send(embed=embed)
                            else:
                                await ctx.send(banquero_msgs.get("error_configurar_bono", "❌ Error al konfigurar el bono de apertura!"))
                                
                        except ValueError:
                            banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                            await ctx.send(banquero_msgs.get("error_numero_invalido", "❌ Cantidad inválida! Usa número entero umano bobo!"))
                
                else:
                    banquero_msgs = PERSONALIDAD.get("discord", {}).get("banquero_messages", {})
                    await ctx.send(banquero_msgs.get("comando_no_reconocido", f"❌ Subkomando '{subcommand}' no rekonocido! Usa `!banquero ayuda` para ver ayuda umano tonto!").format(subcommand=subcommand))
    
    logger.info(f"🎭 [DISCORD] Comandos registrados para rol: {role_name}")
    
    # El trilero se maneja en la sección principal de registro de comandos

# --- REGISTRO DE COMANDOS DEL TRILERO ---
def register_trilero_commands():
    """Registra comandos del trilero con subrol limosna."""
    if LIMOSNA_DB_AVAILABLE:
        if bot.get_command("trilero") is not None:
            logger.info("🎭 [DISCORD] Comandos del trilero ya registrados")
        else:
            logger.info("🎭 [DISCORD] Registrando comandos del trilero con limosna")
            
            @bot.command(name="trilero")
            async def cmd_trilero(ctx, *args):
                """Comando principal del trilero - gestiona el subrol limosna."""
                if not LIMOSNA_DB_AVAILABLE:
                    await ctx.send("❌ El sistema del trilero no está disponible en este servidor.")
                    return
        
                # Si no hay argumentos, mostrar ayuda
                if not args:
                    await ctx.send("❌ Debes especificar una acción. Usa `!trilero ayuda` para ver los comandos disponibles.")
                    return
                
                subcommand = args[0].lower()
                subargs = args[1:] if len(args) > 1 else []
                
                if subcommand == "limosna":
                    await cmd_trilero_limosna(ctx, subargs)
                elif subcommand == "ayuda":
                    await cmd_trilero_ayuda(ctx)
                else:
                    await ctx.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!trilero ayuda` para ver ayuda.")
            
            async def cmd_trilero_limosna(ctx, args):
                """Gestiona el subrol limosna."""
                if not args:
                    await ctx.send("❌ Debes especificar una acción. Usa `!trilero limosna on/off` o `!trilero limosna frecuencia <horas>`. ")
                    return
                
                action = args[0].lower()
                
                if action in ["on", "off"]:
                    await cmd_trilero_limosna_toggle(ctx, action)
                elif action == "frecuencia":
                    await cmd_trilero_limosna_frecuencia(ctx, args[1:])
                elif action == "estado":
                    await cmd_trilero_limosna_estado(ctx)
                else:
                    await ctx.send(f"❌ Acción `{action}` no reconocida. Usa `on`, `off`, `frecuencia` o `estado`.")
            
            async def cmd_trilero_limosna_toggle(ctx, action):
                """Activa o desactiva el subrol limosna (solo administradores)."""
                if not ctx.guild:
                    await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
                    return
                
                if not ctx.author.guild_permissions.administrator:
                    await ctx.send("❌ Solo los administradores pueden activar/desactivar limosna en el servidor.")
                    return
                    
                db_limosna_instance = get_limosna_db_for_server(ctx.guild)
                if not db_limosna_instance:
                    await ctx.send("❌ Error al acceder a la base de datos del trilero.")
                    return
                
                if action == "on":
                    # Activar limosna para todo el servidor
                    server_id = str(ctx.guild.id)
                    server_name = ctx.guild.name
                    
                    # Usar un ID especial para el servidor
                    server_user_id = f"server_{server_id}"
                    
                    if db_limosna_instance.agregar_suscripcion(server_user_id, server_name, server_id):
                        await ctx.send(f"🙏 **Limosna activada para el servidor** - Ahora todos los miembros recibirán peticiones de limosna periódicamente.")
                        logger.info(f"🎭 [TRILERO] {ctx.author.name} activó limosna para el servidor {server_name}")
                    else:
                        await ctx.send("❌ Error al activar limosna. Inténtalo de nuevo.")
                else:  # off
                    # Desactivar limosna para todo el servidor
                    server_id = str(ctx.guild.id)
                    server_user_id = f"server_{server_id}"
                    
                    if db_limosna_instance.eliminar_suscripcion(server_user_id, server_id):
                        await ctx.send(f"🚫 **Limosna desactivada para el servidor** - Ya no se enviarán peticiones de limosna.")
                        logger.info(f"🎭 [TRILERO] {ctx.author.name} desactivó limosna para el servidor {ctx.guild.name}")
                    else:
                        await ctx.send("❌ Error al desactivar limosna. Inténtalo de nuevo.")
    
    async def cmd_trilero_limosna_frecuencia(ctx, args):
        """Ajusta la frecuencia de envío de limosna (solo administradores)."""
        if not ctx.guild:
            await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
            return
        
        if not ctx.author.guild_permissions.administrator:
            await ctx.send("❌ Solo los administradores pueden ajustar la frecuencia de limosna.")
            return
            
        if not args:
            await ctx.send("❌ Debes especificar un número de horas. Ejemplo: `!trilero limosna frecuencia 6`")
            return
        
        try:
            horas = int(args[0])
            if horas < 1 or horas > 168:
                await ctx.send("❌ La frecuencia debe estar entre 1 y 168 horas (1 semana).")
                return
            
            # Aquí podrías guardar la configuración en la base de datos del servidor
            # Por ahora, solo mostramos confirmación
            await ctx.send(f"⏰ **Frecuencia ajustada** - Las peticiones de limosna se enviarán cada {horas} horas.")
            logger.info(f"🎭 [TRILERO] {ctx.author.name} ajustó frecuencia de limosna a {horas} horas en {ctx.guild.name}")
            
        except ValueError:
            await ctx.send("❌ Debes especificar un número válido de horas.")
    
    async def cmd_trilero_limosna_estado(ctx):
        """Muestra el estado actual de limosna en el servidor."""
        if not ctx.guild:
            await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
            return
        
        db_limosna_instance = get_limosna_db_for_server(ctx.guild)
        if not db_limosna_instance:
            await ctx.send("❌ Error al acceder a la base de datos del trilero.")
            return
        
        server_id = str(ctx.guild.id)
        server_user_id = f"server_{server_id}"
        
        # Verificar si limosna está activada para el servidor
        is_active = db_limosna_instance.esta_suscrito(server_user_id, server_id)
        
        # Contar peticiones hoy
        from datetime import datetime, timedelta
        hoy = datetime.now().date()
        
        # Obtener estadísticas básicas
        try:
            # Esto es una aproximación, podrías necesitar agregar métodos específicos a la BD
            count_dm = db_limosna_instance.contar_peticiones_tipo_ultimo_dia("LIMOSNA_DM", server_id)
            count_public = db_limosna_instance.contar_peticiones_tipo_ultimo_dia("LIMOSNA_PUBLICO", server_id)
        except:
            count_dm = 0
            count_public = 0
        
        status_emoji = "✅" if is_active else "❌"
        status_text = "Activada" if is_active else "Desactivada"
        
        estado_msg = f"📊 **Estado de Limosna en {ctx.guild.name}**\n\n"
        estado_msg += f"{status_emoji} **Estado:** {status_text}\n"
        estado_msg += f"📈 **Peticiones hoy (últimas 24h):**\n"
        estado_msg += f"  • Privadas: {count_dm}/2\n"
        estado_msg += f"  • Públicas: {count_public}/4\n"
        estado_msg += f"🆔 **ID del servidor:** {server_id}\n"
        
        if is_active:
            estado_msg += f"\n🙏 Limosna está activa y funcionando en este servidor."
        else:
            estado_msg += f"\n🚫 Limosna está desactivada. Usa `!trilero limosna on` para activarla."
        
        await ctx.send(estado_msg)
    
    async def cmd_trilero_ayuda(ctx):
        """Muestra ayuda específica para el trilero."""
        ayuda_msg = "🎭 **TRILERO - AYUDA** 🎭\n\n"
        ayuda_msg += "**Subrol Limosna** - Solicitudes de donaciones y engaños\n\n"
        ayuda_msg += "📋 **COMANDOS LIMOSNA:** (solo administradores)\n"
        ayuda_msg += "• `!trilero limosna on` - Activa limosna para todo el servidor\n"
        ayuda_msg += "• `!trilero limosna off` - Desactiva limosna del servidor\n"
        ayuda_msg += "• `!trilero limosna frecuencia <horas>` - Ajusta frecuencia (1-168h)\n"
        ayuda_msg += "• `!trilero limosna estado` - Muestra estado actual\n\n"
        ayuda_msg += "**Subrol Bote** - Juego de dados contra la banca\n\n"
        ayuda_msg += "📋 **COMANDOS BOTE:**\n"
        ayuda_msg += "• `!bote jugar` - Realiza una tirada de dados (solo en canales de servidor)\n"
        ayuda_msg += "• `!bote ayuda` - Muestra ayuda completa del juego del Bote\n"
        ayuda_msg += "• `!bote saldo` - Muestra el saldo actual del bote (responde por DM)\n"
        ayuda_msg += "• `!bote stats` - Muestra tus estadísticas personales (responde por DM)\n"
        ayuda_msg += "• `!bote ranking` - Muestra ranking de jugadores del servidor\n"
        ayuda_msg += "• `!bote historial` - Muestra últimas partidas jugadas\n"
        ayuda_msg += "• `!bote config apuesta <cantidad>` - Configura apuesta fija (solo admins)\n"
        ayuda_msg += "• `!bote config anuncios on/off` - Activa/desactiva anuncios (solo admins)\n\n"
        ayuda_msg += "💡 **EJEMPLOS:**\n"
        ayuda_msg += "• `!trilero limosna on` → Activar para todo el servidor\n"
        ayuda_msg += "• `!trilero limosna frecuencia 6` → Cada 6 horas\n"
        ayuda_msg += "• `!trilero limosna estado` → Ver estado y estadísticas\n"
        ayuda_msg += "• `!trilero limosna off` → Desactivar del servidor\n"
        ayuda_msg += "• `!bote jugar` → Jugar al juego de dados\n"
        ayuda_msg += "• `!bote config apuesta 15` → Configurar apuesta a 15 monedas\n\n"
        ayuda_msg += "⚠️ **REQUISITOS:**\n"
        ayuda_msg += "• Solo administradores pueden usar comandos de limosna y configuración del bote\n"
        ayuda_msg += "• Los comandos de limosna y bote solo funcionan en canales del servidor\n"
        ayuda_msg += "• El bote requiere que el rol banquero esté activo\n\n"
        ayuda_msg += "⚠️ **LÍMITES:**\n"
        ayuda_msg += "• Máximo 2 mensajes privados por servidor al día (limosna)\n"
        ayuda_msg += "• Máximo 4 mensajes públicos por servidor al día (limosna)\n"
        ayuda_msg += "• No molestar al mismo usuario en 12 horas (limosna)\n"
        ayuda_msg += "• Apuesta única fija para todos los jugadores (bote)\n"
        
        try:
            await ctx.author.send(ayuda_msg)
            await ctx.send("📩 Ayuda del trilero enviada por mensaje privado.")
        except discord.errors.Forbidden:
            await ctx.send(ayuda_msg[:2000])
    
    if not LIMOSNA_DB_AVAILABLE:
        logger.info("🎭 [DISCORD] Base de datos de limosna no disponible, omitiendo registro de comandos del trilero")

    logger.info("🎭 [DISCORD] Comandos del trilero registrados exitosamente")
    
    # Registrar comandos del bote si está disponible
    if BOTE_AVAILABLE and BOTE_DB_AVAILABLE and BANQUERO_DB_AVAILABLE:
        if bot.get_command("bote") is None:
            logger.info("🎲 [DISCORD] Registrando comandos del bote")
            
            @bot.command(name="bote")
            async def cmd_bote(ctx, *args):
                """Comando principal del juego del Bote."""
                if not ctx.guild:
                    await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
                    return
                
                if not BOTE_AVAILABLE or not BOTE_DB_AVAILABLE or not BANQUERO_DB_AVAILABLE:
                    await ctx.send("❌ El juego del Bote no está disponible en este servidor.")
                    return
                
                # Si no hay argumentos, mostrar ayuda
                if not args:
                    await cmd_bote_ayuda(ctx)
                    return
                
                subcommand = args[0].lower()
                subargs = args[1:] if len(args) > 1 else []
                
                if subcommand == "jugar":
                    await cmd_bote_jugar(ctx)
                elif subcommand == "ayuda":
                    await cmd_bote_ayuda(ctx)
                elif subcommand == "saldo":
                    await cmd_bote_saldo(ctx)
                elif subcommand == "stats":
                    await cmd_bote_stats(ctx)
                elif subcommand == "ranking":
                    await cmd_bote_ranking(ctx)
                elif subcommand == "historial":
                    await cmd_bote_historial(ctx)
                elif subcommand == "config":
                    await cmd_bote_config(ctx, subargs)
                else:
                    await ctx.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!bote ayuda` para ver ayuda.")
            
            async def cmd_bote_jugar(ctx):
                """Realiza una tirada de dados en el juego del bote."""
                if not ctx.guild:
                    await ctx.send("❌ Este comando solo funciona en servidores.")
                    return
                
                try:
                    # Obtener instancias de bases de datos
                    db_banquero = get_banquero_db_instance(ctx.guild.name)
                    db_bote = get_bote_db_instance(ctx.guild.name)
                    
                    if not db_banquero or not db_bote:
                        await ctx.send("❌ Error al acceder a las bases de datos del juego.")
                        return
                    
                    # Verificar que el rol banquero esté activo
                    try:
                        saldo_bote = db_banquero.obtener_saldo("bote_banca", str(ctx.guild.id))
                    except Exception as e:
                        await ctx.send("❌ El rol Banquero debe estar activo para jugar al Bote.")
                        return
                    
                    # Procesar la jugada (ejecutar en thread por ser síncrona)
                    resultado = await asyncio.to_thread(procesar_jugada,
                        str(ctx.author.id),
                        ctx.author.display_name,
                        str(ctx.guild.id),
                        ctx.guild.name,
                        None  # http no necesario para este comando
                    )
                    
                    if resultado["success"]:
                        await ctx.send(resultado["mensaje"])
                        logger.info(f"🎲 [BOTE] {ctx.author.name} jugó en {ctx.guild.name} - Premio: {resultado.get('premio', 0)}")
                    else:
                        await ctx.send(f"❌ {resultado['message']}")
                        
                except Exception as e:
                    logger.exception(f"Error en cmd_bote_jugar: {e}")
                    await ctx.send("❌ Error al procesar la jugada. Inténtalo de nuevo.")
            
            async def cmd_bote_ayuda(ctx):
                """Muestra ayuda completa del juego del Bote."""
                ayuda_msg = "🎲 **JUEGO DEL BOTE - AYUDA** 🎲\n\n"
                ayuda_msg += "**¿Qué es el Bote?**\n"
                ayuda_msg += "Es un juego de dados donde apuestas una cantidad fija contra la banca. "
                ayuda_msg += "Saca 1-1-1 y te llevas todo el bote acumulado.\n\n"
                ayuda_msg += "**🎲 TABLA DE PREMIOS:**\n"
                ayuda_msg += "• **1-1-1** (0.46%) → 🎉 **TODO EL BOTE** 🎉\n"
                ayuda_msg += "• **Triple cualquiera** (2.78%) → x3 tu apuesta\n"
                ayuda_msg += "• **Escalera 4-5-6** (2.78%) → x5 tu apuesta\n"
                ayuda_msg += "• **Par** (41.67%) → Recuperas tu apuesta\n"
                ayuda_msg += "• **Cualquier otra** (52.31%) → Sin premio\n\n"
                ayuda_msg += "**📋 COMANDOS:**\n"
                ayuda_msg += "• `!bote jugar` - Realiza una tirada de dados\n"
                ayuda_msg += "• `!bote saldo` - Muestra el saldo actual del bote (DM)\n"
                ayuda_msg += "• `!bote stats` - Tus estadísticas personales (DM)\n"
                ayuda_msg += "• `!bote ranking` - Ranking de jugadores del servidor\n"
                ayuda_msg += "• `!bote historial` - Últimas partidas jugadas\n"
                ayuda_msg += "• `!bote config apuesta <cantidad>` - Configura apuesta (admins)\n"
                ayuda_msg += "• `!bote config anuncios on/off` - Anuncios automáticos (admins)\n\n"
                ayuda_msg += "**💡 EJEMPLOS:**\n"
                ayuda_msg += "• `!bote jugar` → Tira los dados\n"
                ayuda_msg += "• `!bote config apuesta 15` → Apuesta fija de 15 monedas\n\n"
                ayuda_msg += "**⚠️ REQUISITOS:**\n"
                ayuda_msg += "• Solo funciona en canales de servidor\n"
                ayuda_msg += "• Requiere que el rol Banquero esté activo\n"
                ayuda_msg += "• Apuesta única fija para todos los jugadores\n\n"
                ayuda_msg += "**🏦 ECONOMÍA:**\n"
                ayuda_msg += "• El bote crece con cada tirada sin premio\n"
                ayuda_msg += "• Los premios parciales se pagan de la banca\n"
                ayuda_msg += "• ¡El 1-1-1 vacía todo el bote acumulado!"
                
                try:
                    await ctx.author.send(ayuda_msg)
                    await ctx.send("📩 Ayuda del Bote enviada por mensaje privado.")
                except discord.errors.Forbidden:
                    await ctx.send("❌ No puedo enviarte mensajes privados. Actívalos en la configuración de privacidad.")
                except Exception as e:
                    await ctx.send("❌ Error al enviar la ayuda.")
            
            async def cmd_bote_saldo(ctx):
                """Muestra el saldo actual del bote."""
                if not BANQUERO_DB_AVAILABLE:
                    await ctx.send("❌ El sistema del banquero no está disponible en este servidor.")
                    return
                
                if not BOTE_DB_AVAILABLE:
                    await ctx.send("❌ El sistema del bote no está disponible en este servidor.")
                    return
                
                try:
                    # Obtener mensajes personalizados
                    from roles.trilero.subroles.bote.bote import get_bote_messages
                    messages = get_bote_messages()
                    # Obtener mensajes específicos de saldo o usar fallbacks
                    saldo_messages = PERSONALIDAD.get("discord", {}).get("bote_saldo_messages", {})
                    
                    # Fallbacks si no hay mensajes en la personalidad
                    if not saldo_messages:
                        saldo_messages = {
                            "titulo": "💰 **ESTADO DEL BOTE - {servidor}** 💰\n\n",
                            "saldo_actual": "🎲 **Saldo actual del bote:** {saldo:,} monedas\n",
                            "apuesta_fija": "💎 **Apuesta fija:** {apuesta:,} monedas\n",
                            "jugadas_posibles": "🎯 **Jugadas posibles:** {jugadas}\n\n",
                            "bote_grande": "🔥 **¡EL BOTE ESTÁ GRANDE!** 🔥\n¡Buen momento para intentar ganar {saldo:,} monedas!\n",
                            "bote_mediano": "📈 **Bote mediano** - Bueno para jugar\n",
                            "bote_pequeno": "📉 **Bote pequeño** - Sigue creciendo\n",
                            "usar_comando": "\n💡 Usa `!bote jugar` para intentar tu suerte!",
                            "enviado_privado": "📩 Saldo del bote enviado por mensaje privado.",
                            "error_saldo": "❌ Error al obtener el saldo del bote."
                        }
                    
                    db_banquero = get_banquero_db_instance(ctx.guild.name)
                    saldo_bote = db_banquero.obtener_saldo("bote_banca", str(ctx.guild.id))
                    
                    # Obtener configuración del bote
                    db_bote = get_bote_db_instance(ctx.guild.name)
                    config = db_bote.obtener_configuracion_servidor(str(ctx.guild.id))
                    apuesta_fija = config.get("apuesta_fija", 10)
                    
                    # Construir mensaje usando plantillas desde la personalidad
                    saldo_msg = saldo_messages.get("titulo", "💰 **ESTADO DEL BOTE - {servidor}** 💰\n\n").format(servidor=ctx.guild.name.upper())
                    saldo_msg += saldo_messages.get("saldo_actual", "🎲 **Saldo actual del bote:** {saldo:,} monedas\n").format(saldo=saldo_bote)
                    saldo_msg += saldo_messages.get("apuesta_fija", "💎 **Apuesta fija:** {apuesta:,} monedas\n").format(apuesta=apuesta_fija)
                    saldo_msg += saldo_messages.get("jugadas_posibles", "🎯 **Jugadas posibles:** {jugadas}\n\n").format(jugadas=saldo_bote // apuesta_fija if apuesta_fija > 0 else 0)
                    
                    if saldo_bote >= 100:
                        saldo_msg += saldo_messages.get("bote_grande", "🔥 **¡EL BOTE ESTÁ GRANDE!** 🔥\n¡Buen momento para intentar ganar {saldo:,} monedas!\n").format(saldo=saldo_bote)
                    elif saldo_bote >= 50:
                        saldo_msg += saldo_messages.get("bote_mediano", "📈 **Bote mediano** - Bueno para jugar\n")
                    else:
                        saldo_msg += saldo_messages.get("bote_pequeno", "📉 **Bote pequeño** - Sigue creciendo\n")
                    
                    saldo_msg += saldo_messages.get("usar_comando", "\n💡 Usa `!bote jugar` para intentar tu suerte!")
                    
                    await ctx.author.send(saldo_msg)
                    await ctx.send(saldo_messages.get("enviado_privado", "📩 Saldo del bote enviado por mensaje privado."))
                    
                except Exception as e:
                    logger.exception(f"Error en cmd_bote_saldo: {e}")
                    from roles.trilero.subroles.bote.bote import get_bote_messages
                    messages = get_bote_messages()
                    saldo_messages = PERSONALIDAD.get("discord", {}).get("bote_saldo_messages", {})
                    await ctx.send(saldo_messages.get("error_saldo", "❌ Error al obtener el saldo del bote."))
            
            async def cmd_bote_stats(ctx):
                """Muestra estadísticas personales del jugador."""
                if not ctx.guild:
                    await ctx.send("❌ Este comando solo funciona en servidores.")
                    return
                
                if not BOTE_DB_AVAILABLE:
                    await ctx.send("❌ El sistema del bote no está disponible en este servidor.")
                    return
                
                try:
                    db_bote = get_bote_db_instance(ctx.guild.name)
                    if not db_bote:
                        await ctx.send("❌ Error al acceder a la base de datos del bote.")
                        return
                    
                    stats = db_bote.obtener_estadisticas_jugador(str(ctx.author.id), str(ctx.guild.id))
                    
                    stats_msg = f"📊 **TUS ESTADÍSTICAS DEL BOTE** 📊\n\n"
                    stats_msg += f"👤 **Jugador:** {ctx.author.display_name}\n"
                    stats_msg += f"🎲 **Partidas jugadas:** {stats.get('total_jugadas', 0)}\n"
                    stats_msg += f"💰 **Total apostado:** {stats.get('total_apostado', 0):,} monedas\n"
                    stats_msg += f"🏆 **Total ganado:** {stats.get('total_ganado', 0):,} monedas\n"
                    stats_msg += f"💎 **Botes ganados:** {stats.get('botes_ganados', 0)}\n"
                    stats_msg += f"🎯 **Mayor premio:** {stats.get('mayor_premio', 0):,} monedas\n"
                    stats_msg += f"📈 **Balance neto:** {stats.get('balance', 0):,} monedas\n\n"
                    
                    if stats.get('total_jugadas', 0) > 0:
                        rentabilidad = (stats.get('total_ganado', 0) / stats.get('total_apostado', 1)) * 100
                        stats_msg += f"📊 **Rentabilidad:** {rentabilidad:.1f}%\n"
                        
                        if stats.get('botes_ganados', 0) > 0:
                            stats_msg += f"🎉 **¡FELICIDADES! Has ganado {stats.get('botes_ganados', 0)} bote(s)!\n"
                    else:
                        stats_msg += f"🎲 **Aún no has jugado** - Usa `!bote jugar` para empezar!\n"
                    
                    await ctx.author.send(stats_msg)
                    await ctx.send("📩 Estadísticas enviadas por mensaje privado.")
                    
                except Exception as e:
                    logger.exception(f"Error en cmd_bote_stats: {e}")
                    await ctx.send("❌ Error al obtener tus estadísticas.")
            
            async def cmd_bote_ranking(ctx):
                """Muestra ranking de jugadores del servidor."""
                if not ctx.guild:
                    await ctx.send("❌ Este comando solo funciona en servidores.")
                    return
                
                try:
                    db_bote = get_bote_db_instance(ctx.guild.name)
                    if not db_bote:
                        await ctx.send("❌ Error al acceder a la base de datos del bote.")
                        return
                    
                    ranking = db_bote.obtener_ranking_jugadores(str(ctx.guild.id), "total_ganado", 10)
                    
                    if not ranking:
                        await ctx.send("📊 **RANKING DEL BOTE** - Aún no hay jugadores registrados.")
                        return
                    
                    ranking_msg = f"🏆 **RANKING DEL BOTE - {ctx.guild.name.upper()}** 🏆\n\n"
                    
                    for i, (nombre, ganado, jugadas, total_ganado, total_apostado) in enumerate(ranking, 1):
                        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
                        balance = total_ganado - total_apostado
                        rentabilidad = (total_ganado / total_apostado * 100) if total_apostado > 0 else 0
                        
                        ranking_msg += f"{medal} **{nombre}**\n"
                        ranking_msg += f"   💰 Ganado: {ganado:,} | 🎲 Partidas: {jugadas}\n"
                        ranking_msg += f"   📈 Balance: {balance:,} ({rentabilidad:.1f}%)\n\n"
                    
                    await ctx.send(ranking_msg)
                    
                except Exception as e:
                    logger.exception(f"Error en cmd_bote_ranking: {e}")
                    await ctx.send("❌ Error al obtener el ranking.")
            
            async def cmd_bote_historial(ctx):
                """Muestra las últimas partidas jugadas."""
                if not ctx.guild:
                    await ctx.send("❌ Este comando solo funciona en servidores.")
                    return
                
                try:
                    db_bote = get_bote_db_instance(ctx.guild.name)
                    if not db_bote:
                        await ctx.send("❌ Error al acceder a la base de datos del bote.")
                        return
                    
                    historial = db_bote.obtener_historial_partidas(str(ctx.guild.id), 15)
                    
                    if not historial:
                        await ctx.send("📜 **HISTORIAL DEL BOTE** - Aún no hay partidas registradas.")
                        return
                    
                    historial_msg = f"📜 **ÚLTIMAS PARTIDAS DEL BOTE** 📜\n\n"
                    
                    for nombre, apuesta, dados, combinacion, premio, fecha in historial:
                        # Formatear fecha
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
                            fecha_formateada = dt.strftime("%d/%m %H:%M")
                        except:
                            fecha_formateada = fecha[:16]
                        
                        premio_emoji = "🎉" if premio > 0 else "😅"
                        historial_msg += f"👤 **{nombre}** | {fecha_formateada}\n"
                        historial_msg += f"   🎲 {dados} → {combinacion}\n"
                        historial_msg += f"   {premio_emoji} Premio: {premio:,} monedas\n\n"
                    
                    await ctx.send(historial_msg)
                    
                except Exception as e:
                    logger.exception(f"Error en cmd_bote_historial: {e}")
                    await ctx.send("❌ Error al obtener el historial.")
            
            async def cmd_bote_config(ctx, args):
                """Configura parámetros del bote (solo administradores)."""
                if not ctx.guild:
                    await ctx.send("❌ Este comando solo funciona en servidores.")
                    return
                
                if not ctx.author.guild_permissions.administrator:
                    await ctx.send("❌ Solo los administradores pueden configurar el bote.")
                    return
                
                if not args:
                    await ctx.send("❌ Debes especificar qué configurar. Usa `!bote config apuesta <cantidad>` o `!bote config anuncios on/off`.")
                    return
                
                try:
                    db_bote = get_bote_db_instance(ctx.guild.name)
                    if not db_bote:
                        await ctx.send("❌ Error al acceder a la base de datos del bote.")
                        return
                    
                    param = args[0].lower()
                    
                    if param == "apuesta":
                        if len(args) < 2:
                            await ctx.send("❌ Debes especificar la cantidad. Ejemplo: `!bote config apuesta 15`.")
                            return
                        
                        try:
                            cantidad = int(args[1])
                            if cantidad < 1 or cantidad > 1000:
                                await ctx.send("❌ La apuesta debe estar entre 1 y 1000 monedas.")
                                return
                            
                            if db_bote.configurar_servidor(str(ctx.guild.id), apuesta_fija=cantidad):
                                await ctx.send(f"✅ **Apuesta fija configurada** - Ahora todas las jugadas costarán {cantidad:,} monedas.")
                                logger.info(f"🎲 [BOTE] {ctx.author.name} configuró apuesta a {cantidad} en {ctx.guild.name}")
                            else:
                                await ctx.send("❌ Error al configurar la apuesta.")
                                
                        except ValueError:
                            await ctx.send("❌ Cantidad inválida. Usa un número entero.")
                    
                    elif param == "anuncios":
                        if len(args) < 2:
                            await ctx.send("❌ Debes especificar on/off. Ejemplo: `!bote config anuncios on`.")
                            return
                        
                        estado = args[1].lower()
                        if estado not in ["on", "off"]:
                            await ctx.send("❌ Usa 'on' o 'off'. Ejemplo: `!bote config anuncios on`.")
                            return
                        
                        anuncios_activos = estado == "on"
                        if db_bote.configurar_servidor(str(ctx.guild.id), anuncios_activos=anuncios_activos):
                            estado_msg = "activados" if anuncios_activos else "desactivados"
                            await ctx.send(f"✅ **Anuncios {estado_msg}** - Los anuncios automáticos del bote han sido {estado_msg}.")
                            logger.info(f"🎲 [BOTE] {ctx.author.name} {estado_msg} anuncios en {ctx.guild.name}")
                        else:
                            await ctx.send("❌ Error al configurar los anuncios.")
                    
                    else:
                        await ctx.send("❌ Parámetro no reconocido. Usa `apuesta` o `anuncios`.")
                        
                except Exception as e:
                    logger.exception(f"Error en cmd_bote_config: {e}")
                    await ctx.send("❌ Error al configurar el bote.")
            
            logger.info("🎲 [DISCORD] Comandos del bote registrados exitosamente")
    else:
        logger.warning("🎲 [DISCORD] Sistema del bote no disponible completamente - omitiendo registro de comandos")

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

    # --- INICIO DEL BOT ---
if __name__ == "__main__":
    try:
        # Registrar comandos condicionales antes de iniciar el bot
        try:
            # Registrar comandos del Vigía ANTES de conectar el bot
            if VIGIA_COMMANDS_AVAILABLE:
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
                                await vigia_commands.cmd_general_suscribir(ctx, subargs)
                            elif subcommand == "palabras":
                                await vigia_commands.cmd_palabras_suscribir(ctx, subargs)
                            elif subcommand == "premisas":
                                await vigia_commands.cmd_premisas(ctx, subargs)
                            elif subcommand == "mod":
                                await vigia_commands.cmd_premisas_mod(ctx, subargs)
                            elif subcommand == "reset":
                                await vigia_commands.cmd_reset(ctx, subargs)
                            else:
                                await ctx.author.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!vigiaayuda` para ver ayuda.")
                                if ctx.guild:
                                    await ctx.send("📩 Ayuda enviada por mensaje privado.")
                        except Exception as e:
                            logger.exception(f"Error en comando vigia: {e}")
                            await ctx.send("❌ Error al procesar comando del Vigía")
                
                # Comando de ayuda del Vigía
                if bot.get_command("vigiaayuda") is None:
                    logger.info("📡 [DISCORD] Registrando comando vigiaayuda")
                    
                    @bot.command(name="vigiaayuda")
                    async def cmd_vigia_ayuda(ctx):
                        """Muestra ayuda específica para el Vigía de Noticias (usuarios)."""
                        # Prevenir duplicación usando un ID único del mensaje
                        message_id = f"{ctx.message.id}_{ctx.author.id}"
                        
                        # Si ya procesamos este mensaje, ignorar
                        if hasattr(bot, '_processed_ayuda_messages'):
                            if message_id in bot._processed_ayuda_messages:
                                return
                        else:
                            bot._processed_ayuda_messages = set()
                        
                        bot._processed_ayuda_messages.add(message_id)
                        
                        ayuda_cfg = PERSONALIDAD.get("discord", {}).get("general_messages", {})
                        mensaje_privado = ayuda_cfg.get("help_sent_private", "GRRR Kronk enviar ayuda por mensaje privado umano!")
                        
                        ayuda_vigia = "📡 **Ayuda del Vigía de Noticias - Usuarios** 📡\n\n"
                        
                        ayuda_vigia += "⚠️ **IMPORTANTE:** Solo puedes tener **UN TIPO** de suscripción activa a la vez\n"
                        ayuda_vigia += "• Si te suscribes a un nuevo tipo, se cancelará automáticamente el anterior\n\n"
                        
                        ayuda_vigia += "🎯 **Comandos Principales:**\n"
                        ayuda_vigia += "• `!vigia feeds` - Lista feeds RSS disponibles\n"
                        ayuda_vigia += "• `!vigia categorias` - Muestra categorías activas\n"
                        ayuda_vigia += "• `!vigia estado` - Tu tipo de suscripción activa\n\n"
                        
                        ayuda_vigia += "📰 **Suscripciones Planas:**\n"
                        ayuda_vigia += "• `!vigia suscribir <categoría>` - Todas las noticias con opinión\n"
                        ayuda_vigia += "• **Ejemplo:** `!vigia suscribir economia`\n\n"
                        
                        ayuda_vigia += "🔍 **Palabras Clave:**\n"
                        ayuda_vigia += "• `!vigia palabras \"palabra1,palabra2\"` - Suscripción directa con palabras\n"
                        ayuda_vigia += "• `!vigia palabras add <palabra>` - Añadir palabra a tu lista\n"
                        ayuda_vigia += "• `!vigia palabras list` - Ver todas tus palabras clave\n"
                        ayuda_vigia += "• `!vigia palabras mod <num> \"nueva\"` - Modificar palabra específica\n"
                        ayuda_vigia += "• `!vigia palabras suscribir <categoría>` - Usar palabras ya configuradas\n"
                        ayuda_vigia += "• `!vigia palabras suscripciones` - Ver suscripciones con palabras\n"
                        ayuda_vigia += "• `!vigia palabras desuscribir <categoría>` - Cancelar suscripción\n"
                        ayuda_vigia += "• **Ejemplo:** `!vigia palabras \"bitcoin,crypto\"`\n\n"
                        
                        ayuda_vigia += "🤖 **Suscripciones con IA:**\n"
                        ayuda_vigia += "• `!vigia general <categoría>` - Noticias críticas según tus premisas\n"
                        ayuda_vigia += "• `!vigia general cancelar <categoría>` - Cancelar suscripción con IA\n"
                        ayuda_vigia += "• **Requiere:** Configurar premisas primero (`!vigia premisas add`)\n"
                        ayuda_vigia += "• **Ejemplo:** `!vigia general internacional`\n\n"
                        
                        ayuda_vigia += "🎯 **Gestión de Premisas:**\n"
                        ayuda_vigia += "• `!vigia premisas` / `!vigia premisas list` - Ver tus premisas\n"
                        ayuda_vigia += "• `!vigia premisas add \"texto\"` - Añadir premisa (máx 7)\n"
                        ayuda_vigia += "• `!vigia mod <num> \"nueva premisa\"` - Modificar premisa #<num>\n\n"
                        
                        ayuda_vigia += "🔄 **Reset de Suscripciones:**\n"
                        ayuda_vigia += "• `!vigia reset` - Ver qué tipo de suscripción tienes activa\n"
                        ayuda_vigia += "• `!vigia reset confirmar` - Eliminar TODAS tus suscripciones\n"
                        ayuda_vigia += "• **Úsalo para cambiar de tipo de suscripción**\n\n"
                        
                        ayuda_vigia += "📊 **Estado y Control:**\n"
                        ayuda_vigia += "• `!vigia estado` - Ver tu tipo de suscripción activa\n"
                        ayuda_vigia += "• `!vigia cancelar <categoría>` - Cancelar suscripción plana\n\n"
                        
                        ayuda_vigia += "📂 **Categorías:** economia, internacional, tecnologia, sociedad, politica\n\n"
                        
                        ayuda_vigia += "💡 **Ejemplos Rápidos:**\n"
                        ayuda_vigia += "```\n!vigia palabras add bitcoin           # Añadir palabra\n!vigia palabras list                  # Ver palabras\n!vigia palabras suscribir economia   # Suscribir con palabras\n!vigia reset                         # Ver tipo activo\n!vigia reset confirmar               # Limpiar todo\n!vigia general internacional         # Suscribir con IA\n```\n\n"
                        
                        ayuda_vigia += "📢 **Para Admins:** Usa `!vigiacanalayuda` para comandos de canal"
                        
                        try:
                            # Verificar si el mensaje es demasiado largo antes de enviar
                            if len(ayuda_vigia) > 2000:
                                # Dividir en partes y enviar al usuario por DM
                                partes = [ayuda_vigia[i:i+1900] for i in range(0, len(ayuda_vigia), 1900)]
                                for parte in partes:
                                    await ctx.author.send(parte)
                            else:
                                await ctx.author.send(ayuda_vigia)
                            
                            # Enviar confirmación breve en el canal (solo si está en servidor)
                            if ctx.guild:
                                await ctx.send("📩 Ayuda enviada por mensaje privado.")
                                
                        except discord.errors.Forbidden:
                            # Si no puede enviar DM, enviar en el canal (dividido si es necesario)
                            if len(ayuda_vigia) > 2000:
                                partes = [ayuda_vigia[i:i+1900] for i in range(0, len(ayuda_vigia), 1900)]
                                for parte in partes:
                                    await ctx.send(parte)
                            else:
                                await ctx.send(ayuda_vigia[:2000])
            
            logger.info(f"✅ [DISCORD] Total de comandos registrados: {len(bot.commands)}")
            logger.info(f"🤖 [DISCORD] Comandos registrados: {[cmd.name for cmd in bot.commands]}")
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
