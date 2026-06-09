"""
Customer Activity Report -- data processing.

Starts from the *customer* table (all customers in D365), then
batch-fetches order headers per customer group to find each customer's
most recent order.  Only the latest order per customer is kept in
memory, so the report stays well within Azure Automation's sandbox
limits even as order volume grows.

Customers with no orders since D365 go-live get "N/A" for order fields.
Salesman assignment comes from the customer's SalesGroup, not from orders.
"""

import gc
import logging

import pandas as pd

from config.salesman_excel import get_salesman_display_name_xl, load_salesman_map
from core.columns import rename_columns
from core.dates import D365_GO_LIVE, convert_d365_dates_to_eastern, get_today_eastern
from core.odata import fetch_odata_entity
from data.d365_entities import fetch_customers
from data.field_maps import SALES_ORDER_HEADER_FIELD_MAP

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "Customer Account",
    "Customer Name",
    "Last Order Date",
    "PO #",
    "Sales Order Number",
]

_LAST_ORDER_SELECT = [
    "SalesOrderNumber",
    "OrderCreationDateTime",
    "InvoiceCustomerAccountNumber",
    "CustomerRequisitionNumber",
]

BATCH_SIZE = 50


def fetch_all_data(
    base_url: str,
    token: str,
    company_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch customers, then batch-fetch only the latest order per customer.

    Instead of pulling every order header since go-live (OOM risk), we:
    1. Fetch the customer list (small).
    2. Split customer accounts into batches of ~50.
    3. For each batch, OData-query headers filtered to those accounts.
    4. Keep only the most recent order per customer.
    5. Return the merged last-order lookup alongside the customer list.
    """
    customers_df = fetch_customers(base_url, token, company_id=company_id)
    log.info("Customers fetched: %d rows", len(customers_df))

    if customers_df.empty:
        return customers_df, pd.DataFrame()

    all_accounts = (
        customers_df["CustomerAccount"].astype(str).str.strip()
        .drop_duplicates().tolist()
    )
    all_accounts = [a for a in all_accounts if a]
    log.info("Unique customer accounts to check: %d", len(all_accounts))

    last_orders = _batch_fetch_last_orders(
        base_url, token, all_accounts, company_id,
    )
    log.info("Last-order lookup built: %d customers with orders", len(last_orders))

    return customers_df, last_orders


def _batch_fetch_last_orders(
    base_url: str,
    token,
    accounts: list[str],
    company_id: str | None,
) -> pd.DataFrame:
    """Fetch order headers in batches of customer accounts, keep only the latest per customer."""
    today = get_today_eastern()
    start_str = f"{D365_GO_LIVE.isoformat()}T00:00:00Z"
    end_str = f"{today.isoformat()}T23:59:59Z"

    all_last: list[dict] = []
    num_batches = (len(accounts) + BATCH_SIZE - 1) // BATCH_SIZE
    date_fields = ["OrderCreationDateTime", "OrderCreationDate", "CreatedDateTime"]

    for batch_idx in range(num_batches):
        batch = accounts[batch_idx * BATCH_SIZE : (batch_idx + 1) * BATCH_SIZE]
        cust_parts = [
            f"InvoiceCustomerAccountNumber eq '{a.replace(chr(39), chr(39)*2)}'"
            for a in batch
        ]
        cust_filter = " or ".join(cust_parts)

        batch_df = None
        for date_field in date_fields:
            date_filter = f"{date_field} ge {start_str} and {date_field} le {end_str}"
            filter_expr = f"({date_filter}) and ({cust_filter})"
            try:
                batch_df = fetch_odata_entity(
                    base_url, "SalesOrderHeadersV3", token,
                    select=_LAST_ORDER_SELECT,
                    filter_expr=filter_expr,
                    company_id=company_id,
                    log_pages=False,
                )
                if batch_df is not None and not batch_df.empty:
                    break
            except Exception:
                log.debug("Date field %s failed for batch %d, trying next",
                          date_field, batch_idx + 1, exc_info=True)

        if batch_df is None or batch_df.empty:
            if (batch_idx + 1) % 10 == 0 or batch_idx == num_batches - 1:
                log.info("Batch %d/%d: no orders for %d customers",
                         batch_idx + 1, num_batches, len(batch))
            continue

        batch_df = rename_columns(batch_df, SALES_ORDER_HEADER_FIELD_MAP)
        _extract_last_per_customer(batch_df, all_last)
        del batch_df
        gc.collect()

        if (batch_idx + 1) % 10 == 0 or batch_idx == num_batches - 1:
            log.info("Batch %d/%d done (%d last-orders so far)",
                     batch_idx + 1, num_batches, len(all_last))

    if not all_last:
        return pd.DataFrame(columns=["CustomerAccount", "Last Order Date", "PO #", "Sales Order Number"])

    return pd.DataFrame(all_last)


def _extract_last_per_customer(df: pd.DataFrame, out: list[dict]) -> None:
    """From a batch of headers, find the latest order per customer and append to out."""
    if "OrderDate" in df.columns:
        df["OrderDate"] = convert_d365_dates_to_eastern(df["OrderDate"])
    if "CustomerRequisition" not in df.columns:
        df["CustomerRequisition"] = ""

    df["CustomerAccount"] = df["CustomerAccount"].astype(str).str.strip()

    for cust_acct, grp in df.groupby("CustomerAccount", dropna=False):
        order_dates = grp["OrderDate"].dropna() if "OrderDate" in grp.columns else pd.Series(dtype="datetime64[ns]")
        last_date = order_dates.max() if not order_dates.empty else pd.NaT

        if pd.notna(last_date):
            last_rows = grp.loc[grp["OrderDate"] == last_date]
            last_po = last_rows["CustomerRequisition"].fillna("").astype(str).str.strip().iloc[0]
            last_so = last_rows["SalesOrderNumber"].astype(str).str.strip().iloc[0]
        else:
            last_po = "N/A"
            last_so = "N/A"

        out.append({
            "CustomerAccount": str(cust_acct).strip(),
            "Last Order Date": last_date,
            "PO #": last_po,
            "Sales Order Number": last_so,
        })


def build_customer_activity(
    customers_df: pd.DataFrame,
    last_orders_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the customer activity DataFrame starting from ALL customers.

    Every customer in customers_df appears in the result.  Order info is
    left-joined from last_orders_df (one row per customer, already
    reduced by fetch_all_data); customers with no orders get N/A values.
    Salesman assignment comes from the customer's SalesGroup field.
    """
    if customers_df.empty:
        log.info("No customers -- returning empty activity report")
        return pd.DataFrame(columns=OUTPUT_COLUMNS + ["SalesGroup"])

    cust = customers_df.copy()
    cust["CustomerAccount"] = cust["CustomerAccount"].astype(str).str.strip()

    if "SalesGroup" not in cust.columns:
        cust["SalesGroup"] = ""
    cust["SalesGroup"] = cust["SalesGroup"].fillna("").astype(str).str.strip()

    if "CustomerName" not in cust.columns:
        cust["CustomerName"] = ""

    merged = cust.merge(last_orders_df, on="CustomerAccount", how="left")

    merged["PO #"] = merged["PO #"].fillna("N/A")
    merged["Sales Order Number"] = merged["Sales Order Number"].fillna("N/A")

    result = pd.DataFrame({
        "Customer Account": merged["CustomerAccount"],
        "Customer Name": merged["CustomerName"].fillna("").astype(str),
        "Last Order Date": merged["Last Order Date"],
        "PO #": merged["PO #"],
        "Sales Order Number": merged["Sales Order Number"],
        "SalesGroup": merged["SalesGroup"],
    })

    result = result.sort_values("Customer Name", ascending=True, na_position="last").reset_index(drop=True)
    log.info("Customer activity built: %d customers", len(result))
    return result


def split_by_salesman(
    activity_df: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Split the activity DataFrame into per-salesman DataFrames.

    Returns (assigned_dict, unassigned_df):
      - assigned_dict: {display_name: DataFrame with OUTPUT_COLUMNS}
      - unassigned_df: DataFrame of customers with no salesman (OUTPUT_COLUMNS)
    """
    if activity_df.empty:
        return {}, pd.DataFrame(columns=OUTPUT_COLUMNS)

    load_salesman_map()

    unassigned_mask = activity_df["SalesGroup"].isin(["", "unassigned"])
    unassigned_df = activity_df.loc[unassigned_mask, OUTPUT_COLUMNS].copy().reset_index(drop=True)

    assigned = activity_df[~unassigned_mask]
    result: dict[str, pd.DataFrame] = {}

    for sg, grp in assigned.groupby("SalesGroup", dropna=False):
        display_name = get_salesman_display_name_xl(str(sg))
        df = grp[OUTPUT_COLUMNS].copy().reset_index(drop=True)
        if display_name in result:
            result[display_name] = pd.concat([result[display_name], df], ignore_index=True)
        else:
            result[display_name] = df

    log.info("Split into %d salesman groups + %d unassigned customers", len(result), len(unassigned_df))
    return result, unassigned_df
