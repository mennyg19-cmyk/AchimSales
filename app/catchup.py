"""Shabbos skip → makeup on the next weekday at the same clock time."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone

import cadence
from period import D365_GO_LIVE

ALL_TIME_REPORTS = frozenset({"customer_activity", "salesman"})
_RESCHEDULE_PERIODS = frozenset({"last_7_days", "this_week", "week", "last_month", "month"})
_NO_SELF_HEAL_WEEKDAYS = frozenset({4, 5})


def period_of(params: dict | None) -> str:
    return str((params or {}).get("period") or "").strip().lower()


def classify_action(params: dict | None, report_key: str, skipped: date, cad: dict | None) -> str:
    if (report_key or "") in ALL_TIME_REPORTS:
        return "reschedule"
    p = period_of(params)
    if p in _RESCHEDULE_PERIODS:
        return "reschedule"
    if p == "mtd":
        last = calendar.monthrange(skipped.year, skipped.month)[1]
        if not _self_heal_before(cad, skipped, skipped.replace(day=last)):
            return "reschedule"
        return "skip"
    if p == "ytd":
        if not _self_heal_before(cad, skipped, date(skipped.year, 12, 31)):
            return "reschedule"
        return "skip"
    return "skip"


def makeup_due(cad: dict | None, last_run_iso: str | None, now_utc: datetime, *, action: str, assur: bool) -> bool:
    if assur or action != "reschedule":
        return False
    now = now_utc.astimezone(cadence.EASTERN) if now_utc.tzinfo else now_utc.replace(tzinfo=timezone.utc).astimezone(cadence.EASTERN)
    if now.weekday() >= 5:
        return False
    return cadence.clock_ready(cad, last_run_iso, now_utc)


def overlay_params(params: dict | None, report_key: str, *, skipped: date, today: date) -> dict:
    params = dict(params or {})
    if (report_key or "") in ALL_TIME_REPORTS:
        return params
    p = period_of(params)
    if p in ("all_time", ""):
        return params
    if p in ("daily", "yesterday"):
        return _custom(params, skipped, today - timedelta(days=1))
    if p in ("last_7_days", "week"):
        start = max(today - timedelta(days=6 + max(0, (today - skipped).days)), D365_GO_LIVE)
        return _custom(params, start, today)
    if p == "this_week":
        week_start = skipped - timedelta(days=skipped.weekday())
        return _custom(params, week_start, today)
    if p in ("last_month", "month"):
        last = skipped.replace(day=1) - timedelta(days=1)
        return _custom(params, last.replace(day=1), last)
    return params


def _custom(params: dict, start: date, end: date) -> dict:
    if start > end:
        start, end = end, start
    start = max(start, D365_GO_LIVE)
    out = dict(params)
    out["period"] = "custom"
    out["from_date"] = start.isoformat()
    out["to_date"] = end.isoformat()
    out["start_date"] = start.isoformat()
    out["end_date"] = end.isoformat()
    return out


def _self_heal_before(cad: dict | None, skipped: date, until: date) -> bool:
    day = skipped + timedelta(days=1)
    while day <= until:
        if cadence.day_matches_date(cad, day) and day.weekday() not in _NO_SELF_HEAL_WEEKDAYS:
            return True
        day += timedelta(days=1)
    return False


def as_date(iso: str | None) -> date | None:
    if not iso:
        return None
    try:
        raw = iso.strip()
        if "T" in raw:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(cadence.EASTERN).date()
        return date.fromisoformat(raw[:10])
    except (TypeError, ValueError):
        return None
