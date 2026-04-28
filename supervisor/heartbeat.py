"""Liveness tracking for supervised actors and jobs."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Heartbeat:
    """A single heartbeat slot. Owners call beat() periodically."""
    name: str
    timeout_seconds: float = 60.0
    last_beat: float = field(default_factory=time.monotonic)

    def beat(self) -> None:
        self.last_beat = time.monotonic()

    def is_alive(self, now: Optional[float] = None) -> bool:
        ts = now if now is not None else time.monotonic()
        return (ts - self.last_beat) <= self.timeout_seconds

    def age(self, now: Optional[float] = None) -> float:
        ts = now if now is not None else time.monotonic()
        return ts - self.last_beat


class HeartbeatRegistry:
    """Thread-safe registry of named heartbeats."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._beats: Dict[str, Heartbeat] = {}

    def register(self, name: str, *, timeout_seconds: float = 60.0) -> Heartbeat:
        with self._lock:
            hb = self._beats.get(name)
            if hb is None:
                hb = Heartbeat(name=name, timeout_seconds=timeout_seconds)
                self._beats[name] = hb
            else:
                hb.timeout_seconds = timeout_seconds
                hb.beat()
            return hb

    def unregister(self, name: str) -> None:
        with self._lock:
            self._beats.pop(name, None)

    def beat(self, name: str) -> None:
        with self._lock:
            hb = self._beats.get(name)
            if hb is not None:
                hb.beat()

    def status(self) -> Dict[str, dict]:
        now = time.monotonic()
        with self._lock:
            return {
                name: {
                    "alive": hb.is_alive(now),
                    "age_seconds": round(hb.age(now), 3),
                    "timeout_seconds": hb.timeout_seconds,
                }
                for name, hb in self._beats.items()
            }

    def dead(self) -> Dict[str, Heartbeat]:
        now = time.monotonic()
        with self._lock:
            return {name: hb for name, hb in self._beats.items() if not hb.is_alive(now)}
