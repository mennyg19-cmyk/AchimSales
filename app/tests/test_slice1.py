"""Slice 1 tests. Mock JSON only — never call the office Reporting API."""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


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


def test_invoiced_mock_requires_login(client):
    assert client.get("/api/reports/invoiced/mock").status_code == 401


def test_preview_login_then_invoiced_tabs(client):
    client.post("/login/preview", follow_redirects=False)
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


def test_settings_you(client):
    client.post("/login/preview", follow_redirects=False)
    html = client.get("/settings").text
    assert "Preview Admin" in html
    assert "Appearance" in html
    assert "Monochrome Dark" in html


def test_production_preview_login_blocked(client, monkeypatch):
    monkeypatch.setattr("main.PRODUCTION", True)
    res = client.post("/login/preview")
    assert res.status_code == 403
