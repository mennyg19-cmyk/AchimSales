"""
Customer Activity Report runner.

Orchestrates: fetch from D365 -> build activity metrics -> write Excel
-> optionally email each salesman -> save management report.

Unlike other reports, this has no period concept -- it covers all time.
"""

import argparse
import logging
import os
import sys

from config.paths import get_output_path
from config.salesman_excel import get_salesman_email, load_salesman_map, lookup_salesman_xl, wants_report
from config.settings import (
    get_client_id,
    get_client_secret,
    get_company_id,
    get_d365_env_url,
    get_graph_email_from,
    get_tenant_id,
    validate_d365_config,
)
from core.auth import get_d365_token
from core.dates import get_today_eastern
from core.logging import setup_logging
from reports.customer_activity.builder import build_customer_activity, fetch_all_data, split_by_salesman
from reports.customer_activity.writer import write_individual_report, write_management_report

log = logging.getLogger(__name__)

REPORT_NAME = "Customer Activity Report"


def _send_individual_emails(per_salesman_files: dict[str, str],
                            test_override: str | None = None) -> None:
    """Email each salesman their individual report file.

    If ``test_override`` is a non-empty email address, all salesman emails
    are redirected there instead of the real salesman addresses.
    """
    from core.email_report import send_report_email

    from_addr = get_graph_email_from()
    if not from_addr:
        log.warning("No GRAPH_EMAIL_FROM configured -- skipping individual emails")
        return

    salesman_map = load_salesman_map()
    today = get_today_eastern()
    subject = f"Customer Activity Report - {today.strftime('%B %Y')}"

    for display_name, file_path in per_salesman_files.items():
        sg_key = None
        for k, v in salesman_map.items():
            if v.display_name == display_name:
                sg_key = k
                break

        if not sg_key:
            log.info("No salesman key found for %s -- skipping email", display_name)
            continue

        if not wants_report(sg_key, "customer_activity"):
            log.info("%s opted out of Customer Activity Report -- skipping", display_name)
            continue

        email = test_override if test_override else get_salesman_email(sg_key)
        if not email:
            log.info("No email for %s -- skipping", display_name)
            continue

        body = (
            f"Hi {lookup_salesman_xl(sg_key).full_name},\n\n"
            f"Attached is your Customer Activity Report for {today.strftime('%B %Y')}.\n\n"
            "This report lists each of your customers with their most recent order "
            "details, including order date, total, PO #, and sales order number.\n\n"
            "Best regards,\nReports Team"
        )

        try:
            send_report_email(
                file_path=file_path,
                subject=subject,
                body=body,
                recipients=[email],
            )
            log.info("Emailed report to %s (%s)", display_name, email)
        except Exception:
            log.exception("Failed to email report to %s (%s)", display_name, email)


def _send_master_report_emails(mgmt_path: str, today, test_override: str | None = None) -> None:
    """Email the master customer activity report to master_customer_activity subscribers."""
    from core.email_report import send_report_email
    from config.salesman_excel import get_report_subscribers

    subscribers = get_report_subscribers("master_customer_activity")
    if not subscribers:
        log.info("No subscribers for master customer activity report")
        return

    subject = f"Customer Activity Report - All Salesmen ({today.strftime('%B %Y')})"
    body = (
        f"Attached is the full Customer Activity Report for {today.strftime('%B %Y')}.\n\n"
        "This report covers all salesmen and their customer activity."
    )

    for display_name, email in subscribers:
        recipient = test_override if test_override else email
        try:
            send_report_email(
                file_path=mgmt_path, subject=subject, body=body,
                recipients=[recipient],
            )
            log.info("Emailed master customer activity report to %s (%s)", display_name, recipient)
        except Exception:
            log.exception("Failed to email master customer activity report to %s (%s)", display_name, recipient)


def run(send_email: bool = False, test_mode: bool = False) -> int:
    """Run the Customer Activity Report."""
    setup_logging()
    log.info("=== %s starting ===", REPORT_NAME)

    test_override: str | None = None
    if test_mode:
        from config.settings import get_test_email
        test_override = get_test_email() or None
        if test_override:
            log.info("[TEST] Email recipients will be overridden to: %s", test_override)
        else:
            log.warning("[TEST] --test flag passed but TEST_EMAIL is not configured")

    try:
        validate_d365_config()
        env_url = get_d365_env_url().rstrip("/")
        base_url = f"{env_url}/data/" if "/data" not in env_url.lower() else (env_url if env_url.endswith("/") else f"{env_url}/")

        token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), env_url)
        company = get_company_id() or None

        log.info("Fetching data from D365")
        customers_df, headers_df = fetch_all_data(base_url, token, company_id=company)

        if customers_df.empty:
            log.info("No customers found. Nothing to report.")
            return 0

        log.info("Building customer activity metrics")
        activity_df = build_customer_activity(customers_df, headers_df)

        if activity_df.empty:
            log.info("No customer activity data. Nothing to report.")
            return 0

        per_salesman, unassigned_df = split_by_salesman(activity_df)
        today = get_today_eastern()

        month_folder = f"{today.strftime('%B')} {today.year}"
        test_tag = "_TEST" if test_mode else ""

        per_salesman_files: dict[str, str] = {}
        for display_name, df in per_salesman.items():
            filename = f"Customer_Activity_{display_name}_{today.isoformat()}{test_tag}.xlsx"
            out_path = get_output_path(
                "Salesman Report", month_folder, filename,
                sub_report="Customer Activity",
            )
            write_individual_report(df, display_name, out_path)
            per_salesman_files[display_name] = out_path

        mgmt_filename = f"Customer_Activity_All_{today.isoformat()}{test_tag}.xlsx"
        mgmt_path = get_output_path(
            "Salesman Report", month_folder, mgmt_filename,
            sub_report="Customer Activity",
        )
        write_management_report(per_salesman, mgmt_path, unassigned_df=unassigned_df)

        if send_email:
            log.info("Sending individual emails to salesmen")
            _send_individual_emails(per_salesman_files, test_override=test_override)
            _send_master_report_emails(mgmt_path, today, test_override=test_override)

        log.info("=== %s completed successfully ===", REPORT_NAME)
        return 0

    except Exception:
        log.exception("%s failed", REPORT_NAME)
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=REPORT_NAME)
    parser.add_argument("--email", action="store_true", help="Send individual reports to salesmen by email")
    parser.add_argument("--company", type=str, default=None, help="D365 company ID (optional)")
    parser.add_argument("--test", dest="test", action="store_true", default=False,
                        help="Test mode: append _TEST to filenames and override email recipients to TEST_EMAIL")
    args = parser.parse_args(argv)

    if args.company:
        os.environ["D365_COMPANY_ID"] = args.company

    return run(send_email=args.email, test_mode=args.test)


if __name__ == "__main__":
    sys.exit(main())
