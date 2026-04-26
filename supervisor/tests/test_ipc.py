"""Tests for supervisor.ipc."""

import asyncio
import json
import os
import tempfile
import unittest

from supervisor.ipc import IpcServer, send_command
from supervisor.scheduler import JobScheduler, Schedule
from supervisor.supervisor import Supervisor


class IpcTests(unittest.IsolatedAsyncioTestCase):
    async def test_ping_pong(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock = os.path.join(tmp, "test.sock")
            server = IpcServer(sock)
            await server.start()

            resp = await send_command(sock, {"cmd": "ping"})
            self.assertEqual(resp, {"pong": True})

            await server.stop()

    async def test_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock = os.path.join(tmp, "test.sock")
            sup = Supervisor()
            sched = JobScheduler(tick_seconds=0.1)

            async def dummy():
                pass

            sched.register("test", dummy, Schedule.every(seconds=3600))

            server = IpcServer(sock, supervisor=sup, scheduler=sched)
            await server.start()

            resp = await send_command(sock, {"cmd": "status"})
            self.assertIn("actors", resp)
            self.assertIn("jobs", resp)
            self.assertIn("heartbeats", resp)

            await server.stop()
            await sched.stop()

    async def test_trigger_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock = os.path.join(tmp, "test.sock")
            runs = []

            async def job():
                runs.append(1)

            sched = JobScheduler(tick_seconds=0.05)
            sched.register("j", job, Schedule.every(seconds=3600))
            asyncio.create_task(sched.run_forever())

            server = IpcServer(sock, scheduler=sched)
            await server.start()

            resp = await send_command(sock, {"cmd": "trigger", "job": "j"})
            self.assertEqual(resp, {"ok": True})

            await asyncio.sleep(0.15)
            self.assertGreaterEqual(len(runs), 1)

            await server.stop()
            await sched.stop()

    async def test_pause_resume_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock = os.path.join(tmp, "test.sock")

            async def job():
                pass

            sched = JobScheduler(tick_seconds=0.05)
            sched.register("j", job, Schedule.every(seconds=0.1))

            server = IpcServer(sock, scheduler=sched)
            await server.start()

            await send_command(sock, {"cmd": "pause", "job": "j"})
            st = sched.status()
            self.assertEqual(st["j"]["status"], "paused")

            await send_command(sock, {"cmd": "resume", "job": "j"})
            st = sched.status()
            self.assertEqual(st["j"]["status"], "idle")

            await server.stop()
            await sched.stop()

    async def test_restart_actor(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock = os.path.join(tmp, "test.sock")
            sup = Supervisor()

            async def actor():
                await asyncio.sleep(0.01)

            await sup.add_actor("a", actor, autostart=True)
            await asyncio.sleep(0.02)

            server = IpcServer(sock, supervisor=sup)
            await server.start()

            resp = await send_command(sock, {"cmd": "restart", "actor": "a"})
            self.assertEqual(resp, {"ok": True})

            await asyncio.sleep(0.05)
            a = sup.get("a")
            self.assertGreater(a.restart_count, 0)

            await server.stop()
            await sup.shutdown()

    async def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock = os.path.join(tmp, "test.sock")
            server = IpcServer(sock)
            await server.start()

            resp = await send_command(sock, "not json")
            self.assertIn("error", resp)

            await server.stop()

    async def test_unknown_cmd(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock = os.path.join(tmp, "test.sock")
            server = IpcServer(sock)
            await server.start()

            resp = await send_command(sock, {"cmd": "nonsense"})
            self.assertIn("error", resp)

            await server.stop()

    async def test_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            sock = os.path.join(tmp, "test.sock")
            shutdown_called = False

            async def on_shutdown():
                nonlocal shutdown_called
                shutdown_called = True

            server = IpcServer(sock, on_shutdown=on_shutdown)
            await server.start()

            resp = await send_command(sock, {"cmd": "shutdown"})
            self.assertEqual(resp, {"ok": True})

            await asyncio.sleep(0.05)
            self.assertTrue(shutdown_called)

            await server.stop()


if __name__ == "__main__":
    unittest.main()
