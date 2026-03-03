import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.append(os.path.dirname(__file__))

import asyncio
import xml.etree.ElementTree as ET
import aiohttp
from dotenv import load_dotenv
import cohere
from agent_engine import construir_prompt, get_discord_token
from db_role_vigia import get_vigia_db_instance
from agent_db import get_active_server_name
from agent_logging import get_logger
from discord_http import DiscordHTTP

_env_candidates = [
    (os.getenv("ROLE_AGENT_ENV_FILE") or "").strip(),
    os.path.expanduser("~/.roleagentbot.env"),
    os.path.join(os.path.dirname(__file__), ".env"),
]
for _p in _env_candidates:
    if _p and os.path.exists(_p):
        load_dotenv(_p, override=False)
        break

logger = get_logger('vigia')

# Configuración de la misión
MISSION_CONFIG = {
    "name": "vigia_noticias",
    "system_prompt_addition": "MISION ACTIVA - VIGÍA DE NOTICIAS: Eres el Vigía de la Torre. Tu misión es detectar noticias sumamente importantes. Es crítica cuando: Escala una guerra, cae en bancarrota un país o gran empresa, hay una crisis humanitaria grave, o un evento con impacto global inminente."
}

# Feed RSS de CNBC
RSS_URL = "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362"

ROL_VIGIA = (
    "Eres el Vigía de la Torre. Tu misión es detectar noticias sumamente importantes. "
    "Es crítica cuando: Escala una guerra, cae en bancarrota un país o gran empresa, hay una crisis humanitaria grave, "
    "o un evento con impacto global inminente. Si la noticia no es crítica, responde únicamente: 'basura umana'. "
    "Si es crítica, responde con un análisis breve y directo como un orco, resaltando la gravedad y el impacto potencial."
)


def _analizar_con_cohere(titulo: str) -> str:
    """Analiza una noticia usando Cohere con el sistema unificado de prompts de Putre."""
    api_key = (os.getenv("COHERE_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("COHERE_API_KEY no está configurada (cárgala desde crontab o desde ~/.putrebot.env)")

    client = cohere.Client(api_key=api_key, timeout=60)

    # Usar el sistema unificado de construcción de prompts
    system_instruction, prompt_final = construir_prompt(
        ROL_VIGIA,
        contenido_usuario=f"Noticia para vigilar: {titulo}",
        es_publico=False
    )

    try:
        res = client.chat(
            model="command-a-03-2025",
            message=prompt_final,
            preamble=system_instruction,
            temperature=0.8,  # Temperatura similar a la de Putre
        )
        
        text = getattr(res, "text", None)
        return (text or "").strip()
    except Exception as e:
        logger.exception(f"Error en llamada a Cohere: {e}")
        return "basura umana"

async def _procesar_feeds(http: DiscordHTTP):
    try:
        server_name = get_active_server_name() or "default"
        db_vigia = get_vigia_db_instance(server_name)

        feeds = db_vigia.obtener_feeds_activos()
        logger.info(f"✅ {len(feeds)} feeds configurados")

        if not feeds:
            logger.warning("⚠️ No hay feeds activos configurados")
            return

        for feed_data in feeds:
            await _procesar_feed_individual(http, db_vigia, feed_data)

    except Exception as e:
        logger.exception(f"❌ Error Vigía: {e}")


async def _procesar_feed_individual(http: DiscordHTTP, db_vigia, feed_data):
    """Procesa un feed individual con lógica híbrida."""
    feed_id, nombre, url, categoria, pais, idioma, prioridad, palabras_clave, tipo_feed = feed_data

    try:
        logger.info(f"📡 Procesando feed: {nombre} ({categoria}) - Tipo: {tipo_feed}")

        suscriptores = db_vigia.obtener_suscriptores_por_categoria(categoria, feed_id)
        if not suscriptores:
            logger.info(f"ℹ️ No hay suscriptores para {categoria}/{feed_id}")
            return

        logger.info(f"👥 {len(suscriptores)} suscriptores para {categoria}")

        entries = await _obtener_entradas_feed(url, nombre)
        if not entries:
            return

        for i, titulo in enumerate(entries[:3], 1):
            titulo = titulo or ''
            if not titulo:
                continue

            logger.info(f"📄 [{i}/{len(entries)}] {nombre}: {titulo[:80]}...")

            if db_vigia.noticia_esta_leida(titulo):
                logger.info(f"ℹ️ Noticia ya leída: {titulo}")
                continue

            debe_enviar = await _procesar_noticia_hibrida(db_vigia, titulo, feed_data, suscriptores)

            if debe_enviar:
                analisis = await _analizar_noticia(titulo)
                if analisis and 'basura umana' not in analisis.lower():
                    await _enviar_notificacion_critica(http, db_vigia, suscriptores, titulo, analisis, nombre)

            db_vigia.marcar_noticia_leida(titulo, nombre)

    except Exception as e:
        logger.exception(f"❌ Error procesando feed {nombre}: {e}")


async def _procesar_noticia_hibrida(db_vigia, titulo: str, feed_data, suscriptores_categoria: list) -> bool:
    """Procesa noticia con lógica híbrida según tipo de feed."""
    feed_id, nombre, url, categoria, pais, idioma, prioridad, palabras_clave, tipo_feed = feed_data

    try:
        suscriptores_palabras = db_vigia.verificar_palabras_clave_noticia(titulo)
        todos_suscriptores = list(set(suscriptores_categoria + suscriptores_palabras))

        if not todos_suscriptores:
            return False

        if tipo_feed == 'especializado':
            return True
        elif tipo_feed == 'general':
            categoria_detectada = await _clasificar_noticia_con_ia(titulo)
            logger.info(f"🤖 IA clasificó '{titulo[:50]}...' como: {categoria_detectada}")
            return categoria_detectada == categoria
        elif tipo_feed == 'palabras_clave':
            return len(suscriptores_palabras) > 0

        return False

    except Exception as e:
        logger.exception(f"Error en procesamiento híbrido: {e}")
        return False


async def _clasificar_noticia_con_ia(titulo: str) -> str:
    """Usa IA para clasificar una noticia en categorías."""
    try:
        prompt_clasificacion = f"""
        Clasifica esta noticia en UNA de estas categorías: economia, internacional, tecnologia, sociedad, politica.
        
        Noticia: {titulo}
        
        Responde SOLO con el nombre de la categoría (en minúsculas, sin acentos):
        """

        api_key = (os.getenv("COHERE_API_KEY") or "").strip()
        if not api_key:
            return "general"

        client = cohere.Client(api_key=api_key, timeout=30)
        res = client.chat(
            model="command-a-03-2025",
            message=prompt_clasificacion,
            temperature=0.1,
        )

        categoria = getattr(res, "text", "").strip().lower()
        categorias_validas = ['economia', 'internacional', 'tecnologia', 'sociedad', 'politica']
        if categoria in categorias_validas:
            return categoria
        else:
            logger.warning(f"🤖 IA devolvió categoría inválida: {categoria}")
            return "general"

    except Exception as e:
        logger.exception(f"Error clasificando con IA: {e}")
        return "general"


async def _obtener_entradas_feed(url: str, nombre_feed: str) -> list:
    """Obtiene entradas de un feed RSS usando aiohttp (no bloqueante)."""
    import feedparser
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        logger.info(f"📡 Obteniendo feed desde {url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                content = await resp.read()

        feed = feedparser.parse(content)
        entries = [(getattr(e, 'title', None) or getattr(e, 'summary', '')) for e in feed.entries[:5]]
        logger.info(f"📰 {len(entries)} noticias de {nombre_feed}")
        return entries

    except Exception as e1:
        logger.warning(f"⚠️ Feedparser falló para {nombre_feed}: {e1}, intentando XML...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    content = await resp.read()

            root = ET.fromstring(content)
            items = root.findall('.//item')[:5]
            entries = [(item.find('title').text if item.find('title') is not None else '') for item in items]
            logger.info(f"📰 {len(entries)} noticias de {nombre_feed} (XML)")
            return entries
        except Exception as e:
            logger.exception(f"❌ No se pudo obtener feed {nombre_feed}: {e}")
            return []


async def _analizar_noticia(titulo: str) -> str:
    """Analiza una noticia usando Cohere."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_analizar_con_cohere, titulo),
            timeout=90
        )
    except asyncio.TimeoutError:
        logger.warning(f"⏱️ Timeout analizando: {titulo[:80]}")
        return "basura umana"
    except Exception as e:
        logger.exception(f"⚠️ Error Cohere analizando: {e}")
        return "basura umana"


async def _enviar_notificacion_critica(http: DiscordHTTP, db_vigia, suscriptores, titulo, analisis, fuente):
    """Envía notificación crítica a suscriptores (usuarios y canales) via REST API."""
    try:
        mensaje = f"🚨 **VIGÍA**\n{analisis}\n*Fuente: {fuente}*\n*Noticia: {titulo}*"

        for suscriptor_id in suscriptores:
            try:
                if suscriptor_id.startswith("channel_"):
                    canal_id = int(suscriptor_id[8:])
                    ok = await http.send_channel_message(canal_id, mensaje)
                    if ok:
                        logger.info(f"✅ Enviada al canal {canal_id}: {titulo[:50]}")
                    else:
                        logger.warning(f"⚠️ No se pudo enviar al canal {canal_id}")
                else:
                    ok = await http.send_dm(int(suscriptor_id), mensaje)
                    if ok:
                        logger.info(f"✅ Enviada a usuario {suscriptor_id}: {titulo[:50]}")
                    else:
                        logger.warning(f"⚠️ No se pudo enviar a usuario {suscriptor_id}")
            except Exception as e_user:
                logger.warning(f"⚠️ No se pudo enviar a {suscriptor_id}: {e_user}")

        db_vigia.registrar_notificacion_enviada(titulo, analisis, "critica", fuente)

    except Exception as e:
        logger.exception(f"❌ Error enviando notificación: {e}")


async def main():
    logger.info("👀 Vigía oteando noticias...")
    http = DiscordHTTP(get_discord_token())
    await _procesar_feeds(http)


if __name__ == "__main__":
    asyncio.run(main())
