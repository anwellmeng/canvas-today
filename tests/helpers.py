"""Shared test helpers."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from canvas_today.classify import Classified
from canvas_today.courses import load_courses
from canvas_today.feed import Item

TZ = ZoneInfo("America/Chicago")
NOW = datetime(2026, 11, 9, 8, 0, tzinfo=TZ)
FIXTURES = Path(__file__).parent / "fixtures"


def fixture_courses():
    courses, problems = load_courses(FIXTURES / "courses", TZ)
    assert problems == [], problems
    return courses


def make_item(title="Thing", due=None, uid="u1", kind="assignment", source="feed",
              course_code=None, all_day=False) -> Item:
    return Item(uid, title, course_code, due or NOW, all_day, None, source, kind)


def make_classified(due, kind="homework", weight=None, lead_days=2, uid="u1",
                    title="Thing", item_kind="assignment") -> Classified:
    return Classified(make_item(title, due, uid, item_kind), None, None, kind, weight, lead_days)


FEED_URL = "https://canvas.example.edu/feeds/calendars/user_SECRETTOKEN.ics"


def make_root(tmp: Path, with_cache: bool = True) -> Path:
    """A temp project root with config.toml, fixture courses and (optionally) a cached feed."""
    import shutil

    (tmp / "config.toml").write_text(
        f'feed_url = "{FEED_URL}"\ntimezone = "America/Chicago"\n', encoding="utf-8")
    shutil.copytree(FIXTURES / "courses", tmp / "courses")
    if with_cache:
        (tmp / "data").mkdir()
        shutil.copy(FIXTURES / "canvas_feed.ics", tmp / "data" / "feed_cache.ics")
    return tmp
