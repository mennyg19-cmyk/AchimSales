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
    assert 'id="prevRunsBtn"' in html
    assert "Recent Reports" in html
    assert "header-text-link" in html
    assert 'id="reportJobsBar"' in html
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


def test_beta_base_html_skips_missing_dashboard_endpoints(tmp_path):
    """Beta does not register dashboard — base.html must not url_for it (was a 500)."""
    from dataclasses import replace

    from web.data.migrate import migrate

    cfg = replace(_cfg(tmp_path), is_beta=True)
    app = create_app(cfg)
    with app.app_context():
        migrate(app.config["DB"])
    with app.test_request_context("/"):
        # Context processor supplies nav/is_beta; do not hardcode them.
        html = render_template(
            "base.html",
            user={"name": "Dev", "role": "developer", "_dev": True},
            active_tab="reports",
        )
    assert "Dashboard" not in html
    assert "Schedules" in html
    assert "data-notifications-url" not in html
    assert ">Beta<" not in html


def test_beta_report_view_keeps_schedule_and_run(tmp_path):
    """Beta registers schedules — report view can offer Schedule this view."""
    from dataclasses import replace

    from report_engine.registry import get as get_report
    from web.data.migrate import migrate

    cfg = replace(_cfg(tmp_path), is_beta=True)
    app = create_app(cfg)
    with app.app_context():
        migrate(app.config["DB"])
    spec = get_report("ordered")
    assert spec is not None
    with app.test_request_context("/reports/ordered"):
        html = render_template(
            "report_view.html",
            user={"name": "Dev", "role": "developer", "_dev": True},
            active_tab="reports",
            report=spec,
            filters=(),
            period_options=(),
            status_options=(),
            year_options=[2026],
            n4_mode_options=(),
            is_developer=True,
        )
    assert "scheduleBtn" in html
    assert "data-run-url" in html


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


def test_report_viewer_meeting_ux():
    src = (_SRC / "js" / "report.ts").read_text(encoding="utf-8")
    assert "Rename tab" in src
    assert 'textContent = "Delete"' in src
    assert "Add subgroup" in src
    assert "groupPills" in src
    assert "Save this view as (same name overwrites this view)" in src
    assert "layout.clones" in src
    resume = src.split("async function resumeInFlight", 1)[1].split("async function", 1)[0]
    assert '(q.get("preset") || q.get("cview")) && !wanted) return false' in resume
    assert 'closePresetsPanel(); loadPreset(preset); });' in src
    assert "Updated Default." in src
    assert "Only managers and admins can change the Default view." in src
    assert "Only managers and admins can change company views." in src
    assert "Company views" in src
    assert "Apply this view’s filters (does not run the report)" not in src
    assert "if (!out.salesman && pendingSalesman) out.salesman = pendingSalesman;" in src
    assert "function applySalesman(" in src
    assert "fulfillmentFillCss" in src
    assert 'col.field === "Fulfillment %"' in src
    css = (_SRC / "css" / "pages.css").read_text(encoding="utf-8")
    assert ".group-pill" in css
    html = (_V3 / "web" / "templates" / "report_view.html").read_text(encoding="utf-8")
    assert 'id="groupPills"' in html
    assert "data-default-url" in html
    assert "data-company-view-url" in html
    wizard = (_V3 / "web" / "templates" / "master_schedules.html").read_text(encoding="utf-8")
    assert 'option value="default">Default</option>' in wizard
    assert "Current filters — no saved view" not in wizard
    wiz_js = (_SRC / "js" / "master_wizard.ts").read_text(encoding="utf-8")
    assert 'view_name: selectedViewName()' in wiz_js
    assert 'group.label = "Company views"' in wiz_js
    sched = (_V3 / "web" / "templates" / "schedules.html").read_text(encoding="utf-8")
    assert "<th>View</th>" in sched
    company = (_V3 / "web" / "templates" / "master_schedules.html").read_text(encoding="utf-8")
    assert "<th>View</th>" in company
