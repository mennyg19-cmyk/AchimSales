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


def _column_names(columns) -> list[str]:
    names = []
    for index, col in enumerate(columns or []):
        if isinstance(col, str):
            names.append(col)
            continue
        if isinstance(col, dict):
            names.append(str(col.get("name") or col.get("Name") or col.get("field") or f"col_{index}"))
            continue
        names.append(str(col))
    return names


def _is_matrix(value) -> bool:
    return isinstance(value, list) and bool(value) and isinstance(value[0], (list, tuple))


def _records_from_columns(columns, matrix) -> list[dict]:
    names = _column_names(columns)
    if not names:
        return []
    rows = []
    for raw in matrix or []:
        if isinstance(raw, dict):
            rec = {}
            for name in names:
                val = raw.get(name) if name in raw else None
                rec[name] = "" if val is None else val
            for key, value in raw.items():
                if key not in rec:
                    rec[key] = "" if value is None else value
            rows.append(rec)
            continue
        if not isinstance(raw, (list, tuple)):
            continue
        rec = {}
        for index, name in enumerate(names):
            rec[name] = raw[index] if index < len(raw) and raw[index] is not None else ""
        rows.append(rec)
    return rows


def _as_records(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    if _is_matrix(value):
        return []
    return [row for row in value if isinstance(row, dict)]


def _flatten_tabs(tabs) -> list[dict]:
    if isinstance(tabs, dict):
        items = tabs.values()
    elif isinstance(tabs, list):
        items = tabs
    else:
        return []
    out = []
    for tab in items:
        if isinstance(tab, dict):
            rows = tab.get("rows")
            if isinstance(rows, list):
                if _is_matrix(rows) and isinstance(tab.get("columns"), list):
                    out.extend(_records_from_columns(tab["columns"], rows))
                else:
                    out.extend(_as_records(rows))
        elif isinstance(tab, list):
            out.extend(_as_records(tab))
    return out


def rows_from_body(body) -> list[dict]:
    """Turn old doorway JSON (rows, columns+values, OData value, Table) into dict rows."""
    return _rows_from_value(body, 0)


def _rows_from_value(value, depth: int) -> list[dict]:
    if depth > 5:
        return []
    if isinstance(value, list):
        records = _as_records(value)
        return records
    if not isinstance(value, dict):
        return []
    columns = value.get("columns") or value.get("Columns")
    matrix = None
    if _is_matrix(value.get("rows")):
        matrix = value.get("rows")
    elif _is_matrix(value.get("values")):
        matrix = value.get("values")
    elif _is_matrix(value.get("data")):
        matrix = value.get("data")
    if isinstance(columns, list) and matrix:
        converted = _records_from_columns(columns, matrix)
        if converted:
            return converted
    for key in ("rows", "raw", "value", "Table", "table", "result", "Results", "items"):
        item = value.get(key)
        if item is None:
            continue
        found = _rows_from_value(item, depth + 1)
        if found:
            return found
    data = value.get("data")
    if isinstance(data, list):
        found = _as_records(data)
        if found:
            return found
    if isinstance(data, dict):
        found = _rows_from_value(data, depth + 1)
        if found:
            return found
    tabs = value.get("tabs")
    if isinstance(data, dict) and tabs is None:
        tabs = data.get("tabs")
    flat = _flatten_tabs(tabs)
    if flat:
        return flat
    return []


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
        rows = rows_from_body(body)
        return ReportResult(report_id=body.get("report_id") or report_id, rows=rows, body=body)
    raise DoorwayError(f"Reporting API unreachable for {report_id}: {last_err}")
