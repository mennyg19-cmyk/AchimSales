"""
Salesman Report runner.

Orchestrates: fetch invoice data from D365 -> build salesman comparisons -> write Excel.
Produces one workbook with 12 month tabs (Jan-Dec), matching the legacy Monthly Salesmen Report.
Emails individual salesman workbooks to subscribed salesmen.
"""

import logging
import os
import sys
from datetime import date

from config.paths import get_output_path
from core.dates import FetchPlan, clamp_start, get_today_eastern, resolve_fetch_plan
from core.email_report import send_report_email
from core.logging import setup_logging
from core.validation import validate_output
from reports.base import BaseReportRunner
from reports.invoiced.loader import fetch_invoice_detail
from reports.salesman.builder import build_salesman_full_year_data
from reports.salesman.writer import (
    get_all_salesmen,
    write_individual_salesman_workbook,
    write_monthly_salesmen_workbook,
)

log = logging.getLogger(__name__)

REPORT_NAME = "Salesman Report"
REPORT_KEY = "salesman"


def _resolve_salesman_email(
    sm_display_name: str, test_override: str | None = None,
) -> tuple[str | None, list[str], list[str]]:
    """Look up a salesman's email, CC, and BCC if subscribed to the salesman report.

    Returns (email_or_None, cc_list, bcc_list).
    When ``test_override`` is set, CC/BCC are emptied so test runs don't
    leak emails to real recipients.
    """
    if test_override:
        return test_override, [], []
    try:
        from config.salesman_excel import get_salesman_cc_bcc, get_salesman_email, load_salesman_map, wants_report
        sm_map = load_salesman_map()
        for key, rec in sm_map.items():
            if rec.display_name == sm_display_name:
                if not wants_report(key, REPORT_KEY):
                    log.debug("%s opted out of %s", sm_display_name, REPORT_NAME)
                    return None, [], []
                email = get_salesman_email(key)
                if not email or "@" not in email:
                    return None, [], []
                cc, bcc = get_salesman_cc_bcc(key)
                return email, cc, bcc
        return None, [], []
    except Exception:
        log.debug("Could not resolve email for salesman '%s'", sm_display_name, exc_info=True)
        return None, [], []


def _send_salesman_report_email(
    sm_name: str, file_path: str, year: int,
    sharepoint_url: str | None = None,
    test_override: str | None = None,
) -> None:
    """Email a salesman their individual report."""
    email, cc, bcc = _resolve_salesman_email(sm_name, test_override=test_override)
    if not email:
        log.info("No email for salesman '%s'; skipping report email", sm_name)
        return
    subject = f"{REPORT_NAME} - {sm_name} ({year})"
    body = f"Attached is your {REPORT_NAME} for {year}."
    if sharepoint_url:
        body += f"\n\nSharePoint link: {sharepoint_url}"
    try:
        send_report_email(file_path=file_path, subject=subject, body=body,
                          recipients=[email], cc=cc, bcc=bcc)
        log.info("Emailed report to %s (%s)", sm_name, email)
    except Exception:
        log.exception("Failed to email report to %s (%s)", sm_name, email)


class SalesmanReportRunner(BaseReportRunner):
    report_name = REPORT_NAME

    def __init__(self):
        super().__init__()
        self.pending_salesman_emails: list[dict] = []
        self.defer_salesman_emails: bool = False

    @property
    def _test_email_override(self) -> str | None:
        """Return the TEST_EMAIL address when ``--test`` is active, else None."""
        if not self.test_mode:
            return None
        from config.settings import get_test_email
        addr = get_test_email()
        return addr if addr else None

    def _queue_or_send_salesman_email(
        self, sm_name: str, file_path: str, year: int,
    ) -> None:
        """Queue or immediately send a salesman report email.

        When running inside the universal runbook, emails are deferred so the
        runbook can inject SharePoint links after upload.
        """
        if self.defer_salesman_emails:
            self.pending_salesman_emails.append({
                "salesman": sm_name,
                "file_path": file_path,
                "year": year,
            })
            log.info("Deferred salesman email for %s (will send after upload)", sm_name)
        else:
            _send_salesman_report_email(
                sm_name, file_path, year,
                test_override=self._test_email_override,
            )

    def flush_pending_emails(self, url_map: dict[str, str] | None = None) -> None:
        """Send all deferred salesman emails, optionally with SharePoint URLs.

        url_map: {local_file_basename: sharepoint_webUrl}
        """
        url_map = url_map or {}
        test_override = self._test_email_override
        for entry in self.pending_salesman_emails:
            basename = os.path.basename(entry["file_path"])
            sp_url = url_map.get(basename)

            if entry.get("is_master"):
                from config.salesman_excel import get_report_subscribers
                subscribers = get_report_subscribers("master_salesman")
                for display_name, email, sub_cc, sub_bcc in subscribers:
                    recipient = test_override if test_override else email
                    cc = [] if test_override else sub_cc
                    bcc = [] if test_override else sub_bcc
                    year = entry["year"]
                    subject = f"Monthly Salesmen Report ({year})"
                    body = f"Attached is the Monthly Salesmen Report for {year}."
                    if sp_url:
                        body += f"\n\nSharePoint link: {sp_url}"
                    try:
                        send_report_email(
                            file_path=entry["file_path"], subject=subject, body=body,
                            recipients=[recipient], cc=cc, bcc=bcc,
                        )
                        log.info("Emailed master report to %s (%s)", display_name, recipient)
                    except Exception:
                        log.exception("Failed to email master report to %s (%s)", display_name, recipient)
            else:
                _send_salesman_report_email(
                    entry["salesman"], entry["file_path"], entry["year"],
                    sharepoint_url=sp_url,
                    test_override=test_override,
                )

        sent = len(self.pending_salesman_emails)
        self.pending_salesman_emails.clear()
        if sent:
            log.info("Flushed %d deferred salesman emails", sent)

    def _send_master_report(self, master_path: str, year: int) -> None:
        """Email the master salesman report to all master_salesman subscribers."""
        from config.salesman_excel import get_report_subscribers
        test_override = self._test_email_override
        subscribers = get_report_subscribers("master_salesman")
        if not subscribers:
            log.info("No subscribers for master salesman report")
            return

        subject = f"Monthly Salesmen Report ({year})"
        body = f"Attached is the Monthly Salesmen Report for {year}."

        for display_name, email, sub_cc, sub_bcc in subscribers:
            recipient = test_override if test_override else email
            cc = [] if test_override else sub_cc
            bcc = [] if test_override else sub_bcc
            if self.defer_salesman_emails:
                self.pending_salesman_emails.append({
                    "salesman": display_name,
                    "file_path": master_path,
                    "year": year,
                    "is_master": True,
                })
                log.info("Deferred master report email for %s (will send after upload)", display_name)
            else:
                try:
                    send_report_email(
                        file_path=master_path, subject=subject, body=body,
                        recipients=[recipient], cc=cc, bcc=bcc,
                    )
                    log.info("Emailed master report to %s (%s)", display_name, recipient)
                except Exception:
                    log.exception("Failed to email master report to %s (%s)", display_name, recipient)

    @property
    def _send_emails(self) -> bool:
        """True when ``--email`` was passed on the command line.

        TEMPORARY KILL-SWITCH (May 2026): emails are force-disabled while the
        Monthly Salesman Report output is being verified. The Apr 30 nightly
        run sent empty-attachment emails to every rep due to a runbook flush
        ordering bug (now fixed) and we don't want any further send-outs
        until someone confirms the data is right. To re-enable, delete the
        ``return False`` line below.
        """
        return False
        cli = getattr(self, "_cli_args", None)
        return bool(getattr(cli, "email", False))

    def build_arg_parser(self):
        parser = super().build_arg_parser()
        parser.add_argument("--year", type=int, default=None, help="Report year (default: current year)")
        parser.add_argument("--email", action="store_true", default=False,
                            help="Email individual reports to subscribed salesmen and master report to subscribers")
        return parser

    def resolve_plan(self, args):
        year = getattr(args, "year", None) or get_today_eastern().year
        if args.from_date and args.to_date:
            return resolve_fetch_plan(from_date=args.from_date, to_date=args.to_date)
        if args.date:
            return resolve_fetch_plan(single_date=args.date)
        # Monthly Salesmen: always fetch full prior + current year
        return FetchPlan(
            fetch_start=clamp_start(date(year - 1, 1, 1)),
            fetch_end=date(year, 12, 31),
            periods=[],
        )

    def run(self, plan: FetchPlan, company_id: str | None = None) -> None:
        base_url, token, company = self.connect(company_id)

        year = plan.fetch_end.year

        log.info("Fetching invoice data for salesman report: %s to %s", plan.fetch_start, plan.fetch_end)
        full_detail = fetch_invoice_detail(base_url, token, plan.fetch_start, plan.fetch_end, company)

        if full_detail.empty:
            log.info("No invoices found. Exiting.")
            return

        log.info("Building %s: full year %d", REPORT_NAME, year)
        month_data_by_month = build_salesman_full_year_data(full_detail, year)

        if not month_data_by_month:
            log.info("No data for period. Skipping.")
            return

        _EXPECTED_COLS = [
            "Sales_Current", "Sales_Prior", "Sales_YTD_Current", "Sales_YTD_Prior",
            "Salesman", "CustomerAccount",
        ]
        for m, df in month_data_by_month.items():
            if not df.empty:
                validate_output(df, _EXPECTED_COLS, REPORT_NAME)
                break

        if self.dry_run:
            total_rows = sum(len(df) for df in month_data_by_month.values())
            log.info("[DRY RUN] %s %d: %d total rows across 12 months -- skipping write",
                     REPORT_NAME, year, total_rows)
            return

        today = get_today_eastern()
        month_folder = f"{today.strftime('%B')} {today.year}"
        test_tag = "_TEST" if self.test_mode else ""

        master_filename = f"Monthly Salesmen Report {today.strftime('%b')} {year}{test_tag}.xlsx"
        master_path = get_output_path(
            REPORT_NAME, month_folder, master_filename,
            sub_report="Monthly Salesmen Report",
        )
        log.info("Writing master: %s", master_path)
        write_monthly_salesmen_workbook(month_data_by_month, year, master_path)
        log.info("Saved master: %s", master_path)

        if self._send_emails:
            self._send_master_report(master_path, year)

        from config.salesman_excel import load_salesman_map
        sm_map = load_salesman_map()
        subscribed_displays = {
            rec.display_name for rec in sm_map.values()
            if rec.subscriptions.get(REPORT_KEY, False) and rec.email
        }

        all_salesmen = get_all_salesmen(month_data_by_month)
        for sm_name in all_salesmen:
            if sm_name not in subscribed_displays:
                log.debug("Skipping individual report for %s (not subscribed)", sm_name)
                continue
            sm_filename = f"{sm_name} {today.strftime('%b')} {year}{test_tag}.xlsx"
            sm_path = get_output_path(
                REPORT_NAME, month_folder, sm_filename,
                sub_report="Monthly Salesmen Report",
            )
            write_individual_salesman_workbook(month_data_by_month, year, sm_name, sm_path)
            if self._send_emails:
                self._queue_or_send_salesman_email(sm_name, sm_path, year)


def main(argv=None):
    return SalesmanReportRunner().main(argv)


if __name__ == "__main__":
    sys.exit(main())
