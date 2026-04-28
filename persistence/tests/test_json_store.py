"""Tests for persistence.json_store.JsonStore."""

import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from persistence.json_store import JsonStore


class JsonStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_creates_default_when_missing(self):
        store = JsonStore(self.tmp / "a.json", default_factory=lambda: {"hello": "world"})
        doc = store.load()
        self.assertEqual(doc, {"hello": "world"})
        # File should still not exist until save()
        self.assertFalse((self.tmp / "a.json").exists())

    def test_save_writes_file_atomically(self):
        path = self.tmp / "b.json"
        store = JsonStore(path)
        store.update(lambda d: d.update({"k": 1}))
        self.assertTrue(path.exists())
        with path.open() as f:
            self.assertEqual(json.load(f), {"k": 1})

    def test_schema_version_added_when_absent(self):
        path = self.tmp / "c.json"
        store = JsonStore(path, schema_version=3)
        doc = store.load()
        self.assertEqual(doc.get("version"), 3)

    def test_dotted_get_set(self):
        store = JsonStore(self.tmp / "d.json")
        store.set("memory.recent.0", "first")
        self.assertEqual(store.get("memory.recent.0"), "first")
        self.assertIsNone(store.get("nope.nope"))
        self.assertEqual(store.get("nope.nope", "fallback"), "fallback")

    def test_corrupt_file_falls_back_to_default(self):
        path = self.tmp / "e.json"
        path.write_text("{not valid json", encoding="utf-8")
        store = JsonStore(path, default_factory=lambda: {"safe": True})
        self.assertEqual(store.load(), {"safe": True})

    def test_backup_used_when_main_corrupt(self):
        path = self.tmp / "f.json"
        bak = path.with_suffix(".json.bak")
        bak.write_text(json.dumps({"from": "bak"}), encoding="utf-8")
        path.write_text("garbage", encoding="utf-8")
        store = JsonStore(path)
        self.assertEqual(store.load(), {"from": "bak"})

    def test_keep_backup_creates_bak(self):
        path = self.tmp / "g.json"
        store = JsonStore(path, keep_backup=True)
        store.update(lambda d: d.update({"x": 1}))
        self.assertTrue(path.with_suffix(".json.bak").exists())

    def test_concurrent_updates_serialize_correctly(self):
        path = self.tmp / "h.json"
        store = JsonStore(path, default_factory=lambda: {"counter": 0})
        store.load()  # materialize

        def worker():
            for _ in range(50):
                store.update(lambda d: d.__setitem__("counter", d["counter"] + 1))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 4 threads * 50 increments = 200
        self.assertEqual(store.load()["counter"], 200)

    def test_snapshot_is_independent(self):
        store = JsonStore(self.tmp / "i.json")
        store.update(lambda d: d.update({"nested": {"a": 1}}))
        snap = store.snapshot()
        snap["nested"]["a"] = 999
        self.assertEqual(store.load()["nested"]["a"], 1)


if __name__ == "__main__":
    unittest.main()
