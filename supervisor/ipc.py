"""Unix-socket IPC for runtime control of Supervisor + JobScheduler.

Protocol: newline-delimited JSON. Each request is a JSON object on its
own line. Each response is also a JSON object on its own line.

Commands:
  {"cmd": "status"}                       -> {"actors": {...}, "jobs": {...}, "heartbeats": {...}}
  {"cmd": "trigger", "job": "name"}       -> {"ok": true}
  {"cmd": "pause", "job": "name"}         -> {"ok": true}
  {"cmd": "resume", "job": "name"}        -> {"ok": true}
  {"cmd": "restart", "actor": "name"}     -> {"ok": true}
  {"cmd": "shutdown"}                     -> {"ok": true}
  {"cmd": "ping"}                         -> {"pong": true}
  {"cmd": "metrics"}                      -> {"metrics": "...prometheus text..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional

from supervisor.scheduler import JobScheduler
from supervisor.supervisor import Supervisor


CommandHandler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]


class IpcServer:
    def __init__(
        self,
        socket_path: os.PathLike | str,
        *,
        supervisor: Optional[Supervisor] = None,
        scheduler: Optional[JobScheduler] = None,
        on_shutdown: Optional[Callable[[], Awaitable[None]]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.socket_path = Path(socket_path)
        self.supervisor = supervisor
        self.scheduler = scheduler
        self.on_shutdown = on_shutdown
        self._server: Optional[asyncio.AbstractServer] = None
        self._logger = logger or logging.getLogger("ipc")

    async def start(self) -> None:
        # Remove a stale socket file if any (single-process bot).
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path),
        )
        try:
            os.chmod(self.socket_path, 0o660)
        except OSError:
            pass
        self._logger.info(f"[ipc] listening on {self.socket_path}")

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
        if self.socket_path.exists():
            try:
                self.socket_path.unlink()
            except OSError:
                pass

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            while True:
                line = await reader.readline()
                if not line:
                    return
                response = await self._dispatch(line)
                writer.write((json.dumps(response) + "\n").encode("utf-8"))
                await writer.drain()
        except (ConnectionResetError, asyncio.IncompleteReadError):
            return
        except Exception as e:
            self._logger.exception(f"[ipc] client handler error: {e}")
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _dispatch(self, raw_line: bytes) -> Dict[str, Any]:
        try:
            req = json.loads(raw_line.decode("utf-8"))
        except json.JSONDecodeError as e:
            return {"error": f"invalid_json: {e}"}
        if not isinstance(req, dict):
            return {"error": "request must be a JSON object"}
        cmd = req.get("cmd")
        try:
            if cmd == "ping":
                return {"pong": True}
            if cmd == "status":
                return self._status()
            if cmd == "trigger":
                return await self._trigger(req)
            if cmd == "pause":
                return self._pause(req)
            if cmd == "resume":
                return self._resume(req)
            if cmd == "restart":
                return await self._restart(req)
            if cmd == "shutdown":
                return await self._shutdown()
            if cmd == "metrics":
                return self._metrics()
            return {"error": f"unknown_cmd: {cmd}"}
        except KeyError as e:
            return {"error": f"not_found: {e}"}
        except Exception as e:
            self._logger.exception(f"[ipc] command {cmd!r} failed: {e}")
            return {"error": f"{type(e).__name__}: {e}"}

    # ---- command implementations ----------------------------------------

    def _status(self) -> Dict[str, Any]:
        return {
            "actors": self.supervisor.status() if self.supervisor else {},
            "jobs": self.scheduler.status() if self.scheduler else {},
            "heartbeats": self.supervisor.heartbeats.status() if self.supervisor else {},
        }

    async def _trigger(self, req: Dict[str, Any]) -> Dict[str, Any]:
        if not self.scheduler:
            return {"error": "no_scheduler"}
        name = req.get("job")
        if not name:
            return {"error": "missing_field: job"}
        await self.scheduler.trigger_now(name)
        return {"ok": True}

    def _pause(self, req: Dict[str, Any]) -> Dict[str, Any]:
        if not self.scheduler:
            return {"error": "no_scheduler"}
        name = req.get("job")
        if not name:
            return {"error": "missing_field: job"}
        self.scheduler.pause(name)
        return {"ok": True}

    def _resume(self, req: Dict[str, Any]) -> Dict[str, Any]:
        if not self.scheduler:
            return {"error": "no_scheduler"}
        name = req.get("job")
        if not name:
            return {"error": "missing_field: job"}
        self.scheduler.resume(name)
        return {"ok": True}

    async def _restart(self, req: Dict[str, Any]) -> Dict[str, Any]:
        if not self.supervisor:
            return {"error": "no_supervisor"}
        name = req.get("actor")
        if not name:
            return {"error": "missing_field: actor"}
        await self.supervisor.restart(name)
        return {"ok": True}

    async def _shutdown(self) -> Dict[str, Any]:
        if self.on_shutdown is not None:
            asyncio.create_task(self.on_shutdown())
        return {"ok": True}

    def _metrics(self) -> Dict[str, Any]:
        if not self.scheduler:
            return {"error": "no_scheduler"}
        return {"metrics": self.scheduler.metrics_prometheus()}


# ---------------------------------------------------------------------------
# Minimal client for tools/rabctl.py
# ---------------------------------------------------------------------------

async def send_command(socket_path: os.PathLike | str, command: Dict[str, Any]) -> Dict[str, Any]:
    """Send a single command to an IPC server and return the response."""
    reader, writer = await asyncio.open_unix_connection(path=str(socket_path))
    try:
        writer.write((json.dumps(command) + "\n").encode("utf-8"))
        await writer.drain()
        line = await reader.readline()
        if not line:
            return {"error": "empty_response"}
        return json.loads(line.decode("utf-8"))
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
