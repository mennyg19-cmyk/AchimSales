"""Shared validation + normalization for personal & master schedules."""

from __future__ import annotations

import json
import re
from typing import Any

from test.config.reports import REPORTS, get_report

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CADENCES = {"daily", "weekly", "monthly", "once"}
_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


class ScheduleValidationError(ValueError):
    """Raised with a user-facing message (status 400)."""


def parse_recipients(raw: str) -> list[str]:
    if not raw:
        return []
    addrs = [x.strip() for x in re.split(r"[,;]", raw) if x.strip()]
    return [a for a in addrs if _EMAIL_RE.match(a)]


def normalise_payload(body: dict, *, require_delivery: bool = True) -> dict[str, Any]:
    """Validate + normalize a schedule form payload.

    Returns a dict ready to insert/update:
        name, report_key, report_name, params_json, layouts_json,
        cadence, weekdays, monthdays, time_hhmm,
        start_date, end_date, recipients, sharepoint_path, active.

    Raises ScheduleValidationError on bad input.
    """
    name           = (body.get("name") or "").strip()
    report_key     = (body.get("report_key") or "").strip()
    cadence        = (body.get("cadence") or "").strip().lower()
    weekdays_raw   = (body.get("weekdays") or "").strip().lower()
    monthdays_raw  = (body.get("monthdays") or "").strip()
    time_hhmm      = (body.get("time_hhmm") or "").strip()
    start_date     = (body.get("start_date") or "").strip()
    end_date       = (body.get("end_date") or "").strip() or None
    recipients_raw = (body.get("recipients") or "").strip()
    sp_path        = (body.get("sharepoint_path") or "").strip() or None
    params         = body.get("params")  if isinstance(body.get("params"),  dict) else {}
    layouts        = body.get("layouts") if isinstance(body.get("layouts"), dict) else {}
    active         = body.get("active", 1)

    if not name:
        raise ScheduleValidationError("Name is required.")
    if report_key not in REPORTS:
        raise ScheduleValidationError(f"Unknown report '{report_key}'.")
    if cadence not in _CADENCES:
        raise ScheduleValidationError("Cadence must be daily, weekly, monthly, or once.")
    if not _TIME_RE.match(time_hhmm):
        raise ScheduleValidationError("Time must be HH:MM (24h).")
    if not _DATE_RE.match(start_date):
        raise ScheduleValidationError("Start date must be YYYY-MM-DD.")
    if end_date and not _DATE_RE.match(end_date):
        raise ScheduleValidationError("End date must be YYYY-MM-DD.")

    weekdays = ""
    if cadence == "weekly":
        wds = [w for w in weekdays_raw.split(",") if w]
        if not wds or any(w not in _WEEKDAYS for w in wds):
            raise ScheduleValidationError("Pick at least one weekday (mon..sun).")
        weekdays = ",".join(wds)

    monthdays = ""
    if cadence == "monthly":
        mds: list[str] = []
        for d in monthdays_raw.split(","):
            d = d.strip()
            if not d:
                continue
            try:
                di = int(d)
            except ValueError:
                raise ScheduleValidationError(f"Invalid monthday: {d}")
            if di != -1 and not (1 <= di <= 31):
                raise ScheduleValidationError(
                    f"Monthday {di} must be 1..31 or -1 for 'last day'."
                )
            mds.append(str(di))
        if not mds:
            raise ScheduleValidationError("Pick at least one day of the month.")
        monthdays = ",".join(mds)

    recipients_list = parse_recipients(recipients_raw)
    recipients_csv = ", ".join(recipients_list)

    if require_delivery and not recipients_list and not sp_path:
        raise ScheduleValidationError(
            "Pick at least one delivery target (email recipients or SharePoint folder)."
        )
    if recipients_raw and not recipients_list:
        raise ScheduleValidationError(
            "Enter at least one valid email address (or leave recipients blank)."
        )

    report = get_report(report_key)

    return {
        "name":            name,
        "report_key":      report_key,
        "report_name":     report.name,
        "params_json":     json.dumps({k: v for k, v in params.items()
                                        if v not in (None, "", [])}),
        "layouts_json":    json.dumps(layouts or {}),
        "cadence":         cadence,
        "weekdays":        weekdays,
        "monthdays":       monthdays,
        "time_hhmm":       time_hhmm,
        "start_date":      start_date,
        "end_date":        end_date,
        "recipients":      recipients_csv,
        "sharepoint_path": sp_path,
        "active":          1 if active else 0,
    }
