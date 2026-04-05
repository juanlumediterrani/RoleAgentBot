"""
Treasure Hunter Role - Main execution logic.
Uses the new POE2 subrole manager for enhanced functionality.
"""

import asyncio
import math
import sys
import os
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent_engine import get_discord_token
from agent_mind import call_llm
from agent_db import get_global_db, get_active_server_id
from dotenv import load_dotenv
from agent_logging import get_logger
from discord_bot.discord_http import DiscordHTTP
from roles.treasure_hunter.db_role_treasure_hunter import get_poe_db_instance

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
    "name": "treasure_hunter",
    "system_prompt_addition": "ACTIVE ROLE - TREASURE HUNTER: You are a skilled treasure hunter who searches for valuable items and resources. Your mission is to find and report treasures, artifacts, and valuable discoveries."
}

def get_treasure_hunter_system_prompt():
    """Get system prompt from personality or fallback to English."""
    try:
        from agent_engine import PERSONALITY
        role_prompts = PERSONALITY.get("roles", {})
        return role_prompts.get("treasure_hunter", {}).get("active_duty", "ACTIVE MISSION - TREASURE HUNTER: You search for ancient treasures for your master. If you find something valuable, REMEMBER it and mention it. You search for Ancient Rib, Ancient Collarbone, Ancient Jawbone.")
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
        active_server_name = get_active_server_id()
        if not active_server_name:
            logger.warning("No active server configured for treasure hunter execution")
            return
        db_global = get_global_db(server_id=active_server_name)
        servidores_activos = db_global.get_active_servers()
        
        if not servidores_activos:
            logger.info("No active servers found for treasure hunter execution")
            return
        
        logger.info(f"🔍 Starting treasure hunter execution for {len(servidores_activos)} servers")

        all_subscriptions = []
        refresh_plan = defaultdict(lambda: defaultdict(set))

        for server_id in servidores_activos:
            try:
                server_subscriptions = await procesar_servidor(poe2_manager, server_id)
                for subscription in server_subscriptions:
                    all_subscriptions.append(subscription)
                    league = subscription.get("league", "Standard")
                    for item_name in subscription.get("tracked_items", []):
                        refresh_plan[league][item_name].add(subscription.get("user_id"))
            except Exception as e:
                logger.error(f"Error collecting subscriptions for server {server_id}: {e}")
                continue

        if not all_subscriptions:
            logger.info("No active POE2 subscriptions found across active servers")
            return

        refreshed_items = await actualizar_precios_globales(poe2_manager, refresh_plan)
        delivered_notifications = set()

        for subscription in all_subscriptions:
            try:
                await procesar_suscripcion(poe2_manager, discord_http, subscription, refreshed_items, delivered_notifications)
            except Exception as e:
                logger.error(
                    f"Error processing POE2 subscription for user {subscription.get('user_id')} in server {subscription.get('server_id')}: {e}"
                )

        for league, item_name, signal, current_price in delivered_notifications:
            market_data = refreshed_items.get((league, item_name))
            if not market_data:
                continue
            shared_db = market_data.get("db")
            if shared_db is None:
                continue
            shared_db.register_notification(item_name, league, signal, current_price)
        
        logger.info("✅ Treasure hunter execution completed")
        
    except Exception as e:
        logger.error(f"Error in treasure hunter execution: {e}")

async def procesar_servidor(poe2_manager, server_id):
    """Collect POE2 subscriptions for a single server."""
    if not poe2_manager.is_activated(server_id):
        logger.debug(f"POE2 not activated on server {server_id}, skipping")
        return []

    subscriptions = poe2_manager.get_all_server_subscriptions(server_id)
    valid_subscriptions = []
    for subscription in subscriptions:
        tracked_items = subscription.get("tracked_items", [])
        if not tracked_items:
            continue
        valid_subscriptions.append(subscription)

    logger.info(f"Collected {len(valid_subscriptions)} POE2 subscriptions for server {server_id}")
    return valid_subscriptions

async def actualizar_precios_globales(poe2_manager, refresh_plan):
    """Refresh global shared price history once per league and item."""
    refreshed_items = {}
    for league, items_map in refresh_plan.items():
        if poe2_manager.should_refresh_item_list(league):
            await poe2_manager.download_item_list(league)

        items_catalog = poe2_manager.load_item_list(league)
        shared_db = get_poe_db_instance("default", league)

        for item_name in items_map.keys():
            item_id = items_catalog.get(item_name.lower())
            if not item_id:
                logger.warning(f"POE2 item '{item_name}' not found in league {league}")
                continue

            try:
                history_entries = poe2_manager.client.get_item_history(item_name, league=league, days=30)
                if not history_entries:
                    logger.warning(f"No POE2 history available for {item_name} in {league}")
                    continue

                inserted = shared_db.insert_prices_bulk(item_name, history_entries, league)
                current_price = shared_db.get_current_price(item_name, league)
                min_price, max_price = shared_db.get_statistics(item_name, league)

                refreshed_items[(league, item_name)] = {
                    "item_id": item_id,
                    "entries": history_entries,
                    "inserted": inserted,
                    "current_price": current_price,
                    "min_price": min_price,
                    "max_price": max_price,
                    "signal": calcular_senal(current_price, min_price, max_price) if current_price is not None and min_price is not None and max_price is not None else None,
                    "recent_notification": shared_db.has_recent_similar_notification(
                        item_name,
                        league,
                        calcular_senal(current_price, min_price, max_price),
                        current_price,
                    ) if current_price is not None and min_price is not None and max_price is not None and calcular_senal(current_price, min_price, max_price) else False,
                    "db": shared_db,
                }

                logger.info(
                    f"Refreshed {item_name} in {league}: {len(history_entries)} entries, {inserted} inserted, current={current_price}"
                )
            except Exception as e:
                logger.error(f"Error refreshing POE2 market data for {item_name} in {league}: {e}")

    return refreshed_items

async def procesar_suscripcion(poe2_manager, discord_http, subscription, refreshed_items, delivered_notifications):
    """Process one user subscription using shared global market data."""
    user_id = subscription.get("user_id")
    server_id = subscription.get("server_id")
    league = subscription.get("league", "Standard")
    tracked_items = subscription.get("tracked_items", [])

    for item_name in tracked_items:
        market_data = refreshed_items.get((league, item_name))
        if not market_data:
            continue

        current_price = market_data.get("current_price")
        signal = market_data.get("signal")

        if current_price is None or not signal:
            continue

        if market_data.get("recent_notification"):
            logger.info(f"Skipping recent similar notification for {item_name} in {league}")
            continue

        message = await construir_mensaje_alerta(item_name, signal, current_price)
        sent = await discord_http.send_dm(int(user_id), f"🔮 **POE2 TREASURE** [{server_id}] {message}")
        if sent:
            delivered_notifications.add((league, item_name, signal, current_price))
            logger.info(f"Sent POE2 {signal} alert for {item_name} to user {user_id} from server {server_id}")

def calcular_senal(current_price, min_price, max_price):
    """Calculate the POE2 market signal from historical bounds."""
    if current_price <= min_price * (1 + UMBRAL_COMPRA):
        return "COMPRA"
    if current_price >= max_price * (1 - UMBRAL_VENTA):
        return "VENTA"
    return None

async def construir_mensaje_alerta(item_name, signal, price):
    """Build the user-facing POE2 alert message."""
    try:
        from agent_engine import _build_system_prompt, PERSONALITY

        system_instruction = _build_system_prompt(PERSONALITY)
        role_prompt = PERSONALITY.get("treasure_hunter", {})
        active_duty = role_prompt.get(
            "active_duty",
            role_prompt.get(
                "mission_active",
                "CURRENT DUTY - TREASURE HUNTER: You are a treasure hunter specializing in Path of Exile 2 market analysis. Focus on spotting strong buy or sell opportunities from price history and give clear, direct market advice.",
            ),
        )
        notification_tasks = role_prompt.get("notification_task", {})
        if signal == "COMPRA":
            task_prompt = notification_tasks.get(
                "buy_prompt",
                f"TASK - BUY OPPORTUNITY: A buy opportunity has been detected for {item_name} at {price:.2f} Divines. This price is low according to historical data. Generate a motivational message indicating it's time to buy. Be direct and concise.",
            )
        else:
            task_prompt = notification_tasks.get(
                "sell_prompt",
                f"TASK - SELL OPPORTUNITY: A sell opportunity has been detected for {item_name} at {price:.2f} Divines. This price is high according to historical data. Generate a message indicating it's time to sell for profit. Be direct and concise.",
            )
        task_prompt = task_prompt.format(item_name=item_name, price=price)
        golden_rules = role_prompt.get(
            "golden_rules",
            [
                "1. BE CONCISE: Keep messages short, 2-4 sentences maximum (100-200 characters)",
                "2. CLEAR ACTION: Clearly indicate if it's a BUY or SELL signal",
                "3. PRICE MENTION: Include the current price prominently",
                "4. EXPERT ADVICE: Demonstrate market knowledge and expertise",
                "5. STRONG ENDING: Use decisive tone and clear recommendations",
                "6. NO EXPLANATIONS: Provide only the alert message, no additional context",
            ],
        )
        golden_rules_text = "\n".join(golden_rules)
        complete_prompt = (
            f"{active_duty}\n\n{task_prompt}\n\nGOLDEN RULES:\n"
            f"{golden_rules_text}\n\nRespond only with the alert message, no additional explanations."
        )
        return await asyncio.to_thread(call_llm, system_instruction, complete_prompt, False, "treasure_hunter_notification")
    except Exception as e:
        logger.error(f"Error building POE2 alert message for {item_name}: {e}")
        action = "BUY" if signal == "COMPRA" else "SELL"
        return f"{action} {item_name} at {price:.2f} Div."

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
        db_global = get_global_db(server_id=server_id)
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
