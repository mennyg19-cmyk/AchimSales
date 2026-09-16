"""Expand schedule subject / filename / folder chips.

Date parts are America/New_York at send time. Period and names come from the
saved view / schedule, not from the Reporting API payload.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone

import cadence

DEFAULT_FILENAME = "{Schedule}_{MM}-{DD}-{YYYY}"

# GUI chip order (filename). Subject/folder use a subset in the template.
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
    ("{Report}", "report title"),
    ("{Schedule}", "schedule / view name"),
    ("{Period}", "period from the saved view"),
    ("{Weekday}", "Monday … Sunday"),
)

CHIP_NAMES = tuple(token[1:-1] for token, _hint in TOKEN_HELP) + (
    "SharePointUrl",
    "FileUrl",
    "DownloadButton",
    "Filename",
)

_TOKEN_RE = re.compile(r"\{[A-Za-z]+\}")
_BAD = re.compile(r"[^A-Za-z0-9._-]+")
_FOLDER_BAD = re.compile(r'[\\:*?"<>|#%]')


def expand(
    template: str,
    *,
    schedule_name: str = "",
    period: str = "",
    sharepoint_url: str = "",
    download_url: str = "",
    html_button: bool = False,
    report_name: str = "",
    params: dict | None = None,
    when: datetime | None = None,
    filename: str = "",
) -> str:
    mapping = token_map(
        schedule_name=schedule_name,
        period=period,
        sharepoint_url=sharepoint_url,
        download_url=download_url,
        html_button=html_button,
        report_name=report_name,
        params=params,
        when=when,
        filename=filename,
        slug=False,
    )
    return _TOKEN_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), template or "")


def expand_filename(
    template: str,
    *,
    schedule_name: str = "",
    report_name: str = "",
    params: dict | None = None,
    when: datetime | None = None,
    period: str = "",
) -> str:
    mapping = token_map(
        schedule_name=schedule_name,
        period=period,
        report_name=report_name,
        params=params,
        when=when,
        slug=True,
    )
    raw = (template or "").strip() or DEFAULT_FILENAME
    expanded = _TOKEN_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), raw)
    expanded = _BAD.sub("_", expanded).strip("._") or mapping["{Report}"]
    if not expanded.lower().endswith(".xlsx"):
        expanded += ".xlsx"
    return expanded[:180]


def expand_folder(
    template: str,
    *,
    schedule_name: str = "",
    report_name: str = "",
    params: dict | None = None,
    when: datetime | None = None,
    period: str = "",
) -> str:
    raw = (template or "").replace("\\", "/").strip("/")
    if not raw:
        return ""
    mapping = token_map(
        schedule_name=schedule_name,
        period=period,
        report_name=report_name,
        params=params,
        when=when,
        slug=False,
    )
    expanded = _TOKEN_RE.sub(lambda m: mapping.get(m.group(0), m.group(0)), raw)
    parts: list[str] = []
    for seg in expanded.split("/"):
        cleaned = _FOLDER_BAD.sub("", seg).strip(" .")
        if not cleaned or cleaned in (".", ".."):
            continue
        parts.append(cleaned)
    return "/".join(parts)


def download_button_html(file_url: str, *, label: str = "Download workbook") -> str:
    href = html.escape((file_url or "").strip(), quote=True)
    label_html = html.escape(label or "Download workbook")
    if not href:
        return ""
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
        'style="margin:12px 0;">'
        '<tr><td align="center" bgcolor="#2563eb" style="border-radius:6px;'
        'background-color:#2563eb;">'
        f'<a href="{href}" target="_blank" '
        'style="display:inline-block;padding:12px 22px;'
        "font-family:Segoe UI,Calibri,Arial,sans-serif;font-size:15px;font-weight:600;"
        f'color:#ffffff;text-decoration:none;">{label_html}</a>'
        "</td></tr></table>"
    )


def period_label(params: dict | None) -> str:
    params = params or {}
    raw = str(params.get("period") or "").strip()
    if raw == "custom":
        start = params.get("from_date") or params.get("start_date") or ""
        end = params.get("to_date") or params.get("end_date") or ""
        if start and end:
            return f"{start} to {end}"
    if raw:
        return raw.replace("_", " ")
    year = params.get("year")
    if year not in (None, ""):
        return str(year)
    return ""


def still_has_chips(text: str) -> bool:
    names = "|".join(re.escape(name) for name in CHIP_NAMES)
    return bool(re.search(r"\{(" + names + r")\}", text or ""))


def token_map(
    *,
    schedule_name: str = "",
    period: str = "",
    sharepoint_url: str = "",
    download_url: str = "",
    html_button: bool = False,
    report_name: str = "",
    params: dict | None = None,
    when: datetime | None = None,
    filename: str = "",
    slug: bool = False,
) -> dict[str, str]:
    now = when or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(cadence.EASTERN)
    period_key = str((params or {}).get("period") or period or "").strip()
    period_display = period_label(params) if params else period_key.replace("_", " ")
    period_file = _slug(period_key) if period_key else now.strftime("%Y%m%d")
    report_disp = (report_name or "").strip()
    schedule_disp = (schedule_name or "").strip() or report_disp
    report_file = _slug(report_disp) or "Report"
    schedule_file = _slug(schedule_disp) or report_file
    if slug:
        schedule_val, report_val, period_val = schedule_file, report_file, period_file
    else:
        schedule_val, report_val, period_val = schedule_disp, report_disp, period_display
    url = (sharepoint_url or download_url or "").strip()
    if html_button:
        button = download_button_html(url, label=schedule_disp or "Download workbook") if url else ""
    else:
        button = url
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
        "{Report}": report_val,
        "{Schedule}": schedule_val,
        "{Period}": period_val,
        "{Weekday}": now.strftime("%A"),
        "{SharePointUrl}": url,
        "{FileUrl}": url,
        "{DownloadButton}": button,
        "{Filename}": filename or "",
    }


def _slug(value: str) -> str:
    return _BAD.sub("_", (value or "").strip()).strip("._")
