"""compute_next_run: the scheduler's pure scheduling math."""
from datetime import datetime, timezone

from app.models.schedule import ScheduleType
from app.services.scheduler import compute_next_run

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)  # a Thursday


def test_once_never_reschedules():
    assert compute_next_run(ScheduleType.once, now=NOW) is None


def test_interval():
    nxt = compute_next_run(ScheduleType.interval, now=NOW, interval_minutes=90)
    assert (nxt - NOW).total_seconds() == 90 * 60


def test_interval_minimum_clamped():
    nxt = compute_next_run(ScheduleType.interval, now=NOW, interval_minutes=0)
    assert nxt > NOW


def test_daily_later_today():
    nxt = compute_next_run(ScheduleType.daily, now=NOW, run_at_time="15:30")
    assert nxt.date() == NOW.date()
    assert (nxt.hour, nxt.minute) == (15, 30)


def test_daily_already_passed_goes_tomorrow():
    nxt = compute_next_run(ScheduleType.daily, now=NOW, run_at_time="09:00")
    assert (nxt - NOW).days == 0 and nxt.day == NOW.day + 1


def test_weekly_same_day_future_time():
    # Thursday = weekday 3
    nxt = compute_next_run(ScheduleType.weekly, now=NOW, run_at_time="18:00", weekday=3)
    assert nxt.weekday() == 3 and nxt.date() == NOW.date()


def test_weekly_same_day_past_time_next_week():
    nxt = compute_next_run(ScheduleType.weekly, now=NOW, run_at_time="08:00", weekday=3)
    assert nxt.weekday() == 3
    assert (nxt - NOW).days >= 6


def test_weekly_other_day():
    nxt = compute_next_run(ScheduleType.weekly, now=NOW, run_at_time="10:00", weekday=0)
    assert nxt.weekday() == 0
    assert nxt > NOW


def test_invalid_time_string_falls_back():
    nxt = compute_next_run(ScheduleType.daily, now=NOW, run_at_time="banana")
    assert nxt is not None
