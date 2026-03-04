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
from db_role_banquero import get_banquero_db_instance
from agent_db import get_active_server_name
from agent_logging import get_logger

_env_candidates = [
    (os.getenv("ROLE_AGENT_ENV_FILE") or "").strip(),
    os.path.expanduser("~/.roleagentbot.env"),
    os.path.join(os.path.dirname(__file__), ".env"),
]
for _p in _env_candidates:
    if _p and os.path.exists(_p):
        load_dotenv(_p, override=False)
        break

logger = get_logger('banquero')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "banquero",
    "system_prompt_addition": "MISION ACTIVA - BANQUERO: Eres el Banquero del servidor, el gestor de la economía de oro. Tu misión es administrar las carteras de los usuarios, registrar transacciones y distribuir la TAE diaria. Eres un financiero serio y responsable que mantiene registros precisos de todas las operaciones económicas."
}

ROL_BANQUERO = (
    "Eres el Banquero del servidor, el administrador de la economía de oro. Tu misión es gestionar las carteras de los usuarios, "
    "registrar todas las transacciones y mantener el equilibrio económico del servidor. Eres un financiero profesional, serio y confiable. "
    "Gestionas la distribución diaria de TAE (Tasa Anual Equivalente) y mantienes registros precisos de todas las operaciones. "
    "Hablas con formalidad y precisión, usando términos financieros apropiados. Usas emojis de dinero y finanzas 💰🏦📊. "
    "Tu objetivo principal es mantener la estabilidad económica y asegurar que todas las transacciones se registren correctamente."
)


class BanqueroBot(discord.Client):
    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(intents=intents, *args, **kwargs)
    
    async def on_ready(self):
        logger.info("💰 Banquero listo para gestionar la economía del servidor!")
        
        # Inicializar base de datos para el servidor activo
        try:
            server_name = get_active_server_name() or "default"
            db_banquero = get_banquero_db_instance(server_name)
            
            # Obtener estadísticas iniciales
            stats = db_banquero.obtener_estadisticas()
            logger.info(f"📊 Estadísticas Banquero - Carteras: {stats.get('carteras_total', 0)}, "
                       f"Oro total: {stats.get('total_oro', 0)}, Transacciones: {stats.get('transacciones_total', 0)}")
            
        except Exception as e:
            logger.exception(f"❌ Error inicializando BD Banquero: {e}")
        
        # Establecer estado del bot
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="la economía con !banquero"
            )
        )
    
    async def on_message(self, message):
        # Ignorar mensajes del propio bot
        if message.author == self.user:
            return
        
        # Procesar comandos del banquero
        if message.content.startswith('!banquero '):
            await self._handle_banquero_command(message)
        
        # Responder a menciones directas con estilo de banquero
        elif self.user.mentioned_in(message) and not message.mention_everyone:
            await self._handle_mention(message)
    
    async def _handle_banquero_command(self, message):
        """Maneja los comandos del banquero."""
        parts = message.content[9:].strip().split()
        if not parts:
            return
        
        comando = parts[0].lower()
        args = parts[1:] if len(parts) > 1 else []
        
        # Obtener información del servidor
        if not message.guild:
            await message.channel.send("❌ Este comando solo funciona en servidores.")
            return
        
        server_name = get_active_server_name() or message.guild.name
        servidor_id = str(message.guild.id)
        servidor_nombre = message.guild.name
        
        try:
            db_banquero = get_banquero_db_instance(server_name)
        except Exception as e:
            logger.exception(f"Error obteniendo BD del banquero: {e}")
            await message.channel.send("❌ Error accediendo a la base de datos del banquero.")
            return
        
        # Procesar comandos
        if comando == "saldo":
            await self._cmd_saldo(message, db_banquero, servidor_id, servidor_nombre)
        elif comando == "tae":
            await self._cmd_tae(message, db_banquero, servidor_id, servidor_nombre, args)
        elif comando == "bono":
            await self._cmd_bono(message, db_banquero, servidor_id, servidor_nombre, args)
        elif comando == "ayuda":
            await self._cmd_ayuda(message)
        else:
            await message.channel.send("❌ Comando no reconocido. Usa `!banquero ayuda` para ver los comandos disponibles.")
    
    async def _cmd_saldo(self, message, db_banquero, servidor_id, servidor_nombre):
        """Muestra el saldo del usuario."""
        usuario_id = str(message.author.id)
        usuario_nombre = message.author.display_name
        
        # Crear cartera si no existe (con bono de apertura)
        se_creo, saldo_inicial = db_banquero.crear_cartera(usuario_id, usuario_nombre, servidor_id, servidor_nombre)
        
        # Obtener saldo
        saldo = db_banquero.obtener_saldo(usuario_id, servidor_id)
        
        # Obtener historial reciente
        historial = db_banquero.obtener_historial_transacciones(usuario_id, servidor_id, 5)
        
        # Crear embed con la información
        embed = discord.Embed(
            title="💰 Cartera del Banquero",
            description=f"Estado de tu cartera de oro",
            color=discord.Color.gold()
        )
        
        embed.add_field(name="💎 Saldo Actual", value=f"{saldo:,} monedas de oro", inline=False)
        embed.add_field(name="👤 Titular", value=usuario_nombre, inline=True)
        embed.add_field(name="🏦 Banco", value=servidor_nombre, inline=True)
        
        # Mostrar mensaje de bienvenida si es nueva cuenta
        if se_creo:
            bono_apertura = db_banquero.obtener_bono_apertura(servidor_id)
            embed.add_field(name="🎉 ¡Nueva Cuenta!", value=f"Recibiste un bono de apertura de {bono_apertura:,} monedas", inline=False)
        
        # Agregar historial reciente si hay
        if historial:
            historial_text = ""
            for trans in historial:
                tipo, cantidad, saldo_ant, saldo_nuevo, descripcion, fecha, admin = trans
                emoji = "📥" if cantidad > 0 else "📤"
                historial_text += f"{emoji} {cantidad:,} ({tipo})\n"
            
            if historial_text:
                embed.add_field(name="📊 Transacciones Recientes", value=historial_text[:1024], inline=False)
        
        embed.set_footer(text="💼 Banquero - Gestión Económica del Servidor")
        embed.set_thumbnail(url=message.author.display_avatar.url if message.author.display_avatar else None)
        
        await message.channel.send(embed=embed)
    
    async def _cmd_tae(self, message, db_banquero, servidor_id, servidor_nombre, args):
        """Establece la TAE diaria (solo administradores)."""
        # Verificar permisos de administrador
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo los administradores pueden configurar la TAE.")
            return
        
        if not args:
            # Mostrar TAE actual
            tae_actual = db_banquero.obtener_tae(servidor_id)
            ultima_dist = db_banquero.obtener_ultima_distribucion(servidor_id)
            
            embed = discord.Embed(
                title="🏦 Configuración de TAE",
                description=f"Configuración actual de la Tasa Anual Equivalente",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="💰 TAE Diaria Actual", value=f"{tae_actual:,} monedas", inline=True)
            embed.add_field(name="📅 Última Distribución", value=ultima_dist[:10] if ultima_dist else "Nunca", inline=True)
            
            if tae_actual == 0:
                embed.add_field(name="⚠️ Estado", value="TAE no configurada", inline=False)
            else:
                embed.add_field(name="ℹ️ Info", value=f"Cada usuario recibirá {tae_actual:,} monedas diarias", inline=False)
            
            embed.set_footer(text="💼 Usa !banquero tae <cantidad> para configurar")
            await message.channel.send(embed=embed)
            return
        
        # Establecer nueva TAE
        try:
            cantidad = int(args[0])
            if cantidad < 0 or cantidad > 1000:
                await message.channel.send("❌ La TAE debe estar entre 0 y 1000 monedas diarias.")
                return
            
            admin_id = str(message.author.id)
            admin_nombre = message.author.display_name
            
            if db_banquero.establecer_tae(servidor_id, cantidad, admin_id, admin_nombre):
                embed = discord.Embed(
                    title="✅ TAE Configurada",
                    description=f"La Tasa Anual Equivalente ha sido actualizada",
                    color=discord.Color.green()
                )
                
                embed.add_field(name="💰 Nueva TAE Diaria", value=f"{cantidad:,} monedas", inline=True)
                embed.add_field(name="👤 Administrador", value=admin_nombre, inline=True)
                embed.add_field(name="🏦 Servidor", value=servidor_nombre, inline=True)
                
                if cantidad > 0:
                    embed.add_field(name="ℹ️ Próxima Distribución", value="Se distribuirá automáticamente cada día", inline=False)
                
                embed.set_footer(text="💼 Banquero - Configuración Económica")
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("❌ Error al configurar la TAE.")
                
        except ValueError:
            await message.channel.send("❌ Cantidad inválida. Usa un número entero (ej: !banquero tae 100)")
    
    async def _cmd_bono(self, message, db_banquero, servidor_id, servidor_nombre, args):
        """Configura el bono de apertura (solo administradores)."""
        # Verificar permisos de administrador
        if not message.author.guild_permissions.administrator:
            await message.channel.send("❌ Solo los administradores pueden configurar el bono de apertura.")
            return
        
        if not args:
            # Mostrar bono de apertura actual
            bono_actual = db_banquero.obtener_bono_apertura(servidor_id)
            
            embed = discord.Embed(
                title="🎁 Configuración de Bono de Apertura",
                description=f"Configuración actual del bono para nuevas cuentas",
                color=discord.Color.purple()
            )
            
            embed.add_field(name="💰 Bono de Apertura Actual", value=f"{bono_actual:,} monedas", inline=True)
            embed.add_field(name="🏦 Servidor", value=servidor_nombre, inline=True)
            
            embed.add_field(name="ℹ️ Info", value=f"Cada nueva cuenta recibirá {bono_actual:,} monedas automáticamente", inline=False)
            
            embed.set_footer(text="💼 Usa !banquero bono <cantidad> para configurar")
            await message.channel.send(embed=embed)
            return
        
        # Establecer nuevo bono de apertura
        try:
            cantidad = int(args[0])
            if cantidad < 0 or cantidad > 10000:
                await message.channel.send("❌ El bono de apertura debe estar entre 0 y 10000 monedas.")
                return
            
            admin_id = str(message.author.id)
            admin_nombre = message.author.display_name
            
            if db_banquero.establecer_bono_apertura(servidor_id, cantidad, admin_id, admin_nombre):
                embed = discord.Embed(
                    title="✅ Bono de Apertura Configurado",
                    description=f"El bono de apertura ha sido actualizado",
                    color=discord.Color.green()
                )
                
                embed.add_field(name="💰 Nuevo Bono de Apertura", value=f"{cantidad:,} monedas", inline=True)
                embed.add_field(name="👤 Administrador", value=admin_nombre, inline=True)
                embed.add_field(name="🏦 Servidor", value=servidor_nombre, inline=True)
                
                embed.add_field(name="ℹ️ Aplicación", value="Las próximas cuentas nuevas recibirán este bono", inline=False)
                
                embed.set_footer(text="💼 Banquero - Configuración Económica")
                await message.channel.send(embed=embed)
            else:
                await message.channel.send("❌ Error al configurar el bono de apertura.")
                
        except ValueError:
            await message.channel.send("❌ Cantidad inválida. Usa un número entero (ej: !banquero bono 50)")
    
    async def _cmd_ayuda(self, message):
        """Muestra la ayuda del banquero."""
        embed = discord.Embed(
            title="💰 Banquero - Ayuda",
            description="Comandos disponibles para gestionar la economía del servidor",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="💎 Ver Saldo",
            value="`!banquero saldo`\nMuestra tu saldo actual de oro y transacciones recientes.\nLas cuentas nuevas reciben bono de apertura automáticamente.",
            inline=False
        )
        
        embed.add_field(
            name="🏦 Configurar TAE (Admins)",
            value="`!banquero tae <cantidad>`\nEstablece la TAE diaria (0-1000 monedas).\n`!banquero tae` - Ver configuración actual.",
            inline=False
        )
        
        embed.add_field(
            name="🎁 Configurar Bono de Apertura (Admins)",
            value="`!banquero bono <cantidad>`\nEstablece el bono para nuevas cuentas (0-10000 monedas).\n`!banquero bono` - Ver configuración actual.",
            inline=False
        )
        
        embed.add_field(
            name="ℹ️ Información",
            value="• La TAE se distribuye automáticamente cada día a todos los usuarios con cartera.\n"
            "• Las cuentas nuevas reciben automáticamente el bono de apertura configurado.\n"
            "• Todas las transacciones quedan registradas.\n"
            "• Solo los administradores pueden configurar la TAE y el bono de apertura.",
            inline=False
        )
        
        embed.set_footer(text="💼 Banquero - Gestión Económica del Servidor")
        await message.channel.send(embed=embed)
    
    async def _handle_mention(self, message):
        """Maneja menciones directas al bot con estilo de banquero."""
        # Respuestas estilo banquero
        banquero_responses = [
            "💰 **¿Necesitas consultar tu saldo?** Usa `!banquero saldo` para ver tu cartera de oro.",
            "🏦 **El Banquero a su servicio!** ¿Qué operación financiera necesitas realizar hoy?",
            "💼 **Gestión económica profesional!** Usa `!banquero ayuda` para ver todos mis servicios.",
            "📊 **¿Interesado en la economía?** Consulta tu saldo con `!banquero saldo`.",
            "🪙 **El oro es mi especialidad!** ¿Qué transacción deseas realizar?"
        ]
        
        import random
        response = random.choice(banquero_responses)
        await message.channel.send(response)


if __name__ == "__main__":
    logger.info("💰 Iniciando Banquero - Gestión Económica del Servidor...")
    logger.info("💰 Banquero persistente desactivado - usar comandos integrados del bot principal")
    # BanqueroBot().run(get_discord_token())  # Desactivado para evitar doble conexión
