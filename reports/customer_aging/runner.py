"""
Customer Aging Report runner.

Orchestrates: fetch CustAgedBalances + Customers from D365 -> build views -> write Excel.

Master report: multi-sheet workbook with All Customers, DS, WH, MISC, and per-salesman tabs.
Automated reports: one workbook per salesman emailed to them.
Avi can run for any salesman or any customer from the webapp.
"""

import logging
import os
import sys

from config.paths import get_output_path
from core.dates import FetchPlan, get_today_eastern
from core.email_report import send_report_email
from core.logging import setup_logging
from reports.base import BaseReportRunner
from reports.customer_aging.builder import build_master_sheets, build_salesman_sheet
from reports.customer_aging.loader import load_aging_data
from reports.customer_aging.writer import write_aging_master_workbook, write_aging_salesman_workbook

log = logging.getLogger(__name__)

REPORT_NAME = "Customer Aging Report"
REPORT_KEY = "customer_aging_report"


def _resolve_salesman_email(
    sm_display_name: str, test_override: str | None = None,
) -> tuple[str | None, list[str], list[str]]:
    """Look up a salesman's email, CC, and BCC if subscribed to the aging report."""
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


class CustomerAgingReportRunner(BaseReportRunner):
    report_name = REPORT_NAME

    def __init__(self):
        super().__init__()
        self.pending_salesman_emails: list[dict] = []
        self.defer_salesman_emails: bool = False

    @property
    def _test_email_override(self) -> str | None:
        if not self.test_mode:
            return None
        from config.settings import get_test_email
        addr = get_test_email()
        return addr if addr else None

    @property
    def _send_emails(self) -> bool:
        cli = getattr(self, "_cli_args", None)
        return bool(getattr(cli, "email", False))

    def build_arg_parser(self):
        parser = super().build_arg_parser()
        parser.add_argument("--email", action="store_true", default=False,
                            help="Email individual aging reports to subscribed salesmen")
        return parser

    def resolve_plan(self, args):
        """Aging report is a point-in-time snapshot; no date range needed.

        We still return a FetchPlan for compatibility with the base class,
        but the aging entity itself doesn't use date filters.
        """
        today = get_today_eastern()
        return FetchPlan(
            fetch_start=today,
            fetch_end=today,
            periods=[],
        )

    def _queue_or_send_email(self, sm_name: str, file_path: str) -> None:
        if self.defer_salesman_emails:
            self.pending_salesman_emails.append({
                "salesman": sm_name,
                "file_path": file_path,
            })
            log.info("Deferred aging email for %s (will send after upload)", sm_name)
        else:
            self._send_salesman_email(sm_name, file_path)

    def _send_salesman_email(
        self, sm_name: str, file_path: str,
        sharepoint_url: str | None = None,
    ) -> None:
        email, cc, bcc = _resolve_salesman_email(sm_name, test_override=self._test_email_override)
        if not email:
            log.info("No email for salesman '%s'; skipping aging email", sm_name)
            return
        today = get_today_eastern()
        subject = f"Customer Aging Report - {sm_name} ({today.strftime('%m/%d/%Y')})"
        body = f"Attached is your Customer Aging Report as of {today.strftime('%m/%d/%Y')}."
        if sharepoint_url:
            body += f"\n\nSharePoint link: {sharepoint_url}"
        try:
            send_report_email(file_path=file_path, subject=subject, body=body,
                              recipients=[email], cc=cc, bcc=bcc)
            log.info("Emailed aging report to %s (%s)", sm_name, email)
        except Exception:
            log.exception("Failed to email aging report to %s (%s)", sm_name, email)

    def flush_pending_emails(self, url_map: dict[str, str] | None = None) -> None:
        """Send all deferred salesman emails, optionally with SharePoint URLs."""
        url_map = url_map or {}
        for entry in self.pending_salesman_emails:
            basename = os.path.basename(entry["file_path"])
            sp_url = url_map.get(basename)
            self._send_salesman_email(entry["salesman"], entry["file_path"], sharepoint_url=sp_url)

        sent = len(self.pending_salesman_emails)
        self.pending_salesman_emails.clear()
        if sent:
            log.info("Flushed %d deferred aging emails", sent)

    def run(self, plan: FetchPlan, company_id: str | None = None) -> None:
        base_url, token, company = self.connect(company_id)
        cli = getattr(self, "_cli_args", None)

        customer_filter = getattr(cli, "customer", None) if cli else None
        salesman_filter = getattr(cli, "salesman", None) if cli else None

        log.info("Loading customer aging data...")
        df = load_aging_data(base_url, token, company, customer_account=customer_filter)

        if df.empty:
            log.info("No aging data found. Exiting.")
            return

        log.info("Loaded %d customers with aging data", len(df))

        if self.dry_run:
            log.info("[DRY RUN] %s: %d customers -- skipping write", REPORT_NAME, len(df))
            return

        today = get_today_eastern()
        date_str = today.strftime("%Y-%m-%d")
        test_tag = "_TEST" if self.test_mode else ""

        # If filtering to specific salesman(s), only produce their workbooks
        if salesman_filter and salesman_filter != ["all"]:
            for sm_key in salesman_filter:
                from config.salesman_excel import lookup_salesman_xl
                rec = lookup_salesman_xl(sm_key)
                sm_display = rec.display_name if rec.display_name else sm_key

                sm_data = build_salesman_sheet(df, sm_display)
                if sm_data.empty:
                    log.info("No aging data for salesman %s", sm_display)
                    continue

                sm_filename = f"Customer_Aging_{sm_display}_{date_str}{test_tag}.xlsx"
                sm_path = get_output_path(REPORT_NAME, date_str, sm_filename)
                write_aging_salesman_workbook(sm_data, sm_display, sm_path)

                if self._send_emails:
                    self._queue_or_send_email(sm_display, sm_path)
            return

        # Full master report
        sheets = build_master_sheets(df)
        master_filename = f"Customer_Aging_Master_{date_str}{test_tag}.xlsx"
        master_path = get_output_path(REPORT_NAME, date_str, master_filename)
        write_aging_master_workbook(sheets, master_path)
        log.info("Saved master: %s", master_path)

        # Per-salesman workbooks for email
        if self._send_emails or (salesman_filter and salesman_filter == ["all"]):
            from config.salesman_excel import load_salesman_map
            sm_map = load_salesman_map()
            subscribed_displays = {
                rec.display_name for rec in sm_map.values()
                if rec.subscriptions.get(REPORT_KEY, False) and rec.email
            }

            salesmen = sorted(df["Salesman"].dropna().astype(str).str.strip().unique())
            for sm_name in salesmen:
                if not sm_name:
                    continue
                if sm_name not in subscribed_displays and salesman_filter != ["all"]:
                    log.debug("Skipping aging email for %s (not subscribed)", sm_name)
                    continue

                sm_data = build_salesman_sheet(df, sm_name)
                if sm_data.empty:
                    continue

                sm_filename = f"Customer_Aging_{sm_name}_{date_str}{test_tag}.xlsx"
                sm_path = get_output_path(REPORT_NAME, date_str, sm_filename, sub_report="By Salesman")
                write_aging_salesman_workbook(sm_data, sm_name, sm_path)

                if self._send_emails:
                    self._queue_or_send_email(sm_name, sm_path)


def main(argv=None):
    return CustomerAgingReportRunner().main(argv)


if __name__ == "__main__":
    sys.exit(main())
