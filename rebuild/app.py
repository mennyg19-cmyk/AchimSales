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
# _is_background_leader() -- elect ONE process to run the worker + schedule poller

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
    from .blueprints.reporting_routes import reporting_bp
    from .blueprints.schedules_routes import schedules_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(reporting_bp)
    app.register_blueprint(schedules_bp)

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
_POLLER_KEY = "rebuild.poller"
# Held open for the process lifetime so the background-leader lock stays held.
_bg_lock_handle = None


def _is_background_leader(app: Flask) -> bool:
    """Elect exactly ONE process to run the worker + schedule poller.

    Under gunicorn there can be several worker processes, but the job worker and
    the schedule poller must run in only one of them -- otherwise every process
    would poll and could fire a schedule more than once. The one process that
    grabs an exclusive OS file lock wins and holds it until it dies. Fails OPEN
    (leader=True) on Windows/local dev where the lock isn't available, so a single
    process still runs background work.
    """
    global _bg_lock_handle
    try:
        import fcntl
    except Exception:  # noqa: BLE001 - non-POSIX (local dev): this single process owns it
        return True
    lock_path = get_config(app).precious_db_path.parent / ".rebuild-background.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "w")  # noqa: SIM115 - kept open on purpose to hold the lock
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False  # another process already holds it
    except Exception:  # noqa: BLE001 - never block boot on an unexpected lock error
        log.exception("background lock errored; assuming leader")
        return True
    _bg_lock_handle = handle
    return True


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
    # Only the elected leader process runs the worker + poller (see the lock).
    if not _is_background_leader(app):
        log.info("not the background leader; this process won't run the worker/poller")
        return
    from .jobs.handlers import register_all
    from .jobs.types import registry
    from .jobs.worker import Worker

    register_all(registry)
    worker = Worker(get_db(app), config, registry)
    worker.start()
    app.config[_WORKER_KEY] = worker

    from .scheduling.poller import SchedulePoller

    poller = SchedulePoller(get_db(app), config)
    poller.start()
    app.config[_POLLER_KEY] = poller
    log.warning("in-process worker + schedule poller started (WORKER_MODE=in_process)")
