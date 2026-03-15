import discord
import asyncio
import re
import yt_dlp
import sys
import os
import json
from urllib.parse import urlparse
from agent_logging import get_logger
from agent_engine import PERSONALIDAD

# Asegurar que el path del directorio mc esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = get_logger('mc_commands')


def _load_mc_answers() -> dict:
    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        config_path = os.path.join(project_root, "agent_config.json")
        with open(config_path, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        personality_rel = agent_cfg.get("personality", "")
        answers_path = os.path.join(project_root, os.path.dirname(personality_rel), "answers.json")
        with open(answers_path, encoding="utf-8") as f:
            return json.load(f).get("discord", {})
    except Exception:
        return {}

class MCCommands:
    """Comandos del MC (Master of Ceremonies) para música en Discord."""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.voice_clients = {}  # Almacenar clientes de voz por servidor
        self._playing_next = False  # Flag para evitar duplicaciones
        self.now_playing = {}    # Almacenar canción actual por servidor
        self.queues = {}          # Almacenar colas por servidor
        self._message_callback = None  # Callback para redirigir mensajes
    
    def set_message_callback(self, callback):
        """Establece un callback para redirigir mensajes (usado por Canvas)."""
        self._message_callback = callback
    
    def clear_message_callback(self):
        """Limpia el callback de mensajes."""
        self._message_callback = None
    
    async def _send_message(self, channel, content=None, embed=None, **kwargs):
        """Envía un mensaje, usando el callback si está disponible."""
        if self._message_callback:
            # Usar callback para redirigir al Canvas
            if embed:
                # Para embeds, convertir a texto para el callback
                embed_text = f"**{embed.title}**\n" if embed.title else ""
                if embed.description:
                    embed_text += embed.description
                for field in embed.fields:
                    embed_text += f"\n**{field.name}**: {field.value}"
                await self._message_callback(embed_text, **kwargs)
            else:
                await self._message_callback(content, **kwargs)
        else:
            # Enviar normalmente al canal
            if embed:
                await channel.send(embed=embed, **kwargs)
            else:
                await channel.send(content, **kwargs)
    
    def get_mc_message(self, key, default=None, **kwargs):
        """Obtiene mensaje personalizado del MC desde la personalidad."""
        try:
            role_cfg = _load_mc_answers().get("mc_messages", {})
            message = role_cfg.get(key)
            
            # Si no hay mensaje en personalidad, usar fallback por defecto
            if message is None:
                fallbacks = {
                    'queue_end_disconnect': "🎵 Fin de la cola. Me desconectaré en 5 minutos si no se agregan más canciones.",
                    'inactive_disconnect': "👋 Desconectado por inactividad.",
                    'timeout_connecting': "❌ **Timeout al conectar al canal de voz. Intenta de nuevo.**",
                    'voice_connection_error': "❌ **Error de conexión de voz. Intenta de nuevo.**",
                    'discord_connect_error': "❌ **Error de Discord al conectar.**",
                    'general_connect_error': "❌ **No pude conectarme al canal de voz.**",
                    'volume_range_error': "🎵 **El volumen debe ser un número entre 0 y 100.**",
                    'volume_adjust_error': "❌ **No pude ajustar el volumen.**",
                    'dm_help_error': "📭 **No puedo enviarte mensaje privado.**\n**Por favor, activa los DMs de servidores o usa otro canal.**",
                    'dm_help_blocked': "📭 **No puedo enviarte mensaje privado.**\n**Por favor, activa los DMs de servidores o usa otro canal.**",
                    'help_dm_error': "❌ **Error al enviar ayuda por mensaje privado.**",
                    'no_voice_connection': "❌ **Error: No hay conexión de voz establecida.**",
                    'voice_disconnected': "❌ **Error crítico: Conexión de voz inválida.**\n**El bot necesita reconectarse al canal.**",
                    'critical_voice_error': "❌ **Error crítico: Conexión de voz inválida.**\n**El bot necesita reconectarse al canal.**",
                    'discord_voice_error': "❌ **Error de Discord: {error}**",
                    'unexpected_error': "❌ **Error inesperado: {error_type}**",
                    'next_song_error': "❌ **Error reproduciendo la siguiente canción.**",
                    'connected_to_voice': "🎤 **Conectado a {channel_name}**",
                    'no_dm_permission': "📭 **No puedo enviarte mensaje privado.**\n**Por favor, activa los DMs de servidores o usa otro canal.**"
                }
                message = fallbacks.get(key, default or f"Mensaje no encontrado: {key}")
            
            # Reemplazar variables si se proporcionan
            if kwargs:
                try:
                    message = message.format(**kwargs)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Error formateando mensaje {key}: {e}")
            return message
        except Exception as e:
            logger.warning(f"Error obteniendo mensaje MC {key}: {e}")
            return default or f"Error: {key}"
        
    async def cmd_play(self, message, args):
        """Reproduce una canción o la agrega a la cola."""
        if not args:
            await self._send_message(message.channel, "🎵 **Uso:** `!mc play <nombre o URL de la canción>`")
            return
        
        query = ' '.join(args)
        server_id = str(message.guild.id)
        
        # Verificar que el usuario esté en un canal de voz
        if not message.author.voice:
            await self._send_message(message.channel, self.get_mc_message("not_in_voice", "🎤 **Debes estar en un canal de voz para usar este comando.**"))
            return
        
        voice_channel = message.author.voice.channel
        
        # Conectar al canal de voz si no está conectado
        voice_client = None
        try:
            if server_id not in self.voice_clients:
                logger.info(f"MC: Conectando al canal {voice_channel.name}...")
                logger.info(f"MC: Iniciando conexión de voz (timeout: 60s)...")
                voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=60.0)
                logger.info(f"MC: ✅ Conexión exitosa a {voice_channel.name}")
                self.voice_clients[server_id] = voice_client
                await self._send_message(message.channel, self.get_mc_message("voice_join_empty", f"🎤 **Conectado a {voice_channel.name}**"))
            elif not self.voice_clients[server_id].is_connected():
                logger.info(f"MC: Reconectando al canal {voice_channel.name}...")
                logger.info(f"MC: Iniciando reconexión de voz (timeout: 60s)...")
                voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=60.0)
                logger.info(f"MC: ✅ Reconexión exitosa a {voice_channel.name}")
                self.voice_clients[server_id] = voice_client
                await self._send_message(message.channel, f"🎤 **Reconectado a {voice_channel.name}**")
            else:
                voice_client = self.voice_clients[server_id]
                # Verificar si está en el canal correcto
                if voice_client.channel != voice_channel:
                    logger.info(f"MC: Moviendo de {voice_client.channel.name} a {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                    await self._send_message(message.channel, f"🎤 **Movido a {voice_channel.name}**")
        except asyncio.TimeoutError:
            logger.error(f"MC: Timeout al conectar a {voice_channel.name}")
            # No enviar mensaje de timeout si ya estamos conectados y reproduciendo
            if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
                await self._send_message(message.channel, self.get_mc_message('timeout_connecting'))
            return
        except discord.errors.ClientException as e:
            if "Already connected to a voice channel" in str(e):
                # Ya está conectado, obtener el cliente de voz existente
                voice_client = message.guild.voice_client
                if voice_client:
                    logger.info(f"MC: Ya conectado a {voice_channel.name} (usando cliente existente)")
                    self.voice_clients[server_id] = voice_client
                    await self._send_message(message.channel, f"🎤 **Conectado a {voice_channel.name}**")
                else:
                    logger.error(f"MC: Error: Discord dice que está conectado pero no hay cliente de voz")
                    await self._send_message(message.channel, self.get_mc_message('voice_connection_error'))
                    return
            else:
                logger.exception(f"MC: Error Discord conectando: {e}")
                await self._send_message(message.channel, self.get_mc_message('discord_connect_error'))
                return
        except Exception as e:
            logger.exception(f"MC: Error general conectando a {voice_channel.name}: {e}")
            await self._send_message(message.channel, self.get_mc_message('general_connect_error'))
            return
        
        # Buscar la canción
        await self._send_message(message.channel, "🔍 **Buscando canción...**")
        
        try:
            # Configurar yt-dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'noplaylist': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Determinar si es URL o búsqueda
                if urlparse(query).scheme in ('http', 'https'):
                    info = ydl.extract_info(query, download=False)
                else:
                    info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
                
                title = info.get('title', 'Título desconocido')
                url = info.get('webpage_url', query)
                duration = info.get('duration', 0)
                artist = info.get('uploader', 'Artista desconocido')
                
                # Formatear duración
                if duration:
                    minutes, seconds = divmod(duration, 60)
                    hours, minutes = divmod(minutes, 60)
                    if hours:
                        duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                    else:
                        duration_str = f"{minutes}:{seconds:02d}"
                else:
                    duration_str = "Desconocida"
                
                # Obtener instancia de BD
                from db_role_mc import get_mc_db_instance
                db_mc = get_mc_db_instance(server_id)
                
                # Agregar a la cola en BD (al principio para play inmediato)
                db_mc.agregar_cancion_queue(
                    server_id, str(message.channel.id), str(message.author.id),
                    title, url, duration_str, artist, posicion=0
                )
                
                # Detener canción actual si hay una y reproducir la nueva
                if server_id in self.voice_clients and self.voice_clients[server_id].is_playing():
                    logger.info(f"MC: Deteniendo canción actual en servidor {server_id}")
                    self.voice_clients[server_id].stop()
                
                # Verificar estado de la conexión justo antes de reproducir
                if server_id in self.voice_clients:
                    vc = self.voice_clients[server_id]
                    logger.info(f"MC: Estado antes de reproducir - Conectado: {vc.is_connected()}, Reproduciendo: {vc.is_playing()}, Canal: {vc.channel}")
                
                # Reproducir inmediatamente
                logger.info(f"MC: Iniciando reproducción para '{title}' en servidor {server_id}")
                await self._play_next(server_id, message.channel)
                
        except Exception as e:
            logger.exception(f"Error buscando canción: {e}")
            await self._send_message(message.channel, self.get_mc_message("play_error", "❌ **No pude encontrar la canción.**"))
    
    async def cmd_add(self, message, args):
        """Agrega una canción al final de la cola."""
        if not args:
            await self._send_message(message.channel, "🎵 **Uso:** `!mc add <nombre o URL de la canción>`")
            return
        
        query = ' '.join(args)
        server_id = str(message.guild.id)
        
        # Verificar que el usuario esté en un canal de voz
        if not message.author.voice:
            await self._send_message(message.channel, "🎤 **Debes estar en un canal de voz para usar este comando.**")
            return
        
        voice_channel = message.author.voice.channel
        
        # Conectar al canal de voz si no está conectado
        voice_client = None
        try:
            if server_id not in self.voice_clients:
                logger.info(f"MC: Conectando al canal {voice_channel.name}...")
                voice_client = await voice_channel.connect()
                self.voice_clients[server_id] = voice_client
                await self._send_message(message.channel, f"🎤 **Conectado a {voice_channel.name}**")
            elif not self.voice_clients[server_id].is_connected():
                logger.info(f"MC: Reconectando al canal {voice_channel.name}...")
                voice_client = await voice_channel.connect()
                self.voice_clients[server_id] = voice_client
                await self._send_message(message.channel, f"🎤 **Reconectado a {voice_channel.name}**")
            else:
                voice_client = self.voice_clients[server_id]
                # Verificar si está en el canal correcto
                if voice_client.channel != voice_channel:
                    logger.info(f"MC: Moviendo de {voice_client.channel.name} a {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                    await self._send_message(message.channel, f"🎤 **Movido a {voice_channel.name}**")
        except discord.errors.ClientException as e:
            if "Already connected to a voice channel" in str(e):
                # Ya está conectado, obtener el cliente de voz existente
                voice_client = message.guild.voice_client
                if voice_client:
                    logger.info(f"MC: Ya conectado a {voice_channel.name} (usando cliente existente)")
                    self.voice_clients[server_id] = voice_client
                else:
                    logger.error(f"MC: Error: Discord dice que está conectado pero no hay cliente de voz")
                    await self._send_message(message.channel, self.get_mc_message('voice_connection_error'))
                    return
            else:
                logger.exception(f"MC: Error Discord conectando: {e}")
                await self._send_message(message.channel, self.get_mc_message('discord_connect_error'))
                return
        except Exception as e:
            logger.exception(f"MC: Error general conectando a {voice_channel.name}: {e}")
            await self._send_message(message.channel, self.get_mc_message('general_connect_error'))
            return
        
        # Buscar la canción
        await self._send_message(message.channel, "🔍 **Buscando canción...**")
        
        try:
            # Configurar yt-dlp
            ydl_opts = {
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch',
                'source_address': '0.0.0.0'
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                
                if 'entries' in info:
                    # Playlist, tomar el primer video
                    info = info['entries'][0]
                
                title = info.get('title', 'Desconocido')
                url = info.get('webpage_url', info.get('url', ''))
                artist = info.get('uploader', 'Desconocido')
                duration = info.get('duration')
                
                if duration:
                    minutes, seconds = divmod(duration, 60)
                    hours, minutes = divmod(minutes, 60)
                    if hours:
                        duration_str = f"{hours}:{minutes:02d}:{seconds:02d}"
                    else:
                        duration_str = f"{minutes}:{seconds:02d}"
                else:
                    duration_str = "Desconocida"
                
                # Obtener instancia de BD
                from db_role_mc import get_mc_db_instance
                db_mc = get_mc_db_instance(server_id)
                
                # Agregar a la cola en BD (al final)
                db_mc.agregar_cancion_queue(
                    server_id, str(message.channel.id), str(message.author.id),
                    title, url, duration_str, artist, posicion=-1
                )
                
                # Siempre mostrar mensaje de agregado y NUNCA interrumpir
                await self._send_message(message.channel, self.get_mc_message("song_added", f"🎵 **Agregado al final de la cola:**\n🎶 {title}\n👤 {artist}\n⏱️ {duration_str}", song=title))
                
                # Solo reproducir si no hay nada reproduciéndose Y no hay cliente de voz
                if (server_id not in self.voice_clients or 
                    not self.voice_clients[server_id].is_connected() or 
                    not self.voice_clients[server_id].is_playing()):
                    await self._play_next(server_id, message.channel)
                
        except Exception as e:
            logger.exception(f"Error buscando canción: {e}")
            await self._send_message(message.channel, self.get_mc_message("play_error", "❌ **No pude encontrar la canción.**"))
    
    async def cmd_skip(self, message, args):
        """Salta la canción actual."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_playing():
            await self._send_message(message.channel, "🎵 **No hay nada reproduciéndose.**")
            return
        
        # Verificar que el usuario esté en el mismo canal de voz
        if not message.author.voice or message.author.voice.channel != self.voice_clients[server_id].channel:
            await self._send_message(message.channel, "🎤 **Debes estar en el mismo canal de voz que el bot.**")
            return
        
        # Detener la canción actual (esto activará el callback para la siguiente)
        self.voice_clients[server_id].stop()
        await self._send_message(message.channel, self.get_mc_message("song_skipped", "⏭️ **Canción saltada."))
    
    async def cmd_stop(self, message, args):
        """Detiene completamente la reproducción y limpia la cola."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
            await self._send_message(message.channel, "🎤 **No estoy conectado a ningún canal.**")
            return
        
        # Detener la reproducción
        self.voice_clients[server_id].stop()
        
        # Limpiar la cola de la base de datos
        try:
            from db_role_mc import get_mc_db_instance
            db_mc = get_mc_db_instance(server_id)
            db_mc.limpiar_queue(server_id, str(message.channel.id))
        except Exception as e:
            logger.exception(f"Error limpiando cola: {e}")
        
        # Limpiar cola local
        if server_id in self.queues:
            self.queues[server_id].clear()
        
        await self._send_message(message.channel, self.get_mc_message("queue_cleared", "⏹️ **Reproducción detenida y cola limpiada."))
    
    async def cmd_queue(self, message, args):
        """Muestra la cola de reproducción o reanuda la reproducción."""
        server_id = str(message.guild.id)
        
        # Verificar si es el subcomando resume
        if args and args[0].lower() == 'resume':
            # Reanudar reproducción
            if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
                await self._send_message(message.channel, "🎤 **No estoy conectado a ningún canal.**")
                return
            
            if self.voice_clients[server_id].is_playing():
                await self._send_message(message.channel, "🎵 **Ya estoy reproduciendo.**")
                return
            
            # Intentar reproducir la siguiente canción
            await self._play_next(server_id, message.channel)
            return
        
        # Verificar si es el subcomando clear
        if args and args[0].lower() == 'clear':
            # Limpiar cola
            from db_role_mc import get_mc_db_instance
            db_mc = get_mc_db_instance(server_id)
            
            db_mc.limpiar_queue(server_id, str(message.channel.id))
            await self._send_message(message.channel, "🧹 **Cola limpiada.**")
            return
        
        # Mostrar cola (comportamiento original)
        # Obtener cola de la BD
        from db_role_mc import get_mc_db_instance
        db_mc = get_mc_db_instance(server_id)
        
        queue = db_mc.obtener_queue(server_id, str(message.channel.id))
        
        if not queue:
            await self._send_message(message.channel, "📭 **La cola está vacía.**")
            return
        
        # Crear embed con la cola
        embed = discord.Embed(
            title="🎵 Cola de Reproducción",
            color=discord.Color.blue()
        )
        
        for i, (pos, title, url, duration, artist, user_id, fecha) in enumerate(queue[:10], 1):
            try:
                user = await self.bot.fetch_user(int(user_id))
                user_name = user.display_name
            except:
                user_name = "Usuario desconocido"
            
            embed.add_field(
                name=f"#{pos} {title}",
                value=f"👤 {artist} • ⏱️ {duration} • 🎤 {user_name}",
                inline=False
            )
        
        if len(queue) > 10:
            embed.set_footer(text=f"Y {len(queue) - 10} canciones más...")
        
        await self._send_message(message.channel, embed=embed)
    
    async def cmd_clear(self, message, args):
        """Limpia la cola de reproducción."""
        server_id = str(message.guild.id)
        
        # Verificar permisos (DJ o administrador)
        if not self._check_dj_permissions(message.author):
            await self._send_message(message.channel, "🚫 **Necesitas rol de DJ o ser administrador para usar este comando.**")
            return
        
        # Limpiar cola de BD
        from db_role_mc import get_mc_db_instance
        db_mc = get_mc_db_instance(server_id)
        
        db_mc.limpiar_queue(server_id, str(message.channel.id))
        
        await self._send_message(message.channel, self.get_mc_message("queue_cleared", "🗑️ **Cola de reproducción limpiada.**"))
    
    async def cmd_pause(self, message, args):
        """Pausa la reproducción."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_playing():
            await self._send_message(message.channel, "🎵 **No hay nada reproduciéndose.**")
            return
        
        if not self._check_same_voice_channel(message.author, self.voice_clients[server_id]):
            await self._send_message(message.channel, "🎤 **Debes estar en el mismo canal de voz que el bot.**")
            return
        
        self.voice_clients[server_id].pause()
        await self._send_message(message.channel, "⏸️ **Reproducción pausada.**")
    
    async def cmd_resume(self, message, args):
        """Reanuda la reproducción."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_paused():
            await self._send_message(message.channel, "🎵 **No hay nada pausado.**")
            return
        
        if not self._check_same_voice_channel(message.author, self.voice_clients[server_id]):
            await self._send_message(message.channel, "🎤 **Debes estar en el mismo canal de voz que el bot.**")
            return
        
        self.voice_clients[server_id].resume()
        await self._send_message(message.channel, "▶️ **Reproducción reanudada.**")
    
    async def cmd_nowplaying(self, message, args):
        """Muestra la canción actual."""
        server_id = str(message.guild.id)
        
        if server_id not in self.now_playing:
            await self._send_message(message.channel, "🎵 **No hay nada reproduciéndose.**")
            return
        
        current = self.now_playing[server_id]
        
        embed = discord.Embed(
            title="🎵 Ahora Reproduciendo",
            color=discord.Color.green()
        )
        embed.add_field(name="Título", value=current['title'], inline=False)
        embed.add_field(name="Artista", value=current.get('artist', 'Desconocido'), inline=True)
        embed.add_field(name="Duración", value=current.get('duration', 'Desconocida'), inline=True)
        embed.add_field(name="Agregada por", value=current.get('user', 'Desconocido'), inline=True)
        
        await self._send_message(message.channel, embed=embed)
    
    async def cmd_history(self, message, args):
        """Muestra el historial de reproducción."""
        server_id = str(message.guild.id)
        
        # Obtener historial de BD
        from db_role_mc import get_mc_db_instance
        db_mc = get_mc_db_instance(server_id)
        
        history = db_mc.obtener_historial(server_id, str(message.channel.id), 10)
        
        if not history:
            await message.channel.send("📭 **No hay historial de reproducción.**")
            return
        
        embed = discord.Embed(
            title="📜 Historial de Reproducción",
            color=discord.Color.purple()
        )
        
        for i, (title, url, duration, artist, user_id, fecha) in enumerate(history[:5], 1):
            try:
                user = await self.bot.fetch_user(int(user_id))
                user_name = user.display_name
            except:
                user_name = "Usuario desconocido"
            
            embed.add_field(
                name=f"#{i} {title}",
                value=f"👤 {artist} • 🎤 {user_name}",
                inline=False
            )
        
        await self._send_message(message.channel, embed=embed)
    
    async def cmd_leave(self, message, args):
        """El bot sale del canal de voz."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients:
            await self._send_message(message.channel, "🎵 **No estoy conectado a ningún canal.**")
            return
        
        if not self._check_dj_permissions(message.author):
            await self._send_message(message.channel, "🚫 **Necesitas rol de DJ o ser administrador para usar este comando.**")
            return
        
        await self.voice_clients[server_id].disconnect()
        del self.voice_clients[server_id]
        if server_id in self.now_playing:
            del self.now_playing[server_id]
        
        await self._send_message(message.channel, "👋 **Saliendo del canal de voz.**")
    
    async def cmd_volume(self, message, args):
        """Ajusta el volumen de la reproducción (0-100)."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
            await self._send_message(message.channel, "🎤 **No estoy conectado a ningún canal.**")
            return
        
        if not args:
            await self._send_message(message.channel, "🎵 **Uso:** `!mc volume <0-100>`")
            return
        
        try:
            volume = int(args[0])
            if volume < 0 or volume > 100:
                await self._send_message(message.channel, "🎵 **El volumen debe estar entre 0 y 100.**")
                return
            
            # Convertir a 0.0-1.0 para discord.py
            volume_float = volume / 100.0
            self.voice_clients[server_id].source.volume = volume_float
            
            await self._send_message(message.channel, self.get_mc_message("volume_set", f"🔊 **Volumen ajustado a {volume}%**", volume=volume))
        except ValueError:
            await self._send_message(message.channel, "🎵 **El volumen debe ser un número entre 0 y 100.**")
        except Exception as e:
            logger.exception(f"Error ajustando volumen: {e}")
            await self._send_message(message.channel, "❌ **No pude ajustar el volumen.**")
    
    async def cmd_help(self, message, args):
        """Muestra la ayuda de comandos del MC."""
        embed = discord.Embed(
            title="🎵 Música de Kronk - Master of Ceremonies Orko",
            description="Komandos de música para umanos valientes!",
            color=discord.Color.gold()
        )
        
        commands = [
            ("!mc play <canción>", "Reproduce o agrega kanción inmediatamente"),
            ("!mc add <canción>", "Agrega kanción al final de la lista"),
            ("!mc skip", "Salta kanción actual"),
            ("!mc stop", "Detiene reproducción y limpia lista"),
            ("!mc queue", "Muestra lista de reproducción"),
            ("!mc queue clear", "Limpia toda la lista"),
            ("!mc queue resume", "Reanuda reproducción si está pausada"),
            ("!mc clear", "Limpia la lista (requiere rol DJ)"),
            ("!mc pause", "Pausa reproducción"),
            ("!mc resume", "Reanuda reproducción"),
            ("!mc nowplaying / !mc np", "Muestra kanción actual"),
            ("!mc history", "Muestra historial de reproducción"),
            ("!mc volume <0-100>", "Ajusta volumen de música"),
            ("!mc leave / !mc disconnect", "Sale de kanal de voz (requiere rol DJ)"),
            ("!mc help / !mc commands", "Muestra esta ayuda")
        ]
        
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        
        embed.set_footer(text="GRRR: Algunos komandos necesitan rol DJ o ser jefe orko!")
        
        try:
            await message.author.send(embed=embed)
            # Usar mensaje personalizado desde role_messages
            role_cfg = _load_mc_answers().get("role_messages", {})
            music_privado_msg = role_cfg.get("music_help_sent", "GRRR Kronk enviar ayuda de música por mensaje privado umano!")
            await message.channel.send(music_privado_msg)
        except discord.errors.Forbidden:
            # No se puede enviar DM (el usuario los tiene bloqueados)
            await message.channel.send("📭 **No puedo enviarte mensaje privado.**\n**Por favor, activa los DMs de servidores o usa otro canal.**")
        except Exception as e:
            logger.exception(f"Error enviando DM de ayuda: {e}")
            await message.channel.send("❌ **Error al enviar ayuda por mensaje privado.**")
    
    async def _play_next(self, server_id: str, channel):
        """Reproduce la siguiente canción de la cola."""
        try:
            # Obtener siguiente canción de la BD
            from db_role_mc import get_mc_db_instance
            db_mc = get_mc_db_instance(server_id)
            
            queue = db_mc.obtener_queue(server_id, str(channel.id))
            
            if not queue:
                # No hay más canciones, desconectar después de 5 minutos
                await self._send_message(channel, self.get_mc_message('queue_end_disconnect'))
                
                # Programar desconexión
                await asyncio.sleep(300)  # 5 minutos
                
                if server_id in self.voice_clients and self.voice_clients[server_id].is_connected():
                    if not self.voice_clients[server_id].is_playing():
                        await self.voice_clients[server_id].disconnect()
                        del self.voice_clients[server_id]
                        if server_id in self.now_playing:
                            del self.now_playing[server_id]
                        await self._send_message(channel, self.get_mc_message('inactive_disconnect'))
                return
            
            # Obtener primera canción de la cola
            pos, title, url, duration, artist, user_id, fecha = queue[0]
            
            # Configurar yt-dlp para obtener audio
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info['url']
            
            # Crear fuente de audio
            audio_source = discord.FFmpegPCMAudio(
                audio_url,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn -b:a 128k"
            )
            
            # Verificar que el cliente de voz sigue conectado
            voice_client = self.voice_clients.get(server_id)
            if not voice_client:
                logger.error(f"MC: No hay cliente de voz para servidor {server_id}")
                await self._send_message(channel, "❌ **Error: No hay conexión de voz establecida.**")
                return
            elif not voice_client.is_connected():
                logger.error(f"MC: Cliente de voz desconectado para servidor {server_id}")
                logger.error(f"MC: Estado del cliente - Conectado: {voice_client.is_connected()}, Canal: {getattr(voice_client, 'channel', 'Ninguno')}")
                await self._send_message(channel, "🔌 **Conexión de voz perdida.**\n**Por favor, intenta reproducir la canción nuevamente.**")
                return
            
            # Intentar reproducir con captura detallada de excepciones
            try:
                voice_client.play(audio_source, after=lambda e: self._after_song(e, server_id, channel))
                logger.info(f"MC: Reproducción iniciada para {title}")
            except discord.errors.ClientException as e:
                logger.error(f"MC: Error de Discord ClientException: {e}")
                if "Not connected to voice" in str(e):
                    await self._send_message(channel, "❌ **Error crítico: Conexión de voz inválida.**\n**El bot necesita reconectarse al canal.**")
                else:
                    await self._send_message(channel, f"❌ **Error de Discord: {e}**")
                return
            except Exception as e:
                logger.exception(f"MC: Error inesperado al reproducir: {e}")
                await self._send_message(channel, f"❌ **Error inesperado: {type(e).__name__}**")
                return
            
            # Actualizar ahora reproduciendo
            try:
                user = await self.bot.fetch_user(int(user_id))
                user_name = user.display_name
            except:
                user_name = "Usuario desconocido"
            
            self.now_playing[server_id] = {
                'title': title,
                'url': url,
                'duration': duration,
                'artist': artist,
                'user': user_name
            }
            
            # Remover de la cola y agregar al historial
            db_mc.remover_cancion_queue(server_id, str(channel.id), pos)
            db_mc.registrar_historial(server_id, str(channel.id), user_id, title, url, duration, artist)
            
            # Anunciar
            await self._send_message(channel, self.get_mc_message("now_playing", f"🎵 **Ahora Reproduciendo**\n🎶 {title}\n👤 {artist}\n⏱️ {duration}\n🎤 Agregada por: {user_name}", song=title))
            
        except Exception as e:
            logger.exception(f"Error reproduciendo siguiente canción: {e}")
            await self._send_message(channel, "❌ **Error reproduciendo la siguiente canción.**")
    
    def _after_song(self, error, server_id: str, channel):
        """Callback después de terminar una canción."""
        if error:
            logger.error(f"Error en reproducción: {error}")
        
        # Evitar múltiples llamadas simultáneas
        if hasattr(self, '_playing_next') and self._playing_next:
            logger.info(f"MC: Ya hay una canción en proceso, saltando llamada duplicada")
            return
        
        # Marcar que estamos procesando siguiente canción
        self._playing_next = True
        
        # Programar siguiente canción usando el loop del bot
        try:
            # Obtener el loop del bot principal
            bot_loop = self.bot._connection.loop
            if bot_loop and not bot_loop.is_closed():
                # Programar la siguiente canción en el loop principal
                asyncio.run_coroutine_threadsafe(self._play_next_safe(server_id, channel), bot_loop)
            else:
                logger.error("MC: Loop del bot no disponible")
                self._playing_next = False
        except Exception as e:
            logger.exception(f"MC: Error programando siguiente canción: {e}")
            self._playing_next = False
    
    async def _play_next_safe(self, server_id: str, channel):
        """Versión segura de _play_next que evita duplicaciones."""
        try:
            # Limpiar flag al finalizar
            self._playing_next = False
            await self._play_next(server_id, channel)
        except Exception as e:
            logger.exception(f"Error en _play_next_safe: {e}")
            # Asegurar que el flag se limpie incluso si hay error
            self._playing_next = False
    
    def _check_dj_permissions(self, user) -> bool:
        """Verifica si el usuario tiene permisos de DJ."""
        # Verificar si es administrador
        if user.guild_permissions.administrator:
            return True
        
        # Verificar si tiene rol de DJ
        dj_roles = ["DJ", "dj", "Music", "music", "DJ Role", "dj role"]
        for role in user.roles:
            if role.name in dj_roles:
                return True
        
        return False
    
    def _check_same_voice_channel(self, user, voice_client) -> bool:
        """Verifica si el usuario está en el mismo canal de voz que el bot."""
        return user.voice and user.voice.channel == voice_client.channel


# Diccionario de comandos disponibles
COMANDOS_MC = {
    'play': MCCommands.cmd_play,
    'add': MCCommands.cmd_add,
    'skip': MCCommands.cmd_skip,
    'stop': MCCommands.cmd_stop,
    'queue': MCCommands.cmd_queue,
    'clear': MCCommands.cmd_clear,
    'pause': MCCommands.cmd_pause,
    'resume': MCCommands.cmd_resume,
    'nowplaying': MCCommands.cmd_nowplaying,
    'np': MCCommands.cmd_nowplaying,  # Alias
    'history': MCCommands.cmd_history,
    'leave': MCCommands.cmd_leave,
    'disconnect': MCCommands.cmd_leave,  # Alias
    'help': MCCommands.cmd_help,
    'commands': MCCommands.cmd_help,  # Alias
}
