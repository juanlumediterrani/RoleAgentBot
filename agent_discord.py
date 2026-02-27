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

# Verificar si el rol vigia_noticias está activado en la configuración
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


async def _cmd_insulta(ctx, obj=""):
    target = obj if obj else ctx.author.mention

    if "@everyone" in target or "@here" in target:
        prompt = _insult_cfg.get("prompt_everyone", "Lanza un insulto breve a TODO EL MUNDO, maximo 1 frase")
    else:
        prompt = _insult_cfg.get("prompt_target", "Lanza un insulto breve a una persona especifica, maximo 1 frase")

    res = await asyncio.to_thread(pensar, prompt)
    await ctx.send(f"{target} {res}")

# Registrar el comando dinámicamente con el nombre definido en la personalidad
# Inyectar el nombre de la personalidad en minúsculas si no está ya especificado
if _insult_name == "insulta":
    # Si el nombre por defecto es "insulta", crear uno dinámico
    dynamic_command_name = f"insulta{_personality_name}"
    bot.command(name=dynamic_command_name)(_cmd_insulta)
    logger.info(f"🤖 [DISCORD] Comando insulto dinámico registrado: {dynamic_command_name}")
else:
    # Si ya tiene un nombre personalizado, usarlo
    bot.command(name=_insult_name)(_cmd_insulta)
    logger.info(f"🤖 [DISCORD] Comando insulto personalizado registrado: {_insult_name}")


# --- COMANDOS DEL VIGÍA (atendidos por la personalidad activa) ---

if VIGIA_AVAILABLE:
    @bot.command(name="vigia_suscribir")
    async def vigia_suscribir(ctx):
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

    @bot.command(name="vigia_desuscribir")
    async def vigia_desuscribir(ctx):
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

    logger.info("🤖 [DISCORD] Comandos del Vigía registrados: vigia_suscribir, vigia_desuscribir")
else:
    if not module_available:
        logger.warning("🤖 [DISCORD] Módulo del Vigía no disponible, comandos de suscripción desactivados")
    elif not vigia_role_enabled:
        logger.info("🤖 [DISCORD] Rol Vigía desactivado en configuración, comandos de suscripción desactivados")
    else:
        logger.warning("🤖 [DISCORD] Módulo del Vigía no disponible, comandos de suscripción desactivados")


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
