"""Date / period logic - pure stdlib, US-Eastern, self-contained.

Re-implemented for v3 (no pandas, no legacy `core/` coupling). Matches the
business meaning of the live/test apps' periods so report windows line up:

    daily/yesterday | mtd | last_month | ytd | this_week/wtd | last_7_days
    | all_time | custom | custom_month

The on-prem Reporting API's stored procedures take SQL Server `datetime`
params with NO timezone offset - they interpret the value as already-Eastern.
So `sp_datetime()` emits Eastern wall-clock 'YYYY-MM-DD HH:MM:SS'.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterator
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

# Earliest valid date in D365 F&O; anything before is migration noise.
D365_GO_LIVE = date(2025, 1, 3)

MONTH_OPTIONS: tuple[tuple[str, str], ...] = (
    ("1", "January"),
    ("2", "February"),
    ("3", "March"),
    ("4", "April"),
    ("5", "May"),
    ("6", "June"),
    ("7", "July"),
    ("8", "August"),
    ("9", "September"),
    ("10", "October"),
    ("11", "November"),
    ("12", "December"),
)


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
    elif name in ("this_week", "wtd"):
        monday = today - timedelta(days=today.weekday())
        p = Period("Week to Date", monday, today)
    elif name == "last_7_days":
        p = Period("Last 7 Days", today - timedelta(days=6), today)
    elif name == "all_time":
        p = Period("All Time", D365_GO_LIVE, today)
    else:
        raise ValueError(
            f"Unknown period: {period!r}. Use daily, mtd, last_month, ytd, "
            "this_week, last_7_days, all_time, custom_month."
        )

    return Period(p.label, clamp_start(p.start_date), p.end_date)


def parse_custom_month(year: int | str, month: int | str) -> Period:
    """Full calendar month (1st through last day), start clamped to go-live."""
    try:
        y = int(year)
        m = int(month)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid month/year: {year!r} {month!r}") from exc
    if m < 1 or m > 12:
        raise ValueError(f"Month must be 1-12, got {m}")
    last = monthrange(y, m)[1]
    start = date(y, m, 1)
    end = date(y, m, last)
    start = clamp_start(start)
    if start > end:
        raise ValueError("That month is before the earliest report date.")
    return Period(date(y, m, 1).strftime("%b %Y"), start, end)


def parse_custom_range(start_raw: str, end_raw: str) -> Period:
    """Parse an explicit YYYY-MM-DD..YYYY-MM-DD range (clamped; reversed swaps)."""
    start = date.fromisoformat(start_raw[:10])
    end = date.fromisoformat(end_raw[:10])
    if start > end:
        start, end = end, start
    start = clamp_start(start)
    return Period(f"{start.isoformat()} to {end.isoformat()}", start, end)


def month_chunks(start: date, end: date) -> Iterator[tuple[date, date]]:
    """Walk [start, end] one calendar month at a time, yielding (from, to) dates.

    Why this exists: a full window (e.g. a whole year of order lines, ~500k rows)
    is too big for the on-prem Reporting API to return inside its timeout, so one
    request gets nothing. Splitting the window into month-sized requests keeps each
    response small enough to come back. The chunks are contiguous and inclusive on
    both ends using the same day boundaries the daily reports already use, so
    stitching the pieces back together gives the exact same rows as one big call -
    nothing dropped, nothing double-counted.

    First chunk runs from `start` to the end of its month; middle chunks are whole
    months; the last chunk ends on `end`. A window inside a single month yields one
    chunk. Yields nothing when `end` is before `start`.
    """
    current = start
    while current <= end:
        if current.month == 12:
            month_end = date(current.year, 12, 31)
        else:
            month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
        yield (current, min(month_end, end))
        current = month_end + timedelta(days=1)


def sp_datetime(d: date, *, end_of_day: bool = False) -> str:
    """Format a date as Eastern wall-clock 'YYYY-MM-DD HH:MM:SS' for an SP param.

    `end_of_day=False` -> 00:00:00 (window start); True -> 23:59:59 (window end).
    """
    t = time(23, 59, 59) if end_of_day else time(0, 0, 0)
    return datetime.combine(d, t).strftime("%Y-%m-%d %H:%M:%S")
