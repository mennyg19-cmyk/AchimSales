"""
Factory functions for invoice-related test DataFrames.

Provides both *raw* OData-shaped data (for loader tests) and the
*canonical post-loader* shape used by aggregator/builder tests.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd


def make_invoice_headers(
    n: int = 5,
    invoice_date: date | str = "2026-02-20",
    total_amounts: list[float] | None = None,
    charge_amounts: list[float] | None = None,
    customers: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """OData-shaped invoice headers (pre-loader, post-rename)."""
    rng = np.random.RandomState(seed)
    if isinstance(invoice_date, str):
        invoice_date = date.fromisoformat(invoice_date)
    dt = datetime(invoice_date.year, invoice_date.month, invoice_date.day)

    customers = customers or [f"C{100 + i}" for i in range(n)]
    if len(customers) < n:
        customers = (customers * ((n // len(customers)) + 1))[:n]

    totals = total_amounts or [round(rng.uniform(50, 500), 2) for _ in range(n)]
    if len(totals) < n:
        totals = (totals * ((n // len(totals)) + 1))[:n]

    charges = charge_amounts or [round(t * 0.05, 2) for t in totals]
    if len(charges) < n:
        charges = (charges * ((n // len(charges)) + 1))[:n]

    return pd.DataFrame({
        "InvoiceNumber": [f"INV-{2000 + i}" for i in range(n)],
        "InvoiceDate": pd.to_datetime([dt] * n),
        "CustomerAccount": customers[:n],
        "SalesOrderNumber": [f"SO-{3000 + i}" for i in range(n)],
        "TotalInvoiceAmount": totals[:n],
        "TotalChargeAmount": charges[:n],
        "LedgerVoucher": [f"VOUCH-{i}" for i in range(n)],
        "CustomerName": [f"Customer {c}" for c in customers[:n]],
    })


def make_markup_trans(
    vouchers: list[str],
    charge_types: list[str] | None = None,
    amounts: list[float] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """MarkupTrans rows for a set of vouchers."""
    rng = np.random.RandomState(seed)
    charge_types = charge_types or ["Tariff", "Freight", "CC Processing"]
    rows = []
    for v in vouchers:
        for ct in charge_types:
            rows.append({
                "Voucher": v,
                "Txt": ct,
                "Amount": amounts[0] if amounts else round(rng.uniform(1, 20), 2),
            })
    return pd.DataFrame(rows)


def make_invoice_detail(
    n: int = 5,
    invoice_date: date | str = "2026-02-20",
    salesmen: list[str] | None = None,
    salesman_numbers: list[str] | None = None,
    customers: list[str] | None = None,
    subtotals: list[float] | None = None,
    tariffs: list[float] | None = None,
    freights: list[float] | None = None,
    cc_charges: list[float] | None = None,
    invoice_numbers: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Canonical post-loader invoice detail DataFrame.

    This shape matches what ``fetch_invoice_detail()`` returns and what
    ``build_invoiced_views()`` / ``build_salesman_full_year_data()`` expect.
    """
    rng = np.random.RandomState(seed)
    if isinstance(invoice_date, str):
        invoice_date = date.fromisoformat(invoice_date)
    dt = datetime(invoice_date.year, invoice_date.month, invoice_date.day)

    customers = customers or [f"C{100 + i}" for i in range(n)]
    if len(customers) < n:
        customers = (customers * ((n // len(customers)) + 1))[:n]

    salesmen = salesmen or ["MKolko"] * n
    if len(salesmen) < n:
        salesmen = (salesmen * ((n // len(salesmen)) + 1))[:n]

    salesman_numbers = salesman_numbers or ["01"] * n
    if len(salesman_numbers) < n:
        salesman_numbers = (salesman_numbers * ((n // len(salesman_numbers)) + 1))[:n]

    subs = subtotals or [round(rng.uniform(80, 400), 2) for _ in range(n)]
    if len(subs) < n:
        subs = (subs * ((n // len(subs)) + 1))[:n]
    tars = tariffs or [round(s * 0.05, 2) for s in subs]
    if len(tars) < n:
        tars = (tars * ((n // len(tars)) + 1))[:n]
    frs = freights or [round(s * 0.03, 2) for s in subs]
    if len(frs) < n:
        frs = (frs * ((n // len(frs)) + 1))[:n]
    ccs = cc_charges or [round(s * 0.02, 2) for s in subs]
    if len(ccs) < n:
        ccs = (ccs * ((n // len(ccs)) + 1))[:n]

    totals = [subs[i] + tars[i] + frs[i] + ccs[i] for i in range(n)]

    inv_nums = invoice_numbers or [f"INV-{2000 + i}" for i in range(n)]
    if len(inv_nums) < n:
        inv_nums = (inv_nums * ((n // len(inv_nums)) + 1))[:n]

    return pd.DataFrame({
        "CustomerAccount": customers[:n],
        "CustomerName": [f"Customer {c}" for c in customers[:n]],
        "InvoiceDate": pd.to_datetime([dt] * n),
        "InvoiceNumber": inv_nums[:n],
        "SalesOrderNumber": [f"SO-{3000 + i}" for i in range(n)],
        "SubTotal Invoices": subs[:n],
        "Tariff Charges": tars[:n],
        "Freight Charges": frs[:n],
        "CC Charges": ccs[:n],
        "Total Invoice": totals[:n],
        "Salesman": salesmen[:n],
        "SalesmanNumber": salesman_numbers[:n],
        "SalesmanName": [f"Salesman {sn}" for sn in salesman_numbers[:n]],
    })
