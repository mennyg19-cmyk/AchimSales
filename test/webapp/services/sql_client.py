"""SQL Server client for the test sandbox.

Talks to the on-prem SQL Server through Azure Hybrid Connections.
Connection details come from environment variables so the same code
works locally (no SQL → mock fallback) and on Azure (real SQL).

Environment variables
---------------------
SQL_CONN_STR
    Full pyodbc connection string. If set, this wins.
    Example:
        Driver={ODBC Driver 18 for SQL Server};Server=tcp:host,1433;
        Database=AchimReports;UID=...;PWD=...;Encrypt=yes;
        TrustServerCertificate=yes;

SQL_SERVER, SQL_DATABASE, SQL_USERNAME, SQL_PASSWORD, SQL_DRIVER
    Used to assemble a connection string when SQL_CONN_STR is absent.
    SQL_DRIVER defaults to "ODBC Driver 18 for SQL Server".

SQL_TIMEOUT_SECONDS
    Optional integer command timeout (default 120).

The SP map below is a single source of truth — when the brother sends
the API doc, we just update the SP names / parameter shapes here.
Each entry is:
    {
        "name":    "<dbo.SP_Name>",
        "params":  callable(filter_params: dict) -> dict[str, Any]
    }
The callable maps the filter dict that the viewer hands us into the
exact named parameters the stored procedure expects.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Callable, Iterable

log = logging.getLogger(__name__)

try:
    import pyodbc  # type: ignore
except ImportError:  # pragma: no cover - pyodbc is optional locally
    pyodbc = None  # type: ignore


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


class SQLNotConfigured(RuntimeError):
    """Raised when SQL Server isn't configured in this environment."""


def _build_conn_str() -> str | None:
    """Return a full pyodbc connection string, or None if unavailable."""
    explicit = os.environ.get("SQL_CONN_STR")
    if explicit:
        return explicit

    server = os.environ.get("SQL_SERVER")
    database = os.environ.get("SQL_DATABASE")
    if not (server and database):
        return None

    driver = os.environ.get("SQL_DRIVER", "ODBC Driver 18 for SQL Server")
    user = os.environ.get("SQL_USERNAME")
    pwd = os.environ.get("SQL_PASSWORD")

    parts = [
        f"Driver={{{driver}}}",
        f"Server={server}",
        f"Database={database}",
        "Encrypt=yes",
        "TrustServerCertificate=yes",
    ]
    if user and pwd:
        parts.append(f"UID={user}")
        parts.append(f"PWD={pwd}")
    else:
        parts.append("Trusted_Connection=yes")
    return ";".join(parts) + ";"


def is_configured() -> bool:
    """True if both pyodbc is installed AND a conn string is available."""
    return pyodbc is not None and _build_conn_str() is not None


def _connect():  # -> pyodbc.Connection
    if pyodbc is None:
        raise SQLNotConfigured("pyodbc is not installed in this environment")
    conn_str = _build_conn_str()
    if not conn_str:
        raise SQLNotConfigured(
            "SQL Server is not configured (set SQL_CONN_STR or SQL_SERVER/SQL_DATABASE)"
        )
    timeout = int(os.environ.get("SQL_TIMEOUT_SECONDS", "120"))
    conn = pyodbc.connect(conn_str, timeout=timeout)
    conn.timeout = timeout
    return conn


# ---------------------------------------------------------------------------
# Stored procedure registry
# ---------------------------------------------------------------------------


def _ordered_params(p: dict) -> dict[str, Any]:
    """Map filter dict from the viewer onto the ordered-report SP params.

    Placeholder names — when the API doc lands, update the keys to match
    exactly. Empty / None values are dropped so the SP can use defaults.
    """
    out: dict[str, Any] = {}
    if p.get("date_from"):
        out["StartDate"] = p["date_from"]
    if p.get("date_to"):
        out["EndDate"] = p["date_to"]
    if p.get("status"):
        out["SalesStatus"] = p["status"]
    if p.get("salesman"):
        out["Salesman"] = p["salesman"]
    customers = p.get("customers")
    if customers:
        if isinstance(customers, (list, tuple)):
            out["CustomerAccount"] = ",".join(str(c) for c in customers)
        else:
            out["CustomerAccount"] = str(customers)
    return out


SP_MAP: dict[str, dict[str, Any]] = {
    "ordered": {
        "name": os.environ.get("SQL_SP_ORDERED", "dbo.usp_OrderedReport"),
        "params": _ordered_params,
    },
}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def _normalise_value(v: Any) -> Any:
    """Convert pyodbc values to JSON-friendly Python values."""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if v is None:
        return None
    return v


def _row_to_dict(columns: Iterable[str], row: tuple) -> dict[str, Any]:
    return {col: _normalise_value(val) for col, val in zip(columns, row)}


def execute_sp(sp_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Execute a stored procedure with named parameters and return rows.

    Builds a parametrised EXEC call:
        EXEC <sp_name> @Foo = ?, @Bar = ?

    Returns a list of dicts (one per row). The first result set is used.
    """
    keys = list(params.keys())
    placeholders = ", ".join(f"@{k} = ?" for k in keys)
    sql = f"EXEC {sp_name}" + (f" {placeholders}" if placeholders else "")
    values = [params[k] for k in keys]

    log.info("SQL: %s  params=%s", sql, {k: params[k] for k in keys})
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(sql, values)
        if cur.description is None:
            return []
        cols = [c[0] for c in cur.description]
        rows = [_row_to_dict(cols, r) for r in cur.fetchall()]
    log.info("SQL: %s returned %d rows", sp_name, len(rows))
    return rows


def fetch_report(report_key: str, filter_params: dict) -> list[dict[str, Any]]:
    """Fetch the flat row dump for a report from SQL.

    Raises SQLNotConfigured if the environment isn't wired for SQL.
    Raises KeyError if the report isn't in the SP map.
    """
    entry = SP_MAP.get(report_key)
    if entry is None:
        raise KeyError(f"No SQL stored procedure mapped for report '{report_key}'")
    sp_name = entry["name"]
    mapper: Callable[[dict], dict] = entry["params"]
    sp_params = mapper(filter_params or {})
    return execute_sp(sp_name, sp_params)
