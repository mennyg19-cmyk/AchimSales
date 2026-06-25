"""Tests for the ordered report's adapter, params, tabs, and conditions.

Pure-function tests -- no database, no network. Verifies the manifest maps
the SP's raw column names correctly, the params translator builds the right
SP parameters, and the tab engine groups/filters ordered data.
"""

from __future__ import annotations

from rebuild.reports import conditions
from rebuild.reports.adapter import normalize
from rebuild.reports.engine import build_tabs
from rebuild.reports.manifests import manifest_for
from rebuild.reports.params import force_salesman_scope, translate
from rebuild.reports.transforms import TRANSFORMS


def _raw_sample():
    return [
        {
            "SalesOrderNumber": "SO-001", "CustomerAccount": "C100",
            "customername": "Acme Corp", "CreatedDateTime": "2026-03-15T10:30:00",
            "LineNumber": 1, "Item": "ITEM-A", "ItemDescription": "Widget A",
            "SalesPrice": 25.00, "SalesStatus": "Open order",
            "QuantityOrdered": 100, "QuantityReserved": 50,
            "ReleasedQuantity": 40, "DeliveryRemainder": 60, "CancelledQTY": 0,
            "Ordered $": 2500.00, "Shipped $": 1000.00, "Cancelled $": 0,
            "SalesGroup": "S1", "SalesmanName": "Alice", "Commission": 0.06,
        },
        {
            "SalesOrderNumber": "SO-001", "CustomerAccount": "C100",
            "customername": "Acme Corp", "CreatedDateTime": "2026-03-15T10:30:00",
            "LineNumber": 2, "Item": "ITEM-B", "ItemDescription": "Widget B",
            "SalesPrice": 10.00, "SalesStatus": "Invoiced",
            "QuantityOrdered": 200, "QuantityReserved": 0,
            "ReleasedQuantity": 200, "DeliveryRemainder": 0, "CancelledQTY": 0,
            "Ordered $": 2000.00, "Shipped $": 2000.00, "Cancelled $": 0,
            "SalesGroup": "S1", "SalesmanName": "Alice", "Commission": 0.06,
        },
        {
            "SalesOrderNumber": "SO-002", "CustomerAccount": "C200",
            "customername": "Beta Inc", "CreatedDateTime": "2026-04-01T08:00:00",
            "LineNumber": 1, "Item": "ITEM-C", "ItemDescription": "Gadget C",
            "SalesPrice": 50.00, "SalesStatus": "Open order",
            "QuantityOrdered": 50, "QuantityReserved": 25,
            "ReleasedQuantity": 10, "DeliveryRemainder": 40, "CancelledQTY": 5,
            "Ordered $": 2500.00, "Shipped $": 500.00, "Cancelled $": 250.00,
            "SalesGroup": "S2", "SalesmanName": "Bob", "Commission": 5,
        },
    ]


def test_manifest_exists_for_ordered():
    specs = manifest_for("ordered")
    field_keys = [s.key for s in specs]
    assert "SalesOrderNumber" in field_keys
    assert "Ordered $" in field_keys
    assert "SalesGroup" in field_keys
    assert "Commission" in field_keys


def test_adapter_maps_customername_alias():
    rows = normalize("ordered", _raw_sample())
    assert rows[0]["CustomerName"] == "Acme Corp"


def test_adapter_normalizes_whole_percent_commission():
    rows = normalize("ordered", _raw_sample())
    bob = next(r for r in rows if r["SalesGroup"] == "S2")
    assert bob["Commission"] == 0.05


def test_adapter_cleans_money_and_int_types():
    rows = normalize("ordered", _raw_sample())
    first = rows[0]
    assert isinstance(first["SalesPrice"], float)
    assert isinstance(first["QuantityOrdered"], int)
    assert isinstance(first["Ordered $"], float)


def test_params_translator_builds_date_range():
    sp_params = translate("ordered", {"period": "custom", "start_date": "2026-01-01", "end_date": "2026-06-30"})
    assert sp_params["CreatedDateTimeFrom"] == "2026-01-01"
    assert sp_params["CreatedDateTimeTo"] == "2026-06-30"


def test_params_translator_passes_exact_match_filters():
    sp_params = translate("ordered", {"SalesOrderNumber": "SO-001", "Item": "ITEM-A", "SalesStatus": "Open Order"})
    assert sp_params["SalesOrderNumber"] == "SO-001"
    assert sp_params["Item"] == "ITEM-A"
    assert sp_params["SalesStatus"] == "Open Order"


def test_params_translator_ignores_empty_filters():
    sp_params = translate("ordered", {"SalesOrderNumber": "", "Item": None})
    assert "SalesOrderNumber" not in sp_params
    assert "Item" not in sp_params


def test_params_salesman_scope_pins_sales_group():
    sp_params = translate("ordered", {"period": "ytd"})
    scoped = force_salesman_scope("ordered", sp_params, ["S1", "S2"])
    assert scoped["SalesGroup"] == "S1,S2"


def test_params_salesman_scope_none_leaves_untouched():
    sp_params = translate("ordered", {"period": "ytd"})
    scoped = force_salesman_scope("ordered", sp_params, None)
    assert "SalesGroup" not in scoped


def test_has_multiple_sales_groups_condition():
    rows = normalize("ordered", _raw_sample())
    assert conditions.has_multiple_sales_groups(rows) is True
    single = [r for r in rows if r["SalesGroup"] == "S1"]
    assert conditions.has_multiple_sales_groups(single) is False


def test_full_details_tab_has_all_rows():
    rows = normalize("ordered", _raw_sample())
    tabs = build_tabs(rows, _full_details_tab(), transforms=TRANSFORMS)
    assert len(tabs) == 1
    assert len(tabs[0]["rows"]) == 3


def test_summary_by_customer_groups_correctly():
    rows = normalize("ordered", _raw_sample())
    tabs = build_tabs(rows, _customer_summary_tab(), transforms=TRANSFORMS)
    summary = tabs[0]
    c100 = next(r for r in summary["rows"] if r["CustomerAccount"] == "C100")
    assert c100["OrderCount"] == 1  # 1 distinct order (SO-001, 2 lines)
    assert c100["TotalOrdered"] == 4500.00
    assert c100["TotalShipped"] == 3000.00


def test_open_orders_tab_filters_to_open_status():
    rows = normalize("ordered", _raw_sample())
    tabs = build_tabs(rows, _open_orders_tab(), transforms=TRANSFORMS)
    open_tab = tabs[0]
    # 2 of the 3 sample rows have SalesStatus "Open order"
    assert len(open_tab["rows"]) == 2
    # Both remaining rows are from different orders
    accounts = {r["CustomerAccount"] for r in open_tab["rows"]}
    assert accounts == {"C100", "C200"}


def _full_details_tab():
    return [{
        "tab_key": "full_data", "label": "Full Details",
        "column_keys": [
            {"field": "SalesOrderNumber", "type": "text"},
            {"field": "CustomerAccount", "type": "text"},
            {"field": "Ordered $", "type": "money"},
            {"field": "Shipped $", "type": "money"},
        ],
        "sorters": [{"field": "CreatedDateTime", "dir": "desc"}],
    }]


def _customer_summary_tab():
    return [{
        "tab_key": "summary_by_customer", "label": "Summary by Customer",
        "group_by": ["CustomerAccount", "CustomerName"],
        "aggregations": {
            "OrderCount": "count_distinct:SalesOrderNumber",
            "TotalOrdered": "sum:Ordered $",
            "TotalShipped": "sum:Shipped $",
            "TotalCancelled": "sum:Cancelled $",
        },
        "column_keys": [
            {"field": "CustomerAccount", "type": "text"},
            {"field": "OrderCount", "type": "int"},
            {"field": "TotalOrdered", "type": "money"},
            {"field": "TotalShipped", "type": "money"},
            {"field": "TotalCancelled", "type": "money"},
        ],
    }]


def _open_orders_tab():
    return [{
        "tab_key": "open_orders", "label": "Open Orders",
        "filter_expr": '{"op":"eq","field":"SalesStatus","value":"Open order"}',
        "column_keys": [
            {"field": "SalesOrderNumber", "type": "text"},
            {"field": "CustomerAccount", "type": "text"},
            {"field": "Ordered $", "type": "money"},
        ],
    }]
