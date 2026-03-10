"""
Amazon Weekly Report runner.

Same dataset and layout as the Ordered Report, but:
- Single customer: 9300 (Amazon) via direct OData $filter on SalesOrderHeadersV3.
- Single period: this week (Monday through today).
- Output: one Excel file with ordered / shipped / cancelled / remaining.
- Optional: send report by email (e.g. every Friday 5pm).

Usage:
  python -m reports.amazon_weekly.runner              # this week, write Excel
  python -m reports.amazon_weekly.runner --email     # write Excel and email
"""

import logging
import sys

from config.paths import get_output_path
from config.settings import get_client_id, get_client_secret, get_company_id, get_d365_env_url, get_tenant_id, validate_d365_config
from core.auth import get_d365_token
from core.dates import get_today_eastern, get_week_start, parse_period
from core.logging import setup_logging
from reports.ordered.builder import build_report, fetch_all_data
from reports.ordered.writer import write_report

log = logging.getLogger(__name__)

REPORT_NAME = "Amazon Weekly"
AMAZON_CUSTOMER_ACCOUNT = "9300"


def run(send_email: bool = False, test_mode: bool = False) -> None:
    """Fetch Amazon (9300) orders for this week from D365 via direct OData, build report, write Excel, optionally email."""
    validate_d365_config()
    env_url = get_d365_env_url().rstrip("/")
    base_url = f"{env_url}/data/" if "/data" not in env_url.lower() else (env_url if env_url.endswith("/") else f"{env_url}/")

    token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env_url)
    company_id = get_company_id() or None

    test_recipients: list[str] | None = None
    if test_mode:
        from config.settings import get_test_email
        te = get_test_email()
        if te:
            test_recipients = [te]
            log.info("[TEST] Email recipients overridden to: %s", te)
        else:
            log.warning("[TEST] --test flag passed but TEST_EMAIL is not configured")

    period = parse_period("last_7_days", get_today_eastern())
    log.info("Amazon Weekly: fetch %s to %s (customer %s)", period.start_date, period.end_date, AMAZON_CUSTOMER_ACCOUNT)

    headers_df, lines_df, whs_df, ps_df = fetch_all_data(
        base_url, token, period.start_date, period.end_date, company_id, customer_account=AMAZON_CUSTOMER_ACCOUNT
    )

    if headers_df.empty:
        log.info("No Amazon orders found for this week. Exiting.")
        if send_email:
            from core.email_report import send_report_email
            send_report_email(
                file_path=None,
                subject=f"{REPORT_NAME} – No orders this week",
                body=f"No orders for customer {AMAZON_CUSTOMER_ACCOUNT} (Amazon) for week {period.start_date} to {period.end_date}.",
                recipients=test_recipients,
            )
        return

    df, _empty_reason = build_report(headers_df, lines_df, whs_df, ps_df, period)
    if df.empty:
        log.info("No lines after build. Exiting.")
        return

    test_tag = "_TEST" if test_mode else ""
    filename = f"Amazon_Weekly_Report_{period.filename_tag}{test_tag}.xlsx"
    out_path = get_output_path(REPORT_NAME, period.subfolder, filename)
    log.info("Writing %s (%d rows)", out_path, len(df))
    write_report(df, out_path, report_variant="amazon_weekly")
    log.info("Saved: %s", out_path)

    if send_email:
        from core.email_report import send_report_email
        send_report_email(
            file_path=out_path,
            subject=f"{REPORT_NAME} – {period.label} ({period.start_date} to {period.end_date})",
            body=f"Amazon (customer #9300) orders this week: ordered, shipped, cancelled, remaining.\n\nPeriod: {period.start_date} to {period.end_date}.",
            recipients=test_recipients,
        )
        log.info("Email sent.")


def main(argv=None) -> int:
    import argparse
    setup_logging()
    parser = argparse.ArgumentParser(description=REPORT_NAME)
    parser.add_argument("--email", action="store_true", help="Send report by email after generating")
    parser.add_argument("--test", dest="test", action="store_true", default=False,
                        help="Test mode: append _TEST to filenames and override email recipients to TEST_EMAIL")
    args = parser.parse_args(argv or [])
    try:
        run(send_email=args.email, test_mode=args.test)
        return 0
    except Exception:
        log.exception("%s failed", REPORT_NAME)
        return 1


if __name__ == "__main__":
    sys.exit(main())
