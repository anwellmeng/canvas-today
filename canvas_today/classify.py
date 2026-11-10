"""Resolve feed items to courses and categories; merge syllabus/feed duplicates."""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, replace
from datetime import date, datetime

from .courses import DEFAULT_LEAD_DAYS, Category, Course
from .feed import Item

DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "exam": ["exam", "midterm", "final"],
    "project": ["project"],
    "paper": ["paper", "essay", "report"],
    "quiz": ["quiz"],
    "homework": ["homework", "hw", "assignment", "problem set", "pset", "ps"],
    "lab": ["lab"],
    "participation": ["discussion", "participation", "attendance", "reflection"],
}

# Kinds that stay in the prep tiers even for plain calendar events.
_EVENT_KEEP_KINDS = {"exam", "quiz", "project", "paper"}


@dataclass(frozen=True)
class Classified:
    item: Item
    course: Course | None
    category: Category | None
    kind: str  # a courses.KINDS value, or "event"
    weight: float | None  # per-item weight, percent of final grade
    lead_days: int


def match_course(context: str | None, courses: list[Course]) -> Course | None:
    """Case-insensitive substring match; the longest matching string wins."""
    if not context:
        return None
    ctx = context.lower()
    best: Course | None = None
    best_len = 0
    for course in courses:
        for m in course.match:
            if m.lower() in ctx and len(m) > best_len:
                best, best_len = course, len(m)
    return best


def _kw_in(keyword: str, title: str) -> bool:
    # Word boundary on letters only, so "hw3" matches "hw" but "steps" does not match "ps".
    # A trailing "*" makes it a prefix: "zybooks*" matches "zyBooksW11".
    prefix = keyword.endswith("*")
    stem = re.escape(keyword.rstrip("*").lower())
    pattern = rf"(?<![a-z]){stem}" + ("" if prefix else "(?![a-z])")
    return re.search(pattern, title.lower()) is not None


def _longest_hit(candidates: list[tuple[str, object]], title: str):
    """Among (keyword, payload) pairs, payload of the longest keyword found in title."""
    hits = [(kw, p) for kw, p in candidates if _kw_in(kw, title)]
    return max(hits, key=lambda h: len(h[0]))[1] if hits else None


def _default_kind(title: str) -> str | None:
    return _longest_hit([(kw, kind) for kind, kws in DEFAULT_KEYWORDS.items() for kw in kws], title)


def classify(item: Item, courses: list[Course]) -> Classified:
    if item.source == "syllabus":
        course = next((c for c in courses if c.code == item.course_code), None)
    else:
        course = match_course(item.course_code, courses)

    category: Category | None = None
    if course:
        if item.source == "syllabus":
            ev = next((e for e in course.events
                       if e.title == item.title and _local_date(e.when) == item.due.date()), None)
            category = course.category_named(ev.category) if ev else None
        if category is None:
            category = _longest_hit(
                [(kw, c) for c in course.categories for kw in c.keywords], item.title)

    if category:
        kind, weight, lead = category.kind, category.item_weight, category.effective_lead_days
    else:
        kind = _default_kind(item.title) or "other"
        weight, lead = None, DEFAULT_LEAD_DAYS[kind]

    if item.kind == "event" and kind not in _EVENT_KEEP_KINDS:
        return Classified(item, course, None, "event", None, 0)
    return Classified(item, course, category, kind, weight, lead)


def _local_date(when: date | datetime) -> date:
    return when.date() if isinstance(when, datetime) else when


def _norm(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", title.lower()).split())


def _similar(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    ta, tb = set(a.split()), set(b.split())
    # "Homework 3" and "Homework 4" are different items however close the text is.
    if {t for t in ta if t.isdigit()} != {t for t in tb if t.isdigit()}:
        return False
    return (a == b or a in b or b in a or ta <= tb or tb <= ta
            or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8)


def merge_duplicates(classified: list[Classified]) -> list[Classified]:
    """Drop syllabus items that duplicate a feed item (same course, date, similar title).

    The feed item is kept; it inherits the syllabus category/weight if it had none.
    """
    feed = list(classified)
    result: list[Classified] = []
    absorbed: set[int] = set()
    for syl in (c for c in classified if c.item.source == "syllabus"):
        if syl.course is None:
            continue
        for i, f in enumerate(feed):
            if (f.item.source == "feed" and f.course is syl.course
                    and f.item.due.date() == syl.item.due.date()
                    and _similar(f.item.title, syl.item.title)):
                if f.category is None and syl.category is not None:
                    feed[i] = replace(f, category=syl.category, kind=syl.kind,
                                      weight=syl.weight, lead_days=syl.lead_days)
                absorbed.add(id(syl))
                break
    for c in feed:
        if id(c) not in absorbed:
            result.append(c)
    return result
