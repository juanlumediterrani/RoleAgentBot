import sqlite3
import threading
import os
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('limosna')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('limosna')

from agent_db import get_server_db_path_fallback, get_personality_name

class DatabaseRoleLimosna:
    def __init__(self, server_name: str = "default", db_path="role_limosna.db"):
        if isinstance(db_path, str):
            # Usar el nuevo esquema por servidor
            self.db_path = str(get_server_db_path_fallback(server_name, db_path))
        else:
            self.db_path = str(db_path)
        
        # Asegurar que el directorio existe
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
        logger.info(f"✅ BD limosna local en {self.db_path}")
    
    def _init_db(self):
        """Inicializa la base de datos del rol de limosna."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS peticiones_limosna (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id TEXT NOT NULL,
                    usuario_nombre TEXT NOT NULL,
                    tipo TEXT NOT NULL,  -- 'LIMOSNA_DM' o 'LIMOSNA_PUBLICO'
                    mensaje TEXT NOT NULL,
                    fecha DATETIME NOT NULL,
                    canal_id TEXT,
                    servidor_id TEXT,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS limite_usuario_limosna (
                    usuario_id TEXT PRIMARY KEY,
                    ultima_peticion_dm DATETIME,
                    servidor_id TEXT
                )
            """)
            
            # Tabla de suscripciones a peticiones de limosna
            conn.execute("""
                CREATE TABLE IF NOT EXISTS suscripciones_limosna (
                    usuario_id TEXT,
                    usuario_nombre TEXT,
                    servidor_id TEXT,
                    fecha_suscripcion DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (usuario_id, servidor_id)
                )
            """)
            
            conn.commit()
    
    def registrar_peticion_limosna(self, usuario_id, usuario_nombre, tipo, mensaje, canal_id, servidor_id, metadata=None):
        """Registra una petición de limosna."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO peticiones_limosna 
                    (usuario_id, usuario_nombre, tipo, mensaje, fecha, canal_id, servidor_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, usuario_nombre, tipo, mensaje, datetime.now(), canal_id, servidor_id, 
                      str(metadata) if metadata else None))
                conn.commit()
                logger.info(f"Petición de limosna registrada: {usuario_id} - {tipo}")
                return True
        except Exception as e:
            logger.exception(f"Error registrando petición de limosna: {e}")
            return False
    
    def usuario_ha_pedido_limosna_recientemente(self, usuario_id, horas=12):
        """Verifica si un usuario ha pedido limosna recientemente."""
        fecha_limite = datetime.now() - timedelta(hours=horas)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM peticiones_limosna 
                    WHERE usuario_id = ? AND fecha > ? AND tipo = 'LIMOSNA_DM'
                """, (usuario_id, fecha_limite))
                return cursor.fetchone()[0] > 0
        except Exception:
            logger.exception("Error verificando peticiones recientes de limosna")
            return False
    
    def contar_peticiones_tipo_ultimo_dia(self, tipo, servidor_id=None):
        """Cuenta peticiones de un tipo en el último día."""
        fecha_limite = datetime.now() - timedelta(days=1)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if servidor_id:
                    cursor.execute("""
                        SELECT COUNT(*) FROM peticiones_limosna 
                        WHERE tipo = ? AND servidor_id = ? AND fecha > ?
                    """, (tipo, servidor_id, fecha_limite))
                else:
                    cursor.execute("""
                        SELECT COUNT(*) FROM peticiones_limosna 
                        WHERE tipo = ? AND fecha > ?
                    """, (tipo, fecha_limite))
                return cursor.fetchone()[0]
        except Exception as e:
            logger.exception(f"Error contando peticiones de limosna: {e}")
            return 0
    
    def limpiar_peticiones_antiguas(self, dias=30):
        """Limpia peticiones antiguas."""
        fecha_limite = datetime.now() - timedelta(days=dias)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM peticiones_limosna WHERE fecha < ?", (fecha_limite,))
                filas = cursor.rowcount
                conn.commit()
                logger.info(f"Limpiadas {filas} peticiones de limosna antiguas")
                return filas
        except Exception as e:
            logger.exception(f"Error limpiando peticiones antiguas: {e}")
            return 0
    
    def agregar_suscripcion(self, usuario_id, usuario_nombre, servidor_id):
        """Agrega una suscripción para peticiones de limosna."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO suscripciones_limosna 
                    (usuario_id, usuario_nombre, servidor_id, fecha_suscripcion)
                    VALUES (?, ?, ?, ?)
                """, (usuario_id, usuario_nombre, servidor_id, datetime.now()))
                conn.commit()
                logger.info(f"Usuario {usuario_nombre} suscrito a peticiones de limosna")
                return True
        except Exception as e:
            logger.exception(f"Error agregando suscripción de limosna: {e}")
            return False
    
    def eliminar_suscripcion(self, usuario_id, servidor_id):
        """Elimina una suscripción para peticiones de limosna."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM suscripciones_limosna 
                    WHERE usuario_id = ? AND servidor_id = ?
                """, (usuario_id, servidor_id))
                conn.commit()
                eliminado = cursor.rowcount > 0
                if eliminado:
                    logger.info(f"Usuario {usuario_id} desuscrito de peticiones de limosna")
                return eliminado
        except Exception as e:
            logger.exception(f"Error eliminando suscripción de limosna: {e}")
            return False
    
    def esta_suscrito(self, usuario_id, servidor_id):
        """Verifica si un usuario está suscrito a peticiones de limosna."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM suscripciones_limosna 
                    WHERE usuario_id = ? AND servidor_id = ?
                """, (usuario_id, servidor_id))
                return cursor.fetchone()[0] > 0
        except Exception:
            logger.exception("Error verificando suscripción de limosna")
            return False


# Diccionario para mantener instancias por servidor
_db_limosna_instances = {}

def get_limosna_db_instance(server_name: str = "default") -> DatabaseRoleLimosna:
    """Obtiene o crea una instancia de base de datos de limosna para un servidor específico."""
    if server_name not in _db_limosna_instances:
        _db_limosna_instances[server_name] = DatabaseRoleLimosna(server_name)
    return _db_limosna_instances[server_name]
