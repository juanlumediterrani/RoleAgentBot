import sqlite3
import datetime
import json
import os
import threading
from pathlib import Path
from agent_logging import get_logger

logger = get_logger('db')

# Configuración de rutas y límites
BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / "databases"
DB_PATH = DB_DIR / "agent.db"
HISTORIAL_LIMITE = 5
os.makedirs(DB_DIR, exist_ok=True)

class AgentDatabase:
    def __init__(self, db_path: Path = DB_PATH):
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
            try:
                fallback_dir.mkdir(parents=True, exist_ok=True)
                fallback_db = fallback_dir / 'agent.db'
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

db = AgentDatabase()
logger.info("🗄️ [DB] Base de datos global inicializada")
