"""Phase 8 a11y source checks: dialogs, copy, license, inert."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tabulator_mit_license_is_vendored():
    text = (ROOT / "web/static_src/public/vendor/TABULATOR-LICENSE.txt").read_text()
    assert "MIT License" in text
    assert "Oliver Folkerd" in text


def test_settings_template_links_tabulator_license():
    html = (ROOT / "web/templates/settings.html").read_text()
    assert "vendor/TABULATOR-LICENSE.txt" in html


def test_email_timeout_does_not_say_check_the_outbox():
    src = (ROOT / "web/static_src/js/report-delivery.ts").read_text()
    assert "check the outbox" not in src.lower()


def test_admin_and_sharepoint_use_open_dialog():
    admin = (ROOT / "web/static_src/js/admin.ts").read_text()
    sp = (ROOT / "web/static_src/js/sharepoint_picker.ts").read_text()
    assert "openDialog" in admin
    assert "openDialog" in sp


def test_login_external_dialog_has_aria_modal():
    html = (ROOT / "web/templates/login.html").read_text()
    assert 'aria-modal="true"' in html
    assert "closeExternalLogin" in html


def test_dialog_helper_inerts_background():
    src = (ROOT / "web/static_src/js/dialog.ts").read_text()
    assert "inert" in src
    assert "prefersReducedMotion" in src
    assert "watchHiddenPoll" in src


def test_shell_and_lookup_pollers_use_watch_hidden_poll():
    main = (ROOT / "web/static_src/js/main.ts").read_text()
    assert main.count("watchHiddenPoll(") >= 2
    assert "hiddenPollMs" not in main
    filters = (ROOT / "web/static_src/js/report-filters.ts").read_text()
    assert "setLookupPollTimer" not in filters
    dash = (ROOT / "web/static_src/js/dashboard.ts").read_text()
    announce = dash.split("function announceDash", 1)[1].split("// --- dashboard list", 1)[0]
    assert 'setAttribute("role", text ? "alert" : "status")' in announce


def test_schedule_draft_failure_has_an_error_string():
    src = (ROOT / "web/static_src/js/master_wizard.ts").read_text()
    assert "Could not copy this report into a schedule" in src
    delivery = (ROOT / "web/static_src/js/report-delivery.ts").read_text()
    assert "browser storage is blocked" in delivery


def test_dark_theme_keeps_button_fill_darker_than_text_primary():
    tokens = (ROOT / "web/static_src/css/tokens.css").read_text()
    dark = tokens.split("body.dark-theme {", 1)[1].split("body.monochrome-theme", 1)[0]
    assert "--primary: #60a5fa;" in dark
    assert "--primary-fill: #2563eb;" in dark
    shell = (ROOT / "web/static_src/css/shell.css").read_text()
    assert "background: var(--primary-fill, var(--primary))" in shell
    assert "color: var(--on-primary, #fff)" in shell


def test_leftover_filter_and_close_targets_are_44px():
    report = (ROOT / "web/static_src/css/pages-report.css").read_text()
    assert "min-width: 44px; min-height: 44px; width: 44px; height: 44px" in report
    assert ".group-pill-x" in report and "min-height: 44px" in report.split(".group-pill-x", 1)[1][:400]
    comm = report.split(".commission-live-table thead th", 1)[1][:200]
    assert "#1a5a94" in comm


def test_customer_last_order_pick_uses_bundled_script():
    html = (ROOT / "web/templates/customer_last_order_pick.html").read_text()
    assert "customer_last_order.js" in html
    assert "setTimeout(load" not in html
    src = (ROOT / "web/static_src/js/customer_last_order.ts").read_text()
    assert "watchHiddenPoll" in src
    assert "initPick" in src


def test_from_report_failure_opens_the_wizard():
    src = (ROOT / "web/static_src/js/master_wizard.ts").read_text()
    chunk = src.split("async function consumeReportDraft", 1)[1].split("export function bindMasterWizard", 1)[0]
    fail = chunk.split("if (!draft?.report_key)", 1)[1].split("const form = masterForm()", 1)[0]
    assert "openWizard()" in fail
    assert "Could not copy this report into a schedule" in fail


def test_menus_close_on_tab_and_restore_button():
    src = (ROOT / "web/static_src/js/dialog.ts").read_text()
    bind = src.split("export function bindMenu", 1)[1].split("export function hiddenPollMs", 1)[0]
    assert 'e.key === "Escape" || e.key === "Tab"' in bind
    assert "btn.focus()" in bind


def test_report_customer_picker_matches_searchable_keyboard():
    src = (ROOT / "web/static_src/js/report-filters.ts").read_text()
    keys = src.split("function onCustomerSearchKey", 1)[1].split("export function renderCustomerPills", 1)[0]
    assert 'e.key === "ArrowDown" || e.key === "Enter"' in keys
    assert "onCustomerOptionKey" in src
    assert "returnToSearch" in src
    assert "search?.focus()" in src


def test_failure_live_regions_cover_admin_email_dashboard_schedules():
    users = (ROOT / "web/templates/admin_users.html").read_text()
    assert 'id="addUserMsg" role="alert" aria-live="assertive"' in users
    report = (ROOT / "web/templates/report_view.html").read_text()
    email_tag = report.split('id="emailMsg"', 1)[1].split(">", 1)[0]
    assert 'role="status"' in email_tag
    assert 'aria-live="polite"' in email_tag
    delivery = (ROOT / "web/static_src/js/report-delivery.ts").read_text()
    fn = delivery.split("export function emailMsg", 1)[1].split("let closeEmailDlg", 1)[0]
    assert 'setAttribute("role", isError ? "alert" : "status")' in fn
    dash = (ROOT / "web/static_src/js/dashboard.ts").read_text()
    assert "Could not refresh dashboard data." in dash
    assert "Dashboard refresh timed out. Try again." in dash
    sched_html = (ROOT / "web/templates/schedules.html").read_text()
    assert 'id="scheduleLive" class="form-msg" role="alert" aria-live="assertive"' in sched_html
    sched = (ROOT / "web/static_src/js/schedules.ts").read_text()
    assert "Could not send this schedule now." in sched


def test_monochrome_dark_primary_and_job_fabs_meet_fill_split():
    tokens = (ROOT / "web/static_src/css/tokens.css").read_text()
    mono_dark = tokens.split("body.monochrome-dark-theme {", 1)[1].split(
        "body.monochrome-dark-theme .badge-admin", 1
    )[0]
    assert "--primary: #d4d4d8;" in mono_dark
    assert "--primary-fill: #52525b;" in mono_dark
    shell = (ROOT / "web/static_src/css/shell.css").read_text()
    assert ".report-jobs-done .report-jobs-fab { background: #15803d;" in shell
    assert "body.dark-theme .report-jobs-failed .report-jobs-fab { background: #991b1b;" in shell
    assert "body.monochrome-dark-theme .report-jobs-done .report-jobs-fab { background: #3f3f46;" in shell


def test_add_user_network_failure_returns_an_error_response():
    src = (ROOT / "web/static_src/js/admin.ts").read_text()
    api = src.split("async function api", 1)[1].split("function $(", 1)[0]
    assert "Could not reach the server." in api
    assert "catch" in api


def test_semantic_text_tokens_are_dark_enough_on_their_tints():
    tokens = (ROOT / "web/static_src/css/tokens.css").read_text()
    light = tokens.split(":root {", 1)[1].split("body.dark-theme {", 1)[0]
    assert "--primary: #1d4ed8;" in light
    assert "--primary-fill: #2563eb;" in light
    assert "--success: #15803d;" in light
    assert "--error: #b91c1c;" in light
    assert "--warning: #b45309;" in light
    dark = tokens.split("body.dark-theme {", 1)[1].split("body.monochrome-theme {", 1)[0]
    assert "--error: #f87171;" in dark
    mono_dark = tokens.split("body.monochrome-dark-theme {", 1)[1].split(
        "body.monochrome-dark-theme .badge-admin", 1
    )[0]
    assert "--error: #f87171;" in mono_dark
