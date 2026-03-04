import sqlite3
import threading
import os
import stat
from pathlib import Path
from datetime import datetime, timedelta

try:
    from agent_logging import get_logger
    logger = get_logger('db_bote')
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('db_bote')

from agent_db import get_server_db_path_fallback, get_personality_name

def get_db_path(server_name: str = "default") -> Path:
    """Genera ruta de BD para el bote con nombre de personalidad."""
    personality_name = get_personality_name()
    db_name = f"bote_{personality_name}.db"
    return get_server_db_path_fallback(server_name, db_name)


class DatabaseBote:
    """Base de datos especializada para el juego del Bote.
    Gestiona estadísticas, historial de partidas y configuración.
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
                self._init_partidas_table()
                self._init_estadisticas_table()
                self._init_config_table()
                
                logger.info(f"✅ Base de datos del Bote lista en {self.db_path}")
        except Exception as e:
            logger.exception(f"❌ Error en inicialización de DB Bote: {e}")
    
    def _init_partidas_table(self):
        """Inicializa tabla de partidas jugadas."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS partidas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id TEXT NOT NULL,
                        usuario_nombre TEXT NOT NULL,
                        servidor_id TEXT NOT NULL,
                        servidor_nombre TEXT NOT NULL,
                        apuesta INTEGER NOT NULL,
                        dados TEXT NOT NULL,
                        combinacion TEXT NOT NULL,
                        premio INTEGER NOT NULL,
                        bote_antes INTEGER NOT NULL,
                        bote_despues INTEGER NOT NULL,
                        fecha TEXT NOT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_partidas_usuario ON partidas (usuario_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_partidas_servidor ON partidas (servidor_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_partidas_fecha ON partidas (fecha)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_partidas_combinacion ON partidas (combinacion)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla partidas: {e}")
    
    def _init_estadisticas_table(self):
        """Inicializa tabla de estadísticas de jugadores."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS estadisticas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id TEXT NOT NULL,
                        usuario_nombre TEXT NOT NULL,
                        servidor_id TEXT NOT NULL,
                        total_jugadas INTEGER DEFAULT 0,
                        total_apostado INTEGER DEFAULT 0,
                        total_ganado INTEGER DEFAULT 0,
                        botes_ganados INTEGER DEFAULT 0,
                        mayor_premio INTEGER DEFAULT 0,
                        fecha_actualizacion TEXT DEFAULT NULL,
                        UNIQUE(usuario_id, servidor_id)
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_estadisticas_usuario ON estadisticas (usuario_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_estadisticas_servidor ON estadisticas (servidor_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla estadisticas: {e}")
    
    def _init_config_table(self):
        """Inicializa tabla de configuración del bote."""
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS config (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        servidor_id TEXT NOT NULL UNIQUE,
                        apuesta_fija INTEGER DEFAULT 1,
                        bote_inicial INTEGER DEFAULT 10,
                        anuncios_activos INTEGER DEFAULT 1,
                        fecha_actualizacion TEXT DEFAULT NULL
                    )
                ''')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_config_servidor ON config (servidor_id)')
                conn.commit()
        except Exception as e:
            logger.exception(f"❌ Error creando tabla config: {e}")
    
    def registrar_partida(self, usuario_id: str, usuario_nombre: str,
                         servidor_id: str, servidor_nombre: str,
                         apuesta: int, dados: list[int], combinacion: str,
                         premio: int, bote_antes: int, bote_despues: int) -> bool:
        """Registra una partida jugada."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Registrar partida
                    cursor.execute('''
                        INSERT INTO partidas 
                        (usuario_id, usuario_nombre, servidor_id, servidor_nombre, 
                         apuesta, dados, combinacion, premio, bote_antes, bote_despues, fecha)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (usuario_id, usuario_nombre, servidor_id, servidor_nombre,
                          apuesta, str(dados), combinacion, premio, bote_antes, bote_despues,
                          datetime.now().isoformat()))
                    
                    conn.commit()
                    
                    # Actualizar estadísticas del jugador
                    self._actualizar_estadisticas_jugador(cursor, usuario_id, usuario_nombre,
                                                         servidor_id, apuesta, premio, combinacion)
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error registrando partida: {e}")
            return False
    
    def _actualizar_estadisticas_jugador(self, cursor, usuario_id: str, usuario_nombre: str,
                                        servidor_id: str, apuesta: int, premio: int, combinacion: str):
        """Actualiza las estadísticas de un jugador."""
        try:
            # Verificar si ya existe registro
            cursor.execute('''
                SELECT total_jugadas, total_apostado, total_ganado, botes_ganados, mayor_premio
                FROM estadisticas 
                WHERE usuario_id = ? AND servidor_id = ?
            ''', (usuario_id, servidor_id))
            
            existing = cursor.fetchone()
            
            if existing:
                # Actualizar registro existente
                total_jugadas, total_apostado, total_ganado, botes_ganados, mayor_premio = existing
                
                new_total_jugadas = total_jugadas + 1
                new_total_apostado = total_apostado + apuesta
                new_total_ganado = total_ganado + premio
                new_botes_ganados = botes_ganados + (1 if combinacion == "triple_unos" else 0)
                new_mayor_premio = max(mayor_premio, premio)
                
                cursor.execute('''
                    UPDATE estadisticas 
                    SET total_jugadas = ?, total_apostado = ?, total_ganado = ?,
                        botes_ganados = ?, mayor_premio = ?, fecha_actualizacion = ?
                    WHERE usuario_id = ? AND servidor_id = ?
                ''', (new_total_jugadas, new_total_apostado, new_total_ganado,
                      new_botes_ganados, new_mayor_premio, datetime.now().isoformat(),
                      usuario_id, servidor_id))
            else:
                # Crear nuevo registro
                new_botes_ganados = 1 if combinacion == "triple_unos" else 0
                
                cursor.execute('''
                    INSERT INTO estadisticas 
                    (usuario_id, usuario_nombre, servidor_id, total_jugadas, total_apostado, 
                     total_ganado, botes_ganados, mayor_premio, fecha_actualizacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (usuario_id, usuario_nombre, servidor_id, 1, apuesta,
                      premio, new_botes_ganados, premio, datetime.now().isoformat()))
                      
        except Exception as e:
            logger.exception(f"Error actualizando estadísticas del jugador: {e}")
    
    def obtener_estadisticas_jugador(self, usuario_id: str, servidor_id: str) -> dict:
        """Obtiene las estadísticas de un jugador."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT total_jugadas, total_apostado, total_ganado, botes_ganados, mayor_premio
                    FROM estadisticas 
                    WHERE usuario_id = ? AND servidor_id = ?
                ''', (usuario_id, servidor_id))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "total_jugadas": result[0],
                        "total_apostado": result[1],
                        "total_ganado": result[2],
                        "botes_ganados": result[3],
                        "mayor_premio": result[4],
                        "balance": result[2] - result[1]
                    }
                else:
                    return {
                        "total_jugadas": 0,
                        "total_apostado": 0,
                        "total_ganado": 0,
                        "botes_ganados": 0,
                        "mayor_premio": 0,
                        "balance": 0
                    }
        except Exception as e:
            logger.exception(f"Error obteniendo estadísticas del jugador: {e}")
            return {}
    
    def obtener_historial_partidas(self, servidor_id: str, limite: int = 10) -> list:
        """Obtiene el historial de partidas recientes."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT usuario_nombre, apuesta, dados, combinacion, premio, fecha
                    FROM partidas 
                    WHERE servidor_id = ?
                    ORDER BY fecha DESC
                    LIMIT ?
                ''', (servidor_id, limite))
                
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo historial de partidas: {e}")
            return []
    
    def obtener_ranking_jugadores(self, servidor_id: str, metrica: str = "total_ganado", limite: int = 10) -> list:
        """Obtiene ranking de jugadores según una métrica."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                columnas_validas = ["total_jugadas", "total_apostado", "total_ganado", "botes_ganados", "mayor_premio"]
                if metrica not in columnas_validas:
                    metrica = "total_ganado"
                
                cursor.execute(f'''
                    SELECT usuario_nombre, {metrica}, total_jugadas, total_ganado, total_apostado
                    FROM estadisticas 
                    WHERE servidor_id = ? AND total_jugadas > 0
                    ORDER BY {metrica} DESC
                    LIMIT ?
                ''', (servidor_id, limite))
                
                return cursor.fetchall()
        except Exception as e:
            logger.exception(f"Error obteniendo ranking de jugadores: {e}")
            return []
    
    def obtener_estadisticas_servidor(self, servidor_id: str) -> dict:
        """Obtiene estadísticas generales del servidor."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                
                # Estadísticas generales
                cursor.execute('SELECT COUNT(*) FROM partidas WHERE servidor_id = ?')
                total_partidas = cursor.fetchone()[0]
                
                cursor.execute('SELECT SUM(apuesta) FROM partidas WHERE servidor_id = ?')
                total_apostado = cursor.fetchone()[0] or 0
                
                cursor.execute('SELECT SUM(premio) FROM partidas WHERE servidor_id = ?')
                total_premios = cursor.fetchone()[0] or 0
                
                cursor.execute('SELECT COUNT(*) FROM partidas WHERE servidor_id = ? AND combinacion = "triple_unos"')
                botes_ganados = cursor.fetchone()[0]
                
                cursor.execute('SELECT MAX(premio) FROM partidas WHERE servidor_id = ?')
                mayor_premio = cursor.fetchone()[0] or 0
                
                # Jugadores únicos
                cursor.execute('SELECT COUNT(DISTINCT usuario_id) FROM partidas WHERE servidor_id = ?')
                jugadores_unicos = cursor.fetchone()[0]
                
                return {
                    "total_partidas": total_partidas,
                    "total_apostado": total_apostado,
                    "total_premios": total_premios,
                    "botes_ganados": botes_ganados,
                    "mayor_premio": mayor_premio,
                    "jugadores_unicos": jugadores_unicos,
                    "balance_casa": total_apostado - total_premios
                }
        except Exception as e:
            logger.exception(f"Error obteniendo estadísticas del servidor: {e}")
            return {}
    
    def configurar_servidor(self, servidor_id: str, apuesta_fija: int = None,
                          bote_inicial: int = None, anuncios_activos: bool = None) -> bool:
        """Configura los parámetros del juego para un servidor."""
        try:
            with self._lock:
                with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                    cursor = conn.cursor()
                    
                    # Obtener configuración actual
                    cursor.execute('''
                        SELECT apuesta_fija, bote_inicial, anuncios_activos
                        FROM config WHERE servidor_id = ?
                    ''', (servidor_id,))
                    
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Actualizar solo los campos proporcionados
                        current_apuesta, current_bote, current_anuncios = existing
                        
                        new_apuesta = apuesta_fija if apuesta_fija is not None else current_apuesta
                        new_bote = bote_inicial if bote_inicial is not None else current_bote
                        new_anuncios = anuncios_activos if anuncios_activos is not None else current_anuncios
                        
                        cursor.execute('''
                            UPDATE config 
                            SET apuesta_fija = ?, bote_inicial = ?, anuncios_activos = ?, 
                                fecha_actualizacion = ?
                            WHERE servidor_id = ?
                        ''', (new_apuesta, new_bote, int(new_anuncios), 
                              datetime.now().isoformat(), servidor_id))
                    else:
                        # Crear nueva configuración
                        new_apuesta = apuesta_fija if apuesta_fija is not None else 10
                        new_bote = bote_inicial if bote_inicial is not None else 100
                        new_anuncios = int(anuncios_activos) if anuncios_activos is not None else 1
                        
                        cursor.execute('''
                            INSERT INTO config 
                            (servidor_id, apuesta_fija, bote_inicial, anuncios_activos, fecha_actualizacion)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (servidor_id, new_apuesta, new_bote, new_anuncios, datetime.now().isoformat()))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.exception(f"Error configurando servidor: {e}")
            return False
    
    def obtener_configuracion_servidor(self, servidor_id: str) -> dict:
        """Obtiene la configuración actual del servidor."""
        try:
            with sqlite3.connect(str(self.db_path), timeout=30) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT apuesta_fija, bote_inicial, anuncios_activos
                    FROM config WHERE servidor_id = ?
                ''', (servidor_id,))
                
                result = cursor.fetchone()
                if result:
                    return {
                        "apuesta_fija": result[0],
                        "bote_inicial": result[1],
                        "anuncios_activos": bool(result[2])
                    }
                else:
                    # Valores por defecto
                    return {
                        "apuesta_fija": 1,
                        "bote_inicial": 10,
                        "anuncios_activos": True
                    }
        except Exception as e:
            logger.exception(f"Error obteniendo configuración del servidor: {e}")
            return {
                "apuesta_fija": 1,
                "bote_inicial": 10,
                "anuncios_activos": True
            }


def get_bote_db_instance(server_name: str = "default") -> DatabaseBote:
    """Obtiene una instancia de la base de datos del Bote."""
    return DatabaseBote(server_name)
