import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import discord
import requests
import asyncio
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import cohere
from agent_engine import construir_prompt
import sys
import os
sys.path.append(os.path.dirname(__file__))
from db_role_vigia import db_vigia
from agent_logging import get_logger

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

class NoticiaBot(discord.Client):
    async def on_ready(self):
        logger.info("👀 Vigía oteando noticias...")
        try:
            # Obtener suscriptores de la base de datos
            suscriptores = db_vigia.obtener_suscriptores()
            logger.info(f"✅ {len(suscriptores)} suscriptores encontrados")
            # Obtener entradas del feed (feedparser si está disponible, sino XML)
            entries = []
            try:
                import feedparser
                logger.info(f"📡 Obteniendo feed desde {RSS_URL}")
                resp = requests.get(RSS_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
                feed = feedparser.parse(resp.content)
                entries = [(getattr(e, 'title', None) or getattr(e, 'summary', '')) for e in feed.entries[:5]]
                logger.info(f"📰 Obtenidas {len(entries)} noticias del feed")
            except Exception as e1:
                # Fallback sin feedparser
                logger.warning(f"⚠️ Feedparser falló: {e1}, intentando con XML...")
                try:
                    r = requests.get(RSS_URL, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
                    root = ET.fromstring(r.content)
                    items = root.findall('.//item')[:5]
                    entries = [ (item.find('title').text if item.find('title') is not None else '') for item in items ]
                    logger.info(f"📰 Obtenidas {len(entries)} noticias del feed (XML)")
                except Exception as e:
                    logger.exception(f"❌ Vigía: no se pudo obtener feed: {e}")
                    entries = []

            # Procesar primeras entradas (filtrar duplicados usando db helpers)
            logger.info(f"🔍 Procesando {len(entries)} noticias...")
            for i, titulo in enumerate(entries, 1):
                titulo = titulo or ''
                if not titulo:
                    logger.warning(f"⚠️ Noticia {i} sin título, saltando...")
                    continue
                
                logger.info(f"📄 [{i}/{len(entries)}] Procesando: {titulo[:80]}...")

                if db_vigia.noticia_esta_leida(titulo):
                    logger.info(f"ℹ️ Vigía: noticia ya leída: {titulo}")
                    continue

                # Analizar en hilo para no bloquear
                try:
                    analisis = await asyncio.wait_for(
                        asyncio.to_thread(_analizar_con_cohere, titulo),
                        timeout=90
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"⏱️ Vigía: timeout analizando noticia (90s): {titulo[:80]}")
                    analisis = "basura umana"
                except Exception as e:
                    logger.exception(f"⚠️ Vigía: fallo Cohere analizando noticia: {e}")
                    # Si Cohere falla, marcar como no crítica y continuar
                    analisis = "basura umana"

                if analisis and 'basura umana' not in analisis.lower():
                    try:
                        # Enviar a todos los suscriptores
                        for suscriptor_id in suscriptores:
                            try:
                                user = await self.fetch_user(suscriptor_id)
                                await user.send(f"🚨 **VIGÍA**\n{analisis}\n*Fuente: {titulo}*")
                                logger.info(f"✅ Vigía: enviada noticia a {user.name}: {titulo}")
                            except Exception as e_user:
                                logger.warning(f"⚠️ Vigía: no se pudo enviar a {suscriptor_id}: {e_user}")
                        
                        # Registrar notificación enviada en la BD local
                        db_vigia.registrar_notificacion_enviada(titulo, analisis, "critica", "CNBC")
                    except Exception as e:
                        logger.exception(f"⚠️ Vigía: fallo enviando noticia: {e}")

                # Marcar siempre como leída para no repetir
                ok = db_vigia.marcar_noticia_leida(titulo, "CNBC")
                if not ok:
                    logger.warning(f"⚠️ Vigía: no se pudo marcar noticia: {titulo}")
        except Exception as e: 
            logger.exception(f"❌ Error Vigía: {e}")
        finally: await self.close()

if __name__ == "__main__":
    NoticiaBot(intents=discord.Intents.default()).run(os.getenv('DISCORD_TOKEN'))
