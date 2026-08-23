"""Resolve schedule filename templates with date/report tokens.

Eastern clock for date parts (same zone the reports use). Unknown tokens are
left as-is so a typo is visible in the delivered name instead of silently
dropped.
"""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

_EASTERN = ZoneInfo("America/New_York")
_BAD = re.compile(r"[^A-Za-z0-9._-]+")

# {Token} → value. Order in TOKEN_HELP is the GUI chip order.
TOKEN_HELP: tuple[tuple[str, str], ...] = (
    ("{YYYY}", "4-digit year"),
    ("{YY}", "2-digit year"),
    ("{MM}", "month 01–12"),
    ("{M}", "month 1–12"),
    ("{Month}", "July"),
    ("{Mon}", "Jul"),
    ("{DD}", "day 01–31"),
    ("{D}", "day 1–31"),
    ("{HH}", "hour 00–23 (Eastern)"),
    ("{mm}", "minute 00–59"),
    ("{ss}", "second 00–59"),
    ("{Report}", "report title slug"),
    ("{Schedule}", "schedule name slug"),
    ("{Period}", "period / year from params, if any"),
    ("{Weekday}", "Monday … Sunday"),
)

_TOKEN_RE = re.compile(r"\{[A-Za-z]+\}")
# Folder segments keep spaces ("August 2026"). Strip Graph-illegal chars only.
_FOLDER_BAD = re.compile(r'[\\:*?"<>|#%]')

# Blank templates used to be "{Report}_{YYYY}{MM}{DD}", so Daily 9am and
# DailyOrderReport both arrived as Ordered_20260817.xlsx.
DEFAULT_FILENAME_TEMPLATE = "{Schedule}_{YYYY}-{MM}-{DD}_{HH}{mm}"


def token_values(
    *,
    report_name: str,
    params: dict | None = None,
    when: datetime | None = None,
    schedule_name: str = "",
) -> dict[str, str]:
    now = when or datetime.now(_EASTERN)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_EASTERN)
    else:
        now = now.astimezone(_EASTERN)
    period = _period_label(params or {})
    report_slug = _slug(report_name) or "Report"
    schedule_slug = _slug(schedule_name) or report_slug
    return {
        "{YYYY}": f"{now.year:04d}",
        "{YY}": f"{now.year % 100:02d}",
        "{MM}": f"{now.month:02d}",
        "{M}": str(now.month),
        "{Month}": now.strftime("%B"),
        "{Mon}": now.strftime("%b"),
        "{DD}": f"{now.day:02d}",
        "{D}": str(now.day),
        "{HH}": f"{now.hour:02d}",
        "{mm}": f"{now.minute:02d}",
        "{ss}": f"{now.second:02d}",
        "{Report}": report_slug,
        "{Schedule}": schedule_slug,
        "{Period}": period or now.strftime("%Y%m%d"),
        "{Weekday}": now.strftime("%A"),
    }


def resolve_filename_template(
    template: str,
    *,
    report_name: str,
    params: dict | None = None,
    when: datetime | None = None,
    schedule_name: str = "",
) -> str:
    """Expand tokens; always ends with .xlsx; filesystem-safe."""
    mapping = token_values(
        report_name=report_name, params=params, when=when,
        schedule_name=schedule_name,
    )
    report_slug = mapping["{Report}"]

    raw = (template or "").strip()
    if not raw:
        raw = DEFAULT_FILENAME_TEMPLATE

    def repl(m: re.Match[str]) -> str:
        key = m.group(0)
        return mapping.get(key, key)

    expanded = _TOKEN_RE.sub(repl, raw)
    expanded = _BAD.sub("_", expanded).strip("._") or report_slug
    if not expanded.lower().endswith(".xlsx"):
        expanded = f"{expanded}.xlsx"
    return expanded[:180]


def resolve_folder_template(
    template: str,
    *,
    report_name: str = "",
    params: dict | None = None,
    when: datetime | None = None,
    schedule_name: str = "",
) -> str:
    """Expand the same tokens as filenames. Keeps `/` as folders and spaces in names."""
    raw = (template or "").replace("\\", "/").strip("/")
    if not raw:
        return ""
    mapping = token_values(
        report_name=report_name, params=params, when=when,
        schedule_name=schedule_name,
    )

    def repl(m: re.Match[str]) -> str:
        return mapping.get(m.group(0), m.group(0))

    expanded = _TOKEN_RE.sub(repl, raw)
    parts: list[str] = []
    for seg in expanded.split("/"):
        cleaned = _FOLDER_BAD.sub("", seg).strip(" .")
        if not cleaned or cleaned in (".", ".."):
            continue
        parts.append(cleaned)
    return "/".join(parts)


def _period_label(params: dict) -> str:
    period = str(params.get("period") or "").strip()
    if period:
        return _slug(period)
    year = params.get("year")
    if year not in (None, ""):
        return _slug(str(year))
    return ""


def _slug(value: str) -> str:
    return _BAD.sub("_", (value or "").strip()).strip("._")
