"""Restart, retry and circuit-breaker policies for supervised actors and jobs."""

from __future__ import annotations

import enum
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Backoff
# ---------------------------------------------------------------------------

class BackoffStrategy(enum.Enum):
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


def compute_backoff(
    attempt: int,
    *,
    strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
    base_seconds: float = 1.0,
    max_seconds: float = 300.0,
    jitter: float = 0.1,
) -> float:
    """Compute the delay before the (attempt+1)-th retry.

    `attempt` is 0-indexed (0 = first retry).
    """
    if attempt < 0:
        attempt = 0
    if strategy is BackoffStrategy.FIXED:
        delay = base_seconds
    elif strategy is BackoffStrategy.LINEAR:
        delay = base_seconds * (attempt + 1)
    else:  # EXPONENTIAL
        delay = base_seconds * (2 ** attempt)

    delay = min(delay, max_seconds)
    if jitter > 0:
        delta = delay * jitter
        delay += random.uniform(-delta, delta)
    return max(0.0, delay)


# ---------------------------------------------------------------------------
# Restart policy (for Actors)
# ---------------------------------------------------------------------------

class RestartType(enum.Enum):
    PERMANENT = "permanent"   # always restart on any termination
    TRANSIENT = "transient"   # restart only on abnormal termination
    TEMPORARY = "temporary"   # never restart


@dataclass
class RestartPolicy:
    type: RestartType = RestartType.PERMANENT
    max_restarts: int = 5
    within_seconds: float = 60.0
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    base_seconds: float = 1.0
    max_seconds: float = 300.0
    jitter: float = 0.1
    # Internal state ------------------------------------------------------
    _events: List[float] = field(default_factory=list, repr=False)

    def should_restart(self, *, normal_exit: bool) -> bool:
        if self.type is RestartType.TEMPORARY:
            return False
        if self.type is RestartType.TRANSIENT and normal_exit:
            return False
        return True

    def record_restart(self) -> None:
        now = time.monotonic()
        self._events.append(now)
        cutoff = now - self.within_seconds
        self._events = [t for t in self._events if t >= cutoff]

    def is_burning(self) -> bool:
        """True if the actor exceeded max_restarts within the window."""
        now = time.monotonic()
        cutoff = now - self.within_seconds
        recent = [t for t in self._events if t >= cutoff]
        return len(recent) > self.max_restarts

    def next_delay(self) -> float:
        attempt = max(0, len(self._events) - 1)
        return compute_backoff(
            attempt,
            strategy=self.backoff,
            base_seconds=self.base_seconds,
            max_seconds=self.max_seconds,
            jitter=self.jitter,
        )


# ---------------------------------------------------------------------------
# Retry policy (for jobs / one-shot calls)
# ---------------------------------------------------------------------------

@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    base_seconds: float = 1.0
    max_seconds: float = 60.0
    jitter: float = 0.1

    def delay_for(self, attempt: int) -> float:
        return compute_backoff(
            attempt,
            strategy=self.backoff,
            base_seconds=self.base_seconds,
            max_seconds=self.max_seconds,
            jitter=self.jitter,
        )


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CircuitBreakerOpen(Exception):
    """Raised when the circuit is open and the call is rejected."""


class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_seconds: float = 60.0
    half_open_successes_required: int = 1
    # State ---------------------------------------------------------------
    _state: CircuitState = field(default=CircuitState.CLOSED, repr=False)
    _failure_count: int = field(default=0, repr=False)
    _opened_at: Optional[float] = field(default=None, repr=False)
    _half_open_successes: int = field(default=0, repr=False)

    @property
    def state(self) -> CircuitState:
        # Allow transition OPEN -> HALF_OPEN once recovery elapses.
        if self._state is CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self.recovery_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_successes = 0
        return self._state

    def before_call(self) -> None:
        st = self.state
        if st is CircuitState.OPEN:
            raise CircuitBreakerOpen("circuit breaker is open")

    def record_success(self) -> None:
        st = self.state
        if st is CircuitState.HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.half_open_successes_required:
                self._reset()
        else:
            self._reset()

    def record_failure(self) -> None:
        if self._state is CircuitState.HALF_OPEN:
            self._open()
            return
        self._failure_count += 1
        if self._failure_count >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_successes = 0

    def _reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None
        self._half_open_successes = 0
