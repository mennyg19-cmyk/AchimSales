"""Office Reporting API client. Stdlib urllib. Never points at the website."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

import config

CLIENT_USER_AGENT = "AchimSales-Reports"
TIMEOUT_S = 180
RETRIES = 2


class DoorwayError(RuntimeError):
    """API missing, HTTP error, or unreachable after retries."""


@dataclass
class ReportResult:
    report_id: str
    rows: list[dict]
    body: dict


def configured() -> bool:
    return bool(config.reporting_api_base() and config.reporting_api_key())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def run_report(report_id: str, params: dict | None = None, timeout: float | None = None) -> ReportResult:
    base = config.reporting_api_base()
    key = config.reporting_api_key()
    if not base or not key:
        raise DoorwayError(
            "REPORTING_API_KEY is not set. This preview still has dummy JSON. "
            "Add the office doorway key to use live stored procedures."
        )
    url = f"{base}/api/reports/{report_id}/run"
    payload = json.dumps(params or {}).encode("utf-8")
    headers = {
        "X-API-Key": key,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": CLIENT_USER_AGENT,
    }
    last_err: Exception | None = None
    opener = urllib.request.build_opener(_NoRedirect)
    for attempt in range(RETRIES + 1):
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with opener.open(req, timeout=timeout if timeout is not None else TIMEOUT_S) as resp:
                raw = resp.read()
                body = json.loads(raw.decode("utf-8") or "{}")
        except urllib.error.HTTPError as err:
            snippet = err.read()[:400].decode("utf-8", "replace")
            if 300 <= err.code < 400:
                loc = err.headers.get("Location") or "/"
                raise DoorwayError(
                    f"Reporting API redirected {report_id} to {loc} (HTTP {err.code})"
                ) from err
            if 400 <= err.code < 500:
                raise DoorwayError(
                    f"Reporting API HTTP {err.code} for {report_id}. {snippet}".strip()
                ) from err
            last_err = DoorwayError(f"Reporting API HTTP {err.code} for {report_id}. {snippet}")
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as err:
            last_err = err
            continue
        if not isinstance(body, dict):
            body = {}
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        rows = body.get("rows")
        if not isinstance(rows, list):
            rows = data.get("raw") if isinstance(data.get("raw"), list) else []
        if not isinstance(rows, list):
            rows = []
        return ReportResult(report_id=body.get("report_id") or report_id, rows=rows, body=body)
    raise DoorwayError(f"Reporting API unreachable for {report_id}: {last_err}")
