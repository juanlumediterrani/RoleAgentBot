import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path
from agent_logging import get_logger

logger = get_logger('anillo')

class DatabaseRoleAnillo:
    def __init__(self, db_path="role_anillo.db"):
        # Intentar usar ruta local, si no funciona usar fallback en home
        db_paths = [
            Path(__file__).parent / db_path,  # Local
            Path.home() / '.roleagentbot' / 'roles' / 'anillo' / db_path  # Fallback
        ]
        
        for i, db_path in enumerate(db_paths):
            try:
                self.db_path = str(db_path)
                
                # Asegurar que el directorio existe
                db_path.parent.mkdir(parents=True, exist_ok=True)
                
                self._init_db()
                
                if i == 1:  # Si usamos fallback
                    logger.info(f"ℹ️ BD anillo reubicada a {self.db_path}")
                else:
                    logger.info(f"✅ BD anillo local en {self.db_path}")
                return
                    
            except (PermissionError, OSError, sqlite3.OperationalError) as e:
                logger.warning(f"⚠️ Intento {i+1} fallido para BD anillo en {db_path}: {e}")
                if i == len(db_paths) - 1:  # Último intento
                    logger.error("❌ No se pudo inicializar BD de anillo en ninguna ubicación")
                    raise
                continue
    
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

# Instancia global
db_anillo = DatabaseRoleAnillo()
