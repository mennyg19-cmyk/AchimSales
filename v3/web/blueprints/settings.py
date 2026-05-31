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
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.data.repositories.salesmen import SalesmanRepository
from web.data.repositories.users import UserRepository

settings_bp = Blueprint("settings", __name__)

_THEMES = ("light", "dark")


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
    _persist_theme(current_principal().email, theme)
    flash(f"Theme set to {theme}.", "success")
    return redirect(url_for("settings.settings_page"))


def _persist_theme(email: str, theme: str) -> None:
    db = current_app.config["DB"]
    user = UserRepository(db).get_by_email(email)
    if user is None:
        return
    with db.precious() as conn:
        conn.execute(
            "INSERT INTO user_preferences(user_id, theme) VALUES (?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET theme=excluded.theme",
            (user.id, theme),
        )
