"""
Factory functions for customer-related test DataFrames.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


def make_customers(
    n: int = 10,
    sales_groups: list[str] | None = None,
    cust_groups: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a customer master DataFrame (post-rename shape)."""
    rng = np.random.RandomState(seed)
    sgs = sales_groups or [f"SG{rng.randint(1, 5):02d}" for _ in range(n)]
    if len(sgs) < n:
        sgs = (sgs * ((n // len(sgs)) + 1))[:n]

    cgs = cust_groups or [f"GRP{rng.choice(['A', 'B', 'C'])}" for _ in range(n)]
    if len(cgs) < n:
        cgs = (cgs * ((n // len(cgs)) + 1))[:n]

    return pd.DataFrame({
        "CustomerAccount": [f"C{100 + i}" for i in range(n)],
        "CustomerName": [f"Customer C{100 + i}" for i in range(n)],
        "SalesGroup": sgs[:n],
        "CustGroup": cgs[:n],
        "OrganizationName": [f"Org {i}" for i in range(n)],
        "NameAlias": [f"Alias{i}" for i in range(n)],
    })


def make_aged_balances(
    n: int = 5,
    customers: list[str] | None = None,
    amount_due: list[float] | None = None,
    buckets: dict[str, list[float]] | None = None,
    last_payment_dates: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate CustAgedBalances-shaped DataFrame (post-rename)."""
    rng = np.random.RandomState(seed)
    custs = customers or [f"C{100 + i}" for i in range(n)]
    if len(custs) < n:
        custs = (custs * ((n // len(custs)) + 1))[:n]

    dues = amount_due or [round(rng.uniform(100, 5000), 2) for _ in range(n)]
    if len(dues) < n:
        dues = (dues * ((n // len(dues)) + 1))[:n]

    default_buckets = {
        "Current": [round(d * 0.4, 2) for d in dues],
        "30": [round(d * 0.25, 2) for d in dues],
        "60": [round(d * 0.15, 2) for d in dues],
        "90": [round(d * 0.1, 2) for d in dues],
        "91+": [round(d * 0.1, 2) for d in dues],
    }
    buckets = buckets or default_buckets

    dates = last_payment_dates or ["2026-01-15"] * n
    if len(dates) < n:
        dates = (dates * ((n // len(dates)) + 1))[:n]

    return pd.DataFrame({
        "CustomerAccount": custs[:n],
        "CustomerName": [f"Customer {c}" for c in custs[:n]],
        "AmountDue": dues[:n],
        "Current": buckets.get("Current", [0.0] * n)[:n],
        "30": buckets.get("30", [0.0] * n)[:n],
        "60": buckets.get("60", [0.0] * n)[:n],
        "90": buckets.get("90", [0.0] * n)[:n],
        "91+": buckets.get("91+", [0.0] * n)[:n],
        "LastPaymentDate": pd.to_datetime(dates[:n]),
        "LastPaymentAmount": [round(rng.uniform(50, 500), 2) for _ in range(n)],
        "NumOpenInvoices": [rng.randint(0, 10) for _ in range(n)],
    })
