"""v3 web app factory.

Boots fail-closed: load_config() raises in prod on insecure settings (rule 6),
so an unsafe container never serves traffic. The factory wires config, CSRF, the
"new app" marker, and blueprints. Heavy subsystems (data, jobs, reporting) are
registered as later phases land - this file stays thin.
"""

from __future__ import annotations

from flask import Flask, jsonify, session

from web.auth.authorization import Authorization, Forbidden
from web.auth.session import current_principal
from web.config import Config, load_config
from web.data.connection import from_config
from web.data.repositories.users import UserRepository
from web.extensions import init_csrf


def create_app(config: Config | None = None) -> Flask:
    cfg = config or load_config()

    app = Flask(__name__, static_folder="static_dist", static_url_path="/static")
    app.config["APP_CONFIG"] = cfg
    # In dev with no secret, use an ephemeral one (sessions won't persist across
    # restarts, which is fine locally). In prod, validate() already guaranteed a
    # real secret, so this never falls back insecurely.
    app.secret_key = cfg.flask_secret or _ephemeral_dev_secret(cfg)

    # v3 shares its host with the live app (/) and the v2 app (/test-legacy).
    # All three are Flask; the live app uses the default cookie name "session" and
    # v3 did too, so they stomp on each other's session cookie and wipe the
    # in-flight MSAL auth flow (symptom: "No auth flow in session" at the callback).
    # Give v3 its own name (v2 already uses "v2_session"). SameSite=Lax is required
    # so the cookie is still sent on the top-level GET redirect back from Microsoft.
    app.config["SESSION_COOKIE_NAME"] = "v3_session"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if cfg.is_prod:
        app.config["SESSION_COOKIE_SECURE"] = True

    db = from_config(cfg)
    app.config["DB"] = db
    app.config["AUTHZ"] = Authorization(db)

    init_csrf(app)
    _register_reporting(app, cfg, db)
    _register_context(app, cfg, db)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_cli(app, db)
    return app


def _register_reporting(app: Flask, cfg: Config, db) -> None:
    """Build the reporting stack (no background threads here - wsgi starts those).

    Routes enqueue runs onto the durable job table and read results from the one
    cache; the worker (started by `bootstrap_background`) drains the queue.
    """
    from web.data.repositories.jobs import JobRepository
    from web.data.repositories.salesmen import SalesmanRepository
    from web.jobs.worker import JobWorker
    from web.reporting.cache import ReportCache
    from web.reporting.http_client import ReportingApiClient
    from web.reporting.jobs import JOB_TYPE, make_report_run_handler
    from web.reporting.report_service import ReportService
    from web.reporting.runner import ReportRunner

    client = ReportingApiClient(cfg.reporting_api_base_url, cfg.reporting_api_key)
    service = ReportService(client, SalesmanRepository(db))
    cache = ReportCache(db)
    runner = ReportRunner(cache)
    worker = JobWorker(db)
    worker.register(JOB_TYPE, make_report_run_handler(runner, service.builder_for))

    app.config["REPORT_SERVICE"] = service
    app.config["REPORT_CACHE"] = cache
    app.config["JOB_REPO"] = JobRepository(db)
    app.config["JOB_WORKER"] = worker


def _ephemeral_dev_secret(cfg: Config) -> str:
    if cfg.is_prod:  # defensive: should be unreachable after validate()
        raise RuntimeError("prod reached ephemeral secret path")
    import secrets

    return secrets.token_hex(32)


def _register_context(app: Flask, cfg: Config, db) -> None:
    from flask import url_for

    def _safe_url(endpoint: str, **kw) -> str:
        # A missing endpoint is logged at WARNING (not silently swallowed) so a
        # real routing bug can't hide behind "#".
        try:
            return url_for(endpoint, **kw)
        except Exception:
            app.logger.warning("nav endpoint not registered: %s", endpoint)
            return "#"

    users = UserRepository(db)

    @app.context_processor
    def inject_globals():
        nav = {
            "reports": _safe_url("reports.reports_list"),
            "dashboard": _safe_url("dashboard.dashboard"),
            "settings": _safe_url("settings.settings_page"),
            "login": _safe_url("auth.login_page"),
            "logout": _safe_url("auth.logout_route"),
        }
        p = current_principal()
        user = None
        dashboard_enabled = False
        theme = session.get("theme")
        if p is not None:
            user = {"name": p.name, "role": p.role, "_dev": p.is_dev}
            try:
                row = users.get_by_email(p.email)
                dashboard_enabled = bool(row and row.dashboard_enabled) or p.is_privileged
                if theme is None and row is not None:
                    theme = _load_theme(db, row.id)
            except Exception:  # noqa: BLE001 - never let a nav query break a page render
                app.logger.warning("nav/theme lookup failed for %s", p.email)
        return {
            "new_app_marker": cfg.new_app_marker,  # removable header pill; deleted at cutover
            "app_env": cfg.app_env,
            "nav": nav,
            "user": user,
            "theme": theme or "light",
            "dashboard_enabled": dashboard_enabled,
            "test_site_enabled": False,
        }


def _load_theme(db, user_id: int) -> str | None:
    with db.precious() as conn:
        row = conn.execute(
            "SELECT theme FROM user_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["theme"] if row else None


def _register_blueprints(app: Flask) -> None:
    from web.blueprints.auth import auth_bp
    from web.blueprints.dashboard import dashboard_bp
    from web.blueprints.health import health_bp
    from web.blueprints.reports import reports_bp
    from web.blueprints.settings import settings_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(settings_bp)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(Forbidden)
    def _forbidden(exc: Forbidden):
        return jsonify({"error": str(exc), "status": exc.status_code}), exc.status_code


def _register_cli(app: Flask, db) -> None:
    @app.cli.command("migrate")
    def migrate_cmd():  # pragma: no cover - invoked via `flask migrate`
        from web.data.migrate import migrate

        applied = migrate(db)
        print("Applied migrations:", applied)


def bootstrap_background(app: Flask) -> None:
    """Prod-only side effects: migrate, seed admins/salesmen, start the worker.

    Kept OUT of create_app so tests can build an app without spawning threads or
    touching schema. The wsgi entrypoint calls this once per process. Seeding is
    individually guarded so a bad data file can never stop the app from booting.
    """
    from web.data.migrate import migrate

    db = app.config["DB"]
    migrate(db)
    _seed_admins(app, db)
    _seed_salesmen_if_empty(app, db)
    worker = app.config.get("JOB_WORKER")
    if worker is not None:
        worker.start()


def _seed_admins(app: Flask, db) -> None:
    """Grant admin to the emails in V3_ADMIN_EMAILS (fallback V2_ADMIN_EMAILS).

    Authorization is DB-authoritative + fail-closed, so without this the first
    person to sign in would land as a no-access 'salesman'. Idempotent.
    """
    import os

    raw = os.environ.get("V3_ADMIN_EMAILS") or os.environ.get("V2_ADMIN_EMAILS") or ""
    emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
    if not emails:
        return
    try:
        with db.precious() as conn:
            for email in emails:
                conn.execute(
                    "INSERT INTO users(email, display_name, role, is_active)"
                    " VALUES (?, '', 'admin', 1)"
                    " ON CONFLICT(email) DO UPDATE SET role='admin', is_active=1",
                    (email,),
                )
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("admin seed failed")


def _seed_salesmen_if_empty(app: Flask, db) -> None:
    """Seed the salesmen table from config/salesman_map.xlsx on a fresh DB."""
    from web.data.repositories.salesmen import SalesmanRepository

    try:
        if SalesmanRepository(db).count() > 0:
            return
        from web.data.seed_salesmen import read_seeds_from_xlsx

        seeds = read_seeds_from_xlsx()
        if seeds:
            SalesmanRepository(db).upsert_many(seeds)
            app.logger.info("seeded %d salesmen from config", len(seeds))
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("salesmen seed failed")
