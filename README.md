# canvas-today

A small tool that reads your private Canvas calendar feed and your per-course syllabus files, then writes one HTML page showing what is due and what to start preparing. It runs by hand (`today`) or automatically every morning.

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -e .
cp config.example.toml config.toml
```

Edit `config.toml` and paste your feed URL. In Canvas, open Calendar and click "Calendar Feed" in the right sidebar. Keep that URL secret: anyone with it can read your calendar. `config.toml` is git-ignored, and the tool never prints or embeds the URL.

Then add a file per course in `courses/` (copy `courses/example.toml.sample` to `courses/<name>.toml`; its comments explain every key). Files ending in `.sample` are ignored.

## Commands

Use `.venv/bin/today`, or activate the venv first. All commands accept `--root PATH` before the command name (or set `CANVAS_TODAY_ROOT`).

- `today` builds `data/today.html` and opens it. Options: `--no-open`, `--offline` (use the saved feed).
- `today done <id> [<id>...]` marks items done; `today undo <id>` reverses it. The short id is shown on every row.
- `today check` lists course-file problems and upcoming items whose course or category could not be matched, so you can see which `match` string or category keyword is missing.
- `today schedule --at 07:30` installs a launchd job that runs every morning; `today unschedule` removes it. Check it with `launchctl print gui/$(id -u)/com.canvas-today.daily`. Output goes to `data/launchd.log`.

## How tiers work

Items are sorted into: Overdue (up to `overdue_days` ago), Due today, Due tomorrow, This week (within 7 days), Start preparing (inside the item's lead time, which depends on its kind: exams 10 days, projects and papers 7, and so on), and On the horizon (exams, projects, papers and anything worth 5% or more, up to `horizon_days` away). Plain calendar events only appear today and tomorrow. Done items stay in their section, struck through, at the bottom.

## Limits of the feed

- The feed has no submission status, so Canvas cannot tell the tool you finished something. Use `today done <id>`.
- Items due at 11:59 PM often arrive as all-day items; they are shown as "end of day".
- Exams that are not in Canvas go in a `[[event]]` block in the course file.
- If Canvas cannot be reached, the last saved copy is used and the page says so.
