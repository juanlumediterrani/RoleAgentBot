"""Append-only JSONL ring buffer with size/line rotation.

Used for time-series / interaction-history style data where we only care
about the tail and want O(1) appends without rewriting the whole document.

Rotation policy: when either max_lines or max_bytes is exceeded after an
append, the file is truncated to keep the last `keep_lines` entries (which
defaults to max_lines // 2).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections import deque
from pathlib import Path
from typing import Any, Callable, Deque, Iterable, Iterator, List, Optional


_PATH_LOCKS: dict[str, threading.RLock] = {}
_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock


class JsonlRingBuffer:
    """Append-only JSONL file with rotation by lines and/or bytes."""

    def __init__(
        self,
        path: os.PathLike | str,
        *,
        max_lines: int = 500,
        max_bytes: Optional[int] = 200 * 1024,
        keep_lines: Optional[int] = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_lines = max_lines
        self.max_bytes = max_bytes
        self.keep_lines = keep_lines if keep_lines is not None else max(1, max_lines // 2)
        self._lock = _lock_for(self.path)

    # ---- writes ----------------------------------------------------------

    def append(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(line)
                f.write("\n")
            if self._should_rotate():
                self.rotate()

    def append_many(self, records: Iterable[dict]) -> None:
        records = list(records)
        if not records:
            return
        with self._lock:
            with self.path.open("a", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")))
                    f.write("\n")
            if self._should_rotate():
                self.rotate()

    # ---- reads -----------------------------------------------------------

    def __len__(self) -> int:
        return self.count()

    def count(self) -> int:
        with self._lock:
            if not self.path.exists():
                return 0
            n = 0
            with self.path.open("rb") as f:
                for _ in f:
                    n += 1
            return n

    def tail(self, n: int) -> List[dict]:
        if n <= 0:
            return []
        with self._lock:
            if not self.path.exists():
                return []
            buf: Deque[str] = deque(maxlen=n)
            with self.path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        buf.append(line)
            return [self._safe_load(l) for l in buf if self._safe_load(l) is not None]

    def iter_records(self) -> Iterator[dict]:
        """Yield all records lazily. Caller must not hold the lock indefinitely."""
        with self._lock:
            if not self.path.exists():
                return
            # Read snapshot under lock to avoid mid-rotation surprises
            with self.path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            rec = self._safe_load(line)
            if rec is not None:
                yield rec

    def filter_tail(self, predicate: Callable[[dict], bool], limit: int) -> List[dict]:
        """Return up to `limit` most-recent records matching predicate."""
        if limit <= 0:
            return []
        out: Deque[dict] = deque(maxlen=limit)
        for rec in self.iter_records():
            if predicate(rec):
                out.append(rec)
        return list(out)

    # ---- rotation --------------------------------------------------------

    def _should_rotate(self) -> bool:
        if not self.path.exists():
            return False
        if self.max_bytes is not None:
            try:
                if self.path.stat().st_size > self.max_bytes:
                    return True
            except OSError:
                pass
        if self.max_lines is not None and self.max_lines > 0:
            # Cheap approximation: only check line count if size is large enough
            try:
                if self.path.stat().st_size > 0:
                    if self.count_unlocked() > self.max_lines:
                        return True
            except OSError:
                pass
        return False

    def count_unlocked(self) -> int:
        # Caller must hold self._lock
        if not self.path.exists():
            return 0
        n = 0
        with self.path.open("rb") as f:
            for _ in f:
                n += 1
        return n

    def rotate(self) -> None:
        """Truncate the file to keep only the last `keep_lines` entries."""
        with self._lock:
            if not self.path.exists():
                return
            with self.path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
            kept = lines[-self.keep_lines:] if self.keep_lines > 0 else []

            directory = self.path.parent
            fd, tmp_name = tempfile.mkstemp(
                prefix=self.path.name + ".",
                suffix=".rot",
                dir=str(directory),
            )
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as out:
                    out.writelines(kept)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp_path, self.path)
            except Exception:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                raise

    # ---- helpers ---------------------------------------------------------

    @staticmethod
    def _safe_load(line: str) -> Optional[dict]:
        try:
            obj = json.loads(line)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
