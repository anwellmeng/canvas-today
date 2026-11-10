"""Cases found in code review."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from canvas_today import classify, courses, feed

TZ = ZoneInfo("America/Chicago")


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


class FetchGuard(unittest.TestCase):
    def test_non_calendar_response_keeps_cache(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "feed_cache.ics"
            cache.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
            with mock.patch("urllib.request.urlopen",
                            return_value=FakeResponse(b"<html>Sign in</html>")):
                text, stale = feed.fetch_feed("https://example.invalid/x.ics", cache)
            self.assertTrue(stale)
            self.assertIn("BEGIN:VCALENDAR", text)
            self.assertIn("BEGIN:VCALENDAR", cache.read_text())


class SimilarTitles(unittest.TestCase):
    def test_token_subset(self):
        self.assertTrue(classify._similar("Midterm 1", "Midterm Exam 1"))
        self.assertFalse(classify._similar("Midterm 1", "Midterm 2"))
        self.assertFalse(classify._similar("Homework 3", "Homework 4"))


class CourseFiles(unittest.TestCase):
    def test_wrong_shape_is_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bad.toml").write_text(
                'code = "X 1"\nname = "X"\nmatch = ["X 1"]\ncategory = "oops"\n')
            loaded, problems = courses.load_courses(Path(d), TZ)
            self.assertEqual(loaded, [])
            self.assertEqual(len(problems), 1)

    def test_offset_datetime_is_converted(self):
        when = datetime(2026, 11, 20, 1, 0, tzinfo=timezone.utc)
        course = courses.Course("X 1", "X", ("X 1",),
                                events=(courses.SyllabusEvent("Quiz", when),))
        item = courses.syllabus_items(course, TZ)[0]
        self.assertEqual(item.due.hour, 19)
        self.assertEqual(item.due.day, 19)


if __name__ == "__main__":
    unittest.main()
