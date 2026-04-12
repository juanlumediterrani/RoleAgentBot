import sqlite3
import datetime
import json
import os
import threading
from pathlib import Path
from datetime import date
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

_ACTIVE_SERVER_FILE = Path(__file__).parent / ".active_server"

def get_active_server_id() -> str | None:
    """DEPRECATED: This function is deprecated and will be removed.
    Always pass server_id explicitly to avoid cross-server data contamination.
    """
    logger.warning("🚨 get_active_server_id() is deprecated. Pass server_id explicitly.")
    return None

def get_server_id() -> str | None:
    """Get the current server ID from databases directory.
    
    Reads the server ID from the numeric folder name inside databases/.
    
    Returns:
        str | None: Server ID as string, or None if not found
    """
    try:
        db_dir = Path("databases")
        if db_dir.exists():
            server_dirs = [d for d in db_dir.iterdir() if d.is_dir() and d.name.isdigit()]
            if len(server_dirs) == 1:
                # Only one server directory, use it
                return server_dirs[0].name
            elif len(server_dirs) > 1:
                # Multiple servers, can't determine which one
                logger.warning(f"Multiple server directories found: {[d.name for d in server_dirs]}. Cannot determine active server.")
    except Exception as e:
        logger.warning(f"Error reading databases directory: {e}")
    
    return None

def get_all_server_ids() -> list[str]:
    """Get all server IDs that have databases."""
    try:
        db_dir = Path("databases")
        if not db_dir.exists():
            return []
        
        server_ids = []
        for server_dir in db_dir.iterdir():
            if server_dir.is_dir() and server_dir.name.isdigit():
                # Check if this server has an agent database
                agent_db_path = server_dir / f"agent_{get_personality_name(server_dir.name).lower()}.db"
                if agent_db_path.exists():
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
        db_dir = Path("databases")
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
            # Check for agent database
            personality = get_personality_name(server_id)
            agent_db_path = server_dir / f"agent_{personality.lower()}.db"
            
            if not agent_db_path.exists():
                continue
                
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


def persist_active_server_id(server_id: str) -> None:
    """Persist the active server ID to file."""
    try:
        _ACTIVE_SERVER_FILE.write_text(server_id.strip(), encoding="utf-8")
    except Exception:
        pass


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

def get_server_db_path_fallback(server_id: str, db_name: str) -> Path:
    """
    Version with fallback for Docker environments or restricted permissions.
    """
    server_storage_id = _resolve_server_storage_id(server_id)
    resolved_server_id = server_storage_id or server_id

    # Try local path first
    local_path = get_server_db_path(resolved_server_id, db_name)
    
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
        fallback_dir = Path.home() / '.roleagentbot' / 'databases'
        if server_storage_id:
            fallback_dir = fallback_dir / server_storage_id
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
            server_config_path = Path("databases") / server_id / "server_config.json"
            if server_config_path.exists():
                with open(server_config_path, encoding="utf-8") as f:
                    server_cfg = json.load(f)
                active_personality = server_cfg.get("active_personality")
                if active_personality:
                    logger.info(f"[get_personality_name] Using active_personality from server_config for server {server_id}: {active_personality}")
                    return active_personality.lower()
                else:
                    logger.warning(f"[get_personality_name] server_config exists but no active_personality for server {server_id}")
            else:
                logger.warning(f"[get_personality_name] server_config.json not found for server {server_id}")
        except Exception as e:
            logger.error(f"[get_personality_name] Error reading server_config for server {server_id}: {e}")

    # Then try from environment variable (fallback for global operations or when server_config is missing)
    env_personality = os.getenv('PERSONALITY')
    if env_personality:
        if server_id:
            logger.info(f"[get_personality_name] Using PERSONALITY env var as fallback for server {server_id}: {env_personality}")
        else:
            logger.info(f"[get_personality_name] Using PERSONALITY env var (no server_id): {env_personality}")
        return env_personality.lower()

    # Final fallback
    logger.warning(f"[get_personality_name] No personality found, using fallback 'agent'")
    return "agent"

# Path and limits configuration
BASE_DIR = Path(__file__).parent
HISTORIAL_LIMITE = 5

class AgentDatabase:
    def __init__(self, server_id: str = "default", db_path: Path = None):
        self.server_id = server_id
        if db_path is None:
            # Use personality-specific database name with explicit server_id
            personality_name = get_personality_name(server_id)
            db_name = f"agent_{personality_name}"
            self.db_path = get_server_db_path_fallback(server_id, db_name)
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
            server_storage_id = _resolve_server_storage_id(self.server_id)
            if server_storage_id:
                fallback_dir = fallback_dir / server_storage_id
            fallback_dir.mkdir(parents=True, exist_ok=True)

            fallback_db = fallback_dir / f'agent_{get_personality_name(self.server_id)}.db'
            self.db_path = fallback_db
            logger.info(f"ℹ️ [DB] Database relocated to {self.db_path}")

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
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS daily_memory (
                        memory_date TEXT NOT NULL PRIMARY KEY,
                        summary TEXT NOT NULL,
                        metadata TEXT,
                        updated_at DATETIME NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS recent_memory (
                        memory_date TEXT NOT NULL PRIMARY KEY,
                        summary TEXT NOT NULL,
                        metadata TEXT,
                        updated_at DATETIME NOT NULL,
                        last_interaction_at DATETIME
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_relationship_memory (
                        usuario_id TEXT NOT NULL PRIMARY KEY,
                        summary TEXT NOT NULL,
                        metadata TEXT,
                        updated_at DATETIME NOT NULL,
                        last_interaction_at DATETIME
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_relationship_daily_memory (
                        memory_date TEXT NOT NULL,
                        usuario_id TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        metadata TEXT,
                        updated_at DATETIME NOT NULL,
                        UNIQUE(memory_date, usuario_id)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pending_relationship_updates (
                        usuario_id TEXT NOT NULL PRIMARY KEY,
                        scheduled_for DATETIME NOT NULL,
                        status TEXT NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pending_recent_memory_updates (
                        scheduled_for DATETIME NOT NULL PRIMARY KEY,
                        status TEXT NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS notable_recollections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        memory_date TEXT NOT NULL,
                        recollection_text TEXT NOT NULL,
                        source_paragraph TEXT,
                        extracted_at DATETIME NOT NULL,
                        used_count INTEGER DEFAULT 0,
                        last_used_at DATETIME
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_recollections_date ON notable_recollections (memory_date)')
                conn.commit()
                
                # Initialize notable recollections if empty
                self._initialize_notable_recollections()
                
                logger.info(f"✅ Database ready at {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ [DB] Error in initialization: {e}")

    def _initialize_notable_recollections(self):
        """Initialize notable recollections from personality JSON if table is empty."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Check if recollections table is empty
                cursor.execute(f'''
                    SELECT COUNT(*) FROM notable_recollections
                ''')
                count = cursor.fetchone()[0]
                
                if count == 0:
                    # Get initial recollections from personality
                    try:
                        from agent_mind import _engine
                        engine = _engine()
                        personality = engine.PERSONALITY
                        initial_recollections = personality.get("initial_recollections", [])
                        default_recollections = personality.get("default_recollections", [])
                        # Combine both sources
                        all_recollections = (initial_recollections or []) + (default_recollections or [])
                    except Exception as e:
                        logger.warning(f"⚠️ [DB] Could not load personality for initial recollections: {e}")
                        all_recollections = []
                    
                    if all_recollections:
                        extracted_at = datetime.datetime.now().isoformat()
                        for recollection_text in all_recollections:
                            cursor.execute('''
                                INSERT INTO notable_recollections
                                (memory_date, recollection_text, source_paragraph, extracted_at)
                                VALUES (?, ?, ?, ?)
                            ''', (date.today().isoformat(), recollection_text, 
                                  "Initial recollection from personality JSON", extracted_at))
                        
                        conn.commit()
                        logger.info(f"🧠 [DB] Initialized {len(all_recollections)} notable recollections from personality JSON")
                    else:
                        logger.info(f"🧠 [DB] No initial recollections found in personality JSON")
                
                conn.close()
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error initializing notable recollections: {e}")

    def register_interaction(self, user_id, user_name, interaction_type, context, channel_id=None, server_id=None, metadata=None):
        fecha = datetime.datetime.now().isoformat()
        meta_json = json.dumps(metadata) if metadata else None
        scheduled_for = (datetime.datetime.now() + datetime.timedelta(minutes=60)).isoformat()
        updated_at = datetime.datetime.now().isoformat()
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
                    ''', params)
                    # Programar actualización de recent memory con lógica anti-atasco
                    # Solo programar si no hay tareas pendientes existentes
                    cursor.execute('''
                        SELECT COUNT(*) FROM pending_recent_memory_updates 
                        WHERE status = 'pending'
                    ''')
                    pending_count = cursor.fetchone()[0]
                    
                    if pending_count == 0:
                        cursor.execute('''
                            INSERT INTO pending_recent_memory_updates
                            (scheduled_for, status, updated_at)
                            VALUES (?, ?, ?)
                        ''', (scheduled_for, "pending", updated_at))
                    else:
                        logger.info(f"[DB] Recent memory update already pending, skipping new task")
                    
                    # Programar actualización de relationship con retraso para evitar solapamiento
                    # Recent memory tiene prioridad, relationship se ejecuta 5 minutos después
                    from datetime import timedelta
                    relationship_delay = timedelta(minutes=5)
                    relationship_scheduled_for = (datetime.datetime.fromisoformat(scheduled_for.replace('Z', '+00:00')) + relationship_delay).isoformat()
                    
                    cursor.execute('''
                        SELECT COUNT(*) FROM pending_relationship_updates 
                        WHERE usuario_id = ? AND status = 'pending'
                    ''', (str(user_id),))
                    relationship_pending_count = cursor.fetchone()[0]
                    
                    if relationship_pending_count == 0:
                        cursor.execute('''
                            INSERT INTO pending_relationship_updates
                            (usuario_id, scheduled_for, status, updated_at)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(usuario_id) DO UPDATE SET
                                scheduled_for = excluded.scheduled_for,
                                status = excluded.status,
                                updated_at = excluded.updated_at
                        ''', (str(user_id), relationship_scheduled_for, "pending", updated_at))
                    else:
                        logger.info(f"[DB] Relationship memory update already pending for user {user_id}, skipping new task")
                    
                    logger.info(f"✅ Interaction registered: user_id={user_id}, type={interaction_type}, channel_id={channel_id}")
                    logger.info(f"🧠 [SCHEDULING] Recent memory: {scheduled_for}, Relationship: {relationship_scheduled_for} (5min delay)")
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
                
                # Check if channel_id column exists
                cursor.execute("PRAGMA table_info(interacciones)")
                columns = [row[1] for row in cursor.fetchall()]
                logger.info(f"🧠 [DB] Available columns: {columns}")
                
                if 'canal_id' in columns:
                    logger.info(f"🧠 [DB] Using canal_id filter for channel {channel_id}")
                    cursor.execute('''
                        SELECT usuario_id, usuario_nombre, contexto, metadata, fecha, tipo_interaccion
                        FROM interacciones
                        WHERE canal_id = ? AND fecha >= datetime('now', '-{} minutes')
                        ORDER BY fecha DESC
                        LIMIT ?
                    '''.format(within_minutes), (str(channel_id), max_interactions))
                else:
                    logger.info(f"🧠 [DB] No canal_id column, using fallback for channel {channel_id}")
                    # Fallback: try without channel_id filter (older databases)
                    cursor.execute('''
                        SELECT usuario_id, usuario_nombre, contexto, metadata, fecha, tipo_interaccion
                        FROM interacciones
                        WHERE fecha >= datetime('now', '-{} minutes')
                        ORDER BY fecha DESC
                        LIMIT ?
                    '''.format(within_minutes), (max_interactions,))
                
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
                
                # Check if channel_id column exists
                cursor.execute("PRAGMA table_info(interacciones)")
                columns = [row[1] for row in cursor.fetchall()]
                logger.info(f"🧠 [DB] Available columns: {columns}")
                
                if 'canal_id' in columns:
                    logger.info(f"🧠 [DB] Using canal_id filter for channel {channel_id}")
                    cursor.execute('''
                        SELECT usuario_id, usuario_nombre, contexto, metadata, fecha, tipo_interaccion
                        FROM interacciones
                        WHERE canal_id = ?
                        ORDER BY fecha DESC
                        LIMIT ?
                    ''', (str(channel_id), max_messages))
                else:
                    logger.info(f"🧠 [DB] No canal_id column, using fallback for channel {channel_id}")
                    # Fallback: try without channel_id filter (older databases)
                    cursor.execute('''
                        SELECT usuario_id, usuario_nombre, contexto, metadata, fecha, tipo_interaccion
                        FROM interacciones
                        ORDER BY fecha DESC
                        LIMIT ?
                    ''', (max_messages,))
                
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

    def get_daily_memory(self, memory_date=None):
        """Return the stored daily memory summary for the current server."""
        target_date = memory_date or date.today().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT summary
                    FROM daily_memory
                    WHERE memory_date = ?
                ''', (target_date,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    return row[0] or ""
                else:
                    return ""
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving daily memory: {e}")
            return ""

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

    def get_most_recent_daily_memory_record(self):
        """Return the most recent daily memory row for the current server, regardless of date."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT memory_date, summary, metadata, updated_at
                    FROM daily_memory
                    WHERE summary IS NOT NULL AND summary != ''
                    ORDER BY updated_at DESC
                    LIMIT 1
                ''')
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return None
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                return {
                    "memory_date": row["memory_date"],
                    "summary": row["summary"] or "",
                    "metadata": metadata,
                    "updated_at": row["updated_at"],
                }
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving most recent daily memory record: {e}")
            return None

    def get_daily_memory_record(self, memory_date=None):
        """Return the stored daily memory row for the current server."""
        target_date = memory_date or date.today().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT memory_date, summary, metadata, updated_at
                    FROM daily_memory
                    WHERE memory_date = ?
                ''', (target_date,))
                row = cursor.fetchone()
                conn.close()
                return dict(row) if row else None
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving daily memory record: {e}")
            return None

    def get_last_7_days_daily_memory(self):
        """Return the last 7 days of daily memory summaries for weekly personality evolution.
        
        Returns a list of dicts with memory_date, summary, and updated_at fields,
        ordered from oldest to newest (chronological order).
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # Get records from last 7 days, ordered chronologically (oldest first)
                cursor.execute('''
                    SELECT memory_date, summary, metadata, updated_at
                    FROM daily_memory
                    WHERE summary IS NOT NULL 
                        AND summary != '' 
                        AND summary != '[Error in internal task]'
                        AND memory_date >= date('now', '-7 days')
                    ORDER BY memory_date ASC
                    LIMIT 7
                ''')
                rows = cursor.fetchall()
                conn.close()
                
                memories = []
                for row in rows:
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    memories.append({
                        "memory_date": row["memory_date"],
                        "summary": row["summary"] or "",
                        "metadata": metadata,
                        "updated_at": row["updated_at"],
                    })
                return memories
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving last 7 days daily memory: {e}")
            return []

    def get_most_recent_memory_record(self):
        """Return the most recent stored recent memory row for the current server, regardless of date."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT memory_date, summary, metadata, updated_at, last_interaction_at
                    FROM recent_memory
                    WHERE 1=1
                    ORDER BY updated_at DESC
                    LIMIT 1
                ''', ())
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return None
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                return {
                    "memory_date": row["memory_date"],
                    "summary": row["summary"] or "",
                    "metadata": metadata,
                    "updated_at": row["updated_at"],
                    "last_interaction_at": row["last_interaction_at"],
                }
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving most recent memory record: {e}")
            return None

    def get_recent_memory_record(self, memory_date=None):
        """Return the stored recent memory row for the current server."""
        target_date = memory_date or date.today().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT memory_date, summary, metadata, updated_at, last_interaction_at
                    FROM recent_memory
                    WHERE memory_date = ?
                ''', (target_date,))
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return None
                metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                return {
                    "memory_date": row["memory_date"],
                    "summary": row["summary"] or "",
                    "metadata": metadata,
                    "updated_at": row["updated_at"],
                    "last_interaction_at": row["last_interaction_at"],
                }
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving recent memory record: {e}")
            return None

    def schedule_recent_memory_refresh(self, delay_minutes=60):
        scheduled_for = (datetime.datetime.now() + datetime.timedelta(minutes=delay_minutes)).isoformat()
        updated_at = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO pending_recent_memory_updates
                    (scheduled_for, status, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(scheduled_for) DO UPDATE SET
                        scheduled_for = CASE
                            WHEN pending_recent_memory_updates.status = 'pending' THEN pending_recent_memory_updates.scheduled_for
                            ELSE excluded.scheduled_for
                        END,
                        status = CASE
                            WHEN pending_recent_memory_updates.status = 'pending' THEN pending_recent_memory_updates.status
                            ELSE excluded.status
                        END,
                        updated_at = excluded.updated_at
                ''', (scheduled_for, "pending", updated_at))
                conn.commit()
                conn.close()
                return scheduled_for
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error scheduling recent memory refresh: {e}")
            return None

    def get_pending_recent_memory_refresh(self):
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT scheduled_for, status, updated_at
                    FROM pending_recent_memory_updates
                    WHERE 1=1
                ''', ())
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return None
                return dict(row)
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error getting pending recent memory refresh: {e}")
            return None

    def mark_recent_memory_refresh_completed(self):
        updated_at = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE pending_recent_memory_updates
                    SET status = ?, updated_at = ?
                    WHERE 1=1
                ''', ("completed", updated_at))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error completing recent memory refresh: {e}")
            return False

    def get_due_pending_recent_memory_refreshes(self, now_iso=None):
        current_time = now_iso or datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT scheduled_for, status, updated_at
                    FROM pending_recent_memory_updates
                    WHERE status = ? AND scheduled_for <= ?
                ''', ("pending", current_time))
                rows = cursor.fetchall()
                conn.close()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving due recent memory refreshes: {e}")
            return []

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

    def upsert_daily_memory(self, summary, memory_date=None, metadata=None):
        """Create or update the daily memory summary for the current server."""
        target_date = memory_date or date.today().isoformat()
        updated_at = datetime.datetime.now().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO daily_memory (memory_date, summary, metadata, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(memory_date) DO UPDATE SET
                        summary = excluded.summary,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at
                ''', (target_date, summary, metadata_json, updated_at))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error upserting daily memory: {e}")
            return False

    def upsert_recent_memory(self, summary, memory_date=None, last_interaction_at=None, metadata=None):
        """Create or update the recent memory summary for the current server."""
        target_date = memory_date or date.today().isoformat()
        updated_at = datetime.datetime.now().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO recent_memory
                    (memory_date, summary, metadata, updated_at, last_interaction_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(memory_date) DO UPDATE SET
                        summary = excluded.summary,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at,
                        last_interaction_at = excluded.last_interaction_at
                ''', (
                    target_date,
                    summary,
                    metadata_json,
                    updated_at,
                    last_interaction_at
                ))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error upserting recent memory: {e}")
            return False

    def get_user_relationship_memory(self, user_id):
        """Return the stored relationship summary for a user."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT summary, metadata, updated_at, last_interaction_at
                    FROM user_relationship_memory
                    WHERE usuario_id = ?
                ''', (str(user_id),))
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return {"summary": "", "updated_at": None, "last_interaction_at": None, "metadata": {}}
                return {
                    "summary": row["summary"] or "",
                    "updated_at": row["updated_at"],
                    "last_interaction_at": row["last_interaction_at"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                }
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving relationship memory: {e}")
            return {"summary": "", "updated_at": None, "last_interaction_at": None, "metadata": {}}

    def get_user_relationship_daily_memory(self, user_id, memory_date=None):
        """Return the stored daily relationship summary for a user."""
        target_date = memory_date or date.today().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT summary, metadata, updated_at
                    FROM user_relationship_daily_memory
                    WHERE memory_date = ? AND usuario_id = ?
                ''', (target_date, str(user_id)))
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return None
                return {
                    "summary": row["summary"] or "",
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "updated_at": row["updated_at"],
                }
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving daily relationship memory: {e}")
            return None

    def get_latest_user_relationship_daily_memory(self, user_id, before_date=None):
        """Return the most recent daily relationship snapshot for a user."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if before_date:
                    cursor.execute('''
                        SELECT memory_date, summary, metadata, updated_at
                        FROM user_relationship_daily_memory
                        WHERE usuario_id = ? AND memory_date <= ?
                        ORDER BY memory_date DESC
                        LIMIT 1
                    ''', (str(user_id), before_date))
                else:
                    cursor.execute('''
                        SELECT memory_date, summary, metadata, updated_at
                        FROM user_relationship_daily_memory
                        WHERE usuario_id = ?
                        ORDER BY memory_date DESC
                        LIMIT 1
                    ''', (str(user_id),))
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return None
                return {
                    "memory_date": row["memory_date"],
                    "summary": row["summary"] or "",
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "updated_at": row["updated_at"],
                }
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving latest daily relationship memory: {e}")
            return None

    def upsert_user_relationship_memory(self, user_id, summary, last_interaction_at=None, metadata=None):
        """Create or update temporary relationship memory state for a user."""
        updated_at = datetime.datetime.now().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO user_relationship_memory
                    (usuario_id, summary, metadata, updated_at, last_interaction_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(usuario_id) DO UPDATE SET
                        summary = excluded.summary,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at,
                        last_interaction_at = excluded.last_interaction_at
                ''', (
                    str(user_id),
                    summary,
                    metadata_json,
                    updated_at,
                    last_interaction_at,
                ))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error upserting relationship memory: {e}")
            return False

    def upsert_user_relationship_daily_memory(self, user_id, summary, memory_date=None, metadata=None):
        """Create or update daily relationship memory snapshot for a user."""
        target_date = memory_date or date.today().isoformat()
        updated_at = datetime.datetime.now().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO user_relationship_daily_memory
                    (memory_date, usuario_id, summary, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(memory_date, usuario_id) DO UPDATE SET
                        summary = excluded.summary,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at
                ''', (
                    target_date,
                    str(user_id),
                    summary,
                    metadata_json,
                    updated_at,
                ))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error upserting daily relationship memory: {e}")
            return False

    def clear_user_relationship_memory_state(self, user_id):
        """Delete the temporary relationship memory state for a user."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM user_relationship_memory
                    WHERE usuario_id = ?
                ''', (str(user_id),))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error clearing relationship memory state: {e}")
            return False

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

    def schedule_relationship_refresh(self, user_id, delay_minutes=60):
        """Mark a user relationship summary for refresh after inactivity."""
        scheduled_for = (datetime.datetime.now() + datetime.timedelta(minutes=delay_minutes)).isoformat()
        updated_at = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO pending_relationship_updates
                    (usuario_id, scheduled_for, status, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(usuario_id) DO UPDATE SET
                        scheduled_for = CASE
                            WHEN pending_relationship_updates.status = 'pending' THEN pending_relationship_updates.scheduled_for
                            ELSE excluded.scheduled_for
                        END,
                        status = CASE
                            WHEN pending_relationship_updates.status = 'pending' THEN pending_relationship_updates.status
                            ELSE excluded.status
                        END,
                        updated_at = excluded.updated_at
                ''', (str(user_id), scheduled_for, "pending", updated_at))
                conn.commit()
                conn.close()
                return scheduled_for
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error scheduling relationship refresh: {e}")
            return None

    def get_pending_relationship_refresh(self, user_id):
        """Return scheduled relationship refresh state for a user."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT scheduled_for, status, updated_at
                    FROM pending_relationship_updates
                    WHERE usuario_id = ?
                ''', (str(user_id),))
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return None
                return dict(row)
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error getting pending relationship refresh: {e}")
            return None

    def mark_relationship_refresh_completed(self, user_id):
        """Mark a pending relationship refresh as completed."""
        updated_at = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE pending_relationship_updates
                    SET status = ?, updated_at = ?
                    WHERE usuario_id = ?
                ''', ("completed", updated_at, str(user_id)))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error completing relationship refresh: {e}")
            return False

    def get_due_pending_relationship_refreshes(self, now_iso=None):
        """Return all pending relationship refreshes that are due."""
        current_time = now_iso or datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT usuario_id, scheduled_for, status, updated_at
                    FROM pending_relationship_updates
                    WHERE 1=1 AND status = ? AND scheduled_for <= ?
                    ORDER BY scheduled_for ASC
                ''', ( "pending", current_time))
                rows = cursor.fetchall()
                conn.close()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving due relationship refreshes: {e}")
            return []

    def clear_stale_relationship_memory_states(self, keep_date=None):
        """Delete temporary relationship states that belong to older days."""
        target_date = keep_date or date.today().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                # Simple approach: use string formatting for date comparison (safe as target_date is controlled)
                cursor.execute(f'''
                    DELETE FROM user_relationship_memory
                    WHERE last_interaction_at IS NOT NULL
                    AND date(last_interaction_at) < date('{target_date}')
                ''')
                deleted = cursor.rowcount
                conn.commit()
                conn.close()
                return deleted
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error clearing stale relationship states: {e}")
            return 0

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
                cursor.execute('DROP TABLE IF EXISTS peticiones_oro')
                cursor.execute('DROP TABLE IF EXISTS busquedas_anillo')
                cursor.execute('DROP TABLE IF EXISTS noticias_leidas')
                conn.commit()
                logger.info(f"🧹 Cleaned interactions before {deadline} and duplicate tables")
                return cursor.rowcount

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

    def add_notable_recollection(self, recollection_text: str, memory_date: str = None, source_paragraph: str = None) -> int:
        """Add a new notable recollection extracted from daily synthesis."""
        target_date = memory_date or date.today().isoformat()
        extracted_at = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO notable_recollections
                    (memory_date, recollection_text, source_paragraph, extracted_at)
                    VALUES (?, ?, ?, ?)
                ''', (target_date, recollection_text, source_paragraph, extracted_at))
                recollection_id = cursor.lastrowid
                conn.commit()
                conn.close()
                logger.info(f"🧠 [MEMORY] Added notable recollection id={recollection_id}")
                return recollection_id
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error adding notable recollection: {e}")
            return 0

    def get_random_notable_recollection(self) -> dict | None:
        """Get a random notable recollection for injection into synthesis."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, recollection_text, memory_date, used_count
                    FROM notable_recollections
                    WHERE 1=1
                    ORDER BY RANDOM()
                    LIMIT 1
                ''', ())
                row = cursor.fetchone()
                conn.close()
                if row:
                    return {
                        "id": row["id"],
                        "recollection_text": row["recollection_text"],
                        "memory_date": row["memory_date"],
                        "used_count": row["used_count"],
                    }
                return None
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving random notable recollection: {e}")
            return None

    def increment_recollection_usage(self, recollection_id: int) -> bool:
        """Increment the usage counter for a recollection when it's injected."""
        used_at = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE notable_recollections
                    SET used_count = used_count + 1,
                        last_used_at = ?
                    WHERE id = ?
                ''', (used_at, recollection_id))
                conn.commit()
                updated = cursor.rowcount > 0
                conn.close()
                return updated
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error incrementing recollection usage: {e}")
            return False

    def count_notable_recollections(self) -> int:
        """Count total notable recollections for this server."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM notable_recollections
                    WHERE 1=1
                ''', ())
                count = cursor.fetchone()[0]
                conn.close()
                return count
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error counting notable recollections: {e}")
            return 0

    def get_notable_recollections_for_date(self, memory_date: str = None) -> list:
        """Get all notable recollections extracted on a specific date."""
        target_date = memory_date or date.today().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, recollection_text, source_paragraph, extracted_at
                    FROM notable_recollections
                    WHERE 1=1 AND memory_date = ?
                ''', ( target_date))
                rows = cursor.fetchall()
                conn.close()
                return [
                    {
                        "id": row["id"],
                        "recollection_text": row["recollection_text"],
                        "source_paragraph": row["source_paragraph"],
                        "extracted_at": row["extracted_at"],
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving notable recollections for date: {e}")
            return []
    
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

def get_db_instance(server_id: str = "default") -> AgentDatabase:
    """Get or create a database instance for a specific server."""
    global db
    # Only use active server if no specific server_id provided
    if server_id == "default":
        active = get_server_id()
        if active:
            server_id = active
    if server_id not in _db_instances:
        _db_instances[server_id] = AgentDatabase(server_id)
    return _db_instances[server_id]

def invalidate_db_instance(server_id: str = None):
    """Invalidate cached database instance for a server.
    
    Call this after personality change so the next get_db_instance()
    creates a new AgentDatabase pointing to the correct personality db file.
    
    Args:
        server_id: Server ID to invalidate, or None to clear all.
    """
    global _db_instances, db, _current_server_id
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

def get_all_server_keys() -> list[str]:
    """Get all server keys from the database instances cache."""
    return list(_db_instances.keys())

db = None
_current_server_id = None

def get_global_db(server_id: str = None, use_default_for_roles: bool = False) -> AgentDatabase:
    """Get the global DB instance for the current server."""
    global db, _current_server_id
    
    if server_id is None:
        active = _current_server_id or get_server_id()
        if active:
            server_id = active
        elif use_default_for_roles and os.getenv("ROLE_AGENT_PROCESS"):
            server_id = "default"
        else:
            server_id = "default"
    
    if db is None or _current_server_id != server_id:
        db = get_db_instance(server_id)
        _current_server_id = server_id
        logger.debug(f"🗄️ [DB] Global database initialized for server: {server_id}")
    
    return db

def set_current_server(server_id: str):
    """Set the current server for the global DB."""
    global _current_server_id
    _current_server_id = server_id
    if server_id:
        persist_active_server_id(server_id)
        # Reload personality to load server-specific copy if available
        try:
            from agent_engine import reload_personality
            reload_personality()
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
    centralized_roles = {'beggar', 'trickster', 'mc', 'dice_game', 'nordic_runes', 'banker', 'treasure_hunter'}
    
    if db_type in centralized_roles:
        # Return path to the centralized roles.db with personality-specific naming
        from agent_roles_db import get_roles_db_path
        return str(get_roles_db_path(server_id))
    
    personality_name = get_personality_name(server_id)

    # Map database types to filenames (only for non-centralized roles)
    db_filenames = {
        'news_watcher': f'watcher_{personality_name}',
    }

    db_name = db_filenames.get(db_type, f'{db_type}_{personality_name}')
    return str(get_server_db_path_fallback(server_id, db_name))

# --- FATIGUE DATABASE SYSTEM ---

def get_fatigue_db_path(server_id: str) -> str:
    """
    Get path for fatigue database.

    Args:
        server_id: Server ID

    Returns:
        str: Full path to fatigue database
    """
    personality_name = get_personality_name(server_id)
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
                # Insert server record if it doesn't exist
                db.execute('''
                    INSERT INTO fatigue 
                    (user_id, user_name, daily_requests, total_requests, last_request_date,
                     hourly_requests, last_hour_timestamp, burst_requests, last_burst_timestamp)
                    VALUES (?, ?, 1, 1, ?, 1, ?, 1, ?)
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
