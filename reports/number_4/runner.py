"""
Number 4 Report runner.

Orchestrates: fetch invoice lines from D365 -> aggregate -> write By Item + By Customer.
Smart fetch: no args = single YTD pull (12-month window), filter for each period.
"""

import gc
import logging
import sys
from datetime import date, datetime

from config.paths import get_output_path
from core.dates import FetchPlan, clamp_start, get_today_eastern
from core.logging import setup_logging
from core.validation import validate_output
from reports.base import BaseReportRunner
from reports.number_4.aggregator import (
    aggregate_by_item_customer,
    build_month_labels,
    rolling_12_months,
    ytd_months,
)
from reports.number_4.loader import fetch_number_4_data
from reports.number_4.writer_customer import write_by_customer
from reports.number_4.writer_item import write_by_item

log = logging.getLogger(__name__)

REPORT_NAME = "Number 4 Report"


class Number4ReportRunner(BaseReportRunner):
    report_name = REPORT_NAME

    def run(self, plan: FetchPlan, company_id: str | None = None) -> None:
        base_url, token, company = self.connect(company_id)

        today = get_today_eastern()
        report_date = datetime(today.year, today.month, today.day)

        fetch_start = clamp_start(date(today.year - 1, today.month, 1))
        fetch_end = plan.fetch_end

        log.info("Fetching invoice lines: %s to %s", fetch_start, fetch_end)
        lines = fetch_number_4_data(base_url, token, fetch_start, fetch_end, company)

        if lines.empty:
            log.info("No invoice lines found. Exiting.")
            return

        _EXPECTED_COLS = [
            "InvoiceNumber", "InvoiceDate", "CustomerAccount", "CustomerName", "Salesman",
        ]
        validate_output(lines, _EXPECTED_COLS, REPORT_NAME)

        months_12 = rolling_12_months(report_date)
        months_ytd = ytd_months(report_date)

        agg_12, qty_12, dol_12 = aggregate_by_item_customer(lines, months_12)
        labels_12 = build_month_labels(months_12)
        gc.collect()

        lines_ytd = lines[
            (lines["InvoiceDate"].dt.year == today.year) &
            (lines["InvoiceDate"].dt.month <= today.month)
        ].copy()
        agg_ytd, qty_ytd, dol_ytd = aggregate_by_item_customer(lines_ytd, months_ytd)
        labels_ytd = build_month_labels(months_ytd)
        del lines_ytd
        gc.collect()

        if self.dry_run:
            log.info("[DRY RUN] %s: %d raw lines -- skipping write", REPORT_NAME, len(lines))
        else:
            date_tag = today.isoformat()
            test_tag = "_TEST" if self.test_mode else ""

            item_filename = f"Number_4_Report_Item_{date_tag}{test_tag}.xlsx"
            item_path = get_output_path(REPORT_NAME, "", item_filename, sub_report="By Item")
            log.info("Writing By Item: %s", item_path)
            write_by_item(agg_12, labels_12, qty_12, dol_12, agg_ytd, labels_ytd, qty_ytd, dol_ytd, item_path)

            cust_filename = f"Number_4_Report_Customer_{date_tag}{test_tag}.xlsx"
            cust_path = get_output_path(REPORT_NAME, "", cust_filename, sub_report="By Customer")
            log.info("Writing By Customer: %s", cust_path)
            write_by_customer(agg_12, labels_12, qty_12, dol_12, agg_ytd, labels_ytd, qty_ytd, dol_ytd, cust_path)

            log.info("Saved: %s and %s", item_path, cust_path)

        del lines, agg_12, agg_ytd
        gc.collect()


def main(argv=None):
    return Number4ReportRunner().main(argv)


if __name__ == "__main__":
    sys.exit(main())
