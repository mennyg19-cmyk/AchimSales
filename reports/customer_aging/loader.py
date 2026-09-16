"""
Customer Aging Report data loader.

Fetches CustAgedBalances from D365 and enriches with salesman assignment
and CustGroup from CustomersV3 (since CustAgedBalances does not include them).
"""

import logging

import pandas as pd

from core.auth import D365TokenManager
from core.columns import to_number
from data.d365_entities import fetch_cust_aged_balances, fetch_customers

log = logging.getLogger(__name__)

_SENTINEL_DATE = "1900-01-01"


def load_aging_data(
    base_url: str,
    token: D365TokenManager,
    company_id: str | None = None,
    customer_account: str | list[str] | None = None,
) -> pd.DataFrame:
    """Fetch aging balances and enrich with salesman + CustGroup from the customer master.

    The CustAgedBalances entity already returns one row per customer with:
        CustomerAccount, CustomerName, AmountDue, Current, 30, 60, 90, 91+,
        LastPaymentDate, LastPaymentAmount, NumOpenInvoices
    """
    df = fetch_cust_aged_balances(base_url, token, company_id, customer_account)
    if df.empty:
        return pd.DataFrame()

    for col in ("AmountDue", "Current", "30", "60", "90", "91+", "LastPaymentAmount"):
        if col in df.columns:
            df[col] = to_number(df[col])

    if "NumOpenInvoices" in df.columns:
        df["NumOpenInvoices"] = pd.to_numeric(df["NumOpenInvoices"], errors="coerce").fillna(0).astype(int)
    else:
        df["NumOpenInvoices"] = 0

    if "LastPaymentDate" in df.columns:
        df["LastPaymentDate"] = pd.to_datetime(df["LastPaymentDate"], errors="coerce")
        df.loc[df["LastPaymentDate"].dt.strftime("%Y-%m-%d") == _SENTINEL_DATE, "LastPaymentDate"] = pd.NaT

    # Enrich with CustGroup and salesman from CustomersV3
    customers = fetch_customers(base_url, token, company_id)
    if not customers.empty:
        cust_cols = ["CustomerAccount"]
        if "CustGroup" in customers.columns:
            cust_cols.append("CustGroup")
        if "SalesGroup" in customers.columns:
            cust_cols.append("SalesGroup")

        cust_lookup = customers[cust_cols].drop_duplicates(subset=["CustomerAccount"])
        df = df.merge(cust_lookup, on="CustomerAccount", how="left")

        if "SalesGroup" in df.columns:
            df["SalesGroup"] = df["SalesGroup"].fillna("").astype(str).str.strip()
            from config.salesman_excel import lookup_salesman_xl
            df["Salesman"] = df["SalesGroup"].apply(
                lambda sg: lookup_salesman_xl(sg).display_name if sg else ""
            )
        else:
            df["Salesman"] = ""
    else:
        df["SalesGroup"] = ""
        df["Salesman"] = ""

    if "CustGroup" not in df.columns:
        df["CustGroup"] = ""
    df["CustGroup"] = df["CustGroup"].fillna("").astype(str).str.strip()

    log.info("Aging data loaded: %d customers, total due $%.2f",
             len(df), df["AmountDue"].sum())
    return df
