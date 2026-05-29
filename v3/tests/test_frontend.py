"""Front-end shell: live-faithful tokens, base.html structure, bundled assets."""

from pathlib import Path

import pytest
from flask import render_template

from web import create_app
from web.config import Config

_V3 = Path(__file__).resolve().parent.parent
_SRC = _V3 / "web" / "static_src"


def _cfg(tmp_path) -> Config:
    return Config(
        app_env="dev", auth_mode="dev", flask_secret="t",
        tenant_id="", client_id="", client_secret="",
        reporting_api_base_url="", reporting_api_key="",
        precious_db_path=tmp_path / "p.db", cache_db_path=tmp_path / "c.db",
        litestream_blob_url="", new_app_marker=True,
    )


def test_tokens_match_live_primary_blue():
    tokens = (_SRC / "css" / "tokens.css").read_text(encoding="utf-8")
    assert "--primary: #2563eb" in tokens   # live-blue, NOT the green test app
    assert "--bottom-nav-height: 84px" in tokens


def test_shell_css_has_core_components():
    shell = (_SRC / "css" / "shell.css").read_text(encoding="utf-8")
    for selector in (".app-header", ".bottom-nav", ".btn-primary", ".page-loading-overlay",
                     ".help-popup-overlay", ".ptr-indicator", ".alert"):
        assert selector in shell


def test_base_html_renders_shell(tmp_path):
    app = create_app(_cfg(tmp_path))
    with app.test_request_context("/"):
        html = render_template(
            "base.html",
            user={"name": "Test Admin", "role": "admin", "_dev": False},
            active_tab="reports",
        )
    assert 'class="header-logo"' in html
    assert 'class="bottom-nav"' in html
    # Bundled assets, not inline scripts / per-page CSS.
    assert "css/main.css" in html and "js/main.js" in html
    # Logout is a CSRF-protected POST form, not a GET link.
    assert "<form" in html and "csrf_token" in html


def test_base_html_hides_chrome_when_anonymous(tmp_path):
    app = create_app(_cfg(tmp_path))
    with app.test_request_context("/"):
        html = render_template("base.html", user=None)
    assert 'class="app-header"' not in html
    assert 'class="bottom-nav"' not in html


def _render(app, **ctx) -> str:
    with app.test_request_context("/"):
        return render_template("base.html", **ctx)


def test_admin_sees_dashboard_nav(tmp_path):
    app = create_app(_cfg(tmp_path))
    html = _render(app, user={"name": "A", "role": "admin", "_dev": False})
    assert "Dashboard" in html          # admin/dev get dashboard even when flag off
    assert "badge-admin" in html


def test_salesman_has_no_dashboard_nav(tmp_path):
    app = create_app(_cfg(tmp_path))
    html = _render(app, user={"name": "S", "role": "salesman", "_dev": False})
    assert "Dashboard" not in html
    assert "badge-salesman" in html


def test_impersonation_badge_for_dev_viewing_as_salesman(tmp_path):
    app = create_app(_cfg(tmp_path))
    html = _render(app, user={"name": "Boss (as Rep)", "role": "salesman", "_dev": True})
    assert "badge-impersonate" in html
    assert "Viewing as Boss" in html
    # Dev switch-user control only renders for dev principals.
    assert 'title="Switch user"' in html


def test_switch_user_hidden_for_non_dev(tmp_path):
    app = create_app(_cfg(tmp_path))
    html = _render(app, user={"name": "A", "role": "admin", "_dev": False})
    assert 'title="Switch user"' not in html


def test_test_site_nav_is_gated_off_by_default(tmp_path):
    app = create_app(_cfg(tmp_path))
    html = _render(app, user={"name": "A", "role": "admin", "_dev": False})
    assert "Test Site" not in html
