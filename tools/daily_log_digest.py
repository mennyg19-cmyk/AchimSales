"""
Daily run-log digest + rotation.

# === What's in this file ===
#
# parse_log()         -- Read run_log.csv into a list of dicts
# find_failures()     -- Find STARTED rows with no matching SUCCESS in a time window
# build_digest_html() -- Build the HTML email body (failures or all-clear)
# rotate_log()        -- Keep last N days in run_log.csv, archive older rows
# main()              -- CLI entry point: parse, digest, rotate, email
#
# Designed to run daily from Azure Automation (schedule it for ~10am after
# the overnight reports finish). Can also be run locally for testing.
#
# Usage:
#   python -m tools.daily_log_digest                   # default: 24h window, 90-day retention
#   python -m tools.daily_log_digest --hours 48        # look back 48 hours
#   python -m tools.daily_log_digest --retention 60    # keep 60 days in active log
#   python -m tools.daily_log_digest --dry-run         # print digest, don't email or rotate
"""

import argparse
import csv
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta
from html import escape

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from config.settings import get_alert_recipients
from core.email_report import send_report_email
from core.logging import setup_logging

log = logging.getLogger(__name__)

LOG_COLUMNS = ["timestamp", "report_name", "status", "duration_sec",
               "rows_output", "files_uploaded", "args", "error"]

DEFAULT_HOURS = 24
DEFAULT_RETENTION_DAYS = 90


def parse_log(log_path: str) -> list[dict]:
    """Read run_log.csv into a list of row dicts."""
    rows = []
    if not os.path.exists(log_path):
        return rows
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_raw = (row.get("timestamp") or "").strip()
            if ts_raw:
                try:
                    row["_dt"] = datetime.strptime(ts_raw[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    row["_dt"] = None
            else:
                row["_dt"] = None
            rows.append(row)
    return rows


def find_failures(rows: list[dict], cutoff: datetime) -> list[dict]:
    """Find STARTED rows in the window that never got a SUCCESS.

    A STARTED row is 'unmatched' if no later row with the same report_name
    and base args has status SUCCESS.  This catches both outright failures
    (FAILED status) and silent hangs (STARTED with no follow-up).
    """
    recent = [r for r in rows if r.get("_dt") and r["_dt"] >= cutoff]

    started: list[dict] = []
    successes: set[tuple] = set()

    for r in recent:
        status = (r.get("status") or "").strip().upper()
        key = (
            (r.get("report_name") or "").strip(),
            (r.get("args") or "").strip(),
        )
        if status == "SUCCESS":
            successes.add(key)
        elif status == "STARTED":
            started.append(r)

    failures = []
    for r in started:
        key = (
            (r.get("report_name") or "").strip(),
            (r.get("args") or "").strip(),
        )
        if key not in successes:
            failures.append(r)

    return failures


def build_digest_html(
    failures: list[dict],
    hours: int,
    total_runs: int,
    log_line_count: int,
    archive_count: int,
) -> str:
    """Build the HTML email body."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if failures:
        status_color = "#c62828"
        status_text = f"{len(failures)} report run(s) without a SUCCESS"
        rows_html = ""
        for f in failures:
            rows_html += (
                f"<tr>"
                f"<td style='padding:4px 8px;border:1px solid #ddd'>{escape(f.get('timestamp',''))}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd'>{escape(f.get('report_name',''))}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd'>{escape(f.get('args',''))}</td>"
                f"<td style='padding:4px 8px;border:1px solid #ddd'>{escape(f.get('error',''))}</td>"
                f"</tr>\n"
            )
        table = f"""
        <table style="border-collapse:collapse;margin:12px 0;font-size:13px">
          <tr style="background:#f5f5f5">
            <th style="padding:4px 8px;border:1px solid #ddd;text-align:left">Timestamp</th>
            <th style="padding:4px 8px;border:1px solid #ddd;text-align:left">Report</th>
            <th style="padding:4px 8px;border:1px solid #ddd;text-align:left">Args</th>
            <th style="padding:4px 8px;border:1px solid #ddd;text-align:left">Error</th>
          </tr>
          {rows_html}
        </table>"""
    else:
        status_color = "#2e7d32"
        status_text = "All report runs succeeded"
        table = ""

    archive_note = ""
    if archive_count > 0:
        archive_note = f"<p style='font-size:12px;color:#888'>Archived {archive_count} old log entries (older than retention window).</p>"

    return f"""\
<div style="font-family:Segoe UI,Calibri,Arial,sans-serif;max-width:700px;margin:0 auto">
  <h2 style="margin:0 0 4px 0;color:#1a237e">Daily Report Digest</h2>
  <p style="margin:0 0 16px 0;color:#555;font-size:13px">{escape(now_str)}</p>

  <p style="font-size:15px;color:{status_color};font-weight:600;margin:0 0 8px 0">
    {escape(status_text)}
  </p>

  <p style="font-size:13px;color:#555;margin:0 0 4px 0">
    Window: last {hours} hours &middot; {total_runs} total runs in window &middot;
    {log_line_count} lines in active log
  </p>

  {table}
  {archive_note}
</div>"""


def rotate_log(log_path: str, retention_days: int) -> int:
    """Move rows older than retention_days from run_log.csv to run_log_archive.csv.

    Returns the number of rows archived.
    """
    if not os.path.exists(log_path):
        return 0

    cutoff = datetime.now() - timedelta(days=retention_days)
    archive_path = os.path.join(os.path.dirname(log_path), "run_log_archive.csv")

    rows = parse_log(log_path)
    keep = []
    archive = []

    for r in rows:
        dt = r.get("_dt")
        if dt and dt < cutoff:
            archive.append(r)
        else:
            keep.append(r)

    if not archive:
        return 0

    archive_exists = os.path.exists(archive_path)
    with open(archive_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS, extrasaction="ignore")
        if not archive_exists:
            writer.writeheader()
        for r in archive:
            writer.writerow({k: r.get(k, "") for k in LOG_COLUMNS})

    tmp = log_path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        writer.writeheader()
        for r in keep:
            writer.writerow({k: r.get(k, "") for k in LOG_COLUMNS})

    shutil.move(tmp, log_path)
    log.info("Rotated log: archived %d rows (before %s), kept %d rows",
             len(archive), cutoff.strftime("%Y-%m-%d"), len(keep))
    return len(archive)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Daily run-log digest + rotation")
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS,
                        help=f"Look-back window in hours (default {DEFAULT_HOURS})")
    parser.add_argument("--retention", type=int, default=DEFAULT_RETENTION_DAYS,
                        help=f"Days to keep in active log (default {DEFAULT_RETENTION_DAYS})")
    parser.add_argument("--log-path", default=None,
                        help="Path to run_log.csv (default: logs/run_log.csv relative to scripts/)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print digest to stdout, don't email or rotate")
    parser.add_argument("--recipients", default=None,
                        help="Override email recipients (semicolon-separated)")
    args = parser.parse_args(argv)

    setup_logging()

    log_path = args.log_path or os.path.join(_SCRIPTS_DIR, "logs", "run_log.csv")
    cutoff = datetime.now() - timedelta(hours=args.hours)

    rows = parse_log(log_path)
    log.info("Parsed %d log rows from %s", len(rows), log_path)

    failures = find_failures(rows, cutoff)
    recent_count = sum(1 for r in rows if r.get("_dt") and r["_dt"] >= cutoff)

    if args.dry_run:
        archive_count = 0
    else:
        archive_count = rotate_log(log_path, args.retention)

    refreshed_rows = parse_log(log_path) if not args.dry_run else rows

    html = build_digest_html(
        failures=failures,
        hours=args.hours,
        total_runs=recent_count,
        log_line_count=len(refreshed_rows),
        archive_count=archive_count,
    )

    if args.dry_run:
        print(html)
        if failures:
            print(f"\n--- {len(failures)} failure(s) found ---")
            for f in failures:
                print(f"  {f.get('timestamp')} | {f.get('report_name')} | {f.get('args','')}")
        else:
            print("\n--- All clear ---")
        return 0

    if not failures:
        log.info("All runs succeeded in the last %d hours -- no alert email needed", args.hours)
        return 0

    recipients = None
    if args.recipients:
        recipients = [r.strip() for r in args.recipients.split(";") if r.strip()]
    else:
        recipients = get_alert_recipients()

    if not recipients:
        log.warning("No recipients configured (set ALERT_RECIPIENTS or pass --recipients)")
        return 1

    subject = f"[ALERT] Daily Report Digest - {datetime.now().strftime('%Y-%m-%d')}"

    send_report_email(
        file_path=None,
        subject=subject,
        body=html,
        recipients=recipients,
        content_type="HTML",
    )
    log.info("Alert email sent to %s (subject: %s)", recipients, subject)
    return 0


if __name__ == "__main__":
    sys.exit(main())
