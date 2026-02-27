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

# Verificar si el rol vigia_noticias está activado (prioridad a variables de entorno)
import os
vigia_role_enabled = os.getenv("VIGIA_NOTICIAS_ENABLED", "false").lower() == "true"
if not vigia_role_enabled:
    # Fallback a configuración JSON si no hay variable de entorno
    vigia_role_enabled = agent_config.get("roles", {}).get("vigia_noticias", {}).get("enabled", False)

# VIGIA_AVAILABLE solo es True si el módulo se puede importar Y el rol está activado
VIGIA_AVAILABLE = module_available and vigia_role_enabled

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

logger = get_logger('discord')

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
    """Comando genérico para activar/desactivar saludos."""
    # Verificar permisos (solo admins o mods)
    if not ctx.author.guild_permissions.administrator and not ctx.author.guild_permissions.manage_guild:
        await ctx.send("❌ Solo administradores pueden modificar los saludos.")
        return
    
    set_greeting_enabled(ctx.guild, enabled)
    
    action = "activados" if enabled else "desactivados"
    await ctx.send(f"✅ Saludos {action} en este servidor.")
    logger.info(f"🔧 [DISCORD] {ctx.author.name} {action} los saludos en {ctx.guild.name}")

# Registrar comandos dinámicos para saludos con formato estándar
personality_name = PERSONALIDAD.get("name", "agent").lower()

# Comando para activar saludos: !saluda[nombre]
saluda_command_name = f"saluda{personality_name}"

@bot.command(name=saluda_command_name)
async def cmd_saluda_enable(ctx):
    await _cmd_saluda_toggle(ctx, True)

logger.info(f"🤖 [DISCORD] Comando de saludos registrado: {saluda_command_name}")

# Comando para desactivar saludos: !nosaludes[nombre]
nosaludes_command_name = f"nosaludes{personality_name}"

@bot.command(name=nosaludes_command_name)
async def cmd_saluda_disable(ctx):
    await _cmd_saluda_toggle(ctx, False)

logger.info(f"🤖 [DISCORD] Comando de saludos registrado: {nosaludes_command_name}")

# --- EVENTOS Y COMANDOS ---

@bot.event
async def on_ready():
    template = _discord_cfg.get("on_ready_message", "✅ {bot_name} operativo: {bot_user}")
    print(template.format(bot_name=_bot_display_name, bot_user=bot.user))
    logger.info(f"🤖 [DISCORD] Bot {_bot_display_name} conectado como {bot.user}")
    logger.info(f"🤖 [DISCORD] Comando prefijo: {_cmd_prefix}")
    logger.info(f"🤖 [DISCORD] Comando insulto: {_insult_name}")

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

        personality_name = PERSONALIDAD.get("name", "agent").lower()
        update_log_file_path(active_guild.name, personality_name)
        # Re-obtener logger para que añada handler a fichero ahora que hay servidor activo
        get_logger('discord')

        server_name = active_guild.name.lower().replace(' ', '_').replace('-', '_')
        server_name = ''.join(c for c in server_name if c.isalnum() or c == '_')
        logger.info(f"📁 [DISCORD] Servidor activo: '{active_guild.name}'")
        logger.info(f"📁 [DISCORD] Logs: logs/{server_name}/{personality_name}.log")
    
    if not limpieza_db.is_running():
        limpieza_db.start()
        logger.info("🧹 [DISCORD] Tarea de limpieza automática iniciada")


@bot.event
async def on_guild_join(guild):
    """Se ejecuta cuando el bot se une a un nuevo servidor."""
    personality_name = PERSONALIDAD.get("name", "agent").lower()
    update_log_file_path(guild.name, personality_name)
    get_logger('discord')
    logger.info(f"📁 [DISCORD] Nuevo servidor '{guild.name}': logs/{guild.name.lower().replace(' ', '_')}/{personality_name}.log")


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
async def on_member_update(before, after):
    """Se ejecuta cuando el estado de un miembro cambia (offline a online, etc.)."""
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
    if not hasattr(on_member_update, '_last_greetings'):
        on_member_update._last_greetings = {}
    
    last_greeting_time = on_member_update._last_greetings.get(last_greeting_key, 0)
    if current_time - last_greeting_time < 300:  # 5 minutos
        return
    
    # Determinar canal para saludos de presencia
    presence_channel_name = presence_cfg.get("welcome_channel", "general")
    presence_channel = None
    
    # Buscar canal de presencia
    for channel in after.guild.text_channels:
        if channel.name.lower() == presence_channel_name.lower():
            presence_channel = channel
            break
    
    # Si no se encuentra, usar el primer canal disponible
    if presence_channel is None and after.guild.text_channels:
        presence_channel = after.guild.text_channels[0]
    
    if presence_channel is None:
        return
    
    # Generar saludo de presencia
    presence_prompt = presence_cfg.get("prompt", "Saluda brevemente a {member_name} que se acaba de conectar. Sé breve y amigable.")
    presence_context = presence_prompt.format(member_name=after.display_name)
    
    try:
        # Generar respuesta usando el motor de IA
        saludo = await asyncio.to_thread(pensar, presence_context)
        
        # Enviar saludo al canal
        await presence_channel.send(f"👋 {after.mention} {saludo}")
        
        # Registrar en el log
        logger.info(f"🔄 [DISCORD] Usuario {after.name} ({after.id}) conectado en {after.guild.name}")
        
        # Actualizar timestamp para evitar spam
        on_member_update._last_greetings[last_greeting_key] = current_time
        
        # Registrar interacción en la base de datos
        db_instance = get_db_for_server(after.guild)
        await asyncio.to_thread(
            db_instance.registrar_interaccion,
            after.id,
            after.name,
            "PRESENCIA",
            f"Usuario pasó de offline a online",
            presence_channel.id,
            after.guild.id,
            metadata={"saludo": saludo}
        )
        
    except Exception as e:
        logger.error(f"❌ [DISCORD] Error al saludar presencia de {after.name}: {e}")
        # Saludo de emergencia si falla la IA
        fallback_msg = presence_cfg.get("fallback", "¡Bienvenido de vuelta!")
        await presence_channel.send(f"👋 {after.mention} {fallback_msg}")


async def _cmd_insulta(ctx, obj=""):
    target = obj if obj else ctx.author.mention

    if "@everyone" in target or "@here" in target:
        prompt = _insult_cfg.get("prompt_everyone", "Lanza un insulto breve a TODO EL MUNDO, maximo 1 frase")
    else:
        prompt = _insult_cfg.get("prompt_target", "Lanza un insulto breve a una persona especifica, maximo 1 frase")

    res = await asyncio.to_thread(pensar, prompt)
    await ctx.send(f"{target} {res}")

# Registrar el comando dinámicamente con formato estándar
# Siempre usar formato !insulta[nombre]
insulta_command_name = f"insulta{personality_name}"
bot.command(name=insulta_command_name)(_cmd_insulta)
logger.info(f"🤖 [DISCORD] Comando insulto registrado: {insulta_command_name}")


# --- COMANDOS CONDICIONALES POR ROL ACTIVADO ---

def register_role_commands():
    """Registra comandos solo si el rol correspondiente está activado."""
    import os
    
    # Función helper para verificar si un rol está activado
    def is_role_enabled(role_name):
        # Prioridad a variables de entorno
        env_var = os.getenv(f"{role_name.upper()}_ENABLED", "").lower()
        if env_var:
            return env_var == "true"
        # Fallback a configuración JSON
        return agent_config.get("roles", {}).get(role_name, {}).get("enabled", False)
    
    # Lista de roles a verificar
    roles_to_check = ["vigia_noticias", "buscador_tesoros", "pedir_oro", "buscar_anillo"]
    
    for role_name in roles_to_check:
        if not is_role_enabled(role_name):
            continue
            
        logger.info(f"🎭 [DISCORD] Registrando comandos para rol activado: {role_name}")
        
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
            @bot.command(name="acusaranilo")
            async def cmd_acusar_anillo(ctx, target: str = ""):
                if not target:
                    await ctx.send("❌ Debes mencionar a alguien para acusar. Ejemplo: !acusaranilo @usuario")
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

# Registrar comandos condicionales
register_role_commands()


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.author.bot:
        return  # Ignorar mensajes de otros bots para evitar bucles
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

bot.run(get_discord_token())
