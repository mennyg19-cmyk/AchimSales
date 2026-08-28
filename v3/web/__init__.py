"""v3 web app factory.

Boots fail-closed: load_config() raises in prod on insecure settings (rule 6),
so an unsafe container never serves traffic. The factory wires config, CSRF,
and blueprints. Heavy subsystems (data, jobs, reporting) are registered as
later phases land - this file stays thin.
"""

from __future__ import annotations

import os
import time

from flask import Flask, jsonify, request, session

_ASSET_VERSION = str(int(time.time()))

from web.auth.authorization import Authorization, Forbidden
from web.auth.session import current_principal
from web.config import Config, load_config
from web.data.connection import from_config
from web.data.repositories.feature_flags import FeatureFlagRepository
from web.data.repositories.users import UserRepository
from web.extensions import init_csrf
from web.security_headers import apply_security_headers


def create_app(config: Config | None = None) -> Flask:
    cfg = config or load_config()

    app = Flask(__name__, static_folder="static_dist", static_url_path="/static")
    app.config["APP_CONFIG"] = cfg
    # In dev with no secret, use an ephemeral one (sessions won't persist across
    # restarts, which is fine locally). In prod, validate() already guaranteed a
    # real secret, so this never falls back insecurely.
    app.secret_key = cfg.flask_secret or _ephemeral_dev_secret(cfg)

    from report_engine.lib import iso_date as _iso_date
    app.jinja_env.filters["iso_date"] = _iso_date

    # Home (is_beta) uses the `session` cookie + FLASK_SECRET_KEY so leftover
    # Live cookies still work after the webapp tree is gone.
    if cfg.is_beta:
        app.config["SESSION_COOKIE_NAME"] = "session"
    else:
        app.config["SESSION_COOKIE_NAME"] = "v3_session"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    if cfg.is_prod:
        app.config["SESSION_COOKIE_SECURE"] = True

    db = from_config(cfg)
    app.config["DB"] = db
    app.config["AUTHZ"] = Authorization(db)

    init_csrf(app)

    @app.after_request
    def _security_headers(response):
        hsts = cfg.is_prod or bool(os.environ.get("WEBSITE_SITE_NAME"))
        return apply_security_headers(response, hsts=hsts)

    @app.before_request
    def _hide_source_maps():
        if cfg.is_prod and (request.path or "").endswith(".map"):
            return ("Not Found", 404)

    _register_reporting(app, cfg, db)
    _register_context(app, cfg, db)
    _register_blueprints(app, cfg)
    _register_beta_access_gate(app, cfg)
    _register_error_handlers(app)
    _register_cli(app, db)
    return app


def _register_reporting(app: Flask, cfg: Config, db) -> None:
    """Build the reporting stack (no background threads here - wsgi starts those).

    Routes enqueue runs onto the durable job table and read results from the one
    cache; the worker (started by `bootstrap_background`) drains the queue.
    """
    from web.dashboard.jobs import DASHBOARD_REFRESH_JOB_TYPE, make_refresh_handler
    from web.dashboard.mirror import MirrorService
    from web.dashboard.service import DashboardService
    from web.data.repositories.dashboard import DashboardRepository
    from web.data.repositories.jobs import JobRepository
    from web.data.repositories.outbox import OutboxRepository
    from web.data.repositories.run_log import ReportRunLogRepository
    from web.data.repositories.salesmen import SalesmanRepository
    from web.delivery.email import EmailService
    from web.delivery.jobs import DELIVERY_JOB_TYPE, make_delivery_handler
    from web.delivery.onedrive import OneDriveService
    from web.delivery.service import DeliveryService
    from web.delivery.sharepoint import SharePointService
    from web.jobs.worker import JobWorker
    from web.data.repositories.exports import ExportRepository
    from web.reporting.cache import ReportCache
    from web.reporting.export_jobs import EXPORT_JOB_TYPE, make_export_handler
    from web.reporting.http_client import ReportingApiClient
    from web.reporting.jobs import JOB_TYPE, make_report_run_handler
    from web.reporting.lookups import LookupService
    from web.reporting.report_service import ReportService
    from web.reporting.runner import ReportRunner
    from web.scheduling.jobs import SCHEDULE_RUN_JOB_TYPE, make_schedule_run_handler

    client = ReportingApiClient(cfg.reporting_api_base_url, cfg.reporting_api_key,
                                timeout=cfg.reporting_api_timeout)
    salesmen_repo = SalesmanRepository(db)
    service = ReportService(client, salesmen_repo)
    cache = ReportCache(db)
    runner = ReportRunner(cache)
    worker = JobWorker(db, app=app)
    run_log = ReportRunLogRepository(db)
    worker.register(JOB_TYPE, make_report_run_handler(runner, service.builder_for, run_log))

    exports = ExportRepository(db)
    worker.register(EXPORT_JOB_TYPE, make_export_handler(
        cache, exports, JobRepository(db), app.config["AUTHZ"]))

    sharepoint = SharePointService(cfg)
    onedrive = OneDriveService(cfg)
    email = EmailService(cfg, OutboxRepository(db), sharepoint, onedrive=onedrive)
    delivery = DeliveryService(runner, service.builder_for, email)
    worker.register(DELIVERY_JOB_TYPE, make_delivery_handler(delivery, app.config["AUTHZ"]))

    schedule_runner = _build_schedule_runner(db, delivery, app.config["AUTHZ"])
    worker.register(SCHEDULE_RUN_JOB_TYPE, make_schedule_run_handler(schedule_runner))

    dash_repo = DashboardRepository(db)
    mirror = MirrorService(
        customers_fetch=service.customer_universe, orders_fetch=service.all_orders, repo=dash_repo)
    worker.register(DASHBOARD_REFRESH_JOB_TYPE, make_refresh_handler(mirror, db))
    app.config["DASHBOARD_REPO"] = dash_repo
    app.config["DASHBOARD_SERVICE"] = DashboardService(dash_repo)
    app.config["MIRROR_SERVICE"] = mirror

    app.config["REPORT_SERVICE"] = service
    # Back the filter dropdowns with the shared, persisted customer mirror (the
    # dashboard aggregates) so they populate immediately on any worker - the live
    # universe is per-process and may not be warm yet on the worker serving the
    # request. Mirrors how the test app feeds its dropdown from a refreshed table.
    app.config["LOOKUP_SERVICE"] = LookupService(
        service, salesmen_repo, mirror_customers=dash_repo.all)
    app.config["REPORT_CACHE"] = cache
    app.config["EXPORT_REPO"] = exports
    app.config["JOB_REPO"] = JobRepository(db)
    app.config["RUN_LOG_REPO"] = run_log
    app.config["JOB_WORKER"] = worker
    app.config["SHAREPOINT_SERVICE"] = sharepoint
    app.config["ONEDRIVE_SERVICE"] = onedrive
    app.config["DELIVERY_SERVICE"] = delivery
    app.config["SCHEDULE_RUNNER"] = schedule_runner


def _build_schedule_runner(db, delivery, authz):
    from web.data.repositories.schedules import (
        MasterScheduleRepository,
        ScheduleRepository,
        ScheduleRunRepository,
    )
    from web.data.repositories.users import UserRepository
    from web.scheduling.runner import ScheduleRunner

    return ScheduleRunner(
        schedule_repo=ScheduleRepository(db), master_repo=MasterScheduleRepository(db),
        run_repo=ScheduleRunRepository(db), user_repo=UserRepository(db),
        authz=authz, delivery=delivery,
    )


def _ephemeral_dev_secret(cfg: Config) -> str:
    if cfg.is_prod:  # defensive: should be unreachable after validate()
        raise RuntimeError("prod reached ephemeral secret path")
    import secrets

    return secrets.token_hex(32)


def _register_context(app: Flask, cfg: Config, db) -> None:
    from flask import request, url_for

    from web.auth.session import logout, sync_role

    def _safe_url(endpoint: str, **kw) -> str:
        # A missing endpoint is logged at WARNING (not silently swallowed) so a
        # real routing bug can't hide behind "#".
        try:
            return url_for(endpoint, **kw)
        except Exception:
            app.logger.warning("nav endpoint not registered: %s", endpoint)
            return "#"

    users = UserRepository(db)
    flags = FeatureFlagRepository(db)

    @app.before_request
    def _refresh_session_role():
        # Keep the cached session role in step with the live DB row so the role
        # badge + settings sections reflect promotions (e.g. seeded developer)
        # without a re-login. Security never trusts this cache (Authorization
        # re-resolves from the DB), so this is purely presentation. Skip static
        # assets to avoid a DB hit on every CSS/JS request.
        if request.endpoint == "static":
            return
        p = current_principal()
        if p is None:
            return
        live = session.get("user")
        if isinstance(live, dict) and live.get("_dev"):
            # Live role-picker: session role is the picked user, not the DB row.
            return
        try:
            if not app.config["AUTHZ"].session_allowed(p):
                logout()
                return
            if p.impersonating:
                return
            row = users.get_by_email(p.email)
            if row is not None and row.is_active:
                sync_role(row.role)
        except Exception:  # noqa: BLE001 - a role refresh must never break a request
            app.logger.warning("session role refresh failed for %s", p.email)

    @app.context_processor
    def inject_globals():
        nav = {
            "reports": _safe_url("reports.reports_list"),
            "dashboard": _safe_url("dashboard.dashboard"),
            "schedules": _safe_url("schedules.schedules_page"),
            "master_schedules": _safe_url("schedules.master_page"),
            "settings": _safe_url("settings.settings_page"),
            "login": _safe_url("auth.role_picker") if cfg.is_beta else _safe_url("auth.login_page"),
            "logout": _safe_url("auth.logout_route"),
            # Missing on Beta (no dashboard blueprint) — template must not url_for hard.
            "notifications": _safe_url("dashboard.notifications"),
        }
        p = current_principal()
        user = None
        dashboard_enabled = False
        theme = session.get("theme")
        if p is not None:
            user = {
                "name": p.name,
                "role": p.role,
                "_dev": p.is_dev,
                "_dev_name": p.real_name or (p.name.split(" (as ")[0] if " (as " in p.name else p.name),
            }
            try:
                flag_map = flags.all()
                row = users.get_by_email(p.email)
                # Dashboard tab: global flag AND (per-user opt-in OR privileged).
                dashboard_global = flag_map.get("dashboard_enabled", True)
                privileged = app.config["AUTHZ"].is_privileged(p)
                dashboard_enabled = dashboard_global and (
                    bool(row and row.dashboard_enabled) or privileged
                )
                if theme is None and row is not None:
                    theme = _load_theme(db, row.id)
            except Exception:  # noqa: BLE001 - never let a nav query break a page render
                app.logger.warning("nav/theme lookup failed for %s", p.email)
        return {
            "app_env": cfg.app_env,
            "is_beta": cfg.is_beta,
            "asset_v": _ASSET_VERSION,
            "nav": nav,
            "user": user,
            "theme": theme or "light",
            # Home (is_beta) hides dashboard; schedules stay on.
            "dashboard_enabled": False if cfg.is_beta else dashboard_enabled,
        }


def _load_theme(db, user_id: int) -> str | None:
    with db.precious() as conn:
        row = conn.execute(
            "SELECT theme FROM user_preferences WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["theme"] if row else None


def _register_blueprints(app: Flask, cfg: Config) -> None:
    from web.blueprints.admin import admin_bp
    from web.blueprints.auth import auth_bp
    from web.blueprints.health import health_bp
    from web.blueprints.reports import reports_bp
    from web.blueprints.settings import settings_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(admin_bp)
    from web.blueprints.devtools import devtools_bp
    app.register_blueprint(devtools_bp)

    from web.blueprints.schedules import schedules_bp

    app.register_blueprint(schedules_bp)
    # Beta is reports + schedules; dashboard stays Live-only.
    if not cfg.is_beta:
        from web.blueprints.dashboard import dashboard_bp

        app.register_blueprint(dashboard_bp)


def _register_beta_access_gate(app: Flask, cfg: Config) -> None:
    """Home (is_beta): leftover Live cookie or native v3 login, else /login."""
    if not cfg.is_beta:
        return

    from flask import redirect, request

    from web.beta_live_session import adopt_live_identity, live_login_redirect

    @app.before_request
    def _require_live_login():
        if request.endpoint in (None, "static"):
            return None
        ep = request.endpoint or ""
        if ep.startswith("health."):
            return None
        if ep.startswith("auth."):
            adopt_live_identity()
            return None

        p = adopt_live_identity()
        if p is None:
            mount = (request.script_root or "").rstrip("/")
            dest = mount + (request.full_path if request.full_path != "/?" else "/")
            if dest.endswith("?"):
                dest = dest[:-1]
            if not dest.startswith("/"):
                dest = "/" + dest
            if dest in ("", "?"):
                dest = "/"
            return redirect(live_login_redirect(dest))
        return None


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



from web.background import bootstrap_background, is_background_leader_process
from web.seeds import (
    _AZURE_SCHEDULES,
    _LIVE_RUNBOOK_SCHEDULES,
    _seed_admins,
    _seed_developers,
    _seed_master_schedules,
)

__all__ = [
    "create_app",
    "bootstrap_background",
    "is_background_leader_process",
]
