import sqlite3
import datetime
import json
import os
import threading
from pathlib import Path
from agent_logging import get_logger

logger = get_logger('db')

_ACTIVE_SERVER_FILE = Path(__file__).parent / ".active_server"


def _sanitize_server_name(server_name: str) -> str:
    server_sanitized = server_name.lower().replace(' ', '_').replace('-', '_')
    server_sanitized = ''.join(c for c in server_sanitized if c.isalnum() or c == '_')
    return server_sanitized


def get_active_server_name() -> str | None:
    env_active = os.getenv("ACTIVE_SERVER_NAME")
    if env_active:
        value = env_active.strip()
        return value or None
    try:
        if _ACTIVE_SERVER_FILE.exists():
            value = _ACTIVE_SERVER_FILE.read_text(encoding="utf-8").strip()
            return value or None
    except Exception:
        return None
    return None


def persist_active_server_name(server_name: str) -> None:
    try:
        _ACTIVE_SERVER_FILE.write_text(server_name.strip(), encoding="utf-8")
    except Exception:
        pass

# --- UTILIDADES PARA GESTIÓN DE BASES DE DATOS POR SERVIDOR ---

def get_server_db_path(server_name: str, db_name: str) -> Path:
    """
    Genera ruta de base de datos para un servidor específico.
    
    Args:
        server_name: Nombre del servidor (sanitizado)
        db_name: Nombre del archivo de base de datos
    
    Returns:
        Path: Ruta completa a la base de datos
    """
    if server_name == "default":
        active = get_active_server_name()
        if active:
            server_name = active

    # Sanitizar nombre del servidor
    server_sanitized = _sanitize_server_name(server_name)
    
    # Directorio base
    base_dir = Path(__file__).parent
    server_dir = base_dir / "databases" / server_sanitized
    
    # Crear directorio si no existe
    server_dir.mkdir(parents=True, exist_ok=True)
    
    return server_dir / db_name

def get_server_db_path_fallback(server_name: str, db_name: str) -> Path:
    """
    Versión con fallback para entornos Docker o permisos restringidos.
    """
    if server_name == "default":
        active = get_active_server_name()
        if active:
            server_name = active

    # Intentar ruta local primero
    local_path = get_server_db_path(server_name, db_name)
    
    try:
        # Probar si podemos escribir
        conn = sqlite3.connect(str(local_path))
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS __test_write (id INTEGER)')
        conn.commit()
        cursor.execute('DROP TABLE IF EXISTS __test_write')
        conn.commit()
        conn.close()
        return local_path
    except (PermissionError, OSError) as e:
        logger.warning(f"⚠️ No write access a {local_path}: {e}. Usando fallback en home directory.")
        
        # Fallback en home directory
        server_sanitized = _sanitize_server_name(server_name)
        
        fallback_dir = Path.home() / '.roleagentbot' / 'databases' / server_sanitized
        fallback_dir.mkdir(parents=True, exist_ok=True)
        
        fallback_path = fallback_dir / db_name
        logger.info(f"ℹ️ BD reubicada a {fallback_path}")
        return fallback_path

def get_server_log_path(server_name: str, log_name: str) -> Path:
    """
    Genera ruta de log para un servidor específico.
    
    Args:
        server_name: Nombre del servidor (sanitizado)
        log_name: Nombre del archivo de log
    
    Returns:
        Path: Ruta completa al archivo de log
    """
    if server_name == "default":
        active = get_active_server_name()
        if active:
            server_name = active

    # Sanitizar nombre del servidor
    server_sanitized = _sanitize_server_name(server_name)
    
    # Directorio base
    base_dir = Path(__file__).parent
    server_dir = base_dir / "logs" / server_sanitized
    
    # Crear directorio si no existe
    server_dir.mkdir(parents=True, exist_ok=True)
    
    return server_dir / log_name

def get_personality_name():
    """Obtiene nombre de la personalidad desde variable de entorno o configuración."""
    # Primero intentar desde variable de entorno (prioridad en Docker)
    env_personality = os.getenv('PERSONALITY')
    if env_personality:
        return env_personality.lower()
    
    # Sino intentar desde agent_engine
    try:
        from agent_engine import PERSONALIDAD
        return PERSONALIDAD.get("name", "agent").lower()
    except:
        return "agent"

# Configuración de rutas y límites
BASE_DIR = Path(__file__).parent
HISTORIAL_LIMITE = 5

class AgentDatabase:
    def __init__(self, server_name: str = "default", db_path: Path = None):
        self.server_name = server_name
        if db_path is None:
            personality_name = get_personality_name()
            db_name = f"{personality_name}.db"
            self.db_path = get_server_db_path_fallback(server_name, db_name)
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        logger.info(f"🗄️ [DB] Inicializando base de datos en: {self.db_path}")
        self._ensure_writable_db()
        self._init_db()

    def _ensure_writable_db(self):
        """Attempt to open and write to the configured DB. If the location is read-only,
        switch to a fallback under the user's home directory.
        """
        try:
            db_path_str = str(self.db_path)
            conn = sqlite3.connect(db_path_str)
            cursor = conn.cursor()
            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('CREATE TABLE IF NOT EXISTS __agent_test_write (id INTEGER)')
            conn.commit()
            cursor.execute('DROP TABLE IF EXISTS __agent_test_write')
            conn.commit()
            conn.close()
            logger.info(f"✅ [DB] Base de datos accesible en: {self.db_path}")
            return
        except Exception as e:
            logger.warning(f"⚠️ [DB] No write access a {self.db_path}: {e}. Usando fallback en home directory.")
            fallback_dir = Path.home() / '.roleagentbot' / 'databases'
            server_sanitized = self.server_name.lower().replace(' ', '_').replace('-', '_')
            server_sanitized = ''.join(c for c in server_sanitized if c.isalnum() or c == '_')
            fallback_dir = fallback_dir / server_sanitized
            try:
                fallback_dir.mkdir(parents=True, exist_ok=True)
                personality_name = get_personality_name()
                fallback_db = fallback_dir / f'{personality_name}.db'
                self.db_path = fallback_db
                logger.info(f"ℹ️ [DB] DB reubicada a {self.db_path}")
            except Exception as e2:
                logger.error(f"❌ [DB] No se pudo crear fallback DB directory: {e2}")

    def _init_db(self):
        """Inicializa todas las tablas necesarias."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS interacciones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id TEXT NOT NULL,
                        usuario_nombre TEXT,
                        canal_id TEXT,
                        tipo_interaccion TEXT NOT NULL,
                        contexto TEXT,
                        metadata TEXT,
                        fecha DATETIME NOT NULL,
                        servidor_id TEXT
                    )
                ''')

                cursor.execute('CREATE INDEX IF NOT EXISTS idx_uid_fecha ON interacciones (usuario_id, fecha)')
                conn.commit()
                logger.info(f"✅ Base de datos lista en {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ [DB] Error en inicialización: {e}")

    def registrar_interaccion(self, usuario_id, usuario_nombre, tipo_interaccion, contexto, canal_id=None, servidor_id=None, metadata=None):
        fecha = datetime.datetime.now().isoformat()
        meta_json = json.dumps(metadata) if metadata else None
        try:
            with self._lock:
                db_path_str = str(self.db_path)
                with sqlite3.connect(db_path_str, timeout=30) as conn:
                    cursor = conn.cursor()
                    params = (
                        str(usuario_id),
                        usuario_nombre,
                        str(canal_id) if canal_id is not None else None,
                        tipo_interaccion,
                        contexto,
                        meta_json,
                        fecha,
                        str(servidor_id) if servidor_id is not None else None,
                    )
                    cursor.execute('''
                        INSERT INTO interacciones
                        (usuario_id, usuario_nombre, canal_id, tipo_interaccion, contexto, metadata, fecha, servidor_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', params)
                    conn.commit()
                    logger.info(f"✅ Registrada interaccion: usuario_id={usuario_id}, tipo={tipo_interaccion}, canal_id={canal_id}")
                    return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error al registrar (usuario_id={usuario_id}, tipo={tipo_interaccion}): {e}")
            return False

    def obtener_historial_usuario(self, usuario_id, limite=HISTORIAL_LIMITE):
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT contexto, metadata FROM interacciones
                    WHERE usuario_id = ? ORDER BY fecha DESC LIMIT ?
                ''', (str(usuario_id), limite))

                res = cursor.fetchall()
                historial = []
                for row in res:
                    meta = json.loads(row['metadata']) if row['metadata'] else {}
                    historial.append({"humano": row['contexto'], "bot": meta.get('respuesta', '')})
                return list(reversed(historial))
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error al recuperar historial: {e}")
            return []

    def usuario_ha_pedido_tipo_recientemente(self, usuario_id, tipo_like, horas=12):
        """Evita que el agente repita peticiones al mismo usuario en poco tiempo."""
        fecha_limite = (datetime.datetime.now() - datetime.timedelta(hours=horas)).isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM interacciones
                    WHERE usuario_id = ? AND tipo_interaccion LIKE ? AND fecha > ?
                ''', (str(usuario_id), f'%{tipo_like}%', fecha_limite))
                return cursor.fetchone()[0] > 0
        except Exception:
            logger.exception("⚠️ [DB] Error comprobando interacciones recientes por tipo")
            return False

    def limpiar_interacciones_antiguas(self, dias=30):
        fecha_limite = (datetime.datetime.now() - datetime.timedelta(days=dias)).isoformat()
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM interacciones WHERE fecha < ?', (fecha_limite,))
                cursor.execute('DROP TABLE IF EXISTS peticiones_oro')
                cursor.execute('DROP TABLE IF EXISTS busquedas_anillo')
                cursor.execute('DROP TABLE IF EXISTS noticias_leidas')
                conn.commit()
                logger.info(f"🧹 Eliminadas interacciones anteriores a {fecha_limite} y tablas duplicadas")
                return cursor.rowcount

    def contar_interacciones_tipo_ultimo_dia(self, tipo_interaccion, servidor_id=None):
        """Cuenta cuántas interacciones de `tipo_interaccion` hubo hoy."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                if servidor_id is not None:
                    cursor.execute('''
                        SELECT COUNT(*) FROM interacciones
                        WHERE tipo_interaccion = ? AND servidor_id = ? AND date(fecha) = date('now','localtime')
                    ''', (tipo_interaccion, str(servidor_id)))
                else:
                    cursor.execute('''
                        SELECT COUNT(*) FROM interacciones
                        WHERE tipo_interaccion = ? AND date(fecha) = date('now','localtime')
                    ''', (tipo_interaccion,))
                return cursor.fetchone()[0]
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error contando interacciones (tipo={tipo_interaccion}): {e}")
            return 0

    def usuario_ha_interactuado_recientemente(self, usuario_id, horas=12, tipos=None):
        """Verifica si un usuario ha tenido interacciones recientemente."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                if tipos:
                    placeholders = ','.join(['?' for _ in tipos])
                    cursor.execute(f'''
                        SELECT COUNT(*) FROM interacciones
                        WHERE usuario_id = ? AND datetime(fecha) > datetime('now', '-{horas} hours')
                        AND tipo_interaccion IN ({placeholders})
                    ''', [usuario_id] + tipos)
                else:
                    cursor.execute(f'''
                        SELECT COUNT(*) FROM interacciones
                        WHERE usuario_id = ? AND datetime(fecha) > datetime('now', '-{horas} hours')
                    ''', (usuario_id,))

                count = cursor.fetchone()[0]
                conn.close()
                return count > 0
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error verificando interacciones recientes: {e}")
            return False

# Diccionario para mantener instancias por servidor
_db_instances = {}

def get_db_instance(server_name: str = "default") -> AgentDatabase:
    """Obtiene o crea una instancia de base de datos para un servidor específico."""
    if server_name == "default":
        active = get_active_server_name()
        if active:
            server_name = active
    if server_name not in _db_instances:
        _db_instances[server_name] = AgentDatabase(server_name)
    return _db_instances[server_name]

# Instancia global por defecto (para compatibilidad) - inicialización lazy
db = None
_current_server_name = None

def get_global_db(server_name: str = None, use_default_for_roles: bool = False) -> AgentDatabase:
    """Obtiene la instancia global de BD para el servidor actual."""
    global db, _current_server_name
    
    # Si es un proceso de rol y no hay servidor específico, usar default
    if server_name is None:
        active = _current_server_name or get_active_server_name()
        if active:
            server_name = active
        elif use_default_for_roles and os.getenv("ROLE_AGENT_PROCESS"):
            server_name = "default"
        else:
            server_name = "default"
    
    if db is None or _current_server_name != server_name:
        db = get_db_instance(server_name)
        _current_server_name = server_name
        logger.info(f"🗄️ [DB] Base de datos global inicializada para servidor: {server_name}")
    
    return db

def set_current_server(server_name: str):
    """Establece el servidor actual para la BD global."""
    global _current_server_name
    _current_server_name = server_name
    persist_active_server_name(server_name)
