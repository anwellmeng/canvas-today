import tempfile
import unittest
from pathlib import Path

from canvas_today.config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_missing_file(self):
        with self.assertRaises(ConfigError) as cm:
            load_config(self.root)
        self.assertIn("config.toml", str(cm.exception))

    def test_empty_feed_url(self):
        (self.root / "config.toml").write_text('feed_url = ""\n')
        with self.assertRaises(ConfigError):
            load_config(self.root)
        self.assertEqual(load_config(self.root, require_feed=False).feed_url, "")

    def test_defaults_and_paths(self):
        (self.root / "config.toml").write_text('feed_url = "https://x"\n')
        c = load_config(self.root)
        self.assertEqual(c.timezone.key, "America/Chicago")
        self.assertEqual((c.horizon_days, c.overdue_days, c.open_browser), (30, 3, True))
        self.assertEqual(c.data_dir, self.root / "data")
        self.assertEqual(c.courses_dir, self.root / "courses")
        self.assertEqual(c.html_path, self.root / "data" / "today.html")
        self.assertEqual(c.cache_path.parent, c.data_dir)
        self.assertEqual(c.done_path.parent, c.data_dir)

    def test_bad_timezone(self):
        (self.root / "config.toml").write_text('feed_url = "x"\ntimezone = "Nope/Zone"\n')
        with self.assertRaises(ConfigError):
            load_config(self.root)

    def test_bad_toml(self):
        (self.root / "config.toml").write_text("feed_url = \n")
        with self.assertRaises(ConfigError):
            load_config(self.root)


if __name__ == "__main__":
    unittest.main()
