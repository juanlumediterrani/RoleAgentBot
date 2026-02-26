import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # Path local primero
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))  # Path del proyecto

import discord
import asyncio
import math
from datetime import datetime, timedelta, timezone
# defer importing heavy LLM client until runtime (avoid import-time deps)
# from agent_engine import pensar_como_agente
from agent_db import db
import sys
import os
sys.path.append(os.path.dirname(__file__))
from db_role_poe import DatabaseRolePoe, get_db_path
from poe2scout_client import Poe2ScoutClient, ResponseFormatError, APIError
from dotenv import load_dotenv
from agent_logging import get_logger
load_dotenv()
logger = get_logger('buscador')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "buscador_tesoros",
    "system_prompt_addition": "MISION ACTIVA - BUSCADOR DE TESOROS: Buscas tesoros antiguos para tu jefe. Si encontraste algo valioso, RECUERDALO y mencionalo. Buscas Ancient Rib, Ancient Collarbone, Ancient Jawbone."
}

MI_ID = 235796491988369408
OBJETIVOS = {"Ancient Rib": 4379, "Ancient Collarbone": 4385, "Ancient Jawbone": 4373}
LIGA = "Fate of the Vaal"  # Liga activa actual
ENTRADAS_POR_DIA = 24  # 24 entradas por día para datos completos (24*30 = 720 total)
UMBRAL_COMPRA = 0.15  # 15% por encima del mínimo histórico
UMBRAL_VENTA = 0.15   # 15% por debajo del máximo histórico

# Crear instancia de BD con la liga correcta
db_role_poe = DatabaseRolePoe(get_db_path(LIGA))

def verificar_datos_antiguos(item, liga, horas=24):
    """Verifica si los datos de un item son más antiguos que N horas."""
    try:
        return db_role_poe.verificar_datos_antiguos(item, liga, horas)
    except Exception as e:
        logger.exception(f"Error verificando antigüedad para {item}: {e}")
        return True  # Si hay error, asumimos que necesita actualización

def calcular_zonas_precios(historial):
    """Calcula zonas de máximos y mínimos basándose en frecuencia temporal.
    Retorna (zona_minima, zona_maxima) como promedios ponderados por frecuencia.
    """
    if not historial or len(historial) < 10:
        return None, None
    
    precios = [precio for precio, _ in historial]
    
    # Agrupar precios en bins del 5% para detectar zonas frecuentes
    precio_min_abs = min(precios)
    precio_max_abs = max(precios)
    rango = precio_max_abs - precio_min_abs
    
    if rango == 0:
        return precio_min_abs, precio_max_abs
    
    # Crear bins del 5% del rango
    num_bins = 20  # 100% / 5% = 20 bins
    bin_size = rango / num_bins
    bins_frecuencia = {}
    
    # Contar frecuencia de cada bin (cuántas veces el precio estuvo en ese rango)
    for precio in precios:
        bin_idx = min(int((precio - precio_min_abs) / bin_size), num_bins - 1)
        bins_frecuencia[bin_idx] = bins_frecuencia.get(bin_idx, 0) + 1
    
    # Encontrar zona de mínimos: bins con más frecuencia en el tercio inferior
    tercio_inferior = num_bins // 3
    bins_bajos = {k: v for k, v in bins_frecuencia.items() if k < tercio_inferior}
    
    if bins_bajos:
        # Bin más frecuente en zona baja
        bin_min_frecuente = max(bins_bajos.items(), key=lambda x: x[1])[0]
        zona_minima = precio_min_abs + (bin_min_frecuente + 0.5) * bin_size
    else:
        zona_minima = precio_min_abs
    
    # Encontrar zona de máximos: bins con más frecuencia en el tercio superior
    tercio_superior_inicio = (2 * num_bins) // 3
    bins_altos = {k: v for k, v in bins_frecuencia.items() if k >= tercio_superior_inicio}
    
    if bins_altos:
        # Bin más frecuente en zona alta
        bin_max_frecuente = max(bins_altos.items(), key=lambda x: x[1])[0]
        zona_maxima = precio_min_abs + (bin_max_frecuente + 0.5) * bin_size
    else:
        zona_maxima = precio_max_abs
    
    logger.info(f"Zonas calculadas - Mínima: {zona_minima:.2f} (frecuencia: {bins_frecuencia.get(bin_min_frecuente if bins_bajos else 0, 0)}), "
                f"Máxima: {zona_maxima:.2f} (frecuencia: {bins_frecuencia.get(bin_max_frecuente if bins_altos else num_bins-1, 0)})")
    
    return zona_minima, zona_maxima

def analizar_mercado(item, precio_actual, liga):
    """Analiza el precio actual vs zonas históricas con reglas de 25%.
    Retorna señal de compra, venta o None.
    """
    try:
        # Obtener historial completo para análisis de zonas
        historial = db_role_poe.obtener_historial_precios(item, liga)
        
        if not historial:
            logger.warning(f"No hay historial para {item}")
            return None
        
        # Calcular zonas basadas en frecuencia temporal
        zona_minima, zona_maxima = calcular_zonas_precios(historial)
        
        if not zona_minima or not zona_maxima:
            logger.warning(f"No se pudieron calcular zonas para {item}")
            return None
        
        logger.info(f"{item}: Precio actual={precio_actual}, Zona mín={zona_minima:.2f}, Zona máx={zona_maxima:.2f}")
        
        # Regla de compra: precio <= zona_minima * 1.25
        if precio_actual <= zona_minima * (1 + UMBRAL_COMPRA):
            return "COMPRA"
        
        # Regla de venta: precio >= zona_maxima * 0.75
        if precio_actual >= zona_maxima * (1 - UMBRAL_VENTA):
            return "VENTA"
        
        return None
    except Exception as e:
        logger.exception(f"Error analizando mercado para {item}: {e}")
        return None

class BuscadorBot(discord.Client):
    async def on_ready(self):
        logger.info("💎 Buscando tesoros...")
        user = await self.fetch_user(MI_ID)

        # Use strict client
        client = Poe2ScoutClient()
        
        # Primero: descargar y almacenar todos los datos
        resultados_descarga = {}
        
        for nombre, iid in OBJETIVOS.items():
            try:
                # Verificar si datos son antiguos (más de 24 horas)
                necesita_actualizar = verificar_datos_antiguos(nombre, LIGA, 24)
                
                if necesita_actualizar:
                    logger.info(f"Actualizando {nombre} - datos antiguos o inexistentes")
                    try:
                        entries = client.get_item_history(nombre, league=LIGA)
                    except Exception as e:
                        logger.warning(f"API error for item {nombre}: {e}")
                        continue

                    if not entries:
                        logger.info(f"No entries for {nombre}")
                        continue

                    # Almacenar historial con retención de 720 entradas
                    insertados = db_role_poe.insertar_precios_bulk(nombre, entries, LIGA)
                    logger.info(f"{nombre}: {len(entries)} recibidas, {insertados} nuevas insertadas")
                else:
                    logger.info(f"{nombre}: datos recientes, sin actualización")
                
                # Obtener precio actual desde la BD
                precio_actual = db_role_poe.obtener_precio_actual(nombre, LIGA)
                if precio_actual:
                    resultados_descarga[nombre] = {
                        'precio_actual': precio_actual,
                        'actualizado': necesita_actualizar
                    }
                
            except Exception:
                logger.exception(f"Fallo procesando item {nombre}")
        
        # Segundo: analizar precios y enviar notificaciones
        logger.info("🔍 Analizando precios después de actualizar BD...")
        
        for nombre, datos in resultados_descarga.items():
            actual = datos['precio_actual']
            señal = analizar_mercado(nombre, actual, LIGA)
            if señal:
                logger.info(f"🚨 SEÑAL DETECTADA: {nombre} - {señal} a {actual} Div")
                
                # Verificar si ya se envió una notificación similar recientemente
                notificacion_reciente = db_role_poe.verificar_notificacion_reciente(
                    nombre, LIGA, señal, actual, horas=6, umbral_similitud=0.15
                )
                
                if notificacion_reciente:
                    logger.info(f"🔕 Notificación omitida por duplicidad reciente: {nombre} - {señal}")
                    continue
                
                try:
                    from agent_engine import pensar
                    
                    if señal == "COMPRA":
                        mensaje = f"Misión: Informa de oportunidad de compra. El objeto {nombre} está barato ({actual} Div). ¡Hay que comprar ahora!"
                    else:  # VENTA
                        mensaje = f"Misión: Informa de oportunidad de venta. El objeto {nombre} está caro ({actual} Div). ¡Hay que vender ya!"
                    
                    res = await asyncio.to_thread(pensar, mensaje)
                    await user.send(f"💎 **TESORO DETECTADO**: {res}")
                    logger.info(f"✅ Notificación enviada para {nombre} - {señal}")
                    
                    # Registrar la notificación enviada
                    db_role_poe.registrar_notificacion(nombre, LIGA, señal, actual)
                    
                except Exception:
                    logger.exception("Error enviando mensaje de tesoro")
        
        logger.info("✅ Proceso completado")

        await self.close()

if __name__ == "__main__":
    BuscadorBot(intents=discord.Intents.default()).run(os.getenv('DISCORD_TOKEN'))

