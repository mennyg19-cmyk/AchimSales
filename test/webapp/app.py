"""Sales Reports v2 -- Flask application factory (test/ scaffold).

Clean shell after the rollback: home + dashboard + reports + settings,
plus auth. Each page starts as a minimal stub and grows as we add features.

wsgi.py mounts this app under /v2 via werkzeug.DispatcherMiddleware so
nothing here runs inside the live app's process.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_TEST_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _TEST_DIR.parent
for _p in (str(_REPO_ROOT), str(_TEST_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from flask import Flask, render_template

from test.config.reports import list_reports
from test.config.settings import AUTH_MODE, FLASK_SECRET, URL_PREFIX, USE_MOCK_DATA
from test.webapp.auth import current_user, require_login
from test.webapp.blueprints.auth_bp import auth_bp
from test.webapp.blueprints.dashboard import dashboard_bp
from test.webapp.blueprints.presets import presets_bp
from test.webapp.blueprints.report_api import report_api_bp
from test.webapp.blueprints.reports import reports_bp
from test.webapp.blueprints.settings_bp import settings_bp
from test.webapp.db import init_db

log = logging.getLogger(__name__)


def create_app() -> Flask:
    """Create the /v2 Flask app. Safe to call once per process."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
        static_url_path="/static",
    )
    app.secret_key = FLASK_SECRET

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_NAME"] = "v2_session"
    if os.environ.get("WEBSITE_SITE_NAME"):
        app.config["SESSION_COOKIE_SECURE"] = True

    @app.context_processor
    def _inject_globals():
        return {
            "USE_MOCK_DATA": USE_MOCK_DATA,
            "URL_PREFIX": URL_PREFIX,
            "AUTH_MODE": AUTH_MODE,
            "CURRENT_USER": current_user(),
        }

    @app.route("/")
    @require_login
    def index():
        return render_template("index.html", reports=list_reports(), active_tab="reports")

    @app.route("/healthz")
    def healthz():
        return {"status": "ok", "mock_data": USE_MOCK_DATA, "auth_mode": AUTH_MODE}, 200

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(report_api_bp)
    app.register_blueprint(presets_bp)
    app.register_blueprint(settings_bp)

    init_db()

    log.info("v2 app created (USE_MOCK_DATA=%s prefix=%s)", USE_MOCK_DATA, URL_PREFIX)
    return app
