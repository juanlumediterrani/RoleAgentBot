"""Tests for supervisor.heartbeat."""

import time
import unittest

from supervisor.heartbeat import Heartbeat, HeartbeatRegistry


class HeartbeatTests(unittest.TestCase):
    def test_alive_just_after_creation(self):
        hb = Heartbeat(name="x", timeout_seconds=1.0)
        self.assertTrue(hb.is_alive())

    def test_dies_after_timeout(self):
        hb = Heartbeat(name="x", timeout_seconds=0.05)
        time.sleep(0.1)
        self.assertFalse(hb.is_alive())

    def test_beat_resets_age(self):
        hb = Heartbeat(name="x", timeout_seconds=0.05)
        time.sleep(0.04)
        hb.beat()
        self.assertTrue(hb.is_alive())


class HeartbeatRegistryTests(unittest.TestCase):
    def test_register_and_status(self):
        reg = HeartbeatRegistry()
        reg.register("a", timeout_seconds=1.0)
        reg.register("b", timeout_seconds=1.0)
        st = reg.status()
        self.assertIn("a", st)
        self.assertIn("b", st)
        self.assertTrue(st["a"]["alive"])

    def test_dead_returns_only_dead(self):
        reg = HeartbeatRegistry()
        reg.register("a", timeout_seconds=0.05)
        reg.register("b", timeout_seconds=10.0)
        time.sleep(0.1)
        dead = reg.dead()
        self.assertIn("a", dead)
        self.assertNotIn("b", dead)

    def test_unregister(self):
        reg = HeartbeatRegistry()
        reg.register("a", timeout_seconds=1.0)
        reg.unregister("a")
        self.assertNotIn("a", reg.status())


if __name__ == "__main__":
    unittest.main()
