"""Command-line entry point: `today`, `today done`, `today check`, `today schedule`."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from . import schedule
from .config import Config, ConfigError, load_config
from .feed import FeedError
from .pipeline import Report, build_report
from .prioritize import group_by_tier
from .render import render
from .state import DoneStore, resolve_short_id

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="today", description="Your daily what's-due page.")
    p.add_argument("--root", type=Path,
                   default=Path(os.environ.get("CANVAS_TODAY_ROOT") or PROJECT_ROOT),
                   help="project folder holding config.toml, courses/ and data/")
    p.add_argument("--no-open", action="store_true", help="write the page but do not open it")
    p.add_argument("--offline", action="store_true", help="use the saved feed, no network")
    sub = p.add_subparsers(dest="command")
    for name, text in (("done", "mark items done"), ("undo", "un-mark items")):
        s = sub.add_parser(name, help=text)
        s.add_argument("ids", nargs="+", metavar="ID")
    sub.add_parser("check", help="list course-file problems and unmatched items")
    s = sub.add_parser("schedule", help="run automatically every morning (launchd)")
    s.add_argument("--at", required=True, metavar="HH:MM")
    sub.add_parser("unschedule", help="stop the automatic morning run")
    return p


def _write_page(cfg: Config, report: Report, now: datetime) -> Path:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.html_path.write_text(render(report, now), encoding="utf-8")
    return cfg.html_path


def _cmd_default(cfg: Config, args, now: datetime) -> int:
    report = build_report(cfg, now, offline=args.offline)
    path = _write_page(cfg, report, now)
    DoneStore(cfg.done_path).prune(now)

    groups = group_by_tier(report.ranked)
    counts = " · ".join(f"{len(rows)} {tier.label.lower()}" for tier, rows in groups.items())
    print(counts or "Nothing coming up.")
    notes = []
    if report.stale:
        notes.append("showing an old saved feed")
    if report.problems:
        notes.append(f"{len(report.problems)} course-file problems")
    if report.unmatched:
        notes.append(f"{len(report.unmatched)} unmatched items")
    if notes:
        print("Note: " + "; ".join(notes) + ". Run `today check` for details.")
    print(f"Page: {path}")

    if cfg.open_browser and not args.no_open:
        webbrowser.open(path.as_uri())
    return 0


def _cmd_mark(cfg: Config, args, now: datetime, undo: bool) -> int:
    # The cached feed makes this instant; fetch only when there is no cache yet.
    report = build_report(cfg, now, offline=cfg.cache_path.is_file())
    store = DoneStore(cfg.done_path)
    titles = {r.classified.item.uid: r.classified.item.title for r in report.ranked}
    # Done overdue items drop off the page, but must stay reachable for `undo`.
    uids = set(titles) | store.uids()
    status = 0
    for short in args.ids:
        try:
            uid = resolve_short_id(short, uids)
        except LookupError as e:
            print(e, file=sys.stderr)
            status = 1
            continue
        store.unmark(uid) if undo else store.mark(uid, now)
        print(f"{'Un-marked' if undo else 'Done'}: {titles.get(uid, uid)}")
    # Rebuild so the page reflects the change (no browser).
    _write_page(cfg, build_report(cfg, now, offline=cfg.cache_path.is_file()), now)
    return status


def _cmd_check(cfg: Config, args, now: datetime) -> int:
    report = build_report(cfg, now, offline=args.offline)
    print("Course file problems:")
    for problem in report.problems or ["none"]:
        print(f"  {problem}")

    print("Unmatched upcoming items:")
    groups: dict[tuple[str | None, str | None], list] = {}
    for c in report.unmatched:
        key = (c.course.code if c.course else None, c.item.course_code)
        groups.setdefault(key, []).append(c)
    if not groups:
        print("  none")
    for (code, context), items in groups.items():
        if code is None:
            print(f"  No course matches {context or '(no context)'!r}: add it to a course file's `match`.")
        else:
            print(f"  {code}: no category for these titles; add a keyword to a category:")
        for c in items:
            print(f"    {c.item.title}  (due {c.item.due:%a %b} {c.item.due.day})")

    print(f"{len(report.courses)} courses loaded, {report.feed_count} feed items parsed.")
    return 0


def _cmd_schedule(args, root: Path) -> int:
    try:
        hour, minute = schedule.parse_time(args.at)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    path = schedule.install(root, hour, minute)
    print(f"Scheduled daily at {hour:02d}:{minute:02d}. Wrote {path}")
    print("Check it with: launchctl print gui/$(id -u)/" + schedule.LABEL)
    print(f"Output goes to {root / 'data' / 'launchd.log'}")
    return 0


def _cmd_unschedule() -> int:
    if schedule.uninstall():
        print("Removed the daily schedule.")
    else:
        print("No daily schedule was installed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.expanduser().resolve()
    try:
        if args.command == "schedule":
            return _cmd_schedule(args, root)
        if args.command == "unschedule":
            return _cmd_unschedule()
        cfg = load_config(root)
        now = datetime.now(cfg.timezone)
        if args.command in ("done", "undo"):
            return _cmd_mark(cfg, args, now, undo=args.command == "undo")
        if args.command == "check":
            return _cmd_check(cfg, args, now)
        return _cmd_default(cfg, args, now)
    except (ConfigError, FeedError) as e:
        print(e, file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as e:
        print(f"launchctl failed: {(e.stderr or b'').decode(errors='replace').strip()}",
              file=sys.stderr)
        return 2
