import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import discord
import asyncio
import random
import re
from discord.ext import commands
from dotenv import load_dotenv
load_dotenv()
from agent_engine import PERSONALIDAD, pensar, get_discord_token
from agent_db import get_global_db
from agent_logging import get_logger

logger = get_logger('anillo')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "buscar_anillo",
    "system_prompt_addition": "MISION ACTIVA - BUSCAR ANILLO: Buscas el \"anillo uniko\" para tu jefe. Si ya acusaste a alguien de tener el anillo, RECUERDALO y mencionalo."
}

class AnilloBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
    
    async def on_ready(self):
        logger.info("👁️ Bot del anillo iniciado...")
        
        # Ejecutar búsqueda automática del anillo
        await self.buscar_anillo_automatico()
        
        # Limpiar BD antigua
        filas = await asyncio.to_thread(get_global_db().limpiar_interacciones_antiguas, 30)
        logger.info(f"🧹 Limpieza: {filas} registros borrados.")
        
        await self.close()
    
    async def buscar_anillo_automatico(self):
        """Búsqueda automática del anillo."""
        logger.info("🔍 Iniciando búsqueda automática del anillo...")
        
        for guild in self.guilds:
            miembros = [m for m in guild.members if not m.bot]
            if not miembros:
                continue
            
            objetivo = random.choice(miembros)
            
            # Limitar: max 2 ANILLO por servidor al día
            cuenta_anillo = await asyncio.to_thread(get_global_db().contar_interacciones_tipo_ultimo_dia, "ANILLO", guild.id)
            if cuenta_anillo >= 2:
                logger.info(f"🔕 [Límite] Ya hubo {cuenta_anillo} ANILLO hoy en servidor {guild.id}, saltando.")
                continue
            
            res = await asyncio.to_thread(
                pensar,
                f"Acusa a {objetivo.name} de tener el Anillo unico. Intimidale para que te lo entregue, usando tu personalidad de orco."
            )
            
            try:
                await objetivo.send(f"👁️ **EL OJO QUE TODO LO VE...**\n{res}")
                
                # Registrar en tabla principal
                await asyncio.to_thread(
                    get_global_db().registrar_interaccion,
                    objetivo.id, objetivo.name, "ANILLO", 
                    "Búsqueda del anillo", None, guild.id,
                    metadata={"respuesta": res, "rol": "buscar_anillo"}
                )
                logger.info(f"✅ ANILLO enviado a {objetivo.name}")
            except Exception as e:
                logger.warning(f"⚠️ Error enviando ANILLO a {objetivo}: {e}")
    
    async def detectar_anillo_automatico(self, message):
        """Detecta si alguien menciona tener el anillo."""
        mensaje_lower = message.content.lower()
        palabras_anillo = ["anillo", "anilo", "ring", "anillo unico", "anillo único", "one ring"]
        palabras_posesion = ["tengo", "tenemos", "tiene", "encontre", "encontré", "consegui", "conseguí", "poseo", "mi anillo", "el anillo es mio", "es mío"]
        
        detecta_anillo = any(palabra in mensaje_lower for palabra in palabras_anillo)
        detecta_posesion = any(palabra in mensaje_lower for palabra in palabras_posesion)
        
        # Si menciona el anillo + posesión, Putre reacciona automáticamente
        if detecta_anillo and detecta_posesion and not isinstance(message.channel, discord.DMChannel):
            servidor_id = getattr(message.guild, 'id', None)
            
            # Limitar detecciones automáticas: max 3 por servidor al día
            if servidor_id:
                cuenta_detecciones = await asyncio.to_thread(get_global_db().contar_interacciones_tipo_ultimo_dia, "DETECCION_ANILLO", servidor_id)
                if cuenta_detecciones < 3:
                    async with message.channel.typing():
                        prompt = f"{message.author.name} acaba de decir que tiene el anillo único! Reacciona inmediatamente con sorpresa y exige que te lo entregue. Sé muy insistente."
                        respuesta = await asyncio.to_thread(pensar, prompt)
                        
                        try:
                            await message.reply(f"👁️ {respuesta}")
                            
                            # Registrar en tabla principal
                            await asyncio.to_thread(
                                get_global_db().registrar_interaccion,
                                message.author.id, message.author.name, "DETECCION_ANILLO",
                                message.content, message.channel.id, servidor_id,
                                metadata={"respuesta": respuesta, "mensaje_original": message.content, "rol": "buscar_anillo"}
                            )
                            logger.info(f"✅ Detección automática del anillo: {message.author.name}")
                            return True
                        except Exception as e:
                            logger.warning(f"⚠️ Error en detección automática: {e}")
        return False
    
    async def procesar_sospechas_terceros(self, message):
        """Procesa sospechas de terceros cuando mencionan a otros usuarios."""
        mensaje_lower = message.content.lower()
        palabras_anillo = ["anillo", "anilo", "ring", "anillo unico", "anillo único", "one ring"]
        
        detecta_anillo = any(palabra in mensaje_lower for palabra in palabras_anillo)
        usuarios_mencionados = message.mentions
        
        if detecta_anillo and usuarios_mencionados:
            # Filtrar menciones (excluir al bot y al autor)
            acusados = [u for u in usuarios_mencionados if u.id != self.user.id and u.id != message.author.id and not u.bot]
            
            if acusados:
                # Registrar acusación informal para cada usuario mencionado
                servidor_id = getattr(message.guild, 'id', None)
                for acusado in acusados:
                    await asyncio.to_thread(
                        get_global_db().registrar_interaccion,
                        acusado.id, acusado.name, "SOSPECHA_ANILLO",
                        f"{message.author.name} mencionó que {acusado.name} tiene el anillo",
                        message.channel.id, servidor_id,
                        metadata={
                            "informante_id": str(message.author.id),
                            "informante_nombre": message.author.name,
                            "mensaje_original": message.content,
                            "rol": "buscar_anillo"
                        }
                    )
                    logger.info(f"📝 SOSPECHA registrada: {acusado.name} (por {message.author.name})")
    
    async def on_message(self, message):
        if message.author == self.user:
            return
        
        await self.process_commands(message)
        
        # Procesar detecciones automáticas del anillo
        if await self.detectar_anillo_automatico(message):
            return  # Si hubo detección, no procesar más
        
        # Procesar sospechas de terceros si mencionan al bot o es DM
        if self.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
            await self.procesar_sospechas_terceros(message)
    
    @commands.command()
    async def acusaranillo(self, ctx, miembro: discord.Member = None):
        """Permite a un usuario acusar a otro de tener el anillo único."""
        if not miembro:
            await ctx.send("👹 GRRR ke kieres ke aga umano? dime a KIEN akusar! usa: !acusar @usuario")
            return
        
        if miembro.bot:
            await ctx.send("👹 BLEGH putre no akusar a bots estupidos! solo umanos pueden tener el anillo!")
            return
        
        if miembro.id == ctx.author.id:
            await ctx.send("👹 JUARJUAR umano tonto te akusas a ti mismo? si tienes el anillo dalo a putre aora!")
            return
        
        # Verificar límites diarios de acusaciones (max 5 por servidor al día)
        servidor_id = ctx.guild.id if ctx.guild else None
        if servidor_id:
            cuenta_acusaciones = await asyncio.to_thread(get_global_db().contar_interacciones_tipo_ultimo_dia, "ACUSACION_ANILLO", servidor_id)
            if cuenta_acusaciones >= 5:
                await ctx.send(f"👹 BRRR ya ubo muchas akusaciones oy ({cuenta_acusaciones})! putre esta kansado, vuelve mañana!")
                return
        
        # Generar mensaje de acusación
        acusador_nombre = ctx.author.name
        acusado_nombre = miembro.name
        
        prompt = f"{acusador_nombre} te acusa de tener el Anillo Unico! Interroga a {acusado_nombre} de forma intimidante y exige que te lo entregue si lo tiene. Recuerda que buscas el anillo para tu jefe."
        
        try:
            async with ctx.typing():
                respuesta = await asyncio.to_thread(pensar, prompt)
            
            # Enviar mensaje al acusado por privado
            try:
                await miembro.send(f"👁️ **ACUSACIÓN DEL ANILLO ÚNICO**\n\n{respuesta}\n\n_({acusador_nombre} te ha acusado de tener el anillo)_")
                
                # Confirmar en el canal público
                await ctx.send(f"👹 GRRR {ctx.author.mention} a akusado a {miembro.mention}! putre va a investigar esto...")
                
                # Registrar la acusación en tabla principal
                await asyncio.to_thread(
                    get_global_db().registrar_interaccion,
                    miembro.id, acusado_nombre, "ACUSACION_ANILLO",
                    f"Acusado por {acusador_nombre} de tener el anillo",
                    None, servidor_id,
                    metadata={
                        "acusador_id": ctx.author.id,
                        "acusador_nombre": acusador_nombre,
                        "rol": "buscar_anillo"
                    }
                )
                
                logger.info(f"✅ Acusación procesada: {acusador_nombre} -> {acusado_nombre}")
                
            except discord.Forbidden:
                await ctx.send(f"👹 BLEGH {miembro.mention} tiene mensajes privados serrados! no puedo interrogarle! dile ke los abra si kiere ablar kon putre!")
            except Exception as e:
                logger.warning(f"⚠️ Error enviando acusación a {miembro}: {e}")
                await ctx.send(f"👹 GRRR algo salio mal al intentar ablar kon {miembro.mention}! putre esta konfundido!")
        
        except Exception as e:
            logger.warning(f"⚠️ Error en comando acusar: {e}")
            await ctx.send("👹 BLEGH putre tiene problema! no puede pensar aora, intenta luego!")

if __name__ == "__main__":
    AnilloBot().run(get_discord_token())
