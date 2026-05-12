"""Atomic, thread-safe JSON document store.

Design goals (from the NoSQL migration plan):
- Atomic writes via tmp file + fsync + os.replace.
- In-memory cache to avoid re-parsing on every read.
- Per-path threading.Lock so multiple JsonStore instances pointing at the
  same file serialize their writes correctly within a single process.
- Optional schema_version field for forward-compatible migrations.
- Optional .bak sibling for critical data.

Not goals (single-process bot):
- Cross-process locking (would need fcntl). The bot runs as one process; the
  Supervisor will keep it that way.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Type

try:
    from pydantic import BaseModel, ValidationError as PydanticValidationError
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = None  # type: ignore


# Module-level registry of locks keyed by absolute path so that two
# JsonStore instances pointing at the same file share a single lock.
_PATH_LOCKS: Dict[str, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _PATH_LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


_MISSING = object()


class JsonStore:
    """Thread-safe atomic JSON document store with optional backup file."""

    def __init__(
        self,
        path: os.PathLike | str,
        *,
        default_factory: Optional[Callable[[], dict]] = None,
        schema_version: Optional[int] = None,
        keep_backup: bool = False,
        schema: Optional[Type[BaseModel]] = None,
        validate_on_load: bool = True,
        validate_on_write: bool = True,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _lock_for(self.path)
        self._default_factory = default_factory or (lambda: {})
        self._schema_version = schema_version
        self._keep_backup = keep_backup
        self._schema = schema
        self._validate_on_load = validate_on_load and PYDANTIC_AVAILABLE and schema is not None
        self._validate_on_write = validate_on_write and PYDANTIC_AVAILABLE and schema is not None
        self._cache: Optional[dict] = None
        self._loaded = False

    # ---- public API ------------------------------------------------------

    def load(self) -> dict:
        """Return the cached document, loading from disk on first access."""
        with self._lock:
            if not self._loaded:
                self._cache = self._read_from_disk()
                if self._validate_on_load and self._schema:
                    self._validate_data(self._cache)
                self._loaded = True
            return self._cache  # type: ignore[return-value]

    def reload(self) -> dict:
        """Force-reread from disk, discarding any in-memory cache."""
        with self._lock:
            self._cache = self._read_from_disk()
            self._loaded = True
            return self._cache

    def save(self) -> None:
        """Persist the in-memory document to disk atomically."""
        with self._lock:
            if not self._loaded:
                # Nothing to save; load first if you want to materialize default
                self._cache = self._read_from_disk()
                self._loaded = True
            if self._validate_on_write and self._schema:
                self._validate_data(self._cache or {})
            self._write_to_disk(self._cache or {})

    def update(self, mutator: Callable[[dict], Any]) -> Any:
        """Atomically load, mutate, and save. Returns whatever mutator returns.

        The mutator receives the live cached dict (mutate in place). If it
        returns a non-None dict, that replaces the document.
        """
        with self._lock:
            doc = self.load()
            result = mutator(doc)
            if isinstance(result, dict) and result is not doc:
                self._cache = result
            if self._validate_on_write and self._schema:
                self._validate_data(self._cache or {})
            self.save()
            return result

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Read a nested value with `a.b.c` notation."""
        node: Any = self.load()
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted_key: str, value: Any) -> None:
        """Write a nested value with `a.b.c` notation, creating dicts as needed."""
        with self._lock:
            doc = self.load()
            parts = dotted_key.split(".")
            node = doc
            for part in parts[:-1]:
                nxt = node.get(part)
                if not isinstance(nxt, dict):
                    nxt = {}
                    node[part] = nxt
                node = nxt
            node[parts[-1]] = value
            self.save()

    def snapshot(self) -> dict:
        """Return a deep copy of the current document (safe to mutate)."""
        with self._lock:
            return copy.deepcopy(self.load())

    # ---- internals -------------------------------------------------------

    def _read_from_disk(self) -> dict:
        if not self.path.exists():
            doc = self._default_factory()
            if self._schema_version is not None and "version" not in doc:
                doc["version"] = self._schema_version
            return doc

        try:
            with self.path.open("r", encoding="utf-8") as f:
                doc = json.load(f)
        except (json.JSONDecodeError, OSError):
            # Try the backup if present
            bak = self._bak_path()
            if bak.exists():
                try:
                    with bak.open("r", encoding="utf-8") as f:
                        doc = json.load(f)
                except Exception:
                    doc = self._default_factory()
            else:
                doc = self._default_factory()

        if not isinstance(doc, dict):
            # Not a dict-shaped doc; fall back to default
            doc = self._default_factory()
        if self._schema_version is not None and doc.get("version") is None:
            doc["version"] = self._schema_version
        return doc

    def _write_to_disk(self, doc: dict) -> None:
        # Write to tmp file in same directory, fsync, atomic replace.
        # Then optionally copy to .bak.
        directory = self.path.parent
        fd, tmp_name = tempfile.mkstemp(
            prefix=self.path.name + ".",
            suffix=".tmp",
            dir=str(directory),
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            # Best-effort cleanup - close fd first if still open
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                tmp_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except TypeError:
                # Python <3.8 fallback (we target 3.10+, but be safe)
                if tmp_path.exists():
                    tmp_path.unlink()
            raise

        if self._keep_backup:
            try:
                shutil.copy2(self.path, self._bak_path())
            except OSError:
                pass

    def _bak_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".bak")

    # ---- validation helpers -----------------------------------------------

    def _validate_data(self, data: dict) -> None:
        """Validate data against the Pydantic schema if available."""
        if not PYDANTIC_AVAILABLE or self._schema is None:
            return

        try:
            self._schema(**data)
        except PydanticValidationError as e:
            # Log validation error but don't crash in fail-soft mode
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Validation error for {self.path}: {e}. "
                "Data may be corrupted or schema mismatch."
            )
            # In fail-hard mode, we would re-raise here
            # For now, we just log and continue (fail-soft)

