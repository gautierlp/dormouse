import os
import tempfile
import unittest

from state import DecisionStore


class DecisionStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = DecisionStore(":memory:")

    def test_unknown_is_none(self):
        self.assertIsNone(self.store.get("c1", "2026-10-04T10:00:00Z", "qwen3.5:4b"))

    def test_put_then_get(self):
        self.store.put("c1", "2026-10-04T10:00:00Z", "qwen3.5:4b", False)
        self.assertIs(self.store.get("c1", "2026-10-04T10:00:00Z", "qwen3.5:4b"), False)
        self.assertIsNone(self.store.get("c1", "2026-10-05T09:00:00Z", "qwen3.5:4b"))
        self.assertIsNone(self.store.get("c1", "2026-10-04T10:00:00Z", "gemma4:e4b"))

    def test_put_overwrites(self):
        self.store.put("c1", "t", "m", False)
        self.store.put("c1", "t", "m", True)
        self.assertIs(self.store.get("c1", "t", "m"), True)

    def test_archive_record(self):
        self.assertFalse(self.store.was_archived("c1", "t"))
        self.store.mark_archived("c1", "t")
        self.assertTrue(self.store.was_archived("c1", "t"))
        self.assertFalse(self.store.was_archived("c1", "t2"))

    def test_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "state.db")
            DecisionStore(path).put("c1", "t", "m", True)
            self.assertTrue(os.path.exists(path))

    def test_bare_filename_path(self):
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                DecisionStore("bare.db").db.close()
            finally:
                os.chdir(old)


if __name__ == "__main__":
    unittest.main()
