"""
D365 data-fetching service.

Centralises the fetch-transform patterns that were previously duplicated
across customer_detail, order_detail, and api_customers route handlers.
"""

import logging
import math
from datetime import date

from webapp.helpers import get_d365_connection
from webapp.db import normalize_key

log = logging.getLogger(__name__)


def fetch_customer_info(account: str) -> dict:
    """Return a dict with customer fields from D365, or a minimal stub."""
    base_url, token, company = get_d365_connection()
    from data.d365_entities import fetch_customers

    cust_info = {"account": account, "name": account}
    cust_df = fetch_customers(base_url, token, company_id=company, customer_account=account)

    if not cust_df.empty:
        r = cust_df.iloc[0]
        cust_info = {
            "account": str(r.get("CustomerAccount", "")),
            "name": str(r.get("CustomerName", "")),
            "sales_group": str(r.get("SalesGroup", "")),
        }
    return cust_info


def fetch_recent_invoiced_orders(account: str, limit: int = 10) -> list[dict]:
    """Return the customer's last *limit* invoiced orders, newest first.

    Used by the Customer's Last Order picker. Each dict has order_number,
    order_date, customer_req (PO), order_name, and a rough order_total
    pulled from the header (no line-level totals -- that's the slow part).
    """
    base_url, token, company = get_d365_connection()
    from data.d365_entities import fetch_sales_order_headers
    from core.dates import D365_GO_LIVE, get_today_eastern, convert_d365_dates_to_eastern

    today = get_today_eastern()
    headers_df = fetch_sales_order_headers(
        base_url, token, D365_GO_LIVE, today,
        company_id=company, customer_account=account,
    )
    if headers_df.empty:
        return []

    if "OrderStatus" in headers_df.columns:
        # Match either "Invoiced" or anything containing it (e.g. "Partially invoiced")
        status = headers_df["OrderStatus"].fillna("").astype(str).str.lower()
        headers_df = headers_df[status.str.contains("invoiced")]
    if headers_df.empty:
        return []

    if "OrderDate" in headers_df.columns:
        headers_df["OrderDate"] = convert_d365_dates_to_eastern(headers_df["OrderDate"])
    headers_df = headers_df.sort_values("OrderDate", ascending=False).head(limit)

    orders: list[dict] = []
    for _, row in headers_df.iterrows():
        od = row.get("OrderDate")
        orders.append({
            "order_number":   str(row.get("SalesOrderNumber", "")),
            "order_date":     od.strftime("%Y-%m-%d") if hasattr(od, "strftime") else str(od)[:10] if od else "",
            "status":         str(row.get("OrderStatus", "")),
            "customer_req":   str(row.get("CustomerRequisition", "")),
            "order_name":     str(row.get("SalesOrderName", "")),
        })
    return orders


def fetch_orders_with_qty_breakdown(
    customer_account: str,
    order_numbers: list[str],
) -> tuple[list[dict], list[dict]]:
    """For a set of sales orders, pull headers + lines + WHS releases + packing
    slips, then run the Ordered Report's classifier to get QtyShipped /
    QtyCancelled per line.

    Returns ``(headers_list, lines_list)``.

    Each header dict mirrors what ``fetch_order_with_lines`` produces (single
    order header), so the template can render any of them. Each line dict
    has the columns the Customer's Last Order view needs:

        order_number, item, description, qty_ordered, qty_shipped,
        qty_cancelled, sales_price, total

    where ``total = sales_price * qty_shipped`` (matches the user spec for a
    "what was actually invoiced" Total).
    """
    import pandas as pd

    from data.d365_entities import (
        fetch_sales_order_headers,
        fetch_sales_order_lines,
        fetch_whs_sales_lines,
        fetch_packing_slip_trans,
    )
    from core.dates import D365_GO_LIVE, get_today_eastern, PeriodSpec
    from reports.ordered.builder import build_report

    if not order_numbers:
        return [], []

    base_url, token, company = get_d365_connection()
    today = get_today_eastern()

    headers_df = fetch_sales_order_headers(
        base_url, token, D365_GO_LIVE, today,
        company_id=company, customer_account=customer_account,
    )
    if headers_df.empty:
        return [], []

    wanted = {str(x).strip() for x in order_numbers if str(x).strip()}
    headers_df = headers_df[
        headers_df["SalesOrderNumber"].astype(str).str.strip().isin(wanted)
    ].copy()
    if headers_df.empty:
        return [], []

    lines_df = fetch_sales_order_lines(base_url, token, wanted, company_id=company)
    if lines_df.empty:
        return _headers_to_list(headers_df), []

    inv_lot_ids = set()
    if "InventoryLotId" in lines_df.columns:
        inv_lot_ids = {str(x).strip() for x in lines_df["InventoryLotId"].dropna() if str(x).strip()}
    whs_df = fetch_whs_sales_lines(base_url, token, inv_lot_ids, company_id=company) if inv_lot_ids else pd.DataFrame()
    packing_df = fetch_packing_slip_trans(base_url, token, wanted, company_id=company)

    period = PeriodSpec(
        label="custom", start_date=D365_GO_LIVE, end_date=today,
        subfolder="custom", filename_tag="custom",
    )
    merged_df, _empty_reason = build_report(headers_df, lines_df, whs_df, packing_df, period)

    if merged_df.empty:
        return _headers_to_list(headers_df), []

    lines_out: list[dict] = []
    for _, r in merged_df.iterrows():
        qty_shipped = float(r.get("QtyShipped") or 0)
        sales_price = float(r.get("SalesPrice") or r.get("UnitPrice") or 0)
        lines_out.append({
            "order_number":   str(r.get("SalesOrderNumber", "")).strip(),
            "item":           str(r.get("Item#", "") or "").strip(),
            "description":    str(r.get("LineDescription", "") or "").strip(),
            "qty_ordered":    float(r.get("QtyOrdered") or 0),
            "qty_shipped":    qty_shipped,
            "qty_cancelled":  float(r.get("QtyCancelled") or 0),
            "sales_price":    sales_price,
            "total":          round(sales_price * qty_shipped, 2),
        })

    return _headers_to_list(headers_df), lines_out


def _headers_to_list(headers_df) -> list[dict]:
    """Sort headers newest-first and convert to plain dicts for templates."""
    from core.dates import convert_d365_dates_to_eastern

    df = headers_df.copy()
    if "OrderDate" in df.columns:
        df["OrderDate"] = convert_d365_dates_to_eastern(df["OrderDate"])
        df = df.sort_values("OrderDate", ascending=False)

    out: list[dict] = []
    for _, r in df.iterrows():
        od = r.get("OrderDate")
        out.append({
            "order_number":      str(r.get("SalesOrderNumber", "")).strip(),
            "order_date":        od.strftime("%Y-%m-%d") if hasattr(od, "strftime") else str(od)[:10] if od else "",
            "status":            str(r.get("OrderStatus", "") or ""),
            "processing_status": str(r.get("OrderProcessingStatus", "") or ""),
            "customer_account":  str(r.get("CustomerAccount", "") or ""),
            "customer_name":     str(r.get("CustomerName", "") or ""),
            "salesman":          str(r.get("Salesman", "") or ""),
            "customer_req":      str(r.get("CustomerRequisition", "") or ""),
            "order_name":        str(r.get("SalesOrderName", "") or ""),
        })
    return out


def fetch_customer_orders(account: str, start_date: date, end_date: date,
                          last_n: int | None = None) -> list[dict]:
    """Return a list of order dicts for *account* between the given dates."""
    base_url, token, company = get_d365_connection()
    from data.d365_entities import fetch_sales_order_headers
    from core.dates import convert_d365_dates_to_eastern

    headers_df = fetch_sales_order_headers(
        base_url, token, start_date, end_date,
        company_id=company, customer_account=account,
    )

    if headers_df.empty:
        return []

    if "OrderDate" in headers_df.columns:
        headers_df["OrderDate"] = convert_d365_dates_to_eastern(headers_df["OrderDate"])
    headers_df = headers_df.sort_values("OrderDate", ascending=False)

    if last_n:
        headers_df = headers_df.head(last_n)

    orders = []
    for _, row in headers_df.iterrows():
        od = row.get("OrderDate")
        orders.append({
            "order_number": str(row.get("SalesOrderNumber", "")),
            "order_date": od.strftime("%Y-%m-%d") if hasattr(od, "strftime") else str(od)[:10] if od else "",
            "status": str(row.get("OrderStatus", "")),
            "processing_status": str(row.get("OrderProcessingStatus", "")),
            "customer_req": str(row.get("CustomerRequisition", "")),
            "order_name": str(row.get("SalesOrderName", "")),
        })
    return orders


def fetch_order_with_lines(order_number: str) -> tuple[dict, list[dict], str]:
    """Return *(header_dict, lines_list, customer_account)* for a sales order."""
    base_url, token, company = get_d365_connection()
    from data.d365_entities import fetch_sales_order_lines
    from core.odata import fetch_odata_entity
    from data.field_maps import SALES_ORDER_HEADER_SELECT, SALES_ORDER_HEADER_FIELD_MAP
    from data.d365_entities import rename_columns
    from core.dates import convert_d365_dates_to_eastern

    safe_num = order_number.replace("'", "''")
    filter_expr = f"SalesOrderNumber eq '{safe_num}'"

    hdr_df = fetch_odata_entity(
        base_url, "SalesOrderHeadersV3", token,
        select=SALES_ORDER_HEADER_SELECT,
        filter_expr=filter_expr,
        company_id=company,
    )
    hdr_df = rename_columns(hdr_df, SALES_ORDER_HEADER_FIELD_MAP)

    header = {}
    customer_account = ""
    if not hdr_df.empty:
        if "OrderDate" in hdr_df.columns:
            hdr_df["OrderDate"] = convert_d365_dates_to_eastern(hdr_df["OrderDate"])
        r = hdr_df.iloc[0]
        od = r.get("OrderDate")
        customer_account = str(r.get("CustomerAccount", ""))
        header = {
            "order_number": str(r.get("SalesOrderNumber", "")),
            "order_date": od.strftime("%Y-%m-%d") if hasattr(od, "strftime") else str(od)[:10] if od else "",
            "status": str(r.get("OrderStatus", "")),
            "processing_status": str(r.get("OrderProcessingStatus", "")),
            "customer_account": customer_account,
            "customer_name": str(r.get("CustomerName", "")),
            "salesman": str(r.get("Salesman", "")),
            "customer_req": str(r.get("CustomerRequisition", "")),
            "order_name": str(r.get("SalesOrderName", "")),
        }

    lines_df = fetch_sales_order_lines(base_url, token, {order_number}, company_id=company)

    def _safe_float(val, default=0.0):
        try:
            f = float(val)
            return f if not math.isnan(f) else default
        except (TypeError, ValueError):
            return default

    lines = []
    if not lines_df.empty:
        lines_df = lines_df.sort_values("LineNumber")
        for _, r in lines_df.iterrows():
            lines.append({
                "line_number": r.get("LineNumber", ""),
                "item": str(r.get("Item#", "")),
                "description": str(r.get("LineDescription", "")),
                "qty_ordered": _safe_float(r.get("QtyOrdered")),
                "sales_price": _safe_float(r.get("SalesPrice")),
                "total": _safe_float(r.get("Total")),
                "status": str(r.get("RawLineStatus", "")),
            })

    return header, lines, customer_account


# -- Order entry -----------------------------------------------------------


def fetch_items_for_order(search_term: str = "",
                          customer_account: str | None = None) -> list[dict]:
    """Search released products for order entry.

    Uses the local product_cache (populated by the 4-hourly refresh).
    Falls back to live OData if cache is empty.
    """
    from webapp.db import get_cached_products, get_product_count

    count = get_product_count()
    log.info("fetch_items_for_order: product_cache has %d items, search=%r", count, search_term)

    if count > 0:
        cached = get_cached_products(search_term)
        items = []
        for c in cached:
            items.append({
                "item_number": c["item_number"],
                "item_name": c["product_name"] or "",
                "description": c.get("description", "") or "",
                "case_pack": 1,
                "book_price": float(c["sales_price"] or 0),
                "customer_price": float(c["sales_price"] or 0),
                "upc": "",
                "group": c.get("product_group", "") or "",
            })
        log.info("fetch_items_for_order: returning %d items from cache", len(items))
        return items

    try:
        base_url, token, company = get_d365_connection()
        from core.odata import fetch_odata_entity

        filter_parts = []
        if search_term:
            safe = search_term.replace("'", "''")
            filter_parts.append(
                f"(contains(ItemNumber, '{safe}') or contains(SearchName, '{safe}'))"
            )
        filter_expr = " and ".join(filter_parts) if filter_parts else None

        df = fetch_odata_entity(
            base_url, "ReleasedProductsV2", token,
            select=["ItemNumber", "SearchName", "SalesPrice"],
            filter_expr=filter_expr,
            company_id=company,
        )

        items = []
        if not df.empty:
            for _, r in df.iterrows():
                items.append({
                    "item_number": str(r.get("ItemNumber", "")),
                    "item_name": str(r.get("SearchName", "")),
                    "description": "",
                    "case_pack": 1,
                    "book_price": float(r.get("SalesPrice", 0) or 0),
                    "customer_price": float(r.get("SalesPrice", 0) or 0),
                    "upc": "",
                    "group": "",
                })
            log.info("fetch_items_for_order: returning %d items from live OData", len(items))
            return items
    except Exception:
        log.exception("D365 live OData item search failed")

    log.warning("fetch_items_for_order: no items available (cache empty, OData failed)")
    return []


def fetch_item_by_upc(upc: str) -> dict | None:
    """Look up a single item by UPC barcode.

    TODO: Wire to InventItemBarcode or similar D365 entity.
    """
    return None


def fetch_item_variants(item_number: str) -> dict:
    """Return the variant matrix for a product master.

    TODO: Wire to custom variant entity once field names are provided.
    """
    return {"item_number": item_number, "colors": [], "sizes": [], "grid": {}}


def fetch_customer_price(customer_account: str, item_number: str,
                         qty: float = 1.0) -> dict:
    """Return the customer-specific price for an item.

    Checks the price_cache (trade agreements) first, then falls back
    to the product_cache book price.
    Returns dict with 'customer_price', 'book_price', 'source'.
    """
    from webapp.db import get_cached_price, get_cached_products

    book_price = 0.0
    products = get_cached_products(item_number)
    for p in products:
        if p["item_number"] == item_number:
            book_price = float(p["sales_price"] or 0)
            break

    trade_price = get_cached_price(customer_account, item_number, qty)
    if trade_price is not None:
        return {
            "customer_price": trade_price,
            "book_price": book_price,
            "source": "trade_agreement",
        }

    if book_price > 0:
        return {
            "customer_price": book_price,
            "book_price": book_price,
            "source": "book_price",
        }

    return {"customer_price": 0, "book_price": 0, "source": "none"}


def fetch_ship_methods() -> list[dict]:
    """Return available shipping methods.

    TODO: Wire to D365 DlvMode or similar entity.
    """
    return [
        {"code": "TRUCK", "name": "Truck Freight"},
        {"code": "UPS-GND", "name": "UPS Ground"},
        {"code": "UPS-2DA", "name": "UPS 2nd Day Air"},
        {"code": "FEDEX", "name": "FedEx Ground"},
        {"code": "WILL-CALL", "name": "Will Call / Pickup"},
    ]


def fetch_customers_for_api(salesman_key: str | None = None) -> list[dict]:
    """Return a customer list, optionally filtered by *salesman_key*."""
    base_url, token, company = get_d365_connection()
    from data.d365_entities import fetch_customers

    df = fetch_customers(base_url, token, company)
    if df.empty:
        return []

    if salesman_key and "SalesGroup" in df.columns:
        norm = normalize_key(salesman_key)
        df["_norm_sg"] = df["SalesGroup"].fillna("").astype(str).apply(normalize_key)
        df = df[df["_norm_sg"] == norm].drop(columns=["_norm_sg"])

    customers = [
        {"account": str(row.get("CustomerAccount", "")),
         "name": str(row.get("CustomerName", ""))}
        for _, row in df.iterrows()
    ]
    customers.sort(key=lambda c: c["name"])
    return customers
