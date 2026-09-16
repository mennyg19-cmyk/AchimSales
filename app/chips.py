"""Expand schedule subject / filename / body chips."""

from __future__ import annotations

import html
import re

CHIP_NAMES = ("Schedule", "Period", "SharePointUrl", "DownloadButton")


def expand(
    template: str,
    *,
    schedule_name: str = "",
    period: str = "",
    sharepoint_url: str = "",
    download_url: str = "",
    html_button: bool = False,
) -> str:
    text = template or ""
    text = text.replace("{Schedule}", schedule_name or "")
    text = text.replace("{Period}", (period or "").replace("_", " "))
    text = text.replace("{SharePointUrl}", sharepoint_url or "")
    if "{DownloadButton}" in text:
        if download_url and html_button:
            button = download_button_html(download_url, label=schedule_name or "Download workbook")
        elif download_url:
            button = download_url
        else:
            button = ""
        text = text.replace("{DownloadButton}", button)
    return text


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
    return raw.replace("_", " ") if raw else ""


_UNEXPANDED = re.compile(r"\{(" + "|".join(CHIP_NAMES) + r")\}")


def still_has_chips(text: str) -> bool:
    return bool(_UNEXPANDED.search(text or ""))
