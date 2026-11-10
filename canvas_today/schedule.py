"""Install or remove the launchd job that runs canvas-today every morning."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.canvas-today.daily"


def plist_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def parse_time(text: str) -> tuple[int, int]:
    try:
        hour_text, minute_text = text.strip().split(":")
        hour, minute = int(hour_text), int(minute_text)
    except ValueError:
        raise ValueError(f"Bad time {text!r}; use HH:MM, e.g. 07:30.") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Bad time {text!r}; hour is 0-23 and minute is 0-59.")
    return hour, minute


def build_plist(python: Path, root: Path, hour: int, minute: int, log_path: Path) -> bytes:
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [str(python), "-m", "canvas_today", "--root", str(root)],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "WorkingDirectory": str(root),
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
        "RunAtLoad": False,
    })


def install(root: Path, hour: int, minute: int, *, home: Path | None = None,
            run=subprocess.run) -> Path:
    path = plist_path(home)
    log_path = root / "data" / "launchd.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)  # launchd will not create it
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_plist(Path(sys.executable), root, hour, minute, log_path))

    domain = f"gui/{os.getuid()}"
    run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True)  # may not be loaded
    run(["launchctl", "bootstrap", domain, str(path)], capture_output=True, check=True)
    return path


def uninstall(*, home: Path | None = None, run=subprocess.run) -> bool:
    path = plist_path(home)
    run(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"], capture_output=True)
    existed = path.exists()
    path.unlink(missing_ok=True)
    return existed
