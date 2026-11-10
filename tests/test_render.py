import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from canvas_today.config import load_config
from canvas_today.pipeline import Report, build_report
from canvas_today.prioritize import Ranked, Tier
from canvas_today.render import render
from canvas_today.state import short_id

from .helpers import FEED_URL, NOW, make_classified, make_root


def _ranked(title, uid, url=None, tier=Tier.TODAY):
    c = make_classified(NOW, uid=uid, title=title)
    c = replace(c, item=replace(c.item, url=url))
    return Ranked(c, tier, 0, short_id(uid), False)


class RenderTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = load_config(make_root(Path(tmp.name)))

    def report(self):
        return build_report(self.cfg, NOW, offline=True)

    def test_full_document_with_tiers_and_ids(self):
        report = self.report()
        page = render(report, NOW)
        self.assertTrue(page.startswith("<!doctype html>"))
        self.assertIn('<meta name="viewport"', page)
        self.assertIn("Monday, November 9", page)
        for tier in {r.tier for r in report.ranked}:
            self.assertIn(tier.label, page)
        for r in report.ranked:
            self.assertIn(f"<code>{r.short_id}</code>", page)
        self.assertNotIn("Not refreshed from Canvas", page)

    def test_stale_notice(self):
        report = self.report()
        report.stale, report.cache_time = True, NOW
        self.assertIn("Not refreshed from Canvas; showing the copy saved Mon Nov 9, 8:00 AM",
                      render(report, NOW))

    def test_friendly_formats(self):
        page = render(self.report(), NOW)
        self.assertIn("Today 11:00 PM", page)  # Homework 3
        self.assertIn("% of grade", page)
        self.assertIn("in 11 days", page)  # Final Paper-style prepare/horizon chip

    def test_untrusted_text_is_escaped(self):
        report = self.report()
        evil = _ranked("<script>alert(1)</script> & co", "evil1")
        bad_link = _ranked("Sneaky", "evil2", url="javascript:alert(1)")
        good_link = _ranked("Fine", "ok1", url="https://canvas.example.edu/x?a=1&b=2")
        report.ranked += [evil, bad_link, good_link]
        page = render(report, NOW)
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; co", page)
        self.assertNotIn("javascript:", page)
        self.assertIn('href="https://canvas.example.edu/x?a=1&amp;b=2"', page)

    def test_done_items_are_marked_and_sink(self):
        report = self.report()
        first = next(r for r in report.ranked if r.tier is Tier.TODAY)
        marked = [replace(r, done=True) if r is first else r for r in report.ranked]
        page = render(replace(report, ranked=marked), NOW)
        self.assertIn('class="row done', page)
        today_section = page.split("Due today")[1].split("</section>")[0]
        last_row = today_section.split("<li")[-1]
        self.assertIn("done", last_row)

    def test_no_external_resources_and_no_feed_url(self):
        page = render(self.report(), NOW)
        for needle in ("<link", "<script", "<img", "@import", "url("):
            self.assertNotIn(needle, page)
        self.assertNotIn(FEED_URL, page)
        self.assertNotIn("SECRETTOKEN", page)

    def test_bad_course_colour_is_not_injected(self):
        report = self.report()
        course = replace(report.courses[0], color='red;"><b>x')
        page = render(replace(report, courses=[course]), NOW)
        self.assertNotIn("<b>x", page)

    def test_empty_report_is_friendly(self):
        empty = Report([], [], [], False, [], NOW)
        page = render(empty, NOW)
        self.assertIn("Nothing coming up", page)
        self.assertNotIn("<section", page)

    def test_notices_for_problems_and_unmatched(self):
        report = replace(self.report(), problems=["a.toml: bad"], stale=False)
        page = render(report, NOW)
        self.assertIn("1 problem in course files", page)
        self.assertIn("no matching course or category", page)
        self.assertNotIn("Couldn't reach", page)

    def test_legend_shows_weights_and_thresholds(self):
        page = render(self.report(), NOW)
        self.assertIn("Exams 45%", page)
        self.assertIn("A 93 · AB 88", page)


if __name__ == "__main__":
    unittest.main()
