"""
Comandos de Discord para el Trilero (subrol limosna + bote).
Registra: !trilero, !bote
"""

import asyncio
import discord
from datetime import datetime
from agent_logging import get_logger
from discord_utils import is_admin, send_dm_or_channel

logger = get_logger('trilero_discord')

# Flags de disponibilidad
try:
    from roles.trilero.subroles.limosna.db_limosna import get_limosna_db_instance
    LIMOSNA_DB_AVAILABLE = True
except ImportError:
    LIMOSNA_DB_AVAILABLE = False
    get_limosna_db_instance = None

try:
    from roles.trilero.subroles.bote.db_bote import get_bote_db_instance
    BOTE_DB_AVAILABLE = True
except ImportError:
    BOTE_DB_AVAILABLE = False
    get_bote_db_instance = None

try:
    from roles.trilero.subroles.bote.bote import procesar_jugada
    BOTE_AVAILABLE = True
except ImportError:
    BOTE_AVAILABLE = False
    procesar_jugada = None

try:
    from roles.banquero.db_role_banquero import get_banquero_db_instance
    BANQUERO_DB_AVAILABLE = True
except ImportError:
    BANQUERO_DB_AVAILABLE = False
    get_banquero_db_instance = None


def _get_limosna_db(guild):
    if not LIMOSNA_DB_AVAILABLE or get_limosna_db_instance is None:
        return None
    from discord_utils import get_server_name
    return get_limosna_db_instance(get_server_name(guild))


def register_trilero_commands(bot, personality, agent_config):
    """Registra comandos del trilero con subrol limosna y bote (idempotente)."""

    # --- !trilero ---
    if LIMOSNA_DB_AVAILABLE and bot.get_command("trilero") is None:
        @bot.command(name="trilero")
        async def cmd_trilero(ctx, *args):
            """Comando principal del trilero - gestiona el subrol limosna."""
            if not LIMOSNA_DB_AVAILABLE:
                await ctx.send("❌ El sistema del trilero no está disponible en este servidor.")
                return

            if not args:
                await ctx.send("❌ Debes especificar una acción. Usa `!trilero ayuda` para ver los comandos disponibles.")
                return

            subcommand = args[0].lower()
            subargs = args[1:] if len(args) > 1 else []

            if subcommand == "limosna":
                await _cmd_trilero_limosna(ctx, subargs)
            elif subcommand == "ayuda":
                await _cmd_trilero_ayuda(ctx)
            else:
                await ctx.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!trilero ayuda` para ver ayuda.")

        logger.info("🎭 Comando trilero registrado")
    elif not LIMOSNA_DB_AVAILABLE:
        logger.info("🎭 Base de datos de limosna no disponible, omitiendo registro del trilero")

    # --- !bote ---
    if BOTE_AVAILABLE and BOTE_DB_AVAILABLE and BANQUERO_DB_AVAILABLE:
        if bot.get_command("bote") is None:
            @bot.command(name="bote")
            async def cmd_bote(ctx, *args):
                """Comando principal del juego del Bote."""
                if not ctx.guild:
                    await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
                    return

                if not BOTE_AVAILABLE or not BOTE_DB_AVAILABLE or not BANQUERO_DB_AVAILABLE:
                    await ctx.send("❌ El juego del Bote no está disponible en este servidor.")
                    return

                if not args:
                    await _cmd_bote_ayuda(ctx, personality)
                    return

                subcommand = args[0].lower()
                subargs = args[1:] if len(args) > 1 else []

                dispatch = {
                    "jugar": lambda: _cmd_bote_jugar(ctx),
                    "ayuda": lambda: _cmd_bote_ayuda(ctx, personality),
                    "saldo": lambda: _cmd_bote_saldo(ctx, personality),
                    "stats": lambda: _cmd_bote_stats(ctx),
                    "ranking": lambda: _cmd_bote_ranking(ctx),
                    "historial": lambda: _cmd_bote_historial(ctx),
                    "config": lambda: _cmd_bote_config(ctx, subargs),
                }

                handler = dispatch.get(subcommand)
                if handler:
                    await handler()
                else:
                    await ctx.send(f"❌ Subcomando `{subcommand}` no reconocido. Usa `!bote ayuda` para ver ayuda.")

            logger.info("🎲 Comando bote registrado")
    else:
        logger.warning("🎲 Sistema del bote no disponible completamente - omitiendo registro")

    logger.info("🎭 Comandos del trilero registrados exitosamente")


# --- SUBCOMANDOS TRILERO LIMOSNA ---

async def _cmd_trilero_limosna(ctx, args):
    """Gestiona el subrol limosna."""
    if not args:
        await ctx.send("❌ Debes especificar una acción. Usa `!trilero limosna on/off` o `!trilero limosna frecuencia <horas>`.")
        return

    action = args[0].lower()
    if action in ["on", "off"]:
        await _cmd_trilero_limosna_toggle(ctx, action)
    elif action == "frecuencia":
        await _cmd_trilero_limosna_frecuencia(ctx, args[1:])
    elif action == "estado":
        await _cmd_trilero_limosna_estado(ctx)
    else:
        await ctx.send(f"❌ Acción `{action}` no reconocida. Usa `on`, `off`, `frecuencia` o `estado`.")


async def _cmd_trilero_limosna_toggle(ctx, action):
    """Activa o desactiva el subrol limosna (solo administradores)."""
    if not ctx.guild:
        await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
        return
    if not is_admin(ctx):
        await ctx.send("❌ Solo los administradores pueden activar/desactivar limosna en el servidor.")
        return

    db_limosna = _get_limosna_db(ctx.guild)
    if not db_limosna:
        await ctx.send("❌ Error al acceder a la base de datos del trilero.")
        return

    server_id = str(ctx.guild.id)
    server_name = ctx.guild.name
    server_user_id = f"server_{server_id}"

    if action == "on":
        if db_limosna.agregar_suscripcion(server_user_id, server_name, server_id):
            await ctx.send(f"🙏 **Limosna activada para el servidor** - Ahora todos los miembros recibirán peticiones de limosna periódicamente.")
            logger.info(f"🎭 {ctx.author.name} activó limosna para {server_name}")
        else:
            await ctx.send("❌ Error al activar limosna. Inténtalo de nuevo.")
    else:
        if db_limosna.eliminar_suscripcion(server_user_id, server_id):
            await ctx.send(f"🚫 **Limosna desactivada para el servidor** - Ya no se enviarán peticiones de limosna.")
            logger.info(f"🎭 {ctx.author.name} desactivó limosna para {server_name}")
        else:
            await ctx.send("❌ Error al desactivar limosna. Inténtalo de nuevo.")


async def _cmd_trilero_limosna_frecuencia(ctx, args):
    """Ajusta la frecuencia de envío de limosna (solo administradores)."""
    if not ctx.guild:
        await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
        return
    if not is_admin(ctx):
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
        await ctx.send(f"⏰ **Frecuencia ajustada** - Las peticiones de limosna se enviarán cada {horas} horas.")
        logger.info(f"🎭 {ctx.author.name} ajustó frecuencia de limosna a {horas} horas en {ctx.guild.name}")
    except ValueError:
        await ctx.send("❌ Debes especificar un número válido de horas.")


async def _cmd_trilero_limosna_estado(ctx):
    """Muestra el estado actual de limosna en el servidor."""
    if not ctx.guild:
        await ctx.send("❌ Este comando solo funciona en servidores, no por mensaje privado.")
        return

    db_limosna = _get_limosna_db(ctx.guild)
    if not db_limosna:
        await ctx.send("❌ Error al acceder a la base de datos del trilero.")
        return

    server_id = str(ctx.guild.id)
    server_user_id = f"server_{server_id}"
    is_active = db_limosna.esta_suscrito(server_user_id, server_id)

    try:
        count_dm = db_limosna.contar_peticiones_tipo_ultimo_dia("LIMOSNA_DM", server_id)
        count_public = db_limosna.contar_peticiones_tipo_ultimo_dia("LIMOSNA_PUBLICO", server_id)
    except Exception:
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


async def _cmd_trilero_ayuda(ctx):
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

    await send_dm_or_channel(ctx, ayuda_msg, "📩 Ayuda del trilero enviada por mensaje privado.")


# --- SUBCOMANDOS BOTE ---

async def _cmd_bote_jugar(ctx):
    """Realiza una tirada de dados en el juego del bote."""
    if not ctx.guild:
        await ctx.send("❌ Este comando solo funciona en servidores.")
        return
    try:
        db_banquero = get_banquero_db_instance(ctx.guild.name)
        db_bote = get_bote_db_instance(ctx.guild.name)
        if not db_banquero or not db_bote:
            await ctx.send("❌ Error al acceder a las bases de datos del juego.")
            return

        try:
            db_banquero.obtener_saldo("bote_banca", str(ctx.guild.id))
        except Exception:
            await ctx.send("❌ El rol Banquero debe estar activo para jugar al Bote.")
            return

        resultado = await asyncio.to_thread(procesar_jugada,
            str(ctx.author.id), ctx.author.display_name,
            str(ctx.guild.id), ctx.guild.name, None
        )

        if resultado["success"]:
            await ctx.send(resultado["mensaje"])
            logger.info(f"🎲 {ctx.author.name} jugó en {ctx.guild.name} - Premio: {resultado.get('premio', 0)}")
        else:
            await ctx.send(f"❌ {resultado['message']}")
    except Exception as e:
        logger.exception(f"Error en cmd_bote_jugar: {e}")
        await ctx.send("❌ Error al procesar la jugada. Inténtalo de nuevo.")


async def _cmd_bote_ayuda(ctx, personality):
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

    await send_dm_or_channel(ctx, ayuda_msg, "📩 Ayuda del Bote enviada por mensaje privado.")


async def _cmd_bote_saldo(ctx, personality):
    """Muestra el saldo actual del bote."""
    if not BANQUERO_DB_AVAILABLE or not BOTE_DB_AVAILABLE:
        await ctx.send("❌ El sistema del bote no está disponible en este servidor.")
        return

    try:
        saldo_messages = personality.get("discord", {}).get("bote_saldo_messages", {})
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
        db_bote = get_bote_db_instance(ctx.guild.name)
        config = db_bote.obtener_configuracion_servidor(str(ctx.guild.id))
        apuesta_fija = config.get("apuesta_fija", 10)

        saldo_msg = saldo_messages.get("titulo", "💰 **ESTADO DEL BOTE - {servidor}** 💰\n\n").format(servidor=ctx.guild.name.upper())
        saldo_msg += saldo_messages.get("saldo_actual", "🎲 **Saldo actual del bote:** {saldo:,} monedas\n").format(saldo=saldo_bote)
        saldo_msg += saldo_messages.get("apuesta_fija", "💎 **Apuesta fija:** {apuesta:,} monedas\n").format(apuesta=apuesta_fija)
        saldo_msg += saldo_messages.get("jugadas_posibles", "🎯 **Jugadas posibles:** {jugadas}\n\n").format(jugadas=saldo_bote // apuesta_fija if apuesta_fija > 0 else 0)

        if saldo_bote >= 100:
            saldo_msg += saldo_messages.get("bote_grande", "🔥 **¡EL BOTE ESTÁ GRANDE!** 🔥\n").format(saldo=saldo_bote)
        elif saldo_bote >= 50:
            saldo_msg += saldo_messages.get("bote_mediano", "📈 **Bote mediano** - Bueno para jugar\n")
        else:
            saldo_msg += saldo_messages.get("bote_pequeno", "📉 **Bote pequeño** - Sigue creciendo\n")

        saldo_msg += saldo_messages.get("usar_comando", "\n💡 Usa `!bote jugar` para intentar tu suerte!")
        await ctx.author.send(saldo_msg)
        await ctx.send(saldo_messages.get("enviado_privado", "📩 Saldo del bote enviado por mensaje privado."))
    except Exception as e:
        logger.exception(f"Error en cmd_bote_saldo: {e}")
        await ctx.send("❌ Error al obtener el saldo del bote.")


async def _cmd_bote_stats(ctx):
    """Muestra estadísticas personales del jugador."""
    if not ctx.guild:
        await ctx.send("❌ Este comando solo funciona en servidores.")
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


async def _cmd_bote_ranking(ctx):
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


async def _cmd_bote_historial(ctx):
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
            try:
                dt = datetime.fromisoformat(fecha.replace('Z', '+00:00'))
                fecha_formateada = dt.strftime("%d/%m %H:%M")
            except Exception:
                fecha_formateada = fecha[:16]
            premio_emoji = "🎉" if premio > 0 else "😅"
            historial_msg += f"👤 **{nombre}** | {fecha_formateada}\n"
            historial_msg += f"   🎲 {dados} → {combinacion}\n"
            historial_msg += f"   {premio_emoji} Premio: {premio:,} monedas\n\n"

        await ctx.send(historial_msg)
    except Exception as e:
        logger.exception(f"Error en cmd_bote_historial: {e}")
        await ctx.send("❌ Error al obtener el historial.")


async def _cmd_bote_config(ctx, args):
    """Configura parámetros del bote (solo administradores)."""
    if not ctx.guild:
        await ctx.send("❌ Este comando solo funciona en servidores.")
        return
    if not is_admin(ctx):
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
                    logger.info(f"🎲 {ctx.author.name} configuró apuesta a {cantidad} en {ctx.guild.name}")
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
                logger.info(f"🎲 {ctx.author.name} {estado_msg} anuncios en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al configurar los anuncios.")
        else:
            await ctx.send("❌ Parámetro no reconocido. Usa `apuesta` o `anuncios`.")
    except Exception as e:
        logger.exception(f"Error en cmd_bote_config: {e}")
        await ctx.send("❌ Error al configurar el bote.")
