"""Item Averages builder + privileged-only registry access."""

from report_engine.reports import item_averages as rpt
from report_engine.registry import ReportStatus, get
from web.auth.authorization import Authorization
from web.auth.principal import Principal
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.repositories.users import UserRepository


def test_rollup_sums_across_customers_and_divides_by_12_and_52():
    rows = [
        {"Item #": "A", "Item Name": "Alpha", "Total Qty": 120},
        {"Item #": "A", "Item Name": "Alpha", "Total Qty": 24},
        {"Item #": "B", "Item Name": "Beta", "Total Qty": 52},
    ]
    out = rpt.rollup_by_item(rows)
    assert out[0]["Item #"] == "A"
    assert out[0]["12-Month Qty"] == 144.0
    assert out[0]["Avg/Month"] == 12.0
    assert out[0]["Avg/Week"] == round(144 / 52, 2)
    assert out[1]["Avg/Week"] == 1.0


def test_build_returns_one_tab():
    tabs = rpt.build([{"Item #": "X", "Item Name": "Ex", "Total Qty": 12}])
    assert len(tabs) == 1
    assert tabs[0]["key"] == "item_averages"
    assert tabs[0]["rows"][0]["Avg/Month"] == 1.0


def test_registry_marks_item_averages_privileged_only():
    spec = get("item_averages")
    assert spec is not None
    assert spec.status is ReportStatus.BUILT
    assert spec.privileged_only is True
    assert spec.salesman_default is False


def test_salesman_and_manager_cannot_view_even_with_allow(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    users = UserRepository(db)
    sm = users.upsert("sm@b.com", role="salesman")
    mgr = users.upsert("mgr@b.com", role="manager")
    admin = users.upsert("admin@b.com", role="admin")
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO user_report_access(user_id, report_key, allowed) VALUES (?, ?, 1)",
            (sm.id, "item_averages"),
        )
        conn.execute(
            "INSERT INTO user_report_access(user_id, report_key, allowed) VALUES (?, ?, 1)",
            (mgr.id, "item_averages"),
        )
    authz = Authorization(db)
    assert authz.can_view_report(Principal("sm@b.com", "S", "salesman"), "item_averages") is False
    assert authz.can_view_report(Principal("mgr@b.com", "M", "manager"), "item_averages") is False
    assert authz.can_view_report(Principal("admin@b.com", "A", "admin"), "item_averages") is True
