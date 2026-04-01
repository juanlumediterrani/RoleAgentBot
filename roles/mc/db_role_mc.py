import sqlite3
import threading
import os
import stat
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('db_role_mc')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_mc')

from agent_db import get_server_db_path_fallback, get_personality_name

def get_db_path(server_name: str = "default") -> Path:
    """Generate database path for MC role using centralized roles.db."""
    # MC role now uses the centralized roles.db system with personality-specific naming
    from agent_roles_db import get_roles_db_path
    return get_roles_db_path(server_name)


class DatabaseRoleMC:
    """Base de datos especializada para el MC (Master of Ceremonies).
    Gestiona colas de música, playlists y preferencias.
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
                self._init_playlists_table()
                self._init_queue_table()
                self._init_history_table()
                self._init_preferences_table()
                
                logger.info(f"✅ Base de datos MC lista en {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error en inicialización de DB MC: {e}")
    
    def _init_playlists_table(self):
        """Inicializa tabla de playlists."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS playlists (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre TEXT NOT NULL,
                        usuario_id TEXT NOT NULL,
                        usuario_nombre TEXT NOT NULL,
                        servidor_id TEXT NOT NULL,
                        servidor_nombre TEXT NOT NULL,
                        fecha_creacion TEXT NOT NULL,
                        fecha_actualizacion TEXT DEFAULT NULL,
                        activa INTEGER DEFAULT 1,
                        UNIQUE(usuario_id, nombre)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_playlists_usuario ON playlists (usuario_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_playlists_activa ON playlists (activa)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla playlists: {e}")
    
    def _init_queue_table(self):
        """Inicializa tabla de cola de reproducción."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        servidor_id TEXT NOT NULL,
                        canal_id TEXT NOT NULL,
                        usuario_id TEXT NOT NULL,
                        titulo TEXT NOT NULL,
                        url TEXT NOT NULL,
                        duracion TEXT DEFAULT NULL,
                        artista TEXT DEFAULT NULL,
                        posicion INTEGER NOT NULL,
                        fecha_agregado TEXT NOT NULL,
                        activo INTEGER DEFAULT 1
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_queue_servidor ON queue (servidor_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_queue_posicion ON queue (posicion)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_queue_activo ON queue (activo)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla queue: {e}")
    
    def _init_history_table(self):
        """Inicializa tabla de historial de reproducción."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        servidor_id TEXT NOT NULL,
                        canal_id TEXT NOT NULL,
                        usuario_id TEXT NOT NULL,
                        titulo TEXT NOT NULL,
                        url TEXT NOT NULL,
                        duracion TEXT DEFAULT NULL,
                        artista TEXT DEFAULT NULL,
                        fecha_reproduccion TEXT NOT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_servidor ON history (servidor_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_history_fecha ON history (fecha_reproduccion)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla history: {e}")
    
    def _init_preferences_table(self):
        """Inicializa tabla de preferencias de usuarios."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS preferences (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id TEXT NOT NULL UNIQUE,
                        volumen_default INTEGER DEFAULT 100,
                        calidad_default TEXT DEFAULT 'medium',
                        autoplay INTEGER DEFAULT 0,
                        fecha_actualizacion TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_preferences_usuario ON preferences (usuario_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla preferences: {e}")
    
    def crear_playlist(self, nombre: str, usuario_id: str, usuario_nombre: str, 
                      servidor_id: str, servidor_nombre: str) -> bool:
        """Crea una nueva playlist."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR IGNORE INTO playlists 
                        (nombre, usuario_id, usuario_nombre, servidor_id, servidor_nombre, fecha_creacion)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (nombre, usuario_id, usuario_nombre, servidor_id, servidor_nombre, 
                          datetime.now().isoformat()))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error creando playlist: {e}")
            return False
    
    def obtener_playlists_usuario(self, usuario_id: str) -> list:
        """Obtiene todas las playlists de un usuario."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, nombre, fecha_creacion, fecha_actualizacion
                    FROM playlists 
                    WHERE usuario_id = ? AND activa = 1
                    ORDER BY fecha_creacion DESC
                ''', (usuario_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo playlists de usuario: {e}")
            return []
    
    def agregar_cancion_queue(self, servidor_id: str, canal_id: str, usuario_id: str,
                             titulo: str, url: str, duracion: str = None, artista: str = None, 
                             posicion: int = None) -> bool:
        """Agrega una canción a la cola de reproducción.
        
        Args:
            posicion: Si es None, se agrega al final. Si es 0, al principio.
        """
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    if posicion is None or posicion == -1:
                        # Agregar al final (comportamiento actual)
                        cursor.execute('''
                            SELECT MAX(posicion) FROM queue 
                            WHERE servidor_id = ? AND canal_id = ? AND activo = 1
                        ''', (servidor_id, canal_id))
                        max_pos = cursor.fetchone()[0] or 0
                        nueva_posicion = max_pos + 1
                    elif posicion == 0:
                        # Agregar al principio
                        cursor.execute('''
                            UPDATE queue SET posicion = posicion + 1
                            WHERE servidor_id = ? AND canal_id = ? AND activo = 1
                        ''', (servidor_id, canal_id))
                        nueva_posicion = 1
                    else:
                        # Posición específica
                        cursor.execute('''
                            UPDATE queue SET posicion = posicion + 1
                            WHERE servidor_id = ? AND canal_id = ? AND activo = 1 
                            AND posicion >= ?
                        ''', (servidor_id, canal_id, posicion))
                        nueva_posicion = posicion
                    
                    cursor.execute('''
                        INSERT INTO queue 
                        (servidor_id, canal_id, usuario_id, titulo, url, duracion, artista, posicion, fecha_agregado)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (servidor_id, canal_id, usuario_id, titulo, url, duracion, artista, 
                          nueva_posicion, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error agregando canción a queue: {e}")
            return False
    
    def obtener_queue(self, servidor_id: str, canal_id: str) -> list:
        """Obtiene la cola de reproducción actual."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT posicion, titulo, url, duracion, artista, usuario_id, fecha_agregado
                    FROM queue 
                    WHERE servidor_id = ? AND canal_id = ? AND activo = 1
                    ORDER BY posicion ASC
                ''', (servidor_id, canal_id))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo queue: {e}")
            return []
    
    def remover_cancion_queue(self, servidor_id: str, canal_id: str, posicion: int) -> bool:
        """Remueve una canción específica de la cola."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Marcar como inactiva la canción
                    cursor.execute('''
                        UPDATE queue SET activo = 0 
                        WHERE servidor_id = ? AND canal_id = ? AND posicion = ?
                    ''', (servidor_id, canal_id, posicion))
                    
                    # Reordenar las posiciones restantes
                    cursor.execute('''
                        UPDATE queue SET posicion = posicion - 1 
                        WHERE servidor_id = ? AND canal_id = ? AND posicion > ? AND activo = 1
                    ''', (servidor_id, canal_id, posicion))
                    
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error removiendo canción de queue: {e}")
            return False
    
    def limpiar_queue(self, servidor_id: str, canal_id: str) -> bool:
        """Limpia toda la cola de reproducción."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE queue SET activo = 0 
                        WHERE servidor_id = ? AND canal_id = ?
                    ''', (servidor_id, canal_id))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error limpiando queue: {e}")
            return False
    
    def registrar_historial(self, servidor_id: str, canal_id: str, usuario_id: str,
                          titulo: str, url: str, duracion: str = None, artista: str = None) -> bool:
        """Registra una canción en el historial de reproducción."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO history 
                        (servidor_id, canal_id, usuario_id, titulo, url, duracion, artista, fecha_reproduccion)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (servidor_id, canal_id, usuario_id, titulo, url, duracion, artista,
                          datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error registrando historial: {e}")
            return False
    
    def obtener_historial(self, servidor_id: str, canal_id: str, limite: int = 10) -> list:
        """Obtiene el historial de reproducción reciente."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT titulo, url, duracion, artista, usuario_id, fecha_reproduccion
                    FROM history 
                    WHERE servidor_id = ? AND canal_id = ?
                    ORDER BY fecha_reproduccion DESC
                    LIMIT ?
                ''', (servidor_id, canal_id, limite))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo historial: {e}")
            return []
    
    def obtener_estadisticas(self, servidor_id: str = None) -> dict:
        """Obtiene estadísticas básicas del MC."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Estadísticas generales
                cursor.execute('SELECT COUNT(*) FROM playlists WHERE activa = 1')
                playlists_total = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM queue WHERE activo = 1')
                queue_total = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM history')
                historial_total = cursor.fetchone()[0]
                
                # Estadísticas por servidor si se especifica
                if servidor_id:
                    cursor.execute('SELECT COUNT(*) FROM queue WHERE servidor_id = ? AND activo = 1', (servidor_id,))
                    queue_servidor = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT COUNT(*) FROM history WHERE servidor_id = ?', (servidor_id,))
                    historial_servidor = cursor.fetchone()[0]
                else:
                    queue_servidor = 0
                    historial_servidor = 0
                
                return {
                    'playlists_total': playlists_total,
                    'queue_total': queue_total,
                    'historial_total': historial_total,
                    'queue_servidor': queue_servidor,
                    'historial_servidor': historial_servidor
                }
        except Exception as e:
            logger.exception(f"Error obteniendo estadísticas: {e}")
            return {}


def get_mc_db_instance(server_name: str = "default") -> DatabaseRoleMC:
    """Obtiene una instancia de la base de datos del MC."""
    return DatabaseRoleMC(server_name)
