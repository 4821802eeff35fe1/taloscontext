"""Schedule expansion: rules (local time windows) -> concrete UTC slots.

Semantics
- posts_per_day (capped by max_posts_per_day) are spread over the windows
  round-robin; a window holding k posts is split into k equal segments and
  each post lands in its own segment (start of segment when fixed, a random
  point inside it when randomized). Randomness is seeded by schedule + date +
  index, so the same day always yields the same slots — "next slot" is stable
  across calls and processes.
- Windows are interpreted in the schedule's IANA timezone. DST: a local time
  that doesn't exist (spring-forward gap) resolves to the instant one gap
  later (02:30 -> 03:30 local); an ambiguous local time (fall-back) resolves
  to its first occurrence. Storage is always UTC.
- Paused schedules, days not in days_of_week and exclude_dates yield nothing.
- min_interval_minutes is enforced between consecutive slots and against
  already-occupied times when looking for a free slot.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from zoneinfo import ZoneInfo

from app.models.scheduling import Schedule, ScheduleRule

MAX_DAYS_AHEAD = 120


class ScheduleValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Window:
    start: time
    end: time


def parse_hhmm(value: str) -> time:
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except (ValueError, AttributeError) as exc:
        raise ScheduleValidationError(f"Invalid time {value!r}; use HH:MM") from exc


def validate_windows(pairs: list[tuple[str, str]]) -> list[Window]:
    """Rejects malformed, midnight-crossing and overlapping windows."""
    if not pairs:
        raise ScheduleValidationError("Add at least one time window.")
    windows = sorted((Window(parse_hhmm(a), parse_hhmm(b)) for a, b in pairs), key=lambda w: w.start)
    for w in windows:
        if w.end < w.start:
            raise ScheduleValidationError(
                f"Window {w.start:%H:%M}–{w.end:%H:%M} crosses midnight; split it into two windows."
            )
    for a, b in pairwise(windows):
        if b.start < a.end:
            raise ScheduleValidationError(
                f"Windows {a.start:%H:%M}–{a.end:%H:%M} and {b.start:%H:%M}–{b.end:%H:%M} overlap."
            )
    return windows


def validate_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except Exception as exc:
        raise ScheduleValidationError(f"Unknown timezone {name!r}") from exc
    return name


def _local_to_utc(day: date, t: time, tz: ZoneInfo, extra: timedelta = timedelta()) -> datetime:
    naive = datetime.combine(day, t) + extra
    local = naive.replace(tzinfo=tz, fold=0)
    as_utc = local.astimezone(UTC)
    # Nonexistent local time (DST gap): round-tripping changes the wall clock;
    # PEP 495 fold=0 already maps it one gap later, which is what we want.
    return as_utc


class ScheduleService:
    def _windows(self, rules: list[ScheduleRule]) -> list[Window]:
        windows = sorted((Window(parse_hhmm(r.window_start), parse_hhmm(r.window_end)) for r in rules),
                         key=lambda w: w.start)
        return windows

    def _day_allowed(self, schedule: Schedule, day: date) -> bool:
        days = set(json.loads(schedule.days_of_week_json or "[0,1,2,3,4,5,6]"))
        excluded = set(json.loads(schedule.exclude_dates_json or "[]"))
        return day.weekday() in days and day.isoformat() not in excluded

    def slots_for_day(self, schedule: Schedule, rules: list[ScheduleRule], day: date) -> list[datetime]:
        if schedule.is_paused or not rules or not self._day_allowed(schedule, day):
            return []
        windows = self._windows(rules)
        tz = ZoneInfo(schedule.timezone or "UTC")
        count = max(0, min(schedule.posts_per_day or 0, schedule.max_posts_per_day or 10**6))
        per_window: dict[int, list[int]] = {}
        for i in range(count):
            per_window.setdefault(i % len(windows), []).append(i)

        slots: list[datetime] = []
        for w_idx, indices in per_window.items():
            window = windows[w_idx]
            start = datetime.combine(day, window.start)
            span = datetime.combine(day, window.end) - start
            segment = span / len(indices)
            for j, i in enumerate(indices):
                offset = segment * j
                if schedule.randomize_within_window and segment.total_seconds() > 0:
                    rng = random.Random(f"{schedule.id}:{day.isoformat()}:{i}")
                    offset += timedelta(seconds=rng.uniform(0, segment.total_seconds()))
                slots.append(_local_to_utc(day, window.start, tz, offset))
        slots.sort()
        return self._enforce_min_interval(slots, schedule.min_interval_minutes or 0)

    def upcoming(
        self, schedule: Schedule, rules: list[ScheduleRule], *, after: datetime, until: datetime | None = None,
        limit: int = 50,
    ) -> list[datetime]:
        tz = ZoneInfo(schedule.timezone or "UTC")
        day = after.astimezone(tz).date() - timedelta(days=1)  # slots near midnight UTC may belong to "yesterday"
        out: list[datetime] = []
        for _ in range(MAX_DAYS_AHEAD):
            for slot in self.slots_for_day(schedule, rules, day):
                if slot <= after:
                    continue
                if until and slot > until:
                    return out
                out.append(slot)
                if len(out) >= limit:
                    return out
            day += timedelta(days=1)
        return out

    def next_free_slot(
        self, schedule: Schedule, rules: list[ScheduleRule], *, after: datetime, occupied: list[datetime],
    ) -> datetime | None:
        gap = timedelta(minutes=schedule.min_interval_minutes or 0)
        taken = sorted(o if o.tzinfo else o.replace(tzinfo=UTC) for o in occupied)
        for slot in self.upcoming(schedule, rules, after=after, limit=500):
            if all(abs(slot - o) >= max(gap, timedelta(minutes=1)) for o in taken):
                return slot
        return None

    # v0.1 API kept for callers/tests
    def next_slot(
        self, schedule: Schedule, rules: list[ScheduleRule], *, after: datetime, count: int = 1
    ) -> list[datetime]:
        return self.upcoming(schedule, rules, after=after, limit=count)

    def _enforce_min_interval(self, slots: list[datetime], min_interval_minutes: int) -> list[datetime]:
        if not slots:
            return slots
        result = [slots[0]]
        for slot in slots[1:]:
            if (slot - result[-1]) >= timedelta(minutes=min_interval_minutes):
                result.append(slot)
        return result
