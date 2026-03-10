"""
D365 data-fetching service.

Centralises the fetch-transform patterns that were previously duplicated
across customer_detail, order_detail, and api_customers route handlers.
"""

import logging
import math
from datetime import date, timedelta

from webapp_v2.helpers import get_d365_connection
from webapp_v2.db import normalize_key

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
