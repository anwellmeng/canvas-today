import unittest
from datetime import datetime, timedelta

from canvas_today.classify import classify
from canvas_today.feed import parse_feed
from canvas_today.prioritize import Tier, assign_tier, build, group_by_tier
from canvas_today.state import short_id

from .helpers import FIXTURES, NOW, TZ, fixture_courses, make_classified

H, O = 30, 3


def on_day(d: int, hour=23, minute=59) -> datetime:
    return datetime(2026, 11, 9, hour, minute, tzinfo=TZ) + timedelta(days=d, hours=0)


def tier(d, **kw):
    hour = kw.pop("hour", 23)
    return assign_tier(make_classified(on_day(d, hour, 59 if hour == 23 else 0), **kw), NOW, H, O)


class AssignTierTests(unittest.TestCase):
    def test_boundaries_homework(self):
        expect = {0: Tier.TODAY, 1: Tier.TOMORROW, 2: Tier.THIS_WEEK, 7: Tier.THIS_WEEK, 8: None}
        for d, t in expect.items():
            self.assertEqual(tier(d), t, d)

    def test_local_date_not_24h(self):
        # 08:00 now; due 00:30 tomorrow is only 16.5h away but is tomorrow.
        c = make_classified(datetime(2026, 11, 10, 0, 30, tzinfo=TZ))
        self.assertEqual(assign_tier(c, NOW, H, O), Tier.TOMORROW)

    def test_prepare_boundaries(self):
        self.assertEqual(tier(8, kind="exam", lead_days=10), Tier.PREPARE)
        self.assertEqual(tier(10, kind="exam", lead_days=10), Tier.PREPARE)
        self.assertEqual(tier(11, kind="exam", lead_days=10), Tier.HORIZON)

    def test_horizon_boundaries(self):
        self.assertEqual(tier(30, kind="project"), Tier.HORIZON)
        self.assertIsNone(tier(31, kind="project"))

    def test_horizon_high_stakes_filter(self):
        self.assertIsNone(tier(20, kind="homework", weight=4.9))
        self.assertEqual(tier(20, kind="homework", weight=5), Tier.HORIZON)
        self.assertIsNone(tier(20, kind="homework"))
        self.assertEqual(tier(20, kind="paper"), Tier.HORIZON)
        self.assertIsNone(tier(20, kind="quiz"))

    def test_overdue(self):
        self.assertEqual(tier(-1, hour=12), Tier.OVERDUE)
        self.assertEqual(tier(-3), Tier.OVERDUE)
        self.assertIsNone(tier(-4))

    def test_overdue_earlier_today(self):
        c = make_classified(datetime(2026, 11, 9, 7, 0, tzinfo=TZ))
        self.assertEqual(assign_tier(c, NOW, H, O), Tier.OVERDUE)

    def test_past_exam_and_event_not_overdue(self):
        past = datetime(2026, 11, 8, 12, 0, tzinfo=TZ)
        today_early = datetime(2026, 11, 9, 7, 0, tzinfo=TZ)
        for due in (past, today_early):
            self.assertIsNone(assign_tier(make_classified(due, kind="exam"), NOW, H, O))
            self.assertIsNone(assign_tier(make_classified(due, kind="event", lead_days=0), NOW, H, O))

    def test_event_only_today_and_tomorrow(self):
        got = [tier(d, kind="event", lead_days=0) for d in (0, 1, 2, 5, 9, 20)]
        self.assertEqual(got, [Tier.TODAY, Tier.TOMORROW, None, None, None, None])

    def test_overdue_days_configurable(self):
        c = make_classified(on_day(-2))
        self.assertIsNone(assign_tier(c, NOW, H, 1))


class BuildTests(unittest.TestCase):
    def test_sort_order(self):
        a = make_classified(on_day(0), uid="a", title="B", weight=5)
        b = make_classified(on_day(0), uid="b", title="A", weight=10)
        c = make_classified(on_day(0), uid="c", title="A", weight=5)
        d = make_classified(on_day(0, 9), uid="d", title="Z")  # earlier time wins
        e = make_classified(on_day(1), uid="e")
        f = make_classified(on_day(-1), uid="f")
        ranked = build([e, a, b, c, d, f], set(), NOW, H, O)
        self.assertEqual([r.classified.item.uid for r in ranked], ["f", "d", "b", "c", "a", "e"])

    def test_done_kept_except_overdue(self):
        today = make_classified(on_day(0), uid="t")
        late = make_classified(on_day(-1), uid="l")
        ranked = build([today, late], {"t", "l"}, NOW, H, O)
        self.assertEqual([(r.classified.item.uid, r.done) for r in ranked], [("t", True)])

    def test_not_done_default_and_short_id(self):
        (r,) = build([make_classified(on_day(0), uid="t")], set(), NOW, H, O)
        self.assertFalse(r.done)
        self.assertEqual(r.short_id, short_id("t"))
        self.assertEqual(r.days_until, 0)

    def test_none_dropped(self):
        self.assertEqual(build([make_classified(on_day(40))], set(), NOW, H, O), [])

    def test_group_by_tier(self):
        cs = [make_classified(on_day(d), uid=str(d)) for d in (3, 0, 1, 0)]
        groups = group_by_tier(build(cs, set(), NOW, H, O))
        self.assertEqual(list(groups), [Tier.TODAY, Tier.TOMORROW, Tier.THIS_WEEK])
        self.assertEqual(len(groups[Tier.TODAY]), 2)

    def test_labels(self):
        self.assertEqual(Tier.OVERDUE.label, "Overdue")
        self.assertEqual(Tier.HORIZON.label, "On the horizon")
        self.assertTrue(Tier.OVERDUE < Tier.HORIZON)


class FixtureEndToEndTests(unittest.TestCase):
    def test_pipeline(self):
        from canvas_today.classify import merge_duplicates
        from canvas_today.courses import syllabus_items
        courses = fixture_courses()
        items = parse_feed((FIXTURES / "canvas_feed.ics").read_text(), TZ)
        items += [i for c in courses for i in syllabus_items(c, TZ)]
        ranked = build(merge_duplicates([classify(i, courses) for i in items]), set(), NOW, H, O)
        got = {r.classified.item.uid: r.tier for r in ranked}
        expected = {
            "event-assignment-1002": Tier.OVERDUE,       # d=-3
            "event-assignment-1001": Tier.TODAY,
            "event-calendar-event-98765": Tier.TODAY,    # lecture
            "event-assignment-1003": Tier.TOMORROW,      # UTC date shift
            "event-calendar-event-98766": Tier.TOMORROW,
            "event-assignment-1004": Tier.THIS_WEEK,
            "event-assignment-1012": Tier.THIS_WEEK,
            "event-assignment-1013": Tier.THIS_WEEK,
            "event-assignment-1005": Tier.THIS_WEEK,     # d=7
            "event-assignment-1007": Tier.PREPARE,       # d=10, merged midterm
            "event-assignment-1008": Tier.HORIZON,       # d=11 project
            "event-assignment-1009": Tier.HORIZON,       # d=11 exam
            "event-assignment-1010": Tier.HORIZON,       # d=30
        }
        self.assertEqual(got, expected)  # absent: d=8 hw, d=31 paper, past exam, d=38 final, no-DTSTART


if __name__ == "__main__":
    unittest.main()
