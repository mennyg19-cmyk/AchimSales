"""Invoiced report builder.

Mirrors the live ``reports/invoiced/writer.py`` sheet structure so the
test sandbox shows the same tabs and columns users already trust. Source
data is the ``invoiced_order_charges`` SP (HTTP Reporting API) -- a flat
per-invoice dump with separate charge columns.

Field mapping from SP -> live-style column names::

    InvoiceAccount               -> CustomerAccount
    CustomerName                 -> CustomerName
    InvoiceDate                  -> InvoiceDate
    Invoice                      -> InvoiceNumber
    SalesOrder                   -> SalesOrderNumber
    Amount                       -> SubTotal Invoices
    SH_TariffCharges             -> Tariff Charges
    SH_FreightCharges            -> Freight Charges
    SH_ProcessingFeesCharges     -> CC Charges
    Amount + all three charges   -> Total Invoice
    SalesGroup                   -> Salesman / SalesGroup

The new endpoint does not expose commission rate or amount, so the
Commissions tab is rendered as a placeholder ("pending commission feed")
that's hidden whenever a salesman filter is applied -- matching the old
report's rule that commissions never ship to salesmen.

Tabs (in order):
    1. Summary by Customer  -- one row per customer, sums + invoice count
    2. Commissions          -- placeholder until a rate feed is wired
    3. Full Details         -- one row per invoice (every column)
    4. Credits              -- rows whose invoice number starts CRD/CM/FC
    5. Invoices             -- all non-credit rows

Credit / invoice split mirrors ``reports/invoiced/aggregator.py``: the
new SP doesn't return a row-type flag so we infer from the invoice
number prefix.
"""
from __future__ import annotations

import re
from typing import Any, Iterable


# Mirrors webapp/reports/invoiced/aggregator.py's CREDIT_PREFIX_RE.
_CREDIT_PREFIX_RE = re.compile(r"^(CRD|CM|FC)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------


# One row per invoice -- "Full Details" tab + the source for Credits / Invoices.
FULL_DATA_COLS: list[dict[str, str]] = [
    {"field": "CustomerAccount",    "header": "CustomerAccount",    "type": "text"},
    {"field": "CustomerName",       "header": "CustomerName",       "type": "text"},
    {"field": "InvoiceDate",        "header": "InvoiceDate",        "type": "date"},
    {"field": "InvoiceNumber",      "header": "InvoiceNumber",      "type": "text"},
    {"field": "SalesOrderNumber",   "header": "SalesOrderNumber",   "type": "text"},
    {"field": "SubTotal Invoices",  "header": "SubTotal Invoices",  "type": "money"},
    {"field": "Tariff Charges",     "header": "Tariff Charges",     "type": "money"},
    {"field": "Freight Charges",    "header": "Freight Charges",    "type": "money"},
    {"field": "CC Charges",         "header": "CC Charges",         "type": "money"},
    {"field": "Total Invoice",      "header": "Total Invoice",      "type": "money"},
    {"field": "Salesman",           "header": "Salesman",           "type": "text"},
    {"field": "SalesGroup",         "header": "SalesGroup",         "type": "text"},
]


SUMMARY_COLS: list[dict[str, str]] = [
    {"field": "CustomerAccount",       "header": "CustomerAccount",       "type": "text"},
    {"field": "CustomerName",          "header": "CustomerName",          "type": "text"},
    {"field": "Salesman",              "header": "Salesman",              "type": "text"},
    {"field": "InvoiceCount",          "header": "InvoiceCount",          "type": "int"},
    {"field": "Total Tariff Charges",  "header": "Total Tariff Charges",  "type": "money"},
    {"field": "Total Freight Charges", "header": "Total Freight Charges", "type": "money"},
    {"field": "Total CC Charges",      "header": "Total CC Charges",      "type": "money"},
    {"field": "Total Invoices",        "header": "Total Invoices",        "type": "money"},
]


COMMISSIONS_PLACEHOLDER_COLS: list[dict[str, str]] = [
    {"field": "Message", "header": "Message", "type": "text"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _num(v: Any) -> float:
    if v is None or v == "" or v == "NULL":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _int(v: Any) -> int:
    return int(round(_num(v)))


def _str(v: Any) -> str:
    if v is None or v == "NULL":
        return ""
    return str(v)


def _date_only(v: Any) -> str:
    s = _str(v)
    return s[:10] if len(s) >= 10 else s


def _first(raw: dict, *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", "NULL"):
            return value
    return None


def _norm_row(raw: dict) -> dict:
    """Map an invoiced_order_charges row onto live-style column names."""
    amount       = round(_num(_first(raw, "Amount", "SubTotal", "SubTotalAmount")), 2)
    tariff_chg   = round(_num(_first(raw, "SH_TariffCharges", "TariffCharges", "Tariff Charges")), 2)
    freight_chg  = round(_num(_first(raw, "SH_FreightCharges", "FreightCharges", "Freight Charges")), 2)
    cc_chg       = round(_num(_first(raw, "SH_ProcessingFeesCharges", "ProcessingFeesCharges", "CCCharges", "CC Charges")), 2)
    total        = round(amount + tariff_chg + freight_chg + cc_chg, 2)

    salesgroup = _str(_first(raw, "SalesGroup", "salesgroup", "Salesman"))

    return {
        "CustomerAccount":   _str(_first(raw, "InvoiceAccount", "CustomerAccount", "customeraccount", "AccountNum")),
        "CustomerName":      _str(_first(raw, "CustomerName", "customername", "Name")),
        "InvoiceDate":       _date_only(_first(raw, "InvoiceDate", "Invoice Date", "DocumentDate")),
        "InvoiceNumber":     _str(_first(raw, "Invoice", "InvoiceNumber", "InvoiceNo")),
        "SalesOrderNumber":  _str(_first(raw, "SalesOrder", "SalesOrderNumber", "SalesId")),
        "SubTotal Invoices": amount,
        "Tariff Charges":    tariff_chg,
        "Freight Charges":   freight_chg,
        "CC Charges":        cc_chg,
        "Total Invoice":     total,
        # SalesGroup is what the new endpoint returns. Until a separate
        # salesman-master feed lands we surface it under both the
        # legacy "Salesman" header and the canonical SalesGroup column
        # so existing column logic + new dashboards both work.
        "Salesman":          salesgroup,
        "SalesGroup":        salesgroup,
    }


def _is_credit(invoice_no: str) -> bool:
    return bool(invoice_no and _CREDIT_PREFIX_RE.match(invoice_no.strip()))


# ---------------------------------------------------------------------------
# Tab builders
# ---------------------------------------------------------------------------


_SUMMARY_MONEY_FIELDS = (
    "Total Tariff Charges",
    "Total Freight Charges",
    "Total CC Charges",
    "Total Invoices",
)


def _build_summary_by_customer(invoices: list[dict]) -> dict:
    """Per-customer aggregation. Mirrors live ``_build_summary``."""
    buckets: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    for inv in invoices:
        key = inv["CustomerAccount"] or "(none)"
        if key not in buckets:
            buckets[key] = {
                "InvoiceCount":          0,
                "Total Tariff Charges":  0.0,
                "Total Freight Charges": 0.0,
                "Total CC Charges":      0.0,
                "Total Invoices":        0.0,
            }
            meta[key] = {
                "CustomerName": inv["CustomerName"],
                "Salesman":     inv["Salesman"],
            }
        b = buckets[key]
        b["InvoiceCount"]          += 1
        b["Total Tariff Charges"]  += inv["Tariff Charges"]
        b["Total Freight Charges"] += inv["Freight Charges"]
        b["Total CC Charges"]      += inv["CC Charges"]
        b["Total Invoices"]        += inv["Total Invoice"]

    rows = []
    for cust, b in buckets.items():
        for f in _SUMMARY_MONEY_FIELDS:
            b[f] = round(b[f], 2)
        rows.append({
            "CustomerAccount": cust,
            "CustomerName":    meta[cust]["CustomerName"],
            "Salesman":        meta[cust]["Salesman"],
            **b,
        })
    rows.sort(key=lambda r: -float(r["Total Invoices"] or 0))
    return {
        "key":     "summary_by_customer",
        "name":    "Summary by Customer",
        "columns": SUMMARY_COLS,
        "rows":    rows,
    }


def _build_commissions_placeholder() -> dict:
    """Single-row placeholder until a commission rate feed is wired.

    Tab is hidden whenever a salesman filter is applied (see
    ``report_runner._apply_tab_rules``), so non-admins never see this.
    """
    return {
        "key":     "commissions",
        "name":    "Commissions",
        "columns": COMMISSIONS_PLACEHOLDER_COLS,
        "rows":    [{
            "Message": (
                "Commission rates aren't wired up to the new invoiced_order_charges "
                "endpoint yet. The Commissions tab will populate once a rate/amount "
                "feed is connected."
            ),
        }],
    }


def _build_full_data(invoices: list[dict]) -> dict:
    return {
        "key":     "full_data",
        "name":    "Full Details",
        "columns": FULL_DATA_COLS,
        "rows":    invoices,
    }


def _build_credits(invoices: list[dict]) -> dict:
    rows = [inv for inv in invoices if _is_credit(inv["InvoiceNumber"])]
    return {
        "key":     "credits",
        "name":    "Credits",
        "columns": FULL_DATA_COLS,
        "rows":    rows,
    }


def _build_invoices(invoices: list[dict]) -> dict:
    rows = [inv for inv in invoices if not _is_credit(inv["InvoiceNumber"])]
    return {
        "key":     "invoices",
        "name":    "Invoices",
        "columns": FULL_DATA_COLS,
        "rows":    rows,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build(rows: Iterable[dict]) -> list[dict]:
    """Turn flat invoiced_order_charges rows into the multi-tab payload."""
    invoices = [_norm_row(r) for r in rows]
    return [
        _build_summary_by_customer(invoices),
        _build_commissions_placeholder(),
        _build_full_data(invoices),
        _build_credits(invoices),
        _build_invoices(invoices),
    ]
