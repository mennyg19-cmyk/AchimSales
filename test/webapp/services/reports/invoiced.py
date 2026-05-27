"""Invoiced report builder.

Mirrors the live ``reports/invoiced/`` aggregator + writer output 1:1 so
the test sandbox produces an Excel file users can A/B against the live
"Monthly Invoiced Report" without spotting differences. Source data is
the ``invoiced_order_charges`` SP (HTTP Reporting API) -- a flat per-
invoice dump with separate charge columns.

Field mapping from SP -> live-style column names::

    InvoiceAccount               -> CustomerAccount
    CustomerName                 -> CustomerName
    InvoiceDate                  -> InvoiceDate           (parsed to datetime)
    Invoice                      -> InvoiceNumber
    SalesOrder                   -> SalesOrderNumber
    Amount                       -> SubTotal Invoices
    SH_TariffCharges             -> Tariff Charges
    SH_FreightCharges            -> Freight Charges
    SH_ProcessingFeesCharges     -> CC Charges
    Amount + all three charges   -> Total Invoice
    SalesGroup                   -> Salesman / SalesGroup (then resolved via app_salesmen)

Salesman # / Name + commission % are looked up from the local
``app_salesmen`` table (keyed by the normalized SalesGroup). When the
SalesGroup is empty (typical for credit notes), we emit ``"Unassigned"``
/ ``"?unassigned"`` to match the live loader's behaviour.

Tabs (in order, matching reports/invoiced/writer.py):
    1. Summary by Customer  -- one row per (customer, salesman); sorted by CustomerAccount
    2. Commissions          -- per-salesman commission math (admin-only)
    3. Full Details         -- one row per InvoiceNumber, reversals netted
    4. Credits              -- rows whose invoice number starts CRD/CM/FC
    5. Invoices             -- all non-credit rows
    6. Audit - Reversals    -- invoice numbers that appear positive AND negative
    7. Totals by Salesman   -- per-salesman aggregate (only when 2+ salesmen)

Credit / invoice split mirrors the live aggregator: the SP doesn't
return a row-type flag, so we infer from the invoice number prefix.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Iterable

log = logging.getLogger(__name__)


# Mirrors webapp/reports/invoiced/aggregator.py's CREDIT_PREFIX_RE.
_CREDIT_PREFIX_RE = re.compile(r"^(CRD|CM|FC)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Column definitions  (column ORDER and HEADERS match reports/invoiced/writer.py)
# ---------------------------------------------------------------------------


# Full Details has a DIFFERENT column order than Credits/Invoices in the
# live report -- the live aggregator's _net_detail_by_invoice groupby
# pulls InvoiceNumber to the front (as the group key) and reorders the
# rest. To diff 1:1 against the live workbook we have to match that.
FULL_DETAILS_COLS: list[dict[str, str]] = [
    {"field": "InvoiceNumber",      "header": "InvoiceNumber",      "type": "text"},
    {"field": "CustomerAccount",    "header": "CustomerAccount",    "type": "text"},
    {"field": "CustomerName",       "header": "CustomerName",       "type": "text"},
    {"field": "InvoiceDate",        "header": "InvoiceDate",        "type": "date"},
    {"field": "SalesOrderNumber",   "header": "SalesOrderNumber",   "type": "text"},
    {"field": "Salesman",           "header": "Salesman",           "type": "text"},
    {"field": "SalesmanNumber",     "header": "SalesmanNumber",     "type": "text"},
    {"field": "SalesmanName",       "header": "SalesmanName",       "type": "text"},
    {"field": "SubTotal Invoices",  "header": "SubTotal Invoices",  "type": "money"},
    {"field": "Tariff Charges",     "header": "Tariff Charges",     "type": "money"},
    {"field": "Freight Charges",    "header": "Freight Charges",    "type": "money"},
    {"field": "CC Charges",         "header": "CC Charges",         "type": "money"},
    {"field": "Total Invoice",      "header": "Total Invoice",      "type": "money"},
]


# Credits / Invoices / Audit-Reversals share this schema -- CustomerAccount
# first, money cols before salesman cols. Matches the live loader's
# canonical column order (reports/invoiced/loader.py keep_cols).
CREDIT_INVOICE_COLS: list[dict[str, str]] = [
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
]


# Summary by Customer matches the live aggregator's group_cols:
# [CustomerAccount, CustomerName, SalesmanNumber, SalesmanName] + counts/sums.
# Note: no separate "Salesman" code column -- live report doesn't show one.
SUMMARY_COLS: list[dict[str, str]] = [
    {"field": "CustomerAccount",       "header": "CustomerAccount",       "type": "text"},
    {"field": "CustomerName",          "header": "CustomerName",          "type": "text"},
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


# Per-salesman totals (only emitted when 2+ salesmen in the data).
# Matches reports/invoiced/writer.py:_maybe_write_totals_by_salesman.
SALESMAN_TOTALS_COLS: list[dict[str, str]] = [
    {"field": "SalesmanNumber",    "header": "SalesmanNumber",    "type": "text"},
    {"field": "SalesmanName",      "header": "SalesmanName",      "type": "text"},
    {"field": "Salesman",          "header": "Salesman",          "type": "text"},
    {"field": "InvoiceCount",      "header": "InvoiceCount",      "type": "int"},
    {"field": "SubTotal Invoices", "header": "SubTotal Invoices", "type": "money"},
    {"field": "Tariff Charges",    "header": "Tariff Charges",    "type": "money"},
    {"field": "Freight Charges",   "header": "Freight Charges",   "type": "money"},
    {"field": "CC Charges",        "header": "CC Charges",        "type": "money"},
    {"field": "Total Invoice",     "header": "Total Invoice",     "type": "money"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Live loader uses these as the "no salesman could be resolved" sentinels.
# Reproduce them verbatim so per-row data matches.
_UNASSIGNED_LABEL  = "Unassigned"
_UNASSIGNED_NUMBER = "?unassigned"


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


# Strings the SP can hand us for invoice dates. We've observed:
#   * ISO 8601:     "2026-04-30T12:00:00" / "2026-04-30 00:00:00"
#   * RFC 1123:     "Thu, 30 Apr 2026 12:00:00 GMT"  (the one that
#                   was truncating to "Thu, 30 Ap" via s[:10] slicing)
#   * Plain date:   "2026-04-30"
# Anything else falls through as a string so the Excel writer at least
# shows the raw value for debugging instead of None.
_RFC1123_FMT = "%a, %d %b %Y %H:%M:%S %Z"


def _parse_date(v: Any) -> date | datetime | str | None:
    """Best-effort parse of the SP's InvoiceDate field into a date.

    Returns a ``date`` when we have day-precision, ``datetime`` when we
    have time-of-day, the original string when nothing parses, or
    ``None`` when the field is empty. The renderer downstream treats
    ``date``/``datetime`` instances as proper Excel dates (gets correct
    column formatting, sortable as time, etc.) -- strings render as
    text, which is the bug the previous ``s[:10]`` slice produced.
    """
    if v is None or v == "" or v == "NULL":
        return None
    if isinstance(v, (date, datetime)):
        return v
    s = str(v).strip()
    # Common SP shape: "YYYY-MM-DD..." (ISO date with optional time).
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, IndexError):
        pass
    # RFC 1123 / HTTP-style: "Thu, 30 Apr 2026 12:00:00 GMT"
    try:
        return datetime.strptime(s, _RFC1123_FMT)
    except ValueError:
        pass
    # Some D365 exports drop the timezone token: "Thu, 30 Apr 2026 12:00:00"
    try:
        return datetime.strptime(s, "%a, %d %b %Y %H:%M:%S")
    except ValueError:
        pass
    log.debug("invoiced: unparseable InvoiceDate %r; keeping as raw string", s)
    return s


def _first(raw: dict, *keys: str) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, "", "NULL"):
            return value
    return None


def _load_salesman_map() -> dict[str, dict]:
    """Cache the local salesman-master keyed by normalized key.

    Returns ``{normalized_key: {number, full_name, display_name,
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
    # The SP returns tariff at the sales-LINE level (``SL_TariffCharges``),
    # NOT at the sales-HEADER level (``SH_TariffCharges`` is always null
    # for the data we've seen). Reading the wrong key was producing
    # Tariff Charges=0 for every row -- a $700k+ miss vs the live
    # Monthly Invoiced Report. Try SL first, fall back to SH for
    # forward-compat in case the SP gets updated to also surface tariff
    # at the header level. Freight + CC are still header-level per
    # the SP schema (``SH_FreightCharges`` / ``SH_ProcessingFeesCharges``).
    tariff_chg   = round(_num(_first(raw, "SL_TariffCharges", "SH_TariffCharges", "TariffCharges", "Tariff Charges")), 2)
    freight_chg  = round(_num(_first(raw, "SH_FreightCharges", "SL_FreightCharges", "FreightCharges", "Freight Charges")), 2)
    cc_chg       = round(_num(_first(raw, "SH_ProcessingFeesCharges", "SL_ProcessingFeesCharges", "ProcessingFeesCharges", "CCCharges", "CC Charges")), 2)
    total        = round(amount + tariff_chg + freight_chg + cc_chg, 2)

    salesgroup = _str(_first(raw, "SalesGroup", "salesgroup", "Salesman"))
    sm = sm_map.get(_sm_key(salesgroup)) if salesgroup else None

    # Salesman display label prefers display_name (friendly) over full_name
    # over the raw SalesGroup code, mirroring the dropdown precedence the
    # rest of the app uses. When no salesman resolves, emit the same
    # "Unassigned" / "?unassigned" strings the live loader uses so the
    # output diffs clean against the live report.
    if sm:
        salesman_label  = sm.get("display_name") or sm.get("full_name") or salesgroup
        salesman_number = sm.get("number") or ""
        salesman_name   = sm.get("full_name") or ""
    elif salesgroup:
        # Raw SalesGroup code with no master row -- still better than
        # "Unassigned" because it lets the user spot data quality gaps.
        salesman_label  = salesgroup
        salesman_number = ""
        salesman_name   = ""
    else:
        salesman_label  = _UNASSIGNED_LABEL
        salesman_number = _UNASSIGNED_NUMBER
        salesman_name   = _UNASSIGNED_LABEL

    return {
        "CustomerAccount":   _str(_first(raw, "InvoiceAccount", "CustomerAccount", "customeraccount", "AccountNum")),
        "CustomerName":      _str(_first(raw, "CustomerName", "customername", "Name")),
        "InvoiceDate":       _parse_date(_first(raw, "InvoiceDate", "Invoice Date", "DocumentDate")),
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
        # SalesGroup retained internally for keying (commissions, audit)
        # but stripped from the on-screen / Excel rows below.
        "_sales_group":      salesgroup,
    }


def _is_credit(invoice_no: str) -> bool:
    return bool(invoice_no and _CREDIT_PREFIX_RE.match(invoice_no.strip()))


def _public_row(row: dict) -> dict:
    """Strip private ``_underscore`` helper keys before surfacing a row."""
    return {k: v for k, v in row.items() if not (isinstance(k, str) and k.startswith("_"))}


# ---------------------------------------------------------------------------
# Tab builders
# ---------------------------------------------------------------------------


_MONEY_FIELDS_PER_INVOICE = (
    "SubTotal Invoices",
    "Tariff Charges",
    "Freight Charges",
    "CC Charges",
    "Total Invoice",
)


def _net_detail_by_invoice(invoices: list[dict]) -> list[dict]:
    """Group invoices by InvoiceNumber and sum money columns.

    Mirrors reports/invoiced/aggregator._net_detail_by_invoice. When the
    same InvoiceNumber appears as both a positive and a negative row
    (a reversal), the two get netted -- matches the live "Full Details"
    sheet exactly. Non-money fields keep the first-seen value.
    """
    buckets: dict[str, dict] = {}
    order: list[str] = []
    for inv in invoices:
        key = inv.get("InvoiceNumber") or ""
        if key not in buckets:
            buckets[key] = dict(inv)  # shallow copy keeps non-money fields
            for f in _MONEY_FIELDS_PER_INVOICE:
                buckets[key][f] = 0.0
            order.append(key)
        b = buckets[key]
        for f in _MONEY_FIELDS_PER_INVOICE:
            b[f] = round(b[f] + _num(inv.get(f)), 2)
    return [buckets[k] for k in order]


_SUMMARY_MONEY_FIELDS = (
    "SubTotal Invoices",
    "Total Tariff Charges",
    "Total Freight Charges",
    "Total CC Charges",
    "Total Invoices",
)


def _build_summary_by_customer(invoices_netted: list[dict]) -> dict:
    """Per-(customer, salesman) aggregation. Mirrors live ``_build_summary``.

    Grouped on ``(CustomerAccount, CustomerName, SalesmanNumber, SalesmanName)``
    exactly as the live aggregator does. InvoiceCount is ``nunique`` --
    since we pass the already-netted detail (one row per invoice number),
    a simple len-per-bucket gives the same result.
    """
    buckets: dict[tuple, dict] = {}
    sg_for_key: dict[tuple, str] = {}
    for inv in invoices_netted:
        key = (
            inv.get("CustomerAccount") or "",
            inv.get("CustomerName") or "",
            inv.get("SalesmanNumber") or "",
            inv.get("SalesmanName") or "",
        )
        if key not in buckets:
            buckets[key] = {
                "CustomerAccount":       key[0],
                "CustomerName":          key[1],
                "SalesmanNumber":        key[2],
                "SalesmanName":          key[3],
                "InvoiceCount":          0,
                "SubTotal Invoices":     0.0,
                "Total Tariff Charges":  0.0,
                "Total Freight Charges": 0.0,
                "Total CC Charges":      0.0,
                "Total Invoices":        0.0,
            }
            sg_for_key[key] = inv.get("_sales_group") or ""
        b = buckets[key]
        b["InvoiceCount"]          += 1
        b["SubTotal Invoices"]     += _num(inv.get("SubTotal Invoices"))
        b["Total Tariff Charges"]  += _num(inv.get("Tariff Charges"))
        b["Total Freight Charges"] += _num(inv.get("Freight Charges"))
        b["Total CC Charges"]      += _num(inv.get("CC Charges"))
        b["Total Invoices"]        += _num(inv.get("Total Invoice"))

    rows: list[dict] = []
    for key, b in buckets.items():
        for f in _SUMMARY_MONEY_FIELDS:
            b[f] = round(b[f], 2)
        # Stash the raw SalesGroup so the commissions builder can look
        # the rate up later. Stripped via _public_row before export.
        b["_sales_group"] = sg_for_key[key]
        rows.append(b)

    # Live aggregator sorts by CustomerAccount ascending -- alphabetical
    # so "00011005" precedes "9300". The previous build sorted by
    # Total Invoices DESC, which mismatched the live report.
    rows.sort(key=lambda r: (r.get("CustomerAccount") or "").lower())
    return {
        "key":     "summary_by_customer",
        "name":    "Summary by Customer",
        "columns": SUMMARY_COLS,
        "rows":    rows,
    }


def _build_commissions(summary_rows: list[dict], sm_map: dict[str, dict]) -> dict:
    """Per-customer commission math, anchored on the summary rows.

    Mirrors ``reports/invoiced/aggregator._build_commissions``:
    ``Commission Base = SubTotal Invoices + Total Tariff Charges`` and
    ``Commissions = Commission Base * commission_pct``. Percent comes
    from ``app_salesmen.commission_pct`` keyed by the normalized
    SalesGroup. Rows with no matching salesman get 0%, so the customer
    still appears with $0 commission.
    """
    rows: list[dict] = []
    for r in summary_rows:
        sg = r.get("_sales_group") or ""
        sm = sm_map.get(_sm_key(sg)) if sg else None
        pct    = float(sm["commission_pct"]) if sm else 0.0
        sub    = _num(r.get("SubTotal Invoices"))
        tariff = _num(r.get("Total Tariff Charges"))
        base   = round(sub + tariff, 2)
        comm   = round(base * pct, 2)
        out = _public_row(r)
        out["Percent"] = pct
        out["Commission Base"] = base
        out["Commissions"] = comm
        rows.append(out)
    # Sort by Commissions desc so the largest payouts appear at the top
    # (matches what the live commissions sheet shows after the monthly
    # breakdown rows -- our simplified output skips the legacy month
    # banner but keeps the per-customer rows in the same order).
    rows.sort(key=lambda r: -_num(r.get("Commissions")))
    return {
        "key":     "commissions",
        "name":    "Commissions",
        "columns": COMMISSION_COLS,
        "rows":    rows,
    }


def _build_full_data(invoices_netted: list[dict]) -> dict:
    """One row per InvoiceNumber. Reversal pairs already netted."""
    rows = [_public_row(r) for r in invoices_netted]
    rows.sort(key=lambda r: ((r.get("CustomerAccount") or "").lower(),
                             r.get("InvoiceNumber") or ""))
    return {
        "key":     "full_data",
        "name":    "Full Details",
        "columns": FULL_DETAILS_COLS,
        "rows":    rows,
    }


def _build_credits(invoices_raw: list[dict]) -> dict:
    """Credit-only rows (InvoiceNumber starts CRD/CM/FC).

    Uses the RAW (pre-netting) invoices because the live "Credits" sheet
    keeps every individual credit-note row, not the netted view.
    """
    rows = [_public_row(r) for r in invoices_raw if _is_credit(r.get("InvoiceNumber") or "")]
    rows.sort(key=lambda r: ((r.get("CustomerAccount") or "").lower(),
                             r.get("InvoiceNumber") or ""))
    return {
        "key":     "credits",
        "name":    "Credits",
        "columns": CREDIT_INVOICE_COLS,
        "rows":    rows,
    }


def _build_invoices(invoices_raw: list[dict]) -> dict:
    """Non-credit rows. Raw (pre-netting), one row per source row."""
    rows = [_public_row(r) for r in invoices_raw if not _is_credit(r.get("InvoiceNumber") or "")]
    rows.sort(key=lambda r: ((r.get("CustomerAccount") or "").lower(),
                             r.get("InvoiceNumber") or ""))
    return {
        "key":     "invoices",
        "name":    "Invoices",
        "columns": CREDIT_INVOICE_COLS,
        "rows":    rows,
    }


def _build_audit_reversals(invoices_raw: list[dict]) -> dict | None:
    """Invoices that appear as BOTH positive and negative in the period.

    Mirrors reports/invoiced/aggregator.build_reversal_audit. Returns
    None when there are no reversal pairs so the sheet doesn't show up
    empty.
    """
    by_inv: dict[str, dict[str, float]] = {}
    for r in invoices_raw:
        key = r.get("InvoiceNumber") or ""
        if not key:
            continue
        total = _num(r.get("Total Invoice"))
        stat = by_inv.setdefault(key, {"min": float("inf"), "max": float("-inf")})
        if total < stat["min"]:
            stat["min"] = total
        if total > stat["max"]:
            stat["max"] = total

    reversal_invs = {
        inv for inv, stat in by_inv.items()
        if stat["min"] < 0 and stat["max"] > 0
    }
    if not reversal_invs:
        return None

    rows = [_public_row(r) for r in invoices_raw if (r.get("InvoiceNumber") or "") in reversal_invs]
    rows.sort(key=lambda r: (r.get("InvoiceNumber") or "",
                             str(r.get("InvoiceDate") or "")))
    return {
        "key":     "audit_reversals",
        "name":    "Audit - Reversals",
        "columns": CREDIT_INVOICE_COLS,
        "rows":    rows,
    }


def _build_totals_by_salesman(invoices_raw: list[dict]) -> dict | None:
    """Per-salesman aggregate. Only emitted when 2+ salesmen.

    Mirrors reports/invoiced/writer._maybe_write_totals_by_salesman.
    InvoiceCount is nunique of InvoiceNumber so reversal pairs don't
    double-count.
    """
    unique_sm = {
        (r.get("Salesman") or "").strip()
        for r in invoices_raw
        if (r.get("Salesman") or "").strip()
    }
    if len(unique_sm) < 2:
        return None

    buckets: dict[tuple, dict] = {}
    seen_invs: dict[tuple, set] = {}
    for r in invoices_raw:
        key = (
            r.get("SalesmanNumber") or "",
            r.get("SalesmanName")   or "",
            r.get("Salesman")       or "",
        )
        if key not in buckets:
            buckets[key] = {
                "SalesmanNumber":    key[0],
                "SalesmanName":      key[1],
                "Salesman":          key[2],
                "InvoiceCount":      0,
                "SubTotal Invoices": 0.0,
                "Tariff Charges":    0.0,
                "Freight Charges":   0.0,
                "CC Charges":        0.0,
                "Total Invoice":     0.0,
            }
            seen_invs[key] = set()
        b = buckets[key]
        inv_no = r.get("InvoiceNumber") or ""
        if inv_no:
            seen_invs[key].add(inv_no)
        b["SubTotal Invoices"] += _num(r.get("SubTotal Invoices"))
        b["Tariff Charges"]    += _num(r.get("Tariff Charges"))
        b["Freight Charges"]   += _num(r.get("Freight Charges"))
        b["CC Charges"]        += _num(r.get("CC Charges"))
        b["Total Invoice"]     += _num(r.get("Total Invoice"))

    rows: list[dict] = []
    for key, b in buckets.items():
        b["InvoiceCount"] = len(seen_invs[key])
        for f in ("SubTotal Invoices", "Tariff Charges", "Freight Charges",
                  "CC Charges", "Total Invoice"):
            b[f] = round(b[f], 2)
        rows.append(b)
    rows.sort(key=lambda r: (r.get("SalesmanNumber") or "",
                             r.get("Salesman")       or ""))
    return {
        "key":     "totals_by_salesman",
        "name":    "Totals by Salesman",
        "columns": SALESMAN_TOTALS_COLS,
        "rows":    rows,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build(rows: Iterable[dict]) -> list[dict]:
    """Turn flat invoiced_order_charges rows into the multi-tab payload.

    Tab order matches reports/invoiced/writer.py:
        Summary by Customer -> Commissions -> Full Details -> Credits ->
        Invoices -> Audit - Reversals (when applicable) -> Totals by
        Salesman (when 2+ salesmen).
    """
    sm_map = _load_salesman_map()
    invoices_raw = [_norm_row(r, sm_map) for r in rows]
    invoices_netted = _net_detail_by_invoice(invoices_raw)

    summary     = _build_summary_by_customer(invoices_netted)
    commissions = _build_commissions(summary["rows"], sm_map)
    summary["rows"] = [_public_row(r) for r in summary["rows"]]

    tabs: list[dict] = [
        summary,
        commissions,
        _build_full_data(invoices_netted),
        _build_credits(invoices_raw),
        _build_invoices(invoices_raw),
    ]
    audit = _build_audit_reversals(invoices_raw)
    if audit is not None:
        tabs.append(audit)
    totals_sm = _build_totals_by_salesman(invoices_raw)
    if totals_sm is not None:
        tabs.append(totals_sm)
    return tabs
