"""Warehouse dashboard: open-status filters, UTC→ET stamps, allowlist routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Any

from web import create_app
from web.config import Config
from web.data.migrate import migrate
from web.data.repositories.users import UserRepository
from web.warehouse.access import (
    DEFAULT_ALLOWED_EMAILS,
    email_may_access_wh_dashboard,
    parse_allowed_emails,
)
from web.warehouse.filters import (
    filter_open_rows,
    is_open_cluster,
    is_open_load,
    is_open_shipment,
    is_open_wave,
    is_open_work,
)
from web.warehouse.filters import row_is_not_deleted
from web.warehouse.reporting_api import ReportingApiWarehouseProvider, row_is_achm
from web.warehouse.sample import SampleWarehouseProvider
from web.warehouse.schema import (
    BROAD_FETCH_AREAS,
    OPEN_STATUS_FETCH,
    REPORT_IDS,
    STATUS_COLUMNS,
)
from web.warehouse.timeutil import parse_utc_timestamp, utc_to_eastern_display

_ALLOWED = "bgrossman@achimonline.com"


@dataclass
class _FakeResult:
    report_id: str
    columns: list[str]
    rows: list[dict]
    row_count: int


class _FakeReportClient:
    """Records run_report calls; returns configured rows per (report_id, status)."""

    def __init__(self, by_key: dict[tuple[str, str], list[dict]] | None = None,
                 *, fail: Exception | None = None,
                 row_count_override: dict[tuple[str, str], int] | None = None):
        self.by_key = by_key or {}
        self.fail = fail
        self.row_count_override = row_count_override or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run_report(self, report_id: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((report_id, dict(params)))
        if self.fail is not None:
            raise self.fail
        status = None
        for key, val in params.items():
            if key.endswith("Status"):
                status = val
                break
        rows = list(self.by_key.get((report_id, status), []))
        count = self.row_count_override.get((report_id, status), len(rows))
        return _FakeResult(report_id, [], rows, count)


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


def test_open_wave_excludes_shipped_only():
    assert is_open_wave("Created")
    assert is_open_wave("Released")
    assert is_open_wave("Held")
    assert is_open_wave("Picked")  # not Shipped → open per Nov 19 rule
    assert not is_open_wave("Shipped")
    assert not is_open_wave("shipped")


def test_row_is_not_deleted():
    assert row_is_not_deleted({"IsDeleted": 0})
    assert row_is_not_deleted({"IsDeleted": "0"})
    assert row_is_not_deleted({})
    assert not row_is_not_deleted({"IsDeleted": 1})
    assert not row_is_not_deleted({"IsDeleted": "1"})


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
    display = utc_to_eastern_display("2026-11-11T20:13:03Z")
    assert display is not None
    assert display == "2026-11-11 15:13 ET"


def test_rfc822_gmt_refresh_stamp_converts_to_eastern():
    display = utc_to_eastern_display("Thu, 05 Nov 2026 09:34:36 GMT")
    assert display == "2026-11-05 04:34 ET"


def test_parse_utc_naive_treated_as_utc():
    dt = parse_utc_timestamp("2026-11-11 20:13:03")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.astimezone(timezone.utc).hour == 20


def test_row_is_achm_company_or_data_area():
    assert row_is_achm({"Company": "achm"})
    assert row_is_achm({"dataAreaId": "ACHM"})
    assert not row_is_achm({"Company": "DEMO"})
    assert not row_is_achm({})


def test_sample_provider_matches_nov11_totals():
    prov = SampleWarehouseProvider()
    assert len(prov.get_open_shipments()) == 642
    assert len(prov.get_open_loads()) == 608
    assert len(prov.get_open_work()) == 729
    assert len(prov.get_open_clusters()) == 111
    assert len(prov.get_open_waves()) == 60
    summary = prov.tile_summary()
    by_key = {t["key"]: t for t in summary["tiles"]}
    assert by_key["shipments"]["by_status"] == {
        "Waved": 311, "InProcess": 292, "Open": 34, "Loaded": 5,
    }
    assert by_key["waves"]["coming_soon"] is False
    assert by_key["waves"]["by_status"] == {
        "Released": 40, "Created": 18, "Held": 2,
    }
    assert by_key["due_dates"]["coming_soon"] is True
    assert "2026-11-11" in summary["data_as_of"]


def test_parse_allowed_emails_default_and_casefold():
    assert parse_allowed_emails(None) == frozenset(DEFAULT_ALLOWED_EMAILS)
    assert parse_allowed_emails("") == frozenset(DEFAULT_ALLOWED_EMAILS)
    assert parse_allowed_emails("  A@X.com , b@y.com ") == frozenset({"a@x.com", "b@y.com"})
    assert email_may_access_wh_dashboard("BGROSSMAN@achimonline.com", DEFAULT_ALLOWED_EMAILS)
    assert not email_may_access_wh_dashboard("admin@x.com", DEFAULT_ALLOWED_EMAILS)


def _cfg(tmp_path, *, allowed=_ALLOWED) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True,
        outbox_dir=tmp_path / "outbox",
        wh_dashboard_provider="sample",
        wh_dashboard_allowed_emails=(allowed,),
    )


def _login(client, app, *, email=_ALLOWED, role="salesman"):
    UserRepository(app.config["DB"]).upsert(email, display_name=email, role=role)
    with client.session_transaction() as s:
        s["v3_user"] = {
            "email": email, "name": email, "role": role, "is_dev": False,
        }


def test_wh_dashboard_allowlisted_ok(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    client = app.test_client()
    _login(client, app, email=_ALLOWED, role="salesman")
    for path in ("/whdashboard", "/WHdashboard"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        body = resp.get_data(as_text=True)
        assert "Warehouse Dashboard" in body
        assert "642" in body


def test_wh_dashboard_admin_not_on_list_forbidden(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    client = app.test_client()
    _login(client, app, email="admin@x.com", role="admin")
    assert client.get("/whdashboard").status_code == 403
    assert client.get("/WHdashboard").status_code == 403


def test_wh_dashboard_other_user_forbidden(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    assert client.get("/whdashboard").status_code == 403


def test_wh_list_shipments_allowlisted(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    client = app.test_client()
    _login(client, app, email="BGrossman@AchimOnline.com")
    resp = client.get("/whdashboard/shipments")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "642 open" in body
    assert "SHP-DEMO-" in body
    assert client.get("/WHdashboard/shipments").status_code == 200


def test_wh_list_waves_allowlisted(tmp_path):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    client = app.test_client()
    _login(client, app)
    resp = client.get("/whdashboard/waves")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "60 open" in body
    assert "WV-DEMO-" in body
    assert client.get("/whdashboard/due_dates").status_code == 404


def _achm_row(area: str, status: str, rid: int, **extra) -> dict:
    status_col = STATUS_COLUMNS[area]
    row = {status_col: status, "RecId": rid, "UpdatedUtc": "Thu, 05 Nov 2026 09:34:36 GMT"}
    if area == "shipments":
        row["Company"] = "achm"
        row["ShipmentId"] = f"SHP-{rid}"
    else:
        row["dataAreaId"] = "achm"
        if area == "loads":
            row["LoadId"] = f"LD-{rid}"
            row["LastSeenUtc"] = "Thu, 05 Nov 2026 10:00:00 GMT"
        elif area == "work":
            row["WorkId"] = f"WRK-{rid}"
            row["LastImportedUTC"] = "Thu, 05 Nov 2026 11:00:00 GMT"
        elif area == "waves":
            row["WaveId"] = f"WV-{rid}"
            row["IsDeleted"] = 0
            row["LastSeenUtc"] = "Thu, 05 Nov 2026 13:00:00 GMT"
        else:
            row["ClusterId"] = f"CL-{rid}"
            row["LastSeenUtc"] = "Thu, 05 Nov 2026 12:00:00 GMT"
    row.update(extra)
    return row


def _seed_empty_status_keys(by_key: dict) -> None:
    for area, statuses in OPEN_STATUS_FETCH.items():
        for status in statuses:
            by_key.setdefault((REPORT_IDS[area], status), [])
        if area in BROAD_FETCH_AREAS:
            by_key.setdefault((REPORT_IDS[area], None), [])


def test_reporting_api_provider_fetches_per_status_and_filters():
    by_key: dict[tuple[str, str], list[dict]] = {}
    # Shipments: mix achm open, demo, and shipped (shipped must drop client-side).
    by_key[(REPORT_IDS["shipments"], "Waved")] = [
        _achm_row("shipments", "Waved", 1),
        {"ShipmentStatus": "Waved", "Company": "DEMO", "RecId": 2, "ShipmentId": "X"},
        _achm_row("shipments", "Shipped", 3),  # if API ignores filter
    ]
    by_key[(REPORT_IDS["shipments"], "Open")] = [
        _achm_row("shipments", "Open", 4),
    ]
    for status in OPEN_STATUS_FETCH["loads"]:
        by_key[(REPORT_IDS["loads"], status)] = [
            _achm_row("loads", status, 10 + hash(status) % 50),
        ]
    for status in OPEN_STATUS_FETCH["work"]:
        by_key[(REPORT_IDS["work"], status)] = [
            _achm_row("work", status, 20 + hash(status) % 50),
        ]
    for status in OPEN_STATUS_FETCH["clusters"]:
        by_key[(REPORT_IDS["clusters"], status)] = [
            _achm_row("clusters", status, 30 + hash(status) % 50),
        ]
    for status in OPEN_STATUS_FETCH["waves"]:
        by_key[(REPORT_IDS["waves"], status)] = [
            _achm_row("waves", status, 40 + hash(status) % 50),
        ]
    by_key[(REPORT_IDS["waves"], None)] = []

    client = _FakeReportClient(by_key)
    prov = ReportingApiWarehouseProvider(client, cache_seconds=60)
    ships = prov.get_open_shipments()
    assert {r["RecId"] for r in ships} == {1, 4}
    assert all(row_is_achm(r) for r in ships)

    # One call per known open status per area, plus broad MaxRows for waves.
    expected_calls = (
        sum(len(v) for v in OPEN_STATUS_FETCH.values()) + len(BROAD_FETCH_AREAS)
    )
    assert len(client.calls) == expected_calls
    for report_id, params in client.calls:
        assert params["MaxRows"] == "10000"

    summary = prov.tile_summary()
    assert summary["provider"] == "reporting_api"
    assert summary["using_sample_fallback"] is False
    assert summary["possibly_truncated"] is False
    assert summary["data_as_of"].endswith(" ET")
    # Newest stamp is waves 13:00 GMT → 08:00 ET
    assert "08:00 ET" in summary["data_as_of"] or "2026-11-05" in summary["data_as_of"]
    by_key_tiles = {t["key"]: t for t in summary["tiles"]}
    assert by_key_tiles["waves"]["coming_soon"] is False
    assert by_key_tiles["due_dates"]["coming_soon"] is True


def test_reporting_api_provider_truncation_warning():
    by_key = {
        (REPORT_IDS["shipments"], "Open"): [
            _achm_row("shipments", "Open", i) for i in range(3)
        ],
    }
    _seed_empty_status_keys(by_key)
    override = {(REPORT_IDS["shipments"], "Open"): 10000}
    client = _FakeReportClient(by_key, row_count_override=override)
    prov = ReportingApiWarehouseProvider(client, cache_seconds=60)
    summary = prov.tile_summary()
    assert summary["possibly_truncated"] is True
    assert "shipments" in summary["truncated_areas"]
    by_key_tiles = {t["key"]: t for t in summary["tiles"]}
    assert by_key_tiles["shipments"]["possibly_truncated"] is True


def test_reporting_api_provider_falls_back_to_sample_on_error():
    client = _FakeReportClient(fail=RuntimeError("boom from API"))
    prov = ReportingApiWarehouseProvider(client, cache_seconds=60)
    summary = prov.tile_summary()
    assert summary["using_sample_fallback"] is True
    assert summary["provider"] == "sample"
    assert "boom from API" in (summary["error_message"] or "")
    assert len(prov.get_open_shipments()) == 642
    assert len(prov.get_open_waves()) == 60


def test_reporting_api_provider_cache_avoids_repeat_calls():
    by_key = {}
    for area, statuses in OPEN_STATUS_FETCH.items():
        for status in statuses:
            by_key[(REPORT_IDS[area], status)] = [
                _achm_row(area, status, 1),
            ]
        if area in BROAD_FETCH_AREAS:
            by_key[(REPORT_IDS[area], None)] = []
    client = _FakeReportClient(by_key)
    prov = ReportingApiWarehouseProvider(client, cache_seconds=300)
    prov.get_open_shipments()
    first = len(client.calls)
    prov.get_open_loads()
    prov.get_open_waves()
    prov.tile_summary()
    assert len(client.calls) == first


def test_reporting_api_waves_filters_deleted_and_flags_unknown_status():
    by_key: dict[tuple[str, str | None], list[dict]] = {}
    _seed_empty_status_keys(by_key)
    by_key[(REPORT_IDS["waves"], "Created")] = [
        _achm_row("waves", "Created", 1),
        _achm_row("waves", "Created", 2, IsDeleted=1),
    ]
    # Broad pull surfaces an open status not in OPEN_STATUS_FETCH / known set.
    by_key[(REPORT_IDS["waves"], None)] = [
        _achm_row("waves", "Executing", 3),
        _achm_row("waves", "Shipped", 4),
    ]
    client = _FakeReportClient(by_key)
    prov = ReportingApiWarehouseProvider(client, cache_seconds=60)
    waves = prov.get_open_waves()
    assert {r["RecId"] for r in waves} == {1, 3}
    summary = prov.tile_summary()
    assert summary["unrecognized_statuses"]["waves"] == ["Executing"]
