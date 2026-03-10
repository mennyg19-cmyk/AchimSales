"""
Ordered Report data builder.

Fetches headers + lines + WHS + packing slips from D365,
merges, derives status flags, and computes all quantity/dollar columns.
"""

import logging

import pandas as pd

from core.columns import pick_col, to_number
from core.dates import PeriodSpec, convert_d365_dates_to_eastern
from data.d365_entities import (
    fetch_packing_slip_trans,
    fetch_released_products,
    fetch_sales_order_headers,
    fetch_sales_order_lines,
    fetch_whs_sales_lines,
)

log = logging.getLogger(__name__)

_D365_RAW_FIELDS = frozenset({
    "sysrecversion", "recversion", "recid", "partition", "dataareaid",
    "entity", "_entity", "createdby", "modifiedby", "createddatetime",
    "modifieddatetime", "isdeleted", "isreadonly",
})

FULL_DATA_ORDER = [
    "SalesOrderNumber", "CustomerAccount", "SalesOrderName", "OrderDate",
    "LineNumber", "Item#", "ItemName", "UnitPrice", "Status",
    "Fulfillment %",
    "QtyOrdered", "QtyShipped", "QtyCancelled", "QtyReleased", "QtyOpen",
    "Ordered $", "Shipped $", "Cancelled $", "Released $", "Open $",
    "DataQualityFlag",
]

SUMMARY_COLS = [
    "Customer Name", "Salesman", "Item Number", "Line Description",
    "QtyOrdered", "QtyCancelled", "QtyRemainder",
    "Net Price", "Extended Price - Ordered", "Extended Price Remainder",
]

AGG_COLS = [
    "QtyOrdered", "QtyShipped", "QtyCancelled", "QtyReleased", "QtyOpen",
    "Ordered $", "Shipped $", "Cancelled $", "Released $", "Open $",
]


def fetch_all_data(
    base_url: str,
    token: str,
    start_date,
    end_date,
    company_id: str | None = None,
    customer_account: str | list[str] | None = None,
    status_filter: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fetch all entities needed for the ordered report.

    When customer_account is set (e.g. '9300' or ['9300', '9301']), headers are
    fetched with a direct OData $filter so only those customers' orders are returned.

    When status_filter is set (e.g. 'open'), the OData $filter excludes
    Invoiced/Canceled headers at the API level.

    Returns (headers_df, lines_df, whs_df, packing_slip_df).
    """
    headers_df = fetch_sales_order_headers(
        base_url, token, start_date, end_date, company_id,
        customer_account=customer_account, status_filter=status_filter,
    )
    if headers_df.empty:
        return headers_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    order_nums = set(headers_df["SalesOrderNumber"].astype(str).str.strip().tolist())
    log.info("Found %d unique orders in headers", len(order_nums))

    lines_df = fetch_sales_order_lines(base_url, token, order_nums, company_id)
    if lines_df.empty:
        return headers_df, lines_df, pd.DataFrame(), pd.DataFrame()

    lines_df = _enrich_line_descriptions(lines_df, base_url, token, company_id)

    inv_lot_ids = set()
    if "InventoryLotId" in lines_df.columns:
        inv_lot_ids = set(
            lines_df["InventoryLotId"].astype(str).str.strip()
            .replace({"": None, "nan": None}).dropna().tolist()
        )

    whs_df = fetch_whs_sales_lines(base_url, token, inv_lot_ids, company_id)
    packing_slip_df = fetch_packing_slip_trans(base_url, token, order_nums, company_id)

    return headers_df, lines_df, whs_df, packing_slip_df


def _enrich_line_descriptions(
    lines_df: pd.DataFrame,
    base_url: str,
    token: str,
    company_id: str | None,
) -> pd.DataFrame:
    """Overwrite LineDescription with DVReleasedProducts.ProductName when available.

    Prefers the master product name; falls back to the order-line description
    only when DVReleasedProducts has no match for the item.
    """
    if "Item#" not in lines_df.columns:
        return lines_df
    if "LineDescription" not in lines_df.columns:
        lines_df["LineDescription"] = ""

    all_items = lines_df["Item#"].dropna().astype(str).str.strip().unique().tolist()
    all_items = [s for s in all_items if s and s.lower() != "nan"]
    if not all_items:
        return lines_df

    prods = fetch_released_products(base_url, token, all_items, company_id)
    if prods.empty:
        return lines_df

    prods = prods.drop_duplicates(subset=["ItemNumber"])
    prods = prods.rename(columns={"ItemNumber": "_item", "ProductName": "_ProductName"})

    merged = lines_df.merge(prods[["_item", "_ProductName"]], left_on="Item#", right_on="_item", how="left")
    has_product = merged["_ProductName"].fillna("").astype(str).str.strip() != ""
    overwritten = has_product.sum()
    merged.loc[has_product, "LineDescription"] = (
        merged.loc[has_product, "_ProductName"].astype(str).str.strip()
    )
    merged = merged.drop(columns=["_item", "_ProductName"], errors="ignore")
    log.info("Overwrote %d line descriptions with DVReleasedProducts", int(overwritten))
    return merged


def build_report(
    headers_df: pd.DataFrame,
    lines_df: pd.DataFrame,
    whs_lines_df: pd.DataFrame,
    packing_slip_df: pd.DataFrame,
    period: PeriodSpec,
    salesman_filter: str | list[str] | None = None,
) -> tuple[pd.DataFrame, str | None]:
    """Build the ordered report DataFrame for a single period.

    Filters headers to the period's date range, merges lines, derives statuses,
    and computes all qty/dollar columns.

    When *salesman_filter* is set (a single name or list of names),
    the merged result is narrowed to rows whose ``Salesman`` column matches.

    Returns ``(dataframe, empty_reason)``.  *empty_reason* is ``None`` when
    data is present, or a human-readable string explaining which filter
    eliminated all rows.
    """
    if headers_df.empty or lines_df.empty:
        return pd.DataFrame(), "No order data available for the requested date range"

    headers = headers_df.copy()
    lines = lines_df.copy()

    if "OrderDate" in headers.columns:
        headers["OrderDate"] = pd.to_datetime(headers["OrderDate"], errors="coerce", utc=True)
        headers["OrderDate"] = headers["OrderDate"].dt.tz_localize(None)
    headers["_date_only"] = headers["OrderDate"].dt.date

    start_dt = period.start_date
    end_dt = period.end_date
    headers_filtered = headers[
        (headers["_date_only"] >= start_dt) & (headers["_date_only"] <= end_dt)
    ].copy()

    if headers_filtered.empty:
        log.info("No orders for period %s (%s to %s)", period.label, start_dt, end_dt)
        return pd.DataFrame(), f"No orders found for period {period.label} ({start_dt} to {end_dt})"

    headers_filtered["_so_key"] = headers_filtered["SalesOrderNumber"].astype(str).str.strip()
    order_nums = set(headers_filtered["_so_key"].tolist())

    lines["_so_num"] = lines["SalesOrderNumber"].astype(str).str.strip()
    lines_filtered = lines[lines["_so_num"].isin(order_nums)].copy()

    merge_cols = [c for c in [
        "SalesOrderNumber", "OrderDate", "OrderStatus", "OrderProcessingStatus",
        "CustomerAccount", "SalesOrderName", "Salesman", "CustomerName", "CustomerRequisition",
    ] if c in headers_filtered.columns]

    merged = lines_filtered.merge(
        headers_filtered[merge_cols + ["_so_key"]],
        left_on="_so_num", right_on="_so_key", how="left", suffixes=("", "_h"),
    )

    if "Salesman" not in merged.columns:
        merged["Salesman"] = ""
    else:
        merged["Salesman"] = merged["Salesman"].fillna("").astype(str).str.strip()

    if salesman_filter:
        sm_list = [salesman_filter] if isinstance(salesman_filter, str) else salesman_filter
        sm_lower = {s.strip().lower() for s in sm_list}
        merged = merged[
            merged["Salesman"].str.lower().isin(sm_lower)
        ].reset_index(drop=True)
        if merged.empty:
            sm_label = ",".join(sm_list)
            log.info("No rows after salesman filter '%s' for period %s",
                     sm_label, period.label)
            return pd.DataFrame(), (
                f"No orders found for salesman(s) '{sm_label}' "
                f"in period {period.label} ({period.start_date} to {period.end_date})"
            )

    if "CustomerName" not in merged.columns:
        merged["CustomerName"] = merged.get("SalesOrderName", pd.Series("", index=merged.index)).fillna("").astype(str).str.strip()

    if "CustomerRequisition" not in merged.columns:
        merged["CustomerRequisition"] = ""

    merged["SalesOrderNumber"] = merged["_so_num"]

    item_vals = merged.get("Item#", pd.Series("", index=merged.index)).astype(str).str.strip().str.upper()
    merged = merged[~item_vals.str.contains(r"ERROR\s*ITEM", regex=True, na=False)].reset_index(drop=True)
    if merged.empty:
        return pd.DataFrame(), "All order lines were filtered out (error items removed)"

    if "LineDescription" not in merged.columns:
        merged["LineDescription"] = ""
    else:
        merged["LineDescription"] = merged["LineDescription"].fillna("").astype(str).str.strip()

    merged["QtyOrdered"] = to_number(merged.get("QtyOrdered", pd.Series(0.0, index=merged.index)))

    unit_price_col = pick_col(merged, ["UnitPrice", "Price"])
    total_col = pick_col(merged, ["Total", "LineAmount", "Amount"])
    sales_price_col = pick_col(merged, ["SalesPrice"])

    if unit_price_col:
        merged["UnitPrice"] = to_number(merged[unit_price_col])
    elif total_col:
        merged["UnitPrice"] = (to_number(merged[total_col]) / merged["QtyOrdered"].replace(0, float("nan"))).fillna(0)
    else:
        merged["UnitPrice"] = 0.0

    if sales_price_col:
        merged["SalesPrice"] = to_number(merged[sales_price_col])
    else:
        merged["SalesPrice"] = merged["UnitPrice"]

    merged = _join_whs(merged, whs_lines_df)
    merged = _join_packing_slip(merged, packing_slip_df)
    merged = _derive_statuses(merged)
    merged = _compute_dollars(merged)
    merged = _compute_fulfillment(merged)

    merged = merged.drop(columns=["_so_num", "_date_only", "_so_key"], errors="ignore")
    merged["Status"] = merged["DisplayLineStatus"]

    merged["_StatusCategory"] = "Other"
    merged.loc[merged["DisplayLineStatus"] == "Cancelled", "_StatusCategory"] = "Cancelled"
    merged.loc[
        (merged["DisplayLineStatus"] == "Invoiced") &
        (merged["QtyShipped"] >= merged["QtyOrdered"] - 1e-6),
        "_StatusCategory"
    ] = "Shipped"
    merged.loc[
        (merged["DisplayLineStatus"] == "Invoiced") &
        (merged["QtyShipped"] < merged["QtyOrdered"] - 1e-6) &
        (merged["QtyCancelled"] > 0),
        "_StatusCategory"
    ] = "PartialInvoicedCancelled"
    merged.loc[
        merged["DisplayLineStatus"].isin(["In Process", "InProcess"]),
        "_StatusCategory"
    ] = "Processing"
    merged.loc[
        merged["DisplayLineStatus"].isin(["BackOrdered", "Open"]),
        "_StatusCategory"
    ] = "Backorder"

    return merged, None


def _join_whs(merged: pd.DataFrame, whs_df: pd.DataFrame) -> pd.DataFrame:
    """Join WHS released quantities."""
    merged["WHSReleased"] = 0.0
    inv_lot_col = pick_col(merged, ["InventoryLotId"])
    if whs_df is None or whs_df.empty or not inv_lot_col:
        return merged

    whs_inv = pick_col(whs_df, ["InventTransId"])
    whs_rel = pick_col(whs_df, ["WHSReleased", "Released", "ReleaseQty"])
    if not whs_inv or not whs_rel:
        return merged

    whs_agg = whs_df.groupby(whs_inv, dropna=False)[whs_rel].sum().reset_index()
    whs_agg = whs_agg.rename(columns={whs_rel: "WHSReleased", whs_inv: "InventTransId"})

    merged = merged.merge(
        whs_agg[["InventTransId", "WHSReleased"]],
        left_on=inv_lot_col, right_on="InventTransId",
        how="left", suffixes=("", "_whs"),
    )
    whs_col = "WHSReleased_whs" if "WHSReleased_whs" in merged.columns else "WHSReleased"
    merged["WHSReleased"] = to_number(merged[whs_col]).fillna(0)
    merged = merged.drop(columns=["InventTransId", "WHSReleased_whs"], errors="ignore")
    return merged


def _join_packing_slip(merged: pd.DataFrame, ps_df: pd.DataFrame) -> pd.DataFrame:
    """Join packing slip quantities."""
    merged["PackSlipQty"] = 0.0
    merged["DataQualityFlag"] = ""
    if ps_df is None or ps_df.empty or "PackSlipQty" not in ps_df.columns:
        return merged

    inv_lot_col = pick_col(merged, ["InventoryLotId"])
    ps_inv = pick_col(ps_df, ["InventTransId"])
    ps_sales = pick_col(ps_df, ["SalesId"])
    ps_ln = pick_col(ps_df, ["LineNum", "LineNumber"])

    use_three_key = ps_sales and ps_ln and "LineNumber" in merged.columns
    if ps_inv and inv_lot_col:
        if use_three_key:
            ps_sub = ps_df[[ps_sales, ps_ln, ps_inv, "PackSlipQty"]].copy()
            ps_sub = ps_sub.rename(columns={ps_sales: "_ps_sales", ps_ln: "_ps_ln", ps_inv: "_ps_inv"})
            merged = merged.merge(
                ps_sub,
                left_on=["SalesOrderNumber", "LineNumber", inv_lot_col],
                right_on=["_ps_sales", "_ps_ln", "_ps_inv"],
                how="left", suffixes=("", "_ps"),
            )
        else:
            ps_sub = ps_df[[ps_inv, "PackSlipQty"]].copy()
            ps_sub = ps_sub.rename(columns={ps_inv: "_ps_inv"})
            merged = merged.merge(ps_sub, left_on=inv_lot_col, right_on="_ps_inv", how="left")

        merged["PackSlipQty"] = to_number(merged["PackSlipQty"]).fillna(0)
        merged["DataQualityFlag"] = merged.apply(
            lambda r: "PackSlipQty exceeds QtyOrdered" if r["PackSlipQty"] > r["QtyOrdered"] else "", axis=1,
        )
        drop_cols = [c for c in merged.columns if c.startswith("_ps")]
        merged = merged.drop(columns=drop_cols, errors="ignore")

    return merged


def _derive_statuses(merged: pd.DataFrame) -> pd.DataFrame:
    """Derive DisplayLineStatus and qty buckets from raw statuses."""
    def _sv(col):
        if col not in merged.columns:
            return pd.Series("", index=merged.index)
        return merged[col].fillna("").astype(str).str.strip().str.lower()

    raw_line = _sv("RawLineStatus")
    order_status = _sv("OrderStatus")
    order_proc = _sv("OrderProcessingStatus")

    merged["QtyShipped"] = 0.0
    merged["QtyCancelled"] = 0.0
    merged["QtyReleased"] = 0.0
    merged["QtyOpen"] = 0.0
    merged["DisplayLineStatus"] = ""

    order_cancelled = order_status.isin(["canceled", "cancelled"]) | order_proc.isin(["canceled", "cancelled"])
    merged.loc[order_cancelled, "DisplayLineStatus"] = "Cancelled"
    merged.loc[order_cancelled, "QtyCancelled"] = merged.loc[order_cancelled, "QtyOrdered"]
    done = order_cancelled

    mask = ~done & raw_line.isin(["canceled", "cancelled"])
    merged.loc[mask, "DisplayLineStatus"] = "Cancelled"
    merged.loc[mask, "QtyCancelled"] = merged.loc[mask, "QtyOrdered"]
    done = done | mask

    mask = ~done & (raw_line == "invoiced")
    merged.loc[mask, "DisplayLineStatus"] = "Invoiced"
    merged.loc[mask, "QtyShipped"] = merged.loc[mask, "WHSReleased"]
    merged.loc[mask, "QtyCancelled"] = merged.loc[mask, "QtyOrdered"] - merged.loc[mask, "WHSReleased"]
    done = done | mask

    mask_back = ~done & (raw_line == "backorder")

    m3 = mask_back & (merged["WHSReleased"] >= merged["QtyOrdered"] - 1e-9)
    merged.loc[m3, "DisplayLineStatus"] = "In Process"
    merged.loc[m3, "QtyReleased"] = merged.loc[m3, "WHSReleased"]
    done = done | m3

    m4 = mask_back & ~done & (merged["WHSReleased"] < 1e-9)
    merged.loc[m4, "DisplayLineStatus"] = "Open"
    merged.loc[m4, "QtyOpen"] = merged.loc[m4, "QtyOrdered"]
    done = done | m4

    m5 = (mask_back & ~done &
          (merged["WHSReleased"] > 1e-9) &
          (merged["WHSReleased"] < merged["QtyOrdered"] - 1e-9) &
          ((merged["WHSReleased"] - merged["PackSlipQty"]).abs() < 1e-9))
    merged.loc[m5, "DisplayLineStatus"] = "BackOrdered"
    merged.loc[m5, "QtyShipped"] = merged.loc[m5, "PackSlipQty"]
    merged.loc[m5, "QtyOpen"] = merged.loc[m5, "QtyOrdered"] - merged.loc[m5, "PackSlipQty"]
    done = done | m5

    m6 = (mask_back & ~done &
          (merged["WHSReleased"] > 1e-9) &
          (merged["WHSReleased"] < merged["QtyOrdered"] - 1e-9))
    merged.loc[m6, "DisplayLineStatus"] = "InProcess"
    merged.loc[m6, "QtyShipped"] = merged.loc[m6, "PackSlipQty"]
    merged.loc[m6, "QtyOpen"] = merged.loc[m6, "QtyOrdered"] - merged.loc[m6, "WHSReleased"]
    merged.loc[m6, "QtyReleased"] = merged.loc[m6, "WHSReleased"] - merged.loc[m6, "PackSlipQty"]

    merged["QtyRemainder"] = (merged["QtyOrdered"].fillna(0) - merged["QtyCancelled"].fillna(0)).clip(lower=0)

    for c in ["QtyShipped", "QtyCancelled", "QtyReleased", "QtyOpen", "QtyRemainder"]:
        merged[c] = merged[c].fillna(0).astype(float)

    return merged


def _compute_dollars(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute dollar columns from qty * price."""
    unit = merged["UnitPrice"]
    net_price = merged.get("SalesPrice", merged["UnitPrice"])

    merged["Ordered $"] = (merged["QtyOrdered"] * unit).fillna(0)
    merged["Shipped $"] = (merged["QtyShipped"] * unit).fillna(0)
    merged["Cancelled $"] = (merged["QtyCancelled"] * unit).fillna(0)
    merged["Released $"] = (merged["QtyReleased"] * unit).fillna(0)
    merged["Open $"] = (merged["QtyOpen"] * unit).fillna(0)
    merged["Remainder $"] = (merged["QtyRemainder"] * net_price).fillna(0)

    merged["ItemName"] = merged["LineDescription"].astype(str).str.split("\n").str[-1].str.strip()
    merged["ItemName"] = merged["ItemName"].fillna("").astype(str)

    merged["Extended Price Ordered"] = (merged["QtyOrdered"] * net_price).fillna(0)
    merged["Extended Price Remainder"] = (merged["QtyRemainder"] * net_price).fillna(0)

    return merged


def _compute_fulfillment(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute fulfillment score and percentage."""
    qo = merged["QtyOrdered"].fillna(0)
    qc = merged["QtyCancelled"].fillna(0)
    merged["_FulfillmentScore"] = ((qo - qc) / qo.replace(0, float("nan"))).clip(0, 1)
    merged["Fulfillment %"] = merged["_FulfillmentScore"].apply(
        lambda x: f"{x * 100:.0f}%" if pd.notna(x) and x == x else ""
    )
    return merged
