import sqlite3
import threading
import os
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('anillo')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('anillo')

from agent_db import get_server_db_path_fallback, get_personality_name

class DatabaseRoleAnillo:
    def __init__(self, server_name: str = "default", db_path="role_anillo.db"):
        if isinstance(db_path, str):
            # Usar el nuevo esquema por servidor
            self.db_path = str(get_server_db_path_fallback(server_name, db_path))
        else:
            self.db_path = str(db_path)
        
        # Asegurar que el directorio existe
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
        logger.info(f"✅ BD anillo local en {self.db_path}")
    
    def _init_db(self):
        """Inicializa la base de datos del rol del anillo."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS busquedas_anillo (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id TEXT NOT NULL,
                    usuario_nombre TEXT NOT NULL,
                    tipo TEXT NOT NULL,  -- 'ANILLO', 'ACUSACION_ANILLO', 'DETECCION_ANILLO', 'SOSPECHA_ANILLO'
                    mensaje TEXT NOT NULL,
                    fecha DATETIME NOT NULL,
                    canal_id TEXT,
                    servidor_id TEXT,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS limite_usuario_anillo (
                    usuario_id TEXT PRIMARY KEY,
                    ultima_acusacion DATETIME,
                    servidor_id TEXT
                )
            """)
            
            conn.commit()
    
    def registrar_busqueda_anillo(self, usuario_id, usuario_nombre, tipo, mensaje, canal_id, servidor_id, metadata=None):
        """Registra una búsqueda o acusación del anillo."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO busquedas_anillo 
                    (usuario_id, usuario_nombre, tipo, mensaje, fecha, canal_id, servidor_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, usuario_nombre, tipo, mensaje, datetime.now(), canal_id, servidor_id, 
                      str(metadata) if metadata else None))
                conn.commit()
                logger.info(f"Búsqueda de anillo registrada: {usuario_id} - {tipo}")
                return True
        except Exception as e:
            logger.exception(f"Error registrando búsqueda de anillo: {e}")
            return False
    
    def usuario_ha_acusado_recientemente(self, usuario_id, horas=12):
        """Verifica si un usuario ha acusado recientemente."""
        fecha_limite = datetime.now() - timedelta(hours=horas)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM busquedas_anillo 
                    WHERE usuario_id = ? AND fecha > ? AND tipo = 'ACUSACION_ANILLO'
                """, (usuario_id, fecha_limite))
                return cursor.fetchone()[0] > 0
        except Exception:
            logger.exception("Error verificando acusaciones recientes de anillo")
            return False
    
    def contar_busquedas_tipo_ultimo_dia(self, tipo, servidor_id=None):
        """Cuenta búsquedas de un tipo en el último día."""
        fecha_limite = datetime.now() - timedelta(days=1)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if servidor_id:
                    cursor.execute("""
                        SELECT COUNT(*) FROM busquedas_anillo 
                        WHERE tipo = ? AND servidor_id = ? AND fecha > ?
                    """, (tipo, servidor_id, fecha_limite))
                else:
                    cursor.execute("""
                        SELECT COUNT(*) FROM busquedas_anillo 
                        WHERE tipo = ? AND fecha > ?
                    """, (tipo, fecha_limite))
                return cursor.fetchone()[0]
        except Exception as e:
            logger.exception(f"Error contando búsquedas de anillo: {e}")
            return 0
    
    def limpiar_busquedas_antiguas(self, dias=30):
        """Limpia búsquedas antiguas."""
        fecha_limite = datetime.now() - timedelta(days=dias)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM busquedas_anillo WHERE fecha < ?", (fecha_limite,))
                filas = cursor.rowcount
                conn.commit()
                logger.info(f"Limpiadas {filas} búsquedas de anillo antiguas")
                return filas
        except Exception as e:
            logger.exception(f"Error limpiando búsquedas antiguas: {e}")
            return 0

# Diccionario para mantener instancias por servidor
_db_anillo_instances = {}

def get_anillo_db_instance(server_name: str = "default") -> DatabaseRoleAnillo:
    """Obtiene o crea una instancia de base de datos del anillo para un servidor específico."""
    if server_name not in _db_anillo_instances:
        _db_anillo_instances[server_name] = DatabaseRoleAnillo(server_name)
    return _db_anillo_instances[server_name]
