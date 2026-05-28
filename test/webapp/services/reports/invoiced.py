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


def _parse_date(v: Any) -> str | None:
    """Best-effort parse of the SP's InvoiceDate into a day-precision
    ``YYYY-MM-DD`` string.

    Returns the calendar date as a bare ISO string, or ``None`` when the
    field is empty, or the raw string when nothing parses.

    Why a STRING and not a datetime: the SP hands us values like
    ``"Wed, 22 Apr 2026 00:00:00 GMT"`` (midnight UTC). When that became
    a tz-aware/midnight datetime and the browser later built a JS Date
    from it for the Excel export, the UTC midnight got rendered in the
    user's local zone (US Eastern) and landed on the PREVIOUS evening --
    e.g. an Apr-1 invoice showing as ``2026-03-31 21:00``. The live
    Monthly Invoiced Report sidesteps this by stamping noon; we sidestep
    it more directly by carrying only the calendar date. The client's
    date coercion turns a ``YYYY-MM-DD`` string into a LOCAL-midnight
    Date, so the day never crosses a tz boundary, and Excel still shows
    a real mm/dd/yyyy date (not text).
    """
    if v is None or v == "" or v == "NULL":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    # Common SP shape: "YYYY-MM-DD..." (ISO date with optional time/tz).
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            try:
                return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
            except ValueError:
                return datetime.strptime(s[:10], "%Y-%m-%d").date().isoformat()
    except (ValueError, IndexError):
        pass
    # RFC 1123 / HTTP-style: "Thu, 30 Apr 2026 12:00:00 GMT"
    try:
        return datetime.strptime(s, _RFC1123_FMT).date().isoformat()
    except ValueError:
        pass
    # Some D365 exports drop the timezone token: "Thu, 30 Apr 2026 12:00:00"
    try:
        return datetime.strptime(s, "%a, %d %b %Y %H:%M:%S").date().isoformat()
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


_MONTH_LABELS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _row_month(row: dict) -> int | None:
    """Return 1..12 month index for a row's InvoiceDate, or None."""
    d = row.get("InvoiceDate")
    if isinstance(d, (date, datetime)):
        return d.month
    if isinstance(d, str) and len(d) >= 7 and d[4] == "-":
        try:
            return int(d[5:7])
        except ValueError:
            return None
    return None


def _build_commissions_monthly(
    ytd_rows: list[dict],
    sm_map: dict[str, dict],
    *,
    year: int,
    end_month: int,
) -> dict:
    """Per-salesman YTD commissions, broken down by calendar month.

    Mirrors the live ``reports/invoiced/writer._write_commissions_sheet``
    layout: one block per commissioned salesman, with columns
    ``Jan ... <end_month>`` + ``YTD Total``. The block rows are:

        SubTotal Invoices:
        Total Tariff Charges:
        Total Freight Charges:
        Total CC Charges:
        Total Invoices:           (subtotal + all charges)
        Total Credits:            (negative; sum of CRD/CM/FC rows)
        Net Commission Amount:    (total invoices - freight - cc + credits)
        Commission @ <pct>:       (net * commission_pct)
        Total Payable: <name>     (YTD column only)

    ``ytd_rows`` are the same shape as the per-period rows but cover
    Jan 1..end-of-period (the runner re-fetches the wider window so
    the commissions tab gets prior-month context the live report
    has). ``end_month`` is the last month to show (1..12). Anything
    after ``end_month`` is omitted from the columns even if data
    leaks in via a late-posted invoice.
    """
    if end_month < 1 or end_month > 12:
        end_month = 12

    # Group rows by (salesman_number, month). Bucket separately so the
    # "Credits" line gets the credit-prefix rows even when InvoiceNumber
    # has been netted out of the main detail elsewhere.
    by_sm: dict[str, dict] = {}
    for r in ytd_rows:
        sg = r.get("_sales_group") or ""
        if not sg:
            continue
        sm = sm_map.get(_sm_key(sg))
        if not sm or float(sm.get("commission_pct") or 0) <= 0:
            continue
        number = (sm.get("number") or "").strip()
        if not number:
            continue
        bucket = by_sm.setdefault(number, {
            "salesman_number": number,
            "salesman_name":   sm.get("full_name") or sm.get("display_name") or sg,
            "commission_pct":  float(sm.get("commission_pct") or 0.0),
            "monthly": [{
                "subtotal_invoices":     0.0,
                "tariff_charges":        0.0,
                "freight_charges":       0.0,
                "cc_charges":            0.0,
                "credits":               0.0,
            } for _ in range(end_month)],
        })
        m = _row_month(r)
        if m is None or m < 1 or m > end_month:
            continue
        slot = bucket["monthly"][m - 1]
        inv_no = r.get("InvoiceNumber") or ""
        if _is_credit(inv_no):
            # Live's "Total Credits" line is the sum of the Total
            # Invoice column on credit-prefix rows. The "SubTotal /
            # Tariff / Freight / CC" lines deliberately EXCLUDE credit
            # rows so the credit doesn't double-count against the
            # gross invoice charges. Matches the live writer's split
            # between detail_df (excludes credits via Txt classify)
            # and credits_df (sum-by-month).
            slot["credits"] += _num(r.get("Total Invoice"))
        else:
            slot["subtotal_invoices"] += _num(r.get("SubTotal Invoices"))
            slot["tariff_charges"]    += _num(r.get("Tariff Charges"))
            slot["freight_charges"]   += _num(r.get("Freight Charges"))
            slot["cc_charges"]        += _num(r.get("CC Charges"))

    salesmen: list[dict] = []
    for number in sorted(by_sm.keys(), key=lambda n: int(n) if n.isdigit() else n):
        bucket = by_sm[number]
        pct = bucket["commission_pct"]
        ytd = {
            "subtotal_invoices":     0.0,
            "tariff_charges":        0.0,
            "freight_charges":       0.0,
            "cc_charges":            0.0,
            "total_invoices":        0.0,
            "credits":               0.0,
            "net_commission":        0.0,
            "commission":            0.0,
        }
        rich_monthly: list[dict] = []
        for idx, slot in enumerate(bucket["monthly"]):
            sub  = round(slot["subtotal_invoices"], 2)
            tar  = round(slot["tariff_charges"],    2)
            fre  = round(slot["freight_charges"],   2)
            cc   = round(slot["cc_charges"],        2)
            crd  = round(slot["credits"],           2)
            ti   = round(sub + tar + fre + cc,      2)
            net  = round(ti + crd - fre - cc,       2)
            comm = round(net * pct,                 2)
            rich_monthly.append({
                "month":             idx + 1,
                "month_label":       _MONTH_LABELS[idx],
                "subtotal_invoices": sub,
                "tariff_charges":    tar,
                "freight_charges":   fre,
                "cc_charges":        cc,
                "total_invoices":    ti,
                "credits":           crd,
                "net_commission":    net,
                "commission":        comm,
            })
            ytd["subtotal_invoices"] += sub
            ytd["tariff_charges"]    += tar
            ytd["freight_charges"]   += fre
            ytd["cc_charges"]        += cc
            ytd["total_invoices"]    += ti
            ytd["credits"]           += crd
            ytd["net_commission"]    += net
            ytd["commission"]        += comm
        for k in ytd:
            ytd[k] = round(ytd[k], 2)
        ytd["total_payable"] = ytd["commission"]
        salesmen.append({
            "salesman_number": number,
            "salesman_name":   bucket["salesman_name"],
            "commission_pct":  pct,
            "monthly":         rich_monthly,
            "ytd":             ytd,
        })

    grand = {
        "subtotal_invoices": round(sum(s["ytd"]["subtotal_invoices"] for s in salesmen), 2),
        "tariff_charges":    round(sum(s["ytd"]["tariff_charges"]    for s in salesmen), 2),
        "freight_charges":   round(sum(s["ytd"]["freight_charges"]   for s in salesmen), 2),
        "cc_charges":        round(sum(s["ytd"]["cc_charges"]        for s in salesmen), 2),
        "total_invoices":    round(sum(s["ytd"]["total_invoices"]    for s in salesmen), 2),
        "credits":           round(sum(s["ytd"]["credits"]           for s in salesmen), 2),
        "net_commission":    round(sum(s["ytd"]["net_commission"]    for s in salesmen), 2),
        "commission":        round(sum(s["ytd"]["commission"]        for s in salesmen), 2),
        "total_payable":     round(sum(s["ytd"]["total_payable"]     for s in salesmen), 2),
    }
    return {
        "key":      "commissions",
        "name":     "Commissions",
        "layout":   "commission_cards",
        "year":     year,
        "end_month": end_month,
        "month_labels": list(_MONTH_LABELS[:end_month]),
        "salesmen": salesmen,
        "grand":    grand,
        # Keep ``columns`` / ``rows`` empty so any client that doesn't
        # know about ``layout`` falls back gracefully (no table render,
        # just an empty pane) instead of crashing on missing fields.
        "columns":  [],
        "rows":     [],
    }


def _build_commissions_simple(summary_rows: list[dict], sm_map: dict[str, dict]) -> dict:
    """Flat commissions fallback used when no YTD data is available.

    Older sandboxes (and any caller that doesn't thread ``ytd_rows``
    through ``build``) still get the one-row-per-customer Commissions
    tab. Kept around so report_runner can opt in to the richer
    monthly view incrementally.
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


def build(
    rows: Iterable[dict],
    *,
    ytd_rows: Iterable[dict] | None = None,
    year: int | None = None,
    end_month: int | None = None,
) -> list[dict]:
    """Turn flat invoiced_order_charges rows into the multi-tab payload.

    All tabs EXCEPT Commissions are built from ``rows`` (the selected
    period only). The Commissions tab is built from ``ytd_rows`` --
    the wider Jan-1-through-end-of-period window the live commissions
    summary uses. When ``ytd_rows`` is None we fall back to the
    legacy flat commissions table built from the selected period
    only, so callers that haven't been updated still produce a tab.

    Tab order matches reports/invoiced/writer.py:
        Summary by Customer -> Commissions -> Full Details -> Credits ->
        Invoices -> Audit - Reversals (when applicable) -> Totals by
        Salesman (when 2+ salesmen).
    """
    sm_map = _load_salesman_map()
    invoices_raw = [_norm_row(r, sm_map) for r in rows]
    invoices_netted = _net_detail_by_invoice(invoices_raw)

    summary = _build_summary_by_customer(invoices_netted)

    if ytd_rows is not None and year is not None and end_month is not None:
        ytd_norm = [_norm_row(r, sm_map) for r in ytd_rows]
        commissions = _build_commissions_monthly(
            ytd_norm, sm_map, year=year, end_month=end_month,
        )
    else:
        commissions = _build_commissions_simple(summary["rows"], sm_map)

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
