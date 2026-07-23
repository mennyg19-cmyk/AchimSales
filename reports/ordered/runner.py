"""
Ordered Report runner.

Orchestrates: fetch from D365 -> build report per period -> write Excel.
Implements smart fetch: no args = single YTD pull, filter for each period.

Supports ``--salesman all`` to iterate over every salesman subscribed to
the ordered report (per ``salesman_map.xlsx``), generating and emailing
a separate report to each.
"""

import logging
import os
import shutil
import sys
import tempfile
from datetime import date

from config.paths import get_output_path
from core.dates import D365_GO_LIVE, FetchPlan, PeriodSpec, get_today_eastern
from core.email_report import send_report_email
from core.logging import setup_logging
from core.validation import validate_output
from reports.base import BaseReportRunner
from reports.ordered.builder import FULL_DATA_ORDER, build_report, fetch_all_data
from reports.ordered.writer import write_report

log = logging.getLogger(__name__)

REPORT_NAME = "Ordered Report"
REPORT_KEY = "ordered"


def _resolve_salesman_email(
    sales_group: str, test_override: str | None = None,
) -> tuple[str | None, list[str], list[str]]:
    """Best-effort lookup of the salesman's email, CC, and BCC.

    Returns (email_or_None, cc_list, bcc_list).
    When ``test_override`` is set, CC/BCC are emptied so test runs don't
    leak emails to real recipients.
    """
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


def _get_filtered_report_recipients() -> list[str]:
    """Recipients for --email on customer-filtered runs (Amazon weekly schedules).

    Always AMAZON_EMAIL_RECIPIENTS — never the salesman-map subscription
    columns, which previously fanned Amazon Weekly out to every rep.
    """
    from config.salesman_excel import get_amazon_weekly_recipients
    return get_amazon_weekly_recipients()


def _get_subscribed_salesmen() -> list[tuple[str, str, str]]:
    """Return [(salesman_key, display_name, email)] for salesmen subscribed to ordered report.

    salesman_key is the normalized key that matches D365's Salesman field
    when both are lowered.
    """
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


def _send_no_data_email(
    salesman_name: str,
    customer_label: str | None,
    period_label: str,
    reason: str,
    test_override: str | None = None,
) -> None:
    """Email the salesman explaining why no report was generated."""
    email, cc, bcc = _resolve_salesman_email(salesman_name, test_override=test_override)
    if not email:
        log.info("No email address for salesman '%s'; skipping no-data notification", salesman_name)
        return

    filter_parts = [f"Salesman: {salesman_name}"]
    if customer_label:
        filter_parts.append(f"Customer(s): {customer_label}")
    filter_summary = ", ".join(filter_parts)

    subject = f"{REPORT_NAME} - No Data Found ({period_label})"
    body = (
        f"Your requested {REPORT_NAME} for period '{period_label}' returned no results.\n\n"
        f"Filters applied: {filter_summary}\n\n"
        f"Reason: {reason}\n\n"
        "Please verify the customer account and salesman combination and try again."
    )

    try:
        send_report_email(file_path=None, subject=subject, body=body,
                          recipients=[email], cc=cc, bcc=bcc)
    except Exception:
        log.exception("Failed to send no-data notification to %s", email)


def _send_salesman_report_email(
    salesman_name: str, file_path: str, period_label: str,
    sharepoint_url: str | None = None,
    test_override: str | None = None,
) -> None:
    """Email a completed report to the salesman."""
    email, cc, bcc = _resolve_salesman_email(salesman_name, test_override=test_override)
    if not email:
        log.info("No email for salesman '%s'; skipping report email", salesman_name)
        return
    subject = f"{REPORT_NAME} - {salesman_name} ({period_label})"
    body = f"Attached is your {REPORT_NAME} for period '{period_label}'."
    if sharepoint_url:
        body += f"\n\nSharePoint link: {sharepoint_url}"
    try:
        send_report_email(file_path=file_path, subject=subject, body=body,
                          recipients=[email], cc=cc, bcc=bcc)
        log.info("Emailed report to %s (%s)", salesman_name, email)
    except Exception:
        log.exception("Failed to email report to %s (%s)", salesman_name, email)


class OrderedReportRunner(BaseReportRunner):
    report_name = REPORT_NAME

    def __init__(self):
        super().__init__()
        self.pending_salesman_emails: list[dict] = []
        self.defer_salesman_emails: bool = False

    def build_arg_parser(self):
        parser = super().build_arg_parser()
        parser.add_argument("--email", action="store_true", default=False,
                            help="Email customer-filtered files to AMAZON_EMAIL_RECIPIENTS "
                                 "(Amazon Weekly schedules).")
        return parser

    @property
    def _send_emails(self) -> bool:
        """True when email was requested and this is not a no-send mode."""
        if self.no_email or self.dry_run:
            return False
        cli = getattr(self, "_cli_args", None)
        return bool(getattr(cli, "email", False))

    @property
    def _test_email_override(self) -> str | None:
        """Return the TEST_EMAIL address when ``--test`` is active, else None."""
        if not self.test_mode:
            return None
        from config.settings import get_test_email
        addr = get_test_email()
        return addr if addr else None

    def _queue_or_send_salesman_email(
        self, salesman_name: str, file_path: str, period_label: str,
        *, force_immediate: bool = False,
    ) -> None:
        """Queue or immediately send a salesman report email.

        When running inside the universal runbook, emails are deferred so the
        runbook can inject SharePoint links after upload.  Use
        ``force_immediate=True`` for email-only files that live in a temp dir
        and will be deleted before flush time.
        """
        if self.defer_salesman_emails and not force_immediate:
            self.pending_salesman_emails.append({
                "salesman": salesman_name,
                "file_path": file_path,
                "period_label": period_label,
            })
            log.info("Deferred salesman email for %s (will send after upload)", salesman_name)
        else:
            _send_salesman_report_email(
                salesman_name, file_path, period_label,
                test_override=self._test_email_override,
            )

    def flush_pending_emails(self, url_map: dict[str, str] | None = None) -> None:
        """Send all deferred salesman emails, optionally with SharePoint URLs.

        url_map: {local_file_path_basename: sharepoint_webUrl}
        """
        url_map = url_map or {}
        test_override = self._test_email_override
        for entry in self.pending_salesman_emails:
            basename = os.path.basename(entry["file_path"])
            sp_url = url_map.get(basename)
            _send_salesman_report_email(
                entry["salesman"], entry["file_path"], entry["period_label"],
                sharepoint_url=sp_url,
                test_override=test_override,
            )
        sent = len(self.pending_salesman_emails)
        self.pending_salesman_emails.clear()
        if sent:
            log.info("Flushed %d deferred salesman emails", sent)

    def _run_for_salesman_list(
        self, salesman_list: list[str], customer_filter: list[str] | None,
        plan: FetchPlan, company_id: str | None,
        status_filter: str | None = None,
    ) -> None:
        """Run the report filtered to specific salesman(s) and/or customer(s).

        Output is always written to disk (Direct Reports). Email-only fan-out
        lives in ``_run_for_all_salesmen`` and is only triggered by
        ``--salesman all``. When a specific-salesman run comes back empty, we
        still send a "no data" notification so the salesman knows their
        requested run returned nothing.
        """
        base_url, token, company = self.connect(company_id)

        is_open = status_filter and status_filter.lower() == "open"
        report_label = "Open Orders Report" if is_open else REPORT_NAME
        file_prefix = "Open_Orders" if is_open else "Ordered_Report"

        if salesman_list:
            out_subfolder = "Salesman"
        elif customer_filter:
            out_subfolder = "Customer/" + "_".join(customer_filter)
        else:
            out_subfolder = "Customer"

        customer_label = ",".join(customer_filter) if customer_filter else "all"
        log.info("Fetching data: %s to %s (customer=%s)", plan.fetch_start, plan.fetch_end, customer_label)
        headers_df, lines_df, whs_df, ps_df = fetch_all_data(
            base_url, token, plan.fetch_start, plan.fetch_end, company,
            customer_account=customer_filter, status_filter=status_filter,
        )

        test_override = self._test_email_override

        if headers_df.empty:
            reason = "No orders found for the requested date range"
            if is_open:
                reason = "No open orders found"
            elif customer_filter:
                reason = f"No orders found for customer(s) '{customer_label}' in the requested date range"
            log.info("%s. Exiting.", reason)
            if customer_filter and not salesman_list:
                if self._send_emails:
                    self._email_filtered_report(
                        file_path=None,
                        subject=f"{report_label} \u2013 No orders ({customer_label})",
                        body=f"{reason}.\n\nPeriod: {plan.fetch_start} to {plan.fetch_end}.",
                    )
                return
            for sm in salesman_list:
                for period in plan.periods:
                    _send_no_data_email(sm, customer_label, period.label, reason,
                                        test_override=test_override)
            return

        for period in plan.periods:
            log.info("Building %s: %s (%s to %s)", report_label, period.label, period.start_date, period.end_date)
            df, empty_reason = build_report(
                headers_df, lines_df, whs_df, ps_df, period,
                salesman_filter=salesman_list,
            )

            if df.empty:
                log.info("No data for period %s: %s", period.label, empty_reason)
                if customer_filter and not salesman_list:
                    continue
                for sm in salesman_list:
                    _send_no_data_email(sm, customer_label, period.label, empty_reason or "No data",
                                        test_override=test_override)
                continue

            suffix_parts = []
            if len(salesman_list) == 1:
                suffix_parts.append(salesman_list[0])
            elif len(salesman_list) > 1:
                suffix_parts.append(f"{len(salesman_list)}salesmen")
            if customer_filter:
                suffix_parts.append("Cust_" + "_".join(customer_filter))
            suffix = ("_" + "_".join(suffix_parts)) if suffix_parts else ""

            validate_output(df, FULL_DATA_ORDER, REPORT_NAME)

            if self.dry_run:
                log.info("[DRY RUN] %s %s: %d rows, %d columns -- skipping write",
                         report_label, period.label, len(df), len(df.columns))
                continue

            test_tag = "_TEST" if self.test_mode else ""
            filename = f"{period.filename_prefix}{file_prefix}_{period.filename_tag}{suffix}{test_tag}.xlsx"
            out_path = get_output_path(REPORT_NAME, out_subfolder, filename)

            log.info("Writing %s (%d rows)", out_path, len(df))
            write_report(df, out_path, report_variant="salesman" if salesman_list else "filtered")
            log.info("Saved: %s", out_path)

            if self._send_emails and customer_filter and not salesman_list:
                self._email_filtered_report(
                    file_path=out_path,
                    subject=f"{report_label} \u2013 {period.label} "
                            f"({period.start_date} to {period.end_date})",
                    body=f"Attached is the {report_label} for customer(s) {customer_label}.\n\n"
                         f"Period: {period.start_date} to {period.end_date}.",
                )

    def _email_filtered_report(self, file_path: str | None, subject: str, body: str) -> None:
        """Email a customer-filtered report (or no-data notice) via AMAZON_EMAIL_RECIPIENTS.

        ``--test`` reroutes to TEST_EMAIL. Never uses salesman-map subscriptions.
        """
        if self.dry_run or self.no_email:
            log.info("[NO SEND] Skipping filtered-report email (dry-run/no-email)")
            return
        test_override = self._test_email_override
        if test_override:
            # TEST_EMAIL may hold several addresses joined with ';'
            recipients = [a.strip() for a in test_override.split(";") if a.strip()]
        else:
            recipients = _get_filtered_report_recipients()
        if not recipients:
            log.warning("Filtered-report email skipped: no AMAZON_EMAIL_RECIPIENTS configured")
            return
        try:
            send_report_email(file_path=file_path, subject=subject, body=body,
                              recipients=recipients)
            log.info("Emailed filtered report to %s", recipients)
        except Exception:
            log.exception("Failed to email filtered report")

    def _run_for_all_salesmen(
        self, customer_filter: list[str] | None,
        plan: FetchPlan, company_id: str | None,
        status_filter: str | None = None,
    ) -> None:
        """Run a separate filtered report for each subscribed salesman.

        By default files are email-only (temp dir -> email -> delete).
        With ``--no-email``, files are saved to the normal output directory
        so they can be reviewed without sending anything.
        """
        subscribed = _get_subscribed_salesmen()
        if not subscribed:
            log.warning("No salesmen subscribed to '%s' in salesman_map.xlsx", REPORT_KEY)
            return

        is_open = status_filter and status_filter.lower() == "open"
        report_label = "Open Orders Report" if is_open else REPORT_NAME
        file_prefix = "Open_Orders" if is_open else "Ordered_Report"

        save_to_disk = self.no_email
        mode_label = "files-to-disk" if save_to_disk else "email-only"
        log.info("Running %s for %d subscribed salesmen (%s)", report_label, len(subscribed), mode_label)

        base_url, token, company = self.connect(company_id)

        customer_label = ",".join(customer_filter) if customer_filter else "all"
        log.info("Fetching data: %s to %s (customer=%s)", plan.fetch_start, plan.fetch_end, customer_label)
        headers_df, lines_df, whs_df, ps_df = fetch_all_data(
            base_url, token, plan.fetch_start, plan.fetch_end, company,
            customer_account=customer_filter, status_filter=status_filter,
        )

        test_override = self._test_email_override

        if headers_df.empty:
            reason = "No open orders found" if is_open else "No orders found for the requested date range"
            if customer_filter and not is_open:
                reason = f"No orders found for customer(s) '{customer_label}' in the requested date range"
            log.info("%s. Exiting.", reason)
            if not save_to_disk:
                for sm_key, _, _ in subscribed:
                    for period in plan.periods:
                        _send_no_data_email(sm_key, customer_label, period.label, reason,
                                            test_override=test_override)
            return

        tmp_dir = None if save_to_disk else tempfile.mkdtemp(prefix="ordered_sm_all_")
        try:
            for sm_idx, (sm_key, sm_display, sm_email) in enumerate(subscribed):
                log.info("--- Salesman %d/%d: %s (%s) ---", sm_idx + 1, len(subscribed), sm_display, sm_email)

                for period in plan.periods:
                    log.info("Building %s for %s: %s", report_label, sm_display, period.label)
                    df, empty_reason = build_report(
                        headers_df, lines_df, whs_df, ps_df, period,
                        salesman_filter=sm_key,
                    )

                    if df.empty:
                        log.info("No data for %s, period %s: %s", sm_display, period.label, empty_reason)
                        if not save_to_disk:
                            _send_no_data_email(sm_key, customer_label, period.label, empty_reason or "No data",
                                                test_override=test_override)
                        continue

                    validate_output(df, FULL_DATA_ORDER, REPORT_NAME)

                    if self.dry_run:
                        log.info("[DRY RUN] %s %s %s: %d rows -- skipping write",
                                 report_label, sm_display, period.label, len(df))
                        continue

                    test_tag = "_TEST" if self.test_mode else ""
                    filename = f"{period.filename_prefix}{file_prefix}_{period.filename_tag}_{sm_display}{test_tag}.xlsx"

                    if save_to_disk:
                        out_path = get_output_path(REPORT_NAME, "Salesman", filename)
                    else:
                        out_path = os.path.join(tmp_dir, filename)

                    log.info("Writing %s (%d rows)", out_path, len(df))
                    write_report(df, out_path, report_variant="salesman")
                    log.info("Saved: %s", out_path)

                    if not save_to_disk:
                        self._queue_or_send_salesman_email(
                            sm_key, out_path, period.label, force_immediate=True)
        finally:
            if tmp_dir:
                shutil.rmtree(tmp_dir, ignore_errors=True)
                log.info("Cleaned up temp dir for salesman email-only files")

    def _run_unfiltered(
        self, plan: FetchPlan, company_id: str | None,
        status_filter: str | None = None,
    ) -> None:
        """Run the full report with no salesman/customer filters (all tabs)."""
        base_url, token, company = self.connect(company_id)

        is_open = status_filter and status_filter.lower() == "open"
        report_label = "Open Orders Report" if is_open else REPORT_NAME
        file_prefix = "Open_Orders" if is_open else "Ordered_Report"
        variant = "filtered" if is_open else None

        log.info("Fetching data: %s to %s (customer=all)", plan.fetch_start, plan.fetch_end)
        headers_df, lines_df, whs_df, ps_df = fetch_all_data(
            base_url, token, plan.fetch_start, plan.fetch_end, company,
            status_filter=status_filter,
        )

        if headers_df.empty:
            msg = "No open orders found." if is_open else "No orders found for the requested date range."
            log.info("%s Exiting.", msg)
            return

        for period in plan.periods:
            log.info("Building %s: %s (%s to %s)", report_label, period.label, period.start_date, period.end_date)
            df, empty_reason = build_report(headers_df, lines_df, whs_df, ps_df, period)

            if df.empty:
                log.info("No data for period %s: %s", period.label, empty_reason)
                continue

            validate_output(df, FULL_DATA_ORDER, REPORT_NAME)

            if self.dry_run:
                log.info("[DRY RUN] %s %s: %d rows, %d columns -- skipping write",
                         report_label, period.label, len(df), len(df.columns))
                continue

            test_tag = "_TEST" if self.test_mode else ""
            filename = f"{period.filename_prefix}{file_prefix}_{period.filename_tag}{test_tag}.xlsx"
            out_path = get_output_path(REPORT_NAME, period.subfolder, filename)

            log.info("Writing %s (%d rows)", out_path, len(df))
            write_report(df, out_path, report_variant=variant)
            log.info("Saved: %s", out_path)

    def run(self, plan: FetchPlan, company_id: str | None = None) -> None:
        cli = getattr(self, "_cli_args", None)
        salesman_raw: list[str] | None = getattr(cli, "salesman", None) if cli else None
        customer_filter: list[str] | None = getattr(cli, "customer", None) if cli else None
        status_filter: str | None = getattr(cli, "status", None) if cli else None

        if status_filter and status_filter.lower() == "open":
            has_custom_range = cli and (
                getattr(cli, "from_date", None) or getattr(cli, "to_date", None)
                or getattr(cli, "date", None)
            )
            if not has_custom_range:
                today = get_today_eastern()
                plan = FetchPlan(
                    fetch_start=D365_GO_LIVE,
                    fetch_end=today,
                    periods=[PeriodSpec(
                        label="All Time",
                        start_date=D365_GO_LIVE,
                        end_date=today,
                        subfolder="Open_Orders",
                        filename_tag=today.isoformat(),
                    )],
                )
                log.info("Status filter 'open' with no date args: using all-time range")

        if salesman_raw and len(salesman_raw) == 1 and salesman_raw[0].lower() == "all":
            self._run_for_all_salesmen(customer_filter, plan, company_id, status_filter=status_filter)
        elif salesman_raw or customer_filter:
            self._run_for_salesman_list(salesman_raw or [], customer_filter, plan, company_id, status_filter=status_filter)
        else:
            self._run_unfiltered(plan, company_id, status_filter=status_filter)


def main(argv=None):
    return OrderedReportRunner().main(argv)


if __name__ == "__main__":
    sys.exit(main())
