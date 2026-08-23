"""Item Averages: company-wide qty run-rate from the Number 4 By Item SP.

Admin/developer only. Rolls item×customer Total Qty up to one row per item,
then Avg/Month = total/12 and Avg/Week = total/52.
"""

from __future__ import annotations

from typing import Optional, Sequence

from ..data.connection import normalize_email, utc_now_iso
from ..reporting.authz import allowed_salesmen
from .api_client import ReportingApiClient
from .config_loader import ConfigLoader
from .lib import num, text
from .params import translate

REPORT_KEY = "item_averages"
SP_NAME = "item_customer_sales_rolling_12"

_ITEM_COL = "Item #"
_NAME_COL = "Item Name"
_QTY_COL = "Total Qty"

_COLUMNS = [
    {"field": "Item #", "label": "Item #", "type": "text"},
    {"field": "Item Name", "label": "Item Name", "type": "text"},
    {"field": "12-Month Qty", "label": "12-Month Qty", "type": "int"},
    {"field": "Avg/Month", "label": "Avg/Month", "type": "int"},
    {"field": "Avg/Week", "label": "Avg/Week", "type": "int"},
]


def rollup_by_item(rows: Sequence[dict]) -> list[dict]:
    totals: dict[str, dict] = {}
    for raw in rows:
        item = text(raw.get(_ITEM_COL))
        if not item:
            continue
        name = text(raw.get(_NAME_COL))
        qty = num(raw.get(_QTY_COL))
        slot = totals.get(item)
        if slot is None:
            totals[item] = {"Item #": item, "Item Name": name, "qty": qty}
        else:
            slot["qty"] += qty
            if not slot["Item Name"] and name:
                slot["Item Name"] = name

    out: list[dict] = []
    for item in sorted(totals):
        slot = totals[item]
        total_qty = round(slot["qty"], 2)
        out.append({
            "Item #": slot["Item #"],
            "Item Name": slot["Item Name"],
            "12-Month Qty": total_qty,
            "Avg/Month": round(total_qty / 12, 2),
            "Avg/Week": round(total_qty / 52, 2),
        })
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
) -> dict | None:
    """Build the Item Averages snapshot (same contract as the shared runner)."""
    # Defense in depth: this report is company-wide and privileged-only.
    if allowed_salesmen(scope_token) is not None:
        raise PermissionError(
            "Item Averages is company-wide and only available to admins."
        )

    report_config = ConfigLoader(db).load_runnable(report_key)
    sp_params = translate(report_key, filters)

    timeout = api_timeout if api_timeout is not None else config.reporting_api_timeout
    client = ReportingApiClient(config.reporting_api_base_url, config.reporting_api_key, timeout=timeout)
    api_result = client.run_report(SP_NAME, sp_params)

    if cancelled is not None and cancelled():
        return None

    actual_count = max(int(api_result.row_count or 0), len(api_result.rows))
    if actual_count > config.max_result_rows:
        raise ValueError(
            f"This report returned {actual_count:,} rows, over the current "
            f"{config.max_result_rows:,}-row limit."
        )

    rows = rollup_by_item(api_result.rows)
    return {
        "report_key": report_key,
        "title": report_config.title,
        "generated_at": utc_now_iso(),
        "params": filters,
        "row_count": len(rows),
        "provisional": True,
        "stale": False,
        "identity": normalize_email(requested_by),
        "scope": scope_token or "",
        "tabs": [{
            "key": "item_averages",
            "label": "Item Averages",
            "layout": None,
            "columns": _COLUMNS,
            "rows": rows,
            "total": None,
        }],
    }
