"""The Flask application for the rebuilt reports app."""

# === What's in this file ===
# This builds the web app and hands it back to whatever serves it. The build is
# deliberately FAST and does no database work, so the container's warmup probe
# can't time out and kill the site. The slow setup (creating/upgrading the
# database, seeding, starting the worker) runs afterwards in a background
# thread via bootstrap_background().
#
# get_db() / get_config() -- pull the shared Database / Config off the app
# create_app() -- build and wire the Flask app (fast, no DB work)
# bootstrap_background() -- the slow setup, safe to run after the app is serving

from __future__ import annotations

import logging
from typing import Optional

from flask import Flask, current_app
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config, load_config
from .data.connection import Database
from .security.csrf import init_csrf

log = logging.getLogger("rebuild")

_DB_KEY = "rebuild.db"
_CONFIG_KEY = "rebuild.config"


def get_db(app: Optional[Flask] = None) -> Database:
    return (app or current_app).config[_DB_KEY]


def get_config(app: Optional[Flask] = None) -> Config:
    return (app or current_app).config[_CONFIG_KEY]


def create_app(config: Optional[Config] = None) -> Flask:
    config = config or load_config()

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = config.flask_secret or ("dev-only-secret" if not config.is_prod else "")
    app.config[_CONFIG_KEY] = config
    app.config[_DB_KEY] = Database(config)
    app.config.update(
        SESSION_COOKIE_NAME=config.session_cookie_name,
        # Scope the cookie to this app's mount so it never collides with the
        # live / or existing /test app cookies.
        SESSION_COOKIE_PATH=config.mount_path or "/",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.is_prod,
    )

    # Azure terminates TLS at its proxy, so trust the one forwarded hop for
    # scheme/host. This makes request.url_root https, so the MSAL callback URL
    # we build matches the https URL registered in Entra.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    init_csrf(app)

    from .blueprints.auth_routes import auth_bp
    from .blueprints.health_routes import health_bp
    from .blueprints.main_routes import main_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    return app


def bootstrap_background(app: Flask) -> None:
    """Set up the database after the app is already serving requests.

    Anything that touches SQLite or starts the worker goes here, never in
    create_app(). Failures are logged and swallowed so a setup hiccup degrades
    the app instead of crashing the whole shared process.
    """
    from .data.connection import utc_now_iso
    from .data.migrate import apply_precious_migrations

    try:
        db = get_db(app)
        applied = apply_precious_migrations(db)
        with db.precious() as conn:
            conn.execute(
                "INSERT INTO app_meta (key, value, updated_at) VALUES ('booted_at', ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (utc_now_iso(), utc_now_iso()),
            )
        from .reports.seeds import seed_all

        seed_all(db)
        log.info("rebuild bootstrap complete (migrations applied: %s)", applied or "none")
        _maybe_start_in_process_worker(app)
    except Exception:  # noqa: BLE001 - a setup failure must not crash the shared process
        log.exception("rebuild bootstrap_background failed (app stays up, may be degraded)")


_WORKER_KEY = "rebuild.worker"


def _maybe_start_in_process_worker(app: Flask) -> None:
    """Start the worker as a daemon thread inside the web app, if configured.

    This is the fallback mode for the temporary preview slot: same worker code
    as the standalone process, just living in the web process. The atomic job
    claim keeps it correct even if more than one web process runs one each.
    """
    config = get_config(app)
    if config.worker_mode != "in_process":
        log.info("worker_mode=%s; not starting an in-process worker", config.worker_mode)
        return
    from .jobs.handlers import register_all
    from .jobs.types import registry
    from .jobs.worker import Worker

    register_all(registry)
    worker = Worker(get_db(app), config, registry)
    worker.start()
    app.config[_WORKER_KEY] = worker
    log.warning("in-process worker started (WORKER_MODE=in_process)")
