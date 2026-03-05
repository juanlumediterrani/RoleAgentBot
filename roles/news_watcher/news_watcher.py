import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.dirname(__file__))

import asyncio
import re
import feedparser
import aiohttp
import logging
from dotenv import load_dotenv
from agent_db import get_active_server_name
from agent_logging import get_logger
from discord_bot.discord_http import DiscordHTTP

logger = get_logger('news_watcher')


async def procesar_suscripciones(http, server_name: str = "default"):
    """Process all subscription types using the correct logic."""
    from db_role_news_watcher import get_news_watcher_db_instance
 
    db_watcher = get_news_watcher_db_instance(server_name)
    
    try:
        logger.info("🚀 Iniciando procesamiento de suscripciones...")
        
        # 1. Procesar suscripciones planas (todas las noticias con opinión)
        await procesar_suscripciones_planas(http, db_watcher, server_name)
        
        # 2. Procesar suscripciones con palabras clave (regex)
        await procesar_suscripciones_palabras(http, db_watcher, server_name)
        
        # 3. Procesar suscripciones con IA (detección por premisas)
        await procesar_suscripciones_ia(http, db_watcher, server_name)
        
        logger.info("✅ Procesamiento de suscripciones completado")
        
    except Exception as e:
        logger.exception(f"❌ Error general en procesamiento de suscripciones: {e}")


async def procesar_suscripciones_planas(http, db_watcher, server_name: str):
    """Procesa suscripciones planas (envía todas las noticias con opinión)."""
    try:
        logger.info("📰 Procesando suscripciones planas...")
        
        suscripciones = db_watcher.obtener_todas_suscripciones_activas()
        
        for usuario_id, categoria, feed_id, fecha in suscripciones:
            if feed_id:
                # Feed específico
                feed_data = db_watcher.obtener_feed_por_id(feed_id)
                if feed_data:
                    await _procesar_feed_suscripcion_plana(http, db_watcher, (feed_data[2], feed_data[1]), usuario_id, None)
            else:
                # Todos los feeds de la categoría
                feeds = db_watcher.obtener_feeds_activos(categoria)
                for feed in feeds:
                    await _procesar_feed_suscripcion_plana(http, db_watcher, (feed[2], feed[1]), usuario_id, None)
                    
    except Exception as e:
        logger.exception(f"❌ Error procesando suscripciones planas: {e}")


async def procesar_suscripciones_palabras(http, db_watcher, server_name: str):
    """Procesa suscripciones con palabras clave (regex)."""
    try:
        logger.info("🔍 Procesando suscripciones con palabras clave...")
        
        suscripciones_palabras = db_watcher.obtener_todas_suscripciones_palabras_activas()
        
        for usuario_id, canal_id, palabras_clave, categoria, feed_id in suscripciones_palabras:
            if feed_id:
                # Feed específico
                feed_data = db_watcher.obtener_feed_por_id(feed_id)
                if feed_data:
                    await _procesar_feed_suscripcion_palabras(http, db_watcher, (feed_data[2], feed_data[1]), usuario_id, canal_id, palabras_clave)
            else:
                # Todos los feeds de la categoría
                feeds = db_watcher.obtener_feeds_activos(categoria)
                for feed in feeds:
                    await _procesar_feed_suscripcion_palabras(http, db_watcher, (feed[2], feed[1]), usuario_id, canal_id, palabras_clave)
                    
    except Exception as e:
        logger.exception(f"❌ Error procesando suscripciones con palabras clave: {e}")


async def procesar_suscripciones_ia(http, db_watcher, server_name: str):
    """Procesa suscripciones con IA (detección por premisas)."""
    try:
        logger.info("🤖 Procesando suscripciones con IA...")
        
        suscripciones_ia = db_watcher.obtener_todas_suscripciones_categorias_activas()
        
        for usuario_id, categoria, feed_id, fecha in suscripciones_ia:
            if feed_id:
                # Feed específico
                feed_data = db_watcher.obtener_feed_por_id(feed_id)
                if feed_data:
                    await _procesar_feed_suscripcion_ia(http, db_watcher, (feed_data[2], feed_data[1]), usuario_id, None)
            else:
                # Todos los feeds de la categoría
                feeds = db_watcher.obtener_feeds_activos(categoria)
                for feed in feeds:
                    await _procesar_feed_suscripcion_ia(http, db_watcher, (feed[2], feed[1]), usuario_id, None)
                    
    except Exception as e:
        logger.exception(f"❌ Error procesando suscripciones con IA: {e}")


async def _procesar_feed_suscripcion_plana(http, db_watcher, feed_data, usuario_id, canal_id):
    """Procesa un feed para suscripciones planas (envía todas las noticias con opinión)."""
    try:
        url, nombre = feed_data
        logger.info(f"📰 Procesando feed plano: {nombre}")
        
        entries = await _obtener_ultimas_noticias(url, nombre, 5)
        for i, titulo in enumerate(entries[:5], 1):
            titulo = titulo or ''
            if not titulo:
                continue

            logger.info(f"📄 [{i}/5] {nombre}: {titulo[:80]}...")

            if db_watcher.noticia_esta_leida(titulo):
                logger.info(f"ℹ️ Noticia ya leída: {titulo}")
                continue

            # Para suscripciones planas, generar opinión de la personalidad sobre el título
            opinion = await _generar_opinion_personalidad(titulo, usuario_id)
            
            if opinion:
                await _enviar_notificacion_plana(http, db_watcher, [usuario_id], titulo, opinion, nombre)

            db_watcher.marcar_noticia_leida(titulo, nombre)

    except Exception as e:
        logger.exception(f"❌ Error procesando feed plano {nombre}: {e}")


async def _procesar_feed_suscripcion_palabras(http, db_watcher, feed_data, usuario_id, canal_id, palabras_clave):
    """Procesa un feed para suscripciones con palabras clave (regex)."""
    try:
        url, nombre = feed_data
        logger.info(f"🔍 Procesando feed palabras: {nombre}")
        
        entries = await _obtener_ultimas_noticias(url, nombre, 5)
        for i, titulo in enumerate(entries[:5], 1):
            titulo = titulo or ''
            if not titulo:
                continue

            logger.info(f"📄 [{i}/5] {nombre}: {titulo[:80]}...")

            if db_watcher.noticia_esta_leida(titulo):
                logger.info(f"ℹ️ Noticia ya leída: {titulo}")
                continue

            # Verificar coincidencia con palabras clave usando regex
            if _verificar_palabras_clave_regex(titulo, palabras_clave):
                logger.info(f"🎯 Coincidencia palabras clave: {titulo[:60]}...")
                
                # Generar opinión de la personalidad sobre el título
                opinion = await _generar_opinion_personalidad(titulo, usuario_id)
                
                if opinion:
                    await _enviar_notificacion_palabras(http, db_watcher, [usuario_id], titulo, opinion, nombre, palabras_clave)

            db_watcher.marcar_noticia_leida(titulo, nombre)

    except Exception as e:
        logger.exception(f"❌ Error procesando feed palabras {nombre}: {e}")


async def _procesar_feed_suscripcion_ia(http, db_watcher, feed_data, usuario_id, canal_id):
    """Procesa un feed para suscripciones con IA (detección por premisas)."""
    try:
        url, nombre = feed_data
        logger.info(f"🤖 Procesando feed IA: {nombre}")
        
        entries = await _obtener_ultimas_noticias(url, nombre, 5)
        for i, titulo in enumerate(entries[:5], 1):
            titulo = titulo or ''
            if not titulo:
                continue

            logger.info(f"📄 [{i}/5] {nombre}: {titulo[:80]}...")

            if db_watcher.noticia_esta_leida(titulo):
                logger.info(f"ℹ️ Noticia ya leída: {titulo}")
                continue

            # Analizar con IA según premisas clave del usuario (Cohere SIN personalidad)
            coincidencia = await _analizar_con_cohere_premisas(titulo, usuario_id)
            
            if coincidencia:
                logger.info(f"🎯 Coincidencia IA: {titulo[:60]}...")
                
                # Obtener las premisas del usuario para mostrarlas
                from agent_db import get_active_server_name
                server_name = get_active_server_name() or "default"
                db_watcher_local = get_watcher_db_instance(server_name)
                premisas, contexto = db_watcher_local.obtener_premisas_con_contexto(usuario_id)
                premisas_texto = ", ".join(premisas[:3])  # Mostrar primeras 3 premisas
                
                # Generar opinión de la personalidad sobre la noticia y las premisas
                opinion = await _generar_opinion_premisa(titulo, premisas_texto, usuario_id)
                
                if opinion:
                    await _enviar_notificacion_ia(http, db_watcher, [usuario_id], titulo, opinion, nombre, premisas_texto)

            db_watcher.marcar_noticia_leida(titulo, nombre)

    except Exception as e:
        logger.exception(f"❌ Error procesando feed IA {nombre}: {e}")


async def _analizar_con_cohere_premisas(titulo: str, usuario_id: str) -> bool:
    """Analiza UN TITULAR con Cohere para detectar coincidencias con premisas (SIN personalidad)."""
    try:
        import cohere
        import os
        from agent_db import get_active_server_name
        from db_role_watcher import get_watcher_db_instance
        
        api_key = (os.getenv("COHERE_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("COHERE_API_KEY no está configurada")

        client = cohere.Client(api_key=api_key, timeout=30)  # Timeout más corto para un titular
        
        # Obtener premisas del usuario (personalizadas o globales)
        server_name = get_active_server_name() or "default"
        db_watcher = get_watcher_db_instance(server_name)
        premisas, contexto = db_watcher.obtener_premisas_con_contexto(usuario_id)
        
        if not premisas:
            logger.warning(f"⚠️ No hay premisas configuradas para usuario {usuario_id}")
            return False
        
        # Construir texto de premisas de forma ultra concisa
        texto_premisas = "\n".join([f"{i}. {p}" for i, p in enumerate(premisas, 1)])
        
        # Prompt ultra neutro - solo devuelve TRUE/FALSE para UN TITULAR
        prompt_analisis = f"""{texto_premisas}

Título: "{titulo}"

¿Coincide este título con ALGUNA premisa?
Responde únicamente: TRUE o FALSE"""
        
        try:
            res = client.chat(
                model="command-a-03-2025",
                message=prompt_analisis,
                temperature=0.0,  # Máxima objetividad
                max_tokens=5  # Solo necesita responder TRUE/FALSE
            )
            
            resultado = getattr(res, "text", "").strip()
            logger.info(f"🤖 TITULAR: {titulo[:30]}... → {resultado}")
            
            # Parsear resultado - solo TRUE/FALSE
            return resultado.upper() == "TRUE"
                
        except Exception as e:
            logger.exception(f"Error en llamada a Cohere para titular: {e}")
            return False
            
    except Exception as e:
        logger.exception(f"Error en análisis de titular con Cohere: {e}")
        return False


async def _generar_opinion_personalidad(titulo: str, usuario_id: str) -> str:
    """Genera opinión de la personalidad sobre un título de noticia."""
    try:
        from agent_engine import pensar
        from agent_db import get_active_server_name
        
        server_name = get_active_server_name() or "default"
        
        # Importar el prompt de la personalidad
        from news_watcher import ROL_VIGIA_PERSONALIDAD
        
        # Crear prompt para la personalidad sobre la noticia
        prompt = f"{ROL_VIGIA_PERSONALIDAD}\n\n¿Qué opinas de esta noticia? \"{titulo}\""
        
        # Obtener opinión de la personalidad
        opinion = await pensar(prompt, server_name)
        
        if opinion and len(opinion.strip()) > 0:
            logger.info(f"💭 Opinión generada: {opinion[:50]}...")
            return opinion.strip()
        else:
            logger.warning("⚠️ No se pudo generar opinión de la personalidad")
            return None
            
    except Exception as e:
        logger.exception(f"Error generando opinión de personalidad: {e}")
        return None


async def _generar_opinion_premisa(titulo: str, premisa: str, usuario_id: str) -> str:
    """Genera opinión de la personalidad sobre una noticia que coincide con una premisa."""
    try:
        from agent_engine import pensar
        from agent_db import get_active_server_name
        
        server_name = get_active_server_name() or "default"
        
        # Importar el prompt de la personalidad
        from news_watcher import ROL_VIGIA_PERSONALIDAD
        
        # Crear prompt específico para la premisa
        prompt = f"{ROL_VIGIA_PERSONALIDAD}\n\nEsta noticia coincide con la premisa: \"{premisa}\"\nNoticia: \"{titulo}\"\n¿Cuál es tu opinión sobre esta situación?"
        
        # Obtener opinión de la personalidad
        opinion = await pensar(prompt, server_name)
        
        if opinion and len(opinion.strip()) > 0:
            logger.info(f"💭 Opinión sobre premisa: {opinion[:50]}...")
            return opinion.strip()
        else:
            logger.warning("⚠️ No se pudo generar opinión sobre la premisa")
            return None
            
    except Exception as e:
        logger.exception(f"Error generando opinión sobre premisa: {e}")
        return None


async def _enviar_notificacion_plana(http, db_watcher, usuarios, titulo, opinion, nombre_feed):
    """Envía notificación de suscripción plana."""
    try:
        # Obtener link de la noticia (simulado por ahora)
        link = f"https://example.com/noticia/{hash(titulo) % 10000}"
        
        mensaje = (
            f"📰 **Nueva Noticia** - {nombre_feed}\n\n"
            f"📌 **{titulo}**\n"
            f"🔗 [Leer más]({link})\n\n"
            f"💭 **Opinión:** {opinion}"
        )
        
        for usuario_id in usuarios:
            await http.send_message(usuario_id, mensaje)
            
    except Exception as e:
        logger.exception(f"Error enviando notificación plana: {e}")


async def _enviar_notificacion_palabras(http, db_watcher, usuarios, titulo, opinion, nombre_feed, palabras_clave):
    """Envía notificación de coincidencia de palabras clave."""
    try:
        # Obtener link de la noticia (simulado por ahora)
        link = f"https://example.com/noticia/{hash(titulo) % 10000}"
        
        mensaje = (
            f"🔍 **Coincidencia de Palabras Clave** - {nombre_feed}\n\n"
            f"📌 **{titulo}**\n"
            f"🔗 [Leer más]({link})\n"
            f"🎯 **Palabras:** `{palabras_clave}`\n\n"
            f"💭 **Opinión:** {opinion}"
        )
        
        for usuario_id in usuarios:
            await http.send_message(usuario_id, mensaje)
            
    except Exception as e:
        logger.exception(f"Error enviando notificación de palabras: {e}")


async def _enviar_notificacion_ia(http, db_watcher, usuarios, titulo, opinion, nombre_feed, premisa):
    """Envía notificación de coincidencia de IA."""
    try:
        # Obtener link de la noticia (simulado por ahora)
        link = f"https://example.com/noticia/{hash(titulo) % 10000}"
        
        mensaje = (
            f"🤖 **Alerta Crítica Detectada** - {nombre_feed}\n\n"
            f"📌 **{titulo}**\n"
            f"🔗 [Leer más]({link})\n"
            f"🎯 **Premisa:** {premisa}\n\n"
            f"💭 **Análisis:** {opinion}"
        )
        
        for usuario_id in usuarios:
            await http.send_message(usuario_id, mensaje)
            
    except Exception as e:
        logger.exception(f"Error enviando notificación IA: {e}")


def _verificar_palabras_clave_regex(titulo: str, palabras_clave: str) -> bool:
    """Verifica si una noticia coincide con palabras clave usando regex."""
    try:
        titulo_lower = titulo.lower()
        palabras_lista = [p.strip().lower() for p in palabras_clave.split(',')]
        
        # Crear patrón regex para cada palabra clave
        for palabra in palabras_lista:
            # Escapar caracteres especiales y crear patrón que coincida con la palabra completa
            patron = re.escape(palabra)
            if re.search(rf'\b{patron}\b', titulo_lower):
                return True
        
        return False
    except Exception as e:
        logger.exception(f"Error verificando palabras clave con regex: {e}")
        return False


async def _obtener_ultimas_noticias(url: str, nombre_feed: str, limite: int = 5) -> list:
    """Obtiene las últimas noticias de un feed RSS."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.warning(f"⚠️ Feed {nombre_feed} respondió con status {response.status}")
                    return []
                
                content = await response.text()
                root = feedparser.parse(content)
                entries = root.entries[:limite]
                titles = [entry.title for entry in entries if entry.title]
                logger.info(f"📰 {len(titles)} noticias de {nombre_feed}")
                return titles
    except Exception as e:
        logger.exception(f"❌ No se pudo obtener feed {nombre_feed}: {e}")
        return []

# Cargar variables de entorno
_env_candidates = [
    (os.getenv("ROLE_AGENT_ENV_FILE") or "").strip(),
    os.path.expanduser("~/.roleagentbot.env"),
    os.path.join(os.path.dirname(__file__), ".env"),
]

for _p in _env_candidates:
    if _p and os.path.exists(_p):
        load_dotenv(_p, override=False)
        break

logger = get_logger('watcher')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "news_watcher",
    # "system_prompt_addition": "MISION ACTIVA - NEWS WATCHER DE NOTICIAS: Eres el Vigía de la Torre. Tu misión es detectar noticias sumamente importantes."
}

# Prompt para la personalidad (opinión sobre titulares)
ROL_VIGIA_PERSONALIDAD = (
    "Eres el Vigía de la Torre, un guardián ancestral que vigila el mundo desde lo alto. "
    "Tu carácter es sabio, directo y a veces un poco sombrío. "
    "Cuando das tu opinión sobre las noticias, sé conciso pero impactante. "
    "Usa un lenguaje que refleje tu naturaleza vigilante y tu larga experiencia observando los eventos del mundo."
)

# Prompt neutro para análisis de premisas con Cohere (SIN personalidad)
PROMPT_COHERE_ANALISIS = (
    "Analiza objetivamente si el título de una noticia coincide con las premisas proporcionadas. "
    "Responde únicamente según las instrucciones dadas, sin añadir opiniones ni estilo personal."
)


async def main():
    """Función principal del Vigía de Noticias."""
    try:
        logger.info("🚀 Iniciando Vigía de Noticias...")
        
        # Obtener configuración del servidor
        server_name = get_active_server_name() or "default"
        logger.info(f"📡 Servidor: {server_name}")
        
        # Inicializar cliente HTTP para Discord
        discord_token = os.getenv("DISCORD_TOKEN")
        if not discord_token:
            logger.error("❌ DISCORD_TOKEN no está configurado")
            return
        
        http = DiscordHTTP(discord_token)
        
        # Procesar todas las suscripciones
        await procesar_suscripciones(http, server_name)
        
        logger.info("✅ Vigía de Noticias completado")
        
    except Exception as e:
        logger.exception(f"❌ Error en main del Vigía: {e}")


if __name__ == "__main__":
    asyncio.run(main())
