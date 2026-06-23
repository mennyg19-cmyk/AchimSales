"""Tests for the report email: composition, size fallback, and the send service.

No network: the Graph call is faked. These guard the parts that decide what
goes out -- subject, the open-in-app link, when a too-big workbook becomes a
link-only email, that the sender/reply-to are right, and that every attempt is
written to the audit log.
"""

from __future__ import annotations

from types import SimpleNamespace

from rebuild.delivery.graph_mail import GraphMailError
from rebuild.delivery.report_email import MAX_ATTACH_BYTES, EmailService, compose_report_email


def test_small_report_is_attached_with_a_link():
    composed = compose_report_email(
        report_title="Invoiced",
        subtitle="By salesman",
        view_url="https://report.achimonline.com/test-next/reports/invoiced",
        xlsx_bytes=b"x" * 1000,
        xlsx_filename="invoiced_by_salesman.xlsx",
    )
    assert composed.attached is True
    assert len(composed.attachments) == 1
    assert composed.attachments[0].filename == "invoiced_by_salesman.xlsx"
    assert composed.subject == "Invoiced - By salesman"
    assert "Open this report in the app" in composed.html_body
    assert "report.achimonline.com" in composed.html_body


def test_oversize_report_becomes_link_only():
    composed = compose_report_email(
        report_title="Invoiced",
        subtitle="All",
        view_url="https://x/reports/invoiced",
        xlsx_bytes=b"x" * (MAX_ATTACH_BYTES + 1),
        xlsx_filename="big.xlsx",
    )
    assert composed.attached is False
    assert composed.attachments == []
    assert "too large to attach" in composed.html_body


def test_subject_without_subtitle_is_just_the_title():
    composed = compose_report_email(
        report_title="Invoiced", subtitle="", view_url="", xlsx_bytes=b"x", xlsx_filename="f.xlsx"
    )
    assert composed.subject == "Invoiced"
    assert "Open this report" not in composed.html_body


def test_html_body_escapes_the_report_title():
    composed = compose_report_email(
        report_title="<script>", subtitle="", view_url="", xlsx_bytes=b"x", xlsx_filename="f.xlsx"
    )
    assert "<script>" not in composed.html_body
    assert "&lt;script&gt;" in composed.html_body


class _FakeLog:
    def __init__(self) -> None:
        self.entries: list[tuple[str, dict]] = []

    def record(self, action: str, **kwargs) -> None:
        self.entries.append((action, kwargs))


class _FakeMailer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: dict | None = None

    def send(self, **kwargs) -> None:
        if self.fail:
            raise GraphMailError("Graph said no")
        self.sent = kwargs


def _config(mail_from: str = "reports@achimonline.com"):
    return SimpleNamespace(
        mail_from=mail_from, tenant_id="t", client_id="c", client_secret="s",
        public_base_url="https://report.achimonline.com/test-next",
    )


def test_send_report_records_sent_and_sets_sender_and_reply_to():
    log = _FakeLog()
    mailer = _FakeMailer()
    service = EmailService(_config(), log, mailer=mailer)
    result = service.send_report(
        to=["me@achimonline.com"], report_key="invoiced", report_title="Invoiced",
        subtitle="By salesman", xlsx_bytes=b"x" * 10, xlsx_filename="f.xlsx",
        reply_to="me@achimonline.com", requested_by="me@achimonline.com",
    )
    assert result.ok and result.attached
    assert mailer.sent["sender"] == "reports@achimonline.com"
    assert mailer.sent["reply_to"] == "me@achimonline.com"
    assert log.entries[0][0] == "report.email"
    assert log.entries[0][1]["status"] == "sent"


def test_send_report_without_a_sender_mailbox_is_off():
    service = EmailService(_config(mail_from=""), _FakeLog(), mailer=_FakeMailer())
    result = service.send_report(
        to=["me@achimonline.com"], report_key="invoiced", report_title="t",
        subtitle="", xlsx_bytes=b"x", xlsx_filename="f.xlsx",
    )
    assert not result.ok
    assert "set up" in result.error


def test_send_report_failure_is_recorded_as_failed():
    log = _FakeLog()
    service = EmailService(_config(), log, mailer=_FakeMailer(fail=True))
    result = service.send_report(
        to=["me@achimonline.com"], report_key="invoiced", report_title="t",
        subtitle="", xlsx_bytes=b"x", xlsx_filename="f.xlsx",
    )
    assert not result.ok
    assert log.entries[0][1]["status"] == "failed"


def test_unconfigured_send_is_still_audited_as_failed():
    log = _FakeLog()
    service = EmailService(_config(mail_from=""), log, mailer=_FakeMailer())
    result = service.send_report(
        to=["me@achimonline.com"], report_key="invoiced", report_title="t",
        subtitle="", xlsx_bytes=b"x", xlsx_filename="f.xlsx",
    )
    assert not result.ok
    assert log.entries and log.entries[0][1]["status"] == "failed"


def test_oversize_with_no_app_link_fails_instead_of_sending_a_linkless_email():
    log = _FakeLog()
    mailer = _FakeMailer()
    config = _config()
    config.public_base_url = ""  # no fallback link can be built
    service = EmailService(config, log, mailer=mailer)
    result = service.send_report(
        to=["me@achimonline.com"], report_key="invoiced", report_title="t",
        subtitle="", xlsx_bytes=b"x" * (MAX_ATTACH_BYTES + 1), xlsx_filename="big.xlsx",
    )
    assert not result.ok
    assert mailer.sent is None
    assert log.entries[0][1]["status"] == "failed"


def test_compose_escapes_subtitle_and_filename():
    composed = compose_report_email(
        report_title="R", subtitle="<b>x</b>", view_url="",
        xlsx_bytes=b"x", xlsx_filename="<i>f</i>.xlsx",
    )
    assert "<b>" not in composed.html_body
    assert "<i>" not in composed.html_body
