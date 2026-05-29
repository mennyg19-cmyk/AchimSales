"""Date / period logic - pure stdlib, US-Eastern, self-contained.

Re-implemented for v3 (no pandas, no legacy `core/` coupling). Matches the
business meaning of the live/test apps' periods so report windows line up:

    daily/yesterday | mtd | last_month | ytd | this_week | last_7_days
    | all_time | custom

The on-prem Reporting API's stored procedures take SQL Server `datetime`
params with NO timezone offset - they interpret the value as already-Eastern.
So `sp_datetime()` emits Eastern wall-clock 'YYYY-MM-DD HH:MM:SS'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

# Earliest valid date in D365 F&O; anything before is migration noise.
D365_GO_LIVE = date(2025, 1, 3)


def now_eastern() -> datetime:
    return datetime.now(tz=EASTERN)


def today_eastern() -> date:
    return now_eastern().date()


def clamp_start(start: date) -> date:
    """Never let a window start before D365 go-live."""
    return max(start, D365_GO_LIVE)


@dataclass(frozen=True)
class Period:
    """A resolved reporting window (inclusive dates)."""
    label: str
    start_date: date
    end_date: date


def parse_period(period: str, today: date | None = None) -> Period:
    """Resolve a named period to an inclusive date window (start clamped to go-live)."""
    today = today or today_eastern()
    name = (period or "").strip().lower()

    if name in ("daily", "yesterday"):
        y = today - timedelta(days=1)
        p = Period(y.isoformat(), y, y)
    elif name == "mtd":
        p = Period("MTD", today.replace(day=1), today)
    elif name == "last_month":
        first_this = today.replace(day=1)
        last_prior = first_this - timedelta(days=1)
        p = Period(
            f"Last Month ({last_prior.strftime('%b %Y')})",
            last_prior.replace(day=1),
            last_prior,
        )
    elif name == "ytd":
        p = Period("YTD", today.replace(month=1, day=1), today)
    elif name == "this_week":
        monday = today - timedelta(days=today.weekday())
        p = Period("This Week", monday, today)
    elif name == "last_7_days":
        p = Period("Last 7 Days", today - timedelta(days=6), today)
    elif name == "all_time":
        p = Period("All Time", D365_GO_LIVE, today)
    else:
        raise ValueError(
            f"Unknown period: {period!r}. Use daily, mtd, last_month, ytd, "
            "this_week, last_7_days, all_time."
        )

    return Period(p.label, clamp_start(p.start_date), p.end_date)


def parse_custom_range(start_raw: str, end_raw: str) -> Period:
    """Parse an explicit YYYY-MM-DD..YYYY-MM-DD range (clamped; reversed swaps)."""
    start = date.fromisoformat(start_raw[:10])
    end = date.fromisoformat(end_raw[:10])
    if start > end:
        start, end = end, start
    start = clamp_start(start)
    return Period(f"{start.isoformat()} to {end.isoformat()}", start, end)


def sp_datetime(d: date, *, end_of_day: bool = False) -> str:
    """Format a date as Eastern wall-clock 'YYYY-MM-DD HH:MM:SS' for an SP param.

    `end_of_day=False` -> 00:00:00 (window start); True -> 23:59:59 (window end).
    """
    t = time(23, 59, 59) if end_of_day else time(0, 0, 0)
    return datetime.combine(d, t).strftime("%Y-%m-%d %H:%M:%S")
