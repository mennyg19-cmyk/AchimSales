"""
Base runbook for Azure Automation.

Handles:
1. Download scripts from SharePoint to local temp
2. Run the report
3. Upload outputs to SharePoint Direct Reports folder
4. Cleanup

Also provides:
- Alert-on-failure / alert-on-no-output notifications
- Timing with configurable threshold alerts
- Post-run heartbeat / summary email with params and file links
"""

import logging
import os
import sys
import time
import traceback
from html import escape
from urllib.parse import unquote

from config.settings import (
    get_client_id,
    get_client_secret,
    get_drive_root_path,
    get_sp_site_url,
    get_tenant_id,
    validate_graph_config,
)
from core.alerts import send_alert
from core.auth import get_graph_token, get_graph_token_manager
from core.graph import resolve_site_and_drive, upload_tree
from core.logging import setup_logging

log = logging.getLogger(__name__)

SLOW_THRESHOLD_SECONDS = 30 * 60


def _detect_argv() -> str:
    """Return the CLI args that were passed to this runbook."""
    if len(sys.argv) > 1:
        return " ".join(sys.argv[1:])
    return "(none)"


def run_report_in_runbook(report_runner_class, argv: list[str] | None = None) -> int:
    """Generic runbook entry point.

    1. Validates Graph config
    2. Runs the report (outputs go to Direct Reports/)
    3. Uploads Direct Reports/ to SharePoint
    4. Sends heartbeat summary with params and file links
    5. Alerts on any failure
    """
    setup_logging()
    log.info("=== Azure Runbook starting ===")

    report_name = getattr(report_runner_class, "report_name", None) or report_runner_class.__name__
    cli_args = " ".join(argv) if argv else _detect_argv()
    start = time.monotonic()
    exit_code = 0
    files_uploaded = 0
    uploaded_urls: list[str] = []
    summary_lines: list[str] = []

    try:
        runner = report_runner_class()
        report_name = getattr(runner, "report_name", report_name)

        exit_code = runner.main(argv)
        elapsed = time.monotonic() - start

        if exit_code != 0:
            msg = f"{report_name} runner returned exit code {exit_code}"
            log.error(msg)
            send_alert(f"{report_name} FAILED", msg)
            return exit_code

        summary_lines.append(f"{report_name}: completed in {elapsed:.0f}s")

        if elapsed > SLOW_THRESHOLD_SECONDS:
            send_alert(
                f"{report_name} slow execution",
                f"{report_name} took {elapsed:.0f}s (threshold {SLOW_THRESHOLD_SECONDS}s). "
                "This may indicate D365 API slowness or unexpected data volume growth.",
            )

        files_uploaded, uploaded_urls = _upload_results_safe(report_name, summary_lines)
        log.info("=== Azure Runbook completed successfully ===")
        return 0

    except Exception:
        elapsed = time.monotonic() - start
        tb = traceback.format_exc()
        msg = f"{report_name} raised an exception after {elapsed:.0f}s:\n\n{tb}"
        log.exception("Runbook failed")
        send_alert(f"{report_name} EXCEPTION", msg)
        return 1

    finally:
        elapsed = time.monotonic() - start
        _send_heartbeat(
            report_name=report_name,
            cli_args=cli_args,
            elapsed=elapsed,
            exit_code=exit_code,
            files_uploaded=files_uploaded,
            uploaded_urls=uploaded_urls,
            extra_lines=summary_lines,
        )


def _upload_results_safe(
    report_name: str, summary_lines: list[str],
) -> tuple[int, list[str]]:
    """Upload Direct Reports/ to SharePoint, alerting on failure."""
    try:
        return _upload_results()
    except Exception:
        tb = traceback.format_exc()
        msg = f"SharePoint upload failed for {report_name}:\n\n{tb}"
        log.exception("Upload failed")
        send_alert(f"{report_name} upload FAILED", msg)
        summary_lines.append("Upload: FAILED")
        return 0, []


def _upload_results() -> tuple[int, list[str]]:
    """Upload Direct Reports/ folder to SharePoint.

    Returns ``(file_count, [webUrl, ...])``.
    """
    try:
        validate_graph_config()
    except RuntimeError:
        log.info("Graph config not available, skipping SharePoint upload")
        return 0, []

    from config.paths import get_direct_reports_root
    local_dir = get_direct_reports_root()

    if not os.path.isdir(local_dir):
        log.info("No Direct Reports directory to upload")
        return 0, []

    token_mgr = get_graph_token_manager(get_tenant_id(), get_client_id(), get_client_secret())
    site_url = get_sp_site_url()
    _, drive_id = resolve_site_and_drive(site_url, token_mgr)

    root_path = get_drive_root_path()
    cloud_root = f"{root_path}/Direct Reports" if root_path else "Direct Reports"

    log.info("Uploading Direct Reports to SharePoint: %s", cloud_root)
    count, urls = upload_tree(drive_id, cloud_root, local_dir, token_mgr)
    log.info("Uploaded %d files to SharePoint", count)
    return count, urls


def _send_heartbeat(
    *,
    report_name: str,
    cli_args: str,
    elapsed: float,
    exit_code: int,
    files_uploaded: int,
    uploaded_urls: list[str],
    extra_lines: list[str],
) -> None:
    """Send an HTML heartbeat / summary email."""
    from datetime import datetime, timezone, timedelta
    eastern = timezone(timedelta(hours=-5))
    timestamp = datetime.now(tz=eastern).strftime("%Y-%m-%d %H:%M:%S")

    status_color = "#2e7d32" if exit_code == 0 else "#c62828"
    status_label = "SUCCESS" if exit_code == 0 else "FAILED"

    files_html = ""
    if uploaded_urls:
        files_html = '<h3 style="margin:18px 0 8px 0;color:#1a237e">Files Created</h3>\n<ul style="margin:0;padding-left:20px">\n'
        for url in uploaded_urls:
            display = unquote(url.rsplit("/", 1)[-1]) if "/" in url else url
            files_html += f'<li style="margin:4px 0"><a href="{escape(url)}">{escape(display)}</a></li>\n'
        files_html += "</ul>\n"

    html_body = f"""\
<div style="font-family:Segoe UI,Calibri,Arial,sans-serif;max-width:700px;margin:0 auto">
  <h2 style="margin:0 0 4px 0;color:#1a237e">Runbook Heartbeat</h2>
  <p style="margin:0 0 16px 0;color:#555;font-size:13px">{escape(timestamp)}</p>

  <table style="border-collapse:collapse;margin-bottom:16px">
    <tr>
      <td style="padding:4px 12px 4px 0;font-weight:bold">Overall Status</td>
      <td style="padding:4px 0;font-weight:bold;color:{status_color}">{status_label}</td>
    </tr>
    <tr>
      <td style="padding:4px 12px 4px 0;font-weight:bold">Report</td>
      <td style="padding:4px 0">{escape(report_name)}</td>
    </tr>
    <tr>
      <td style="padding:4px 12px 4px 0;font-weight:bold">Parameters</td>
      <td style="padding:4px 0"><code>{escape(cli_args)}</code></td>
    </tr>
    <tr>
      <td style="padding:4px 12px 4px 0;font-weight:bold">Duration</td>
      <td style="padding:4px 0">{elapsed:.0f}s</td>
    </tr>
    <tr>
      <td style="padding:4px 12px 4px 0;font-weight:bold">Files Uploaded</td>
      <td style="padding:4px 0">{files_uploaded}</td>
    </tr>
  </table>

  {files_html}
</div>"""

    subject = f"{report_name} - Runbook Summary"
    try:
        send_alert(subject, html_body, content_type="HTML")
    except Exception:
        log.debug("Could not send heartbeat summary", exc_info=True)
