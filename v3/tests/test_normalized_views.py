"""Normalized views tables: handles, Gate A round-trip, foreign keys, Gate B workbooks."""

import io
import sqlite3
from datetime import date

import pytest

from report_engine.reports import number_4 as number4_builder
from report_engine.reports import ordered as ordered_builder
from report_engine.sources import ordered as ordered_source
from web.data.connection import Database
from web.data.migrate import migrate
from web.data.normalized_views import (
    after_table_write,
    assemble_layout,
    assemble_params,
    canonicalize_layout,
    canonicalize_params,
    company_view_id,
    project_from_legacy,
    suggest_handle,
)
from web.delivery.layout import apply_layout, expand_clones
from web.reporting.export import build_workbook
from web.data.repositories.company_views import CompanyViewRepository
from web.data.repositories.report_defaults import ReportDefaultRepository
from web.data.repositories.saved_reports import SavedReportRepository
from web.data.repositories.schedules import MasterScheduleRepository, ScheduleRepository
from web.data.repositories.users import UserRepository
from web.scheduling.company_layouts import (
    DAILY_ORDERED_LAYOUT,
    DAILY_ORDERED_VIEW,
    HESHY_OPEN_LAYOUT,
    HESHY_OPEN_VIEW,
    seed_canonical_company_views,
)


def _db(tmp_path):
    db = Database(tmp_path / "p.db", tmp_path / "c.db")
    migrate(db)
    return db


def test_handle_collision_suffixes_second_user(tmp_path):
    db = _db(tmp_path)
    users = UserRepository(db)
    a = users.create("meir@x.com", role="admin", display_name="Meir Grego")
    b = users.create("mike@x.com", role="admin", display_name="Mike Grego")
    project_from_legacy(db)
    with db.precious() as conn:
        handles = {
            r["id"]: r["handle"]
            for r in conn.execute("SELECT id, handle FROM users")
        }
    assert handles[a.id] == "mgrego"
    assert handles[b.id] == "mgrego2"


def test_handle_from_first_initial_last_name():
    assert suggest_handle("Meir Grego", "meir@x.com") == "mgrego"
    assert suggest_handle("H Kaufman", "h@x.com") == "hkaufman"


def test_handle_falls_back_to_email_local_part():
    assert suggest_handle("", "mike.roth@achim.com") == "mikeroth"


def test_canonicalize_keeps_spaced_status_and_salesman_as_one_value():
    assert canonicalize_params({"status": "Open order", "salesman": "H Kaufman"}) == {
        "status": ["Open order"], "salesman": ["H Kaufman"],
    }
    assert canonicalize_params({"status": "Open order,Delivered"})["status"] == [
        "Open order", "Delivered",
    ]


def test_gate_a_round_trip_company_and_personal_and_defaults(tmp_path):
    db = _db(tmp_path)
    users = UserRepository(db)
    meir = users.create("meir@x.com", role="admin", display_name="Meir Grego")
    defaults = ReportDefaultRepository(db)
    defaults.upsert("ordered", params={"period": "ytd"},
                    layout={"views": {"by_order": {"group": []}}}, updated_by=meir.id)
    CompanyViewRepository(db).upsert(
        "ordered", DAILY_ORDERED_VIEW, params={}, layout=DAILY_ORDERED_LAYOUT, updated_by=None)
    CompanyViewRepository(db).upsert(
        "ordered", HESHY_OPEN_VIEW,
        params={"period": "yesterday", "salesman": "Hkaufman", "status": "Open order"},
        layout=HESHY_OPEN_LAYOUT, updated_by=None)
    n4 = {"active": "by_item", "order": ["by_item"],
          "views": {"by_item": {"group": ["Item Number"],
                                "sorters": [{"column": "Item Number", "dir": "asc"}]}}}
    CompanyViewRepository(db).upsert(
        "number_4", "YTD", params={"mode": "both", "year": "2026"}, layout=n4, updated_by=None)
    SavedReportRepository(db).create(
        meir.id, "ordered", "Open Orders",
        {"period": "this_week", "status": ["Open order"]},
        {"order": ["by_order"], "views": {"by_order": {"group": []}}})
    project_from_legacy(db)

    with db.precious() as conn:
        handle = conn.execute("SELECT handle FROM users WHERE id=?", (meir.id,)).fetchone()["handle"]
        assert handle == "mgrego"
        rows = conn.execute("SELECT id, kind, report_key, name FROM views").fetchall()
        by_name = {(r["kind"], r["report_key"], r["name"]): r["id"] for r in rows}

        cases = [
            ("default", "ordered", "Default",
             {"period": "ytd"}, {"views": {"by_order": {"group": []}}}),
            ("company", "ordered", DAILY_ORDERED_VIEW, {}, DAILY_ORDERED_LAYOUT),
            ("company", "ordered", HESHY_OPEN_VIEW,
             {"period": "yesterday", "salesman": "Hkaufman", "status": "Open order"},
             HESHY_OPEN_LAYOUT),
            ("company", "number_4", "YTD", {"mode": "both", "year": "2026"}, n4),
            ("personal", "ordered", "Open Orders",
             {"period": "this_week", "status": ["Open order"]},
             {"order": ["by_order"], "views": {"by_order": {"group": []}}}),
        ]
        for kind, report, name, params, layout in cases:
            vid = by_name[(kind, report, name)]
            assert assemble_params(conn, vid) == canonicalize_params(params)
            assert assemble_layout(conn, vid) == canonicalize_layout(layout)
            if kind == "company" and name == DAILY_ORDERED_VIEW:
                assert vid == company_view_id("ordered", DAILY_ORDERED_VIEW)
                groups = [r["column_name"] for r in conn.execute(
                    "SELECT g.column_name FROM layout_tab_groups g"
                    " JOIN layout_tabs t ON t.id=g.tab_id"
                    " WHERE t.view_id=? AND t.tab_key='summary' ORDER BY g.position",
                    (vid,))]
                assert groups == ["Salesman", "Customer Name"]


def test_project_is_idempotent(tmp_path):
    db = _db(tmp_path)
    seed_canonical_company_views(db)
    project_from_legacy(db)
    project_from_legacy(db)
    with db.precious() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM views WHERE kind='company'").fetchone()["c"]
        assert n == 2


def test_matching_named_schedule_reuses_view(tmp_path):
    db = _db(tmp_path)
    users = UserRepository(db)
    u = users.create("meir@x.com", role="admin", display_name="Meir Grego")
    layout = {"views": {"by_order": {"group": []}}}
    SavedReportRepository(db).create(u.id, "ordered", "Open Orders",
                                     {"period": "yesterday"}, layout)
    ScheduleRepository(db).create(
        u.id, "ordered", params={"period": "yesterday"}, layout=layout,
        cadence={"freq": "daily", "time": "08:00"}, view_name="Open Orders")
    project_from_legacy(db)
    with db.precious() as conn:
        n_views = conn.execute("SELECT COUNT(*) AS c FROM views WHERE kind='personal'").fetchone()["c"]
        assert n_views == 1
        sched = conn.execute("SELECT view_id FROM report_schedules WHERE legacy_kind='personal'").fetchone()
        view = conn.execute("SELECT id FROM views WHERE kind='personal'").fetchone()
        assert sched["view_id"] == view["id"]


def test_divergent_snapshot_gets_its_own_view(tmp_path):
    db = _db(tmp_path)
    users = UserRepository(db)
    u = users.create("meir@x.com", role="admin", display_name="Meir Grego")
    SavedReportRepository(db).create(
        u.id, "ordered", "Open Orders", {"period": "yesterday"},
        {"views": {"by_order": {"group": []}}})
    ScheduleRepository(db).create(
        u.id, "ordered", params={"period": "yesterday"},
        layout={"views": {"by_customer": {"group": ["Salesman"]}}},
        cadence={"freq": "daily", "time": "08:00"}, view_name="Open Orders")
    project_from_legacy(db)
    with db.precious() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM views WHERE kind='personal'").fetchone()["c"]
        assert n == 2
        live = conn.execute(
            "SELECT id FROM views WHERE kind='personal' AND name='Open Orders'"
        ).fetchone()["id"]
        used = conn.execute("SELECT view_id FROM report_schedules").fetchone()["view_id"]
        assert used != live
        assert assemble_layout(conn, used)["views"]["by_customer"]["group"] == ["Salesman"]


def test_orphan_layout_tab_is_rejected(tmp_path):
    db = _db(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        with db.precious() as conn:
            conn.execute(
                "INSERT INTO layout_tabs(id, view_id, tab_key, has_view)"
                " VALUES ('x','missing','by_order',1)"
            )


def test_cannot_delete_view_a_schedule_still_uses(tmp_path):
    db = _db(tmp_path)
    users = UserRepository(db)
    u = users.create("meir@x.com", role="admin", display_name="Meir Grego")
    SavedReportRepository(db).create(
        u.id, "ordered", "Open Orders", {"period": "yesterday"},
        {"views": {"by_order": {"group": []}}})
    ScheduleRepository(db).create(
        u.id, "ordered", params={"period": "yesterday"},
        layout={"views": {"by_order": {"group": []}}},
        cadence={"freq": "daily", "time": "08:00"}, view_name="Open Orders")
    project_from_legacy(db)
    with pytest.raises(sqlite3.IntegrityError):
        with db.precious() as conn:
            vid = conn.execute("SELECT id FROM views WHERE kind='personal'").fetchone()["id"]
            conn.execute("DELETE FROM views WHERE id=?", (vid,))


def test_unused_view_delete_cascades_tabs(tmp_path):
    db = _db(tmp_path)
    CompanyViewRepository(db).upsert(
        "ordered", DAILY_ORDERED_VIEW, params={}, layout=DAILY_ORDERED_LAYOUT, updated_by=None)
    project_from_legacy(db)
    with db.precious() as conn:
        vid = conn.execute("SELECT id FROM views").fetchone()["id"]
        conn.execute("DELETE FROM views WHERE id=?", (vid,))
        assert conn.execute("SELECT COUNT(*) AS c FROM layout_tabs").fetchone()["c"] == 0


def test_company_schedule_keeps_its_window_on_the_schedule_row(tmp_path):
    db = _db(tmp_path)
    seed_canonical_company_views(db)
    MasterScheduleRepository(db).create(
        "ordered", "DailyOrderReport", params={"period": "ytd"},
        layout=DAILY_ORDERED_LAYOUT, cadence={"freq": "daily", "time": "00:00"},
        view_name=DAILY_ORDERED_VIEW)
    project_from_legacy(db)
    with db.precious() as conn:
        row = conn.execute(
            "SELECT view_id, window_period FROM report_schedules WHERE legacy_kind='master'"
        ).fetchone()
        assert row["window_period"] == "ytd"
        name = conn.execute("SELECT name FROM views WHERE id=?", (row["view_id"],)).fetchone()["name"]
        assert name == DAILY_ORDERED_VIEW


def test_migration_creates_new_tables(tmp_path):
    db = _db(tmp_path)
    with db.precious() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for name in ("views", "layout_tabs", "layout_tab_groups", "report_schedules",
                 "schedule_recipients"):
        assert name in tables
    with db.precious() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    assert "handle" in cols


def test_save_this_view_writes_new_tables(tmp_path):
    db = _db(tmp_path)
    u = UserRepository(db).create("meir@x.com", role="admin", display_name="Meir Grego")
    layout = {"order": ["by_order"], "views": {"by_order": {"group": []}}}
    pid = SavedReportRepository(db).create(
        u.id, "ordered", "Open Orders", {"period": "yesterday"}, layout)
    with db.precious() as conn:
        vid = conn.execute(
            "SELECT id FROM views WHERE legacy_source='saved_reports' AND legacy_id=?",
            (pid,),
        ).fetchone()["id"]
        assert assemble_layout(conn, vid) == canonicalize_layout(layout)
        assert assemble_params(conn, vid) == canonicalize_params({"period": "yesterday"})


def test_edit_group_row_writes_back_old_json(tmp_path):
    db = _db(tmp_path)
    u = UserRepository(db).create("meir@x.com", role="admin", display_name="Meir Grego")
    pid = SavedReportRepository(db).create(
        u.id, "ordered", "Open Orders", {},
        {"views": {"by_order": {"group": []}}})
    with db.precious() as conn:
        tab = conn.execute(
            "SELECT t.id FROM layout_tabs t JOIN views v ON v.id=t.view_id"
            " WHERE v.legacy_id=? AND t.tab_key='by_order'",
            (pid,),
        ).fetchone()
        conn.execute(
            "INSERT INTO layout_tab_groups(id, tab_id, position, column_name)"
            " VALUES ('g1', ?, 1, 'Salesman')",
            (tab["id"],),
        )
        after_table_write(conn, "layout_tab_groups", "g1")
    row = SavedReportRepository(db).get_any(pid)
    assert row.layout["views"]["by_order"]["group"] == ["Salesman"]


def test_edit_old_layout_json_updates_new_tables(tmp_path):
    db = _db(tmp_path)
    u = UserRepository(db).create("meir@x.com", role="admin", display_name="Meir Grego")
    pid = SavedReportRepository(db).create(
        u.id, "ordered", "Open Orders", {},
        {"views": {"by_order": {"group": []}}})
    with db.precious() as conn:
        conn.execute(
            "UPDATE saved_reports SET layout_json=? WHERE id=?",
            ('{"views":{"by_order":{"group":["Salesman"]}}}', pid),
        )
        after_table_write(conn, "saved_reports", pid)
        vid = conn.execute(
            "SELECT id FROM views WHERE legacy_source='saved_reports' AND legacy_id=?",
            (pid,),
        ).fetchone()["id"]
        assert assemble_layout(conn, vid)["views"]["by_order"]["group"] == ["Salesman"]


def test_repo_read_prefers_new_tables_when_json_is_stale(tmp_path):
    """Live GUI/clock path: assembled tables win over a stale layout_json copy."""
    db = _db(tmp_path)
    u = UserRepository(db).create("meir@x.com", role="admin", display_name="Meir Grego")
    pid = SavedReportRepository(db).create(
        u.id, "ordered", "Open Orders", {},
        {"views": {"by_order": {"group": []}}})
    with db.precious() as conn:
        tab = conn.execute(
            "SELECT t.id FROM layout_tabs t JOIN views v ON v.id=t.view_id"
            " WHERE v.legacy_id=? AND t.tab_key='by_order'",
            (pid,),
        ).fetchone()
        conn.execute(
            "INSERT INTO layout_tab_groups(id, tab_id, position, column_name)"
            " VALUES ('g-live', ?, 1, 'Salesman')",
            (tab["id"],),
        )
        # Leave layout_json as group: [] — do not call after_table_write.
    row = SavedReportRepository(db).get_any(pid)
    assert row.layout["views"]["by_order"]["group"] == ["Salesman"]
    with db.precious() as conn:
        raw = conn.execute(
            "SELECT layout_json FROM saved_reports WHERE id=?", (pid,),
        ).fetchone()["layout_json"]
    assert '"group": []' in raw.replace(" ", "") or '"group":[]' in raw.replace(" ", "")


PERSONAL_ORDERED_VIEW = "Open Orders"
UNGROUPED_BY_ORDER_VIEW = "Ungrouped By Order"
NUMBER_4_VIEW = "YTD"

PERSONAL_ORDERED_LAYOUT = {
    "active": "by_order",
    "order": ["by_order", "full_data"],
    "views": {
        "by_order": {
            "group": ["Salesman"],
            "sorters": [{"column": "SalesOrderNumber", "dir": "asc"}],
            "columnFilters": {"Status": {"op": "contains", "v": "Open"}},
        },
        "full_data": {
            "group": [],
            "hidden": ["LineNumber"],
        },
    },
}

UNGROUPED_BY_ORDER_LAYOUT = {
    "order": ["by_order"],
    "views": {"by_order": {"group": []}},
}

NUMBER_4_LAYOUT = {
    "active": "by_item",
    "order": ["by_item"],
    "views": {
        "by_item": {
            "group": ["Item #"],
            "sorters": [{"column": "Item #", "dir": "asc"}],
        },
    },
}


def _ordered_sp_row(**over):
    row = {
        "SalesOrderNumber": "SO1", "CustomerAccount": "100", "customername": "Acme",
        "SalesGroup": "REdwards", "CreatedDateTime": "2026-03-01T08:30:00",
        "CustomerRequisition": "PO-1001", "purchid": "PO-7788",
        "ExpectedArrivalDate": "2026-03-15T00:00:00",
        "LineNumber": "1", "Item": "ITM-A", "ItemDescription": "Widget",
        "SalesPrice": "2.29", "SalesStatus": "Open order", "QuantityOrdered": "30",
        "QuantityReserved": "5", "CancelledQTY": "0", "ReleasedQuantity": "10",
        "DeliveryRemainder": "20",
        "Ordered $": "68.70", "Shipped $": "22.90", "Cancelled $": "0",
        "Commission": "0.06", "SalesmanName": "Ron Edwards",
    }
    row.update(over)
    return row


def _ordered_payload():
    rows = [
        _ordered_sp_row(),
        _ordered_sp_row(
            SalesOrderNumber="SO2", CreatedDateTime="2026-03-02T08:30:00",
            CustomerRequisition="PO-1002", purchid="", Item="ITM-B",
            ItemDescription="Gadget", SalesPrice="5.00", SalesStatus="Cancelled",
            QuantityOrdered="4", QuantityReserved="0", CancelledQTY="4",
            ReleasedQuantity="0", DeliveryRemainder="0",
            **{"Ordered $": "20.00", "Shipped $": "0", "Cancelled $": "20.00"}),
        _ordered_sp_row(
            SalesOrderNumber="SO3", CustomerAccount="200", customername="BOSCOV'S",
            SalesGroup="AGrossman", CreatedDateTime="2026-03-03T08:30:00",
            Item="ITM-A", SalesmanName="Ari Grossman"),
        _ordered_sp_row(
            SalesOrderNumber="SO4", CustomerAccount="300", customername="MACY'S",
            SalesGroup="AGrossman", CreatedDateTime="2026-03-04T08:30:00",
            Item="ITM-C", ItemDescription="Gizmo", SalesmanName="Ari Grossman"),
        _ordered_sp_row(
            SalesOrderNumber="SO5", CustomerAccount="400", customername="ZEBRA",
            CreatedDateTime="2026-03-05T08:30:00", Item="ITM-A"),
    ]
    return {"report_key": "ordered",
            "tabs": ordered_builder.build(ordered_source.to_facts_ordered_report(rows))}


def _number_4_payload():
    def row(**over):
        base = {
            "Customer #": "100", "Customer Name": "Acme",
            "Item #": "ITM-A", "Item Name": "Widget",
            "Jul-25 Qty": 2, "Jul-25 $": 20,
            "Jun-26 Qty": 1, "Jun-26 $": 10.5,
            "Total Qty": 3, "Total $": 30.5, "Avg Price": 10.17,
            "Book Price": 12.50, "Salesman": "REdwards",
        }
        base.update(over)
        return base
    rows = [
        row(),
        row(**{"Customer #": "200", "Customer Name": "BOSCOV'S",
               "Item #": "ITM-B", "Item Name": "Gadget", "Salesman": "AGrossman"}),
        row(**{"Item #": "ITM-B", "Item Name": "Gadget"}),
    ]
    headers = list(rows[0].keys())
    return {
        "report_key": "number_4",
        "tabs": number4_builder.build(
            by_customer=(headers, [dict(r) for r in rows]),
            by_item=(headers, [dict(r) for r in rows]),
            as_of=date(2026, 8, 25),
        ),
    }


def _sheet_grid(xlsx_bytes: bytes):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=False)
    sheets = []
    for name in wb.sheetnames:
        rows = []
        for row in wb[name].iter_rows(values_only=True):
            vals = list(row)
            while vals and vals[-1] is None:
                vals.pop()
            rows.append(tuple(vals))
        sheets.append((name, tuple(rows)))
    wb.close()
    return tuple(sheets)


def _xlsx(payload, layout):
    shaped = apply_layout(expand_clones(payload, layout), layout)
    return build_workbook(shaped, layout)


def _text(sheets) -> str:
    return " | ".join(
        str(v) for _name, rows in sheets for row in rows for v in row if v is not None)


def test_gate_b_workbooks_match_assembled_views(tmp_path):
    db = _db(tmp_path)
    meir = UserRepository(db).create("meir@x.com", role="admin", display_name="Meir Grego")
    CompanyViewRepository(db).upsert(
        "ordered", DAILY_ORDERED_VIEW, params={}, layout=DAILY_ORDERED_LAYOUT, updated_by=None)
    CompanyViewRepository(db).upsert(
        "ordered", HESHY_OPEN_VIEW,
        params={"period": "yesterday", "salesman": "Hkaufman", "status": "Open order"},
        layout=HESHY_OPEN_LAYOUT, updated_by=None)
    CompanyViewRepository(db).upsert(
        "number_4", NUMBER_4_VIEW, params={"mode": "both", "year": "2026"},
        layout=NUMBER_4_LAYOUT, updated_by=None)
    SavedReportRepository(db).create(
        meir.id, "ordered", PERSONAL_ORDERED_VIEW,
        {"period": "this_week", "status": ["Open order"]}, PERSONAL_ORDERED_LAYOUT)
    SavedReportRepository(db).create(
        meir.id, "ordered", UNGROUPED_BY_ORDER_VIEW, {}, UNGROUPED_BY_ORDER_LAYOUT)

    ordered = _ordered_payload()
    number4 = _number_4_payload()
    cases = [
        (DAILY_ORDERED_VIEW, "company", DAILY_ORDERED_LAYOUT, ordered),
        (HESHY_OPEN_VIEW, "company", HESHY_OPEN_LAYOUT, ordered),
        (PERSONAL_ORDERED_VIEW, "personal", PERSONAL_ORDERED_LAYOUT, ordered),
        (NUMBER_4_VIEW, "company", NUMBER_4_LAYOUT, number4),
        (UNGROUPED_BY_ORDER_VIEW, "personal", UNGROUPED_BY_ORDER_LAYOUT, ordered),
    ]
    with db.precious() as conn:
        for name, kind, old_layout, payload in cases:
            vid = conn.execute(
                "SELECT id FROM views WHERE kind=? AND name=?", (kind, name),
            ).fetchone()["id"]
            assembled = assemble_layout(conn, vid)
            old_sheets = _sheet_grid(_xlsx(payload, old_layout))
            new_sheets = _sheet_grid(_xlsx(payload, assembled))
            assert old_sheets == new_sheets, name
            names = [n for n, _rows in old_sheets]
            blob = _text(old_sheets)
            if name == DAILY_ORDERED_VIEW:
                assert names == [
                    "Summary", "By Customer", "By Item", "By Order",
                    "By Salesman", "Full Data"]
                assert "Salesman: AGrossman" in blob
                assert "Customer Name: BOSCOV'S" in blob
                by_order = next(s for s in old_sheets if s[0] == "By Order")
                assert not any(
                    str(v).startswith("Salesman:") for row in by_order[1] for v in row)
            elif name == HESHY_OPEN_VIEW:
                assert names == ["Full Data"]
                headers = old_sheets[0][1][0]
                assert "LineNumber" not in headers
                assert "SalesOrderNumber" in headers
                assert "SalesOrderNumber: SO1" in blob
            elif name == PERSONAL_ORDERED_VIEW:
                assert names == ["By Order", "Full Data"]
                assert "Salesman: AGrossman" in blob
                by_order = next(s for s in old_sheets if s[0] == "By Order")
                assert not any("SO2" in [str(v) for v in row] for row in by_order[1])
                full = next(s for s in old_sheets if s[0] == "Full Data")
                assert "LineNumber" not in full[1][0]
                assert not any(
                    str(v).startswith("SalesOrderNumber:") for row in full[1] for v in row)
            elif name == NUMBER_4_VIEW:
                assert names == ["By Item (12 Months)"]
                assert "Item #: ITM-A" in blob
            else:
                assert names == ["By Order"]
                assert not any(
                    str(v).startswith("Salesman:") for row in old_sheets[0][1] for v in row)
                assert "Grand total" not in blob


def test_slug_colliding_filters_get_distinct_ids(tmp_path):
    from web.data.normalized_views import _unique_clipped_id, slug

    used: set[str] = set()
    a = _unique_clipped_id(f"v__sm-{slug('A B')}", used)
    b = _unique_clipped_id(f"v__sm-{slug('A-B')}", used)
    assert a != b
    assert a in used and b in used


def test_unique_clipped_id_keeps_suffix_at_max_length():
    from web.data.normalized_views import _ID_MAX, _unique_clipped_id

    used: set[str] = set()
    base = "x" * (_ID_MAX + 20)
    first = _unique_clipped_id(base, used)
    second = _unique_clipped_id(base, used)
    assert len(first) <= _ID_MAX
    assert len(second) <= _ID_MAX
    assert first != second
    assert second.endswith("-2")


def test_deleting_normalized_view_removes_legacy_json(tmp_path):
    from web.data.normalized_views import delete_legacy_for_view_row, project_from_legacy

    db = _db(tmp_path)
    meir = UserRepository(db).create("meir@x.com", role="admin", display_name="Meir Grego")
    saved = SavedReportRepository(db)
    rid = saved.create(
        meir.id, "ordered", "Temp View",
        {"period": "yesterday"},
        {"order": ["by_order"], "views": {"by_order": {"group": []}}},
    )
    project_from_legacy(db)
    with db.precious() as conn:
        view = conn.execute(
            "SELECT * FROM views WHERE legacy_source='saved_reports' AND legacy_id=?",
            (rid,),
        ).fetchone()
        assert view is not None
        conn.execute("DELETE FROM views WHERE id=?", (view["id"],))
        delete_legacy_for_view_row(conn, view)
        assert conn.execute(
            "SELECT 1 FROM saved_reports WHERE id=?", (rid,),
        ).fetchone() is None


def test_missing_group_key_stays_absent_through_assemble(tmp_path):
    """Missing group = builder default; must not become group:[]."""
    from web.data.normalized_views import assemble_layout, canonicalize_layout, project_from_legacy

    raw = {"views": {"summary": {"hidden": ["LineNumber"]}}}
    assert "group" not in canonicalize_layout(raw)["views"]["summary"]
    db = _db(tmp_path)
    meir = UserRepository(db).create("a@x.com", role="admin", display_name="A B")
    ReportDefaultRepository(db).upsert(
        "ordered", params={}, layout=raw, updated_by=meir.id)
    project_from_legacy(db)
    with db.precious() as conn:
        vid = conn.execute(
            "SELECT id FROM views WHERE kind='default' AND report_key='ordered'"
        ).fetchone()["id"]
        tab = conn.execute(
            "SELECT groups_explicit FROM layout_tabs WHERE view_id=? AND tab_key='summary'",
            (vid,),
        ).fetchone()
        assembled = assemble_layout(conn, vid)
    assert tab["groups_explicit"] == 0
    assert "group" not in assembled["views"]["summary"]
    assert assembled["views"]["summary"]["hidden"] == ["LineNumber"]
