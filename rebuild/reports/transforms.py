"""Bespoke per-tab math that the generic group/total engine can't express."""

# === What's in this file ===
# Most tabs are plain group-and-total, but Commissions is a month-by-month build
# per salesman with its own net formula. Two tabs share that math via one helper:
# a flat pivot (one row per salesman, a column per month) and a card view (one
# block per salesman with a Month / Net / Commission mini-table).
#
# THE COMMISSION MATH (owner-confirmed, mirrors LIVE; numbers are PROVISIONAL
# until owner sign-off):
#   The SP sends only the salesman's RATE (column `commission`, a fraction).
#   Per salesman, per month:
#     net = (subtotal + tariff + freight + cc + misc) + credits - freight - cc
#         (credits are negative; freight + cc are excluded from the commission base)
#     commission = net * rate
#   YTD commission = sum of the months (rounded only to display).
#
# _salesman_months() -- shared: per salesman, per month net + commission
# commission_monthly_pivot() -- flat: one row per salesman, a column per month
# commission_cards() -- one card payload per salesman (month mini-table + YTD)
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


def _salesman_months(rows: Sequence[dict]) -> dict:
    """Per salesman who earns commission, the net base and commission for each
    month of the reported year. Returns the month labels, the earners (sorted by
    name), their rate, and per-salesman lists of {net, commission} by month."""
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
    ordered = sorted(earners, key=lambda s: names.get(s, s).lower())
    # Keep the monthly net/commission UNROUNDED here; callers round only the
    # numbers they display, and sum the raw values for YTD/grand totals so the
    # totals can't drift from the months by a penny.
    per_salesman: dict[str, list[dict]] = {}
    for salesman in ordered:
        rate = earners[salesman]
        months_out = []
        for idx in range(end_month):
            slot = buckets[salesman][idx]
            ti = slot["subtotal"] + slot["tariff"] + slot["freight"] + slot["cc"] + slot["misc"]
            net = ti + slot["credits"] - slot["freight"] - slot["cc"]
            months_out.append({"net": net, "commission": net * rate})
        per_salesman[salesman] = months_out

    return {
        "labels": labels,
        "ordered": ordered,
        "names": names,
        "rates": earners,
        "per_salesman": per_salesman,
    }


def commission_monthly_pivot(rows: Sequence[dict], params: Mapping[str, Any]) -> dict:
    built = _salesman_months(rows)
    labels = built["labels"]

    columns = [
        {"field": "Salesman", "label": "Salesman", "type": "text"},
        {"field": "Commission %", "label": "Commission %", "type": "percent"},
    ]
    columns += [{"field": f"Comm {lbl}", "label": lbl, "type": "money"} for lbl in labels]
    columns.append({"field": "YTD Commission", "label": "YTD Commission", "type": "money"})

    grand_by_label = {lbl: 0.0 for lbl in labels}
    grand_ytd = 0.0
    data_rows: list[dict] = []
    for salesman in built["ordered"]:
        months = built["per_salesman"][salesman]
        row: dict[str, Any] = {
            "Salesman": built["names"].get(salesman, salesman),
            "Commission %": built["rates"][salesman],
        }
        ytd = 0.0
        for idx, lbl in enumerate(labels):
            commission = months[idx]["commission"]
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


def commission_cards(rows: Sequence[dict], params: Mapping[str, Any]) -> dict:
    built = _salesman_months(rows)
    labels = built["labels"]

    salesmen = []
    grand_net_raw = 0.0
    grand_commission_raw = 0.0
    for salesman in built["ordered"]:
        months = built["per_salesman"][salesman]
        monthly = [
            {"month_label": labels[idx], "net": round(months[idx]["net"], 2), "commission": round(months[idx]["commission"], 2)}
            for idx in range(len(labels))
        ]
        raw_net = sum(m["net"] for m in months)
        raw_commission = sum(m["commission"] for m in months)
        grand_net_raw += raw_net
        grand_commission_raw += raw_commission
        salesmen.append({
            "salesman_number": salesman,
            "salesman_name": built["names"].get(salesman, salesman),
            "commission_pct": built["rates"][salesman],
            "monthly": monthly,
            "ytd": {"net": round(raw_net, 2), "commission": round(raw_commission, 2)},
        })

    grand = {"net": round(grand_net_raw, 2), "commission": round(grand_commission_raw, 2)}
    # Keep a flat columns/rows so non-card consumers (and exports) still work.
    columns = [
        {"field": "Salesman", "label": "Salesman", "type": "text"},
        {"field": "Commission %", "label": "Commission %", "type": "percent"},
        {"field": "YTD Net", "label": "YTD Net", "type": "money"},
        {"field": "YTD Commission", "label": "YTD Commission", "type": "money"},
    ]
    flat_rows = [
        {
            "Salesman": s["salesman_name"],
            "Commission %": s["commission_pct"],
            "YTD Net": s["ytd"]["net"],
            "YTD Commission": s["ytd"]["commission"],
        }
        for s in salesmen
    ]
    total = {"Salesman": "TOTAL", "Commission %": "", "YTD Net": grand["net"], "YTD Commission": grand["commission"]}

    return {
        "columns": columns,
        "rows": flat_rows,
        "total": total,
        "layout": "commission_cards",
        "salesmen": salesmen,
        "month_labels": labels,
        "grand": grand,
    }


TRANSFORMS = {
    "commission_monthly_pivot": commission_monthly_pivot,
    "commission_cards": commission_cards,
}
