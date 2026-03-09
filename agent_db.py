import sqlite3
import datetime
import json
import os
import threading
from pathlib import Path
from agent_logging import get_logger

logger = get_logger('db')

_ACTIVE_SERVER_FILE = Path(__file__).parent / ".active_server"
DB_DIR = Path(__file__).parent / 'databases'
DB_DIR.mkdir(parents=True, exist_ok=True)


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

# --- UTILITIES FOR SERVER-SPECIFIC DATABASE MANAGEMENT ---

def get_server_db_path(server_name: str, db_name: str = None) -> Path:
    """
    Genera ruta de base de datos para un servidor específico.
    
    Args:
        server_name: Nombre del servidor (sanitizado)
        db_name: Nombre de la base de datos (opcional)
    
    Returns:
        Path: Ruta completa al archivo de base de datos
    """
    # Sanitizar nombre del servidor
    server_sanitized = server_name.lower().replace(' ', '_').replace('-', '_')
    server_sanitized = ''.join(c for c in server_sanitized if c.isalnum() or c == '_')
    
    # Directorio base
    server_dir = DB_DIR / server_sanitized
    try:
        server_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        # Si no podemos crear el directorio del servidor, usar el directorio base
        print(f"⚠️ No se puede crear directorio de BD {server_dir}: {e}")
        print(f"🗄️ Usando directorio base: {DB_DIR}")
        server_dir = DB_DIR
    
    # Usar nombre de BD si se proporciona, si no el global
    db_filename = db_name or get_personality_name()
    db_path = server_dir / f'{db_filename}.db'
    
    # Ensure proper permissions if file doesn't exist
    if not db_path.exists():
        try:
            db_path.touch(exist_ok=True)
            # Set 666 permissions (rw for all) to avoid permission issues
            os.chmod(db_path, 0o666)
        except (PermissionError, OSError):
            pass  # If we can't set permissions, continue anyway
    
    return db_path

def get_server_db_path_fallback(server_name: str, db_name: str) -> Path:
    """
    Version with fallback for Docker environments or restricted permissions.
    """
    if server_name == "default":
        active = get_active_server_name()
        if active:
            server_name = active

    # Try local path first
    local_path = get_server_db_path(server_name, db_name)
    
    try:
        # Test if we can write
        conn = sqlite3.connect(str(local_path))
        cursor = conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS __test_write (id INTEGER)')
        conn.commit()
        cursor.execute('DROP TABLE IF EXISTS __test_write')
        conn.commit()
        conn.close()
        return local_path
    except (PermissionError, OSError) as e:
        logger.warning(f"⚠️ No write access to {local_path}: {e}. Using fallback in home directory.")
        
        # Fallback in home directory
        server_sanitized = _sanitize_server_name(server_name)
        
        fallback_dir = Path.home() / '.roleagentbot' / 'databases' / server_sanitized
        fallback_dir.mkdir(parents=True, exist_ok=True)
        
        fallback_path = fallback_dir / db_name
        logger.info(f"ℹ️ DB relocated to {fallback_path}")
        
        # Ensure proper permissions for fallback database
        if not fallback_path.exists():
            try:
                fallback_path.touch(exist_ok=True)
                os.chmod(fallback_path, 0o666)
            except (PermissionError, OSError):
                pass
        
        return fallback_path

def get_server_log_path(server_name: str, log_name: str) -> Path:
    """
    Generate log path for a specific server.
    
    Args:
        server_name: Server name (sanitized)
        log_name: Log file name
    
    Returns:
        Path: Full path to the log file
    """
    if server_name == "default":
        active = get_active_server_name()
        if active:
            server_name = active

    # Sanitize server name
    server_sanitized = _sanitize_server_name(server_name)
    
    # Base directory
    base_dir = Path(__file__).parent
    server_dir = base_dir / "logs" / server_sanitized
    
    # Create directory if it doesn't exist
    server_dir.mkdir(parents=True, exist_ok=True)
    
    return server_dir / log_name

def get_personality_name():
    """Get personality name from environment variable or configuration."""
    # First try from environment variable (priority in Docker)
    env_personality = os.getenv('PERSONALITY')
    if env_personality:
        return env_personality.lower()
    
    # Then try from agent_engine
    try:
        from agent_engine import PERSONALIDAD
        return PERSONALIDAD.get("name", "agent").lower()
    except:
        return "agent"

# Path and limits configuration
BASE_DIR = Path(__file__).parent
HISTORIAL_LIMITE = 5

class AgentDatabase:
    def __init__(self, server_name: str = "default", db_path: Path = None):
        self.server_name = server_name
        if db_path is None:
            personality_name = get_personality_name()
            db_name = f"{personality_name}"
            self.db_path = get_server_db_path_fallback(server_name, db_name)
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        logger.info(f"🗄️ [DB] Initializing database at: {self.db_path}")
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
            logger.info(f"✅ [DB] Database accessible at: {self.db_path}")
            return
        except Exception as e:
            logger.warning(f"⚠️ [DB] No write access to {self.db_path}: {e}. Using fallback in home directory.")
            fallback_dir = Path.home() / '.roleagentbot' / 'databases'
            server_sanitized = self.server_name.lower().replace(' ', '_').replace('-', '_')
            server_sanitized = ''.join(c for c in server_sanitized if c.isalnum() or c == '_')
            fallback_dir = fallback_dir / server_sanitized
            try:
                fallback_dir.mkdir(parents=True, exist_ok=True)
                personality_name = get_personality_name()
                fallback_db = fallback_dir / f'{personality_name}'
                self.db_path = fallback_db
                logger.info(f"ℹ️ [DB] Database relocated to {self.db_path}")
            except Exception as e2:
                logger.error(f"❌ [DB] Could not create fallback DB directory: {e2}")

    def _init_db(self):
        """Initialize all necessary tables."""
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
                logger.info(f"✅ Database ready at {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ [DB] Error in initialization: {e}")

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
            logger.exception(f"⚠️ [DB] Error retrieving history: {e}")
            return []

    def obtener_historial_usuario_reciente(self, usuario_id, minutos=3):
        """Get history from the last N minutes for temporal context."""
        fecha_limite = (datetime.datetime.now() - datetime.timedelta(minutes=minutos)).isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT contexto, metadata FROM interacciones
                    WHERE usuario_id = ? AND fecha > ? ORDER BY fecha DESC
                ''', (str(usuario_id), fecha_limite))

                res = cursor.fetchall()
                historial = []
                for row in res:
                    meta = json.loads(row['metadata']) if row['metadata'] else {}
                    historial.append({"humano": row['contexto'], "bot": meta.get('respuesta', '')})
                return list(reversed(historial))
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error al recuperar historial reciente: {e}")
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
                logger.info(f"🧹 Cleaned interactions before {fecha_limite} and duplicate tables")
                return cursor.rowcount

    def contar_interacciones_tipo_ultimo_dia(self, tipo_interaccion, servidor_id=None):
        """Count how many interactions of `tipo_interaccion` occurred today."""
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
    
    def get_active_servers(self) -> list:
        """Get list of all active servers."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Get unique servers from interactions
                cursor.execute('''
                    SELECT DISTINCT servidor_id 
                    FROM interacciones 
                    WHERE servidor_id IS NOT NULL 
                    ORDER BY servidor_id
                ''')
                
                servers = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                # If no servers in interactions, return current server
                if not servers:
                    return [self.server_name]
                
                return servers
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error getting active servers: {e}")
            return [self.server_name]  # Fallback to current server

# Dictionary to maintain instances per server
_db_instances = {}

def get_db_instance(server_name: str = "default") -> AgentDatabase:
    """Get or create a database instance for a specific server."""
    if server_name == "default":
        active = get_active_server_name()
        if active:
            server_name = active
    if server_name not in _db_instances:
        _db_instances[server_name] = AgentDatabase(server_name)
    return _db_instances[server_name]

# Global default instance (for compatibility) - lazy initialization
db = None
_current_server_name = None

def get_global_db(server_name: str = None, use_default_for_roles: bool = False) -> AgentDatabase:
    """Get the global DB instance for the current server."""
    global db, _current_server_name
    
    # If it's a role process and no specific server, use default
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
        logger.info(f"🗄️ [DB] Global database initialized for server: {server_name}")
    
    return db

def set_current_server(server_name: str):
    """Set the current server for the global DB."""
    global _current_server_name
    _current_server_name = server_name
    persist_active_server_name(server_name)

def get_database_path(server_name: str, db_type: str) -> str:
    """
    Get database path for role-specific databases.
    
    Args:
        server_name: Server name
        db_type: Database type (banker, news_watcher, dice_game, etc.)
    
    Returns:
        str: Full path to the database file
    """
    server_sanitized = _sanitize_server_name(server_name)
    personality_name = get_personality_name()
    
    # Map database types to filenames
    db_filenames = {
        'banker': f'banker_{personality_name}',
        'news_watcher': f'watcher_{personality_name}', 
        'dice_game': f'dice_game_{personality_name}',
        'treasure_hunter': f'hunter_{personality_name}',
        'trickster': f'trickster_{personality_name}',
        'mc': f'mc_{personality_name}'
    }
    
    db_name = db_filenames.get(db_type, f'{db_type}_{personality_name}')
    return str(get_server_db_path_fallback(server_name, db_name))
