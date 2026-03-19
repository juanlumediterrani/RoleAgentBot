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

def get_personality_name():
    """Get the active personality name for log file naming."""
    import os
    env_personality = os.getenv('PERSONALITY')
    if env_personality:
        return env_personality.lower()

    try:
        from agent_engine import PERSONALITY
        return PERSONALITY.get("name", "agent").lower()
    except Exception:
        return "agent"

def get_server_log_path(server_name: str, personality_name: str = None) -> Path:
    """
    Build the log path for a specific server.

    Args:
        server_name: Sanitized server name
        personality_name: Optional personality name

    Returns:
        Full path to the log file
    """
    server_sanitized = server_name.lower().replace(' ', '_').replace('-', '_')
    server_sanitized = ''.join(c for c in server_sanitized if c.isalnum() or c == '_')

    server_dir = LOG_DIR / server_sanitized
    try:
        server_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        print(f"⚠️ Could not create server log directory {server_dir}: {e}")
        print(f"📝 Falling back to base log directory: {LOG_DIR}")
        server_dir = LOG_DIR

    log_name = personality_name or get_personality_name()
    log_file = server_dir / f'{log_name}.log'

    try:
        log_file.touch(exist_ok=True)
    except (PermissionError, OSError) as e:
        print(f"⚠️ Could not create log file {log_file}: {e}")
        fallback_file = LOG_DIR / f'{log_name}.log'
        print(f"📝 Falling back to log file: {fallback_file}")
        return fallback_file

    return log_file


_active_server = _get_active_server_name()
if _active_server:
    _current_log_file = get_server_log_path(_active_server, get_personality_name())
else:
    _current_log_file = LOG_DIR / f'{get_personality_name()}.log'

def update_log_file_path(server_name: str, personality_name: str = None):
    """
    Update the current log file path for a specific server.

    Args:
        server_name: Server name
        personality_name: Optional personality name
    """
    global _current_log_file
    _current_log_file = get_server_log_path(server_name, personality_name)

def get_logger(name='agent'):
    global _current_log_file
    logger = logging.getLogger(name)

    if logger.handlers:
        has_file = any(isinstance(h, RotatingFileHandler) for h in logger.handlers)
        if not has_file:
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

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    try:
        fh = RotatingFileHandler(_current_log_file, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
        fh.setLevel(logging.INFO)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except (PermissionError, OSError) as e:
        print(f"⚠️ Could not write to log file {_current_log_file}: {e}")
        print("📝 Falling back to console output only")

    return logger
