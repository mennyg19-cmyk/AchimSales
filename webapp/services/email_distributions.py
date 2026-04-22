"""
Email distribution engine.

Checks whether each enabled distribution should fire (based on trigger mode,
frequency, and schedule), downloads the report files from SharePoint using
explicit path templates, and sends a bundled email.
"""

import logging
import threading
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

log = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 15 * 60  # 15 minutes
_thread: threading.Thread | None = None

REPORT_KEY_TO_DISPLAY = {
    "ordered": "Ordered Report",
    "invoiced": "Invoiced Report",
    "salesman": "Salesman Report",
    "number_4": "Number 4 Report",
    "amazon_weekly": "Amazon Weekly",
    "customer_activity": "Customer Activity Report",
    "customer_aging": "Customer Aging Report",
}

DEFAULT_PATH_TEMPLATES = {
    "ordered": "Direct Reports/Ordered Report/Daily/Ordered_Report_{yesterday}.xlsx",
    "invoiced": "Direct Reports/Invoiced Report/Daily/{month_folder}/Invoiced_Report_{yesterday}.xlsx",
    "salesman": "Direct Reports/Salesman Report/Daily/Salesman_Report_{yesterday}.xlsx",
    "number_4": "Direct Reports/Number 4 Report/Daily/Number_4_Report_{yesterday}.xlsx",
    "customer_activity": "Direct Reports/Salesman Report/Customer Activity/Customer_Activity_{yesterday}.xlsx",
    "customer_aging": "Direct Reports/Customer Aging Report/Daily/Customer_Aging_{yesterday}.xlsx",
    "amazon_weekly": "Direct Reports/Amazon Weekly/Amazon_Weekly_{yesterday}.xlsx",
}

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _resolve_path_template(template: str, today: date) -> str:
    """Replace variables in a path template.

    Supported variables:
        {yesterday}     -- YYYY-MM-DD (one day before today)
        {today}         -- YYYY-MM-DD
        {date}          -- alias for {yesterday}
        {month_folder}  -- YYYY-MM Mon (e.g. '2026-03 Mar') based on yesterday's date
        {year}          -- YYYY based on yesterday's date
        {month}         -- MM based on yesterday's date

    Also ensures the SharePoint drive root prefix (e.g. 'D365 F&O/') is present
    so templates like 'Direct Reports/...' work even without the prefix.
    """
    import os
    drive_root = os.environ.get("DriveRootPath", "D365 F&O").strip().strip("/")

    yesterday_date = today - timedelta(days=1)
    yesterday = yesterday_date.isoformat()
    today_str = today.isoformat()
    month_folder = f"{yesterday_date.strftime('%Y-%m')} {MONTH_ABBR[yesterday_date.month - 1]}"

    resolved = (template
                .replace("{yesterday}", yesterday)
                .replace("{today}", today_str)
                .replace("{date}", yesterday)
                .replace("{month_folder}", month_folder)
                .replace("{year}", str(yesterday_date.year))
                .replace("{month}", f"{yesterday_date.month:02d}"))

    if drive_root and not resolved.startswith(drive_root):
        resolved = f"{drive_root}/{resolved.lstrip('/')}"

    return resolved


def _reports_completed_today(required_keys: list[dict], today_str: str) -> bool:
    """Check runbook_history for today: have all required reports completed?"""
    from webapp.db import get_db
    conn = get_db()
    try:
        for rk in required_keys:
            display_name = REPORT_KEY_TO_DISPLAY.get(rk["report_key"])
            if not display_name:
                log.warning("Unknown report_key: %s", rk["report_key"])
                return False

            row = conn.execute(
                """SELECT id FROM runbook_history
                   WHERE report_name = ?
                     AND status IN ('SUCCESS', 'Completed')
                     AND DATE(timestamp) = ?
                   LIMIT 1""",
                (display_name, today_str),
            ).fetchone()

            if not row:
                return False
        return True
    finally:
        conn.close()


def _is_shabbos_yomtov_today(required_keys: list[dict], today_str: str) -> bool:
    """Check if any required report was SKIPPED or RESCHEDULED today (Shabbos/YT guard)."""
    from webapp.db import get_db
    conn = get_db()
    try:
        for rk in required_keys:
            display_name = REPORT_KEY_TO_DISPLAY.get(rk["report_key"])
            if not display_name:
                continue
            row = conn.execute(
                """SELECT id FROM runbook_history
                   WHERE report_name = ?
                     AND status IN ('SKIPPED', 'RESCHEDULED')
                     AND DATE(timestamp) = ?
                   LIMIT 1""",
                (display_name, today_str),
            ).fetchone()
            if row:
                return True
        return False
    finally:
        conn.close()


def _matches_frequency(dist: dict, today: date) -> bool:
    """Check if today matches the distribution's frequency/day filter."""
    freq = dist.get("frequency", "daily")
    if freq == "daily":
        return True
    if freq == "weekly":
        allowed = [d.strip() for d in (dist.get("days_of_week") or "").split(",") if d.strip()]
        if not allowed:
            return True
        return DAY_NAMES[today.weekday()] in allowed
    if freq == "monthly":
        allowed = [d.strip() for d in (dist.get("month_days") or "").split(",") if d.strip()]
        if not allowed:
            return True
        return str(today.day) in allowed
    return True


def _was_skipped_today(dist_id: int, today_str: str, reason_prefix: str) -> bool:
    """Check if a 'skipped' log entry already exists today with the given reason prefix."""
    from webapp.db import get_db
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id FROM email_distribution_log WHERE distribution_id = ? AND sent_date = ? AND status = 'skipped'",
            (dist_id, today_str),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _past_send_time(dist: dict, now: datetime) -> bool:
    """For scheduled trigger mode, check if we're past the configured send_time."""
    send_time_str = (dist.get("send_time") or "").strip()
    if not send_time_str:
        return True
    try:
        parts = send_time_str.split(":")
        hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        return now.hour > hour or (now.hour == hour and now.minute >= minute)
    except (ValueError, IndexError):
        return True


REPORT_FILE_PREFIXES = {
    "ordered": "Ordered_Report_",
    "invoiced": "Invoiced_Report_",
    "salesman": "Salesman_Report_",
    "number_4": "Number_4_Report_",
    "customer_activity": "Customer_Activity_",
    "customer_aging": "Customer_Aging_",
    "amazon_weekly": "Amazon_Weekly_",
}


def _find_latest_in_folder(folder_path: str, prefix: str, yesterday: date) -> tuple[str, bytes] | None:
    """Fallback: list the SharePoint folder and find the most recent file
    whose name starts with *prefix* and whose date range includes *yesterday*.

    Handles both normal files (``Ordered_Report_2026-03-22.xlsx``) and
    catch-up files (``Ordered_Report_2026-03-20_to_2026-03-22.xlsx``).
    """
    from webapp.services.sharepoint import list_children, download_file_content
    import re

    items = list_children(folder_path)
    if not items:
        return None

    y_str = yesterday.isoformat()
    candidates: list[dict] = []

    for item in items:
        name = item.get("name", "")
        if not name.startswith(prefix) or not name.endswith(".xlsx"):
            continue

        stem = name[len(prefix):-5]  # strip prefix and .xlsx

        range_match = re.match(r"(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})", stem)
        if range_match:
            from_d, to_d = range_match.group(1), range_match.group(2)
            if from_d <= y_str <= to_d:
                candidates.append(item)
                continue
        elif re.match(r"\d{4}-\d{2}-\d{2}$", stem):
            if stem == y_str:
                candidates.append(item)
                continue

    if not candidates:
        return None

    candidates.sort(key=lambda c: c.get("lastModifiedDateTime", ""), reverse=True)
    best = candidates[0]
    fname = best["name"]
    item_id = best["id"]
    log.info("Fallback: found '%s' in folder listing (id=%s)", fname, item_id)
    content = download_file_content(item_id)
    return fname, content


def _download_report_files(
    required_keys: list[dict], today: date
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Download report files from SharePoint using explicit path templates.

    Returns (attachments, errors) where attachments is list of (filename, bytes)
    and errors is list of human-readable error strings per failed file.

    When the exact template path returns 404 (e.g. after a catch-up run that
    used a date-range filename), falls back to listing the parent folder and
    finding the latest file whose name matches the report prefix and covers
    yesterday's date.
    """
    from webapp.services.sharepoint import download_file_by_path

    attachments: list[tuple[str, bytes]] = []
    errors: list[str] = []
    yesterday = today - timedelta(days=1)

    for rk in required_keys:
        report_key = rk["report_key"]
        template = (rk.get("file_path_template") or "").strip()
        if not template:
            template = DEFAULT_PATH_TEMPLATES.get(report_key, "")
        if not template:
            errors.append(f"{report_key}: no file path template configured")
            continue

        resolved = _resolve_path_template(template, today)
        filename = resolved.rsplit("/", 1)[-1] if "/" in resolved else resolved

        try:
            content = download_file_by_path(resolved)
            attachments.append((filename, content))
            log.info("Downloaded %s (%d bytes) for distribution", filename, len(content))
        except Exception as e:
            log.info("Exact path failed for %s ('%s': %s), trying folder fallback...",
                     report_key, resolved, e)
            folder_path = resolved.rsplit("/", 1)[0] if "/" in resolved else ""
            prefix = REPORT_FILE_PREFIXES.get(report_key, "")
            if folder_path and prefix:
                try:
                    result = _find_latest_in_folder(folder_path, prefix, yesterday)
                    if result:
                        attachments.append(result)
                        log.info("Fallback succeeded: %s (%d bytes)", result[0], len(result[1]))
                        continue
                except Exception as e2:
                    log.warning("Folder fallback also failed for %s: %s", report_key, e2)

            msg = f"{report_key}: file not found at '{resolved}' ({e})"
            log.warning("Failed to download: %s", msg)
            errors.append(msg)

    return attachments, errors


def send_distribution(dist: dict, today_str: str, force: bool = False) -> dict:
    """Process a single distribution: download files and send email.

    Args:
        dist: Distribution dict from get_all_distributions / get_distribution_by_id
        today_str: Date string (YYYY-MM-DD)
        force: If True, skip the readiness check

    Returns dict with "success", "error", "reports_sent".
    """
    from webapp.db import was_distribution_sent_today, log_distribution_send
    from core.email_report import send_multi_attachment_email

    dist_id = dist["id"]
    name = dist["name"]
    required = dist["report_keys"]
    today = date.fromisoformat(today_str)

    if not force:
        if was_distribution_sent_today(dist_id, today_str):
            return {"success": False, "error": "Already sent today", "reports_sent": []}

        trigger = dist.get("trigger_mode", "after_reports")
        if trigger != "scheduled" and not _reports_completed_today(required, today_str):
            return {"success": False, "error": "Not all reports completed yet", "reports_sent": []}

    try:
        attachments, download_errors = _download_report_files(required, today)
    except Exception as e:
        error_msg = f"Failed to download files: {e}"
        log.exception("Distribution '%s': %s", name, error_msg)
        log_distribution_send(dist_id, today_str, "failed", [], error=error_msg)
        return {"success": False, "error": error_msg, "reports_sent": []}

    if not attachments:
        detail = "; ".join(download_errors) if download_errors else "No path templates configured"
        error_msg = f"No report files downloaded. {detail}"
        log.warning("Distribution '%s': %s", name, error_msg)
        log_distribution_send(dist_id, today_str, "failed", [], error=error_msg)
        return {"success": False, "error": error_msg, "reports_sent": []}

    subject = dist.get("subject_template", "Daily Reports - {date}").replace("{date}", today_str)
    body = dist.get("body_template", "") or f"Attached are your reports for {today_str}."
    body = body.replace("{date}", today_str)

    try:
        send_multi_attachment_email(
            attachments=attachments,
            subject=subject,
            body=body,
            recipients=dist["recipients"],
            cc=dist.get("cc") or None,
        )
    except Exception as e:
        error_msg = f"Failed to send email: {e}"
        log.exception("Distribution '%s': %s", name, error_msg)
        filenames = [a[0] for a in attachments]
        log_distribution_send(dist_id, today_str, "failed", filenames, error=error_msg)
        return {"success": False, "error": error_msg, "reports_sent": filenames}

    filenames = [a[0] for a in attachments]
    log_distribution_send(dist_id, today_str, "sent", filenames)
    log.info("Distribution '%s' sent to %s with %d files", name, dist["recipients"], len(filenames))
    return {"success": True, "error": None, "reports_sent": filenames}


def check_and_send_distributions():
    """Check all enabled distributions and send any that are ready."""
    from webapp.db import get_all_distributions, was_distribution_sent_today, log_distribution_send

    now = datetime.now(EASTERN)
    today = now.date()
    today_str = today.isoformat()
    distributions = get_all_distributions()
    sent_count = 0

    log.info("=== Distribution check at %s (Eastern) | today=%s | %d distribution(s) found ===",
             now.strftime("%Y-%m-%d %H:%M:%S"), today_str, len(distributions))

    for dist in distributions:
        dist_id = dist["id"]
        name = dist["name"]

        if not dist["enabled"]:
            log.info("  [%s] SKIP: disabled", name)
            continue
        if not dist["report_keys"]:
            log.info("  [%s] SKIP: no report_keys", name)
            continue
        if was_distribution_sent_today(dist_id, today_str):
            log.info("  [%s] SKIP: already sent today", name)
            continue

        if not _matches_frequency(dist, today):
            if not _was_skipped_today(dist_id, today_str, "Not scheduled today (frequency filter)"):
                log_distribution_send(dist_id, today_str, "skipped", [],
                                      error="Not scheduled today (frequency filter)")
            log.info("  [%s] SKIP: frequency filter (freq=%s, days_of_week=%s, month_days=%s)",
                     name, dist.get("frequency"), dist.get("days_of_week"), dist.get("month_days"))
            continue

        if _is_shabbos_yomtov_today(dist["report_keys"], today_str):
            if not _was_skipped_today(dist_id, today_str, "Shabbos/Yom Tov"):
                log_distribution_send(dist_id, today_str, "skipped", [],
                                      error="Shabbos/Yom Tov -- reports were skipped today")
            log.info("  [%s] SKIP: Shabbos/YT", name)
            continue

        trigger = dist.get("trigger_mode", "after_reports")
        log.info("  [%s] trigger=%s, send_time=%s, enabled=%s",
                 name, trigger, dist.get("send_time"), dist.get("enabled"))

        if trigger == "after_reports":
            if not _reports_completed_today(dist["report_keys"], today_str):
                log.info("  [%s] SKIP: reports not completed yet (after_reports mode)", name)
                continue
        elif trigger == "scheduled":
            past = _past_send_time(dist, now)
            log.info("  [%s] scheduled mode: send_time=%s, now=%s, past_send_time=%s",
                     name, dist.get("send_time"), now.strftime("%H:%M"), past)
            if not past:
                log.info("  [%s] SKIP: not past send time yet", name)
                continue
        else:
            if not _reports_completed_today(dist["report_keys"], today_str):
                log.info("  [%s] SKIP: reports not completed (unknown trigger '%s')", name, trigger)
                continue

        log.info("  [%s] READY -- calling send_distribution...", name)
        result = send_distribution(dist, today_str)
        log.info("  [%s] send result: success=%s, error=%s, reports=%s",
                 name, result.get("success"), result.get("error"), result.get("reports_sent"))
        if result["success"]:
            sent_count += 1

    log.info("=== Distribution check complete: %d sent ===", sent_count)
    return sent_count


def send_distribution_now(dist_id: int) -> dict:
    """Manual trigger: send a distribution immediately regardless of readiness."""
    from webapp.db import get_distribution_by_id

    dist = get_distribution_by_id(dist_id)
    if not dist:
        return {"success": False, "error": "Distribution not found", "reports_sent": []}

    today_str = datetime.now(EASTERN).date().isoformat()
    return send_distribution(dist, today_str, force=True)


def _sync_runbook_history_if_needed():
    """Sync runbook history from Azure/SharePoint so _reports_completed_today works.

    The runbook_history table is populated by sync_runbook_history() which
    normally runs on the dashboard refresh cycle (every 4 hours).  The email
    distribution loop runs every 15 minutes, so we need a fresh sync each
    cycle to detect newly completed reports promptly.
    """
    try:
        from webapp.dashboard_data import sync_runbook_history
        sync_runbook_history()
    except Exception:
        log.exception("Runbook history sync failed (non-fatal, will retry next cycle)")


def _distribution_check_loop():
    """Background loop that checks distributions periodically."""
    log.info("Distribution check loop started. Interval: %ds. Sleeping before first check...",
             CHECK_INTERVAL_SECONDS)
    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)
        try:
            now = datetime.now(EASTERN)
            hour = now.hour
            log.info("Distribution loop woke up at %s Eastern (hour=%d)",
                     now.strftime("%Y-%m-%d %H:%M:%S"), hour)
            if hour < 6 or hour >= 20:
                log.info("Outside active hours (6-20), skipping.")
                continue
            _sync_runbook_history_if_needed()
            sent = check_and_send_distributions()
            if sent:
                log.info("Distribution check: sent %d distribution(s)", sent)
        except Exception:
            log.exception("Distribution check loop error")


def start_distribution_check():
    """Start the background distribution checker thread."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_distribution_check_loop, daemon=True,
                               name="email-distribution-check")
    _thread.start()
    log.info("Email distribution check thread started (interval: %ds)", CHECK_INTERVAL_SECONDS)
