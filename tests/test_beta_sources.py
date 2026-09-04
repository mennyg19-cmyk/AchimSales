"""Unit tests for Beta source map + access helpers."""

from __future__ import annotations

import pytest

from webapp import db as live_db


@pytest.fixture()
def live_mem_db(monkeypatch, tmp_path):
    path = tmp_path / "live.db"
    monkeypatch.setattr(live_db, "DB_PATH", str(path))
    live_db.init_db()
    return path


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


def test_live_login_redirect_escapes_mount():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "v3" / "web" / "beta_live_session.py"
    spec = importlib.util.spec_from_file_location("beta_live_session", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    assert mod.live_login_redirect("/") == "/login?next=/"
    assert mod.live_login_redirect("/reports") == "/login?next=/reports"
    # Reject open redirects
    assert mod.live_login_redirect("https://evil.example/") == "/login?next=/"


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

