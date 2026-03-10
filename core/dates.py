"""
Date and time utilities. All dates normalized to US Eastern time.

Provides:
- get_now_eastern() / get_today_eastern() -- single source of truth for "now"
- parse_period() -- resolve named periods (daily, mtd, ytd, this_week) to date ranges
- resolve_fetch_plan() -- determine widest fetch range and per-period report specs
- UTC-to-Eastern conversion for D365 datetime fields
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

log = logging.getLogger(__name__)

EASTERN = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

ALL_PERIODS = ("daily", "mtd", "ytd", "last_7_days")


def get_now_eastern() -> datetime:
    """Current datetime in US Eastern."""
    return datetime.now(tz=EASTERN)


def get_today_eastern() -> date:
    """Current date in US Eastern."""
    return get_now_eastern().date()


def utc_to_eastern(dt: datetime) -> datetime:
    """Convert a UTC datetime to US Eastern. Naive datetimes are assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(EASTERN)


def convert_d365_dates_to_eastern(series: pd.Series) -> pd.Series:
    """Convert a pandas Series of D365 UTC datetimes to naive US Eastern datetimes.

    D365 OData returns ISO 8601 UTC strings. This converts to Eastern and strips tz
    for Excel compatibility.
    """
    dt = pd.to_datetime(series, errors="coerce", utc=True)
    eastern = dt.dt.tz_convert(EASTERN).dt.tz_localize(None)
    return eastern


def get_yesterday(today: date | None = None) -> date:
    today = today or get_today_eastern()
    return today - timedelta(days=1)


def get_week_start(today: date | None = None) -> date:
    """Monday of the current week."""
    today = today or get_today_eastern()
    return today - timedelta(days=today.weekday())


def get_month_start(today: date | None = None) -> date:
    today = today or get_today_eastern()
    return today.replace(day=1)


def get_year_start(today: date | None = None) -> date:
    today = today or get_today_eastern()
    return today.replace(month=1, day=1)


@dataclass
class PeriodSpec:
    """A single report period specification."""
    label: str
    start_date: date
    end_date: date
    subfolder: str
    filename_tag: str
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None


@dataclass
class FetchPlan:
    """Describes what to fetch from D365 and what reports to build from it."""
    fetch_start: date
    fetch_end: date
    periods: list[PeriodSpec] = field(default_factory=list)


def parse_period(period: str, today: date | None = None) -> PeriodSpec:
    """Resolve a named period to a PeriodSpec."""
    today = today or get_today_eastern()
    yesterday = get_yesterday(today)

    if period in ("daily", "yesterday"):
        return PeriodSpec(
            label=yesterday.isoformat(),
            start_date=yesterday,
            end_date=yesterday,
            subfolder="Daily",
            filename_tag=yesterday.isoformat(),
        )
    elif period == "mtd":
        return PeriodSpec(
            label="MTD",
            start_date=get_month_start(today),
            end_date=today,
            subfolder="MTD",
            filename_tag=f"MTD_{today.isoformat()}",
        )
    elif period == "ytd":
        return PeriodSpec(
            label="YTD",
            start_date=get_year_start(today),
            end_date=today,
            subfolder="YTD",
            filename_tag=f"YTD_{today.isoformat()}",
        )
    elif period == "this_week":
        week_start = get_week_start(today)
        return PeriodSpec(
            label="This Week",
            start_date=week_start,
            end_date=today,
            subfolder="This Week",
            filename_tag=f"Week_{week_start.isoformat()}_to_{today.isoformat()}",
        )
    elif period == "last_7_days":
        start_7 = today - timedelta(days=6)
        return PeriodSpec(
            label="Last 7 Days",
            start_date=start_7,
            end_date=today,
            subfolder="This Week",
            filename_tag=f"Week_{start_7.isoformat()}_to_{today.isoformat()}",
        )
    else:
        raise ValueError(f"Unknown period: {period}. Use: daily, yesterday, mtd, ytd, this_week, last_7_days")


def parse_custom_range(from_date: str, to_date: str) -> PeriodSpec:
    """Parse a custom date range from strings."""
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)
    if start > end:
        start, end = end, start
    return PeriodSpec(
        label=f"{start.isoformat()} to {end.isoformat()}",
        start_date=start,
        end_date=end,
        subfolder="Custom",
        filename_tag=f"{start.isoformat()}_to_{end.isoformat()}",
    )


def resolve_fetch_plan(
    periods: list[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    single_date: str | None = None,
    today: date | None = None,
) -> FetchPlan:
    """Determine the optimal fetch range and list of reports to build.

    No args (periods=None, no dates) -> all standard periods, single YTD fetch.
    Single period -> narrow fetch for just that period.
    Custom range -> fetch exactly that range.
    """
    today = today or get_today_eastern()

    if from_date and to_date:
        spec = parse_custom_range(from_date, to_date)
        return FetchPlan(fetch_start=spec.start_date, fetch_end=spec.end_date, periods=[spec])

    if single_date:
        d = date.fromisoformat(single_date)
        spec = PeriodSpec(
            label=d.isoformat(),
            start_date=d,
            end_date=d,
            subfolder="Daily",
            filename_tag=d.isoformat(),
        )
        return FetchPlan(fetch_start=d, fetch_end=d, periods=[spec])

    if periods is None:
        periods = list(ALL_PERIODS)

    specs = [parse_period(p, today) for p in periods]

    fetch_start = min(s.start_date for s in specs)
    fetch_end = max(s.end_date for s in specs)

    return FetchPlan(fetch_start=fetch_start, fetch_end=fetch_end, periods=specs)
