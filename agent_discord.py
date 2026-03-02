import os
import json
import discord
import asyncio
import re
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

logger = get_logger('discord')

# Importar clases del Vigía si está disponible
try:
    from roles.vigia_noticias.vigia_commands import VigiaCommands, COMANDOS_VIGIA, COMANDOS_VIGIA_CANAL
    VIGIA_COMMANDS_AVAILABLE = True
    logger.info("📡 [DISCORD] Comandos del Vigía importados correctamente")
except ImportError as e:
    VIGIA_COMMANDS_AVAILABLE = False
    logger.warning(f"⚠️ [DISCORD] No se pudieron importar comandos del Vigía: {e}")

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
    # Verificar permisos (solo admins o mods)
    if not ctx.author.guild_permissions.administrator and not ctx.author.guild_permissions.manage_guild:
        await ctx.send("❌ Solo administradores pueden modificar los saludos de presencia.")
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
    # Verificar permisos (solo admins o mods)
    if not ctx.author.guild_permissions.administrator and not ctx.author.guild_permissions.manage_guild:
        await ctx.send("❌ Solo administradores pueden modificar los saludos de bienvenida.")
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
    logger.info(f"🧪 Comando test ejecutado por {ctx.author.name}")
    await ctx.send("✅ Comando test funciona!")

# Comando de prueba del Vigía
@bot.command(name="vigiatest")
async def cmd_vigia_test(ctx):
    """Comando de prueba para el Vigía."""
    logger.info(f"📡 Comando vigiatest ejecutado por {ctx.author.name}")
    await ctx.send("📡 ✅ Comando vigiatest funciona - el Vigía está respondiendo!")

# Comando de ayuda
ayuda_command_name = f"ayuda{_personality_name}"

@bot.command(name=ayuda_command_name)
async def cmd_ayuda(ctx):
    """Muestra todos los comandos activos para este agente."""
    
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
        ayuda_msg += "📡 **Vigía de Noticias** - `!avisanoticias` / `!noavisanoticias` | `!vigiaayuda` para ayuda específica\n"
    
    # Buscador de tesoros
    if os.getenv("BUSCADOR_TESOROS_ENABLED", "false").lower() == "true" or roles_config.get("buscador_tesoros", {}).get("enabled", False):
        ayuda_msg += "💎 **Buscador de Tesoros** - `!buscartesoros` / `!nobuscartesoros` | `!poe2ayuda` para ayuda específica\n"
    
    # Pedir oro
    if os.getenv("PEDIR_ORO_ENABLED", "false").lower() == "true" or roles_config.get("pedir_oro", {}).get("enabled", False):
        ayuda_msg += "💰 **Pedir Oro** - `!pediroro` / `!nopediroro`\n"
    
    # Buscar anillo
    if os.getenv("BUSCAR_ANILLO_ENABLED", "false").lower() == "true" or roles_config.get("buscar_anillo", {}).get("enabled", False):
        ayuda_msg += "👁️ **Buscar Anillo** - `!buscanillo` / `!nobuscanillo`\n"
    
    # Música (siempre disponible, independiente de roles)
    ayuda_msg += "🎵 **Música** - `!mc play <canción>` / `!mc queue` | `!mc help` para ayuda completa (siempre disponible)\n\n"
    
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
        elif role_name == "pedir_oro":
            ayuda_msg += f"• {status_emoji} **Pedir Oro** - Solicitudes de donaciones\n"
        elif role_name == "buscar_anillo":
            ayuda_msg += f"• {status_emoji} **Buscar Anillo** - Acusaciones por el anillo\n"
        elif role_name == "mc":
            ayuda_msg += f"• ✅ **Música** - Siempre disponible (no requiere activación)\n"
    
    await ctx.author.send(ayuda_msg)
    await ctx.send(get_message('ayuda_enviada_privado'))

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
    
    await ctx.author.send(ayuda_poe2)
    await ctx.send("✅ Te he enviado la ayuda de POE2 por mensaje privado 📩")

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
    
    await ctx.author.send(ayuda_vigia)
    await ctx.send(mensaje_privado)


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

@bot.event
async def on_ready():
    template = _discord_cfg.get("on_ready_message", "✅ {bot_name} operativo: {bot_user}")
    print(template.format(bot_name=_bot_display_name, bot_user=bot.user))
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
        # Re-obtener logger para que añada handler a fichero ahora que hay servidor activo
        get_logger('discord')

        server_name = active_guild.name.lower().replace(' ', '_').replace('-', '_')
        server_name = ''.join(c for c in server_name if c.isalnum() or c == '_')
        logger.info(f"📁 [DISCORD] Servidor activo: '{active_guild.name}'")
        logger.info(f"📁 [DISCORD] Logs: logs/{server_name}/{_personality_name}.log")
    
    if not limpieza_db.is_running():
        limpieza_db.start()
        logger.info("🧹 [DISCORD] Tarea de limpieza automática iniciada")


@bot.event
async def on_guild_join(guild):
    """Se ejecuta cuando el bot se une a un nuevo servidor."""
    _personality_name = PERSONALIDAD.get("name", "agent").lower()
    update_log_file_path(guild.name, _personality_name)
    get_logger('discord')
    logger.info(f"📁 [DISCORD] Nuevo servidor '{guild.name}': logs/{guild.name.lower().replace(' ', '_').replace('-', '_')}/{_personality_name}.log")


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


# --- COMANDOS DE CONTROL DE ROLES ---

async def _cmd_role_toggle(ctx, role_name: str, enabled: bool):
    """Comando genérico para activar/desactivar roles dinámicamente."""
    # Verificar permisos (solo admins)
    if not ctx.author.guild_permissions.administrator and not ctx.author.guild_permissions.manage_guild:
        await ctx.send("❌ Solo administradores pueden modificar los roles.")
        return
    
    # Lista de roles válidos
    valid_roles = ["vigia_noticias", "buscador_tesoros", "pedir_oro", "buscar_anillo"]
    
    if role_name not in valid_roles:
        await ctx.send(f"❌ Rol '{role_name}' no válido. Roles disponibles: {', '.join(valid_roles)}")
        return
    
    # Variable de entorno
    env_var_name = f"{role_name.upper()}_ENABLED"
    env_value = "true" if enabled else "false"
    
    # Establecer variable de entorno (solo para esta sesión)
    os.environ[env_var_name] = env_value
    
    # Actualizar configuración en tiempo de ejecución
    if "roles" not in agent_config:
        agent_config["roles"] = {}
    
    if role_name not in agent_config["roles"]:
        agent_config["roles"][role_name] = {}
    
    agent_config["roles"][role_name]["enabled"] = enabled
    
    # Registrar comandos del rol si se está activando
    if enabled:
        await register_specific_role_commands(role_name)
    else:
        # Desregistrar comandos del rol (opcional, complicado)
        logger.info(f"🎭 [DISCORD] Rol {role_name} desactivado (comandos permanecen registrados)")
    
    action = "activado" if enabled else "desactivado"
    await ctx.send(f"✅ Rol '{role_name}' {action} correctamente.")
    logger.info(f"🎭 [DISCORD] {ctx.author.name} {action} el rol {role_name} en {ctx.guild.name}")

async def register_specific_role_commands(role_name: str):
    """Registra comandos para un rol específico."""
    logger.info(f"🎭 [DISCORD] Registrando comandos para rol: {role_name}")
    
    if role_name == "vigia_noticias":
        # Comandos del Vigía de Noticias
        @bot.command(name="avisanoticias")
        async def cmd_avisa_noticias(ctx):
            if not VIGIA_AVAILABLE:
                await ctx.send("❌ El Vigía de la Torre no está disponible en este servidor.")
                return
            
            db_vigia_instance = get_vigia_db_for_server(ctx.guild)
            if not db_vigia_instance:
                await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                return
            
            usuario_id = str(ctx.author.id)
            usuario_nombre = ctx.author.name
            
            # Verificar si ya está suscrito
            if db_vigia_instance.esta_suscrito(usuario_id):
                await ctx.send(f"🛡️ {ctx.author.mention} Ya estás suscrito a las alertas del Vigía de la Torre.")
                return
            
            # Agregar suscripción
            if db_vigia_instance.agregar_suscripcion(usuario_id, usuario_nombre):
                await ctx.send(f"✅ {ctx.author.mention} Te has suscrito a las alertas del Vigía de la Torre. Recibirás noticias críticas cuando ocurran.")
                logger.info(f"📡 [VIGÍA] {usuario_nombre} ({usuario_id}) se suscribió a las alertas en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al suscribirte a las alertas. Inténtalo de nuevo.")
        
        @bot.command(name="noavisanoticias")
        async def cmd_no_avisa_noticias(ctx):
            if not VIGIA_AVAILABLE:
                await ctx.send("❌ El Vigía de la Torre no está disponible en este servidor.")
                return
            
            db_vigia_instance = get_vigia_db_for_server(ctx.guild)
            if not db_vigia_instance:
                await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                return
            
            usuario_id = str(ctx.author.id)
            usuario_nombre = ctx.author.name
            
            # Verificar si está suscrito
            if not db_vigia_instance.esta_suscrito(usuario_id):
                await ctx.send(f"🛡️ {ctx.author.mention} No estás suscrito a las alertas del Vigía de la Torre.")
                return
            
            # Eliminar suscripción
            if db_vigia_instance.eliminar_suscripcion(usuario_id):
                await ctx.send(f"✅ {ctx.author.mention} Te has desuscrito de las alertas del Vigía de la Torre. Ya no recibirás noticias críticas.")
                logger.info(f"📡 [VIGÍA] {usuario_nombre} ({usuario_id}) se desuscribió de las alertas en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al desuscribirte de las alertas. Inténtalo de nuevo.")
    
    elif role_name == "buscar_anillo":
        # Comando para acusar por el anillo
        @bot.command(name="acusaranillo")
        async def cmd_acusar_anillo(ctx, target: str = ""):
            if not target:
                await ctx.send("❌ Debes mencionar a alguien para acusar. Ejemplo: !acusaranillo @usuario")
                return
            
            # Obtener instancia de BD para este servidor
            db_instance = get_db_for_server(ctx.guild)
            
            # Buscar al usuario mencionado
            mentioned_user = None
            for user in ctx.message.mentions:
                if not user.bot and user.id != ctx.author.id:
                    mentioned_user = user
                    break
            
            if not mentioned_user:
                await ctx.send("❌ No se encontró un usuario válido para acusar.")
                return
            
            # Generar acusación usando la personalidad
            accusation_prompt = f"Acusa brevemente a {mentioned_user.display_name} de tener el anillo uniko. Sé orco y directo."
            accusation = await asyncio.to_thread(pensar, accusation_prompt)
            
            await ctx.send(f"👁️ {mentioned_user.mention} {accusation}")
            
            # Registrar en la base de datos
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
    
    elif role_name == "buscador_tesoros":
        # Importar pensar para el subrol POE2
        from agent_engine import pensar
        
        # Comandos del subrol POE2
        @bot.command(name="buscartesoros")
        async def cmd_buscar_tesoros(ctx, subrol: str = ""):
            if not subrol or subrol.lower() != "poe2":
                await ctx.send("❌ Debes especificar el subrol. Ejemplo: !buscartesoros poe2")
                return
            
            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return
            
            db_poe2_instance = get_poe2_db_for_server(ctx.guild)
            if not db_poe2_instance:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return
            
            # Activar el subrol
            if db_poe2_instance.set_activo(True):
                await ctx.send(f"✅ {ctx.author.mention} Subrol POE2 activado. Ahora buscaré tesoros en Path of Exile 2.")
                logger.info(f"🔮 [POE2] {ctx.author.name} activó el subrol en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al activar el subrol POE2. Inténtalo de nuevo.")
        
        @bot.command(name="nobuscartesoros")
        async def cmd_no_buscar_tesoros(ctx, subrol: str = ""):
            if not subrol or subrol.lower() != "poe2":
                await ctx.send("❌ Debes especificar el subrol. Ejemplo: !nobuscartesoros poe2")
                return
            
            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return
            
            db_poe2_instance = get_poe2_db_for_server(ctx.guild)
            if not db_poe2_instance:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return
            
            # Desactivar el subrol
            if db_poe2_instance.set_activo(False):
                await ctx.send(f"✅ {ctx.author.mention} Subrol POE2 desactivado. Ya no buscaré tesoros en Path of Exile 2.")
                logger.info(f"🔮 [POE2] {ctx.author.name} desactivó el subrol en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al desactivar el subrol POE2. Inténtalo de nuevo.")
        
        # Comandos de gestión del subrol POE2
        @bot.command(name="poe2liga")
        async def cmd_poe2_liga(ctx, liga: str = ""):
            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return
            
            if not liga:
                # Mostrar liga actual
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                liga_actual = db_poe2_instance.get_liga()
                await ctx.send(f"🔮 **Liga POE2 actual**: {liga_actual}")
                return
            
            # Validar liga
            liga_lower = liga.lower()
            if liga_lower not in ["standard", "fate of the vaal"]:
                await ctx.send("❌ Liga no válida. Las ligas disponibles son: `Standard` y `Fate of the Vaal`")
                return
            
            db_poe2_instance = get_poe2_db_for_server(ctx.guild)
            if not db_poe2_instance:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return
            
            # Establecer liga
            liga_formateada = "Fate of the Vaal" if liga_lower == "fate of the vaal" else "Standard"
            if db_poe2_instance.set_liga(liga_formateada):
                await ctx.send(f"✅ {ctx.author.mention} Liga POE2 establecida a: {liga_formateada}")
                logger.info(f"🔮 [POE2] {ctx.author.name} cambió liga a {liga_formateada} en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al cambiar la liga. Inténtalo de nuevo.")
        
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
            
            # Añadir objetivo
            if db_poe2_instance.add_objetivo(item_name):
                await ctx.send(f"✅ {ctx.author.mention} Item añadido a objetivos: {item_name}")
                logger.info(f"🔮 [POE2] {ctx.author.name} añadió objetivo {item_name} en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al añadir el item. Inténtalo de nuevo.")
        
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
            
            # Eliminar objetivo
            if db_poe2_instance.remove_objetivo(item_name):
                await ctx.send(f"✅ {ctx.author.mention} Item eliminado de objetivos: {item_name}")
                logger.info(f"🔮 [POE2] {ctx.author.name} eliminó objetivo {item_name} en {ctx.guild.name}")
            else:
                await ctx.send(f"❌ No se encontró el item '{item_name}' en la lista de objetivos.")
        
        @bot.command(name="poe2list")
        async def cmd_poe2_list(ctx):
            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return
            
            db_poe2_instance = get_poe2_db_for_server(ctx.guild)
            if not db_poe2_instance:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return
            
            # Obtener configuración actual
            liga_actual = db_poe2_instance.get_liga()
            activo = db_poe2_instance.is_activo()
            objetivos = db_poe2_instance.get_objetivos()
            
            # Formatear respuesta
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

def register_role_commands():
    """Registra comandos solo si el rol correspondiente está activado."""
    import os
    
    # Función helper para verificar si un rol está activado
    def is_role_enabled(role_name):
        # Prioridad a variables de entorno
        env_var = os.getenv(f"{role_name.upper()}_ENABLED", "").lower()
        if env_var:
            logger.info(f"🔍 Verificando {role_name}: env_var={env_var} -> {env_var == 'true'}")
            return env_var == "true"
        # Fallback a configuración JSON
        enabled = agent_config.get("roles", {}).get(role_name, {}).get("enabled", False)
        logger.info(f"🔍 Verificando {role_name}: config={enabled}")
        return enabled
    
    # Lista de roles a verificar
    roles_to_check = ["vigia_noticias", "buscador_tesoros", "pedir_oro", "buscar_anillo"]
    
    logger.info(f"🎭 [DISCORD] Iniciando registro de comandos para {len(roles_to_check)} roles")
    
    for role_name in roles_to_check:
        if not is_role_enabled(role_name):
            logger.info(f"🎭 [DISCORD] Rol {role_name} no está activado, omitiendo")
            continue
            
        logger.info(f"🎭 [DISCORD] Registrando comandos para rol activado: {role_name}")
        
        if role_name == "vigia_noticias":
            if not VIGIA_COMMANDS_AVAILABLE:
                logger.warning("⚠️ [DISCORD] Comandos del Vigía no disponibles, usando implementación básica")
                # Implementación básica de fallback
                @bot.command(name="avisanoticias")
                async def cmd_avisa_noticias(ctx):
                    if not VIGIA_AVAILABLE:
                        await ctx.send("❌ El Vigía de la Torre no está disponible en este servidor.")
                        return
                    
                    db_vigia_instance = get_vigia_db_for_server(ctx.guild)
                    if not db_vigia_instance:
                        await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                        return
                    
                    usuario_id = str(ctx.author.id)
                    usuario_nombre = ctx.author.name
                    
                    # Verificar si ya está suscrito
                    if db_vigia_instance.esta_suscrito(usuario_id):
                        await ctx.send(f"🛡️ {ctx.author.mention} Ya estás suscrito a las alertas del Vigía de la Torre.")
                        return
                    
                    # Agregar suscripción
                    if db_vigia_instance.agregar_suscripcion(usuario_id, usuario_nombre):
                        await ctx.send(f"✅ {ctx.author.mention} Te has suscrito a las alertas del Vigía de la Torre. Recibirás noticias críticas cuando ocurran.")
                        logger.info(f"📡 [VIGÍA] {usuario_nombre} ({usuario_id}) se suscribió a las alertas en {ctx.guild.name}")
                    else:
                        await ctx.send("❌ Error al suscribirte a las alertas. Inténtalo de nuevo.")
                
                @bot.command(name="noavisanoticias")
                async def cmd_no_avisa_noticias(ctx):
                    if not VIGIA_AVAILABLE:
                        await ctx.send("❌ El Vigía de la Torre no está disponible en este servidor.")
                        return
                    
                    db_vigia_instance = get_vigia_db_for_server(ctx.guild)
                    if not db_vigia_instance:
                        await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                        return
                    
                    usuario_id = str(ctx.author.id)
                    usuario_nombre = ctx.author.name
                    
                    # Verificar si está suscrito
                    if not db_vigia_instance.esta_suscrito(usuario_id):
                        await ctx.send(f"🛡️ {ctx.author.mention} No estás suscrito a las alertas del Vigía de la Torre.")
                        return
                    
                    # Eliminar suscripción
                    if db_vigia_instance.eliminar_suscripcion(usuario_id):
                        await ctx.send(f"✅ {ctx.author.mention} Te has desuscrito de las alertas del Vigía de la Torre. Ya no recibirás noticias críticas.")
                        logger.info(f"📡 [VIGÍA] {usuario_nombre} ({usuario_id}) se desuscribió de las alertas en {ctx.guild.name}")
                    else:
                        await ctx.send("❌ Error al desuscribirte de las alertas. Inténtalo de nuevo.")
            else:
                # Implementación completa del Vigía usando VigiaCommands con grupos de comandos
                logger.info("📡 [DISCORD] Registrando comandos completos del Vigía")
                vigia_commands = VigiaCommands(bot)
                
                # Crear grupo de comandos vigia
                @bot.group(name="vigia")
                async def vigia_group(ctx):
                    """Comandos del Vigía de Noticias."""
                    if ctx.invoked_subcommand is None:
                        await ctx.send("📡 Usa `!vigiaayuda` para ver la ayuda completa del Vigía")
                
                # Crear grupo de comandos vigiacanal
                @bot.group(name="vigiacanal")
                async def vigiacanal_group(ctx):
                    """Comandos del Vigía para canales."""
                    if ctx.invoked_subcommand is None:
                        await ctx.send("📡 Usa `!vigiaayuda` para ver la ayuda completa del Vigía")
                
                # Registrar comandos principales del Vigía
                for cmd_name, cmd_func in COMANDOS_VIGIA.items():
                    try:
                        def make_command(name, func):
                            async def command(ctx, *args):
                                return await func(vigia_commands, ctx.message, list(args))
                            return command
                        
                        cmd_func_wrapper = make_command(cmd_name, cmd_func)
                        vigia_group.command(name=cmd_name)(cmd_func_wrapper)
                        logger.info(f"📡 [DISCORD] Subcomando vigia {cmd_name} registrado")
                    except Exception as e:
                        logger.error(f"Error registrando comando vigia {cmd_name}: {e}")
                
                # Registrar comandos de canal del Vigía
                for cmd_name, cmd_func in COMANDOS_VIGIA_CANAL.items():
                    try:
                        def make_command(name, func):
                            async def command(ctx, *args):
                                return await func(vigia_commands, ctx.message, list(args))
                            return command
                        
                        cmd_func_wrapper = make_command(cmd_name, cmd_func)
                        vigiacanal_group.command(name=cmd_name)(cmd_func_wrapper)
                        logger.info(f"📡 [DISCORD] Subcomando vigiacanal {cmd_name} registrado")
                    except Exception as e:
                        logger.error(f"Error registrando comando vigiacanal {cmd_name}: {e}")
                
                logger.info(f"📡 [DISCORD] Registrados {len(COMANDOS_VIGIA)} comandos vigia y {len(COMANDOS_VIGIA_CANAL)} comandos vigiacanal")
        
        elif role_name == "buscar_anillo":
            # Comando para acusar por el anillo
            @bot.command(name="acusaranillo")
            async def cmd_acusar_anillo(ctx, target: str = ""):
                if not target:
                    await ctx.send("❌ Debes mencionar a alguien para acusar. Ejemplo: !acusaranillo @usuario")
                    return
                
                # Obtener instancia de BD para este servidor
                db_instance = get_db_for_server(ctx.guild)
                
                # Buscar al usuario mencionado
                mentioned_user = None
                for user in ctx.message.mentions:
                    if not user.bot and user.id != ctx.author.id:
                        mentioned_user = user
                        break
                
                if not mentioned_user:
                    await ctx.send("❌ No se encontró un usuario válido para acusar.")
                    return
                
                # Generar acusación usando la personalidad
                accusation_prompt = f"Acusa brevemente a {mentioned_user.display_name} de tener el anillo uniko. Sé orco y directo."
                accusation = await asyncio.to_thread(pensar, accusation_prompt)
                
                # Enviar acusación
                await ctx.send(f"👁️ {mentioned_user.mention} {accusation}")
                
                # Registrar en la base de datos
                servidor_id = getattr(ctx.guild, 'id', None)
                await asyncio.to_thread(
                    db_instance.registrar_interaccion,
                    mentioned_user.id,
                    mentioned_user.name,
                    "ACUSACION_ANILLO",
                    f"Acusado por tener el anillo",
                    ctx.channel.id,
                    servidor_id,
                    metadata={
                        "acusador_id": str(ctx.author.id),
                        "acusador_nombre": ctx.author.name,
                        "acusacion": accusation
                    }
                )
                
                logger.info(f"👁️ [ANILLO] {ctx.author.name} acusó a {mentioned_user.name} en {ctx.guild.name}")
        
        elif role_name == "buscador_tesoros":
            # Importar pensar para el subrol POE2
            from agent_engine import pensar
            
            # Comandos del subrol POE2
            @bot.command(name="buscartesoros")
            async def cmd_buscar_tesoros(ctx, subrol: str = ""):
                if not subrol or subrol.lower() != "poe2":
                    await ctx.send("❌ Debes especificar el subrol. Ejemplo: !buscartesoros poe2")
                    return
                
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                # Activar el subrol
                if db_poe2_instance.set_activo(True):
                    await ctx.send(f"✅ {ctx.author.mention} Subrol POE2 activado. Ahora buscaré tesoros en Path of Exile 2.")
                    logger.info(f"🔮 [POE2] {ctx.author.name} activó el subrol en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al activar el subrol POE2. Inténtalo de nuevo.")
            
            @bot.command(name="nobuscartesoros")
            async def cmd_no_buscar_tesoros(ctx, subrol: str = ""):
                if not subrol or subrol.lower() != "poe2":
                    await ctx.send("❌ Debes especificar el subrol. Ejemplo: !nobuscartesoros poe2")
                    return
                
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                # Desactivar el subrol
                if db_poe2_instance.set_activo(False):
                    await ctx.send(f"✅ {ctx.author.mention} Subrol POE2 desactivado. Ya no buscaré tesoros en Path of Exile 2.")
                    logger.info(f"🔮 [POE2] {ctx.author.name} desactivó el subrol en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al desactivar el subrol POE2. Inténtalo de nuevo.")
            
            # Comandos de gestión del subrol POE2
            @bot.command(name="poe2liga")
            async def cmd_poe2_liga(ctx, liga: str = ""):
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                if not liga:
                    # Mostrar liga actual
                    db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                    if not db_poe2_instance:
                        await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                        return
                    
                    liga_actual = db_poe2_instance.get_liga()
                    await ctx.send(f"🔮 **Liga POE2 actual**: {liga_actual}")
                    return
                
                # Validar liga
                liga_lower = liga.lower()
                if liga_lower not in ["standard", "fate of the vaal"]:
                    await ctx.send("❌ Liga no válida. Las ligas disponibles son: `Standard` y `Fate of the Vaal`")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                # Establecer liga
                liga_formateada = "Fate of the Vaal" if liga_lower == "fate of the vaal" else "Standard"
                if db_poe2_instance.set_liga(liga_formateada):
                    await ctx.send(f"✅ {ctx.author.mention} Liga POE2 establecida a: {liga_formateada}")
                    logger.info(f"🔮 [POE2] {ctx.author.name} cambió liga a {liga_formateada} en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al cambiar la liga. Inténtalo de nuevo.")
            
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
                
                # Añadir objetivo
                if db_poe2_instance.add_objetivo(item_name):
                    await ctx.send(f"✅ {ctx.author.mention} Item añadido a objetivos: {item_name}")
                    logger.info(f"🔮 [POE2] {ctx.author.name} añadió objetivo {item_name} en {ctx.guild.name}")
                else:
                    await ctx.send("❌ Error al añadir el item. Inténtalo de nuevo.")
            
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
                
                # Eliminar objetivo
                if db_poe2_instance.remove_objetivo(item_name):
                    await ctx.send(f"✅ {ctx.author.mention} Item eliminado de objetivos: {item_name}")
                    logger.info(f"🔮 [POE2] {ctx.author.name} eliminó objetivo {item_name} en {ctx.guild.name}")
                else:
                    await ctx.send(f"❌ No se encontró el item '{item_name}' en la lista de objetivos.")
            
            @bot.command(name="poe2list")
            async def cmd_poe2_list(ctx):
                if not POE2_AVAILABLE:
                    await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                    return
                
                db_poe2_instance = get_poe2_db_for_server(ctx.guild)
                if not db_poe2_instance:
                    await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                    return
                
                # Obtener configuración actual
                liga_actual = db_poe2_instance.get_liga()
                activo = db_poe2_instance.is_activo()
                objetivos = db_poe2_instance.get_objetivos()
                
                # Formatear respuesta
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


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.author.bot:
        return  # Ignorar mensajes de otros bots para evitar bucles
    
    # Log para ver si los mensajes están llegando
    logger.info(f"📨 [DISCORD] Mensaje recibido: '{message.content}' de {message.author.name}")
    
    await bot.process_commands(message)

    if message.content.startswith(bot.command_prefix):
        return

    # --- CONVERSACIÓN NORMAL (cuando mencionan al bot o DM) ---
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        async with message.channel.typing():
            fallback_msg = _discord_cfg.get("empty_message_fallback", "Hola")
            texto = re.sub(r'<@!?\d+>', '', message.content).strip() or fallback_msg

            # --- DETECCIÓN DE ACUSACIONES / MENCIONES DE TERCEROS ---
            usuarios_mencionados = message.mentions
            accusation_type = _discord_cfg.get("accusation_type", "MENCION")
            accusation_template = _discord_cfg.get(
                "accusation_template",
                "{informante} mencionó a {acusado}"
            )
            
            # Obtener instancia de BD para este servidor
            db_instance = get_db_for_server(message.guild)

            if usuarios_mencionados:
                acusados = [
                    u for u in usuarios_mencionados
                    if u.id != bot.user.id and u.id != message.author.id and not u.bot
                ]
                if acusados:
                    servidor_id = getattr(message.guild, 'id', None)
                    for acusado in acusados:
                        contexto_acusacion = accusation_template.format(
                            informante=message.author.name,
                            acusado=acusado.name
                        )
                        await asyncio.to_thread(
                            db_instance.registrar_interaccion,
                            acusado.id,
                            acusado.name,
                            accusation_type,
                            contexto_acusacion,
                            message.channel.id,
                            servidor_id,
                            metadata={
                                "informante_id": str(message.author.id),
                                "informante_nombre": message.author.name,
                                "mensaje_original": message.content
                            }
                        )

            # --- MEMORIA HÍBRIDA ---
            hist_user = await asyncio.to_thread(db_instance.obtener_historial_usuario, str(message.author.id))
            hist_canal = []
            if not isinstance(message.channel, discord.DMChannel):
                hist_canal = await asyncio.to_thread(db_instance.obtener_historial_usuario, str(message.channel.id), limite=1)

            # Historial de menciones (keywords importantes de la personalidad)
            hist_sospechas = []
            keywords = PERSONALIDAD.get("history_keywords", [])
            if usuarios_mencionados and keywords:
                for usuario in usuarios_mencionados:
                    if usuario.id != bot.user.id and not usuario.bot:
                        sospechas = await asyncio.to_thread(db_instance.obtener_historial_usuario, str(usuario.id), limite=3)
                        for s in sospechas:
                            texto_s = (s.get("humano", "") + " " + s.get("bot", "")).lower()
                            if any(kw in texto_s for kw in keywords):
                                hist_sospechas.append(s)

            hist_total = hist_canal + hist_user + hist_sospechas

            # --- CONTEXTO DINÁMICO SEGÚN PERSONALIDAD ---
            contexto = _discord_cfg.get("default_context", "Hablas con alguien. Responde en personaje.")
            contexts_cfg = _discord_cfg.get("contexts", {})
            texto_lower = texto.lower()

            # Primero el mensaje actual, luego el historial
            matched = False
            for ctx_key, ctx_def in contexts_cfg.items():
                if any(kw in texto_lower for kw in ctx_def.get("keywords", [])):
                    contexto = ctx_def["message"]
                    matched = True
                    break

            if not matched:
                for ctx_key, ctx_def in contexts_cfg.items():
                    if any(
                        any(kw in (h.get("humano", "") + " " + h.get("bot", "")).lower() for kw in ctx_def.get("keywords", []))
                        for h in hist_total
                    ):
                        contexto = ctx_def["message"]
                        break

            es_canal_publico = not isinstance(message.channel, discord.DMChannel)
            respuesta = await asyncio.to_thread(pensar, contexto, texto, hist_total, es_canal_publico)
            await message.reply(respuesta)

            servidor_id = getattr(message.guild, 'id', None)
            await asyncio.to_thread(
                db_instance.registrar_interaccion,
                message.author.id,
                message.author.name,
                "CHARLA",
                texto,
                message.channel.id if message.channel else None,
                servidor_id,
                metadata={"respuesta": respuesta}
            )

# Registrar comandos condicionales antes de iniciar el bot
print("🔍 Llamando a register_role_commands...")
try:
    register_role_commands()
    print("🔍 register_role_commands completado")
except Exception as e:
    print(f"❌ Error en register_role_commands: {e}")
    import traceback
    traceback.print_exc()

# Forzar registro de comandos del Vigía si están disponibles
if VIGIA_COMMANDS_AVAILABLE:
    print("🔍 Forzando registro de comandos del Vigía...")
    try:
        # Implementación completa del Vigía usando VigiaCommands con grupos de comandos
        logger.info("📡 [DISCORD] Registrando comandos completos del Vigía (forzado)")
        vigia_commands = VigiaCommands(bot)
        
        # Verificar si el grupo vigia ya existe
        if "vigia" not in [cmd.name for cmd in bot.commands]:
            # Crear grupo de comandos vigia
            @bot.group(name="vigia")
            async def vigia_group(ctx):
                """Comandos del Vigía de Noticias."""
                if ctx.invoked_subcommand is None:
                    await ctx.send("📡 Usa `!vigiaayuda` para ver la ayuda completa del Vigía")
            
            logger.info("📡 [DISCORD] Grupo vigia creado (forzado)")
        else:
            # Obtener el grupo existente
            vigia_group = bot.get_command("vigia")
            logger.info("📡 [DISCORD] Grupo vigia ya existente, reutilizando (forzado)")
        
        # Verificar si el grupo vigiacanal ya existe
        if "vigiacanal" not in [cmd.name for cmd in bot.commands]:
            # Crear grupo de comandos vigiacanal
            @bot.group(name="vigiacanal")
            async def vigiacanal_group(ctx):
                """Comandos del Vigía para canales."""
                if ctx.invoked_subcommand is None:
                    await ctx.send("📡 Usa `!vigiaayuda` para ver la ayuda completa del Vigía")
            
            logger.info("📡 [DISCORD] Grupo vigiacanal creado (forzado)")
        else:
            # Obtener el grupo existente
            vigiacanal_group = bot.get_command("vigiacanal")
            logger.info("📡 [DISCORD] Grupo vigiacanal ya existente, reutilizando (forzado)")
        
        # Registrar comandos principales del Vigía
        for cmd_name, cmd_func in COMANDOS_VIGIA.items():
            try:
                def make_command(name, func):
                    async def command(ctx, *args):
                        return await func(vigia_commands, ctx.message, list(args))
                    return command
                
                cmd_func_wrapper = make_command(cmd_name, cmd_func)
                vigia_group.command(name=cmd_name)(cmd_func_wrapper)
                logger.info(f"📡 [DISCORD] Subcomando vigia {cmd_name} registrado (forzado)")
            except Exception as e:
                logger.error(f"Error registrando comando vigia {cmd_name}: {e}")
        
        # Registrar comandos de canal del Vigía
        for cmd_name, cmd_func in COMANDOS_VIGIA_CANAL.items():
            try:
                def make_command(name, func):
                    async def command(ctx, *args):
                        return await func(vigia_commands, ctx.message, list(args))
                    return command
                
                cmd_func_wrapper = make_command(cmd_name, cmd_func)
                vigiacanal_group.command(name=cmd_name)(cmd_func_wrapper)
                logger.info(f"📡 [DISCORD] Subcomando vigiacanal {cmd_name} registrado (forzado)")
            except Exception as e:
                logger.error(f"Error registrando comando vigiacanal {cmd_name}: {e}")
        
        logger.info(f"📡 [DISCORD] Registrados {len(COMANDOS_VIGIA)} comandos vigia y {len(COMANDOS_VIGIA_CANAL)} comandos vigiacanal (forzado)")
        print("🔍 Comandos del Vigía registrados correctamente (forzado)")
    except Exception as e:
        print(f"❌ Error forzando registro del Vigía: {e}")
        import traceback
        traceback.print_exc()

# Verificar comandos registrados
print(f"🔍 Total de comandos registrados: {len(bot.commands)}")
for cmd in bot.commands:
    print(f"  - {cmd.name}")

bot.run(get_discord_token())
