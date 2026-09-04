"""Schedule email subject/HTML templates: tokens, Outlook-safe HTML, sanitizer."""

from email.message import EmailMessage

from web.delivery.email_template import (
    apply_mail_templates,
    download_button_html,
    resolve_subject,
    sanitize_html,
    sanitize_subject,
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


def test_sanitize_html_rejects_encoded_javascript_href():
    for raw in (
        '<a href="java&#10;script:alert(1)">x</a>',
        '<a href="java&#9;script:alert(1)">x</a>',
        '<a href="javascript&colon;alert(1)">x</a>',
        '<a href=" data:text/html,hi">x</a>',
    ):
        out = sanitize_html(raw).lower()
        assert "javascript:" not in out
        assert "data:text/html" not in out
        assert "\n" not in out
        assert "\t" not in out
    keep = sanitize_html('<a href="{SharePointUrl}">Open</a>')
    assert 'href="{SharePointUrl}"' in keep
    keep_https = sanitize_html('<a href="https://achim.sharepoint.com/f/x.xlsx">Open</a>')
    assert "https://achim.sharepoint.com/f/x.xlsx" in keep_https


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


def test_retry_mark_stays_on_custom_subject_and_body():
    from web.delivery.email_template import RETRY_SUBJECT_MARK
    retry_body = (
        "This send failed once, then retried and succeeded.\n"
        "First attempt: graph timeout\n\n"
        "There is no separate failure email for this run.\n"
    )
    subj, text, html = apply_mail_templates(
        subject_default=f"[TEST] Scheduled: X{RETRY_SUBJECT_MARK}",
        body_text_default=retry_body, body_html_default=None,
        subject_template="{Schedule}",
        body_html_template="<p>Hi {Schedule}</p>",
        report_name="Ordered", schedule_name="Mine",
        filename="", file_url="", attached=True,
    )
    assert subj.startswith("[TEST] Mine")
    assert subj.endswith(RETRY_SUBJECT_MARK)
    assert "This send failed once" in text
    assert "This send failed once" in html
    assert "Hi Mine" in html


def test_custom_subject_strips_encoded_crlf():
    subj, _, _ = apply_mail_templates(
        subject_default="Scheduled: X",
        body_text_default="x", body_html_default=None,
        subject_template="Nightly&#13;Bcc: victim@example.com",
        body_html_template="",
        report_name="Ordered", schedule_name="Mine",
        filename="", file_url="", attached=True,
    )
    assert "\r" not in subj
    assert "\n" not in subj
    assert "Bcc:" in subj
    msg = EmailMessage()
    msg["Subject"] = subj
    assert "Bcc:" in msg["Subject"]
    assert "\r" not in sanitize_subject("Line&#10;two")


def test_retry_mark_survives_max_length_subject():
    from web.delivery.email_template import RETRY_SUBJECT_MARK
    subj, _, _ = apply_mail_templates(
        subject_default=f"[TEST] Scheduled: X{RETRY_SUBJECT_MARK}",
        body_text_default="x", body_html_default=None,
        subject_template="A" * 240, body_html_template="",
        report_name="Ordered", schedule_name="Mine",
        filename="", file_url="", attached=True,
    )
    assert subj.startswith("[TEST] ")
    assert subj.endswith(RETRY_SUBJECT_MARK)
    assert len(subj) <= 240
    msg = EmailMessage()
    msg["Subject"] = subj
