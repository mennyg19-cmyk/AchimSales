"""
Invoiced Report aggregation logic.

Builds summary, commission, detail, credit, and invoice views
from the canonical invoice detail DataFrame.
"""

import logging

import numpy as np
import pandas as pd

from config.commission_map import get_commission_rate
from config.salesman_map import pad_salesman_number
from core.columns import to_number

log = logging.getLogger(__name__)


def build_invoiced_views(detail_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build all views from invoice detail.

    Returns: (summary, commissions, details_net, credits, invoices)
    """
    if detail_df.empty:
        empty = pd.DataFrame()
        return empty, empty, empty, empty, empty

    df = detail_df.copy()
    for c in ["SubTotal Invoices", "Tariff Charges", "Freight Charges", "CC Charges", "Total Invoice"]:
        if c in df.columns:
            df[c] = to_number(df[c])

    details_net = _net_detail_by_invoice(df)
    is_credit = df["InvoiceNumber"].astype(str).str.upper().str.contains("CRD|CM|FC", regex=True, na=False)
    credits = df[is_credit].copy()
    invoices = df[~is_credit].copy()

    summary = _build_summary(df)
    commissions = _build_commissions(summary)

    return summary, commissions, details_net, credits, invoices


def _net_detail_by_invoice(df: pd.DataFrame) -> pd.DataFrame:
    """Net reversals: if an invoice has both positive and negative totals, sum distinct values."""
    money_cols = ["SubTotal Invoices", "Tariff Charges", "Freight Charges", "CC Charges", "Total Invoice"]
    existing_money = [c for c in money_cols if c in df.columns]

    group_cols = ["InvoiceNumber"]
    keep_first = [c for c in df.columns if c not in existing_money and c not in group_cols]

    agg_dict = {c: "first" for c in keep_first}
    agg_dict.update({c: "sum" for c in existing_money})

    netted = df.groupby("InvoiceNumber", dropna=False).agg(agg_dict).reset_index()
    return netted


def _build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate by customer: counts and sums."""
    group_cols = ["CustomerAccount", "CustomerName", "SalesmanNumber", "SalesmanName"]
    existing_group = [c for c in group_cols if c in df.columns]

    agg = df.groupby(existing_group, dropna=False).agg(
        InvoiceCount=("InvoiceNumber", "nunique"),
        **{c: (c, "sum") for c in ["SubTotal Invoices", "Tariff Charges", "Freight Charges", "CC Charges", "Total Invoice"] if c in df.columns},
    ).reset_index()

    agg = agg.rename(columns={
        "Tariff Charges": "Total Tariff Charges",
        "Freight Charges": "Total Freight Charges",
        "CC Charges": "Total CC Charges",
        "Total Invoice": "Total Invoices",
    })

    agg = agg.sort_values(by=existing_group[0] if existing_group else "InvoiceCount", na_position="last")
    return agg


def _build_commissions(summary: pd.DataFrame) -> pd.DataFrame:
    """Add commission columns to summary."""
    comm = summary.copy()
    if "SalesmanNumber" not in comm.columns:
        comm["Percent"] = 0.0
        comm["Commissions"] = 0.0
        return comm

    comm["Percent"] = comm["SalesmanNumber"].apply(lambda x: get_commission_rate(str(x)))

    sub = comm.get("SubTotal Invoices", pd.Series(0.0, index=comm.index))
    tariff = comm.get("Total Tariff Charges", pd.Series(0.0, index=comm.index))
    comm["Commission Base"] = sub + tariff
    comm["Commissions"] = comm["Commission Base"] * comm["Percent"]

    return comm


def build_reversal_audit(df: pd.DataFrame) -> pd.DataFrame:
    """Find invoices with both positive and negative totals in the same month (reversals)."""
    if df.empty or "Total Invoice" not in df.columns:
        return pd.DataFrame()

    df = df.copy()
    df["Total Invoice"] = to_number(df["Total Invoice"])

    grouped = df.groupby("InvoiceNumber")["Total Invoice"].agg(["min", "max"]).reset_index()
    mixed = grouped[(grouped["min"] < 0) & (grouped["max"] > 0)]["InvoiceNumber"]

    if mixed.empty:
        return pd.DataFrame()

    return df[df["InvoiceNumber"].isin(mixed)].sort_values(["InvoiceNumber", "InvoiceDate"])
