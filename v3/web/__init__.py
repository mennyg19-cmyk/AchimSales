"""v3 web app factory.

Boots fail-closed: load_config() raises in prod on insecure settings (rule 6),
so an unsafe container never serves traffic. The factory wires config, CSRF, the
"new app" marker, and blueprints. Heavy subsystems (data, jobs, reporting) are
registered as later phases land - this file stays thin.
"""

from __future__ import annotations

import os
import time

from flask import Flask, jsonify, session

_ASSET_VERSION = str(int(time.time()))

from web.auth.authorization import Authorization, Forbidden
from web.auth.session import current_principal
from web.config import Config, load_config
from web.data.connection import from_config
from web.data.repositories.feature_flags import FeatureFlagRepository
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

    from report_engine.lib import iso_date as _iso_date
    app.jinja_env.filters["iso_date"] = _iso_date

    # v3 shares its host with the live app (/) and optionally rebuild (/test-next)
    # and beta (/beta). Each mount needs its own session cookie name so they don't
    # stomp each other (symptom: "No auth flow in session" at callback).
    app.config["SESSION_COOKIE_NAME"] = "beta_session" if cfg.is_beta else "v3_session"
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
    worker = JobWorker(db)
    run_log = ReportRunLogRepository(db)
    worker.register(JOB_TYPE, make_report_run_handler(runner, service.builder_for, run_log))

    exports = ExportRepository(db)
    worker.register(EXPORT_JOB_TYPE, make_export_handler(
        cache, exports, JobRepository(db), app.config["AUTHZ"]))

    sharepoint = SharePointService(cfg)
    email = EmailService(cfg, OutboxRepository(db), sharepoint)
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
    from web.auth.session import sync_role

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
            "login": _safe_url("auth.login_page"),
            "logout": _safe_url("auth.logout_route"),
        }
        p = current_principal()
        user = None
        dashboard_enabled = False
        order_entry_enabled = False
        test_site_enabled = False
        theme = session.get("theme")
        if p is not None:
            user = {"name": p.name, "role": p.role, "_dev": p.is_dev}
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
            # Beta is reports-only: never show dashboard/schedules tabs.
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

    # Beta is reports-only (grill): no dashboard / schedules surface.
    if not cfg.is_beta:
        from web.blueprints.dashboard import dashboard_bp
        from web.blueprints.schedules import schedules_bp

        app.register_blueprint(dashboard_bp)
        app.register_blueprint(schedules_bp)


def _register_beta_access_gate(app: Flask, cfg: Config) -> None:
    """Hard-gate /beta: no Live beta_access_enabled => 403 even on direct URL."""
    if not cfg.is_beta:
        return

    from flask import abort, redirect, request, url_for

    from web.beta_access import user_has_beta_access

    @app.before_request
    def _require_beta_access():
        if request.endpoint in (None, "static"):
            return None
        # Allow health + login/callback so people can sign in, then gate the rest.
        ep = request.endpoint or ""
        if ep.startswith("health.") or ep.startswith("auth."):
            return None
        p = current_principal()
        if p is None:
            return redirect(url_for("auth.login"))
        if not user_has_beta_access(p.email):
            abort(403)
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


def bootstrap_background(app: Flask) -> None:
    """Prod-only side effects: migrate, seed admins/salesmen, start the worker.

    Kept OUT of create_app so tests can build an app without spawning threads or
    touching schema. The wsgi entrypoint calls this once per process. Seeding is
    individually guarded so a bad data file can never stop the app from booting.
    """
    from web.data.migrate import migrate

    db = app.config["DB"]
    migrate(db)
    _seed_feature_flags(app, db)      # default flags so nav gating is deterministic
    _seed_salesmen_if_empty(app, db)  # salesmen first: user_salesman_access FKs them
    _seed_users_from_live(app, db)    # mirror the live user directory into v3
    _seed_admins(app, db)             # explicit env admins override the mirror
    _seed_developers(app, db)         # explicit env developers win last (outrank admin)
    cfg = app.config["APP_CONFIG"]
    if not getattr(cfg, "is_beta", False):
        _seed_master_schedules(app, db)   # migrate Azure Automation schedules into v3
    else:
        app.logger.info("beta mode: skipping master schedule seed")

    # Background OWNERSHIP (the job worker + the cron scheduler + orphan recovery)
    # must run in exactly ONE process. Under gunicorn we have multiple workers, so
    # we elect a single owner with an exclusive OS file lock (see
    # _is_background_leader). Without this, every worker's recover_orphans() would
    # requeue jobs another worker is actively running -> duplicate report
    # deliveries + schedule fires.
    if _is_background_leader(app):
        app.logger.info("v3 background ownership acquired by this worker (pid=%s)", os.getpid())
        worker = app.config.get("JOB_WORKER")
        if worker is not None:
            worker.start()
        if not app.config["APP_CONFIG"].dashboard_refresh_enabled:
            _cancel_pending_dashboard_refreshes(app, db)
        # Beta is reports-only: no schedule cron (Live owns schedules).
        if not getattr(app.config["APP_CONFIG"], "is_beta", False):
            _start_scheduler(app, db)
    else:
        app.logger.info("v3 background ownership held by another worker; skipping (pid=%s)", os.getpid())


# Held open for the whole process lifetime so the advisory lock below stays held.
_BG_LOCK_FH = None


def is_background_leader_process() -> bool:
    """True in the one gunicorn worker that won the background lock (and therefore
    actually runs the job poller + scheduler). Lets the admin diagnostic say
    whether it's talking to the leader or a follower."""
    return _BG_LOCK_FH is not None


def _is_background_leader(app: Flask) -> bool:
    """Elect exactly ONE process to own v3 background work (job worker + cron).

    Uses a real OS advisory lock instead of the gunicorn env signal. That signal
    depends on post_fork setting the env BEFORE the worker imports the app, which
    is unreliable in our dispatcher: the live app is imported during the worker's
    synchronous load while v3 bootstraps in a later daemon thread, so the two read
    different env values (observed in prod). An exclusive, non-blocking flock is
    immune to that ordering - the one worker that grabs it wins and holds it until
    the process dies.

    Fail-open to leader=True when fcntl is unavailable (Windows/local dev) or the
    lock can't be taken for an unexpected reason, so single-process/dev still runs
    background work.
    """
    global _BG_LOCK_FH
    try:
        import fcntl
    except Exception:  # noqa: BLE001 - non-POSIX (local dev): single process owns it
        return True
    cfg = app.config["APP_CONFIG"]
    lock_path = cfg.precious_db_path.parent / ".v3-background.lock"
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(lock_path, "w")  # noqa: SIM115 - intentionally kept open
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False  # another worker already holds the lock
    except Exception:  # noqa: BLE001 - never block boot on an unexpected lock error
        app.logger.exception("v3 background lock errored; assuming leader")
        return True
    _BG_LOCK_FH = fh  # keep the handle alive so GC can't drop the lock
    return True


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
    """Start the once-a-minute cron tick that enqueues due schedules.

    Best-effort: if APScheduler isn't installed (e.g. some local envs) the tick
    simply doesn't run - schedules can still be triggered with "Run now" - and
    boot is never blocked.
    """
    from web.dashboard.jobs import enqueue_refresh
    from web.jobs.scheduler import Scheduler
    from web.scheduling.tick import make_tick

    job_repo = app.config["JOB_REPO"]
    dashboard_on = app.config["APP_CONFIG"].dashboard_refresh_enabled

    def _tick_mirror():
        try:
            enqueue_refresh(job_repo)
        except Exception:  # noqa: BLE001 - a tick failure must not kill the scheduler
            app.logger.exception("dashboard mirror tick failed")

    try:
        scheduler = Scheduler()
        scheduler.add_cron("schedule-tick", make_tick(db, job_repo), minute="*")
        # Dashboard customer mirror: rebuild every 4 hours (LIVE cadence). Skipped
        # entirely when the dashboard refresh is turned off.
        if dashboard_on:
            scheduler.add_cron("dashboard-mirror", _tick_mirror, hour="*/4", minute=5)
        scheduler.start()
        app.config["SCHEDULER"] = scheduler
        app.logger.info("schedule cron started (dashboard mirror %s)",
                        "on" if dashboard_on else "OFF")
    except Exception:  # noqa: BLE001 - scheduler is optional; never block boot
        app.logger.exception("scheduler start failed (schedules will only run via Run now)")

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
                    "INSERT INTO users(email, display_name, role, is_active)"
                    " VALUES (?, '', 'developer', 1)"
                    " ON CONFLICT(email) DO UPDATE SET role='developer', is_active=1",
                    (email,),
                )
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("developer seed failed")


def _seed_users_from_live(app: Flask, db) -> None:
    """Mirror the live app's user directory (roles + flags) into v3's users table.

    Live (webapp/) is the authoritative list of who may sign in. Reading it here
    means every existing account works on /test without manual re-entry. Guarded:
    a missing/locked live DB must never block boot.
    """
    from web.data.seed_users import live_db_path, seed_users_from_live

    try:
        n = seed_users_from_live(db)
        if n:
            app.logger.info("mirrored %d users from live DB (%s)", n, live_db_path())
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("live user mirror failed")


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


_AZURE_SCHEDULES: list[dict] = [
    {
        "name": "Daily Invoiced Report",
        "report_key": "invoiced",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Direct Reports/Invoiced Report/Daily",
    },
    {
        "name": "Daily Ordered Report",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "00:00"},
        "sharepoint_path": "Direct Reports/Ordered Report/Daily",
    },
    {
        "name": "Daily Number 4 Report",
        "report_key": "number_4",
        "params": {},
        "cadence": {"freq": "daily", "time": "05:00"},
        "sharepoint_path": "Direct Reports/Number 4 Report/Daily",
    },
    {
        "name": "Daily Ordered (9am)",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Direct Reports/Ordered Report/Daily",
    },
    {
        "name": "Daily Salesmen Ordered (9am)",
        "report_key": "ordered",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Direct Reports/Salesman Report/Daily",
    },
    {
        "name": "Daily Salesmen Shipped (9am)",
        "report_key": "invoiced",
        "params": {"period": "yesterday"},
        "cadence": {"freq": "daily", "time": "09:00"},
        "sharepoint_path": "Direct Reports/Salesman Report/Daily",
    },
    {
        "name": "Monthly Invoiced Report",
        "report_key": "invoiced",
        "params": {"period": "month"},
        "cadence": {"freq": "monthly", "time": "05:00", "monthday": 1},
        "sharepoint_path": "Direct Reports/Invoiced Report/Monthly",
    },
    {
        "name": "Monthly Customer Activity",
        "report_key": "customer_activity",
        "params": {},
        "cadence": {"freq": "monthly", "time": "00:00", "monthday": 1},
        "sharepoint_path": "Direct Reports/Salesman Report/Customer Activity",
    },
    {
        "name": "Monthly Salesman Report",
        "report_key": "salesman",
        "params": {},
        "cadence": {"freq": "monthly", "time": "22:00", "monthday": 1},
        "sharepoint_path": "Direct Reports/Salesman Report/Monthly",
    },
    {
        "name": "Amazon Monthly Ordered",
        "report_key": "ordered",
        "params": {"period": "month"},
        "cadence": {"freq": "monthly", "time": "19:59", "monthday": 28},
        "sharepoint_path": "Direct Reports/Amazon Weekly",
    },
    {
        "name": "Weekly Amazon Ordered (Friday)",
        "report_key": "ordered",
        "params": {"period": "week"},
        "cadence": {"freq": "weekly", "time": "00:00", "weekdays": [4]},
        "sharepoint_path": "Direct Reports/Amazon Weekly",
    },
]


def _seed_master_schedules(app: Flask, db) -> None:
    """Seed master_schedules from the current Azure Automation configuration.

    Uses upsert-by-name: inserts any schedule whose name doesn't already exist.
    Existing schedules (including manually edited ones) are left untouched.
    """
    from web.data.repositories.schedules import MasterScheduleRepository

    try:
        repo = MasterScheduleRepository(db)
        existing = {s.name for s in repo.list_all()}
        added = 0
        for s in _AZURE_SCHEDULES:
            if s["name"] in existing:
                continue
            repo.create(
                s["report_key"], s["name"],
                params=s.get("params", {}), layout={},
                cadence=s.get("cadence", {}),
                sharepoint_path=s.get("sharepoint_path", ""),
            )
            added += 1
        if added:
            app.logger.info("seeded %d master schedules from Azure config", added)
    except Exception:  # noqa: BLE001 - seeding must never block boot
        app.logger.exception("master schedule seed failed")
