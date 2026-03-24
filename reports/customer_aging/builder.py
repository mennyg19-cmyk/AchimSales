"""
Customer Aging Report builder.

Splits the aging data into the required views:
  - All Salesmen, All Customers
  - One sheet per salesman
"""

import logging

import pandas as pd

log = logging.getLogger(__name__)

REPORT_COLUMNS = [
    "CustomerAccount",
    "CustomerName",
    "Salesman",
    "AmountDue",
    "LastPaymentDate",
    "LastPaymentAmount",
    "NumOpenInvoices",
    "Current",
    "30",
    "60",
    "90",
    "91+",
]

DISPLAY_HEADERS = [
    "Cust #",
    "Cust Name",
    "Salesman",
    "Amount Due",
    "Last Payment Date",
    "Last Payment Amount",
    "Num Open Invoices",
    "Current",
    "30",
    "60",
    "90",
    "91+",
]


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all report columns exist and are in the correct order."""
    for col in REPORT_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col in ("CustomerAccount", "CustomerName", "Salesman") else 0
    return df[REPORT_COLUMNS].copy()


def _sort_df(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by Salesman then CustomerAccount for consistent output."""
    sort_cols = [c for c in ("Salesman", "CustomerAccount") if c in df.columns]
    if sort_cols:
        return df.sort_values(sort_cols, na_position="last").reset_index(drop=True)
    return df


def build_master_sheets(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build the master workbook sheet dict.

    Returns {sheet_name: DataFrame} in the order:
      1. All Salesmen, All Customers
      2+. One sheet per salesman (sorted alphabetically)
    """
    df = _ensure_columns(df)
    sheets: dict[str, pd.DataFrame] = {}

    sheets["All Customers"] = _sort_df(df)

    salesmen = sorted(df["Salesman"].dropna().astype(str).str.strip().unique())
    for sm in salesmen:
        if not sm:
            continue
        sm_data = df[df["Salesman"].astype(str).str.strip() == sm].copy()
        sm_data = _sort_df(sm_data)
        safe_name = sm[:31]
        sheets[safe_name] = sm_data

    log.info("Built %d sheets for master workbook (%d total customers)",
             len(sheets), len(df))
    return sheets


def build_salesman_sheet(df: pd.DataFrame, salesman_name: str) -> pd.DataFrame:
    """Build a single-sheet DataFrame for one salesman."""
    df = _ensure_columns(df)
    sm_data = df[df["Salesman"].astype(str).str.strip() == salesman_name].copy()
    return _sort_df(sm_data)
