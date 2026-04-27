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

from agent_engine import get_discord_token, _get_personality
from agent_mind import call_llm_async
from agent_db import get_global_db, get_server_id
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


def get_bot_identity(server_id: str) -> dict:
    """Get bot personality name, nickname and avatar for embeds."""
    try:
        personality = _get_personality(server_id) if server_id else {}
        name = personality.get("name", "Bot")
        bot_display_name = personality.get("bot_display_name", name)
        
        # Get avatar URL from personality
        avatar_url = None
        try:
            from pathlib import Path
            import os
            base_dir = Path(__file__).parent.parent.parent
            personality_name = personality.get("name", "rab").lower()
            avatar_path = base_dir / "personalities" / personality_name / "avatar.png"
            if avatar_path.exists():
                # For Discord HTTP client, we need to use the bot's avatar URL
                # Since we're sending via HTTP, we can't attach files easily
                # Use a placeholder or the bot's default avatar
                from agent_db import get_server_id
                from discord_bot.agent_discord import get_bot_instance
                bot = get_bot_instance()
                if bot and bot.user:
                    avatar_url = bot.user.display_avatar.url if bot.user.display_avatar else None
        except Exception:
            pass
        
        return {
            "name": name,
            "nickname": bot_display_name,
            "avatar_url": avatar_url
        }
    except Exception as e:
        logger.error(f"Error getting bot identity for server {server_id}: {e}")
        return {"name": "Bot", "nickname": "Bot", "avatar_url": None}


def get_treasure_hunter_translations(server_id: str) -> dict:
    """Get treasure_hunter translations from personality descriptions."""
    try:
        from agent_engine import _get_personality_descriptions
        descriptions = _get_personality_descriptions(server_id)
        return descriptions.get("treasure_hunter", {}).get("poe2", {})
    except Exception as e:
        logger.error(f"Error getting treasure_hunter translations for server {server_id}: {e}")
        return {}

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
    
    zona_compra = precio_min * (1 + UMBRAL_COMPRA)
    zona_venta = precio_max * (1 - UMBRAL_VENTA)
    
    return precio_min, precio_max, zona_compra, zona_venta

async def ejecutar_mision_treasure_hunter(config, server_name=None):
    """Execute treasure hunter mission using new POE2 per-item table structure.
    
    This function runs with LOW PRIORITY to avoid blocking the main runtime:
    1. Updates prices for ALL registered items in background
    2. Checks for buy/sell signals based on updated prices
    3. Sends alerts to users with matching item_ids
    4. Only checks servers with POE2 subrole activated
    
    All operations are non-blocking and yield control to the main runtime.
    """
    if not POE2_MANAGER_AVAILABLE:
        logger.warning("POE2 manager not available, skipping treasure hunter execution")
        return
    
    poe2_manager = get_poe2_manager()
    if not poe2_manager:
        logger.warning("Could not get POE2 manager instance")
        return
    
    # Create background task with low priority - don't block main runtime
    asyncio.create_task(
        _ejecutar_mision_treasure_hunter_background(poe2_manager, config),
        name="treasure_hunter_background_task"
    )
    logger.info("🚀 Treasure hunter background task launched (non-blocking)")


async def _ejecutar_mision_treasure_hunter_background(poe2_manager, config):
    """Background task that actually performs the treasure hunter work.
    
    This runs with low priority, yielding control frequently to avoid blocking.
    """
    try:
        # Yield control immediately to ensure main runtime gets priority
        await asyncio.sleep(0)
        
        # Get Discord token and HTTP client
        token = get_discord_token()
        discord_http = DiscordHTTP(token)
        
        # STEP 1: Update prices for ALL registered items
        logger.info("🔄 [BG] Step 1: Updating prices for all registered items")
        all_price_updates = await poe2_manager.run_price_update_task()
        
        # Yield control after heavy operation
        await asyncio.sleep(0)
        
        if not all_price_updates:
            logger.info("[BG] No price updates available, skipping alert processing")
            return
        
        # STEP 2: Get active servers with POE2 subrole activated
        logger.info("🔍 [BG] Step 2: Checking active servers with POE2 subrole")
        active_servers = poe2_manager.get_active_servers()
        
        # Yield control
        await asyncio.sleep(0)
        
        if not active_servers:
            logger.info("[BG] No servers have POE2 subrole activated, skipping alert processing")
            return
        
        logger.info(f"[BG] Found {len(active_servers)} servers with POE2 activated")
        
        # STEP 3: Process alerts for each active server with cooperative multitasking
        delivered_notifications = set()
        
        for server_id in active_servers:
            try:
                # Process one server at a time but yield between servers
                await procesar_alerts_para_servidor_low_priority(
                    poe2_manager, 
                    discord_http, 
                    server_id, 
                    all_price_updates, 
                    delivered_notifications
                )
                # Yield control after each server to let other tasks run
                await asyncio.sleep(0.01)  # 10ms yield
            except Exception as e:
                logger.error(f"[BG] Error processing alerts for server {server_id}: {e}")
                continue
        
        logger.info("✅ [BG] Treasure hunter background execution completed")
        
    except Exception as e:
        logger.error(f"[BG] Error in treasure hunter background execution: {e}")

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

async def procesar_alerts_para_servidor(poe2_manager, discord_http, server_id, all_price_updates, delivered_notifications):
    """Process buy/sell alerts for a single server based on item_id matching.
    
    This function:
    1. Gets all subscriptions for the server
    2. Checks each subscription's tracked_items (for buy alerts) and purchases (for sell alerts)
    3. Compares item_ids with updated price data
    4. Sends alerts when price signals match
    """
    try:
        # Get all subscriptions for this server
        subscriptions = poe2_manager.get_all_server_subscriptions(server_id)
        
        if not subscriptions:
            logger.debug(f"No subscriptions found for server {server_id}")
            return
        
        logger.info(f"Processing alerts for {len(subscriptions)} subscriptions on server {server_id}")
        
        for subscription in subscriptions:
            try:
                user_id = subscription.get("user_id")
                league = subscription.get("league", "Standard")
                tracked_items = subscription.get("tracked_items", [])
                purchases = subscription.get("purchases", [])
                
                # Get price updates for this league
                league_updates = all_price_updates.get(league, {})
                if not league_updates:
                    continue
                
                # Process tracked items for BUY alerts
                for item in tracked_items:
                    # Handle both old format (string) and new format (dict with item_id)
                    if isinstance(item, dict):
                        item_name = item.get('item_name', '')
                        item_id = item.get('item_id')
                    else:
                        item_name = item
                        item_id = None
                    
                    if not item_id:
                        continue
                    
                    # Check if this item_id has updated price data
                    price_data = league_updates.get(item_id)
                    if not price_data:
                        continue
                    
                    current_price = price_data.get('current_price')
                    min_price = price_data.get('min_price')
                    max_price = price_data.get('max_price')
                    
                    # Check for buy signal
                    signal = poe2_manager.check_price_signal(current_price, min_price, max_price)
                    
                    if signal == "COMPRA":
                        # Check if already purchased (don't send buy alert if already bought)
                        already_purchased = any(
                            p.get('item_id') == item_id or p.get('item_name') == item_name 
                            for p in purchases
                        )
                        
                        if not already_purchased:
                            # Send buy alert
                            alert_key = (server_id, user_id, item_id, "COMPRA", current_price)
                            if alert_key not in delivered_notifications:
                                await enviar_alerta_compra(
                                    discord_http, 
                                    user_id, 
                                    server_id, 
                                    item_name, 
                                    current_price, 
                                    league, 
                                    item_id
                                )
                                delivered_notifications.add(alert_key)
                                logger.info(f"📗 Sent BUY alert for {item_name} to user {user_id}")
                
                # Process purchases for SELL alerts
                for purchase in purchases:
                    item_id = purchase.get('item_id')
                    item_name = purchase.get('item_name', '')
                    buy_price = purchase.get('buy_price')
                    
                    if not item_id:
                        continue
                    
                    # Check if this item_id has updated price data
                    price_data = league_updates.get(item_id)
                    if not price_data:
                        continue
                    
                    current_price = price_data.get('current_price')
                    min_price = price_data.get('min_price')
                    max_price = price_data.get('max_price')
                    
                    # Check for sell signal
                    signal = poe2_manager.check_price_signal(current_price, min_price, max_price)
                    
                    if signal == "VENTA":
                        # Only send sell alert if price is higher than buy price (profit)
                        if buy_price and current_price > buy_price:
                            alert_key = (server_id, user_id, item_id, "VENTA", current_price)
                            if alert_key not in delivered_notifications:
                                await enviar_alerta_venta(
                                    discord_http, 
                                    user_id, 
                                    server_id, 
                                    item_name, 
                                    current_price, 
                                    buy_price
                                )
                                delivered_notifications.add(alert_key)
                                logger.info(f"📕 Sent SELL alert for {item_name} to user {user_id}")
                
            except Exception as e:
                logger.error(f"Error processing subscription for user {subscription.get('user_id')}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Error processing alerts for server {server_id}: {e}")


async def procesar_alerts_para_servidor_low_priority(poe2_manager, discord_http, server_id, all_price_updates, delivered_notifications):
    """Process buy/sell alerts with LOW PRIORITY - yields control frequently.
    
    This version is designed to run in the background without blocking the main runtime.
    It yields control after processing each subscription and between items.
    """
    try:
        # Get all subscriptions for this server
        subscriptions = poe2_manager.get_all_server_subscriptions(server_id)
        
        if not subscriptions:
            logger.debug(f"[BG-LP] No subscriptions found for server {server_id}")
            return
        
        logger.info(f"[BG-LP] Processing alerts for {len(subscriptions)} subscriptions on server {server_id}")
        
        for subscription in subscriptions:
            try:
                # Yield control before processing each subscription
                await asyncio.sleep(0)
                
                user_id = subscription.get("user_id")
                league = subscription.get("league", "Standard")
                tracked_items = subscription.get("tracked_items", [])
                purchases = subscription.get("purchases", [])
                
                # Get price updates for this league
                league_updates = all_price_updates.get(league, {})
                if not league_updates:
                    continue
                
                # Process tracked items for BUY alerts with yielding
                for item in tracked_items:
                    # Yield control between items
                    await asyncio.sleep(0)
                    
                    # Handle both old format (string) and new format (dict with item_id)
                    if isinstance(item, dict):
                        item_name = item.get('item_name', '')
                        item_id = item.get('item_id')
                    else:
                        item_name = item
                        item_id = None
                    
                    if not item_id:
                        continue
                    
                    # Check if this item_id has updated price data
                    price_data = league_updates.get(item_id)
                    if not price_data:
                        continue
                    
                    current_price = price_data.get('current_price')
                    min_price = price_data.get('min_price')
                    max_price = price_data.get('max_price')
                    
                    # Check for buy signal
                    signal = poe2_manager.check_price_signal(current_price, min_price, max_price)
                    
                    if signal == "COMPRA":
                        # Check if already purchased (don't send buy alert if already bought)
                        already_purchased = any(
                            p.get('item_id') == item_id or p.get('item_name') == item_name 
                            for p in purchases
                        )
                        
                        if not already_purchased:
                            # Send buy alert
                            alert_key = (server_id, user_id, item_id, "COMPRA", current_price)
                            if alert_key not in delivered_notifications:
                                # Use create_task for non-blocking send
                                asyncio.create_task(
                                    enviar_alerta_compra(
                                        discord_http, 
                                        user_id, 
                                        server_id, 
                                        item_name, 
                                        current_price, 
                                        league, 
                                        item_id
                                    ),
                                    name=f"buy_alert_{user_id}_{item_id}"
                                )
                                delivered_notifications.add(alert_key)
                                logger.info(f"[BG-LP] 📗 Queued BUY alert for {item_name} to user {user_id}")
                
                # Yield control before processing purchases
                await asyncio.sleep(0.001)  # 1ms yield
                
                # Process purchases for SELL alerts with yielding
                for purchase in purchases:
                    # Yield control between purchases
                    await asyncio.sleep(0)
                    
                    item_id = purchase.get('item_id')
                    item_name = purchase.get('item_name', '')
                    buy_price = purchase.get('buy_price')
                    
                    if not item_id:
                        continue
                    
                    # Check if this item_id has updated price data
                    price_data = league_updates.get(item_id)
                    if not price_data:
                        continue
                    
                    current_price = price_data.get('current_price')
                    min_price = price_data.get('min_price')
                    max_price = price_data.get('max_price')
                    
                    # Check for sell signal
                    signal = poe2_manager.check_price_signal(current_price, min_price, max_price)
                    
                    if signal == "VENTA":
                        # Only send sell alert if price is higher than buy price (profit)
                        if buy_price and current_price > buy_price:
                            alert_key = (server_id, user_id, item_id, "VENTA", current_price)
                            if alert_key not in delivered_notifications:
                                # Use create_task for non-blocking send
                                asyncio.create_task(
                                    enviar_alerta_venta(
                                        discord_http, 
                                        user_id, 
                                        server_id, 
                                        item_name, 
                                        current_price, 
                                        buy_price
                                    ),
                                    name=f"sell_alert_{user_id}_{item_id}"
                                )
                                delivered_notifications.add(alert_key)
                                logger.info(f"[BG-LP] 📕 Queued SELL alert for {item_name} to user {user_id}")
                
            except Exception as e:
                logger.error(f"[BG-LP] Error processing subscription for user {subscription.get('user_id')}: {e}")
                continue
        
        logger.info(f"[BG-LP] Finished processing alerts for server {server_id}")
                
    except Exception as e:
        logger.error(f"[BG-LP] Error processing alerts for server {server_id}: {e}")


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
                # Use the most recent price from API data (history_entries[0]) instead of DB
                # This avoids date format issues with '%m-%d %H:%M' which doesn't include year
                current_price = history_entries[0].price if history_entries else None
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
    purchases = subscription.get("purchases", [])

    for item in tracked_items:
        # Handle both old format (string) and new format (dict with item_name and item_id)
        if isinstance(item, dict):
            item_name = item.get('item_name', '')
            item_id = item.get('item_id')
        else:
            item_name = item
            item_id = None
        
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

        # Check if user has already purchased this item
        purchased_item = next((p for p in purchases if p["item_name"] == item_name), None)
        
        if purchased_item:
            # Check for sell signal for purchased items
            if signal == "VENTA":
                # Send sell alert with finish button
                await enviar_alerta_venta(discord_http, user_id, server_id, item_name, current_price, purchased_item["buy_price"])
                delivered_notifications.add((league, item_name, signal, current_price))
                logger.info(f"Sent POE2 SELL alert for purchased {item_name} to user {user_id}")
        else:
            # Only send buy alerts for items not yet purchased
            if signal == "COMPRA":
                await enviar_alerta_compra(discord_http, user_id, server_id, item_name, current_price, league, item_id)
                delivered_notifications.add((league, item_name, signal, current_price))
                logger.info(f"Sent POE2 BUY alert for {item_name} to user {user_id} from server {server_id}")

def calcular_senal(current_price, min_price, max_price):
    """Calculate the POE2 market signal from historical bounds."""
    if current_price <= min_price * (1 + UMBRAL_COMPRA):
        return "COMPRA"
    if current_price >= max_price * (1 - UMBRAL_VENTA):
        return "VENTA"
    return None

async def enviar_alerta_compra(discord_http, user_id, server_id, item_name, current_price, league, item_id=None):
    """Send a buy alert as an embed with a button to record purchase."""
    try:
        # Get bot identity for embed
        bot_identity = get_bot_identity(server_id)
        
        # Get translations
        translations = get_treasure_hunter_translations(server_id)
        
        # Generate alert message using LLM with personality, fallback to JSON
        try:
            message = await construir_mensaje_alerta(item_name, "COMPRA", current_price, server_id)
        except Exception as e:
            logger.warning(f"LLM message generation failed, using JSON fallback: {e}")
            message_template = translations.get("alert_buy_message", "{item} at {price} Div is a good buy opportunity.")
            message = message_template.format(item=item_name, price=current_price)
        
        # Create embed with translations
        title = translations.get("alert_buy_title", "🟢 Buy Opportunity - {item}").format(item=item_name)
        current_price_label = translations.get("alert_current_price", "💰 Current Price")
        league_label = translations.get("alert_league", "🏆 League")
        item_label = translations.get("alert_item", "� Item")
        footer_text = translations.get("alert_footer", "By {nickname}").format(nickname=bot_identity['nickname'])
        button_label = translations.get("button_record_purchase", "📝 Record Purchase")
        
        embed_data = {
            "title": title,
            "description": message,
            "color": 0x00ff00,
            "author": {
                "name": bot_identity['nickname'],
                "icon_url": bot_identity['avatar_url']
            },
            "fields": [
                {"name": current_price_label, "value": f"{current_price:.2f} Div", "inline": True},
                {"name": league_label, "value": league, "inline": True},
                {"name": item_label, "value": item_name, "inline": True}
            ],
            "footer": {
                "text": footer_text
            },
            "timestamp": datetime.now().isoformat()
        }
        
        # Create button for recording purchase
        button = discord_http.create_button(
            custom_id=f"poe2_buy_{item_name}_{league}_{current_price}",
            label=button_label,
            style=3,  # Success (green)
            emoji="💰"
        )
        
        action_row = discord_http.create_action_row([button])
        
        # Send as DM with embed and button
        sent = await discord_http.send_dm(
            int(user_id),
            embed=embed_data,
            components=[action_row]
        )
        
        if not sent:
            # Fallback to text message if embed fails
            fallback_msg = f"🟢 **BUY** {message}\n\n💰 Price: {current_price:.2f} Div\n🏆 League: {league}\n\n*To record this purchase, use the Canvas command or contact the administrator.*"
            await discord_http.send_dm(int(user_id), fallback_msg)
        
        return sent
    except Exception as e:
        logger.error(f"Error sending buy alert for {item_name}: {e}")
        return False

async def enviar_alerta_venta(discord_http, user_id, server_id, item_name, current_price, buy_price):
    """Send a sell alert for purchased items with a button to finish operation."""
    try:
        # Get bot identity for embed
        bot_identity = get_bot_identity(server_id)
        
        # Get translations
        translations = get_treasure_hunter_translations(server_id)
        
        # Calculate profit
        profit = current_price - buy_price
        profit_percent = (profit / buy_price) * 100 if buy_price > 0 else 0
        
        # Generate alert message using LLM with personality, fallback to JSON
        try:
            message = await construir_mensaje_alerta(item_name, "VENTA", current_price, server_id)
        except Exception as e:
            logger.warning(f"LLM message generation failed, using JSON fallback: {e}")
            message_template = translations.get("alert_sell_message", "{item} at {price} Div is a good sell opportunity.")
            message = message_template.format(item=item_name, price=current_price)
        
        # Create embed with translations
        title = translations.get("alert_sell_title", "🔴 Sell Opportunity - {item}").format(item=item_name)
        current_price_label = translations.get("alert_current_price", "💰 Current Price")
        buy_price_label = translations.get("alert_buy_price", "📥 Buy Price")
        profit_label = translations.get("alert_profit", "📈 Profit")
        footer_text = translations.get("alert_footer", "By {nickname}").format(nickname=bot_identity['nickname'])
        button_label = translations.get("button_finish_operation", "✅ Finish Operation")
        
        embed_data = {
            "title": title,
            "description": message,
            "color": 0xff0000,
            "author": {
                "name": bot_identity['nickname'],
                "icon_url": bot_identity['avatar_url']
            },
            "fields": [
                {"name": current_price_label, "value": f"{current_price:.2f} Div", "inline": True},
                {"name": buy_price_label, "value": f"{buy_price:.2f} Div", "inline": True},
                {"name": profit_label, "value": f"{profit:+.2f} Div ({profit_percent:+.1f}%)", "inline": True}
            ],
            "footer": {
                "text": footer_text
            },
            "timestamp": datetime.now().isoformat()
        }
        
        # Create button for finishing operation
        button = discord_http.create_button(
            custom_id=f"poe2_sell_{item_name}_{current_price}",
            label=button_label,
            style=4,  # Danger (red)
            emoji="💎"
        )
        
        action_row = discord_http.create_action_row([button])
        
        # Send as DM with embed and button
        sent = await discord_http.send_dm(
            int(user_id),
            embed=embed_data,
            components=[action_row]
        )
        
        if not sent:
            # Fallback to text message
            fallback_msg = f"🔴 **SELL** {message}\n\n💰 Price: {current_price:.2f} Div\n📥 Bought at: {buy_price:.2f} Div\n📈 Profit: {profit:+.2f} Div ({profit_percent:+.1f}%)\n\n*To finish this operation, use the Canvas command or contact the administrator.*"
            await discord_http.send_dm(int(user_id), fallback_msg)
        
        return sent
    except Exception as e:
        logger.error(f"Error sending sell alert for {item_name}: {e}")
        return False

async def construir_mensaje_alerta(item_name, signal, price, server_id=None):
    """Build the user-facing POE2 alert message."""
    try:
        from agent_engine import _build_system_prompt, _get_personality
        from agent_db import get_server_id

        server_to_use = server_id or get_server_id()
        server_personality = _get_personality(server_to_use) if server_to_use else PERSONALITY
        system_instruction = _build_system_prompt(server_personality, server_to_use)
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
        return await call_llm_async(system_instruction, complete_prompt, background=False, call_type="treasure_hunter_notification")
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
    """Store price history in the shared database using per-item table structure."""
    try:
        # Get item_id from item list
        items_catalog = poe2_manager.load_item_list(league)
        item_id = items_catalog.get(item_name.lower())
        
        if not item_id:
            logger.warning(f"Cannot store history for {item_name}: item_id not found")
            return
        
        # Convert entries to dict format
        price_entries = []
        for entry in historial[-10:]:  # Store last 10 entries
            price_entries.append({
                'price': entry.price,
                'timestamp': entry.time or datetime.now().isoformat(),
                'quantity': entry.quantity
            })
        
        # Use new per-item table structure (no raw_data)
        inserted = poe2_manager.insert_prices_bulk_for_item(league, item_id, item_name, price_entries)
        logger.debug(f"Stored {inserted} price entries for {item_name} (ID: {item_id}) in {league}")
        
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
