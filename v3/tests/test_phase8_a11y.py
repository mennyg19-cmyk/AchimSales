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
