"""Unit tests for Beta source map + access helpers."""

from __future__ import annotations

import sqlite3

import pytest

from webapp import db as live_db


@pytest.fixture()
def live_mem_db(monkeypatch, tmp_path):
    path = tmp_path / "live.db"
    monkeypatch.setattr(live_db, "DB_PATH", str(path))
    live_db.init_db()
    return path


def test_beta_sources_default_signed_off_sql(live_mem_db, monkeypatch):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "v3" / "web" / "beta_sources.py"
    spec = importlib.util.spec_from_file_location("beta_sources", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    sources = mod.get_sources()
    assert sources["ordered"] == "sql"
    assert sources["invoiced"] == "sql"
    assert sources["customer_activity"] == "sql"
    assert sources["number_4"] == "odata"


def test_beta_sources_set_and_read(live_mem_db):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "v3" / "web" / "beta_sources.py"
    spec = importlib.util.spec_from_file_location("beta_sources", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    mod.set_source("number_4", "sql")
    assert mod.get_source("number_4") == "sql"
    mod.set_source("number_4", "odata")
    assert mod.get_source("number_4") == "odata"


def test_beta_access_respects_flag(live_mem_db):
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "v3" / "web" / "beta_access.py"
    spec = importlib.util.spec_from_file_location("beta_access", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    live_db.add_user("beta.user@example.com", "salesman", None, "Beta User")
    assert mod.user_has_beta_access("beta.user@example.com") is False
    live_db.set_user_beta_access("beta.user@example.com", True)
    assert mod.user_has_beta_access("beta.user@example.com") is True


def test_odata_workbook_to_tabs(tmp_path):
    from openpyxl import Workbook

    from pathlib import Path
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "v3" / "web" / "reporting" / "odata_bridge.py"
    spec = importlib.util.spec_from_file_location("odata_bridge", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    wb = Workbook()
    ws = wb.active
    ws.title = "Full Details"
    ws.append(["InvoiceNumber", "Total Invoice", "Salesman"])
    ws.append(["IN1", 10.5, "SM01"])
    ws.append(["IN2", 20.0, "SM02"])
    xlsx = tmp_path / "sample.xlsx"
    wb.save(xlsx)

    tabs = mod._workbook_to_tabs(str(xlsx))
    assert len(tabs) == 1
    assert tabs[0]["key"] == "full_details"
    assert tabs[0]["columns"] == ["InvoiceNumber", "Total Invoice", "Salesman"]
    assert len(tabs[0]["rows"]) == 2

    scoped = mod._scope_tab(tabs[0], {"SM01"})
    assert len(scoped["rows"]) == 1
    assert scoped["rows"][0]["InvoiceNumber"] == "IN1"


def test_live_login_redirect_escapes_mount():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "v3" / "web" / "beta_live_session.py"
    spec = importlib.util.spec_from_file_location("beta_live_session", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    assert mod.live_login_redirect("/") == "/legacy/login?next=/"
    assert mod.live_login_redirect("/reports") == "/legacy/login?next=/reports"
    # Reject open redirects
    assert mod.live_login_redirect("https://evil.example/") == "/legacy/login?next=/"


def test_live_auth_safe_next():
    from webapp.blueprints.auth import _safe_next

    assert _safe_next("/beta/") == "/beta/"
    assert _safe_next("/beta/reports?x=1") == "/beta/reports?x=1"
    assert _safe_next("/legacy/settings") == "/legacy/settings"
    assert _safe_next("https://evil.example/") is None
    assert _safe_next("//evil.example/") is None
    assert _safe_next(None) is None


def test_entra_redirect_uri_ignores_legacy_script_name():
    from flask import Flask

    from webapp.auth import _get_redirect_uri

    app = Flask(__name__)
    with app.test_request_context(
        "/login",
        base_url="https://reports.achimonline.com",
        environ_overrides={"SCRIPT_NAME": "/legacy"},
        headers={"X-Forwarded-Proto": "https"},
    ):
        assert _get_redirect_uri() == "https://reports.achimonline.com/auth/callback"

