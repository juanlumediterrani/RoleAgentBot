"""Async job scheduler with timeouts, retries, semaphores and circuit breakers.

Replaces the duplicated scheduling logic in run.py and agent_discord.py
with a single source of truth. State (last_run / next_run) can be
persisted via a JsonStore so the schedule survives process restarts.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

from supervisor.policies import (
    CircuitBreaker,
    CircuitBreakerOpen,
    RetryPolicy,
)


JobFn = Callable[[], Awaitable[Any]]


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@dataclass
class Schedule:
    """Recurring schedule descriptor.

    Use Schedule.every(seconds=..., minutes=..., hours=...) for fixed-period.
    """
    period_seconds: float
    initial_delay_seconds: float = 0.0

    @classmethod
    def every(
        cls,
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        initial_delay_seconds: float = 0.0,
    ) -> "Schedule":
        total = seconds + minutes * 60 + hours * 3600
        if total <= 0:
            raise ValueError("schedule period must be > 0")
        return cls(period_seconds=total, initial_delay_seconds=initial_delay_seconds)

    def first_run_at(self, now: float) -> float:
        return now + self.initial_delay_seconds

    def next_run_after(self, now: float) -> float:
        return now + self.period_seconds


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

class JobStatus(enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class Job:
    name: str
    fn: JobFn
    schedule: Schedule
    timeout_seconds: Optional[float] = 300.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    semaphore_name: Optional[str] = None
    breaker: Optional[CircuitBreaker] = None
    enabled: bool = True
    # Runtime state -------------------------------------------------------
    status: JobStatus = JobStatus.IDLE
    next_run_monotonic: float = 0.0
    last_run_started_at: Optional[float] = None
    last_run_duration: Optional[float] = None
    last_error: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0


# ---------------------------------------------------------------------------
# JobScheduler
# ---------------------------------------------------------------------------

class JobScheduler:
    """Async scheduler running registered jobs cooperatively."""

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        tick_seconds: float = 1.0,
        enable_persistence: bool = True,
    ) -> None:
        self._jobs: Dict[str, Job] = {}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._tick = tick_seconds
        self._stop_event: Optional[asyncio.Event] = None
        self._logger = logger or logging.getLogger("scheduler")
        self._trigger_now: set[str] = set()
        self._lock = asyncio.Lock()
        self._enable_persistence = enable_persistence
        self._scheduler_state = None

        if enable_persistence:
            try:
                from supervisor.scheduler_state import get_scheduler_state
                self._scheduler_state = get_scheduler_state()
                self._logger.info("[Scheduler] State persistence enabled")
            except Exception as e:
                self._logger.warning(f"[Scheduler] Failed to enable state persistence: {e}")

    # ---- registration ----------------------------------------------------

    def register_semaphore(self, name: str, max_concurrent: int) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._semaphores[name] = asyncio.Semaphore(max_concurrent)

    def register(
        self,
        name: str,
        fn: JobFn,
        schedule: Schedule,
        *,
        timeout_seconds: Optional[float] = 300.0,
        retry: Optional[RetryPolicy] = None,
        semaphore: Optional[str] = None,
        breaker: Optional[CircuitBreaker] = None,
        enabled: bool = True,
    ) -> Job:
        if name in self._jobs:
            raise ValueError(f"job already registered: {name}")
        if semaphore is not None and semaphore not in self._semaphores:
            raise KeyError(f"unknown semaphore: {semaphore}")
        job = Job(
            name=name,
            fn=fn,
            schedule=schedule,
            timeout_seconds=timeout_seconds,
            retry=retry or RetryPolicy(),
            semaphore_name=semaphore,
            breaker=breaker,
            enabled=enabled,
        )

        # Load persisted next_run if available
        if self._scheduler_state:
            persisted_next_run = self._scheduler_state.get_job_next_run(name)
            if persisted_next_run is not None:
                job.next_run_monotonic = persisted_next_run
                self._logger.debug(f"[Scheduler] Restored next_run for '{name}': {persisted_next_run}")
            else:
                job.next_run_monotonic = job.schedule.first_run_at(time.monotonic())
        else:
            job.next_run_monotonic = job.schedule.first_run_at(time.monotonic())

        self._jobs[name] = job
        return job

    def unregister(self, name: str) -> None:
        self._jobs.pop(name, None)

    # ---- runtime control -------------------------------------------------

    async def trigger_now(self, name: str) -> None:
        if name not in self._jobs:
            raise KeyError(f"unknown job: {name}")
        async with self._lock:
            self._trigger_now.add(name)

    def pause(self, name: str) -> None:
        job = self._jobs[name]
        job.status = JobStatus.PAUSED
        job.enabled = False

    def resume(self, name: str) -> None:
        job = self._jobs[name]
        job.status = JobStatus.IDLE
        job.enabled = True
        job.next_run_monotonic = time.monotonic()

    def status(self) -> Dict[str, dict]:
        return {
            name: {
                "status": j.status.value,
                "enabled": j.enabled,
                "success_count": j.success_count,
                "failure_count": j.failure_count,
                "last_error": j.last_error,
                "last_run_duration": j.last_run_duration,
                "next_run_in_seconds": max(0.0, j.next_run_monotonic - time.monotonic()),
            }
            for name, j in self._jobs.items()
        }

    def metrics_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines = [
            "# HELP rab_job_success_count Total number of successful job executions",
            "# TYPE rab_job_success_count counter",
            "# HELP rab_job_failure_count Total number of failed job executions",
            "# TYPE rab_job_failure_count counter",
            "# HELP rab_job_last_run_duration_seconds Last job execution duration in seconds",
            "# TYPE rab_job_last_run_duration_seconds gauge",
            "# HELP rab_job_next_run_seconds Seconds until next job execution",
            "# TYPE rab_job_next_run_seconds gauge",
            "# HELP rab_job_enabled Whether job is enabled (1) or disabled (0)",
            "# TYPE rab_job_enabled gauge",
        ]

        for name, job in self._jobs.items():
            lines.append(f'rab_job_success_count{{job="{name}"}} {job.success_count}')
            lines.append(f'rab_job_failure_count{{job="{name}"}} {job.failure_count}')
            if job.last_run_duration:
                lines.append(f'rab_job_last_run_duration_seconds{{job="{name}"}} {job.last_run_duration:.2f}')
            next_run = max(0.0, job.next_run_monotonic - time.monotonic())
            lines.append(f'rab_job_next_run_seconds{{job="{name}"}} {next_run:.2f}')
            lines.append(f'rab_job_enabled{{job="{name}"}} {1 if job.enabled else 0}')

        return "\n".join(lines)

    # ---- main loop -------------------------------------------------------

    async def run_forever(self) -> None:
        self._stop_event = asyncio.Event()
        running_tasks: Dict[str, asyncio.Task] = {}
        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                async with self._lock:
                    triggered = set(self._trigger_now)
                    self._trigger_now.clear()

                for name, job in list(self._jobs.items()):
                    if not job.enabled:
                        continue
                    is_running = name in running_tasks and not running_tasks[name].done()
                    due = now >= job.next_run_monotonic or name in triggered
                    if due and not is_running:
                        running_tasks[name] = asyncio.create_task(
                            self._execute_job(job), name=f"job:{name}"
                        )

                # Reap completed tasks
                done = [n for n, t in running_tasks.items() if t.done()]
                for n in done:
                    t = running_tasks.pop(n)
                    exc = t.exception() if not t.cancelled() else None
                    if exc:
                        self._logger.error(f"[scheduler] job {n!r} task error: {exc}")

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self._tick)
                except asyncio.TimeoutError:
                    pass
        finally:
            # Cancel any in-flight job tasks on shutdown
            for n, t in running_tasks.items():
                if not t.done():
                    t.cancel()
            await asyncio.gather(*running_tasks.values(), return_exceptions=True)

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        # Persist shutdown time
        if self._scheduler_state:
            self._scheduler_state.save_last_shutdown()

    # ---- job execution ---------------------------------------------------

    async def _execute_job(self, job: Job) -> None:
        job.status = JobStatus.RUNNING
        job.last_run_started_at = time.monotonic()
        sem = self._semaphores.get(job.semaphore_name) if job.semaphore_name else None
        try:
            if job.breaker is not None:
                try:
                    job.breaker.before_call()
                except CircuitBreakerOpen:
                    job.last_error = "circuit_open"
                    job.failure_count += 1
                    job.status = JobStatus.FAILED
                    job.next_run_monotonic = job.schedule.next_run_after(time.monotonic())
                    self._logger.warning(f"[scheduler] {job.name!r} skipped: circuit open")
                    return

            if sem is not None:
                await sem.acquire()
            try:
                await self._run_with_retry(job)
            finally:
                if sem is not None:
                    sem.release()
        finally:
            job.last_run_duration = time.monotonic() - (job.last_run_started_at or time.monotonic())
            job.next_run_monotonic = job.schedule.next_run_after(time.monotonic())
            if job.status is JobStatus.RUNNING:
                job.status = JobStatus.IDLE

            # Persist next_run to avoid double-trigger after restart
            if self._scheduler_state:
                self._scheduler_state.save_job_next_run(job.name, job.next_run_monotonic)

    async def _run_with_retry(self, job: Job) -> None:
        last_exc: Optional[BaseException] = None
        for attempt in range(job.retry.max_attempts):
            try:
                if job.timeout_seconds is not None:
                    await asyncio.wait_for(job.fn(), timeout=job.timeout_seconds)
                else:
                    await job.fn()
                job.success_count += 1
                job.last_error = None
                if job.breaker is not None:
                    job.breaker.record_success()
                return
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError as e:
                last_exc = e
                job.last_error = "timeout"
                self._logger.warning(
                    f"[scheduler] {job.name!r} timeout (attempt {attempt + 1}/{job.retry.max_attempts})"
                )
            except Exception as e:
                last_exc = e
                job.last_error = f"{type(e).__name__}: {e}"
                self._logger.warning(
                    f"[scheduler] {job.name!r} failed (attempt {attempt + 1}/{job.retry.max_attempts}): {e}"
                )

            # Backoff before next attempt (except after the last)
            if attempt + 1 < job.retry.max_attempts:
                delay = job.retry.delay_for(attempt)
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    raise

        job.failure_count += 1
        job.status = JobStatus.FAILED
        if job.breaker is not None:
            job.breaker.record_failure()
        if last_exc is not None:
            self._logger.error(
                f"[scheduler] {job.name!r} exhausted retries: {job.last_error}"
            )


def now_iso() -> str:
    """UTC ISO8601 helper for state persistence."""
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
