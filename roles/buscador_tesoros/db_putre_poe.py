import sqlite3
import threading
import os
import stat
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('db_role_poe')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_role_poe')

BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / "databases"

def get_db_path(liga: str = "Standard") -> Path:
    """Genera ruta de BD basada en el nombre de la liga."""
    if liga.lower() == "fate of the vaal":
        liga_sanitized = "FOTV"
    elif liga.lower() == "standard":
        liga_sanitized = "standard"
    else:
        liga_sanitized = liga.lower().replace(' ', '_').replace('-', '_')
    return DB_DIR / f"poe_{liga_sanitized}.db"

DB_DIR.mkdir(parents=True, exist_ok=True)


class DatabaseRolePoe:
    """Base de datos especializada para el Buscador de Tesoros.
    Gestiona el historial de precios con retención de 720 entradas (30 días).
    """
    
    def __init__(self, db_path: Path):
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
                cursor.execute("PRAGMA journal_mode=DELETE;")  # Changed from WAL to DELETE
                conn.commit()
                
                # Inicializar tabla de notificaciones
                self._init_notifications_table()
                
                logger.info(f"✅ Base de datos PutrePoe lista en {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error en inicialización de DB PutrePoe: {e}")
    
    def _sanitize_table_name(self, item_name: str) -> str:
        """Convierte nombre de item en nombre de tabla SQL válido."""
        sanitized = item_name.lower()
        sanitized = sanitized.replace(' ', '_').replace('-', '_')
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c == '_')
        return f"precio_{sanitized}"
    
    def _ensure_table_exists(self, item_name: str, conn: sqlite3.Connection):
        """Crea tabla para el item si no existe."""
        table_name = self._sanitize_table_name(item_name)
        cursor = conn.cursor()
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                precio REAL NOT NULL,
                cantidad INTEGER DEFAULT NULL,
                liga TEXT NOT NULL,
                fecha TEXT NOT NULL
            )
        ''')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_fecha ON {table_name} (fecha)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_liga ON {table_name} (liga)')
        conn.commit()
    
    def insertar_precios_bulk(self, item_name: str, entradas: list, liga: str):
        """Inserta múltiples entradas de precio y mantiene máximo 720 entradas.
        Evita duplicados por fecha y liga.
        """
        insertados = 0
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    
                    # Formatear liga
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    
                    # Insertar nuevas entradas evitando duplicados
                    for entry in entradas:
                        if not entry.time:
                            continue
                            
                        # Parsear fecha y formatear
                        try:
                            fecha_iso = datetime.fromisoformat(entry.time.replace('Z', '+00:00')).replace(tzinfo=None)
                            fecha_formateada = fecha_iso.strftime('%m-%d %H:%M')
                        except:
                            continue
                        
                        # Verificar duplicado
                        cursor.execute(f'''
                            SELECT COUNT(*) FROM {table_name}
                            WHERE fecha = ? AND liga = ?
                        ''', (fecha_formateada, liga_formateada))
                        if cursor.fetchone()[0] > 0:
                            continue
                        
                        # Insertar
                        cursor.execute(f'''
                            INSERT INTO {table_name} 
                            (precio, cantidad, liga, fecha)
                            VALUES (?, ?, ?, ?)
                        ''', (round(entry.price, 2),
                              entry.quantity if entry.quantity is not None else None,
                              liga_formateada,
                              fecha_formateada))
                        insertados += 1
                    
                    # Mantener máximo 720 entradas por item/liga
                    cursor.execute(f'''
                        DELETE FROM {table_name}
                        WHERE liga = ? AND id NOT IN (
                            SELECT id FROM {table_name}
                            WHERE liga = ?
                            ORDER BY fecha DESC
                            LIMIT 720
                        )
                    ''', (liga_formateada, liga_formateada))
                    
                    eliminados = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"✅ {insertados} nuevos, {eliminados} eliminados para {item_name} ({liga_formateada})")
                    return insertados
        except Exception as e:
            logger.exception(f"⚠️ Error en bulk insert para {item_name}: {e}")
            return insertados
    
    def obtener_estadisticas(self, item_name: str, liga: str):
        """Obtiene MIN y MAX de precios históricos para un item."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    cursor.execute(f'''
                        SELECT MIN(precio), MAX(precio) 
                        FROM {table_name} 
                        WHERE liga = ?
                    ''', (liga_formateada,))
                    result = cursor.fetchone()
                    return result if result else (None, None)
        except Exception as e:
            logger.exception(f"⚠️ Error obteniendo estadísticas para {item_name}: {e}")
            return (None, None)
    
    def obtener_historial_precios(self, item_name: str, liga: str):
        """Obtiene todos los precios históricos ordenados por fecha para análisis de zonas."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    cursor.execute(f'''
                        SELECT precio, fecha
                        FROM {table_name}
                        WHERE liga = ?
                        ORDER BY fecha DESC
                    ''', (liga_formateada,))
                    return cursor.fetchall()
        except Exception as e:
            logger.exception(f"⚠️ Error obteniendo historial para {item_name}: {e}")
            return []
    
    def obtener_conteo(self, item_name: str, liga: str):
        """Obtiene el número de entradas para un item."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    cursor.execute(f'SELECT COUNT(*) FROM {table_name} WHERE liga = ?', (liga_formateada,))
                    return cursor.fetchone()[0]
        except Exception as e:
            logger.exception(f"⚠️ Error obteniendo conteo para {item_name}: {e}")
            return 0
    
    def obtener_precio_actual(self, item_name: str, liga: str):
        """Obtiene el precio más reciente para un item."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    cursor.execute(f'''
                        SELECT precio 
                        FROM {table_name}
                        WHERE liga = ?
                        ORDER BY fecha DESC
                        LIMIT 1
                    ''', (liga_formateada,))
                    result = cursor.fetchone()
                    return result[0] if result else None
        except Exception as e:
            logger.exception(f"⚠️ Error obteniendo precio actual para {item_name}: {e}")
            return None
    
    def obtener_ultima_fecha(self, item_name: str, liga: str):
        """Obtiene la fecha de la última entrada para un item."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    self._ensure_table_exists(item_name, conn)
                    table_name = self._sanitize_table_name(item_name)
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    cursor.execute(f'''
                        SELECT MAX(fecha) 
                        FROM {table_name} 
                        WHERE liga = ?
                    ''', (liga_formateada,))
                    result = cursor.fetchone()
                    return result[0] if result and result[0] else None
        except Exception as e:
            logger.exception(f"⚠️ Error obteniendo última fecha para {item_name}: {e}")
            return None
    
    def verificar_datos_antiguos(self, item_name: str, liga: str, horas: int = 24):
        """Verifica si los datos son más antiguos que N horas."""
        try:
            ultima_fecha_str = self.obtener_ultima_fecha(item_name, liga)
            if not ultima_fecha_str:
                return True  # No hay datos, se consideran "antiguos"
            
            # Convertir fecha formateada (MM-DD HH:mm) a datetime
            try:
                # Asumir año actual para la fecha formateada
                año_actual = datetime.now().year
                fecha_completa = f"{año_actual}-{ultima_fecha_str}"
                ultima_fecha = datetime.strptime(fecha_completa, '%Y-%m-%d %H:%M')
                
                # Si la fecha es futura, asumir año anterior
                if ultima_fecha > datetime.now():
                    año_anterior = año_actual - 1
                    fecha_completa = f"{año_anterior}-{ultima_fecha_str}"
                    ultima_fecha = datetime.strptime(fecha_completa, '%Y-%m-%d %H:%M')
            except ValueError:
                return True  # Si no puede parsear, asumir que necesita actualización
            
            fecha_limite = datetime.now() - timedelta(hours=horas)
            return ultima_fecha < fecha_limite
        except Exception as e:
            logger.exception(f"⚠️ Error verificando datos antiguos para {item_name}: {e}")
            return True  # Si hay error, asumimos que necesita actualización
    
    def _init_notifications_table(self):
        """Inicializa la tabla de notificaciones."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS notificaciones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        item_name TEXT NOT NULL,
                        liga TEXT NOT NULL,
                        tipo_señal TEXT NOT NULL,  -- 'COMPRA' o 'VENTA'
                        precio REAL NOT NULL,
                        fecha_envio TEXT NOT NULL  -- timestamp ISO
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notificaciones_item_fecha ON notificaciones (item_name, liga, fecha_envio)')
                conn.commit()
                logger.info("✅ Tabla de notificaciones inicializada")
        except Exception as e:
            logger.exception(f"❌ Error inicializando tabla de notificaciones: {e}")
    
    def registrar_notificacion(self, item_name: str, liga: str, tipo_señal: str, precio: float):
        """Registra una notificación enviada."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    fecha_envio = datetime.now().isoformat()
                    
                    cursor.execute('''
                        INSERT INTO notificaciones (item_name, liga, tipo_señal, precio, fecha_envio)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (item_name, liga_formateada, tipo_señal, precio, fecha_envio))
                    conn.commit()
                    logger.info(f"✅ Notificación registrada: {item_name} - {tipo_señal} a {precio}")
        except Exception as e:
            logger.exception(f"⚠️ Error registrando notificación: {e}")
    
    def verificar_notificacion_reciente(self, item_name: str, liga: str, tipo_señal: str, precio_actual: float, horas: int = 6, umbral_similitud: float = 0.15):
        """Verifica si hubo una notificación similar en las últimas N horas.
        
        Args:
            item_name: Nombre del item
            liga: Liga actual
            tipo_señal: Tipo de señal ('COMPRA' o 'VENTA')
            precio_actual: Precio actual
            horas: Ventana de tiempo en horas (default: 6)
            umbral_similitud: Umbral de similitud de precios (default: 15% = 0.15)
        
        Returns:
            bool: True si hay una notificación similar reciente, False si no
        """
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path)) as conn:
                    cursor = conn.cursor()
                    liga_formateada = ''.join([word[0].upper() for word in liga.split()])
                    
                    # Calcular fecha límite
                    fecha_limite = datetime.now() - timedelta(hours=horas)
                    fecha_limite_iso = fecha_limite.isoformat()
                    
                    # Buscar notificaciones recientes del mismo item y tipo
                    cursor.execute('''
                        SELECT precio, fecha_envio
                        FROM notificaciones
                        WHERE item_name = ? AND liga = ? AND tipo_señal = ? AND fecha_envio > ?
                        ORDER BY fecha_envio DESC
                    ''', (item_name, liga_formateada, tipo_señal, fecha_limite_iso))
                    
                    notificaciones = cursor.fetchall()
                    
                    for precio_anterior, fecha_envio in notificaciones:
                        # Calcular diferencia porcentual
                        if precio_anterior > 0:
                            diferencia = abs(precio_actual - precio_anterior) / precio_anterior
                            if diferencia <= umbral_similitud:
                                logger.info(f"🚫 Notificación similar encontrada: {item_name} - {tipo_señal} a {precio_anterior} (hace {(datetime.now() - datetime.fromisoformat(fecha_envio)).total_seconds() / 3600:.1f}h)")
                                return True
                    
                    return False
        except Exception as e:
            logger.exception(f"⚠️ Error verificando notificación reciente: {e}")
            return False  # Si hay error, permitimos la notificación


# La instancia se creará en buscador_tesoros.py con la liga correcta
