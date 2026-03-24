"""
Amazon Weekly Report runner.

Same dataset and layout as the Ordered Report, but:
- Customers: 9300 and 9301 (Amazon accounts) via direct OData $filter.
- Period: last 7 days.
- Output: one Excel file with ordered / shipped / cancelled / remaining.
- Optional: send report by email (e.g. every Friday 5pm).
- Recipients: spreadsheet subscribers (Recv_AmazonWeekly column in salesman_map.xlsx),
  falling back to AMAZON_EMAIL_RECIPIENTS env var.

Usage:
  python -m reports.amazon_weekly.runner              # write Excel only
  python -m reports.amazon_weekly.runner --email     # write Excel and email
"""

import logging
import sys

from config.paths import get_output_path
from config.settings import get_client_id, get_client_secret, get_company_id, get_d365_env_url, get_tenant_id, validate_d365_config
from core.auth import D365TokenManager
from core.dates import get_today_eastern, parse_period
from core.logging import setup_logging
from reports.ordered.builder import build_report, fetch_all_data
from reports.ordered.writer import write_report

log = logging.getLogger(__name__)

REPORT_NAME = "Amazon Weekly"
AMAZON_CUSTOMER_ACCOUNTS = ["9300", "9301"]


def _get_email_recipients() -> list[str] | None:
    """Spreadsheet subscribers first, then AMAZON_EMAIL_RECIPIENTS env var fallback."""
    try:
        from config.salesman_excel import get_report_subscribers
        subscribers = get_report_subscribers("amazon_weekly")
        if subscribers:
            return [email for _, email, _, _ in subscribers]
    except Exception:
        log.debug("Could not load spreadsheet subscribers, falling back to env var")
    return None


def run(send_email: bool = False, test_mode: bool = False) -> None:
    """Fetch Amazon orders for last 7 days from D365, build report, write Excel, optionally email."""
    validate_d365_config()
    env_url = get_d365_env_url().rstrip("/")
    base_url = f"{env_url}/data/" if "/data" not in env_url.lower() else (env_url if env_url.endswith("/") else f"{env_url}/")

    token = D365TokenManager(get_tenant_id(), get_client_id(), get_client_secret(), env_url)
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
    acct_str = ", ".join(AMAZON_CUSTOMER_ACCOUNTS)
    log.info("Amazon Weekly: fetch %s to %s (customers %s)", period.start_date, period.end_date, acct_str)

    headers_df, lines_df, whs_df, ps_df = fetch_all_data(
        base_url, token, period.start_date, period.end_date, company_id, customer_account=AMAZON_CUSTOMER_ACCOUNTS
    )

    recipients = test_recipients or (_get_email_recipients() if send_email else None)

    if headers_df.empty:
        log.info("No Amazon orders found for this period. Exiting.")
        if send_email:
            from core.email_report import send_report_email
            send_report_email(
                file_path=None,
                subject=f"{REPORT_NAME} \u2013 No orders this week",
                body=f"No orders for customers {acct_str} (Amazon) for {period.start_date} to {period.end_date}.",
                recipients=recipients,
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
            subject=f"{REPORT_NAME} \u2013 {period.label} ({period.start_date} to {period.end_date})",
            body=f"Amazon (customers {acct_str}) orders: ordered, shipped, cancelled, remaining.\n\nPeriod: {period.start_date} to {period.end_date}.",
            recipients=recipients,
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
