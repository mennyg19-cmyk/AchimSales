"""Cadence helpers: validate the JSON cadence and decide if a schedule is due.

Cadence shape (stored as JSON in the schedule's ``cadence`` column):
    {"freq": "daily"|"weekly"|"monthly", "time": "HH:MM",
     "weekdays": [0..6]   # Mon=0, only for weekly
     "monthday": 1..28}   # only for monthly

All wall-clock reasoning is in US/Eastern (the business timezone) so an "8:00"
schedule fires at 8am Eastern regardless of the container's UTC clock. A schedule
fires at most once per calendar day: once it has run today (Eastern) it won't be
re-enqueued until the next eligible day.
"""

from __future__ import annotations

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
        day = int(c.get("monthday", 1))
        out["monthday"] = max(1, min(28, day))  # clamp to 28 so every month has it
    return out


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
        return f"Monthly on day {c.get('monthday', 1)} at {t}"
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


def _day_matches(c: dict, now: datetime) -> bool:
    freq = c.get("freq")
    if freq == "daily":
        return True
    if freq == "weekly":
        return now.weekday() in (c.get("weekdays") or [])
    if freq == "monthly":
        return now.day == max(1, min(28, int(c.get("monthday", 1))))
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
