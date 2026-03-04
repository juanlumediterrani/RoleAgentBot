import discord
import asyncio
import sys
import os
from datetime import datetime
from agent_logging import get_logger

# Asegurar que el path del directorio vigia_noticias esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db_role_vigia import get_vigia_db_instance
from vigia_messages import get_message
from premisas_manager import get_premisas_manager

logger = get_logger('vigia_commands')

class VigiaCommands:
    """Comandos de Discord para gestionar el Vigía de Noticias."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_vigia = None
    
    def _get_db(self, server_name: str = None):
        """Obtiene instancia de BD del vigía."""
        if not self.db_vigia:
            from agent_db import get_active_server_name
            server_name = server_name or get_active_server_name() or "default"
            self.db_vigia = get_vigia_db_instance(server_name)
        return self.db_vigia
    
    async def cmd_feeds(self, message, args):
        """Muestra todos los feeds disponibles."""
        try:
            db = self._get_db()
            feeds = db.obtener_feeds_activos()
            
            if not feeds:
                await message.channel.send(get_message('error_no_hay_feeds'))
                return
            
            embed = discord.Embed(
                title=get_message('feeds_disponibles_title'),
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            feeds_por_categoria = {}
            for feed in feeds:
                feed_id, nombre, url, categoria, pais, idioma, prioridad, palabras_clave, tipo_feed = feed
                if categoria not in feeds_por_categoria:
                    feeds_por_categoria[categoria] = []
                feeds_por_categoria[categoria].append({
                    'id': feed_id, 'nombre': nombre, 'url': url,
                    'pais': pais, 'idioma': idioma, 'prioridad': prioridad, 'tipo_feed': tipo_feed
                })
            
            for categoria, feeds_cat in feeds_por_categoria.items():
                valor = ""
                for feed in feeds_cat:
                    bandera = self._get_bandera_pais(feed['pais'])
                    valor += f"**{feed['nombre']}** ({feed['id']}) {bandera}\n"
                    valor += f"Prioridad: {feed['prioridad']} | Idioma: {feed['idioma'].upper()}\n\n"
                
                embed.add_field(
                    name=f"📂 {categoria.title()} ({len(feeds_cat)} feeds)",
                    value=valor,
                    inline=False
                )
            
            embed.set_footer(text=f"Usa !vigia suscribir <categoría> para recibir noticias")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_feeds: {e}")
            await message.channel.send(get_message('error_general', error=e))
    
    async def cmd_reset(self, message, args):
        """Limpia completamente todas las suscripciones del usuario."""
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            # Verificar si tiene alguna suscripción
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            
            if not tipo_actual:
                await message.channel.send("📝 No tienes ninguna suscripción activa para limpiar.")
                return
            
            # Verificar si es confirmación
            if args and args[0].lower() == "confirmar":
                # Ejecutar reset confirmado
                canceladas = 0
                
                if tipo_actual == 'plana':
                    # Cancelar suscripciones planas
                    suscripciones = db.obtener_suscripciones_usuario(usuario_id)
                    for categoria, feed_id, _ in suscripciones:
                        if db.cancelar_suscripcion_categoria(usuario_id, categoria, feed_id):
                            canceladas += 1
                            
                elif tipo_actual == 'palabras':
                    # Cancelar suscripciones con palabras clave
                    suscripciones = db.obtener_suscripciones_palabras_usuario(usuario_id)
                    for categoria, _, _ in suscripciones:
                        if db.cancelar_suscripcion_palabras_usuario(usuario_id, categoria):
                            canceladas += 1
                            
                elif tipo_actual == 'ia':
                    # Cancelar suscripciones con IA
                    suscripciones = db.obtener_suscripciones_ia_usuario(usuario_id)
                    for categoria, feed_id, _ in suscripciones:
                        if db.cancelar_suscripcion_categoria(usuario_id, categoria, feed_id):
                            canceladas += 1
                
                if canceladas > 0:
                    await message.channel.send(f"✅ **RESET COMPLETADO**\n"
                                             f"Se eliminaron {canceladas} suscripción(es) de tipo '{tipo_actual}'.\n"
                                             f"Ahora puedes suscribirte a un nuevo tipo de alertas.")
                else:
                    await message.channel.send("❌ No se encontraron suscripciones activas para cancelar.")
                return
            
            # Si no es confirmación, mostrar mensaje de confirmación
            await message.channel.send(f"⚠️ **CONFIRMACIÓN REQUERIDA**\n"
                                     f"Vas a eliminar TODAS tus suscripciones de tipo '{tipo_actual}'.\n"
                                     f"Esta acción no se puede deshacer.\n"
                                     f"Para confirmar, usa: `!vigia reset confirmar`")
            
        except Exception as e:
            logger.exception(f"Error en cmd_reset: {e}")
            await message.channel.send("❌ Error al procesar solicitud de reset")
    
    async def cmd_categorias(self, message, args):
        """Muestra categorías disponibles."""
        try:
            db = self._get_db()
            categorias = db.obtener_categorias_disponibles()
            
            if not categorias:
                await message.channel.send(get_message('error_no_hay_categorias'))
                return
            
            embed = discord.Embed(
                title=get_message('categorias_disponibles_title'),
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            
            valor = ""
            for categoria, count in categorias:
                icono = self._get_icono_categoria(categoria)
                valor += f"{icono} **{categoria.title()}** - {count} feeds\n"
            
            embed.description = valor
            embed.set_footer(text="Usa !vigia suscribir <categoría> para recibir noticias de esa categoría")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_categorias: {e}")
            await message.channel.send(get_message('error_general', error=e))
    
    async def cmd_suscribir(self, message, args):
        """Suscribe usuario a una categoría o feed específico (suscripción plana)."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia suscribir <categoría> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = args[0].lower()
            feed_id = None
            
            # Verificar si es un feed_id específico
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verificar que el feed exista y pertenezca a la categoría
                    feeds = db.obtener_feeds_activos(categoria)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(f"❌ Feed ID {feed_id} no encontrado en categoría '{categoria}'")
                        return
                except ValueError:
                    await message.channel.send("❌ El feed_id debe ser un número")
                    return
            else:
                # Verificar que la categoría exista
                categorias = db.obtener_categorias_disponibles()
                if not any(cat[0] == categoria for cat in categorias):
                    await message.channel.send(f"❌ Categoría '{categoria}' no encontrada")
                    return
            
            # Verificar tipo de suscripción actual del usuario
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            
            # Si ya tiene suscripción plana, informar y bloquear
            if tipo_actual == 'plana':
                await message.channel.send("ℹ️ Ya tienes una suscripción plana activa. Usa `!vigia cancelar <categoría>` primero si quieres cambiar.")
                return
            
            # Si tiene otros tipos de suscripción, advertir y bloquear
            if tipo_actual in ['palabras', 'ia']:
                await message.channel.send(f"⚠️ Tienes una suscripción de tipo '{tipo_actual}' activa. Solo puedes tener UN tipo de suscripción a la vez. Usa `!vigia reset` para limpiar todas las suscripciones.")
                return
            
            # Realizar suscripción plana
            if db.suscribir_usuario_categoria(usuario_id, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ Suscripción plana exitosa: Feed {feed_id} de categoría '{categoria}'")
                else:
                    await message.channel.send(f"✅ Suscripción plana exitosa: Categoría '{categoria}'")
            else:
                await message.channel.send("❌ Error al crear suscripción plana")
                
        except Exception as e:
            logger.exception(f"Error en cmd_suscribir: {e}")
            await message.channel.send("❌ Error al procesar la suscripción")
    
    async def cmd_cancelar(self, message, args):
        """Cancela suscripción plana a categoría o feed."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia cancelar <categoría> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = args[0].lower()
            feed_id = None
            
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send("❌ El feed_id debe ser un número")
                    return
            
            if db.cancelar_suscripcion_categoria(usuario_id, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ Suscripción plana cancelada: Feed {feed_id} de '{categoria}'")
                else:
                    await message.channel.send(f"✅ Suscripción plana cancelada: Categoría '{categoria}'")
            else:
                await message.channel.send("❌ No tienes suscripción plana activa en esa categoría/feed")
                
        except Exception as e:
            logger.exception(f"Error en cmd_cancelar: {e}")
            await message.channel.send("❌ Error al cancelar suscripción plana")
    
    async def cmd_general_cancelar(self, message, args):
        """Cancela suscripción con IA a categoría o feed."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia general cancelar <categoría> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = args[0].lower()
            feed_id = None
            
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send("❌ El feed_id debe ser un número")
                    return
            
            if db.cancelar_suscripcion_categoria(usuario_id, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ Suscripción con IA cancelada: Feed {feed_id} de '{categoria}'")
                else:
                    await message.channel.send(f"✅ Suscripción con IA cancelada: Categoría '{categoria}'")
            else:
                await message.channel.send("❌ No tienes suscripción con IA activa en esa categoría/feed")
                
        except Exception as e:
            logger.exception(f"Error en cmd_general_cancelar: {e}")
            await message.channel.send("❌ Error al cancelar suscripción con IA")
    
    async def cmd_estado(self, message, args):
        """Muestra el tipo de suscripción activa del usuario."""
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            # Verificar tipo de suscripción actual
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            logger.info(f"DEBUG: Tipo de suscripción para {usuario_id}: {tipo_actual}")
            
            if not tipo_actual:
                await message.channel.send("📝 No tienes ninguna suscripción activa")
                return
            
            # Mostrar información según el tipo
            if tipo_actual == 'plana':
                suscripciones = db.obtener_suscripciones_usuario(usuario_id)
                if suscripciones:
                    embed = discord.Embed(
                        title="📰 Suscripción Plana Activa",
                        description="Recibes **todas las noticias** con opinión generada",
                        color=discord.Color.blue()
                    )
                    
                    for i, (categoria, feed_id, fecha) in enumerate(suscripciones, 1):
                        if feed_id:
                            embed.add_field(
                                name=f"#{i} - {categoria}",
                                value=f"Feed ID: {feed_id}\nDesde: {fecha}",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"#{i} - {categoria}",
                                value=f"Toda la categoría\nDesde: {fecha}",
                                inline=False
                            )
                    
                    embed.set_footer(text="Usa !vigia cancelar <categoría> para cancelar")
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send("📝 No tienes suscripción plana activa")
                    
            elif tipo_actual == 'palabras':
                suscripciones = db.obtener_suscripciones_palabras_usuario(usuario_id)
                if suscripciones:
                    embed = discord.Embed(
                        title="🔍 Suscripción con Palabras Clave Activa",
                        description="Recibes **noticias filtradas** que coinciden con tus palabras clave",
                        color=discord.Color.green()
                    )
                    
                    for i, (categoria, feed_id, palabras) in enumerate(suscripciones, 1):
                        if feed_id:
                            embed.add_field(
                                name=f"#{i} - {categoria} (Feed {feed_id})",
                                value=f"Palabras: {palabras}",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"#{i} - {categoria}",
                                value=f"Palabras: {palabras}",
                                inline=False
                            )
                    
                    embed.set_footer(text="Usa !vigia palabras desuscribir <categoría> para cancelar")
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send("📝 No tienes suscripción con palabras clave activa")
                    
            elif tipo_actual == 'ia':
                suscripciones = db.obtener_suscripciones_ia_usuario(usuario_id)
                logger.info(f"DEBUG: Suscripciones IA encontradas: {suscripciones}")
                if suscripciones:
                    embed = discord.Embed(
                        title="🤖 Suscripción con IA Activa",
                        description="Recibes **noticias críticas** analizadas según tus premisas",
                        color=discord.Color.purple()
                    )
                    
                    for i, (categoria, feed_id, premisas) in enumerate(suscripciones, 1):
                        if feed_id:
                            embed.add_field(
                                name=f"#{i} - {categoria} (Feed {feed_id})",
                                value=f"Premisas configuradas: {len(premisas.split(','))}",
                                inline=False
                            )
                        else:
                            embed.add_field(
                                name=f"#{i} - {categoria}",
                                value=f"Premisas configuradas: {len(premisas.split(','))}",
                                inline=False
                            )
                    
                    embed.set_footer(text="Usa !vigia general cancelar <categoría> para cancelar")
                    await message.channel.send(embed=embed)
                else:
                    logger.warning(f"DEBUG: Inconsistencia detectada - tipo='ia' pero no hay suscripciones IA para usuario {usuario_id}")
                    await message.channel.send("📝 No tienes suscripción con IA activa")
                    
        except Exception as e:
            logger.exception(f"Error en cmd_estado: {e}")
            await message.channel.send("❌ Error al mostrar estado de suscripciones")
    
    async def cmd_categorias(self, message, args):
        """Muestra categorías disponibles con feeds activos."""
        try:
            db = self._get_db()
            categorias = db.obtener_categorias_disponibles()
            
            if not categorias:
                await message.channel.send("📝 No hay categorías disponibles")
                return
            
            embed = discord.Embed(
                title="📂 Categorías Disponibles",
                description=f"Hay {len(categorias)} categorías con feeds activos:",
                color=discord.Color.blue()
            )
            
            for categoria, count in categorias:
                icono = self._get_icono_categoria(categoria)
                embed.add_field(
                    name=f"{icono} {categoria.title()}",
                    value=f"{count} feeds disponibles",
                    inline=True
                )
            
            embed.set_footer(text="Usa !vigia feeds para ver los feeds de cada categoría")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_categorias: {e}")
            await message.channel.send("❌ Error al mostrar categorías")
    
    async def cmd_agregar_feed(self, message, args):
        """Agrega nuevo feed (solo admins)."""
        if len(args) < 3:
            await message.channel.send("📝 Uso: `!vigia agregar_feed <nombre> <url> <categoría> [país] [idioma]`")
            return
        
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo administradores pueden agregar feeds")
            return
        
        try:
            db = self._get_db()
            nombre = args[0]
            url = args[1]
            categoria = args[2].lower()
            pais = args[3] if len(args) > 3 else None
            idioma = args[4] if len(args) > 4 else 'es'
            
            if db.agregar_feed(nombre, url, categoria, pais, idioma):
                await message.channel.send(f"✅ Feed '{nombre}' agregado a categoría '{categoria}'")
            else:
                await message.channel.send(get_message('error_agregar_feed'))
                
        except Exception as e:
            logger.exception(f"Error en cmd_agregar_feed: {e}")
            await message.channel.send("❌ Error al agregar feed")
    
    def _get_icono_categoria(self, categoria: str) -> str:
        """Obtiene icono para categoría."""
        iconos = {
            'economia': '💰',
            'internacional': '🌍',
            'tecnologia': '💻',
            'sociedad': '👥',
            'politica': '🏛️',
            'deportes': '⚽',
            'cultura': '🎭',
            'ciencia': '🔬'
        }
        return iconos.get(categoria, '📰')
    
    async def cmd_general_suscribir(self, message, args):
        """Suscripción con IA - analiza noticias según premisas clave."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia general <categoría> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = args[0].lower()
            feed_id = None
            
            # Verificar si es un feed_id específico
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verificar que el feed exista y pertenezca a la categoría
                    feeds = db.obtener_feeds_activos(categoria)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(f"❌ Feed ID {feed_id} no encontrado en categoría '{categoria}'")
                        return
                except ValueError:
                    await message.channel.send("❌ El feed_id debe ser un número")
                    return
            else:
                # Verificar que la categoría exista
                categorias = db.obtener_categorias_disponibles()
                if not any(cat[0] == categoria for cat in categorias):
                    await message.channel.send(f"❌ Categoría '{categoria}' no encontrada")
                    return
            
            # Verificar tipo de suscripción actual del usuario
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            
            # Si ya tiene suscripción con IA, informar y bloquear
            if tipo_actual == 'ia':
                await message.channel.send("ℹ️ Ya tienes una suscripción con IA activa. Usa `!vigia general cancelar <categoría>` primero si quieres cambiar.")
                return
            
            # Si tiene otros tipos de suscripción, advertir y bloquear
            if tipo_actual in ['plana', 'palabras']:
                await message.channel.send(f"⚠️ Tienes una suscripción de tipo '{tipo_actual}' activa. Solo puedes tener UN tipo de suscripción a la vez. Usa `!vigia reset` para limpiar todas las suscripciones.")
                return
            
            # Verificar si el usuario tiene premisas configuradas
            premisas, contexto = db.obtener_premisas_con_contexto(usuario_id)
            if not premisas:
                await message.channel.send("⚠️ No tienes premisas configuradas. Usa `!vigia premisas add <premisa>` para agregar premisas antes de suscribirte con IA.")
                return
            
            # Realizar suscripción con IA (agregando premisas del usuario)
            premisas_str = ",".join(premisas) if premisas else ""
            if db.suscribir_usuario_categoria_ia(usuario_id, categoria, feed_id, premisas_str):
                if feed_id:
                    await message.channel.send(f"🤖 **Suscripción con IA** al feed {feed_id} de '{categoria}' - Analizaré noticias críticas según tus premisas")
                else:
                    await message.channel.send(f"🤖 **Suscripción con IA** a '{categoria}' - Analizaré noticias críticas según tus premisas")
            else:
                await message.channel.send("❌ Error al crear suscripción con IA")
                
        except Exception as e:
            logger.exception(f"Error en cmd_general_suscribir: {e}")
            await message.channel.send("❌ Error al procesar la suscripción con IA")
    
    async def cmd_palabras_suscribir(self, message, args):
        """Suscribe a palabras clave específicas con análisis regex."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia palabras \"palabra1,palabra2\" [categoría] [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            # Extraer palabras clave (entre comillas)
            palabras_clave = args[0].strip('"\'')
            categoria = None
            feed_id = None
            
            # Verificar si se especificó categoría
            if len(args) > 1:
                categoria = args[1].lower()
                
                # Verificar si se especificó feed_id
                if len(args) > 2:
                    try:
                        feed_id = int(args[2])
                        # Verificar que el feed exista y pertenezca a la categoría
                        feeds = db.obtener_feeds_activos(categoria)
                        feed_existente = any(f[0] == feed_id for f in feeds)
                        if not feed_existente:
                            await message.channel.send(f"❌ Feed ID {feed_id} no encontrado en categoría '{categoria}'")
                            return
                    except ValueError:
                        await message.channel.send("❌ El feed_id debe ser un número")
                        return
                else:
                    # Verificar que la categoría exista
                    categorias = db.obtener_categorias_disponibles()
                    if not any(cat[0] == categoria for cat in categorias):
                        await message.channel.send(f"❌ Categoría '{categoria}' no encontrada")
                        return
            
            if not palabras_clave:
                await message.channel.send("❌ Debes proporcionar palabras clave")
                return
            
            # Verificar tipo de suscripción actual del usuario
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            
            # Si ya tiene suscripción de palabras clave, informar y bloquear
            if tipo_actual == 'palabras':
                await message.channel.send("ℹ️ Ya tienes una suscripción con palabras clave activa. Usa `!vigia palabras desuscribir <categoría>` primero si quieres cambiar.")
                return
            
            # Si tiene otros tipos de suscripción, advertir y bloquear
            if tipo_actual in ['plana', 'ia']:
                await message.channel.send(f"⚠️ Tienes una suscripción de tipo '{tipo_actual}' activa. Solo puedes tener UN tipo de suscripción a la vez. Usa `!vigia reset` para limpiar todas las suscripciones.")
                return
            
            # Realizar suscripción de palabras clave
            if db.suscribir_palabras_clave(usuario_id, palabras_clave, None, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"🔍 **Suscripción con palabras clave** al feed {feed_id} de '{categoria}' - Buscaré: '{palabras_clave}'")
                elif categoria:
                    await message.channel.send(f"🔍 **Suscripción con palabras clave** a '{categoria}' - Buscaré: '{palabras_clave}'")
                else:
                    await message.channel.send(f"🔍 **Suscripción con palabras clave** global - Buscaré: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error al suscribirse a palabras clave")
                
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_suscribir: {e}")
            await message.channel.send("❌ Error al suscribirse a palabras clave")
    
    async def cmd_palabras_add(self, message, args):
        """Añade una palabra clave a la lista."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia palabras add <palabra>`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            palabra = args[0]
            
            # Obtener palabras actuales
            palabras_actuales = db.obtener_palabras_usuario(usuario_id)
            
            if not palabras_actuales:
                # Si no tiene palabras, crear nueva lista
                if db.suscribir_palabras_clave(usuario_id, palabra, None, None, None):
                    await message.channel.send(f"✅ Palabra clave '{palabra}' añadida. Lista: {palabra}")
                else:
                    await message.channel.send("❌ Error al añadir palabra clave")
            else:
                # Añadir a la lista existente
                lista_palabras = palabras_actuales.split(',')
                if palabra in lista_palabras:
                    await message.channel.send(f"ℹ️ La palabra '{palabra}' ya está en tu lista")
                    return
                
                lista_palabras.append(palabra)
                nuevas_palabras = ','.join(lista_palabras)
                
                if db.actualizar_palabras_usuario(usuario_id, nuevas_palabras):
                    await message.channel.send(f"✅ Palabra clave '{palabra}' añadida. Lista actual: {nuevas_palabras}")
                else:
                    await message.channel.send("❌ Error al añadir palabra clave")
                    
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_add: {e}")
            await message.channel.send("❌ Error al añadir palabra clave")
    
    async def cmd_palabras_list(self, message, args):
        """Muestra todas las palabras clave del usuario."""
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            palabras = db.obtener_palabras_usuario(usuario_id)
            
            if not palabras:
                await message.channel.send("📝 No tienes palabras clave configuradas")
                return
            
            lista_palabras = palabras.split(',')
            
            embed = discord.Embed(
                title="🔍 Tus Palabras Clave",
                description=f"Tienes {len(lista_palabras)} palabras clave configuradas:",
                color=discord.Color.blue()
            )
            
            for i, palabra in enumerate(lista_palabras, 1):
                embed.add_field(name=f"#{i}", value=palabra, inline=False)
            
            embed.set_footer(text="Usa !vigia palabras add <palabra> para añadir más")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_list: {e}")
            await message.channel.send("❌ Error al mostrar palabras clave")
    
    async def cmd_palabras_mod(self, message, args):
        """Modifica una palabra clave específica."""
        if len(args) < 2:
            await message.channel.send("📝 Uso: `!vigia palabras mod <número> \"nueva palabra\"`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            try:
                num = int(args[0]) - 1  # Convertir a 0-based index
                if num < 0:
                    raise ValueError
            except ValueError:
                await message.channel.send("❌ El número debe ser un entero positivo")
                return
            
            nueva_palabra = args[1].strip('"\'')
            
            palabras = db.obtener_palabras_usuario(usuario_id)
            if not palabras:
                await message.channel.send("❌ No tienes palabras clave configuradas")
                return
            
            lista_palabras = palabras.split(',')
            
            if num >= len(lista_palabras):
                await message.channel.send(f"❌ No tienes palabra #{num + 1}. Tienes {len(lista_palabras)} palabras")
                return
            
            palabra_antigua = lista_palabras[num]
            lista_palabras[num] = nueva_palabra
            palabras_actualizadas = ','.join(lista_palabras)
            
            if db.actualizar_palabras_usuario(usuario_id, palabras_actualizadas):
                await message.channel.send(f"✅ Palabra #{num + 1} modificada: '{palabra_antigua}' → '{nueva_palabra}'")
            else:
                await message.channel.send("❌ Error al modificar palabra clave")
                
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_mod: {e}")
            await message.channel.send("❌ Error al modificar palabra clave")
    
    async def cmd_palabras_suscribir(self, message, args):
        """Suscribe a categoría/feed con palabras clave existentes."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia palabras suscribir <categoría> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = args[0].lower()
            feed_id = None
            
            # Verificar si tiene palabras clave configuradas
            palabras = db.obtener_palabras_usuario(usuario_id)
            if not palabras:
                await message.channel.send("❌ No tienes palabras clave configuradas. Usa `!vigia palabras add <palabra>` primero")
                return
            
            # Verificar si es un feed_id específico
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verificar que el feed exista y pertenezca a la categoría
                    feeds = db.obtener_feeds_activos(categoria)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(f"❌ Feed ID {feed_id} no encontrado en categoría '{categoria}'")
                        return
                except ValueError:
                    await message.channel.send("❌ El feed_id debe ser un número")
                    return
            else:
                # Verificar que la categoría exista
                categorias = db.obtener_categorias_disponibles()
                if not any(cat[0] == categoria for cat in categorias):
                    await message.channel.send(f"❌ Categoría '{categoria}' no encontrada")
                    return
            
            # Verificar tipo de suscripción actual del usuario
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            
            # Si ya tiene suscripción de palabras clave, informar y bloquear
            if tipo_actual == 'palabras':
                await message.channel.send("ℹ️ Ya tienes una suscripción con palabras clave activa. Usa `!vigia palabras desuscribir <categoría>` primero si quieres cambiar.")
                return
            
            # Si tiene otros tipos de suscripción, advertir y bloquear
            if tipo_actual in ['plana', 'ia']:
                await message.channel.send(f"⚠️ Tienes una suscripción de tipo '{tipo_actual}' activa. Solo puedes tener UN tipo de suscripción a la vez. Usa `!vigia reset` para limpiar todas las suscripciones.")
                return
            
            # Realizar suscripción de palabras clave
            if db.suscribir_palabras_clave(usuario_id, palabras, None, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"🔍 **Suscripción con palabras clave** al feed {feed_id} de '{categoria}' - Buscaré: '{palabras}'")
                else:
                    await message.channel.send(f"🔍 **Suscripción con palabras clave** a '{categoria}' - Buscaré: '{palabras}'")
            else:
                await message.channel.send("❌ Error al suscribirse a palabras clave")
                
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_suscribir: {e}")
            await message.channel.send("❌ Error al suscribirse a palabras clave")
    
    async def cmd_palabras_suscripciones(self, message, args):
        """Muestra las suscripciones activas con palabras clave."""
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            suscripciones = db.obtener_suscripciones_palabras_usuario(usuario_id)
            
            if not suscripciones:
                await message.channel.send("📝 No tienes suscripciones con palabras clave activas")
                return
            
            embed = discord.Embed(
                title="🔍 Suscripciones con Palabras Clave",
                description=f"Tienes {len(suscripciones)} suscripciones activas:",
                color=discord.Color.blue()
            )
            
            for i, (categoria, feed_id, palabras) in enumerate(suscripciones, 1):
                if feed_id:
                    embed.add_field(
                        name=f"#{i} - {categoria} (Feed {feed_id})",
                        value=f"Palabras: {palabras}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name=f"#{i} - {categoria}",
                        value=f"Palabras: {palabras}",
                        inline=False
                    )
            
            embed.set_footer(text="Usa !vigia palabras desuscribir <categoría> para cancelar")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_suscripciones: {e}")
            await message.channel.send("❌ Error al mostrar suscripciones")
    
    async def cmd_palabras_desuscribir(self, message, args):
        """Cancela suscripción a palabras clave de una categoría."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia palabras desuscribir <categoría>`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = args[0].lower()
            
            if db.cancelar_suscripcion_palabras_usuario(usuario_id, categoria):
                await message.channel.send(f"✅ Suscripción con palabras clave cancelada para '{categoria}'")
            else:
                await message.channel.send(f"❌ No tienes suscripción con palabras clave en '{categoria}'")
                
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_desuscribir: {e}")
            await message.channel.send("❌ Error al cancelar suscripción")
    
    async def cmd_palabras_cancelar(self, message, args):
        """Cancela suscripción a palabras clave."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia cancelar_palabras \"palabra1,palabra2\"`")
            return
        
        try:
            db = self._get_db()
            palabras_clave = " ".join(args).strip('"\'')
            
            if db.cancelar_suscripcion_palabras(str(message.author.id), palabras_clave):
                await message.channel.send(f"✅ Suscripción cancelada: '{palabras_clave}'")
            else:
                await message.channel.send("❌ No se encontró esa suscripción de palabras clave")
                
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_cancelar: {e}")
            await message.channel.send("❌ Error al cancelar suscripción de palabras clave")
    
    async def cmd_mixto_suscribir(self, message, args):
        """Suscribe a feeds especializados + generales de una categoría."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia mixto <categoría>`")
            return
        
        try:
            db = self._get_db()
            categoria = args[0].lower()
            
            # Verificar que la categoría exista
            categorias = db.obtener_categorias_disponibles()
            if not any(cat[0] == categoria for cat in categorias):
                await message.channel.send(get_message('categoria_no_encontrada', categoria=categoria))
                return
            
            # Suscribir a feeds especializados (sin feed_id)
            if db.suscribir_usuario_categoria(str(message.author.id), categoria):
                # También suscribir a feeds generales si existen
                feeds = db.obtener_feeds_activos(categoria)
                feeds_generales = [f for f in feeds if f[8] == 'general']
                
                for feed in feeds_generales:
                    db.suscribir_usuario_categoria(str(message.author.id), categoria, feed[0])
                
                if feeds_generales:
                    await message.channel.send(f"✅ Suscrito a cobertura mixta de '{categoria}' (especializado + general)")
                else:
                    await message.channel.send(f"✅ Suscrito a cobertura especializada de '{categoria}'")
            else:
                await message.channel.send("❌ Error al realizar suscripción mixta")
                
        except Exception as e:
            logger.exception(f"Error en cmd_mixto_suscribir: {e}")
            await message.channel.send("❌ Error al suscribirse a cobertura mixta")
    
    async def cmd_estado_palabras(self, message, args):
        """Muestra suscripciones de palabras clave del usuario."""
        try:
            db = self._get_db()
            suscripciones = db.obtener_suscripciones_palabras(str(message.author.id))
            
            if not suscripciones:
                await message.channel.send(get_message('error_no_hay_palabras_clave'))
                return
            
            embed = discord.Embed(
                title=f"🔍 Tus Palabras Clave - {message.author.display_name}",
                color=discord.Color.dark_blue(),
                timestamp=datetime.now()
            )
            
            valor = ""
            for palabras, fecha in suscripciones:
                valor += f"🔑 **{palabras}**\n"
                valor += f"📅 Suscrito: {fecha[:10]}\n\n"
            
            embed.description = valor
            embed.set_footer(text="Usa !vigia cancelar_palabras \"palabras\" para cancelar")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_estado_palabras: {e}")
            await message.channel.send("❌ Error obteniendo palabras clave")
    
    async def cmd_canal_palabras_suscribir(self, message, args):
        """Suscribe canal a palabras clave."""
        if not args:
            await message.channel.send("📝 Uso: `!vigiacanal palabras \"palabra1,palabra2\"`")
            return
        
        # Verificar permisos
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send("❌ Necesitas permiso 'Gestionar Canales' para suscribir el canal")
            return
        
        try:
            db = self._get_db()
            palabras_clave = " ".join(args).strip('"\'')
            canal = message.channel
            
            if db.suscribir_palabras_clave(str(message.author.id), palabras_clave, str(canal.id)):
                await message.channel.send(f"✅ Canal suscrito a palabras clave: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error al suscribir canal a palabras clave")
                
        except Exception as e:
            logger.exception(f"Error en cmd_canal_palabras_suscribir: {e}")
            await message.channel.send("❌ Error al suscribir canal a palabras clave")
    
    async def cmd_canal_palabras_cancelar(self, message, args):
        """Cancela suscripción de palabras clave del canal."""
        if not args:
            await message.channel.send("📝 Uso: `!vigiacanal palabras cancelar \"palabra1,palabra2\"`")
            return
        
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo administradores pueden gestionar suscripciones de canal")
            return
        
        try:
            db = self._get_db()
            canal = message.channel
            palabras_clave = " ".join(args).strip('"\'')
            
            if db.cancelar_suscripcion_palabras_canal(str(canal.id), palabras_clave):
                await message.channel.send(f"✅ Suscripción de palabras clave cancelada: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error al cancelar suscripción de palabras clave")
                
        except Exception as e:
            logger.exception(f"Error en cmd_canal_palabras_cancelar: {e}")
            await message.channel.send("❌ Error cancelando suscripción de palabras clave")
    
    # ===== COMANDOS DE PREMISAS PARA CANALES =====
    
    async def cmd_canal_premisas(self, message, args):
        """Comando principal de gestión de premisas para canales."""
        if not args:
            # Si no hay subcomando, mostrar lista por defecto
            await self.cmd_canal_premisas_listar(message, args)
            return
        
        subcomando = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []
        
        if subcomando == 'listar' or subcomando == 'list':
            await self.cmd_canal_premisas_listar(message, subargs)
        elif subcomando == 'add':
            await self.cmd_canal_premisas_add(message, subargs)
        elif subcomando == 'mod':
            await self.cmd_canal_premisas_mod(message, subargs)
        else:
            await message.channel.send(f"❌ Subcomando '{subcomando}' no reconocido. Usa: list, add, mod")
    
    async def cmd_canal_premisas_listar(self, message, args):
        """Lista todas las premisas del canal (personalizadas o globales)."""
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo administradores pueden ver las premisas del canal")
            return
        
        try:
            db = self._get_db()
            canal = message.channel
            canal_id = str(canal.id)
            
            # Obtener premisas con contexto
            premisas, contexto = db.obtener_premisas_canal_con_contexto(canal_id)
            
            if not premisas:
                await message.channel.send("📭 No hay premisas configuradas para este canal.")
                return
            
            embed = discord.Embed(
                title=f"🎯 Premisas del Canal #{canal.name} ({contexto.title()})",
                description="Estas son las condiciones que hacen una noticia **CRÍTICA** para este canal:",
                color=discord.Color.blue() if contexto == "personalizadas" else discord.Color.red(),
                timestamp=datetime.now()
            )
            
            for i, premisa in enumerate(premisas, 1):
                embed.add_field(
                    name=f"Premisa #{i}",
                    value=f"📍 {premisa}",
                    inline=False
                )
            
            if contexto == "personalizadas":
                embed.set_footer(text="Usa !vigiacanal premisas add/mod para gestionar las premisas del canal")
            else:
                embed.set_footer(text="Usa !vigiacanal premisas add para crear premisas personalizadas para el canal")
            
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_canal_premisas_listar: {e}")
            await message.channel.send("❌ Error listando premisas del canal")
    
    async def cmd_canal_premisas_add(self, message, args):
        """Añade una nueva premisa al canal si hay hueco (máximo 7)."""
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo administradores pueden gestionar premisas del canal")
            return
        
        if not args:
            await message.channel.send("📝 Uso: `!vigiacanal premisas add \"texto de la nueva premisa\"`")
            return
        
        try:
            db = self._get_db()
            canal = message.channel
            canal_id = str(canal.id)
            nueva_premisa = " ".join(args).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la premisa.")
                return
            
            success, mensaje = db.añadir_premisa_canal(canal_id, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error en cmd_canal_premisas_add: {e}")
            await message.channel.send("❌ Error añadiendo premisa del canal")
    
    async def cmd_canal_premisas_mod(self, message, args):
        """Modifica una premisa específica del canal por número."""
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo administradores pueden gestionar premisas del canal")
            return
        
        if len(args) < 2:
            await message.channel.send("📝 Uso: `!vigiacanal premisas mod <número> \"nueva premisa\"`")
            return
        
        try:
            db = self._get_db()
            canal = message.channel
            canal_id = str(canal.id)
            
            # Parsear número
            try:
                indice = int(args[0])
            except ValueError:
                await message.channel.send("❌ El número debe ser un entero.")
                return
            
            nueva_premisa = " ".join(args[1:]).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la nueva premisa.")
                return
            
            success, mensaje = db.modificar_premisa_canal(canal_id, indice, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error en cmd_canal_premisas_mod: {e}")
            await message.channel.send("❌ Error modificando premisa del canal")
    
    async def cmd_canal_general_suscribir(self, message, args):
        """Suscribe canal a categoría con IA - analiza noticias según premisas clave."""
        if not args:
            await message.channel.send("📝 Uso: `!vigiacanal general <categoría> [feed_id]`")
            return
        
        try:
            # Verificar permisos de admin
            if not message.author.guild_permissions.administrator:
                await message.channel.send("❌ Solo administradores pueden suscribir canales")
                return
            
            db = self._get_db()
            canal_id = str(message.channel.id)
            canal_nombre = message.channel.name
            servidor_id = str(message.guild.id)
            servidor_nombre = message.guild.name
            categoria = args[0].lower()
            feed_id = None
            
            # Verificar si es un feed_id específico
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verificar que el feed exista y pertenezca a la categoría
                    feeds = db.obtener_feeds_activos(categoria)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(f"❌ Feed ID {feed_id} no encontrado en categoría '{categoria}'")
                        return
                except ValueError:
                    await message.channel.send("❌ El feed_id debe ser un número")
                    return
            else:
                # Verificar que la categoría exista
                categorias = db.obtener_categorias_disponibles()
                if not any(cat[0] == categoria for cat in categorias):
                    await message.channel.send(f"❌ Categoría '{categoria}' no encontrada")
                    return
            
            # Verificar si el canal tiene premisas configuradas
            premisas, contexto = db.obtener_premisas_con_contexto(f"canal_{canal_id}")
            if not premisas:
                await message.channel.send("⚠️ El canal no tiene premisas configuradas. Usa `!vigiacanal premisas add <premisa>` para agregar premisas antes de suscribirte con IA.")
                return
            
            # Realizar suscripción con IA (agregando premisas del canal)
            premisas_str = ",".join(premisas) if premisas else ""
            if db.suscribir_canal_categoria_ia(canal_id, canal_nombre, servidor_id, servidor_nombre, categoria, feed_id, premisas_str):
                if feed_id:
                    await message.channel.send(f"🤖 **Suscripción con IA del canal** al feed {feed_id} de '{categoria}' - Analizaré noticias críticas según las premisas del canal")
                else:
                    await message.channel.send(f"🤖 **Suscripción con IA del canal** a '{categoria}' - Analizaré noticias críticas según las premisas del canal")
            else:
                await message.channel.send("❌ Error al crear suscripción con IA del canal")
                
        except Exception as e:
            logger.exception(f"Error en cmd_canal_general_suscribir: {e}")
            await message.channel.send("❌ Error al procesar la suscripción con IA del canal")
    
    async def cmd_canal_general_cancelar(self, message, args):
        """Cancela suscripción con IA de canal a categoría/feed."""
        if not args:
            await message.channel.send("📝 Uso: `!vigiacanal general cancelar <categoría> [feed_id]`")
            return
        
        try:
            # Verificar permisos de admin
            if not message.author.guild_permissions.administrator:
                await message.channel.send("❌ Solo administradores pueden cancelar suscripciones de canal")
                return
            
            db = self._get_db()
            canal_id = str(message.channel.id)
            categoria = args[0].lower()
            feed_id = None
            
            # Si hay más argumentos después de la categoría, es el feed_id
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send("❌ El feed_id debe ser un número")
                    return
            
            if db.cancelar_suscripcion_categoria(f"canal_{canal_id}", categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ Suscripción con IA del canal cancelada: Feed {feed_id} de '{categoria}'")
                else:
                    await message.channel.send(f"✅ Suscripción con IA del canal cancelada: Categoría '{categoria}'")
            else:
                await message.channel.send("❌ El canal no tiene suscripción con IA activa en esa categoría/feed")
                
        except Exception as e:
            logger.exception(f"Error en cmd_canal_general_cancelar: {e}")
            await message.channel.send("❌ Error al cancelar suscripción con IA del canal")
    
    def _get_icono_categoria(self, categoria: str) -> str:
        """Obtiene icono para categoría."""
        iconos = {
            'economia': '💰',
            'internacional': '🌍',
            'tecnologia': '💻',
            'sociedad': '👥',
            'politica': '🏛️',
            'deportes': '⚽',
            'cultura': '🎭',
            'ciencia': '🔬'
        }
        return iconos.get(categoria, '📰')
    
    async def cmd_canal_suscribir(self, message, args):
        """Suscribe el canal actual a una categoría o feed específico."""
        if not args:
            await message.channel.send("📝 Uso: `!vigiacanal suscribir <categoría> [feed_id]`")
            return
        
        # Verificar permisos (requiere manage channel)
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send("❌ Necesitas permiso 'Gestionar Canales' para suscribir el canal")
            return
        
        try:
            db = self._get_db()
            categoria = args[0].lower()
            feed_id = None
            
            # Verificar si es un feed_id específico
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verificar que el feed exista y pertenezca a la categoría
                    feeds = db.obtener_feeds_activos(categoria)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(get_message('feed_id_no_encontrado', feed_id=feed_id, categoria=categoria))
                        return
                except ValueError:
                    await message.channel.send(get_message('feed_id_numero'))
                    return
            else:
                # Verificar que la categoría exista
                categorias = db.obtener_categorias_disponibles()
                if not any(cat[0] == categoria for cat in categorias):
                    await message.channel.send(get_message('categoria_no_encontrada', categoria=categoria))
                    return
            
            # Realizar suscripción del canal
            canal = message.channel
            servidor = message.guild
            
            if db.suscribir_canal_categoria(
                str(canal.id), canal.name, str(servidor.id), servidor.name, categoria, feed_id
            ):
                if feed_id:
                    await message.channel.send(get_message('suscripcion_canal_exitosa_feed', feed_id=feed_id, categoria=categoria))
                else:
                    await message.channel.send(get_message('suscripcion_canal_exitosa_categoria', categoria=categoria))
            else:
                await message.channel.send("❌ Error al realizar suscripción del canal")
                
        except Exception as e:
            logger.exception(f"Error en cmd_canal_suscribir: {e}")
            await message.channel.send("❌ Error al suscribir el canal")
    
    async def cmd_canal_cancelar(self, message, args):
        """Cancela suscripción del canal actual a categoría/feed."""
        if not args:
            await message.channel.send("📝 Uso: `!vigiacanal cancelar <categoría> [feed_id]`")
            return
        
        # Verificar permisos
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send("❌ Necesitas permiso 'Gestionar Canales' para cancelar suscripción")
            return
        
        try:
            db = self._get_db()
            categoria = args[0].lower()
            feed_id = None
            
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send(get_message('feed_id_numero'))
                    return
            
            canal = message.channel
            
            if db.cancelar_suscripcion_canal(str(canal.id), categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ Suscripción cancelada al feed {feed_id} de '{categoria}'")
                else:
                    await message.channel.send(f"✅ Suscripción cancelada a la categoría '{categoria}'")
            else:
                await message.channel.send("❌ No se encontró esa suscripción para cancelar")
                
        except Exception as e:
            logger.exception(f"Error en cmd_canal_cancelar: {e}")
            await message.channel.send("❌ Error al cancelar suscripción del canal")
    
    async def cmd_canal_estado(self, message, args):
        """Muestra estado de suscripciones del canal actual."""
        try:
            db = self._get_db()
            canal = message.channel
            suscripciones = db.obtener_suscripciones_canal(str(canal.id))
            
            if not suscripciones:
                await message.channel.send("📭 Este canal no tiene suscripciones activas.")
                return
            
            embed = discord.Embed(
                title=f"📊 Suscripciones del Canal - #{canal.name}",
                color=discord.Color.orange(),
                timestamp=datetime.now()
            )
            
            suscripciones_por_categoria = {}
            for categoria, feed_id, fecha in suscripciones:
                if categoria not in suscripciones_por_categoria:
                    suscripciones_por_categoria[categoria] = []
                suscripciones_por_categoria[categoria].append(feed_id)
            
            for categoria, feeds in suscripciones_por_categoria.items():
                icono = self._get_icono_categoria(categoria)
                if any(f is not None for f in feeds):
                    # Feeds específicos
                    feeds_especificos = [f for f in feeds if f is not None]
                    valor = f"Feeds específicos: {', '.join(map(str, feeds_especificos))}"
                else:
                    # Toda la categoría
                    valor = "Todos los feeds de esta categoría"
                
                embed.add_field(
                    name=f"{icono} {categoria.title()}",
                    value=valor,
                    inline=False
                )
            
            embed.set_footer(text="Usa !vigiacanal cancelar <categoría> para cancelar")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_canal_estado: {e}")
            await message.channel.send("❌ Error obteniendo estado del canal")
    
    # ===== COMANDOS DE GESTIÓN DE PREMISAS (SUSCRIPCIONES CON IA) =====
    
    async def cmd_premisas(self, message, args):
        """Comando principal de gestión de premisas para suscripciones con IA."""
        if not args:
            # Si no hay subcomando, mostrar lista por defecto
            await self.cmd_premisas_listar(message, args)
            return
        
        subcomando = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []
        
        if subcomando == 'listar' or subcomando == 'list':
            await self.cmd_premisas_listar(message, subargs)
        elif subcomando == 'add':
            await self.cmd_premisas_add(message, subargs)
        elif subcomando == 'mod':
            await self.cmd_premisas_mod(message, subargs)
        else:
            await message.channel.send(f"❌ Subcomando '{subcomando}' no reconocido. Usa: list, add, mod")
    
    async def cmd_premisas_listar(self, message, args):
        """Lista todas las premisas del usuario (personalizadas o globales)."""
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            # Obtener premisas con contexto
            premisas, contexto = db.obtener_premisas_con_contexto(usuario_id)
            
            if not premisas:
                await message.channel.send("📭 No hay premisas configuradas.")
                return
            
            embed = discord.Embed(
                title=f"🎯 Tus Premisas ({contexto.title()})",
                description="Estas son las condiciones que hacen una noticia **CRÍTICA** para ti:",
                color=discord.Color.blue() if contexto == "personalizadas" else discord.Color.red(),
                timestamp=datetime.now()
            )
            
            for i, premisa in enumerate(premisas, 1):
                embed.add_field(
                    name=f"Premisa #{i}",
                    value=f"📍 {premisa}",
                    inline=False
                )
            
            if contexto == "personalizadas":
                embed.set_footer(text="Usa !vigia premisas add/mod para gestionar tus premisas")
            else:
                embed.set_footer(text="Usa !vigia premisas add para crear premisas personalizadas")
            
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_premisas_listar: {e}")
            await message.channel.send("❌ Error listando tus premisas")
    
    async def cmd_premisas_add(self, message, args):
        """Añade una nueva premisa si hay hueco (máximo 7)."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia premisas add \"texto de la nueva premisa\"`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            nueva_premisa = " ".join(args).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la premisa.")
                return
            
            success, mensaje = db.añadir_premisa_usuario(usuario_id, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error en cmd_premisas_add: {e}")
            await message.channel.send("❌ Error añadiendo premisa")
    
    async def cmd_premisas_mod(self, message, args):
        """Modifica una premisa específica por número."""
        if len(args) < 2:
            await message.channel.send("📝 Uso: `!vigia premisas mod <número> \"nueva premisa\"`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            # Parsear número
            try:
                indice = int(args[0])
            except ValueError:
                await message.channel.send("❌ El número debe ser un entero.")
                return
            
            nueva_premisa = " ".join(args[1:]).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la nueva premisa.")
                return
            
            success, mensaje = db.modificar_premisa_usuario(usuario_id, indice, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error en cmd_premisas_mod: {e}")
            await message.channel.send("❌ Error modificando premisa")
    
    async def cmd_premisas_añadir(self, message, args):
        """Añade una nueva premisa global (solo admins)."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia premisas añadir \"texto de la premisa\"`")
            return
        
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo administradores pueden gestionar premisas globales")
            return
        
        try:
            from agent_db import get_active_server_name
            server_name = get_active_server_name() or "default"
            premisas_manager = get_premisas_manager(server_name)
            
            nueva_premisa = " ".join(args).strip('"\'')
            
            if premisas_manager.añadir_premisa(nueva_premisa):
                await message.channel.send(f"✅ Premisa global añadida: \"{nueva_premisa}\"")
            else:
                await message.channel.send("⚠️ Esa premisa global ya existe")
                
        except Exception as e:
            logger.exception(f"Error en cmd_premisas_añadir: {e}")
            await message.channel.send("❌ Error añadiendo premisa global")
    
    async def cmd_premisas_eliminar(self, message, args):
        """Elimina una premisa global existente (solo admins)."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia premisas eliminar \"texto de la premisa\"`")
            return
        
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo administradores pueden gestionar premisas globales")
            return
        
        try:
            from agent_db import get_active_server_name
            server_name = get_active_server_name() or "default"
            premisas_manager = get_premisas_manager(server_name)
            
            premisa_a_eliminar = " ".join(args).strip('"\'')
            
            if premisas_manager.quitar_premisa(premisa_a_eliminar):
                await message.channel.send(f"🗑️ Premisa global eliminada: \"{premisa_a_eliminar}\"")
            else:
                await message.channel.send("⚠️ No se encontró esa premisa global")
                
        except Exception as e:
            logger.exception(f"Error en cmd_premisas_eliminar: {e}")
            await message.channel.send("❌ Error eliminando premisa global")
    
    async def cmd_mis_premisas(self, message, args):
        """Muestra las premisas personalizadas del usuario."""
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            premisas_usuario = db.obtener_premisas_usuario(usuario_id)
            
            if not premisas_usuario:
                await message.channel.send("📭 No tienes premisas personalizadas. Usarás las premisas globales.\nUsa `!vigia premisas configurar` para crear tus premisas personalizadas.")
                return
            
            embed = discord.Embed(
                title=f"🎯 Tus Premisas Personalizadas",
                description="Estas son tus condiciones **personales** para noticias críticas:",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            for i, premisa in enumerate(premisas_usuario, 1):
                embed.add_field(
                    name=f"Tu Premisa #{i}",
                    value=f"📍 {premisa}",
                    inline=False
                )
            
            embed.set_footer(text="Máximo 7 premisas personalizadas. Usa !vigia premisas configurar para modificarlas")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_mis_premisas: {e}")
            await message.channel.send("❌ Error obteniendo tus premisas")
    
    async def cmd_configurar_premisas(self, message, args):
        """Configura las premisas personalizadas del usuario."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia premisas configurar \"premisa1,premisa2,premisa3\"`\nMáximo 7 premisas, separadas por comas.")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            # Extraer y limpiar premisas
            texto_premisas = " ".join(args).strip('"\'')
            premisas_lista = [p.strip() for p in texto_premisas.split(',') if p.strip()]
            
            if len(premisas_lista) > 7:
                await message.channel.send("❌ Puedes tener máximo 7 premisas personalizadas.")
                return
            
            if not premisas_lista:
                await message.channel.send("❌ Debes proporcionar al menos una premisa.")
                return
            
            if db.actualizar_premisas_usuario(usuario_id, premisas_lista):
                await message.channel.send(f"✅ Tus premisas personalizadas han sido configuradas ({len(premisas_lista)} premisas).\nUsa `!vigia premisas mis_premisas` para verlas.")
            else:
                await message.channel.send("❌ Error al configurar tus premisas")
                
        except Exception as e:
            logger.exception(f"Error en cmd_configurar_premisas: {e}")
            await message.channel.send("❌ Error configurando tus premisas")
    
    def _get_bandera_pais(self, pais: str) -> str:
        """Obtiene bandera para país."""
        banderas = {
            'US': '🇺🇸',
            'ES': '🇪🇸',
            'UK': '🇬🇧',
            'MX': '🇲🇽',
            'AR': '🇦🇷',
            'FR': '🇫🇷',
            'DE': '🇩🇪',
            'IT': '🇮🇹',
            'BR': '🇧🇷',
            'CA': '🇨🇦'
        }
        return banderas.get(pais, '🌐')

# Registro de comandos - Solo los necesarios
COMANDOS_VIGIA = {
    'feeds': VigiaCommands.cmd_feeds,
    'categorias': VigiaCommands.cmd_categorias,
    'suscribir': VigiaCommands.cmd_suscribir,
    'cancelar': VigiaCommands.cmd_cancelar,
    'estado': VigiaCommands.cmd_estado,
    'general': VigiaCommands.cmd_general_suscribir,  # Suscripciones con IA
    'palabras': VigiaCommands.cmd_palabras_suscribir,
    'premisas': VigiaCommands.cmd_premisas,  # Gestión de premisas
    'mod': VigiaCommands.cmd_premisas_mod,  # Modificar premisa por número
}

# Registro de comandos de canal - Solo los necesarios
COMANDOS_VIGIA_CANAL = {
    'suscribir': VigiaCommands.cmd_canal_suscribir,
    'cancelar': VigiaCommands.cmd_canal_cancelar,
    'estado': VigiaCommands.cmd_canal_estado,
    'palabras': VigiaCommands.cmd_canal_palabras_suscribir,
    'premisas': VigiaCommands.cmd_canal_premisas,  # Gestión de premisas de canal
    'general': VigiaCommands.cmd_canal_general_suscribir,  # Suscripciones con IA para canal
}
