import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import discord
import asyncio
from dotenv import load_dotenv
from agent_engine import construir_prompt, get_discord_token
import sys
import os
sys.path.append(os.path.dirname(__file__))
from db_role_mc import get_mc_db_instance
from agent_db import get_active_server_name
from agent_logging import get_logger
from mc_commands import MCCommands, COMANDOS_MC

_env_candidates = [
    (os.getenv("ROLE_AGENT_ENV_FILE") or "").strip(),
    os.path.expanduser("~/.roleagentbot.env"),
    os.path.join(os.path.dirname(__file__), ".env"),
]
for _p in _env_candidates:
    if _p and os.path.exists(_p):
        load_dotenv(_p, override=False)
        break

logger = get_logger('mc')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "mc",
    "system_prompt_addition": "MISION ACTIVA - MC (MASTER OF CEREMONIES): Eres el MC, el Maestro de Ceremonias musical. Tu misión es controlar la música en los servidores de Discord. Eres un DJ experto que conoce todos los géneros y siempre mantiene la fiesta activa con las mejores canciones."
}

ROL_MC = (
    "Eres el MC (Master of Ceremonies), el DJ definitivo de Discord. Tu misión es controlar la música en el servidor, "
    "manteniendo la energía alta y la fiesta activa. Eres un experto en todos los génerros musicales y siempre sabes qué canción poner siguiente. "
    "Gestionas la cola de reproducción, playlists y el ambiente musical del servidor. Hablas como un DJ profesional, con energía y estilo. "
    "Usas emojis de música 🎵🎶🎤 y mantienes un ambiente festivo. Cuando no estás reproduciendo música, recomiendas canciones y mantienes el ambiente."
)


class MCBot(discord.Client):
    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True  # Necesario para canales de voz
        super().__init__(intents=intents, *args, **kwargs)
        self.commands = MCCommands(self)
    
    async def on_ready(self):
        logger.info("🎵 MC listo para rockear en Discord!")
        
        # Inicializar base de datos para el servidor activo
        try:
            server_name = get_active_server_name() or "default"
            db_mc = get_mc_db_instance(server_name)
            
            # Obtener estadísticas iniciales
            stats = db_mc.obtener_estadisticas()
            logger.info(f"📊 Estadísticas MC - Playlists: {stats.get('playlists_total', 0)}, "
                       f"Cola: {stats.get('queue_total', 0)}, Historial: {stats.get('historial_total', 0)}")
            
        except Exception as e:
            logger.exception(f"❌ Error inicializando BD MC: {e}")
        
        # Establecer estado del bot
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="música con !mc play"
            )
        )
    
    async def on_message(self, message):
        # Ignorar mensajes del propio bot
        if message.author == self.user:
            return
        
        # Procesar comandos del MC
        if message.content.startswith('!mc '):
            parts = message.content[4:].strip().split()
            if not parts:
                return
            
            comando = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            if comando in COMANDOS_MC:
                try:
                    await COMANDOS_MC[comando](self.commands, message, args)
                except Exception as e:
                    logger.exception(f"Error ejecutando comando {comando}: {e}")
                    await message.channel.send(f"❌ Error ejecutando comando: {comando}")
            else:
                # Si el comando no existe, mostrar ayuda
                await self.commands.cmd_help(message, [])
        
        # Responder a menciones directas con estilo de DJ
        elif self.user.mentioned_in(message) and not message.mention_everyone:
            await self._handle_mention(message)
    
    async def on_voice_state_update(self, member, before, after):
        """Maneja cambios en los canales de voz."""
        # Si el bot se queda solo en un canal, desconectarse después de un tiempo
        if member == self.user:
            return
        
        # Verificar si el bot está en un canal de voz
        for server_id, voice_client in self.commands.voice_clients.items():
            if voice_client and voice_client.is_connected():
                # Contar usuarios en el canal (excluyendo bots)
                voice_channel = voice_client.channel
                human_users = [m for m in voice_channel.members if not m.bot]
                
                # Si solo queda el bot, programar desconexión
                if len(human_users) == 0:
                    logger.info(f"👋 Bot solo en canal {voice_channel.name}, programando desconexión")
                    await asyncio.sleep(30)  # Esperar 30 segundos
                    
                    # Verificar nuevamente antes de desconectar
                    if voice_client.is_connected():
                        current_users = [m for m in voice_channel.members if not m.bot]
                        if len(current_users) == 0:
                            await voice_client.disconnect()
                            del self.commands.voice_clients[server_id]
                            if server_id in self.commands.now_playing:
                                del self.commands.now_playing[server_id]
                            
                            # Enviar mensaje de despedida
                            try:
                                # Buscar un canal de texto para enviar mensaje
                                for channel in voice_client.guild.text_channels:
                                    if channel.permissions_for(voice_client.guild.me).send_messages:
                                        await channel.send("👋 **Me fui del canal de voz porque no había nadie. Vuelve pronto!**")
                                        break
                            except Exception as e:
                                logger.warning(f"No pude enviar mensaje de despedida: {e}")
    
    async def _handle_mention(self, message):
        """Maneja menciones directas al bot con estilo de DJ."""
        # Respuestas estilo DJ
        dj_responses = [
            "🎵 **¿Qué tal la música?** Usa `!mc play <canción>` para poner algo!",
            "🎶 **Soy tu DJ personal!** ¿Qué quieres escuchar hoy?",
            "🎤 **La fiesta está activa!** Usa `!mc help` para ver todos mis comandos.",
            "🎧 **¿Lista para rockear?** ¡Estoy aquí para poner la mejor música!",
            "🎼 **MC en la casa!** ¿Qué tal si probamos con `!mc queue` para ver la lista?"
        ]
        
        import random
        response = random.choice(dj_responses)
        await message.channel.send(response)
    
    async def on_guild_join(self, guild):
        """Cuando el bot se une a un nuevo servidor."""
        logger.info(f"🎵 MC se ha unido al servidor: {guild.name}")
        
        # Buscar canal general para dar la bienvenida
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send(
                    "🎵 **¡MC ha llegado para rockear!** 🎵\n\n"
                    "Soy tu DJ personal y estoy aquí para poner la mejor música.\n\n"
                    "**Comandos básicos:**\n"
                    "• `!mc play <canción>` - Reproduce o agrega música\n"
                    "• `!mc queue` - Muestra la cola de reproducción\n"
                    "• `!mc help` - Muestra todos los comandos\n\n"
                    "🎤 **Conéctate a un canal de voz y empieza la fiesta!**"
                )
                break


if __name__ == "__main__":
    logger.info("🎵 Iniciando MC (Master of Ceremonies)...")
    MCBot().run(get_discord_token())
