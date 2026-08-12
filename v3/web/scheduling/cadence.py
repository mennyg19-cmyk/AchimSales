"""Cadence helpers: validate the JSON cadence and decide if a schedule is due.

Cadence shape (stored as JSON in the schedule's ``cadence`` column):
    {"freq": "daily"|"weekly"|"monthly", "time": "HH:MM",
     "weekdays": [0..6],          # Mon=0, only for weekly
     "monthdays": [1..28 | -1],   # monthly; -1 = last day of month
     "monthday": 1..28 | -1}      # legacy single day (still accepted on write)

All wall-clock reasoning is in US/Eastern (the business timezone) so an "8:00"
schedule fires at 8am Eastern regardless of the container's UTC clock. A schedule
fires at most once per calendar day: once it has run today (Eastern) it won't be
re-enqueued until the next eligible day.
"""

from __future__ import annotations

import calendar
from datetime import datetime, time, timezone

try:  # zoneinfo is stdlib on 3.9+, but guard so imports never explode
    from zoneinfo import ZoneInfo

    _EASTERN = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - fallback to UTC if tzdata missing
    _EASTERN = timezone.utc

VALID_FREQ = ("daily", "weekly", "monthly")


def normalize(cadence: dict | None) -> dict:
    """Coerce a raw cadence dict into a clean, stored form. Raises ValueError."""
    c = cadence or {}
    freq = str(c.get("freq", "")).strip().lower()
    if freq not in VALID_FREQ:
        raise ValueError(f"cadence.freq must be one of {VALID_FREQ}")
    hh, mm = _parse_time(c.get("time", "08:00"))
    out: dict = {"freq": freq, "time": f"{hh:02d}:{mm:02d}"}
    if freq == "weekly":
        days = sorted({int(d) for d in (c.get("weekdays") or []) if 0 <= int(d) <= 6})
        if not days:
            raise ValueError("weekly cadence needs at least one weekday")
        out["weekdays"] = days
    elif freq == "monthly":
        days = _clean_monthdays(c)
        if not days:
            raise ValueError("monthly cadence needs at least one day of the month")
        out["monthdays"] = days
        out["monthday"] = days[0]  # keep for older readers / UIs
    return out


def eastern_date_iso(now_utc: datetime | None = None) -> str:
    """The current calendar date in US/Eastern as 'YYYY-MM-DD'.

    Schedule start/end windows must compare against the SAME business timezone the
    cadence fires in, or a late-evening Eastern schedule starts/ends a day early
    around UTC midnight.
    """
    now = (now_utc or datetime.now(timezone.utc)).astimezone(_EASTERN)
    return now.date().isoformat()


def describe(cadence: dict | None) -> str:
    """Human label for the schedules list, e.g. 'Weekly (Mon, Wed) at 08:00'."""
    c = cadence or {}
    freq = c.get("freq")
    t = c.get("time", "")
    if freq == "daily":
        return f"Daily at {t}"
    if freq == "weekly":
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        days = ", ".join(names[d] for d in c.get("weekdays", []) if 0 <= d <= 6)
        return f"Weekly ({days}) at {t}"
    if freq == "monthly":
        labels = [_monthday_label(d) for d in _monthdays_from(c)]
        joined = ", ".join(labels) if labels else "day 1"
        return f"Monthly on {joined} at {t}"
    return "Not scheduled"


def due_now(cadence: dict | None, last_run_iso: str | None,
            now_utc: datetime | None = None) -> bool:
    """True if a schedule with this cadence should fire now and hasn't today."""
    c = cadence or {}
    if c.get("freq") not in VALID_FREQ:
        return False
    now = (now_utc or datetime.now(timezone.utc)).astimezone(_EASTERN)
    hh, mm = _parse_time(c.get("time", "08:00"))
    if now.time() < time(hh, mm):
        return False  # not yet the scheduled minute today
    if not _day_matches(c, now):
        return False
    return not _ran_today(last_run_iso, now)


# -- internals --------------------------------------------------------------

def _parse_time(raw) -> tuple[int, int]:
    try:
        hh, mm = str(raw).split(":", 1)
        return max(0, min(23, int(hh))), max(0, min(59, int(mm)))
    except (TypeError, ValueError):
        return 8, 0


def _clamp_monthday(day: int) -> int:
    return -1 if day == -1 else max(1, min(28, day))


def _clean_monthdays(c: dict) -> list[int]:
    raw = c.get("monthdays")
    if raw is None:
        if c.get("monthday") is not None:
            raw = [c.get("monthday")]
        else:
            raw = [1]
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]
    cleaned = {_clamp_monthday(int(d)) for d in raw}
    # numbers first, last-day (-1) at the end
    return sorted(cleaned, key=lambda d: (d < 0, d))


def _monthdays_from(c: dict) -> list[int]:
    if isinstance(c.get("monthdays"), (list, tuple)) and c["monthdays"]:
        return [_clamp_monthday(int(d)) for d in c["monthdays"]]
    if c.get("monthday") is not None:
        return [_clamp_monthday(int(c["monthday"]))]
    return [1]


def _monthday_label(day: int) -> str:
    return "last day" if day == -1 else f"day {day}"


def _day_matches(c: dict, now: datetime) -> bool:
    freq = c.get("freq")
    if freq == "daily":
        return True
    if freq == "weekly":
        return now.weekday() in (c.get("weekdays") or [])
    if freq == "monthly":
        last = calendar.monthrange(now.year, now.month)[1]
        for md in _monthdays_from(c):
            if md == -1:
                if now.day == last:
                    return True
            elif now.day == md:
                return True
        return False
    return False


def _ran_today(last_run_iso: str | None, now_eastern: datetime) -> bool:
    if not last_run_iso:
        return False
    try:
        last = datetime.fromisoformat(last_run_iso)
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last.astimezone(_EASTERN).date() == now_eastern.date()
