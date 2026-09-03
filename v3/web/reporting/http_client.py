"""HTTP client for the on-prem Reporting API (via Azure Hybrid Connection).

    POST {base}/api/reports/{report_id}/run
    Headers: X-API-Key, Content-Type: application/json
    Body:    { <PascalCase filter params> }
    Returns: { columns, report_id, row_count, rows: [ {...}, ... ] }

The `session` is injectable so this is unit-testable without a live API.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

log = logging.getLogger(__name__)


def _capture_raw_response(report_id: str, params: dict, body: Any) -> None:
    """Diagnostic tap: record the untouched endpoint response so we can prove
    what the API actually returned, before any app-side filtering or adapting.

    Off unless RAW_CAPTURE_REPORTS lists this report_id (comma-separated). When
    on, it logs a per-month invoice-date histogram (the quick proof) and, if
    RAW_CAPTURE_DIR is set, writes the full raw body to a gzipped JSON file
    there. Best-effort: a capture failure must never break a report run.
    """
    targets = {t.strip() for t in os.environ.get("RAW_CAPTURE_REPORTS", "").split(",") if t.strip()}
    if report_id not in targets:
        return
    try:
        rows = body.get("rows") if isinstance(body, dict) else None
        rows = rows if isinstance(rows, list) else []
        months: Counter = Counter()
        for row in rows:
            raw_date = row.get("InvoiceDate") or row.get("Invoice Date") or ""
            months[str(raw_date)[:7] or "(blank)"] += 1
        log.info("RAW CAPTURE %s: row_count=%d params=%s months=%s",
                 report_id, len(rows), params, dict(sorted(months.items())))
        cap_dir = os.environ.get("RAW_CAPTURE_DIR", "").strip()
        if cap_dir:
            os.makedirs(cap_dir, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
            out_path = os.path.join(cap_dir, f"{report_id}_{stamp}.json.gz")
            with gzip.open(out_path, "wt", encoding="utf-8") as handle:
                json.dump({"report_id": report_id, "params": params, "body": body},
                          handle, default=str)
            log.info("RAW CAPTURE %s: wrote %s", report_id, out_path)
    except Exception:  # noqa: BLE001 - a diagnostic must never break a report run
        log.exception("RAW CAPTURE failed (non-fatal)")


_DATE_KEYS = (
    "InvoiceDate", "Invoice Date", "CreatedDateTime", "OrderDate",
    "Order Date", "Date", "InvoiceDateTime",
)


def _compact_json(obj: Any, limit: int = 900) -> str:
    try:
        text = json.dumps(obj, default=str, separators=(",", ":"))
    except TypeError:
        text = str(obj)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _date_span(rows: list[dict]) -> str:
    values: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in _DATE_KEYS:
            raw = str(row.get(key) or "").strip()
            if raw:
                values.append(raw[:19])
                break
    if not values:
        return ""
    return f"{min(values)}..{max(values)}"


def _sample_row(row: dict | None) -> str:
    if not isinstance(row, dict) or not row:
        return ""
    parts: list[str] = []
    for i, (key, value) in enumerate(row.items()):
        if i >= 10:
            parts.append("…")
            break
        parts.append(f"{key}={str(value)[:80]}")
    return "; ".join(parts)


def _response_detail(report_id: str, status: int, body: Any, raw_len: int,
                     took_s: float) -> str:
    rows = body.get("rows") if isinstance(body, dict) else None
    rows = rows if isinstance(rows, list) else []
    columns = []
    if isinstance(body, dict):
        columns = body.get("columns") or (list(rows[0].keys()) if rows else [])
    if not isinstance(columns, list):
        columns = []
    claimed = (body or {}).get("row_count") if isinstance(body, dict) else None
    bits = [
        f"HTTP {status} {report_id} in {took_s:.1f}s",
        f"rows={claimed if claimed is not None else len(rows)}",
        f"len={len(rows)}",
        f"cols={len(columns)}",
    ]
    if raw_len:
        bits.append(f"bytes={raw_len}")
    if columns:
        bits.append("columns=" + ",".join(str(c) for c in columns[:40]))
        if len(columns) > 40:
            bits.append("…")
    span = _date_span(rows)
    if span:
        bits.append(f"dates={span}")
    sample = _sample_row(rows[0] if rows else None)
    if sample:
        bits.append(f"first_row={sample}")
    return " ".join(bits)


def _err_snippet(resp: Any) -> str:
    try:
        return _compact_json(resp.json(), 400)
    except Exception:
        raw = getattr(resp, "text", None)
        if raw is None:
            raw = getattr(resp, "content", b"")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        text = str(raw).strip()
        return text[:400] if text else ""


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
        from web.jobs.trace import JobCancelled, raise_if_cancelled, step as job_step

        raise_if_cancelled()
        job_step("api", f"calling {report_id} {_compact_json(params)}")
        for attempt in range(self.retries + 1):
            raise_if_cancelled()
            t0 = time.monotonic()
            try:
                resp = session.post(url, json=params, headers=headers,
                                    timeout=(10, self.timeout))
                status = resp.status_code
                if 400 <= status < 500:
                    extra = _err_snippet(resp)
                    job_step("api", f"HTTP {status} {report_id} (not retrying)"
                             + (f" {extra}" if extra else ""))
                    raise ReportingApiError(f"Reporting API {status} for {report_id}")
                if status >= 500:
                    extra = _err_snippet(resp)
                    job_step("api", f"HTTP {status} {report_id} attempt {attempt + 1}"
                             + (f" {extra}" if extra else ""))
                    raise _Transient(f"Reporting API {status} for {report_id}")
                body = resp.json()
                took = time.monotonic() - t0
                raw_len = len(getattr(resp, "content", b"") or b"")
                row_count = (body or {}).get("row_count")
                log.info("Reporting API OK %s in %.1fs (rows=%s)", report_id,
                         took, row_count)
                job_step("api", _response_detail(report_id, status, body, raw_len, took),
                         ms=took * 1000)
                _capture_raw_response(report_id, params, body)
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
            except JobCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - transient/network/parse: retry then surface
                last_exc = exc
                job_step("api", f"failed {report_id} attempt {attempt + 1}/{self.retries + 1}: {exc}")
                log.warning("Reporting API attempt %d/%d failed: %s", attempt + 1, self.retries + 1, exc)
        raise ReportingApiError(f"Reporting API unreachable for {report_id}: {last_exc}")


class _Transient(Exception):
    """Internal: a retryable (5xx/network) failure."""
