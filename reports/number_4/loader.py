"""
Number 4 Report data loader.

Fetches invoice lines from D365, enriches with customer/salesman data,
and prepares the canonical line-level DataFrame for aggregation.
"""

import logging
from datetime import date

import pandas as pd

from config.salesman_map import get_salesman_display_name
from core.columns import to_number
from data.d365_entities import (
    fetch_book_prices,
    fetch_customers,
    fetch_sales_invoice_headers,
    fetch_sales_invoice_lines,
)

log = logging.getLogger(__name__)


def fetch_number_4_data(
    base_url: str,
    token: str,
    start_date: date,
    end_date: date,
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch and merge all data needed for Number 4 Report.

    Returns DataFrame with columns:
        InvoiceNumber, InvoiceDate, Item_#, Item_Name, Qty, Price, Total_$,
        CustomerAccount, CustomerName, Salesman, BookPrice
    """
    lines = fetch_sales_invoice_lines(base_url, token, start_date, end_date, company_id)
    if lines.empty:
        log.info("No invoice lines for %s to %s", start_date, end_date)
        return pd.DataFrame()

    if "InvoiceDate" in lines.columns:
        lines["InvoiceDate"] = pd.to_datetime(lines["InvoiceDate"], errors="coerce", utc=True)
        lines["InvoiceDate"] = lines["InvoiceDate"].dt.tz_localize(None)

    for c in ["Qty", "Price", "Total_$"]:
        if c in lines.columns:
            lines[c] = to_number(lines[c])

    if "Total_$" not in lines.columns and "Qty" in lines.columns and "Price" in lines.columns:
        lines["Total_$"] = lines["Qty"] * lines["Price"]

    headers = fetch_sales_invoice_headers(base_url, token, start_date, end_date, company_id)
    if not headers.empty and "InvoiceNumber" in headers.columns and "CustomerAccount" in headers.columns:
        merge_cols = ["InvoiceNumber", "CustomerAccount"]
        if "SalesOrderNumber" in headers.columns:
            merge_cols.append("SalesOrderNumber")
        header_map = headers[merge_cols].drop_duplicates(subset=["InvoiceNumber"], keep="first")
        lines = lines.merge(header_map, on="InvoiceNumber", how="left")
    else:
        lines["CustomerAccount"] = ""

    pre_filter = len(lines)
    if "SalesOrderNumber" in lines.columns:
        so = lines["SalesOrderNumber"].fillna("").astype(str).str.strip()
        lines = lines[so != ""].reset_index(drop=True)
        lines.drop(columns=["SalesOrderNumber"], inplace=True, errors="ignore")
    log.info("Excluded %d free-text invoice lines (no SalesOrderNumber)", pre_filter - len(lines))
    if lines.empty:
        log.info("No invoice lines remaining after free-text exclusion")
        return pd.DataFrame()

    customers = fetch_customers(base_url, token, company_id)
    if not customers.empty and "CustomerAccount" in customers.columns:
        cust_map = customers[["CustomerAccount", "CustomerName"]].copy()
        if "SalesGroup" in customers.columns:
            cust_map["Salesman"] = customers["SalesGroup"].apply(
                lambda sg: get_salesman_display_name(sg) if sg else "Unassigned"
            )
        else:
            cust_map["Salesman"] = "Unassigned"
        cust_map = cust_map.drop_duplicates(subset=["CustomerAccount"], keep="last")
        lines = lines.merge(cust_map, on="CustomerAccount", how="left", suffixes=("", "_cust"))
        if "CustomerName_cust" in lines.columns:
            lines["CustomerName"] = lines["CustomerName"].fillna(lines["CustomerName_cust"])
            lines = lines.drop(columns=["CustomerName_cust"], errors="ignore")
    else:
        if "CustomerName" not in lines.columns:
            lines["CustomerName"] = ""
        if "Salesman" not in lines.columns:
            lines["Salesman"] = "Unassigned"

    lines["CustomerName"] = lines["CustomerName"].fillna("").astype(str).str.strip()
    lines["Salesman"] = lines["Salesman"].fillna("Unassigned").astype(str).str.strip()
    lines["CustomerAccount"] = lines["CustomerAccount"].fillna("").astype(str).str.strip()

    book = fetch_book_prices(base_url, token, company_id)
    if not book.empty and "Item_#" in lines.columns:
        book["_item_join"] = book["ItemNumber"].str.upper()
        lines["_item_join"] = lines["Item_#"].astype(str).str.strip().str.upper()
        lines = lines.merge(book[["_item_join", "BookPrice"]], on="_item_join", how="left")
        lines.drop(columns=["_item_join"], inplace=True, errors="ignore")
    else:
        lines["BookPrice"] = pd.NA

    return lines
