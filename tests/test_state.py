import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from canvas_today.state import DoneStore, resolve_short_id, short_id

from .helpers import NOW


class ShortIdTests(unittest.TestCase):
    def test_stable_format(self):
        s = short_id("event-assignment-1001")
        self.assertEqual(s, short_id("event-assignment-1001"))
        self.assertEqual(len(s), 4)
        self.assertRegex(s, r"^[2-9a-km-np-z]{4}$")

    def test_known_value_never_changes(self):
        # ids are typed by the user; changing the algorithm must be a conscious act.
        self.assertEqual(short_id("event-assignment-1001"), "x2hp")

    def test_distinct_enough(self):
        self.assertEqual(len({short_id(f"u{i}") for i in range(200)}), 200)

    def test_resolve(self):
        uids = ["a", "b", "c"]
        self.assertEqual(resolve_short_id(short_id("b").upper(), uids), "b")

    def test_resolve_none(self):
        with self.assertRaises(LookupError) as cm:
            resolve_short_id("zzzz", ["a"])
        self.assertIn("zzzz", str(cm.exception))

    def test_resolve_collision(self):
        from unittest import mock
        with mock.patch("canvas_today.state.short_id", return_value="aaaa"):
            with self.assertRaises(LookupError) as cm:
                resolve_short_id("aaaa", ["u1", "u2"])
        self.assertIn("u1", str(cm.exception))
        self.assertIn("u2", str(cm.exception))


class DoneStoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "data" / "done.json"
        self.store = DoneStore(self.path)

    def test_missing_file(self):
        self.assertEqual(self.store.load(), {})
        self.assertEqual(self.store.uids(), set())

    def test_round_trip(self):
        self.store.mark("a", NOW)
        self.store.mark("b", NOW)
        self.assertEqual(self.store.uids(), {"a", "b"})
        self.assertEqual(self.store.load()["a"], NOW.isoformat())
        self.store.unmark("a")
        self.assertEqual(self.store.uids(), {"b"})
        self.store.unmark("missing")  # no error

    def test_corrupt_file(self):
        self.path.parent.mkdir()
        self.path.write_text("{not json")
        self.assertEqual(self.store.load(), {})
        self.store.mark("a", NOW)  # recovers
        self.assertEqual(self.store.uids(), {"a"})

    def test_wrong_shape(self):
        self.path.parent.mkdir()
        self.path.write_text("[1, 2]")
        self.assertEqual(self.store.load(), {})

    def test_prune(self):
        self.store.mark("old", NOW - timedelta(days=121))
        self.store.mark("edge", NOW - timedelta(days=120))
        self.store.mark("new", NOW)
        self.assertEqual(self.store.prune(NOW), 1)
        self.assertEqual(self.store.uids(), {"edge", "new"})

    def test_no_temp_files_left(self):
        self.store.mark("a", NOW)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["done.json"])


if __name__ == "__main__":
    unittest.main()
