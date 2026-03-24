"""
Factory functions for order-related test DataFrames.

All factories return DataFrames with the *post-rename* column names
(i.e. the names used inside builder/writer code), matching what
``d365_entities.fetch_*`` returns after ``rename_columns()``.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd


def make_order_headers(
    n: int = 5,
    order_date: date | str = "2026-02-20",
    customers: list[str] | None = None,
    statuses: list[str] | None = None,
    salesmen: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate *n* order header rows.

    ``order_date`` can be a single date (applied to all rows) or an ISO string.
    Pass a list of dates for per-row control via DataFrame assignment after.
    """
    rng = np.random.RandomState(seed)
    if isinstance(order_date, str):
        order_date = date.fromisoformat(order_date)

    dt = datetime(order_date.year, order_date.month, order_date.day)

    customers = customers or [f"C{100 + i}" for i in range(n)]
    if len(customers) < n:
        customers = (customers * ((n // len(customers)) + 1))[:n]

    statuses = statuses or [""] * n
    if len(statuses) < n:
        statuses = (statuses * ((n // len(statuses)) + 1))[:n]

    salesmen = salesmen or [f"SM{rng.randint(1, 4):02d}" for _ in range(n)]
    if len(salesmen) < n:
        salesmen = (salesmen * ((n // len(salesmen)) + 1))[:n]

    return pd.DataFrame({
        "SalesOrderNumber": [f"SO-{1000 + i}" for i in range(n)],
        "CustomerAccount": customers[:n],
        "SalesOrderName": [f"Customer {c}" for c in customers[:n]],
        "OrderDate": pd.to_datetime([dt] * n),
        "OrderStatus": statuses[:n],
        "OrderProcessingStatus": [""] * n,
        "Salesman": salesmen[:n],
        "CustomerName": [f"Customer {c}" for c in customers[:n]],
        "CustomerRequisition": [f"PO-{rng.randint(1000, 9999)}" for _ in range(n)],
    })


def make_order_lines(
    headers_df: pd.DataFrame,
    lines_per_order: int = 2,
    items: list[str] | None = None,
    unit_price: float = 10.0,
    qty_ordered: float = 10.0,
    raw_status: str = "backorder",
    seed: int = 42,
) -> pd.DataFrame:
    """Generate lines referencing the provided headers."""
    rng = np.random.RandomState(seed)
    items = items or ["ITEM-A", "ITEM-B", "ITEM-C", "ITEM-D"]
    rows = []
    for _, hdr in headers_df.iterrows():
        so = hdr["SalesOrderNumber"]
        for ln in range(1, lines_per_order + 1):
            rows.append({
                "SalesOrderNumber": so,
                "LineNumber": ln,
                "Item#": items[rng.randint(0, len(items))],
                "LineDescription": f"Widget {items[rng.randint(0, len(items))]}",
                "QtyOrdered": qty_ordered,
                "UnitPrice": unit_price,
                "SalesPrice": unit_price,
                "RawLineStatus": raw_status,
                "InventoryLotId": f"INV-{so}-{ln}",
            })
    return pd.DataFrame(rows)


def make_whs_lines(
    lines_df: pd.DataFrame,
    released_pct: float = 1.0,
) -> pd.DataFrame:
    """Generate WHS released lines matching order lines.

    ``released_pct`` controls what fraction of QtyOrdered is released.
    """
    rows = []
    for _, line in lines_df.iterrows():
        rows.append({
            "InventTransId": line["InventoryLotId"],
            "WHSReleased": float(line["QtyOrdered"]) * released_pct,
        })
    return pd.DataFrame(rows)


def make_packing_slips(
    lines_df: pd.DataFrame,
    shipped_pct: float = 1.0,
) -> pd.DataFrame:
    """Generate packing slip rows matching order lines.

    ``shipped_pct`` controls what fraction of QtyOrdered was shipped.
    """
    rows = []
    for _, line in lines_df.iterrows():
        qty = float(line["QtyOrdered"]) * shipped_pct
        if qty > 0:
            rows.append({
                "SalesId": line["SalesOrderNumber"],
                "LineNum": line["LineNumber"],
                "InventTransId": line["InventoryLotId"],
                "PackSlipQty": qty,
            })
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["SalesId", "LineNum", "InventTransId", "PackSlipQty"]
    )
