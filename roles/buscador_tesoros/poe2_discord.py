"""
Comandos de Discord para el Buscador de Tesoros (subrol POE2).
Registra: !buscartesoros, !nobuscartesoros, !poe2liga, !poe2add, !poe2del, !poe2list, !poe2ayuda, !tesorosfrecuencia
"""

import asyncio
import discord
from agent_logging import get_logger
from discord_utils import get_server_name, send_dm_or_channel

logger = get_logger('poe2_discord')

# Flags de disponibilidad
try:
    from roles.buscador_tesoros.poe2 import get_poe2_db_instance
    POE2_MODULE_AVAILABLE = True
except ImportError:
    POE2_MODULE_AVAILABLE = False
    get_poe2_db_instance = None


def _get_poe2_db(guild):
    """Obtiene instancia de BD de POE2 para un servidor."""
    if not POE2_MODULE_AVAILABLE or get_poe2_db_instance is None:
        return None
    server_name = get_server_name(guild)
    return get_poe2_db_instance(server_name)


def _is_poe2_available(agent_config):
    """Verifica si POE2 está disponible (módulo + rol activado)."""
    import os
    if not POE2_MODULE_AVAILABLE:
        return False
    enabled = os.getenv("BUSCADOR_TESOROS_ENABLED", "false").lower() == "true"
    if not enabled:
        enabled = agent_config.get("roles", {}).get("buscador_tesoros", {}).get("enabled", False)
    return enabled


def register_poe2_commands(bot, personality, agent_config):
    """Registra todos los comandos del Buscador de Tesoros POE2 (idempotente)."""

    POE2_AVAILABLE = _is_poe2_available(agent_config)

    # --- !buscartesoros ---
    if bot.get_command("buscartesoros") is None:
        @bot.command(name="buscartesoros")
        async def cmd_buscar_tesoros(ctx, subrol: str = ""):
            if not subrol or subrol.lower() != "poe2":
                role_cfg = personality.get("discord", {}).get("role_messages", {})
                subrol_msg = role_cfg.get("subrol_required", "❌ Debes especificar el subrol. Ejemplo: !buscartesoros poe2")
                await ctx.send(subrol_msg.format(command="buscartesoros"))
                return

            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return

            db_poe2 = _get_poe2_db(ctx.guild)
            if not db_poe2:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return

            if db_poe2.set_activo(True):
                await ctx.send(f"✅ {ctx.author.mention} Subrol POE2 activado. Ahora buscaré tesoros en Path of Exile 2.")
                server_name = ctx.guild.name if ctx.guild else "DM"
                logger.info(f"🔮 {ctx.author.name} activó el subrol en {server_name}")

                # Descargar datos para todos los items existentes
                await ctx.send(f"🔄 {ctx.author.mention} Descargando datos de items existentes...")
                await _download_existing_items(ctx, db_poe2)
            else:
                await ctx.send("❌ Error al activar el subrol POE2. Inténtalo de nuevo.")

        logger.info("🔮 Comando buscartesoros registrado")

    # --- !nobuscartesoros ---
    if bot.get_command("nobuscartesoros") is None:
        @bot.command(name="nobuscartesoros")
        async def cmd_no_buscar_tesoros(ctx, subrol: str = ""):
            if not subrol or subrol.lower() != "poe2":
                role_cfg = personality.get("discord", {}).get("role_messages", {})
                subrol_msg = role_cfg.get("subrol_required", "❌ Debes especificar el subrol. Ejemplo: !nobuscartesoros poe2")
                await ctx.send(subrol_msg.format(command="nobuscartesoros"))
                return

            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return

            db_poe2 = _get_poe2_db(ctx.guild)
            if not db_poe2:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return

            if db_poe2.set_activo(False):
                await ctx.send(f"✅ {ctx.author.mention} Subrol POE2 desactivado. Ya no buscaré tesoros en Path of Exile 2.")
                logger.info(f"🔮 {ctx.author.name} desactivó el subrol en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al desactivar el subrol POE2. Inténtalo de nuevo.")

        logger.info("🔮 Comando nobuscartesoros registrado")

    # --- !poe2liga ---
    if bot.get_command("poe2liga") is None:
        @bot.command(name="poe2liga")
        async def cmd_poe2_liga(ctx, liga: str = ""):
            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return

            db_poe2 = _get_poe2_db(ctx.guild)
            if not db_poe2:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return

            if not liga:
                liga_actual = db_poe2.get_liga()
                await ctx.send(f"🔮 **Liga POE2 actual**: {liga_actual}")
                return

            liga_lower = liga.lower()
            if liga_lower not in ["standard", "fate of the vaal"]:
                await ctx.send("❌ Liga no válida. Las ligas disponibles son: `Standard` y `Fate of the Vaal`")
                return

            liga_formateada = "Fate of the Vaal" if liga_lower == "fate of the vaal" else "Standard"

            if db_poe2.set_liga(liga_formateada):
                await ctx.send(f"✅ {ctx.author.mention} Liga POE2 establecida a: {liga_formateada}")
                await ctx.send(f"ℹ️ {ctx.author.mention} El buscador automático descargará los datos en la próxima ejecución.")
                logger.info(f"🔮 {ctx.author.name} cambió liga a {liga_formateada} en {ctx.guild.name}")
            else:
                await ctx.send("❌ Error al cambiar la liga. Inténtalo de nuevo.")

        logger.info("🔮 Comando poe2liga registrado")

    # --- !poe2add ---
    if bot.get_command("poe2add") is None:
        @bot.command(name="poe2add")
        async def cmd_poe2_add(ctx, item_name: str = ""):
            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return
            if not item_name:
                await ctx.send("❌ Debes especificar el nombre del item. Ejemplo: !poe2add \"Ancient Rib\"")
                return

            db_poe2 = _get_poe2_db(ctx.guild)
            if not db_poe2:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return

            if not db_poe2.add_objetivo(item_name):
                await ctx.send("❌ Error al añadir el item. Inténtalo de nuevo.")
                return

            await ctx.send(f"🔄 {ctx.author.mention} Descargando historial para {item_name}...")
            await _download_and_analyze_item(ctx, db_poe2, item_name)

        logger.info("🔮 Comando poe2add registrado")

    # --- !poe2del ---
    if bot.get_command("poe2del") is None:
        @bot.command(name="poe2del")
        async def cmd_poe2_del(ctx, item_name: str = ""):
            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return
            if not item_name:
                await ctx.send("❌ Debes especificar el nombre del item o número. Ejemplo: !poe2del \"Ancient Rib\" o !poe2del 3")
                return

            db_poe2 = _get_poe2_db(ctx.guild)
            if not db_poe2:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return

            try:
                item_index = int(item_name)
                objetivos = db_poe2.get_objetivos()
                if 1 <= item_index <= len(objetivos):
                    item_real_name = objetivos[item_index - 1][0]
                    if db_poe2.remove_objetivo(item_real_name):
                        await ctx.send(f"✅ {ctx.author.mention} Item #{item_index} eliminado de objetivos: **{item_real_name}**")
                        logger.info(f"🔮 {ctx.author.name} eliminó objetivo #{item_index} ({item_real_name}) en {ctx.guild.name}")
                    else:
                        await ctx.send(f"❌ Error al eliminar el item #{item_index}.")
                else:
                    await ctx.send(f"❌ Número inválido. Hay {len(objetivos)} items. Usa un número entre 1 y {len(objetivos)}.")
            except ValueError:
                if db_poe2.remove_objetivo(item_name):
                    await ctx.send(f"✅ {ctx.author.mention} Item eliminado de objetivos: {item_name}")
                    logger.info(f"🔮 {ctx.author.name} eliminó objetivo {item_name} en {ctx.guild.name}")
                else:
                    await ctx.send(f"❌ No se encontró el item '{item_name}' en la lista de objetivos.")

        logger.info("🔮 Comando poe2del registrado")

    # --- !poe2list ---
    if bot.get_command("poe2list") is None:
        @bot.command(name="poe2list")
        async def cmd_poe2_list(ctx):
            if not POE2_AVAILABLE:
                await ctx.send("❌ El subrol POE2 no está disponible en este servidor.")
                return

            db_poe2 = _get_poe2_db(ctx.guild)
            if not db_poe2:
                await ctx.send("❌ Error al acceder a la base de datos de POE2.")
                return

            liga_actual = db_poe2.get_liga()
            activo = db_poe2.is_activo()
            objetivos = db_poe2.get_objetivos()

            estado = "🟢 Activo" if activo else "🔴 Inactivo"
            response = f"🔮 **Configuración POE2**\n"
            response += f"📊 **Estado**: {estado}\n"
            response += f"🏆 **Liga**: {liga_actual}\n"
            response += f"🎯 **Objetivos** ({len(objetivos)} items):\n"

            if objetivos:
                from roles.buscador_tesoros.db_role_poe import DatabaseRolePoe
                db_precios = DatabaseRolePoe(get_server_name(ctx.guild), liga_actual)
                for i, (nombre, item_id, activo_item, fecha) in enumerate(objetivos, 1):
                    estado_item = "✅" if activo_item else "❌"
                    precio_actual = db_precios.obtener_precio_actual(nombre, liga_actual)
                    if precio_actual:
                        response += f"  {i}. {estado_item} {nombre} - **{precio_actual:.2f} Div**\n"
                    else:
                        response += f"  {i}. {estado_item} {nombre} - *Sin datos*\n"
            else:
                response += "  *No hay items configurados*\n"

            await ctx.send(response)

        logger.info("🔮 Comando poe2list registrado")

    # --- !poe2ayuda ---
    if bot.get_command("poe2ayuda") is None:
        @bot.command(name="poe2ayuda")
        async def cmd_poe2_ayuda(ctx):
            """Muestra ayuda específica para el subrol POE2."""
            ayuda = _build_poe2_help_text()
            await send_dm_or_channel(ctx, ayuda, "📩 Ayuda enviada por mensaje privado.")

        logger.info("🔮 Comando poe2ayuda registrado")

    # --- !tesorosfrecuencia ---
    if bot.get_command("tesorosfrecuencia") is None:
        @bot.command(name="tesorosfrecuencia")
        async def cmd_tesoros_frecuencia(ctx, hours: str = ""):
            """Configura la frecuencia de ejecución automática del buscador de tesoros."""
            if not POE2_AVAILABLE:
                await ctx.send("❌ El buscador de tesoros no está disponible en este servidor.")
                return
            await _cmd_role_frequency(ctx, "buscador_tesoros", hours, personality, agent_config)

        logger.info("💎 Comando tesorosfrecuencia registrado")

    logger.info("🔮 Todos los comandos del Buscador de Tesoros registrados")


# --- Helpers privados ---

async def _download_existing_items(ctx, db_poe2):
    """Descarga datos para todos los items existentes al activar el subrol."""
    try:
        from roles.buscador_tesoros.poe2scout_client import Poe2ScoutClient
        from roles.buscador_tesoros.db_role_poe import DatabaseRolePoe
        from agent_db import get_active_server_name, set_current_server

        original_server = get_active_server_name()
        set_current_server(ctx.guild.name)

        liga_actual = db_poe2.get_liga()
        server_name = get_active_server_name() or "default"
        objetivos_activos = db_poe2.get_objetivos_activos()

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

        if original_server:
            set_current_server(original_server)
    except Exception as e:
        logger.exception(f"Error descargando datos al activar POE2: {e}")
        await ctx.send(f"⚠️ {ctx.author.mention} Hubo un error descargando datos, pero el subrol está activo.")


async def _download_and_analyze_item(ctx, db_poe2, item_name):
    """Descarga historial de un item y realiza análisis inmediato."""
    original_server = None
    exito_descarga = False
    precio_actual = None

    try:
        from roles.buscador_tesoros.db_role_poe import DatabaseRolePoe
        from roles.buscador_tesoros.poe2scout_client import Poe2ScoutClient
        from agent_db import get_active_server_name, set_current_server

        original_server = get_active_server_name()
        set_current_server(get_server_name(ctx.guild))

        liga_actual = db_poe2.get_liga()
        db_precios = DatabaseRolePoe(get_server_name(ctx.guild), liga_actual)
        scout = Poe2ScoutClient()

        entries = scout.get_item_history(item_name, league=liga_actual)
        if entries:
            insertados = db_precios.insertar_precios_bulk(item_name, entries, liga_actual)
            precio_actual = entries[0].price if entries else None
            if precio_actual:
                await ctx.send(f"✅ {ctx.author.mention} Item añadido y actualizado: **{item_name}** - Precio actual: **{precio_actual:.2f} Div** ({insertados} registros nuevos)")
            else:
                await ctx.send(f"✅ {ctx.author.mention} Item añadido: **{item_name}** ({insertados} registros nuevos, sin precio actual)")
            logger.info(f"🔮 {ctx.author.name} añadió y actualizó {item_name} con {insertados} registros en {ctx.guild.name}")
            exito_descarga = True
        else:
            await ctx.send(f"⚠️ {ctx.author.mention} Item añadido pero no se encontraron datos: **{item_name}**")
            logger.warning(f"🔮 No hay datos para {item_name} en liga {liga_actual}")
            exito_descarga = True
    except Exception as e:
        logger.exception(f"Error descargando historial para {item_name}: {e}")
        if not exito_descarga:
            await ctx.send(f"⚠️ {ctx.author.mention} Error al descargar historial para **{item_name}**. El item fue añadido a objetivos y se intentará descargar en la próxima ejecución automática.")
    finally:
        if original_server:
            from agent_db import set_current_server
            set_current_server(original_server)

    # Análisis inmediato del precio
    if exito_descarga and precio_actual:
        try:
            from roles.buscador_tesoros.db_role_poe import DatabaseRolePoe
            from roles.buscador_tesoros.buscador_tesoros import analizar_mercado
            from agent_engine import pensar
            from postprocessor import is_internal_thinking

            liga_actual = db_poe2.get_liga()
            db_precios = DatabaseRolePoe(get_server_name(ctx.guild), liga_actual)
            señal = analizar_mercado(db_precios, item_name, precio_actual, liga_actual)

            if señal:
                logger.info(f"🚨 SEÑAL INMEDIATA: {item_name} - {señal} a {precio_actual} Div")
                notificacion_reciente = db_precios.verificar_notificacion_reciente(
                    item_name, liga_actual, señal, precio_actual, horas=6, umbral_similitud=0.15
                )
                if not notificacion_reciente:
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
                    await ctx.send(f"💎 **TESORO DETECTADO INMEDIATO**: {res}")
                    db_precios.registrar_notificacion(item_name, liga_actual, señal, precio_actual)
                    logger.info(f"✅ Notificación inmediata enviada para {item_name} - {señal}")
                else:
                    logger.info(f"🔕 Notificación inmediata omitida por duplicidad: {item_name} - {señal}")
        except Exception as analisis_e:
            logger.exception(f"Error en análisis inmediato para {item_name}: {analisis_e}")


async def _cmd_role_frequency(ctx, role_name, hours, personality, agent_config):
    """Comando genérico para configurar frecuencia de roles."""
    from discord_utils import is_admin
    role_cfg = personality.get("discord", {}).get("role_messages", {})
    if not is_admin(ctx):
        await ctx.send(role_cfg.get("role_no_permission", "❌ Solo administradores pueden modificar la frecuencia."))
        return

    try:
        hours_int = int(hours) if hours else 0
        if hours_int < 1 or hours_int > 168:
            await ctx.send(role_cfg.get("frequency_invalid", "❌ Las horas deben estar entre 1 y 168."))
            return
    except ValueError:
        await ctx.send(role_cfg.get("frequency_invalid", "❌ Debes especificar un número válido de horas."))
        return

    if "roles" not in agent_config:
        agent_config["roles"] = {}
    if role_name not in agent_config["roles"]:
        agent_config["roles"][role_name] = {}
    agent_config["roles"][role_name]["interval_hours"] = hours_int

    await ctx.send(role_cfg.get("frequency_updated", "✅ Frecuencia de '{role}' actualizada a {hours} horas.").format(role=role_name, hours=hours_int))
    logger.info(f"🎭 {ctx.author.name} actualizó frecuencia de {role_name} a {hours_int} horas en {ctx.guild.name}")


def _build_poe2_help_text():
    """Construye el texto de ayuda del subrol POE2."""
    ayuda = "🔮 **AYUDA DEL BUSCADOR DE TESOROS - POE2**\n\n"
    ayuda += "🎯 **Activación:**\n"
    ayuda += "• `!buscartesoros poe2` - Activa el subrol POE2\n"
    ayuda += "• `!nobuscartesoros poe2` - Desactiva el subrol POE2\n\n"
    ayuda += "🏆 **Gestión de Liga:**\n"
    ayuda += "• `!poe2liga` - Muestra la liga actual\n"
    ayuda += "• `!poe2liga Standard` - Establece liga Standard\n"
    ayuda += "• `!poe2liga Fate of the Vaal` - Establece liga Fate of the Vaal\n"
    ayuda += "• ℹ️ **Nota**: Después de cambiar liga, ejecuta `!buscartesoros poe2` para descargar datos inmediatamente\n\n"
    ayuda += "🎯 **Gestión de Objetivos:**\n"
    ayuda += "• `!poe2add \"Nombre del Item\"` - Añade item a objetivos\n"
    ayuda += "• `!poe2del \"Nombre del Item\"` - Elimina item de objetivos\n"
    ayuda += "• `!poe2list` - Muestra configuración y objetivos actuales\n\n"
    ayuda += "⚖️ **Lógica de Compra/Venta:**\n"
    ayuda += "• **COMPRA**: Precio ≤ mínimo histórico × 1.15\n"
    ayuda += "• **VENTA**: Precio ≥ máximo histórico × 0.85\n\n"
    ayuda += "💡 **Ejemplos de Uso:**\n"
    ayuda += "```\n!buscartesoros poe2\n!poe2liga Fate of the Vaal\n!poe2add \"Ancient Rib\"\n!poe2add \"Fracturing Orb\"\n!poe2list\n```"
    return ayuda
