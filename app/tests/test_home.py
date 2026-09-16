"""Dummy home-site tests. Mock JSON only — never call the office Reporting API."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from catalog import REPORTS
from db import db
from main import create_app
import store as home_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "home.sqlite"))
    monkeypatch.delenv("REPORTING_API_KEY", raising=False)
    monkeypatch.delenv("REPORTING_API_BASE_URL", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


def login(client: TestClient):
    res = client.post("/login/preview", follow_redirects=False)
    html = client.get("/").text
    match = re.search(r'data-csrf="([^"]+)"', html)
    assert match, "signed-in pages must expose data-csrf"
    client.csrf = match.group(1)
    return res


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.csrf}


def become(client: TestClient, email: str):
    row = home_store.get_user(email)
    res = client.post(
        f"/admin/users/{row['id']}/view-as",
        data={"csrf": client.csrf},
        follow_redirects=False,
    )
    assert res.status_code == 303
    html = client.get("/").text
    match = re.search(r'data-csrf="([^"]+)"', html)
    assert match
    client.csrf = match.group(1)


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
    assert 'id="customerPicker"' in page
    assert 'id="columnsBtn"' in page
    assert "Freeze pins it" in page
    assert 'id="reportStatus"' in page
    assert 'id="moreBtn"' in page
    assert "Audit - Reversals" in str(tabs)
    assert "totals_by_salesman" in tabs


def test_every_grid_report_returns_tabs(client):
    login(client)
    for item in REPORTS:
        if item["in_app"]:
            continue
        payload = client.post(f"/api/reports/{item['key']}/run", json={}, headers=csrf_headers(client)).json()
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
    assert "Dummy JSON" in html


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
        data={"email": "new.rep@achimonline.com", "role": "salesman", "display_name": "New Rep", "sales_group": "DDweck", "csrf": client.csrf},
        follow_redirects=False,
    )
    assert res.status_code == 303
    html = client.get("/admin/users").text
    assert "new.rep@achimonline.com" in html
    again = client.post(
        "/admin/users/add",
        data={"email": "new.rep@achimonline.com", "role": "salesman", "csrf": client.csrf},
        follow_redirects=True,
    )
    assert "already on the list" in again.text


def test_visibility_hides_card(client):
    login(client)
    client.post("/api/settings/visibility", json={"key": "sales_by_state", "enabled": False}, headers=csrf_headers(client))
    html = client.get("/").text
    assert "Sales by State" not in html
    hidden = client.get("/reports/sales_by_state", follow_redirects=False)
    assert hidden.status_code == 302


def test_save_view_and_schedule_run_now(client):
    login(client)
    created = client.post(
        "/api/views",
        json={"name": "My Invoiced", "report_key": "invoiced", "kind": "personal", "params": {"period": "mtd"}, "include_period": True},
        headers=csrf_headers(client),
    ).json()
    assert created["ok"]
    add = client.post(
        "/schedules/add",
        data={"view_id": created["id"], "freq": "daily", "run_time": "09:00", "recipients": "preview@achimonline.com", "csrf": client.csrf},
        follow_redirects=False,
    )
    assert add.status_code == 303
    schedules = client.get("/schedules").text
    assert "My Invoiced" in schedules
    # seeded Daily Ordered is id 2-ish; run the one we added via history list
    with db() as conn:
        row = conn.execute("SELECT id FROM schedules ORDER BY id DESC LIMIT 1").fetchone()
        sid = row["id"]
    client.post(f"/schedules/{sid}/run-now", data={"csrf": client.csrf}, follow_redirects=True)
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
    res = client.post("/api/reports/invoiced/email", json={"period": "last_7_days"}, headers=csrf_headers(client)).json()
    assert res["ok"]
    assert res["mock"] is True


def test_keep_job(client):
    login(client)
    payload = client.post("/api/reports/invoiced/run", json={}, headers=csrf_headers(client)).json()
    job_id = payload["data"]["job_id"]
    client.post(f"/api/jobs/{job_id}/keep", json={"name": "Friday pack"}, headers=csrf_headers(client))
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


def test_api_run_requires_csrf(client):
    login(client)
    res = client.post("/api/reports/invoiced/run", json={})
    assert res.status_code == 403


def test_login_next_rejects_offsite(client):
    html = client.get("/login?next=https://evil.example").text
    assert 'name="next" value="/"' in html
    res = client.post("/login/preview", data={"next": "//evil.example"}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/"


def test_disabled_magic_link_is_403(client):
    login(client)
    with db() as conn:
        conn.execute("UPDATE users SET is_active = 0 WHERE email = 'external@example.com'")
    client.post("/logout", data={"csrf": client.csrf})
    res = client.post("/login/magic-link", data={"email": "external@example.com"})
    assert res.status_code == 403


def test_copy_schedule(client):
    login(client)
    with db() as conn:
        row = conn.execute("SELECT id FROM schedules ORDER BY id LIMIT 1").fetchone()
        sid = row["id"]
    copied = client.post(f"/schedules/{sid}/copy", data={"csrf": client.csrf}, follow_redirects=False)
    assert copied.status_code == 303
    html = client.get("/schedules").text
    assert "Copied" in html or html.count("Run now") >= 2


def test_reporting_api_stub_without_key(client):
    login(client)
    res = client.post("/api/dev/reporting/invoiced_report/run", headers=csrf_headers(client))
    assert res.status_code == 501
    assert res.json()["mock"] is True


def test_exclusions_hide_last_order_customer(client):
    login(client)
    res = client.post(
        "/api/settings/exclusions",
        json={"accounts": ["C-1001"]},
        headers=csrf_headers(client),
    )
    assert res.status_code == 200
    pick = client.get("/report/customer-last-order").text
    assert "C-1001" not in pick
    assert "HD SUPPLY" not in pick
    hidden = client.get("/report/customer-last-order/C-1001", follow_redirects=False)
    assert hidden.status_code == 302


def test_salesman_cannot_read_others_jobs(client):
    login(client)
    payload = client.post("/api/reports/invoiced/run", json={}, headers=csrf_headers(client)).json()
    job_id = payload["data"]["job_id"]
    become(client, "salesman@achimonline.com")
    listed = client.get("/api/jobs").json()["jobs"]
    assert all(job["id"] != job_id for job in listed)
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    keep = client.post(
        f"/api/jobs/{job_id}/keep",
        json={"name": "stolen"},
        headers=csrf_headers(client),
    )
    assert keep.status_code == 404


def test_salesman_cannot_read_others_schedule_logs(client):
    login(client)
    with db() as conn:
        sid = conn.execute(
            "SELECT id FROM schedules WHERE owner_email = 'preview@achimonline.com' LIMIT 1"
        ).fetchone()["id"]
    client.post(f"/schedules/{sid}/run-now", data={"csrf": client.csrf}, follow_redirects=True)
    with db() as conn:
        run_id = conn.execute(
            "SELECT id FROM schedule_runs WHERE schedule_id = ? ORDER BY id DESC LIMIT 1",
            (sid,),
        ).fetchone()["id"]
    become(client, "salesman@achimonline.com")
    hist = client.get(f"/schedules/{sid}/history", follow_redirects=False)
    assert hist.status_code == 302
    log = client.get(f"/schedules/runs/{run_id}", follow_redirects=False)
    assert log.status_code == 302


def test_role_picker_is_privileged(client):
    login(client)
    become(client, "salesman@achimonline.com")
    res = client.get("/dev/role-picker", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["location"] == "/settings"


def test_hidden_report_hides_company_view_card(client):
    login(client)
    home = client.get("/").text
    assert "Daily Ordered" in home
    client.post(
        "/api/settings/visibility",
        json={"key": "ordered", "enabled": False},
        headers=csrf_headers(client),
    )
    html = client.get("/").text
    assert "Daily Ordered" not in html
    assert "/reports/ordered" not in html


def test_hidden_last_order_blocks_store_visit(client):
    login(client)
    client.post(
        "/api/settings/visibility",
        json={"key": "customer_last_order", "enabled": False},
        headers=csrf_headers(client),
    )
    pick = client.get("/report/customer-last-order", follow_redirects=False)
    assert pick.status_code == 302
    visit = client.get("/report/customer-last-order/C-1001", follow_redirects=False)
    assert visit.status_code == 302
    assert "SO-88021" not in (visit.text or "")


def test_salesman_cannot_copy_others_schedule(client):
    login(client)
    with db() as conn:
        sid = conn.execute(
            "SELECT id FROM schedules WHERE owner_email = 'preview@achimonline.com' LIMIT 1"
        ).fetchone()["id"]
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM schedules WHERE owner_email = 'salesman@achimonline.com'"
        ).fetchone()["n"]
    become(client, "salesman@achimonline.com")
    copied = client.post(
        f"/schedules/{sid}/copy",
        data={"csrf": client.csrf},
        follow_redirects=False,
    )
    assert copied.status_code == 303
    with db() as conn:
        after = conn.execute(
            "SELECT COUNT(*) AS n FROM schedules WHERE owner_email = 'salesman@achimonline.com'"
        ).fetchone()["n"]
    assert after == before


def test_salesman_cannot_schedule_others_personal_view(client):
    login(client)
    created = client.post(
        "/api/views",
        json={
            "name": "Admin only view",
            "report_key": "invoiced",
            "kind": "personal",
            "params": {"period": "mtd"},
            "include_period": True,
        },
        headers=csrf_headers(client),
    ).json()
    view_id = created["id"]
    become(client, "salesman@achimonline.com")
    with db() as conn:
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM schedules WHERE owner_email = 'salesman@achimonline.com'"
        ).fetchone()["n"]
    add = client.post(
        "/schedules/add",
        data={
            "view_id": view_id,
            "freq": "daily",
            "run_time": "09:00",
            "recipients": "salesman@achimonline.com",
            "csrf": client.csrf,
        },
        follow_redirects=False,
    )
    assert add.status_code == 303
    with db() as conn:
        after = conn.execute(
            "SELECT COUNT(*) AS n FROM schedules WHERE owner_email = 'salesman@achimonline.com'"
        ).fetchone()["n"]
    assert after == before


def test_pwa_icons_and_manifest(client):
    manifest = client.get("/manifest.json").json()
    assert manifest["theme_color"] == "#2563eb"
    icon_192 = client.get("/static/icon-192.png")
    icon_512 = client.get("/static/icon-512.png")
    assert icon_192.status_code == 200
    assert icon_512.status_code == 200
    assert icon_192.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert icon_512.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_extra_sales_group_opens_last_order_customers(client):
    login(client)
    row = home_store.get_user("salesman@achimonline.com")
    saved = client.post(
        f"/admin/users/{row['id']}/edit",
        data={
            "csrf": client.csrf,
            "display_name": "Preview Salesman",
            "role": "salesman",
            "sales_group": "HKaufman",
            "is_active": "1",
            "extra_groups": ["DDweck"],
        },
        follow_redirects=False,
    )
    assert saved.status_code == 303
    become(client, "salesman@achimonline.com")
    pick = client.get("/report/customer-last-order").text
    assert "HD SUPPLY" in pick
    visit = client.get("/report/customer-last-order/C-1001")
    assert "SO-88021" in visit.text


def test_report_allow_overrides_global_visibility(client):
    login(client)
    row = home_store.get_user("salesman@achimonline.com")
    client.post(
        "/api/settings/visibility",
        json={"key": "ordered", "enabled": False},
        headers=csrf_headers(client),
    )
    client.post(
        f"/admin/users/{row['id']}/edit",
        data={
            "csrf": client.csrf,
            "display_name": "Preview Salesman",
            "role": "salesman",
            "sales_group": "HKaufman",
            "is_active": "1",
            "report_access_ordered": "allow",
        },
        follow_redirects=False,
    )
    become(client, "salesman@achimonline.com")
    html = client.get("/").text
    assert "Ordered" in html
    assert "/reports/ordered" in html


def test_report_deny_hides_card(client):
    login(client)
    row = home_store.get_user("salesman@achimonline.com")
    client.post(
        f"/admin/users/{row['id']}/edit",
        data={
            "csrf": client.csrf,
            "display_name": "Preview Salesman",
            "role": "salesman",
            "sales_group": "HKaufman",
            "is_active": "1",
            "report_access_invoiced": "deny",
        },
        follow_redirects=False,
    )
    become(client, "salesman@achimonline.com")
    html = client.get("/").text
    assert "/reports/invoiced" not in html


def test_item_averages_allow_still_admin_only(client):
    login(client)
    row = home_store.get_user("salesman@achimonline.com")
    client.post(
        f"/admin/users/{row['id']}/edit",
        data={
            "csrf": client.csrf,
            "display_name": "Preview Salesman",
            "role": "salesman",
            "sales_group": "HKaufman",
            "is_active": "1",
            "report_access_item_averages": "allow",
        },
        follow_redirects=False,
    )
    become(client, "salesman@achimonline.com")
    assert client.get("/reports/item_averages", follow_redirects=False).status_code == 302
    run = client.post("/api/reports/item_averages/run", json={}, headers=csrf_headers(client))
    assert run.status_code == 404


def test_manager_sees_company_schedules_not_others_personal(client):
    login(client)
    created = client.post(
        "/api/views",
        json={
            "name": "Admin personal for manager test",
            "report_key": "invoiced",
            "kind": "personal",
            "params": {"period": "mtd"},
        },
        headers=csrf_headers(client),
    ).json()
    client.post(
        "/schedules/add",
        data={
            "view_id": created["id"],
            "freq": "daily",
            "run_time": "07:00",
            "recipients": "preview@achimonline.com",
            "csrf": client.csrf,
        },
        follow_redirects=False,
    )
    become(client, "manager@achimonline.com")
    html = client.get("/schedules").text
    assert "Daily Ordered" in html
    assert "Admin personal for manager test" not in html


def test_schedule_delivery_fields_land_in_outbox(client):
    login(client)
    with db() as conn:
        view_id = conn.execute(
            "SELECT id FROM views WHERE name = 'Daily Ordered' AND kind = 'company'"
        ).fetchone()["id"]
    add = client.post(
        "/schedules/add",
        data={
            "view_id": view_id,
            "freq": "weekly",
            "run_time": "09:15",
            "weekdays": ["mon", "wed"],
            "recipients": "preview@achimonline.com",
            "cc": "cc@achimonline.com",
            "bcc": "bcc@achimonline.com",
            "subject": "[MOCK] weekly",
            "filename": "{Schedule}.xlsx",
            "sharepoint_folder": "/Reports/Dummy",
            "onedrive_folder": "/OneDrive/Dummy",
            "csrf": client.csrf,
        },
        follow_redirects=False,
    )
    assert add.status_code == 303
    with db() as conn:
        sid = conn.execute(
            "SELECT id FROM schedules WHERE filename = '{Schedule}.xlsx' ORDER BY id DESC LIMIT 1"
        ).fetchone()["id"]
    client.post(f"/schedules/{sid}/run-now", data={"csrf": client.csrf}, follow_redirects=True)
    diag = client.get("/dev/notif-diagnostic").text
    assert "CC cc@achimonline.com" in diag
    assert "file Daily Ordered.xlsx" in diag
    assert "SharePoint /Reports/Dummy" in diag
    assert "OneDrive /OneDrive/Dummy" in diag
    sched = client.get("/schedules").text
    assert "Clock skips Shabbos and Yom Tov" in sched
    assert 'href="/schedules/runs/' in sched
    assert "Step 1 of 3" in sched
    assert "OneDrive folder" in sched


def test_master_schedule_history_and_diagnostics(client):
    login(client)
    with db() as conn:
        sid = conn.execute("SELECT id FROM schedules ORDER BY id LIMIT 1").fetchone()["id"]
    hist = client.get(f"/master-schedules/{sid}/history")
    assert hist.status_code == 200
    assert "Daily Ordered" in hist.text or "when" in hist.text.lower()
    diag = client.get("/dev/diagnostics")
    assert diag.status_code == 200
    assert "P4.I8" in diag.text


def test_dashboard_flag_does_not_add_nav(client):
    login(client)
    row = home_store.get_user("preview@achimonline.com")
    client.post(
        f"/admin/users/{row['id']}/edit",
        data={
            "csrf": client.csrf,
            "display_name": "Preview Admin",
            "role": "admin",
            "is_active": "1",
            "dashboard_enabled": "1",
            "test_access": "1",
        },
        follow_redirects=False,
    )
    users = client.get("/admin/users").text
    assert "Dashboard" in users
    assert "Test" in users
    home = client.get("/").text
    assert "bottom-nav-label\">Dashboard" not in home
    assert "/dashboard" not in home


def test_cannot_delete_own_login(client):
    login(client)
    row = home_store.get_user("preview@achimonline.com")
    res = client.post(
        f"/admin/users/{row['id']}/delete",
        data={"csrf": client.csrf},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert home_store.get_user("preview@achimonline.com") is not None


def test_manager_cannot_run_others_personal_schedule(client):
    login(client)
    created = client.post(
        "/api/views",
        json={
            "name": "Admin personal IDOR bait",
            "report_key": "invoiced",
            "kind": "personal",
            "params": {"period": "mtd"},
        },
        headers=csrf_headers(client),
    ).json()
    client.post(
        "/schedules/add",
        data={
            "view_id": created["id"],
            "freq": "daily",
            "run_time": "07:00",
            "recipients": "preview@achimonline.com",
            "csrf": client.csrf,
        },
        follow_redirects=False,
    )
    with db() as conn:
        sid = conn.execute(
            "SELECT id FROM schedules WHERE view_id = ? ORDER BY id DESC LIMIT 1",
            (created["id"],),
        ).fetchone()["id"]
        company = conn.execute(
            "SELECT s.id FROM schedules s JOIN views v ON v.id = s.view_id "
            "WHERE v.kind = 'company' LIMIT 1"
        ).fetchone()["id"]
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM schedule_runs WHERE schedule_id = ?",
            (sid,),
        ).fetchone()["n"]
    become(client, "manager@achimonline.com")
    blocked = client.post(
        f"/schedules/{sid}/run-now",
        data={"csrf": client.csrf},
        follow_redirects=False,
    )
    assert blocked.status_code == 303
    with db() as conn:
        after = conn.execute(
            "SELECT COUNT(*) AS n FROM schedule_runs WHERE schedule_id = ?",
            (sid,),
        ).fetchone()["n"]
    assert after == before
    company_run = client.post(
        f"/schedules/{company}/run-now",
        data={"csrf": client.csrf},
        follow_redirects=False,
    )
    assert company_run.status_code == 303
    with db() as conn:
        company_runs = conn.execute(
            "SELECT COUNT(*) AS n FROM schedule_runs WHERE schedule_id = ?",
            (company,),
        ).fetchone()["n"]
    assert company_runs >= 1


def test_salesman_cannot_schedule_company_view(client):
    login(client)
    with db() as conn:
        view_id = conn.execute(
            "SELECT id FROM views WHERE name = 'Daily Ordered' AND kind = 'company'"
        ).fetchone()["id"]
    become(client, "salesman@achimonline.com")
    with db() as conn:
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM schedules WHERE owner_email = 'salesman@achimonline.com'"
        ).fetchone()["n"]
    add = client.post(
        "/schedules/add",
        data={
            "view_id": view_id,
            "freq": "daily",
            "run_time": "09:00",
            "recipients": "salesman@achimonline.com",
            "csrf": client.csrf,
        },
        follow_redirects=False,
    )
    assert add.status_code == 303
    with db() as conn:
        after = conn.execute(
            "SELECT COUNT(*) AS n FROM schedules WHERE owner_email = 'salesman@achimonline.com'"
        ).fetchone()["n"]
    assert after == before
    html = client.get("/schedules").text
    assert "Daily Ordered" not in html


def test_invoiced_hides_totals_for_one_salesman(client):
    login(client)
    kaufman = client.post(
        "/api/reports/invoiced/run",
        json={"salesman": "HKaufman"},
        headers=csrf_headers(client),
    ).json()["data"]["tabs"]
    assert "totals_by_salesman" not in kaufman
    assert "audit_reversals" not in kaufman
    dweck = client.post(
        "/api/reports/invoiced/run",
        json={"salesman": "DDweck"},
        headers=csrf_headers(client),
    ).json()["data"]["tabs"]
    assert "totals_by_salesman" not in dweck
    assert "audit_reversals" in dweck


def test_invoiced_filters_apply_to_every_tab(client):
    login(client)
    dweck = client.post(
        "/api/reports/invoiced/run",
        json={"salesman": "DDweck"},
        headers=csrf_headers(client),
    ).json()["data"]["tabs"]
    details = {row["CustomerName"] for row in dweck["full_details"]["rows"]}
    assert "HD SUPPLY" in details
    assert "AMAZON.COM DEDC, LLC" not in details
    assert {row["Salesman"] for row in dweck["commissions"]["rows"]} == {"DDweck"}
    assert {row["InvoiceNumber"] for row in dweck["invoices"]["rows"]} == {"IN01008282"}
    hd = client.post(
        "/api/reports/invoiced/run",
        json={"customers": ["C-1001"]},
        headers=csrf_headers(client),
    ).json()["data"]["tabs"]
    assert {row["CustomerAccount"] for row in hd["full_details"]["rows"]} == {"C-1001"}
    assert {row["CustomerAccount"] for row in hd["summary_by_customer"]["rows"]} == {"C-1001"}
    assert "audit_reversals" not in hd
    assert "totals_by_salesman" not in hd


def test_save_view_for_other_user_and_group_array(client):
    login(client)
    bad = client.post(
        "/api/views",
        json={"name": "Bad group", "report_key": "invoiced", "params": {"group": "Salesman"}},
        headers=csrf_headers(client),
    )
    assert bad.status_code == 400
    assert "array" in bad.json()["error"]
    ok = client.post(
        "/api/views",
        json={
            "name": "Salesman copy",
            "report_key": "invoiced",
            "kind": "personal",
            "for_email": "salesman@achimonline.com",
            "params": {"period": "mtd", "group": ["Salesman"]},
            "include_period": True,
        },
        headers=csrf_headers(client),
    )
    assert ok.status_code == 200
    become(client, "salesman@achimonline.com")
    views = client.get("/api/views?report=invoiced").json()["views"]
    names = {view["name"] for view in views}
    assert "Salesman copy" in names
    copied = next(view for view in views if view["name"] == "Salesman copy")
    assert copied["layout"]["views"]["_default"]["group"] == ["Salesman"]


def test_last_order_recent_invoices_and_xlsx(client):
    login(client)
    html = client.get("/report/customer-last-order/C-1001").text
    assert "Recent invoiced" in html
    assert "IN01008282" in html
    xlsx = client.get("/report/customer-last-order/C-1001/xlsx")
    assert xlsx.status_code == 200
    assert xlsx.content[:2] == b"PK"


def test_cancel_running_job(client):
    login(client)
    job_id = home_store.save_job("invoiced", "Invoiced", {"data": {"tabs": {}}}, owner_email="preview@achimonline.com", status="running")
    res = client.post(f"/api/jobs/{job_id}/cancel", headers=csrf_headers(client))
    assert res.status_code == 200
    assert home_store.get_job(job_id)["status"] == "cancelled"
    done = client.post("/api/reports/invoiced/run", json={}, headers=csrf_headers(client)).json()
    finished_id = done["data"]["job_id"]
    again = client.post(f"/api/jobs/{finished_id}/cancel", headers=csrf_headers(client))
    assert again.status_code == 409


def test_explorer_write_confirm(client):
    login(client)
    drop = client.post(
        "/dev/db-explorer",
        data={"sql": "DROP TABLE users", "csrf": client.csrf},
        follow_redirects=True,
    )
    assert "DROP/ALTER" in drop.text
    write = client.post(
        "/dev/db-explorer",
        data={"sql": "UPDATE views SET name = name", "csrf": client.csrf},
        follow_redirects=True,
    )
    assert "Confirm write" in write.text
    listed = client.post(
        "/dev/db-explorer",
        data={"sql": "SELECT id, name, period FROM views", "csrf": client.csrf},
        follow_redirects=True,
    )
    assert listed.status_code == 200
    assert "Daily Ordered" in listed.text
    assert "params_json" not in listed.text
    assert "JSON editor" not in listed.text
    cte = client.post(
        "/dev/db-explorer",
        data={
            "sql": "WITH x AS (SELECT 1 AS n) UPDATE views SET name = name",
            "csrf": client.csrf,
        },
        follow_redirects=True,
    )
    assert "Confirm write" in cte.text


def test_delete_named_view(client):
    login(client)
    created = client.post(
        "/api/views",
        json={"name": "Throwaway", "report_key": "invoiced", "params": {}},
        headers=csrf_headers(client),
    ).json()
    view_id = created["id"]
    gone = client.post(f"/api/views/{view_id}/delete", headers=csrf_headers(client))
    assert gone.status_code == 200
    assert gone.json() == {"ok": True}
    leftover = [view["id"] for view in client.get("/api/views?report=invoiced").json()["views"]]
    assert view_id not in leftover
