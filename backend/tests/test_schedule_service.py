from datetime import UTC, datetime

from app.models.scheduling import Schedule, ScheduleRule
from app.services.scheduling.service import ScheduleService


def test_next_slot_respects_window_and_timezone():
    schedule = Schedule(
        workspace_id=None, name="Daily", timezone="Europe/Moscow", posts_per_day=1,
        days_of_week_json="[0,1,2,3,4,5,6]", min_interval_minutes=60,
        randomize_within_window=False,
    )
    rule = ScheduleRule(schedule_id=None, window_start="11:00", window_end="13:00")

    service = ScheduleService()
    after = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    slots = service.next_slot(schedule, [rule], after=after, count=1)

    assert len(slots) == 1
    slot = slots[0]
    assert slot.tzinfo is not None
    # 11:00 Europe/Moscow (UTC+3) == 08:00 UTC
    assert slot.hour == 8
    assert slot.minute == 0


def test_next_slot_skips_excluded_days():
    schedule = Schedule(
        workspace_id=None, name="Weekdays only", timezone="UTC", posts_per_day=1,
        days_of_week_json="[0,1,2,3,4]", min_interval_minutes=60,
        randomize_within_window=False,
    )
    rule = ScheduleRule(schedule_id=None, window_start="10:00", window_end="10:00")

    service = ScheduleService()
    # 2026-01-03 is a Saturday (weekday 5) -> should be skipped
    after = datetime(2026, 1, 3, 0, 0, tzinfo=UTC)
    slots = service.next_slot(schedule, [rule], after=after, count=1)

    assert len(slots) == 1
    assert slots[0].weekday() in {0, 1, 2, 3, 4}


def test_min_interval_enforced_across_multiple_windows():
    schedule = Schedule(
        workspace_id=None, name="Three windows", timezone="UTC", posts_per_day=3,
        days_of_week_json="[0,1,2,3,4,5,6]", min_interval_minutes=120,
        randomize_within_window=False,
    )
    rules = [
        ScheduleRule(schedule_id=None, window_start="09:00", window_end="09:00"),
        ScheduleRule(schedule_id=None, window_start="09:30", window_end="09:30"),
        ScheduleRule(schedule_id=None, window_start="14:00", window_end="14:00"),
    ]
    service = ScheduleService()
    after = datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    slots = service.next_slot(schedule, rules, after=after, count=3)

    for earlier, later in zip(slots, slots[1:]):
        assert (later - earlier).total_seconds() >= 120 * 60
