"""v3 web app factory.

Boots fail-closed: load_config() raises in prod on insecure settings (rule 6),
so an unsafe container never serves traffic. The factory wires config, CSRF, the
"new app" marker, and blueprints. Heavy subsystems (data, jobs, reporting) are
registered as later phases land - this file stays thin.
"""

from __future__ import annotations
import time

from flask import Flask, jsonify, session

_ASSET_VERSION = str(int(time.time()))

from web.auth.authorization import Authorization, Forbidden
from web.auth.session import current_principal
from web.config import Config, load_config
from web.data.connection import from_config
from web.data.repositories.feature_flags import FeatureFlagRepository
from web.data.repositories.report_config import ReportConfigRepository
from web.data.repositories.users import UserRepository
from web.extensions import init_csrf
from web.security_headers import apply_security_headers

_WORKER_PROCESS = False


def is_worker_process() -> bool:
    """True in the sibling worker after start_worker_services(); False in Gunicorn."""
    return _WORKER_PROCESS


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

    # /test keeps its own cookie. Beta shares Live's default `session` cookie
    # (same FLASK_SECRET_KEY) so one Live login covers the home app — no second Entra callback.
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
        cfg = app.config["APP_CONFIG"]
        return apply_security_headers(response, hsts=bool(getattr(cfg, "is_prod", False)))

    _register_reporting(app, cfg, db)
    _register_context(app, cfg, db)
    _register_blueprints(app, cfg)
    _register_beta_access_gate(app, cfg)
    _register_error_handlers(app)
    _register_cli(app, db)
    return app


def _register_reporting(app: Flask, cfg: Config, db) -> None:
    """Build the reporting stack without starting background work.

    Routes enqueue runs onto the durable job table and read results from the one
    cache; the sibling worker process drains the queue.
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
    worker = JobWorker(
        db, is_beta=cfg.is_beta, app_env=cfg.app_env, auth_mode=cfg.auth_mode
    )
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
    app.config["JOB_REPO"] = worker.repo
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

    from web.auth.principal import ROLE_SALESMAN
    from web.auth.session import sync_role, logout

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
        try:
            if p.impersonating:
                real_row = users.get_by_email(p.real_email) if p.real_email else None
                if not Authorization.is_active_developer_row(real_row):
                    logout()
                    return
            live = session.get("user")
            if isinstance(live, dict) and live.get("_dev"):
                real = str(live.get("_dev_email") or "").strip().lower()
                actor = users.get_by_email(real) if real else None
                picked = (p.email or "").strip().lower()
                if (Authorization.is_active_developer_row(actor)
                        and picked and picked != real):
                    # Impersonation: session role is the picked user, not the DB row.
                    return
            row = users.get_by_email(p.email)
            if row is not None and row.is_active:
                sync_role(row.role)
            else:
                # Locked out (deleted/disabled): drop any cached privileged role so
                # the UI (badge + admin sections) matches the DB-enforced denial.
                # Identity stays; the security layer already denies everything.
                sync_role(ROLE_SALESMAN)
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
        order_entry_enabled = False
        test_site_enabled = False
        theme = session.get("theme")
        if p is not None:
            user = {
                "name": p.name,
                "email": p.email,
                "role": p.role,
                "_dev": p.is_dev,
                "_dev_name": p.real_name or (p.name.split(" (as ")[0] if " (as " in p.name else p.name),
                "impersonating": p.impersonating,
            }
            try:
                flag_map = flags.all()
                order_entry_enabled = flag_map.get("order_entry_enabled", False)
                row = users.get_by_email(p.email)
                # Dashboard tab: global flag AND (per-user opt-in OR privileged).
                dashboard_global = flag_map.get("dashboard_enabled", True)
                dashboard_enabled = dashboard_global and (
                    bool(row and row.dashboard_enabled) or p.is_privileged
                )
                # Test-site link: global flag AND per-user opt-in (privileged always).
                test_site_enabled = flag_map.get("test_site_enabled", False) and (
                    bool(row and row.test_access) or p.is_privileged
                )
                if theme is None and row is not None:
                    theme = _load_theme(db, row.id)
            except Exception:  # noqa: BLE001 - never let a nav query break a page render
                app.logger.warning("nav/theme lookup failed for %s", p.email)
        return {
            "new_app_marker": cfg.new_app_marker,  # removable header pill; deleted at cutover
            "app_env": cfg.app_env,
            "is_beta": cfg.is_beta,
            "asset_v": _ASSET_VERSION,
            "nav": nav,
            "user": user,
            "theme": theme or "light",
            # Beta hides dashboard; schedules are enabled (grill 2026-08-12).
            "dashboard_enabled": False if cfg.is_beta else dashboard_enabled,
            "order_entry_enabled": False if cfg.is_beta else order_entry_enabled,
            "test_site_enabled": test_site_enabled,
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
    """Home (is_beta) uses Live login: adopt session["user"], else /legacy/login.

    Beta Access is no longer a hard gate — / is the site.
    """
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
        # Auth routes: adopt if already signed into Live; else Live login page.
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

    @app.cli.command("seed-users-from-live")
    def seed_users_from_live_cmd():  # pragma: no cover - invoked via Flask CLI
        # One-time import; normal boot must not overwrite Users & access.
        _seed_users_from_live(app, db)

    @app.cli.command("bootstrap")
    def bootstrap_cmd():  # pragma: no cover - invoked via `flask bootstrap`
        """Apply migrations and idempotent seeds without starting background work."""
        bootstrap_database(app)


def bootstrap_database(app: Flask) -> None:
    """Apply migrations and idempotent seeds for the worker-owned database."""
    from web.data.migrate import migrate

    db = app.config["DB"]
    migrate(db)
    _seed_feature_flags(app, db)      # default flags so nav gating is deterministic
    _seed_report_config(app, db)
    _seed_admins(app, db)             # explicit env admins override the mirror
    _seed_developers(app, db)         # explicit env developers win last (outrank admin)
    cfg = app.config["APP_CONFIG"]
    if getattr(cfg, "is_beta", False):
        _seed_master_schedules(app, db, _LIVE_RUNBOOK_SCHEDULES, inactive=True)
    else:
        _seed_master_schedules(app, db, _AZURE_SCHEDULES)
    _seed_company_views(app, db)


def start_worker_services(app: Flask) -> None:
    """Start the scheduler and durable-job poller in the worker process only."""
    global _WORKER_PROCESS
    from web.jobs import status

    db = app.config["DB"]
    if not app.config["APP_CONFIG"].dashboard_refresh_enabled:
        _cancel_pending_dashboard_refreshes(app, db)
    _start_scheduler(app, db)
    status.mark_bootstrap_finished(db)
    status.beat(db)
    app.config["JOB_WORKER"].start(heartbeat=lambda: status.beat(db))
    _WORKER_PROCESS = True


def stop_worker_services(app: Flask) -> None:
    global _WORKER_PROCESS
    worker = app.config.get("JOB_WORKER")
    if worker is not None:
        worker.stop()
    scheduler = app.config.get("SCHEDULER")
    if scheduler is not None:
        scheduler.shutdown()
    _WORKER_PROCESS = False


def _cancel_pending_dashboard_refreshes(app: Flask, db) -> None:
    """With the dashboard off, cancel any queued/running dashboard.refresh jobs so
    orphan-recovery doesn't resurrect one that's stuck on a slow Reporting API and
    keep tying up a worker slot."""
    from web.dashboard.jobs import DASHBOARD_REFRESH_JOB_TYPE

    try:
        with db.precious() as conn:
            n = conn.execute(
                "UPDATE jobs SET status='cancelled', finished_at=datetime('now')"
                " WHERE type=? AND status IN ('queued','running')",
                (DASHBOARD_REFRESH_JOB_TYPE,),
            ).rowcount
        if n:
            app.logger.info("dashboard refresh off: cancelled %d pending refresh job(s)", n)
    except Exception:  # noqa: BLE001 - cleanup is best-effort; never block boot
        app.logger.exception("dashboard refresh cleanup failed")


def _start_scheduler(app: Flask, db) -> None:
    """Start the once-a-minute cron tick that enqueues due schedules."""
    from web.dashboard.jobs import enqueue_refresh
    from web.jobs import status
    from web.jobs.cleanup import run_cleanup
    from web.jobs.scheduler import Scheduler
    from web.scheduling.tick import make_tick

    job_repo = app.config["JOB_REPO"]
    dashboard_on = app.config["APP_CONFIG"].dashboard_refresh_enabled
    schedule_tick = make_tick(db, job_repo, app.config.get("SCHEDULE_RUNNER"))

    def _tick_mirror():
        try:
            enqueue_refresh(job_repo)
        except Exception:  # noqa: BLE001 - a tick failure must not kill the scheduler
            app.logger.exception("dashboard mirror tick failed")

    scheduler = Scheduler()

    def _schedule_tick():
        try:
            schedule_tick()
        finally:
            status.beat_scheduler(db)

    def _cleanup():
        try:
            run_cleanup(db)
        except Exception:  # noqa: BLE001 - cleanup must not stop scheduling
            app.logger.exception("worker cleanup failed")

    scheduler.add_cron(
        "schedule-tick",
        _schedule_tick,
        minute="*",
    )
    scheduler.add_cron("cache-cleanup", _cleanup, hour=3, minute=15)
    # Dashboard customer mirror: rebuild every 4 hours (LIVE cadence). Skipped
    # entirely when the dashboard refresh is turned off.
    if dashboard_on:
        scheduler.add_cron("dashboard-mirror", _tick_mirror, hour="*/4", minute=5)
    scheduler.start()
    status.beat_scheduler(db)
    status.write_process_identity(db)
    app.config["SCHEDULER"] = scheduler
    app.logger.info("schedule cron started (dashboard mirror %s)",
                    "on" if dashboard_on else "OFF")
    _cleanup()

    # Prime the mirror on boot if it's empty so the dashboard isn't blank on a
    # cold container (LIVE does an immediate refresh when the cache is empty).
    if not dashboard_on:
        return
    try:
        if app.config["DASHBOARD_REPO"].count() == 0:
            enqueue_refresh(job_repo)
    except Exception:  # noqa: BLE001 - best-effort prime
        app.logger.exception("dashboard mirror prime failed")


def _seed_feature_flags(app: Flask, db) -> None:
    """Insert default feature flags on a fresh DB (idempotent)."""
    try:
        FeatureFlagRepository(db).seed_defaults()
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("feature-flag seed failed")


def _seed_report_config(app: Flask, db) -> None:
    try:
        ReportConfigRepository(db).seed_built()
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("report-config seed failed")


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


def _seed_developers(app: Flask, db) -> None:
    """Grant 'developer' to the emails in V3_DEVELOPER_EMAILS. Runs AFTER admins so
    a developer listed here also in V2_ADMIN_EMAILS ends up developer, not admin
    (developer outranks admin: it adds the dev tools). Creates the row if missing
    so an account that isn't in the live directory yet still works. Idempotent.
    """
    import os

    raw = os.environ.get("V3_DEVELOPER_EMAILS") or ""
    emails = [e.strip().lower() for e in raw.split(",") if e.strip()]
    if not emails:
        return
    try:
        with db.precious() as conn:
            for email in emails:
                conn.execute(
                    "INSERT INTO users(email, display_name, role, is_active,"
                    " can_see_company_views)"
                    " VALUES (?, '', 'developer', 1, 1)"
                    " ON CONFLICT(email) DO UPDATE SET role='developer', is_active=1,"
                    " can_see_company_views=1",
                    (email,),
                )
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("developer seed failed")


def _seed_users_from_live(app: Flask, db) -> None:
    """One-time Live directory import. Existing v3 roles are kept."""
    from web.data.seed_users import live_db_path, seed_users_from_live

    try:
        n = seed_users_from_live(db)
        if n:
            app.logger.info("mirrored %d users from live DB (%s)", n, live_db_path())
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("live user mirror failed")


# Live `--salesman all`: one file per salesman with an email.
_SALESMEN_ALL = {"period": "yesterday", "split_by_salesman": True}
# Invoiced always includes a Commissions sheet. Salesmen Shipped files should not.
_INVOICED_WITHOUT_COMMISSIONS = {
    "order": [
        "summary_by_customer", "full_data", "credits", "invoices",
        "audit_reversals", "totals_by_salesman",
    ],
}
# Per-rep Ordered files: drop By Salesman (the file is already one salesman).
_ORDERED_SALESMAN_FILE = {
    "order": ["summary", "by_customer", "by_item", "by_order", "full_data"],
}


_AZURE_SCHEDULES: list[dict] = [
    {
        "name": "Daily Invoiced Report",
        "report_key": "invoiced",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Invoiced Report/Daily",
    },
    {
        "name": "Daily Ordered Report",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "00:00"},
        "sharepoint_path": "Ordered Report/Daily",
    },
    {
        "name": "Daily Number 4 Report",
        "report_key": "number_4",
        "params": {},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Number 4 Report/Daily",
    },
    {
        "name": "Daily Ordered (9am)",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Ordered Report/Daily",
    },
    {
        "name": "Daily Salesmen Ordered (9am)",
        "report_key": "ordered",
        "params": _SALESMEN_ALL,
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Salesman Report/Daily",
        "layout": _ORDERED_SALESMAN_FILE,
    },
    {
        "name": "Daily Salesmen Shipped (9am)",
        "report_key": "invoiced",
        "params": _SALESMEN_ALL,
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Salesman Report/Daily",
        "layout": _INVOICED_WITHOUT_COMMISSIONS,
    },
    {
        "name": "Monthly Invoiced Report",
        "report_key": "invoiced",
        "params": {"period": "month"},
        "cadence": {"freq": "monthly", "time": "05:00", "monthday": 1},
        "sharepoint_path": "Invoiced Report/Monthly",
    },
    {
        "name": "Monthly Customer Activity",
        "report_key": "customer_activity",
        "params": {},
        "cadence": {"freq": "monthly", "time": "00:00", "monthday": 1},
        "sharepoint_path": "Salesman Report/Customer Activity/{Month} {YYYY}",
    },
    {
        "name": "Monthly Salesman Report",
        "report_key": "salesman",
        "params": {},
        "cadence": {"freq": "monthly", "time": "22:00", "monthday": 1},
        "sharepoint_path": "Salesman Report/Monthly",
    },
    {
        "name": "Monthly Salesmen Report",
        "report_key": "salesman",
        "params": {"split_by_salesman": True},
        "cadence": {"freq": "monthly", "time": "22:00", "monthday": 1},
    },
    {
        "name": "Amazon Monthly Ordered",
        "report_key": "ordered",
        "params": {"period": "month"},
        "cadence": {"freq": "monthly", "time": "19:59", "monthday": 28},
        "sharepoint_path": "Amazon Weekly",
    },
    {
        "name": "Weekly Amazon Ordered (Friday)",
        "report_key": "ordered",
        "params": {"period": "week"},
        "cadence": {"freq": "weekly", "time": "00:00", "weekdays": [4]},
        "sharepoint_path": "Amazon Weekly",
    },
]


# Live Azure Automation jobs as of 2026-08-13. Names match Azure. Email-only
# Live jobs have no stored recipients here — SharePoint is the delivery so the
# row can be saved; add addresses after you check each one. Skipped:
# amazon_weekly (no Beta report), leftover OrderReportDirect, and Daily 9am
# (customer 48999/917/2267 — deleted on Beta; boot must not put it back).
_LIVE_RUNBOOK_SCHEDULES: list[dict] = [
    {
        "name": "DailyInvoicedReport",
        "report_key": "invoiced",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Invoiced Report/Daily",
    },
    {
        "name": "DailyOrderReport",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "00:00"},
        "sharepoint_path": "Ordered Report/Daily",
    },
    {
        "name": "Daily 5am Number_4",
        "report_key": "number_4",
        "params": {},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Number 4 Report/Daily",
    },
    {
        "name": "Daily 9am Salesmen Ordered",
        "report_key": "ordered",
        "params": _SALESMEN_ALL,
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Salesman Report/Daily",
        "layout": _ORDERED_SALESMAN_FILE,
    },
    {
        "name": "Daily 9am Salesmen Shipped",
        "report_key": "invoiced",
        "params": _SALESMEN_ALL,
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Salesman Report/Daily",
        "layout": _INVOICED_WITHOUT_COMMISSIONS,
    },
    {
        "name": "Daily Open Orders Report",
        "report_key": "ordered",
        "params": {"period": "yesterday", "salesman": ["Hkaufman"], "status": ["Open order"]},
        "cadence": {"freq": "daily", "time": "11:00"},
        "sharepoint_path": "Ordered Report/Daily",
    },
    {
        "name": "Monthly Invoiced Report",
        "report_key": "invoiced",
        "params": {"period": "last_month"},
        "cadence": {"freq": "monthly", "time": "05:00", "monthdays": [1]},
        "sharepoint_path": "Invoiced Report/Monthly",
    },
    {
        "name": "Monthly 1st 12am Customer Activity",
        "report_key": "customer_activity",
        "params": {},
        "cadence": {"freq": "monthly", "time": "00:00", "monthdays": [1]},
        "sharepoint_path": "Salesman Report/Customer Activity/{Month} {YYYY}",
    },
    {
        "name": "Monthly 1st 12am Monthly Salesman",
        "report_key": "salesman",
        "params": {},
        "cadence": {"freq": "monthly", "time": "22:00", "monthdays": [1]},
        "sharepoint_path": "Salesman Report/Monthly",
    },
    {
        "name": "Monthly 1st 12am Monthly Salesmen",
        "report_key": "salesman",
        "params": {"split_by_salesman": True},
        "cadence": {"freq": "monthly", "time": "22:00", "monthdays": [1]},
    },
    {
        "name": "Amazon Monthly Ordered",
        "report_key": "ordered",
        "params": {"period": "mtd", "customers": ["9300", "9301"]},
        "cadence": {"freq": "monthly", "time": "19:59", "monthdays": [-1]},
        "sharepoint_path": "Amazon Weekly",
    },
    {
        "name": "Weekly 5pm Friday Amazon Ordered",
        "report_key": "ordered",
        "params": {"period": "last_7_days", "customers": ["9300", "9301"]},
        "cadence": {"freq": "weekly", "time": "00:00", "weekdays": [3]},
        "sharepoint_path": "Amazon Weekly",
    },
]


def _seed_master_schedules(app: Flask, db, rows: list[dict] | None = None,
                           *, inactive: bool = False) -> None:
    """Insert missing master_schedules. Existing and operator-deleted names stay put."""
    import sqlite3

    from web.data.repositories.schedules import MasterScheduleRepository
    from web.delivery.sharepoint import strip_reports_home
    from web.scheduling import cadence as C

    try:
        from web.data.repositories.app_settings import AppSettingsRepository

        repo = MasterScheduleRepository(db)
        skipped = AppSettingsRepository(db).skipped_seed_names()
        existing = {s.name for s in repo.list_all()}
        added = 0
        for s in (rows if rows is not None else _AZURE_SCHEDULES):
            if s["name"] in existing or s["name"] in skipped:
                continue
            try:
                repo.create(
                    s["report_key"], s["name"],
                    params=s.get("params", {}), layout=s.get("layout") or {},
                    cadence=C.normalize(s.get("cadence") or {"freq": "daily", "time": "08:00"}),
                    sharepoint_path=strip_reports_home(s.get("sharepoint_path", "")),
                    is_shared=True,
                    is_active=not inactive,
                )
            except sqlite3.IntegrityError:
                continue
            existing.add(s["name"])
            added += 1
        for s in (rows if rows is not None else _AZURE_SCHEDULES):
            layout = s.get("layout") or {}
            if layout.get("order"):
                repo.fill_layout_if_blank(s["name"], layout)
            if (s.get("params") or {}).get("split_by_salesman"):
                repo.enable_split_all_if_plain(s["name"])
        if added:
            state = "disabled" if inactive else "active"
            app.logger.info("seeded %d master schedules (%s) from Azure config", added, state)
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("master schedule seed failed")


def _seed_company_views(app: Flask, db) -> None:
    try:
        from web.scheduling.company_layouts import seed_canonical_company_views

        seed_canonical_company_views(db)
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("company view seed failed")
