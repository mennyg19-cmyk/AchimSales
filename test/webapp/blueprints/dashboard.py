"""Dashboard blueprint -- stub until we port the old dashboard content."""

from __future__ import annotations

from flask import Blueprint, render_template

from test.webapp.auth import require_login

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@require_login
def index():
    return render_template("dashboard.html", active_tab="dashboard")
