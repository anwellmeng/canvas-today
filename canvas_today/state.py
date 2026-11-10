"""Persistent "done" marks and short ids that can be typed on the command line."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

# base32 without ambiguous characters (0, 1, o, l)
_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyz"


def short_id(uid: str) -> str:
    """Stable 4-character id derived from the uid."""
    n = int.from_bytes(hashlib.sha1(uid.encode("utf-8")).digest()[:8], "big")
    chars = []
    for _ in range(4):
        n, r = divmod(n, len(_ALPHABET))
        chars.append(_ALPHABET[r])
    return "".join(chars)


def resolve_short_id(short: str, uids: Iterable[str]) -> str:
    """Return the uid whose short id is `short`; LookupError if none or ambiguous."""
    short = short.strip().lower()
    matches = sorted({u for u in uids if short_id(u) == short})
    if not matches:
        raise LookupError(f"No item has the id {short!r}.")
    if len(matches) > 1:
        raise LookupError(f"Id {short!r} is ambiguous; candidates: {', '.join(matches)}")
    return matches[0]


class DoneStore:
    """uid -> ISO timestamp of when it was marked done, stored as JSON."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}

    def _save(self, data: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def mark(self, uid: str, now: datetime) -> None:
        data = self.load()
        data[uid] = now.isoformat()
        self._save(data)

    def unmark(self, uid: str) -> None:
        data = self.load()
        if data.pop(uid, None) is not None:
            self._save(data)

    def uids(self) -> set[str]:
        return set(self.load())

    def prune(self, now: datetime, max_age_days: int = 120) -> int:
        """Drop entries older than max_age_days (or unreadable). Returns number removed."""
        cutoff = now - timedelta(days=max_age_days)
        data = self.load()
        kept: dict[str, str] = {}
        for uid, stamp in data.items():
            try:
                if datetime.fromisoformat(stamp) >= cutoff:
                    kept[uid] = stamp
            except (ValueError, TypeError):
                continue
        if len(kept) != len(data):
            self._save(kept)
        return len(data) - len(kept)
