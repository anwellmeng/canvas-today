"""Load config.toml from the project root."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigError(Exception):
    """Raised for a missing or invalid configuration."""


@dataclass
class Config:
    feed_url: str
    timezone: ZoneInfo
    root: Path
    horizon_days: int = 30
    overdue_days: int = 3
    open_browser: bool = True

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def courses_dir(self) -> Path:
        return self.root / "courses"

    @property
    def cache_path(self) -> Path:
        return self.data_dir / "feed_cache.ics"

    @property
    def done_path(self) -> Path:
        return self.data_dir / "done.json"

    @property
    def html_path(self) -> Path:
        return self.data_dir / "today.html"


def load_config(root: Path, require_feed: bool = True) -> Config:
    path = root / "config.toml"
    if not path.is_file():
        raise ConfigError(
            f"Missing {path}. Copy config.example.toml to config.toml and set feed_url."
        )
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} is not valid TOML: {e}") from e

    feed_url = str(raw.get("feed_url", "")).strip()
    if require_feed and not feed_url:
        raise ConfigError(f"feed_url is empty in {path}. Paste your Canvas calendar feed URL.")

    tz_name = raw.get("timezone", "America/Chicago")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ConfigError(f"Unknown timezone {tz_name!r} in {path}.") from e

    try:
        return Config(
            feed_url=feed_url,
            timezone=tz,
            root=root,
            horizon_days=int(raw.get("horizon_days", 30)),
            overdue_days=int(raw.get("overdue_days", 3)),
            open_browser=bool(raw.get("open_browser", True)),
        )
    except (TypeError, ValueError) as e:
        raise ConfigError(f"Invalid numeric setting in {path}: {e}") from e
