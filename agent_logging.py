"""Centralised logging for the bot.

Design goals:

1. **Global runtime log** — ``logs/runtime.log`` receives only global records
   (startup, shutdown, system-level events). Server-specific records are
   excluded to avoid duplication.
2. **Per-server files without cross-contamination** — records emitted while a
   server context is bound go to ``logs/<server>/<personality>.log``.
   Routing is done by a demux handler that reads a ``ContextVar``; because
   ``ContextVar`` propagates through asyncio tasks, every coroutine spawned
   inside a ``with server_log_context(...)`` block lands in the right file.
3. **No global-mutation traps** — the deprecated ``update_log_file_path`` is
   kept as a thin wrapper over :func:`bind_server_context` so existing callers
   do not break, but the old broken behaviour (mutating a global path shared
   across already-bound handlers) is gone.
"""

from __future__ import annotations

import contextvars
import logging
from contextlib import contextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

RUNTIME_LOG_FILE = LOG_DIR / 'runtime.log'


# ---------------------------------------------------------------------------
# Server-scoped context
# ---------------------------------------------------------------------------

_ctx_server_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "ragentbot_server_id", default=None
)
_ctx_personality: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "ragentbot_personality", default=None
)


def bind_server_context(server_id: Optional[str], personality_name: Optional[str] = None) -> None:
    """Pin the current asyncio/thread context to a specific server.

    Any log record emitted from this point onwards (within the same context)
    will be tee'd to the server-specific log file in addition to the shared
    runtime log. Safe to call multiple times; each call replaces the binding
    for the current context only.
    """
    _ctx_server_id.set(server_id)
    _ctx_personality.set(personality_name)


@contextmanager
def server_log_context(server_id: Optional[str], personality_name: Optional[str] = None):
    """Context manager flavour of :func:`bind_server_context`.

    Use this around event handlers (e.g. ``on_message``) so the binding is
    scoped to a single event instead of leaking across the process.
    """
    sid_token = _ctx_server_id.set(server_id)
    pers_token = _ctx_personality.set(personality_name)
    try:
        yield
    finally:
        _ctx_server_id.reset(sid_token)
        _ctx_personality.reset(pers_token)


def get_personality_name():
    """Best-effort personality name for log file naming.

    Preference: ``$PERSONALITY`` env var → current runtime personality dir →
    personality JSON ``name`` field → literal ``"agent"``.
    """
    import os
    env_personality = os.getenv('PERSONALITY')
    if env_personality:
        return env_personality.lower()

    try:
        from agent_runtime import get_personality_directory
        personality_dir = get_personality_directory()
        if personality_dir:
            return os.path.basename(personality_dir).lower()
    except Exception:
        pass

    try:
        from agent_engine import PERSONALITY
        return PERSONALITY.get("name", "agent").lower()
    except Exception:
        return "agent"


def _sanitize_segment(name: str) -> str:
    name = (name or "").lower().replace(' ', '_').replace('-', '_')
    return ''.join(c for c in name if c.isalnum() or c == '_') or "unknown"


def get_server_log_path(server_name: str, personality_name: Optional[str] = None) -> Path:
    """Compute (and create) the path ``logs/<server>/<personality>.log``."""
    server_sanitized = _sanitize_segment(server_name)
    server_dir = LOG_DIR / server_sanitized
    try:
        server_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        print(f"⚠️ Could not create server log directory {server_dir}: {e}")
        print(f"📝 Falling back to base log directory: {LOG_DIR}")
        server_dir = LOG_DIR

    log_name = _sanitize_segment(personality_name or get_personality_name())
    log_file = server_dir / f'{log_name}.log'

    try:
        log_file.touch(exist_ok=True)
    except (PermissionError, OSError) as e:
        print(f"⚠️ Could not create log file {log_file}: {e}")
        fallback_file = LOG_DIR / f'{log_name}.log'
        print(f"📝 Falling back to log file: {fallback_file}")
        return fallback_file

    return log_file


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

_FORMATTER = logging.Formatter('%(asctime)s %(levelname)s %(name)s%(server_suffix)s: %(message)s')


class _ServerContextFilter(logging.Filter):
    """Stamp each record with whatever server/personality the context holds."""

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        sid = _ctx_server_id.get()
        pers = _ctx_personality.get()
        record.server_id = sid
        record.personality = pers
        record.server_suffix = f" [srv={sid}]" if sid else ""
        return True


class _RuntimeOnlyFilter(logging.Filter):
    """Filter out server-bound records from the runtime log to avoid duplication.

    Records with a server_id should go ONLY to the per-server log file,
    not to the global runtime.log.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        sid = _ctx_server_id.get()
        # Reject records that have server context - they go to per-server logs
        if sid:
            return False
        # Accept only global records without server context
        return True


class _ServerDemuxHandler(logging.Handler):
    """Tee every context-bound record into its per-server log file."""

    def __init__(self) -> None:
        super().__init__()
        self._handlers: dict[tuple[str, str], RotatingFileHandler] = {}

    def _get_handler(self, server_id: str, personality: str) -> Optional[RotatingFileHandler]:
        key = (server_id, personality)
        h = self._handlers.get(key)
        if h is not None:
            return h
        try:
            path = get_server_log_path(server_id, personality)
            h = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding='utf-8')
            h.setFormatter(_FORMATTER)
            h.setLevel(logging.INFO)
            self._handlers[key] = h
            return h
        except (PermissionError, OSError) as e:
            print(f"⚠️ Cannot open server log {server_id}/{personality}: {e}")
            return None

    def emit(self, record: logging.LogRecord) -> None:  # type: ignore[override]
        sid = getattr(record, 'server_id', None)
        if not sid:
            return
        pers = getattr(record, 'personality', None) or get_personality_name()
        handler = self._get_handler(_sanitize_segment(sid), _sanitize_segment(pers))
        if handler is None:
            return
        try:
            handler.emit(record)
        except Exception:
            self.handleError(record)


def _build_stream_handler() -> logging.Handler:
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(_FORMATTER)
    ch.addFilter(_ServerContextFilter())
    return ch


def _build_runtime_handler() -> Optional[logging.Handler]:
    try:
        fh = RotatingFileHandler(RUNTIME_LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
        fh.setLevel(logging.INFO)
        fh.setFormatter(_FORMATTER)
        # Use RuntimeOnlyFilter to exclude server-bound records from runtime.log
        fh.addFilter(_RuntimeOnlyFilter())
        return fh
    except (PermissionError, OSError) as e:
        print(f"⚠️ Could not open runtime log {RUNTIME_LOG_FILE}: {e}")
        return None


_DEMUX_HANDLER: Optional[_ServerDemuxHandler] = None


def _get_demux_handler() -> _ServerDemuxHandler:
    global _DEMUX_HANDLER
    if _DEMUX_HANDLER is None:
        _DEMUX_HANDLER = _ServerDemuxHandler()
        _DEMUX_HANDLER.setLevel(logging.INFO)
        _DEMUX_HANDLER.addFilter(_ServerContextFilter())
    return _DEMUX_HANDLER


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_logger(name: str = 'agent') -> logging.Logger:
    """Return a logger wired to console + runtime log + per-server demux.

    Idempotent: calling twice with the same name does not duplicate handlers.
    """
    logger = logging.getLogger(name)
    if getattr(logger, '_ragentbot_wired', False):
        return logger

    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.addHandler(_build_stream_handler())
    rh = _build_runtime_handler()
    if rh is not None:
        logger.addHandler(rh)
    logger.addHandler(_get_demux_handler())

    logger._ragentbot_wired = True  # type: ignore[attr-defined]
    return logger


def update_log_file_path(server_id: str, personality_name: Optional[str] = None) -> None:
    """Backwards-compatible shim.

    Previously this mutated a global ``_current_log_file`` which caused
    cross-server contamination because handlers were bound at logger
    creation. The new routing is context-driven, so this function simply
    binds the calling context to the given server.
    """
    bind_server_context(server_id, personality_name)
