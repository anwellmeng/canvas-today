"""Render a Report as one self-contained HTML page (inline CSS, no scripts)."""

from __future__ import annotations

import re
from datetime import datetime
from html import escape

from .pipeline import Report
from .prioritize import Ranked, Tier, group_by_tier

EXAM_WINDOW_DAYS = 10
_HIGH_STAKES_KINDS = {"exam", "project", "paper"}
_HIGH_STAKES_WEIGHT = 5
_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}")

CSS = """
:root {
  --bg: #fbfaf8; --text: #1d1d1f; --muted: #5c5c63; --line: #e4e2dd;
  --accent: #b42318; --neutral: #9a9aa2; --chip: #efede8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #17171a; --text: #ececef; --muted: #a1a1aa; --line: #2d2d33;
    --accent: #ff8a80; --neutral: #70707a; --chip: #25252b;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text); line-height: 1.5;
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
main { max-width: 760px; margin: 0 auto; padding: 32px 16px 48px; }
h1 { font-size: 1.6rem; margin: 0; }
.summary { color: var(--muted); margin: 4px 0 20px; }
.notice { border: 1px solid var(--line); border-radius: 6px; padding: 8px 12px;
  margin: 0 0 10px; color: var(--muted); font-size: 0.9rem; }
section { margin-top: 28px; }
h2 { font-size: 0.8rem; letter-spacing: 0.06em; text-transform: uppercase;
  margin: 0; padding-bottom: 6px; border-bottom: 1px solid var(--line); }
h2 .count { color: var(--muted); font-weight: 400; }
section.urgent h2 { color: var(--accent); border-bottom-color: var(--accent); }
ul { list-style: none; margin: 0; padding: 0; }
.row { display: flex; flex-wrap: wrap; gap: 2px 16px; padding: 10px 0;
  border-bottom: 1px solid var(--line); }
.main { flex: 1 1 20rem; min-width: 0; }
.when { flex: 0 0 auto; display: flex; flex-direction: column; align-items: flex-end;
  font-size: 0.9rem; font-variant-numeric: tabular-nums; }
.title { overflow-wrap: anywhere; }
.title a { color: inherit; text-decoration-color: var(--neutral); }
.stakes .title { font-weight: 650; }
.meta, .when .weight { font-size: 0.85rem; color: var(--muted); }
.dot { display: inline-block; width: 0.6rem; height: 0.6rem; border-radius: 50%;
  background: var(--c, var(--neutral)); margin-right: 5px; }
.chip { background: var(--chip); border-radius: 4px; padding: 0 6px; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85em; }
.row:not(.event) .meta code { color: var(--text); }
.event .title { font-weight: 400; color: var(--muted); }
.done { opacity: 0.6; }
.done .title { text-decoration: line-through; }
footer { margin-top: 40px; font-size: 0.85rem; color: var(--muted); }
footer p { margin: 4px 0; }
.legend { margin-bottom: 16px; }
.legend div { margin: 6px 0; }
@media (max-width: 560px) {
  .when { flex-basis: 100%; flex-direction: row; align-items: baseline; gap: 12px; }
}
"""


def _fmt_num(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def _clock(d: datetime) -> str:
    return f"{d:%I:%M %p}".lstrip("0")


def _day(d: datetime) -> str:
    return f"{d:%a %b} {d.day}"


def _friendly_due(r: Ranked, now: datetime) -> str:
    item = r.classified.item
    due = item.due.astimezone(now.tzinfo)
    delta = (due.date() - now.date()).days
    day = "Today" if delta == 0 else "Tomorrow" if delta == 1 else _day(due)
    if item.all_day:
        return f"{day}, end of day"
    sep = " " if delta in (0, 1) else ", "
    return f"{day}{sep}{_clock(due)}"


def _is_high_stakes(r: Ranked) -> bool:
    c = r.classified
    return c.kind in _HIGH_STAKES_KINDS or (c.weight or 0) >= _HIGH_STAKES_WEIGHT


def _dot(color: str | None) -> str:
    style = f' style="--c:{escape(color)}"' if color and _COLOR.fullmatch(color) else ""
    return f'<span class="dot"{style}></span>'


def _row(r: Ranked, now: datetime) -> str:
    c = r.classified
    item = c.item
    classes = ["row"]
    if r.done:
        classes.append("done")
    if c.kind == "event":
        classes.append("event")
    if _is_high_stakes(r):
        classes.append("stakes")

    title = escape(item.title)
    if item.url and item.url.startswith(("https://", "http://")):
        title = f'<a href="{escape(item.url)}">{title}</a>'

    code = c.course.code if c.course else (item.course_code or "No course")
    meta = [_dot(c.course.color if c.course else None) + escape(code)]
    if c.kind != "other":
        meta.append(c.kind.capitalize())
    if r.tier in (Tier.PREPARE, Tier.HORIZON):
        meta.append(f'<span class="chip">in {r.days_until} days</span>')
    meta.append(f"<code>{escape(r.short_id)}</code>")

    weight = ""
    if c.weight is not None:
        weight = f'<span class="weight">{_fmt_num(c.weight)}% of grade</span>'
    return (f'<li class="{" ".join(classes)}"><div class="main">'
            f'<div class="title">{title}</div>'
            f'<div class="meta">{" · ".join(meta)}</div></div>'
            f'<div class="when"><span>{escape(_friendly_due(r, now))}</span>{weight}</div></li>')


def _summary(ranked: list[Ranked]) -> str:
    live = [r for r in ranked if not r.done]
    exams = [r for r in live if r.classified.kind == "exam"
             and 0 <= r.days_until <= EXAM_WINDOW_DAYS]
    count = lambda tier: sum(r.tier is tier for r in live)  # noqa: E731
    parts = [
        (count(Tier.OVERDUE), "overdue"),
        (count(Tier.TODAY), "due today"),
        (count(Tier.TOMORROW), "due tomorrow"),
        (len(exams), f"exam{'s' if len(exams) != 1 else ''} within {EXAM_WINDOW_DAYS} days"),
        (count(Tier.THIS_WEEK), "this week"),
    ]
    text = " · ".join(f"{n} {label}" for n, label in parts if n)
    return text or "Nothing coming up."


def _notices(report: Report) -> list[str]:
    notes = []
    if report.stale:
        when = ""
        if report.cache_time:
            when = f" {_day(report.cache_time)}, {_clock(report.cache_time)}"
        notes.append(f"Not refreshed from Canvas; showing the copy saved{when}.")
    if report.problems:
        n = len(report.problems)
        notes.append(f"{n} problem{'s' if n != 1 else ''} in course files "
                     "&mdash; run <code>today check</code>.")
    if report.unmatched:
        n = len(report.unmatched)
        notes.append(f"{n} upcoming item{'s' if n != 1 else ''} with no matching course or "
                     "category &mdash; run <code>today check</code>.")
    return [f'<p class="notice">{n}</p>' for n in notes]


def _legend(report: Report) -> str:
    lines = []
    for course in report.courses:
        cats = " · ".join(f"{escape(c.name)} {_fmt_num(c.weight)}%" for c in course.categories)
        grades = " · ".join(f"{escape(k)} {_fmt_num(v)}" for k, v in course.thresholds.items())
        detail = "<br>".join(x for x in (cats, grades) if x)
        lines.append(f"<div>{_dot(course.color)}<strong>{escape(course.code)}</strong> "
                     f"{escape(course.name)}" + (f"<br>{detail}" if detail else "") + "</div>")
    return f'<div class="legend">{"".join(lines)}</div>' if lines else ""


def render(report: Report, now: datetime) -> str:
    sections = []
    for tier, rows in group_by_tier(report.ranked).items():
        rows = sorted(rows, key=lambda r: r.done)  # stable: done items sink to the bottom
        urgent = ' class="urgent"' if tier in (Tier.OVERDUE, Tier.TODAY) else ""
        sections.append(
            f'<section{urgent}><h2>{escape(tier.label)} '
            f'<span class="count">{len(rows)}</span></h2>'
            f'<ul>{"".join(_row(r, now) for r in rows)}</ul></section>')

    generated = report.generated
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Today · {escape(_day(now))}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<header>
<h1>{now:%A, %B} {now.day}</h1>
<p class="summary">{escape(_summary(report.ranked))}</p>
{"".join(_notices(report))}
</header>
{"".join(sections)}
<footer>
{_legend(report)}
<p>Generated {escape(_day(generated))}, {escape(_clock(generated))}</p>
<p><code>today done &lt;id&gt;</code> · <code>today undo &lt;id&gt;</code> · <code>today check</code></p>
</footer>
</main>
</body>
</html>
"""
