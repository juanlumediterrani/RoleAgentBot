import sqlite3
import threading
import os
import stat
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('db_role_vigia')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_vigia')

from db_utils import get_server_db_path_fallback, get_personality_name

def get_db_path(server_name: str = "default") -> Path:
    """Genera ruta de BD para el vigía de noticias con nombre de personalidad."""
    personality_name = get_personality_name()
    db_name = f"noticias_{personality_name}.db"
    return get_server_db_path_fallback(server_name, db_name)


class DatabaseRoleVigia:
    """Base de datos especializada para el Vigía de Noticias.
    Gestiona noticias leídas y notificaciones enviadas.
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
            # Asegurar que el directorio exista con permisos correctos
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._fix_permissions(self.db_path.parent)
            
            # Conectar y forzar permisos del archivo
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=DELETE;')
            conn.close()
            
            # Forzar permisos del archivo de BD
            self._fix_permissions(self.db_path)
            
        except Exception as e:
            logger.error(f"Cannot access database at {self.db_path}: {e}")
            raise
    
    def _fix_permissions(self, path: Path):
        """Fuerza permisos de usuario/grupo actual en archivo/directorio."""
        try:
            if path.exists():
                # Obtener uid/gid actual
                uid = os.getuid()
                gid = os.getgid()
                
                # Cambiar owner
                os.chown(path, uid, gid)
                
                # Permisos: 664 para archivos, 775 para directorios
                if path.is_file():
                    current_mode = path.stat().st_mode
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP
                    os.chmod(path, new_mode)
                elif path.is_dir():
                    current_mode = path.stat().st_mode  
                    new_mode = (current_mode & 0o777) | stat.S_IWUSR | stat.S_IWGRP | stat.S_IXUSR | stat.S_IXGRP
                    os.chmod(path, new_mode)
                    
                logger.debug(f"Fixed permissions for {path}: uid={uid}, gid={gid}")
        except Exception as e:
            logger.warning(f"Could not fix permissions for {path}: {e}")
    
    def _init_db(self):
        """Inicializa la base de datos con configuración DELETE."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=DELETE;")
                conn.commit()
                
                # Inicializar tablas
                self._init_noticias_table()
                self._init_notificaciones_table()
                self._init_suscripciones_table()
                
                logger.info(f"✅ Base de datos Vigía lista en {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error en inicialización de DB Vigía: {e}")
    
    def _init_noticias_table(self):
        """Inicializa tabla de noticias leídas."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS noticias_leidas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        titulo TEXT NOT NULL UNIQUE,
                        hash_titulo TEXT NOT NULL UNIQUE,
                        fecha_leida TEXT NOT NULL,
                        fuente TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_noticias_hash ON noticias_leidas (hash_titulo)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_noticias_fecha ON noticias_leidas (fecha_leida)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla noticias_leidas: {e}")
    
    def _init_notificaciones_table(self):
        """Inicializa tabla de notificaciones enviadas."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS notificaciones_enviadas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        titulo TEXT NOT NULL,
                        hash_titulo TEXT NOT NULL,
                        tipo_notificacion TEXT NOT NULL,
                        analisis TEXT NOT NULL,
                        fecha_envio TEXT NOT NULL,
                        fuente TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notificaciones_hash ON notificaciones_enviadas (hash_titulo)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notificaciones_fecha ON notificaciones_enviadas (fecha_envio)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notificaciones_tipo ON notificaciones_enviadas (tipo_notificacion)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla notificaciones_enviadas: {e}")
    
    def _generar_hash_titulo(self, titulo: str) -> str:
        """Genera un hash simple del título para evitar duplicados."""
        import hashlib
        return hashlib.md5(titulo.lower().strip().encode('utf-8')).hexdigest()
    
    def noticia_esta_leida(self, titulo: str) -> bool:
        """Verifica si una noticia ya fue leída."""
        try:
            hash_titulo = self._generar_hash_titulo(titulo)
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT 1 FROM noticias_leidas WHERE hash_titulo = ?', (hash_titulo,))
                    return cursor.fetchone() is not None
        except Exception as e:
            logger.exception(f"Error verificando noticia leída: {e}")
            return False
    
    def marcar_noticia_leida(self, titulo: str, fuente: str = None) -> bool:
        """Marca una noticia como leída."""
        try:
            hash_titulo = self._generar_hash_titulo(titulo)
            fecha_actual = datetime.now().isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR IGNORE INTO noticias_leidas (titulo, hash_titulo, fecha_leida, fuente)
                        VALUES (?, ?, ?, ?)
                    ''', (titulo, hash_titulo, fecha_actual, fuente))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error marcando noticia como leída: {e}")
            return False
    
    def registrar_notificacion_enviada(self, titulo: str, analisis: str, tipo_notificacion: str = "critica", fuente: str = None) -> bool:
        """Registra una notificación enviada."""
        try:
            hash_titulo = self._generar_hash_titulo(titulo)
            fecha_actual = datetime.now().isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO notificaciones_enviadas 
                        (titulo, hash_titulo, tipo_notificacion, analisis, fecha_envio, fuente)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (titulo, hash_titulo, tipo_notificacion, analisis, fecha_actual, fuente))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error registrando notificación enviada: {e}")
            return False
    
    def limpiar_noticias_antiguas(self, dias: int = 30) -> bool:
        """Limpia noticias más antiguas que N días."""
        try:
            fecha_limite = (datetime.now() - timedelta(days=dias)).isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Limpiar noticias leídas
                    cursor.execute('DELETE FROM noticias_leidas WHERE fecha_leida < ?', (fecha_limite,))
                    noticias_eliminadas = cursor.rowcount
                    
                    # Limpiar notificaciones enviadas
                    cursor.execute('DELETE FROM notificaciones_enviadas WHERE fecha_envio < ?', (fecha_limite,))
                    notificaciones_eliminadas = cursor.rowcount
                    
                    conn.commit()
                    logger.info(f"🧹 Limpieza: {noticias_eliminadas} noticias y {notificaciones_eliminadas} notificaciones antiguas")
                    return True
        except Exception as e:
            logger.exception(f"Error limpiando noticias antiguas: {e}")
            return False
    
    def obtener_estadisticas(self) -> dict:
        """Obtiene estadísticas básicas de la base de datos."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Contar noticias leídas
                cursor.execute('SELECT COUNT(*) FROM noticias_leidas')
                noticias_leidas = cursor.fetchone()[0]
                
                # Contar notificaciones enviadas
                cursor.execute('SELECT COUNT(*) FROM notificaciones_enviadas')
                notificaciones_enviadas = cursor.fetchone()[0]
                
                # Última actividad
                cursor.execute('SELECT MAX(fecha_leida) FROM noticias_leidas')
                ultima_noticia = cursor.fetchone()[0]
                
                cursor.execute('SELECT MAX(fecha_envio) FROM notificaciones_enviadas')
                ultima_notificacion = cursor.fetchone()[0]
                
                return {
                    'noticias_leidas': noticias_leidas,
                    'notificaciones_enviadas': notificaciones_enviadas,
                    'ultima_noticia': ultima_noticia,
                    'ultima_notificacion': ultima_notificacion
                }
        except Exception as e:
            logger.exception(f"Error obteniendo estadísticas: {e}")
            return {}


    def _init_suscripciones_table(self):
        """Inicializa tabla de suscripciones al vigía."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS suscripciones_vigia (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id TEXT NOT NULL UNIQUE,
                        usuario_nombre TEXT NOT NULL,
                        fecha_suscripcion TEXT NOT NULL,
                        activa INTEGER DEFAULT 1
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_usuario ON suscripciones_vigia (usuario_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_activa ON suscripciones_vigia (activa)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla suscripciones_vigia: {e}")
    
    def agregar_suscripcion(self, usuario_id: str, usuario_nombre: str) -> bool:
        """Agrega una suscripción de usuario al vigía."""
        try:
            fecha_actual = datetime.now().isoformat()
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO suscripciones_vigia 
                        (usuario_id, usuario_nombre, fecha_suscripcion, activa)
                        VALUES (?, ?, ?, 1)
                    ''', (usuario_id, usuario_nombre, fecha_actual))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error agregando suscripción: {e}")
            return False
    
    def eliminar_suscripcion(self, usuario_id: str) -> bool:
        """Elimina una suscripción de usuario del vigía."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE suscripciones_vigia SET activa = 0 
                        WHERE usuario_id = ?
                    ''', (usuario_id,))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error eliminando suscripción: {e}")
            return False
    
    def obtener_suscriptores_activos(self) -> list:
        """Obtiene lista de suscriptores activos."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT usuario_id, usuario_nombre, fecha_suscripcion 
                    FROM suscripciones_vigia 
                    WHERE activa = 1
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo suscriptores: {e}")
            return []
    
    def esta_suscrito(self, usuario_id: str) -> bool:
        """Verifica si un usuario está suscrito."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT 1 FROM suscripciones_vigia 
                    WHERE usuario_id = ? AND activa = 1
                ''', (usuario_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.exception(f"Error verificando suscripción: {e}")
            return False


# Diccionario para mantener instancias por servidor
_db_vigia_instances = {}

def get_vigia_db_instance(server_name: str = "default") -> DatabaseRoleVigia:
    """Obtiene o crea una instancia de base de datos del vigía para un servidor específico."""
    if server_name not in _db_vigia_instances:
        _db_vigia_instances[server_name] = DatabaseRoleVigia(server_name)
    return _db_vigia_instances[server_name]

# Instancia global por defecto (para compatibilidad)
db_vigia = get_vigia_db_instance("default")
