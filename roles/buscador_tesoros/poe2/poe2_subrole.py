import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import sqlite3
import threading
import os as os_module
import stat
from pathlib import Path
from datetime import datetime, timedelta
import discord
import asyncio
import json
from dotenv import load_dotenv

try:
    from agent_logging import get_logger
    logger = get_logger('poe2_subrole')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('poe2_subrole')

from agent_db import get_server_db_path_fallback
from agent_engine import get_discord_token, pensar
from agent_db import get_active_server_name
from poe2scout_client import Poe2ScoutClient, ResponseFormatError, APIError

load_dotenv()

# Configuración del subrol
SUBROLE_CONFIG = {
    "name": "poe2_subrole",
    "system_prompt_addition": "SUBROL ACTIVO - POE2 TESORO HUNTER: Buscas tesoros en Path of Exile 2. Monitorizas precios de items específicos y alertas sobre oportunidades de compra/venta."
}

MI_ID = 235796491988369408
ENTRADAS_POR_DIA = 24
UMBRAL_COMPRA = 0.15
UMBRAL_VENTA = 0.15

# --- BASE DE DATOS POE2 ---

def get_db_path(server_name: str = "default") -> Path:
    """Genera ruta de BD para el subrol POE2."""
    return get_server_db_path_fallback(server_name, "PoE2Subrole.db")

class DatabaseRolePoe2:
    """Base de datos para el subrol POE2 del Buscador de Tesoros.
    Gestiona configuración de liga, objetivos y preferencias.
    """
    
    def __init__(self, server_name: str = "default", db_path: Path = None):
        if db_path is None:
            self.db_path = get_db_path(server_name)
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_writable_db()
        self._init_db()
    
    def _ensure_writable_db(self):
        """Verifica que la BD sea accesible y force permisos correctos."""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._fix_permissions(self.db_path.parent)
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=DELETE;')
            conn.close()
            
            self._fix_permissions(self.db_path)
            
        except Exception as e:
            logger.error(f"Cannot access database at {self.db_path}: {e}")
            raise
    
    def _fix_permissions(self, path: Path):
        """Fuerza permisos de usuario/grupo actual en archivo/directorio."""
        try:
            if path.exists():
                uid = os_module.getuid()
                gid = os_module.getgid()
                
                os_module.chown(path, uid, gid)
                
                if path.is_file():
                    current_mode = path.stat().st_mode
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP
                    os_module.chmod(path, new_mode)
                elif path.is_dir():
                    current_mode = path.stat().st_mode  
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP | stat.S_IXUSR | stat.S_IXGRP
                    os_module.chmod(path, new_mode)
                    
                logger.debug(f"Fixed permissions for {path}: uid={uid}, gid={gid}")
        except Exception as e:
            logger.warning(f"Could not fix permissions for {path}: {e}")
    
    def _init_db(self):
        """Inicializa la base de datos."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=DELETE;")
                conn.commit()
                
                # Tabla de configuración
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS configuracion (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        liga_actual TEXT NOT NULL DEFAULT 'Standard',
                        activo INTEGER NOT NULL DEFAULT 0,
                        fecha_actualizacion TEXT NOT NULL
                    )
                ''')
                
                # Tabla de objetivos
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS objetivos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre_item TEXT NOT NULL UNIQUE,
                        item_id INTEGER,
                        activo INTEGER NOT NULL DEFAULT 1,
                        fecha_agregado TEXT NOT NULL
                    )
                ''')
                
                # Insertar configuración inicial si no existe
                cursor.execute('SELECT COUNT(*) FROM configuracion')
                if cursor.fetchone()[0] == 0:
                    cursor.execute('''
                        INSERT INTO configuracion (id, liga_actual, activo, fecha_actualizacion)
                        VALUES (1, 'Standard', 0, ?)
                    ''', (datetime.now().isoformat(),))
                
                conn.commit()
                logger.info(f"✅ Base de datos POE2 lista en {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error en inicialización de DB POE2: {e}")
    
    def set_liga(self, liga: str) -> bool:
        """Establece la liga actual."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE configuracion 
                        SET liga_actual = ?, fecha_actualizacion = ?
                        WHERE id = 1
                    ''', (liga, datetime.now().isoformat()))
                    conn.commit()
                    logger.info(f"✅ Liga actualizada a: {liga}")
                    return True
        except Exception as e:
            logger.exception(f"⚠️ Error actualizando liga: {e}")
            return False
    
    def get_liga(self) -> str:
        """Obtiene la liga actual."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT liga_actual FROM configuracion WHERE id = 1')
                    result = cursor.fetchone()
                    return result[0] if result else "Standard"
        except Exception as e:
            logger.exception(f"⚠️ Error obteniendo liga: {e}")
            return "Standard"
    
    def set_activo(self, activo: bool) -> bool:
        """Activa o desactiva el subrol."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE configuracion 
                        SET activo = ?, fecha_actualizacion = ?
                        WHERE id = 1
                    ''', (1 if activo else 0, datetime.now().isoformat()))
                    conn.commit()
                    estado = "activado" if activo else "desactivado"
                    logger.info(f"✅ Subrol POE2 {estado}")
                    return True
        except Exception as e:
            logger.exception(f"⚠️ Error cambiando estado del subrol: {e}")
            return False
    
    def is_activo(self) -> bool:
        """Verifica si el subrol está activo."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT activo FROM configuracion WHERE id = 1')
                    result = cursor.fetchone()
                    return bool(result[0]) if result else False
        except Exception as e:
            logger.exception(f"⚠️ Error verificando estado del subrol: {e}")
            return False
    
    def add_objetivo(self, nombre_item: str, item_id: int = None) -> bool:
        """Añade un item a la lista de objetivos."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO objetivos (nombre_item, item_id, activo, fecha_agregado)
                        VALUES (?, ?, 1, ?)
                    ''', (nombre_item.strip(), item_id, datetime.now().isoformat()))
                    conn.commit()
                    logger.info(f"✅ Objetivo añadido: {nombre_item}")
                    return True
        except Exception as e:
            logger.exception(f"⚠️ Error añadiendo objetivo {nombre_item}: {e}")
            return False
    
    def remove_objetivo(self, nombre_item: str) -> bool:
        """Elimina un item de la lista de objetivos."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM objetivos WHERE nombre_item = ?', (nombre_item.strip(),))
                    conn.commit()
                    if cursor.rowcount > 0:
                        logger.info(f"✅ Objetivo eliminado: {nombre_item}")
                        return True
                    else:
                        logger.warning(f"⚠️ Objetivo no encontrado: {nombre_item}")
                        return False
        except Exception as e:
            logger.exception(f"⚠️ Error eliminando objetivo {nombre_item}: {e}")
            return False
    
    def get_objetivos(self) -> list:
        """Obtiene la lista de objetivos activos."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT nombre_item, item_id, activo, fecha_agregado
                        FROM objetivos
                        ORDER BY fecha_agregado DESC
                    ''')
                    return cursor.fetchall()
        except Exception as e:
            logger.exception(f"⚠️ Error obteniendo objetivos: {e}")
            return []
    
    def get_objetivos_activos(self) -> list:
        """Obtiene la lista de objetivos activos."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT nombre_item, item_id
                        FROM objetivos
                        WHERE activo = 1
                        ORDER BY fecha_agregado DESC
                    ''')
                    return cursor.fetchall()
        except Exception as e:
            logger.exception(f"⚠️ Error obteniendo objetivos activos: {e}")
            return []

# Diccionario para mantener instancias por servidor
_db_poe2_instances = {}

def get_poe2_db_instance(server_name: str = "default") -> DatabaseRolePoe2:
    """Obtiene o crea una instancia de base de datos POE2 para un servidor específico."""
    if server_name not in _db_poe2_instances:
        _db_poe2_instances[server_name] = DatabaseRolePoe2(server_name)
    return _db_poe2_instances[server_name]

# --- LÓGICA DEL SUBROL POE2 ---

class Poe2SubroleBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.db_poe2 = None
        self.client = Poe2ScoutClient()
    
    async def on_ready(self):
        logger.info("🔮 Iniciando subrol POE2...")
        
        try:
            user = await self.fetch_user(MI_ID)
            
            # Obtener instancia de BD para el servidor activo
            server_name = get_active_server_name() or "default"
            self.db_poe2 = get_poe2_db_instance(server_name)
            
            # Verificar si el subrol está activo
            if not self.db_poe2.is_activo():
                logger.info("💤 Subrol POE2 inactivo, finalizando...")
                await self.close()
                return
            
            # Obtener configuración actual
            liga_actual = self.db_poe2.get_liga()
            objetivos = self.db_poe2.get_objetivos_activos()
            
            if not objetivos:
                logger.info("📝 No hay objetivos configurados para POE2")
                await user.send("⚠️ **POE2**: No tienes items objetivos configurados. Usa `!poe2add \"nombre item\"` para añadirlos.")
                await self.close()
                return
            
            logger.info(f"🎯 POE2 activo en liga '{liga_actual}' con {len(objetivos)} objetivos")
            
            # Procesar cada objetivo
            for nombre_item, item_id in objetivos:
                try:
                    await self._procesar_item(nombre_item, item_id, liga_actual, user)
                except Exception as e:
                    logger.exception(f"Error procesando item {nombre_item}: {e}")
                    continue
            
            logger.info("✅ Proceso POE2 completado")
            
        except Exception as e:
            logger.exception(f"Error en on_ready de POE2: {e}")
        
        await self.close()
    
    async def _procesar_item(self, nombre_item: str, item_id: int, liga: str, user):
        """Procesa un item específico: obtiene datos y analiza oportunidades."""
        try:
            logger.info(f"🔍 Analizando {nombre_item} en liga {liga}")
            
            # Obtener historial de precios
            entries = self.client.get_item_history(nombre_item, league=liga)
            
            if not entries:
                logger.warning(f"No hay datos para {nombre_item}")
                return
            
            # Obtener precio actual
            precio_actual = entries[0].price if entries else None
            if not precio_actual:
                logger.warning(f"No se pudo obtener precio actual para {nombre_item}")
                return
            
            # Analizar oportunidad
            señal = self._analizar_oportunidad(entries, precio_actual)
            
            if señal:
                logger.info(f"🚨 SEÑAL DETECTADA: {nombre_item} - {señal} a {precio_actual:.2f} Div")
                
                # Enviar notificación
                await self._enviar_notificacion(nombre_item, señal, precio_actual, user)
            else:
                logger.info(f"📊 {nombre_item}: Precio actual {precio_actual:.2f} Div - sin señal")
                
        except Exception as e:
            logger.exception(f"Error procesando {nombre_item}: {e}")
    
    def _analizar_oportunidad(self, entries: list, precio_actual: float) -> str:
        """Analiza si hay oportunidad de compra/venta basada en historial."""
        if len(entries) < 10:
            return None
        
        precios = [entry.price for entry in entries]
        precio_min = min(precios)
        precio_max = max(precios)
        
        logger.info(f"{entries[0].time if entries[0].time else 'N/A'}: Precio={precio_actual:.2f}, Mín={precio_min:.2f}, Máx={precio_max:.2f}")
        
        # Regla de compra: precio <= mínimo histórico * 1.15
        if precio_actual <= precio_min * (1 + UMBRAL_COMPRA):
            return "COMPRA"
        
        # Regla de venta: precio >= máximo histórico * 0.85
        if precio_actual >= precio_max * (1 - UMBRAL_VENTA):
            return "VENTA"
        
        return None
    
    async def _enviar_notificacion(self, nombre_item: str, señal: str, precio: float, user):
        """Envía una notificación sobre oportunidad detectada."""
        try:
            if señal == "COMPRA":
                mensaje = f"Misión POE2: Oportunidad de compra detectada. El item {nombre_item} está barato ({precio:.2f} Div). ¡Momento de comprar!"
            else:  # VENTA
                mensaje = f"Misión POE2: Oportunidad de venta detectada. El item {nombre_item} está caro ({precio:.2f} Div). ¡Momento de vender!"
            
            res = await asyncio.to_thread(pensar, mensaje)
            await user.send(f"🔮 **POE2 TESORO**: {res}")
            logger.info(f"✅ Notificación POE2 enviada para {nombre_item} - {señal}")
            
        except Exception as e:
            logger.exception(f"Error enviando notificación POE2: {e}")

# --- FUNCIÓN DE REFERENCIA DE ITEMS ---

def get_items_reference():
    """Obtiene la referencia de items disponibles usando el método getItems del scrapper."""
    try:
        client = Poe2ScoutClient()
        
        # Intentar obtener items de la API
        # Nota: Esto necesitaría implementarse en el cliente si la API lo soporta
        # Por ahora, devolvemos un diccionario con los items conocidos
        items_conocidos = {
            "ancient rib": 4379,
            "ancient collarbone": 4385,
            "ancient jawbone": 4373,
            "fracturing orb": 294,
            "igniferis": 25,
            "idol of uldurn": 24,
        }
        
        logger.info(f"📋 Referencia de items cargada: {len(items_conocidos)} items")
        return items_conocidos
        
    except Exception as e:
        logger.exception(f"Error obteniendo referencia de items: {e}")
        return {}

# --- EJECUCIÓN PRINCIPAL ---

if __name__ == "__main__":
    Poe2SubroleBot().run(get_discord_token())
