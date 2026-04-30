import sqlite3
import datetime
import json
import os
import threading
from pathlib import Path
from datetime import date
from typing import Optional
from agent_logging import get_logger

logger = get_logger('db')

# Import needed for get_user_last_server_id
try:
    from agent_engine import get_personality_name
except ImportError:
    def get_personality_name():
        return "HANS"  # fallback

DB_DIR = Path(__file__).parent / 'databases'
DB_DIR.mkdir(parents=True, exist_ok=True)


def get_server_id() -> str | None:
    """Get the current server ID from databases directory.
    
    Reads the server ID from the numeric folder name inside databases/.
    
    Returns:
        str | None: Server ID as string, or None if not found
    """
    try:
        db_dir = Path(__file__).parent / "databases"
        if db_dir.exists():
            server_dirs = [d for d in db_dir.iterdir() if d.is_dir() and d.name.isdigit()]
            if len(server_dirs) == 1:
                # Only one server directory, use it
                return server_dirs[0].name
            elif len(server_dirs) > 1:
                # Multiple servers, can't determine which one (expected for multi-server deployments)
                logger.debug(f"Multiple server directories found: {[d.name for d in server_dirs]}. Cannot determine active server.")
    except Exception as e:
        logger.warning(f"Error reading databases directory: {e}")
    
    return None

def get_all_server_ids() -> list[str]:
    """Get all server IDs that have databases."""
    try:
        db_dir = Path(__file__).parent / "databases"
        if not db_dir.exists():
            return []
        
        server_ids = []
        for server_dir in db_dir.iterdir():
            if server_dir.is_dir() and server_dir.name.isdigit():
                # Check if this server has an agent database (any personality)
                if any(server_dir.glob("agent_*.db")):
                    server_ids.append(server_dir.name)
        
        return sorted(server_ids)
    except Exception as e:
        logger.error(f"Error getting all server IDs: {e}")
        return []


def get_user_last_server_id(user_id: str) -> str | None:
    """Get the last server ID where the user had interactions."""
    try:
        import sqlite3
        from pathlib import Path
        
        # Try to find the user's last server from any available database
        db_dir = Path(__file__).parent / "databases"
        if not db_dir.exists():
            return None
            
        # Track the most recent interaction across all servers
        most_recent_server = None
        most_recent_time = None
        
        # Look through all server databases to find the most recent interaction
        for server_dir in db_dir.iterdir():
            if not server_dir.is_dir():
                continue

            server_id = server_dir.name
            # Find agent database without resolving personality name
            agent_db_matches = list(server_dir.glob("agent_*.db"))
            if not agent_db_matches:
                continue
            agent_db_path = agent_db_matches[0]
                
            try:
                # Connect to this server's database
                conn = sqlite3.connect(str(agent_db_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Look for the most recent interaction from this user
                cursor.execute('''
                    SELECT servidor_id, fecha 
                    FROM interacciones 
                    WHERE usuario_id = ? 
                    ORDER BY fecha DESC 
                    LIMIT 1
                ''', (str(user_id),))
                
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    interaction_time = row['fecha']
                    if most_recent_time is None or interaction_time > most_recent_time:
                        most_recent_time = interaction_time
                        most_recent_server = str(row['servidor_id']) if row['servidor_id'] else server_id
                        
            except Exception as e:
                logger.debug(f"Could not check server {server_id} for user {user_id}: {e}")
                continue
        
        return most_recent_server
    except Exception as e:
        logger.warning(f"Could not get user's last server: {e}")
        return None


_DM_SESSIONS_FILE = DB_DIR / "dm_sessions.json"


def _load_dm_sessions() -> dict:
    """Load DM sessions from databases/dm_sessions.json."""
    try:
        if _DM_SESSIONS_FILE.exists():
            return json.loads(_DM_SESSIONS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Could not load dm_sessions.json: {e}")
    return {}


def _save_dm_sessions(sessions: dict) -> None:
    """Save DM sessions to databases/dm_sessions.json."""
    try:
        DB_DIR.mkdir(parents=True, exist_ok=True)
        _DM_SESSIONS_FILE.write_text(json.dumps(sessions, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"Could not save dm_sessions.json: {e}")


def pin_dm_session(user_id: int, server_id: str) -> None:
    """Pin a DM conversation to a specific server. Persisted in databases/dm_sessions.json."""
    sessions = _load_dm_sessions()
    sessions[str(user_id)] = str(server_id)
    _save_dm_sessions(sessions)
    logger.debug(f"DM session pinned: user={user_id} → server={server_id}")


def get_pinned_dm_server(user_id: int) -> str | None:
    """Return the pinned server_id for a user's DM, or None if not set."""
    return _load_dm_sessions().get(str(user_id))


def clear_dm_session(user_id: int) -> None:
    """Clear the pinned DM session for a user."""
    sessions = _load_dm_sessions()
    if str(user_id) in sessions:
        del sessions[str(user_id)]
        _save_dm_sessions(sessions)
        logger.debug(f"DM session cleared for user={user_id}")


def get_data_dir() -> Path:
    """Return the shared data directory used by runtime databases."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return DB_DIR


def get_shared_data_path(file_name: str, subdir: str = None) -> Path:
    """Return a path inside the shared runtime data directory."""
    base_dir = get_data_dir()
    if subdir:
        base_dir = base_dir / subdir
        base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / file_name

# --- UTILITIES FOR SERVER-SPECIFIC DATABASE MANAGEMENT ---

def _resolve_server_storage_id(server_id: str | None) -> str | None:
    """Resolve server storage ID with fallback to active server."""
    candidate = str(server_id).strip() if server_id is not None else ""
    if candidate and candidate.isdigit():
        return candidate

    active = get_server_id()
    if active and active.isdigit():
        return active

    return None

def get_server_db_path(server_id: str, db_name: str = None) -> Path:
    """
    Generate database path for a specific server.
    
    Args:
        server_id: Server ID (sanitized)
        db_name: Database name (optional)
    
    Returns:
        Path: Full path to database file
    """
    server_storage_id = _resolve_server_storage_id(server_id)
    
    # Base directory
    server_dir = DB_DIR / server_storage_id if server_storage_id else DB_DIR
    try:
        server_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        # If we can't create server directory, use base directory
        print(f"⚠️ Cannot create DB directory {server_dir}: {e}")
        print(f"🗄️ Using base directory: {DB_DIR}")
        server_dir = DB_DIR
    
    # Use provided DB name or global default
    db_filename = db_name or get_personality_name(server_id)
    db_file_name = db_filename if str(db_filename).endswith('.db') else f'{db_filename}.db'
    db_path = server_dir / db_file_name
    
    # Ensure proper permissions if file doesn't exist
    if not db_path.exists():
        try:
            db_path.touch(exist_ok=True)
            # Set 666 permissions (rw for all) to avoid permission issues
            os.chmod(db_path, 0o666)
        except (PermissionError, OSError):
            pass  # If we can't set permissions, continue anyway
    
    return db_path

def get_server_log_path(server_id: str, log_name: str) -> Path:
    """
    Generate log path for a specific server.
    
    Args:
        server_id: Server ID (sanitized)
        log_name: Log file name
    
    Returns:
        Path: Full path to the log file
    """
    server_storage_id = _resolve_server_storage_id(server_id)
    
    # Base directory
    base_dir = Path(__file__).parent
    server_dir = base_dir / "logs"
    if server_storage_id:
        server_dir = server_dir / server_storage_id
    
    # Create directory if it doesn't exist
    server_dir.mkdir(parents=True, exist_ok=True)
    
    return server_dir / log_name

def get_personality_name(server_id: str = None):
    """Get personality name for database naming.

    Uses the directory name (e.g., 'putre(english)') from runtime
    rather than the 'name' field from personality.json to ensure
    correct server-specific database naming.

    Args:
        server_id: Optional server ID to get personality for specific server.
                  If not provided, uses active server detection.
    """
    logger.debug(f"[get_personality_name] Called with server_id={server_id}, __file__={__file__}")
    
    # Server 0 is a placeholder for initialization only - skip server_config check
    if server_id == "0":
        env_personality = os.getenv('PERSONALITY')
        if env_personality:
            return env_personality.lower()
        return "agent"  # Fallback for server 0 placeholder
    
    # Try to get from server-specific config (highest priority for server-specific requests)
    if server_id:
        try:
            import json
            # Use absolute path based on script location, not relative to CWD
            _base_dir = Path(__file__).parent
            logger.debug(f"[get_personality_name] _base_dir={_base_dir}")
            server_config_path = _base_dir / "databases" / server_id / "server_config.json"
            logger.debug(f"[get_personality_name] server_config_path={server_config_path}, exists={server_config_path.exists()}")
            if server_config_path.exists():
                with open(server_config_path, encoding="utf-8") as f:
                    server_cfg = json.load(f)
                logger.debug(f"[get_personality_name] server_cfg={server_cfg}")
                active_personality = server_cfg.get("active_personality")
                if active_personality:
                    logger.debug(f"[get_personality_name] Using active_personality from server_config for server {server_id}: {active_personality}")
                    return active_personality.lower()
                else:
                    logger.warning(f"[get_personality_name] server_config exists but no active_personality for server {server_id}")
                # (real configuration anomaly, keep as warning)
            else:
                logger.debug(f"[get_personality_name] server_config.json not found at {server_config_path}")
        except Exception as e:
            logger.error(f"[get_personality_name] Error reading server_config for server {server_id}: {e}", exc_info=True)

    # Then try from environment variable (fallback for global operations or when server_config is missing)
    env_personality = os.getenv('PERSONALITY')
    if env_personality:
        if server_id:
            logger.debug(f"[get_personality_name] Using PERSONALITY env var as fallback for server {server_id}: {env_personality}")
        else:
            logger.debug(f"[get_personality_name] Using PERSONALITY env var (no server_id): {env_personality}")
        return env_personality.lower()

    # No valid personality found - return None instead of creating placeholder
    logger.debug(f"[get_personality_name] No personality found for server {server_id}, returning None")
    return None

# Path and limits configuration
BASE_DIR = Path(__file__).parent
HISTORIAL_LIMITE = 5

class AgentDatabase:
    def __init__(self, server_id: str = "default", db_path: Path = None):
        self.server_id = server_id
        if db_path is None:
            # Use personality-specific database name with explicit server_id
            personality_name = get_personality_name(server_id)
            
            # Don't create database if personality cannot be determined
            if not personality_name:
                logger.warning(f"[AgentDatabase] Cannot determine personality for server {server_id}, skipping database initialization")
                self.db_path = None
                return
            
            db_name = f"agent_{personality_name}"
            self.db_path = get_server_db_path(server_id, db_name)
        else:
            self.db_path = db_path
        self._lock = threading.Lock()
        logger.info(f"🗄️ [DB] Initializing database at: {self.db_path}")
        self._init_db()

    def _init_db(self):
        """Initialize all necessary tables."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL;")
                    cursor.execute("PRAGMA busy_timeout=5000;")
                    cursor.execute("PRAGMA synchronous=NORMAL;")

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

    def register_interaction(self, user_id, user_name, interaction_type, context, channel_id=None, server_id=None, metadata=None):
        """Register an interaction (SQLite version - memory updates handled by NoSQL)."""
        fecha = datetime.datetime.now().isoformat()
        meta_json = json.dumps(metadata) if metadata else None
        try:
            with self._lock:
                db_path_str = str(self.db_path)
                with sqlite3.connect(db_path_str, timeout=30) as conn:
                    cursor = conn.cursor()
                    params = (
                        str(user_id),
                        user_name,
                        str(channel_id) if channel_id is not None else None,
                        interaction_type,
                        context,
                        meta_json,
                        fecha,
                        str(server_id) if server_id is not None else None,
                    )
                    cursor.execute('''
                        INSERT INTO interacciones
                        (usuario_id, usuario_nombre, canal_id, tipo_interaccion, contexto, metadata, fecha, servidor_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(usuario_id, fecha, tipo_interaccion) DO NOTHING
                    ''', params)
                    conn.commit()
                    conn.close()
                    logger.debug(f"✅ [DB] Interaction registered: user_id={user_id}, type={interaction_type}")
                    return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error registering interaction (user_id={user_id}, type={interaction_type}): {e}")
            return False

    def get_user_history(self, user_id, limite=HISTORIAL_LIMITE):
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT contexto, metadata FROM interacciones
                    WHERE usuario_id = ? ORDER BY fecha DESC LIMIT ?
                ''', (str(user_id), limite))

                res = cursor.fetchall()
                historial = []
                for row in res:
                    meta = json.loads(row['metadata']) if row['metadata'] else {}
                    historial.append({
                        "humano": row['contexto'],
                        "bot": meta.get('response', '') or meta.get('greeting', '') or meta.get('respuesta', '') or meta.get('saludo', '')
                    })
                return list(reversed(historial))
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving history: {e}")
            return []

    def get_recent_user_history(self, user_id, minutes=3):
        """Get history from the last N minutes for temporal context."""
        fecha_limite = (datetime.datetime.now() - datetime.timedelta(minutes=minutes)).isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT contexto, metadata FROM interacciones
                    WHERE usuario_id = ? AND fecha >= ? ORDER BY fecha DESC
                ''', (str(user_id), fecha_limite))

                res = cursor.fetchall()
                historial = []
                for row in res:
                    meta = json.loads(row['metadata']) if row['metadata'] else {}
                    historial.append({
                        "humano": row['contexto'],
                        "bot": meta.get('response', '') or meta.get('greeting', '') or meta.get('respuesta', '') or meta.get('saludo', '')
                    })
                return list(reversed(historial))
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error al recuperar historial reciente: {e}")
            return []

    
    def get_last_dialogue_window(self, user_id, max_messages=10):
        """Return last 10 human/bot dialogue pairs for prompt injection regardless of time window."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT contexto, metadata, fecha FROM interacciones
                    WHERE usuario_id = ? ORDER BY fecha DESC LIMIT ?
                ''', (str(user_id), max_messages * 2))

                rows = cursor.fetchall()
                dialogue = []
                for row in reversed(rows):
                    meta = json.loads(row['metadata']) if row['metadata'] else {}
                    dialogue.append({
                        "humano": row['contexto'] or "",
                        "bot": meta.get('response', '') or "",
                        "fecha": row['fecha'],
                    })
                return dialogue
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving last dialogue window: {e}")
            return []

    def get_recent_channel_interactions(self, channel_id, within_minutes=60, max_interactions=10):
        """Return recent messages from a specific channel for prompt injection."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT usuario_id, usuario_nombre, contexto, metadata, fecha, tipo_interaccion
                    FROM interacciones
                    WHERE canal_id = ? AND fecha >= datetime('now', '-{} minutes')
                    ORDER BY fecha DESC
                    LIMIT ?
                '''.format(within_minutes), (str(channel_id), max_interactions))
                
                rows = cursor.fetchall()
                logger.info(f"🧠 [DB] Found {len(rows)} rows in database")
                conn.close()
                
                messages = []
                for row in rows:
                    meta = json.loads(row['metadata']) if row['metadata'] else {}
                    messages.append({
                        "user_id": row['usuario_id'],
                        "user_name": row['usuario_nombre'],
                        "content": row['contexto'] or "",
                        "response": meta.get('response', '') or "",
                        "timestamp": row['fecha'],
                        "type": row['tipo_interaccion']
                    })
                return messages
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving recent channel messages: {e}")
            return []

    def get_last_channel_interactions(self, channel_id, max_messages=10):
        """Return last 10 messages from a specific channel for prompt injection regardless of time window."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT usuario_id, usuario_nombre, contexto, metadata, fecha, tipo_interaccion
                    FROM interacciones
                    WHERE canal_id = ?
                    ORDER BY fecha DESC
                    LIMIT ?
                ''', (str(channel_id), max_messages))
                
                rows = cursor.fetchall()
                logger.info(f"🧠 [DB] Found {len(rows)} rows in database")
                conn.close()
                
                messages = []
                for row in rows:
                    meta = json.loads(row['metadata']) if row['metadata'] else {}
                    messages.append({
                        "user_id": row['usuario_id'],
                        "user_name": row['usuario_nombre'],
                        "content": row['contexto'] or "",
                        "response": meta.get('response', '') or "",
                        "timestamp": row['fecha'],
                        "type": row['tipo_interaccion']
                    })
                return messages
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving last channel messages: {e}")
            return []

    def get_last_interaction(self, user_id):
        """Get the last interaction for a user to check if bot or human spoke last."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT contexto, metadata, fecha, tipo_interaccion
                    FROM interacciones
                    WHERE usuario_id = ?
                    ORDER BY fecha DESC
                    LIMIT 1
                ''', (str(user_id),))

                row = cursor.fetchone()
                conn.close()
                
                if row:
                    meta = json.loads(row['metadata']) if row['metadata'] else {}
                    return {
                        "context": row['contexto'] or "",
                        "bot_response": meta.get('response', '') or meta.get('greeting', '') or meta.get('respuesta', '') or meta.get('saludo', ''),
                        "type": row['tipo_interaccion'],
                        "date": row['fecha']
                    }
                return None
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving last interaction: {e}")
            return None

    def get_daily_interactions(self, limit=25, target_date=None):
        """Return the latest general interactions for a given day."""
        day_value = target_date or date.today().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT usuario_id, usuario_nombre, tipo_interaccion, contexto, metadata, fecha
                    FROM interacciones
                    WHERE date(fecha) = ?
                    ORDER BY fecha DESC
                    LIMIT ?
                ''', (day_value, limit))
                rows = cursor.fetchall()
                conn.close()
                interactions = []
                for row in reversed(rows):
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    interactions.append({
                        "usuario_id": row["usuario_id"],
                        "usuario_nombre": row["usuario_nombre"] or "",
                        "tipo_interaccion": row["tipo_interaccion"] or "",
                        "contexto": row["contexto"] or "",
                        "respuesta": metadata.get("response", "") or metadata.get("respuesta", "") or metadata.get("greeting", "") or metadata.get("saludo", ""),
                        "fecha": row["fecha"],
                    })
                return interactions
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving daily interactions: {e}")
            return []

    def get_daily_interactions_since(self, since_iso=None, limit=25, target_date=None):
        """Return day-scoped general interactions after a given timestamp."""
        day_value = target_date or date.today().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if since_iso:
                    cursor.execute('''
                        SELECT usuario_id, usuario_nombre, tipo_interaccion, contexto, metadata, fecha
                        FROM interacciones
                        WHERE date(fecha) = ? AND fecha > ?
                        ORDER BY fecha ASC
                        LIMIT ?
                    ''', (day_value, since_iso, limit))
                else:
                    cursor.execute('''
                        SELECT usuario_id, usuario_nombre, tipo_interaccion, contexto, metadata, fecha
                        FROM interacciones
                        WHERE date(fecha) = ?
                        ORDER BY fecha DESC
                        LIMIT ?
                    ''', (day_value, limit))
                rows = cursor.fetchall()
                conn.close()
                interactions = []
                ordered_rows = rows if since_iso else list(reversed(rows))
                for row in ordered_rows:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    interactions.append({
                        "usuario_id": row["usuario_id"],
                        "usuario_nombre": row["usuario_nombre"] or "",
                        "tipo_interaccion": row["tipo_interaccion"] or "",
                        "contexto": row["contexto"] or "",
                        "respuesta": metadata.get("response", "") or metadata.get("respuesta", "") or metadata.get("greeting", "") or metadata.get("saludo", ""),
                        "fecha": row["fecha"],
                    })
                return interactions
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving daily interactions since: {e}")
            return []

    def get_user_last_server_id(self, user_id: str) -> str | None:
        """Get the last server ID where the user had interactions."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Look for the most recent interaction from this user
                cursor.execute('''
                    SELECT servidor_id 
                    FROM interacciones 
                    WHERE usuario_id = ? 
                    ORDER BY fecha DESC 
                    LIMIT 1
                ''', (str(user_id),))
                
                row = cursor.fetchone()
                conn.close()
                
                if row and row['servidor_id']:
                    return str(row['servidor_id'])
                return None
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error getting user's last server: {e}")
            return None

    def get_user_interactions_since(self, user_id, since_iso=None, limit=25):
        """Return user interactions after a given timestamp."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if since_iso:
                    cursor.execute('''
                        SELECT contexto, metadata, fecha, tipo_interaccion, usuario_nombre
                        FROM interacciones
                        WHERE usuario_id = ? AND fecha > ?
                        ORDER BY fecha ASC
                        LIMIT ?
                    ''', (str(user_id), since_iso, limit))
                else:
                    cursor.execute('''
                        SELECT contexto, metadata, fecha, tipo_interaccion, usuario_nombre
                        FROM interacciones
                        WHERE usuario_id = ?
                        ORDER BY fecha DESC
                        LIMIT ?
                    ''', (str(user_id), limit))
                rows = cursor.fetchall()
                conn.close()
                interactions = []
                ordered_rows = rows if since_iso else list(reversed(rows))
                for row in ordered_rows:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    interactions.append({
                        "humano": row["contexto"] or "",
                        "bot": metadata.get("response", "") or metadata.get("greeting", "") or metadata.get("respuesta", "") or metadata.get("saludo", "") or "",
                        "fecha": row["fecha"],
                        "tipo_interaccion": row["tipo_interaccion"] or "",
                        "usuario_nombre": row["usuario_nombre"] or "",
                    })
                return interactions
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving user interactions since: {e}")
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
                ''', (str(user_id), f'%{tipo_like}%', fecha_limite))
                return cursor.fetchone()[0] > 0
        except Exception:
            logger.exception("⚠️ [DB] Error comprobando interacciones recientes por tipo")
            return False

    def clean_old_interactions(self, days=30):
        deadline = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM interacciones WHERE fecha < ?', (deadline,))
                deleted = cursor.rowcount if cursor.rowcount is not None and cursor.rowcount >= 0 else 0
                conn.commit()
                logger.info(f"🧹 Cleaned interactions before {deadline}")
                return deleted

    def forget_user(self, user_id, user_name: str = None, extra_names=None) -> dict:
        """GDPR — right to erasure (Art. 17).

        Two-phase wipe:

        1. Drop every row directly keyed by this `user_id` (raw interactions,
           per-user relationship memories, scheduled relationship updates).
        2. When a ``user_name`` (and optional aliases in ``extra_names``) is
           provided, **redact** mentions of those names in LLM-synthesised
           narrative tables. Those tables do not carry a user_id column, so
           leaving the text intact after erasure would still identify the
           user by name. We rewrite each occurrence to ``[redacted]`` in place
           and keep the row (the aggregate memory is about the whole server,
           not only that user).

        Returns a per-table report of rows deleted / rewritten.
        """
        uid = str(user_id)
        tables_keyed_by_uid = [
            ('interacciones', 'usuario_id'),
        ]
        deleted: dict = {}

        # Build the name-redaction list, deduplicated and ordered longest-first
        # so we do not leave partial matches behind.
        names = []
        for n in [user_name] + list(extra_names or []):
            if n and n.strip() and n.strip() not in names:
                names.append(n.strip())
        names.sort(key=len, reverse=True)

        # No narrative targets (memory tables removed - using NoSQL now)
        narrative_targets = []

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Phase 1 — delete rows keyed by uid.
                for table, column in tables_keyed_by_uid:
                    try:
                        cursor.execute(f'DELETE FROM {table} WHERE {column} = ?', (uid,))
                        deleted[table] = cursor.rowcount
                    except sqlite3.OperationalError:
                        deleted[table] = 0

                # Phase 2 — redact names in synthesised prose.
                if names:
                    import re
                    pattern = re.compile(
                        r'\b(' + '|'.join(re.escape(n) for n in names) + r')\b',
                        flags=re.IGNORECASE,
                    )
                    for table, column in narrative_targets:
                        try:
                            cursor.execute(f'SELECT rowid, {column} FROM {table}')
                            rows = cursor.fetchall()
                        except sqlite3.OperationalError:
                            deleted[f'{table}.redacted'] = 0
                            continue
                        rewrites = 0
                        for rowid, text in rows:
                            if not text:
                                continue
                            new_text = pattern.sub('[redacted]', text)
                            if new_text != text:
                                cursor.execute(
                                    f'UPDATE {table} SET {column} = ? WHERE rowid = ?',
                                    (new_text, rowid),
                                )
                                rewrites += 1
                        deleted[f'{table}.redacted'] = rewrites

                conn.commit()

        total = sum(deleted.values())
        logger.info(f"🧹 [GDPR] forget_user({uid}) on {self.db_path.name}: {deleted} (total_ops={total})")
        return deleted

    def apply_retention(self, interactions_days: int = 90, derived_memory_days: int = 365) -> dict:
        """Purge data older than the retention thresholds.

        Args:
            interactions_days: Hard limit for raw ``interacciones`` rows — the
                most direct PII we store. Defaults to 90 days.
            derived_memory_days: No longer used (memory tables removed - using NoSQL now).

        Returns a per-table row count of what was deleted.
        """
        import datetime as _dt
        now = _dt.datetime.now()
        interactions_deadline = (now - _dt.timedelta(days=interactions_days)).isoformat()

        # (table, column, deadline, comparator_is_date_only)
        plan = [
            ('interacciones', 'fecha', interactions_deadline, False),
        ]

        report: dict = {}
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for table, column, deadline, _is_date in plan:
                    try:
                        cursor.execute(f'DELETE FROM {table} WHERE {column} < ?', (deadline,))
                        report[table] = cursor.rowcount
                    except sqlite3.OperationalError:
                        report[table] = 0
                conn.commit()

        total = sum(report.values())
        if total:
            logger.info(
                f"🧹 [GDPR] apply_retention on {self.db_path.name}: {report} "
                f"(interactions≥{interactions_days}d)"
            )
        return report

    def count_interactions_by_type_last_day(self, interaction_type, server_id=None):
        """Count how many interactions of `interaction_type` occurred today."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                if server_id is not None:
                    cursor.execute('''
                        SELECT COUNT(*) FROM interacciones
                        WHERE tipo_interaccion = ? AND servidor_id = ? AND date(fecha) = date('now','localtime')
                    ''', (interaction_type, str(server_id)))
                else:
                    cursor.execute('''
                        SELECT COUNT(*) FROM interacciones
                        WHERE tipo_interaccion = ? AND date(fecha) = date('now','localtime')
                    ''', (interaction_type,))
                return cursor.fetchone()[0]
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error counting interactions (type={interaction_type}): {e}")
            return 0

    def user_has_recent_interactions(self, user_id, hours=12, types=None):
        """Check if a user has had recent interactions."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                if types:
                    placeholders = ','.join(['?' for _ in types])
                    cursor.execute(f'''
                        SELECT COUNT(*) FROM interacciones
                        WHERE usuario_id = ? AND datetime(fecha) > datetime('now', '-{hours} hours')
                        AND tipo_interaccion IN ({placeholders})
                    ''', [user_id] + types)
                else:
                    cursor.execute(f'''
                        SELECT COUNT(*) FROM interacciones
                        WHERE usuario_id = ? AND datetime(fecha) > datetime('now', '-{hours} hours')
                    ''', (user_id,))

                count = cursor.fetchone()[0]
                conn.close()
                return count > 0
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error checking recent interactions: {e}")
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
                    return [self.server_id]
                
                return servers
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error getting active servers: {e}")
            return [self.server_id]  # Fallback to current server

# Dictionary to maintain instances per server
_db_instances = {}

# Lock for thread-safe access to _db_instances
_db_instances_lock = threading.Lock()

def get_db_instance(server_id: str = "default"):
    """Get or create a database instance for a specific server.
    
    Returns an AgentState (NoSQL-backed) instance by default.
    """
    global db
    # Only use active server if no specific server_id provided
    if server_id == "default":
        active = get_server_id()
        if active:
            server_id = active
    
    # Thread-safe access to _db_instances
    with _db_instances_lock:
        if server_id not in _db_instances:
            from persistence.agent_state import AgentState
            _db_instances[server_id] = AgentState(server_id)
        return _db_instances[server_id]

def invalidate_db_instance(server_id: str = None):
    """Invalidate cached database instance for a server.
    
    Call this after personality change so the next get_db_instance()
    creates a new AgentDatabase pointing to the correct personality db file.
    
    Args:
        server_id: Server ID to invalidate, or None to clear all.
    """
    global _db_instances, db, _current_server_id
    with _db_instances_lock:
        if server_id:
            if server_id in _db_instances:
                del _db_instances[server_id]
                logger.info(f"🗄️ [DB] Invalidated cached db instance for server: {server_id}")
            # Also reset global db if it was for this server
            if _current_server_id == server_id:
                db = None
                _current_server_id = None
        else:
            _db_instances = {}
            db = None
            _current_server_id = None
            logger.info("🗄️ [DB] Invalidated all cached db instances")

def _delete_old_personality_database(old_db_path: Path, server_id: str):
    """
    Delete old personality database file when personality changes.
    
    When a server switches personality (e.g., from rab to igorrr), the old
    database file (agent_rab.db) becomes orphaned. This function removes it
    to prevent confusion and wasted disk space.
    
    Args:
        old_db_path: Path to the old personality database
        server_id: Server ID for logging purposes
    """
    try:
        if not old_db_path.exists():
            return
        
        # Delete the old database file
        old_db_path.unlink()
        logger.info(
            f"🗄️ [DB] Deleted old personality database for server {server_id}: {old_db_path.name}"
        )
    except Exception as e:
        logger.warning(f"🗄️ [DB] Could not delete old database {old_db_path}: {e}")

def get_all_server_keys() -> list[str]:
    """Get all server keys from the database instances cache."""
    return list(_db_instances.keys())

db = None
_current_server_id = None

def get_global_db(server_id: str = None, use_default_for_roles: bool = False):
    """Get the global DB instance for the current server (NoSQL-backed)."""
    global db, _current_server_id
    
    if server_id is None:
        active = _current_server_id or get_server_id()
        if active:
            server_id = active
        elif use_default_for_roles and os.getenv("ROLE_AGENT_PROCESS"):
            server_id = "default"
        else:
            server_id = "default"
    
    # Always route through get_db_instance so personality-change validation runs.
    db = get_db_instance(server_id)
    _current_server_id = server_id
    
    return db

def set_current_server(server_id: str):
    """Set the current server for the global DB."""
    global _current_server_id
    _current_server_id = server_id
    if server_id:
        # Reload personality to load server-specific copy if available
        try:
            from agent_engine import reload_personality
            reload_personality(server_id)
        except Exception as e:
            logger.warning(f"Could not reload personality on server change: {e}")

def get_database_path(server_id: str, db_type: str) -> str:
    """
    Get database path for role-specific databases.
    
    Args:
        server_id: Server ID
        db_type: Database type (banker, news_watcher, dice_game, etc.)
    
    Returns:
        str: Full path to the database file
    """
    # Roles that have been migrated to centralized roles.db system
    # NOTE: 'banker' moved to dedicated roles/banker.db (see roles/banker/db_banker_core.py)
    centralized_roles = {'beggar', 'trickster', 'mc', 'dice_game', 'nordic_runes', 'treasure_hunter'}
    
    if db_type in centralized_roles:
        # Return path to the centralized roles.db with personality-specific naming
        from agent_roles_db import get_roles_db_path
        return str(get_roles_db_path(server_id))
    
    personality_name = get_personality_name(server_id)

    # Don't create database if personality cannot be determined
    if not personality_name:
        logger.warning(f"[get_database_path] Cannot determine personality for server {server_id}, skipping database creation for {db_type}")
        return None

    # Map database types to filenames (only for non-centralized roles)
    db_filenames = {
        'news_watcher': f'watcher_{personality_name}',
    }

    db_name = db_filenames.get(db_type, f'{db_type}_{personality_name}')
    return str(get_server_db_path(server_id, db_name))

# --- FATIGUE DATABASE SYSTEM ---

def get_fatigue_db_path(server_id: str) -> Optional[str]:
    """
    Get path for fatigue database.

    Args:
        server_id: Server ID

    Returns:
        str: Full path to fatigue database, or None if personality cannot be determined
    """
    personality_name = get_personality_name(server_id)
    
    # Don't create database if personality cannot be determined
    if not personality_name:
        logger.warning(f"[get_fatigue_db_path] Cannot determine personality for server {server_id}, skipping database creation")
        return None
    
    db_name = f"fatigue_{personality_name}"
    return str(get_server_db_path(server_id, db_name))

def init_fatigue_db(server_id: str) -> sqlite3.Connection:
    """
    Initialize fatigue database for a server.
    
    Args:
        server_id: Server ID
        
    Returns:
        sqlite3.Connection: Database connection
    """
    db_path = get_fatigue_db_path(server_id)
    db = sqlite3.connect(db_path, timeout=30.0)
    
    # Check if table exists and needs migration
    cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fatigue'")
    table_exists = cursor.fetchone() is not None
    
    if table_exists:
        # Check if new columns exist
        cursor = db.execute("PRAGMA table_info(fatigue)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Add new columns if they don't exist
        if 'hourly_requests' not in columns:
            db.execute('ALTER TABLE fatigue ADD COLUMN hourly_requests INTEGER DEFAULT 0')
        if 'last_hour_timestamp' not in columns:
            db.execute('ALTER TABLE fatigue ADD COLUMN last_hour_timestamp TEXT')
        if 'burst_requests' not in columns:
            db.execute('ALTER TABLE fatigue ADD COLUMN burst_requests INTEGER DEFAULT 0')
        if 'last_burst_timestamp' not in columns:
            db.execute('ALTER TABLE fatigue ADD COLUMN last_burst_timestamp TEXT')
        if 'created_at' not in columns:
            db.execute('ALTER TABLE fatigue ADD COLUMN created_at TEXT DEFAULT CURRENT_TIMESTAMP')
        if 'updated_at' not in columns:
            db.execute('ALTER TABLE fatigue ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP')
    else:
        # Create fatigue table if it doesn't exist
        db.execute('''
            CREATE TABLE IF NOT EXISTS fatigue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                user_name TEXT,
                daily_requests INTEGER DEFAULT 0,
                total_requests INTEGER DEFAULT 0,
                last_request_date TEXT,
                hourly_requests INTEGER DEFAULT 0,
                last_hour_timestamp TEXT,
                burst_requests INTEGER DEFAULT 0,
                last_burst_timestamp TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id)
            )
        ''')
    
    # Create server row if it doesn't exist
    server_row_id = f"server_{server_id}"
    today = str(date.today())
    
    db.execute('''
        INSERT OR IGNORE INTO fatigue 
        (user_id, user_name, daily_requests, total_requests, last_request_date, hourly_requests, last_hour_timestamp, burst_requests, last_burst_timestamp)
        VALUES (?, ?, 0, 0, ?, 0, ?, 0, ?)
    ''', (server_row_id, f"Server_{server_id}", today, today, today))
    
    db.commit()
    return db

def increment_fatigue_count(server_id: str, user_id: str, user_name: str = None) -> tuple[int, int]:
    """
    Increment fatigue count for a user and server.
    
    Args:
        server_id: Server ID
        user_id: User ID (or "server_{server_id}" for server total)
        user_name: User name (optional)
        
    Returns:
        tuple[int, int]: (daily_requests, total_requests) after increment
    """
    db = init_fatigue_db(server_id)
    today = str(date.today())
    
    try:
        # Get current stats
        cursor = db.execute('''
            SELECT daily_requests, total_requests, last_request_date,
                   hourly_requests, last_hour_timestamp,
                   burst_requests, last_burst_timestamp
            FROM fatigue WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        
        # Get current timestamps for tracking
        now = datetime.datetime.now()
        current_hour = now.replace(minute=0, second=0, microsecond=0).isoformat()
        five_min_ago = (now - datetime.timedelta(minutes=5)).isoformat()
        
        if row:
            current_daily, current_total, last_date, current_hourly, last_hour_ts, current_burst, last_burst_ts = row
            
            # Reset daily count if date changed
            if last_date != today:
                new_daily = 1
            else:
                new_daily = current_daily + 1
                
            # Reset hourly count if hour changed
            if last_hour_ts != current_hour:
                new_hourly = 1
            else:
                new_hourly = current_hourly + 1
                
            # Reset burst count if more than 5 minutes since last burst
            if last_burst_ts and last_burst_ts > five_min_ago:
                new_burst = current_burst + 1
            else:
                new_burst = 1
                
            new_total = current_total + 1
            
            # Update user record
            db.execute('''
                UPDATE fatigue 
                SET daily_requests = ?, total_requests = ?, 
                    last_request_date = ?, updated_at = CURRENT_TIMESTAMP,
                    hourly_requests = ?, last_hour_timestamp = ?,
                    burst_requests = ?, last_burst_timestamp = ?,
                    user_name = COALESCE(?, user_name)
                WHERE user_id = ?
            ''', (new_daily, new_total, today, new_hourly, current_hour, 
                  new_burst, now.isoformat(), user_name, user_id))
        else:
            # Insert new user record
            new_daily = 1
            new_total = 1
            new_hourly = 1
            new_burst = 1
            
            db.execute('''
                INSERT INTO fatigue 
                (user_id, user_name, daily_requests, total_requests, last_request_date,
                 hourly_requests, last_hour_timestamp, burst_requests, last_burst_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    daily_requests = excluded.daily_requests,
                    total_requests = excluded.total_requests,
                    last_request_date = excluded.last_request_date,
                    hourly_requests = excluded.hourly_requests,
                    last_hour_timestamp = excluded.last_hour_timestamp,
                    burst_requests = excluded.burst_requests,
                    last_burst_timestamp = excluded.last_burst_timestamp
            ''', (user_id, user_name or f"User_{user_id}", new_daily, new_total, today,
                  new_hourly, current_hour, new_burst, now.isoformat()))
        
        # Also increment server total if this is a user request (avoid recursion)
        if not user_id.startswith("server_"):
            server_row_id = f"server_{server_id}"
            # Direct server increment without recursion
            cursor = db.execute('''
                SELECT daily_requests, total_requests, last_request_date,
                       hourly_requests, last_hour_timestamp,
                       burst_requests, last_burst_timestamp
                FROM fatigue WHERE user_id = ?
            ''', (server_row_id,))
            
            server_row = cursor.fetchone()
            if server_row:
                srv_daily, srv_total, srv_last_date, srv_hourly, srv_last_hour, srv_burst, srv_last_burst = server_row
                
                # Reset server daily if date changed
                if srv_last_date != today:
                    new_srv_daily = 1
                else:
                    new_srv_daily = srv_daily + 1
                    
                # Reset server hourly if hour changed
                if srv_last_hour != current_hour:
                    new_srv_hourly = 1
                else:
                    new_srv_hourly = srv_hourly + 1
                    
                # Reset server burst if more than 5 minutes
                if srv_last_burst and srv_last_burst > five_min_ago:
                    new_srv_burst = srv_burst + 1
                else:
                    new_srv_burst = 1
                    
                new_srv_total = srv_total + 1
                
                db.execute('''
                    UPDATE fatigue 
                    SET daily_requests = ?, total_requests = ?, 
                        last_request_date = ?, updated_at = CURRENT_TIMESTAMP,
                        hourly_requests = ?, last_hour_timestamp = ?,
                        burst_requests = ?, last_burst_timestamp = ?
                    WHERE user_id = ?
                ''', (new_srv_daily, new_srv_total, today, new_srv_hourly, current_hour,
                      new_srv_burst, now.isoformat(), server_id))
            else:
                # Insert server record if it doesn't exist (idempotent)
                db.execute('''
                    INSERT INTO fatigue 
                    (user_id, user_name, daily_requests, total_requests, last_request_date,
                     hourly_requests, last_hour_timestamp, burst_requests, last_burst_timestamp)
                    VALUES (?, ?, 1, 1, ?, 1, ?, 1, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        daily_requests = excluded.daily_requests,
                        total_requests = excluded.total_requests,
                        last_request_date = excluded.last_request_date,
                        hourly_requests = excluded.hourly_requests,
                        last_hour_timestamp = excluded.last_hour_timestamp,
                        burst_requests = excluded.burst_requests,
                        last_burst_timestamp = excluded.last_burst_timestamp
                ''', (server_row_id, f"Server_{server_id}", today, current_hour, now.isoformat()))
            
            db.commit()
        return new_daily, new_total
        
    except Exception as e:
        logger.error(f"Error incrementing fatigue count: {e}")
        return 0, 0
    finally:
        db.close()

def get_fatigue_stats(server_id: str, user_id: str = None) -> dict:
    """
    Get fatigue statistics.
    
    Args:
        server_id: Server ID
        user_id: User ID (optional, if None gets all users)
        
    Returns:
        dict: Fatigue statistics
    """
    db = init_fatigue_db(server_id)
    
    try:
        if user_id:
            # Get specific user stats
            cursor = db.execute('''
                SELECT user_id, user_name, daily_requests, total_requests, last_request_date,
                       hourly_requests, last_hour_timestamp, burst_requests, last_burst_timestamp
                FROM fatigue WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'user_name': row[1],
                    'daily_requests': row[2],
                    'total_requests': row[3],
                    'last_request_date': row[4],
                    'hourly_requests': row[5],
                    'last_hour_timestamp': row[6],
                    'burst_requests': row[7],
                    'last_burst_timestamp': row[8]
                }
            else:
                return {}
        else:
            # Get all users stats
            cursor = db.execute('''
                SELECT user_id, user_name, daily_requests, total_requests, last_request_date,
                       hourly_requests, last_hour_timestamp, burst_requests, last_burst_timestamp
                FROM fatigue ORDER BY total_requests DESC
            ''')
            
            stats = []
            for row in cursor.fetchall():
                stats.append({
                    'user_id': row[0],
                    'user_name': row[1],
                    'daily_requests': row[2],
                    'total_requests': row[3],
                    'last_request_date': row[4],
                    'hourly_requests': row[5],
                    'last_hour_timestamp': row[6],
                    'burst_requests': row[7],
                    'last_burst_timestamp': row[8]
                })
            
            return {'users': stats}
            
    finally:
        db.close()

def reset_daily_fatigue(server_id: str) -> int:
    """
    Reset daily fatigue counts for all users in a server.
    This should be called when the date changes.
    
    Args:
        server_id: Server ID
        
    Returns:
        int: Number of users whose daily count was reset
    """
    db = init_fatigue_db(server_id)
    
    try:
        cursor = db.execute('''
            UPDATE fatigue 
            SET daily_requests = 0, updated_at = CURRENT_TIMESTAMP
            WHERE daily_requests > 0
        ''')
        
        db.commit()
        return cursor.rowcount
        
    finally:
        db.close()

def forget_user_across_servers(user_id, user_name: str = None, extra_names=None, server_ids=None) -> dict:
    """GDPR — sweep a user out of every per-server database we know about.

    Args:
        user_id: The Discord user id (str/int).
        user_name: Best-known display/user name. When provided, occurrences
            are also redacted from LLM-synthesised summaries (see
            :meth:`AgentDatabase.forget_user`).
        extra_names: Optional additional aliases to redact.
        server_ids: Optional iterable of server ids to limit the sweep. When
            omitted, every subdirectory under ``databases/`` that looks like a
            server id is processed.

    Returns:
        Mapping ``{server_id: {table: deleted_rows}}`` with one entry per
        server successfully processed. Fatigue rows keyed by user_id are also
        purged.
    """
    report: dict = {}
    db_root = DB_DIR
    if server_ids is None:
        try:
            server_ids = [p.name for p in db_root.iterdir() if p.is_dir() and p.name.isdigit()]
        except OSError:
            server_ids = []

    uid = str(user_id)
    for sid in server_ids:
        server_report: dict = {}
        # Main agent DB
        try:
            db = get_db_instance(sid)
            if db is not None:
                server_report.update(db.forget_user(uid, user_name=user_name, extra_names=extra_names))
        except Exception as e:
            logger.warning(f"[GDPR] forget_user failed on agent DB for server {sid}: {e}")

        # Fatigue table lives in its own DB per server
        try:
            fat_db = init_fatigue_db(sid)
            try:
                cursor = fat_db.execute('DELETE FROM fatigue WHERE user_id = ?', (uid,))
                server_report['fatigue'] = cursor.rowcount
                fat_db.commit()
            finally:
                fat_db.close()
        except Exception as e:
            logger.warning(f"[GDPR] forget_user failed on fatigue DB for server {sid}: {e}")

        # Nordic Runes readings (NoSQL-backed)
        try:
            from agent_roles_db import get_roles_db_instance
            roles_db = get_roles_db_instance(sid)
            if roles_db is not None:
                deleted_runes = roles_db.delete_nordic_runes_readings(uid)
                if deleted_runes > 0:
                    server_report['nordic_runes'] = deleted_runes
        except Exception as e:
            logger.warning(f"[GDPR] forget_user failed on nordic runes for server {sid}: {e}")

        if server_report:
            report[sid] = server_report

    logger.info(f"🧹 [GDPR] forget_user_across_servers({uid}): touched {len(report)} servers")
    return report


def apply_retention_across_servers(interactions_days: int = 90, derived_memory_days: int = 365,
                                   server_ids=None) -> dict:
    """Run :meth:`AgentDatabase.apply_retention` on every server database.

    Returns a mapping ``{server_id: {table: deleted_rows}}`` with only the
    servers where at least one row was deleted.
    """
    report: dict = {}
    db_root = DB_DIR
    if server_ids is None:
        try:
            server_ids = [p.name for p in db_root.iterdir() if p.is_dir() and p.name.isdigit()]
        except OSError:
            server_ids = []

    for sid in server_ids:
        try:
            db = get_db_instance(sid)
            if db is None:
                continue
            server_report = db.apply_retention(
                interactions_days=interactions_days,
                derived_memory_days=derived_memory_days,
            )
            if any(server_report.values()):
                report[sid] = server_report
        except Exception as e:
            logger.warning(f"[GDPR] apply_retention failed for server {sid}: {e}")

    if report:
        logger.info(f"🧹 [GDPR] apply_retention_across_servers: purged on {len(report)} servers")
    return report


def cleanup_old_fatigue_data(server_id: str, days_to_keep: int = 30) -> int:
    """
    Clean up old fatigue data (users with no activity for specified days).
    
    Args:
        server_id: Server ID
        days_to_keep: Number of days to keep inactive users
        
    Returns:
        int: Number of users removed
    """
    db = init_fatigue_db(server_id)
    
    try:
        cutoff_date = (date.today() - datetime.timedelta(days=days_to_keep)).isoformat()
        
        cursor = db.execute('''
            DELETE FROM fatigue 
            WHERE user_id NOT LIKE 'server_%' 
            AND last_request_date < ?
            AND total_requests < 10
        ''', (cutoff_date,))
        
        db.commit()
        return cursor.rowcount
        
    finally:
        db.close()
