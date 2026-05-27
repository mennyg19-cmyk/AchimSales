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

from flask import Flask, redirect, url_for

from test.config.settings import AUTH_MODE, FLASK_SECRET, URL_PREFIX, USE_MOCK_DATA
from test.webapp.auth import current_user, is_admin as user_is_admin, require_login
from test.webapp.blueprints.auth_bp import auth_bp
from test.webapp.blueprints.customer_last_order import bp as customer_last_order_bp
from test.webapp.blueprints.dashboard import dashboard_bp
from test.webapp.blueprints.notifications import notifications_bp
from test.webapp.blueprints.presets import presets_bp
from test.webapp.blueprints.report_api import report_api_bp, sharepoint_api_bp
from test.webapp.blueprints.reports import reports_bp
from test.webapp.blueprints.schedules import schedules_bp
from test.webapp.blueprints.settings_bp import settings_bp
from test.webapp.db import init_db, teardown_request_connection

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

    # Release the per-request SQLite connection (see db.connect) on
    # every request exit. Doing this here keeps the db module free of
    # any Flask import-time dependency.
    app.teardown_request(teardown_request_connection)

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_NAME"] = "v2_session"
    if os.environ.get("WEBSITE_SITE_NAME"):
        app.config["SESSION_COOKIE_SECURE"] = True

    @app.context_processor
    def _inject_globals():
        from test.webapp.auth import has_sharepoint_access as _has_sp
        from test.webapp.db import get_app_user, get_feature_flag, get_user_preferences
        from test.webapp.services.report_access import get_user_profile

        user = current_user()
        prefs = {}
        dashboard_enabled = False
        current_user_is_admin = False
        if user and user.get("email"):
            current_user_is_admin = user_is_admin(user)
            try:
                prefs = get_user_preferences(user["email"])
            except Exception:
                prefs = {}
            try:
                profile = get_user_profile(user["email"])
                if profile["role"] in {"admin", "developer"}:
                    dashboard_enabled = True
                elif get_feature_flag("dashboard_enabled", True):
                    row = get_app_user(user["email"])
                    dashboard_enabled = bool(row is None or row.get("dashboard_enabled", True))
            except Exception:
                dashboard_enabled = False
        return {
            "USE_MOCK_DATA": USE_MOCK_DATA,
            "URL_PREFIX": URL_PREFIX,
            "AUTH_MODE": AUTH_MODE,
            "CURRENT_USER": user,
            "CURRENT_USER_IS_ADMIN": current_user_is_admin,
            "USER_PREFS": prefs,
            "HAS_SHAREPOINT_ACCESS": _has_sp(user) if user else False,
            "DASHBOARD_ENABLED": dashboard_enabled,
        }

    _LANDING_ENDPOINTS = {
        "reports":   "reports.list_all",
        "dashboard": "dashboard.index",
        "schedules": "schedules.index",
    }

    @app.route("/")
    @require_login
    def index():
        from test.webapp.db import get_user_preferences
        user = current_user() or {}
        landing = "reports"
        try:
            prefs = get_user_preferences(user.get("email", ""))
            landing = prefs.get("landing_page") or "reports"
        except Exception:
            pass
        endpoint = _LANDING_ENDPOINTS.get(landing, "reports.list_all")
        return redirect(url_for(endpoint))

    @app.route("/healthz")
    def healthz():
        return {"status": "ok", "mock_data": USE_MOCK_DATA, "auth_mode": AUTH_MODE}, 200

    # PWA manifest. Served dynamically so start_url + icon srcs include
    # whatever URL_PREFIX the app is mounted at (e.g. /test). A static
    # manifest with hard-coded "/" + "/static/..." paths resolves to the
    # host root and ignores the mount, breaking installability.
    @app.route("/manifest.json")
    def manifest():
        prefix = (URL_PREFIX or "").rstrip("/")
        return {
            "name":             "Achim Sales Reports (test)",
            "short_name":       "Sales (test)",
            "description":      "Sales reports and customer dashboard (test sandbox)",
            "start_url":        f"{prefix}/",
            "scope":            f"{prefix}/",
            "display":          "standalone",
            "background_color": "#ffffff",
            "theme_color":      "#16a34a",
            "orientation":      "portrait",
            "icons": [
                {
                    "src":   f"{prefix}/static/icon-192.png",
                    "sizes": "192x192",
                    "type":  "image/png",
                },
                {
                    "src":   f"{prefix}/static/icon-512.png",
                    "sizes": "512x512",
                    "type":  "image/png",
                },
            ],
        }, 200, {"Content-Type": "application/manifest+json"}

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(report_api_bp)
    app.register_blueprint(sharepoint_api_bp)
    app.register_blueprint(presets_bp)
    app.register_blueprint(schedules_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(customer_last_order_bp)

    from test.webapp.blueprints.master_schedules import master_schedules_bp
    app.register_blueprint(master_schedules_bp)

    from test.webapp.blueprints.diag import diag_bp
    app.register_blueprint(diag_bp)

    # The hot DB lives on /tmp (local SSD) -- copy the durable
    # Azure Files snapshot down before anything else touches it.
    # bootstrap_from_persistent() also handles malformed snapshots
    # via best-effort salvage so a corrupted /home/data/v2_app.db
    # doesn't block boot.
    try:
        from test.webapp.services.db_sync import bootstrap_from_persistent
        bootstrap_from_persistent()
    except Exception:
        log.exception("db_sync bootstrap failed; will continue with whatever exists at APP_DB_PATH")

    # init_db now hits /tmp, but we still keep the boot-time catch
    # in case anything (lazy mirror init, schema migration) trips on
    # the first connection. lazy_init_db() retries from connect() on
    # the first DB-touching request.
    try:
        init_db()
    except Exception:
        log.exception("init_db failed during boot; worker will continue and lazy-init on first DB use")

    # Periodic snapshot back to /home/data so a container restart
    # doesn't lose mirror data and user state.
    try:
        from test.webapp.services.db_sync import start_snapshot_loop
        start_snapshot_loop()
    except Exception:
        log.exception("db_sync snapshot loop failed to start (non-fatal)")

    # Boot the daily mirror-refresh scheduler. Disabled when running
    # tests / with the Flask reloader so we never end up with two
    # parallel schedulers.
    if os.environ.get("V2_DISABLE_SCHEDULER") != "1":
        try:
            from test.webapp.services.mirror_scheduler import start_scheduler
            start_scheduler()
        except Exception:
            log.exception("mirror scheduler failed to start (non-fatal)")
        try:
            from test.webapp.services.dashboard_data import start_background_refresh
            start_background_refresh()
        except Exception:
            log.exception("dashboard refresh scheduler failed to start (non-fatal)")

    log.info("v2 app created (USE_MOCK_DATA=%s prefix=%s)", USE_MOCK_DATA, URL_PREFIX)
    return app
