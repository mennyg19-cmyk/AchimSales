"""Customer's Last Order builder (in-app, customer-picker driven).

Source: ``customer_last_orders`` (rpt.usp_customer_last_orders). That SP returns
line detail for the latest logical customer orders (open + uninvoiced included).
A PO beginning with ADDON is already rolled into the matching main PO under one
Order Rank, with main-order metadata on every line.

UX matches live: show the newest logical order by default; "Add previous order"
merges earlier ranks from the same SP result (OrderCount=10). Rows are rolled up
by (item, sales_price) across selected ranks so merging two visits looks like
live's merge of two sales orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from report_engine.lib import first_of, num, text


@dataclass(frozen=True)
class OrderSummary:
    """One logical order header for the picker (newest / rank 1 first)."""
    order_number: str
    order_date: str
    status: str
    customer_req: str
    order_name: str
    rank: int = 0
    salesman: str = ""


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


def _col(row: Mapping[str, Any], *names: str) -> Any:
    return first_of(row, *names)


def _rank(row: Mapping[str, Any]) -> int:
    raw = _col(row, "Order Rank", "OrderRank", "order_rank")
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 0


def _line_dict(row: Mapping[str, Any]) -> dict:
    """Normalize one SP line for rollup / display."""
    price = round(num(_col(row, "Sales Price", "SalesPrice", "sales_price")), 4)
    qty_shipped = num(_col(row, "Qty Shipped", "QtyShipped", "qty_shipped"))
    total_raw = _col(row, "Total", "total")
    total = num(total_raw) if total_raw not in (None, "") else round(price * qty_shipped, 2)
    return {
        "Item#": text(_col(row, "Item #", "Item#", "Item", "item")),
        "ItemName": text(_col(row, "Description", "ItemDescription", "Item Name", "description")),
        "QtyOrdered": num(_col(row, "Qty Ordered", "QtyOrdered", "qty_ordered")),
        "QtyShipped": qty_shipped,
        "QtyCancelled": num(_col(row, "Qty Cancelled", "QtyCancelled", "qty_cancelled")),
        "UnitPrice": price,
        "Total": total,
        "SalesOrderNumber": text(_col(
            row, "Sales Order Number", "SalesOrderNumber", "sales_order_number")),
    }


def logical_orders(rows: list[Mapping[str, Any]]) -> list[OrderSummary]:
    """Distinct logical orders (one per Order Rank), rank ascending (newest first).

    Header fields come from the SP's main-order metadata already stamped on each
    line after ADDON rollup — never invent a second card for an ADDON PO.
    """
    by_rank: dict[int, OrderSummary] = {}
    for row in rows:
        rank = _rank(row)
        if rank < 1 or rank in by_rank:
            continue
        by_rank[rank] = OrderSummary(
            order_number=text(_col(
                row, "Sales Order Number", "SalesOrderNumber", "sales_order_number")),
            order_date=text(_col(row, "Order Date", "OrderDate", "order_date"))[:10],
            status="",
            customer_req=text(_col(row, "PO #", "PO#", "CustomerRequisition", "po_number")),
            order_name="",
            rank=rank,
            salesman=text(_col(row, "Salesman", "SalesGroup", "salesman")),
        )
    return [by_rank[r] for r in sorted(by_rank)]


def _common_po_prefix(pos: list[str]) -> str:
    """Longest shared PO prefix (trailing separators stripped), else the first."""
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
    """Combine identical (item, sales_price) rows across selected ranks."""
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
        g["total"] += round(float(ln.get("Total") or 0), 2)
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


def build(rows: list[Mapping[str, Any]], requested_orders: list[str] | None = None) -> LastOrder:
    """Assemble the last-order view from SP rows.

    ``requested_orders`` is main Sales Order Numbers to show together; when
    omitted (or none match) it defaults to the single newest logical order
    (lowest Order Rank).
    """
    summaries = logical_orders(rows)
    by_number = {s.order_number: s for s in summaries if s.order_number}

    wanted = [o.strip() for o in (requested_orders or []) if o.strip()]
    selected = [o for o in wanted if o in by_number]
    if not selected and summaries:
        selected = [summaries[0].order_number]

    selected_set = set(selected)
    headers = [by_number[o] for o in sorted(
        selected, key=lambda o: by_number[o].rank or 10**9)]

    selected_ranks = {h.rank for h in headers}
    chosen_lines = [
        _line_dict(r) for r in rows
        if _rank(r) in selected_ranks
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
