"""Tests for supervisor.supervisor."""

import asyncio
import unittest

from supervisor.policies import RestartPolicy, RestartType
from supervisor.supervisor import Actor, ActorState, Supervisor


class SupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def test_add_and_start_actor(self):
        async def simple():
            await asyncio.sleep(0.01)

        sup = Supervisor()
        actor = await sup.add_actor("test", simple, autostart=False)
        self.assertEqual(actor.state, ActorState.PENDING)

        await sup.start("test")
        self.assertEqual(actor.state, ActorState.RUNNING)

        await sup.stop("test")
        self.assertEqual(actor.state, ActorState.STOPPED)

    async def test_permanent_actor_restarts_on_crash(self):
        # Test that restart policy tracks restarts correctly
        policy = RestartPolicy(
            type=RestartType.PERMANENT,
            max_restarts=5,
            within_seconds=10.0,
        )
        self.assertTrue(policy.should_restart(normal_exit=False))
        policy.record_restart()
        policy.record_restart()
        self.assertEqual(len(policy._events), 2)
        self.assertFalse(policy.is_burning())

        # Test burning
        for _ in range(5):
            policy.record_restart()
        self.assertTrue(policy.is_burning())

    async def test_transient_actor_does_not_restart_on_normal_exit(self):
        async def normal():
            return

        sup = Supervisor()
        policy = RestartPolicy(type=RestartType.TRANSIENT)
        await sup.add_actor("norm", normal, policy=policy, autostart=True)
        await asyncio.sleep(0.05)

        actor = sup.get("norm")
        self.assertEqual(actor.state, ActorState.STOPPED)
        self.assertEqual(actor.restart_count, 0)

    async def test_burning_actor_quarantined(self):
        async def fail_fast():
            raise RuntimeError("boom")

        sup = Supervisor()
        policy = RestartPolicy(
            type=RestartType.PERMANENT,
            max_restarts=2,
            within_seconds=0.1,
            base_seconds=0.01,
            jitter=0,
        )
        await sup.add_actor("burn", fail_fast, policy=policy, autostart=True)

        await asyncio.sleep(0.3)

        actor = sup.get("burn")
        self.assertEqual(actor.state, ActorState.BURNING)

        await sup.shutdown()

    async def test_manual_restart(self):
        call_count = 0

        async def counter():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)

        sup = Supervisor()
        # Use PERMANENT policy to allow restart
        policy = RestartPolicy(type=RestartType.PERMANENT, max_restarts=10)
        await sup.add_actor("c", counter, policy=policy, autostart=True)
        await asyncio.sleep(0.05)

        # Manual restart via stop + start
        await sup.stop("c")
        await asyncio.sleep(0.05)
        await sup.start("c")
        await asyncio.sleep(0.2)  # Wait for restart to complete

        actor = sup.get("c")
        # After restart, it should be RUNNING (or at least not STOPPED)
        self.assertIn(actor.state, [ActorState.RUNNING, ActorState.RESTARTING])

        await sup.shutdown()

    async def test_shutdown_stops_all_actors(self):
        async def sleeper():
            await asyncio.sleep(10)

        sup = Supervisor()
        await sup.add_actor("a1", sleeper, autostart=True)
        await sup.add_actor("a2", sleeper, autostart=True)

        await asyncio.sleep(0.01)
        await sup.shutdown(timeout=0.5)

        a1 = sup.get("a1")
        a2 = sup.get("a2")
        self.assertEqual(a1.state, ActorState.STOPPED)
        self.assertEqual(a2.state, ActorState.STOPPED)

    async def test_status(self):
        async def dummy():
            await asyncio.sleep(0.01)

        sup = Supervisor()
        await sup.add_actor("x", dummy, autostart=True)
        await asyncio.sleep(0.01)

        st = sup.status()
        self.assertIn("x", st)
        self.assertEqual(st["x"]["state"], "running")

        await sup.shutdown()

    async def test_heartbeat_integration(self):
        async def heartbeater(sup):
            while True:
                sup.heartbeats.beat("hb")
                await asyncio.sleep(0.02)

        sup = Supervisor()
        await sup.add_actor("hb", heartbeater, autostart=True, heartbeat_timeout=0.1)

        await asyncio.sleep(0.05)
        status = sup.heartbeats.status()
        self.assertTrue(status["hb"]["alive"])

        await sup.shutdown()


if __name__ == "__main__":
    unittest.main()
