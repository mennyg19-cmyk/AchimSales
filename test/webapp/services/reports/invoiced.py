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

Salesman # / Name + commission % are looked up from the local
``app_salesmen`` table (keyed by the normalized SalesGroup). That table
also drives the Commissions tab, which mirrors the live aggregator's
``Commission Base = SubTotal + Tariff`` and ``Commissions = Base * pct``
formula. When a salesman filter is applied at the request level,
``report_runner._apply_tab_rules`` drops the Commissions tab entirely
so salesmen never see commission data (matching the live report's
``skip_commissions=bool(salesman_filter)`` rule).

Tabs (in order):
    1. Summary by Customer  -- one row per (customer, salesman), sums + invoice count
    2. Commissions          -- per-salesman commission math (admin-only)
    3. Full Details         -- one row per invoice (every column)
    4. Credits              -- rows whose invoice number starts CRD/CM/FC
    5. Invoices             -- all non-credit rows

Credit / invoice split mirrors ``reports/invoiced/aggregator.py``: the
new SP doesn't return a row-type flag so we infer from the invoice
number prefix.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable

log = logging.getLogger(__name__)


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
    {"field": "SalesmanNumber",     "header": "SalesmanNumber",     "type": "text"},
    {"field": "SalesmanName",       "header": "SalesmanName",       "type": "text"},
    {"field": "SalesGroup",         "header": "SalesGroup",         "type": "text"},
]


SUMMARY_COLS: list[dict[str, str]] = [
    {"field": "CustomerAccount",       "header": "CustomerAccount",       "type": "text"},
    {"field": "CustomerName",          "header": "CustomerName",          "type": "text"},
    {"field": "Salesman",              "header": "Salesman",              "type": "text"},
    {"field": "SalesmanNumber",        "header": "SalesmanNumber",        "type": "text"},
    {"field": "SalesmanName",          "header": "SalesmanName",          "type": "text"},
    {"field": "InvoiceCount",          "header": "InvoiceCount",          "type": "int"},
    {"field": "SubTotal Invoices",     "header": "SubTotal Invoices",     "type": "money"},
    {"field": "Total Tariff Charges",  "header": "Total Tariff Charges",  "type": "money"},
    {"field": "Total Freight Charges", "header": "Total Freight Charges", "type": "money"},
    {"field": "Total CC Charges",      "header": "Total CC Charges",      "type": "money"},
    {"field": "Total Invoices",        "header": "Total Invoices",        "type": "money"},
]


COMMISSION_COLS: list[dict[str, str]] = SUMMARY_COLS + [
    {"field": "Percent",         "header": "Percent",         "type": "percent"},
    {"field": "Commission Base", "header": "Commission Base", "type": "money"},
    {"field": "Commissions",     "header": "Commissions",     "type": "money"},
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


def _load_salesman_map() -> dict[str, dict]:
    """Cache the local salesman-master keyed by normalized key.

    Returns a dict of ``{normalized_key: {number, full_name, display_name,
    commission_pct}}``. Empty dict if the lookup fails (the builder
    treats no-match defensively).
    """
    try:
        from test.webapp.db import list_salesman_map
        rows = list_salesman_map()
    except Exception:
        log.exception("invoiced: failed to load app_salesmen; commissions will be zero")
        return {}
    out: dict[str, dict] = {}
    for r in rows or []:
        key = (r.get("key") or "").strip().lower()
        if not key:
            continue
        out[key] = {
            "number":         (r.get("number") or "").strip(),
            "full_name":      (r.get("full_name") or "").strip(),
            "display_name":   (r.get("display_name") or "").strip(),
            "commission_pct": float(r.get("commission_pct") or 0.0),
        }
    return out


def _sm_key(sales_group: str) -> str:
    """Normalize a SalesGroup to the app_salesmen.key form (lowercase alnum)."""
    return re.sub(r"[^a-z0-9]+", "", (sales_group or "").strip().lower())


def _norm_row(raw: dict, sm_map: dict[str, dict]) -> dict:
    """Map an invoiced_order_charges row onto live-style column names."""
    amount       = round(_num(_first(raw, "Amount", "SubTotal", "SubTotalAmount")), 2)
    tariff_chg   = round(_num(_first(raw, "SH_TariffCharges", "TariffCharges", "Tariff Charges")), 2)
    freight_chg  = round(_num(_first(raw, "SH_FreightCharges", "FreightCharges", "Freight Charges")), 2)
    cc_chg       = round(_num(_first(raw, "SH_ProcessingFeesCharges", "ProcessingFeesCharges", "CCCharges", "CC Charges")), 2)
    total        = round(amount + tariff_chg + freight_chg + cc_chg, 2)

    salesgroup = _str(_first(raw, "SalesGroup", "salesgroup", "Salesman"))
    sm = sm_map.get(_sm_key(salesgroup)) if salesgroup else None

    # Salesman display label prefers display_name (friendly) over full_name
    # over the raw SalesGroup code, mirroring the dropdown precedence the
    # rest of the app uses.
    if sm:
        salesman_label = sm.get("display_name") or sm.get("full_name") or salesgroup
        salesman_number = sm.get("number") or ""
        salesman_name = sm.get("full_name") or ""
    else:
        salesman_label = salesgroup
        salesman_number = ""
        salesman_name = ""

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
        "Salesman":          salesman_label,
        "SalesmanNumber":    salesman_number,
        "SalesmanName":      salesman_name,
        "SalesGroup":        salesgroup,
    }


def _is_credit(invoice_no: str) -> bool:
    return bool(invoice_no and _CREDIT_PREFIX_RE.match(invoice_no.strip()))


# ---------------------------------------------------------------------------
# Tab builders
# ---------------------------------------------------------------------------


_SUMMARY_MONEY_FIELDS = (
    "SubTotal Invoices",
    "Total Tariff Charges",
    "Total Freight Charges",
    "Total CC Charges",
    "Total Invoices",
)


def _build_summary_by_customer(invoices: list[dict]) -> dict:
    """Per-(customer, salesman) aggregation. Mirrors live ``_build_summary``.

    Grouped on ``(CustomerAccount, SalesmanNumber)`` so that the same
    customer billed by two different salesmen produces two rows --
    matches the live aggregator's group-cols list of
    ``[CustomerAccount, CustomerName, SalesmanNumber, SalesmanName]``.
    """
    buckets: dict[tuple, dict] = {}
    meta: dict[tuple, dict] = {}
    for inv in invoices:
        key = (inv["CustomerAccount"] or "(none)", inv["SalesmanNumber"] or "")
        if key not in buckets:
            buckets[key] = {
                "InvoiceCount":          0,
                "SubTotal Invoices":     0.0,
                "Total Tariff Charges":  0.0,
                "Total Freight Charges": 0.0,
                "Total CC Charges":      0.0,
                "Total Invoices":        0.0,
            }
            meta[key] = {
                "CustomerName":   inv["CustomerName"],
                "Salesman":       inv["Salesman"],
                "SalesmanName":   inv["SalesmanName"],
                "SalesGroup":     inv["SalesGroup"],
            }
        b = buckets[key]
        b["InvoiceCount"]          += 1
        b["SubTotal Invoices"]     += inv["SubTotal Invoices"]
        b["Total Tariff Charges"]  += inv["Tariff Charges"]
        b["Total Freight Charges"] += inv["Freight Charges"]
        b["Total CC Charges"]      += inv["CC Charges"]
        b["Total Invoices"]        += inv["Total Invoice"]

    rows = []
    for (cust, sm_no), b in buckets.items():
        for f in _SUMMARY_MONEY_FIELDS:
            b[f] = round(b[f], 2)
        m = meta[(cust, sm_no)]
        rows.append({
            "CustomerAccount": cust,
            "CustomerName":    m["CustomerName"],
            "Salesman":        m["Salesman"],
            "SalesmanNumber":  sm_no,
            "SalesmanName":    m["SalesmanName"],
            "_sales_group":    m["SalesGroup"],  # not surfaced, used by commissions
            **b,
        })
    rows.sort(key=lambda r: -float(r["Total Invoices"] or 0))
    return {
        "key":     "summary_by_customer",
        "name":    "Summary by Customer",
        "columns": SUMMARY_COLS,
        "rows":    rows,
    }


def _build_commissions(summary_rows: list[dict], sm_map: dict[str, dict]) -> dict:
    """Per-salesman commission math.

    Mirrors ``reports/invoiced/aggregator._build_commissions``:
    ``Commission Base = SubTotal Invoices + Total Tariff Charges`` and
    ``Commissions = Commission Base * commission_pct``. The percent
    comes from ``app_salesmen.commission_pct`` keyed by the normalized
    SalesGroup. Rows where we have no commission rate fall through with
    zero so the customer still appears, just with $0 commission.
    """
    rows: list[dict] = []
    for r in summary_rows:
        sg = r.get("_sales_group") or ""
        sm = sm_map.get(_sm_key(sg)) if sg else None
        pct = float(sm["commission_pct"]) if sm else 0.0
        sub = float(r.get("SubTotal Invoices") or 0)
        tariff = float(r.get("Total Tariff Charges") or 0)
        base = round(sub + tariff, 2)
        comm = round(base * pct, 2)
        out = {k: v for k, v in r.items() if k != "_sales_group"}
        out["Percent"] = pct
        out["Commission Base"] = base
        out["Commissions"] = comm
        rows.append(out)
    rows.sort(key=lambda r: -float(r.get("Commissions") or 0))
    return {
        "key":     "commissions",
        "name":    "Commissions",
        "columns": COMMISSION_COLS,
        "rows":    rows,
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
    sm_map = _load_salesman_map()
    invoices = [_norm_row(r, sm_map) for r in rows]
    summary = _build_summary_by_customer(invoices)
    commissions = _build_commissions(summary["rows"], sm_map)
    # Strip the private _sales_group helper key from summary rows so it
    # doesn't appear in the on-screen grid or Excel export.
    summary["rows"] = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in summary["rows"]
    ]
    return [
        summary,
        commissions,
        _build_full_data(invoices),
        _build_credits(invoices),
        _build_invoices(invoices),
    ]
