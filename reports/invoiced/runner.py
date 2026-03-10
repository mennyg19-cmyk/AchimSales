"""
Invoiced Report runner.

Orchestrates: fetch from D365 -> aggregate -> write Excel per period.
Smart fetch: no args = single YTD pull, filter for each period.
"""

import logging
import sys
from datetime import date

from config.commission_map import get_commission_pct_map
from config.paths import get_output_path
from core.dates import FetchPlan, PeriodSpec
from core.logging import setup_logging
from core.validation import validate_output
from reports.base import BaseReportRunner
from reports.invoiced.aggregator import build_invoiced_views, build_reversal_audit
from reports.invoiced.loader import fetch_invoice_detail
from reports.invoiced.writer import write_invoiced_report

log = logging.getLogger(__name__)

REPORT_NAME = "Invoiced Report"


class InvoicedReportRunner(BaseReportRunner):
    report_name = REPORT_NAME

    def run(self, plan: FetchPlan, company_id: str | None = None) -> None:
        cli = getattr(self, "_cli_args", None)
        salesman_filter: list[str] | None = getattr(cli, "salesman", None) if cli else None
        customer_filter: list[str] | None = getattr(cli, "customer", None) if cli else None

        is_shipped = bool(salesman_filter)
        display_name = "Shipped Report" if is_shipped else REPORT_NAME
        file_prefix = "Shipped_Report" if is_shipped else "Invoiced_Report"
        report_dir_name = "Shipped Report" if is_shipped else REPORT_NAME

        base_url, token, company = self.connect(company_id)

        ytd_start = date(plan.fetch_end.year, 1, 1)
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

            _EXPECTED_COLS = [
                "CustomerAccount", "CustomerName", "InvoiceDate", "InvoiceNumber",
                "SalesOrderNumber", "SubTotal Invoices", "Total Invoice",
                "Salesman", "SalesmanNumber", "SalesmanName",
            ]
            validate_output(period_detail, _EXPECTED_COLS, display_name)

            summary, commissions, details_net, credits, invoices = build_invoiced_views(period_detail)
            audit = build_reversal_audit(period_detail)

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
            out_subfolder = subfolder_base if subfolder_base else period.subfolder
            out_path = get_output_path(report_dir_name, out_subfolder, filename)

            report_year = period.end_date.year
            pct_map = get_commission_pct_map(report_year)

            log.info("Writing %s (%d detail rows)", out_path, len(period_detail))
            write_invoiced_report(
                summary, commissions, details_net, credits, invoices, audit, out_path,
                year=report_year, full_detail=full_detail,
                ytd_credits=ytd_credits, ytd_invoices=ytd_invoices,
                pct_map=pct_map, current_month=period.end_date.month,
            )
            log.info("Saved: %s", out_path)


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
