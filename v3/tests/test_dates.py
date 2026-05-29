"""report_engine.dates: period windows + SP datetime formatting."""

from datetime import date

import pytest

from report_engine.dates import (
    D365_GO_LIVE,
    parse_custom_range,
    parse_period,
    sp_datetime,
)

_TODAY = date(2026, 4, 15)  # a Wednesday


def test_daily_is_yesterday():
    p = parse_period("daily", today=_TODAY)
    assert p.start_date == date(2026, 4, 14)
    assert p.end_date == date(2026, 4, 14)


def test_mtd_starts_first_of_month():
    p = parse_period("mtd", today=_TODAY)
    assert p.start_date == date(2026, 4, 1)
    assert p.end_date == _TODAY


def test_last_month_is_full_prior_calendar_month():
    p = parse_period("last_month", today=date(2026, 5, 3))
    assert p.start_date == date(2026, 4, 1)
    assert p.end_date == date(2026, 4, 30)


def test_ytd_starts_jan_1():
    p = parse_period("ytd", today=_TODAY)
    assert p.start_date == date(2026, 1, 1)
    assert p.end_date == _TODAY


def test_this_week_starts_monday():
    p = parse_period("this_week", today=_TODAY)
    assert p.start_date == date(2026, 4, 13)  # Monday
    assert p.end_date == _TODAY


def test_last_7_days_is_six_days_back_inclusive():
    p = parse_period("last_7_days", today=_TODAY)
    assert p.start_date == date(2026, 4, 9)
    assert p.end_date == _TODAY


def test_all_time_starts_go_live():
    p = parse_period("all_time", today=_TODAY)
    assert p.start_date == D365_GO_LIVE
    assert p.end_date == _TODAY


def test_start_is_clamped_to_go_live():
    # A YTD in early 2025 would start Jan 1 2025, before go-live Jan 3.
    p = parse_period("ytd", today=date(2025, 1, 10))
    assert p.start_date == D365_GO_LIVE


def test_unknown_period_raises():
    with pytest.raises(ValueError, match="Unknown period"):
        parse_period("bogus", today=_TODAY)


def test_custom_range_reversed_is_swapped_and_clamped():
    p = parse_custom_range("2026-03-10", "2026-02-01")
    assert p.start_date == date(2026, 2, 1)
    assert p.end_date == date(2026, 3, 10)


def test_sp_datetime_start_and_end_of_day():
    assert sp_datetime(date(2026, 4, 1)) == "2026-04-01 00:00:00"
    assert sp_datetime(date(2026, 4, 1), end_of_day=True) == "2026-04-01 23:59:59"
