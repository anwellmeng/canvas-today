"""Sort classified items into urgency tiers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from .classify import Classified
from .state import short_id

_HIGH_STAKES_KINDS = {"exam", "project", "paper"}
_HIGH_STAKES_WEIGHT = 5


class Tier(IntEnum):
    OVERDUE = 1
    TODAY = 2
    TOMORROW = 3
    THIS_WEEK = 4
    PREPARE = 5
    HORIZON = 6

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    Tier.OVERDUE: "Overdue",
    Tier.TODAY: "Due today",
    Tier.TOMORROW: "Due tomorrow",
    Tier.THIS_WEEK: "This week",
    Tier.PREPARE: "Start preparing",
    Tier.HORIZON: "On the horizon",
}


@dataclass(frozen=True)
class Ranked:
    classified: Classified
    tier: Tier
    days_until: int  # local calendar days from now's date; negative if past
    short_id: str
    done: bool


def _days_until(c: Classified, now: datetime) -> int:
    return (c.item.due.astimezone(now.tzinfo).date() - now.date()).days


def assign_tier(c: Classified, now: datetime, horizon_days: int, overdue_days: int) -> Tier | None:
    d = _days_until(c, now)
    if c.item.due < now:
        if c.kind not in ("event", "exam") and d >= -overdue_days:
            return Tier.OVERDUE
        return None
    if d == 0:
        return Tier.TODAY
    if d == 1:
        return Tier.TOMORROW
    if c.kind == "event":
        return None
    if d <= 7:
        return Tier.THIS_WEEK
    if d <= c.lead_days:
        return Tier.PREPARE
    high_stakes = c.kind in _HIGH_STAKES_KINDS or (
        c.weight is not None and c.weight >= _HIGH_STAKES_WEIGHT)
    if d <= horizon_days and high_stakes:
        return Tier.HORIZON
    return None


def build(classified: list[Classified], done_uids: set[str], now: datetime,
          horizon_days: int, overdue_days: int) -> list[Ranked]:
    ranked: list[Ranked] = []
    for c in classified:
        tier = assign_tier(c, now, horizon_days, overdue_days)
        if tier is None:
            continue
        done = c.item.uid in done_uids
        if done and tier is Tier.OVERDUE:
            continue
        ranked.append(Ranked(c, tier, _days_until(c, now), short_id(c.item.uid), done))
    ranked.sort(key=lambda r: (r.tier, r.classified.item.due,
                               -(r.classified.weight or 0), r.classified.item.title))
    return ranked


def group_by_tier(ranked: list[Ranked]) -> dict[Tier, list[Ranked]]:
    groups: dict[Tier, list[Ranked]] = {}
    for r in ranked:
        groups.setdefault(r.tier, []).append(r)
    return groups
