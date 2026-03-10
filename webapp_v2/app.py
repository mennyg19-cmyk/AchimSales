"""
Sales Reports Web App -- Flask application factory.

Refactored version: routes are split across blueprints, business logic
lives in the services layer, and this file is kept minimal.
"""

import logging
import os
import sys

_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from flask import Flask

from webapp_v2.config import FLASK_SECRET
from webapp_v2.db import init_db
from webapp_v2.helpers import inject_theme

from webapp_v2.blueprints.auth import auth_bp
from webapp_v2.blueprints.reports import reports_bp
from webapp_v2.blueprints.dashboard import dashboard_bp
from webapp_v2.blueprints.settings import settings_bp
from webapp_v2.blueprints.api import api_bp

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _cleanup_old_reports(max_age_days: int = 7):
    """Delete report output files older than *max_age_days*."""
    from webapp_v2.config import REPORT_OUTPUT_DIR
    import time
    cutoff = time.time() - (max_age_days * 86400)
    try:
        for fname in os.listdir(REPORT_OUTPUT_DIR):
            fpath = os.path.join(REPORT_OUTPUT_DIR, fname)
            if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
                log.info("Cleaned up old report file: %s", fname)
    except Exception:
        log.exception("Report cleanup failed")


def create_app() -> Flask:
    """Application factory."""
    application = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    application.secret_key = FLASK_SECRET

    application.config["SESSION_COOKIE_HTTPONLY"] = True
    application.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if os.environ.get("WEBSITE_SITE_NAME"):
        application.config["SESSION_COOKIE_SECURE"] = True

    application.context_processor(inject_theme)

    application.register_blueprint(auth_bp)
    application.register_blueprint(reports_bp)
    application.register_blueprint(dashboard_bp)
    application.register_blueprint(settings_bp)
    application.register_blueprint(api_bp)

    init_db()

    from webapp_v2.dashboard_data import start_background_refresh
    start_background_refresh()

    _cleanup_old_reports()

    return application


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
