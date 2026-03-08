"""
Treasure Hunter Role - Main execution logic.
Uses the new POE2 subrole manager for enhanced functionality.
"""

import asyncio
import math
import sys
import os
from datetime import datetime, timedelta, timezone

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent_engine import get_discord_token, think
from agent_db import get_global_db, get_active_server_name
from dotenv import load_dotenv
from agent_logging import get_logger
from discord_bot.discord_http import DiscordHTTP

# Import the new POE2 manager
try:
    from poe2.poe2_subrole_manager import get_poe2_manager
    POE2_MANAGER_AVAILABLE = True
except ImportError:
    POE2_MANAGER_AVAILABLE = False
    get_poe2_manager = None

load_dotenv()
logger = get_logger('treasure_hunter')

# Configuration
MISSION_CONFIG = {
    "name": "treasure_hunter"
}

def get_treasure_hunter_system_prompt():
    """Get system prompt from personality or fallback to English."""
    try:
        from agent_engine import PERSONALIDAD
        role_prompts = PERSONALIDAD.get("role_system_prompts", {})
        return role_prompts.get("treasure_hunter", "ACTIVE MISSION - TREASURE HUNTER: You search for ancient treasures for your master. If you find something valuable, REMEMBER it and mention it. You search for Ancient Rib, Ancient Collarbone, Ancient Jawbone.")
    except Exception:
        return "ACTIVE MISSION - TREASURE HUNTER: You search for ancient treasures for your master. If you find something valuable, REMEMBER it and mention it. You search for Ancient Rib, Ancient Collarbone, Ancient Jawbone."

# Trading thresholds
ENTRADAS_POR_DIA = 24  # 24 entries per day for complete data (24*30 = 720 total)
UMBRAL_COMPRA = 0.15  # 15% above historical minimum
UMBRAL_VENTA = 0.15   # 15% below historical maximum

def calcular_zonas_precios(historial):
    """Calculate buy/sell zones from price history."""
    if not historial:
        return None, None, None, None
    
    precios = [entry.price for entry in historial]
    if len(precios) < 2:
        return None, None, None, None
    
    precio_min = min(precios)
    precio_max = max(precios)
    precio_actual = precios[-1]
    
    zona_compra = precio_min * (1 - UMBRAL_COMPRA)
    zona_venta = precio_max * (1 - UMBRAL_VENTA)
    
    return precio_min, precio_max, zona_compra, zona_venta

async def ejecutar_mision_treasure_hunter(config, server_name=None):
    """Execute treasure hunter mission using new POE2 manager."""
    if not POE2_MANAGER_AVAILABLE:
        logger.warning("POE2 manager not available, skipping treasure hunter execution")
        return
    
    poe2_manager = get_poe2_manager()
    if not poe2_manager:
        logger.warning("Could not get POE2 manager instance")
        return
    
    try:
        # Get Discord token and HTTP client
        token = get_discord_token()
        discord_http = DiscordHTTP(token)
        
        # Get active servers from database
        db_global = get_global_db()
        servidores_activos = db_global.get_active_servers()
        
        if not servidores_activos:
            logger.info("No active servers found for treasure hunter execution")
            return
        
        logger.info(f"🔍 Starting treasure hunter execution for {len(servidores_activos)} servers")
        
        for server_id in servidores_activos:
            try:
                await procesar_servidor(poe2_manager, discord_http, server_id)
            except Exception as e:
                logger.error(f"Error processing server {server_id}: {e}")
                continue
        
        logger.info("✅ Treasure hunter execution completed")
        
    except Exception as e:
        logger.error(f"Error in treasure hunter execution: {e}")

async def procesar_servidor(poe2_manager, discord_http, server_id):
    """Process a single server for treasure hunting."""
    # Check if POE2 is activated on this server
    if not poe2_manager.is_activated(server_id):
        logger.debug(f"POE2 not activated on server {server_id}, skipping")
        return
    
    # Get active league
    league = poe2_manager.get_active_league(server_id)
    
    # Get objectives for this server
    success, objectives_data = poe2_manager.list_objectives(server_id)
    if not success:
        logger.warning(f"Could not get objectives for server {server_id}: {objectives_data}")
        return
    
    # Parse objectives from the list response
    objectives = []
    lines = objectives_data.split('\n')
    for line in lines:
        if line.strip().startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')):
            # Extract item name from line like "1. ✅ Ancient Rib - **2.5 Div**"
            parts = line.split(' ', 3)
            if len(parts) >= 3:
                item_name = parts[2].strip()
                if item_name.endswith('**'):
                    item_name = item_name[:-2].strip()
                objectives.append(item_name)
    
    if not objectives:
        logger.info(f"No objectives configured for server {server_id}")
        return
    
    logger.info(f"🎯 Processing {len(objectives)} objectives for server {server_id} ({league})")
    
    # Process each objective
    from poe2.poe2scout_client import Poe2ScoutClient
    client = Poe2ScoutClient()
    
    for item_name in objectives:
        try:
            await procesar_item(poe2_manager, client, discord_http, server_id, item_name, league)
        except Exception as e:
            logger.error(f"Error processing item {item_name} on server {server_id}: {e}")
            continue

async def procesar_item(poe2_manager, client, discord_http, server_id, item_name, league):
    """Process a single item for treasure hunting."""
    logger.info(f"🔍 Analyzing {item_name} on server {server_id}")
    
    try:
        # Get item history
        historial = client.get_item_history(item_name, league=league, days=30)
        
        if not historial:
            logger.warning(f"No price history found for {item_name}")
            return
        
        # Calculate trading zones
        precio_min, precio_max, zona_compra, zona_venta = calcular_zonas_precios(historial)
        
        if precio_min is None:
            logger.warning(f"Could not calculate price zones for {item_name}")
            return
        
        precio_actual = historial[-1].price
        
        # Determine trading signal
        senal_compra = precio_actual <= zona_compra
        senal_venta = precio_actual >= zona_venta
        
        logger.info(f"💰 {item_name}: ${precio_actual:.2f} | Buy: ${zona_compra:.2f} | Sell: ${zona_venta:.2f}")
        
        # Generate trading message if signal detected
        mensaje = None
        if senal_compra:
            mensaje = f"🟢 **BUY SIGNAL** - {item_name} at ${precio_actual:.2f} (≤ ${zona_compra:.2f})"
        elif senal_venta:
            mensaje = f"🔴 **SELL SIGNAL** - {item_name} at ${precio_actual:.2f} (≥ ${zona_venta:.2f})"
        
        # Send message if signal detected
        if mensaje:
            await enviar_senal_discord(discord_http, server_id, mensaje, item_name, precio_actual, zona_compra, zona_venta)
        
        # Store price history in database
        await almacenar_historial_precios(poe2_manager, server_id, item_name, league, historial)
        
    except Exception as e:
        logger.error(f"Error processing item {item_name}: {e}")

async def almacenar_historial_precios(poe2_manager, server_id, item_name, league, historial):
    """Store price history in the shared database."""
    try:
        import sqlite3
        
        # Get the shared price history database for this league
        db_path = poe2_manager.get_price_history_path(league)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Store latest price entries
        for entry in historial[-10:]:  # Store last 10 entries
            cursor.execute('''
                INSERT OR REPLACE INTO price_history 
                (item_name, item_id, league, price, timestamp, quantity, raw_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item_name,
                0,  # We don't have item_id here, could be enhanced
                league,
                entry.price,
                entry.time or datetime.now().isoformat(),
                entry.quantity,
                str(entry.raw) if entry.raw else None
            ))
        
        conn.commit()
        conn.close()
        logger.debug(f"Stored price history for {item_name} in {league}")
        
    except Exception as e:
        logger.error(f"Error storing price history for {item_name}: {e}")

async def enviar_senal_discord(discord_http, server_id, mensaje, item_name, precio_actual, zona_compra, zona_venta):
    """Send trading signal to Discord."""
    try:
        # Get server channel for treasure hunter notifications
        db_global = get_global_db()
        canal_id = db_global.get_role_channel(server_id, "treasure_hunter")
        
        if not canal_id:
            logger.warning(f"No treasure hunter channel configured for server {server_id}")
            return
        
        # Create embed message
        embed_data = {
            "title": f"🔮 Treasure Hunter Signal",
            "description": mensaje,
            "color": 0x00ff00 if "BUY" in mensaje else 0xff0000,
            "fields": [
                {"name": "Item", "value": item_name, "inline": True},
                {"name": "Current Price", "value": f"${precio_actual:.2f}", "inline": True},
                {"name": "Buy Zone", "value": f"${zona_compra:.2f}", "inline": True},
                {"name": "Sell Zone", "value": f"${zona_venta:.2f}", "inline": True}
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        # Send message
        await discord_http.send_embed(canal_id, embed_data)
        logger.info(f"📢 Sent trading signal for {item_name} to server {server_id}")
        
    except Exception as e:
        logger.error(f"Error sending Discord message: {e}")

# Main execution function
async def main():
    """Main execution entry point."""
    config = {}
    await ejecutar_mision_treasure_hunter(config)

if __name__ == "__main__":
    asyncio.run(main())
