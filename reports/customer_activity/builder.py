"""
Customer Activity Report -- data processing.

Starts from the *customer* table (all customers in D365), joins to
all-time order headers to find each customer's most recent order.
Customers with no orders ever still appear with "N/A" for order fields.

Salesman assignment comes from the customer's SalesGroup, not from orders.
"""

import logging
from datetime import date

import pandas as pd

from config.salesman_excel import get_salesman_display_name_xl, load_salesman_map
from core.dates import convert_d365_dates_to_eastern, get_today_eastern
from data.d365_entities import fetch_customers, fetch_sales_order_headers

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "Customer Account",
    "Customer Name",
    "Last Order Date",
    "PO #",
    "Sales Order Number",
]

CURRENCY_COLUMNS: set[str] = set()


def fetch_all_data(
    base_url: str,
    token: str,
    company_id: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch customers and all-time order headers from D365.

    Returns (customers_df, headers_df).  headers_df may be empty if no
    orders exist at all -- that is fine; every customer still appears.
    """
    today = get_today_eastern()
    all_time_start = date(2000, 1, 1)

    customers_df = fetch_customers(base_url, token, company_id=company_id)
    log.info("Customers fetched: %d rows", len(customers_df))

    headers_df = fetch_sales_order_headers(
        base_url, token, all_time_start, today, company_id=company_id,
    )
    log.info("Order headers fetched: %d rows", len(headers_df))

    return customers_df, headers_df


def _build_last_order_lookup(headers_df: pd.DataFrame) -> pd.DataFrame:
    """From raw order headers, return one row per customer with last-order info."""
    if headers_df.empty:
        return pd.DataFrame(columns=["CustomerAccount", "Last Order Date", "PO #", "Sales Order Number"])

    h = headers_df.copy()
    if "OrderDate" in h.columns:
        h["OrderDate"] = convert_d365_dates_to_eastern(h["OrderDate"])
    if "CustomerRequisition" not in h.columns:
        h["CustomerRequisition"] = ""

    h["CustomerAccount"] = h["CustomerAccount"].astype(str).str.strip()

    rows = []
    for cust_acct, grp in h.groupby("CustomerAccount", dropna=False):
        order_dates = grp["OrderDate"].dropna() if "OrderDate" in grp.columns else pd.Series(dtype="datetime64[ns]")
        last_date = order_dates.max() if not order_dates.empty else pd.NaT

        if pd.notna(last_date):
            last_rows = grp.loc[grp["OrderDate"] == last_date]
            last_po = last_rows["CustomerRequisition"].fillna("").astype(str).str.strip().iloc[0]
            last_so = last_rows["SalesOrderNumber"].astype(str).str.strip().iloc[0]
        else:
            last_po = "N/A"
            last_so = "N/A"

        rows.append({
            "CustomerAccount": str(cust_acct).strip(),
            "Last Order Date": last_date,
            "PO #": last_po,
            "Sales Order Number": last_so,
        })

    return pd.DataFrame(rows)


def build_customer_activity(
    customers_df: pd.DataFrame,
    headers_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build the customer activity DataFrame starting from ALL customers.

    Every customer in customers_df appears in the result.  Order info is
    left-joined from headers_df; customers with no orders get N/A values.
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

    last_orders = _build_last_order_lookup(headers_df)

    merged = cust.merge(last_orders, on="CustomerAccount", how="left")

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
