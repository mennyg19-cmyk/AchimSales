"""Settings: profile, theme preference, and (admin) a read-only salesmen view.

Theme is stored in the session for instant rendering and persisted to
user_preferences so it survives a new session. Kept thin; richer admin tooling
(user/report-access editing) is a later, separately-reviewed phase.
"""

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

from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.data.repositories.feature_flags import DEFAULTS as FLAG_DEFAULTS
from web.data.repositories.feature_flags import FeatureFlagRepository
from web.data.repositories.preferences import PreferencesRepository
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
    """Return the principal if privileged, else None (caller 403s)."""
    p = current_principal()
    return p if current_app.config["AUTHZ"].is_privileged(p) else None


@settings_bp.get("/settings")
@require_login
def settings_page():
    p = current_principal()
    flags = []
    master_schedule_count = 0
    if current_app.config["AUTHZ"].is_privileged(p):  # live DB check, not session role
        current = _flags().all()
        flags = [
            {"key": key, "enabled": current.get(key, default), "description": desc}
            for key, (default, desc) in FLAG_DEFAULTS.items()
        ]
        from web.data.repositories.schedules import MasterScheduleRepository
        master_schedule_count = len(MasterScheduleRepository(current_app.config["DB"]).list_all())
    return render_template(
        "settings.html", active_tab="settings", profile=p, flags=flags,
        master_schedule_count=master_schedule_count,
    )


@settings_bp.get("/admin/run-log")
@require_login
def run_log_page():
    if _require_admin() is None:
        return jsonify({"error": "Forbidden"}), 403
    entries = current_app.config["RUN_LOG_REPO"].recent(limit=200)
    return render_template("run_log.html", active_tab="settings", entries=entries)


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
    """JSON preference update used by the header theme toggle + settings page.

    Accepts any subset of {theme, landing_page, default_report_tab}; only the
    provided fields change. Returns the resolved preferences.
    """
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
