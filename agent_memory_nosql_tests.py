"""Tests for agent_memory_nosql module."""

import json
import tempfile
import unittest

from agent_memory_nosql import AgentMemoryNoSQL


class AgentMemoryNoSQLTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.memory = AgentMemoryNoSQL("test", db_dir=self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_register_and_get_interaction(self):
        self.memory.register_interaction(
            user_id="123",
            user_name="Alice",
            interaction_type="chat",
            context="Hello",
            metadata={"response": "Hi there!"},
        )
        history = self.memory.get_user_history("123", limit=1)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["humano"], "Hello")
        self.assertEqual(history[0]["bot"], "Hi there!")

    def test_multiple_interactions_retention(self):
        for i in range(300):
            self.memory.register_interaction(
                user_id="123",
                user_name="Alice",
                interaction_type="chat",
                context=f"Message {i}",
                metadata={"response": f"Reply {i}"},
            )
        # Should keep only max 250
        history = self.memory.get_user_history("123", limit=300)
        self.assertLessEqual(len(history), 250)

    def test_daily_memory_retention(self):
        for i in range(20):
            self.memory.add_daily_memory(f"Day {i} summary")
        daily = self.memory.get_daily_memory_entries(days=30)
        self.assertLessEqual(len(daily), 14)

    def test_recent_memory(self):
        self.memory.set_recent_memory("Recent summary", metadata={"key": "value"})
        recent = self.memory.get_recent_memory()
        self.assertIsNotNone(recent)
        self.assertEqual(recent["summary"], "Recent summary")
        self.assertEqual(recent["metadata"], {"key": "value"})

    def test_relationship(self):
        self.memory.set_relationship("123", "Alice is friendly", {"trust": 0.8})
        rel = self.memory.get_relationship("123")
        self.assertIsNotNone(rel)
        self.assertEqual(rel["summary"], "Alice is friendly")
        self.assertEqual(rel["metadata"], {"trust": 0.8})

    def test_relationship_retention(self):
        # Add more than 200 users
        for i in range(250):
            self.memory.set_relationship(str(i), f"User {i}")
        all_rels = self.memory.get_all_relationships()
        self.assertLessEqual(len(all_rels), 200)

    def test_relationship_daily(self):
        for i in range(20):
            self.memory.set_relationship_daily("123", f"Day {i} summary")
        daily = self.memory.get_relationship_daily("123", days=30)
        self.assertLessEqual(len(daily), 14)

    def test_recollection(self):
        self.memory.add_recollection("Important fact", "source paragraph")
        recs = self.memory.get_recollections()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["recollection_text"], "Important fact")

    def test_recollection_retention(self):
        for i in range(60):
            self.memory.add_recollection(f"Fact {i}")
        recs = self.memory.get_recollections()
        self.assertLessEqual(len(recs), 50)

    def test_recollection_used(self):
        self.memory.add_recollection("Important fact")
        self.memory.mark_recollection_used("Important fact")
        recs = self.memory.get_recollections()
        self.assertEqual(recs[0]["used_count"], 1)
        self.assertIsNotNone(recs[0]["last_used_at"])

    def test_pending_relationship_update(self):
        self.memory.schedule_relationship_update("123", delay_minutes=5)
        pending = self.memory.get_pending_relationship_updates()
        self.assertIn("123", pending)
        self.assertEqual(pending["123"]["status"], "pending")

        self.memory.clear_relationship_update("123")
        pending = self.memory.get_pending_relationship_updates()
        self.assertNotIn("123", pending)

    def test_pending_recent_memory_update(self):
        self.memory.schedule_recent_memory_update(delay_minutes=60)
        pending = self.memory.get_pending_recent_memory_updates()
        self.assertEqual(len(pending), 1)

        # Clear by scheduled_for key
        scheduled_key = list(pending.keys())[0]
        self.memory.clear_recent_memory_update(scheduled_key)
        pending = self.memory.get_pending_recent_memory_updates()
        self.assertEqual(len(pending), 0)


class AgentStateStaggerTests(unittest.TestCase):
    """Tests for per-server stagger scheduling via AgentState facade."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _make_state(self, server_id):
        import os
        from persistence.agent_state import AgentState
        sub = os.path.join(self.tmpdir.name, server_id)
        return AgentState(server_id, db_dir=sub)

    def test_stagger_offset_deterministic_and_distributed(self):
        from persistence.agent_state import stagger_offset_seconds
        # Same input → same output
        self.assertEqual(
            stagger_offset_seconds("server_A", 3600),
            stagger_offset_seconds("server_A", 3600),
        )
        # Different servers → different offsets (with overwhelming probability)
        offsets = {stagger_offset_seconds(f"srv_{i}", 3600) for i in range(100)}
        # Expect high diversity (>80 unique out of 100) across a 3600 window
        self.assertGreater(len(offsets), 80)
        # Offsets bounded by window
        for i in range(100):
            self.assertLess(stagger_offset_seconds(f"srv_{i}", 3600), 3600)

    def test_scheduled_task_first_call_not_due(self):
        st = self._make_state("server1")
        # First call schedules next_run in the future (within the window)
        self.assertFalse(
            st.is_scheduled_task_due("daily_memory_summary", 24, stagger_window_hours=24)
        )
        # And a second call immediately also returns False (still not due)
        self.assertFalse(
            st.is_scheduled_task_due("daily_memory_summary", 24, stagger_window_hours=24)
        )

    def test_mark_done_advances_next_run(self):
        st = self._make_state("server2")
        st.is_scheduled_task_due("task_x", 24, stagger_window_hours=24)  # init
        before = st._memory.get_next_scheduled_at("task_x")
        st.mark_scheduled_task_done("task_x", interval_hours=24, stagger_window_hours=24)
        after = st._memory.get_next_scheduled_at("task_x")
        self.assertNotEqual(before, after)
        # After marking done, next_run is ~24h+ away
        from datetime import datetime, timedelta
        next_dt = datetime.fromisoformat(after)
        self.assertGreater(next_dt - datetime.now(), timedelta(hours=23))


if __name__ == "__main__":
    unittest.main()
