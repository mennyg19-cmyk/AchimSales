"""Settings hub: profile, theme, exclusions, admin categories, run history."""

from __future__ import annotations

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from report_engine import registry
from report_engine.lib import salesman_key
from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.data.repositories.app_settings import AppSettingsRepository
from web.data.repositories.exclusions import ExclusionRepository
from web.data.repositories.feature_flags import DEFAULTS as FLAG_DEFAULTS
from web.data.repositories.feature_flags import FeatureFlagRepository
from web.data.repositories.preferences import PreferencesRepository
from web.data.repositories.report_config import ReportConfigRepository
from web.data.repositories.schedules import MASTER, PERSONAL, ScheduleRunRepository
from web.data.repositories.users import UserRepository

settings_bp = Blueprint("settings", __name__)

_THEMES = ("light", "dark", "monochrome", "monochrome_dark")


def _prefs() -> PreferencesRepository:
    return PreferencesRepository(current_app.config["DB"])


def _flags() -> FeatureFlagRepository:
    return FeatureFlagRepository(current_app.config["DB"])


def _uid(email: str) -> int | None:
    user = UserRepository(current_app.config["DB"]).get_by_email(email)
    return user.id if user else None


def _require_admin():
    p = current_principal()
    return p if current_app.config["AUTHZ"].is_privileged(p) else None


def _is_developer(p) -> bool:
    return current_app.config["AUTHZ"].is_developer(p)


@settings_bp.get("/settings")
@require_login
def settings_page():
    p = current_principal()
    authz = current_app.config["AUTHZ"]
    is_admin = authz.is_privileged(p)
    flags = []
    reports = []
    test_mode_on = False
    test_emails: list[str] = []
    if is_admin:
        current = _flags().all()
        flags = [
            {"key": key, "enabled": current.get(key, default), "description": desc}
            for key, (default, desc) in FLAG_DEFAULTS.items()
        ]
        settings = AppSettingsRepository(current_app.config["DB"])
        test_mode_on = settings.is_schedule_test_mode()
        test_emails = settings.test_emails()
        vis = ReportConfigRepository(current_app.config["DB"]).all()
        reports = [
            {"key": s.key, "title": s.title, "enabled": vis.get(s.key, True)}
            for s in sorted(registry.built_reports(), key=lambda s: s.title)
        ]
    uid = _uid(p.email)
    excluded = ExclusionRepository(current_app.config["DB"]).get(uid) if uid else set()
    customers = _exclusion_customers(p, excluded)
    beta_sources = {}
    if _is_developer(p):
        try:
            from web.beta_sources import get_sources
            beta_sources = get_sources()
        except Exception:  # noqa: BLE001 - page still renders
            current_app.logger.exception("beta sources load failed")
            from web.beta_sources import default_sources
            beta_sources = default_sources()
    return render_template(
        "settings.html", active_tab="settings", profile=p, flags=flags,
        test_mode_on=test_mode_on, test_emails=test_emails,
        is_admin=is_admin, is_developer=_is_developer(p),
        reports=reports, customers=customers, excluded=excluded,
        beta_sources=beta_sources,
    )


def _exclusion_customers(p, excluded: set[str]) -> list[dict]:
    authz = current_app.config["AUTHZ"]
    allowed = authz.visible_salesman_keys(p)
    rows = current_app.config["DASHBOARD_REPO"].all()
    out = []
    for r in rows:
        if allowed is not None and salesman_key(r.sales_group) not in allowed:
            continue
        out.append({
            "account": r.customer_account, "name": r.customer_name,
            "last_order": r.last_order_date or "",
            "excluded": r.customer_account in excluded,
        })
    return out


@settings_bp.get("/admin/run-log")
@require_login
def run_log_page():
    if _require_admin() is None:
        return jsonify({"error": "Forbidden"}), 403
    entries = current_app.config["RUN_LOG_REPO"].recent(limit=200)
    return render_template("run_log.html", active_tab="settings", entries=entries)


@settings_bp.get("/admin/schedule-runs")
@require_login
def schedule_runs_page():
    if _require_admin() is None:
        return jsonify({"error": "Forbidden"}), 403
    db = current_app.config["DB"]
    runs = ScheduleRunRepository(db).list_recent(limit=200)
    labels: dict[tuple[str, int], str] = {}
    with db.precious() as conn:
        for r in conn.execute("SELECT id, report_key FROM schedules"):
            labels[(PERSONAL, r["id"])] = r["report_key"]
        for r in conn.execute("SELECT id, name FROM master_schedules"):
            labels[(MASTER, r["id"])] = r["name"]
    entries = []
    for run in runs:
        key = (run.schedule_type, run.schedule_id or 0)
        entries.append({
            "id": run.id, "status": run.status,
            "started_at": run.started_at, "finished_at": run.finished_at,
            "rows": run.rows, "schedule_type": run.schedule_type,
            "label": labels.get(key, "—"),
            "summary": (run.debug_log or run.output_meta.get("summary") or "")[:200],
        })
    return render_template("schedule_runs.html", active_tab="settings", entries=entries)


@settings_bp.post("/api/admin/feature-flags")
@require_login
def set_feature_flag():
    if _require_admin() is None:
        return jsonify({"error": "Forbidden"}), 403
    body = request.get_json(silent=True) or {}
    key = (body.get("key") or "").strip()
    if key not in FLAG_DEFAULTS:
        return jsonify({"error": "Unknown flag"}), 400
    _flags().set(key, bool(body.get("enabled")))
    return jsonify({"key": key, "enabled": bool(body.get("enabled"))})


@settings_bp.post("/api/admin/report-visibility")
@require_login
def set_report_visibility():
    if _require_admin() is None:
        return jsonify({"error": "Forbidden"}), 403
    body = request.get_json(silent=True) or {}
    key = (body.get("report_key") or "").strip()
    if registry.get(key) is None:
        return jsonify({"error": "Unknown report"}), 400
    enabled = bool(body.get("enabled"))
    ReportConfigRepository(current_app.config["DB"]).set(key, enabled)
    return jsonify({"report_key": key, "enabled": enabled})


@settings_bp.post("/api/admin/schedule-test")
@require_login
def set_schedule_test():
    if _require_admin() is None:
        return jsonify({"error": "Forbidden"}), 403
    body = request.get_json(silent=True) or {}
    repo = AppSettingsRepository(current_app.config["DB"])
    emails = body.get("emails")
    enabled = body.get("enabled")
    if emails is not None and not isinstance(emails, list):
        return jsonify({"error": "emails must be a list"}), 400
    try:
        repo.set_schedule_test(
            enabled=None if enabled is None else bool(enabled),
            emails=None if emails is None else [str(x) for x in emails],
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"enabled": repo.is_schedule_test_mode(), "emails": repo.test_emails()})


@settings_bp.post("/api/settings/exclusions")
@require_login
def set_exclusion():
    p = current_principal()
    uid = _uid(p.email)
    if uid is None:
        return jsonify({"error": "Unknown user"}), 403
    body = request.get_json(silent=True) or {}
    account = (body.get("customer_account") or "").strip()
    if not account:
        return jsonify({"error": "customer_account required"}), 400
    excluded = bool(body.get("excluded"))
    ExclusionRepository(current_app.config["DB"]).set(uid, account, excluded)
    return jsonify({"customer_account": account, "excluded": excluded})


@settings_bp.get("/api/dev/beta-sources")
@require_login
def get_beta_sources():
    if not _is_developer(current_principal()):
        return jsonify({"error": "Forbidden"}), 403
    from web.beta_sources import get_sources
    return jsonify({"sources": get_sources()})


@settings_bp.post("/api/dev/beta-sources")
@require_login
def set_beta_source():
    if not _is_developer(current_principal()):
        return jsonify({"error": "Forbidden"}), 403
    body = request.get_json(silent=True) or {}
    key = (body.get("report_key") or "").strip()
    source = (body.get("source") or "").strip().lower()
    from web.beta_sources import set_source
    try:
        set_source(key, source)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    from web.beta_sources import get_source
    return jsonify({"report_key": key, "source": get_source(key)})


@settings_bp.post("/settings/theme")
@require_login
def set_theme():
    theme = (request.form.get("theme") or "").strip().lower()
    if theme not in _THEMES:
        theme = "light"
    session["theme"] = theme
    uid = _uid(current_principal().email)
    if uid is not None:
        _prefs().set(uid, theme=theme)
    flash(f"Theme set to {theme}.", "success")
    return redirect(url_for("settings.settings_page"))


@settings_bp.post("/api/settings/preferences")
@require_login
def set_preferences():
    body = request.get_json(silent=True) or {}
    uid = _uid(current_principal().email)
    if uid is None:
        return jsonify({"error": "Unknown user"}), 403
    prefs = _prefs().set(
        uid, theme=body.get("theme"), landing_page=body.get("landing_page"),
        default_report_tab=body.get("default_report_tab"),
    )
    if "theme" in body:
        session["theme"] = prefs.theme
    return jsonify({"theme": prefs.theme, "landing_page": prefs.landing_page,
                    "default_report_tab": prefs.default_report_tab})
