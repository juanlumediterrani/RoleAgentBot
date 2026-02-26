import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / 'agent.log'

def get_logger(name='agent'):
    logger = logging.getLogger(name)
    if logger.handlers:
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
        fh = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except (PermissionError, OSError) as e:
        # Si no podemos escribir al archivo, solo usamos console
        print(f"⚠️ No se puede escribir en log file {LOG_FILE}: {e}")
        print("📝 Usando solo salida a consola")

    return logger
