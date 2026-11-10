import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from canvas_today.courses import Category, load_courses, syllabus_items

from .helpers import FIXTURES, TZ

VALID = '''
code = "X 1"
name = "Ex"
match = ["X1"]
[[category]]
name = "A"
kind = "exam"
weight = 100
'''


class LoadCoursesTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def load(self, text: str, name="c.toml"):
        (self.dir / name).write_text(text)
        return load_courses(self.dir, TZ)

    def test_fixtures_happy_path(self):
        courses, problems = load_courses(FIXTURES / "courses", TZ)
        self.assertEqual(problems, [])
        self.assertEqual([c.code for c in courses], ["CS 400", "HIST 101", "MATH 221"])
        cs = courses[0]
        self.assertEqual(cs.thresholds, {"A": 93, "AB": 88})
        self.assertEqual(cs.categories[0].item_weight, 15)
        self.assertEqual(len(cs.events), 2)

    def test_missing_dir(self):
        self.assertEqual(load_courses(self.dir / "nope", TZ), ([], []))

    def test_sample_suffix_not_loaded(self):
        (self.dir / "a.toml.sample").write_text(VALID)
        self.assertEqual(load_courses(self.dir, TZ), ([], []))

    def test_valid(self):
        courses, problems = self.load(VALID)
        self.assertEqual((len(courses), problems), (1, []))

    def test_unparseable_skipped(self):
        courses, problems = self.load("code = = =")
        self.assertEqual(courses, [])
        self.assertIn("c.toml", problems[0])

    def test_missing_required_keys(self):
        courses, problems = self.load('name = "x"\n')
        self.assertEqual(courses, [])
        self.assertTrue(any("'code'" in p for p in problems))
        self.assertTrue(any("'match'" in p for p in problems))

    def test_bad_kind(self):
        _, problems = self.load(VALID.replace('"exam"', '"party"'))
        self.assertTrue(any("kind" in p and "party" in p for p in problems))

    def test_bad_weight(self):
        for bad in ('"lots"', "150", "-1"):
            _, problems = self.load(VALID.replace("weight = 100", f"weight = {bad}"))
            self.assertTrue(any("weight" in p for p in problems), bad)

    def test_unknown_event_category(self):
        _, problems = self.load(VALID + '[[event]]\ntitle = "T"\ndate = 2026-11-19\ncategory = "Nope"\n')
        self.assertTrue(any("'Nope'" in p for p in problems))

    def test_bad_event_date(self):
        _, problems = self.load(VALID + '[[event]]\ntitle = "T"\ndate = "soon"\n')
        self.assertTrue(any("date" in p for p in problems))

    def test_weights_not_100_is_warning_only(self):
        courses, problems = self.load(VALID.replace("weight = 100", "weight = 90"))
        self.assertEqual(len(courses), 1)
        self.assertTrue(any("sum to 90" in p for p in problems))

    def test_bad_threshold(self):
        _, problems = self.load(VALID + '[thresholds]\nA = 120\n')
        self.assertTrue(any("threshold" in p for p in problems))

    def test_one_bad_file_does_not_break_others(self):
        (self.dir / "bad.toml").write_text("= =")
        courses, problems = self.load(VALID, "good.toml")
        self.assertEqual(len(courses), 1)
        self.assertEqual(len(problems), 1)


class CategoryTests(unittest.TestCase):
    def test_item_weight(self):
        self.assertEqual(Category("A", "exam", 45, 3).item_weight, 15)
        self.assertIsNone(Category("A", "exam", 45).item_weight)

    def test_lead_days(self):
        self.assertEqual(Category("A", "exam", 1).effective_lead_days, 10)
        self.assertEqual(Category("A", "quiz", 1).effective_lead_days, 3)
        self.assertEqual(Category("A", "quiz", 1, lead_days=5).effective_lead_days, 5)


class SyllabusItemsTests(unittest.TestCase):
    def test_items(self):
        cs = load_courses(FIXTURES / "courses", TZ)[0][0]
        midterm, final = syllabus_items(cs, TZ)
        self.assertEqual(midterm.uid, "syllabus-cs-400-midterm-1-20261119")
        self.assertEqual(midterm.due, datetime(2026, 11, 19, 19, 15, tzinfo=TZ))
        self.assertFalse(midterm.all_day)
        self.assertEqual(midterm.source, "syllabus")
        self.assertEqual(final.due, datetime(2026, 12, 17, 23, 59, tzinfo=TZ))
        self.assertTrue(final.all_day)


if __name__ == "__main__":
    unittest.main()
