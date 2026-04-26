"""Lightweight asyncio supervisor for long-lived coroutines (Actors).

An Actor wraps a coroutine factory. The Supervisor runs it as an asyncio
task and applies the configured RestartPolicy on termination, with
backoff. Burning actors (those exceeding max_restarts in the rolling
window) are quarantined.

Designed to be the single entry-point for the bot main loop replacing
the current `run.py` orchestrator that mixes scheduler + subprocess
launches. Subprocess actors can be added later by switching the actor
body to one that spawns and awaits a subprocess; the supervision
contract is the same.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from supervisor.heartbeat import HeartbeatRegistry
from supervisor.policies import RestartPolicy, RestartType


CoroFactory = Callable[[], Awaitable[Any]]


class ActorState(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    RESTARTING = "restarting"
    BURNING = "burning"      # exceeded restart budget
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class Actor:
    name: str
    factory: CoroFactory
    policy: RestartPolicy = field(default_factory=RestartPolicy)
    state: ActorState = ActorState.PENDING
    last_error: Optional[str] = None
    started_at: Optional[float] = None
    stopped_at: Optional[float] = None
    restart_count: int = 0
    _task: Optional[asyncio.Task] = field(default=None, repr=False)
    _stop_event: Optional[asyncio.Event] = field(default=None, repr=False)


class Supervisor:
    """Manages a set of Actors with restart policies and heartbeats."""

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
        heartbeats: Optional[HeartbeatRegistry] = None,
    ) -> None:
        self._actors: Dict[str, Actor] = {}
        self._lock = asyncio.Lock()
        self._logger = logger or logging.getLogger("supervisor")
        self._shutting_down = False
        self.heartbeats = heartbeats or HeartbeatRegistry()

    # ---- public API ------------------------------------------------------

    async def add_actor(
        self,
        name: str,
        factory: CoroFactory,
        *,
        policy: Optional[RestartPolicy] = None,
        autostart: bool = True,
        heartbeat_timeout: Optional[float] = None,
    ) -> Actor:
        async with self._lock:
            if name in self._actors:
                raise ValueError(f"actor already registered: {name}")
            actor = Actor(name=name, factory=factory, policy=policy or RestartPolicy())
            self._actors[name] = actor
        if heartbeat_timeout is not None:
            self.heartbeats.register(name, timeout_seconds=heartbeat_timeout)
        if autostart:
            await self.start(name)
        return actor

    async def start(self, name: str) -> None:
        actor = self._require(name)
        if actor._task and not actor._task.done():
            return
        actor._stop_event = asyncio.Event()
        actor.state = ActorState.RUNNING
        actor.started_at = time.monotonic()
        actor._task = asyncio.create_task(self._run_actor(actor), name=f"actor:{name}")

    async def stop(self, name: str, *, timeout: float = 10.0) -> None:
        actor = self._require(name)
        if actor._task is None or actor._task.done():
            actor.state = ActorState.STOPPED
            return
        actor.state = ActorState.STOPPING
        if actor._stop_event is not None:
            actor._stop_event.set()
        actor._task.cancel()
        try:
            await asyncio.wait_for(actor._task, timeout=timeout)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        actor.state = ActorState.STOPPED
        actor.stopped_at = time.monotonic()

    async def restart(self, name: str, *, timeout: float = 10.0) -> None:
        await self.stop(name, timeout=timeout)
        actor = self._require(name)
        actor.policy.record_restart()
        actor.restart_count += 1
        await self.start(name)

    async def shutdown(self, *, timeout: float = 30.0) -> None:
        self._shutting_down = True
        names = list(self._actors.keys())
        await asyncio.gather(
            *[self.stop(n, timeout=timeout / max(1, len(names))) for n in names],
            return_exceptions=True,
        )

    def status(self) -> Dict[str, dict]:
        out = {}
        for name, a in self._actors.items():
            out[name] = {
                "state": a.state.value,
                "restart_count": a.restart_count,
                "last_error": a.last_error,
                "started_at": a.started_at,
                "stopped_at": a.stopped_at,
            }
        return out

    def get(self, name: str) -> Actor:
        return self._require(name)

    # ---- internals -------------------------------------------------------

    def _require(self, name: str) -> Actor:
        actor = self._actors.get(name)
        if actor is None:
            raise KeyError(f"unknown actor: {name}")
        return actor

    async def _run_actor(self, actor: Actor) -> None:
        while True:
            normal_exit = False
            try:
                self._logger.info(f"[supervisor] starting actor {actor.name!r}")
                actor.state = ActorState.RUNNING
                actor.last_error = None
                await actor.factory()
                normal_exit = True
                self._logger.info(f"[supervisor] actor {actor.name!r} finished normally")
            except asyncio.CancelledError:
                self._logger.info(f"[supervisor] actor {actor.name!r} cancelled")
                actor.state = ActorState.STOPPED
                raise
            except Exception as e:
                actor.last_error = f"{type(e).__name__}: {e}"
                self._logger.exception(
                    f"[supervisor] actor {actor.name!r} crashed: {actor.last_error}"
                )

            # Decide whether to restart.
            if self._shutting_down:
                actor.state = ActorState.STOPPED
                return
            if not actor.policy.should_restart(normal_exit=normal_exit):
                actor.state = ActorState.STOPPED
                return

            actor.policy.record_restart()
            actor.restart_count += 1

            if actor.policy.is_burning():
                actor.state = ActorState.BURNING
                self._logger.error(
                    f"[supervisor] actor {actor.name!r} exceeded restart budget "
                    f"({actor.policy.max_restarts} in {actor.policy.within_seconds}s); "
                    f"quarantined"
                )
                return

            delay = actor.policy.next_delay()
            actor.state = ActorState.RESTARTING
            self._logger.warning(
                f"[supervisor] restarting actor {actor.name!r} in {delay:.2f}s "
                f"(attempt {actor.restart_count})"
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                actor.state = ActorState.STOPPED
                raise


# Convenience: wrap a subprocess as an actor body
async def subprocess_actor_body(
    *cmd: str,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    on_line: Optional[Callable[[str], None]] = None,
) -> int:
    """Run a subprocess and stream stdout. Returns exit code; raises on signals.

    Usable as the factory of an Actor when external isolation is desired.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if on_line:
                on_line(line)
        rc = await proc.wait()
        if rc != 0:
            raise RuntimeError(f"subprocess exited with code {rc}")
        return rc
    except asyncio.CancelledError:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        raise
