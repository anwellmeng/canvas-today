"""Fetch and parse the Canvas iCal calendar feed."""

from __future__ import annotations

import re
import ssl
import time as _time
import urllib.error
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


def fetch_feed(url: str, cache_path: Path, timeout: int = 20,
               retries: int = 0, retry_wait: float = 4.0) -> tuple[str, bool]:
    """Return (ics_text, stale). Falls back to the cache once every attempt has failed."""
    for _ in range(retries):
        try:
            return _fetch_once(url, cache_path, timeout, use_cache=False)
        except FeedError:
            _time.sleep(retry_wait)
    return _fetch_once(url, cache_path, timeout, use_cache=True)


# python.org builds of Python on macOS ship without CA certificates; the system bundle is here.
_SYSTEM_CA_BUNDLE = Path("/etc/ssl/cert.pem")


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not ctx.cert_store_stats()["x509_ca"] and _SYSTEM_CA_BUNDLE.is_file():
        ctx.load_verify_locations(cafile=str(_SYSTEM_CA_BUNDLE))
    return ctx


def _reason(e: Exception) -> str:
    """A short cause for the error message. Never includes the URL."""
    if isinstance(e, urllib.error.HTTPError):
        return f"Canvas answered HTTP {e.code}"
    if isinstance(getattr(e, "reason", None), ssl.SSLError) or isinstance(e, ssl.SSLError):
        return "the secure connection could not be verified"
    if isinstance(e, ValueError):
        return "the address did not return a calendar"
    return "network error"


def _fetch_once(url: str, cache_path: Path, timeout: int, use_cache: bool) -> tuple[str, bool]:
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    req = urllib.request.Request(url, headers={"User-Agent": "canvas-today"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            text = resp.read().decode("utf-8")
        if "BEGIN:VCALENDAR" not in text:
            raise ValueError("response is not a calendar")
    except Exception as e:  # noqa: BLE001 - deliberately generic; never surface the URL
        if use_cache and cache_path.is_file():
            return cache_path.read_text(encoding="utf-8"), True
        raise FeedError(f"Could not download the calendar feed ({_reason(e)}) and no saved "
                        "copy exists. Check your connection and the feed_url in config.toml."
                        ) from None
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
