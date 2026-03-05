import discord
import asyncio
import sys
import os
from datetime import datetime
from agent_logging import get_logger

from .db_role_news_watcher import get_news_watcher_db_instance
from .watcher_messages import get_message
from .premises_manager import get_premises_manager

logger = get_logger('vigia_commands')

class WatcherCommands:
    """Discord commands to manage the News Watcher role."""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_vigia = None
    
    def _get_db(self, server_name: str = None):
        """Get (and cache) the watcher DB instance."""
        if not self.db_vigia:
            from agent_db import get_active_server_name
            server_name = server_name or get_active_server_name() or "default"
            self.db_vigia = get_news_watcher_db_instance(server_name)
        return self.db_vigia

    def _normalize_category(self, categoria: str | None) -> str | None:
        if categoria is None:
            return None

        cat = str(categoria).strip().lower()
        if not cat:
            return cat

        aliases = {
            "international": "internacional",
            "economy": "economia",
            "technology": "tecnologia",
            "society": "sociedad",
            "politics": "politica",
            "sports": "deportes",
            "culture": "cultura",
            "science": "ciencia",
        }
        return aliases.get(cat, cat)
    
    async def cmd_feeds(self, message, args):
        """Show all available feeds."""
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
        """Completely clear all user subscriptions."""
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
            
            # If not confirmed, show confirmation message
            await message.channel.send(
                f"⚠️ **CONFIRMATION REQUIRED**\n"
                f"You are about to delete ALL of your '{tipo_actual}' subscriptions.\n"
                f"This action cannot be undone.\n"
                f"To confirm, use: `!watcher reset confirm`"
            )
            
        except Exception as e:
            logger.exception(f"Error en cmd_reset: {e}")
            await message.channel.send("❌ Error processing reset request")

    async def cmd_categories(self, message, args):
        """Show available categories."""
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
            
            embed.set_footer(text="Use !watcher subscribe <category> to receive news from that category")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_categories: {e}")
            await message.channel.send(get_message('error_general', error=e))

    async def cmd_subscribe(self, message, args):
        """Subscribe the user to a category or a specific feed (flat subscription)."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher subscribe <category> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = self._normalize_category(args[0])
            feed_id = None
            
            # Verificar si es un feed_id específico
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verificar que el feed exista y pertenezca a la categoría
                    feeds = db.obtener_feeds_activos(categoria)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(f"❌ Feed ID {feed_id} not found in category '{categoria}'")
                        return
                except ValueError:
                    await message.channel.send("❌ feed_id must be a number")
                    return
            else:
                # Verify category exists
                categorias = db.obtener_categorias_disponibles()
                if not any(cat[0] == categoria for cat in categorias):
                    await message.channel.send(f"❌ Category '{categoria}' not found")
                    return
            
            # Check current subscription type
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            
            # If already has flat subscription, block
            if tipo_actual == 'plana':
                await message.channel.send("ℹ️ You already have an active flat subscription. Use `!watcher unsubscribe <category>` first if you want to change.")
                return
            
            # If has other subscription types, block
            if tipo_actual in ['palabras', 'ia']:
                await message.channel.send(
                    f"⚠️ You have an active '{tipo_actual}' subscription. You can only have ONE subscription type at a time. Use `!watcher reset` to clear all subscriptions."
                )
                return
            
            # Create flat subscription
            if db.suscribir_usuario_categoria(usuario_id, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ Flat subscription created: Feed {feed_id} in category '{categoria}'")
                else:
                    await message.channel.send(f"✅ Flat subscription created: Category '{categoria}'")
            else:
                await message.channel.send("❌ Error creating flat subscription")
                
        except Exception as e:
            logger.exception(f"Error in cmd_subscribe: {e}")
            await message.channel.send("❌ Error processing subscription")

    async def cmd_unsubscribe(self, message, args):
        """Cancel a flat subscription for a category or feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher unsubscribe <category> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = self._normalize_category(args[0])
            feed_id = None
            
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send("❌ feed_id must be a number")
                    return
            
            if db.cancelar_suscripcion_categoria(usuario_id, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ Suscripción plana cancelada: Feed {feed_id} de '{categoria}'")
                else:
                    await message.channel.send(f"✅ Suscripción plana cancelada: Categoría '{categoria}'")
            else:
                await message.channel.send("❌ No tienes suscripción plana activa en esa categoría/feed")
                
        except Exception as e:
            logger.exception(f"Error in cmd_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling flat subscription")
    
    async def cmd_general_unsubscribe(self, message, args):
        """Cancel an AI (premises-based) subscription for a category/feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher general unsubscribe <category> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = self._normalize_category(args[0])
            feed_id = None
            
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send("❌ feed_id must be a number")
                    return
            
            if db.cancelar_suscripcion_categoria(usuario_id, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ AI subscription canceled: Feed {feed_id} in '{categoria}'")
                else:
                    await message.channel.send(f"✅ AI subscription canceled: Category '{categoria}'")
            else:
                await message.channel.send("❌ You don't have an active AI subscription for that category/feed")
                
        except Exception as e:
            logger.exception(f"Error in cmd_general_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling AI subscription")
    
    async def cmd_status(self, message, args):
        """Show the user's active subscription type and details."""
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            
            # Verificar tipo de suscripción actual
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            logger.info(f"DEBUG: Subscription type for {usuario_id}: {tipo_actual}")
            
            if not tipo_actual:
                await message.channel.send("📝 You don't have any active subscriptions")
                return
            
            # Mostrar información según el tipo
            if tipo_actual == 'plana':
                suscripciones = db.obtener_suscripciones_usuario(usuario_id)
                if suscripciones:
                    embed = discord.Embed(
                        title="📰 Active Flat Subscription",
                        description="You receive **all news** (with generated opinion)",
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
                                value=f"Entire category\nSince: {fecha}",
                                inline=False
                            )
                    
                    embed.set_footer(text="Use !watcher unsubscribe <category> to cancel")
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send("📝 You don't have an active flat subscription")
                    
            elif tipo_actual == 'palabras':
                suscripciones = db.obtener_suscripciones_palabras_usuario(usuario_id)
                if suscripciones:
                    embed = discord.Embed(
                        title="🔍 Active Keywords Subscription",
                        description="You receive **filtered news** matching your keywords",
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
                                value=f"Keywords: {palabras}",
                                inline=False
                            )
                    
                    embed.set_footer(text="Use !watcher keywords unsubscribe <category> to cancel")
                    await message.channel.send(embed=embed)
                else:
                    await message.channel.send("📝 You don't have an active keywords subscription")
                    
            elif tipo_actual == 'ia':
                suscripciones = db.obtener_suscripciones_ia_usuario(usuario_id)
                logger.info(f"DEBUG: Suscripciones IA encontradas: {suscripciones}")
                if suscripciones:
                    embed = discord.Embed(
                        title="🤖 Active AI Subscription",
                        description="You receive **critical news** analyzed using your premises",
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
                    
                    embed.set_footer(text="Use !watcher general unsubscribe <category> to cancel")
                    await message.channel.send(embed=embed)
                else:
                    logger.warning(f"DEBUG: Inconsistencia detectada - tipo='ia' pero no hay suscripciones IA para usuario {usuario_id}")
                    await message.channel.send("📝 You don't have an active AI subscription")
                    
        except Exception as e:
            logger.exception(f"Error in cmd_status: {e}")
            await message.channel.send("❌ Error showing subscription status")
    
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
    
    async def cmd_general_subscribe(self, message, args):
        """Subscribe with AI (premises-based) to a category/feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher general <category> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = self._normalize_category(args[0])
            feed_id = None
            
            # Verificar si es un feed_id específico
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verificar que el feed exista y pertenezca a la categoría
                    feeds = db.obtener_feeds_activos(categoria)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(f"❌ Feed ID {feed_id} not found in category '{categoria}'")
                        return
                except ValueError:
                    await message.channel.send("❌ feed_id must be a number")
                    return
            else:
                # Verify category exists
                categorias = db.obtener_categorias_disponibles()
                if not any(cat[0] == categoria for cat in categorias):
                    await message.channel.send(f"❌ Category '{categoria}' not found")
                    return
            
            # Check current subscription type
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            
            # If already has AI subscription, block
            if tipo_actual == 'ia':
                await message.channel.send("ℹ️ You already have an active AI subscription. Use `!watcher general unsubscribe <category>` first if you want to change.")
                return
            
            # If has other subscription types, block
            if tipo_actual in ['plana', 'palabras']:
                await message.channel.send(
                    f"⚠️ You have an active '{tipo_actual}' subscription. You can only have ONE subscription type at a time. Use `!watcher reset` to clear all subscriptions."
                )
                return
            
            # Ensure the user has premises configured
            premisas, contexto = db.obtener_premisas_con_contexto(usuario_id)
            if not premisas:
                await message.channel.send("⚠️ You have no premises configured. Use `!watcher premises add <premise>` before subscribing with AI.")
                return
            
            # Create AI subscription (store user premises)
            premisas_str = ",".join(premisas) if premisas else ""
            if db.suscribir_usuario_categoria_ia(usuario_id, categoria, feed_id, premisas_str):
                if feed_id:
                    await message.channel.send(f"🤖 **AI subscription** to feed {feed_id} in '{categoria}' - I will analyze critical news using your premises")
                else:
                    await message.channel.send(f"🤖 **AI subscription** to '{categoria}' - I will analyze critical news using your premises")
            else:
                await message.channel.send("❌ Error creating AI subscription")
                
        except Exception as e:
            logger.exception(f"Error in cmd_general_subscribe: {e}")
            await message.channel.send("❌ Error processing AI subscription")
    
    async def cmd_keywords_subscribe(self, message, args):
        """Keywords command.

        Supported forms:
        - !watcher keywords "kw1,kw2" [category] [feed_id]
        - !watcher keywords add <keyword>
        - !watcher keywords list
        - !watcher keywords mod <number> "new keyword"
        - !watcher keywords subscribe <category> [feed_id]  (use saved keywords)
        - !watcher keywords unsubscribe <category>
        """

        if not args:
            await message.channel.send(
                "📝 Usage: `!watcher keywords \"kw1,kw2\" [category] [feed_id]`\n"
                "Or: `!watcher keywords add|list|mod|subscribe|unsubscribe ...`"
            )
            return

        sub = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []

        if sub == "add":
            await self.cmd_keywords_add(message, subargs)
            return
        if sub == "list":
            await self.cmd_keywords_list(message, subargs)
            return
        if sub == "mod":
            await self.cmd_keywords_mod(message, subargs)
            return
        if sub == "subscribe":
            await self.cmd_keywords_subscribe_existing(message, subargs)
            return
        if sub == "unsubscribe":
            await self.cmd_keywords_unsubscribe(message, subargs)
            return

        # Default: treat first arg as "kw1,kw2" payload
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)

            palabras_clave = args[0].strip('"\'')
            categoria = None
            feed_id = None

            if len(args) > 1:
                categoria = self._normalize_category(args[1])
                if len(args) > 2:
                    try:
                        feed_id = int(args[2])
                        feeds = db.obtener_feeds_activos(categoria)
                        feed_existente = any(f[0] == feed_id for f in feeds)
                        if not feed_existente:
                            await message.channel.send(f"❌ Feed ID {feed_id} not found in category '{categoria}'")
                            return
                    except ValueError:
                        await message.channel.send("❌ feed_id must be a number")
                        return
                else:
                    categorias = db.obtener_categorias_disponibles()
                    if not any(cat[0] == categoria for cat in categorias):
                        await message.channel.send(f"❌ Category '{categoria}' not found")
                        return

            if not palabras_clave:
                await message.channel.send("❌ You must provide keywords")
                return

            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            if tipo_actual == 'palabras':
                await message.channel.send(
                    "ℹ️ You already have an active keywords subscription. Use `!watcher keywords unsubscribe <category>` first if you want to change."
                )
                return
            if tipo_actual in ['plana', 'ia']:
                await message.channel.send(
                    f"⚠️ You have an active '{tipo_actual}' subscription. You can only have ONE subscription type at a time. Use `!watcher reset` to clear all subscriptions."
                )
                return

            if db.suscribir_palabras_clave(usuario_id, palabras_clave, None, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"🔍 **Keywords subscription** to feed {feed_id} in '{categoria}' - Searching: '{palabras_clave}'")
                elif categoria:
                    await message.channel.send(f"🔍 **Keywords subscription** to '{categoria}' - Searching: '{palabras_clave}'")
                else:
                    await message.channel.send(f"🔍 **Global keywords subscription** - Searching: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error subscribing to keywords")

        except Exception as e:
            logger.exception(f"Error in cmd_keywords_subscribe: {e}")
            await message.channel.send("❌ Error subscribing to keywords")
    
    async def cmd_keywords_add(self, message, args):
        """Add a keyword to the user's saved keyword list."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher keywords add <keyword>`")
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
            logger.exception(f"Error in cmd_keywords_add: {e}")
            await message.channel.send("❌ Error al añadir palabra clave")
    
    async def cmd_keywords_list(self, message, args):
        """List the user's saved keywords."""
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
            
            embed.set_footer(text="Use !watcher keywords add <keyword> to add more")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_list: {e}")
            await message.channel.send("❌ Error al mostrar palabras clave")
    
    async def cmd_keywords_mod(self, message, args):
        """Modify a saved keyword by index."""
        if len(args) < 2:
            await message.channel.send("📝 Usage: `!watcher keywords mod <number> \"new keyword\"`")
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
            logger.exception(f"Error in cmd_keywords_mod: {e}")
            await message.channel.send("❌ Error al modificar palabra clave")
    
    async def cmd_keywords_subscribe_existing(self, message, args):
        """Subscribe to a category/feed using the user's existing saved keywords."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher keywords subscribe <category> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = self._normalize_category(args[0])
            feed_id = None
            
            # Ensure the user has saved keywords
            palabras = db.obtener_palabras_usuario(usuario_id)
            if not palabras:
                await message.channel.send("❌ You have no saved keywords. Use `!watcher keywords add <keyword>` first")
                return
            
            # Verificar si es un feed_id específico
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                    # Verificar que el feed exista y pertenezca a la categoría
                    feeds = db.obtener_feeds_activos(categoria)
                    feed_existente = any(f[0] == feed_id for f in feeds)
                    if not feed_existente:
                        await message.channel.send(f"❌ Feed ID {feed_id} not found in category '{categoria}'")
                        return
                except ValueError:
                    await message.channel.send("❌ feed_id must be a number")
                    return
            else:
                # Verify category exists
                categorias = db.obtener_categorias_disponibles()
                if not any(cat[0] == categoria for cat in categorias):
                    await message.channel.send(f"❌ Category '{categoria}' not found")
                    return
            
            # Verificar tipo de suscripción actual del usuario
            tipo_actual = db.verificar_tipo_suscripcion_usuario(usuario_id)
            
            # If already has keywords subscription, block
            if tipo_actual == 'palabras':
                await message.channel.send("ℹ️ You already have an active keywords subscription. Use `!watcher keywords unsubscribe <category>` first if you want to change.")
                return
            
            # If has other subscription types, block
            if tipo_actual in ['plana', 'ia']:
                await message.channel.send(
                    f"⚠️ You have an active '{tipo_actual}' subscription. You can only have ONE subscription type at a time. Use `!watcher reset` to clear all subscriptions."
                )
                return
            
            # Create keywords subscription
            if db.suscribir_palabras_clave(usuario_id, palabras, None, categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"🔍 **Keywords subscription** to feed {feed_id} in '{categoria}' - Searching: '{palabras}'")
                else:
                    await message.channel.send(f"🔍 **Keywords subscription** to '{categoria}' - Searching: '{palabras}'")
            else:
                await message.channel.send("❌ Error subscribing to keywords")
                
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_subscribe_existing: {e}")
            await message.channel.send("❌ Error subscribing to keywords")
    
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
    
    async def cmd_keywords_unsubscribe(self, message, args):
        """Cancel a user's keywords subscription for a category."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher keywords unsubscribe <category>`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            categoria = self._normalize_category(args[0])
            
            if db.cancelar_suscripcion_palabras_usuario(usuario_id, categoria):
                await message.channel.send(f"✅ Keywords subscription canceled for '{categoria}'")
            else:
                await message.channel.send(f"❌ You don't have a keywords subscription in '{categoria}'")
                
        except Exception as e:
            logger.exception(f"Error in cmd_keywords_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling subscription")
    
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
            categoria = self._normalize_category(args[0])
            
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
    
    async def cmd_channel_keywords(self, message, args):
        """Subscribe the current channel to keywords."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel keywords \"kw1,kw2\"`")
            return

        if args and args[0].lower() == "unsubscribe":
            await self.cmd_channel_keywords_unsubscribe(message, args[1:] if len(args) > 1 else [])
            return
        
        # Verificar permisos
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send("❌ You need the 'Manage Channels' permission to subscribe the channel")
            return
        
        try:
            db = self._get_db()
            palabras_clave = " ".join(args).strip('"\'')
            canal = message.channel
            
            if db.suscribir_palabras_clave(str(message.author.id), palabras_clave, str(canal.id)):
                await message.channel.send(f"✅ Channel subscribed to keywords: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error subscribing channel to keywords")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_keywords: {e}")
            await message.channel.send("❌ Error subscribing channel to keywords")
    
    async def cmd_channel_keywords_unsubscribe(self, message, args):
        """Cancel a channel keywords subscription."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel keywords unsubscribe \"kw1,kw2\"`")
            return
        
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Only administrators can manage channel subscriptions")
            return
        
        try:
            db = self._get_db()
            canal = message.channel
            palabras_clave = " ".join(args).strip('"\'')
            
            if db.cancelar_suscripcion_palabras_canal(str(canal.id), palabras_clave):
                await message.channel.send(f"✅ Channel keywords subscription canceled: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error canceling channel keywords subscription")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_keywords_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling channel keywords subscription")
    
    # ===== COMANDOS DE PREMISAS PARA CANALES =====
    
    async def cmd_channel_premises(self, message, args):
        """Channel premises management command."""
        if not args:
            # Si no hay subcomando, mostrar lista por defecto
            await self.cmd_channel_premises_list(message, args)
            return
        
        subcomando = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []
        
        if subcomando == 'listar' or subcomando == 'list':
            await self.cmd_channel_premises_list(message, subargs)
        elif subcomando == 'add':
            await self.cmd_channel_premises_add(message, subargs)
        elif subcomando == 'mod':
            await self.cmd_channel_premises_mod(message, subargs)
        else:
            await message.channel.send(f"❌ Subcomando '{subcomando}' no reconocido. Usa: list, add, mod")
    
    async def cmd_channel_premises_list(self, message, args):
        """List channel premises (custom or global)."""
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
                embed.set_footer(text="Use !watcherchannel premises add/mod to manage channel premises")
            else:
                embed.set_footer(text="Use !watcherchannel premises add to create custom channel premises")
            
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_list: {e}")
            await message.channel.send("❌ Error listing channel premises")
    
    async def cmd_channel_premises_add(self, message, args):
        """Add a new premise to the channel (max 7)."""
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo administradores pueden gestionar premisas del canal")
            return
        
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel premises add \"premise text\"`")
            return
        
        try:
            db = self._get_db()
            canal = message.channel
            canal_id = str(canal.id)
            nueva_premisa = " ".join(args).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la premisa.")
                return
            
            success, mensaje = db.add_premise_canal(canal_id, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_premises_add: {e}")
            await message.channel.send("❌ Error adding channel premise")
    
    async def cmd_channel_premises_mod(self, message, args):
        """Modify a specific channel premise by index."""
        # Verificar permisos de admin
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo administradores pueden gestionar premisas del canal")
            return
        
        if len(args) < 2:
            await message.channel.send("📝 Usage: `!watcherchannel premises mod <number> \"new premise\"`")
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
            logger.exception(f"Error in cmd_channel_premises_mod: {e}")
            await message.channel.send("❌ Error modifying channel premise")
    
    async def cmd_channel_general_subscribe(self, message, args):
        """AI subscription for a channel: analyze news using channel premises."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel general <category> [feed_id]`")
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
            categoria = self._normalize_category(args[0])
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
                await message.channel.send("⚠️ This channel has no premises configured. Use `!watcherchannel premises add \"premise\"` before subscribing with AI.")
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
            logger.exception(f"Error in cmd_channel_general_subscribe: {e}")
            await message.channel.send("❌ Error processing channel AI subscription")
    
    async def cmd_channel_general_unsubscribe(self, message, args):
        """Cancel a channel AI subscription for category/feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel general unsubscribe <category> [feed_id]`")
            return
        
        try:
            # Verificar permisos de admin
            if not message.author.guild_permissions.administrator:
                await message.channel.send("❌ Solo administradores pueden cancelar suscripciones de canal")
                return
            
            db = self._get_db()
            canal_id = str(message.channel.id)
            categoria = self._normalize_category(args[0])
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
            logger.exception(f"Error in cmd_channel_general_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling channel AI subscription")
    
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
    
    async def cmd_channel_subscribe(self, message, args):
        """Subscribe the current channel to a category or feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel subscribe <category> [feed_id]`")
            return
        
        # Verificar permisos (requiere manage channel)
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send("❌ You need the 'Manage Channels' permission to subscribe the channel")
            return
        
        try:
            db = self._get_db()
            categoria = self._normalize_category(args[0])
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
                await message.channel.send("❌ Error creating channel subscription")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_subscribe: {e}")
            await message.channel.send("❌ Error subscribing the channel")
    
    async def cmd_channel_unsubscribe(self, message, args):
        """Cancel the current channel subscription for a category/feed."""
        if not args:
            await message.channel.send("📝 Usage: `!watcherchannel unsubscribe <category> [feed_id]`")
            return
        
        # Verificar permisos
        if not message.author.guild_permissions.manage_channels:
            await message.channel.send("❌ You need the 'Manage Channels' permission to cancel subscriptions")
            return
        
        try:
            db = self._get_db()
            categoria = self._normalize_category(args[0])
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
                    await message.channel.send(f"✅ Subscription canceled for feed {feed_id} in '{categoria}'")
                else:
                    await message.channel.send(f"✅ Subscription canceled for category '{categoria}'")
            else:
                await message.channel.send("❌ No matching subscription found to cancel")
                
        except Exception as e:
            logger.exception(f"Error in cmd_channel_unsubscribe: {e}")
            await message.channel.send("❌ Error canceling channel subscription")
    
    async def cmd_channel_status(self, message, args):
        """Show current channel subscription status."""
        try:
            db = self._get_db()
            canal = message.channel
            suscripciones = db.obtener_suscripciones_canal(str(canal.id))
            
            if not suscripciones:
                await message.channel.send("📭 This channel has no active subscriptions.")
                return
            
            embed = discord.Embed(
                title=f"📊 Channel Subscriptions - #{canal.name}",
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
                    valor = "All feeds in this category"
                
                embed.add_field(
                    name=f"{icono} {categoria.title()}",
                    value=valor,
                    inline=False
                )
            
            embed.set_footer(text="Use !watcherchannel unsubscribe <category> to cancel")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error in cmd_channel_status: {e}")
            await message.channel.send("❌ Error getting channel status")
    
    # ===== COMANDOS DE GESTIÓN DE PREMISAS (SUSCRIPCIONES CON IA) =====
    
    async def cmd_premises(self, message, args):
        """Premises management command for AI subscriptions."""
        if not args:
            # Si no hay subcomando, mostrar lista por defecto
            await self.cmd_premises_list(message, args)
            return
        
        subcomando = args[0].lower()
        subargs = args[1:] if len(args) > 1 else []
        
        if subcomando == 'listar' or subcomando == 'list':
            await self.cmd_premises_list(message, subargs)
        elif subcomando == 'add':
            await self.cmd_premises_add(message, subargs)
        elif subcomando == 'mod':
            await self.cmd_premises_mod(message, subargs)
        else:
            await message.channel.send(f"❌ Subcomando '{subcomando}' no reconocido. Usa: list, add, mod")
    
    async def cmd_premises_list(self, message, args):
        """List all user premises (custom or global)."""
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
            logger.exception(f"Error in cmd_premises_list: {e}")
            await message.channel.send("❌ Error listing your premises")
    
    async def cmd_premises_add(self, message, args):
        """Add a new premise (max 7)."""
        if not args:
            await message.channel.send("📝 Usage: `!watcher premises add \"premise text\"`")
            return
        
        try:
            db = self._get_db()
            usuario_id = str(message.author.id)
            nueva_premisa = " ".join(args).strip('"\'')
            
            if not nueva_premisa:
                await message.channel.send("❌ Debes proporcionar el texto de la premisa.")
                return
            
            success, mensaje = db.add_premise_usuario(usuario_id, nueva_premisa)
            
            if success:
                await message.channel.send(f"✅ {mensaje}")
            else:
                await message.channel.send(f"❌ {mensaje}")
                
        except Exception as e:
            logger.exception(f"Error in cmd_premises_add: {e}")
            await message.channel.send("❌ Error adding premise")
    
    async def cmd_premises_mod(self, message, args):
        """Modify a premise by index."""
        if len(args) < 2:
            await message.channel.send("📝 Usage: `!watcher premises mod <number> \"new premise\"`")
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
            logger.exception(f"Error in cmd_premises_mod: {e}")
            await message.channel.send("❌ Error modifying premise")
    
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
            premises_manager = get_premises_manager(server_name)
            
            nueva_premisa = " ".join(args).strip('"\'')
            
            if premises_manager.add_premise(nueva_premisa):
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
            premises_manager = get_premises_manager(server_name)
            
            premisa_a_eliminar = " ".join(args).strip('"\'')
            
            if premises_manager.remove_premise(premisa_a_eliminar):
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


