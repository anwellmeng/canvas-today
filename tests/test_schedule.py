import plistlib
import tempfile
import unittest
from pathlib import Path

from canvas_today import schedule


class FakeRun:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.home, self.root = self.tmp / "home", self.tmp / "proj"

    def test_build_plist_round_trips(self):
        data = schedule.build_plist(Path("/py/python"), Path("/proj"), 7, 30, Path("/proj/data/launchd.log"))
        plist = plistlib.loads(data)
        self.assertEqual(plist["Label"], schedule.LABEL)
        self.assertEqual(plist["ProgramArguments"],
                         ["/py/python", "-m", "canvas_today", "--root", "/proj"])
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 7, "Minute": 30})
        self.assertEqual(plist["WorkingDirectory"], "/proj")
        self.assertEqual(plist["StandardOutPath"], "/proj/data/launchd.log")
        self.assertEqual(plist["StandardErrorPath"], "/proj/data/launchd.log")
        self.assertIs(plist["RunAtLoad"], False)

    def test_parse_time(self):
        self.assertEqual(schedule.parse_time("07:30"), (7, 30))
        self.assertEqual(schedule.parse_time("7:05"), (7, 5))
        for bad in ("", "7", "24:00", "07:60", "ab:cd", "1:2:3"):
            with self.assertRaises(ValueError, msg=bad):
                schedule.parse_time(bad)

    def test_plist_path_uses_home(self):
        self.assertEqual(schedule.plist_path(self.home),
                         self.home / "Library/LaunchAgents/com.canvas-today.daily.plist")

    def test_install_writes_plist_and_runs_launchctl(self):
        run = FakeRun()
        path = schedule.install(self.root, 8, 15, home=self.home, run=run)
        self.assertEqual(path, schedule.plist_path(self.home))
        self.assertEqual(plistlib.loads(path.read_bytes())["StartCalendarInterval"],
                         {"Hour": 8, "Minute": 15})
        self.assertEqual([c[:2] for c in run.calls],
                         [["launchctl", "bootout"], ["launchctl", "bootstrap"]])
        self.assertTrue(run.calls[0][2].endswith(schedule.LABEL))
        self.assertEqual(run.calls[1][3], str(path))

    def test_uninstall(self):
        run = FakeRun()
        self.assertFalse(schedule.uninstall(home=self.home, run=run))
        path = schedule.install(self.root, 8, 0, home=self.home, run=FakeRun())
        self.assertTrue(schedule.uninstall(home=self.home, run=run))
        self.assertFalse(path.exists())
        self.assertEqual(run.calls[-1][:2], ["launchctl", "bootout"])


if __name__ == "__main__":
    unittest.main()
