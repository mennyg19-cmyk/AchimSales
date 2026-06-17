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
        # Fresh list per call, like the real client (which json-parses new rows
        # each time); the adapters consume the list to save memory on big runs.
        return _FakeResult(list(self.rows_by_report.get(report_id, [])))


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
        worker.register(JOB_TYPE, make_report_run_handler(
            runner, service.builder_for, app.config["RUN_LOG_REPO"]))
        email = EmailService(app.config["APP_CONFIG"], OutboxRepository(app.config["DB"]),
                             app.config["SHAREPOINT_SERVICE"])
        delivery = DeliveryService(runner, service.builder_for, email)
        app.config["DELIVERY_SERVICE"] = delivery
        worker.register(DELIVERY_JOB_TYPE, make_delivery_handler(delivery, app.config["AUTHZ"]))

        from web.data.repositories.schedules import (
            MasterScheduleRepository, ScheduleRepository, ScheduleRunRepository)
        from web.data.repositories.users import UserRepository as _UR
        from web.scheduling.jobs import SCHEDULE_RUN_JOB_TYPE, make_schedule_run_handler
        from web.scheduling.runner import ScheduleRunner

        db = app.config["DB"]
        sched_runner = ScheduleRunner(
            schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
            run_repo=ScheduleRunRepository(db), user_repo=_UR(db),
            authz=app.config["AUTHZ"], delivery=delivery)
        app.config["SCHEDULE_RUNNER"] = sched_runner
        worker.register(SCHEDULE_RUN_JOB_TYPE, make_schedule_run_handler(sched_runner))
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


def test_salesman_inherit_shows_salesman_default_reports(tmp_path):
    """With no per-user overrides ('inherit'), a salesman sees the salesman-filter
    reports by default (legacy parity) but not the non-default ones."""
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    html = client.get("/").get_data(as_text=True)
    assert "Ordered" in html and "Invoiced" in html and "Customer Activity" in html
    assert "Number 4" not in html  # non-salesman-default: inherit-hidden until allowed


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

    # Export is now a BACKGROUND job: POST kicks it off, the worker builds it
    # (drained inline in tests), then we download the stored blob.
    exp = client.post(f"/api/reports/ordered/export/{job_id}", json={},
                      headers={"X-CSRF-Token": _CSRF})
    assert exp.status_code == 202
    export_id = exp.get_json()["export_id"]

    st = client.get(f"/api/jobs/{export_id}").get_json()
    assert st["status"] == "success"

    listing = client.get("/api/reports/exports").get_json()["exports"]
    assert any(e["export_id"] == export_id and e["ready"] for e in listing)

    xlsx = client.get(f"/api/reports/exports/{export_id}/download")
    assert xlsx.status_code == 200
    assert xlsx.data[:2] == b"PK"  # xlsx is a zip

    # A different user must not be able to download someone else's export.
    _login(client, app, email="other@x.com", role="admin")
    assert client.get(f"/api/reports/exports/{export_id}/download").status_code == 404
    assert all(e["export_id"] != export_id
               for e in client.get("/api/reports/exports").get_json()["exports"])


def test_run_log_records_and_renders(tmp_path):
    rows = {"salesline_release": [
        {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
         "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
         "SalesStatus": "Open", "OrderDate": "2026-03-01"}]}
    app = _make_app(tmp_path, rows_by_report=rows)
    client = app.test_client()
    _login(client, app)
    run = client.post("/api/reports/ordered/run", json={"period": "all_time"},
                      headers={"X-CSRF-Token": _CSRF})
    assert client.get(f"/api/jobs/{run.get_json()['job_id']}").get_json()["status"] == "success"

    page = client.get("/admin/run-log").get_data(as_text=True)
    assert "ordered" in page and "success" in page


def test_run_log_forbidden_for_salesman(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    assert client.get("/admin/run-log").status_code == 403


def _seed_salesman(app, key="redwards", number="42"):
    with app.config["DB"].precious() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO salesmen(key, number, display_name, is_active)"
            " VALUES (?, ?, ?, 1)", (key, number, "R Edwards"))


def test_admin_user_crud_and_scope(tmp_path):
    app = _make_app(tmp_path)
    _seed_salesman(app)
    client = app.test_client()
    _login(client, app)  # admin

    created = client.post("/api/admin/users", json={"email": "new@x.com", "role": "salesman"},
                          headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    uid = created.get_json()["id"]

    upd = client.put(f"/api/admin/users/{uid}", json={"role": "manager", "dashboard_enabled": True},
                     headers={"X-CSRF-Token": _CSRF})
    assert upd.status_code == 200 and upd.get_json()["role"] == "manager"
    assert upd.get_json()["dashboard_enabled"] is True

    scope = client.post(f"/api/admin/users/{uid}/salesman-access", json={"keys": ["redwards"]},
                        headers={"X-CSRF-Token": _CSRF})
    assert scope.get_json()["keys"] == ["redwards"]

    deleted = client.delete(f"/api/admin/users/{uid}", headers={"X-CSRF-Token": _CSRF})
    assert deleted.status_code == 200


def test_admin_report_access_tristate(tmp_path):
    """The per-report override API is tri-state: inherit (clears the row), allow,
    deny. GET returns only the explicit overrides; inherit keys are absent."""
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)  # admin
    created = client.post("/api/admin/users", json={"email": "rep@x.com", "role": "salesman"},
                          headers={"X-CSRF-Token": _CSRF})
    uid = created.get_json()["id"]

    # allow + deny
    client.post(f"/api/admin/users/{uid}/report-access",
                json={"report_key": "salesman", "access": "allow"}, headers={"X-CSRF-Token": _CSRF})
    client.post(f"/api/admin/users/{uid}/report-access",
                json={"report_key": "number_4", "access": "deny"}, headers={"X-CSRF-Token": _CSRF})
    access = client.get(f"/api/admin/users/{uid}/report-access").get_json()["access"]
    assert access == {"salesman": "allow", "number_4": "deny"}

    # inherit clears the row
    client.post(f"/api/admin/users/{uid}/report-access",
                json={"report_key": "salesman", "access": "inherit"}, headers={"X-CSRF-Token": _CSRF})
    access = client.get(f"/api/admin/users/{uid}/report-access").get_json()["access"]
    assert access == {"number_4": "deny"}

    # back-compat: bare {allowed: true} still maps to allow
    client.post(f"/api/admin/users/{uid}/report-access",
                json={"report_key": "ordered", "allowed": True}, headers={"X-CSRF-Token": _CSRF})
    access = client.get(f"/api/admin/users/{uid}/report-access").get_json()["access"]
    assert access["ordered"] == "allow"


def test_admin_cannot_delete_self(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    uid = UserRepository(app.config["DB"]).get_by_email("admin@x.com").id
    resp = client.delete(f"/api/admin/users/{uid}", headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 400


def test_admin_users_forbidden_for_salesman(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    assert client.get("/admin/users").status_code == 403
    assert client.get("/api/admin/users").status_code == 403


def test_admin_salesman_active_toggle(tmp_path):
    app = _make_app(tmp_path)
    _seed_salesman(app)
    client = app.test_client()
    _login(client, app)
    resp = client.put("/api/admin/salesmen/redwards", json={"is_active": False},
                      headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 200
    from web.data.repositories.salesmen import SalesmanRepository
    rows = {s.key: s for s in SalesmanRepository(app.config["DB"]).list_all()}
    assert rows["redwards"].is_active is False


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


@pytest.mark.parametrize("theme,body_class", [
    ("monochrome", "monochrome-theme"),
    ("monochrome_dark", "monochrome-dark-theme"),
])
def test_settings_accepts_monochrome_themes(tmp_path, theme, body_class):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/settings/theme", data={"theme": theme, "csrf_token": _CSRF})
    assert resp.status_code in (301, 302)
    with client.session_transaction() as s:
        assert s["theme"] == theme
    # And it actually renders: the body carries the right theme class.
    assert f'class="{body_class}"' in client.get("/settings").get_data(as_text=True)


def test_session_role_self_heals_from_db(tmp_path):
    """A stale session role (captured at an old login) must not hide the live
    DB role: the role badge + admin settings should reflect the DB on the next
    request, with no re-login. Security was always DB-authoritative; this fixes
    presentation parity."""
    app = _make_app(tmp_path)
    client = app.test_client()
    UserRepository(app.config["DB"]).upsert("dev@x.com", display_name="Dev", role="developer")
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "dev@x.com", "name": "Dev", "role": "salesman", "is_dev": False}
        s["_csrf_token"] = _CSRF

    body = client.get("/settings").get_data(as_text=True)
    assert "/admin/users" in body  # admin section is visible (role resolved to developer)
    with client.session_transaction() as s:
        assert s["v3_user"]["role"] == "developer"  # session was rewritten to the live role


def test_session_role_fails_closed_for_disabled_user(tmp_path):
    """A disabled (or deleted) account that still carries a privileged session
    role must not render privileged UI: the cached role is dropped to salesman."""
    app = _make_app(tmp_path)
    client = app.test_client()
    repo = UserRepository(app.config["DB"])
    u = repo.upsert("ex@x.com", display_name="Ex", role="developer")
    repo.update(u.id, is_active=False)
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "ex@x.com", "name": "Ex", "role": "developer", "is_dev": False}
        s["_csrf_token"] = _CSRF

    body = client.get("/settings").get_data(as_text=True)
    assert "/admin/users" not in body  # admin section hidden
    with client.session_transaction() as s:
        assert s["v3_user"]["role"] == "salesman"  # downgraded to fail closed


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
    assert "Customer Dashboard" in html
    assert 'data-status="overdue"' in html  # tiles present
    assert "Refresh data" in html


def test_dashboard_tiles_and_exclusion(tmp_path):
    app = _make_app(tmp_path)
    # Seed mirror rows directly so the tiles + table have data.
    from web.data.repositories.dashboard import DashboardCustomer, DashboardRepository
    DashboardRepository(app.config["DB"]).replace_all([
        DashboardCustomer("100", "Acme", "", "2026-05-01", 5, 30.0, 2.0, 32.0, 5, "active"),
        DashboardCustomer("200", "Beta", "", "2026-01-01", 3, 10.0, 1.0, 11.0, 120, "overdue"),
    ])
    client = app.test_client()
    _login(client, app)
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Acme" in html and "Beta" in html

    uid = UserRepository(app.config["DB"]).get_by_email("admin@x.com").id
    resp = client.post("/api/dashboard/exclusion",
                       json={"customer_account": "200", "excluded": True},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 200
    from web.data.repositories.exclusions import ExclusionRepository
    assert "200" in ExclusionRepository(app.config["DB"]).get(uid)


def test_notifications_api_lists_and_dismisses(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    uid = UserRepository(app.config["DB"]).get_by_email("admin@x.com").id
    from web.data.repositories.notifications import OVERDUE, NotificationRepository
    repo = NotificationRepository(app.config["DB"])
    repo.create(uid, OVERDUE, {"customer_account": "100", "customer_name": "Acme"})

    data = client.get("/api/notifications").get_json()
    assert data["overdue_count"] == 1 and data["total"] == 1
    assert data["items"][0]["customer_account"] == "100"

    dis = client.post("/api/notifications/dismiss", json={"all": True},
                      headers={"X-CSRF-Token": _CSRF})
    assert dis.get_json()["dismissed"] == 1
    assert client.get("/api/notifications").get_json()["total"] == 0


def test_dashboard_forbidden_for_plain_salesman(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    assert client.get("/dashboard").status_code == 403


def test_settings_renders_for_admin(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/settings").get_data(as_text=True)
    assert "Appearance" in html and "Profile" in html


def test_granted_non_privileged_user_can_run_scoped_report(tmp_path):
    """A manager with an explicit report grant can run it (scoped to their keys)."""
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
    assert "Ordered" in client.get("/").get_data(as_text=True)
    assert client.get("/reports/ordered").status_code == 200
    resp = client.post("/api/reports/ordered/run", json={},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 202


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


def test_preview_body_shows_sp_params_for_developer(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    resp = client.post("/api/reports/ordered/preview-body",
                       json={"period": "ytd", "salesman": "REdwards"},
                       headers={"X-CSRF-Token": _CSRF})
    body = resp.get_json()
    assert body["report_id"] == "salesline_release"
    assert body["body"]["SalesGroup"] == "REdwards"
    assert "CreatedDateTimeFrom" in body["body"]


def test_preview_body_forbidden_for_non_developer(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)  # admin -- privileged, but not a developer
    resp = client.post("/api/reports/ordered/preview-body",
                       json={"period": "ytd"},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 403


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


def test_delivery_job_reauthorizes_owner_and_fails_closed(tmp_path):
    """A queued delivery fails at execution time when the owner's access has been
    revoked since enqueue (live re-auth). Guards against mid-flight role changes."""
    app = _make_app(tmp_path, rows_by_report=_ordered_rows())
    db = app.config["DB"]
    rep = UserRepository(db).upsert("rep@x.com", display_name="Rep", role="salesman")
    # Explicitly deny this user's access to the ordered report
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO user_report_access(user_id, report_key, allowed) VALUES (?, 'ordered', 0)",
            (rep.id,),
        )
    from web.delivery.jobs import enqueue_delivery

    job_id = enqueue_delivery(app.config["JOB_REPO"], owner_user_id=rep.id, payload={
        "report_key": "ordered", "identity": "rep@x.com", "builder_version": 1,
        "params": {"period": "all_time"}, "layout": {}, "recipients": "a@x.com",
        "subject": "x", "report_name": "Ordered", "sharepoint_path": "",
    })
    app.config["JOB_WORKER"].drain()
    job = app.config["JOB_REPO"].get(job_id)
    assert job.status == "failure"


def test_schedule_rejects_invalid_recipients(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/schedules", json={
        "report_key": "ordered", "recipients": "not-an-email",
        "cadence": {"freq": "daily", "time": "08:00"}},
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


def _ordered_rows():
    return {"salesline_release": [
        {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
         "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
         "SalesStatus": "Open", "OrderDate": "2026-03-01"},
    ]}


def test_schedule_create_run_history_and_delete(tmp_path):
    app = _make_app(tmp_path, rows_by_report=_ordered_rows())
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/schedules", json={
        "report_key": "ordered", "recipients": "a@x.com",
        "cadence": {"freq": "daily", "time": "08:00"}, "params": {"period": "all_time"},
        "layout": {}}, headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    sid = created.get_json()["id"]

    # appears on the page
    assert "Daily at 08:00" in client.get("/schedules").get_data(as_text=True)

    # run now -> job success + a history row
    run = client.post(f"/api/schedules/{sid}/run", headers={"X-CSRF-Token": _CSRF})
    assert run.status_code == 202
    assert client.get(f"/api/jobs/{run.get_json()['job_id']}").get_json()["status"] == "success"
    assert "success" in client.get(f"/schedules/{sid}/history").get_data(as_text=True).lower()

    # toggle + delete
    assert client.post(f"/api/schedules/{sid}/toggle", json={"active": False},
                       headers={"X-CSRF-Token": _CSRF}).status_code == 200
    assert client.delete(f"/api/schedules/{sid}", headers={"X-CSRF-Token": _CSRF}).status_code == 200


def test_schedule_requires_recipient_or_sharepoint(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/schedules", json={
        "report_key": "ordered", "cadence": {"freq": "daily", "time": "08:00"}},
        headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 400


def test_schedule_rejects_bad_cadence(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/schedules", json={
        "report_key": "ordered", "recipients": "a@x.com", "cadence": {"freq": "yearly"}},
        headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 400


def test_schedule_is_owner_scoped(tmp_path):
    app = _make_app(tmp_path)
    owner = app.test_client()
    _login(owner, app)
    sid = owner.post("/api/schedules", json={
        "report_key": "ordered", "recipients": "a@x.com",
        "cadence": {"freq": "daily", "time": "08:00"}},
        headers={"X-CSRF-Token": _CSRF}).get_json()["id"]
    other = app.test_client()
    _login(other, app, email="rep@x.com", role="admin")
    assert other.delete(f"/api/schedules/{sid}", headers={"X-CSRF-Token": _CSRF}).status_code == 404


def test_master_schedule_admin_only(tmp_path):
    app = _make_app(tmp_path)
    rep = app.test_client()
    _login(rep, app, email="rep@x.com", role="salesman")
    assert rep.get("/master-schedules").status_code == 403
    assert rep.post("/api/master-schedules", json={
        "name": "x", "report_key": "ordered", "recipients": "t@x.com",
        "cadence": {"freq": "daily", "time": "08:00"}},
        headers={"X-CSRF-Token": _CSRF}).status_code == 403

    admin = app.test_client()
    _login(admin, app)
    created = admin.post("/api/master-schedules", json={
        "name": "Nightly", "report_key": "ordered", "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "06:00"}},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    assert "Nightly" in admin.get("/master-schedules").get_data(as_text=True)


def test_preferences_api_persists_theme(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/settings/preferences", json={"theme": "dark"},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 200 and resp.get_json()["theme"] == "dark"
    # persisted in user_preferences
    from web.data.repositories.preferences import PreferencesRepository
    from web.data.repositories.users import UserRepository as _UR
    uid = _UR(app.config["DB"]).get_by_email("admin@x.com").id
    assert PreferencesRepository(app.config["DB"]).get(uid).theme == "dark"


def test_preferences_api_rejects_unknown_user(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    # session without a DB-backed user row
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "ghost@x.com", "name": "G", "role": "salesman", "is_dev": True}
        s["_csrf_token"] = _CSRF
    resp = client.post("/api/settings/preferences", json={"theme": "dark"},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 403


def test_report_view_has_help_triggers(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/reports/ordered").get_data(as_text=True)
    assert 'help_content.js' in html          # dictionary loaded in <head>
    assert 'data-help="report-ordered"' in html
    assert 'data-help="param-period"' in html


def test_manifest_is_dynamic_and_prefix_aware(tmp_path):
    app = _make_app(tmp_path)
    data = app.test_client().get("/manifest.json").get_json()
    assert data["start_url"].endswith("/") or data["start_url"] != ""
    assert data["scope"].endswith("/")
    assert all(i["src"].endswith(".png") for i in data["icons"])


def test_header_has_theme_toggle(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    assert 'id="themeToggleBtn"' in client.get("/settings").get_data(as_text=True)


def test_feature_flag_admin_set_and_reflects_in_settings(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)  # admin
    resp = client.post("/api/admin/feature-flags", json={"key": "test_site_enabled", "enabled": True},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 200 and resp.get_json()["enabled"] is True
    from web.data.repositories.feature_flags import FeatureFlagRepository
    assert FeatureFlagRepository(app.config["DB"]).is_enabled("test_site_enabled") is True


def test_feature_flag_rejects_unknown_key(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/admin/feature-flags", json={"key": "nope", "enabled": True},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 400


def test_feature_flag_forbidden_for_salesman(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "rep@x.com", "name": "Rep", "role": "salesman", "is_dev": True}
        s["_csrf_token"] = _CSRF
    resp = client.post("/api/admin/feature-flags", json={"key": "test_site_enabled", "enabled": True},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 403


def _clo_rows():
    return [
        {"SalesOrderNumber": "SO3", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": "REdwards", "OrderStatus": "Invoiced", "OrderDate": "2026-03-10",
         "CustomerRequisition": "PO-9", "LineNumber": "1", "Item": "ITM-A",
         "ItemDescription": "Widget", "SalesPrice": "2.00", "SalesStatus": "Delivered",
         "QuantityOrdered": "10", "ReleasedQuantity": "10", "DeliveryRemainder": "0",
         "QuantityLefttoLoad": "0", "Ordered $": "20.00", "Shipped $": "20.00", "Cancelled $": "0"},
    ]


def test_customer_last_order_pick_renders(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/report/customer-last-order").get_data(as_text=True)
    assert "Customer's Last Order" in html
    assert "Pick a customer" in html


def test_customer_last_order_listed_as_built(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/").get_data(as_text=True)
    assert "Customer&#39;s Last Order" in html or "Customer's Last Order" in html
    # It's an in-app report -> links to the picker, not the standard viewer.
    assert "/report/customer-last-order" in html


def test_customer_last_order_view_shows_latest_invoiced(tmp_path):
    app = _make_app(tmp_path, rows_by_report={"salesline_release": _clo_rows()})
    client = app.test_client()
    _login(client, app)
    html = client.get("/report/customer-last-order/100").get_data(as_text=True)
    assert "Last Invoiced Order" in html
    assert "SO3" in html and "ITM-A" in html
    assert "Acme" in html


def test_customer_last_order_recent_invoiced_api(tmp_path):
    app = _make_app(tmp_path, rows_by_report={"salesline_release": _clo_rows()})
    client = app.test_client()
    _login(client, app)
    data = client.get("/api/report/customer-last-order/100/recent-invoiced").get_json()
    assert [o["order_number"] for o in data["orders"]] == ["SO3"]


def test_customer_last_order_view_redirects_from_standard_viewer(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.get("/reports/customer_last_order")
    assert resp.status_code in (301, 302)
    assert "/report/customer-last-order" in resp.headers["Location"]


def _clo_real_rows(sales_group):
    # Real salesline_release shape: per-line SalesStatus, no header OrderStatus.
    return {"salesline_release": [
        {"SalesOrderNumber": "SO3", "CustomerAccount": "100", "customername": "Acme",
         "SalesGroup": sales_group, "SalesStatus": "Invoiced", "OrderDate": "2026-03-10",
         "CustomerRequisition": "PO-9", "LineNumber": "1", "Item": "ITM-A",
         "ItemDescription": "Widget", "SalesPrice": "2.00",
         "QuantityOrdered": "10", "ReleasedQuantity": "10", "DeliveryRemainder": "0",
         "QuantityLefttoLoad": "0", "Ordered $": "20.00", "Shipped $": "20.00", "Cancelled $": "0"},
    ]}


def _grant_clo_salesman(app, *, salesman_group):
    from report_engine.lib import salesman_key
    from web.data.repositories.salesmen import SalesmanRepository, SalesmanSeed

    db = app.config["DB"]
    # The salesman key must exist (user_salesman_access FKs salesmen.key).
    SalesmanRepository(db).upsert_many([SalesmanSeed(
        raw_key=salesman_group, number="1", full_name=salesman_group,
        display_name=salesman_group)])
    user = UserRepository(db).upsert("rep@x.com", display_name="Rep", role="salesman")
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO user_report_access(user_id, report_key, allowed) "
            "VALUES (?, 'customer_last_order', 1)", (user.id,))
        conn.execute(
            "INSERT INTO user_salesman_access(user_id, salesman_key) VALUES (?, ?)",
            (user.id, salesman_key(salesman_group)))


def test_customer_last_order_scoped_salesman_in_scope_ok(tmp_path):
    app = _make_app(tmp_path, rows_by_report=_clo_real_rows("REdwards"))
    _grant_clo_salesman(app, salesman_group="REdwards")
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    resp = client.get("/report/customer-last-order/100")
    assert resp.status_code == 200
    assert "SO3" in resp.get_data(as_text=True)


def test_customer_last_order_scoped_salesman_out_of_scope_denied(tmp_path):
    # Granted the report + a salesman key, but this customer's line belongs to a
    # different salesgroup -> customer-level scope denies it (403), even from the
    # line-level data (blank/foreign SalesGroup must not slip through).
    app = _make_app(tmp_path, rows_by_report=_clo_real_rows("OtherRep"))
    _grant_clo_salesman(app, salesman_group="REdwards")
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    assert client.get("/report/customer-last-order/100").status_code == 403


def test_customer_last_order_salesmen_endpoint_scoped(tmp_path):
    # The picker is hidden for scoped users, but the endpoint is directly callable;
    # it must not enumerate salesmen outside the caller's scope.
    app = _make_app(tmp_path, rows_by_report=_clo_real_rows("REdwards"))
    _grant_clo_salesman(app, salesman_group="REdwards")
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    data = client.get("/api/report/customer-last-order/salesmen").get_json()
    from report_engine.lib import salesman_key
    assert all(salesman_key(s["key"]) == salesman_key("REdwards") for s in data["salesmen"])


def test_customer_last_order_forbidden_for_ungranted_salesman(tmp_path):
    app = _make_app(tmp_path, rows_by_report={"salesline_release": _clo_rows()})
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    # No per-report grant -> page access denied (fail closed).
    assert client.get("/report/customer-last-order").status_code == 403


def test_invoiced_commissions_tab_is_not_blank(tmp_path):
    rows = [
        {"InvoiceNumber": "INV1", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-03-01", "SubTotal": "100", "SH_TariffCharges": "0",
         "FreightCharges": "0", "CCSurcharge": "0", "SalesGroup": "REdwards"},
    ]
    app = _make_app(tmp_path, rows_by_report={"invoiced_report": rows})
    client = app.test_client()
    _login(client, app)
    job_id = client.post("/api/reports/invoiced/run", json={"year": "2026"},
                         headers={"X-CSRF-Token": _CSRF}).get_json()["job_id"]
    payload = client.get(f"/api/reports/result/{job_id}").get_json()
    comm = next(t for t in payload["tabs"] if t["key"] == "commissions")
    assert comm["columns"] and comm["rows"]  # renders as a real table, not blank
