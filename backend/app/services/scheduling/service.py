from __future__ import annotations

import json
import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.scheduling import Schedule, ScheduleRule


class ScheduleService:
    """Expands a Schedule + its windows into concrete UTC scheduled_at timestamps.

    All storage is UTC (ARCHITECTURE.md §3); the schedule's own timezone is only
    used to interpret window_start/window_end during expansion.
    """

    def next_slot(
        self, schedule: Schedule, rules: list[ScheduleRule], *, after: datetime, count: int = 1
    ) -> list[datetime]:
        tz = ZoneInfo(schedule.timezone)
        days_allowed = set(json.loads(schedule.days_of_week_json or "[0,1,2,3,4,5,6]"))
        exclude_dates = set(json.loads(schedule.exclude_dates_json or "[]"))

        slots: list[datetime] = []
        cursor_date = after.astimezone(tz).date()
        attempts = 0

        while len(slots) < count and attempts < 60:
            attempts += 1
            if cursor_date.weekday() in days_allowed and cursor_date.isoformat() not in exclude_dates:
                for rule in rules:
                    candidate = self._pick_time_in_window(
                        cursor_date, rule, tz, schedule.randomize_within_window
                    )
                    if candidate.astimezone(ZoneInfo("UTC")) > after:
                        slots.append(candidate.astimezone(ZoneInfo("UTC")))
                        if len(slots) >= count:
                            break
            cursor_date = cursor_date + timedelta(days=1)

        return self._enforce_min_interval(sorted(slots), schedule.min_interval_minutes)[:count]

    def _pick_time_in_window(
        self, day: date, rule: ScheduleRule, tz: ZoneInfo, randomize: bool
    ) -> datetime:
        start_h, start_m = (int(x) for x in rule.window_start.split(":"))
        end_h, end_m = (int(x) for x in rule.window_end.split(":"))
        start_dt = datetime.combine(day, time(start_h, start_m), tzinfo=tz)
        end_dt = datetime.combine(day, time(end_h, end_m), tzinfo=tz)
        if not randomize:
            return start_dt
        delta_seconds = max(0, int((end_dt - start_dt).total_seconds()))
        offset = random.randint(0, delta_seconds) if delta_seconds > 0 else 0
        return start_dt + timedelta(seconds=offset)

    def _enforce_min_interval(self, slots: list[datetime], min_interval_minutes: int) -> list[datetime]:
        if not slots:
            return slots
        result = [slots[0]]
        for slot in slots[1:]:
            if (slot - result[-1]) >= timedelta(minutes=min_interval_minutes):
                result.append(slot)
        return result
