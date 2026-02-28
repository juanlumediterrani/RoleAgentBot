import discord
import asyncio
from datetime import datetime
from agent_logging import get_logger
from db_role_vigia import get_vigia_db_instance

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
                await message.channel.send("📭 No hay feeds configurados.")
                return
            
            embed = discord.Embed(
                title="📡 Feeds Disponibles",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            feeds_por_categoria = {}
            for feed in feeds:
                feed_id, nombre, url, categoria, pais, idioma, prioridad, palabras_clave = feed
                if categoria not in feeds_por_categoria:
                    feeds_por_categoria[categoria] = []
                feeds_por_categoria[categoria].append({
                    'id': feed_id, 'nombre': nombre, 'url': url,
                    'pais': pais, 'idioma': idioma, 'prioridad': prioridad
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
            await message.channel.send("❌ Error obteniendo feeds.")
    
    async def cmd_categorias(self, message, args):
        """Muestra categorías disponibles."""
        try:
            db = self._get_db()
            categorias = db.obtener_categorias_disponibles()
            
            if not categorias:
                await message.channel.send("📭 No hay categorías disponibles.")
                return
            
            embed = discord.Embed(
                title="📂 Categorías Disponibles",
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
            await message.channel.send("❌ Error obteniendo categorías.")
    
    async def cmd_suscribir(self, message, args):
        """Suscribe usuario a una categoría o feed específico."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia suscribir <categoría> [feed_id]`")
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
                        await message.channel.send(f"❌ Feed ID {feed_id} no encontrado en categoría '{categoria}'")
                        return
                except ValueError:
                    await message.channel.send("❌ Feed ID debe ser un número")
                    return
            else:
                # Verificar que la categoría exista
                categorias = db.obtener_categorias_disponibles()
                if not any(cat[0] == categoria for cat in categorias):
                    await message.channel.send(f"❌ Categoría '{categoria}' no encontrada. Usa `!vigia categorías`")
                    return
            
            # Realizar suscripción
            if db.suscribir_usuario_categoria(str(message.author.id), categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ Te has suscrito al feed {feed_id} de la categoría '{categoria}'")
                else:
                    await message.channel.send(f"✅ Te has suscrito a todas las noticias de '{categoria}'")
            else:
                await message.channel.send("❌ Error al realizar suscripción")
                
        except Exception as e:
            logger.exception(f"Error en cmd_suscribir: {e}")
            await message.channel.send("❌ Error al suscribirse")
    
    async def cmd_cancelar(self, message, args):
        """Cancela suscripción a categoría o feed."""
        if not args:
            await message.channel.send("📝 Uso: `!vigia cancelar <categoría> [feed_id]`")
            return
        
        try:
            db = self._get_db()
            categoria = args[0].lower()
            feed_id = None
            
            if len(args) > 1:
                try:
                    feed_id = int(args[1])
                except ValueError:
                    await message.channel.send("❌ Feed ID debe ser un número")
                    return
            
            if db.cancelar_suscripcion_categoria(str(message.author.id), categoria, feed_id):
                if feed_id:
                    await message.channel.send(f"✅ Suscripción cancelada al feed {feed_id} de '{categoria}'")
                else:
                    await message.channel.send(f"✅ Suscripción cancelada a la categoría '{categoria}'")
            else:
                await message.channel.send("❌ No se encontró esa suscripción para cancelar")
                
        except Exception as e:
            logger.exception(f"Error en cmd_cancelar: {e}")
            await message.channel.send("❌ Error al cancelar suscripción")
    
    async def cmd_estado(self, message, args):
        """Muestra estado de suscripciones del usuario."""
        try:
            db = self._get_db()
            suscripciones = db.obtener_suscripciones_usuario(str(message.author.id))
            
            if not suscripciones:
                await message.channel.send("📭 No tienes suscripciones activas.")
                return
            
            embed = discord.Embed(
                title=f"📊 Tus Suscripciones - {message.author.display_name}",
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
                await message.channel.send("❌ Error al agregar feed")
                
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
}
