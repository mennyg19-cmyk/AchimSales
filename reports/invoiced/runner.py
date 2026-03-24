"""
Invoiced Report runner.

Orchestrates: fetch from D365 -> aggregate -> write Excel per period.
Smart fetch: no args = single YTD pull, filter for each period.

Supports ``--salesman all`` to iterate over every salesman subscribed to
the invoiced report (per ``salesman_map.xlsx``), generating a "Shipped Report"
and emailing it to each (email-only, no file saved to disk / SharePoint).
"""

import logging
import os
import shutil
import sys
import tempfile
from datetime import date

from config.commission_map import get_commission_pct_map
from config.paths import get_output_path
from core.dates import FetchPlan, PeriodSpec, clamp_start
from core.email_report import send_report_email
from core.validation import validate_output
from reports.base import BaseReportRunner
from reports.invoiced.aggregator import build_invoiced_views, build_reversal_audit
from reports.invoiced.loader import fetch_invoice_detail
from reports.invoiced.writer import write_invoiced_report

log = logging.getLogger(__name__)

REPORT_NAME = "Invoiced Report"
REPORT_KEY = "invoiced"

_EXPECTED_COLS = [
    "CustomerAccount", "CustomerName", "InvoiceDate", "InvoiceNumber",
    "SalesOrderNumber", "SubTotal Invoices", "Total Invoice",
    "Salesman", "SalesmanNumber", "SalesmanName",
]


def _resolve_salesman_email(
    sales_group: str, test_override: str | None = None,
) -> tuple[str | None, list[str], list[str]]:
    """Best-effort lookup of the salesman's email, CC, and BCC."""
    if test_override:
        return test_override, [], []
    try:
        from config.salesman_excel import get_salesman_cc_bcc, get_salesman_email
        email = get_salesman_email(sales_group)
        if not email or "@" not in email:
            return None, [], []
        cc, bcc = get_salesman_cc_bcc(sales_group)
        return email, cc, bcc
    except Exception:
        log.debug("Could not resolve email for salesman '%s'", sales_group, exc_info=True)
        return None, [], []


def _get_subscribed_salesmen() -> list[tuple[str, str, str]]:
    """Return [(salesman_key, display_name, email)] for salesmen subscribed to invoiced report."""
    try:
        from config.salesman_excel import load_salesman_map
        sm_map = load_salesman_map()
        result = []
        for key, rec in sm_map.items():
            if rec.email and rec.subscriptions.get(REPORT_KEY, False):
                result.append((key, rec.display_name or key, rec.email))
        return result
    except Exception:
        log.exception("Could not load salesman subscriptions for --salesman all")
        return []


def _send_salesman_report_email(
    salesman_name: str, file_path: str, period_label: str,
    test_override: str | None = None,
) -> None:
    """Email a completed Shipped Report to the salesman."""
    email, cc, bcc = _resolve_salesman_email(salesman_name, test_override=test_override)
    if not email:
        log.info("No email for salesman '%s'; skipping report email", salesman_name)
        return
    subject = f"Shipped Report - {salesman_name} ({period_label})"
    body = f"Attached is your Shipped Report for period '{period_label}'."
    try:
        send_report_email(file_path=file_path, subject=subject, body=body,
                          recipients=[email], cc=cc, bcc=bcc)
        log.info("Emailed Shipped Report to %s (%s)", salesman_name, email)
    except Exception:
        log.exception("Failed to email Shipped Report to %s (%s)", salesman_name, email)


class InvoicedReportRunner(BaseReportRunner):
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

    def flush_pending_emails(self, url_map: dict[str, str] | None = None) -> None:
        """Send all deferred salesman emails.

        For invoiced/shipped salesman reports, files are email-only so
        SharePoint URLs are not applicable -- but the interface is kept
        consistent with other runners.
        """
        test_override = self._test_email_override
        for entry in self.pending_salesman_emails:
            _send_salesman_report_email(
                entry["salesman"], entry["file_path"], entry["period_label"],
                test_override=test_override,
            )
        sent = len(self.pending_salesman_emails)
        self.pending_salesman_emails.clear()
        if sent:
            log.info("Flushed %d deferred salesman emails", sent)

    def _send_or_queue_email(
        self, salesman_name: str, file_path: str, period_label: str,
    ) -> None:
        """Always send immediately -- salesman shipped files live in a temp dir."""
        _send_salesman_report_email(
            salesman_name, file_path, period_label,
            test_override=self._test_email_override,
        )

    def _resolve_out_subfolder(self, period: PeriodSpec, subfolder_base: str | None) -> str:
        if subfolder_base:
            return subfolder_base
        if period.subfolder == "Daily":
            return f"Daily/{period.start_date.strftime('%Y-%m %b')}"
        return period.subfolder

    def _write_period_report(
        self, period: PeriodSpec, full_detail, ytd_credits, ytd_invoices,
        period_detail, out_path: str, display_name: str,
        *, skip_commissions: bool = False,
    ) -> None:
        """Build views and write the invoiced/shipped workbook."""
        summary, commissions, details_net, credits, invoices = build_invoiced_views(period_detail)
        audit = build_reversal_audit(period_detail)
        report_year = period.end_date.year
        pct_map = get_commission_pct_map()
        log.info("Writing %s (%d detail rows)", out_path, len(period_detail))
        write_invoiced_report(
            summary, commissions, details_net, credits, invoices, audit, out_path,
            year=report_year, full_detail=full_detail,
            ytd_credits=ytd_credits, ytd_invoices=ytd_invoices,
            pct_map=pct_map, current_month=period.end_date.month,
            skip_commissions=skip_commissions,
        )

    def _run_for_all_salesmen(
        self, plan: FetchPlan, company_id: str | None,
        customer_filter: list[str] | None,
    ) -> None:
        """Run a separate Shipped Report for each subscribed salesman (email-only)."""
        subscribed = _get_subscribed_salesmen()
        if not subscribed:
            log.warning("No salesmen subscribed to '%s' in salesman_map.xlsx", REPORT_KEY)
            return

        log.info("Running Shipped Report for %d subscribed salesmen (email-only)", len(subscribed))

        base_url, token, company = self.connect(company_id)

        ytd_start = clamp_start(date(plan.fetch_end.year, 1, 1))
        effective_start = min(plan.fetch_start, ytd_start)
        log.info("Fetching invoice data: %s to %s", effective_start, plan.fetch_end)
        full_detail = fetch_invoice_detail(base_url, token, effective_start, plan.fetch_end, company)

        if customer_filter and "CustomerAccount" in full_detail.columns:
            accts = full_detail["CustomerAccount"].astype(str).str.strip()
            full_detail = full_detail[accts.isin(customer_filter)].reset_index(drop=True)

        if full_detail.empty:
            log.info("No invoices found for fetch range. Exiting.")
            return

        _, _, _, ytd_credits, ytd_invoices = build_invoiced_views(full_detail)

        tmp_dir = tempfile.mkdtemp(prefix="shipped_sm_all_")
        try:
            for sm_idx, (sm_key, sm_display, sm_email) in enumerate(subscribed):
                log.info("--- Salesman %d/%d: %s (%s) ---",
                         sm_idx + 1, len(subscribed), sm_display, sm_email)

                if "Salesman" in full_detail.columns:
                    sm_lower = sm_key.strip().lower()
                    sm_detail = full_detail[
                        full_detail["Salesman"].astype(str).str.strip().str.lower() == sm_lower
                    ].reset_index(drop=True)
                else:
                    sm_detail = full_detail

                if sm_detail.empty:
                    log.info("No invoice data for %s. Skipping.", sm_display)
                    continue

                if "Salesman" in ytd_credits.columns:
                    sm_ytd_credits = ytd_credits[
                        ytd_credits["Salesman"].astype(str).str.strip().str.lower() == sm_lower
                    ].reset_index(drop=True)
                else:
                    sm_ytd_credits = ytd_credits
                if "Salesman" in ytd_invoices.columns:
                    sm_ytd_invoices = ytd_invoices[
                        ytd_invoices["Salesman"].astype(str).str.strip().str.lower() == sm_lower
                    ].reset_index(drop=True)
                else:
                    sm_ytd_invoices = ytd_invoices

                for period in plan.periods:
                    log.info("Building Shipped Report for %s: %s", sm_display, period.label)
                    period_detail = _filter_to_period(sm_detail, period)

                    if period_detail.empty:
                        log.info("No data for %s, period %s. Skipping.", sm_display, period.label)
                        continue

                    validate_output(period_detail, _EXPECTED_COLS, "Shipped Report")

                    if self.dry_run:
                        log.info("[DRY RUN] Shipped Report %s %s: %d rows -- skipping",
                                 sm_display, period.label, len(period_detail))
                        continue

                    test_tag = "_TEST" if self.test_mode else ""
                    filename = f"Shipped_Report_{period.filename_tag}_{sm_display}{test_tag}.xlsx"
                    out_path = os.path.join(tmp_dir, filename)

                    self._write_period_report(
                        period, sm_detail, sm_ytd_credits, sm_ytd_invoices,
                        period_detail, out_path, "Shipped Report",
                        skip_commissions=True,
                    )
                    log.info("Saved (temp): %s", out_path)

                    self._send_or_queue_email(sm_key, out_path, period.label)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            log.info("Cleaned up temp dir for shipped email-only files")

    def _run_standard(
        self, plan: FetchPlan, company_id: str | None,
        salesman_filter: list[str] | None,
        customer_filter: list[str] | None,
    ) -> None:
        """Standard run: unfiltered or filtered by specific salesman(s)/customer(s).

        Files are saved to disk (Direct Reports).
        """
        is_shipped = bool(salesman_filter)
        display_name = "Shipped Report" if is_shipped else REPORT_NAME
        file_prefix = "Shipped_Report" if is_shipped else "Invoiced_Report"
        report_dir_name = "Salesman Report" if is_shipped else REPORT_NAME
        sub_report = "Shipped Report" if is_shipped else None

        base_url, token, company = self.connect(company_id)

        ytd_start = clamp_start(date(plan.fetch_end.year, 1, 1))
        effective_start = min(plan.fetch_start, ytd_start)
        if effective_start < plan.fetch_start:
            log.info("Fetching invoice data: %s to %s (widened from %s for commissions YTD)",
                     effective_start, plan.fetch_end, plan.fetch_start)
        else:
            log.info("Fetching invoice data: %s to %s", effective_start, plan.fetch_end)
        full_detail = fetch_invoice_detail(base_url, token, effective_start, plan.fetch_end, company)

        if customer_filter and "CustomerAccount" in full_detail.columns:
            accts = full_detail["CustomerAccount"].astype(str).str.strip()
            full_detail = full_detail[accts.isin(customer_filter)].reset_index(drop=True)

        if salesman_filter and "Salesman" in full_detail.columns:
            sm_lower = {s.strip().lower() for s in salesman_filter}
            full_detail = full_detail[
                full_detail["Salesman"].astype(str).str.strip().str.lower().isin(sm_lower)
            ].reset_index(drop=True)

        if full_detail.empty:
            if customer_filter:
                log.info("No invoices found for customer(s) %s. Skipping silently.",
                         ",".join(customer_filter))
            else:
                log.info("No invoices found for fetch range. Exiting.")
            return

        _, _, _, ytd_credits, ytd_invoices = build_invoiced_views(full_detail)

        if customer_filter:
            subfolder_base = "Customer/" + "_".join(customer_filter)
        else:
            subfolder_base = None

        for period in plan.periods:
            log.info("Building %s: %s (%s to %s)", display_name, period.label, period.start_date, period.end_date)
            period_detail = _filter_to_period(full_detail, period)

            if period_detail.empty:
                if customer_filter:
                    log.info("No data for period %s for customer(s) %s. Skipping silently.",
                             period.label, ",".join(customer_filter))
                else:
                    log.info("No data for period %s. Skipping.", period.label)
                continue

            validate_output(period_detail, _EXPECTED_COLS, display_name)

            if self.dry_run:
                log.info("[DRY RUN] %s %s: %d detail rows -- skipping write",
                         display_name, period.label, len(period_detail))
                continue

            suffix_parts = []
            if salesman_filter:
                if len(salesman_filter) == 1:
                    suffix_parts.append(salesman_filter[0])
                else:
                    suffix_parts.append(f"{len(salesman_filter)}salesmen")
            if customer_filter:
                suffix_parts.append("Cust_" + "_".join(customer_filter))
            suffix = ("_" + "_".join(suffix_parts)) if suffix_parts else ""

            test_tag = "_TEST" if self.test_mode else ""
            filename = f"{file_prefix}_{period.filename_tag}{suffix}{test_tag}.xlsx"
            out_subfolder = self._resolve_out_subfolder(period, subfolder_base)
            out_path = get_output_path(report_dir_name, out_subfolder, filename, sub_report=sub_report)

            self._write_period_report(
                period, full_detail, ytd_credits, ytd_invoices,
                period_detail, out_path, display_name,
                skip_commissions=is_shipped,
            )
            log.info("Saved: %s", out_path)

    def run(self, plan: FetchPlan, company_id: str | None = None) -> None:
        cli = getattr(self, "_cli_args", None)
        salesman_filter: list[str] | None = getattr(cli, "salesman", None) if cli else None
        customer_filter: list[str] | None = getattr(cli, "customer", None) if cli else None

        if salesman_filter and len(salesman_filter) == 1 and salesman_filter[0].lower() == "all":
            self._run_for_all_salesmen(plan, company_id, customer_filter)
        else:
            self._run_standard(plan, company_id, salesman_filter, customer_filter)


def _filter_to_period(df, period: PeriodSpec):
    """Filter detail DataFrame to a period's date range."""
    if df.empty or "InvoiceDate" not in df.columns:
        return df

    import pandas as pd
    dates = pd.to_datetime(df["InvoiceDate"], errors="coerce").dt.date
    mask = (dates >= period.start_date) & (dates <= period.end_date)
    return df[mask].copy()


def main(argv=None):
    return InvoicedReportRunner().main(argv)


if __name__ == "__main__":
    sys.exit(main())
