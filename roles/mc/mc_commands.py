import discord
import asyncio
import re
import yt_dlp
import sys
import os
import json
from urllib.parse import urlparse
from agent_logging import get_logger
from agent_engine import PERSONALITY

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
                    'queue_end_disconnect': "🎵 End of queue. I will disconnect in 5 minutes if no more songs are added.",
                    'inactive_disconnect': "👋 Disconnected due to inactivity.",
                    'timeout_connecting': "❌ **Timeout while connecting to the voice channel. Please try again.**",
                    'voice_connection_error': "❌ **Voice connection error. Please try again.**",
                    'discord_connect_error': "❌ **Discord connection error.**",
                    'general_connect_error': "❌ **I could not connect to the voice channel.**",
                    'volume_range_error': "🎵 **Volume must be a number between 0 and 100.**",
                    'volume_adjust_error': "❌ **I could not adjust the volume.**",
                    'dm_help_error': "📭 **I can't send you a private message.**\n**Please enable server DMs or use another channel.**",
                    'dm_help_blocked': "📭 **I can't send you a private message.**\n**Please enable server DMs or use another channel.**",
                    'help_dm_error': "❌ **Error sending help by private message.**",
                    'no_voice_connection': "❌ **Error: No voice connection is established.**",
                    'voice_disconnected': "❌ **Critical error: Invalid voice connection.**\n**The bot needs to reconnect to the channel.**",
                    'critical_voice_error': "❌ **Critical error: Invalid voice connection.**\n**The bot needs to reconnect to the channel.**",
                    'discord_voice_error': "❌ **Discord error: {error}**",
                    'unexpected_error': "❌ **Unexpected error: {error_type}**",
                    'next_song_error': "❌ **Error playing the next song.**",
                    'connected_to_voice': "🎤 **Connected to {channel_name}**",
                    'no_dm_permission': "📭 **I can't send you a private message.**\n**Please enable server DMs or use another channel.**"
                }
                message = fallbacks.get(key, default or f"Message not found: {key}")
            
            # Reemplazar variables si se proporcionan
            if kwargs:
                try:
                    message = message.format(**kwargs)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Error formating message {key}: {e}")
            return message
        except Exception as e:
            logger.warning(f"Error honding the message from MC {key}: {e}")
            return default or f"Error: {key}"
        
    async def cmd_play(self, message, args):
        """Play a song or add one to the queue"""
        if not args:
            await self._send_message(message.channel, "🎵 **Usage:** `!mc play <song name or song URL>`")
            return
        
        query = ' '.join(args)
        server_id = str(message.guild.id)
        
        # Verificar que el usuario esté en un canal de voz
        if not message.author.voice:
            await self._send_message(message.channel, self.get_mc_message("not_in_voice", "🎤 **You must be in a voice channel to use this command.**"))
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
                await self._send_message(message.channel, self.get_mc_message("voice_join_empty", f"🎤 **Connected to {voice_channel.name}**"))
            elif not self.voice_clients[server_id].is_connected():
                logger.info(f"MC: Reconectando al canal {voice_channel.name}...")
                logger.info(f"MC: Iniciando reconexión de voz (timeout: 60s)...")
                voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=60.0)
                logger.info(f"MC: ✅ Reconexión exitosa a {voice_channel.name}")
                self.voice_clients[server_id] = voice_client
                await self._send_message(message.channel, f"🎤 **Reconnected to {voice_channel.name}**")
            else:
                voice_client = self.voice_clients[server_id]
                # Verificar si está en el canal correcto
                if voice_client.channel != voice_channel:
                    logger.info(f"MC: Moviendo de {voice_client.channel.name} a {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                    await self._send_message(message.channel, f"🎤 **Moved to {voice_channel.name}**")
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
                    await self._send_message(message.channel, f"🎤 **Connected to {voice_channel.name}**")
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
        await self._send_message(message.channel, "🔍 **Searching for song...**")
        
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
                

                from db_role_mc import get_mc_db_instance
                db_mc = get_mc_db_instance(server_id)
                

                db_mc.agregar_cancion_queue(
                    server_id, str(message.channel.id), str(message.author.id),
                    title, url, duration_str, artist, posicion=0
                )
                

                if server_id in self.voice_clients and self.voice_clients[server_id].is_playing():
                    logger.info(f"MC: Stop song in the server {server_id}")
                    self.voice_clients[server_id].stop()
                

                if server_id in self.voice_clients:
                    vc = self.voice_clients[server_id]
                    logger.info(f"MC: State before reproduction - Conected: {vc.is_connected()}, Playing: {vc.is_playing()}, Channel: {vc.channel}")
                
                
                logger.info(f"MC: Inialising the reproduction for '{title}' in the server {server_id}")
                await self._play_next(server_id, message.channel)
                
        except Exception as e:
            logger.exception(f"Error finding song {e}")
            await self._send_message(message.channel, self.get_mc_message("play_error", "❌ **I could not find the song. **"))
    
    async def cmd_add(self, message, args):
        """Add a song to the tail of the queue"""
        if not args:
            await self._send_message(message.channel, "🎵 **Usage:** `!mc add <song name or song URL>`")
            return
        
        query = ' '.join(args)
        server_id = str(message.guild.id)
        
        # Verificar que el usuario esté en un canal de voz
        if not message.author.voice:
            await self._send_message(message.channel, "🎤 **You must be in a voice channel to use this command.**")
            return
        
        voice_channel = message.author.voice.channel
        
        # Conectar al canal de voz si no está conectado
        voice_client = None
        try:
            if server_id not in self.voice_clients:
                logger.info(f"MC: Connecting to channel {voice_channel.name}...")
                voice_client = await voice_channel.connect()
                self.voice_clients[server_id] = voice_client
                await self._send_message(message.channel, f"🎤 **Connected to {voice_channel.name}**")
            elif not self.voice_clients[server_id].is_connected():
                logger.info(f"MC: Reconnectiong to channel {voice_channel.name}...")
                voice_client = await voice_channel.connect()
                self.voice_clients[server_id] = voice_client
                await self._send_message(message.channel, f"🎤 **Reconnected to {voice_channel.name}**")
            else:
                voice_client = self.voice_clients[server_id]

                if voice_client.channel != voice_channel:
                    logger.info(f"MC: Moving from {voice_client.channel.name} to {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                    await self._send_message(message.channel, f"🎤 **Moved to {voice_channel.name}**")
        except discord.errors.ClientException as e:
            if "Already connected to a voice channel" in str(e):

                voice_client = message.guild.voice_client
                if voice_client:
                    logger.info(f"MC: You alredy connected to {voice_channel.name} (using a existing client)")
                    self.voice_clients[server_id] = voice_client
                else:
                    logger.error(f"MC: Error: Discord say that you are conected but the voice client isn't there.")
                    await self._send_message(message.channel, self.get_mc_message('voice_connection_error'))
                    return
            else:
                logger.exception(f"MC: Error Discord coneccting: {e}")
                await self._send_message(message.channel, self.get_mc_message('discord_connect_error'))
                return
        except Exception as e:
            logger.exception(f"MC: General Error conecting to {voice_channel.name}: {e}")
            await self._send_message(message.channel, self.get_mc_message('general_connect_error'))
            return
        

        await self._send_message(message.channel, "🔍 **Searching for the song...**")
        
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
                
                from db_role_mc import get_mc_db_instance
                db_mc = get_mc_db_instance(server_id)
                
                db_mc.agregar_cancion_queue(
                    server_id, str(message.channel.id), str(message.author.id),
                    title, url, duration_str, artist, posicion=-1
                )
                
                await self._send_message(message.channel, self.get_mc_message("song_added", f"🎵 **Adding song to tha tail of the queue:**\n🎶 {title}\n👤 {artist}\n⏱️ {duration_str}", song=title))
                
                if (server_id not in self.voice_clients or 
                    not self.voice_clients[server_id].is_connected() or 
                    not self.voice_clients[server_id].is_playing()):
                    await self._play_next(server_id, message.channel)
                
        except Exception as e:
            logger.exception(f"Error finding for song {e}")
            await self._send_message(message.channel, self.get_mc_message("play_error", "❌ **I couldn't find the song**"))
    
    async def cmd_skip(self, message, args):
        """Skip the current song"""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_playing():
            await self._send_message(message.channel, "🎵 **Nothing is playing.**")
            return
        
        if not message.author.voice or message.author.voice.channel != self.voice_clients[server_id].channel:
            await self._send_message(message.channel, "🎤 **You must be in the same voice channel as the bot.**")
            return
        
        self.voice_clients[server_id].stop()
        await self._send_message(message.channel, self.get_mc_message("song_skipped", "⏭️ **Song skipped.**"))
    
    async def cmd_stop(self, message, args):
        """Stop the reproducction and clear the queue"""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
            await self._send_message(message.channel, "🎤 **I am not connected to any channel.**")
            return
        
        self.voice_clients[server_id].stop()
        
        try:
            from db_role_mc import get_mc_db_instance
            db_mc = get_mc_db_instance(server_id)
            db_mc.limpiar_queue(server_id, str(message.channel.id))
        except Exception as e:
            logger.exception(f"Error cleaning the queue {e}")
        
        # Limpiar cola local
        if server_id in self.queues:
            self.queues[server_id].clear()
        
        await self._send_message(message.channel, self.get_mc_message("queue_cleared", "⏹️ **Playback stopped and queue cleared.**"))
    
    async def cmd_queue(self, message, args):
        """Show the current queue and resume the reproduction"""
        server_id = str(message.guild.id)
        
        if args and args[0].lower() == 'resume':

            if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
                await self._send_message(message.channel, "🎤 **I am not connected to any channel.**")
                return
            
            if self.voice_clients[server_id].is_playing():
                await self._send_message(message.channel, "🎵 **I am already playing.**")
                return

            await self._play_next(server_id, message.channel)
            return
        

        if args and args[0].lower() == 'clear':
            from db_role_mc import get_mc_db_instance
            db_mc = get_mc_db_instance(server_id)
            
            db_mc.limpiar_queue(server_id, str(message.channel.id))
            await self._send_message(message.channel, "🧹 **Queue clear**")
            return

        from db_role_mc import get_mc_db_instance
        db_mc = get_mc_db_instance(server_id)
        
        queue = db_mc.obtener_queue(server_id, str(message.channel.id))
        
        if not queue:
            await self._send_message(message.channel, "📭 **The queue is empty.**")
            return
        
        # Crear embed con la cola
        embed = discord.Embed(
            title="🎵Queue reproduction",
            color=discord.Color.blue()
        )
        
        for i, (pos, title, url, duration, artist, user_id, fecha) in enumerate(queue[:10], 1):
            try:
                user = await self.bot.fetch_user(int(user_id))
                user_name = user.display_name
            except:
                user_name = "Unknown user"
            
            embed.add_field(
                name=f"#{pos} {title}",
                value=f"👤 {artist} • ⏱️ {duration} • 🎤 {user_name}",
                inline=False
            )
        
        if len(queue) > 10:
            embed.set_footer(text=f"Y {len(queue) - 10} more songs...")
        
        await self._send_message(message.channel, embed=embed)
    
    async def cmd_clear(self, message, args):
        """Clean the queue"""
        server_id = str(message.guild.id)
        
        if not self._check_dj_permissions(message.author):
            await self._send_message(message.channel, "🚫 **You need the DJ role or administrator permissions to use this command.**")
            return
        
        from db_role_mc import get_mc_db_instance
        db_mc = get_mc_db_instance(server_id)
        
        db_mc.limpiar_queue(server_id, str(message.channel.id))
        
        await self._send_message(message.channel, self.get_mc_message("queue_cleared", "🗑️ **Playback queue cleared.**"))
    
    async def cmd_pause(self, message, args):
        """Pause the reproduction"""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_playing():
            await self._send_message(message.channel, "🎵 **Nothing is playing.**")
            return
        
        if not self._check_same_voice_channel(message.author, self.voice_clients[server_id]):
            await self._send_message(message.channel, "🎤 **You must be in the same voice channel as the bot.**")
            return
        
        self.voice_clients[server_id].pause()
        await self._send_message(message.channel, "⏸️ **Playback paused.**")
    
    async def cmd_resume(self, message, args):
        """Resume the reproduction"""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_paused():
            await self._send_message(message.channel, "🎵 **Nothing is paused.**")
            return
        
        if not self._check_same_voice_channel(message.author, self.voice_clients[server_id]):
            await self._send_message(message.channel, "🎤 **You must be in the same voice channel as the bot.**")
            return
        
        self.voice_clients[server_id].resume()
        await self._send_message(message.channel, "▶️ **Playback resumed.**")
    
    async def cmd_nowplaying(self, message, args):
        """Show the current song"""
        server_id = str(message.guild.id)
        
        if server_id not in self.now_playing:
            await self._send_message(message.channel, "🎵 **Nothing is playing.**")
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
        """Show the history of the reproduction"""
        server_id = str(message.guild.id)

        from db_role_mc import get_mc_db_instance
        db_mc = get_mc_db_instance(server_id)
        
        history = db_mc.obtener_historial(server_id, str(message.channel.id), 10)
        
        if not history:
            await message.channel.send("📭 **The history its empty**")
            return
        
        embed = discord.Embed(
            title="📜 Reproduction history",
            color=discord.Color.purple()
        )
        
        for i, (title, url, duration, artist, user_id, fecha) in enumerate(history[:5], 1):
            try:
                user = await self.bot.fetch_user(int(user_id))
                user_name = user.display_name
            except:
                user_name = "Unknown user"
            
            embed.add_field(
                name=f"#{i} {title}",
                value=f"👤 {artist} • 🎤 {user_name}",
                inline=False
            )
        
        await self._send_message(message.channel, embed=embed)
    
    async def cmd_leave(self, message, args):
        """The bot is going out from the voice channel"""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients:
            await self._send_message(message.channel, "🎵 **I am not connected to any channel.**")
            return
        
        if not self._check_dj_permissions(message.author):
            await self._send_message(message.channel, "🚫 **You need the DJ role or administrator permissions to use this command.**")
            return
        
        await self.voice_clients[server_id].disconnect()
        del self.voice_clients[server_id]
        if server_id in self.now_playing:
            del self.now_playing[server_id]
        
        await self._send_message(message.channel, "👋 **Leaving the voice channel.**")
    
    async def cmd_volume(self, message, args):
        """Set the volume (0-100)."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
            await self._send_message(message.channel, "🎤 **I am not connected to any channel.**")
            return
        
        if not args:
            await self._send_message(message.channel, "🎵 **Usage:** `!mc volume <0-100>`")
            return
        
        try:
            volume = int(args[0])
            if volume < 0 or volume > 100:
                await self._send_message(message.channel, "🎵 **Volume must be between 0 and 100.**")
                return
            
            volume_float = volume / 100.0
            self.voice_clients[server_id].source.volume = volume_float
            
            await self._send_message(message.channel, self.get_mc_message("volume_set", f"🔊 **Volume set to {volume}%**", volume=volume))
        except ValueError:
            await self._send_message(message.channel, "🎵 **Volume must be a number between 0 and 100.**")
        except Exception as e:
            logger.exception(f"Error ajustando volumen: {e}")
            await self._send_message(message.channel, "❌ **I couldn't adjust the volumen**")
    
    async def cmd_help(self, message, args):
        """Show the MC commands"""
        embed = discord.Embed(
            title="🎵 MC Music bot",
            description="Music commands",
            color=discord.Color.gold()
        )
        
        commands = [
            ("!mc play <song>", "Plays or adds a song immediately"),
            ("!mc add <song>", "Adds a song to the end of the queue"),
            ("!mc skip", "Skips the current song"),
            ("!mc stop", "Stops playback and clears the queue"),
            ("!mc queue", "Shows the current playlist"),
            ("!mc queue clear", "Clears the entire queue"),
            ("!mc queue resume", "Resumes playback if paused"),
            ("!mc clear", "Clears the queue (DJ role required)"),
            ("!mc pause", "Pauses playback"),
            ("!mc resume", "Resumes playback"),
            ("!mc nowplaying / !mc np", "Shows the current song"),
            ("!mc history", "Shows the playback history"),
            ("!mc volume <0-100>", "Adjusts the music volume"),
            ("!mc leave / !mc disconnect", "Leaves the voice channel (DJ role required)"),
            ("!mc help / !mc commands", "Shows this help message")
        ]
        
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        
        embed.set_footer(text="Some commands need admin privilegies")
        
        try:
            await message.author.send(embed=embed)
            
            role_cfg = _load_mc_answers().get("role_messages", {})
            music_privado_msg = role_cfg.get("music_help_sent", "Help sended by DM")
            await message.channel.send(music_privado_msg)
        except discord.errors.Forbidden:
         
            await message.channel.send("📭 **I couldn't  send you the help message**\n")
        except Exception as e:
            logger.exception(f"Error sending help DM: {e}")
            await message.channel.send("❌ **Error sending help for DM**")
    
    async def _play_next(self, server_id: str, channel):
        """Reproduce the next song from the queue"""
        try:
            from db_role_mc import get_mc_db_instance
            db_mc = get_mc_db_instance(server_id)
            
            queue = db_mc.obtener_queue(server_id, str(channel.id))
            
            if not queue:
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
            
            pos, title, url, duration, artist, user_id, fecha = queue[0]
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                audio_url = info['url']
            
            audio_source = discord.FFmpegPCMAudio(
                audio_url,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                options="-vn -b:a 128k"
            )

            voice_client = self.voice_clients.get(server_id)
            if not voice_client:
                logger.error(f"MC: Not client voice from the server {server_id}")
                await self._send_message(channel, "❌ **Error: No voice connection is established.**")
                return
            elif not voice_client.is_connected():
                logger.error(f"MC: Voice client disconecte for {server_id}")
                logger.error(f"MC: Client status Connected: {voice_client.is_connected()}, Channel: {getattr(voice_client, 'channel', 'Any')}")
                await self._send_message(channel, "🔌 **Voice connection lost.**\n**Please try playing the song again.**")
                return
            
            try:
                voice_client.play(audio_source, after=lambda e: self._after_song(e, server_id, channel))
                logger.info(f"MC: Reproducción iniciada para {title}")
            except discord.errors.ClientException as e:
                logger.error(f"MC: Error de Discord ClientException: {e}")
                if "Not connected to voice" in str(e):
                    await self._send_message(channel, "❌ **Critical error: Invalid voice connection.**\n**The bot needs to reconnect to the channel.**")
                else:
                    await self._send_message(channel, f"❌ **Discord error: {e}**")
                return
            except Exception as e:
                logger.exception(f"MC: Unexpected error playing {e}")
                await self._send_message(channel, f"❌ **Unexpected Error: {type(e).__name__}**")
                return
            
            try:
                user = await self.bot.fetch_user(int(user_id))
                user_name = user.display_name
            except:
                user_name = "Unknown user"
            
            self.now_playing[server_id] = {
                'title': title,
                'url': url,
                'duration': duration,
                'artist': artist,
                'user': user_name
            }
            
            db_mc.remover_cancion_queue(server_id, str(channel.id), pos)
            db_mc.registrar_historial(server_id, str(channel.id), user_id, title, url, duration, artist)
            
            # Anunciar
            await self._send_message(channel, self.get_mc_message("now_playing", f"🎵 **Now Playing**\n🎶 {title}\n👤 {artist}\n⏱️ {duration}\n🎤 Added by: {user_name}", song=title))
            
        except Exception as e:
            logger.exception(f"Error playing the next song {e}")
            await self._send_message(channel, "❌ **Error playing the next song.**")
    
    def _after_song(self, error, server_id: str, channel):
        """Callback after finish a song"""
        if error:
            logger.error(f"Error playing  {error}")
        
        if hasattr(self, '_playing_next') and self._playing_next:
            logger.info(f"MC: Its alredy a song in the proccess, skipping the duplicated call")
            return

        self._playing_next = True

        try:
            bot_loop = self.bot._connection.loop
            if bot_loop and not bot_loop.is_closed():

                asyncio.run_coroutine_threadsafe(self._play_next_safe(server_id, channel), bot_loop)
            else:
                logger.error("MC: Loop of the bot unavaible")
                self._playing_next = False
        except Exception as e:
            logger.exception(f"MC: Error sheduling the next song {e}")
            self._playing_next = False
    
    async def _play_next_safe(self, server_id: str, channel):
        """Safe version por _play to avoid duplicity"""
        try:
            self._playing_next = False
            await self._play_next(server_id, channel)
        except Exception as e:
            logger.exception(f"Error in _play_next_safe: {e}")
            self._playing_next = False
    
    def _check_dj_permissions(self, user) -> bool:
        """Verify if the user have DJ permissions"""
        if user.guild_permissions.administrator:
            return True
        
        dj_roles = ["DJ", "dj", "Music", "music", "DJ Role", "dj role"]
        for role in user.roles:
            if role.name in dj_roles:
                return True
        
        return False
    
    def _check_same_voice_channel(self, user, voice_client) -> bool:
        """Check if the user is in the currect voice channel of the bot"""
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
