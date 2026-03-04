import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from agent_logging import get_logger

try:
    logger = get_logger('db_role_vigia')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_vigia')

from agent_db import get_server_db_path_fallback, get_personality_name

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
                self._init_feeds_table()
                self._init_suscripciones_categorias_table()
                self._init_suscripciones_canales_table()
                self._init_suscripciones_palabras_table()
                self._insertar_feeds_por_defecto()
                
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
    
    def _init_feeds_table(self):
        """Inicializa tabla de feeds configurables."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS feeds_config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre TEXT NOT NULL UNIQUE,
                        url TEXT NOT NULL UNIQUE,
                        categoria TEXT NOT NULL,
                        pais TEXT DEFAULT NULL,
                        idioma TEXT DEFAULT 'es',
                        activo INTEGER DEFAULT 1,
                        prioridad INTEGER DEFAULT 1,
                        palabras_clave TEXT DEFAULT NULL,
                        tipo_feed TEXT DEFAULT 'especializado',
                        fecha_creacion TEXT NOT NULL,
                        fecha_actualizacion TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_categoria ON feeds_config (categoria)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_activo ON feeds_config (activo)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_prioridad ON feeds_config (prioridad)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_feeds_tipo ON feeds_config (tipo_feed)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla feeds_config: {e}")
    
    def _init_suscripciones_categorias_table(self):
        """Inicializa tabla de suscripciones por categorías (para suscripciones con IA)."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS suscripciones_categorias (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id TEXT NOT NULL,
                        categoria TEXT NOT NULL,
                        feed_id INTEGER DEFAULT NULL,
                        fecha_suscripcion TEXT NOT NULL,
                        activa INTEGER DEFAULT 1,
                        premisas_usuario TEXT DEFAULT NULL,  -- JSON con premisas personalizadas del usuario
                        UNIQUE(usuario_id, categoria, feed_id)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_categorias_usuario ON suscripciones_categorias (usuario_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_categorias_categoria ON suscripciones_categorias (categoria)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_categorias_activa ON suscripciones_categorias (activa)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla suscripciones_categorias: {e}")
    
    def _init_suscripciones_canales_table(self):
        """Inicializa tabla de suscripciones de canales."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS suscripciones_canales (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        canal_id TEXT NOT NULL UNIQUE,
                        canal_nombre TEXT NOT NULL,
                        servidor_id TEXT NOT NULL,
                        servidor_nombre TEXT NOT NULL,
                        categoria TEXT NOT NULL,
                        feed_id INTEGER DEFAULT NULL,
                        fecha_suscripcion TEXT NOT NULL,
                        activa INTEGER DEFAULT 1,
                        UNIQUE(canal_id, categoria, feed_id)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_canal_id ON suscripciones_canales (canal_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_canal_categoria ON suscripciones_canales (categoria)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_canal_feed ON suscripciones_canales (feed_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_canal_activa ON suscripciones_canales (activa)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla suscripciones_canales: {e}")
    
    def _init_suscripciones_palabras_table(self):
        """Inicializa tabla de suscripciones por palabras clave."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS suscripciones_palabras (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id TEXT NOT NULL,
                        canal_id TEXT DEFAULT NULL,
                        palabras_clave TEXT NOT NULL,
                        categoria TEXT DEFAULT NULL,
                        feed_id INTEGER DEFAULT NULL,
                        fecha_suscripcion TEXT NOT NULL,
                        activa INTEGER DEFAULT 1,
                        UNIQUE(usuario_id, canal_id, palabras_clave, categoria, feed_id)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_palabras_usuario ON suscripciones_palabras (usuario_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_palabras_canal ON suscripciones_palabras (canal_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_palabras_activa ON suscripciones_palabras (activa)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_palabras_categoria ON suscripciones_palabras (categoria)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_suscripciones_palabras_feed ON suscripciones_palabras (feed_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla suscripciones_palabras: {e}")
    
    def _insertar_feeds_por_defecto(self):
        """Inserta feeds por defecto si no existen."""
        try:
            feeds_por_defecto = [
                {
                    'nombre': 'CNBC Noticias',
                    'url': 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362',
                    'categoria': 'economia',
                    'pais': 'US',
                    'idioma': 'en',
                    'palabras_clave': 'market,stock,economy,business,finance',
                    'tipo_feed': 'especializado'
                },
                {
                    'nombre': 'El País Internacional',
                    'url': 'https://elpais.com/internacional/rss/portada.xml',
                    'categoria': 'internacional',
                    'pais': 'ES',
                    'idioma': 'es',
                    'palabras_clave': 'guerra,conflicto,diplomacia,crisis',
                    'tipo_feed': 'especializado'
                },
                {
                    'nombre': 'Reuters World',
                    'url': 'https://www.reuters.com/rssFeed/worldNews',
                    'categoria': 'internacional',
                    'pais': 'US',
                    'idioma': 'en',
                    'palabras_clave': 'war,conflict,crisis,government,politics',
                    'tipo_feed': 'general'
                },
                {
                    'nombre': 'BBC Technology',
                    'url': 'https://feeds.bbci.co.uk/news/technology/rss.xml',
                    'categoria': 'tecnologia',
                    'pais': 'UK',
                    'idioma': 'en',
                    'palabras_clave': 'ai,technology,cybersecurity,innovation',
                    'tipo_feed': 'especializado'
                },
                {
                    'nombre': 'CNN World',
                    'url': 'http://rss.cnn.com/rss/edition_world.rss',
                    'categoria': 'general',
                    'pais': 'US',
                    'idioma': 'en',
                    'palabras_clave': 'world,news,breaking,global',
                    'tipo_feed': 'general'
                },
                {
                    'nombre': 'Crypto News Feed',
                    'url': 'https://cointelegraph.com/rss',
                    'categoria': 'cripto',
                    'pais': 'US',
                    'idioma': 'en',
                    'palabras_clave': 'bitcoin,cryptocurrency,blockchain,ethereum',
                    'tipo_feed': 'palabras_clave'
                }
            ]
            
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                for feed in feeds_por_defecto:
                    cursor.execute('''
                        INSERT OR IGNORE INTO feeds_config 
                        (nombre, url, categoria, pais, idioma, palabras_clave, tipo_feed, fecha_creacion)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        feed['nombre'], feed['url'], feed['categoria'], 
                        feed['pais'], feed['idioma'], feed['palabras_clave'],
                        feed['tipo_feed'], datetime.now().isoformat()
                    ))
                conn.commit()
                logger.info("✅ Feeds por defecto insertados")
        except Exception as e:
            logger.exception(f"❌ Error insertando feeds por defecto: {e}")
    
    def agregar_feed(self, nombre: str, url: str, categoria: str, pais: str = None, 
                   idioma: str = 'es', palabras_clave: str = None, tipo_feed: str = 'especializado') -> bool:
        """Agrega un nuevo feed configurado."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO feeds_config 
                        (nombre, url, categoria, pais, idioma, palabras_clave, tipo_feed,
                         fecha_creacion, fecha_actualizacion)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (nombre, url, categoria, pais, idioma, palabras_clave, tipo_feed,
                         datetime.now().isoformat(), datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error agregando feed: {e}")
            return False
    
    def obtener_feeds_activos(self, categoria: str = None) -> list:
        """Obtiene feeds activos, opcionalmente filtrados por categoría."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                if categoria:
                    cursor.execute('''
                        SELECT id, nombre, url, categoria, pais, idioma, prioridad, palabras_clave, tipo_feed
                        FROM feeds_config 
                        WHERE activo = 1 AND categoria = ?
                        ORDER BY prioridad DESC, nombre
                    ''', (categoria,))
                else:
                    cursor.execute('''
                        SELECT id, nombre, url, categoria, pais, idioma, prioridad, palabras_clave, tipo_feed
                        FROM feeds_config 
                        WHERE activo = 1
                        ORDER BY prioridad DESC, nombre
                    ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo feeds activos: {e}")
            return []
    
    def obtener_feed_por_id(self, feed_id: int) -> list:
        """Obtiene un feed específico por su ID."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, nombre, url, categoria, pais, idioma, prioridad, palabras_clave, tipo_feed
                    FROM feeds_config 
                    WHERE id = ? AND activo = 1
                ''', (feed_id,))
                result = cursor.fetchone()
                return result if result else None
        except Exception as e:
            logger.exception(f"Error obteniendo feed por ID: {e}")
            return None
    
    def obtener_categorias_disponibles(self) -> list:
        """Obtiene categorías disponibles con feeds activos."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT categoria, COUNT(*) as count
                    FROM feeds_config 
                    WHERE activo = 1
                    GROUP BY categoria
                    ORDER BY categoria
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo categorías: {e}")
            return []
    
    def suscribir_usuario_categoria(self, usuario_id: str, categoria: str, feed_id: int = None) -> bool:
        """Suscribe usuario a una categoría o feed específico."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO suscripciones_categorias 
                        (usuario_id, categoria, feed_id, fecha_suscripcion, activa)
                        VALUES (?, ?, ?, ?, 1)
                    ''', (usuario_id, categoria, feed_id, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error suscribiendo usuario a categoría: {e}")
            return False
    
    def suscribir_usuario_categoria_ia(self, usuario_id: str, categoria: str, feed_id: int = None, premisas: str = None) -> bool:
        """Suscribe usuario a una categoría con análisis IA."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO suscripciones_categorias 
                        (usuario_id, categoria, feed_id, fecha_suscripcion, activa, premisas_usuario)
                        VALUES (?, ?, ?, ?, 1, ?)
                    ''', (usuario_id, categoria, feed_id, datetime.now().isoformat(), premisas))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error suscribiendo usuario a categoría con IA: {e}")
            return False
    
    def cancelar_suscripcion_categoria(self, usuario_id: str, categoria: str, feed_id: int = None) -> bool:
        """Cancela suscripción de usuario a categoría/feed."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    if feed_id:
                        cursor.execute('''
                            UPDATE suscripciones_categorias SET activa = 0 
                            WHERE usuario_id = ? AND categoria = ? AND feed_id = ?
                        ''', (usuario_id, categoria, feed_id))
                    else:
                        cursor.execute('''
                            UPDATE suscripciones_categorias SET activa = 0 
                            WHERE usuario_id = ? AND categoria = ? AND feed_id IS NULL
                        ''', (usuario_id, categoria))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error cancelando suscripción: {e}")
            return False
    
    def obtener_suscripciones_usuario(self, usuario_id: str) -> list:
        """Obtiene suscripciones activas de un usuario."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT categoria, feed_id, fecha_suscripcion
                    FROM suscripciones_categorias 
                    WHERE usuario_id = ? AND activa = 1
                ''', (usuario_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo suscripciones de usuario: {e}")
            return []
    
    def obtener_suscriptores_por_categoria(self, categoria: str, feed_id: int = None) -> list:
        """Obtiene usuarios suscritos a una categoría o feed específico."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                if feed_id:
                    cursor.execute('''
                        SELECT DISTINCT sc.usuario_id
                        FROM suscripciones_categorias sc
                        WHERE sc.categoria = ? AND sc.feed_id = ? AND sc.activa = 1
                        UNION
                        SELECT DISTINCT sv.usuario_id
                        FROM suscripciones_vigia sv
                        WHERE sv.activa = 1
                    ''', (categoria, feed_id))
                else:
                    cursor.execute('''
                        SELECT DISTINCT sc.usuario_id
                        FROM suscripciones_categorias sc
                        WHERE sc.categoria = ? AND sc.feed_id IS NULL AND sc.activa = 1
                        UNION
                        SELECT DISTINCT sv.usuario_id
                        FROM suscripciones_vigia sv
                        WHERE sv.activa = 1
                    ''', (categoria,))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.exception(f"Error obteniendo suscriptores por categoría: {e}")
            return []
    
    def suscribir_palabras_clave(self, usuario_id: str, palabras_clave: str, canal_id: str = None, categoria: str = None, feed_id: int = None) -> bool:
        """Suscribe usuario o canal a palabras clave específicas (opcionalmente en categoría/feed)."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO suscripciones_palabras 
                        (usuario_id, canal_id, palabras_clave, categoria, feed_id, fecha_suscripcion, activa)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                    ''', (usuario_id, canal_id, palabras_clave, categoria, feed_id, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error suscribiendo palabras clave: {e}")
            return False
    
    def cancelar_suscripcion_palabras(self, usuario_id: str, palabras_clave: str, canal_id: str = None) -> bool:
        """Cancela suscripción a palabras clave."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE suscripciones_palabras SET activa = 0 
                        WHERE usuario_id = ? AND palabras_clave = ? AND canal_id = ?
                    ''', (usuario_id, palabras_clave, canal_id))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error cancelando suscripción palabras: {e}")
            return False
    
    def obtener_suscripciones_palabras(self, usuario_id: str, canal_id: str = None) -> list:
        """Obtiene suscripciones de palabras clave de un usuario o canal."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT palabras_clave, fecha_suscripcion
                    FROM suscripciones_palabras 
                    WHERE usuario_id = ? AND canal_id = ? AND activa = 1
                ''', (usuario_id, canal_id))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo suscripciones palabras: {e}")
            return []
    
    def obtener_suscriptores_palabras_clave(self) -> list:
        """Obtiene todas las suscripciones activas de palabras clave."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT usuario_id, canal_id, palabras_clave
                    FROM suscripciones_palabras 
                    WHERE activa = 1
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo suscriptores palabras clave: {e}")
            return []
    
    def verificar_palabras_clave_noticia(self, titulo: str) -> list:
        """Verifica si una noticia coincide con suscripciones de palabras clave."""
        try:
            suscriptores_palabras = self.obtener_suscriptores_palabras_clave()
            coincidencias = []
            
            titulo_lower = titulo.lower()
            
            for usuario_id, canal_id, palabras in suscriptores_palabras:
                palabras_lista = [p.strip().lower() for p in palabras.split(',')]
                
                # Verificar si alguna palabra clave está en el título
                if any(palabra in titulo_lower for palabra in palabras_lista):
                    if canal_id:
                        coincidencias.append(f"channel_{canal_id}")
                    else:
                        coincidencias.append(usuario_id)
            
            return coincidencias
        except Exception as e:
            logger.exception(f"Error verificando palabras clave: {e}")
            return []
    
    def suscribir_canal_categoria(self, canal_id: str, canal_nombre: str, servidor_id: str, 
                                 servidor_nombre: str, categoria: str, feed_id: int = None) -> bool:
        """Suscribe un canal a una categoría o feed específico."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO suscripciones_canales 
                        (canal_id, canal_nombre, servidor_id, servidor_nombre, categoria, feed_id, fecha_suscripcion, activa)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ''', (canal_id, canal_nombre, servidor_id, servidor_nombre, categoria, 
                         feed_id, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error suscribiendo canal a categoría: {e}")
            return False
    
    def cancelar_suscripcion_canal(self, canal_id: str, categoria: str, feed_id: int = None) -> bool:
        """Cancela suscripción de canal a categoría/feed."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    if feed_id:
                        cursor.execute('''
                            UPDATE suscripciones_canales SET activa = 0 
                            WHERE canal_id = ? AND categoria = ? AND feed_id = ?
                        ''', (canal_id, categoria, feed_id))
                    else:
                        cursor.execute('''
                            UPDATE suscripciones_canales SET activa = 0 
                            WHERE canal_id = ? AND categoria = ? AND feed_id IS NULL
                        ''', (canal_id, categoria))
                    conn.commit()
                    return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error cancelando suscripción de canal: {e}")
            return False
    
    def suscribir_canal_categoria_ia(self, canal_id: str, canal_nombre: str, servidor_id: str, 
                                   servidor_nombre: str, categoria: str, feed_id: int = None, premisas: str = None) -> bool:
        """Suscribe un canal a una categoría con análisis IA."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO suscripciones_categorias 
                        (usuario_id, categoria, feed_id, fecha_suscripcion, activa, premisas_usuario)
                        VALUES (?, ?, ?, ?, 1, ?)
                    ''', (f"canal_{canal_id}", categoria, feed_id, datetime.now().isoformat(), premisas))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error suscribiendo canal a categoría con IA: {e}")
            return False
    
    def obtener_suscripciones_canal(self, canal_id: str) -> list:
        """Obtiene suscripciones activas de un canal."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT categoria, feed_id, fecha_suscripcion
                    FROM suscripciones_canales 
                    WHERE canal_id = ? AND activa = 1
                ''', (canal_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo suscripciones de canal: {e}")
            return []
    
    def obtener_canales_suscritos_categoria(self, categoria: str, feed_id: int = None) -> list:
        """Obtiene canales suscritos a una categoría o feed específico."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                if feed_id:
                    cursor.execute('''
                        SELECT DISTINCT canal_id, canal_nombre, servidor_id
                        FROM suscripciones_canales
                        WHERE categoria = ? AND feed_id = ? AND activa = 1
                    ''', (categoria, feed_id))
                else:
                    cursor.execute('''
                        SELECT DISTINCT canal_id, canal_nombre, servidor_id
                        FROM suscripciones_canales
                        WHERE categoria = ? AND feed_id IS NULL AND activa = 1
                    ''', (categoria,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo canales suscritos por categoría: {e}")
            return []
    
    def obtener_suscriptores_por_categoria(self, categoria: str, feed_id: int = None) -> list:
        """Obtiene usuarios suscritos a una categoría o feed específico (incluyendo canales)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Obtener suscriptores individuales
                suscriptores_individuales = []
                if feed_id:
                    cursor.execute('''
                        SELECT DISTINCT sc.usuario_id
                        FROM suscripciones_categorias sc
                        WHERE sc.categoria = ? AND sc.feed_id = ? AND sc.activa = 1
                        UNION
                        SELECT DISTINCT sv.usuario_id
                        FROM suscripciones_vigia sv
                        WHERE sv.activa = 1
                    ''', (categoria, feed_id))
                else:
                    cursor.execute('''
                        SELECT DISTINCT sc.usuario_id
                        FROM suscripciones_categorias sc
                        WHERE sc.categoria = ? AND sc.feed_id IS NULL AND sc.activa = 1
                        UNION
                        SELECT DISTINCT sv.usuario_id
                        FROM suscripciones_vigia sv
                        WHERE sv.activa = 1
                    ''', (categoria,))
                suscriptores_individuales = [row[0] for row in cursor.fetchall()]
                
                # Obtener canales (marcados con prefijo especial para identificarlos)
                canales = []
                if feed_id:
                    cursor.execute('''
                        SELECT DISTINCT canal_id
                        FROM suscripciones_canales
                        WHERE categoria = ? AND feed_id = ? AND activa = 1
                    ''', (categoria, feed_id))
                else:
                    cursor.execute('''
                        SELECT DISTINCT canal_id
                        FROM suscripciones_canales
                        WHERE categoria = ? AND feed_id IS NULL AND activa = 1
                    ''', (categoria,))
                canales = [f"channel_{row[0]}" for row in cursor.fetchall()]
                
                return suscriptores_individuales + canales
        except Exception as e:
            logger.exception(f"Error obteniendo suscriptores por categoría: {e}")
            return []
    
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
    
    def obtener_todas_suscripciones_categorias_activas(self) -> list:
        """Obtiene todas las suscripciones activas con IA (con premisas)."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT usuario_id, categoria, feed_id, fecha_suscripcion
                    FROM suscripciones_categorias 
                    WHERE activa = 1 AND premisas_usuario IS NOT NULL AND premisas_usuario != ''
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo todas las suscripciones de categorías: {e}")
            return []
    
    def obtener_todas_suscripciones_palabras_activas(self) -> list:
        """Obtiene todas las suscripciones activas de palabras clave."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT usuario_id, canal_id, palabras_clave, categoria, feed_id
                    FROM suscripciones_palabras 
                    WHERE activa = 1
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo todas las suscripciones de palabras: {e}")
            return []
    
    # ===== GESTIÓN DE PREMISAS PERSONALIZADAS POR USUARIO =====
    
    def obtener_premisas_usuario(self, usuario_id: str) -> list:
        """Obtiene las premisas personalizadas de un usuario."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT premisas_usuario
                    FROM suscripciones_categorias 
                    WHERE usuario_id = ? AND activa = 1 AND premisas_usuario IS NOT NULL
                ''', (usuario_id,))
                result = cursor.fetchone()
                
                if result and result[0]:
                    try:
                        return json.loads(result[0])
                    except json.JSONDecodeError:
                        logger.warning(f"Error decodificando premisas del usuario {usuario_id}")
                        return []
                return []
        except Exception as e:
            logger.exception(f"Error obteniendo premisas del usuario: {e}")
            return []
    
    def actualizar_premisas_usuario(self, usuario_id: str, premisas: list) -> bool:
        """Actualiza las premisas personalizadas de un usuario (máximo 7)."""
        try:
            if len(premisas) > 7:
                logger.warning(f"Usuario {usuario_id} intentó guardar más de 7 premisas")
                return False
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    # Actualizar todas las suscripciones del usuario con las nuevas premisas
                    cursor.execute('''
                        UPDATE suscripciones_categorias 
                        SET premisas_usuario = ?
                        WHERE usuario_id = ? AND activa = 1
                    ''', (json.dumps(premisas), usuario_id))
                    conn.commit()
                    
                    logger.info(f"✅ Premisas actualizadas para usuario {usuario_id}: {len(premisas)} premisas")
                    return True
        except Exception as e:
            logger.exception(f"Error actualizando premisas del usuario: {e}")
            return False
    
    def obtener_premisas_con_contexto(self, usuario_id: str) -> tuple:
        """Obtiene las premisas del usuario con contexto (si tiene personalizadas o usa las globales)."""
        premisas_usuario = self.obtener_premisas_usuario(usuario_id)
        
        if premisas_usuario:
            return premisas_usuario, "personalizadas"
        else:
            # Usar premisas globales del premisas_manager
            try:
                import sys
                import os
                # Añadir el path del directorio vigia_noticias al sys.path
                vigia_path = os.path.dirname(os.path.abspath(__file__))
                if vigia_path not in sys.path:
                    sys.path.insert(0, vigia_path)
                
                from premisas_manager import get_premisas_manager
                from agent_db import get_active_server_name
                server_name = get_active_server_name() or "default"
                premisas_manager = get_premisas_manager(server_name)
                return premisas_manager.obtener_premisas_activas(), "globales"
            except ImportError as e:
                logger.error(f"Error importando premisas_manager: {e}")
                return [], "error"
    
    def añadir_premisa_usuario(self, usuario_id: str, nueva_premisa: str) -> tuple:
        """Añade una premisa al usuario si hay hueco (máximo 7)."""
        try:
            premisas_actuales = self.obtener_premisas_usuario(usuario_id)
            
            if len(premisas_actuales) >= 7:
                return False, "Has alcanzado el máximo de 7 premisas personalizadas"
            
            if nueva_premisa in premisas_actuales:
                return False, "Esa premisa ya existe en tu lista"
            
            premisas_actuales.append(nueva_premisa)
            
            if self.actualizar_premisas_usuario(usuario_id, premisas_actuales):
                return True, f"Premisa añadida: \"{nueva_premisa}\" ({len(premisas_actuales)}/7)"
            else:
                return False, "Error al guardar la premisa"
                
        except Exception as e:
            logger.exception(f"Error añadiendo premisa del usuario: {e}")
            return False, "Error al añadir la premisa"
    
    def modificar_premisa_usuario(self, usuario_id: str, indice: int, nueva_premisa: str) -> tuple:
        """Modifica una premisa específica por su índice (1-based)."""
        try:
            premisas_actuales = self.obtener_premisas_usuario(usuario_id)
            
            if not premisas_actuales:
                return False, "No tienes premisas personalizadas. Usa !vigia premisas add para crearlas."
            
            if indice < 1 or indice > len(premisas_actuales):
                return False, f"Índice inválido. Debe estar entre 1 y {len(premisas_actuales)}"
            
            # Modificar la premisa
            premisa_anterior = premisas_actuales[indice - 1]
            premisas_actuales[indice - 1] = nueva_premisa
            
            if self.actualizar_premisas_usuario(usuario_id, premisas_actuales):
                return True, f"Premisa #{indice} actualizada: \"{premisa_anterior}\" → \"{nueva_premisa}\""
            else:
                return False, "Error al modificar la premisa"
                
        except Exception as e:
            logger.exception(f"Error modificando premisa del usuario: {e}")
            return False, "Error al modificar la premisa"
    
    # ===== MÉTODOS PARA PREMISAS DE CANALES =====
    
    def obtener_premisas_canal(self, canal_id: str) -> list:
        """Obtiene las premisas personalizadas de un canal."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT DISTINCT premisas_canal
                    FROM suscripciones_canales 
                    WHERE canal_id = ? AND activa = 1 AND premisas_canal IS NOT NULL
                ''', (canal_id,))
                result = cursor.fetchone()
                
                if result and result[0]:
                    try:
                        return json.loads(result[0])
                    except json.JSONDecodeError:
                        logger.warning(f"Error decodificando premisas del canal {canal_id}")
                        return []
                return []
        except Exception as e:
            logger.exception(f"Error obteniendo premisas del canal: {e}")
            return []
    
    def actualizar_premisas_canal(self, canal_id: str, premisas: list) -> bool:
        """Actualiza las premisas personalizadas de un canal (máximo 7)."""
        try:
            if len(premisas) > 7:
                logger.warning(f"Canal {canal_id} intentó guardar más de 7 premisas")
                return False
            
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    # Actualizar todas las suscripciones del canal con las nuevas premisas
                    cursor.execute('''
                        UPDATE suscripciones_canales 
                        SET premisas_canal = ?
                        WHERE canal_id = ? AND activa = 1
                    ''', (json.dumps(premisas), canal_id))
                    conn.commit()
                    
                    logger.info(f"✅ Premisas actualizadas para canal {canal_id}: {len(premisas)} premisas")
                    return True
        except Exception as e:
            logger.exception(f"Error actualizando premisas del canal: {e}")
            return False
    
    def añadir_premisa_canal(self, canal_id: str, nueva_premisa: str) -> tuple:
        """Añade una premisa al canal si hay hueco (máximo 7)."""
        try:
            premisas_actuales = self.obtener_premisas_canal(canal_id)
            
            if len(premisas_actuales) >= 7:
                return False, "El canal ha alcanzado el máximo de 7 premisas personalizadas"
            
            if nueva_premisa in premisas_actuales:
                return False, "Esa premisa ya existe en la lista del canal"
            
            premisas_actuales.append(nueva_premisa)
            
            if self.actualizar_premisas_canal(canal_id, premisas_actuales):
                return True, f"Premisa de canal añadida: \"{nueva_premisa}\" ({len(premisas_actuales)}/7)"
            else:
                return False, "Error al guardar la premisa del canal"
                
        except Exception as e:
            logger.exception(f"Error añadiendo premisa del canal: {e}")
            return False, "Error al añadir la premisa del canal"
    
    def modificar_premisa_canal(self, canal_id: str, indice: int, nueva_premisa: str) -> tuple:
        """Modifica una premisa específica del canal por su índice (1-based)."""
        try:
            premisas_actuales = self.obtener_premisas_canal(canal_id)
            
            if not premisas_actuales:
                return False, "El canal no tiene premisas personalizadas. Usa !vigiacanal premisas add para crearlas."
            
            if indice < 1 or indice > len(premisas_actuales):
                return False, f"Índice inválido. Debe estar entre 1 y {len(premisas_actuales)}"
            
            # Modificar la premisa
            premisa_anterior = premisas_actuales[indice - 1]
            premisas_actuales[indice - 1] = nueva_premisa
            
            if self.actualizar_premisas_canal(canal_id, premisas_actuales):
                return True, f"Premisa de canal #{indice} actualizada: \"{premisa_anterior}\" → \"{nueva_premisa}\""
            else:
                return False, "Error al modificar la premisa del canal"
                
        except Exception as e:
            logger.exception(f"Error modificando premisa del canal: {e}")
            return False, "Error al modificar la premisa del canal"
    
    def obtener_premisas_canal_con_contexto(self, canal_id: str) -> tuple:
        """Obtiene las premisas del canal con contexto (si tiene personalizadas o usa las globales)."""
        premisas_canal = self.obtener_premisas_canal(canal_id)
        
        if premisas_canal:
            return premisas_canal, "personalizadas"
        else:
            # Usar premisas globales del premisas_manager
            import sys
            import os
            # Añadir el path del directorio vigia_noticias al sys.path
            vigia_path = os.path.dirname(os.path.abspath(__file__))
            if vigia_path not in sys.path:
                sys.path.insert(0, vigia_path)
            
            from premisas_manager import get_premisas_manager
            from agent_db import get_active_server_name
            server_name = get_active_server_name() or "default"
            premisas_manager = get_premisas_manager(server_name)
            return premisas_manager.obtener_premisas_activas(), "globales"

    def verificar_tipo_suscripcion_usuario(self, usuario_id: str) -> str:
        """Verifica qué tipo de suscripción tiene un usuario (exclusivo).
        
        Returns:
            str: 'plana', 'palabras', 'ia', or 'ninguna'
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Verificar si tiene suscripción plana (suscripciones_categorias sin IA)
                cursor.execute('''
                    SELECT COUNT(*) FROM suscripciones_categorias 
                    WHERE usuario_id = ? AND activa = 1 AND (premisas_usuario IS NULL OR premisas_usuario = '')
                ''', (usuario_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'plana'
                
                # Verificar si tiene suscripción con palabras clave
                cursor.execute('''
                    SELECT COUNT(*) FROM suscripciones_palabras 
                    WHERE usuario_id = ? AND activa = 1
                ''', (usuario_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'palabras'
                
                # Verificar si tiene suscripción con IA (suscripciones_categorias con premisas)
                cursor.execute('''
                    SELECT COUNT(*) FROM suscripciones_categorias 
                    WHERE usuario_id = ? AND activa = 1 AND premisas_usuario IS NOT NULL AND premisas_usuario != ''
                ''', (usuario_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'ia'
                
                return 'ninguna'
                
        except Exception as e:
            logger.exception(f"Error verificando tipo de suscripción usuario: {e}")
            return 'ninguna'
    
    def verificar_tipo_suscripcion_canal(self, canal_id: str) -> str:
        """Verifica qué tipo de suscripción tiene un canal (exclusivo).
        
        Returns:
            str: 'plana', 'palabras', 'ia', or 'ninguna'
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Verificar si tiene suscripción plana
                cursor.execute('''
                    SELECT COUNT(*) FROM suscripciones_canales 
                    WHERE canal_id = ? AND activa = 1 AND (premisas_canal IS NULL OR premisas_canal = '')
                ''', (canal_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'plana'
                
                # Verificar si tiene suscripción con palabras clave
                cursor.execute('''
                    SELECT COUNT(*) FROM suscripciones_palabras 
                    WHERE canal_id = ? AND activa = 1
                ''', (canal_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'palabras'
                
                # Verificar si tiene suscripción con IA (canales con premisas)
                cursor.execute('''
                    SELECT COUNT(*) FROM suscripciones_canales 
                    WHERE canal_id = ? AND activa = 1 AND premisas_canal IS NOT NULL AND premisas_canal != ''
                ''', (canal_id,))
                
                if cursor.fetchone()[0] > 0:
                    return 'ia'
                
                return 'ninguna'
                
        except Exception as e:
            logger.exception(f"Error verificando tipo de suscripción canal: {e}")
            return 'ninguna'
    
    def cancelar_otras_suscripciones_usuario(self, usuario_id: str, tipo_a_mantener: str):
        """Cancela todas las suscripciones del usuario excepto el tipo especificado.
        
        Args:
            usuario_id: ID del usuario
            tipo_a_mantener: 'plana', 'palabras', 'ia', or 'ninguna'
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Cancelar suscripciones planas si no se deben mantener
                if tipo_a_mantener != 'plana':
                    cursor.execute('''
                        UPDATE suscripciones_categorias 
                        SET activa = 0 
                        WHERE usuario_id = ? AND activa = 1 AND (premisas_usuario IS NULL OR premisas_usuario = '')
                    ''', (usuario_id,))
                
                # Cancelar suscripciones con palabras clave si no se deben mantener
                if tipo_a_mantener != 'palabras':
                    cursor.execute('''
                        UPDATE suscripciones_palabras 
                        SET activa = 0 
                        WHERE usuario_id = ? AND activa = 1
                    ''', (usuario_id,))
                
                # Cancelar suscripciones con IA si no se deben mantener
                if tipo_a_mantener != 'ia':
                    cursor.execute('''
                        UPDATE suscripciones_categorias 
                        SET activa = 0 
                        WHERE usuario_id = ? AND activa = 1 AND premisas_usuario IS NOT NULL AND premisas_usuario != ''
                    ''', (usuario_id,))
                
                conn.commit()
                logger.info(f"✅ Canceladas suscripciones anteriores del usuario {usuario_id}")
                
        except Exception as e:
            logger.exception(f"Error cancelando otras suscripciones usuario: {e}")
    
    def cancelar_otras_suscripciones_canal(self, canal_id: str, tipo_a_mantener: str):
        """Cancela todas las suscripciones del canal excepto el tipo especificado.
        
        Args:
            canal_id: ID del canal
            tipo_a_mantener: 'plana', 'palabras', 'ia', or 'ninguna'
        """
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Cancelar suscripciones planas si no se deben mantener
                if tipo_a_mantener != 'plana':
                    cursor.execute('''
                        UPDATE suscripciones_canales 
                        SET activa = 0 
                        WHERE canal_id = ? AND activa = 1 AND (premisas_canal IS NULL OR premisas_canal = '')
                    ''', (canal_id,))
                
                # Cancelar suscripciones con palabras clave si no se deben mantener
                if tipo_a_mantener != 'palabras':
                    cursor.execute('''
                        UPDATE suscripciones_palabras 
                        SET activa = 0 
                        WHERE canal_id = ? AND activa = 1
                    ''', (canal_id,))
                
                # Cancelar suscripciones con IA si no se deben mantener
                if tipo_a_mantener != 'ia':
                    cursor.execute('''
                        UPDATE suscripciones_canales 
                        SET activa = 0 
                        WHERE canal_id = ? AND activa = 1 AND premisas_canal IS NOT NULL AND premisas_canal != ''
                    ''', (canal_id,))
                
                conn.commit()
                logger.info(f"✅ Canceladas suscripciones anteriores del canal {canal_id}")
                
        except Exception as e:
            logger.exception(f"Error cancelando otras suscripciones canal: {e}")
    
    def obtener_todas_suscripciones_activas(self):
        """Obtiene todas las suscripciones planas activas."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT usuario_id, categoria, feed_id, fecha_suscripcion
                    FROM suscripciones_categorias 
                    WHERE activa = 1 AND (premisas_usuario IS NULL OR premisas_usuario = '')
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo suscripciones activas: {e}")
            return []
    
    def obtener_palabras_usuario(self, usuario_id: str) -> str:
        """Obtiene las palabras clave configuradas de un usuario."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT palabras_clave FROM suscripciones_palabras 
                    WHERE usuario_id = ? AND activa = 1
                    ORDER BY id DESC LIMIT 1
                ''', (usuario_id,))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.exception(f"Error obteniendo palabras del usuario: {e}")
            return None
    
    def actualizar_palabras_usuario(self, usuario_id: str, palabras: str) -> bool:
        """Actualiza las palabras clave de un usuario."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE suscripciones_palabras 
                    SET palabras_clave = ?, actualizado_en = datetime('now')
                    WHERE usuario_id = ? AND activa = 1
                ''', (palabras, usuario_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error actualizando palabras del usuario: {e}")
            return False
    
    def obtener_suscripciones_palabras_usuario(self, usuario_id: str) -> list:
        """Obtiene todas las suscripciones con palabras clave de un usuario."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT categoria, feed_id, palabras_clave 
                    FROM suscripciones_palabras 
                    WHERE usuario_id = ? AND activa = 1
                    ORDER BY categoria, feed_id
                ''', (usuario_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo suscripciones con palabras: {e}")
            return []
    
    def cancelar_suscripcion_palabras_usuario(self, usuario_id: str, categoria: str) -> bool:
        """Cancela la suscripción con palabras clave de un usuario para una categoría."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE suscripciones_palabras 
                    SET activa = 0, actualizado_en = datetime('now')
                    WHERE usuario_id = ? AND categoria = ? AND activa = 1
                ''', (usuario_id, categoria))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.exception(f"Error cancelando suscripción con palabras: {e}")
            return False
    
    def obtener_suscripciones_ia_usuario(self, usuario_id: str) -> list:
        """Obtiene todas las suscripciones con IA de un usuario."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT categoria, feed_id, premisas_usuario 
                    FROM suscripciones_categorias 
                    WHERE usuario_id = ? AND activa = 1 AND premisas_usuario IS NOT NULL AND premisas_usuario != ''
                    ORDER BY categoria, feed_id
                ''', (usuario_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo suscripciones con IA: {e}")
            return []


# Diccionario para mantener instancias por servidor
_db_vigia_instances = {}

def get_vigia_db_instance(server_name: str = "default") -> DatabaseRoleVigia:
    """Obtiene o crea una instancia de base de datos del vigía para un servidor específico."""
    if server_name not in _db_vigia_instances:
        _db_vigia_instances[server_name] = DatabaseRoleVigia(server_name)
    return _db_vigia_instances[server_name]
