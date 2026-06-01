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
from web.data.repositories.preferences import PreferencesRepository
from web.data.repositories.salesmen import SalesmanRepository
from web.data.repositories.users import UserRepository

settings_bp = Blueprint("settings", __name__)

_THEMES = ("light", "dark")


def _prefs() -> PreferencesRepository:
    return PreferencesRepository(current_app.config["DB"])


def _uid(email: str) -> int | None:
    user = UserRepository(current_app.config["DB"]).get_by_email(email)
    return user.id if user else None


@settings_bp.get("/settings")
@require_login
def settings_page():
    p = current_principal()
    db = current_app.config["DB"]
    salesmen = []
    if current_app.config["AUTHZ"].is_privileged(p):  # live DB check, not session role
        salesmen = sorted(
            SalesmanRepository(db).all_as_facts().values(),
            key=lambda s: (s.number or "", s.display_name or ""),
        )
    return render_template(
        "settings.html", active_tab="settings", profile=p, salesmen=salesmen,
    )


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
