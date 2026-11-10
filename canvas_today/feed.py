"""Fetch and parse the Canvas iCal calendar feed."""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from icalendar import Calendar


class FeedError(Exception):
    """Raised when the feed cannot be fetched or parsed."""


@dataclass(frozen=True)
class Item:
    uid: str
    title: str
    course_code: str | None  # raw bracket context from the feed until classify resolves it
    due: datetime
    all_day: bool
    url: str | None
    source: Literal["feed", "syllabus"]
    kind: Literal["assignment", "event"]


def fetch_feed(url: str, cache_path: Path, timeout: int = 20) -> tuple[str, bool]:
    """Return (ics_text, stale). Falls back to the cache on any failure."""
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    req = urllib.request.Request(url, headers={"User-Agent": "canvas-today"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
        if "BEGIN:VCALENDAR" not in text:
            raise ValueError("response is not a calendar")
    except Exception:  # noqa: BLE001 - deliberately generic; never surface the URL
        if cache_path.is_file():
            return cache_path.read_text(encoding="utf-8"), True
        raise FeedError("Could not download the calendar feed and no cached copy exists.") from None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(text, encoding="utf-8")
    return text, False


_CONTEXT = re.compile(r"^(.*?)\s*\[([^\[\]]*)\]\s*$", re.DOTALL)


def split_summary(summary: str) -> tuple[str, str | None]:
    """'Homework 3 [COMPSCI 400 LEC 001]' -> ('Homework 3', 'COMPSCI 400 LEC 001')."""
    summary = " ".join(summary.split())
    m = _CONTEXT.match(summary)
    if m and m.group(1):
        return m.group(1), m.group(2).strip() or None
    return summary, None


def parse_feed(text: str, tz: ZoneInfo) -> list[Item]:
    try:
        cal = Calendar.from_ical(text)
    except Exception as e:  # noqa: BLE001
        raise FeedError(f"Calendar feed is not valid iCal data: {e}") from e

    items: list[Item] = []
    for ev in cal.walk("VEVENT"):
        dtstart = ev.get("DTSTART")
        summary = ev.get("SUMMARY")
        if dtstart is None or not summary:
            continue
        value = dtstart.dt
        if isinstance(value, datetime):
            # Floating (naive) times are taken as already local.
            due = value.astimezone(tz) if value.tzinfo else value.replace(tzinfo=tz)
            all_day = False
        elif isinstance(value, date):
            due = datetime.combine(value, time(23, 59), tzinfo=tz)
            all_day = True
        else:
            continue
        title, context = split_summary(str(summary))
        uid = str(ev.get("UID", "")) or f"feed-{title}-{due.isoformat()}"
        url = ev.get("URL")
        items.append(
            Item(
                uid=uid,
                title=title,
                course_code=context,
                due=due,
                all_day=all_day,
                url=str(url) if url else None,
                source="feed",
                kind="assignment" if uid.startswith("event-assignment") else "event",
            )
        )
    return items
