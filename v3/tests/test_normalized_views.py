"""Normalized views tables: handles, Gate A round-trip, foreign keys."""

import sqlite3

import pytest

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.normalized_views import (
    assemble_layout,
    assemble_params,
    canonicalize_layout,
    canonicalize_params,
    company_view_id,
    project_from_legacy,
    suggest_handle,
)
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
