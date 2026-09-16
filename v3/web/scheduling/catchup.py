"""When a Shabbos skip is owed, when to fire it and which dates to cover.

Clock runs never send at havdalah. Skip-class periods wait for the next regular
slot at the same HH:MM. Reschedule-class periods (the next regular slot would
drop data) fire at the next weekday Mon–Fri at that same HH:MM.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

from report_engine.dates import clamp_start, parse_period
from web.scheduling import cadence as C

ALL_TIME_REPORTS = frozenset({"customer_activity", "salesman"})
_RESCHEDULE_PERIODS = frozenset({
    "last_7_days", "this_week", "week", "last_month", "month",
})
# Friday and Saturday cannot self-heal an evening schedule skipped for Shabbos.
_NO_SELF_HEAL_WEEKDAYS = frozenset({4, 5})


def period_of(params: dict | None) -> str:
    return str((params or {}).get("period") or "").strip().lower()


def classify_action(params: dict | None, report_key: str,
                    skipped: date, cadence: dict | None) -> str:
    """``skip`` (next regular slot) or ``reschedule`` (next weekday, same clock)."""
    if (report_key or "") in ALL_TIME_REPORTS:
        return "reschedule"
    p = period_of(params)
    if p in _RESCHEDULE_PERIODS:
        return "reschedule"
    if p == "mtd":
        last = calendar.monthrange(skipped.year, skipped.month)[1]
        month_end = skipped.replace(day=last)
        if not _self_heal_before(cadence, skipped, month_end):
            return "reschedule"
        return "skip"
    if p == "ytd":
        year_end = date(skipped.year, 12, 31)
        if not _self_heal_before(cadence, skipped, year_end):
            return "reschedule"
        return "skip"
    return "skip"


def makeup_due(cadence: dict | None, last_run_iso: str | None, now_utc: datetime,
               *, action: str, assur: bool) -> bool:
    """Reschedule-class owed send: weekday, same HH:MM, restriction over."""
    if assur or action != "reschedule":
        return False
    now = now_utc.astimezone(C.EASTERN) if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc).astimezone(C.EASTERN)
    if now.weekday() >= 5:
        return False
    return C.clock_ready(cadence, last_run_iso, now_utc)


def overlay_windows(params: dict | None, report_key: str, *, skipped: date,
                    today: date, last_success: date | None) -> list[dict]:
    """One or more params dicts covering the skipped slot (and month-end if needed)."""
    params = dict(params or {})
    if (report_key or "") in ALL_TIME_REPORTS:
        return [params]
    p = period_of(params)
    if p in ("all_time", ""):
        return [params]
    if p in ("daily", "yesterday"):
        start = last_success if last_success else skipped
        end = today - timedelta(days=1)
        if start > end:
            return [params]
        return [_with_custom(params, start, end)]
    if p == "mtd":
        month_start = skipped.replace(day=1)
        last = calendar.monthrange(skipped.year, skipped.month)[1]
        month_end = skipped.replace(day=last)
        if today.month == skipped.month and today.year == skipped.year:
            return [params]
        windows = [_with_custom(params, month_start, skipped)]
        if skipped < month_end:
            windows.append(_with_custom(params, month_start, month_end))
        return windows
    if p == "ytd":
        if today.year == skipped.year:
            return [params]
        return [_with_custom(params, date(skipped.year, 1, 1), date(skipped.year, 12, 31))]
    if p in ("last_7_days", "week"):
        gap = (today - last_success).days if last_success else (today - skipped).days + 1
        extra = max(0, gap - 1)
        start = clamp_start(today - timedelta(days=6 + extra))
        return [_with_custom(params, start, today)]
    if p == "this_week":
        week = parse_period("this_week", today=skipped)
        end = today if today > skipped else max(week.end_date, skipped)
        return [_with_custom(params, week.start_date, end)]
    if p in ("last_month", "month"):
        owed = parse_period("last_month", today=skipped)
        now_window = parse_period("last_month", today=today)
        if (owed.start_date, owed.end_date) == (now_window.start_date, now_window.end_date):
            return [params]
        return [_with_custom(params, owed.start_date, owed.end_date)]
    return [params]


def run_param_windows(params: dict | None, report_key: str, *,
                      skipped_iso: str | None, today: date,
                      last_success: date | None,
                      include_regular: bool) -> list[dict]:
    params = dict(params or {})
    windows: list[dict] = []
    skipped = _as_date(skipped_iso)
    if skipped is not None:
        windows.extend(overlay_windows(
            params, report_key, skipped=skipped, today=today, last_success=last_success,
        ))
    if include_regular or not windows:
        windows.append(params)
    return _dedupe(windows)


def eastern_date_of(iso: str | None) -> date | None:
    return _as_date(iso)


def _self_heal_before(cadence: dict | None, skipped: date, until: date) -> bool:
    """True if a later matching day before `until` is Sun–Thu (can run in-window)."""
    day = skipped + timedelta(days=1)
    while day <= until:
        if C.day_matches_date(cadence, day) and day.weekday() not in _NO_SELF_HEAL_WEEKDAYS:
            return True
        day += timedelta(days=1)
    return False


def _with_custom(params: dict, start: date, end: date) -> dict:
    out = dict(params)
    out["period"] = "custom"
    out["start_date"] = clamp_start(start).isoformat()
    out["end_date"] = end.isoformat()
    return out


def _dedupe(windows: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for window in windows:
        key = (window.get("period"), window.get("start_date"), window.get("end_date"))
        if key in seen:
            continue
        seen.add(key)
        out.append(window)
    return out


def _as_date(iso: str | None) -> date | None:
    if not iso:
        return None
    try:
        raw = iso.strip()
        if "T" in raw:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(C.EASTERN).date()
        return date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return None
