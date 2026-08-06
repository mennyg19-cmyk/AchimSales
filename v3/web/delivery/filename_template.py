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
    ("{Period}", "period / year from params, if any"),
)

_TOKEN_RE = re.compile(r"\{[A-Za-z]+\}")


def resolve_filename_template(
    template: str,
    *,
    report_name: str,
    params: dict | None = None,
    when: datetime | None = None,
) -> str:
    """Expand tokens; always ends with .xlsx; filesystem-safe."""
    now = when or datetime.now(_EASTERN)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_EASTERN)
    else:
        now = now.astimezone(_EASTERN)

    period = _period_label(params or {})
    report_slug = _slug(report_name) or "Report"
    mapping = {
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
        "{Period}": period or now.strftime("%Y%m%d"),
    }

    raw = (template or "").strip()
    if not raw:
        raw = "{Report}_{YYYY}{MM}{DD}"

    def repl(m: re.Match[str]) -> str:
        key = m.group(0)
        return mapping.get(key, key)

    expanded = _TOKEN_RE.sub(repl, raw)
    expanded = _BAD.sub("_", expanded).strip("._") or report_slug
    if not expanded.lower().endswith(".xlsx"):
        expanded = f"{expanded}.xlsx"
    return expanded[:180]


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
