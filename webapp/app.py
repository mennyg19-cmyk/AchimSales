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

from webapp.config import FLASK_SECRET
from webapp.db import init_db, cleanup_stale_running_reports
from webapp.helpers import inject_theme

from webapp.blueprints.auth import auth_bp
from webapp.blueprints.reports import reports_bp
from webapp.blueprints.dashboard import dashboard_bp
from webapp.blueprints.settings import settings_bp
from webapp.blueprints.api import api_bp
from webapp.blueprints.schedules import schedules_bp
from webapp.blueprints.orders import orders_bp
from webapp.blueprints.email_distributions import email_dist_bp
from webapp.blueprints.db_explorer import db_explorer_bp

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _cleanup_old_reports(max_age_days: int = 7):
    """Delete report output files older than *max_age_days*."""
    from webapp.config import REPORT_OUTPUT_DIR
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

    @application.template_filter("format_summary_value")
    def _format_summary_value(value, key=""):
        """Format summary values: money keys get $X,XXX.XX, others stay as-is."""
        kl = (key or "").lower()
        money_kws = ("total", "amount", "subtotal", "net", "revenue", "price",
                     "sales", "invoice", "balance", "commission")
        if isinstance(value, (int, float)) and any(kw in kl for kw in money_kws):
            return f"${value:,.2f}"
        if isinstance(value, (int, float)) and "row" in kl:
            return f"{value:,}"
        return value

    @application.template_filter("format_summary_label")
    def _format_summary_label(key):
        """Clean up summary key for display: strip 'total_' prefix, humanize."""
        import re
        label = re.sub(r"^total_", "", key, flags=re.IGNORECASE)
        label = label.replace("_", " ")
        label = re.sub(r"([A-Z])", r" \1", label)
        label = re.sub(r"\bunique\b", "", label, flags=re.IGNORECASE)
        label = " ".join(label.split()).strip()
        return label.title() if label else key

    application.register_blueprint(auth_bp)
    application.register_blueprint(reports_bp)
    application.register_blueprint(dashboard_bp)
    application.register_blueprint(settings_bp)
    application.register_blueprint(api_bp)
    application.register_blueprint(schedules_bp)
    application.register_blueprint(orders_bp)
    application.register_blueprint(email_dist_bp)
    application.register_blueprint(db_explorer_bp)

    print("[app] Initializing database...", flush=True)
    init_db()
    cleanup_stale_running_reports()
    print("[app] Database initialized.", flush=True)

    from webapp.dashboard_data import start_background_refresh
    start_background_refresh()
    print("[app] Background refresh thread started.", flush=True)

    from webapp.services.email_distributions import start_distribution_check
    start_distribution_check()
    print("[app] Email distribution check thread started.", flush=True)

    _cleanup_old_reports()
    print("[app] App factory complete.", flush=True)

    return application


print("[app] Creating Flask application...", flush=True)
app = create_app()
print("[app] Flask application created successfully.", flush=True)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
