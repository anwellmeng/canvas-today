import unittest
from dataclasses import replace
from datetime import datetime

from canvas_today.classify import classify, match_course, merge_duplicates
from canvas_today.courses import Category, Course, syllabus_items
from canvas_today.feed import parse_feed

from .helpers import FIXTURES, NOW, TZ, fixture_courses, make_item


class MatchCourseTests(unittest.TestCase):
    def test_match(self):
        courses = fixture_courses()
        self.assertEqual(match_course("compsci 400 LEC 001", courses).code, "CS 400")
        self.assertIsNone(match_course("BIO 100", courses))
        self.assertIsNone(match_course(None, courses))

    def test_longest_wins(self):
        a = Course("A", "a", ("COMPSCI 4",))
        b = Course("B", "b", ("COMPSCI 400",))
        self.assertIs(match_course("COMPSCI 400 LEC", [a, b]), b)
        self.assertIs(match_course("COMPSCI 400 LEC", [b, a]), b)


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.courses = fixture_courses()

    def c(self, title, context="COMPSCI 400", **kw):
        return classify(make_item(title, course_code=context, **kw), self.courses)

    def test_course_category(self):
        r = self.c("Homework 3")
        self.assertEqual((r.course.code, r.category.name, r.kind), ("CS 400", "Homework", "homework"))
        self.assertEqual((r.weight, r.lead_days), (3.0, 2))

    def test_exam_weight_and_lead(self):
        r = self.c("Midterm Exam 1")
        self.assertEqual((r.kind, r.weight, r.lead_days), ("exam", 15.0, 10))

    def test_word_boundaries(self):
        math = "MATH 221"
        self.assertEqual(self.c("Problem Set 5", math).category.name, "Problem Sets")
        self.assertEqual(self.c("PS5", math).category.name, "Problem Sets")
        self.assertEqual(self.c("Next steps", math).kind, "other")  # not "ps"
        self.assertEqual(self.c("Finalize notes").kind, "other")  # not "final"
        self.assertEqual(self.c("Final review").kind, "exam")

    def test_longest_keyword_wins(self):
        course = Course("Z", "z", ("Z",), categories=(
            Category("Short", "quiz", 10, keywords=("project",)),
            Category("Long", "project", 10, keywords=("project proposal",)),
        ))
        r = classify(make_item("Project Proposal", course_code="Z"), [course])
        self.assertEqual(r.category.name, "Long")

    def test_default_keywords_without_course(self):
        for title, kind in [("Midterm", "exam"), ("Essay 2", "paper"), ("Quiz 1", "quiz"),
                            ("HW 3", "homework"), ("Lab 2", "lab"), ("Discussion 4", "participation"),
                            ("Project", "project"), ("Whatever", "other")]:
            r = classify(make_item(title, course_code="BIO 100"), self.courses)
            self.assertEqual((r.kind, r.course), (kind, None), title)
            self.assertIsNone(r.weight)

    def test_default_category_when_course_has_no_match(self):
        r = self.c("Lab 4 [draft]")
        self.assertEqual((r.course.code, r.category, r.kind, r.lead_days), ("CS 400", None, "lab", 2))

    def test_event_kind_demoted(self):
        r = classify(make_item("Lecture: Graphs", kind="event", course_code="COMPSCI 400"), self.courses)
        self.assertEqual((r.kind, r.lead_days, r.weight, r.category), ("event", 0, None, None))

    def test_event_with_homework_keyword_still_event(self):
        r = classify(make_item("Homework help", kind="event", course_code="COMPSCI 400"), self.courses)
        self.assertEqual(r.kind, "event")

    def test_event_with_exam_keyword_kept(self):
        r = classify(make_item("Midterm review", kind="event", course_code="COMPSCI 400"), self.courses)
        self.assertEqual(r.kind, "exam")

    def test_syllabus_item_uses_named_category(self):
        cs = self.courses[0]
        item = syllabus_items(cs, TZ)[1]  # "Final Exam"
        r = classify(item, self.courses)
        self.assertEqual((r.course, r.category.name, r.kind, r.weight), (cs, "Exams", "exam", 15.0))


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.courses = fixture_courses()
        text = (FIXTURES / "canvas_feed.ics").read_text()
        feed = [classify(i, self.courses) for i in parse_feed(text, TZ)]
        syl = [classify(i, self.courses) for c in self.courses for i in syllabus_items(c, TZ)]
        self.all = feed + syl

    def test_fixture_duplicate_merged(self):
        merged = merge_duplicates(self.all)
        uids = [m.item.uid for m in merged]
        self.assertNotIn("syllabus-cs-400-midterm-1-20261119", uids)
        self.assertIn("event-assignment-1007", uids)
        self.assertIn("syllabus-cs-400-final-exam-20261217", uids)  # no duplicate, kept
        self.assertEqual(len(merged), len(self.all) - 1)

    def test_feed_item_kept_with_url(self):
        m = next(x for x in merge_duplicates(self.all) if x.item.uid == "event-assignment-1007")
        self.assertIsNotNone(m.item.url)

    def test_category_taken_when_feed_has_none(self):
        cs = self.courses[0]
        feed = classify(make_item("Midterm 1", due=datetime(2026, 11, 19, 19, 15, tzinfo=TZ),
                                  course_code="COMPSCI 400"), self.courses)
        feed = replace(feed, category=None, kind="other", weight=None, lead_days=2)
        syl = classify(syllabus_items(cs, TZ)[0], self.courses)
        (m,) = merge_duplicates([feed, syl])
        self.assertEqual((m.item.source, m.category.name, m.kind, m.weight), ("feed", "Exams", "exam", 15.0))

    def test_different_date_or_course_or_title_not_merged(self):
        cs = self.courses[0]
        syl = classify(syllabus_items(cs, TZ)[0], self.courses)  # Midterm 1, Nov 19, CS
        base = dict(course_code="COMPSCI 400", due=datetime(2026, 11, 19, 12, 0, tzinfo=TZ))
        for over in ({"due": datetime(2026, 11, 20, 12, 0, tzinfo=TZ)},
                     {"course_code": "MATH 221"},
                     {"title": "Homework 8"}):
            f = classify(make_item(**{"title": "Midterm 1", **base, **over}), self.courses)
            self.assertEqual(len(merge_duplicates([f, syl])), 2, over)

    def test_title_similarity_variants(self):
        cs = self.courses[0]
        syl = classify(syllabus_items(cs, TZ)[0], self.courses)
        for title in ("MIDTERM 1!", "Midterm 1 (in class)", "Midterm-1"):
            f = classify(make_item(title, due=syl.item.due, course_code="COMPSCI 400"), self.courses)
            self.assertEqual(len(merge_duplicates([f, syl])), 1, title)


if __name__ == "__main__":
    unittest.main()
