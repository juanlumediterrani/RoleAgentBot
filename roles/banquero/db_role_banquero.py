import sqlite3
import threading
import os
import stat
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('db_role_banquero')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_banquero')

from agent_db import get_server_db_path_fallback, get_personality_name

def get_db_path(server_name: str = "default") -> Path:
    """Genera ruta de BD para el banquero con nombre de personalidad."""
    personality_name = get_personality_name()
    db_name = f"banquero_{personality_name}.db"
    return get_server_db_path_fallback(server_name, db_name)


class DatabaseRoleBanquero:
    """Base de datos especializada para el Banquero.
    Gestiona carteras de oro, transacciones y distribución diaria.
    """
    
    def __init__(self, server_name: str = "default", db_path: Path = None):
        if db_path is None:
            self.db_path = get_db_path(server_name)
        else:
            self.db_path = db_path
        self._lock = threading.RLock()
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
            cursor.execute('PRAGMA journal_mode=WAL;')
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
        """Inicializa la base de datos con todas las tablas necesarias."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                conn.commit()
                
                # Inicializar tablas
                self._init_carteras_table()
                self._init_transacciones_table()
                self._init_config_table()
                
                logger.info(f"✅ Base de datos del Banquero lista en {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error en inicialización de DB Banquero: {e}")
    
    def _init_carteras_table(self):
        """Inicializa tabla de carteras de los usuarios."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS carteras (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id TEXT NOT NULL UNIQUE,
                        usuario_nombre TEXT NOT NULL,
                        servidor_id TEXT NOT NULL,
                        servidor_nombre TEXT NOT NULL,
                        saldo INTEGER DEFAULT 0,
                        fecha_creacion TEXT NOT NULL,
                        fecha_actualizacion TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_carteras_usuario ON carteras (usuario_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_carteras_servidor ON carteras (servidor_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla carteras: {e}")
    
    def _init_transacciones_table(self):
        """Inicializa tabla de transacciones."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transacciones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id TEXT NOT NULL,
                        usuario_nombre TEXT NOT NULL,
                        servidor_id TEXT NOT NULL,
                        servidor_nombre TEXT NOT NULL,
                        tipo TEXT NOT NULL,
                        cantidad INTEGER NOT NULL,
                        saldo_anterior INTEGER NOT NULL,
                        saldo_nuevo INTEGER NOT NULL,
                        descripcion TEXT,
                        fecha TEXT NOT NULL,
                        administrador_id TEXT DEFAULT NULL,
                        administrador_nombre TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transacciones_usuario ON transacciones (usuario_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transacciones_servidor ON transacciones (servidor_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transacciones_fecha ON transacciones (fecha)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_transacciones_tipo ON transacciones (tipo)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla transacciones: {e}")
    
    def _init_config_table(self):
        """Inicializa tabla de configuración del banquero."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        servidor_id TEXT NOT NULL UNIQUE,
                        tae_diaria INTEGER DEFAULT 1,
                        bono_apertura INTEGER DEFAULT 10,
                        ultima_distribucion TEXT DEFAULT NULL,
                        fecha_actualizacion TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_config_servidor ON config (servidor_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla config: {e}")
    
    def crear_cartera(self, usuario_id: str, usuario_nombre: str, 
                      servidor_id: str, servidor_nombre: str) -> tuple[bool, int]:
        """Crea una nueva cartera para un usuario y aplica bono de apertura.
        
        Returns:
            tuple: (se_creo, saldo_inicial)
        """
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Verificar si ya existe
                    cursor.execute('''
                        SELECT saldo FROM carteras 
                        WHERE usuario_id = ? AND servidor_id = ?
                    ''', (usuario_id, servidor_id))
                    existing = cursor.fetchone()
                    
                    if existing:
                        return False, existing[0]
                    
                    # Obtener bono de apertura del servidor
                    cursor.execute('''
                        SELECT bono_apertura FROM config WHERE servidor_id = ?
                    ''', (servidor_id,))
                    bono_result = cursor.fetchone()
                    bono_apertura = bono_result[0] if bono_result else 10
                    
                    # Insertar nueva cartera con el bono
                    cursor.execute('''
                        INSERT INTO carteras 
                        (usuario_id, usuario_nombre, servidor_id, servidor_nombre, saldo, fecha_creacion)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (usuario_id, usuario_nombre, servidor_id, servidor_nombre, 
                          bono_apertura, datetime.now().isoformat()))
                    
                    # Registrar transacción de bono de apertura
                    cursor.execute('''
                        INSERT INTO transacciones 
                        (usuario_id, usuario_nombre, servidor_id, servidor_nombre, 
                         tipo, cantidad, saldo_anterior, saldo_nuevo, descripcion, fecha)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (usuario_id, usuario_nombre, servidor_id, servidor_nombre,
                          "bono_apertura", bono_apertura, 0, bono_apertura,
                          f"Bono de apertura de cuenta ({bono_apertura} monedas)",
                          datetime.now().isoformat()))
                    
                    conn.commit()
                    return True, bono_apertura
        except Exception as e:
            logger.exception(f"Error creando cartera: {e}")
            return False, 0
    
    def obtener_saldo(self, usuario_id: str, servidor_id: str) -> int:
        """Obtiene el saldo de un usuario."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT saldo FROM carteras 
                    WHERE usuario_id = ? AND servidor_id = ?
                ''', (usuario_id, servidor_id))
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.exception(f"Error obteniendo saldo: {e}")
            return 0
    
    def actualizar_saldo(self, usuario_id: str, usuario_nombre: str,
                        servidor_id: str, servidor_nombre: str,
                        cantidad: int, tipo: str, descripcion: str = None,
                        administrador_id: str = None, administrador_nombre: str = None) -> bool:
        """Actualiza el saldo de un usuario y registra la transacción."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Crear cartera si no existe (con bono de apertura)
                    se_creo, saldo_existente = self.crear_cartera(usuario_id, usuario_nombre, servidor_id, servidor_nombre)
                    
                    # Obtener saldo actual (después de posible creación)
                    cursor.execute('''
                        SELECT saldo FROM carteras 
                        WHERE usuario_id = ? AND servidor_id = ?
                    ''', (usuario_id, servidor_id))
                    saldo_anterior = cursor.fetchone()[0] or 0
                    
                    # Calcular nuevo saldo
                    saldo_nuevo = saldo_anterior + cantidad
                    
                    # Actualizar saldo
                    cursor.execute('''
                        UPDATE carteras 
                        SET saldo = ?, fecha_actualizacion = ?
                        WHERE usuario_id = ? AND servidor_id = ?
                    ''', (saldo_nuevo, datetime.now().isoformat(), usuario_id, servidor_id))
                    
                    # Registrar transacción
                    cursor.execute('''
                        INSERT INTO transacciones 
                        (usuario_id, usuario_nombre, servidor_id, servidor_nombre, 
                         tipo, cantidad, saldo_anterior, saldo_nuevo, descripcion, fecha,
                         administrador_id, administrador_nombre)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (usuario_id, usuario_nombre, servidor_id, servidor_nombre,
                          tipo, cantidad, saldo_anterior, saldo_nuevo, descripcion,
                          datetime.now().isoformat(), administrador_id, administrador_nombre))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error actualizando saldo: {e}")
            return False
    
    def establecer_tae(self, servidor_id: str, tae_diaria: int, 
                      administrador_id: str, administrador_nombre: str) -> bool:
        """Establece la TAE (Tasa Anual Equivalente) diaria del servidor."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO config 
                        (servidor_id, tae_diaria, fecha_actualizacion)
                        VALUES (?, ?, ?)
                    ''', (servidor_id, tae_diaria, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error estableciendo TAE: {e}")
            return False
    
    def establecer_bono_apertura(self, servidor_id: str, bono_apertura: int,
                                administrador_id: str, administrador_nombre: str) -> bool:
        """Establece el bono de apertura del servidor."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT OR REPLACE INTO config 
                        (servidor_id, bono_apertura, fecha_actualizacion)
                        VALUES (?, ?, ?)
                    ''', (servidor_id, bono_apertura, datetime.now().isoformat()))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error estableciendo bono de apertura: {e}")
            return False
    
    def obtener_bono_apertura(self, servidor_id: str) -> int:
        """Obtiene el bono de apertura del servidor."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT bono_apertura FROM config WHERE servidor_id = ?
                ''', (servidor_id,))
                result = cursor.fetchone()
                return result[0] if result else 10
        except Exception as e:
            logger.exception(f"Error obteniendo bono de apertura: {e}")
            return 10
    
    def obtener_tae(self, servidor_id: str) -> int:
        """Obtiene la TAE diaria del servidor."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT tae_diaria FROM config WHERE servidor_id = ?
                ''', (servidor_id,))
                result = cursor.fetchone()
                return result[0] if result else 1
        except Exception as e:
            logger.exception(f"Error obteniendo TAE: {e}")
            return 0
    
    def obtener_ultima_distribucion(self, servidor_id: str) -> str:
        """Obtiene la fecha de la última distribución."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT ultima_distribucion FROM config WHERE servidor_id = ?
                ''', (servidor_id,))
                result = cursor.fetchone()
                return result[0] if result and result[0] else None
        except Exception as e:
            logger.exception(f"Error obteniendo última distribución: {e}")
            return None
    
    def registrar_distribucion_diaria(self, servidor_id: str) -> bool:
        """Registra que se hizo una distribución diaria hoy."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE config 
                        SET ultima_distribucion = ?
                        WHERE servidor_id = ?
                    ''', (datetime.now().isoformat(), servidor_id))
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error registrando distribución diaria: {e}")
            return False
    
    def distribuir_tae_diaria(self, servidor_id: str, servidor_nombre: str) -> dict:
        """Distribuye la TAE diaria a todos los usuarios del servidor."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Obtener TAE diaria
                    cursor.execute('''
                        SELECT tae_diaria FROM config WHERE servidor_id = ?
                    ''', (servidor_id,))
                    result = cursor.fetchone()
                    tae_diaria = result[0] if result else 0
                    
                    if tae_diaria <= 0:
                        return {"success": False, "message": "No hay TAE configurada"}
                    
                    # Obtener todos los usuarios del servidor
                    cursor.execute('''
                        SELECT usuario_id, usuario_nombre, saldo FROM carteras 
                        WHERE servidor_id = ?
                    ''', (servidor_id,))
                    usuarios = cursor.fetchall()
                    
                    if not usuarios:
                        return {"success": False, "message": "No hay usuarios con cartera"}
                    
                    # Distribuir a cada usuario
                    distribuciones = []
                    for usuario_id, usuario_nombre, saldo_actual in usuarios:
                        nuevo_saldo = saldo_actual + tae_diaria
                        
                        # Actualizar saldo
                        cursor.execute('''
                            UPDATE carteras 
                            SET saldo = ?, fecha_actualizacion = ?
                            WHERE usuario_id = ? AND servidor_id = ?
                        ''', (nuevo_saldo, datetime.now().isoformat(), usuario_id, servidor_id))
                        
                        # Registrar transacción
                        cursor.execute('''
                            INSERT INTO transacciones 
                            (usuario_id, usuario_nombre, servidor_id, servidor_nombre, 
                             tipo, cantidad, saldo_anterior, saldo_nuevo, descripcion, fecha)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (usuario_id, usuario_nombre, servidor_id, servidor_nombre,
                              "tae_diaria", tae_diaria, saldo_actual, nuevo_saldo,
                              f"Distribución diaria de TAE ({tae_diaria} monedas)",
                              datetime.now().isoformat()))
                        
                        distribuciones.append({
                            "usuario_id": usuario_id,
                            "usuario_nombre": usuario_nombre,
                            "cantidad": tae_diaria,
                            "saldo_anterior": saldo_actual,
                            "saldo_nuevo": nuevo_saldo
                        })
                    
                    # Registrar distribución
                    cursor.execute('''
                        UPDATE config 
                        SET ultima_distribucion = ?
                        WHERE servidor_id = ?
                    ''', (datetime.now().isoformat(), servidor_id))
                    
                    conn.commit()
                    
                    return {
                        "success": True,
                        "tae_diaria": tae_diaria,
                        "usuarios_distribuidos": len(distribuciones),
                        "distribuciones": distribuciones
                    }
        except Exception as e:
            logger.exception(f"Error distribuyendo TAE diaria: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}
    
    def obtener_historial_transacciones(self, usuario_id: str, servidor_id: str, limite: int = 10) -> list:
        """Obtiene el historial de transacciones de un usuario."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT tipo, cantidad, saldo_anterior, saldo_nuevo, descripcion, fecha,
                           administrador_nombre
                    FROM transacciones 
                    WHERE usuario_id = ? AND servidor_id = ?
                    ORDER BY fecha DESC
                    LIMIT ?
                ''', (usuario_id, servidor_id, limite))
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo historial de transacciones: {e}")
            return []
    
    def obtener_estadisticas(self, servidor_id: str = None) -> dict:
        """Obtiene estadísticas básicas del banquero."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Estadísticas generales
                cursor.execute('SELECT COUNT(*) FROM carteras')
                carteras_total = cursor.fetchone()[0]
                
                cursor.execute('SELECT SUM(saldo) FROM carteras')
                total_oro = cursor.fetchone()[0] or 0
                
                cursor.execute('SELECT COUNT(*) FROM transacciones')
                transacciones_total = cursor.fetchone()[0]
                
                # Estadísticas por servidor si se especifica
                if servidor_id:
                    cursor.execute('SELECT COUNT(*) FROM carteras WHERE servidor_id = ?', (servidor_id,))
                    carteras_servidor = cursor.fetchone()[0]
                    
                    cursor.execute('SELECT SUM(saldo) FROM carteras WHERE servidor_id = ?', (servidor_id,))
                    oro_servidor = cursor.fetchone()[0] or 0
                    
                    cursor.execute('SELECT COUNT(*) FROM transacciones WHERE servidor_id = ?', (servidor_id,))
                    transacciones_servidor = cursor.fetchone()[0]
                else:
                    carteras_servidor = 0
                    oro_servidor = 0
                    transacciones_servidor = 0
                
                return {
                    'carteras_total': carteras_total,
                    'total_oro': total_oro,
                    'transacciones_total': transacciones_total,
                    'carteras_servidor': carteras_servidor,
                    'oro_servidor': oro_servidor,
                    'transacciones_servidor': transacciones_servidor
                }
        except Exception as e:
            logger.exception(f"Error obteniendo estadísticas: {e}")
            return {}


def get_banquero_db_instance(server_name: str = "default") -> DatabaseRoleBanquero:
    """Obtiene una instancia de la base de datos del Banquero."""
    return DatabaseRoleBanquero(server_name)
