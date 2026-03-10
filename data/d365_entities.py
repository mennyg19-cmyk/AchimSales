"""
D365 OData entity fetchers.

Each function fetches a specific entity with server-side $filter and $select,
then renames columns to internal standard names. All date filtering uses
US Eastern-converted dates.
"""

import logging
import time
from datetime import date

import pandas as pd

from core.columns import rename_columns, to_number
from core.odata import fetch_odata_batched, fetch_odata_entity
from data.field_maps import (
    BOOK_PRICE_FIELD_MAP,
    BOOK_PRICE_SELECT,
    CUSTOMER_FIELD_MAP,
    CUSTOMER_SELECT,
    MARKUP_TRANS_FIELD_MAP,
    MARKUP_TRANS_SELECT,
    PACKING_SLIP_FIELD_MAP,
    PACKING_SLIP_SELECT,
    PRODUCT_FIELD_MAP,
    PRODUCT_SELECT,
    SALES_INVOICE_HEADER_FIELD_MAP,
    SALES_INVOICE_HEADER_SELECT,
    SALES_INVOICE_LINE_FIELD_MAP,
    SALES_INVOICE_LINE_SELECT,
    SALES_ORDER_HEADER_FIELD_MAP,
    SALES_ORDER_HEADER_SELECT,
    SALES_ORDER_LINE_FIELD_MAP,
    SALES_ORDER_LINE_SELECT,
    WHS_LINE_FIELD_MAP,
    WHS_LINE_SELECT,
)

# Optional SalesOrderHeadersV3 fields; if $select fails, we retry without these
SALES_ORDER_HEADER_OPTIONAL_SELECT = ["CustomerRequisitionNumber"]

log = logging.getLogger(__name__)


def _date_filter(field: str, start: date, end: date) -> str:
    """Build OData date filter: field ge start and field le end."""
    start_str = f"{start.isoformat()}T00:00:00Z"
    end_str = f"{end.isoformat()}T23:59:59Z"
    return f"{field} ge {start_str} and {field} le {end_str}"


# =====================================================================
# Sales Order Headers (Ordered Report)
# =====================================================================

def fetch_sales_order_headers(
    base_url: str,
    token: str,
    start_date: date,
    end_date: date,
    company_id: str | None = None,
    customer_account: str | list[str] | None = None,
    status_filter: str | None = None,
) -> pd.DataFrame:
    """Fetch SalesOrderHeadersV3 filtered by OrderCreationDateTime and optionally by customer(s) and status (direct OData filter)."""
    customers = ([customer_account] if isinstance(customer_account, str) else customer_account) if customer_account else None
    log.info("Fetching SalesOrderHeadersV3 (%s to %s)%s%s", start_date, end_date,
             f", customer={','.join(customers)}" if customers else "",
             f", status={status_filter}" if status_filter else "")
    t0 = time.monotonic()

    date_fields = ["OrderCreationDateTime", "OrderCreationDate", "CreatedDateTime"]
    customer_filter_field = "InvoiceCustomerAccountNumber"
    df = None
    for select_list in (SALES_ORDER_HEADER_SELECT, [f for f in SALES_ORDER_HEADER_SELECT if f not in SALES_ORDER_HEADER_OPTIONAL_SELECT]):
        for date_field in date_fields:
            filter_expr = _date_filter(date_field, start_date, end_date)
            if customers:
                parts = [f"{customer_filter_field} eq '{str(c).replace(chr(39), chr(39)*2)}'" for c in customers]
                cust_filter = " or ".join(parts) if len(parts) > 1 else parts[0]
                filter_expr = f"({filter_expr}) and ({cust_filter})"
            if status_filter and status_filter.lower() == "open":
                filter_expr = f"({filter_expr}) and SalesOrderStatus ne 'Invoiced' and SalesOrderStatus ne 'Canceled'"
            try:
                df = fetch_odata_entity(
                    base_url, "SalesOrderHeadersV3", token,
                    select=select_list,
                    filter_expr=filter_expr,
                    company_id=company_id,
                )
                log.info("SalesOrderHeadersV3: filter on %s succeeded", date_field)
                break
            except Exception:
                log.debug("SalesOrderHeadersV3: filter on %s failed, trying next", date_field, exc_info=True)
        if df is not None and not df.empty:
            break
        if select_list == SALES_ORDER_HEADER_SELECT:
            log.info("SalesOrderHeadersV3: retrying without optional fields (e.g. CustomerRequisitionNumber)")

    if df is None or df.empty:
        log.info("SalesOrderHeadersV3: no headers in date range (%.1fs)", time.monotonic() - t0)
        return pd.DataFrame()

    df = rename_columns(df, SALES_ORDER_HEADER_FIELD_MAP)

    if "OrderDate" not in df.columns:
        for cand in ["OrderCreationDateTime", "CreatedDateTime"]:
            if cand in df.columns:
                df["OrderDate"] = df[cand]
                break

    log.info("SalesOrderHeadersV3: %d rows in %.1fs", len(df), time.monotonic() - t0)
    return df


# =====================================================================
# Sales Order Lines (Ordered Report)
# =====================================================================

def fetch_sales_order_lines(
    base_url: str,
    token: str,
    order_numbers: set[str],
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch SalesOrderLinesV3 filtered by SalesOrderNumber (batched)."""
    if not order_numbers:
        return pd.DataFrame()
    log.info("Fetching SalesOrderLinesV3 (%d orders)...", len(order_numbers))
    t0 = time.monotonic()

    df = fetch_odata_batched(
        base_url, "SalesOrderLinesV3", token,
        filter_field="SalesOrderNumber",
        filter_values=list(order_numbers),
        select=SALES_ORDER_LINE_SELECT,
        company_id=company_id,
    )
    if df.empty:
        log.info("SalesOrderLinesV3: 0 rows in %.1fs", time.monotonic() - t0)
        return df
    df = rename_columns(df, SALES_ORDER_LINE_FIELD_MAP)
    log.info("SalesOrderLinesV3: %d rows in %.1fs", len(df), time.monotonic() - t0)
    return df


# =====================================================================
# WHS Sales Lines (Ordered Report - warehouse release qty)
# =====================================================================

def fetch_whs_sales_lines(
    base_url: str,
    token: str,
    inventory_lot_ids: set[str],
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch WHSSalesLineBiEntities filtered by InventTransId (batched)."""
    ids = [s for s in inventory_lot_ids if s and str(s).strip() not in ("", "nan")]
    if not ids:
        return pd.DataFrame()
    log.info("Fetching WHSSalesLineBiEntities (%d IDs)...", len(ids))
    t0 = time.monotonic()

    df = fetch_odata_batched(
        base_url, "WHSSalesLineBiEntities", token,
        filter_field="InventTransId",
        filter_values=ids,
        select=WHS_LINE_SELECT,
        company_id=company_id,
    )
    if df.empty:
        log.info("WHSSalesLineBiEntities: 0 rows in %.1fs", time.monotonic() - t0)
        return df
    df = rename_columns(df, WHS_LINE_FIELD_MAP)
    log.info("WHSSalesLineBiEntities: %d rows in %.1fs", len(df), time.monotonic() - t0)
    return df


# =====================================================================
# Packing Slip Transactions (Ordered Report)
# =====================================================================

def fetch_packing_slip_trans(
    base_url: str,
    token: str,
    order_numbers: set[str],
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch CustPackingSlipTransBiEntities, aggregate Qty -> PackSlipQty."""
    if not order_numbers:
        return pd.DataFrame()
    log.info("Fetching CustPackingSlipTransBiEntities (%d orders)...", len(order_numbers))
    t0 = time.monotonic()

    df = fetch_odata_batched(
        base_url, "CustPackingSlipTransBiEntities", token,
        filter_field="SalesId",
        filter_values=list(order_numbers),
        select=PACKING_SLIP_SELECT,
        company_id=company_id,
    )
    if df.empty:
        log.info("CustPackingSlipTransBiEntities: 0 rows in %.1fs", time.monotonic() - t0)
        return pd.DataFrame()

    df = rename_columns(df, PACKING_SLIP_FIELD_MAP)

    qty_col = "Qty" if "Qty" in df.columns else None
    if qty_col is None:
        log.warning("CustPackingSlipTransBiEntities: no Qty column found")
        return pd.DataFrame()

    group_cols = [c for c in ["SalesId", "LineNum", "InventTransId"] if c in df.columns]
    if len(group_cols) >= 2:
        agg = df.groupby(group_cols, dropna=False)[qty_col].sum().reset_index()
        agg = agg.rename(columns={qty_col: "PackSlipQty"})
    else:
        return pd.DataFrame()

    log.info("CustPackingSlipTransBiEntities: %d rows -> %d aggregated in %.1fs", len(df), len(agg), time.monotonic() - t0)
    return agg


# =====================================================================
# Released Products (LineDescription fallback)
# =====================================================================

def fetch_released_products(
    base_url: str,
    token: str,
    item_numbers: list[str],
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch DVReleasedProducts for ProductName fallback."""
    if not item_numbers:
        return pd.DataFrame()
    log.info("Fetching DVReleasedProducts (%d items)...", len(item_numbers))
    t0 = time.monotonic()

    df = fetch_odata_batched(
        base_url, "DVReleasedProducts", token,
        filter_field="ItemNumber",
        filter_values=item_numbers,
        select=PRODUCT_SELECT,
        company_id=company_id,
        batch_size=100,
    )
    if df.empty:
        log.info("DVReleasedProducts: 0 rows in %.1fs", time.monotonic() - t0)
        return df
    df = rename_columns(df, PRODUCT_FIELD_MAP)
    log.info("DVReleasedProducts: %d rows in %.1fs", len(df), time.monotonic() - t0)
    return df


def fetch_book_prices(
    base_url: str,
    token: str,
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch standard sales price (Book Price) per item from ReleasedProductsV2.

    Returns DataFrame with columns: ItemNumber, BookPrice
    """
    log.info("Fetching ReleasedProductsV2 (book prices)")
    t0 = time.monotonic()

    df = fetch_odata_entity(
        base_url, "ReleasedProductsV2", token,
        select=BOOK_PRICE_SELECT,
        company_id=company_id,
    )
    if df.empty:
        log.info("ReleasedProductsV2: 0 rows in %.1fs", time.monotonic() - t0)
        return df
    df = rename_columns(df, BOOK_PRICE_FIELD_MAP)
    df["ItemNumber"] = df["ItemNumber"].astype(str).str.strip()
    df["BookPrice"] = to_number(df["BookPrice"])
    df = df.drop_duplicates(subset=["ItemNumber"], keep="first")
    log.info("ReleasedProductsV2: %d items in %.1fs", len(df), time.monotonic() - t0)
    return df


# =====================================================================
# Sales Invoice Headers (Invoiced + Salesman Reports)
# =====================================================================

def fetch_sales_invoice_headers(
    base_url: str,
    token: str,
    start_date: date,
    end_date: date,
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch SalesInvoiceHeadersV2 filtered by InvoiceDate."""
    log.info("Fetching SalesInvoiceHeadersV2 (%s to %s)", start_date, end_date)
    t0 = time.monotonic()
    filter_expr = _date_filter("InvoiceDate", start_date, end_date)

    df = fetch_odata_entity(
        base_url, "SalesInvoiceHeadersV2", token,
        select=SALES_INVOICE_HEADER_SELECT,
        filter_expr=filter_expr,
        company_id=company_id,
    )
    if df.empty:
        log.info("SalesInvoiceHeadersV2: 0 rows in %.1fs", time.monotonic() - t0)
        return df
    df = rename_columns(df, SALES_INVOICE_HEADER_FIELD_MAP)
    log.info("SalesInvoiceHeadersV2: %d rows in %.1fs", len(df), time.monotonic() - t0)
    return df


# =====================================================================
# Markup Transactions (Invoiced Report - charges)
# =====================================================================

def fetch_markup_trans(
    base_url: str,
    token: str,
    voucher_ids: set[str],
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch MarkupTrans filtered by Voucher (batched)."""
    if not voucher_ids:
        return pd.DataFrame()
    log.info("Fetching MarkupTransBiEntities (%d vouchers)...", len(voucher_ids))
    t0 = time.monotonic()

    df = fetch_odata_batched(
        base_url, "MarkupTransBiEntities", token,
        filter_field="Voucher",
        filter_values=list(voucher_ids),
        select=MARKUP_TRANS_SELECT,
        company_id=company_id,
    )
    if df.empty:
        log.info("MarkupTransBiEntities: 0 rows in %.1fs", time.monotonic() - t0)
        return df
    df = rename_columns(df, MARKUP_TRANS_FIELD_MAP)
    log.info("MarkupTransBiEntities: %d rows in %.1fs", len(df), time.monotonic() - t0)
    return df


# =====================================================================
# Sales Invoice Lines (Number 4 Report)
# =====================================================================

def fetch_sales_invoice_lines(
    base_url: str,
    token: str,
    start_date: date,
    end_date: date,
    company_id: str | None = None,
) -> pd.DataFrame:
    """Fetch SalesInvoiceV4Lines filtered by InvoiceDate."""
    log.info("Fetching SalesInvoiceV4Lines (%s to %s)", start_date, end_date)
    t0 = time.monotonic()
    filter_expr = _date_filter("InvoiceDate", start_date, end_date)

    df = fetch_odata_entity(
        base_url, "SalesInvoiceV4Lines", token,
        select=SALES_INVOICE_LINE_SELECT,
        filter_expr=filter_expr,
        company_id=company_id,
    )
    if df.empty:
        log.info("SalesInvoiceV4Lines: 0 rows in %.1fs", time.monotonic() - t0)
        return df
    df = rename_columns(df, SALES_INVOICE_LINE_FIELD_MAP)
    log.info("SalesInvoiceV4Lines: %d rows in %.1fs", len(df), time.monotonic() - t0)
    return df


# =====================================================================
# Customers (salesman assignment fallback)
# =====================================================================

def _coalesce_customer_name(df: pd.DataFrame) -> pd.DataFrame:
    """Coalesce AddressDescription, OrganizationName, NameAlias into CustomerName."""
    for col in ("AddressDescription", "OrganizationName", "NameAlias"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()

    df["CustomerName"] = df["AddressDescription"]
    blank = df["CustomerName"] == ""
    df.loc[blank, "CustomerName"] = df.loc[blank, "OrganizationName"]
    blank = df["CustomerName"] == ""
    df.loc[blank, "CustomerName"] = df.loc[blank, "NameAlias"]

    df = df.drop(columns=["AddressDescription", "OrganizationName", "NameAlias"], errors="ignore")
    return df


def fetch_customers(
    base_url: str,
    token: str,
    company_id: str | None = None,
    sales_group: str | None = None,
    customer_account: str | None = None,
) -> pd.DataFrame:
    """Fetch customer list with sales group for salesman assignment.

    If sales_group is provided, filters by CommissionSalesGroupId.
    If customer_account is provided, filters by CustomerAccount (single lookup).
    """
    parts = []
    if sales_group:
        parts.append(f"SalesGroup={sales_group}")
    if customer_account:
        parts.append(f"Account={customer_account}")
    scope = ", ".join(parts) if parts else "all"
    log.info("Fetching CustomersV3 (%s)", scope)
    t0 = time.monotonic()

    filters = []
    if sales_group:
        safe = str(sales_group).replace("'", "''")
        filters.append(f"CommissionSalesGroupId eq '{safe}'")
    if customer_account:
        safe = str(customer_account).replace("'", "''")
        filters.append(f"CustomerAccount eq '{safe}'")

    filter_expr = " and ".join(filters) if filters else None

    df = fetch_odata_entity(
        base_url, "CustomersV3", token,
        select=CUSTOMER_SELECT,
        filter_expr=filter_expr,
        company_id=company_id,
    )
    if df.empty:
        log.info("CustomersV3: 0 rows in %.1fs", time.monotonic() - t0)
        return df
    df = rename_columns(df, CUSTOMER_FIELD_MAP)
    df = _coalesce_customer_name(df)
    log.info("CustomersV3: %d rows in %.1fs", len(df), time.monotonic() - t0)
    return df
