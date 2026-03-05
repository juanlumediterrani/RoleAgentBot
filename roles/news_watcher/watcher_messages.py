import os
import json
from agent_logging import get_logger

logger = get_logger('vigia_messages')

def get_vigia_messages():
    """Carga los mensajes personalizados del Vigía desde el archivo de personalidad."""
    try:
        # Intentar cargar desde la personalidad activa
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # Root del proyecto
        agent_config_path = os.path.join(base_dir, "agent_config.json")
        
        with open(agent_config_path, encoding="utf-8") as f:
            agent_cfg = json.load(f)
        
        personality_rel = agent_cfg.get("personality", "personalities/default.json")
        personality_path = os.path.join(base_dir, personality_rel)
        
        with open(personality_path, encoding="utf-8") as f:
            personality = json.load(f)
        
        # Obtener mensajes específicos del vigía
        vigia_messages = personality.get("discord", {}).get("vigia_messages", {})
        
        if not vigia_messages:
            logger.warning("⚠️ No se encontraron mensajes personalizados del vigía en la personalidad")
            return get_default_messages()
        
        logger.info("🦅 Mensajes personalizados del vigía cargados desde personalidad")
        return vigia_messages
        
    except Exception as e:
        logger.error(f"❌ Error cargando mensajes del vigía: {e}")
        return get_default_messages()

def get_default_messages():
    """Mensajes por defecto si no hay personalización."""
    return {
        "feeds_disponibles_title": "📡 Feeds Disponibles",
        "categorias_disponibles_title": "📂 Categorías Disponibles",
        "suscripcion_exitosa_categoria": "✅ Te has suscrito a todas las noticias de '{categoria}'",
        "suscripcion_exitosa_feed": "✅ Te has suscrito al feed {feed_id} de la categoría '{categoria}'",
        "suscripcion_canal_exitosa_categoria": "✅ Este canal ha sido suscrito a todas las noticias de '{categoria}'",
        "suscripcion_canal_exitosa_feed": "✅ Este canal ha sido suscrito al feed {feed_id} de '{categoria}'",
        "suscripcion_cancelada_categoria": "✅ Suscripción cancelada a la categoría '{categoria}'",
        "suscripcion_cancelada_feed": "✅ Suscripción cancelada al feed {feed_id} de '{categoria}'",
        "suscripcion_canal_cancelada_categoria": "✅ Suscripción cancelada a la categoría '{categoria}'",
        "suscripcion_canal_cancelada_feed": "✅ Suscripción cancelada al feed {feed_id} de '{categoria}'",
        "error_general": "❌ Error: {error}",
        "error_suscripcion": "❌ Error al realizar suscripción",
        "error_cancelacion": "❌ Error al cancelar suscripción",
        "error_permisos": "❌ Solo administradores pueden realizar esta acción",
        "error_feed_no_encontrado": "❌ Feed ID {feed_id} no encontrado en categoría '{categoria}'",
        "error_categoria_no_encontrada": "❌ Categoría '{categoria}' no encontrada",
        "error_feed_id_invalido": "❌ Feed ID debe ser un número",
        "error_no_hay_feeds": "📭 No hay feeds configurados",
        "error_no_hay_categorias": "📭 No hay categorías disponibles",
        "error_no_suscripciones": "📭 No tienes suscripciones activas",
        "error_no_suscripciones_canal": "📭 Este canal no tiene suscripciones activas",
        "error_no_hay_feeds_generales": "❌ No hay feeds generales para '{categoria}'",
        "error_no_hay_palabras_clave": "📭 No tienes suscripciones de palabras clave",
        "estado_titulo": "📊 Tus Suscripciones",
        "estado_canal_titulo": "📊 Suscripciones del Canal",
        "palabras_clave_titulo": "🔍 Tus Palabras Clave",
        "uso_suscribir": "📝 Uso: `!vigia suscribir <categoría> [feed_id]`",
        "uso_cancelar": "📝 Uso: `!vigia cancelar <categoría> [feed_id]`",
        "uso_general": "📝 Uso: `!vigia general <categoría>`",
        "uso_palabras": "📝 Uso: `!vigia palabras \"palabra1,palabra2,palabra3\"`",
        "usage_cancelar_palabras": "📝 Uso: `!vigia cancelar_palabras \"palabra1,palabra2\"`",
        "usage_mixto": "📝 Uso: `!vigia mixto <categoría>`",
        "usage_agregar_feed": "📝 Uso: `!vigia agregar_feed <nombre> <url> <categoría> [país] [idioma]`",
        "usage_canal_suscribir": "📝 Uso: `!vigiacanal suscribir <categoría> [feed_id]`",
        "usage_canal_cancelar": "📝 Uso: `!vigiacanal cancelar <categoría> [feed_id]`",
        "usage_canal_palabras": "📝 Uso: `!vigiacanal palabras \"palabra1,palabra2\"`",
        "suscripcion_general_exitosa": "✅ Suscrito a feeds generales de '{categoria}' con clasificación IA",
        "suscripcion_palabras_exitosa": "✅ Suscrito a palabras clave: '{palabras}'",
        "suscripcion_palabras_cancelada": "✅ Suscripción cancelada: '{palabras}'",
        "suscripcion_mixta_exitosa": "✅ Suscrito a cobertura mixta de '{categoria}' (especializado + general)",
        "suscripcion_mixta_parcial": "✅ Suscrito a cobertura especializada de '{categoria}'",
        "suscripcion_canal_palabras_exitosa": "✅ Canal suscrito a palabras clave: '{palabras}'",
        "notificacion_critica_detectada": "🚨 ¡NOTICIA CRÍTICA DETECTADA! {titulo}",
        "notificacion_normal": "📡 Nueva noticia: {titulo}",
        "feed_agregado_exitosa": "✅ Feed '{nombre}' agregado a categoría '{categoria}'"
    }

def get_message(key, **kwargs):
    """Obtiene un mensaje personalizado con formato de variables."""
    messages = get_vigia_messages()
    message = messages.get(key, f"❌ Mensaje no encontrado: {key}")
    
    # Reemplazar variables en el mensaje
    try:
        return message.format(**kwargs)
    except KeyError as e:
        logger.error(f"❌ Error formateando mensaje '{key}': variable no encontrada {e}")
        return message
    except Exception as e:
        logger.error(f"❌ Error formateando mensaje '{key}': {e}")
        return message
