"""Bespoke per-tab math that the generic group/total engine can't express."""

# === What's in this file ===
# Most tabs are plain group-and-total, but the Commissions tab is a month-by-
# month pivot per salesman with its own net formula. This holds those special
# builders, keyed by name so a tab's config can point at one.
#
# THE COMMISSION MATH (owner-confirmed, mirrors LIVE; numbers are PROVISIONAL
# until owner sign-off):
#   The SP sends only the salesman's RATE (column `commission`, a fraction).
#   Per salesman, per month:
#     net = TotalInvoice + Credits - Freight - CC      (credits are negative)
#     commission = net * rate
#   YTD commission = sum of the months (kept unrounded, rounded only to display).
#
# commission_monthly_pivot() -- one row per salesman: rate, a commission per
#   month, and the YTD commission, plus a TOTAL row
# TRANSFORMS -- name -> transform function, passed to the engine

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .lib import num, text

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _year_of(row: dict) -> int | None:
    d = row.get("InvoiceDate")
    if isinstance(d, str) and len(d) >= 4 and d[:4].isdigit():
        return int(d[:4])
    return None


def _month_of(row: dict) -> int | None:
    d = row.get("InvoiceDate")
    if isinstance(d, str) and len(d) >= 7 and d[4] == "-" and d[5:7].isdigit():
        return int(d[5:7])
    return None


def commission_monthly_pivot(rows: Sequence[dict], params: Mapping[str, Any]) -> dict:
    rates: dict[str, float] = {}
    names: dict[str, str] = {}
    for r in rows:
        salesman = text(r.get("Salesman"))
        if not salesman:
            continue
        rate = num(r.get("commission"))
        if rate > rates.get(salesman, 0.0):
            rates[salesman] = rate
        if not names.get(salesman):
            names[salesman] = text(r.get("SalesmanName")) or salesman

    years = [y for y in (_year_of(r) for r in rows) if y]
    year = max(years) if years else None
    end_month = 12
    if year is not None:
        months = [m for m in (_month_of(r) for r in rows if _year_of(r) == year) if m]
        end_month = max(months) if months else 12

    earners = {s: rate for s, rate in rates.items() if rate > 0}
    buckets = {
        s: [dict(subtotal=0.0, tariff=0.0, freight=0.0, cc=0.0, misc=0.0, credits=0.0)
            for _ in range(end_month)]
        for s in earners
    }
    for r in rows:
        salesman = text(r.get("Salesman"))
        if salesman not in buckets:
            continue
        if year is not None and _year_of(r) != year:
            continue
        month = _month_of(r)
        if not month or month > end_month:
            continue
        slot = buckets[salesman][month - 1]
        if r.get("IsCredit"):
            slot["credits"] += num(r.get("Total Invoice"))
        else:
            slot["subtotal"] += num(r.get("SubTotal Invoices"))
            slot["tariff"] += num(r.get("Tariff Charges"))
            slot["freight"] += num(r.get("Freight Charges"))
            slot["cc"] += num(r.get("CC Charges"))
            slot["misc"] += num(r.get("Misc Charges"))

    labels = list(_MONTHS[:end_month])
    columns = [
        {"field": "Salesman", "label": "Salesman", "type": "text"},
        {"field": "Commission %", "label": "Commission %", "type": "percent"},
    ]
    columns += [{"field": f"Comm {lbl}", "label": lbl, "type": "money"} for lbl in labels]
    columns.append({"field": "YTD Commission", "label": "YTD Commission", "type": "money"})

    grand_by_label = {lbl: 0.0 for lbl in labels}
    grand_ytd = 0.0
    data_rows: list[dict] = []
    for salesman in sorted(earners, key=lambda s: names.get(s, s).lower()):
        rate = earners[salesman]
        row: dict[str, Any] = {"Salesman": names.get(salesman, salesman), "Commission %": rate}
        ytd = 0.0
        for idx, lbl in enumerate(labels):
            slot = buckets[salesman][idx]
            ti = slot["subtotal"] + slot["tariff"] + slot["freight"] + slot["cc"] + slot["misc"]
            net = ti + slot["credits"] - slot["freight"] - slot["cc"]
            commission = net * rate
            row[f"Comm {lbl}"] = round(commission, 2)
            grand_by_label[lbl] += commission
            ytd += commission
        row["YTD Commission"] = round(ytd, 2)
        grand_ytd += ytd
        data_rows.append(row)

    total: dict[str, Any] = {"Salesman": "TOTAL", "Commission %": ""}
    for lbl in labels:
        total[f"Comm {lbl}"] = round(grand_by_label[lbl], 2)
    total["YTD Commission"] = round(grand_ytd, 2)

    return {"columns": columns, "rows": data_rows, "total": total, "layout": "commission"}


TRANSFORMS = {
    "commission_monthly_pivot": commission_monthly_pivot,
}
