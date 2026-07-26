"""RRULE translation and timezone handling for reminders."""
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from saathi.agent.tools.handlers import to_rrule, next_fire

IST = "Asia/Kolkata"


def test_daily():
    assert to_rrule("daily", "08:00") == "FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0"


def test_weekly():
    assert "BYDAY=MO" in to_rrule("weekly:mon", "22:30")


def test_monthly():
    assert "BYMONTHDAY=14" in to_rrule("monthly:14", "09:15")


def test_once_has_no_rrule():
    assert to_rrule("once", "07:00") is None


def test_unsupported_recurrence_raises():
    with pytest.raises(ValueError):
        to_rrule("fortnightly", "07:00")


def test_next_fire_is_utc_but_local_wallclock():
    # 08:00 IST must land at 02:30 UTC, whatever the server timezone is.
    after = datetime(2026, 7, 26, 6, 0, tzinfo=ZoneInfo(IST))
    got = next_fire("FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0", IST, after=after)
    assert got.tzinfo is not None
    assert (got.hour, got.minute) == (2, 30), got
    assert got.astimezone(ZoneInfo(IST)).hour == 8


def test_next_fire_rolls_to_tomorrow_when_time_has_passed():
    after = datetime(2026, 7, 26, 9, 0, tzinfo=ZoneInfo(IST))   # already past 08:00
    got = next_fire("FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0", IST, after=after)
    assert got.astimezone(ZoneInfo(IST)).day == 27


def test_one_off_needs_date():
    with pytest.raises(ValueError):
        next_fire(None, IST)
