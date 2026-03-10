"""
Salesman Report data builder.

Aggregates invoice data by salesman and customer, computes
current vs prior year comparisons, YTD, and full year totals.
"""

import logging
from datetime import date

import pandas as pd

from config.salesman_map import pad_salesman_number
from core.columns import to_number

log = logging.getLogger(__name__)


def build_salesman_full_year_data(
    detail_df: pd.DataFrame,
    year: int,
) -> dict[int, pd.DataFrame]:
    """Build salesman report data for all 12 months.

    Includes all active customers: anyone with sales in current OR prior year.
    Returns {1: df_jan, 2: df_feb, ..., 12: df_dec} with same schema as build_salesman_month_data.
    """
    if detail_df.empty:
        return {}

    df = detail_df.copy()
    for c in ["SubTotal Invoices", "Tariff Charges", "Freight Charges", "CC Charges", "Total Invoice"]:
        if c in df.columns:
            df[c] = to_number(df[c])

    if "InvoiceDate" not in df.columns:
        return {}

    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    df["_year"] = df["InvoiceDate"].dt.year
    df["_month"] = df["InvoiceDate"].dt.month
    df["Sales"] = df.get("Total Invoice", 0) - df.get("CC Charges", 0) - df.get("Freight Charges", 0)

    group_cols = ["CustomerAccount", "CustomerName", "SalesmanNumber", "Salesman"]
    existing = [c for c in group_cols if c in df.columns]
    if not existing:
        return {}

    # Restrict to current and prior year
    df = df[(df["_year"] == year) | (df["_year"] == year - 1)]

    # Active customers: all (customer, salesman) pairs with sales in either year
    active = (
        df.groupby(existing, dropna=False)["Sales"]
        .sum()
        .reset_index()
        .drop(columns=["Sales"])
    )

    def _agg(subset: pd.DataFrame, label: str) -> pd.DataFrame:
        if subset.empty:
            return pd.DataFrame(columns=existing + [label])
        return subset.groupby(existing, dropna=False)["Sales"].sum().reset_index().rename(columns={"Sales": label})

    result_by_month: dict[int, pd.DataFrame] = {}

    for m in range(1, 13):
        current_month = df[(df["_year"] == year) & (df["_month"] == m)]
        prior_month = df[(df["_year"] == year - 1) & (df["_month"] == m)]
        ytd_current = df[(df["_year"] == year) & (df["_month"] <= m)]
        ytd_prior = df[(df["_year"] == year - 1) & (df["_month"] <= m)]
        full_current = df[df["_year"] == year]
        full_prior = df[df["_year"] == year - 1]

        result = _agg(current_month, "Sales_Current")
        if result.empty:
            result = active.copy()
            result["Sales_Current"] = 0.0

        for subset, label in [
            (prior_month, "Sales_Prior"),
            (ytd_current, "Sales_YTD_Current"),
            (ytd_prior, "Sales_YTD_Prior"),
            (full_current, "Sales_FullYear_Current"),
            (full_prior, "Sales_FullYear_Prior"),
        ]:
            agg_df = _agg(subset, label)
            if agg_df.empty:
                result[label] = 0.0
            else:
                result = result.merge(agg_df, on=existing, how="outer")

        for c in ["Sales_Current", "Sales_Prior", "Sales_YTD_Current", "Sales_YTD_Prior",
                  "Sales_FullYear_Current", "Sales_FullYear_Prior"]:
            if c not in result.columns:
                result[c] = 0.0
            result[c] = result[c].fillna(0.0)

        result["$ Month Diff"] = result["Sales_Current"] - result["Sales_Prior"]
        result["% Month Diff"] = (
            result["$ Month Diff"] / result["Sales_Prior"].replace(0, float("nan"))
        ).fillna(0)

        result["$ YTD Diff"] = result["Sales_YTD_Current"] - result["Sales_YTD_Prior"]
        result["% YTD Diff"] = (
            result["$ YTD Diff"] / result["Sales_YTD_Prior"].replace(0, float("nan"))
        ).fillna(0)

        result["$ FullYear Diff"] = result["Sales_FullYear_Current"] - result["Sales_FullYear_Prior"]
        result["% FullYear Diff"] = (
            result["$ FullYear Diff"] / result["Sales_FullYear_Prior"].replace(0, float("nan"))
        ).fillna(0)

        if "SalesmanNumber" in result.columns:
            result["Sort Number"] = result["SalesmanNumber"].apply(pad_salesman_number)
            result = result.sort_values(["Sort Number", "CustomerAccount"], na_position="last")
        else:
            result["Sort Number"] = ""

        result["Cust. #"] = result.get("CustomerAccount", "")
        result["Customer Name"] = result.get("CustomerName", "")

        result_by_month[m] = result

    return result_by_month


def build_salesman_month_data(
    detail_df: pd.DataFrame,
    year: int,
    month: int,
) -> pd.DataFrame:
    """Build salesman report data for a single month.

    Returns DataFrame with columns:
        Sort Number, Cust. #, Customer Name, Salesman,
        Sales_Current, Sales_Prior, Sales_YTD_Current, Sales_YTD_Prior,
        Sales_FullYear_Current, Sales_FullYear_Prior
    """
    if detail_df.empty:
        return pd.DataFrame()

    df = detail_df.copy()
    for c in ["SubTotal Invoices", "Tariff Charges", "Freight Charges", "CC Charges", "Total Invoice"]:
        if c in df.columns:
            df[c] = to_number(df[c])

    if "InvoiceDate" in df.columns:
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
        df["_year"] = df["InvoiceDate"].dt.year
        df["_month"] = df["InvoiceDate"].dt.month
    else:
        return pd.DataFrame()

    df["Sales"] = df.get("Total Invoice", 0) - df.get("CC Charges", 0) - df.get("Freight Charges", 0)

    group_cols = ["CustomerAccount", "CustomerName", "SalesmanNumber", "Salesman"]
    existing = [c for c in group_cols if c in df.columns]

    current_month = df[(df["_year"] == year) & (df["_month"] == month)]
    prior_month = df[(df["_year"] == year - 1) & (df["_month"] == month)]
    ytd_current = df[(df["_year"] == year) & (df["_month"] <= month)]
    ytd_prior = df[(df["_year"] == year - 1) & (df["_month"] <= month)]
    full_current = df[df["_year"] == year]
    full_prior = df[df["_year"] == year - 1]

    def _agg(subset, label):
        if subset.empty:
            return pd.DataFrame()
        return subset.groupby(existing, dropna=False)["Sales"].sum().reset_index().rename(columns={"Sales": label})

    result = _agg(current_month, "Sales_Current")
    if result.empty:
        return pd.DataFrame()

    for subset, label in [
        (prior_month, "Sales_Prior"),
        (ytd_current, "Sales_YTD_Current"),
        (ytd_prior, "Sales_YTD_Prior"),
        (full_current, "Sales_FullYear_Current"),
        (full_prior, "Sales_FullYear_Prior"),
    ]:
        agg = _agg(subset, label)
        if not agg.empty:
            result = result.merge(agg, on=existing, how="outer")

    for c in ["Sales_Current", "Sales_Prior", "Sales_YTD_Current", "Sales_YTD_Prior",
              "Sales_FullYear_Current", "Sales_FullYear_Prior"]:
        if c not in result.columns:
            result[c] = 0.0
        result[c] = result[c].fillna(0.0)

    result["$ Month Diff"] = result["Sales_Current"] - result["Sales_Prior"]
    result["% Month Diff"] = (result["$ Month Diff"] / result["Sales_Prior"].replace(0, float("nan"))).fillna(0)

    result["$ YTD Diff"] = result["Sales_YTD_Current"] - result["Sales_YTD_Prior"]
    result["% YTD Diff"] = (result["$ YTD Diff"] / result["Sales_YTD_Prior"].replace(0, float("nan"))).fillna(0)

    result["$ FullYear Diff"] = result["Sales_FullYear_Current"] - result["Sales_FullYear_Prior"]
    result["% FullYear Diff"] = (result["$ FullYear Diff"] / result["Sales_FullYear_Prior"].replace(0, float("nan"))).fillna(0)

    if "SalesmanNumber" in result.columns:
        result["Sort Number"] = result["SalesmanNumber"].apply(pad_salesman_number)
        result = result.sort_values(["Sort Number", "CustomerAccount"], na_position="last")
    else:
        result["Sort Number"] = ""

    result["Cust. #"] = result.get("CustomerAccount", "")
    result["Customer Name"] = result.get("CustomerName", "")

    return result
