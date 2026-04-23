"""Settings blueprint -- stub until we port the old settings screens."""

from __future__ import annotations

from flask import Blueprint, render_template

from test.webapp.auth import require_login

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
@require_login
def index():
    return render_template("settings.html", active_tab="settings")
