import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import asyncio
import random
from datetime import datetime
from dotenv import load_dotenv

_env_candidates = [
    (os.getenv("ROLE_AGENT_ENV_FILE") or "").strip(),
    os.path.expanduser("~/.roleagentbot.env"),
    os.path.join(os.path.dirname(__file__), ".env"),
]
for _p in _env_candidates:
    if _p and os.path.exists(_p):
        load_dotenv(_p, override=False)
        break

from agent_engine import pensar, get_discord_token, PERSONALIDAD
from agent_db import get_global_db
from agent_logging import get_logger
from discord_http import DiscordHTTP
from roles.banquero.db_role_banquero import get_banquero_db_instance

logger = get_logger('bote')

# Configuración del juego
BOTE_CONFIG = {
    "name": "bote",
    "system_prompt_addition": "MISION ACTIVA - BOTE: Eres el gestor del juego de dados 'El Bote'. Animas a los jugadores a apostar, gestionas las tiradas y pagas los premios con entusiasmo. Usas tu personalidad de orco para hacer el juego más emocionante.",
    "apuesta_defecto": 10,  # Apuesta única por defecto
    "bote_usuario_id": "bote_banca",  # ID especial para la cuenta del bote
    "bote_usuario_nombre": "La Banca del Bote"
}

# Combinaciones ganadoras (fallback)
COMBINACIONES_FALLBACK = {
    "triple_unos": {"dados": [1, 1, 1], "premio": "bote", "multiplicador": 0, "nombre": "¡¡¡TRIPLE UNOS!!!", "descripcion": "Tres unos - ¡Premio máximo!"},
    "triple": {"dados": "triple", "premio": "multiplicador", "multiplicador": 3, "nombre": "TRIPLE", "descripcion": "Tres dados iguales"},
    "escalera": {"dados": [4, 5, 6], "premio": "multiplicador", "multiplicador": 5, "nombre": "ESCALERA 4-5-6", "descripcion": "Secuencia perfecta"},
    "par": {"dados": "par", "premio": "multiplicador", "multiplicador": 1, "nombre": "PAR", "descripcion": "Dos dados iguales"},
    "nada": {"dados": "otro", "premio": 0, "multiplicador": 0, "nombre": "NADA", "descripcion": "Sin combinación"}
}

def get_bote_combinations():
    """Obtiene las combinaciones ganadoras desde la personalidad o usa fallbacks."""
    try:
        combinations = PERSONALIDAD.get("discord", {}).get("bote_combinations", {})
        # Si no hay combinaciones en la personalidad, usar los fallbacks
        if not combinations:
            return COMBINACIONES_FALLBACK
        return combinations
    except Exception:
        return COMBINACIONES_FALLBACK

def get_bote_messages():
    """Obtiene mensajes personalizados para el juego del bote."""
    try:
        messages = PERSONALIDAD.get("discord", {}).get("bote_messages", {})
        # Si no hay mensajes en la personalidad, usar los fallbacks
        if not messages:
            return {
                "invitacion": "🎲 ¡VEN A JUGAR AL BOTE! 🎲 Apuesta oro y gana premios increíbles con los dados de la suerte.",
                "ganador": "¡¡¡GANASTE!!! 🎉",
                "perdedor": "¡Suerte la próxima vez! 🎲",
                "bote_grande": "🤑 ¡EL BOTE ESTÁ ENORME! 🤑",
                "animacion": "🎲🎲🎲 ¡TIRA LOS DADOS! 🎲🎲🎲",
                "saldo_insuficiente": "No tienes suficiente saldo. Necesitas {apuesta:,} monedas para jugar. Tu saldo actual: {saldo:,} monedas",
                "bote_ganado": "🎉🎉🎉 ¡¡¡GANASTE EL BOTE COMPLETO!!! 🎉🎉🎉 {premio:,} monedas",
                "premio_multiplicador": "🎊 ¡GANASTE! {combinacion} - Premio: {premio:,} monedas",
                "sin_premio": "😅 {combinacion} - Sin premio. ¡Suerte la próxima!",
                "error_jugada": "Error procesando la jugada: {error}",
                "titulo_tirada": "🎲 **TIRADA:**",
                "titulo_combinacion": "📊 **COMBINACIÓN:**",
                "titulo_premio": "💰 **PREMIO:**",
                "titulo_bote_actual": "💎 **BOTE ACTUAL:**",
                "anuncio_bote_grande": "🤑 ¡EL BOTE ESTÁ ENORME! 🤑 El bote acumulado tiene **{saldo:,} monedas de oro**! ¡Usa `!bote jugar` para intentar ganártelo todo! 🎲"
            }
        return messages
    except Exception:
        return {
            "invitacion": "🎲 ¡VEN A JUGAR AL BOTE! 🎲 Apuesta oro y gana premios increíbles con los dados de la suerte.",
            "ganador": "¡¡¡GANASTE!!! 🎉",
            "perdedor": "¡Suerte la próxima vez! 🎲",
            "bote_grande": "🤑 ¡EL BOTE ESTÁ ENORME! 🤑",
            "animacion": "🎲🎲🎲 ¡TIRA LOS DADOS! 🎲🎲🎲",
            "saldo_insuficiente": "No tienes suficiente saldo. Necesitas {apuesta:,} monedas para jugar. Tu saldo actual: {saldo:,} monedas",
            "bote_ganado": "🎉🎉🎉 ¡¡¡GANASTE EL BOTE COMPLETO!!! 🎉🎉🎉 {premio:,} monedas",
            "premio_multiplicador": "🎊 ¡GANASTE! {combinacion} - Premio: {premio:,} monedas",
            "sin_premio": "😅 {combinacion} - Sin premio. ¡Suerte la próxima!",
            "error_jugada": "Error procesando la jugada: {error}",
            "titulo_tirada": "🎲 **TIRADA:**",
            "titulo_combinacion": "📊 **COMBINACIÓN:**",
            "titulo_premio": "💰 **PREMIO:**",
            "titulo_bote_actual": "💎 **BOTE ACTUAL:**",
            "anuncio_bote_grande": "🤑 ¡EL BOTE ESTÁ ENORME! 🤑 El bote acumulado tiene **{saldo:,} monedas de oro**! ¡Usa `!bote jugar` para intentar ganártelo todo! 🎲"
        }

async def tarea_bote(http: DiscordHTTP = None):
    """Gestiona el juego del bote en todos los servidores."""
    logger.info("🎲 Iniciando gestión del juego del Bote...")
    
    # Si no se proporciona http, crear una instancia
    if http is None:
        token = get_discord_token()
        http = DiscordHTTP(token)

    guilds = await http.get_guilds()
    for guild_data in guilds:
        await _gestionar_bote_servidor(http, guild_data)

async def _gestionar_bote_servidor(http: DiscordHTTP, guild_data: dict):
    """Gestiona el juego del bote en un servidor específico."""
    guild_id = int(guild_data["id"])
    guild_name = guild_data.get("name", f"Servidor {guild_id}")
    
    try:
        # Verificar que el banquero esté activo
        db_banquero = get_banquero_db_instance(guild_name)
        
        # Asegurar que la cuenta del bote exista
        await _asegurar_cuenta_bote(db_banquero, guild_id, guild_name)
        
        # Obtener estado actual del bote
        saldo_bote = db_banquero.obtener_saldo(BOTE_CONFIG["bote_usuario_id"], str(guild_id))
        
        # Anunciar el juego si el bote es grande
        if saldo_bote >= 50:
            await _anunciar_bote_grande(http, guild_data, saldo_bote)
        
        # Verificar si hay jugadores esperando
        await _procesar_jugadores_pendientes(http, guild_data, db_banquero)
        
    except Exception as e:
        logger.exception(f"Error gestionando bote en servidor {guild_name}: {e}")

async def _asegurar_cuenta_bote(db_banquero, guild_id: int, guild_name: str):
    """Asegura que la cuenta del bote exista y tenga saldo inicial."""
    try:
        servidor_id = str(guild_id)
        
        # Crear cuenta si no existe
        se_creo, saldo_inicial = db_banquero.crear_cartera(
            BOTE_CONFIG["bote_usuario_id"],
            BOTE_CONFIG["bote_usuario_nombre"],
            servidor_id,
            guild_name
        )
        
        # Si es nueva cuenta, darle saldo inicial
        if se_creo and saldo_inicial == 0:
            # Añadir saldo inicial para arrancar el juego
            db_banquero.actualizar_saldo(
                BOTE_CONFIG["bote_usuario_id"],
                BOTE_CONFIG["bote_usuario_nombre"],
                servidor_id,
                guild_name,
                100,  # Saldo inicial de 100 monedas
                "aporte_inicial_bote",
                "Aporte inicial para arrancar el juego del Bote"
            )
            logger.info(f"🎲 Cuenta del bote creada con 100 monedas iniciales en {guild_name}")
        
    except Exception as e:
        logger.exception(f"Error asegurando cuenta del bote: {e}")

async def _anunciar_bote_grande(http: DiscordHTTP, guild_data: dict, saldo_bote: int):
    """Anuncia que el bote está grande para atraer jugadores."""
    guild_id = int(guild_data["id"])
    
    # Limitar anuncios: máximo 2 por día por servidor
    cuenta_anuncios = await asyncio.to_thread(
        get_global_db().contar_interacciones_tipo_ultimo_dia, "BOTE_ANUNCIO", guild_id
    )
    if cuenta_anuncios >= 2:
        return
    
    # Buscar canal general
    canales = await http.get_guild_channels(guild_id)
    canal = next((c for c in canales if c.get("name") == "general" and c.get("type") == 0), None)
    if canal is None:
        canal = next((c for c in canales if c.get("type") == 0), None)
    if canal is None:
        return
    
    canal_id = int(canal["id"])
    messages = get_bote_messages()
    
    # Construir mensaje de anuncio usando la plantilla desde la personalidad
    mensaje_anuncio = messages.get("anuncio_bote_grande", "🤑 ¡EL BOTE ESTÁ ENORME! 🤑 El bote acumulado tiene **{saldo:,} monedas de oro**! ¡Usa `!bote jugar` para intentar ganártelo todo! 🎲")
    mensaje_anuncio = mensaje_anuncio.format(saldo=saldo_bote)
    
    if await http.send_channel_message(canal_id, mensaje_anuncio):
        await asyncio.to_thread(
            get_global_db().registrar_interaccion,
            str(canal_id), "CANAL_PUBLICO", "BOTE_ANUNCIO",
            "Anuncio de bote grande", canal_id, guild_id,
            metadata={"bote_amount": saldo_bote, "rol": "bote"}
        )
        logger.info(f"🎲 Anuncio de bote grande enviado en {guild_name}")

async def _procesar_jugadores_pendientes(http: DiscordHTTP, guild_data: dict, db_banquero):
    """Procesa jugadores que quieren jugar (esta función se activará con comandos)."""
    # Esta función se implementará cuando se integren los comandos de Discord
    pass

def tirar_dados() -> list[int]:
    """Simula la tirada de 3 dados de 6 caras."""
    return [random.randint(1, 6) for _ in range(3)]

def evaluar_combinacion(dados: list) -> dict:
    """Evalúa la combinación de dados y devuelve el resultado."""
    combinations = get_bote_combinations()
    
    # Verificar triple unos (premio especial)
    if dados == combinations["triple_unos"]["dados"]:
        return combinations["triple_unos"]
    
    # Verificar triple
    if dados[0] == dados[1] == dados[2]:
        return combinations["triple"]
    
    # Verificar escalera 4-5-6
    if dados == combinations["escalera"]["dados"]:
        return combinations["escalera"]
    
    # Verificar par
    if dados[0] == dados[1] or dados[1] == dados[2] or dados[0] == dados[2]:
        return combinations["par"]
    
    # Sin premio
    return combinations["nada"]

def procesar_jugada(usuario_id: str, usuario_nombre: str, 
                     servidor_id: str, servidor_nombre: str,
                     http: DiscordHTTP = None) -> dict:
    """Procesa una jugada completa del juego del bote con apuesta fija."""
    try:
        # Obtener mensajes personalizados
        messages = get_bote_messages()
        
        # Obtener instancia del banquero y del bote
        db_banquero = get_banquero_db_instance(servidor_nombre)
        from .db_bote import get_bote_db_instance
        db_bote = get_bote_db_instance(servidor_nombre)
        
        # Obtener apuesta configurada para el servidor
        config = db_bote.obtener_configuracion_servidor(servidor_id)
        apuesta = config.get("apuesta_fija", BOTE_CONFIG["apuesta_defecto"])
        
        # Verificar saldo del jugador
        saldo_jugador = db_banquero.obtener_saldo(usuario_id, servidor_id)
        if saldo_jugador < apuesta:
            mensaje_error = messages.get("saldo_insuficiente", "No tienes suficiente saldo. Necesitas {apuesta:,} monedas para jugar. Tu saldo actual: {saldo:,} monedas")
            return {"success": False, "message": mensaje_error.format(apuesta=apuesta, saldo=saldo_jugador)}
        
        # Verificar saldo del bote
        saldo_bote = db_banquero.obtener_saldo(BOTE_CONFIG["bote_usuario_id"], servidor_id)
        
        # Realizar la apuesta (restar al jugador)
        db_banquero.actualizar_saldo(
            usuario_id, usuario_nombre, servidor_id, servidor_nombre,
            -apuesta, "apuesta_bote", f"Apuesta de {apuesta} monedas en el juego del Bote"
        )
        
        # Añadir al bote
        db_banquero.actualizar_saldo(
            BOTE_CONFIG["bote_usuario_id"], BOTE_CONFIG["bote_usuario_nombre"],
            servidor_id, servidor_nombre,
            apuesta, "apuesta_recibida", f"Apuesta recibida de {usuario_nombre}: {apuesta} monedas"
        )
        
        # Tirar los dados
        dados = tirar_dados()
        resultado = evaluar_combinacion(dados)
        
        # Calcular premio
        premio = 0
        mensaje_premio = ""
        
        if resultado["premio"] == "bote":
            # ¡GANÓ EL BOTE COMPLETO!
            premio = saldo_bote + apuesta  # Todo el bote más su apuesta
            
            # Vaciar el bote
            db_banquero.actualizar_saldo(
                BOTE_CONFIG["bote_usuario_id"], BOTE_CONFIG["bote_usuario_nombre"],
                servidor_id, servidor_nombre,
                -premio, "bote_ganado", f"¡{usuario_nombre} ganó el bote completo! {premio} monedas"
            )
            
            # Pagar al jugador
            db_banquero.actualizar_saldo(
                usuario_id, usuario_nombre, servidor_id, servidor_nombre,
                premio, "bote_premio", f"¡Premio del BOTE COMPLETO! {premio} monedas"
            )
            
            mensaje_bote_ganado = messages.get("bote_ganado", "🎉🎉🎉 ¡¡¡GANASTE EL BOTE COMPLETO!!! 🎉🎉🎉 {premio:,} monedas")
            mensaje_premio = mensaje_bote_ganado.format(premio=premio)
            
        elif resultado["premio"] == "multiplicador":
            premio = apuesta * resultado["multiplicador"]
            
            # Pagar desde el bote
            db_banquero.actualizar_saldo(
                BOTE_CONFIG["bote_usuario_id"], BOTE_CONFIG["bote_usuario_nombre"],
                servidor_id, servidor_nombre,
                -premio, "premio_pagado", f"Premio pagado a {usuario_nombre}: {premio} monedas"
            )
            
            # Pagar al jugador
            db_banquero.actualizar_saldo(
                usuario_id, usuario_nombre, servidor_id, servidor_nombre,
                premio, "premio_bote", f"Premio del Bote: {premio} monedas"
            )
            
            mensaje_multiplicador = messages.get("premio_multiplicador", "🎊 ¡GANASTE! {combinacion} - Premio: {premio:,} monedas")
            mensaje_premio = mensaje_multiplicador.format(combinacion=resultado['nombre'], premio=premio)
            
        else:
            # Sin premio, la apuesta se queda en el bote (ya se añadió antes)
            mensaje_sin_premio = messages.get("sin_premio", "😅 {combinacion} - Sin premio. ¡Suerte la próxima!")
            mensaje_premio = mensaje_sin_premio.format(combinacion=resultado['nombre'])
        
        # Registrar partida en la BD del bote
        db_bote.registrar_partida(
            usuario_id, usuario_nombre, servidor_id, servidor_nombre,
            apuesta, dados, resultado["nombre"], premio, saldo_bote, 
            db_banquero.obtener_saldo(BOTE_CONFIG["bote_usuario_id"], servidor_id)
        )
        
        # Construir mensaje de resultado usando plantillas desde la personalidad
        dados_str = " ".join([f"🎲{d}" for d in dados])
        mensaje_resultado = f"{messages.get('titulo_tirada', '🎲 **TIRADA:**')} {dados_str}\n"
        mensaje_resultado += f"{messages.get('titulo_combinacion', '📊 **COMBINACIÓN:**')} {resultado['nombre']}\n"
        mensaje_resultado += f"{messages.get('titulo_premio', '💰 **PREMIO:**')} {mensaje_premio}\n"
        mensaje_resultado += f"{messages.get('titulo_bote_actual', '💎 **BOTE ACTUAL:**')} {db_banquero.obtener_saldo(BOTE_CONFIG['bote_usuario_id'], servidor_id):,} monedas"
        
        return {
            "success": True,
            "dados": dados,
            "resultado": resultado,
            "premio": premio,
            "mensaje": mensaje_resultado,
            "saldo_bote_actual": db_banquero.obtener_saldo(BOTE_CONFIG["bote_usuario_id"], servidor_id),
            "apuesta": apuesta
        }
        
    except Exception as e:
        logger.exception(f"Error procesando jugada: {e}")
        messages = get_bote_messages()
        mensaje_error = messages.get("error_jugada", "Error procesando la jugada: {error}")
        return {"success": False, "message": mensaje_error.format(error=str(e))}

async def main():
    logger.info("🎲 Juego del Bote iniciado...")
    token = get_discord_token()
    http = DiscordHTTP(token)

    await tarea_bote(http)

if __name__ == "__main__":
    asyncio.run(main())
