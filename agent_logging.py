import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

_ACTIVE_SERVER_FILE = Path(__file__).parent / ".active_server"


def _get_active_server_name() -> str | None:
    import os
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

# Obtener nombre de la personalidad para el log
def get_personality_name():
    # Primero intentar desde variable de entorno (prioridad en Docker)
    import os
    env_personality = os.getenv('PERSONALITY')
    if env_personality:
        return env_personality.lower()
    
    # Sino intentar desde agent_engine
    try:
        from agent_engine import PERSONALIDAD
        return PERSONALIDAD.get("name", "agent").lower()
    except:
        return "agent"

def get_server_log_path(server_name: str, personality_name: str = None) -> Path:
    """
    Genera ruta de log para un servidor específico.
    
    Args:
        server_name: Nombre del servidor (sanitizado)
        personality_name: Nombre de la personalidad (opcional)
    
    Returns:
        Path: Ruta completa al archivo de log
    """
    # Sanitizar nombre del servidor
    server_sanitized = server_name.lower().replace(' ', '_').replace('-', '_')
    server_sanitized = ''.join(c for c in server_sanitized if c.isalnum() or c == '_')
    
    # Directorio base
    server_dir = LOG_DIR / server_sanitized
    server_dir.mkdir(parents=True, exist_ok=True)
    
    # Usar nombre de personalidad si se proporciona, si no el global
    log_name = personality_name or get_personality_name()
    return server_dir / f'{log_name}.log'


# Variable global para el archivo de log actual
_active_server = _get_active_server_name()
if _active_server:
    _current_log_file = get_server_log_path(_active_server, get_personality_name())
else:
    _current_log_file = LOG_DIR / f'{get_personality_name()}.log'

def update_log_file_path(server_name: str, personality_name: str = None):
    """
    Actualiza la ruta del archivo de log para un servidor específico.
    
    Args:
        server_name: Nombre del servidor
        personality_name: Nombre de la personalidad (opcional)
    """
    global _current_log_file
    _current_log_file = get_server_log_path(server_name, personality_name)

def get_logger(name='agent'):
    global _current_log_file
    logger = logging.getLogger(name)

    # Si ya existe el logger, aún podemos añadir el file handler más tarde
    if logger.handlers:
        has_file = any(isinstance(h, RotatingFileHandler) for h in logger.handlers)
        if not has_file:
            active_server = _get_active_server_name()
            if active_server:
                try:
                    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
                    fh = RotatingFileHandler(_current_log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
                    fh.setLevel(logging.INFO)
                    fh.setFormatter(fmt)
                    logger.addHandler(fh)
                except (PermissionError, OSError):
                    pass
        return logger

    logger.propagate = False

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # Rotating file handler con manejo de errores de permisos
    try:
        # Solo crear log a fichero si ya tenemos servidor activo
        active_server = _get_active_server_name()
        if active_server:
            fh = RotatingFileHandler(_current_log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
            fh.setLevel(logging.INFO)
            fh.setFormatter(fmt)
            logger.addHandler(fh)
    except (PermissionError, OSError) as e:
        # Si no podemos escribir al archivo, solo usamos console
        print(f"⚠️ No se puede escribir en log file {_current_log_file}: {e}")
        print("📝 Usando solo salida a consola")

    return logger
