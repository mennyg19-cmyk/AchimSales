"""
Run log for tracking report execution history.

Maintains a CSV log on SharePoint that records every report run with
timestamps, status, duration, row counts, and error details. The log
is downloaded before a run, appended to, and re-uploaded afterwards.

The CSV lives at: D365 F&O/scripts/logs/run_log.csv
"""

import csv
import io
import logging
import os
import tempfile
from datetime import datetime

log = logging.getLogger(__name__)

CSV_COLUMNS = [
    "timestamp",
    "report_name",
    "status",
    "duration_sec",
    "rows_output",
    "files_uploaded",
    "args",
    "error",
]

_LOG_CLOUD_PATH = "D365 F&O/scripts/logs/run_log.csv"


def _now_stamp() -> str:
    from core.dates import get_now_eastern
    return get_now_eastern().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_header(local_path: str) -> None:
    """Create the CSV with a header row if it doesn't exist or is empty."""
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        return
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    with open(local_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)


def _append_row(local_path: str, row: dict) -> None:
    _ensure_header(local_path)
    with open(local_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writerow(row)


class RunLog:
    """Context manager that logs STARTED on enter, SUCCESS/FAILED on exit.

    Usage::

        with RunLog(drive_id, token, "Ordered Report", "--period daily") as rl:
            # run report
            rl.rows_output = 1799
            rl.files_uploaded = 4

    On exit it appends the final status row and uploads the CSV.
    """

    def __init__(
        self,
        drive_id: str,
        access_token: str,
        report_name: str,
        args_str: str = "",
    ):
        self.drive_id = drive_id
        self.access_token = access_token
        self.report_name = report_name
        self.args_str = args_str
        self.rows_output: int = 0
        self.files_uploaded: int = 0
        self._start_time: float = 0.0
        self._local_path = ""
        self._error: str = ""

    def _download_log(self) -> str:
        """Download the run_log.csv from SharePoint, or create a fresh one."""
        tmp_dir = tempfile.mkdtemp(prefix="run_log_")
        local_path = os.path.join(tmp_dir, "run_log.csv")
        try:
            from core.graph import download_file_by_path
            ok = download_file_by_path(
                self.drive_id, _LOG_CLOUD_PATH, local_path, self.access_token,
            )
            if not ok:
                log.info("No existing run_log.csv on SharePoint; starting fresh")
                _ensure_header(local_path)
        except Exception:
            log.debug("Could not download run_log.csv; starting fresh", exc_info=True)
            _ensure_header(local_path)
        return local_path

    def _upload_log(self) -> None:
        """Upload the run_log.csv back to SharePoint."""
        try:
            from core.graph import ensure_folder, upload_file
            cloud_folder = "/".join(_LOG_CLOUD_PATH.replace("\\", "/").split("/")[:-1])
            ensure_folder(self.drive_id, cloud_folder, self.access_token)
            upload_file(self.drive_id, cloud_folder, self._local_path, self.access_token)
            log.info("Run log uploaded to %s", _LOG_CLOUD_PATH)
        except Exception:
            log.warning("Could not upload run_log.csv to SharePoint", exc_info=True)

    def __enter__(self):
        import time
        self._start_time = time.monotonic()
        self._local_path = self._download_log()
        _append_row(self._local_path, {
            "timestamp": _now_stamp(),
            "report_name": self.report_name,
            "status": "STARTED",
            "args": self.args_str,
        })
        self._upload_log()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        elapsed = time.monotonic() - self._start_time

        if exc_type is not None:
            status = "FAILED"
            self._error = f"{exc_type.__name__}: {exc_val}"
        else:
            status = "SUCCESS"

        # Re-download in case another runbook appended concurrently
        try:
            fresh = self._download_log()
            self._local_path = fresh
        except Exception:
            log.debug("Could not re-download log for final append", exc_info=True)

        _append_row(self._local_path, {
            "timestamp": _now_stamp(),
            "report_name": self.report_name,
            "status": status,
            "duration_sec": f"{elapsed:.0f}",
            "rows_output": str(self.rows_output),
            "files_uploaded": str(self.files_uploaded),
            "args": self.args_str,
            "error": self._error,
        })
        self._upload_log()

        return False
