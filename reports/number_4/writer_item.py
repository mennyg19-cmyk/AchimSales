"""
Number 4 Report - By Item Excel writer (streaming / write_only mode).

Writes sections per item with customer rows, TOTALS per item, and GRAND TOTALS.
Two sheets: "12 Months" and "Year to Date". Quantity only — no dollar columns.
"""

import logging
import os

import pandas as pd
from openpyxl import Workbook

from reports.number_4._styles import (
    FILL_GRAND,
    FILL_HEADER,
    FILL_TOTALS,
    styled_row,
)

log = logging.getLogger(__name__)


def write_by_item(
    agg_12: pd.DataFrame,
    labels_12: list[tuple[str, str]],
    qty_cols_12: list[str],
    agg_ytd: pd.DataFrame,
    labels_ytd: list[tuple[str, str]],
    qty_cols_ytd: list[str],
    out_path: str,
) -> None:
    """Write By Item workbook with 12 Months and Year to Date sheets."""
    log.info("Writing Number 4 By Item: 12mo=%d rows, YTD=%d rows", len(agg_12), len(agg_ytd))
    wb = Workbook(write_only=True)

    ws_12 = wb.create_sheet("12 Months")
    log.info("  Writing sheet: 12 Months (%d rows)", len(agg_12))
    _write_sheet(ws_12, agg_12, labels_12, qty_cols_12)

    ws_ytd = wb.create_sheet("Year to Date")
    log.info("  Writing sheet: Year to Date (%d rows)", len(agg_ytd))
    _write_sheet(ws_ytd, agg_ytd, labels_ytd, qty_cols_ytd)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    wb.save(out_path)
    try:
        size_kb = os.path.getsize(out_path) / 1024
        log.info("Excel saved: %.0f KB -- %s", size_kb, out_path)
    except OSError:
        log.info("Wrote: %s", out_path)


def _write_sheet(ws, agg_df, month_labels, qty_cols):
    if agg_df.empty:
        ws.append(["No data"])
        return

    headers = ["Item #", "Item Name", "Customer #", "Customer Name"]
    for lbl_q, _ in month_labels:
        headers.append(lbl_q)
    headers.extend(["Total Qty", "Salesman"])
    n_month = len(qty_cols)

    qty_set = set(range(4, 4 + n_month)) | {4 + n_month}
    currency_set: set[int] = set()

    ws.append(styled_row(ws, headers, qty_set, currency_set, fill=FILL_HEADER, bold=True))

    grand_qty = {qc: 0.0 for qc in qty_cols}
    grand_total_qty = 0.0

    for item_key, grp in agg_df.groupby(["Item_#", "Item_Name"], sort=True):
        _item_id, item_name = item_key

        item_qty = {qc: 0.0 for qc in qty_cols}
        item_total_qty = 0.0

        for _, r in grp.iterrows():
            vals = [r["Item_#"], r["Item_Name"], r.get("CustomerAccount", ""), r.get("CustomerName", "")]
            for qc in qty_cols:
                v = float(r.get(qc, 0))
                vals.append(v)
                item_qty[qc] += v
            tq = float(r["Total_Qty"])
            item_total_qty += tq
            vals.append(tq)
            vals.append(r.get("Salesman", ""))
            ws.append(styled_row(ws, vals, qty_set, currency_set))

        tot_vals = ["TOTALS:", item_name, "", ""]
        for qc in qty_cols:
            tot_vals.append(item_qty[qc])
            grand_qty[qc] += item_qty[qc]
        tot_vals.append(item_total_qty)
        tot_vals.append("")
        grand_total_qty += item_total_qty
        ws.append(styled_row(ws, tot_vals, qty_set, currency_set, fill=FILL_TOTALS, bold=True))
        ws.append([])

    grand_vals = ["GRAND TOTALS:", "", "", ""]
    for qc in qty_cols:
        grand_vals.append(grand_qty[qc])
    grand_vals.append(grand_total_qty)
    grand_vals.append("")
    ws.append(styled_row(ws, grand_vals, qty_set, currency_set, fill=FILL_GRAND, bold=True))
