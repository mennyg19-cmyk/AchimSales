"""Customer Activity: last-order join, salesman tabs, N/A, scope filtering."""

from report_engine.facts import SalesmanFact
from report_engine.lib import salesman_key
from report_engine.reports import customer_activity as B
from report_engine.sources import customer_master as CM
from report_engine.sources import ordered as O


def _salesmen():
    return {
        salesman_key("REdwards"): SalesmanFact(
            source="reporting_api", key="redwards", number="10",
            full_name="Robert Edwards", display_name="Bob", commission_pct=0.0),
        salesman_key("JSmith"): SalesmanFact(
            source="reporting_api", key="jsmith", number="20",
            full_name="Jane Smith", display_name="Jane", commission_pct=0.0),
    }


def _customers():
    return CM.to_facts([
        {"CustomerAccount": "100", "CustomerName": "Acme", "SalesGroup": "REdwards"},
        {"CustomerAccount": "200", "CustomerName": "Beta", "SalesGroup": "JSmith"},
        {"CustomerAccount": "300", "CustomerName": "Cold Co", "SalesGroup": ""},  # unassigned
    ])


def _orders():
    return O.to_facts([
        {"CustomerAccount": "100", "SalesOrderNumber": "SO-OLD", "CustomerRequisition": "PO-1",
         "CreatedDateTime": "2026-01-01T00:00:00", "QuantityOrdered": "1", "Item": "X"},
        {"CustomerAccount": "100", "SalesOrderNumber": "SO-NEW", "CustomerRequisition": "PO-2",
         "CreatedDateTime": "2026-03-15T00:00:00", "QuantityOrdered": "1", "Item": "X"},
        # customer 200 has an order; 300 has none
        {"CustomerAccount": "200", "SalesOrderNumber": "SO-B", "CustomerRequisition": "",
         "CreatedDateTime": "2025-12-01T00:00:00", "QuantityOrdered": "1", "Item": "Y"},
    ])


def test_all_tab_has_every_customer_with_salesman_column():
    tabs = B.build(_customers(), _orders(), salesmen=_salesmen())
    all_tab = next(t for t in tabs if t["key"] == "all")
    assert all_tab["columns"][0]["field"] == "Salesman"
    assert len(all_tab["rows"]) == 3


def test_most_recent_order_wins():
    tabs = B.build(_customers(), _orders(), salesmen=_salesmen())
    acme = next(r for r in next(t for t in tabs if t["key"] == "all")["rows"]
                if r["Customer Account"] == "100")
    assert acme["Last Order Date"] == "2026-03-15"
    assert acme["Sales Order Number"] == "SO-NEW"
    assert acme["PO #"] == "PO-2"


def test_no_orders_shows_na():
    tabs = B.build(_customers(), _orders(), salesmen=_salesmen())
    cold = next(r for r in next(t for t in tabs if t["key"] == "all")["rows"]
                if r["Customer Account"] == "300")
    assert cold["Last Order Date"] == "N/A"
    assert cold["PO #"] == "N/A" and cold["Sales Order Number"] == "N/A"


def test_blank_po_falls_back_to_na():
    tabs = B.build(_customers(), _orders(), salesmen=_salesmen())
    beta = next(r for r in next(t for t in tabs if t["key"] == "all")["rows"]
                if r["Customer Account"] == "200")
    assert beta["PO #"] == "N/A"          # order had blank PO
    assert beta["Sales Order Number"] == "SO-B"


def test_per_salesman_and_unassigned_tabs():
    tabs = B.build(_customers(), _orders(), salesmen=_salesmen())
    keys = [t["key"] for t in tabs]
    names = [t["name"] for t in tabs]
    assert "unassigned" in keys
    assert "Bob" in names and "Jane" in names       # resolved display names
    bob = next(t for t in tabs if t["name"] == "Bob")
    assert bob["columns"] == B._BASE_COLS            # no Salesman column on sub-tabs


def test_scope_restricts_to_own_book_and_hides_unassigned():
    tabs = B.build(_customers(), _orders(), salesmen=_salesmen(),
                   scope={"salesman": "REdwards"})
    keys = [t["key"] for t in tabs]
    assert "unassigned" not in keys
    all_rows = next(t for t in tabs if t["key"] == "all")["rows"]
    assert {r["Customer Account"] for r in all_rows} == {"100"}
