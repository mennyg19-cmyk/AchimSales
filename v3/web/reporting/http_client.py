"""HTTP client for the on-prem Reporting API (via Azure Hybrid Connection).

    POST {base}/api/reports/{report_id}/run
    Headers: X-API-Key, Content-Type: application/json
    Body:    { <PascalCase filter params> }
    Returns: { columns, report_id, row_count, rows: [ {...}, ... ] }

The `session` is injectable so this is unit-testable without a live API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)


class ReportingApiNotConfigured(RuntimeError):
    """REPORTING_API_BASE_URL / KEY not set in this environment."""


class ReportingApiError(RuntimeError):
    """The API returned an error or unreachable after retries."""


class _Session(Protocol):
    def post(self, url: str, *, json: Any, headers: dict, timeout: float): ...


@dataclass
class ReportResult:
    report_id: str
    columns: list[str]
    rows: list[dict]
    row_count: int


class ReportingApiClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 300.0,
                 retries: int = 2, session: _Session | None = None):
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout
        self.retries = max(0, retries)
        self._session = session

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def _session_or_default(self) -> _Session:
        if self._session is not None:
            return self._session
        import requests

        return requests.Session()

    def run_report(self, report_id: str, params: dict[str, Any]) -> ReportResult:
        if not self.configured:
            raise ReportingApiNotConfigured("REPORTING_API_BASE_URL/KEY not set")
        url = f"{self.base_url}/api/reports/{report_id}/run"
        headers = {"X-API-Key": self.api_key, "Content-Type": "application/json"}
        session = self._session_or_default()

        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = session.post(url, json=params, headers=headers,
                                    timeout=(10, self.timeout))
                status = resp.status_code
                if 400 <= status < 500:
                    # Client error (bad params / SP rejection): don't retry.
                    raise ReportingApiError(f"Reporting API {status} for {report_id}")
                if status >= 500:
                    # Transient server error: retry then surface.
                    raise _Transient(f"Reporting API {status} for {report_id}")
                body = resp.json()
                rows = body.get("rows")
                if not isinstance(rows, list):
                    rows = []
                return ReportResult(
                    report_id=body.get("report_id", report_id),
                    columns=body.get("columns") or (list(rows[0].keys()) if rows else []),
                    rows=rows,
                    row_count=body.get("row_count", len(rows)),
                )
            except ReportingApiError:
                raise
            except Exception as exc:  # noqa: BLE001 - transient/network/parse: retry then surface
                last_exc = exc
                log.warning("Reporting API attempt %d/%d failed: %s", attempt + 1, self.retries + 1, exc)
        raise ReportingApiError(f"Reporting API unreachable for {report_id}: {last_exc}")


class _Transient(Exception):
    """Internal: a retryable (5xx/network) failure."""
