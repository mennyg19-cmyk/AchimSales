"""When a schedule is due. Wall clock is US/Eastern; at most once per Eastern day."""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timezone

try:
    from zoneinfo import ZoneInfo

    _EASTERN = ZoneInfo("America/New_York")
except Exception:
    _EASTERN = timezone.utc

EASTERN = _EASTERN
VALID_FREQ = ("daily", "weekly", "monthly")
WEEKDAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def from_schedule(row: dict) -> dict:
    freq = str(row.get("freq") or "").strip().lower()
    out: dict = {"freq": freq, "time": str(row.get("run_time") or "08:00")}
    if freq == "weekly":
        names = [
            part.strip().lower()[:3]
            for part in str(row.get("weekdays") or "").split(",")
            if part.strip()
        ]
        out["weekdays"] = [WEEKDAY_NAMES.index(name) for name in names if name in WEEKDAY_NAMES]
    elif freq == "monthly":
        day = row.get("monthday")
        out["monthday"] = int(day) if day not in (None, "") else 1
    return out


def describe(row: dict | None) -> str:
    """One-line cadence for the schedules table (Daily 08:00, Weekly Mon, Wed 09:00)."""
    raw = row or {}
    freq = str(raw.get("freq") or "").strip().lower()
    run_time = str(raw.get("run_time") or raw.get("time") or "08:00")
    if freq == "weekly":
        days = [
            part.strip().lower()[:3].title()
            for part in str(raw.get("weekdays") or "").split(",")
            if part.strip()
        ]
        label = "Weekly " + (", ".join(days) if days else "").strip()
        return f"{label} {run_time}".strip()
    if freq == "monthly":
        day = raw.get("monthday")
        if day in (None, ""):
            day = 1
        return f"Monthly day {day} {run_time}"
    if freq == "daily":
        return f"Daily {run_time}"
    return f"{freq} {run_time}".strip()


def eastern_date_iso(now_utc: datetime | None = None) -> str:
    now = (now_utc or datetime.now(timezone.utc)).astimezone(_EASTERN)
    return now.date().isoformat()


def due_now(cadence: dict | None, last_run_iso: str | None, now_utc: datetime | None = None) -> bool:
    c = cadence or {}
    if c.get("freq") not in VALID_FREQ:
        return False
    now = (now_utc or datetime.now(timezone.utc)).astimezone(_EASTERN)
    hh, mm = _parse_time(c.get("time", "08:00"))
    if now.time() < time(hh, mm):
        return False
    if not _day_matches(c, now):
        return False
    return not ran_today(last_run_iso, now)


def clock_ready(cadence: dict | None, last_run_iso: str | None, now_utc: datetime | None = None) -> bool:
    """True if today's scheduled HH:MM has passed and this schedule has not run today.

    Ignores weekday/monthday so a Shabbos makeup can fire on a Monday at the
    same clock time.
    """
    c = cadence or {}
    if c.get("freq") not in VALID_FREQ:
        return False
    now = (now_utc or datetime.now(timezone.utc)).astimezone(_EASTERN)
    hh, mm = _parse_time(c.get("time", "08:00"))
    if now.time() < time(hh, mm):
        return False
    return not ran_today(last_run_iso, now)


def day_matches_date(cadence: dict | None, day: date) -> bool:
    """True if this cadence would fire on this calendar date (Eastern)."""
    noon = datetime(day.year, day.month, day.day, 12, 0, tzinfo=_EASTERN)
    return _day_matches(cadence or {}, noon)


def ran_today(last_run_iso: str | None, now_eastern: datetime | None = None) -> bool:
    if not last_run_iso:
        return False
    now = now_eastern or datetime.now(timezone.utc).astimezone(_EASTERN)
    try:
        last = datetime.fromisoformat(last_run_iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return last.astimezone(_EASTERN).date() == now.date()


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
        last = calendar.monthrange(now.year, now.month)[1]
        md = int(c.get("monthday") or 1)
        if md == -1:
            return now.day == last
        return now.day == md
    return False
