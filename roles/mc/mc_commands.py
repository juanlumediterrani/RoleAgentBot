import discord
import asyncio
import re
import yt_dlp
import sys
import os
from urllib.parse import urlparse
from agent_logging import get_logger

# Asegurar que el path del directorio mc esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = get_logger('mc_commands')

class MCCommands:
    """Comandos del MC (Master of Ceremonies) para música en Discord."""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.voice_clients = {}  # Almacenar clientes de voz por servidor
        self._playing_next = False  # Flag para evitar duplicaciones
        self.now_playing = {}    # Almacenar canción actual por servidor
        self.queues = {}          # Almacenar colas por servidor
        
    async def cmd_play(self, message, args):
        """Reproduce una canción o la agrega a la cola."""
        if not args:
            await message.channel.send("🎵 **Uso:** `!mc play <nombre o URL de la canción>`")
            return
        
        query = ' '.join(args)
        server_id = str(message.guild.id)
        
        # Verificar que el usuario esté en un canal de voz
        if not message.author.voice:
            await message.channel.send("🎤 **Debes estar en un canal de voz para usar este comando.**")
            return
        
        voice_channel = message.author.voice.channel
        
        # Conectar al canal de voz si no está conectado
        voice_client = None
        try:
            if server_id not in self.voice_clients:
                logger.info(f"MC: Conectando al canal {voice_channel.name}...")
                voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
                self.voice_clients[server_id] = voice_client
                await message.channel.send(f"🎤 **Conectado a {voice_channel.name}**")
            elif not self.voice_clients[server_id].is_connected():
                logger.info(f"MC: Reconectando al canal {voice_channel.name}...")
                voice_client = await asyncio.wait_for(voice_channel.connect(), timeout=10.0)
                self.voice_clients[server_id] = voice_client
                await message.channel.send(f"🎤 **Reconectado a {voice_channel.name}**")
            else:
                voice_client = self.voice_clients[server_id]
                # Verificar si está en el canal correcto
                if voice_client.channel != voice_channel:
                    logger.info(f"MC: Moviendo de {voice_client.channel.name} a {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                    await message.channel.send(f"🎤 **Movido a {voice_channel.name}**")
        except asyncio.TimeoutError:
            logger.error(f"MC: Timeout al conectar a {voice_channel.name}")
            # No enviar mensaje de timeout si ya estamos conectados y reproduciendo
            if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
                await message.channel.send("❌ **Timeout al conectar al canal de voz. Intenta de nuevo.**")
            return
        except discord.errors.ClientException as e:
            if "Already connected to a voice channel" in str(e):
                # Ya está conectado, obtener el cliente de voz existente
                voice_client = message.guild.voice_client
                if voice_client:
                    logger.info(f"MC: Ya conectado a {voice_channel.name} (usando cliente existente)")
                    self.voice_clients[server_id] = voice_client
                    await message.channel.send(f"🎤 **Conectado a {voice_channel.name}**")
                else:
                    logger.error(f"MC: Error: Discord dice que está conectado pero no hay cliente de voz")
                    await message.channel.send("❌ **Error de conexión de voz. Intenta de nuevo.**")
                    return
            else:
                logger.exception(f"MC: Error Discord conectando: {e}")
                await message.channel.send("❌ **Error de Discord al conectar.**")
                return
        except Exception as e:
            logger.exception(f"MC: Error general conectando a {voice_channel.name}: {e}")
            await message.channel.send("❌ **No pude conectarme al canal de voz.**")
            return
        
        # Buscar la canción
        await message.channel.send("🔍 **Buscando canción...**")
        
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
                from agent_db import get_active_server_name
                server_name = get_active_server_name() or "default"
                db_mc = get_mc_db_instance(server_name)
                
                # Agregar a la cola en BD (al principio para play inmediato)
                db_mc.agregar_cancion_queue(
                    server_id, str(message.channel.id), str(message.author.id),
                    title, url, duration_str, artist, posicion=0
                )
                
                # Detener canción actual si hay una y reproducir la nueva
                if server_id in self.voice_clients and self.voice_clients[server_id].is_playing():
                    self.voice_clients[server_id].stop()
                
                # Reproducir inmediatamente
                await self._play_next(server_id, message.channel)
                
        except Exception as e:
            logger.exception(f"Error buscando canción: {e}")
            await message.channel.send("❌ **No pude encontrar la canción.**")
    
    async def cmd_add(self, message, args):
        """Agrega una canción al final de la cola."""
        if not args:
            await message.channel.send("🎵 **Uso:** `!mc add <nombre o URL de la canción>`")
            return
        
        query = ' '.join(args)
        server_id = str(message.guild.id)
        
        # Verificar que el usuario esté en un canal de voz
        if not message.author.voice:
            await message.channel.send("🎤 **Debes estar en un canal de voz para usar este comando.**")
            return
        
        voice_channel = message.author.voice.channel
        
        # Conectar al canal de voz si no está conectado
        voice_client = None
        try:
            if server_id not in self.voice_clients:
                logger.info(f"MC: Conectando al canal {voice_channel.name}...")
                voice_client = await voice_channel.connect()
                self.voice_clients[server_id] = voice_client
                await message.channel.send(f"🎤 **Conectado a {voice_channel.name}**")
            elif not self.voice_clients[server_id].is_connected():
                logger.info(f"MC: Reconectando al canal {voice_channel.name}...")
                voice_client = await voice_channel.connect()
                self.voice_clients[server_id] = voice_client
                await message.channel.send(f"🎤 **Reconectado a {voice_channel.name}**")
            else:
                voice_client = self.voice_clients[server_id]
                # Verificar si está en el canal correcto
                if voice_client.channel != voice_channel:
                    logger.info(f"MC: Moviendo de {voice_client.channel.name} a {voice_channel.name}")
                    await voice_client.move_to(voice_channel)
                    await message.channel.send(f"🎤 **Movido a {voice_channel.name}**")
        except discord.errors.ClientException as e:
            if "Already connected to a voice channel" in str(e):
                # Ya está conectado, obtener el cliente de voz existente
                voice_client = message.guild.voice_client
                if voice_client:
                    logger.info(f"MC: Ya conectado a {voice_channel.name} (usando cliente existente)")
                    self.voice_clients[server_id] = voice_client
                else:
                    logger.error(f"MC: Error: Discord dice que está conectado pero no hay cliente de voz")
                    await message.channel.send("❌ **Error de conexión de voz. Intenta de nuevo.**")
                    return
            else:
                logger.exception(f"MC: Error Discord conectando: {e}")
                await message.channel.send("❌ **Error de Discord al conectar.**")
                return
        except Exception as e:
            logger.exception(f"MC: Error general conectando a {voice_channel.name}: {e}")
            await message.channel.send("❌ **No pude conectarme al canal de voz.**")
            return
        
        # Buscar la canción
        await message.channel.send("🔍 **Buscando canción...**")
        
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
                from agent_db import get_active_server_name
                server_name = get_active_server_name() or "default"
                db_mc = get_mc_db_instance(server_name)
                
                # Agregar a la cola en BD (al final)
                db_mc.agregar_cancion_queue(
                    server_id, str(message.channel.id), str(message.author.id),
                    title, url, duration_str, artist, posicion=-1
                )
                
                # Siempre mostrar mensaje de agregado y NUNCA interrumpir
                await message.channel.send(f"🎵 **Agregado al final de la cola:**\n"
                                        f"🎶 {title}\n"
                                        f"👤 {artist}\n"
                                        f"⏱️ {duration_str}")
                
                # Solo reproducir si no hay nada reproduciéndose Y no hay cliente de voz
                if (server_id not in self.voice_clients or 
                    not self.voice_clients[server_id].is_connected() or 
                    not self.voice_clients[server_id].is_playing()):
                    await self._play_next(server_id, message.channel)
                
        except Exception as e:
            logger.exception(f"Error buscando canción: {e}")
            await message.channel.send("❌ **No pude encontrar la canción.**")
    
    async def cmd_skip(self, message, args):
        """Salta la canción actual."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_playing():
            await message.channel.send("🎵 **No hay nada reproduciéndose.**")
            return
        
        # Verificar que el usuario esté en el mismo canal de voz
        if not message.author.voice or message.author.voice.channel != self.voice_clients[server_id].channel:
            await message.channel.send("🎤 **Debes estar en el mismo canal de voz que el bot.**")
            return
        
        # Detener la canción actual (esto activará el callback para la siguiente)
        self.voice_clients[server_id].stop()
        await message.channel.send("⏭️ **Canción saltada.**")
    
    async def cmd_stop(self, message, args):
        """Detiene completamente la reproducción y limpia la cola."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
            await message.channel.send("🎤 **No estoy conectado a ningún canal.**")
            return
        
        # Detener la reproducción
        self.voice_clients[server_id].stop()
        
        # Limpiar la cola
        if server_id in self.queues:
            self.queues[server_id].clear()
        
        await message.channel.send("⏹️ **Reproducción detenida y cola limpiada.**")
    
    async def cmd_queue(self, message, args):
        """Muestra la cola de reproducción o reanuda la reproducción."""
        server_id = str(message.guild.id)
        
        # Verificar si es el subcomando resume
        if args and args[0].lower() == 'resume':
            # Reanudar reproducción
            if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
                await message.channel.send("🎤 **No estoy conectado a ningún canal.**")
                return
            
            if self.voice_clients[server_id].is_playing():
                await message.channel.send("🎵 **Ya estoy reproduciendo.**")
                return
            
            # Intentar reproducir la siguiente canción
            await self._play_next(server_id, message.channel)
            return
        
        # Verificar si es el subcomando clear
        if args and args[0].lower() == 'clear':
            # Limpiar cola
            from db_role_mc import get_mc_db_instance
            from agent_db import get_active_server_name
            server_name = get_active_server_name() or "default"
            db_mc = get_mc_db_instance(server_name)
            
            db_mc.limpiar_queue(server_id, str(message.channel.id))
            await message.channel.send("🧹 **Cola limpiada.**")
            return
        
        # Mostrar cola (comportamiento original)
        # Obtener cola de la BD
        from db_role_mc import get_mc_db_instance
        from agent_db import get_active_server_name
        server_name = get_active_server_name() or "default"
        db_mc = get_mc_db_instance(server_name)
        
        queue = db_mc.obtener_queue(server_id, str(message.channel.id))
        
        if not queue:
            await message.channel.send("📭 **La cola está vacía.**")
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
        
        await message.channel.send(embed=embed)
    
    async def cmd_clear(self, message, args):
        """Limpia la cola de reproducción."""
        server_id = str(message.guild.id)
        
        # Verificar permisos (DJ o administrador)
        if not self._check_dj_permissions(message.author):
            await message.channel.send("🚫 **Necesitas rol de DJ o ser administrador para usar este comando.**")
            return
        
        # Limpiar cola de BD
        from db_role_mc import get_mc_db_instance
        from agent_db import get_active_server_name
        server_name = get_active_server_name() or "default"
        db_mc = get_mc_db_instance(server_name)
        
        db_mc.limpiar_queue(server_id, str(message.channel.id))
        
        await message.channel.send("🗑️ **Cola de reproducción limpiada.**")
    
    async def cmd_pause(self, message, args):
        """Pausa la reproducción."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_playing():
            await message.channel.send("🎵 **No hay nada reproduciéndose.**")
            return
        
        if not self._check_same_voice_channel(message.author, self.voice_clients[server_id]):
            await message.channel.send("🎤 **Debes estar en el mismo canal de voz que el bot.**")
            return
        
        self.voice_clients[server_id].pause()
        await message.channel.send("⏸️ **Reproducción pausada.**")
    
    async def cmd_resume(self, message, args):
        """Reanuda la reproducción."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_paused():
            await message.channel.send("🎵 **No hay nada pausado.**")
            return
        
        if not self._check_same_voice_channel(message.author, self.voice_clients[server_id]):
            await message.channel.send("🎤 **Debes estar en el mismo canal de voz que el bot.**")
            return
        
        self.voice_clients[server_id].resume()
        await message.channel.send("▶️ **Reproducción reanudada.**")
    
    async def cmd_nowplaying(self, message, args):
        """Muestra la canción actual."""
        server_id = str(message.guild.id)
        
        if server_id not in self.now_playing:
            await message.channel.send("🎵 **No hay nada reproduciéndose.**")
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
        
        await message.channel.send(embed=embed)
    
    async def cmd_history(self, message, args):
        """Muestra el historial de reproducción."""
        server_id = str(message.guild.id)
        
        # Obtener historial de BD
        from db_role_mc import get_mc_db_instance
        from agent_db import get_active_server_name
        server_name = get_active_server_name() or "default"
        db_mc = get_mc_db_instance(server_name)
        
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
        
        await message.channel.send(embed=embed)
    
    async def cmd_leave(self, message, args):
        """El bot sale del canal de voz."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients:
            await message.channel.send("🎵 **No estoy conectado a ningún canal.**")
            return
        
        if not self._check_dj_permissions(message.author):
            await message.channel.send("🚫 **Necesitas rol de DJ o ser administrador para usar este comando.**")
            return
        
        await self.voice_clients[server_id].disconnect()
        del self.voice_clients[server_id]
        if server_id in self.now_playing:
            del self.now_playing[server_id]
        
        await message.channel.send("👋 **Saliendo del canal de voz.**")
    
    async def cmd_volume(self, message, args):
        """Ajusta el volumen de la reproducción (0-100)."""
        server_id = str(message.guild.id)
        
        if server_id not in self.voice_clients or not self.voice_clients[server_id].is_connected():
            await message.channel.send("🎤 **No estoy conectado a ningún canal.**")
            return
        
        if not args:
            await message.channel.send("🎵 **Uso:** `!mc volume <0-100>`")
            return
        
        try:
            volume = int(args[0])
            if volume < 0 or volume > 100:
                await message.channel.send("🎵 **El volumen debe estar entre 0 y 100.**")
                return
            
            # Convertir a 0.0-1.0 para discord.py
            volume_float = volume / 100.0
            self.voice_clients[server_id].source.volume = volume_float
            
            await message.channel.send(f"🔊 **Volumen ajustado a {volume}%**")
        except ValueError:
            await message.channel.send("🎵 **El volumen debe ser un número entre 0 y 100.**")
        except Exception as e:
            logger.exception(f"Error ajustando volumen: {e}")
            await message.channel.send("❌ **No pude ajustar el volumen.**")
    
    async def cmd_help(self, message, args):
        """Muestra la ayuda de comandos del MC."""
        embed = discord.Embed(
            title="🎵 MC - Master of Ceremonies",
            description="Comandos de música para Discord",
            color=discord.Color.gold()
        )
        
        commands = [
            ("!mc play <canción>", "Reproduce o agrega una canción"),
            ("!mc skip", "Salta la canción actual"),
            ("!mc queue", "Muestra la cola de reproducción"),
            ("!mc clear", "Limpia la cola (requiere rol DJ)"),
            ("!mc pause", "Pausa la reproducción"),
            ("!mc resume", "Reanuda la reproducción"),
            ("!mc nowplaying", "Muestra la canción actual"),
            ("!mc history", "Muestra el historial"),
            ("!mc leave", "Sale del canal de voz (requiere rol DJ)"),
            ("!mc help", "Muestra esta ayuda")
        ]
        
        for cmd, desc in commands:
            embed.add_field(name=cmd, value=desc, inline=False)
        
        embed.set_footer(text="Nota: Algunos comandos requieren rol de DJ o permisos de administrador")
        
        await message.author.send(embed=embed)
        await message.channel.send("✅ Te he enviado la ayuda de música por mensaje privado 📩")
    
    async def _play_next(self, server_id: str, channel):
        """Reproduce la siguiente canción de la cola."""
        try:
            # Obtener siguiente canción de la BD
            from db_role_mc import get_mc_db_instance
            from agent_db import get_active_server_name
            server_name = get_active_server_name() or "default"
            db_mc = get_mc_db_instance(server_name)
            
            queue = db_mc.obtener_queue(server_id, str(channel.id))
            
            if not queue:
                # No hay más canciones, desconectar después de 5 minutos
                await channel.send("🎵 **Fin de la cola. Me desconectaré en 5 minutos si no se agregan más canciones.**")
                
                # Programar desconexión
                await asyncio.sleep(300)  # 5 minutos
                
                if server_id in self.voice_clients and self.voice_clients[server_id].is_connected():
                    if not self.voice_clients[server_id].is_playing():
                        await self.voice_clients[server_id].disconnect()
                        del self.voice_clients[server_id]
                        if server_id in self.now_playing:
                            del self.now_playing[server_id]
                        await channel.send("👋 **Desconectado por inactividad.**")
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
            
            # Reproducir
            voice_client = self.voice_clients[server_id]
            voice_client.play(audio_source, after=lambda e: self._after_song(e, server_id, channel))
            
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
            embed = discord.Embed(
                title="🎵 Ahora Reproduciendo",
                color=discord.Color.green()
            )
            embed.add_field(name="Título", value=title, inline=False)
            embed.add_field(name="Artista", value=artist, inline=True)
            embed.add_field(name="Duración", value=duration, inline=True)
            embed.add_field(name="Agregada por", value=user_name, inline=True)
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.exception(f"Error reproduciendo siguiente canción: {e}")
            await channel.send("❌ **Error reproduciendo la siguiente canción.**")
    
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
        
        # Programar siguiente canción
        asyncio.create_task(self._play_next_safe(server_id, channel))
    
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
