import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import discord
import asyncio
import random
from discord.ext import tasks
from dotenv import load_dotenv
load_dotenv()
from agent_engine import PERSONALIDAD, pensar, get_discord_token
from agent_db import get_global_db
from agent_logging import get_logger

logger = get_logger('oro')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "pedir_oro",
    "system_prompt_addition": "MISION ACTIVA - PEDIR ORO: Necesitas oro para traer a tu familia orca contigo. Si ya pediste oro recientemente, RECUERDALO y mencionalo."
}

# Lista de razones variadas para pedir oro
RAZONES_PEDIR_ORO = [
    "para traer a tu familia orca contigo",
    "para komprar armas nuevas y aser la guerra",
    "para pagar tributo al jefe orko y ke no te mate",
    "porke tienes ambre y no keres komer karne umana otra ves",
    "para komprar armadura nueva porke la tuya esta rota",
    "porke perdiste todo tu oro jugando kon otros orkos",
    "para komprar un lobo gigante ke te ayude en batallas",
    "porke keres aser una fiesta orca kon komida y bebida",
    "para arreglar tu kasa ke se esta kayendo",
    "porke otros orkos te robaron y nesesitas rekuperar",
    "para komprar veneno para tus flechas",
    "porke keres impresionar a una orka ke te gusta",
    "para pagar deudas kon orkos peligrosos",
    "porke keres komprar un jabalí de guerra"
]

class OroBot(discord.Client):
    def __init__(self, *args, **kwargs):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        super().__init__(intents=intents, *args, **kwargs)
    
    async def on_ready(self):
        logger.info("👹 Bot de oro iniciado...")
        
        # Ejecutar tarea de pedir oro
        await self.tarea_pedir_oro()
        
        # Limpiar BD antigua
        filas = await asyncio.to_thread(get_global_db().limpiar_interacciones_antiguas, 30)
        logger.info(f"🧹 Limpieza: {filas} registros borrados.")
        
        await self.close()
    
    async def tarea_pedir_oro(self):
        """Pide oro por privado o en público, registrando el contexto."""
        logger.info("💰 Iniciando ronda de peticiones de oro...")
        
        for guild in self.guilds:
            # 50% probabilidad: Privado o Público
            es_privado = random.choice([True, False])
            
            if es_privado:
                await self._pedir_oro_privado(guild)
            else:
                await self._pedir_oro_publico(guild)
    
    async def _pedir_oro_privado(self, guild):
        """Pide oro por mensaje privado."""
        miembros = [m for m in guild.members if not m.bot]
        if not miembros:
            return
        
        objetivo = random.choice(miembros)
        
        # Limitar: max 2 ORO_DM por servidor al día
        cuenta_dm = await asyncio.to_thread(get_global_db().contar_interacciones_tipo_ultimo_dia, "ORO_DM", guild.id)
        if cuenta_dm >= 2:
            logger.info(f"🔕 [Límite] Ya hubo {cuenta_dm} ORO_DM hoy en servidor {guild.id}, saltando.")
            return
        
        # Verificar si usuario ha recibido oro recientemente (últimas 12h)
        ha_pedido_recientemente = await asyncio.to_thread(get_global_db().usuario_ha_pedido_tipo_recientemente, objetivo.id, "ORO_DM", 12)
        if not ha_pedido_recientemente:
            razon = random.choice(RAZONES_PEDIR_ORO)
            res = await asyncio.to_thread(pensar, f"Pídele oro a {objetivo.name}: {razon}, convencele.")
            
            try:
                await objetivo.send(f"👹 {res}")
                
                # Registrar en tabla principal
                await asyncio.to_thread(
                    get_global_db().registrar_interaccion,
                    objetivo.id, objetivo.name, "ORO_DM", 
                    "Te pedí oro por privado", None, guild.id, 
                    metadata={"respuesta": res, "rol": "pedir_oro"}
                )
                logger.info(f"✅ ORO_DM enviado a {objetivo.name}")
            except Exception as e:
                logger.warning(f"⚠️ Error enviando ORO_DM a {objetivo}: {e}")
    
    async def _pedir_oro_publico(self, guild):
        """Pide oro en canal público."""
        canal = discord.utils.get(guild.text_channels, name='general') or guild.text_channels[0]
        if not canal:
            return
        
        # Limitar: max 4 ORO_PUBLICO por servidor al día
        cuenta_publico = await asyncio.to_thread(get_global_db().contar_interacciones_tipo_ultimo_dia, "ORO_PUBLICO", guild.id)
        if cuenta_publico >= 4:
            logger.info(f"🔕 [Límite] Ya hubo {cuenta_publico} ORO_PUBLICO hoy en servidor {guild.id}, saltando.")
            return
        
        razon = random.choice(RAZONES_PEDIR_ORO)
        res = await asyncio.to_thread(
            pensar,
            f"Estas gritando en el centro del pueblo para que los humanos te den oro {razon}. Escribe un mensaje para convencerlos, usando tu personalidad de orco.", 
            "", [], True
        )
        
        try:
            await canal.send(f"📢 **DONATIVOS PARA LOS VERDES:** {res}")
            
            # Registrar en tabla principal
            await asyncio.to_thread(
                get_global_db().registrar_interaccion,
                str(canal.id), "CANAL_PUBLICO", "ORO_PUBLICO", 
                "Grito de oro en el canal", canal.id, guild.id, 
                metadata={"respuesta": res, "rol": "pedir_oro"}
            )
            logger.info(f"✅ ORO_PUBLICO enviado en canal {canal.name}")
        except Exception as e:
            logger.warning(f"⚠️ Error enviando ORO_PUBLICO en {canal}: {e}")

if __name__ == "__main__":
    OroBot().run(get_discord_token())
