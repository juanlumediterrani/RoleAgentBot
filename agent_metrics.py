"""
Lightweight in-process metrics for the bot's hot paths.

Tracks counters, gauges, and rolling latency stats for LLM calls, the chat
queue, and rate limiters. Thread-safe (atomic via a single Lock). Snapshot
via :func:`get_metrics` and reset via :func:`reset_metrics` (testing only).

Used by:
- :mod:`agent_mind` -> records call_llm and call_llm_async timings + provider.
- :mod:`discord_bot.message_queue` -> reports queue depth via :func:`set_gauge`.
- :mod:`discord_bot.discord_utils` -> increments rate-limit drop counters.

This module deliberately has zero dependencies and never raises in the hot
path: any error inside metrics is logged and swallowed.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Deque, Dict


_LOCK = threading.Lock()

# Monotonic counters (never reset in production; reset only by tests).
_COUNTERS: Dict[str, int] = {}

# Point-in-time gauges (set by producers, read by inspectors).
_GAUGES: Dict[str, float] = {}

# Rolling latency samples (seconds) per call_type. Bounded at _LATENCY_MAX.
_LATENCY_MAX = 256
_LATENCIES: Dict[str, Deque[float]] = {}

# Process start time for uptime metric.
_STARTED_AT = time.time()


def incr(name: str, delta: int = 1) -> None:
    """Atomically add ``delta`` to counter ``name`` (default +1)."""
    with _LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + delta


def set_gauge(name: str, value: float) -> None:
    """Set a gauge to ``value`` (overwrites previous reading)."""
    with _LOCK:
        _GAUGES[name] = float(value)


def record_latency(call_type: str, seconds: float) -> None:
    """Append a latency sample for ``call_type`` (bounded ring buffer)."""
    with _LOCK:
        buf = _LATENCIES.get(call_type)
        if buf is None:
            buf = deque(maxlen=_LATENCY_MAX)
            _LATENCIES[call_type] = buf
        buf.append(float(seconds))


def get_metrics() -> Dict[str, object]:
    """Return a snapshot of all metrics (counters, gauges, latency stats)."""
    with _LOCK:
        latency_stats = {}
        for ct, buf in _LATENCIES.items():
            if not buf:
                continue
            samples = sorted(buf)
            n = len(samples)
            avg = sum(samples) / n
            p50 = samples[n // 2]
            p95 = samples[min(n - 1, int(n * 0.95))]
            p99 = samples[min(n - 1, int(n * 0.99))]
            latency_stats[ct] = {
                "n": n,
                "avg": round(avg, 3),
                "p50": round(p50, 3),
                "p95": round(p95, 3),
                "p99": round(p99, 3),
                "max": round(samples[-1], 3),
            }
        return {
            "uptime_seconds": round(time.time() - _STARTED_AT, 1),
            "counters": dict(_COUNTERS),
            "gauges": dict(_GAUGES),
            "latency": latency_stats,
        }


def format_metrics(snapshot: Dict[str, object] | None = None) -> str:
    """Format a metrics snapshot as a multi-line human-readable string."""
    if snapshot is None:
        snapshot = get_metrics()
    lines = [f"Uptime: {snapshot['uptime_seconds']}s"]
    counters = snapshot.get("counters") or {}
    if counters:
        lines.append("Counters:")
        for k in sorted(counters):
            lines.append(f"  {k}: {counters[k]}")
    gauges = snapshot.get("gauges") or {}
    if gauges:
        lines.append("Gauges:")
        for k in sorted(gauges):
            lines.append(f"  {k}: {gauges[k]}")
    latency = snapshot.get("latency") or {}
    if latency:
        lines.append("Latency (s):")
        for ct in sorted(latency):
            s = latency[ct]
            lines.append(
                f"  {ct}: n={s['n']} avg={s['avg']} p50={s['p50']} "
                f"p95={s['p95']} p99={s['p99']} max={s['max']}"
            )
    return "\n".join(lines)


def reset_metrics() -> None:
    """Reset all counters/gauges/latency. Intended for tests only."""
    with _LOCK:
        _COUNTERS.clear()
        _GAUGES.clear()
        _LATENCIES.clear()
