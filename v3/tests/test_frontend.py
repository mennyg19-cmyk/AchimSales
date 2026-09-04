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
    assert "Beta" in html


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
    assert "function openSaveViewModal" in src
    assert "function confirmSaveView" in src
    assert 'id="saveViewModal"' in (_V3 / "web" / "templates" / "report_view.html").read_text(encoding="utf-8")
    assert "include_window" in src
    assert "function syncSavePeriodRow" in src
    assert 'window.prompt("Save as a company view"' not in src
    assert "layout.clones" in src
    resume = src.split("async function resumeInFlight", 1)[1].split("async function", 1)[0]
    assert '(q.get("preset") || q.get("cview")) && !wanted) return false' in resume
    assert "if (!st.ok) return false" in resume
    cancel = src.split("async function cancelRun", 1)[1].split("async function poll", 1)[0]
    assert "if (!res.ok)" in cancel
    assert "Could not cancel this run." in cancel
    assert "showCancel(job.status === \"running\" && !!job.can_cancel)" in src
    assert 'closePresetsPanel(); loadPreset(preset); });' in src
    assert "Updated Default." in src
    assert "Only managers and admins can change the Default view." in src
    assert "Only managers and admins can change company views." in src
    assert "Company views" in src
    assert "function collectCompanyViewParams" in src
    assert "canDelete: !!p.can_edit, canEdit: !!p.can_edit" in src
    assert "companyViewGetUrl(String(preset.id).slice(COMPANY_VIEW_PREFIX.length))" in src
    assert "function mapPeriodValue" in src
    assert 'v.toLowerCase() === "yesterday" ? "daily"' in src
    assert "function periodIsRunnable" in src
    assert "function layoutForCompanySave" in src
    assert "state.generatedAt = payload.generated_at" in src
    assert '!(state.tabs[k] as any)?._isDuplicate' in src
    assert "__generated_at__" not in src
    assert "run: !isReportShown() && periodIsRunnable(preset.params)" in src
    assert 'className = "presets-fold"' in src
    assert "function appendPresetFold" in src
    fold = src.split("function appendPresetFold", 1)[1].split("async function togglePresetsPanel", 1)[0]
    assert "wrap.open" not in fold
    assert "function syncViewOwner" in src
    assert "owner_user_id" in src
    assert " — views" in src
    assert "data?.others" in src
    assert "for ${ownerLabel}." in src
    assert "autoRunRequested = periodIsRunnable(view?.params)" in src
    assert "includeWindow ? collectParams() : collectCompanyViewParams()" in src
    assert "Apply this view’s filters (does not run the report)" not in src
    cview = src.split("async function autoOpenPresetIfRequested", 1)[1].split("const id = q.get", 1)[0]
    assert "if (!view) return;" in cview
    assert "if (!out.salesman && pendingSalesman) out.salesman = pendingSalesman;" in src
    assert "function applySalesman(" in src
    assert "function orderNumber4Columns" in src
    assert "function salesmanBandIndex" in src
    assert "typeof col.band === \"number\"" in src
    assert "function canSumColumn" in src
    assert 'c.field === "Net Price"' in src
    assert "c.sum === false" in src
    assert "function saveForCompany" in src
    assert "Save the date window" in (_V3 / "web" / "templates" / "report_view.html").read_text(encoding="utf-8")
    assert "Load Default or a named saved view to schedule it." in src
    assert "isDefaultViewId(loadedNamedView.id)" in src
    remember = src.split("function rememberNamedView", 1)[1].split("function isLoadedViewDirty", 1)[0]
    assert 'key === "customer_activity"' not in remember
    assert "isNamedPersonalPreset(preset)" in remember
    assert "isDefaultViewId(preset.id)" in remember
    assert "isCustomPeriod(preset.params)" in remember
    sync = src.split("function syncScheduleButton", 1)[1].split("function hasFilter", 1)[0]
    assert "customer_activity" not in sync
    assert "on the schedule list yet" not in src
    toolbar = src.split("function setToolbarEnabled", 1)[1].split("function closeExportMenu", 1)[0]
    assert "syncScheduleButton()" in toolbar
    assert "function paintNestedGroups" in src
    assert "function nestHeaderColors" in src
    assert "function nestFooterColors" in src
    assert "NEST_GRAND" in src
    assert "[229, 231, 235]" not in src
    assert "[156, 163, 175]" in src
    assert "paintNestedGroups(table)" in src
    css = (_SRC / "css" / "pages.css").read_text(encoding="utf-8")
    assert ".group-pill" in css
    assert ".presets-fold" in css
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
    assert 'personal_schedule_wizard.html' in sched
    assert "container-narrow" not in sched
    assert "ps-sched-table" in sched
    assert "ps-owner-row" in sched
    assert 'id="psGridEditBtn"' in sched
    assert "data-job-url" in sched
    sched_js = (_SRC / "js" / "schedules.ts").read_text(encoding="utf-8")
    assert "function pollJob" in sched_js
    assert "data-job-url" in sched_js
    assert "function bindGridEdit" in sched_js
    assert "email_to_owner: listed.some" in sched_js
    assert "email_on_no_data_me_only" in sched_js
    assert "if (row.dataset.savedReportId)" in sched_js
    assert "if (rec.value.trim() === origRec && path === origFolder) continue" in sched_js
    assert "run-log-steps" in sched_js
    css = (_SRC / "css" / "pages.css").read_text(encoding="utf-8")
    assert "table-layout: fixed" in css
    company_page = (_V3 / "web" / "templates" / "company_schedules.html").read_text(encoding="utf-8")
    assert "container-narrow" not in company_page
    assert "data-job-url" in company_page
    personal = (_V3 / "web" / "templates" / "personal_schedule_wizard.html").read_text(encoding="utf-8")
    assert 'id="psWizard"' in personal
    assert "Whose views?" in personal
    assert 'id="psOwnerSelect"' in personal
    assert 'id="psViewSelect"' in personal
    wiz_js = (_SRC / "js" / "personal_wizard.ts").read_text(encoding="utf-8")
    assert 'startsWith("default:")' in wiz_js
    assert 'startsWith("company:")' in wiz_js
    assert "company views and Default" in personal
    assert 'data-user-name="{{ current_user_name }}"' in personal
    assert "picked.owner.user_id !== 0" in wiz_js
    assert 'id="psEmailSubject"' in personal
    assert 'id="psEmailBody"' in personal
    assert "{DownloadButton}" in personal
    assert "{SharePointUrl}" in personal
    assert "email_subject:" in wiz_js
    assert "email_html: emailHtml()" in wiz_js
    assert "function wrapSharePointLink" in wiz_js
    company = (_V3 / "web" / "templates" / "master_schedules.html").read_text(encoding="utf-8")
    assert "<th>View</th>" in company


def test_new_schedules_default_filename_template():
    default = "{Schedule}_{MM}-{DD}-{YYYY}"
    preview = (_SRC / "js" / "filename_preview.ts").read_text(encoding="utf-8")
    assert f'DEFAULT_FILENAME_TEMPLATE = "{default}"' in preview
    py = (_V3 / "web" / "delivery" / "filename_template.py").read_text(encoding="utf-8")
    assert f'DEFAULT_FILENAME_TEMPLATE = "{default}"' in py
    wiz_js = (_SRC / "js" / "personal_wizard.ts").read_text(encoding="utf-8")
    assert "picked?.view.name" in wiz_js
    report_js = (_SRC / "js" / "report.ts").read_text(encoding="utf-8")
    assert "loadedNamedView.name" in report_js
    for rel in (
        "templates/personal_schedule_wizard.html",
        "templates/master_schedules.html",
        "templates/report_view.html",
    ):
        html = (_V3 / "web" / rel).read_text(encoding="utf-8")
        assert default in html
        assert "{Schedule}_{YYYY}-{MM}-{DD}_{HH}{mm}" not in html


def test_personal_and_report_schedule_have_cc_bcc_fields():
    personal = (_V3 / "web" / "templates" / "personal_schedule_wizard.html").read_text(encoding="utf-8")
    assert 'id="psCc"' in personal
    assert 'id="psBcc"' in personal
    wiz_js = (_SRC / "js" / "personal_wizard.ts").read_text(encoding="utf-8")
    assert "body.email_cc" in wiz_js
    assert "body.email_bcc" in wiz_js
    assert "params.email_cc" in wiz_js
    report_html = (_V3 / "web" / "templates" / "report_view.html").read_text(encoding="utf-8")
    assert 'id="schedCc"' in report_html
    assert 'id="schedBcc"' in report_html
    assert 'id="viewOwner"' in report_html
    assert "Save for" in report_html
    assert 'option value="company">Company</option>' in report_html
    report_js = (_SRC / "js" / "report.ts").read_text(encoding="utf-8")
    assert "body.email_cc" in report_js
    assert "body.email_bcc" in report_js


def test_settings_exclusions_use_customer_picker():
    html = (_V3 / "web" / "templates" / "settings.html").read_text(encoding="utf-8")
    assert 'id="exclPicker"' in html
    assert 'id="exclPills"' in html
    assert "data-customers-url" in html
    assert "data-lookup-status-url" in html
    assert 'id="exclSearch"' not in html
    assert "excl-toggle" not in html
    src = (_SRC / "js" / "settings.ts").read_text(encoding="utf-8")
    assert "SearchablePicker" in src
    assert "data-customers-url" in src


def test_admin_users_has_company_views_flag():
    html = (_V3 / "web" / "templates" / "admin_users.html").read_text(encoding="utf-8")
    assert 'id="euCompanyViews"' in html
    assert "data-company-views" in html
    assert "View as" in html
    assert "D365 salesman master" in html
    src = (_SRC / "js" / "admin.ts").read_text(encoding="utf-8")
    assert "can_see_company_views: checked(\"euCompanyViews\")" in src
    assert 'role === "developer"' in src


def test_admin_users_edit_modal_has_display_name():
    html = (_V3 / "web" / "templates" / "admin_users.html").read_text(encoding="utf-8")
    assert 'id="euDisplay"' in html
    src = (_SRC / "js" / "admin.ts").read_text(encoding="utf-8")
    assert 'display_name: (($("euDisplay") as HTMLInputElement)).value.trim()' in src
    assert "tr.dataset.name" in src


def test_admin_users_has_sales_group_dropdown():
    html = (_V3 / "web" / "templates" / "admin_users.html").read_text(encoding="utf-8")
    assert 'id="euSalesGroup"' in html
    assert 'id="addSalesGroup"' in html
    assert 'id="salesmanTable"' not in html
    assert "Managers and sales reps can see every checked SalesGroup" in html
    assert "data-sales-groups-url" in html
    assert "data-lookup-status-url" in html
    src = (_SRC / "js" / "admin.ts").read_text(encoding="utf-8")
    assert "sales_group: role === \"salesman\"" in src
    assert 'role !== "manager" && role !== "salesman"' in src
    assert 'role === "manager" || role === "salesman"' in src
    assert "keys.add(salesmanKey(salesGroup))" in src
    assert "list_sales_groups" not in src
    assert "data-sales-groups-url" in src


def test_live_job_log_shows_every_entry():
    report_html = (_V3 / "web" / "templates" / "report_view.html").read_text(encoding="utf-8")
    assert 'id="jobLiveLog"' in report_html
    assert 'id="jobLiveLogPanel"' in report_html
    assert "live-job-log" in report_html
    report_js = (_SRC / "js" / "report.ts").read_text(encoding="utf-8")
    assert 'from "./job_log"' in report_js
    assert 'renderJobLog($("jobLiveLog"), job.log)' in report_js
    sched_js = (_SRC / "js" / "schedules.ts").read_text(encoding="utf-8")
    assert 'from "./job_log"' in sched_js
    assert "renderJobLog(ol, stepLogs[i])" in sched_js
    assert "pollJobLog(url, live" in sched_js
    main_src = (_SRC / "js" / "main.ts").read_text(encoding="utf-8")
    assert 'from "./job_log"' in main_src
    assert "renderJobLog(ol, job.log)" in main_src
    assert "live-job-entry" not in main_src
    assert 'li class="live-job-entry"' not in sched_js
    assert "js-watch-job" in sched_js
    assert "canSeeJobLog" in sched_js
    assert 'href="${esc(r.log_url)}">Log</a>' in sched_js
    assert "data-job-log" in (_V3 / "web" / "templates" / "schedules.html").read_text(encoding="utf-8")
    assert "{% if is_developer %}" in report_html
    panel_at = report_html.find('id="jobLiveLogPanel"')
    assert "{% if is_developer %}" in report_html[max(0, panel_at - 120):panel_at]
    assert 'id="liveJobLog"' in (_V3 / "web" / "templates" / "schedules.html").read_text(encoding="utf-8")
    assert 'id="liveJobLog"' in (_V3 / "web" / "templates" / "company_schedules.html").read_text(encoding="utf-8")
    assert 'href="{{ r.log_url }}">Log</a>' in (_V3 / "web" / "templates" / "schedules.html").read_text(encoding="utf-8")
    assert "schedule_history" in (_V3 / "web" / "templates" / "schedules.html").read_text(encoding="utf-8")
    hist = (_V3 / "web" / "templates" / "schedule_history.html").read_text(encoding="utf-8")
    assert "run-history-steps" in hist
    home = (_V3 / "web" / "templates" / "reports_list.html").read_text(encoding="utf-8")
    assert 'class="home-fold"' in home
    assert '<details class="home-fold">' in home
    assert '<details class="home-fold" open' not in home
    assert "job.kept && job.owned" in main_src
    run_page = (_V3 / "web" / "templates" / "schedule_run.html").read_text(encoding="utf-8")
    assert 'id="runJobLog"' in run_page
    log_js = (_SRC / "js" / "job_log.ts").read_text(encoding="utf-8")
    assert "export function renderJobLog" in log_js
    assert "export async function pollJobLog" in log_js
    assert "live-job-entry" in log_js
    assert "live-job-step" in log_js
    assert "live-job-detail" in log_js
    assert "jobLiveLogPanel" in log_js
    css = (_SRC / "css" / "pages.css").read_text(encoding="utf-8")
    assert ".live-job-log" in css
    assert ".live-job-entry" in css
    assert ".live-job-step" in css
    assert ".live-job-detail" in css
    assert ".job-live-log-panel" in css
    assert 'id="activeJobs"' in (_V3 / "web" / "templates" / "schedules.html").read_text(encoding="utf-8")
    assert 'id="activeJobs"' in (_V3 / "web" / "templates" / "company_schedules.html").read_text(encoding="utf-8")
    assert "data-cancel-url" in (_V3 / "web" / "templates" / "schedules.html").read_text(encoding="utf-8")
    assert "function cancelJob" in sched_js
    assert "js-cancel-job" in sched_js
