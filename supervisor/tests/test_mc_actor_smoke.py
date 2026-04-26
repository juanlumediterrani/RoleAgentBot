"""Smoke test for MC actor lifecycle via Supervisor.

Verifies that an actor wrapping a long-lived coroutine:
- Starts when registered with autostart=True
- Survives a coroutine exception (gets restarted by policy)
- Stops cleanly on supervisor shutdown
"""

import asyncio
import unittest

from supervisor.policies import RestartPolicy, RestartType
from supervisor.supervisor import ActorState, Supervisor


class McActorSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_actor_starts_and_runs(self):
        """Actor with long-lived loop must reach RUNNING state."""
        ticks = []

        async def fake_mc_loop():
            try:
                while True:
                    ticks.append(1)
                    await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                raise

        sup = Supervisor()
        await sup.add_actor(
            "mc",
            fake_mc_loop,
            policy=RestartPolicy(type=RestartType.PERMANENT, base_seconds=0.05),
            autostart=True,
        )

        await asyncio.sleep(0.15)
        status = sup.status()
        self.assertEqual(status["mc"]["state"], ActorState.RUNNING.value)
        self.assertGreaterEqual(len(ticks), 1)

        await sup.shutdown()
        self.assertEqual(sup.status()["mc"]["state"], ActorState.STOPPED.value)

    async def test_actor_restarts_on_failure(self):
        """Actor that crashes must be restarted by the policy."""
        attempts = []

        async def crashy_loop():
            attempts.append(1)
            await asyncio.sleep(0.02)
            raise RuntimeError("simulated crash")

        sup = Supervisor()
        await sup.add_actor(
            "crashy",
            crashy_loop,
            policy=RestartPolicy(
                type=RestartType.PERMANENT,
                max_restarts=10,
                base_seconds=0.02,
                within_seconds=10.0,
            ),
            autostart=True,
        )

        await asyncio.sleep(0.3)
        await sup.shutdown()

        # Should have attempted multiple times due to PERMANENT policy
        self.assertGreaterEqual(len(attempts), 2)


if __name__ == "__main__":
    unittest.main()
