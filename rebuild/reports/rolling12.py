"""The Number 4 report: rolling-12-month sales, by customer and/or by item."""

# === What's in this file ===
# Number 4 doesn't fit the generic one-SP-per-report engine: the person picks
# By Customer, By Item, or Both, each view comes from its OWN stored procedure,
# and the month columns (Jul-25 Qty, Jul-25 $, ...) change with the date -- so
# they can't be listed in a fixed column manifest. This module builds the whole
# snapshot for it; the shared runner hands off here when the report is number_4.
# Scoping, the row limit, cancellation, and the snapshot shape all match the
# generic path exactly, so the viewer/export/email/schedule code needs nothing
# special.
#
# fetch_plan() -- the mode choice -> which SPs to call, one tab per SP
# _column_type() -- name a column's type from its header (Qty=int, $=money)
# _clean_rows() -- coerce the SP's qty/$ cells to real numbers
# build_snapshot() -- run the plan, scope the rows, return the tabs + meta

from __future__ import annotations

from typing import Any, Optional, Sequence

from ..data.connection import normalize_email, utc_now_iso
from ..reporting.authz import allowed_salesmen
from .api_client import ReportingApiClient
from .config_loader import ConfigLoader
from .engine import _total_row
from .lib import money, num, text
from .params import force_salesman_scope, scope_row_field, translate

REPORT_KEY = "number_4"

# One tab per stored procedure: (sp_name, tab_key, label).
_BY_CUSTOMER = ("customer_item_sales_rolling_12", "by_customer", "By Customer")
_BY_ITEM = ("item_customer_sales_rolling_12", "by_item", "By Item")

_MODE_PLANS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "both": (_BY_CUSTOMER, _BY_ITEM),
    "by_customer": (_BY_CUSTOMER,),
    "by_item": (_BY_ITEM,),
}

# Fixed trailing columns the handoff names; everything else ending in "Qty" or
# "$" is a dynamic month column.
_MONEY_HEADERS = {"Total $", "Avg Price", "Book Price"}
_INT_HEADERS = {"Total Qty"}


def fetch_plan(filters: dict) -> tuple[tuple[str, str, str], ...]:
    mode = text(filters.get("mode")) or "both"
    return _MODE_PLANS.get(mode, _MODE_PLANS["both"])


def _column_type(header: str) -> str:
    if header in _MONEY_HEADERS or header.endswith("$"):
        return "money"
    if header in _INT_HEADERS or header.endswith("Qty"):
        return "int"
    return "text"


def _columns(headers: Sequence[str]) -> list[dict]:
    # The SP decides the column set and order (the handoff says don't hard-code
    # month names); we only name each column's type so the viewer/export format
    # quantities and dollars right.
    return [{"field": h, "label": h, "type": _column_type(h)} for h in headers]


def _clean_rows(rows: Sequence[dict], columns: Sequence[dict]) -> list[dict]:
    numeric = {c["field"]: c["type"] for c in columns if c["type"] != "text"}
    out = []
    for raw in rows:
        row = dict(raw)
        for field, col_type in numeric.items():
            # Quantities can be fractional (cases vs eaches), so "int" columns
            # keep 2 decimals too -- the type only drives display alignment.
            row[field] = money(raw.get(field)) if col_type == "money" else round(num(raw.get(field)), 2)
        out.append(row)
    return out


def build_snapshot(
    db,
    config,
    report_key: str,
    filters: dict,
    scope_token: Optional[str],
    *,
    requested_by: Optional[str] = None,
    api_timeout: Optional[float] = None,
    cancelled=None,
) -> Optional[dict]:
    """Number 4's version of build_report_snapshot (same contract, same shape)."""
    report_config = ConfigLoader(db).load_runnable(report_key)
    scoped_salesmen = allowed_salesmen(scope_token)
    sp_params = force_salesman_scope(report_key, translate(report_key, filters), scoped_salesmen)
    sp_params.pop("_mode", None)  # cache-key marker, not an SP parameter

    timeout = api_timeout if api_timeout is not None else config.reporting_api_timeout
    client = ReportingApiClient(config.reporting_api_base_url, config.reporting_api_key, timeout=timeout)

    tabs: list[dict] = []
    visible_count = 0
    for sp_name, tab_key, label in fetch_plan(filters):
        api_result = client.run_report(sp_name, sp_params)
        if cancelled is not None and cancelled():
            return None

        actual_count = max(int(api_result.row_count or 0), len(api_result.rows))
        if actual_count > config.max_result_rows:
            raise ValueError(
                f"The {label} view returned {actual_count:,} rows, over the current "
                f"{config.max_result_rows:,}-row limit. Filter it down and run again."
            )

        columns = _columns(api_result.columns)
        rows = _clean_rows(api_result.rows, columns)
        # Same backstop as the generic runner: even if the SP ignored the
        # SalesGroup filter, a scoped person never sees another salesman's rows.
        if scoped_salesmen is not None:
            allowed = set(scoped_salesmen)
            scope_field = scope_row_field(report_key)
            rows = [row for row in rows if str(row.get(scope_field, "")).strip() in allowed]
        visible_count += len(rows)
        tabs.append({
            "key": tab_key,
            "label": label,
            "layout": None,
            "columns": columns,
            "rows": rows,
            "total": _total_row(rows, columns),
        })

    return {
        "report_key": report_key,
        "title": report_config.title,
        "generated_at": utc_now_iso(),
        "params": filters,
        "row_count": visible_count,
        "provisional": True,
        "stale": False,
        "identity": normalize_email(requested_by),
        "scope": scope_token or "",
        "tabs": tabs,
    }
