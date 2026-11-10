import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from canvas_today import cli
from canvas_today.state import short_id

from .helpers import FEED_URL, NOW, make_root

HW3_UID = "event-assignment-1001"  # Homework 3, due today in the fixture


class CliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = make_root(self.tmp)
        # Only cli.main reads the clock; pin it to the fixture's date.
        patcher = mock.patch("canvas_today.cli.datetime")
        patcher.start().now.return_value = NOW
        self.addCleanup(patcher.stop)

    def run_cli(self, *args, root=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--root", str(root or self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_default_writes_page_without_opening(self):
        with mock.patch("webbrowser.open") as opened:
            code, out, _ = self.run_cli("--no-open", "--offline")
        self.assertEqual(code, 0)
        opened.assert_not_called()
        html = (self.root / "data" / "today.html").read_text()
        self.assertIn("Homework 3", html)
        self.assertIn("today.html", out)
        self.assertNotIn(FEED_URL, out + html)

    def test_default_opens_browser_once(self):
        with mock.patch("webbrowser.open") as opened:
            self.run_cli("--offline")
        opened.assert_called_once()
        self.assertTrue(opened.call_args.args[0].startswith("file://"))

    def test_open_browser_false_in_config_is_respected(self):
        with (self.root / "config.toml").open("a") as f:
            f.write("open_browser = false\n")
        with mock.patch("webbrowser.open") as opened:
            self.run_cli("--offline")
        opened.assert_not_called()

    def test_done_undo_round_trip(self):
        sid = short_id(HW3_UID)
        done_path = self.root / "data" / "done.json"
        code, out, _ = self.run_cli("done", sid)
        self.assertEqual(code, 0)
        self.assertIn("Homework 3", out)
        self.assertIn(HW3_UID, json.loads(done_path.read_text()))
        html = (self.root / "data" / "today.html").read_text()
        self.assertIn('class="row done', html)

        code, out, _ = self.run_cli("undo", sid)
        self.assertEqual(code, 0)
        self.assertNotIn(HW3_UID, json.loads(done_path.read_text()))
        self.assertNotIn('class="row done', (self.root / "data" / "today.html").read_text())

    def test_bad_id_exits_1_and_changes_nothing(self):
        code, _, err = self.run_cli("done", "zzzz")
        self.assertEqual(code, 1)
        self.assertIn("zzzz", err)
        self.assertFalse((self.root / "data" / "done.json").exists())

    def test_missing_config_exits_2(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        code, _, err = self.run_cli("--no-open", root=empty)
        self.assertEqual(code, 2)
        self.assertIn("config.toml", err)

    def test_offline_without_cache_exits_2(self):
        (self.root / "data" / "feed_cache.ics").unlink()
        code, _, err = self.run_cli("--offline", "--no-open")
        self.assertEqual(code, 2)
        self.assertNotIn(FEED_URL, err)

    def test_check_lists_unmatched_item(self):
        code, out, _ = self.run_cli("--offline", "check")
        self.assertEqual(code, 0)
        self.assertIn("Lab 4 [draft]", out)
        self.assertIn("CS 400", out)
        self.assertIn("3 courses loaded", out)

    def test_schedule_bad_time_exits_2(self):
        code, _, err = self.run_cli("schedule", "--at", "25:00")
        self.assertEqual(code, 2)
        self.assertIn("25:00", err)

    def test_schedule_and_unschedule_call_schedule_module(self):
        with mock.patch("canvas_today.cli.schedule.install", return_value=Path("/x/p.plist")) as ins:
            code, out, _ = self.run_cli("schedule", "--at", "07:30")
        self.assertEqual(code, 0)
        ins.assert_called_once_with(self.root.resolve(), 7, 30)
        self.assertIn("launchctl print", out)
        with mock.patch("canvas_today.cli.schedule.uninstall", return_value=True):
            code, out, _ = self.run_cli("unschedule")
        self.assertEqual(code, 0)
        self.assertIn("Removed", out)


if __name__ == "__main__":
    unittest.main()
