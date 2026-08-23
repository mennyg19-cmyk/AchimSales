"""
Customer Activity Report -- data processing.

Starts from the *customer* table (all customers in D365), then asks D365 for
exactly ONE order per customer -- their most recent -- via a `$top=1` ordered
query run in parallel across customers. Each call returns a single row, so the
whole report pulls ~one row per customer instead of the entire order history.

The earlier version dragged every order for every customer across the wire
(358k+ rows since go-live) just to find each customer's latest, which made the
report take the better part of an hour. Per-customer top-1 lookups (a few
hundred customers, parallelised) finish in a couple of minutes.

Customers with no orders since D365 go-live get "N/A" for order fields.
Salesman assignment comes from the customer's SalesGroup, not from orders.
"""

import logging

import pandas as pd

from config.salesman_excel import get_salesman_display_name_xl, load_salesman_map
from core.columns import rename_columns
from core.dates import convert_d365_dates_to_eastern
from core.odata import fetch_top1_per_value
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

_LAST_ORDER_COLUMNS = ["CustomerAccount", "Last Order Date", "PO #", "Sales Order Number"]

# Narrow $select for the per-customer last-order lookup: just what the report shows.
_LAST_ORDER_SELECT = [
    "SalesOrderNumber",
    "OrderCreationDateTime",
    "InvoiceCustomerAccountNumber",
    "CustomerRequisitionNumber",
]

# Customers fan out across this many parallel $top=1 requests. 8 was throttle-clean
# in testing (~0.14s/customer) while keeping well under D365's request limits.
_LAST_ORDER_WORKERS = 8


def fetch_all_data(
    base_url: str,
    token: str,
    company_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch the customer universe and each customer's most recent order.

    Returns ``(customers_df, headers_df)`` where headers_df holds at most one
    order row per customer (their latest). ``build_customer_activity`` joins it
    onto the full customer list.
    """
    customers_df = fetch_customers(base_url, token, company_id=company_id)
    log.info("Customers fetched: %d rows", len(customers_df))

    if customers_df.empty:
        return customers_df, pd.DataFrame()

    accounts = [
        a for a in customers_df["CustomerAccount"].astype(str).str.strip()
        .drop_duplicates().tolist() if a
    ]

    rows = fetch_top1_per_value(
        base_url, "SalesOrderHeadersV3", token,
        filter_field="InvoiceCustomerAccountNumber",
        values=accounts,
        order_by="OrderCreationDateTime desc",
        select=_LAST_ORDER_SELECT,
        company_id=company_id,
        max_workers=_LAST_ORDER_WORKERS,
    )
    headers_df = rename_columns(pd.DataFrame(rows), SALES_ORDER_HEADER_FIELD_MAP) if rows else pd.DataFrame()
    log.info("Last orders fetched: %d customers with orders", len(headers_df))

    return customers_df, headers_df


def _latest_order_per_customer(headers_df: pd.DataFrame) -> pd.DataFrame:
    """Collapse raw order headers to one row per customer: their most recent order.

    Accepts the raw SalesOrderHeadersV3 shape (CustomerAccount, OrderDate,
    SalesOrderNumber, CustomerRequisition). Customers with no dated order are
    dropped here and resurface as "N/A" after the left-join in the caller.
    """
    if headers_df is None or headers_df.empty or "OrderDate" not in headers_df.columns:
        return pd.DataFrame(columns=_LAST_ORDER_COLUMNS)

    df = headers_df.copy()
    df["CustomerAccount"] = df["CustomerAccount"].astype(str).str.strip()
    df["OrderDate"] = convert_d365_dates_to_eastern(df["OrderDate"])
    if "CustomerRequisition" not in df.columns:
        df["CustomerRequisition"] = ""
    if "SalesOrderNumber" not in df.columns:
        df["SalesOrderNumber"] = ""

    dated = df.dropna(subset=["OrderDate"])
    if dated.empty:
        return pd.DataFrame(columns=_LAST_ORDER_COLUMNS)

    latest = dated.loc[dated.groupby("CustomerAccount", dropna=False)["OrderDate"].idxmax()]

    return pd.DataFrame({
        "CustomerAccount": latest["CustomerAccount"].values,
        "Last Order Date": latest["OrderDate"].values,
        "PO #": latest["CustomerRequisition"].fillna("").astype(str).str.strip().values,
        "Sales Order Number": latest["SalesOrderNumber"].astype(str).str.strip().values,
    })


def build_customer_activity(
    customers_df: pd.DataFrame,
    headers_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the customer activity DataFrame starting from ALL customers.

    Every customer in customers_df appears in the result. Raw order headers are
    reduced to each customer's most recent order and left-joined on; customers
    with no orders get N/A values. Salesman assignment comes from the customer's
    SalesGroup field.
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

    last_orders_df = _latest_order_per_customer(headers_df)
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
