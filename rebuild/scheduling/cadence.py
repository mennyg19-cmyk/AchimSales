"""When a schedule should fire, reasoned in the business timezone."""

# === What's in this file ===
# A schedule stores its cadence as a small dict. This module is the only code
# that reads that dict: it cleans it up on save (normalize), turns it into a
# human label for the list (describe), and answers the poller's one question --
# "is this due right now and hasn't it already run today?" (due_now).
#
# All wall-clock thinking is in US/Eastern (where the business is), so an "08:00"
# schedule fires at 8am Eastern no matter what the server's clock is set to. A
# schedule fires at most once per Eastern calendar day: once it has run today it
# won't fire again until the next day its cadence matches.
#
# Cadence shape (stored as JSON):
#   {"freq": "daily"|"weekly"|"monthly", "time": "HH:MM",
#    "weekdays": [0..6],   # Mon=0 .. Sun=6, weekly only
#    "monthday": 1..28|-1}  # monthly only; -1 means the last day of the month
#
# normalize() -- clean a raw cadence into its stored form (raises ValueError)
# describe() -- a plain-English label, e.g. "Weekly (Mon, Wed) at 08:00"
# due_now() -- True if a schedule with this cadence should fire now
# eastern_today_iso() -- today's date in US/Eastern as YYYY-MM-DD

from __future__ import annotations

import calendar
from datetime import datetime, time, timezone

try:
    from zoneinfo import ZoneInfo

    _EASTERN = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover - fall back to UTC if tzdata is unavailable
    _EASTERN = timezone.utc

VALID_FREQ = ("daily", "weekly", "monthly")
_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def normalize(cadence: dict | None) -> dict:
    """Coerce a raw cadence into a clean, stored form. Raises ValueError if it
    can't be made valid (e.g. a weekly schedule with no weekday picked)."""
    raw_cadence = cadence or {}
    freq = str(raw_cadence.get("freq", "")).strip().lower()
    if freq not in VALID_FREQ:
        raise ValueError(f"Pick how often to send: {', '.join(VALID_FREQ)}.")
    hh, mm = _parse_time(raw_cadence.get("time", "08:00"))
    clean: dict = {"freq": freq, "time": f"{hh:02d}:{mm:02d}"}
    if freq == "weekly":
        days = sorted({int(d) for d in (raw_cadence.get("weekdays") or []) if 0 <= int(d) <= 6})
        if not days:
            raise ValueError("Pick at least one day of the week for a weekly schedule.")
        clean["weekdays"] = days
    elif freq == "monthly":
        day = int(raw_cadence.get("monthday", 1))
        clean["monthday"] = -1 if day == -1 else max(1, min(28, day))
    return clean


def describe(cadence: dict | None) -> str:
    raw = cadence or {}
    freq = raw.get("freq")
    at = raw.get("time", "")
    if freq == "daily":
        return f"Daily at {at}"
    if freq == "weekly":
        days = ", ".join(_WEEKDAY_NAMES[d] for d in raw.get("weekdays", []) if 0 <= d <= 6)
        return f"Weekly ({days}) at {at}"
    if freq == "monthly":
        monthday = raw.get("monthday", 1)
        which = "last day" if monthday == -1 else f"day {monthday}"
        return f"Monthly on {which} at {at}"
    return "Not scheduled"


def due_now(cadence: dict | None, last_run_iso: str | None, now_utc: datetime | None = None) -> bool:
    """True if a schedule with this cadence should fire now and hasn't today."""
    raw = cadence or {}
    if raw.get("freq") not in VALID_FREQ:
        return False
    now = _eastern(now_utc)
    hh, mm = _parse_time(raw.get("time", "08:00"))
    if now.time() < time(hh, mm):
        return False  # the scheduled minute hasn't arrived yet today
    if not _day_matches(raw, now):
        return False
    return not _ran_today(last_run_iso, now)


def eastern_today_iso(now_utc: datetime | None = None) -> str:
    return _eastern(now_utc).date().isoformat()


# -- internals --------------------------------------------------------------

def _eastern(now_utc: datetime | None) -> datetime:
    return (now_utc or datetime.now(timezone.utc)).astimezone(_EASTERN)


def _parse_time(raw) -> tuple[int, int]:
    try:
        hh, mm = str(raw).split(":", 1)
        return max(0, min(23, int(hh))), max(0, min(59, int(mm)))
    except (TypeError, ValueError):
        return 8, 0


def _day_matches(cadence: dict, now_eastern: datetime) -> bool:
    freq = cadence.get("freq")
    if freq == "daily":
        return True
    if freq == "weekly":
        return now_eastern.weekday() in (cadence.get("weekdays") or [])
    if freq == "monthly":
        monthday = int(cadence.get("monthday", 1))
        if monthday == -1:
            last = calendar.monthrange(now_eastern.year, now_eastern.month)[1]
            return now_eastern.day == last
        return now_eastern.day == max(1, min(28, monthday))
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
