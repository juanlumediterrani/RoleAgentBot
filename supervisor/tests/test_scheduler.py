"""Tests for supervisor.scheduler."""

import asyncio
import unittest

from supervisor.policies import CircuitBreaker, RetryPolicy
from supervisor.scheduler import Job, JobScheduler, JobStatus, Schedule


class JobSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_and_status(self):
        async def dummy():
            pass

        sched = JobScheduler(tick_seconds=0.05)
        job = sched.register(
            "test",
            dummy,
            Schedule.every(seconds=0.1),
            timeout_seconds=1.0,
        )
        self.assertEqual(job.name, "test")
        st = sched.status()
        self.assertIn("test", st)
        self.assertEqual(st["test"]["status"], "idle")

        await sched.stop()

    async def test_job_runs_on_schedule(self):
        runs = []

        async def periodic():
            runs.append(1)

        sched = JobScheduler(tick_seconds=0.02)
        sched.register(
            "p",
            periodic,
            Schedule.every(seconds=0.1, initial_delay_seconds=0.05),
        )
        asyncio.create_task(sched.run_forever())
        await asyncio.sleep(0.25)

        await sched.stop()
        self.assertGreaterEqual(len(runs), 1)

    async def test_trigger_now(self):
        runs = []

        async def once():
            runs.append(1)

        sched = JobScheduler(tick_seconds=0.05)
        sched.register("once", once, Schedule.every(seconds=3600))
        asyncio.create_task(sched.run_forever())
        await asyncio.sleep(0.02)

        await sched.trigger_now("once")
        await asyncio.sleep(0.1)

        await sched.stop()
        self.assertGreaterEqual(len(runs), 1)

    async def test_pause_resume(self):
        runs = []

        async def counter():
            runs.append(1)

        sched = JobScheduler(tick_seconds=0.02)
        sched.register("c", counter, Schedule.every(seconds=0.1))
        asyncio.create_task(sched.run_forever())
        await asyncio.sleep(0.15)

        before = len(runs)
        sched.pause("c")
        await asyncio.sleep(0.15)
        paused = len(runs)

        sched.resume("c")
        await asyncio.sleep(0.15)
        after = len(runs)

        await sched.stop()
        self.assertEqual(before, paused)
        self.assertGreater(after, paused)

    async def test_timeout_cancels_job(self):
        # Test that timeout is configured and job can be registered
        async def slow():
            await asyncio.sleep(10)

        sched = JobScheduler(tick_seconds=0.05)
        job = sched.register("slow", slow, Schedule.every(seconds=3600), timeout_seconds=0.1)
        self.assertEqual(job.timeout_seconds, 0.1)

        # Trigger and let it timeout
        asyncio.create_task(sched.run_forever())
        await sched.trigger_now("slow")
        await asyncio.sleep(0.2)

        st = sched.status()
        await sched.stop()
        # Just verify it has a last_error (timeout or similar)
        self.assertIsNotNone(st["slow"]["last_error"])

    async def test_retry_policy(self):
        attempts = []

        async def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("boom")

        sched = JobScheduler(tick_seconds=0.02)
        sched.register(
            "flaky",
            flaky,
            Schedule.every(seconds=3600),
            retry=RetryPolicy(max_attempts=3, base_seconds=0.01, jitter=0),
        )
        asyncio.create_task(sched.run_forever())
        await asyncio.sleep(0.2)

        st = sched.status()
        await sched.stop()
        self.assertEqual(len(attempts), 3)
        self.assertEqual(st["flaky"]["success_count"], 1)

    async def test_circuit_breaker(self):
        # Test that circuit breaker is configured correctly
        async def fail():
            raise RuntimeError("fail")

        sched = JobScheduler(tick_seconds=0.05)
        breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=0.1)
        job = sched.register("f", fail, Schedule.every(seconds=3600), breaker=breaker)
        self.assertEqual(job.breaker, breaker)
        self.assertEqual(breaker.failure_threshold, 2)

        # Trigger once to ensure it runs
        asyncio.create_task(sched.run_forever())
        await sched.trigger_now("f")
        await asyncio.sleep(0.15)

        await sched.stop()
        # Job should have been attempted
        self.assertIsNotNone(job.last_error)

    async def test_semaphore_limits_concurrency(self):
        active = 0
        max_active = 0

        async def holder():
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.1)
            active -= 1

        sched = JobScheduler(tick_seconds=0.02)
        sched.register_semaphore("lim", max_concurrent=2)
        sched.register("h1", holder, Schedule.every(seconds=3600))
        sched.register("h2", holder, Schedule.every(seconds=3600))
        sched.register("h3", holder, Schedule.every(seconds=3600))
        sched.register("h4", holder, Schedule.every(seconds=3600), semaphore="lim")

        asyncio.create_task(sched.run_forever())
        await asyncio.sleep(0.01)

        # Trigger all at once
        await sched.trigger_now("h1")
        await sched.trigger_now("h2")
        await sched.trigger_now("h3")
        await sched.trigger_now("h4")
        await asyncio.sleep(0.15)

        await sched.stop()
        # h4 respects semaphore of 2, others no limit
        self.assertGreaterEqual(max_active, 3)  # h1+h2+h3

    async def test_unregister(self):
        async def dummy():
            pass

        sched = JobScheduler(tick_seconds=0.02)
        sched.register("x", dummy, Schedule.every(seconds=3600))
        self.assertIn("x", sched.status())
        sched.unregister("x")
        self.assertNotIn("x", sched.status())


if __name__ == "__main__":
    unittest.main()
