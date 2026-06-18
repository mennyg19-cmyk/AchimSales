"""
Customer Activity Report -- data processing.

Starts from the *customer* table (all customers in D365), then pulls every
order header since go-live in ONE date-filtered query and reduces it to each
customer's most recent order. The old version queried headers 50 customers at
a time, sequentially, dragging every order for every customer across the wire
just to find the latest -- which made the report take the better part of an
hour. One scan + an in-memory reduce does the same work in a fraction of the
time (output is ~1,500 customers, so header volume is modest).

Customers with no orders since D365 go-live get "N/A" for order fields.
Salesman assignment comes from the customer's SalesGroup, not from orders.
"""

import logging

import pandas as pd

from config.salesman_excel import get_salesman_display_name_xl, load_salesman_map
from core.dates import D365_GO_LIVE, convert_d365_dates_to_eastern, get_today_eastern
from data.d365_entities import fetch_customers, fetch_sales_order_headers

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "Customer Account",
    "Customer Name",
    "Last Order Date",
    "PO #",
    "Sales Order Number",
]

_LAST_ORDER_COLUMNS = ["CustomerAccount", "Last Order Date", "PO #", "Sales Order Number"]


def fetch_all_data(
    base_url: str,
    token: str,
    company_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch the customer universe and all order headers since go-live.

    Returns ``(customers_df, headers_df)``. The headers are the raw
    SalesOrderHeadersV3 rows (one per order); ``build_customer_activity``
    reduces them to each customer's latest order. A single date-filtered scan
    replaces the previous 50-customers-at-a-time sequential loop.
    """
    customers_df = fetch_customers(base_url, token, company_id=company_id)
    log.info("Customers fetched: %d rows", len(customers_df))

    if customers_df.empty:
        return customers_df, pd.DataFrame()

    headers_df = fetch_sales_order_headers(
        base_url, token, D365_GO_LIVE, get_today_eastern(), company_id=company_id,
    )
    log.info("Order headers fetched: %d rows", len(headers_df))

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
