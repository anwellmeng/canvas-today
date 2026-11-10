# canvas-today

A daily "what's due" page for Canvas. It reads your Canvas calendar feed and your course files, then opens one page showing what is overdue, due today, due this week, and worth starting on now.

## Setup (once)

```
python3 -m venv .venv
.venv/bin/pip install -e .
cp config.example.toml config.toml
```

1. In Canvas, open **Calendar** and click **Calendar Feed** (bottom of the right sidebar). Copy the URL.
2. Paste it into `config.toml` as `feed_url = "..."`. Treat it like a password: anyone with it can read your calendar. `config.toml` is never committed.
3. For each class, copy `courses/example.toml.sample` to `courses/<class>.toml` and fill in the grade weights and any exam dates from the syllabus. The comments in the sample explain each line.

Optional: add `alias today="/path/to/canvas_tool/.venv/bin/today"` to your `~/.zshrc` so you can type `today` anywhere. The examples below assume that.

## Daily use

| Command | What it does |
| --- | --- |
| `today` | Fetch the feed, build the page, open it in your browser |
| `today done k3f9` | Mark an item finished (the 4-character id is shown on each row) |
| `today undo k3f9` | Un-mark it |
| `today check` | List items that didn't match a course or category, and mistakes in course files |
| `today schedule --at 10:00` | Open the page automatically every day at that time |
| `today unschedule` | Stop the automatic run |

Two options go **before** the command name: `--no-open` (build the page without opening it) and `--offline` (use the last saved feed). Example: `today --offline check`.

## Reading the page

Items are grouped by urgency:

- **Overdue**: past due in the last 3 days and not marked done
- **Due today** / **Due tomorrow**
- **This week**: the next 7 days
- **Start preparing**: further out, but inside the lead time for that kind of item (exams 10 days, projects and papers 7)
- **On the horizon**: exams, projects, and anything worth 5% or more, up to 30 days out

Each row shows the course, the kind of item, when it is due, and its share of your grade when the course file knows it.

## Good to know

- **Canvas can't tell the tool what you've submitted.** Finished items stay listed until you run `today done <id>` or they pass their due date.
- **Things not in Canvas** (an exam listed only in the syllabus) go in an `[[event]]` block in the course file.
- **Recurring noise** such as office hours can be hidden with `ignore_titles = ["Office Hours"]` in `config.toml`.
- **Asleep at the scheduled time?** The page opens when the laptop next wakes. If it was shut down, run `today` by hand.
- **No connection?** The last saved copy is used, and the page says so if that copy is old.
- **New item not labelled right?** Run `today check`, then add a keyword to the matching category in the course file.

Your feed URL, course files, syllabi and generated page all stay on your machine and are git-ignored.

Things I want to add in future (no particular order):
- Mark items done from the page itself (checkboxes) instead of the `today done <id>` command
- An interactive front end to support that: a local web server, a menu bar app, or a browser extension, in place of the static HTML file