"""Talks to the on-prem Reporting API that runs the stored procedures."""

# === What's in this file ===
# Every report's data comes from one HTTP call to the on-prem Reporting API
# (reached through Azure's hybrid connection). This is the only place that makes
# that call. It POSTs the stored-procedure parameters and returns the flat table
# of rows. Uses the standard library so there's no extra dependency to manage.
#
#   POST {base}/api/reports/{report_id}/run   header X-API-Key, JSON body
#   returns { columns, rows: [ {...} ], row_count }
#
# ReportingApiNotConfigured -- base URL / key missing in this environment
# ReportingApiError -- the API failed (after retries) or rejected the request
# ReportResult -- columns + rows + row_count from one call
# ReportingApiClient.run_report() -- make the call, with retry on 5xx/network

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

log = logging.getLogger("rebuild.reports.api")

_CONNECT_READ_RETRIES = 2


class ReportingApiNotConfigured(RuntimeError):
    """REPORTING_API_BASE_URL / KEY are not set in this environment."""


class ReportingApiError(RuntimeError):
    """The Reporting API failed after retries, or rejected the parameters."""


@dataclass
class ReportResult:
    report_id: str
    columns: list[str]
    rows: list[dict]
    row_count: int


class ReportingApiClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 300.0, retries: int = _CONNECT_READ_RETRIES) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = api_key or ""
        self._timeout = timeout
        self._retries = max(0, retries)

    @property
    def configured(self) -> bool:
        return bool(self._base_url and self._api_key)

    def run_report(self, report_id: str, params: dict) -> ReportResult:
        if not self.configured:
            raise ReportingApiNotConfigured("REPORTING_API_BASE_URL / REPORTING_API_KEY are not set")

        url = f"{self._base_url}/api/reports/{report_id}/run"
        body = json.dumps(params or {}).encode("utf-8")
        last_error: Exception | None = None

        for attempt in range(self._retries + 1):
            started = time.monotonic()
            request = urllib.request.Request(
                url,
                data=body,
                headers={"X-API-Key": self._api_key, "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                rows = payload.get("rows")
                rows = rows if isinstance(rows, list) else []
                log.info(
                    "Reporting API OK %s in %.1fs (rows=%s)",
                    report_id, time.monotonic() - started, payload.get("row_count", len(rows)),
                )
                return ReportResult(
                    report_id=payload.get("report_id", report_id),
                    columns=payload.get("columns") or (list(rows[0].keys()) if rows else []),
                    rows=rows,
                    row_count=payload.get("row_count", len(rows)),
                )
            except urllib.error.HTTPError as exc:
                # A 4xx means our request was wrong (bad params); retrying won't help.
                if 400 <= exc.code < 500:
                    raise ReportingApiError(f"Reporting API rejected {report_id} ({exc.code})") from exc
                last_error = exc
                log.warning("Reporting API %s attempt %d failed: HTTP %s", report_id, attempt + 1, exc.code)
            except Exception as exc:  # noqa: BLE001 - network/parse errors are retryable
                last_error = exc
                log.warning("Reporting API %s attempt %d failed: %s", report_id, attempt + 1, exc)

        raise ReportingApiError(f"Reporting API unreachable for {report_id}: {last_error}")
