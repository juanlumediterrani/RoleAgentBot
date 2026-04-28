"""Tests for persistence.jsonl_store.JsonlRingBuffer."""

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from persistence.jsonl_store import JsonlRingBuffer


class JsonlRingBufferTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_append_and_count(self):
        buf = JsonlRingBuffer(self.tmp / "a.jsonl", max_lines=100)
        buf.append({"i": 1})
        buf.append({"i": 2})
        self.assertEqual(buf.count(), 2)

    def test_tail_returns_last_n(self):
        buf = JsonlRingBuffer(self.tmp / "b.jsonl", max_lines=100)
        for i in range(10):
            buf.append({"i": i})
        last3 = buf.tail(3)
        self.assertEqual([r["i"] for r in last3], [7, 8, 9])

    def test_rotation_by_lines(self):
        buf = JsonlRingBuffer(self.tmp / "c.jsonl", max_lines=10, max_bytes=None, keep_lines=5)
        for i in range(20):
            buf.append({"i": i})
        # After rotation, should keep last 5
        self.assertLessEqual(buf.count(), 10)
        tail = buf.tail(5)
        self.assertEqual([r["i"] for r in tail], [15, 16, 17, 18, 19])

    def test_rotation_by_bytes(self):
        # Each line ~12 bytes; with max_bytes=200 expect rotation
        buf = JsonlRingBuffer(self.tmp / "d.jsonl", max_lines=10000, max_bytes=200, keep_lines=5)
        for i in range(100):
            buf.append({"i": i})
        self.assertLessEqual(buf.path.stat().st_size, 1000)  # rough upper bound after final rotation
        tail = buf.tail(5)
        self.assertTrue(len(tail) <= 5)
        # The most recent appended is index 99
        self.assertEqual(tail[-1]["i"], 99)

    def test_filter_tail(self):
        buf = JsonlRingBuffer(self.tmp / "e.jsonl", max_lines=100)
        for i in range(20):
            buf.append({"i": i, "even": i % 2 == 0})
        evens = buf.filter_tail(lambda r: r["even"], limit=3)
        self.assertEqual([r["i"] for r in evens], [14, 16, 18])

    def test_corrupt_lines_skipped(self):
        path = self.tmp / "f.jsonl"
        path.write_text('{"i":1}\nnot-json\n{"i":2}\n', encoding="utf-8")
        buf = JsonlRingBuffer(path, max_lines=100)
        all_recs = list(buf.iter_records())
        self.assertEqual([r["i"] for r in all_recs], [1, 2])

    def test_empty_tail(self):
        buf = JsonlRingBuffer(self.tmp / "g.jsonl", max_lines=10)
        self.assertEqual(buf.tail(5), [])

    def test_concurrent_appends(self):
        buf = JsonlRingBuffer(self.tmp / "h.jsonl", max_lines=10000, max_bytes=None)

        def worker(start: int):
            for i in range(50):
                buf.append({"i": start + i})

        threads = [threading.Thread(target=worker, args=(k * 50,)) for k in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(buf.count(), 200)

    def test_append_many(self):
        buf = JsonlRingBuffer(self.tmp / "i.jsonl", max_lines=100)
        buf.append_many([{"i": i} for i in range(5)])
        self.assertEqual(buf.count(), 5)
        self.assertEqual([r["i"] for r in buf.tail(5)], [0, 1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
