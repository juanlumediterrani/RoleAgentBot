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
        """Suscribe usuario a una categoría o feed específico."""
        if not args:
            await message.channel.send(get_message('uso_suscribir'))
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
            
            # Realizar suscripción
            if db.suscribir_usuario_categoria(str(message.author.id), categoria, feed_id):
                if feed_id:
                    await message.channel.send(get_message('suscripcion_exitosa_feed', feed_id=feed_id, categoria=categoria))
                else:
                    await message.channel.send(get_message('suscripcion_exitosa_categoria', categoria=categoria))
            else:
                await message.channel.send(get_message('error_suscripcion'))
                
        except Exception as e:
            logger.exception(f"Error en cmd_suscribir: {e}")
            await message.channel.send(get_message('error_general', error=e))
    
    async def cmd_cancelar(self, message, args):
        """Cancela suscripción a categoría o feed."""
        if not args:
            await message.channel.send(get_message('uso_cancelar'))
            return
        
        try:
            db = self._get_db()
            categoria = args[0].lower()
            feed_id = None
            
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send(get_message('error_feed_id_invalido'))
                    return
            
            if db.cancelar_suscripcion_categoria(str(message.author.id), categoria, feed_id):
                if feed_id:
                    await message.channel.send(get_message('suscripcion_cancelada_feed', feed_id=feed_id, categoria=categoria))
                else:
                    await message.channel.send(get_message('suscripcion_cancelada_categoria', categoria=categoria))
            else:
                await message.channel.send(get_message('error_cancelacion'))
                
        except Exception as e:
            logger.exception(f"Error en cmd_cancelar: {e}")
            await message.channel.send(get_message('error_general', error=e))
    
    async def cmd_estado(self, message, args):
        """Muestra estado de suscripciones del usuario."""
        try:
            db = self._get_db()
            suscripciones = db.obtener_suscripciones_usuario(str(message.author.id))
            
            if not suscripciones:
                await message.channel.send(get_message('error_no_suscripciones'))
                return
            
            embed = discord.Embed(
                title=get_message('estado_titulo') + f" - {message.author.display_name}",
                color=discord.Color.purple(),
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
            
            embed.set_footer(text="Usa !vigia cancelar <categoría> para cancelar")
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error en cmd_estado: {e}")
            await message.channel.send("❌ Error obteniendo estado")
    
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
        """Suscribe a feeds generales con clasificación IA."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia general <categoría>`")
            return
        
        try:
            db = self._get_db()
            categoria = args[0].lower()
            
            # Verificar que existan feeds generales para esta categoría
            feeds = db.obtener_feeds_activos(categoria)
            feeds_generales = [f for f in feeds if f[8] == 'general']  # tipo_feed en posición 8
            
            if not feeds_generales:
                await message.channel.send(get_message('no_feeds_generales', categoria=categoria))
                return
            
            # Suscribir a feeds generales
            for feed in feeds_generales:
                feed_id = feed[0]
                if db.suscribir_usuario_categoria(str(message.author.id), categoria, feed_id):
                    await message.channel.send(f"✅ Suscrito a feeds generales de '{categoria}' con clasificación IA")
                else:
                    await message.channel.send(get_message('error_suscribir_generales'))
                    
        except Exception as e:
            logger.exception(f"Error en cmd_general_suscribir: {e}")
            await message.channel.send("❌ Error al suscribirse a feeds generales")
    
    async def cmd_palabras_suscribir(self, message, args):
        """Suscribe a palabras clave específicas."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia palabras \"palabra1,palabra2,palabra3\"`")
            return
        
        try:
            db = self._get_db()
            palabras_clave = " ".join(args).strip('"\'')
            
            if not palabras_clave:
                await message.channel.send(get_message('debes_proporcionar_palabras'))
                return
            
            if db.suscribir_palabras_clave(str(message.author.id), palabras_clave):
                await message.channel.send(f"✅ Suscrito a palabras clave: '{palabras_clave}'")
            else:
                await message.channel.send("❌ Error al suscribirse a palabras clave")
                
        except Exception as e:
            logger.exception(f"Error en cmd_palabras_suscribir: {e}")
            await message.channel.send("❌ Error al suscribirse a palabras clave")
    
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

# Registro de comandos
COMANDOS_VIGIA = {
    'feeds': VigiaCommands.cmd_feeds,
    'categorias': VigiaCommands.cmd_categorias,
    'suscribir': VigiaCommands.cmd_suscribir,
    'cancelar': VigiaCommands.cmd_cancelar,
    'estado': VigiaCommands.cmd_estado,
    'agregar_feed': VigiaCommands.cmd_agregar_feed,
    'general': VigiaCommands.cmd_general_suscribir,
    'palabras': VigiaCommands.cmd_palabras_suscribir,
    'cancelar_palabras': VigiaCommands.cmd_palabras_cancelar,
    'mixto': VigiaCommands.cmd_mixto_suscribir,
    'estado_palabras': VigiaCommands.cmd_estado_palabras,
}

# Registro de comandos de canal
COMANDOS_VIGIA_CANAL = {
    'suscribir': VigiaCommands.cmd_canal_suscribir,
    'cancelar': VigiaCommands.cmd_canal_cancelar,
    'estado': VigiaCommands.cmd_canal_estado,
    'palabras': VigiaCommands.cmd_canal_palabras_suscribir,
}
