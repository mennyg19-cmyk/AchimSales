"""Customer's Last Order builder (in-app, customer-picker driven).

Pick a customer, see their most recent *invoiced* order with the option to merge
earlier invoiced orders (the "addon" pattern). Format + math follow LIVE
(webapp/blueprints/reports.py `_rollup_lines` / `_common_po_prefix` and
webapp/services/d365.py): rows rolled up by (item, sales_price); ``Total`` =
sales_price * qty_shipped (what actually invoiced).

The per-line Qty Shipped / Qty Cancelled breakdown reuses the Ordered report's
classifier (`report_engine.reports.ordered.classify_line`) so the numbers match
the Ordered Excel cell-for-cell. Like Ordered, those qty buckets stay provisional
until salesline_release returns an explicit cancelled quantity.

Pure + source-agnostic: it consumes OrderLineFacts (the same facts the Ordered
report consumes) and returns plain dicts/dataclasses the route renders. All I/O
(the SP fetch) lives in web.reporting.report_service.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from report_engine.facts import OrderLineFact
from report_engine.reports.ordered import classify_line

# A line is part of the customer's order history only when its order is invoiced.
# Mirrors LIVE: the header OrderStatus must contain "invoiced" (covers
# "Invoiced" and "Partially invoiced"), case-insensitive.
_INVOICED = "invoiced"


@dataclass(frozen=True)
class OrderSummary:
    """One invoiced order header for the picker (newest first)."""
    order_number: str
    order_date: str
    status: str
    customer_req: str
    order_name: str


@dataclass(frozen=True)
class LineRow:
    item: str
    description: str
    qty_ordered: float
    qty_shipped: float
    qty_cancelled: float
    sales_price: float
    total: float
    from_orders: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LastOrder:
    """The assembled view: selected orders + rolled-up lines + totals."""
    headers: list[OrderSummary]
    lines: list[LineRow]
    totals: dict
    display_po: str
    selected_orders: list[str]

    @property
    def primary(self) -> OrderSummary | None:
        return self.headers[0] if self.headers else None


def _is_invoiced(order_status: str) -> bool:
    return _INVOICED in (order_status or "").lower()


def invoiced_orders(facts: list[OrderLineFact]) -> list[OrderSummary]:
    """Distinct invoiced orders for the customer, newest first.

    One summary per SalesOrderNumber, taking the header fields off the first
    line seen for that order. Sorted by order_date descending (blank dates last).
    """
    seen: dict[str, OrderSummary] = {}
    for f in facts:
        if not _is_invoiced(f.order_status):
            continue
        num = (f.sales_order_number or "").strip()
        if not num or num in seen:
            continue
        seen[num] = OrderSummary(
            order_number=num,
            order_date=f.order_date or "",
            status=f.order_status or "",
            customer_req=f.po_number or "",
            order_name=f.sales_order_name or "",
        )
    return sorted(seen.values(), key=lambda o: o.order_date or "", reverse=True)


def _common_po_prefix(pos: list[str]) -> str:
    """Longest shared PO prefix (trailing separators stripped), else the first.

    Renders a clean header when merged orders look like 'PO123' + 'PO123-addon'.
    """
    pos = [p.strip() for p in pos if p and p.strip()]
    if not pos:
        return ""
    if len(pos) == 1:
        return pos[0]
    prefix = pos[0]
    for p in pos[1:]:
        i = 0
        while i < len(prefix) and i < len(p) and prefix[i] == p[i]:
            i += 1
        prefix = prefix[:i]
    return prefix.rstrip("-_ ").strip() or pos[0]


def _rollup(lines: list[dict]) -> list[LineRow]:
    """Combine identical (item, sales_price) rows across orders.

    Different items, or the same item at a different price, stay separate so the
    rep can see a price discrepancy. ``total`` = sales_price * qty_shipped.
    """
    grouped: dict[tuple[str, float], dict] = {}
    orders_for: dict[tuple[str, float], list[str]] = {}
    for ln in lines:
        price = round(float(ln.get("UnitPrice") or 0), 4)
        key = (ln.get("Item#", ""), price)
        g = grouped.get(key)
        if g is None:
            g = grouped[key] = {
                "item": ln.get("Item#", ""),
                "description": ln.get("ItemName", ""),
                "qty_ordered": 0.0, "qty_shipped": 0.0, "qty_cancelled": 0.0,
                "sales_price": price, "total": 0.0,
            }
            orders_for[key] = []
        g["qty_ordered"] += float(ln.get("QtyOrdered") or 0)
        g["qty_shipped"] += float(ln.get("QtyShipped") or 0)
        g["qty_cancelled"] += float(ln.get("QtyCancelled") or 0)
        g["total"] += price * float(ln.get("QtyShipped") or 0)
        onum = ln.get("SalesOrderNumber")
        if onum and onum not in orders_for[key]:
            orders_for[key].append(onum)

    rows = [
        LineRow(
            item=g["item"], description=g["description"],
            qty_ordered=round(g["qty_ordered"], 2),
            qty_shipped=round(g["qty_shipped"], 2),
            qty_cancelled=round(g["qty_cancelled"], 2),
            sales_price=g["sales_price"], total=round(g["total"], 2),
            from_orders=orders_for[key],
        )
        for key, g in grouped.items()
    ]
    rows.sort(key=lambda r: r.item)
    return rows


def build(facts: list[OrderLineFact], requested_orders: list[str] | None = None) -> LastOrder:
    """Assemble the last-order view.

    ``requested_orders`` is an explicit set of orders to show together; when
    omitted (or none match) it defaults to the single most recent invoiced order.
    """
    summaries = invoiced_orders(facts)
    by_number = {s.order_number: s for s in summaries}

    wanted = [o.strip() for o in (requested_orders or []) if o.strip()]
    selected = [o for o in wanted if o in by_number]
    if not selected and summaries:
        selected = [summaries[0].order_number]

    selected_set = set(selected)
    headers = [by_number[o] for o in sorted(
        selected, key=lambda o: by_number[o].order_date or "", reverse=True)]

    chosen_lines = [
        classify_line(f) for f in facts
        if (f.sales_order_number or "").strip() in selected_set
    ]
    rolled = _rollup(chosen_lines)

    pos = [h.customer_req for h in headers if h.customer_req]
    display_po = _common_po_prefix(pos) if pos else (headers[0].customer_req if headers else "")

    totals = {
        "qty_ordered": round(sum(r.qty_ordered for r in rolled), 2),
        "qty_shipped": round(sum(r.qty_shipped for r in rolled), 2),
        "qty_cancelled": round(sum(r.qty_cancelled for r in rolled), 2),
        "total": round(sum(r.total for r in rolled), 2),
    }
    return LastOrder(headers=headers, lines=rolled, totals=totals,
                     display_po=display_po, selected_orders=selected)
