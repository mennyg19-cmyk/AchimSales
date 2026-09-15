"""Dummy home-site tests. Mock JSON only — never call the office Reporting API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from catalog import REPORTS
from main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.delenv("REPORTING_API_KEY", raising=False)
    monkeypatch.delenv("REPORTING_API_BASE_URL", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


def login(client: TestClient):
    return client.post("/login/preview", follow_redirects=False)


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_beta_redirects_home(client):
    res = client.get("/beta", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/"


def test_always_on_root(client):
    res = client.get("/", headers={"User-Agent": "AlwaysOn"})
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_login_looks_like_v3(client):
    html = client.get("/login").text
    assert "Sales Reports" in html
    assert "Achim User Login" in html
    assert "External Rep Login" in html
    assert "Sign in to continue" in html
    assert "This preview does not send mail" in html
    assert "Send sign-in link" not in html


def test_invoiced_mock_requires_login(client):
    assert client.get("/api/reports/invoiced/mock").status_code == 401


def test_preview_login_then_invoiced_tabs(client):
    login(client)
    payload = client.get("/api/reports/invoiced/mock").json()
    data = payload["data"]
    assert data["report_key"] == "invoiced"
    assert "raw" in data
    tabs = data["tabs"]
    assert "full_details" in tabs
    names = {row["CustomerName"] for row in tabs["full_details"]["rows"]}
    assert "HD SUPPLY" in names
    page = client.get("/reports/invoiced").text
    assert "tabulator" in page.lower()
    assert "Run report" in page
    assert 'id="reportTable"' in page


def test_every_grid_report_returns_tabs(client):
    login(client)
    for item in REPORTS:
        if item["in_app"]:
            continue
        payload = client.post(f"/api/reports/{item['key']}/run", json={}).json()
        tabs = payload["data"]["tabs"]
        assert tabs, item["key"]
        first = next(iter(tabs.values()))
        assert "name" in first
        assert "rows" in first
        html = client.get(f"/reports/{item['key']}").text
        assert "Run report" in html
        assert item["title"] in html


def test_home_lists_all_cards(client):
    login(client)
    html = client.get("/").text
    for title in ("Ordered", "Invoiced", "Salesman", "Number 4", "Customer Activity",
                  "Item Averages", "Sales by State", "Customer Aging"):
        assert title in html
    assert "Last Order" in html
    assert "/report/customer-last-order" in html
    assert "Coming soon" in html
    assert "Daily Ordered" in html
    assert "Daily Invoiced" in html


def test_last_order_store_visit(client):
    login(client)
    pick = client.get("/report/customer-last-order").text
    assert "HD SUPPLY" in pick
    view = client.get("/report/customer-last-order/C-1001").text
    assert "SO-88021" in view
    assert "Widget" in view


def test_settings_hub_admin_sections(client):
    login(client)
    html = client.get("/settings").text
    assert "Preview Admin" in html
    assert "Users &amp; access" in html or "Users & access" in html
    assert "Global report visibility" in html
    assert "Schedule test mode" in html
    assert "Report run log" in html
    assert "Monochrome Dark" in html


def test_add_user_no_self_register(client):
    login(client)
    res = client.post(
        "/admin/users/add",
        data={"email": "new.rep@achimonline.com", "role": "salesman", "display_name": "New Rep", "sales_group": "DDweck"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    html = client.get("/admin/users").text
    assert "new.rep@achimonline.com" in html
    again = client.post(
        "/admin/users/add",
        data={"email": "new.rep@achimonline.com", "role": "salesman"},
        follow_redirects=True,
    )
    assert "already on the list" in again.text


def test_visibility_hides_card(client):
    login(client)
    client.post("/api/settings/visibility", json={"key": "sales_by_state", "enabled": False})
    html = client.get("/").text
    assert "Sales by State" not in html
    hidden = client.get("/reports/sales_by_state", follow_redirects=False)
    assert hidden.status_code == 302


def test_save_view_and_schedule_run_now(client):
    login(client)
    created = client.post(
        "/api/views",
        json={"name": "My Invoiced", "report_key": "invoiced", "kind": "personal", "params": {"period": "mtd"}, "include_period": True},
    ).json()
    assert created["ok"]
    add = client.post(
        "/schedules/add",
        data={"view_id": created["id"], "freq": "daily", "run_time": "09:00", "recipients": "preview@achimonline.com"},
        follow_redirects=False,
    )
    assert add.status_code == 303
    schedules = client.get("/schedules").text
    assert "My Invoiced" in schedules
    # seeded Daily Ordered is id 2-ish; run the one we added via history list
    from db import db
    with db() as conn:
        row = conn.execute("SELECT id FROM schedules ORDER BY id DESC LIMIT 1").fetchone()
        sid = row["id"]
    client.post(f"/schedules/{sid}/run-now", follow_redirects=True)
    outbox = client.get("/dev/notif-diagnostic").text
    assert "[MOCK]" in outbox
    assert "preview@achimonline.com" in outbox
    with db() as conn:
        run = conn.execute("SELECT id FROM schedule_runs ORDER BY id DESC LIMIT 1").fetchone()
        run_id = run["id"]
    log = client.get(f"/schedules/runs/{run_id}")
    assert log.status_code == 200
    assert "Time" in log.text
    assert "Step" in log.text
    assert "Detail" in log.text
    history = client.get(f"/schedules/{sid}/history")
    assert history.status_code == 200
    assert f"/schedules/runs/{run_id}" in history.text


def test_xlsx_export(client):
    login(client)
    res = client.get("/api/reports/ordered/xlsx")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert res.content[:2] == b"PK"


def test_email_me_writes_outbox(client):
    login(client)
    res = client.post("/api/reports/invoiced/email", json={"period": "last_7_days"}).json()
    assert res["ok"]
    assert res["mock"] is True


def test_keep_job(client):
    login(client)
    payload = client.post("/api/reports/invoiced/run", json={}).json()
    job_id = payload["data"]["job_id"]
    client.post(f"/api/jobs/{job_id}/keep", json={"name": "Friday pack"})
    jobs = client.get("/api/jobs?kept=1").json()["jobs"]
    assert any(job["keep_name"] == "Friday pack" for job in jobs)


def test_magic_link_external_preview(client):
    res = client.post("/login/magic-link", data={"email": "external@example.com"}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/"
    home = client.get("/").text
    assert "Preview External" in home
    assert "Item Averages" not in home


def test_production_preview_login_blocked(client, monkeypatch):
    monkeypatch.setattr("config.PRODUCTION", True)
    res = client.post("/login/preview")
    assert res.status_code == 403


def test_reporting_api_refuses_website_host(monkeypatch):
    monkeypatch.setenv("REPORTING_API_BASE_URL", "https://reports.achimonline.com")
    from config import reporting_api_base
    with pytest.raises(RuntimeError, match="office doorway"):
        reporting_api_base()
