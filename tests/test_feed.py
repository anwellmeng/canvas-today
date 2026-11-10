import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from canvas_today.feed import FeedError, fetch_feed, parse_feed, split_summary

from .helpers import FIXTURES, TZ


class SplitSummaryTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(split_summary("Homework 3 [COMPSCI 400 LEC 001 FA26]"),
                         ("Homework 3", "COMPSCI 400 LEC 001 FA26"))

    def test_no_context(self):
        self.assertEqual(split_summary("Dentist"), ("Dentist", None))

    def test_only_last_group_stripped(self):
        self.assertEqual(split_summary("Lab 4 [draft] [CS 1]"), ("Lab 4 [draft]", "CS 1"))

    def test_only_bracket_is_title(self):
        self.assertEqual(split_summary("[draft]"), ("[draft]", None))


class ParseFeedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = (FIXTURES / "canvas_feed.ics").read_text()
        cls.items = {i.uid: i for i in parse_feed(text, TZ)}

    def test_skips_missing_dtstart(self):
        self.assertNotIn("event-assignment-1015", self.items)
        self.assertEqual(len(self.items), 16)

    def test_skips_missing_summary(self):
        ics = "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:x\r\nDTSTART:20261110T050000Z\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
        self.assertEqual(parse_feed(ics, TZ), [])

    def test_context_split(self):
        i = self.items["event-assignment-1001"]
        self.assertEqual((i.title, i.course_code), ("Homework 3", "COMPSCI 400 LEC 001 FA26"))
        self.assertEqual(i.url, "https://canvas.example.edu/event-assignment-1001")
        self.assertEqual(i.source, "feed")

    def test_no_context(self):
        i = self.items["event-calendar-event-98766"]
        self.assertEqual((i.title, i.course_code), ("Dentist appointment", None))

    def test_bracket_in_title(self):
        i = self.items["event-assignment-1012"]
        self.assertEqual(i.title, "Lab 4 [draft]")
        self.assertEqual(i.course_code, "COMPSCI 400 LEC 001 FA26")

    def test_folded_summary(self):
        i = self.items["event-assignment-1013"]
        self.assertTrue(i.title.endswith("in the nineteenth century"))
        self.assertEqual(i.course_code, "HIST 101 DIS 003 FA26")

    def test_utc_conversion(self):
        i = self.items["event-assignment-1001"]
        self.assertEqual((i.due.day, i.due.hour, i.due.minute), (9, 23, 0))
        self.assertEqual(i.due.tzinfo, TZ)
        self.assertFalse(i.all_day)

    def test_utc_date_differs_from_local_date(self):
        i = self.items["event-assignment-1003"]  # 03:30Z on the 11th
        self.assertEqual((i.due.month, i.due.day, i.due.hour, i.due.minute), (11, 10, 21, 30))

    def test_all_day(self):
        i = self.items["event-assignment-1004"]
        self.assertTrue(i.all_day)
        self.assertEqual((i.due.day, i.due.hour, i.due.minute), (11, 23, 59))
        self.assertEqual(i.due.tzinfo, TZ)

    def test_kind_from_uid(self):
        self.assertEqual(self.items["event-assignment-1001"].kind, "assignment")
        self.assertEqual(self.items["event-calendar-event-98765"].kind, "event")

    def test_malformed(self):
        with self.assertRaises(FeedError):
            parse_feed("BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:garbage", TZ)


class FakeResponse:
    def __init__(self, body: str):
        self.body = body.encode()

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


ICS = "BEGIN:VCALENDAR\nEND:VCALENDAR\n"


class FetchFeedTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = Path(tmp.name) / "sub" / "feed.ics"

    def test_success_writes_cache(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(ICS)) as m:
            self.assertEqual(fetch_feed("https://h/x.ics", self.cache), (ICS, False))
        self.assertEqual(self.cache.read_text(), ICS)
        req = m.call_args.args[0]
        self.assertEqual(req.get_header("User-agent"), "canvas-today")

    def test_webcal_rewritten(self):
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(ICS)) as m:
            fetch_feed("webcal://h/x.ics", self.cache)
        self.assertEqual(m.call_args.args[0].full_url, "https://h/x.ics")

    def test_stale_fallback(self):
        self.cache.parent.mkdir()
        self.cache.write_text("OLD")
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            self.assertEqual(fetch_feed("https://h/x.ics", self.cache), ("OLD", True))

    def test_no_cache_raises_without_leaking_url(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(FeedError) as cm:
                fetch_feed("https://secret.example/token123", self.cache)
        self.assertNotIn("token123", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
