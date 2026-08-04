"""Customer's Last Order builder: Order Rank grouping, ADDON under main,
default-to-latest, merge + (item, price) rollup."""

from report_engine.reports import customer_last_order as B


def _row(rank, so, po, date, item, desc, qty_o, qty_s, qty_c, price, total,
         account="100", name="Acme", salesman="REdwards"):
    return {
        "Order Rank": rank,
        "Customer Account": account,
        "Customer Name": name,
        "Sales Order Number": so,
        "PO #": po,
        "Order Date": date,
        "Salesman": salesman,
        "Item #": item,
        "Description": desc,
        "Qty Ordered": qty_o,
        "Qty Shipped": qty_s,
        "Qty Cancelled": qty_c,
        "Sales Price": price,
        "Total": total,
    }


def _rows():
    # Rank 1 = newest logical order (main + ADDON already rolled by SP).
    # Rank 2 = older logical order. No separate ADDON card/rank.
    return [
        _row(1, "ORD00821525", "CL42726", "2026-04-28",
             "ITM-A", "Widget", 10, 10, 0, 2.00, 20.00),
        _row(1, "ORD00821525", "CL42726", "2026-04-28",
             "ITM-B", "Gadget", 3, 3, 0, 5.00, 15.00),  # came from ADDON SO
        _row(2, "SO2", "PO-555", "2026-02-01",
             "ITM-A", "Widget", 5, 5, 0, 2.00, 10.00),
    ]


def test_logical_orders_one_per_rank_newest_first():
    orders = B.logical_orders(_rows())
    assert [o.order_number for o in orders] == ["ORD00821525", "SO2"]
    assert orders[0].customer_req == "CL42726"
    assert orders[0].rank == 1


def test_addon_lines_stay_under_main_rank():
    # ADDON physical SO is not a separate logical order; its lines share rank 1.
    view = B.build(_rows())
    assert view.selected_orders == ["ORD00821525"]
    assert view.primary.order_number == "ORD00821525"
    assert view.display_po == "CL42726"
    assert {l.item for l in view.lines} == {"ITM-A", "ITM-B"}
    assert view.totals["total"] == 35.0


def test_defaults_to_newest_rank():
    view = B.build(_rows())
    assert view.selected_orders == ["ORD00821525"]
    assert len(view.headers) == 1


def test_merge_rolls_up_same_item_price_across_ranks():
    view = B.build(_rows(), requested_orders=["ORD00821525", "SO2"])
    assert len(view.headers) == 2
    a = next(l for l in view.lines if l.item == "ITM-A")
    assert a.qty_shipped == 15 and a.total == 30.0
    b = next(l for l in view.lines if l.item == "ITM-B")
    assert b.qty_shipped == 3 and b.total == 15.0
    assert view.totals["qty_shipped"] == 18 and view.totals["total"] == 45.0


def test_display_po_uses_common_prefix_when_merging():
    rows = [
        _row(1, "SO3", "PO-555", "2026-03-10", "ITM-A", "W", 1, 1, 0, 1, 1),
        _row(2, "SO2", "PO-555-X", "2026-02-01", "ITM-B", "G", 1, 1, 0, 1, 1),
    ]
    view = B.build(rows, requested_orders=["SO3", "SO2"])
    assert view.display_po == "PO-555"


def test_unknown_requested_order_falls_back_to_latest():
    view = B.build(_rows(), requested_orders=["NOPE"])
    assert view.selected_orders == ["ORD00821525"]


def test_no_rows_yields_empty_view():
    view = B.build([])
    assert view.headers == [] and view.lines == [] and view.primary is None
    assert view.totals["total"] == 0
