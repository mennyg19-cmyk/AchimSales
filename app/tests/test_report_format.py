"""Report Formatter. Catalog columns only — never the office Reporting API."""

from __future__ import annotations

import report_format
import store
from tests.test_home import become, csrf_headers, login

pytest_plugins = ["tests.test_home"]


def test_ordered_tabs_come_from_catalog():
    tabs = {tab["key"]: tab for tab in report_format.tabs_for("ordered")}
    assert set(tabs) == {"summary", "by_customer", "by_item", "by_order", "by_salesman", "full_data"}
    fields = [col["field"] for col in tabs["summary"]["columns"]]
    assert "CustomerAccount" in fields
    assert report_format.tabs_for("nope") == []


def test_apply_format_keeps_other_layout_keys():
    merged = report_format.apply_format(
        {"views": {"summary": {"hidden": ["Open$"], "group": ["CustomerName"]}}},
        [{"key": "summary", "set_group": True, "group": [], "sorters": [{"column": "CustomerAccount", "dir": "desc"}]}],
    )
    summary = merged["views"]["summary"]
    assert summary["hidden"] == ["Open$"]
    assert summary["group"] == []
    assert summary["groups_explicit"] is True
    assert summary["sorters"] == [{"column": "CustomerAccount", "dir": "desc"}]


def test_run_stores_tabs_and_formatter_can_hide_them(client):
    login(client)
    ran = client.post("/api/reports/ordered/run", headers=csrf_headers(client), json={})
    assert ran.status_code == 200
    body = client.get("/api/dev/report-format", params={"report_key": "ordered"}).json()
    keys = [tab["key"] for tab in body["tabs"]]
    assert "summary" in keys
    assert any(col["field"] == "CustomerAccount" for col in body["tabs"][keys.index("summary")]["columns"])
    saved = client.post(
        "/api/dev/report-format",
        headers=csrf_headers(client),
        json={
            "report_key": "ordered",
            "format_name": "default",
            "tabs": [
                {"key": "summary", "show_tab": True, "hidden": ["Open$"], "set_group": False, "group": [], "sorters": [], "filters": []},
                {"key": "by_item", "show_tab": False, "hidden": [], "set_group": False, "group": [], "sorters": [], "filters": []},
            ],
        },
    )
    assert saved.status_code == 200
    layout = saved.json()["layout"]
    assert layout["order"] == ["summary"]
    assert layout["views"]["summary"]["hidden"] == ["Open$"]
    page = client.get("/dev/report-formatter").text
    assert "Show tab" in page
    assert "fmtCols" in page


def test_formatter_page_and_links(client):
    login(client)
    page = client.get("/dev/report-formatter")
    assert page.status_code == 200
    assert "fmtTabs" in page.text
    assert "+ Add" in page.text
    assert "Flat list" in page.text
    assert "Report Formatter" in client.get("/settings").text
    assert "Report Formatter" in client.get("/dev/db-explorer").text


def test_salesman_cannot_open_formatter(client):
    login(client)
    become(client, "salesman@achimonline.com")
    page = client.get("/dev/report-formatter", follow_redirects=False)
    assert page.status_code == 302
    api = client.get("/api/dev/report-format")
    assert api.status_code == 403


def test_admin_and_developer_see_every_users_view(client):
    login(client)
    view_id = store.add_view(
        "salesman@achimonline.com",
        "ordered",
        "Mine",
        "personal",
        {"period": "mtd"},
        0,
        {"views": {"summary": {"group": ["Salesman"], "groups_explicit": True}}},
    )
    body = client.get("/api/dev/report-format", params={"report_key": "ordered"}).json()
    labels = [row["label"] for row in body["formats"]]
    assert "Preview Salesman — Mine" in labels
    loaded = client.get(
        "/api/dev/report-format",
        params={"report_key": "ordered", "format": f"user:{view_id}"},
    ).json()
    assert loaded["layout"]["views"]["summary"]["group"] == ["Salesman"]

    store.add_user("dev.format@achimonline.com", "Dev Format", "developer", 0, "")
    become(client, "dev.format@achimonline.com")
    as_dev = client.get("/api/dev/report-format", params={"report_key": "ordered"}).json()
    assert "Preview Salesman — Mine" in [row["label"] for row in as_dev["formats"]]
    assert client.get("/dev/report-formatter").status_code == 200


def test_save_personal_keeps_period_and_company_format_leaves_default(client):
    login(client)
    view_id = store.add_view(
        "salesman@achimonline.com",
        "ordered",
        "Mine",
        "personal",
        {"period": "mtd"},
        1,
        {},
    )
    saved = client.post(
        "/api/dev/report-format",
        headers=csrf_headers(client),
        json={
            "report_key": "ordered",
            "format_name": f"user:{view_id}",
            "tabs": [{
                "key": "summary",
                "set_group": True,
                "group": ["CustomerName"],
                "sorters": [],
                "filters": [],
            }],
        },
    )
    assert saved.status_code == 200
    row = store.get_view(view_id)
    assert row["params"]["period"] == "mtd"
    assert row["layout"]["views"]["summary"]["group"] == ["CustomerName"]

    company = client.post(
        "/api/dev/report-format",
        headers=csrf_headers(client),
        json={
            "report_key": "ordered",
            "format_name": "Shelf",
            "tabs": [{
                "key": "summary",
                "set_group": True,
                "group": ["Salesman"],
                "sorters": [{"column": "CustomerAccount", "dir": "asc"}],
                "filters": [{"column": "CustomerName", "op": "contains", "v": "HD", "v2": ""}],
            }],
        },
    )
    assert company.status_code == 200
    assert company.json()["format_name"].startswith("company:")
    default = client.get("/api/dev/report-format", params={"report_key": "ordered"}).json()
    assert default["format_name"] == "default"
    assert "summary" not in (default["layout"].get("views") or {})
    shelf_id = company.json()["format_name"]
    shelf = client.get(
        "/api/dev/report-format",
        params={"report_key": "ordered", "format": shelf_id},
    ).json()
    assert shelf["layout"]["views"]["summary"]["group"] == ["Salesman"]
    assert shelf["layout"]["views"]["summary"]["columnFilters"]["CustomerName"]["v"] == "HD"
