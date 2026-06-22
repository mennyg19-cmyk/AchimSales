# Graph backbone — Area C: Platform (auth, jobs, data, delivery, scheduling, config, deploy)

Factual map only. Scope = what the invoiced report + confirmed shell features
need. Note deferred areas (dashboard repos/metrics/mirror, master schedules) but
don't deep-audit them.

## Auth (`v3/web/auth/`)
- `msal_flow.py` — Entra/Microsoft login (MSAL); the company-login requirement.
- `session.py` — `current_principal`, session user.
- `principal.py` — Principal, roles (`ROLE_DEVELOPER`, admin/manager/salesman).
- `authorization.py` — central authz: `assert_report_runnable`, `can_view_report`,
  `visible_salesman_keys` (scope), impersonation.
- `decorators.py` — `require_login`.
- Blueprint `blueprints/auth.py` (login/logout/switch), `blueprints/settings.py`
  (theme/preferences), `blueprints/admin.py` (users, salesman access, report
  access), `blueprints/health.py` (manifest/health).

## Jobs (`v3/web/jobs/`)
- `worker.py` — in-process durable job worker (Handler, JobContext, drain, leader).
- `scheduler.py` — periodic scheduler tick.
- Job wiring for reports in `web/reporting/jobs.py`; exports in `export_jobs.py`;
  delivery in `web/delivery/jobs.py`; scheduling in `web/scheduling/jobs.py`.

## Data (`v3/web/data/`)
- `connection.py` — Database: `precious()` (durable) + `cache()` (disposable) SQLite.
- `migrate.py` — schema migrations.
- `repositories/`: jobs, users, saved_reports (presets), salesmen, exports,
  run_log (audit), preferences, notifications, exclusions, feature_flags
  (+ deferred: dashboard, schedules for the deferred pages).
- `seed_users.py`, `seed_salesmen.py` — seeds.

## Delivery (`v3/web/delivery/`)
- `email.py` (EmailService, split_recipients, outbox), `sharepoint.py`,
  `service.py`, `jobs.py` (delivery job), `layout.py`.

## Scheduling (`v3/web/scheduling/`)
- `runner.py`, `tick.py`, `cadence.py`, `jobs.py` — recurring report delivery.

## App wiring + deploy
- `web/__init__.py` create_app (config, blueprints, worker, scheduler, leader
  election, `_ASSET_VERSION` cache-busting), `web/config.py` Config (incl.
  `dashboard_refresh_enabled`), `web/wsgi.py` + root `wsgi.py` (DispatcherMiddleware
  mounts v3 at `/test`).
- Persistence: local-disk SQLite + Litestream → Azure Storage (acct
  `achimsalesreportsv3`, container `litestream`, RG `AchimReportsApp`). NEVER SMB.
- Deploy: `deploy.ps1` → Azure App Service `achim-sales-reports`
  (`reports.achimonline.com`), v3 mounted at `/test`.

## Non-negotiables this area must preserve (rebuild)
- Entra company login; central authz on every data route; CSRF on writes;
  refuse insecure prod boot; durable jobs (no long work in request handlers);
  local SQLite + Litestream (Postgres = documented off-ramp); audit/run log.

## What auditors must cover (Area C)
- Inventory: auth/login/logout/impersonation, admin user + access management,
  settings/theme, job lifecycle + recovery, email + schedule delivery, audit log,
  migrations, config/boot safety, deploy + persistence.
- Structure: SMB/SQLite history, OOM/crash-loop history, worker saturation, the
  SQLite-vs-Postgres open question, repository interface seams for the off-ramp.
