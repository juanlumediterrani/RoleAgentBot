import sqlite3
import datetime
import json
import os
import threading
from pathlib import Path
from datetime import date
from agent_logging import get_logger

logger = get_logger('db')

_ACTIVE_SERVER_FILE = Path(__file__).parent / ".active_server"
DB_DIR = Path(__file__).parent / 'databases'
DB_DIR.mkdir(parents=True, exist_ok=True)


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

def _resolve_server_storage_id(server_name: str | None) -> str | None:
    candidate = str(server_name).strip() if server_name is not None else ""
    if candidate and candidate.isdigit():
        return candidate

    active = get_active_server_name()
    if active and active.isdigit():
        return active

    return None

def get_server_db_path(server_name: str, db_name: str = None) -> Path:
    """
    Genera ruta de base de datos para un servidor específico.
    
    Args:
        server_name: Nombre del servidor (sanitizado)
        db_name: Nombre de la base de datos (opcional)
    
    Returns:
        Path: Ruta completa al archivo de base de datos
    """
    server_storage_id = _resolve_server_storage_id(server_name)
    
    # Directorio base
    server_dir = DB_DIR / server_storage_id if server_storage_id else DB_DIR
    try:
        server_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        # Si no podemos crear el directorio del servidor, usar el directorio base
        print(f"⚠️ No se puede crear directorio de BD {server_dir}: {e}")
        print(f"🗄️ Usando directorio base: {DB_DIR}")
        server_dir = DB_DIR
    
    # Usar nombre de BD si se proporciona, si no el global
    db_filename = db_name or get_personality_name()
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

def get_server_db_path_fallback(server_name: str, db_name: str) -> Path:
    """
    Version with fallback for Docker environments or restricted permissions.
    """
    server_storage_id = _resolve_server_storage_id(server_name)
    resolved_server_name = server_storage_id or server_name

    # Try local path first
    local_path = get_server_db_path(resolved_server_name, db_name)
    
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

def get_server_log_path(server_name: str, log_name: str) -> Path:
    """
    Generate log path for a specific server.
    
    Args:
        server_name: Server name (sanitized)
        log_name: Log file name
    
    Returns:
        Path: Full path to the log file
    """
    server_storage_id = _resolve_server_storage_id(server_name)
    
    # Base directory
    base_dir = Path(__file__).parent
    server_dir = base_dir / "logs"
    if server_storage_id:
        server_dir = server_dir / server_storage_id
    
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
        from agent_engine import PERSONALITY
        return PERSONALITY.get("name", "agent").lower()
    except:
        return "agent"

# Path and limits configuration
BASE_DIR = Path(__file__).parent
HISTORIAL_LIMITE = 5

class AgentDatabase:
    def __init__(self, server_name: str = "default", db_path: Path = None):
        self.server_name = server_name
        if db_path is None:
            # Use personality-specific database name
            personality_name = get_personality_name()
            db_name = f"agent_{personality_name}"
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
            server_storage_id = _resolve_server_storage_id(self.server_name)
            if server_storage_id:
                fallback_dir = fallback_dir / server_storage_id
            fallback_dir.mkdir(parents=True, exist_ok=True)
            
            fallback_db = fallback_dir / f'agent_{get_personality_name()}.db'
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
                        memory_date TEXT NOT NULL,
                        server_name TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        metadata TEXT,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (memory_date, server_name)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS recent_memory (
                        memory_date TEXT NOT NULL,
                        server_name TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        metadata TEXT,
                        updated_at DATETIME NOT NULL,
                        last_interaction_at DATETIME,
                        PRIMARY KEY (memory_date, server_name)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_relationship_memory (
                        usuario_id TEXT NOT NULL,
                        server_name TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        metadata TEXT,
                        updated_at DATETIME NOT NULL,
                        last_interaction_at DATETIME,
                        PRIMARY KEY (usuario_id, server_name)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_relationship_daily_memory (
                        memory_date TEXT NOT NULL,
                        usuario_id TEXT NOT NULL,
                        server_name TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        metadata TEXT,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (memory_date, usuario_id, server_name)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pending_relationship_updates (
                        usuario_id TEXT NOT NULL,
                        server_name TEXT NOT NULL,
                        scheduled_for DATETIME NOT NULL,
                        status TEXT NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (usuario_id, server_name)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS pending_recent_memory_updates (
                        server_name TEXT NOT NULL,
                        scheduled_for DATETIME NOT NULL,
                        status TEXT NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (server_name)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS notable_recollections (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        server_name TEXT NOT NULL,
                        memory_date TEXT NOT NULL,
                        recollection_text TEXT NOT NULL,
                        source_paragraph TEXT,
                        extracted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        used_count INTEGER DEFAULT 0,
                        last_used_at DATETIME
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_recollections_server ON notable_recollections (server_name)')
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
                    WHERE server_name = ?
                ''', (self.server_name,))
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
                                (server_name, memory_date, recollection_text, source_paragraph, extracted_at)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (self.server_name, date.today().isoformat(), recollection_text, 
                                  "Initial recollection from personality JSON", extracted_at))
                        
                        conn.commit()
                        logger.info(f"🧠 [DB] Initialized {len(all_recollections)} notable recollections from personality JSON")
                    else:
                        logger.info(f"🧠 [DB] No initial recollections found in personality JSON")
                
                conn.close()
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error initializing notable recollections: {e}")

    def registrar_interaccion(self, usuario_id, usuario_nombre, tipo_interaccion, contexto, canal_id=None, servidor_id=None, metadata=None):
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
                    # Programar actualización de recent memory con lógica anti-atasco
                    cursor.execute('''
                        INSERT INTO pending_recent_memory_updates
                        (server_name, scheduled_for, status, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(server_name) DO UPDATE SET
                            scheduled_for = CASE
                                WHEN pending_recent_memory_updates.status = 'pending' 
                                     AND datetime(pending_recent_memory_updates.scheduled_for) < datetime('now', '-2 hours')
                                THEN excluded.scheduled_for
                                ELSE pending_recent_memory_updates.scheduled_for
                            END,
                            updated_at = CASE
                                WHEN pending_recent_memory_updates.status = 'pending' 
                                     AND datetime(pending_recent_memory_updates.scheduled_for) < datetime('now', '-2 hours')
                                THEN excluded.updated_at
                                ELSE pending_recent_memory_updates.updated_at
                            END
                    ''', (self.server_name, scheduled_for, "pending", updated_at))
                    
                    # Programar actualización de relationship con retraso para evitar solapamiento
                    # Recent memory tiene prioridad, relationship se ejecuta 5 minutos después
                    from datetime import timedelta
                    relationship_delay = timedelta(minutes=5)
                    relationship_scheduled_for = (datetime.datetime.fromisoformat(scheduled_for.replace('Z', '+00:00')) + relationship_delay).isoformat()
                    
                    cursor.execute('''
                        INSERT INTO pending_relationship_updates
                        (usuario_id, server_name, scheduled_for, status, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(usuario_id, server_name) DO UPDATE SET
                            scheduled_for = CASE
                                WHEN pending_relationship_updates.status = 'pending' THEN pending_relationship_updates.scheduled_for
                                ELSE excluded.scheduled_for
                            END,
                            status = CASE
                                WHEN pending_relationship_updates.status = 'pending' THEN pending_relationship_updates.status
                                ELSE excluded.status
                            END,
                            updated_at = excluded.updated_at
                    ''', (str(usuario_id), self.server_name, relationship_scheduled_for, "pending", updated_at))
                    
                    logger.info(f"✅ Interaction registered: user_id={usuario_id}, type={tipo_interaccion}, channel_id={canal_id}")
                    logger.info(f"🧠 [SCHEDULING] Recent memory: {scheduled_for}, Relationship: {relationship_scheduled_for} (5min delay)")
                    return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error registering interaction (user_id={usuario_id}, type={tipo_interaccion}): {e}")
            return False

    def get_user_history(self, usuario_id, limite=HISTORIAL_LIMITE):
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
                    historial.append({
                        "humano": row['contexto'],
                        "bot": meta.get('response', '') or meta.get('greeting', '') or meta.get('respuesta', '') or meta.get('saludo', '')
                    })
                return list(reversed(historial))
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving history: {e}")
            return []

    def get_recent_user_history(self, usuario_id, minutos=3):
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
                    historial.append({
                        "humano": row['contexto'],
                        "bot": meta.get('response', '') or meta.get('greeting', '') or meta.get('respuesta', '') or meta.get('saludo', '')
                    })
                return list(reversed(historial))
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error al recuperar historial reciente: {e}")
            return []

    
    def get_last_dialogue_window(self, usuario_id, max_messages=10):
        """Return last 10 human/bot dialogue pairs for prompt injection regardless of time window."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT contexto, metadata, fecha
                    FROM interacciones
                    WHERE usuario_id = ?
                    ORDER BY fecha DESC
                    LIMIT ?
                ''', (str(usuario_id), max_messages))

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
        fecha_limite = (datetime.datetime.now() - datetime.timedelta(minutes=within_minutes)).isoformat()
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
                        WHERE canal_id = ? AND fecha >= ?
                        ORDER BY fecha DESC
                        LIMIT ?
                    ''', (str(channel_id), fecha_limite, max_interactions))
                else:
                    logger.info(f"🧠 [DB] No canal_id column, using fallback for channel {channel_id}")
                    # Fallback: try without channel_id filter (older databases)
                    cursor.execute('''
                        SELECT usuario_id, usuario_nombre, contexto, metadata, fecha, tipo_interaccion
                        FROM interacciones
                        WHERE fecha >= ?
                        ORDER BY fecha DESC
                        LIMIT ?
                    ''', (fecha_limite, max_interactions))
                
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
                    WHERE memory_date = ? AND server_name = ?
                ''', (target_date, self.server_name))
                row = cursor.fetchone()
                conn.close()
                return row[0] if row else ""
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving daily memory: {e}")
            return ""

    def get_last_interaction(self, usuario_id):
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
                ''', (str(usuario_id),))

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
                    WHERE server_name = ? AND summary IS NOT NULL AND summary != ''
                    ORDER BY updated_at DESC
                    LIMIT 1
                ''', (self.server_name,))
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
                    WHERE memory_date = ? AND server_name = ?
                ''', (target_date, self.server_name))
                row = cursor.fetchone()
                conn.close()
                return dict(row) if row else None
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error retrieving daily memory record: {e}")
            return None

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
                    WHERE server_name = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                ''', (self.server_name,))
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
                    WHERE memory_date = ? AND server_name = ?
                ''', (target_date, self.server_name))
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
                    (server_name, scheduled_for, status, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(server_name) DO UPDATE SET
                        scheduled_for = CASE
                            WHEN pending_recent_memory_updates.status = 'pending' THEN pending_recent_memory_updates.scheduled_for
                            ELSE excluded.scheduled_for
                        END,
                        status = CASE
                            WHEN pending_recent_memory_updates.status = 'pending' THEN pending_recent_memory_updates.status
                            ELSE excluded.status
                        END,
                        updated_at = excluded.updated_at
                ''', (self.server_name, scheduled_for, "pending", updated_at))
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
                    WHERE server_name = ?
                ''', (self.server_name,))
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
                    WHERE server_name = ?
                ''', ("completed", updated_at, self.server_name))
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
                    SELECT server_name, scheduled_for, status, updated_at
                    FROM pending_recent_memory_updates
                    WHERE server_name = ? AND status = ? AND scheduled_for <= ?
                ''', (self.server_name, "pending", current_time))
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
                    INSERT INTO daily_memory (memory_date, server_name, summary, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(memory_date, server_name) DO UPDATE SET
                        summary = excluded.summary,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at
                ''', (target_date, self.server_name, summary, metadata_json, updated_at))
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
                    (memory_date, server_name, summary, metadata, updated_at, last_interaction_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(memory_date, server_name) DO UPDATE SET
                        summary = excluded.summary,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at,
                        last_interaction_at = excluded.last_interaction_at
                ''', (
                    target_date,
                    self.server_name,
                    summary,
                    metadata_json,
                    updated_at,
                    last_interaction_at,
                ))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error upserting recent memory: {e}")
            return False

    def get_user_relationship_memory(self, usuario_id):
        """Return the stored relationship summary for a user."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT summary, metadata, updated_at, last_interaction_at
                    FROM user_relationship_memory
                    WHERE usuario_id = ? AND server_name = ?
                ''', (str(usuario_id), self.server_name))
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

    def get_user_relationship_daily_memory(self, usuario_id, memory_date=None):
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
                    WHERE memory_date = ? AND usuario_id = ? AND server_name = ?
                ''', (target_date, str(usuario_id), self.server_name))
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

    def get_latest_user_relationship_daily_memory(self, usuario_id, before_date=None):
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
                        WHERE usuario_id = ? AND server_name = ? AND memory_date <= ?
                        ORDER BY memory_date DESC
                        LIMIT 1
                    ''', (str(usuario_id), self.server_name, before_date))
                else:
                    cursor.execute('''
                        SELECT memory_date, summary, metadata, updated_at
                        FROM user_relationship_daily_memory
                        WHERE usuario_id = ? AND server_name = ?
                        ORDER BY memory_date DESC
                        LIMIT 1
                    ''', (str(usuario_id), self.server_name))
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

    def upsert_user_relationship_memory(self, usuario_id, summary, last_interaction_at=None, metadata=None):
        """Create or update temporary relationship memory state for a user."""
        updated_at = datetime.datetime.now().isoformat()
        metadata_json = json.dumps(metadata) if metadata else None
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO user_relationship_memory
                    (usuario_id, server_name, summary, metadata, updated_at, last_interaction_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(usuario_id, server_name) DO UPDATE SET
                        summary = excluded.summary,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at,
                        last_interaction_at = excluded.last_interaction_at
                ''', (
                    str(usuario_id),
                    self.server_name,
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

    def upsert_user_relationship_daily_memory(self, usuario_id, summary, memory_date=None, metadata=None):
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
                    (memory_date, usuario_id, server_name, summary, metadata, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(memory_date, usuario_id, server_name) DO UPDATE SET
                        summary = excluded.summary,
                        metadata = excluded.metadata,
                        updated_at = excluded.updated_at
                ''', (
                    target_date,
                    str(usuario_id),
                    self.server_name,
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

    def clear_user_relationship_memory_state(self, usuario_id):
        """Delete the temporary relationship memory state for a user."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM user_relationship_memory
                    WHERE usuario_id = ? AND server_name = ?
                ''', (str(usuario_id), self.server_name))
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error clearing relationship memory state: {e}")
            return False

    def get_user_interactions_since(self, usuario_id, since_iso=None, limit=25):
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
                    ''', (str(usuario_id), since_iso, limit))
                else:
                    cursor.execute('''
                        SELECT contexto, metadata, fecha, tipo_interaccion, usuario_nombre
                        FROM interacciones
                        WHERE usuario_id = ?
                        ORDER BY fecha DESC
                        LIMIT ?
                    ''', (str(usuario_id), limit))
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

    def schedule_relationship_refresh(self, usuario_id, delay_minutes=60):
        """Mark a user relationship summary for refresh after inactivity."""
        scheduled_for = (datetime.datetime.now() + datetime.timedelta(minutes=delay_minutes)).isoformat()
        updated_at = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO pending_relationship_updates
                    (usuario_id, server_name, scheduled_for, status, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(usuario_id, server_name) DO UPDATE SET
                        scheduled_for = CASE
                            WHEN pending_relationship_updates.status = 'pending' THEN pending_relationship_updates.scheduled_for
                            ELSE excluded.scheduled_for
                        END,
                        status = CASE
                            WHEN pending_relationship_updates.status = 'pending' THEN pending_relationship_updates.status
                            ELSE excluded.status
                        END,
                        updated_at = excluded.updated_at
                ''', (str(usuario_id), self.server_name, scheduled_for, "pending", updated_at))
                conn.commit()
                conn.close()
                return scheduled_for
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error scheduling relationship refresh: {e}")
            return None

    def get_pending_relationship_refresh(self, usuario_id):
        """Return scheduled relationship refresh state for a user."""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT scheduled_for, status, updated_at
                    FROM pending_relationship_updates
                    WHERE usuario_id = ? AND server_name = ?
                ''', (str(usuario_id), self.server_name))
                row = cursor.fetchone()
                conn.close()
                if not row:
                    return None
                return dict(row)
        except Exception as e:
            logger.exception(f"⚠️ [DB] Error getting pending relationship refresh: {e}")
            return None

    def mark_relationship_refresh_completed(self, usuario_id):
        """Mark a pending relationship refresh as completed."""
        updated_at = datetime.datetime.now().isoformat()
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE pending_relationship_updates
                    SET status = ?, updated_at = ?
                    WHERE usuario_id = ? AND server_name = ?
                ''', ("completed", updated_at, str(usuario_id), self.server_name))
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
                    WHERE server_name = ? AND status = ? AND scheduled_for <= ?
                    ORDER BY scheduled_for ASC
                ''', (self.server_name, "pending", current_time))
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
                cursor.execute('''
                    DELETE FROM user_relationship_memory
                    WHERE server_name = ?
                    AND last_interaction_at IS NOT NULL
                    AND date(last_interaction_at) < ?
                ''', (self.server_name, target_date))
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
                    (server_name, memory_date, recollection_text, source_paragraph, extracted_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (self.server_name, target_date, recollection_text, source_paragraph, extracted_at))
                recollection_id = cursor.lastrowid
                conn.commit()
                conn.close()
                logger.info(f"🧠 [MEMORY] Added notable recollection id={recollection_id} for server={self.server_name}")
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
                    WHERE server_name = ?
                    ORDER BY RANDOM()
                    LIMIT 1
                ''', (self.server_name,))
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
                    WHERE id = ? AND server_name = ?
                ''', (used_at, recollection_id, self.server_name))
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
                    WHERE server_name = ?
                ''', (self.server_name,))
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
                    WHERE server_name = ? AND memory_date = ?
                ''', (self.server_name, target_date))
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
    resolved_server_id = _resolve_server_storage_id(server_name)
    _current_server_name = resolved_server_id or _current_server_name or "default"
    if resolved_server_id:
        persist_active_server_name(resolved_server_id)

def get_database_path(server_name: str, db_type: str) -> str:
    """
    Get database path for role-specific databases.
    
    Args:
        server_name: Server name
        db_type: Database type (banker, news_watcher, dice_game, etc.)
    
    Returns:
        str: Full path to the database file
    """
    # Roles that have been migrated to centralized roles.db system
    centralized_roles = {'beggar', 'trickster', 'mc', 'dice_game', 'nordic_runes', 'banker', 'treasure_hunter'}
    
    if db_type in centralized_roles:
        # Return path to the centralized roles.db with personality-specific naming
        from agent_roles_db import get_roles_db_path
        return str(get_roles_db_path(server_name))
    
    personality_name = get_personality_name()
    
    # Map database types to filenames (only for non-centralized roles)
    db_filenames = {
        'news_watcher': f'watcher_{personality_name}', 
    }
    
    db_name = db_filenames.get(db_type, f'{db_type}_{personality_name}')
    return str(get_server_db_path_fallback(server_name, db_name))

# --- FATIGUE DATABASE SYSTEM ---

def get_fatigue_db_path(server_name: str) -> str:
    """
    Get path for fatigue database.
    
    Args:
        server_name: Server name
        
    Returns:
        str: Full path to fatigue database
    """
    personality_name = get_personality_name()
    db_name = f"fatigue_{personality_name}"
    return str(get_server_db_path(server_name, db_name))

def init_fatigue_db(server_name: str) -> sqlite3.Connection:
    """
    Initialize fatigue database for a server.
    
    Args:
        server_name: Server name
        
    Returns:
        sqlite3.Connection: Database connection
    """
    db_path = get_fatigue_db_path(server_name)
    db = sqlite3.connect(db_path, timeout=30.0)
    
    # Create fatigue table if it doesn't exist
    db.execute('''
        CREATE TABLE IF NOT EXISTS fatigue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            user_name TEXT,
            daily_requests INTEGER DEFAULT 0,
            total_requests INTEGER DEFAULT 0,
            last_request_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id)
        )
    ''')
    
    # Create server row if it doesn't exist
    server_id = f"server_{server_name}"
    today = str(date.today())
    
    db.execute('''
        INSERT OR IGNORE INTO fatigue 
        (user_id, user_name, daily_requests, total_requests, last_request_date)
        VALUES (?, ?, 0, 0, ?)
    ''', (server_id, f"Server_{server_name}", today))
    
    db.commit()
    return db

def increment_fatigue_count(server_name: str, user_id: str, user_name: str = None) -> tuple[int, int]:
    """
    Increment fatigue count for a user and server.
    
    Args:
        server_name: Server name
        user_id: User ID (or "server_{server_name}" for server total)
        user_name: User name (optional)
        
    Returns:
        tuple[int, int]: (daily_requests, total_requests) after increment
    """
    db = init_fatigue_db(server_name)
    today = str(date.today())
    
    try:
        # Get current stats
        cursor = db.execute('''
            SELECT daily_requests, total_requests, last_request_date 
            FROM fatigue WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        
        if row:
            current_daily, current_total, last_date = row
            
            # Reset daily count if date changed
            if last_date != today:
                new_daily = 1
            else:
                new_daily = current_daily + 1
                
            new_total = current_total + 1
            
            # Update user record
            db.execute('''
                UPDATE fatigue 
                SET daily_requests = ?, total_requests = ?, 
                    last_request_date = ?, updated_at = CURRENT_TIMESTAMP,
                    user_name = COALESCE(?, user_name)
                WHERE user_id = ?
            ''', (new_daily, new_total, today, user_name, user_id))
        else:
            # Insert new user record
            new_daily = 1
            new_total = 1
            
            db.execute('''
                INSERT INTO fatigue 
                (user_id, user_name, daily_requests, total_requests, last_request_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, user_name or f"User_{user_id}", new_daily, new_total, today))
        
        # Also increment server total if this is a user request (avoid recursion)
        if not user_id.startswith("server_"):
            server_id = f"server_{server_name}"
            # Direct server increment without recursion
            cursor = db.execute('''
                SELECT daily_requests, total_requests, last_request_date 
                FROM fatigue WHERE user_id = ?
            ''', (server_id,))
            
            server_row = cursor.fetchone()
            
            if server_row:
                server_daily, server_total, server_last_date = server_row
                
                # Reset server daily count if date changed
                if server_last_date != today:
                    new_server_daily = 1
                else:
                    new_server_daily = server_daily + 1
                    
                new_server_total = server_total + 1
                
                db.execute('''
                    UPDATE fatigue 
                    SET daily_requests = ?, total_requests = ?, 
                        last_request_date = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (new_server_daily, new_server_total, today, server_id))
            else:
                # Insert server record if it doesn't exist
                db.execute('''
                    INSERT INTO fatigue 
                    (user_id, user_name, daily_requests, total_requests, last_request_date)
                    VALUES (?, ?, 1, 1, ?)
                ''', (server_id, f"Server_{server_name}", today))
        
        db.commit()
        return (new_daily, new_total)
        
    finally:
        db.close()

def get_fatigue_stats(server_name: str, user_id: str = None) -> dict:
    """
    Get fatigue statistics.
    
    Args:
        server_name: Server name
        user_id: User ID (optional, if None gets all users)
        
    Returns:
        dict: Fatigue statistics
    """
    db = init_fatigue_db(server_name)
    
    try:
        if user_id:
            # Get specific user stats
            cursor = db.execute('''
                SELECT user_id, user_name, daily_requests, total_requests, last_request_date
                FROM fatigue WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'user_name': row[1],
                    'daily_requests': row[2],
                    'total_requests': row[3],
                    'last_request_date': row[4]
                }
            else:
                return {}
        else:
            # Get all users stats
            cursor = db.execute('''
                SELECT user_id, user_name, daily_requests, total_requests, last_request_date
                FROM fatigue ORDER BY total_requests DESC
            ''')
            
            stats = []
            for row in cursor.fetchall():
                stats.append({
                    'user_id': row[0],
                    'user_name': row[1],
                    'daily_requests': row[2],
                    'total_requests': row[3],
                    'last_request_date': row[4]
                })
            
            return {'users': stats}
            
    finally:
        db.close()

def reset_daily_fatigue(server_name: str) -> int:
    """
    Reset daily fatigue counts for all users in a server.
    This should be called when the date changes.
    
    Args:
        server_name: Server name
        
    Returns:
        int: Number of users whose daily count was reset
    """
    db = init_fatigue_db(server_name)
    
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

def cleanup_old_fatigue_data(server_name: str, days_to_keep: int = 30) -> int:
    """
    Clean up old fatigue data (users with no activity for specified days).
    
    Args:
        server_name: Server name
        days_to_keep: Number of days to keep inactive users
        
    Returns:
        int: Number of users removed
    """
    db = init_fatigue_db(server_name)
    
    try:
        cutoff_date = (date.today() - datetime.timedelta(days=days_to_keep)).isoformat()
        
        cursor = db.execute('''
            DELETE FROM fatigue 
            WHERE user_id NOT LIKE 'server_%' 
            AND last_request_date < ?
            AND total_requests < 10  # Keep users with some activity
        ''', (cutoff_date,))
        
        db.commit()
        return cursor.rowcount
        
    finally:
        db.close()
