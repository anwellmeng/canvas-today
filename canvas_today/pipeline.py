"""Run the whole pipeline: feed + course files -> a Report ready to render."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .classify import Classified, classify, merge_duplicates
from .config import Config
from .courses import Course, load_courses, syllabus_items
from .feed import FeedError, fetch_feed, parse_feed
from .prioritize import Ranked, build
from .state import DoneStore

# A saved feed older than this is flagged on the page.
STALE_AFTER = timedelta(hours=18)


@dataclass
class Report:
    ranked: list[Ranked]
    courses: list[Course]
    problems: list[str]  # course-file problems
    stale: bool  # True when showing the cached feed instead of a fresh download
    unmatched: list[Classified]  # upcoming feed items with no course or no category
    generated: datetime
    cache_time: datetime | None = None  # when the cached feed was last saved (if stale)
    feed_count: int = 0  # number of items parsed from the feed


def build_report(cfg: Config, now: datetime, offline: bool = False) -> Report:
    courses, problems = load_courses(cfg.courses_dir, cfg.timezone)

    if offline:
        if not cfg.cache_path.is_file():
            raise FeedError("No cached feed yet. Run `today` once while online first.")
        text = cfg.cache_path.read_text(encoding="utf-8")
        saved = datetime.fromtimestamp(cfg.cache_path.stat().st_mtime, cfg.timezone)
        stale = now - saved > STALE_AFTER
    else:
        text, stale = fetch_feed(cfg.feed_url, cfg.cache_path, retries=2)
    cache_time = None
    if stale:
        cache_time = datetime.fromtimestamp(cfg.cache_path.stat().st_mtime, cfg.timezone)

    feed_items = parse_feed(text, cfg.timezone)
    items = feed_items + [i for c in courses for i in syllabus_items(c, cfg.timezone)]
    merged = merge_duplicates([classify(i, courses) for i in items])

    ranked = build(merged, DoneStore(cfg.done_path).uids(), now,
                   cfg.horizon_days, cfg.overdue_days)

    last = now + timedelta(days=cfg.horizon_days)
    unmatched = [c for c in merged
                 if c.item.source == "feed" and c.kind != "event"
                 and (c.course is None or c.category is None)
                 and now <= c.item.due <= last]
    return Report(ranked, courses, problems, stale, unmatched, now, cache_time, len(feed_items))
