"""
Tests for core.dates — period parsing, fetch plan resolution, and edge cases.

Every test freezes "today" to a specific date so results are deterministic
regardless of when the suite runs.
"""

from datetime import date

import pytest

from core.dates import (
    D365_GO_LIVE,
    FetchPlan,
    PeriodSpec,
    clamp_start,
    parse_custom_range,
    parse_period,
    resolve_fetch_plan,
)
from tests.helpers.date_helpers import freeze_today


class TestParsePeriod:
    """Named period → PeriodSpec conversion."""

    def test_daily_period_normal(self):
        with freeze_today(date(2025, 3, 15)):
            spec = parse_period("daily")
        assert spec.start_date == date(2025, 3, 14)
        assert spec.end_date == date(2025, 3, 14)
        assert spec.subfolder == "Daily"

    def test_yesterday_alias(self):
        with freeze_today(date(2025, 3, 15)):
            spec = parse_period("yesterday")
        assert spec.start_date == date(2025, 3, 14)
        assert spec.end_date == date(2025, 3, 14)

    def test_mtd_start_of_month(self):
        with freeze_today(date(2025, 7, 1)):
            spec = parse_period("mtd")
        assert spec.start_date == date(2025, 7, 1)
        assert spec.end_date == date(2025, 7, 1)
        assert spec.subfolder == "MTD"

    def test_mtd_end_of_month(self):
        with freeze_today(date(2025, 7, 31)):
            spec = parse_period("mtd")
        assert spec.start_date == date(2025, 7, 1)
        assert spec.end_date == date(2025, 7, 31)

    def test_ytd_jan_1(self):
        with freeze_today(date(2025, 1, 1)):
            spec = parse_period("ytd")
        assert spec.start_date == date(2025, 1, 3)  # clamped to D365_GO_LIVE
        assert spec.end_date == date(2025, 1, 1)

    def test_ytd_normal(self):
        with freeze_today(date(2026, 6, 15)):
            spec = parse_period("ytd")
        assert spec.start_date == date(2026, 1, 1)
        assert spec.end_date == date(2026, 6, 15)

    def test_last_7_days(self):
        with freeze_today(date(2025, 3, 10)):
            spec = parse_period("last_7_days")
        assert spec.start_date == date(2025, 3, 4)
        assert spec.end_date == date(2025, 3, 10)
        assert spec.subfolder == "This Week"

    def test_this_week_monday(self):
        # 2025-03-10 is a Monday
        with freeze_today(date(2025, 3, 10)):
            spec = parse_period("this_week")
        assert spec.start_date == date(2025, 3, 10)
        assert spec.end_date == date(2025, 3, 10)

    def test_this_week_friday(self):
        # 2025-03-14 is a Friday; Monday = 2025-03-10
        with freeze_today(date(2025, 3, 14)):
            spec = parse_period("this_week")
        assert spec.start_date == date(2025, 3, 10)
        assert spec.end_date == date(2025, 3, 14)

    def test_all_time(self):
        with freeze_today(date(2026, 6, 15)):
            spec = parse_period("all_time")
        assert spec.start_date == D365_GO_LIVE
        assert spec.end_date == date(2026, 6, 15)

    def test_clamp_to_go_live(self):
        """YTD in Jan 2025 should clamp start to D365_GO_LIVE (Jan 3)."""
        with freeze_today(date(2025, 1, 5)):
            spec = parse_period("ytd")
        assert spec.start_date == D365_GO_LIVE
        assert spec.end_date == date(2025, 1, 5)

    def test_leap_year_feb_29(self):
        with freeze_today(date(2028, 2, 29)):
            spec = parse_period("mtd")
        assert spec.start_date == date(2028, 2, 1)
        assert spec.end_date == date(2028, 2, 29)

    def test_year_boundary(self):
        """On Jan 1 2026: YTD = single day, daily = Dec 31 2025."""
        with freeze_today(date(2026, 1, 1)):
            ytd = parse_period("ytd")
            daily = parse_period("daily")
        assert ytd.start_date == date(2026, 1, 1)
        assert ytd.end_date == date(2026, 1, 1)
        assert daily.start_date == date(2025, 12, 31)
        assert daily.end_date == date(2025, 12, 31)

    def test_unknown_period_raises(self):
        with pytest.raises(ValueError, match="Unknown period"):
            parse_period("quarterly")


class TestResolveFetchPlan:
    """FetchPlan resolution from CLI-style arguments."""

    def test_default_all_periods(self):
        with freeze_today(date(2026, 3, 15)):
            plan = resolve_fetch_plan()
        assert len(plan.periods) == 4
        labels = {p.label for p in plan.periods}
        assert "MTD" in labels
        assert "YTD" in labels

    def test_single_period(self):
        with freeze_today(date(2026, 3, 15)):
            plan = resolve_fetch_plan(periods=["mtd"])
        assert len(plan.periods) == 1
        assert plan.periods[0].label == "MTD"
        assert plan.fetch_start == date(2026, 3, 1)
        assert plan.fetch_end == date(2026, 3, 15)

    def test_custom_range(self):
        plan = resolve_fetch_plan(from_date="2026-01-10", to_date="2026-01-20")
        assert len(plan.periods) == 1
        assert plan.fetch_start == date(2026, 1, 10)
        assert plan.fetch_end == date(2026, 1, 20)

    def test_custom_range_swapped(self):
        plan = resolve_fetch_plan(from_date="2026-03-20", to_date="2026-03-10")
        assert plan.fetch_start == date(2026, 3, 10)
        assert plan.fetch_end == date(2026, 3, 20)

    def test_single_date(self):
        plan = resolve_fetch_plan(single_date="2026-02-14")
        assert len(plan.periods) == 1
        assert plan.fetch_start == date(2026, 2, 14)
        assert plan.fetch_end == date(2026, 2, 14)

    def test_fetch_range_covers_all_periods(self):
        with freeze_today(date(2026, 6, 15)):
            plan = resolve_fetch_plan()
        assert plan.fetch_start == date(2026, 1, 1)  # YTD start
        assert plan.fetch_end == date(2026, 6, 15)


class TestClampStart:

    def test_before_go_live(self):
        assert clamp_start(date(2024, 12, 1)) == D365_GO_LIVE

    def test_after_go_live(self):
        d = date(2025, 6, 1)
        assert clamp_start(d) == d

    def test_exact_go_live(self):
        assert clamp_start(D365_GO_LIVE) == D365_GO_LIVE


class TestParseCustomRange:

    def test_normal_range(self):
        spec = parse_custom_range("2026-02-01", "2026-02-28")
        assert spec.start_date == date(2026, 2, 1)
        assert spec.end_date == date(2026, 2, 28)
        assert spec.subfolder == "Custom"

    def test_subfolder_override(self):
        spec = parse_custom_range("2026-02-01", "2026-02-28", subfolder_override="Daily")
        assert spec.subfolder == "Daily"

    def test_before_go_live_clamped(self):
        spec = parse_custom_range("2024-01-01", "2025-02-01")
        assert spec.start_date == D365_GO_LIVE
