"""
Invoiced Report data loader.

Fetches invoice headers + markup transactions from D365,
classifies charges (freight, tariff, CC), and builds the
canonical invoice detail DataFrame.
"""

import logging
from datetime import date

import pandas as pd

from config.salesman_map import get_salesman_display_name, get_salesman_full_name, get_salesman_number
from core.columns import rename_columns, to_number
from core.odata import fetch_odata_batched
from data.d365_entities import (
    fetch_customers,
    fetch_markup_trans,
    fetch_sales_invoice_headers,
)
from data.field_maps import SALES_ORDER_HEADER_FIELD_MAP

log = logging.getLogger(__name__)


def _classify_charge(txt: str) -> str:
    """Classify a MarkupTrans.Txt value into charge type."""
    t = str(txt).strip().lower()
    if "tariff" in t:
        return "tariff"
    if "processing" in t or "cc" in t:
        return "cc"
    if "freight" in t:
        return "freight"
    return "other"


def fetch_invoice_detail(
    base_url: str,
    token: str,
    start_date: date,
    end_date: date,
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch and build canonical invoice detail from D365.

    Returns DataFrame with columns:
        CustomerAccount, CustomerName, InvoiceDate, InvoiceNumber,
        SalesOrderNumber, SubTotal Invoices, Tariff Charges,
        Freight Charges, CC Charges, Total Invoice, Salesman, SalesmanNumber, SalesmanName
    """
    headers = fetch_sales_invoice_headers(base_url, token, start_date, end_date, company_id)
    if headers.empty:
        log.info("No invoice headers for %s to %s", start_date, end_date)
        return pd.DataFrame()

    if "InvoiceDate" in headers.columns:
        headers["InvoiceDate"] = pd.to_datetime(headers["InvoiceDate"], errors="coerce", utc=True)
        headers["InvoiceDate"] = headers["InvoiceDate"].dt.tz_localize(None)

    voucher_ids = set()
    if "LedgerVoucher" in headers.columns:
        voucher_ids = set(headers["LedgerVoucher"].dropna().astype(str).str.strip().tolist())
        voucher_ids.discard("")
        voucher_ids.discard("nan")

    charges_df = pd.DataFrame()
    if voucher_ids:
        markup = fetch_markup_trans(base_url, token, voucher_ids, company_id)
        if not markup.empty:
            charges_df = _aggregate_charges(markup)

    detail = headers.copy()
    if "TotalInvoiceAmount" in detail.columns:
        detail["Total Invoice"] = to_number(detail["TotalInvoiceAmount"])
    else:
        detail["Total Invoice"] = 0.0

    detail["Tariff Charges"] = 0.0
    detail["Freight Charges"] = 0.0
    detail["CC Charges"] = 0.0

    if not charges_df.empty and "LedgerVoucher" in detail.columns:
        detail = detail.merge(charges_df, left_on="LedgerVoucher", right_on="Voucher", how="left")
        for ct in ["tariff", "freight", "cc"]:
            col = f"{ct}_amount"
            if col in detail.columns:
                detail[{"tariff": "Tariff Charges", "freight": "Freight Charges", "cc": "CC Charges"}[ct]] = (
                    detail[col].fillna(0)
                )
        detail = detail.drop(columns=["Voucher", "tariff_amount", "freight_amount", "cc_amount", "other_amount"], errors="ignore")

    for col in ["Tariff Charges", "Freight Charges", "CC Charges"]:
        detail[col] = detail[col].abs()

    detail["SubTotal Invoices"] = (
        detail["Total Invoice"] - detail["Tariff Charges"] - detail["Freight Charges"] - detail["CC Charges"]
    )

    if "SalesOrderNumber" not in detail.columns:
        detail["SalesOrderNumber"] = ""

    detail = _assign_salesman(detail, base_url, token, company_id)

    keep_cols = [
        "CustomerAccount", "CustomerName", "InvoiceDate", "InvoiceNumber",
        "SalesOrderNumber", "SubTotal Invoices", "Tariff Charges",
        "Freight Charges", "CC Charges", "Total Invoice",
        "Salesman", "SalesmanNumber", "SalesmanName",
    ]
    for c in keep_cols:
        if c not in detail.columns:
            detail[c] = ""

    return detail[keep_cols].copy()


def _aggregate_charges(markup: pd.DataFrame) -> pd.DataFrame:
    """Aggregate MarkupTrans into per-voucher charge columns."""
    if "Txt" not in markup.columns or "Amount" not in markup.columns or "Voucher" not in markup.columns:
        return pd.DataFrame()

    markup["_charge_type"] = markup["Txt"].apply(_classify_charge)
    markup["Amount"] = to_number(markup["Amount"])

    pivot = markup.groupby(["Voucher", "_charge_type"])["Amount"].sum().reset_index()
    pivot = pivot.pivot_table(index="Voucher", columns="_charge_type", values="Amount", fill_value=0).reset_index()

    for ct in ["tariff", "freight", "cc", "other"]:
        col = f"{ct}_amount" if ct != "other" else "other_amount"
        if ct in pivot.columns:
            pivot = pivot.rename(columns={ct: col})
        else:
            pivot[col] = 0.0

    return pivot


def _assign_salesman(
    detail: pd.DataFrame,
    base_url: str,
    token: str,
    company_id: str | None,
) -> pd.DataFrame:
    """Assign salesman to each invoice row.

    Priority: SalesOrderHeaders.CommissionSalesRepresentativeGroupId -> CustomersV3.SalesGroup
    """
    detail["Salesman"] = ""
    detail["SalesmanNumber"] = ""
    detail["SalesmanName"] = ""

    so_nums: set[str] = set()
    if "SalesOrderNumber" in detail.columns:
        so_nums = set(
            detail["SalesOrderNumber"].dropna().astype(str).str.strip()
            .replace({"": None, "nan": None}).dropna().tolist()
        )

    so_salesman_map: dict[str, str] = {}
    if so_nums:
        try:
            so_headers = fetch_odata_batched(
                base_url, "SalesOrderHeadersV3", token,
                filter_field="SalesOrderNumber",
                filter_values=list(so_nums),
                select=["SalesOrderNumber", "CommissionSalesRepresentativeGroupId"],
                company_id=company_id,
            )
            so_headers = rename_columns(so_headers, SALES_ORDER_HEADER_FIELD_MAP)
            if not so_headers.empty and "SalesOrderNumber" in so_headers.columns and "Salesman" in so_headers.columns:
                valid = so_headers.dropna(subset=["SalesOrderNumber", "Salesman"])
                valid = valid[valid["Salesman"].astype(str).str.strip() != ""]
                so_salesman_map = dict(zip(
                    valid["SalesOrderNumber"].astype(str).str.strip(),
                    valid["Salesman"].astype(str).str.strip(),
                ))
                log.info("Built SO->salesman map: %d entries from %d order numbers", len(so_salesman_map), len(so_nums))
        except Exception:
            log.warning("Could not fetch SalesOrderHeaders for salesman assignment", exc_info=True)

    cust_salesman_map: dict[str, str] = {}
    cust_name_map: dict[str, str] = {}
    try:
        customers = fetch_customers(base_url, token, company_id)
        if not customers.empty and "CustomerAccount" in customers.columns:
            accts = customers["CustomerAccount"].astype(str).str.strip()
            if "CustomerName" in customers.columns:
                cust_name_map = dict(zip(
                    accts, customers["CustomerName"].astype(str).str.strip(),
                ))
            if "SalesGroup" in customers.columns:
                valid = customers.dropna(subset=["CustomerAccount", "SalesGroup"])
                valid = valid[valid["SalesGroup"].astype(str).str.strip() != ""]
                cust_salesman_map = dict(zip(
                    valid["CustomerAccount"].astype(str).str.strip(),
                    valid["SalesGroup"].astype(str).str.strip(),
                ))
    except Exception:
        log.warning("Could not fetch CustomersV3 for salesman/customer-name assignment", exc_info=True)

    so_col = detail["SalesOrderNumber"].astype(str).str.strip()
    acct_col = detail["CustomerAccount"].astype(str).str.strip()

    sg = so_col.map(so_salesman_map).fillna(acct_col.map(cust_salesman_map)).fillna("")

    detail["Salesman"] = sg.map(lambda s: get_salesman_display_name(s) if s else "Unassigned")
    detail["SalesmanNumber"] = sg.map(lambda s: get_salesman_number(s) if s else "?unassigned")
    detail["SalesmanName"] = sg.map(lambda s: get_salesman_full_name(s) if s else "Unassigned")

    if cust_name_map and ("CustomerName" not in detail.columns or detail["CustomerName"].astype(str).str.strip().eq("").all()):
        detail["CustomerName"] = acct_col.map(cust_name_map).fillna("")

    return detail
