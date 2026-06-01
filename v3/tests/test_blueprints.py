"""Route-level tests for the reports/dashboard/settings blueprints.

Drives the real run -> poll -> result -> export flow end-to-end with a fake
Reporting API client and the worker drained inline (no background thread).
"""

from __future__ import annotations

import pytest

from web import create_app
from web.config import Config
from web.data.migrate import migrate
from web.data.repositories.users import UserRepository
from web.reporting.jobs import JOB_TYPE, make_report_run_handler
from web.reporting.report_service import ReportService
from web.reporting.runner import ReportRunner

_CSRF = "test-csrf-token"


class _FakeResult:
    def __init__(self, rows):
        self.rows = rows
        self.columns = list(rows[0].keys()) if rows else []
        self.row_count = len(rows)


class _FakeClient:
    def __init__(self, rows_by_report, configured=False):
        self.rows_by_report = rows_by_report
        self.configured = configured

    def run_report(self, report_id, params):
        return _FakeResult(self.rows_by_report.get(report_id, []))


class _FakeSalesmen:
    def all_as_facts(self):
        return {}


def _cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True,
        outbox_dir=tmp_path / "outbox",
    )


def _make_app(tmp_path, rows_by_report=None):
    app = create_app(_cfg(tmp_path))
    migrate(app.config["DB"])
    if rows_by_report is not None:
        # Swap in a fake-backed service + re-register the worker handlers (run +
        # deliver) so the inline drain uses the fake data.
        from web.data.repositories.outbox import OutboxRepository
        from web.delivery.email import EmailService
        from web.delivery.jobs import DELIVERY_JOB_TYPE, make_delivery_handler
        from web.delivery.service import DeliveryService

        service = ReportService(_FakeClient(rows_by_report), _FakeSalesmen())
        app.config["REPORT_SERVICE"] = service
        runner = ReportRunner(app.config["REPORT_CACHE"])
        worker = app.config["JOB_WORKER"]
        worker.register(JOB_TYPE, make_report_run_handler(runner, service.builder_for))
        email = EmailService(app.config["APP_CONFIG"], OutboxRepository(app.config["DB"]),
                             app.config["SHAREPOINT_SERVICE"])
        delivery = DeliveryService(runner, service.builder_for, email)
        app.config["DELIVERY_SERVICE"] = delivery
        worker.register(DELIVERY_JOB_TYPE, make_delivery_handler(delivery))
    return app


def _login(client, app, *, email="admin@x.com", role="admin"):
    UserRepository(app.config["DB"]).upsert(email, display_name="Admin", role=role)
    with client.session_transaction() as s:
        s["v3_user"] = {"email": email, "name": "Admin", "role": role, "is_dev": True}
        s["_csrf_token"] = _CSRF


def test_reports_list_requires_login(tmp_path):
    app = _make_app(tmp_path)
    resp = app.test_client().get("/")
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers["Location"]


def test_reports_list_shows_built_reports_for_admin(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/").get_data(as_text=True)
    assert "Ordered" in html and "Invoiced" in html and "Customer Activity" in html
    assert "Coming soon" in html  # backlog section


def test_salesman_with_no_grants_sees_no_reports(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    html = client.get("/").get_data(as_text=True)
    assert "don't have access" in html


def test_report_view_renders_filters(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/reports/ordered").get_data(as_text=True)
    assert 'id="runBtn"' in html
    assert 'name="period"' in html  # ordered exposes a period filter


def test_run_poll_result_export_flow(tmp_path):
    rows = {
        "salesline_release": [
            {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
             "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
             "SalesStatus": "Open", "OrderDate": "2026-03-01"},
        ]
    }
    app = _make_app(tmp_path, rows_by_report=rows)
    client = app.test_client()
    _login(client, app)

    run = client.post("/api/reports/ordered/run", json={"period": "all_time"},
                      headers={"X-CSRF-Token": _CSRF})
    assert run.status_code == 202
    job_id = run.get_json()["job_id"]

    status = client.get(f"/api/jobs/{job_id}").get_json()
    assert status["status"] == "success"

    payload = client.get(f"/api/reports/result/{job_id}").get_json()
    assert payload["report_key"] == "ordered"
    assert any(t["rows"] for t in payload["tabs"])

    xlsx = client.get(f"/reports/ordered/export/{job_id}")
    assert xlsx.status_code == 200
    assert xlsx.data[:2] == b"PK"  # xlsx is a zip


def test_run_requires_csrf(tmp_path):
    app = _make_app(tmp_path, rows_by_report={})
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/reports/ordered/run", json={})
    assert resp.status_code == 400  # missing CSRF header


def test_cannot_read_another_users_job(tmp_path):
    app = _make_app(tmp_path, rows_by_report={"salesline_release": []})
    client = app.test_client()
    _login(client, app)
    job_id = client.post("/api/reports/ordered/run", json={},
                         headers={"X-CSRF-Token": _CSRF}).get_json()["job_id"]

    other = app.test_client()
    _login(other, app, email="other@x.com", role="admin")
    assert other.get(f"/api/jobs/{job_id}").status_code == 404


def test_settings_theme_toggle(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/settings/theme", data={"theme": "dark", "csrf_token": _CSRF})
    assert resp.status_code in (301, 302)
    with client.session_transaction() as s:
        assert s["theme"] == "dark"


def test_dashboard_forbidden_for_salesman(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    assert client.get("/dashboard").status_code == 403


def test_dashboard_renders_for_admin(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Built reports" in html


def test_settings_renders_for_admin(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/settings").get_data(as_text=True)
    assert "Appearance" in html and "Profile" in html


def test_granted_non_privileged_user_cannot_run_report(tmp_path):
    """A manager with an explicit report grant may VIEW the report in the list
    but must NOT be able to run it (scope enforcement pending; fail closed)."""
    app = _make_app(tmp_path, rows_by_report={"salesline_release": []})
    db = app.config["DB"]
    user = UserRepository(db).upsert("mgr@x.com", display_name="Mgr", role="manager")
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO user_report_access(user_id, report_key, allowed) VALUES (?, 'ordered', 1)",
            (user.id,),
        )
    client = app.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "mgr@x.com", "name": "Mgr", "role": "manager", "is_dev": True}
        s["_csrf_token"] = _CSRF
    # Visible in the list...
    assert "Ordered" in client.get("/").get_data(as_text=True)
    # ...but cannot run / view it.
    assert client.get("/reports/ordered").status_code == 403
    assert client.post("/api/reports/ordered/run", json={},
                       headers={"X-CSRF-Token": _CSRF}).status_code == 403


def test_revoked_access_blocks_result_read(tmp_path):
    app = _make_app(tmp_path, rows_by_report={"salesline_release": []})
    client = app.test_client()
    _login(client, app)
    job_id = client.post("/api/reports/ordered/run", json={},
                         headers={"X-CSRF-Token": _CSRF}).get_json()["job_id"]
    # Demote the admin to salesman (fail-closed) and confirm the cached result is denied.
    db = app.config["DB"]
    with db.precious() as conn:
        conn.execute("UPDATE users SET role='salesman' WHERE email='admin@x.com'")
    assert client.get(f"/api/reports/result/{job_id}").status_code == 403


def test_report_view_renders_status_and_customer_filters(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/reports/ordered").get_data(as_text=True)
    assert 'id="statusSelect"' in html      # Ordered status filter
    assert 'id="customerPicker"' in html    # searchable customer multi-select
    assert 'id="salesmanSelect"' in html


def _with_lookups(app, rows):
    """Replace the app's LookupService with one over a configured fake client
    that returns `rows` for customer_master, and populate it synchronously."""
    from web.reporting.lookups import LookupService

    service = ReportService(_FakeClient({"customer_master": rows}, configured=True),
                            _FakeSalesmen())
    lookup = LookupService(service, _FakeSalesmen())
    lookup._populate()  # synchronous fetch so the endpoints are deterministic
    app.config["LOOKUP_SERVICE"] = lookup


def test_salesmen_and_customers_lookups(tmp_path):
    rows = [
        {"CustomerAccount": "100", "CustomerName": "Acme", "SalesGroup": "REdwards"},
        {"CustomerAccount": "200", "CustomerName": "Globex", "SalesGroup": "JSmith"},
        {"CustomerAccount": "300", "CustomerName": "Initech", "SalesGroup": "REdwards"},
    ]
    app = _make_app(tmp_path)
    _with_lookups(app, rows)
    client = app.test_client()
    _login(client, app)

    sm = client.get("/api/reports/ordered/salesmen").get_json()["salesmen"]
    assert {r["key"] for r in sm} == {"REdwards", "JSmith"}

    all_cust = client.get("/api/reports/ordered/customers").get_json()["customers"]
    assert {c["key"] for c in all_cust} == {"100", "200", "300"}

    one = client.get("/api/reports/ordered/customers?salesman=REdwards").get_json()["customers"]
    assert {c["key"] for c in one} == {"100", "300"}


def test_lookup_status_endpoint(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    status = client.get("/api/reports/lookups/status").get_json()
    assert "configured" in status and "status" in status


def test_preview_body_shows_sp_params(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/reports/ordered/preview-body",
                       json={"period": "ytd", "salesman": "REdwards"},
                       headers={"X-CSRF-Token": _CSRF})
    body = resp.get_json()
    assert body["report_id"] == "salesline_release"
    assert body["body"]["SalesGroup"] == "REdwards"
    assert "CreatedDateTimeFrom" in body["body"]


def test_preset_create_list_get_delete_and_home(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)

    # Create
    created = client.post("/api/reports/ordered/presets",
                          json={"name": "March", "params": {"period": "mtd"},
                                "layout": {"active": "summary", "views": {}}},
                          headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    pid = created.get_json()["id"]

    # List for the report
    lst = client.get("/api/reports/ordered/presets").get_json()["presets"]
    assert len(lst) == 1 and lst[0]["name"] == "March"

    # Single fetch carries the layout
    one = client.get(f"/api/reports/presets/{pid}").get_json()
    assert one["layout"]["active"] == "summary"

    # Cross-report list (My Presets) + home page shows it
    allp = client.get("/api/saved-reports").get_json()["presets"]
    assert any(p["id"] == pid for p in allp)
    assert "My presets" in client.get("/").get_data(as_text=True)
    assert "March" in client.get("/").get_data(as_text=True)

    # Delete
    assert client.delete(f"/api/reports/presets/{pid}",
                         headers={"X-CSRF-Token": _CSRF}).status_code == 200
    assert client.get("/api/reports/ordered/presets").get_json()["presets"] == []


def test_preset_is_owner_scoped(tmp_path):
    app = _make_app(tmp_path)
    owner = app.test_client()
    _login(owner, app)
    pid = owner.post("/api/reports/ordered/presets",
                     json={"name": "mine", "params": {}, "layout": {}},
                     headers={"X-CSRF-Token": _CSRF}).get_json()["id"]
    other = app.test_client()
    _login(other, app, email="other@x.com", role="admin")
    assert other.get(f"/api/reports/presets/{pid}").status_code == 404
    assert other.delete(f"/api/reports/presets/{pid}",
                        headers={"X-CSRF-Token": _CSRF}).status_code == 404


def test_preset_requires_name(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/reports/ordered/presets", json={"params": {}},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 400


def test_email_now_enqueues_and_delivers(tmp_path):
    rows = {"salesline_release": [
        {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
         "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
         "SalesStatus": "Open", "OrderDate": "2026-03-01"},
    ]}
    app = _make_app(tmp_path, rows_by_report=rows)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/reports/ordered/email-now",
                       json={"recipients": "a@x.com", "subject": "Ordered",
                             "params": {"period": "all_time"}, "layout": {}},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 202
    job_id = resp.get_json()["job_id"]
    status = client.get(f"/api/jobs/{job_id}").get_json()
    assert status["status"] == "success"
    # an outbox row + .eml artifact were produced
    from web.data.repositories.outbox import OutboxRepository
    assert OutboxRepository(app.config["DB"]).list_recent()
    assert list((tmp_path / "outbox").glob("*.eml"))


def test_email_now_rejects_no_target(tmp_path):
    app = _make_app(tmp_path, rows_by_report={"salesline_release": []})
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/reports/ordered/email-now",
                       json={"recipients": "not-an-email", "params": {}},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 400


def test_sharepoint_status_and_folders_mock(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)  # admin -> has sharepoint access
    st = client.get("/api/sharepoint/status").get_json()
    assert st["enabled"] is True and st["configured"] is False
    folders = client.get("/api/sharepoint/folders?path=").get_json()["folders"]
    assert any(f["name"] == "Ordered" for f in folders)


def test_sharepoint_folders_forbidden_for_salesman(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    assert client.get("/api/sharepoint/folders").status_code == 403


def test_invoiced_commissions_tab_is_not_blank(tmp_path):
    rows = [
        {"InvoiceNumber": "INV1", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-03-01", "SubTotal": "100", "SH_TariffCharges": "0",
         "FreightCharges": "0", "CCSurcharge": "0", "SalesGroup": "REdwards"},
    ]
    app = _make_app(tmp_path, rows_by_report={"invoiced_order_charges": rows})
    client = app.test_client()
    _login(client, app)
    job_id = client.post("/api/reports/invoiced/run", json={"year": "2026"},
                         headers={"X-CSRF-Token": _CSRF}).get_json()["job_id"]
    payload = client.get(f"/api/reports/result/{job_id}").get_json()
    comm = next(t for t in payload["tabs"] if t["key"] == "commissions")
    assert comm["columns"] and comm["rows"]  # renders as a real table, not blank
