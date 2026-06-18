"""Invoiced report builder (pure).

Facts -> the multi-tab payload. Column order/headers match the LIVE Monthly
Invoiced Report export. SQL returns invoice-level rows; Flask only shapes tabs,
splits credits, and runs commission math (needs Azure commission %).

Tabs, in LIVE order:
    1. Summary by Customer  - GROUP BY (customer, salesman) from period rows
    2. Commissions          - per-salesman YTD pivot (admin-only; cards layout)
    3. Full Details         - one row per invoice (net only if SQL sends dupes)
    4. Credits              - rows flagged as credit
    5. Invoices             - non-credit rows
    6. Audit - Reversals    - only when same invoice has + and - totals
    7. Totals by Salesman   - per-salesman net aggregate, credits subtracted
                              (only when 2+ salesmen)
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

from report_engine.facts import InvoiceChargeFact, SalesmanFact
from report_engine.lib import num, salesman_key

_UNASSIGNED_LABEL = "Unassigned"

_MONTH_LABELS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# --- column definitions (order + headers match the LIVE export) -------------

FULL_DETAILS_COLS = [
    {"field": "InvoiceNumber", "header": "InvoiceNumber", "type": "text"},
    {"field": "CustomerAccount", "header": "CustomerAccount", "type": "text"},
    {"field": "CustomerName", "header": "CustomerName", "type": "text"},
    {"field": "InvoiceDate", "header": "InvoiceDate", "type": "date"},
    {"field": "SalesOrderNumber", "header": "SalesOrderNumber", "type": "text"},
    {"field": "Salesman", "header": "Salesman", "type": "text"},
    {"field": "SalesmanName", "header": "SalesmanName", "type": "text"},
    {"field": "SubTotal Invoices", "header": "SubTotal Invoices", "type": "money"},
    {"field": "Tariff Charges", "header": "Tariff Charges", "type": "money"},
    {"field": "Freight Charges", "header": "Freight Charges", "type": "money"},
    {"field": "CC Charges", "header": "CC Charges", "type": "money"},
    {"field": "Misc Charges", "header": "Misc Charges", "type": "money"},
    {"field": "Total Invoice", "header": "Total Invoice", "type": "money"},
]

CREDIT_INVOICE_COLS = [
    {"field": "CustomerAccount", "header": "CustomerAccount", "type": "text"},
    {"field": "CustomerName", "header": "CustomerName", "type": "text"},
    {"field": "InvoiceDate", "header": "InvoiceDate", "type": "date"},
    {"field": "InvoiceNumber", "header": "InvoiceNumber", "type": "text"},
    {"field": "SalesOrderNumber", "header": "SalesOrderNumber", "type": "text"},
    {"field": "SubTotal Invoices", "header": "SubTotal Invoices", "type": "money"},
    {"field": "Tariff Charges", "header": "Tariff Charges", "type": "money"},
    {"field": "Freight Charges", "header": "Freight Charges", "type": "money"},
    {"field": "CC Charges", "header": "CC Charges", "type": "money"},
    {"field": "Misc Charges", "header": "Misc Charges", "type": "money"},
    {"field": "Total Invoice", "header": "Total Invoice", "type": "money"},
    {"field": "Salesman", "header": "Salesman", "type": "text"},
    {"field": "SalesmanName", "header": "SalesmanName", "type": "text"},
]

SUMMARY_COLS = [
    {"field": "CustomerAccount", "header": "CustomerAccount", "type": "text"},
    {"field": "CustomerName", "header": "CustomerName", "type": "text"},
    {"field": "Salesman", "header": "Salesman", "type": "text"},
    {"field": "SalesmanName", "header": "SalesmanName", "type": "text"},
    {"field": "InvoiceCount", "header": "InvoiceCount", "type": "int"},
    {"field": "SubTotal Invoices", "header": "SubTotal Invoices", "type": "money"},
    {"field": "Total Tariff Charges", "header": "Total Tariff Charges", "type": "money"},
    {"field": "Total Freight Charges", "header": "Total Freight Charges", "type": "money"},
    {"field": "Total CC Charges", "header": "Total CC Charges", "type": "money"},
    {"field": "Total Misc Charges", "header": "Total Misc Charges", "type": "money"},
    {"field": "Total Invoices", "header": "Total Invoices", "type": "money"},
]

COMMISSION_COLS = SUMMARY_COLS + [
    {"field": "Percent", "header": "Percent", "type": "percent"},
    {"field": "Commission Base", "header": "Commission Base", "type": "money"},
    {"field": "Commissions", "header": "Commissions", "type": "money"},
]

SALESMAN_TOTALS_COLS = [
    {"field": "Salesman", "header": "Salesman", "type": "text"},
    {"field": "SalesmanName", "header": "SalesmanName", "type": "text"},
    {"field": "InvoiceCount", "header": "InvoiceCount", "type": "int"},
    {"field": "SubTotal Invoices", "header": "SubTotal Invoices", "type": "money"},
    {"field": "Tariff Charges", "header": "Tariff Charges", "type": "money"},
    {"field": "Freight Charges", "header": "Freight Charges", "type": "money"},
    {"field": "CC Charges", "header": "CC Charges", "type": "money"},
    {"field": "Misc Charges", "header": "Misc Charges", "type": "money"},
    {"field": "Total Invoice", "header": "Total Invoice", "type": "money"},
]

_INVOICE_MONEY = ("SubTotal Invoices", "Tariff Charges", "Freight Charges",
                  "CC Charges", "Misc Charges", "Total Invoice")


# --- row enrichment (SQL labels + Azure commission lookup) ------------------

def _salesman_columns(fact: InvoiceChargeFact,
                      salesmen: Mapping[str, SalesmanFact]) -> tuple[str, str]:
    """Salesman code + name from SQL; Azure fills name gaps only."""
    sm = salesmen.get(salesman_key(fact.sales_group)) if fact.sales_group else None
    if not fact.sales_group:
        return (_UNASSIGNED_LABEL, _UNASSIGNED_LABEL)
    name = fact.salesman_name or (sm.full_name if sm else "")
    return (fact.sales_group, name)


def _enriched(fact: InvoiceChargeFact, salesmen: Mapping[str, SalesmanFact]) -> dict:
    """One fact -> a row with LIVE column names (+ private keys for grouping)."""
    label, name = _salesman_columns(fact, salesmen)
    return {
        "CustomerAccount": fact.customer_account,
        "CustomerName": fact.customer_name,
        "InvoiceDate": fact.invoice_date,
        "InvoiceNumber": fact.invoice_number,
        "SalesOrderNumber": fact.sales_order_number,
        "SubTotal Invoices": fact.subtotal,
        "Tariff Charges": fact.tariff,
        "Freight Charges": fact.freight,
        "CC Charges": fact.cc,
        "Misc Charges": fact.misc,
        "Total Invoice": fact.total,
        "Salesman": label,
        "SalesmanName": name,
        "_sales_group": fact.sales_group,
        "_is_credit": fact.is_credit,
        "_commission_pct": fact.commission_pct,
    }


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if not k.startswith("_")}


def _month_of(row: dict) -> int | None:
    d = row.get("InvoiceDate")
    if isinstance(d, str) and len(d) >= 7 and d[4] == "-":
        try:
            return int(d[5:7])
        except ValueError:
            return None
    return None


def _year_of(row: dict) -> int | None:
    d = row.get("InvoiceDate")
    if isinstance(d, str) and len(d) >= 4:
        try:
            return int(d[:4])
        except ValueError:
            return None
    return None


def _row_rates_by_salesman(rows: Iterable[dict]) -> dict[str, float]:
    """Highest commission rate the SP sent per salesman key (rows should agree;
    max ignores blank/zero rows like credits). Empty when the SP sends none."""
    rates: dict[str, float] = {}
    for r in rows:
        sg = r.get("_sales_group") or ""
        if not sg:
            continue
        rate = num(r.get("_commission_pct"))
        key = salesman_key(sg)
        if rate > rates.get(key, 0.0):
            rates[key] = rate
    return rates


def _commission_rate(sales_group: str, salesmen: Mapping[str, SalesmanFact],
                     row_rates: Mapping[str, float]) -> float:
    """The rate to use for one salesman: the SP's per-row rate when present,
    otherwise the salesman master. Both are fractions (0.06 = 6%)."""
    key = salesman_key(sales_group)
    row_rate = row_rates.get(key, 0.0)
    if row_rate > 0:
        return row_rate
    sm = salesmen.get(key)
    return sm.commission_pct if sm else 0.0


# --- per-tab builders -------------------------------------------------------

def _has_duplicate_invoices(rows: Sequence[dict]) -> bool:
    seen: set[str] = set()
    for r in rows:
        inv = r.get("InvoiceNumber") or ""
        if not inv:
            continue
        if inv in seen:
            return True
        seen.add(inv)
    return False


def _net_by_invoice(rows: Sequence[dict]) -> list[dict]:
    """Group rows by InvoiceNumber, summing money. Only needed when SQL still
    returns multiple rows per invoice (reversal pairs before server-side net)."""
    buckets: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        key = r.get("InvoiceNumber") or ""
        b = buckets.get(key)
        if b is None:
            b = dict(r)
            for f in _INVOICE_MONEY:
                b[f] = 0.0
            buckets[key] = b
            order.append(key)
        for f in _INVOICE_MONEY:
            b[f] = round(b[f] + num(r.get(f)), 2)
    return [buckets[k] for k in order]


def _summary_by_customer(raw: Sequence[dict]) -> dict:
    """Per-(customer, salesman) aggregation from the full detail (credits incl.).

    Matches LIVE `_build_summary(df)`: group by
    (CustomerAccount, CustomerName, Salesman, SalesmanName); InvoiceCount
    is nunique(InvoiceNumber); money columns are summed over all rows.
    """
    buckets: dict[tuple, dict] = {}
    invoices_seen: dict[tuple, set] = {}
    for r in raw:
        key = (r.get("CustomerAccount") or "", r.get("CustomerName") or "",
               r.get("Salesman") or "", r.get("SalesmanName") or "")
        b = buckets.get(key)
        if b is None:
            b = {
                "CustomerAccount": key[0], "CustomerName": key[1],
                "Salesman": key[2], "SalesmanName": key[3],
                "InvoiceCount": 0, "SubTotal Invoices": 0.0,
                "Total Tariff Charges": 0.0, "Total Freight Charges": 0.0,
                "Total CC Charges": 0.0, "Total Misc Charges": 0.0,
                "Total Invoices": 0.0,
                "_sales_group": r.get("_sales_group") or "",
            }
            buckets[key] = b
            invoices_seen[key] = set()
        if r.get("InvoiceNumber"):
            invoices_seen[key].add(r["InvoiceNumber"])
        b["SubTotal Invoices"] += num(r.get("SubTotal Invoices"))
        b["Total Tariff Charges"] += num(r.get("Tariff Charges"))
        b["Total Freight Charges"] += num(r.get("Freight Charges"))
        b["Total CC Charges"] += num(r.get("CC Charges"))
        b["Total Misc Charges"] += num(r.get("Misc Charges"))
        b["Total Invoices"] += num(r.get("Total Invoice"))
    rows = list(buckets.values())
    for key, b in buckets.items():
        b["InvoiceCount"] = len(invoices_seen[key])
        for f in ("SubTotal Invoices", "Total Tariff Charges", "Total Freight Charges",
                  "Total CC Charges", "Total Misc Charges", "Total Invoices"):
            b[f] = round(b[f], 2)
    rows.sort(key=lambda r: (r.get("CustomerAccount") or "").lower())
    return {"key": "summary_by_customer", "name": "Summary by Customer",
            "columns": SUMMARY_COLS, "rows": rows}


def _commissions_monthly(ytd_rows: Sequence[dict], salesmen: Mapping[str, SalesmanFact],
                         *, year: int, end_month: int) -> dict:
    if not 1 <= end_month <= 12:
        end_month = 12

    row_rates = _row_rates_by_salesman(ytd_rows)
    by_sm: dict[str, dict] = {}
    for r in ytd_rows:
        sg = r.get("_sales_group") or ""
        if not sg:
            continue
        rate = _commission_rate(sg, salesmen, row_rates)
        if rate <= 0:
            continue
        # Guard against a caller passing a wider window than Jan 1..period end:
        # only count rows in the report year (LIVE fetches exactly that window).
        if _year_of(r) != year:
            continue
        m = _month_of(r)
        if m is None or not 1 <= m <= end_month:
            continue
        bucket_key = salesman_key(sg)
        sm = salesmen.get(bucket_key)
        bucket = by_sm.setdefault(bucket_key, {
            "label": r.get("Salesman") or sg,
            "name": r.get("SalesmanName") or (sm.full_name or sm.display_name if sm else "") or sg,
            "pct": rate,
            "monthly": [dict(subtotal=0.0, tariff=0.0, freight=0.0, cc=0.0, misc=0.0,
                             credits=0.0)
                        for _ in range(end_month)],
        })
        slot = bucket["monthly"][m - 1]
        if r.get("_is_credit"):
            slot["credits"] += num(r.get("Total Invoice"))
        else:
            slot["subtotal"] += num(r.get("SubTotal Invoices"))
            slot["tariff"] += num(r.get("Tariff Charges"))
            slot["freight"] += num(r.get("Freight Charges"))
            slot["cc"] += num(r.get("CC Charges"))
            slot["misc"] += num(r.get("Misc Charges"))

    salesmen_out: list[dict] = []
    for bucket_key in sorted(by_sm, key=lambda k: by_sm[k]["name"].lower()):
        bucket = by_sm[bucket_key]
        pct = bucket["pct"]
        ytd = dict(subtotal_invoices=0.0, tariff_charges=0.0, freight_charges=0.0,
                   cc_charges=0.0, misc_charges=0.0, total_invoices=0.0, credits=0.0,
                   net_commission=0.0, commission=0.0)
        monthly_out: list[dict] = []
        for idx, slot in enumerate(bucket["monthly"]):
            sub = round(slot["subtotal"], 2)
            tar = round(slot["tariff"], 2)
            fre = round(slot["freight"], 2)
            cc = round(slot["cc"], 2)
            misc = round(slot["misc"], 2)
            crd = round(slot["credits"], 2)
            ti = round(sub + tar + fre + cc + misc, 2)
            net = round(ti + crd - fre - cc, 2)
            comm = net * pct  # kept UNrounded; YTD sums these (matches LIVE)
            monthly_out.append({
                "month": idx + 1, "month_label": _MONTH_LABELS[idx],
                "subtotal_invoices": sub, "tariff_charges": tar,
                "freight_charges": fre, "cc_charges": cc, "misc_charges": misc,
                "total_invoices": ti,
                "credits": crd, "net_commission": net, "commission": round(comm, 2),
            })
            ytd["subtotal_invoices"] += sub
            ytd["tariff_charges"] += tar
            ytd["freight_charges"] += fre
            ytd["cc_charges"] += cc
            ytd["misc_charges"] += misc
            ytd["total_invoices"] += ti
            ytd["credits"] += crd
            ytd["net_commission"] += net
            ytd["commission"] += comm
        for k in ytd:
            ytd[k] = round(ytd[k], 2)
        ytd["total_payable"] = ytd["commission"]
        salesmen_out.append({
            "salesman": bucket["label"], "salesman_name": bucket["name"],
            "commission_pct": pct, "monthly": monthly_out, "ytd": ytd,
        })

    def _g(field: str) -> float:
        return round(sum(s["ytd"][field] for s in salesmen_out), 2)

    grand = {f: _g(f) for f in ("subtotal_invoices", "tariff_charges", "freight_charges",
                                "cc_charges", "misc_charges", "total_invoices", "credits",
                                "net_commission", "commission", "total_payable")}
    labels = list(_MONTH_LABELS[:end_month])
    columns, rows = _commissions_flat_table(salesmen_out, grand, labels)
    return {
        "key": "commissions", "name": "Commissions", "layout": "commission_cards",
        "year": year, "end_month": end_month,
        "month_labels": labels,
        # Rich per-salesman card data kept for a future card UI; columns/rows give
        # the generic on-screen table + Excel export a real (non-blank) view now.
        "salesmen": salesmen_out, "grand": grand,
        "columns": columns, "rows": rows,
    }


def _commissions_flat_table(salesmen_out: list[dict], grand: dict,
                            labels: list[str]) -> tuple[list[dict], list[dict]]:
    """Flatten the monthly commission cards into one row per salesman (+ a TOTAL
    row): Salesman, %, a commission column per month, and YTD commission."""
    columns = [
        {"field": "Salesman", "header": "Salesman", "type": "text"},
        {"field": "Commission %", "header": "Commission %", "type": "percent"},
    ]
    columns += [{"field": f"Comm {lbl}", "header": lbl, "type": "money"} for lbl in labels]
    columns.append({"field": "YTD Commission", "header": "YTD Commission", "type": "money"})

    rows: list[dict] = []
    for s in salesmen_out:
        name = s["salesman_name"] or s.get("salesman") or ""
        row = {"Salesman": name, "Commission %": s["commission_pct"]}
        by_label = {m["month_label"]: m["commission"] for m in s["monthly"]}
        for lbl in labels:
            row[f"Comm {lbl}"] = by_label.get(lbl, 0.0)
        row["YTD Commission"] = s["ytd"]["commission"]
        rows.append(row)

    total = {"Salesman": "TOTAL", "Commission %": ""}
    for lbl in labels:
        total[f"Comm {lbl}"] = round(sum(r.get(f"Comm {lbl}", 0.0) for r in rows), 2)
    total["YTD Commission"] = grand.get("commission", 0.0)
    rows.append(total)
    return columns, rows


def _commissions_simple(summary_rows: Sequence[dict],
                        salesmen: Mapping[str, SalesmanFact],
                        row_rates: Mapping[str, float]) -> dict:
    rows: list[dict] = []
    for r in summary_rows:
        sg = r.get("_sales_group") or ""
        pct = _commission_rate(sg, salesmen, row_rates) if sg else 0.0
        base = round(num(r.get("SubTotal Invoices")) + num(r.get("Total Tariff Charges")), 2)
        out = _public(r)
        out["Percent"] = pct
        out["Commission Base"] = base
        out["Commissions"] = round(base * pct, 2)
        rows.append(out)
    rows.sort(key=lambda r: -num(r.get("Commissions")))
    return {"key": "commissions", "name": "Commissions",
            "columns": COMMISSION_COLS, "rows": rows}


def _full_details(netted: Sequence[dict]) -> dict:
    rows = [_public(r) for r in netted]
    rows.sort(key=lambda r: ((r.get("CustomerAccount") or "").lower(),
                             r.get("InvoiceNumber") or ""))
    return {"key": "full_data", "name": "Full Details",
            "columns": FULL_DETAILS_COLS, "rows": rows}


def _credits(raw: Sequence[dict]) -> dict:
    rows = [_public(r) for r in raw if r.get("_is_credit")]
    rows.sort(key=lambda r: ((r.get("CustomerAccount") or "").lower(),
                             r.get("InvoiceNumber") or ""))
    return {"key": "credits", "name": "Credits",
            "columns": CREDIT_INVOICE_COLS, "rows": rows}


def _invoices(raw: Sequence[dict]) -> dict:
    rows = [_public(r) for r in raw if not r.get("_is_credit")]
    rows.sort(key=lambda r: ((r.get("CustomerAccount") or "").lower(),
                             r.get("InvoiceNumber") or ""))
    return {"key": "invoices", "name": "Invoices",
            "columns": CREDIT_INVOICE_COLS, "rows": rows}


def _audit_reversals(raw: Sequence[dict]) -> dict | None:
    extents: dict[str, list[float]] = {}
    for r in raw:
        key = r.get("InvoiceNumber") or ""
        if not key:
            continue
        total = num(r.get("Total Invoice"))
        ext = extents.setdefault(key, [float("inf"), float("-inf")])
        ext[0] = min(ext[0], total)
        ext[1] = max(ext[1], total)
    flagged = {k for k, (lo, hi) in extents.items() if lo < 0 < hi}
    if not flagged:
        return None
    rows = [_public(r) for r in raw if (r.get("InvoiceNumber") or "") in flagged]
    rows.sort(key=lambda r: (r.get("InvoiceNumber") or "", str(r.get("InvoiceDate") or "")))
    return {"key": "audit_reversals", "name": "Audit - Reversals",
            "columns": CREDIT_INVOICE_COLS, "rows": rows}


def _totals_by_salesman(rows: Sequence[dict]) -> dict | None:
    """Per-salesman NET aggregate. Credits carry negative amounts and are
    summed in alongside invoices, so each salesman's totals are net of credits.
    Only emitted for 2+ salesmen; InvoiceCount is nunique(InvoiceNumber)."""
    distinct = {(r.get("Salesman") or "").strip() for r in rows if (r.get("Salesman") or "").strip()}
    if len(distinct) < 2:
        return None
    buckets: dict[tuple, dict] = {}
    invoices_seen: dict[tuple, set] = {}
    for r in rows:
        key = (r.get("Salesman") or "", r.get("SalesmanName") or "")
        b = buckets.get(key)
        if b is None:
            b = {"Salesman": key[0], "SalesmanName": key[1],
                 "InvoiceCount": 0, "SubTotal Invoices": 0.0, "Tariff Charges": 0.0,
                 "Freight Charges": 0.0, "CC Charges": 0.0, "Misc Charges": 0.0,
                 "Total Invoice": 0.0}
            buckets[key] = b
            invoices_seen[key] = set()
        if r.get("InvoiceNumber"):
            invoices_seen[key].add(r["InvoiceNumber"])
        b["SubTotal Invoices"] += num(r.get("SubTotal Invoices"))
        b["Tariff Charges"] += num(r.get("Tariff Charges"))
        b["Freight Charges"] += num(r.get("Freight Charges"))
        b["CC Charges"] += num(r.get("CC Charges"))
        b["Misc Charges"] += num(r.get("Misc Charges"))
        b["Total Invoice"] += num(r.get("Total Invoice"))
    rows: list[dict] = []
    for key, b in buckets.items():
        b["InvoiceCount"] = len(invoices_seen[key])
        for f in ("SubTotal Invoices", "Tariff Charges", "Freight Charges", "Misc Charges",
                  "CC Charges", "Total Invoice"):
            b[f] = round(b[f], 2)
        rows.append(b)
    rows.sort(key=lambda r: ((r.get("Salesman") or "").lower(),
                             r.get("SalesmanName") or ""))
    return {"key": "totals_by_salesman", "name": "Totals by Salesman",
            "columns": SALESMAN_TOTALS_COLS, "rows": rows}


# --- public entry point -----------------------------------------------------

def build(facts: Iterable[InvoiceChargeFact], *,
          salesmen: Mapping[str, SalesmanFact],
          ytd_facts: Iterable[InvoiceChargeFact] | None = None,
          year: int | None = None,
          end_month: int | None = None) -> list[dict]:
    """Build the invoiced multi-tab payload.

    All tabs except Commissions come from `facts` (selected period). The
    Commissions pivot uses `ytd_facts` (Jan 1..period end) when provided; else
    it falls back to the flat per-customer commissions table.
    """
    raw = [_enriched(f, salesmen) for f in facts]
    netted = _net_by_invoice(raw) if _has_duplicate_invoices(raw) else list(raw)
    summary = _summary_by_customer(raw)

    if ytd_facts is not None and year is not None and end_month is not None:
        ytd_rows = [_enriched(f, salesmen) for f in ytd_facts]
        commissions = _commissions_monthly(ytd_rows, salesmen, year=year, end_month=end_month)
    else:
        commissions = _commissions_simple(summary["rows"], salesmen, _row_rates_by_salesman(raw))

    summary["rows"] = [_public(r) for r in summary["rows"]]

    tabs = [summary, commissions, _full_details(netted), _credits(raw), _invoices(raw)]
    if (audit := _audit_reversals(raw)) is not None:
        tabs.append(audit)
    if (totals := _totals_by_salesman(raw)) is not None:
        tabs.append(totals)
    return tabs
