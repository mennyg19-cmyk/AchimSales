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
    assert "Sales by State" in html
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
    assert "Sales by State" not in html


def test_report_view_renders_filters(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/reports/ordered").get_data(as_text=True)
    assert 'id="runBtn"' in html
    assert 'id="emailMeBtn"' in html
    assert 'name="period"' in html  # ordered exposes a period filter


def test_run_poll_result_export_flow(tmp_path):
    rows = {
        "ordered_report": [
            {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
             "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
             "SalesStatus": "Open", "CreatedDateTime": "2026-03-01"},
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
    rows = {"ordered_report": [
        {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
         "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
         "SalesStatus": "Open", "CreatedDateTime": "2026-03-01"}]}
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


def test_admin_can_update_salesman_email(tmp_path):
    app = _make_app(tmp_path)
    _seed_salesman(app)
    client = app.test_client()
    _login(client, app)
    resp = client.put("/api/admin/salesmen/redwards", json={"email": "rep@x.com"},
                      headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 200
    from web.data.repositories.salesmen import SalesmanRepository
    rows = {s.key: s for s in SalesmanRepository(app.config["DB"]).list_all()}
    assert rows["redwards"].email == "rep@x.com"


def test_run_requires_csrf(tmp_path):
    app = _make_app(tmp_path, rows_by_report={})
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/reports/ordered/run", json={})
    assert resp.status_code == 400  # missing CSRF header


def test_cancel_job_endpoint_cancels_owned_job(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    uid = UserRepository(app.config["DB"]).get_by_email("admin@x.com").id
    # A queued job owned by the admin (enqueued directly so it isn't drained).
    job_id = app.config["JOB_REPO"].enqueue(JOB_TYPE, owner_user_id=uid, params={})
    resp = client.post(f"/api/jobs/{job_id}/cancel", headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 200
    assert resp.get_json()["cancelled"] is True
    assert app.config["JOB_REPO"].get(job_id).status == "cancelled"


def test_cannot_cancel_another_users_job(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    uid = UserRepository(app.config["DB"]).get_by_email("admin@x.com").id
    job_id = app.config["JOB_REPO"].enqueue(JOB_TYPE, owner_user_id=uid, params={})
    other = app.test_client()
    _login(other, app, email="other@x.com", role="admin")
    assert other.post(f"/api/jobs/{job_id}/cancel",
                      headers={"X-CSRF-Token": _CSRF}).status_code == 404
    assert app.config["JOB_REPO"].get(job_id).status == "queued"  # untouched


def test_active_report_runs_lists_owners_recent_run(tmp_path):
    rows = {
        "ordered_report": [
            {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
             "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
             "SalesStatus": "Open", "CreatedDateTime": "2026-03-01"},
        ]
    }
    app = _make_app(tmp_path, rows_by_report=rows)
    client = app.test_client()
    _login(client, app)
    job_id = client.post("/api/reports/ordered/run", json={"period": "all_time"},
                         headers={"X-CSRF-Token": _CSRF}).get_json()["job_id"]

    jobs = client.get("/api/reports/active").get_json()["jobs"]
    mine = [j for j in jobs if j["job_id"] == job_id]
    assert len(mine) == 1
    assert mine[0]["report_key"] == "ordered"
    assert mine[0]["status"] == "success"  # worker drains inline in tests
    assert mine[0]["title"]
    assert mine[0]["created_at"]
    assert "keep_name" in mine[0]


def test_keep_report_run_stores_name(tmp_path):
    rows = {
        "ordered_report": [
            {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
             "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
             "SalesStatus": "Open", "CreatedDateTime": "2026-03-01"},
        ]
    }
    app = _make_app(tmp_path, rows_by_report=rows)
    client = app.test_client()
    _login(client, app)
    job_id = client.post("/api/reports/ordered/run", json={"period": "all_time"},
                         headers={"X-CSRF-Token": _CSRF}).get_json()["job_id"]
    resp = client.post(
        f"/api/reports/runs/{job_id}/keep",
        json={"name": "Monday morning"},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["keep_name"] == "Monday morning" and body["kept"] is True
    mine = [j for j in client.get("/api/reports/active").get_json()["jobs"]
            if j["job_id"] == job_id][0]
    assert mine["keep_name"] == "Monday morning" and mine["kept"] is True
    assert mine["finished_at"]


def test_active_report_runs_is_owner_scoped(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    uid = UserRepository(app.config["DB"]).get_by_email("admin@x.com").id
    job_id = app.config["JOB_REPO"].enqueue(
        JOB_TYPE, owner_user_id=uid, params={"report_key": "ordered"})

    other = app.test_client()
    _login(other, app, email="other@x.com", role="admin")
    jobs = other.get("/api/reports/active").get_json()["jobs"]
    assert all(j["job_id"] != job_id for j in jobs)


def test_reporting_api_diagnostics_developer_only(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)  # admin -- privileged, but not a developer
    assert client.get("/api/reports/diagnostics/reporting-api").status_code == 403


def test_reporting_api_diagnostics_reports_state(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="dev@x.com", role="developer")
    data = client.get("/api/reports/diagnostics/reporting-api").get_json()
    # No API URL is configured in the test cfg, so the probe short-circuits
    # without a network call but still reports structure.
    assert data["reporting_api"]["configured"] is False
    assert "by_status" in data["jobs"] and "active" in data["jobs"]


def test_report_view_renders_cancel_button(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/reports/ordered").get_data(as_text=True)
    assert 'id="cancelRunBtn"' in html
    assert "data-cancel-url" in html


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
    """A disabled account must be signed out, not left in as a salesman."""
    app = _make_app(tmp_path)
    client = app.test_client()
    repo = UserRepository(app.config["DB"])
    u = repo.upsert("ex@x.com", display_name="Ex", role="developer")
    repo.update(u.id, is_active=False)
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "ex@x.com", "name": "Ex", "role": "developer", "is_dev": False}
        s["_csrf_token"] = _CSRF

    resp = client.get("/settings")
    assert resp.status_code in (301, 302)
    assert "/login" in (resp.headers.get("Location") or "")
    with client.session_transaction() as s:
        assert not s.get("v3_user")


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
    assert body["report_id"] == "ordered_report"
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

    patched = client.patch(f"/api/reports/presets/{pid}",
                           json={"name": "March edited", "params": {"period": "yesterday"}},
                           headers={"X-CSRF-Token": _CSRF})
    assert patched.status_code == 200
    assert patched.get_json()["name"] == "March edited"
    assert patched.get_json()["params"]["period"] == "yesterday"

    # Cross-report list (My Presets) + home page shows it
    allp = client.get("/api/saved-reports").get_json()["presets"]
    assert any(p["id"] == pid for p in allp)
    assert "My presets" in client.get("/").get_data(as_text=True)
    assert "March edited" in client.get("/").get_data(as_text=True)

    # Delete
    assert client.delete(f"/api/reports/presets/{pid}",
                         headers={"X-CSRF-Token": _CSRF}).status_code == 200
    assert client.get("/api/reports/ordered/presets").get_json()["presets"] == []


def test_home_preset_url_keeps_salesman_and_open_status(tmp_path):
    """A saved Ordered view for one salesman + Open must deep-link those filters."""
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/reports/ordered/presets",
                          json={"name": "Heshy Open Orders",
                                "params": {"period": "all_time", "salesman": "HGoldberg",
                                           "status": "Open order"},
                                "layout": {}},
                          headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    pid = created.get_json()["id"]
    saved = client.get(f"/api/reports/presets/{pid}").get_json()
    assert saved["params"]["salesman"] == "HGoldberg"
    assert saved["params"]["status"] == "Open order"
    html = client.get("/").get_data(as_text=True)
    assert "Heshy Open Orders" in html
    assert "salesman=HGoldberg" in html
    assert "Open+order" in html or "Open%20order" in html
    assert f"preset={pid}" in html


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


def test_preset_cannot_use_the_name_default(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/reports/ordered/presets",
                       json={"name": "Default", "params": {}, "layout": {}},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 400


def test_default_view_get_put_and_presets_include_it(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    empty = client.get("/api/reports/ordered/default-view").get_json()
    assert empty["name"] == "Default"
    assert empty["layout"] == {}
    assert empty["can_edit"] is True
    saved = client.put(
        "/api/reports/ordered/default-view",
        json={"params": {"period": "yesterday"},
              "layout": {"active": "summary", "views": {"summary": {"hidden": ["x"]}}}},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert saved.status_code == 200
    assert saved.get_json()["params"]["period"] == "yesterday"
    assert saved.get_json()["layout"]["active"] == "summary"
    listed = client.get("/api/reports/ordered/presets").get_json()
    assert listed["default"]["layout"]["active"] == "summary"
    assert listed["presets"] == []
    assert listed["company"] == []


def test_salesman_cannot_edit_default_view(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    got = client.get("/api/reports/ordered/default-view")
    assert got.status_code == 200
    assert got.get_json()["can_edit"] is False
    put = client.put(
        "/api/reports/ordered/default-view",
        json={"params": {}, "layout": {"active": "x"}},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert put.status_code == 403


def test_company_views_list_put_and_home_cards(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    empty = client.get("/api/reports/ordered/presets").get_json()
    assert empty["company"] == []
    saved = client.put(
        "/api/reports/ordered/company-views",
        json={"name": "Daily Ordered", "params": {"period": "yesterday"},
              "layout": {"active": "by_customer",
                         "views": {"by_customer": {"group": ["Salesman", "CustomerName"]}}}},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["name"] == "Daily Ordered" and body["kind"] == "company"
    listed = client.get("/api/reports/ordered/presets").get_json()
    assert listed["company"][0]["name"] == "Daily Ordered"
    one = client.get(f"/api/reports/ordered/company-views/{body['id']}").get_json()
    assert one["layout"]["active"] == "by_customer"
    home = client.get("/").get_data(as_text=True)
    assert "Company views" in home and "Daily Ordered" in home
    reserved = client.put(
        "/api/reports/ordered/company-views",
        json={"name": "Default", "params": {}, "layout": {}},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert reserved.status_code == 400


def test_salesman_cannot_edit_company_view(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    saved = admin.put(
        "/api/reports/ordered/company-views",
        json={"name": "Heshy Open Orders", "params": {}, "layout": {"order": ["full_data"]}},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert saved.status_code == 200
    rep = app.test_client()
    _login(rep, app, email="rep@x.com", role="salesman")
    listed = rep.get("/api/reports/ordered/presets").get_json()
    assert listed["company"][0]["can_edit"] is False
    put = rep.put(
        "/api/reports/ordered/company-views",
        json={"name": "Heshy Open Orders", "params": {}, "layout": {"order": ["summary"]}},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert put.status_code == 403


def test_schedule_create_default_view_shows_on_page(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/schedules", json={
        "report_key": "ordered", "recipients": "a@x.com",
        "cadence": {"freq": "daily", "time": "08:00"}, "params": {},
        "layout": {}, "view_name": "Default"},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    html = client.get("/schedules").get_data(as_text=True)
    assert "<th>View</th>" in html
    assert 'data-view-name="Default"' in html


def test_schedule_from_layout_snapshot_is_custom(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/schedules", json={
        "report_key": "ordered", "recipients": "a@x.com",
        "cadence": {"freq": "daily", "time": "08:00"},
        "layout": {"order": ["summary"], "views": {"summary": {"hidden": []}}}},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    html = client.get("/schedules").get_data(as_text=True)
    assert 'data-view-name="Custom"' in html


def test_email_now_enqueues_and_delivers(tmp_path):
    rows = {"ordered_report": [
        {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
         "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
         "SalesStatus": "Open", "CreatedDateTime": "2026-03-01"},
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
    return {"ordered_report": [
        {"SalesOrderNumber": "SO1", "CustomerAccount": "100", "Item": "ITM-1",
         "ItemDescription": "Widget", "QuantityOrdered": "5", "Ordered $": "50",
         "SalesStatus": "Open", "CreatedDateTime": "2026-03-01"},
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

    recent = client.get("/api/schedules/recent-runs")
    assert recent.status_code == 200
    runs = recent.get_json()["runs"]
    assert runs and runs[0]["status"] == "success"
    assert runs[0]["schedule_id"] == sid

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


def test_schedules_page_company_section_admin_only(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    admin_html = admin.get("/schedules").get_data(as_text=True)
    assert "My schedules" in admin_html
    assert "Company schedules" in admin_html
    assert "msWizard" in admin_html
    assert "Add a schedule" in admin_html

    rep = app.test_client()
    _login(rep, app, email="rep@x.com", role="salesman")
    rep_html = rep.get("/schedules").get_data(as_text=True)
    assert "My schedules" in rep_html
    assert "Add a schedule" in rep_html
    assert "msWizard" in rep_html
    assert "Company schedules" not in rep_html
    assert "Keep private" not in rep_html
    assert "Run as a manager" not in rep_html


def test_personal_schedule_row_has_edit(tmp_path):
    app = _make_app(tmp_path)
    c = app.test_client()
    _login(c, app, email="rep@x.com", role="salesman")
    created = c.post("/api/schedules", json={
        "report_key": "ordered", "recipients": "a@x.com",
        "cadence": {"freq": "daily", "time": "08:00"}},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    html = c.get("/schedules").get_data(as_text=True)
    assert "js-edit" in html
    assert 'data-kind="personal"' in html
    assert "data-personal-update-url-tpl" in html


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
    redirected = admin.get("/master-schedules")
    assert redirected.status_code == 302
    assert redirected.headers["Location"].endswith("/schedules#company")
    created = admin.post("/api/master-schedules", json={
        "name": "Nightly", "report_key": "ordered", "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "06:00"},
        "params": {
            "period": "yesterday",
            "customers": ["9300", "9301"],
            "salesman": ["MKolko", "AGrossman"],
            "status": ["Open order", "Delivered"],
            "email_to_salesmen": True,
        }},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    page = admin.get("/schedules").get_data(as_text=True)
    assert "Nightly" in page
    assert "Company schedules" in page
    assert "Recent run log" in page
    assert "msWizard" in page
    assert "Add a schedule" in page
    assert "data-pane=\"1\"" in page
    assert 'id="msStatusPicker"' in page
    assert 'id="msSalesmanPicker"' in page
    assert 'id="msCustomerPicker"' in page
    assert "master-schedules/lookups/salesmen" in page
    assert "master-schedules/lookups/salesmen-emails" in page
    assert "master-schedules/lookups/customers" in page
    assert "master-schedules/lookups/status" in page
    assert f"/master-schedules/{created.get_json()['id']}/history" in page

    from web.data.repositories.schedules import MasterScheduleRepository
    mid = created.get_json()["id"]
    saved = MasterScheduleRepository(app.config["DB"]).get(mid)
    assert saved.params["period"] == "yesterday"
    assert saved.params["customers"] == ["9300", "9301"]
    assert saved.params["salesman"] == ["MKolko", "AGrossman"]
    assert saved.params["status"] == ["Open order", "Delivered"]
    assert saved.params["email_to_salesmen"] is True
    assert saved.params["split_by_salesman"] is False

    hist = admin.get(f"/master-schedules/{mid}/history")
    assert hist.status_code == 200
    assert "run history" in hist.get_data(as_text=True).lower()
    assert rep.get(f"/master-schedules/{mid}/history").status_code == 403


def test_company_schedules_list_sorted_by_name(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    for name in ("Zebra nightly", "Apple daily"):
        created = client.post("/api/master-schedules", json={
            "name": name, "report_key": "ordered", "recipients": "t@x.com",
            "cadence": {"freq": "daily", "time": "06:00"}, "is_shared": True,
        }, headers={"X-CSRF-Token": _CSRF})
        assert created.status_code == 201
    page = client.get("/schedules").get_data(as_text=True)
    assert 'id="companySchedulesTable"' in page
    assert "js-sortable" in page
    assert page.find("Apple daily") < page.find("Zebra nightly")


def test_deleted_company_schedule_is_not_reseeded(tmp_path):
    from web import _seed_master_schedules
    from web.data.repositories.schedules import MasterScheduleRepository

    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/master-schedules", json={
        "name": "Daily Ordered Report", "report_key": "ordered",
        "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "00:00"}, "is_shared": True,
    }, headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    sid = created.get_json()["id"]
    assert client.delete(
        f"/api/master-schedules/{sid}", headers={"X-CSRF-Token": _CSRF},
    ).status_code == 200
    _seed_master_schedules(app, app.config["DB"], [{
        "name": "Daily Ordered Report",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "00:00"},
        "sharepoint_path": "Direct Reports/Ordered Report/Daily",
    }])
    repo = MasterScheduleRepository(app.config["DB"])
    assert "Daily Ordered Report" not in {r.name for r in repo.list_all()}


def test_master_schedule_lookups_admin_only(tmp_path):
    rows = [
        {"CustomerAccount": "100", "CustomerName": "Acme", "SalesGroup": "MKolko"},
        {"CustomerAccount": "200", "CustomerName": "Beta", "SalesGroup": "AGrossman"},
    ]
    app = _make_app(tmp_path)
    _with_lookups(app, rows)

    rep = app.test_client()
    _login(rep, app, email="rep@x.com", role="salesman")
    assert rep.get("/api/master-schedules/lookups/salesmen").status_code == 403
    assert rep.get("/api/master-schedules/lookups/salesmen-emails").status_code == 403
    assert rep.get("/api/master-schedules/lookups/customers").status_code == 403

    admin = app.test_client()
    _login(admin, app)
    from web.data.repositories.salesmen import SalesmanRepository, SalesmanSeed
    SalesmanRepository(app.config["DB"]).upsert_many([
        SalesmanSeed(raw_key="MKolko", number="1", full_name="M Kolko",
                     display_name="M Kolko", email="m@x.com"),
        SalesmanSeed(raw_key="AGrossman", number="2", full_name="A Grossman",
                     display_name="A Grossman", email=""),
    ])
    sm = admin.get("/api/master-schedules/lookups/salesmen").get_json()["salesmen"]
    assert {r["key"] for r in sm} >= {"MKolko", "AGrossman"}
    mgr = app.test_client()
    _login(mgr, app, email="mgr@x.com", role="manager")
    assert mgr.get("/api/master-schedules/lookups/salesmen").status_code == 200
    sm_emails = admin.get("/api/master-schedules/lookups/salesmen-emails").get_json()["salesmen"]
    assert sm_emails == [{"email": "m@x.com", "key": "MKolko", "name": "MKolko"}]
    cust = admin.get("/api/master-schedules/lookups/customers").get_json()["customers"]
    assert {c["key"] for c in cust} == {"100", "200"}
    st = admin.get("/api/master-schedules/lookups/status").get_json()
    assert st["cached_row_count"] == 2


def test_manager_company_schedule_edit_and_share(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    created = admin.post("/api/master-schedules", json={
        "name": "Admin nightly", "report_key": "ordered", "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "06:00"}, "is_shared": True,
    }, headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    admin_id = created.get_json()["id"]

    mgr = app.test_client()
    _login(mgr, app, email="mgr@x.com", role="manager")
    page = mgr.get("/schedules").get_data(as_text=True)
    assert "Company schedules" in page
    assert "Admin nightly" in page
    assert "Speak to an admin." in page
    assert mgr.put(f"/api/master-schedules/{admin_id}", json={
        "name": "Hacked", "report_key": "ordered", "recipients": "x@x.com",
        "cadence": {"freq": "daily", "time": "06:00"},
    }, headers={"X-CSRF-Token": _CSRF}).status_code == 403

    own = mgr.post("/api/master-schedules", json={
        "name": "Mgr shared", "report_key": "ordered", "recipients": "m@x.com",
        "cadence": {"freq": "daily", "time": "07:00"}, "is_shared": True,
    }, headers={"X-CSRF-Token": _CSRF})
    assert own.status_code == 201
    own_id = own.get_json()["id"]
    assert mgr.put(f"/api/master-schedules/{own_id}", json={
        "name": "Mgr shared edited", "report_key": "ordered", "recipients": "m@x.com",
        "cadence": {"freq": "daily", "time": "07:00"}, "is_shared": True,
    }, headers={"X-CSRF-Token": _CSRF}).status_code == 200

    private = mgr.post("/api/master-schedules", json={
        "name": "Mgr private", "report_key": "ordered", "recipients": "m@x.com",
        "cadence": {"freq": "daily", "time": "08:00"}, "is_shared": False,
    }, headers={"X-CSRF-Token": _CSRF})
    assert private.status_code == 201
    assert "Mgr private" not in admin.get("/schedules").get_data(as_text=True)
    mgr_html = mgr.get("/schedules").get_data(as_text=True)
    assert "Mgr private" in mgr_html
    assert "Mgr shared edited" in mgr_html

    other = app.test_client()
    _login(other, app, email="mgr2@x.com", role="manager")
    assert other.put(f"/api/master-schedules/{own_id}", json={
        "name": "Nope", "report_key": "ordered", "recipients": "x@x.com",
        "cadence": {"freq": "daily", "time": "07:00"},
    }, headers={"X-CSRF-Token": _CSRF}).status_code == 403
    other_html = other.get("/schedules").get_data(as_text=True)
    assert "Mgr shared edited" in other_html
    assert "Mgr private" not in other_html
    assert "Speak to an admin." in other_html


def test_master_schedule_put_keeps_layout_when_wizard_sends_empty(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    created = admin.post("/api/master-schedules", json={
        "name": "Shipped", "report_key": "invoiced", "recipients": "t@x.com",
        "cadence": {"freq": "daily", "time": "09:00"}, "is_shared": True,
        "layout": {"order": ["invoices", "credits"]},
    }, headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    mid = created.get_json()["id"]
    assert admin.put(f"/api/master-schedules/{mid}", json={
        "name": "Shipped", "report_key": "invoiced", "recipients": "t@x.com",
        "cadence": {"freq": "daily", "time": "09:00"}, "is_shared": True,
        "layout": {},
    }, headers={"X-CSRF-Token": _CSRF}).status_code == 200
    from web.data.repositories.schedules import MasterScheduleRepository
    with app.app_context():
        row = MasterScheduleRepository(app.config["DB"]).get(mid)
    assert row is not None
    assert row.layout.get("order") == ["invoices", "credits"]


def test_master_schedule_normalizes_csv_multi_params(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    created = admin.post("/api/master-schedules", json={
        "name": "CSV multi", "report_key": "ordered", "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "06:00"},
        "params": {
            "period": "yesterday",
            "customers": "9300 9301",
            "salesman": "MKolko,AGrossman",
            "status": "Open order,Delivered",
        }},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    from web.data.repositories.schedules import MasterScheduleRepository
    saved = MasterScheduleRepository(app.config["DB"]).get(created.get_json()["id"])
    assert saved.params["customers"] == ["9300", "9301"]
    assert saved.params["salesman"] == ["MKolko", "AGrossman"]
    assert saved.params["status"] == ["Open order", "Delivered"]


def test_master_schedule_persists_unfiltered_salesman_delivery_options(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    created = admin.post("/api/master-schedules", json={
        "name": "Split email", "report_key": "ordered",
        "cadence": {"freq": "daily", "time": "06:00"},
        "params": {
            "period": "yesterday",
            "split_by_salesman": True,
            "email_salesman_keys": ["MKolko", "AGrossman"],
        }},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    from web.data.repositories.schedules import MasterScheduleRepository
    saved = MasterScheduleRepository(app.config["DB"]).get(created.get_json()["id"])
    assert saved.recipients == ""
    assert saved.params["split_by_salesman"] is True
    assert saved.params["email_to_salesmen"] is False
    assert saved.params["email_salesman_keys"] == ["MKolko", "AGrossman"]


def test_master_schedule_persists_salesman_report_split(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    created = admin.post("/api/master-schedules", json={
        "name": "Monthly Salesmen", "report_key": "salesman",
        "cadence": {"freq": "monthly", "time": "22:00", "monthdays": [1]},
        "params": {"split_by_salesman": True},
    }, headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    from web.data.repositories.schedules import MasterScheduleRepository
    saved = MasterScheduleRepository(app.config["DB"]).get(created.get_json()["id"])
    assert saved.recipients == ""
    assert saved.sharepoint_path == ""
    assert saved.params["split_by_salesman"] is True


def test_master_schedule_rejects_in_app_report(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    resp = admin.post("/api/master-schedules", json={
        "name": "CLO", "report_key": "customer_last_order", "recipients": "t@x.com",
        "cadence": {"freq": "daily", "time": "08:00"}},
        headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 400


def test_settings_links_company_schedules_without_master_card(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    html = admin.get("/settings").get_data(as_text=True)
    assert "Company schedules" in html
    assert "admin-sched-card" not in html
    assert "Set up / manage schedules" not in html



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
    resp = client.post("/api/admin/feature-flags", json={"key": "dashboard_enabled", "enabled": True},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 200 and resp.get_json()["enabled"] is True
    from web.data.repositories.feature_flags import FeatureFlagRepository
    assert FeatureFlagRepository(app.config["DB"]).is_enabled("dashboard_enabled") is True


def test_feature_flag_rejects_unknown_key(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/admin/feature-flags", json={"key": "nope", "enabled": True},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 400
    for key in ("test_site_enabled", "order_entry_enabled"):
        retired = client.post("/api/admin/feature-flags", json={"key": key, "enabled": True},
                              headers={"X-CSRF-Token": _CSRF})
        assert retired.status_code == 400


def test_feature_flag_forbidden_for_salesman(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "rep@x.com", "name": "Rep", "role": "salesman", "is_dev": True}
        s["_csrf_token"] = _CSRF
    resp = client.post("/api/admin/feature-flags", json={"key": "dashboard_enabled", "enabled": True},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 403


def test_schedule_test_mode_admin_set_and_rejects_empty_enable(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/settings").get_data(as_text=True)
    assert "Schedule test mode" in html
    empty = client.post("/api/admin/schedule-test", json={"enabled": True},
                        headers={"X-CSRF-Token": _CSRF})
    assert empty.status_code == 400
    saved = client.post(
        "/api/admin/schedule-test",
        json={"enabled": True, "emails": ["menny@x.com", "other@x.com", "bad"]},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["enabled"] is True
    assert body["emails"] == ["menny@x.com", "other@x.com"]
    banner = client.get("/schedules").get_data(as_text=True)
    assert "Test mode is on" in banner
    assert "menny@x.com" in banner


def test_schedule_copy_is_inactive_duplicate(tmp_path):
    app = _make_app(tmp_path, rows_by_report=_ordered_rows())
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/schedules", json={
        "report_key": "ordered", "recipients": "a@x.com",
        "cadence": {"freq": "daily", "time": "08:00"},
        "filename_template": "{Report}_{Period}",
        "params": {"period": "yesterday"}},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    sid = created.get_json()["id"]
    copied = client.post(f"/api/schedules/{sid}/copy", headers={"X-CSRF-Token": _CSRF})
    assert copied.status_code == 201
    copy_id = copied.get_json()["id"]
    assert copy_id != sid
    from web.data.repositories.schedules import ScheduleRepository
    repo = ScheduleRepository(app.config["DB"])
    uid = UserRepository(app.config["DB"]).get_by_email("admin@x.com").id
    original = repo.get(sid, uid)
    clone = repo.get(copy_id, uid)
    assert original.is_active is True
    assert clone.is_active is False
    assert clone.recipients == "a@x.com"
    assert clone.filename_template == "{Report}_{Period}"
    assert clone.params["period"] == "yesterday"


def test_master_schedule_copy_is_inactive_unique_name(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/master-schedules", json={
        "name": "CopySrc Ordered", "report_key": "ordered",
        "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "09:00"},
        "params": {"period": "yesterday", "split_by_salesman": True},
        "layout": {"order": ["invoices"]},
        "filename_template": "{Schedule}_{YYYY}-{MM}-{DD}",
        "sharepoint_path": "Direct Reports/Ordered",
        "is_shared": True,
    }, headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    sid = created.get_json()["id"]
    copied = client.post(f"/api/master-schedules/{sid}/copy", headers={"X-CSRF-Token": _CSRF})
    assert copied.status_code == 201
    copy_id = copied.get_json()["id"]
    assert copy_id != sid
    from web.data.repositories.schedules import MasterScheduleRepository
    repo = MasterScheduleRepository(app.config["DB"])
    original = repo.get(sid)
    clone = repo.get(copy_id)
    assert original.is_active is True
    assert clone.is_active is False
    assert clone.name == "CopySrc Ordered (copy)"
    assert clone.recipients == "team@x.com"
    assert clone.sharepoint_path == "Ordered"
    assert clone.filename_template == "{Schedule}_{YYYY}-{MM}-{DD}"
    assert clone.params["period"] == "yesterday"
    assert clone.params["split_by_salesman"] is True
    assert clone.layout["order"] == ["invoices"]
    assert clone.is_shared is True
    assert clone.run_as_user_id == original.run_as_user_id
    owner = UserRepository(app.config["DB"]).get_by_email("admin@x.com")
    assert clone.owner_user_id == owner.id
    again = client.post(f"/api/master-schedules/{sid}/copy", headers={"X-CSRF-Token": _CSRF})
    assert again.status_code == 201
    assert repo.get(again.get_json()["id"]).name == "CopySrc Ordered (copy 2)"
    html = client.get("/schedules").get_data(as_text=True)
    assert f"/api/master-schedules/{sid}/copy" in html


def test_master_schedule_save_strips_direct_reports_prefix(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/master-schedules", json={
        "name": "Prefixed folder", "report_key": "ordered",
        "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Direct Reports/Direct Reports/Ordered Report/Daily",
        "is_shared": True,
    }, headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    from web.data.repositories.schedules import MasterScheduleRepository
    row = MasterScheduleRepository(app.config["DB"]).get(created.get_json()["id"])
    assert row.sharepoint_path == "Ordered Report/Daily"


def test_master_schedule_copy_forbidden_unless_can_edit(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    created = admin.post("/api/master-schedules", json={
        "name": "Admin nightly copygate", "report_key": "ordered",
        "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "06:00"}, "is_shared": True,
    }, headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    admin_id = created.get_json()["id"]

    mgr = app.test_client()
    _login(mgr, app, email="mgr@x.com", role="manager")
    assert mgr.post(f"/api/master-schedules/{admin_id}/copy",
                    headers={"X-CSRF-Token": _CSRF}).status_code == 403
    mgr_html = mgr.get("/schedules").get_data(as_text=True)
    assert f"/api/master-schedules/{admin_id}/copy" not in mgr_html

    own = mgr.post("/api/master-schedules", json={
        "name": "Mgr copyable", "report_key": "ordered", "recipients": "m@x.com",
        "cadence": {"freq": "daily", "time": "07:00"}, "is_shared": True,
    }, headers={"X-CSRF-Token": _CSRF})
    assert own.status_code == 201
    own_id = own.get_json()["id"]
    copied = mgr.post(f"/api/master-schedules/{own_id}/copy",
                      headers={"X-CSRF-Token": _CSRF})
    assert copied.status_code == 201
    from web.data.repositories.schedules import MasterScheduleRepository
    clone = MasterScheduleRepository(app.config["DB"]).get(copied.get_json()["id"])
    assert clone.name == "Mgr copyable (copy)"
    assert clone.is_active is False
    assert f"/api/master-schedules/{own_id}/copy" in mgr.get("/schedules").get_data(as_text=True)

    rep = app.test_client()
    _login(rep, app, email="rep@x.com", role="salesman")
    assert rep.post(f"/api/master-schedules/{admin_id}/copy",
                    headers={"X-CSRF-Token": _CSRF}).status_code == 403


def test_master_run_now_writes_outbox_and_history(tmp_path):
    app = _make_app(tmp_path, rows_by_report=_ordered_rows())
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/master-schedules", json={
        "name": "DailyInvoicedReport", "report_key": "ordered",
        "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "05:00"},
        "params": {"period": "all_time"}},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    mid = created.get_json()["id"]
    run = client.post(f"/api/master-schedules/{mid}/run", headers={"X-CSRF-Token": _CSRF})
    assert run.status_code == 202
    from web.data.repositories.jobs import JobRepository
    from web.data.repositories.schedules import MASTER, ScheduleRunRepository
    job = JobRepository(app.config["DB"]).get(run.get_json()["job_id"])
    assert job is not None and job.status == "success"
    hist_rows = ScheduleRunRepository(app.config["DB"]).list_for_schedule(mid, MASTER)
    assert hist_rows and hist_rows[0].status == "success"
    hist = client.get(f"/master-schedules/{mid}/history").get_data(as_text=True).lower()
    assert "success" in hist
    from web.data.repositories.outbox import OutboxRepository
    rows = OutboxRepository(app.config["DB"]).list_recent()
    assert rows and "team@x.com" in rows[0].recipients
    assert "[TEST]" not in rows[0].subject
    assert list((tmp_path / "outbox").glob("*.eml"))
    page = client.get("/schedules").get_data(as_text=True)
    start = page.find('<details class="run-log-panel"')
    end = page.find(">", start)
    assert start != -1 and "open" not in page[start:end]


def test_master_run_now_test_mode_mails_test_list_only(tmp_path):
    app = _make_app(tmp_path, rows_by_report=_ordered_rows())
    client = app.test_client()
    _login(client, app)
    saved = client.post(
        "/api/admin/schedule-test",
        json={"enabled": True, "emails": ["menny@x.com"]},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert saved.status_code == 200
    created = client.post("/api/master-schedules", json={
        "name": "DailyInvoicedReport", "report_key": "ordered",
        "recipients": "customers@x.com",
        "sharepoint_path": "Direct Reports/Invoiced Report/Daily",
        "cadence": {"freq": "daily", "time": "05:00"},
        "params": {"period": "all_time", "email_cc": "cc@x.com"}},
        headers={"X-CSRF-Token": _CSRF})
    mid = created.get_json()["id"]
    run = client.post(f"/api/master-schedules/{mid}/run", headers={"X-CSRF-Token": _CSRF})
    assert run.status_code == 202
    from web.data.repositories.jobs import JobRepository
    job = JobRepository(app.config["DB"]).get(run.get_json()["job_id"])
    assert job is not None and job.status == "success"
    from web.data.repositories.outbox import OutboxRepository
    row = OutboxRepository(app.config["DB"]).list_recent()[0]
    assert row.recipients == "menny@x.com"
    assert row.subject.startswith("[TEST] ")
    assert "customers@x.com" not in row.recipients
    meta = row.sharepoint_meta or {}
    assert meta.get("saved") is True
    assert meta.get("path") == "Test"


def test_clock_tick_drains_personal_and_master_to_outbox(tmp_path):
    from datetime import datetime, timezone
    from web.data.repositories.jobs import JobRepository
    from web.data.repositories.schedules import MasterScheduleRepository, ScheduleRepository
    from web.data.repositories.users import UserRepository
    from web.scheduling.tick import enqueue_due

    app = _make_app(tmp_path, rows_by_report=_ordered_rows())
    client = app.test_client()
    _login(client, app)
    uid = UserRepository(app.config["DB"]).get_by_email("admin@x.com").id
    db = app.config["DB"]
    ScheduleRepository(db).create(
        uid, "ordered", params={"period": "all_time"}, layout={},
        cadence={"freq": "daily", "time": "08:00"}, recipients="me@x.com")
    MasterScheduleRepository(db).create(
        "ordered", "Nightly", params={"period": "all_time"}, layout={},
        cadence={"freq": "daily", "time": "05:00"}, recipients="team@x.com")
    now = datetime(2026, 6, 1, 13, 0, tzinfo=timezone.utc)
    assert enqueue_due(db, JobRepository(db), now) == 2
    app.config["JOB_WORKER"].drain()
    from web.data.repositories.outbox import OutboxRepository
    recips = {r.recipients for r in OutboxRepository(db).list_recent()}
    assert "me@x.com" in recips
    assert "team@x.com" in recips
    assert len(list((tmp_path / "outbox").glob("*.eml"))) >= 2


def test_save_and_on_do_not_catch_up_todays_missed_slot(tmp_path):
    from datetime import datetime, timezone
    from web.data.repositories.jobs import JobRepository
    from web.data.repositories.schedules import MasterScheduleRepository
    from web.scheduling.tick import enqueue_due

    app = _make_app(tmp_path, rows_by_report=_ordered_rows())
    client = app.test_client()
    _login(client, app)
    created = client.post("/api/master-schedules", json={
        "name": "Wait for slot", "report_key": "ordered", "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "00:00"},
        "params": {"period": "all_time"}},
        headers={"X-CSRF-Token": _CSRF})
    assert created.status_code == 201
    mid = created.get_json()["id"]
    db = app.config["DB"]
    now = datetime.now(timezone.utc)
    assert enqueue_due(db, JobRepository(db), now) == 0

    client.post(f"/api/master-schedules/{mid}/toggle", json={"active": False},
                headers={"X-CSRF-Token": _CSRF})
    client.post(f"/api/master-schedules/{mid}/toggle", json={"active": True},
                headers={"X-CSRF-Token": _CSRF})
    assert enqueue_due(db, JobRepository(db), now) == 0

    client.put(f"/api/master-schedules/{mid}", json={
        "name": "Wait for slot", "report_key": "ordered", "recipients": "team@x.com",
        "cadence": {"freq": "daily", "time": "00:00"},
        "params": {"period": "all_time"}},
        headers={"X-CSRF-Token": _CSRF})
    assert enqueue_due(db, JobRepository(db), now) == 0
    row = MasterScheduleRepository(db).get(mid)
    assert row.last_claimed_at
    run = client.post(f"/api/master-schedules/{mid}/run", headers={"X-CSRF-Token": _CSRF})
    assert run.status_code == 202


def test_schedule_test_mode_forbidden_for_salesman(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    with client.session_transaction() as s:
        s["v3_user"] = {"email": "rep@x.com", "name": "Rep", "role": "salesman", "is_dev": True}
        s["_csrf_token"] = _CSRF
    resp = client.post(
        "/api/admin/schedule-test", json={"enabled": True, "emails": ["a@x.com"]},
        headers={"X-CSRF-Token": _CSRF},
    )
    assert resp.status_code == 403


def _clo_rows():
    return [
        {"Order Rank": 1, "Customer Account": "100", "Customer Name": "Acme",
         "Sales Order Number": "SO3", "PO #": "PO-9", "Order Date": "2026-03-10",
         "Salesman": "REdwards", "Item #": "ITM-A", "Description": "Widget",
         "Qty Ordered": 10, "Qty Shipped": 10, "Qty Cancelled": 0,
         "Sales Price": 2.00, "Total": 20.00},
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
    app = _make_app(tmp_path, rows_by_report={"customer_last_orders": _clo_rows()})
    client = app.test_client()
    _login(client, app)
    html = client.get("/report/customer-last-order/100").get_data(as_text=True)
    assert "Last Order" in html
    assert "SO3" in html and "ITM-A" in html
    assert "Acme" in html


def test_customer_last_order_recent_invoiced_api(tmp_path):
    app = _make_app(tmp_path, rows_by_report={"customer_last_orders": _clo_rows()})
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
    return {"customer_last_orders": [
        {"Order Rank": 1, "Customer Account": "100", "Customer Name": "Acme",
         "Sales Order Number": "SO3", "PO #": "PO-9", "Order Date": "2026-03-10",
         "Salesman": sales_group, "Item #": "ITM-A", "Description": "Widget",
         "Qty Ordered": 10, "Qty Shipped": 10, "Qty Cancelled": 0,
         "Sales Price": 2.00, "Total": 20.00},
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
    app = _make_app(tmp_path, rows_by_report={"customer_last_orders": _clo_rows()})
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


def test_salesman_invoiced_run_omits_commissions_tab(tmp_path):
    rows = [
        {"InvoiceNumber": "INV1", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-03-01", "SubTotal": "100", "SH_TariffCharges": "0",
         "FreightCharges": "0", "CCSurcharge": "0", "SalesGroup": "REdwards"},
    ]
    app = _make_app(tmp_path, rows_by_report={"invoiced_report": rows})
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    html = client.get("/reports/invoiced").get_data(as_text=True)
    assert 'data-hide-commissions="1"' in html
    job_id = client.post("/api/reports/invoiced/run", json={"year": "2026"},
                         headers={"X-CSRF-Token": _CSRF}).get_json()["job_id"]
    payload = client.get(f"/api/reports/result/{job_id}").get_json()
    assert "commissions" not in {t["key"] for t in payload["tabs"]}


def test_salesman_email_now_invoiced_skips_commissions(tmp_path):
    rows = [
        {"InvoiceNumber": "INV1", "InvoiceAccount": "100", "CustomerName": "Acme",
         "InvoiceDate": "2026-03-01", "SubTotal": "100", "SH_TariffCharges": "0",
         "FreightCharges": "0", "CCSurcharge": "0", "SalesGroup": "REdwards"},
    ]
    app = _make_app(tmp_path, rows_by_report={"invoiced_report": rows})
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    resp = client.post("/api/reports/invoiced/email-now",
                       json={"recipients": "rep@x.com", "subject": "Invoiced",
                             "params": {"year": "2026"}, "layout": {}},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 202
    job_id = resp.get_json()["job_id"]
    status = client.get(f"/api/jobs/{job_id}").get_json()
    assert status["status"] == "success"


def test_settings_hub_hides_admin_from_salesman(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    html = client.get("/settings").get_data(as_text=True)
    assert "container-narrow" in html
    assert "Customer exclusions" in html
    assert "Users &amp; access" not in html
    assert "Database explorer" not in html
    assert "Global report visibility" not in html


def test_settings_hub_admin_has_categories(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    html = client.get("/settings").get_data(as_text=True)
    assert "container-narrow" in html
    assert "Users &amp; access" in html
    assert "Global report visibility" in html
    assert "Scheduled run history" in html
    assert "Email Distributions" not in html
    assert "Database explorer" not in html  # admin is not developer


def test_report_visibility_api_and_history_pages(tmp_path):
    app = _make_app(tmp_path)
    client = app.test_client()
    _login(client, app)
    resp = client.post("/api/admin/report-visibility",
                       json={"report_key": "ordered", "enabled": False},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 200 and resp.get_json()["enabled"] is False
    assert client.get("/admin/schedule-runs").status_code == 200
    assert client.get("/admin/run-log").status_code == 200
    sales = app.test_client()
    _login(sales, app, email="rep@x.com", role="salesman")
    assert sales.post("/api/admin/report-visibility",
                      json={"report_key": "ordered", "enabled": True},
                      headers={"X-CSRF-Token": _CSRF}).status_code == 403
    assert sales.get("/admin/schedule-runs").status_code == 403


def test_settings_exclusion_does_not_need_dashboard(tmp_path):
    from web.data.repositories.dashboard import DashboardCustomer, DashboardRepository
    from web.data.repositories.exclusions import ExclusionRepository
    app = _make_app(tmp_path)
    DashboardRepository(app.config["DB"]).replace_all([
        DashboardCustomer("100", "Acme", "", "2026-05-01", 5, 30.0, 2.0, 32.0, 5, "active"),
    ])
    admin = app.test_client()
    _login(admin, app)
    assert "Acme" in admin.get("/settings").get_data(as_text=True)
    client = app.test_client()
    _login(client, app, email="rep@x.com", role="salesman")
    assert client.get("/settings").status_code == 200
    resp = client.post("/api/settings/exclusions",
                       json={"customer_account": "100", "excluded": True},
                       headers={"X-CSRF-Token": _CSRF})
    assert resp.status_code == 200
    uid = UserRepository(app.config["DB"]).get_by_email("rep@x.com").id
    assert "100" in ExclusionRepository(app.config["DB"]).get(uid)


def test_devtools_forbidden_for_admin_and_ok_for_developer(tmp_path):
    app = _make_app(tmp_path)
    admin = app.test_client()
    _login(admin, app)
    assert admin.get("/dev/db-explorer").status_code == 403
    assert admin.get("/dev/notif-diagnostic").status_code == 403
    dev = app.test_client()
    _login(dev, app, email="dev@x.com", role="developer")
    assert dev.get("/dev/db-explorer").status_code == 200
    tables = dev.get("/api/dev/db/tables?db=precious").get_json()["tables"]
    assert any(t["name"] == "users" for t in tables)
    html = dev.get("/settings").get_data(as_text=True)
    assert "Database explorer" in html and "Report data sources" in html
    assert "Beta report data sources" not in html
    # SQL-only: not on the Beta source selector. Global visibility still lists it.
    assert 'class="beta-source-select" data-key="sales_by_state"' not in html
    assert 'class="vis-toggle" data-key="sales_by_state"' in html
    assert dev.get("/dev/notif-diagnostic").status_code == 200
