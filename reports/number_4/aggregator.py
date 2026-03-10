"""
Number 4 Report aggregation.

Pivots line-level data into monthly qty/dollar columns per
(Item, Customer) combination, with totals and averages.
"""

import logging
from calendar import monthrange
from datetime import datetime

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def rolling_12_months(report_date: datetime) -> list[tuple[int, int]]:
    """Return list of (year, month) for last 12 calendar months ending at report_date."""
    y, m = report_date.year, report_date.month
    out = []
    for i in range(12):
        mm = m - i
        yy = y
        while mm < 1:
            mm += 12
            yy -= 1
        out.append((yy, mm))
    out.reverse()
    return out


def ytd_months(report_date: datetime) -> list[tuple[int, int]]:
    """Months from January through report_date month (inclusive)."""
    return [(report_date.year, m) for m in range(1, report_date.month + 1)]


def aggregate_by_item_customer(
    lines: pd.DataFrame,
    months: list[tuple[int, int]],
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Aggregate lines into monthly qty/dollar columns.

    Returns (agg_df, qty_col_keys, dol_col_keys).
    qty_col_keys are like "2026-01", dol_col_keys are like "2026-01_$".
    """
    group_cols = ["Item_#", "Item_Name", "CustomerAccount", "CustomerName", "Salesman"]
    existing = [c for c in group_cols if c in lines.columns]

    lines = lines.copy()
    lines["_ym"] = lines["InvoiceDate"].dt.year.astype(str) + "-" + lines["InvoiceDate"].dt.month.astype(str).str.zfill(2)

    book_price_map = None
    if "BookPrice" in lines.columns and "Item_#" in lines.columns:
        bp = lines.dropna(subset=["BookPrice"])[["Item_#", "BookPrice"]].drop_duplicates(subset=["Item_#"], keep="first")
        if not bp.empty:
            book_price_map = dict(zip(bp["Item_#"], bp["BookPrice"]))

    full = lines.groupby(existing + ["_ym"], as_index=False, dropna=False).agg({"Qty": "sum", "Total_$": "sum"})

    month_keys = [f"{y}-{m:02d}" for y, m in months]

    piv_qty = full.pivot_table(index=existing, columns="_ym", values="Qty", aggfunc="sum", fill_value=0).reset_index()
    piv_dol = full.pivot_table(index=existing, columns="_ym", values="Total_$", aggfunc="sum", fill_value=0).reset_index()

    for mk in month_keys:
        if mk not in piv_qty.columns:
            piv_qty[mk] = 0.0
        if mk not in piv_dol.columns:
            piv_dol[mk] = 0.0

    out = piv_qty[existing + month_keys].copy()
    dol_keys = []
    for c in month_keys:
        dk = f"{c}_$"
        out[dk] = piv_dol[c].values
        dol_keys.append(dk)

    out["Total_Qty"] = out[month_keys].sum(axis=1)
    out["Total_$"] = out[dol_keys].sum(axis=1)
    out["Avg_Price"] = np.where(out["Total_Qty"] != 0, out["Total_$"] / out["Total_Qty"], np.nan)

    if book_price_map and "Item_#" in out.columns:
        out["BookPrice"] = out["Item_#"].map(book_price_map)
    else:
        out["BookPrice"] = np.nan

    return out, month_keys, dol_keys


def build_month_labels(months: list[tuple[int, int]]) -> list[tuple[str, str]]:
    """Build display labels for month columns: (qty_label, dol_label)."""
    labels = []
    for y, m in months:
        lbl = datetime(y, m, 1).strftime("%b-%y")
        labels.append((f"{lbl} Qty", f"{lbl} $"))
    return labels
