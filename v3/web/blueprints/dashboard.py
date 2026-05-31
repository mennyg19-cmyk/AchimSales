"""Dashboard: a privileged at-a-glance page (admin/developer, or users with the
dashboard flag). Thin - it only summarizes state the other layers own.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, render_template

from report_engine import registry
from web.auth.decorators import require_login
from web.auth.session import current_principal
from web.data.repositories.jobs import JobRepository
from web.data.repositories.users import UserRepository

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/dashboard")
@require_login
def dashboard():
    p = current_principal()
    db = current_app.config["DB"]
    row = UserRepository(db).get_by_email(p.email)
    # Live checks (never the session role): active privileged user, or the
    # dashboard flag on the live DB row.
    allowed = current_app.config["AUTHZ"].is_privileged(p) or bool(
        row and row.is_active and row.dashboard_enabled
    )
    if not allowed:
        abort(403, description="Dashboard access required")

    recent_jobs = JobRepository(db).list_for_user(row.id, limit=10) if row else []
    return render_template(
        "dashboard.html", active_tab="dashboard",
        built_reports=registry.built_reports(),
        backlog_reports=registry.backlog_reports(),
        recent_jobs=recent_jobs,
    )
