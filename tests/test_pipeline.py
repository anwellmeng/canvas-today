import os
from datetime import timedelta
import tempfile
import unittest
from pathlib import Path

from canvas_today.config import load_config
from canvas_today.feed import FeedError
from canvas_today.pipeline import build_report
from canvas_today.prioritize import Tier

from .helpers import NOW, make_root


class BuildReportTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_root(Path(tmp.name))
        self.cfg = load_config(self.root)

    def _age_cache(self, hours):
        stamp = (NOW - timedelta(hours=hours)).timestamp()
        os.utime(self.cfg.cache_path, (stamp, stamp))

    def test_offline_with_recent_cache_is_not_stale(self):
        self._age_cache(2)
        report = build_report(self.cfg, NOW, offline=True)
        self.assertFalse(report.stale)
        self.assertIsNone(report.cache_time)

    def test_offline_report_is_stale_with_cache_time(self):
        self._age_cache(30)
        report = build_report(self.cfg, NOW, offline=True)
        self.assertTrue(report.stale)
        self.assertEqual(report.cache_time, NOW - timedelta(hours=30))
        self.assertEqual(len(report.courses), 3)
        self.assertEqual(report.problems, [])
        self.assertGreater(report.feed_count, 10)

    def test_tiers_are_sensible(self):
        report = build_report(self.cfg, NOW, offline=True)
        by_title = {r.classified.item.title: r.tier for r in report.ranked}
        self.assertEqual(by_title["Homework 2"], Tier.OVERDUE)
        self.assertEqual(by_title["Homework 3"], Tier.TODAY)
        self.assertEqual(by_title["Lecture: Graphs"], Tier.TODAY)
        self.assertEqual(by_title["Final Paper"], Tier.HORIZON)

    def test_unmatched_lists_upcoming_feed_items_without_category(self):
        report = build_report(self.cfg, NOW, offline=True)
        titles = {c.item.title for c in report.unmatched}
        self.assertIn("Lab 4 [draft]", titles)
        self.assertNotIn("Homework 3", titles)
        self.assertNotIn("Dentist appointment", titles)  # plain events are never "unmatched"
        self.assertTrue(all(c.item.due >= NOW for c in report.unmatched))

    def test_offline_without_cache_raises(self):
        self.cfg.cache_path.unlink()
        with self.assertRaisesRegex(FeedError, "No cached feed"):
            build_report(self.cfg, NOW, offline=True)


if __name__ == "__main__":
    unittest.main()
