"""Warehouse dashboard: open-status filters, UTC→ET stamps, routes + sample totals."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from web import create_app
from web.config import Config
from web.data.migrate import migrate
from web.data.repositories.users import UserRepository
from web.warehouse.filters import (
    filter_open_rows,
    is_open_cluster,
    is_open_load,
    is_open_shipment,
    is_open_wave,
    is_open_work,
)
from web.warehouse.sample import SampleWarehouseProvider
from web.warehouse.timeutil import parse_utc_timestamp, utc_to_eastern_display


def test_open_shipment_excludes_shipped():
    assert is_open_shipment("Open")
    assert is_open_shipment("Waved")
    assert not is_open_shipment("Shipped")
    assert not is_open_shipment("shipped")


def test_open_load_excludes_shipped():
    assert is_open_load("Loaded")
    assert not is_open_load("Shipped")


def test_open_work_excludes_closed_and_cancelled():
    assert is_open_work("Open")
    assert is_open_work("InProcess")
    assert not is_open_work("Closed")
    assert not is_open_work("Cancelled")
    assert not is_open_work("Canceled")


def test_open_cluster_excludes_closed():
    assert is_open_cluster("Open")
    assert is_open_cluster("Passed")
    assert is_open_cluster("InProcess")
    assert not is_open_cluster("Closed")


def test_open_wave_excludes_picked_and_shipped():
    assert is_open_wave("Open")
    assert not is_open_wave("Picked")
    assert not is_open_wave("Shipped")


def test_filter_open_rows_work():
    rows = [
        {"WorkStatus": "Open", "WorkId": "1"},
        {"WorkStatus": "Closed", "WorkId": "2"},
        {"WorkStatus": "Cancelled", "WorkId": "3"},
        {"WorkStatus": "InProcess", "WorkId": "4"},
    ]
    open_rows = filter_open_rows("work", rows)
    assert [r["WorkId"] for r in open_rows] == ["1", "4"]


def test_utc_refresh_stamp_converts_to_eastern():
    # 2026-11-11 20:13:03 UTC → 15:13 EST (EDT ended Nov 1 2026 → EST).
    display = utc_to_eastern_display("2026-11-11T20:13:03Z")
    assert display is not None
    assert display.startswith("2026-11-11 15:13")
    assert "EST" in display or "EDT" in display


def test_parse_utc_naive_treated_as_utc():
    dt = parse_utc_timestamp("2026-11-11 20:13:03")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.astimezone(timezone.utc).hour == 20


def test_sample_provider_matches_nov11_totals():
    prov = SampleWarehouseProvider()
    assert len(prov.get_open_shipments()) == 642
    assert len(prov.get_open_loads()) == 608
    assert len(prov.get_open_work()) == 729
    assert len(prov.get_open_clusters()) == 111
    summary = prov.tile_summary()
    by_key = {t["key"]: t for t in summary["tiles"]}
    assert by_key["shipments"]["by_status"] == {
        "Waved": 311, "InProcess": 292, "Open": 34, "Loaded": 5,
    }
    assert by_key["waves"]["coming_soon"] is True
    assert by_key["due_dates"]["coming_soon"] is True
    assert "sample" in summary["data_as_of"].lower() or "2026-11-11" in summary["data_as_of"]


def _cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True,
        outbox_dir=tmp_path / "outbox",
        wh_dashboard_provider="sample",
    )


def _login(client, app, *, email="admin@x.com", role="admin"):
    UserRepository(app.config["DB"]).upsert(email, display_name="Admin", role=role)
    with client.session_transaction() as s:
        s["v3_user"] = {
            "email": email, "name": "Admin", "role": role, "is_dev": False,
        }


def test_wh_dashboard_admin_ok(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    client = app.test_client()
    _login(client, app, role="admin")
    resp = client.get("/WHdashboard")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Warehouse Dashboard" in body
    assert "Shipments" in body
    assert "Coming soon" in body
    assert "642" in body


def test_wh_dashboard_salesman_forbidden(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    resp = client.get("/WHdashboard")
    assert resp.status_code == 403


def test_wh_list_shipments(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    client = app.test_client()
    _login(client, app, role="admin")
    resp = client.get("/WHdashboard/shipments")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "642 open" in body
    assert "SHP-DEMO-" in body
    assert "whSearch" in body


def test_wh_list_waves_coming_soon_404(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    client = app.test_client()
    _login(client, app, role="admin")
    assert client.get("/WHdashboard/waves").status_code == 404
