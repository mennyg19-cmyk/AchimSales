"""Expand schedule email subject/HTML templates and keep Outlook-safe markup.

Unknown {Tokens} stay in the string so a typo is visible, same as filenames.
{DownloadButton} is HTML (a table-cell link Outlook will not strip). Subject
lines get the words “Download workbook” instead of that markup.
"""

from __future__ import annotations

import re
from html import escape, unescape
from html.parser import HTMLParser

from web.delivery.filename_template import token_values

_TOKEN_RE = re.compile(r"\{[A-Za-z]+\}")
_BTN_BG = "#2563eb"
_STYLE_BAD = re.compile(r"expression|javascript|url\s*\(", re.I)

_ALLOWED: dict[str, frozenset[str]] = {
    "p": frozenset({"style"}),
    "br": frozenset(),
    "div": frozenset({"style"}),
    "span": frozenset({"style"}),
    "strong": frozenset(),
    "b": frozenset(),
    "em": frozenset(),
    "i": frozenset(),
    "u": frozenset(),
    "a": frozenset({"href", "style", "target"}),
    "table": frozenset({"role", "cellspacing", "cellpadding", "border", "style"}),
    "tbody": frozenset(),
    "thead": frozenset(),
    "tr": frozenset({"style"}),
    "td": frozenset({"style", "align", "bgcolor"}),
}
_VOID = frozenset({"br"})
_LINK_TOKENS = ("{DownloadButton}", "{SharePointUrl}", "{FileUrl}")


def download_button_html(file_url: str, *, label: str = "Download workbook") -> str:
    """Outlook-safe button: table cell + <a>, not a CSS button."""
    href = escape((file_url or "").strip(), quote=True)
    label_html = escape(label)
    if not href:
        return ""
    return (
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0" '
        'style="margin:12px 0;">'
        f'<tr><td align="center" bgcolor="{_BTN_BG}" style="border-radius:6px;'
        f'background-color:{_BTN_BG};">'
        f'<a href="{href}" target="_blank" '
        'style="display:inline-block;padding:12px 22px;'
        "font-family:Segoe UI,Calibri,Arial,sans-serif;font-size:15px;font-weight:600;"
        f'color:#ffffff;text-decoration:none;">{label_html}</a>'
        "</td></tr></table>"
    )


def email_token_map(
    *,
    report_name: str,
    schedule_name: str = "",
    params: dict | None = None,
    filename: str = "",
    file_url: str = "",
) -> dict[str, str]:
    dates = token_values(
        report_name=report_name, params=params, schedule_name=schedule_name)
    raw_period = str((params or {}).get("period") or "").strip().replace("_", " ")
    url = (file_url or "").strip()
    report = (report_name or "").strip() or dates["{Report}"]
    schedule = (schedule_name or "").strip() or dates["{Schedule}"]
    return {
        **dates,
        "{Report}": report,
        "{Schedule}": schedule,
        "{Period}": raw_period or dates["{Period}"],
        "{Filename}": filename or "",
        "{SharePointUrl}": url,
        "{FileUrl}": url,
        "{DownloadButton}": download_button_html(url) if url else "",
    }


def expand_tokens(template: str, mapping: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        return mapping.get(m.group(0), m.group(0))
    return _TOKEN_RE.sub(repl, template or "")


def sanitize_html(raw: str) -> str:
    parser = _AllowlistParser()
    parser.feed(raw or "")
    parser.close()
    return parser.out


def html_to_text(raw: str) -> str:
    parser = _TextParser()
    parser.feed(raw or "")
    parser.close()
    return re.sub(r"\n{3,}", "\n\n", parser.out).strip()


def resolve_subject(template: str, mapping: dict[str, str]) -> str:
    subj_map = dict(mapping)
    subj_map["{DownloadButton}"] = "Download workbook" if mapping.get("{FileUrl}") else ""
    text = expand_tokens(template, subj_map)
    text = re.sub(r"<[^>]+>", "", text)
    return unescape(text).replace("\n", " ").strip()[:240]


def apply_mail_templates(
    *,
    subject_default: str,
    body_text_default: str,
    body_html_default: str | None,
    subject_template: str = "",
    body_html_template: str = "",
    report_name: str,
    schedule_name: str = "",
    filename: str = "",
    file_url: str = "",
    params: dict | None = None,
    attached: bool = False,
) -> tuple[str, str, str | None]:
    mapping = email_token_map(
        report_name=report_name, schedule_name=schedule_name, params=params,
        filename=filename, file_url=file_url,
    )
    subject = (subject_default or report_name).strip()
    tpl = (subject_template or "").strip()
    if tpl:
        resolved = resolve_subject(tpl, mapping)
        if resolved:
            subject = resolved
            if subject_default.startswith("[TEST] ") and not subject.startswith("[TEST] "):
                subject = f"[TEST] {subject}"
    html_tpl = (body_html_template or "").strip()
    if not html_tpl:
        return subject, body_text_default, body_html_default
    html = sanitize_html(expand_tokens(html_tpl, mapping))
    if (
        not attached
        and file_url
        and not any(tok in html_tpl for tok in _LINK_TOKENS)
    ):
        html += download_button_html(file_url)
    text = html_to_text(html) or body_text_default
    return subject, text, html or None


def _safe_href(value: str) -> str | None:
    v = unescape((value or "").strip())
    if v.startswith("{") and v.endswith("}") and _TOKEN_RE.fullmatch(v):
        return v
    low = v.lower()
    if low.startswith(("javascript:", "data:", "vbscript:")):
        return None
    return v


def _safe_style(value: str) -> str | None:
    if _STYLE_BAD.search(value or ""):
        return None
    return value


class _AllowlistParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        allowed = _ALLOWED.get(tag)
        if allowed is None:
            return
        parts = [tag]
        for name, val in attrs:
            key = (name or "").lower()
            if key not in allowed or val is None:
                continue
            if key == "href":
                href = _safe_href(val)
                if href is None:
                    continue
                parts.append(f'href="{escape(href, quote=True)}"')
            elif key == "style":
                style = _safe_style(val)
                if style is None:
                    continue
                parts.append(f'style="{escape(style, quote=True)}"')
            elif key == "target":
                if val.strip().lower() == "_blank":
                    parts.append('target="_blank"')
            else:
                parts.append(f'{key}="{escape(str(val), quote=True)}"')
        joined = " ".join(parts)
        if tag in _VOID:
            self.out += f"<{joined}>"
        else:
            self.out += f"<{joined}>"

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _ALLOWED and tag not in _VOID:
            self.out += f"</{tag}>"

    def handle_data(self, data: str) -> None:
        self.out += escape(data)

    def handle_entityref(self, name: str) -> None:
        self.out += f"&{name};"

    def handle_charref(self, name: str) -> None:
        self.out += f"&#{name};"


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in ("br", "p", "div", "tr"):
            self.out += "\n"

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in ("p", "div", "table"):
            self.out += "\n"

    def handle_data(self, data: str) -> None:
        self.out += data
