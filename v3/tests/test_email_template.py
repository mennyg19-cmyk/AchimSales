"""Schedule email subject/HTML templates: tokens, Outlook-safe HTML, sanitizer."""

from web.delivery.email_template import (
    apply_mail_templates,
    download_button_html,
    resolve_subject,
    sanitize_html,
    email_token_map,
    expand_tokens,
)


def test_expand_subject_uses_readable_names_not_slugs():
    mapping = email_token_map(
        report_name="Ordered Report", schedule_name="Daily Ordered",
        params={"period": "yesterday"}, filename="Daily_Ordered.xlsx",
        file_url="https://achim.sharepoint.com/f/file.xlsx",
    )
    assert resolve_subject("{Schedule} {Period} {YYYY}", mapping).startswith("Daily Ordered yesterday ")
    assert "Download workbook" in resolve_subject("Get it {DownloadButton}", mapping)


def test_download_button_is_table_cell_link():
    html = download_button_html("https://achim.sharepoint.com/f/x.xlsx")
    assert "Download workbook" in html
    assert "<table" in html
    assert "https://achim.sharepoint.com/f/x.xlsx" in html
    assert "#2563eb" in html


def test_sanitize_html_strips_script_and_js_href():
    raw = '<p>Hi</p><script>alert(1)</script><a href="javascript:alert(1)">x</a>'
    out = sanitize_html(raw)
    assert "<script" not in out.lower()
    assert "javascript:" not in out.lower()
    assert "Hi" in out


def test_apply_template_fills_sharepoint_url_and_keeps_blank_as_default():
    subj, text, html = apply_mail_templates(
        subject_default="Scheduled: Daily Ordered (2026-09-03)",
        body_text_default="See attached.",
        body_html_default=None,
        subject_template="{Schedule} ready",
        body_html_template='<p>Open {SharePointUrl}</p>{DownloadButton}',
        report_name="Ordered Report", schedule_name="Daily Ordered",
        filename="f.xlsx", file_url="https://example.com/f.xlsx",
        params={"period": "yesterday"}, attached=False,
    )
    assert subj == "Daily Ordered ready"
    assert "https://example.com/f.xlsx" in text
    assert "Download workbook" in html
    assert "<script" not in html

    subj2, text2, html2 = apply_mail_templates(
        subject_default="Scheduled: X",
        body_text_default="See attached.",
        body_html_default=None,
        subject_template="", body_html_template="",
        report_name="Ordered", schedule_name="X",
        filename="f.xlsx", file_url="", attached=True,
    )
    assert subj2 == "Scheduled: X"
    assert text2 == "See attached."
    assert html2 is None


def test_custom_html_without_link_token_appends_download_button():
    _, _, html = apply_mail_templates(
        subject_default="S", body_text_default="See attached.",
        body_html_default=None, subject_template="",
        body_html_template="<p>Hello</p>",
        report_name="Ordered", schedule_name="Daily",
        filename="f.xlsx", file_url="https://example.com/f.xlsx",
        attached=False,
    )
    assert "Hello" in html
    assert "Download workbook" in html
    assert "https://example.com/f.xlsx" in html

    _, _, attached_html = apply_mail_templates(
        subject_default="S", body_text_default="See attached.",
        body_html_default=None, subject_template="",
        body_html_template="<p>Hello</p>",
        report_name="Ordered", schedule_name="Daily",
        filename="f.xlsx", file_url="https://example.com/f.xlsx",
        attached=True,
    )
    assert "Download workbook" not in (attached_html or "")


def test_unknown_token_stays_visible():
    assert "{Nope}" in expand_tokens("hi {Nope}", email_token_map(report_name="R"))


def test_test_prefix_stays_on_custom_subject():
    subj, _, _ = apply_mail_templates(
        subject_default="[TEST] Scheduled: X",
        body_text_default="x", body_html_default=None,
        subject_template="{Schedule}", body_html_template="",
        report_name="Ordered", schedule_name="Mine",
        filename="", file_url="", attached=True,
    )
    assert subj == "[TEST] Mine"
