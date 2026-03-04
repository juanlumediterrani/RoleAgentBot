"""
Comandos de Discord para el Banquero.
Registra: !banquero (saldo, tae, bono, ayuda)
"""

import discord
from agent_logging import get_logger
from discord_utils import is_admin, send_embed_dm_or_channel

logger = get_logger('banquero_discord')

# Flags de disponibilidad
try:
    from roles.banquero.db_role_banquero import DatabaseRoleBanquero, get_banquero_db_instance
    BANQUERO_DB_AVAILABLE = True
except ImportError:
    BANQUERO_DB_AVAILABLE = False
    get_banquero_db_instance = None


def _get_banquero_db(guild):
    """Obtiene instancia de BD del banquero para un servidor."""
    if not BANQUERO_DB_AVAILABLE or get_banquero_db_instance is None:
        return None
    return get_banquero_db_instance(guild.name)


def _get_banquero_msgs(personality):
    """Obtiene mensajes personalizados del banquero."""
    return personality.get("discord", {}).get("banquero_messages", {})


def _build_banquero_help_embed(personality):
    """Construye el embed de ayuda del banquero (reutilizado en ayuda y sin args)."""
    msgs = _get_banquero_msgs(personality)
    embed = discord.Embed(
        title=msgs.get("ayuda_title", "💰 Banquero - Ayuda"),
        description=msgs.get("ayuda_description", "Comandos disponibles para gestionar la economía del servidor"),
        color=discord.Color.gold()
    )
    embed.add_field(
        name=msgs.get("ver_saldo", "💎 Ver Saldo"),
        value=msgs.get("ver_saldo_desc", "`!banquero saldo`\nMuestra tu saldo actual de oro y transacciones recientes.\nLas cuentas nuevas reciben bono de apertura automáticamente."),
        inline=False
    )
    embed.add_field(
        name=msgs.get("configurar_tae", "🏦 Configurar TAE (Admins)"),
        value=msgs.get("configurar_tae_desc", "`!banquero tae <cantidad>`\nEstablece la TAE diaria (0-1000 monedas).\n`!banquero tae` - Ver configuración actual."),
        inline=False
    )
    embed.add_field(
        name=msgs.get("configurar_bono", "🎁 Configurar Bono de Apertura (Admins)"),
        value=msgs.get("configurar_bono_desc", "`!banquero bono <cantidad>`\nEstablece el bono para nuevas cuentas (0-10000 monedas).\n`!banquero bono` - Ver configuración actual."),
        inline=False
    )
    embed.add_field(
        name=msgs.get("informacion", "ℹ️ Información"),
        value=msgs.get("informacion_desc", "• La TAE se distribuye automáticamente cada día a todos los usuarios con cartera.\n• Las cuentas nuevas reciben automáticamente el bono de apertura configurado.\n• Todas las transacciones quedan registradas.\n• Solo los administradores pueden configurar la TAE y el bono de apertura."),
        inline=False
    )
    embed.set_footer(text=msgs.get("ayuda_footer", "💼 Banquero - Gestión Económica del Servidor"))
    return embed


def register_banquero_commands(bot, personality, agent_config):
    """Registra comandos del Banquero (idempotente)."""

    if not BANQUERO_DB_AVAILABLE:
        logger.warning("💰 Base de datos del banquero no disponible, omitiendo registro de comandos")
        return

    if bot.get_command("banquero") is not None:
        logger.info("💰 Comandos del banquero ya registrados")
        return

    @bot.command(name="banquero")
    async def cmd_banquero(ctx, *args):
        """Comando principal del Banquero para gestión económica."""
        logger.info(f"💰 Comando banquero recibido con args: {args}")

        if not ctx.guild:
            msgs = _get_banquero_msgs(personality)
            await ctx.send(msgs.get("error_bd_banquero", "❌ Este comando solo funciona en servidores."))
            return

        try:
            db_banquero = _get_banquero_db(ctx.guild)
            if db_banquero is None:
                msgs = _get_banquero_msgs(personality)
                await ctx.send(msgs.get("error_bd_banquero", "❌ Base de datos del banquero no disponible."))
                return
        except Exception as e:
            logger.exception(f"Error obteniendo BD del banquero: {e}")
            msgs = _get_banquero_msgs(personality)
            await ctx.send(msgs.get("error_bd_banquero", "❌ Error accediendo a la base de datos del banquero."))
            return

        servidor_id = str(ctx.guild.id)
        servidor_nombre = ctx.guild.name

        # Sin argumentos o "ayuda" → mostrar ayuda
        if not args or (args and args[0].lower() == "ayuda"):
            embed = _build_banquero_help_embed(personality)
            confirm = _get_banquero_msgs(personality).get("ayuda_enviada", "📩 Ayuda del banquero enviada por mensaje privado.")
            await send_embed_dm_or_channel(ctx, embed, confirm)
            return

        subcommand = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []

        if subcommand == "saldo":
            await _cmd_banquero_saldo(ctx, db_banquero, servidor_id, servidor_nombre, personality)
        elif subcommand == "tae":
            await _cmd_banquero_tae(ctx, db_banquero, servidor_id, servidor_nombre, subargs, personality)
        elif subcommand == "bono":
            await _cmd_banquero_bono(ctx, db_banquero, servidor_id, servidor_nombre, subargs, personality)
        else:
            msgs = _get_banquero_msgs(personality)
            await ctx.send(msgs.get("comando_no_reconocido", "❌ Subkomando '{subcommand}' no rekonocido! Usa `!banquero ayuda` para ver ayuda umano tonto!").format(subcommand=subcommand))

    logger.info("💰 Comandos del banquero registrados")


# --- SUBCOMANDOS ---

async def _cmd_banquero_saldo(ctx, db_banquero, servidor_id, servidor_nombre, personality):
    """Muestra saldo del usuario."""
    usuario_id = str(ctx.author.id)
    usuario_nombre = ctx.author.display_name

    db_banquero.crear_cartera(usuario_id, usuario_nombre, servidor_id, servidor_nombre)
    saldo = db_banquero.obtener_saldo(usuario_id, servidor_id)
    historial = db_banquero.obtener_historial_transacciones(usuario_id, servidor_id, 5)

    msgs = _get_banquero_msgs(personality)
    embed = discord.Embed(
        title=msgs.get("saldo_title", "💰 Cartera del Banquero"),
        description=msgs.get("saldo_description", "Estado de tu cartera de oro"),
        color=discord.Color.gold()
    )
    embed.add_field(name=msgs.get("saldo_actual", "💎 Saldo Actual"), value=f"{saldo:,} monedas de oro", inline=False)
    embed.add_field(name=msgs.get("titular", "👤 Titular"), value=usuario_nombre, inline=True)
    embed.add_field(name=msgs.get("banco", "🏦 Banco"), value=servidor_nombre, inline=True)

    if historial:
        historial_text = ""
        for trans in historial:
            tipo, cantidad, saldo_ant, saldo_nuevo, descripcion, fecha, admin = trans
            emoji = "📥" if cantidad > 0 else "📤"
            historial_text += f"{emoji} {cantidad:,} ({tipo})\n"
        if historial_text:
            embed.add_field(name=msgs.get("transacciones_recientes", "📊 Transacciones Recientes"), value=historial_text[:1024], inline=False)

    embed.set_footer(text=msgs.get("ayuda_footer", "💼 Banquero - Gestión Económica del Servidor"))
    embed.set_thumbnail(url=ctx.author.display_avatar.url if ctx.author.display_avatar else None)

    confirm = msgs.get("saldo_enviado", "💰 Información de tu cartera enviada por mensaje privado.")
    await send_embed_dm_or_channel(ctx, embed, confirm)


async def _cmd_banquero_tae(ctx, db_banquero, servidor_id, servidor_nombre, subargs, personality):
    """Configurar o ver TAE (solo admins)."""
    if not is_admin(ctx):
        msgs = _get_banquero_msgs(personality)
        await ctx.send(msgs.get("error_no_admin_tae", "❌ Solo los jefes orkos pueden configurar la TAE umano!"))
        return

    msgs = _get_banquero_msgs(personality)

    if not subargs:
        # Mostrar TAE actual
        tae_actual = db_banquero.obtener_tae(servidor_id)
        ultima_dist = db_banquero.obtener_ultima_distribucion(servidor_id)

        embed = discord.Embed(
            title=msgs.get("tae_config_title", "🏦 Konfiguración de TAE"),
            description=msgs.get("tae_description", "Konfiguración aktual de la Tasa Anual Ekuivalente"),
            color=discord.Color.blue()
        )
        embed.add_field(name=msgs.get("tae_actual", "💰 TAE Diaria Aktual"), value=f"{tae_actual:,} monedas", inline=True)
        embed.add_field(name=msgs.get("ultima_distribucion", "📅 Última Distribución"), value=ultima_dist[:10] if ultima_dist else "Nunca", inline=True)

        if tae_actual == 0:
            embed.add_field(name=msgs.get("tae_no_configurada", "⚠️ Estado: TAE no konfigurada"), value="\u200b", inline=False)
        else:
            embed.add_field(name=msgs.get("tae_info", "ℹ️ Info"), value=f"Kada usuario recibirá {tae_actual:,} monedas diarias", inline=False)

        embed.set_footer(text=msgs.get("tae_footer", "💼 Usa !banquero tae <cantidad> para konfigurar"))
        await ctx.send(embed=embed)
    else:
        # Establecer nueva TAE
        try:
            cantidad = int(subargs[0])
            if cantidad < 0 or cantidad > 1000:
                await ctx.send(msgs.get("error_tae_rango", "❌ La TAE debe estar entre 0 y 1000 monedas diarias!"))
                return

            admin_id = str(ctx.author.id)
            admin_nombre = ctx.author.display_name

            if db_banquero.establecer_tae(servidor_id, cantidad, admin_id, admin_nombre):
                embed = discord.Embed(
                    title=msgs.get("tae_configurada", "✅ TAE Konfigurada"),
                    description=msgs.get("tae_actualizada", "La Tasa Anual Ekuivalente ha sido aktualizada"),
                    color=discord.Color.green()
                )
                embed.add_field(name=msgs.get("nueva_tae", "💰 Nueva TAE Diaria"), value=f"{cantidad:,} monedas", inline=True)
                embed.add_field(name=msgs.get("administrador", "👤 Administrador"), value=admin_nombre, inline=True)
                embed.add_field(name=msgs.get("servidor", "🏦 Servidor"), value=servidor_nombre, inline=True)
                if cantidad > 0:
                    embed.add_field(name=msgs.get("proxima_distribucion", "ℹ️ Próxima Distribución"), value="Se distribuirá automáticamente kada día", inline=False)
                embed.set_footer(text=msgs.get("ayuda_footer", "💼 Banquero - Gestión Ekonómika"))
                await ctx.send(embed=embed)
            else:
                await ctx.send(msgs.get("error_configurar_tae", "❌ Error al konfigurar la TAE!"))
        except ValueError:
            await ctx.send(msgs.get("error_numero_invalido", "❌ Cantidad inválida! Usa número entero umano bobo!"))


async def _cmd_banquero_bono(ctx, db_banquero, servidor_id, servidor_nombre, subargs, personality):
    """Configurar o ver bono de apertura (solo admins)."""
    if not is_admin(ctx):
        msgs = _get_banquero_msgs(personality)
        await ctx.send(msgs.get("error_no_admin_bono", "❌ Solo los jefes orkos pueden konfigurar el bono de apertura umano!"))
        return

    msgs = _get_banquero_msgs(personality)

    if not subargs:
        # Mostrar bono actual
        bono_actual = db_banquero.obtener_bono_apertura(servidor_id)

        embed = discord.Embed(
            title=msgs.get("bono_config_title", "🎁 Konfiguración de Bono de Apertura"),
            description=msgs.get("bono_description", "Konfiguración aktual del bono para nuevas kuentas"),
            color=discord.Color.purple()
        )
        embed.add_field(name=msgs.get("bono_actual", "💰 Bono de Apertura Aktual"), value=f"{bono_actual:,} monedas", inline=True)
        embed.add_field(name=msgs.get("servidor", "🏦 Servidor"), value=servidor_nombre, inline=True)
        embed.add_field(name=msgs.get("bono_info", "ℹ️ Info"), value=f"Kada nueva kuenta recibirá {bono_actual:,} monedas automáticamente", inline=False)
        embed.set_footer(text=msgs.get("bono_footer", "💼 Usa !banquero bono <cantidad> para konfigurar"))
        await ctx.send(embed=embed)
    else:
        # Establecer nuevo bono
        try:
            cantidad = int(subargs[0])
            if cantidad < 0 or cantidad > 10000:
                await ctx.send(msgs.get("error_bono_rango", "❌ El bono de apertura debe estar entre 0 y 10000 monedas!"))
                return

            admin_id = str(ctx.author.id)
            admin_nombre = ctx.author.display_name

            if db_banquero.establecer_bono_apertura(servidor_id, cantidad, admin_id, admin_nombre):
                embed = discord.Embed(
                    title=msgs.get("bono_configurado", "✅ Bono de Apertura Konfigurado"),
                    description=msgs.get("bono_actualizado", "El bono de apertura ha sido aktualizado"),
                    color=discord.Color.green()
                )
                embed.add_field(name=msgs.get("nuevo_bono", "💰 Nuevo Bono de Apertura"), value=f"{cantidad:,} monedas", inline=True)
                embed.add_field(name=msgs.get("administrador", "👤 Administrador"), value=admin_nombre, inline=True)
                embed.add_field(name=msgs.get("servidor", "🏦 Servidor"), value=servidor_nombre, inline=True)
                embed.add_field(name=msgs.get("aplicacion", "ℹ️ Aplikación"), value="Las próximas kuentas nuevas recibirán este bono", inline=False)
                embed.set_footer(text=msgs.get("ayuda_footer", "💼 Banquero - Konfiguración Ekonómika"))
                await ctx.send(embed=embed)
            else:
                await ctx.send(msgs.get("error_configurar_bono", "❌ Error al konfigurar el bono de apertura!"))
        except ValueError:
            await ctx.send(msgs.get("error_numero_invalido", "❌ Cantidad inválida! Usa número entero umano bobo!"))
