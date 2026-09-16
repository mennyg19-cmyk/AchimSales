"""Eastern date windows for Reporting API params. Stdlib only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
D365_GO_LIVE = date(2025, 1, 3)


def today_eastern() -> date:
    return datetime.now(tz=EASTERN).date()


def sp_datetime(day: date, *, end_of_day: bool = False) -> str:
    clock = time(23, 59, 59) if end_of_day else time(0, 0, 0)
    return datetime.combine(day, clock).strftime("%Y-%m-%d %H:%M:%S")


@dataclass(frozen=True)
class Period:
    start_date: date
    end_date: date


def resolve_period(period: str, from_date: str = "", to_date: str = "") -> Period | None:
    """Inclusive window, or None for all_time / empty (SP default)."""
    name = (period or "").strip().lower().replace(" ", "_")
    if name in {"", "all_time"}:
        return None
    today = today_eastern()
    if name == "custom":
        if not (from_date and to_date):
            return None
        start = date.fromisoformat(from_date[:10])
        end = date.fromisoformat(to_date[:10])
        if start > end:
            start, end = end, start
        return Period(max(start, D365_GO_LIVE), end)
    if name in {"daily", "yesterday"}:
        day = today - timedelta(days=1)
        start = end = day
    elif name == "mtd":
        start, end = today.replace(day=1), today
    elif name == "last_month":
        last = today.replace(day=1) - timedelta(days=1)
        start, end = last.replace(day=1), last
    elif name == "ytd":
        start, end = today.replace(month=1, day=1), today
    elif name == "this_week":
        start, end = today - timedelta(days=today.weekday()), today
    elif name == "last_7_days":
        start, end = today - timedelta(days=6), today
    else:
        return None
    return Period(max(start, D365_GO_LIVE), end)
