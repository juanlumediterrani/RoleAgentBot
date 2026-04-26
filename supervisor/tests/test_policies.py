"""Tests for supervisor.policies."""

import time
import unittest

from supervisor.policies import (
    BackoffStrategy,
    CircuitBreaker,
    CircuitBreakerOpen,
    RestartPolicy,
    RestartType,
    RetryPolicy,
    compute_backoff,
)


class BackoffTests(unittest.TestCase):
    def test_fixed(self):
        d = compute_backoff(0, strategy=BackoffStrategy.FIXED, base_seconds=2.0, jitter=0)
        self.assertEqual(d, 2.0)
        d = compute_backoff(5, strategy=BackoffStrategy.FIXED, base_seconds=2.0, jitter=0)
        self.assertEqual(d, 2.0)

    def test_exponential_capped(self):
        d = compute_backoff(10, strategy=BackoffStrategy.EXPONENTIAL,
                            base_seconds=1.0, max_seconds=30.0, jitter=0)
        self.assertEqual(d, 30.0)

    def test_linear(self):
        d = compute_backoff(3, strategy=BackoffStrategy.LINEAR, base_seconds=2.0, jitter=0)
        self.assertEqual(d, 8.0)

    def test_jitter_within_bounds(self):
        for _ in range(100):
            d = compute_backoff(2, strategy=BackoffStrategy.EXPONENTIAL,
                                base_seconds=1.0, max_seconds=100.0, jitter=0.5)
            # nominal = 4.0; jitter +/- 50% => [2, 6]
            self.assertGreaterEqual(d, 2.0)
            self.assertLessEqual(d, 6.0)


class RestartPolicyTests(unittest.TestCase):
    def test_should_restart_permanent(self):
        p = RestartPolicy(type=RestartType.PERMANENT)
        self.assertTrue(p.should_restart(normal_exit=True))
        self.assertTrue(p.should_restart(normal_exit=False))

    def test_should_restart_transient(self):
        p = RestartPolicy(type=RestartType.TRANSIENT)
        self.assertFalse(p.should_restart(normal_exit=True))
        self.assertTrue(p.should_restart(normal_exit=False))

    def test_should_restart_temporary(self):
        p = RestartPolicy(type=RestartType.TEMPORARY)
        self.assertFalse(p.should_restart(normal_exit=True))
        self.assertFalse(p.should_restart(normal_exit=False))

    def test_burning_after_max_restarts(self):
        p = RestartPolicy(max_restarts=3, within_seconds=60.0)
        for _ in range(3):
            p.record_restart()
        self.assertFalse(p.is_burning())
        p.record_restart()
        self.assertTrue(p.is_burning())

    def test_window_evicts_old_events(self):
        p = RestartPolicy(max_restarts=3, within_seconds=0.05)
        for _ in range(5):
            p.record_restart()
        self.assertTrue(p.is_burning())
        time.sleep(0.1)
        # Trigger eviction by recording one more
        p.record_restart()
        self.assertFalse(p.is_burning())


class RetryPolicyTests(unittest.TestCase):
    def test_delay_for_uses_strategy(self):
        rp = RetryPolicy(max_attempts=3, backoff=BackoffStrategy.EXPONENTIAL,
                         base_seconds=1.0, max_seconds=10.0, jitter=0)
        self.assertEqual(rp.delay_for(0), 1.0)
        self.assertEqual(rp.delay_for(1), 2.0)
        self.assertEqual(rp.delay_for(2), 4.0)


class CircuitBreakerTests(unittest.TestCase):
    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=10.0)
        for _ in range(2):
            cb.record_failure()
        cb.before_call()  # still closed
        cb.record_failure()
        with self.assertRaises(CircuitBreakerOpen):
            cb.before_call()

    def test_half_open_recovers_on_success(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_seconds=0.05,
                            half_open_successes_required=1)
        cb.record_failure()
        cb.record_failure()
        with self.assertRaises(CircuitBreakerOpen):
            cb.before_call()
        time.sleep(0.1)
        # Now should be half-open and allow a call
        cb.before_call()
        cb.record_success()
        # After success, should be closed again
        cb.before_call()  # no exception

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_seconds=0.05)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.1)
        cb.before_call()  # half-open
        cb.record_failure()  # back to open
        with self.assertRaises(CircuitBreakerOpen):
            cb.before_call()


if __name__ == "__main__":
    unittest.main()
