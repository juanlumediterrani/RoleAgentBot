import os
import json
from agent_logging import get_logger

logger = get_logger('watcher_messages')

def get_watcher_messages():
    """Load custom Watcher messages from personality file."""
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "agent_config.json")
        with open(config_path, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        personality_rel = agent_cfg.get("personality", "")
        answers_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            os.path.dirname(personality_rel),
            "answers.json",
        )
        with open(answers_path, encoding="utf-8") as f:
            watcher_messages = json.load(f).get("discord", {}).get("watcher_messages", {})
        
        if not watcher_messages:
            logger.warning("⚠️ No custom watcher messages found in personality")
            return get_default_messages()
        
        logger.info("🦅 Custom watcher messages loaded from personality")
        return watcher_messages
        
    except Exception as e:
        logger.error(f"❌ Error loading watcher messages: {e}")
        return get_default_messages()

def get_default_messages():
    """Default messages if no customization available."""
    return {
        "feeds_available_title": "📡 Available Feeds",
        "categorias_disponibles_title": "📂 Available Categories",
        "suscripcion_exitosa_categoria": "✅ You have subscribed to all news from '{category}'",
        "suscripcion_exitosa_feed": "✅ You have subscribed to feed {feed_id} from category '{category}'",
        "suscripcion_canal_exitosa_categoria": "✅ This channel has been subscribed to all news from '{category}'",
        "suscripcion_canal_exitosa_feed": "✅ This channel has been subscribed to feed {feed_id} from '{category}'",
        "suscripcion_cancelada_categoria": "✅ Subscription cancelled to category '{category}'",
        "suscripcion_cancelada_feed": "✅ Subscription cancelled to feed {feed_id} from '{category}'",
        "suscripcion_canal_cancelada_categoria": "✅ Subscription cancelled to category '{category}'",
        "suscripcion_canal_cancelada_feed": "✅ Subscription cancelled to feed {feed_id} from '{category}'",
        "error_general": "❌ Error: {error}",
        "error_suscripcion": "❌ Error performing subscription",
        "error_cancelacion": "❌ Error cancelling subscription",
        "error_permisos": "❌ Only administrators can perform this action",
        "error_feed_no_encontrado": "❌ Feed ID {feed_id} not found in category '{category}'",
        "error_categoria_no_encontrada": "❌ Category '{category}' not found",
        "error_feed_id_invalido": "❌ Feed ID must be a number",
        "error_no_hay_feeds": "📭 No feeds configured",
        "error_no_hay_categorias": "📭 No categories available",
        "error_no_suscripciones": "📭 You have no active subscriptions",
        "error_no_suscripciones_canal": "📭 This channel has no active subscriptions",
        "error_no_hay_feeds_generales": "❌ No general feeds for '{category}'",
        "error_no_hay_palabras_clave": "📭 You have no keyword subscriptions",
        "estado_titulo": "📊 Your Subscriptions",
        "estado_canal_titulo": "📊 Channel Subscriptions",
        "palabras_clave_titulo": "🔍 Your Keywords",
        "uso_suscribir": "📝 Usage: `!watcher subscribe <category> [feed_id]`",
        "uso_cancelar": "📝 Usage: `!watcher cancel <category> [feed_id]`",
        "uso_general": "📝 Usage: `!watcher general <category>`",
        "uso_palabras": "📝 Usage: `!watcher keywords \"word1,word2,word3\"`",
        "usage_cancelar_palabras": "📝 Usage: `!watcher cancel_keywords \"word1,word2\"`",
        "usage_mixto": "📝 Usage: `!watcher mixed <category>`",
        "usage_agregar_feed": "📝 Usage: `!watcher add_feed <name> <url> <category> [country] [language]`",
        "usage_canal_suscribir": "📝 Usage: `!watcherchannel subscribe <category> [feed_id]`",
        "usage_canal_cancelar": "📝 Usage: `!watcherchannel cancel <category> [feed_id]`",
        "usage_canal_palabras": "📝 Usage: `!watcherchannel keywords \"word1,word2\"`",
        "suscripcion_general_exitosa": "✅ Subscribed to general feeds from '{category}' with AI classification",
        "suscripcion_palabras_exitosa": "✅ Subscribed to keywords: '{keywords}'",
        "suscripcion_palabras_cancelada": "✅ Subscription cancelled: '{keywords}'",
        "suscripcion_mixta_exitosa": "✅ Subscribed to mixed coverage of '{category}' (specialized + general)",
        "suscripcion_mixta_parcial": "✅ Subscribed to specialized coverage of '{category}'",
        "suscripcion_canal_palabras_exitosa": "✅ Channel subscribed to keywords: '{keywords}'",
        "notificacion_critica_detectada": "🚨 CRITICAL NEWS DETECTED! {title}",
        "notificacion_normal": "📡 New news: {title}",
        "feed_agregado_exitosa": "✅ Feed '{name}' added to category '{category}'"
    }

def get_message(key, **kwargs):
    """Get a custom message with variable formatting."""
    messages = get_watcher_messages()
    message = messages.get(key)
    
    # If personality doesn't have the message, use English fallback
    if message is None:
        message = get_english_fallback(key)
    
    # Replace variables in message
    try:
        return message.format(**kwargs)
    except KeyError as e:
        logger.error(f"❌ Error formatting message '{key}': variable not found {e}")
        return message
    except Exception as e:
        logger.error(f"❌ Error formatting message '{key}': {e}")
        return message

def get_english_fallback(key):
    """Get English fallback message for when personality doesn't have custom message."""
    fallbacks = {
        "error_no_suscripciones": "📝 You don't have any active subscriptions to clear.",
        "error_no_hay_kategorias": "📝 No categories available",
        "uso_suscribir": "📝 Usage: `!watcher subscribe <category> [feed_id]`",
        "error_feed_no_encontrado": "❌ Feed ID {feed_id} not found in category '{category}'",
        "error_feed_id_invalido": "❌ feed_id must be a number",
        "error_kategori_no_encontrada": "❌ Category '{category}' not found",
        "suscripcion_exitosa_categoria": "✅ You have subscribed to all news from '{category}'",
        "suscripcion_exitosa_feed": "✅ You have subscribed to feed {feed_id} from category '{category}'",
        "error_suscripcion": "❌ Error creating flat subscription",
        "uso_cancelar": "📝 Usage: `!watcher unsubscribe <category> [feed_id]`",
        "suscripcion_cancelada_kategori": "✅ Subscription cancelled to category '{category}'",
        "suscripcion_cancelada_feed": "✅ Subscription cancelled to feed {feed_id} from '{category}'",
        "error_cancelasion": "❌ Error canceling flat subscription",
        "error_general": "❌ Error: {error}",
        "error_no_hay_feeds": "📭 No feeds configured",
        "error_no_active_subscriptions": "📭 You have no active subscriptions",
        "estado_titulo": "📊 Your Subscriptions",
        "palabras_clave_titulo": "🔍 Your Keywords",
        "uso_general": "📝 Usage: `!watcher general <category>`",
        "uso_palabras": "📝 Usage: `!watcher keywords \"word1,word2,word3\"`",
        "usage_cancelar_palabras": "📝 Usage: `!watcher cancel_keywords \"word1,word2\"`",
        "usage_mixto": "📝 Usage: `!watcher mixed <category>`",
        "usage_agregar_feed": "📝 Usage: `!watcher add_feed <name> <url> <category> [country] [language]`",
        "suscripcion_general_exitosa": "✅ Subscribed to general feeds from '{category}' with AI classification",
        "suscripcion_palabras_exitosa": "✅ Subscribed to keywords: '{keywords}'",
        "suscripcion_palabras_cancelada": "✅ Subscription cancelled: '{keywords}'",
        "suscripcion_mixta_exitosa": "✅ Subscribed to mixed coverage of '{category}' (specialized + general)",
        "suscripcion_mixta_parcial": "✅ Subscribed to specialized coverage of '{category}'",
        "suscripcion_canal_palabras_exitosa": "✅ Channel subscribed to keywords: '{keywords}'",
        "notificacion_critica_detectada": "🚨 CRITICAL NEWS DETECTED! {title}",
        "notificacion_normal": "📡 New news: {title}",
        "feed_agregado_exitosa": "✅ Feed '{name}' added to category '{category}'",
        "error_permisos": "❌ Only administrators can perform this action",
        "error_no_hay_feeds_generales": "❌ No general feeds for '{category}'",
        "error_no_hay_palabras_clave": "📭 You have no keyword subscriptions",
        "error_no_suscripciones_kanal": "📭 This channel has no active subscriptions",
        "debes_proporcionar_palabras": "❌ You must provide keywords",
        "error_suscribir_palabras": "❌ Error subscribing to keywords",
        "no_suscripcion_palabras": "❌ No keyword subscription found",
        "error_cancelar_palabras": "❌ Error canceling keyword subscription",
        "error_suscripcion_mixta": "❌ Error creating mixed subscription",
        "error_suscribir_cobertura": "❌ Error subscribing to coverage",
        "permisos_gestionar_canales": "❌ Only administrators can manage channels",
        "error_suscribir_canal_palabras": "❌ Error subscribing channel to keywords",
        "permisos_cancelar_canal": "❌ Only administrators can cancel channel subscriptions",
        "no_suscripcion_cancelar": "❌ No subscription found to cancel",
        "error_cancelar_suscripcion_canal": "❌ Error canceling channel subscription",
        "no_active_channel_subscriptions": "📭 This channel has no active subscriptions",
        "error_obteniendo_estado_canal": "❌ Error getting channel status",
        "error_obteniendo_palabras_clave": "❌ Error getting keywords",
        "error_obteniendo_estado": "❌ Error getting status",
        "help_sent_private": "📝 Help sent via private message",
        "feed_id_no_encontrado": "❌ Feed ID {feed_id} not found in category '{category}'",
        "categoria_no_encontrada": "❌ Category '{category}' not found. Use `!watcher categories`",
        "solo_admins_feeds": "❌ Only administrators can add feeds",
        "error_agregar_feed": "❌ Error adding feed",
        "no_feeds_generales": "❌ No general feeds for '{category}'. Use `!watcher feeds`",
        "error_suscribir_generales": "❌ Error subscribing to general feeds",
        "error_procesando_suscripcion": "❌ Error processing subscription",
        "error_cancelando_suscripcion": "❌ Error canceling flat subscription",
        "error_cancelando_suscripcion_ia": "❌ Error canceling AI subscription",
        "error_mostrando_estado": "❌ Error showing subscription status",
        "error_mostrando_categorias": "❌ Error showing categories",
        "error_agregando_feed": "❌ Error adding feed",
        "uso_general_unsubscribe": "📝 Usage: `!watcher general unsubscribe <category> [feed_id]`",
        "ya_tienes_suscripcion_plana": "ℹ️ You already have an active flat subscription. Use `!watcher unsubscribe <category>` first if you want to change.",
        "no_tienes_suscripcion_plana": "❌ You don't have an active flat subscription in that category/feed",
        "ya_tienes_suscripcion_ia": "ℹ️ You already have an active AI subscription. Use `!watcher general unsubscribe <category>` first if you want to change.",
        "no_tienes_suscripcion_ia": "❌ You don't have an active AI subscription for that category/feed",
        "no_active_flat_subscription": "📝 You don't have an active flat subscription",
        "no_active_keyword_subscription": "📝 You don't have an active keywords subscription",
        "no_active_ai_subscription": "📝 You don't have an active AI subscription",
        "no_premisas_configuradas": "⚠️ You have no premises configured. Use `!watcher premises add <premise>` before subscribing with AI.",
        "suscripcion_ia_exitosa_feed": "✅ AI subscription created: Feed {feed_id} in category '{category}'",
        "suscripcion_ia_exitosa_categoria": "🤖 **AI subscription** to '{category}' - I will analyze critical news using your premises",
        "error_creando_suscripcion_ia": "❌ Error creating AI subscription",
        "error_procesando_suscripcion_ia": "❌ Error processing AI subscription",
        "suscripcion_palabras_global": "🔍 **Global keywords subscription** - Searching: '{keywords}'",
        "error_suscribiendo_palabras_clave": "❌ Error subscribing to keywords",
        "uso_keywords_add": "📝 Usage: `!watcher keywords add <keyword>`",
        "palabra_añadida": "✅ Keyword '{keyword}' added. List: {keywords}",
        "palabra_añadida_lista": "✅ Keyword '{keyword}' added. Current list: {keywords}",
        "error_añadir_palabra": "❌ Error adding keyword",
        "channel_subscription_successful_category": "🤖 **AI subscription** to '{category}' - I will analyze critical news using your premises",
        "channel_subscription_successful_feed": "🤖 **AI subscription** to feed {feed_id} in '{category}' - I will analyze critical news using your premises",
        "feed_id_not_found": "❌ Feed ID {feed_id} not found in category '{category}'",
        "feed_id_must_be_number": "❌ Feed ID must be a number"
    }
    
    return fallbacks.get(key, f"❌ Message not found: {key}")
