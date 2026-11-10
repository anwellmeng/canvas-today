"""Per-course TOML files (syllabus-derived): categories, weights, extra events."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from .feed import Item

KINDS = ("exam", "project", "paper", "quiz", "homework", "lab", "participation", "other")
DEFAULT_LEAD_DAYS = {
    "exam": 10, "project": 7, "paper": 7, "quiz": 3,
    "homework": 2, "lab": 2, "participation": 1, "other": 2,
}


@dataclass(frozen=True)
class Category:
    name: str
    kind: str
    weight: float
    count: int | None = None
    keywords: tuple[str, ...] = ()
    lead_days: int | None = None

    @property
    def item_weight(self) -> float | None:
        return self.weight / self.count if self.count else None

    @property
    def effective_lead_days(self) -> int:
        return self.lead_days if self.lead_days is not None else DEFAULT_LEAD_DAYS[self.kind]


@dataclass(frozen=True)
class SyllabusEvent:
    title: str
    when: date | datetime  # a datetime is naive local time
    category: str | None = None


@dataclass(frozen=True)
class Course:
    code: str
    name: str
    match: tuple[str, ...]
    color: str | None = None
    thresholds: dict[str, float] = field(default_factory=dict)
    categories: tuple[Category, ...] = ()
    events: tuple[SyllabusEvent, ...] = ()

    def category_named(self, name: str | None) -> Category | None:
        return next((c for c in self.categories if c.name == name), None)


def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_int(v: object, minimum: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= minimum


def _parse_course(raw: dict, problems: list[str], fname: str) -> Course | None:
    """Build a Course, appending human-readable problems. None if unusable."""
    def bad(msg: str) -> None:
        problems.append(f"{fname}: {msg}")

    code, name, match = raw.get("code"), raw.get("name"), raw.get("match")
    fatal = False
    if not isinstance(code, str) or not code.strip():
        bad("missing required key 'code'")
        fatal = True
    if not isinstance(name, str) or not name.strip():
        bad("missing required key 'name'")
        fatal = True
    if not isinstance(match, list) or not match or not all(isinstance(m, str) and m for m in match):
        bad("'match' must be a non-empty list of strings")
        fatal = True
    if fatal:
        return None

    thresholds: dict[str, float] = {}
    for k, v in (raw.get("thresholds") or {}).items():
        if _is_number(v) and 0 <= v <= 100:
            thresholds[k] = v
        else:
            bad(f"threshold {k!r} must be a number between 0 and 100")

    categories: list[Category] = []
    for i, c in enumerate(raw.get("category", []), 1):
        cname = c.get("name")
        if not isinstance(cname, str) or not cname:
            bad(f"category #{i} is missing 'name'")
            continue
        label = f"category {cname!r}"
        kind = c.get("kind")
        if kind not in KINDS:
            bad(f"{label}: kind {kind!r} must be one of {', '.join(KINDS)}")
            continue
        weight = c.get("weight")
        if not _is_number(weight) or not 0 <= weight <= 100:
            bad(f"{label}: weight must be a number between 0 and 100")
            continue
        count, lead = c.get("count"), c.get("lead_days")
        if count is not None and not _is_int(count, 1):
            bad(f"{label}: count must be a positive integer")
            count = None
        if lead is not None and not _is_int(lead, 0):
            bad(f"{label}: lead_days must be a non-negative integer")
            lead = None
        categories.append(Category(cname, kind, float(weight), count,
                                   tuple(str(k) for k in c.get("keywords", [])), lead))

    if categories:
        total = sum(c.weight for c in categories)
        if abs(total - 100) > 1e-6:
            bad(f"warning: category weights sum to {total:g}, not 100")

    names = {c.name for c in categories}
    events: list[SyllabusEvent] = []
    for i, e in enumerate(raw.get("event", []), 1):
        title, when = e.get("title"), e.get("date")
        if not isinstance(title, str) or not title:
            bad(f"event #{i} is missing 'title'")
            continue
        if not isinstance(when, date):  # datetime is a subclass of date
            bad(f"event {title!r}: 'date' must be a TOML date or datetime")
            continue
        cat = e.get("category")
        if cat is not None and cat not in names:
            bad(f"event {title!r}: category {cat!r} does not exist")
            cat = None
        events.append(SyllabusEvent(title, when, cat))

    return Course(code.strip(), name.strip(), tuple(match), raw.get("color"),
                  thresholds, tuple(categories), tuple(events))


def load_courses(courses_dir: Path, tz: ZoneInfo) -> tuple[list[Course], list[str]]:
    """Load every *.toml in courses_dir. Never raises for bad files; returns problems.

    `tz` is unused here (times are resolved in syllabus_items) but kept in the
    signature so callers pass one consistent set of arguments.
    """
    if not courses_dir.is_dir():
        return [], []
    courses: list[Course] = []
    problems: list[str] = []
    for path in sorted(courses_dir.glob("*.toml")):
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as e:
            problems.append(f"{path.name}: cannot be parsed, skipped ({e})")
            continue
        try:
            course = _parse_course(raw, problems, path.name)
        except (AttributeError, TypeError, ValueError) as e:
            problems.append(f"{path.name}: unexpected structure, skipped ({e})")
            continue
        if course:
            courses.append(course)
    return courses, problems


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def syllabus_items(course: Course, tz: ZoneInfo) -> list[Item]:
    items = []
    for ev in course.events:
        if isinstance(ev.when, datetime):
            when = ev.when
            due = when.astimezone(tz) if when.tzinfo else when.replace(tzinfo=tz)
            all_day = False
        else:
            due, all_day = datetime.combine(ev.when, time(23, 59), tzinfo=tz), True
        uid = f"syllabus-{_slug(course.code)}-{_slug(ev.title)}-{due:%Y%m%d}"
        items.append(Item(uid, ev.title, course.code, due, all_day, None, "syllabus", "assignment"))
    return items
