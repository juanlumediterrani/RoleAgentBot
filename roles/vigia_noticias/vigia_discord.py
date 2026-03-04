"""
Comandos de Discord para el Vigía de Noticias.
Registra: !vigia, !novigia, !avisanoticias, !noavisanoticias, !vigiaayuda, !vigiacanalayuda, !vigiacanal
"""

import discord
from agent_logging import get_logger
from discord_utils import send_dm_or_channel

logger = get_logger('vigia_discord')

# Flags de disponibilidad (se evalúan al importar)
try:
    from roles.vigia_noticias.vigia_commands import VigiaCommands
    from roles.vigia_noticias.db_role_vigia import get_vigia_db_instance
    VIGIA_COMMANDS_AVAILABLE = True
except ImportError as e:
    VIGIA_COMMANDS_AVAILABLE = False
    VigiaCommands = None
    get_vigia_db_instance = None
    logger.warning(f"Dependencias del Vigía no disponibles: {e}")

try:
    from roles.vigia_noticias.vigia_messages import get_message
except ImportError:
    def get_message(key, **kwargs):
        return "✅ Te he enviado la ayuda por mensaje privado 📩"


def _get_vigia_db(guild):
    """Obtiene instancia de BD del vigía para un servidor."""
    if not VIGIA_COMMANDS_AVAILABLE or get_vigia_db_instance is None:
        return None
    from discord_utils import get_server_name
    server_name = get_server_name(guild)
    return get_vigia_db_instance(server_name)


def register_vigia_commands(bot, personality, agent_config):
    """Registra todos los comandos del Vigía de Noticias (idempotente)."""

    if not VIGIA_COMMANDS_AVAILABLE:
        logger.warning("Vigía no disponible, omitiendo registro de comandos")
        return

    vigia_commands = VigiaCommands(bot)

    # --- !vigia ---
    if bot.get_command("vigia") is None:
        @bot.command(name="vigia")
        async def cmd_vigia(ctx, *args):
            """Comando principal del Vigía de Noticias (funciona por DM)."""
            db_vigia = _get_vigia_db(ctx.guild)
            if not db_vigia:
                await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                return

            if not args:
                await ctx.author.send("📡 **Vigía de Noticias** - Usa `!vigiaayuda` para ver todos los comandos disponibles.")
                if ctx.guild:
                    await ctx.send("📩 Ayuda enviada por mensaje privado.")
                return

            subcommand = args[0].lower()
            subargs = args[1:] if len(args) > 1 else []

            dispatch = {
                "feeds": vigia_commands.cmd_feeds,
                "categorias": vigia_commands.cmd_categorias,
                "estado": vigia_commands.cmd_estado,
                "suscribir": vigia_commands.cmd_suscribir,
                "cancelar": vigia_commands.cmd_cancelar,
                "general": vigia_commands.cmd_general_suscribir,
                "palabras": vigia_commands.cmd_palabras_suscribir,
                "premisas": vigia_commands.cmd_premisas,
                "mod": vigia_commands.cmd_premisas_mod,
                "reset": vigia_commands.cmd_reset,
            }

            handler = dispatch.get(subcommand)
            if handler:
                try:
                    await handler(ctx, subargs)
                except Exception as e:
                    logger.error(f"Error en comando vigia {subcommand}: {e}")
                    await ctx.author.send("❌ Error al ejecutar el comando. Inténtalo de nuevo.")
                    if ctx.guild:
                        await ctx.send("📩 Error enviado por mensaje privado.")
            else:
                await ctx.author.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!vigiaayuda` para ver ayuda.")
                if ctx.guild:
                    await ctx.send("📩 Ayuda enviada por mensaje privado.")

        logger.info("📡 Comando vigia registrado")

    # --- !novigia ---
    if bot.get_command("novigia") is None:
        @bot.command(name="novigia")
        async def cmd_no_vigia(ctx):
            """Desactiva el rol Vigía de Noticias (funciona por DM)."""
            db_vigia = _get_vigia_db(ctx.guild)
            if not db_vigia:
                await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                return

            usuario_id = str(ctx.author.id)
            if not db_vigia.esta_suscrito(usuario_id):
                await ctx.author.send("🛡️ No estás suscrito a las alertas del Vigía de la Torre.")
                if ctx.guild:
                    await ctx.send("📩 Respuesta enviada por mensaje privado.")
                return

            if db_vigia.eliminar_suscripcion(usuario_id):
                await ctx.author.send("✅ Te has desuscrito de las alertas del Vigía de la Torre. Ya no recibirás noticias críticas.")
                if ctx.guild:
                    await ctx.send("📩 Respuesta enviada por mensaje privado.")
                logger.info(f"📡 {ctx.author.name} ({usuario_id}) se desuscribió de las alertas")
            else:
                await ctx.send("❌ Error al desuscribirte de las alertas. Inténtalo de nuevo.")

        logger.info("📡 Comando novigia registrado")

    # --- !avisanoticias ---
    if bot.get_command("avisanoticias") is None:
        @bot.command(name="avisanoticias")
        async def cmd_avisa_noticias(ctx):
            """Alias para suscribirse a alertas críticas del Vigía (funciona por DM)."""
            db_vigia = _get_vigia_db(ctx.guild)
            if not db_vigia:
                await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                return

            usuario_id = str(ctx.author.id)
            usuario_nombre = ctx.author.name

            if db_vigia.esta_suscrito(usuario_id):
                await ctx.author.send("🛡️ Ya estás suscrito a las alertas del Vigía de la Torre.")
                if ctx.guild:
                    await ctx.send("📩 Respuesta enviada por mensaje privado.")
                return

            if db_vigia.agregar_suscripcion(usuario_id, usuario_nombre):
                await ctx.author.send("✅ Te has suscrito a las alertas del Vigía de la Torre. Recibirás noticias críticas cuando ocurran.")
                await ctx.author.send("💡 Usa `!vigiaayuda` para ver todos los comandos disponibles del Vigía.")
                if ctx.guild:
                    await ctx.send("📩 Respuesta enviada por mensaje privado.")
                logger.info(f"📡 {usuario_nombre} ({usuario_id}) se suscribió a las alertas")
            else:
                await ctx.send("❌ Error al suscribirte a las alertas. Inténtalo de nuevo.")

        logger.info("📡 Comando avisanoticias registrado")

    # --- !noavisanoticias ---
    if bot.get_command("noavisanoticias") is None:
        @bot.command(name="noavisanoticias")
        async def cmd_no_avisa_noticias(ctx):
            """Alias para desuscribirse de alertas críticas del Vigía (funciona por DM)."""
            db_vigia = _get_vigia_db(ctx.guild)
            if not db_vigia:
                await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                return

            usuario_id = str(ctx.author.id)
            usuario_nombre = ctx.author.name

            if not db_vigia.esta_suscrito(usuario_id):
                await ctx.author.send("🛡️ No estás suscrito a las alertas del Vigía de la Torre.")
                if ctx.guild:
                    await ctx.send("📩 Respuesta enviada por mensaje privado.")
                return

            if db_vigia.eliminar_suscripcion(usuario_id):
                await ctx.author.send("✅ Te has desuscrito de las alertas del Vigía de la Torre. Ya no recibirás noticias críticas.")
                await ctx.author.send("💡 Usa `!vigiaayuda` para ver todos los comandos disponibles del Vigía.")
                if ctx.guild:
                    await ctx.send("📩 Respuesta enviada por mensaje privado.")
                logger.info(f"📡 {usuario_nombre} ({usuario_id}) se desuscribió de las alertas")
            else:
                await ctx.send("❌ Error al desuscribirte de las alertas. Inténtalo de nuevo.")

        logger.info("📡 Comando noavisanoticias registrado")

    # --- !vigiaayuda ---
    if bot.get_command("vigiaayuda") is None:
        @bot.command(name="vigiaayuda")
        async def cmd_vigia_ayuda(ctx):
            """Muestra ayuda específica para el Vigía de Noticias (usuarios)."""
            # Prevenir duplicación
            message_id = f"{ctx.message.id}_{ctx.author.id}"
            if hasattr(bot, '_processed_ayuda_messages'):
                if message_id in bot._processed_ayuda_messages:
                    return
            else:
                bot._processed_ayuda_messages = set()
            bot._processed_ayuda_messages.add(message_id)

            ayuda_vigia = _build_vigia_help_text()

            confirm_msg = "📩 Ayuda enviada por mensaje privado."
            await send_dm_or_channel(ctx, ayuda_vigia, confirm_msg)

        logger.info("📡 Comando vigiaayuda registrado")

    # --- !vigiacanalayuda ---
    if bot.get_command("vigiacanalayuda") is None:
        @bot.command(name="vigiacanalayuda")
        async def cmd_vigia_canal_ayuda(ctx):
            """Muestra ayuda específica para el Vigía de Noticias en canales (solo admins)."""
            if not ctx.guild:
                await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
                return
            if not ctx.author.guild_permissions.administrator:
                await ctx.send("❌ Solo administradores pueden usar este comando.")
                return

            db_vigia = _get_vigia_db(ctx.guild)
            if not db_vigia:
                await ctx.send("❌ Error al acceder a la base de datos del Vigía.")
                return

            ayuda_msg = _build_vigia_canal_help_text()
            await ctx.send(ayuda_msg[:2000])

        logger.info("📡 Comando vigiacanalayuda registrado")

    # --- !vigiacanal ---
    if bot.get_command("vigiacanal") is None:
        @bot.command(name="vigiacanal")
        async def cmd_vigia_canal(ctx, *args):
            """Comandos del Vigía para el canal (solo en servidor)."""
            if ctx.guild is None:
                await ctx.send("❌ Este comando solo se puede usar en un servidor, no en mensajes directos.")
                return
            if not args:
                await ctx.send("❌ Debes especificar una acción. Usa `!vigiacanalayuda` para ver ayuda.")
                return

            subcommand = args[0].lower()
            subargs = args[1:] if len(args) > 1 else []

            dispatch = {
                "suscribir": vigia_commands.cmd_canal_suscribir,
                "cancelar": vigia_commands.cmd_canal_cancelar,
                "estado": vigia_commands.cmd_canal_estado,
                "palabras": vigia_commands.cmd_canal_palabras,
                "premisas": vigia_commands.cmd_canal_premisas,
            }

            handler = dispatch.get(subcommand)
            if handler:
                try:
                    await handler(ctx, subargs)
                except Exception as e:
                    logger.error(f"Error en comando vigiacanal {subcommand}: {e}")
                    await ctx.send("❌ Error al ejecutar el comando. Inténtalo de nuevo.")
            elif subcommand == "general":
                try:
                    if len(subargs) > 0 and subargs[0].lower() == "cancelar":
                        await vigia_commands.cmd_canal_general_cancelar(ctx, subargs[1:] if len(subargs) > 1 else [])
                    else:
                        await vigia_commands.cmd_canal_general_suscribir(ctx, subargs)
                except Exception as e:
                    logger.error(f"Error en comando vigiacanal general: {e}")
                    await ctx.send("❌ Error al ejecutar el comando. Inténtalo de nuevo.")
            else:
                await ctx.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!vigiacanalayuda` para ver ayuda.")

        logger.info("📡 Comando vigiacanal registrado")

    logger.info("📡 Todos los comandos del Vigía registrados")


def _build_vigia_help_text():
    """Construye el texto de ayuda del Vigía para usuarios."""
    ayuda = "📡 **Ayuda del Vigía de Noticias - Usuarios** 📡\n\n"
    ayuda += "⚠️ **IMPORTANTE:** Solo puedes tener **UN TIPO** de suscripción activa a la vez\n"
    ayuda += "• Si te suscribes a un nuevo tipo, se cancelará automáticamente el anterior\n\n"
    ayuda += "🎯 **Comandos Principales:**\n"
    ayuda += "• `!vigia feeds` - Lista feeds RSS disponibles\n"
    ayuda += "• `!vigia categorias` - Muestra categorías activas\n"
    ayuda += "• `!vigia estado` - Tu tipo de suscripción activa\n\n"
    ayuda += "📰 **Suscripciones Planas:**\n"
    ayuda += "• `!vigia suscribir <categoría>` - Todas las noticias con opinión\n"
    ayuda += "• **Ejemplo:** `!vigia suscribir economia`\n\n"
    ayuda += "🔍 **Palabras Clave:**\n"
    ayuda += "• `!vigia palabras \"palabra1,palabra2\"` - Suscripción directa con palabras\n"
    ayuda += "• `!vigia palabras add <palabra>` - Añadir palabra a tu lista\n"
    ayuda += "• `!vigia palabras list` - Ver todas tus palabras clave\n"
    ayuda += "• `!vigia palabras mod <num> \"nueva\"` - Modificar palabra específica\n"
    ayuda += "• `!vigia palabras suscribir <categoría>` - Usar palabras ya configuradas\n"
    ayuda += "• `!vigia palabras suscripciones` - Ver suscripciones con palabras\n"
    ayuda += "• `!vigia palabras desuscribir <categoría>` - Cancelar suscripción\n"
    ayuda += "• **Ejemplo:** `!vigia palabras \"bitcoin,crypto\"`\n\n"
    ayuda += "🤖 **Suscripciones con IA:**\n"
    ayuda += "• `!vigia general <categoría>` - Noticias críticas según tus premisas\n"
    ayuda += "• `!vigia general cancelar <categoría>` - Cancelar suscripción con IA\n"
    ayuda += "• **Requiere:** Configurar premisas primero (`!vigia premisas add`)\n"
    ayuda += "• **Ejemplo:** `!vigia general internacional`\n\n"
    ayuda += "🎯 **Gestión de Premisas:**\n"
    ayuda += "• `!vigia premisas` / `!vigia premisas list` - Ver tus premisas\n"
    ayuda += "• `!vigia premisas add \"texto\"` - Añadir premisa (máx 7)\n"
    ayuda += "• `!vigia mod <num> \"nueva premisa\"` - Modificar premisa #<num>\n\n"
    ayuda += "🔄 **Reset de Suscripciones:**\n"
    ayuda += "• `!vigia reset` - Ver qué tipo de suscripción tienes activa\n"
    ayuda += "• `!vigia reset confirmar` - Eliminar TODAS tus suscripciones\n"
    ayuda += "• **Úsalo para cambiar de tipo de suscripción**\n\n"
    ayuda += "📊 **Estado y Control:**\n"
    ayuda += "• `!vigia estado` - Ver tu tipo de suscripción activa\n"
    ayuda += "• `!vigia cancelar <categoría>` - Cancelar suscripción plana\n\n"
    ayuda += "📂 **Categorías:** economia, internacional, tecnologia, sociedad, politica\n\n"
    ayuda += "💡 **Ejemplos Rápidos:**\n"
    ayuda += "```\n!vigia palabras add bitcoin           # Añadir palabra\n!vigia palabras list                  # Ver palabras\n!vigia palabras suscribir economia   # Suscribir con palabras\n!vigia reset                         # Ver tipo activo\n!vigia reset confirmar               # Limpiar todo\n!vigia general internacional         # Suscribir con IA\n```\n\n"
    ayuda += "📢 **Para Admins:** Usa `!vigiacanalayuda` para comandos de canal"
    return ayuda


def _build_vigia_canal_help_text():
    """Construye el texto de ayuda del Vigía para canales (admins)."""
    ayuda = "📡 **AYUDA DEL VIGÍA - COMANDOS DE CANAL** 📡\n\n"
    ayuda += "🔧 **Comandos de Administración:**\n"
    ayuda += "```\n"
    ayuda += "!vigiacanal suscribir <feed_id>     # Suscribir canal a un feed\n"
    ayuda += "!vigiacanal cancelar <feed_id>     # Cancelar suscripción del canal\n"
    ayuda += "!vigiacanal estado                 # Ver estado de suscripciones del canal\n"
    ayuda += "!vigiacanal palabras add <palabra> # Añadir palabra clave al canal\n"
    ayuda += "!vigiacanal palabras del <palabra>  # Eliminar palabra clave del canal\n"
    ayuda += "!vigiacanal premisas add <texto>    # Añadir premisa al canal\n"
    ayuda += "!vigiacanal premisas del <id>       # Eliminar premisa del canal\n"
    ayuda += "!vigiacanal general <categoria> [feed_id]     # Suscribir canal con IA\n"
    ayuda += "!vigiacanal general cancelar <categoria> [feed_id]  # Cancelar suscripción IA\n"
    ayuda += "```\n\n"
    ayuda += "💡 **Para ver todos los feeds disponibles:** `!vigia feeds`\n"
    ayuda += "📋 **Para ver categorías:** `!vigia categorias`\n\n"
    ayuda += "⚠️ **IMPORTANTE - Exclusión Mutua:**\n"
    ayuda += "• Un canal puede tener **SOLO UN TIPO** de suscripción activa\n"
    ayuda += "• Al cambiar de tipo, se cancela automáticamente la anterior\n"
    ayuda += "• **Tipos:** Plana (todas), Palabras (filtradas), IA (críticas)\n"
    ayuda += "• Solo administradores pueden gestionar suscripciones de canal"
    return ayuda
