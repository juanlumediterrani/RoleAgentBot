import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path
from agent_logging import get_logger

logger = get_logger('oro')

class DatabaseRoleOro:
    def __init__(self, db_path="role_oro.db"):
        # Intentar usar ruta local, si no funciona usar fallback en home
        db_paths = [
            Path(__file__).parent / db_path,  # Local
            Path.home() / '.roleagentbot' / 'roles' / 'oro' / db_path  # Fallback
        ]
        
        for i, db_path in enumerate(db_paths):
            try:
                self.db_path = str(db_path)
                
                # Asegurar que el directorio existe
                db_path.parent.mkdir(parents=True, exist_ok=True)
                
                self._init_db()
                
                if i == 1:  # Si usamos fallback
                    logger.info(f"ℹ️ BD oro reubicada a {self.db_path}")
                else:
                    logger.info(f"✅ BD oro local en {self.db_path}")
                return
                    
            except (PermissionError, OSError, sqlite3.OperationalError) as e:
                logger.warning(f"⚠️ Intento {i+1} fallido para BD oro en {db_path}: {e}")
                if i == len(db_paths) - 1:  # Último intento
                    logger.error("❌ No se pudo inicializar BD de oro en ninguna ubicación")
                    raise
                continue
    
    def _init_db(self):
        """Inicializa la base de datos del rol de oro."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS peticiones_oro (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    usuario_id TEXT NOT NULL,
                    usuario_nombre TEXT NOT NULL,
                    tipo TEXT NOT NULL,  -- 'ORO_DM' o 'ORO_PUBLICO'
                    mensaje TEXT NOT NULL,
                    fecha DATETIME NOT NULL,
                    canal_id TEXT,
                    servidor_id TEXT,
                    metadata TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS limite_usuario_oro (
                    usuario_id TEXT PRIMARY KEY,
                    ultima_peticion_dm DATETIME,
                    servidor_id TEXT
                )
            """)
            
            conn.commit()
    
    def registrar_peticion_oro(self, usuario_id, usuario_nombre, tipo, mensaje, canal_id, servidor_id, metadata=None):
        """Registra una petición de oro."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO peticiones_oro 
                    (usuario_id, usuario_nombre, tipo, mensaje, fecha, canal_id, servidor_id, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (usuario_id, usuario_nombre, tipo, mensaje, datetime.now(), canal_id, servidor_id, 
                      str(metadata) if metadata else None))
                conn.commit()
                logger.info(f"Petición de oro registrada: {usuario_id} - {tipo}")
                return True
        except Exception as e:
            logger.exception(f"Error registrando petición de oro: {e}")
            return False
    
    def usuario_ha_pedido_oro_recientemente(self, usuario_id, horas=12):
        """Verifica si un usuario ha pedido oro recientemente."""
        fecha_limite = datetime.now() - timedelta(hours=horas)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM peticiones_oro 
                    WHERE usuario_id = ? AND fecha > ? AND tipo = 'ORO_DM'
                """, (usuario_id, fecha_limite))
                return cursor.fetchone()[0] > 0
        except Exception:
            logger.exception("Error verificando peticiones recientes de oro")
            return False
    
    def contar_peticiones_tipo_ultimo_dia(self, tipo, servidor_id=None):
        """Cuenta peticiones de un tipo en el último día."""
        fecha_limite = datetime.now() - timedelta(days=1)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                if servidor_id:
                    cursor.execute("""
                        SELECT COUNT(*) FROM peticiones_oro 
                        WHERE tipo = ? AND servidor_id = ? AND fecha > ?
                    """, (tipo, servidor_id, fecha_limite))
                else:
                    cursor.execute("""
                        SELECT COUNT(*) FROM peticiones_oro 
                        WHERE tipo = ? AND fecha > ?
                    """, (tipo, fecha_limite))
                return cursor.fetchone()[0]
        except Exception as e:
            logger.exception(f"Error contando peticiones de oro: {e}")
            return 0
    
    def limpiar_peticiones_antiguas(self, dias=30):
        """Limpia peticiones antiguas."""
        fecha_limite = datetime.now() - timedelta(days=dias)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM peticiones_oro WHERE fecha < ?", (fecha_limite,))
                filas = cursor.rowcount
                conn.commit()
                logger.info(f"Limpiadas {filas} peticiones de oro antiguas")
                return filas
        except Exception as e:
            logger.exception(f"Error limpiando peticiones antiguas: {e}")
            return 0

# Instancia global
db_oro = DatabaseRoleOro()
