# Structure audit

Model: gpt-5.6-sol-medium
Runner: spawn
Area: settings-dashboard-data
Role: structure
Graph: graph via parent digest

## Proof of read

`AUDITOR-INSTRUCTIONS.md`: live scope is `/workspace/v3/`; application edits and from-scratch rewrite proposals are out of scope.
`graph-backbone/INDEX.md`: 4 audit areas, 5 worker job types, 4 roles; Beta shares the Live session and does not register the dashboard blueprint.
`graph-backbone/settings-dashboard-data.md`: 11 settings path rows (12 method routes), 7 dashboard paths, 8 devtool paths, and 2 health/PWA paths.
The area digest names 17 repositories, 18 precious migrations, 13 initial tables, and 2 databases; the cache side contains 5 migrations.

## Findings

### S1 — High: the global dashboard flag hides navigation but does not gate dashboard routes

- `web/__init__.py:_register_context` combines global `dashboard_enabled` with per-user/privileged access only for the injected navigation state.
- `web/blueprints/dashboard.py:_require_dashboard_user` checks only privilege or `users.dashboard_enabled`.
- On non-Beta mounts the blueprint remains registered regardless of the global feature flag, so `/dashboard`, refresh, exclusion, and customer-detail routes remain directly reachable while the feature is shown as off.
- This splits one access policy across presentation and route layers and makes the feature flag's meaning unreliable.

### S2 — High: notification diagnostics build executable markup from unescaped data

- `web/static_src/js/notif_diag.ts:load` assigns a template string to `out.innerHTML`.
- The string includes user fields, customer account/name, skip reasons, exclusions, and timestamps returned from the database/API.
- This developer-only surface still crosses a data-to-DOM trust boundary and can execute stored markup in a privileged session.

### S3 — Medium: the app factory is an 861-line composition, operations, and seed-data god file

- `web/__init__.py` contains app construction, request/session synchronization, dependency wiring, blueprint policy, Beta login gating, error handlers, CLI registration, migrations, leader election, worker startup, scheduler startup, direct job cleanup SQL, user/role seeding, schedule inventories, and company-view seeding.
- Settings/dashboard concerns therefore span the route modules and a large unrelated bootstrap module.
- `_register_reporting` alone constructs reporting, exports, delivery, scheduling, dashboard mirror, lookup, repositories, and the shared worker.

### S4 — Medium: migration policy is split between ordered SQL and boot-time schema repair

- `web/data/migrate.py:migrate` applies versioned SQL, then calls `_ensure_users_company_views_column`, `_ensure_users_sales_group_column`, and `convert_personal_schedules`.
- The module header says there are no ad-hoc boot-time `ALTER TABLE` operations, but both `_ensure_*` functions issue them.
- Migration state can therefore be produced by either migration files or repair branches, and the repair branches do not write the corresponding migration version.
- The generic duplicate-column recovery in `apply_migrations` records an entire migration version as applied; this is especially risky for multi-statement migrations such as `0016_can_see_company_views.sql`.

### S5 — Medium: `/healthz` is liveness-only despite being named as readiness

- `web/blueprints/health.py` always returns `{"status":"ok"}`.
- It does not establish that precious/cache SQLite can be opened, migrations completed, or the elected background worker is alive.
- `JobWorker.health` and `is_background_leader_process` expose the needed operational facts elsewhere, but the health blueprint does not compose them.

### S6 — Medium: the settings blueprint crosses route, query, policy, and developer-tool boundaries

- `web/blueprints/settings.py` contains personal preferences/exclusions, admin feature/report controls, delivery test settings, run-history views, and Beta source controls.
- `schedule_runs_page` directly queries `schedules` and `master_schedules` instead of using the repository boundary used for schedule runs.
- `_require_admin` actually accepts the broader privileged role set, while developer checks use a separate helper and route-local branches.
- Theme values are duplicated in `settings.py:_THEMES` and `web/data/repositories/preferences.py:THEMES`.

### S7 — Medium: exclusion writes have two different validation contracts

- `web.blueprints.settings.set_exclusion` checks that the customer exists and is in the principal's salesman scope.
- `web.blueprints.dashboard.toggle_exclusion` writes any non-empty account without either check.
- Both routes mutate `ExclusionRepository`, so correctness depends on which screen issued the same domain operation.
- The dashboard route also dereferences `row.id` unconditionally after allowing privileged principals even when no user row was resolved.

### S8 — Medium: dashboard refresh returns a job contract that its client discards

- `web.blueprints.dashboard.refresh` returns `job_id` with HTTP 202.
- `web/static_src/js/dashboard.ts:doRefresh` ignores the response status and body, then polls aggregate `last_refreshed` for up to 40 attempts.
- A rejected enqueue, deduped job, or failed job is indistinguishable from a slow refresh; the durable job state is not used by this flow.

### S9 — Low: the settings client is a multi-feature controller

- `web/static_src/js/settings.ts` is 337 lines covering accordion state, flags, report visibility, customer lookup polling, exclusions, Beta sources, and schedule test recipients.
- Each concern has its own endpoint and DOM section, but all lifecycle and request behavior is coupled to one entrypoint.
- Error presentation is inconsistent: some controls silently roll back while others show messages.

### S10 — Low: the generic database editor bypasses repository invariants

- `web/blueprints/devtools.py` permits updates to every known column, including primary keys, and deletes any row with a single-column primary key.
- `web/static_src/js/db_explorer.ts` renders every value as an editable text input.
- Developer authorization and identifier allow-listing prevent arbitrary SQL, but domain validation, audit logging, foreign-key-aware affordances, and undo are absent.

### S11 — Low: worker diagnostics depend on a private synchronization field

- `web/jobs/worker.py:health` and `_loop` read `BoundedSemaphore._value`.
- This private implementation detail is used for operational status and heartbeat logging.
- `running` means a poller object exists, while `health.poller_alive` carries the actual liveness state; callers can easily select the weaker signal.

## Coverage skeleton

### Routes and composition

- `web/__init__.py`: `create_app`, `_register_reporting`, `_register_context`, `_register_blueprints`, `bootstrap_background`, `_is_background_leader`, `_start_scheduler`
- `web/blueprints/settings.py`: `settings_page`, `run_log_page`, `schedule_runs_page`, `set_feature_flag`, `set_report_visibility`, `set_schedule_test`, `set_exclusion`, `settings_customers`, `get_beta_sources`, `set_beta_source`, `set_theme`, `set_preferences`
- `web/blueprints/dashboard.py`: `dashboard`, `refresh`, `refresh_status`, `toggle_exclusion`, `notifications`, `dismiss_notification`, `customer_detail`
- `web/blueprints/devtools.py`: `db_explorer_page`, `api_list_tables`, `api_get_rows`, `api_update_cell`, `api_delete_row`, `notif_diagnostic_page`, `api_notif_diagnostic`, `api_notif_diagnostic_run`
- `web/blueprints/health.py`: `healthz`, `manifest`

### Dashboard and jobs

- `web/dashboard/jobs.py`: `DASHBOARD_REFRESH_JOB_TYPE`, `enqueue_refresh`, `make_refresh_handler`
- `web/dashboard/mirror.py`: `MirrorService`
- `web/dashboard/service.py`: `DashboardSummary`, `DashboardService`
- `web/dashboard/notifications.py`: `generate_overdue_notifications`, `diagnose_overdue`
- `web/jobs/worker.py`: `JobContext`, `JobWorker`

### Data

- `web/data/connection.py`: `_connect`, `Database`, `from_config`
- `web/data/migrate.py`: `apply_migrations`, `migrate`, `migrate_cache_only`, `_ensure_users_company_views_column`, `_ensure_users_sales_group_column`
- `web/data/repositories/app_settings.py`: `AppSettingsRepository`
- `web/data/repositories/company_views.py`
- `web/data/repositories/dashboard.py`: `DashboardCustomer`, `DashboardRepository`
- `web/data/repositories/exclusions.py`: `ExclusionRepository`
- `web/data/repositories/exports.py`
- `web/data/repositories/feature_flags.py`: `FeatureFlagRepository`
- `web/data/repositories/jobs.py`: `Job`, `JobRepository`
- `web/data/repositories/notifications.py`
- `web/data/repositories/outbox.py`
- `web/data/repositories/preferences.py`: `Preferences`, `PreferencesRepository`
- `web/data/repositories/report_config.py`
- `web/data/repositories/report_defaults.py`
- `web/data/repositories/run_log.py`
- `web/data/repositories/salesmen.py`
- `web/data/repositories/saved_reports.py`
- `web/data/repositories/schedules.py`
- `web/data/repositories/users.py`
- `web/data/migrations/precious/0001_initial.sql` through `0018_usa_drop_salesmen_fk.sql`
- `web/data/migrations/cache/0001_initial.sql` through `0005_export_retention.sql`

### UI

- `web/templates/settings.html`
- `web/templates/dashboard.html`
- `web/templates/customer_detail.html`
- `web/templates/run_log.html`
- `web/templates/schedule_runs.html`
- `web/templates/db_explorer.html`
- `web/templates/notif_diagnostic.html`
- `web/static_src/js/settings.ts`
- `web/static_src/js/dashboard.ts`
- `web/static_src/js/db_explorer.ts`
- `web/static_src/js/notif_diag.ts`

## CodeGraph queries deferred

- `impact _require_dashboard_user`
- `callers FeatureFlagRepository.is_enabled`
- `callers ExclusionRepository.set`
- `callers JobWorker.health`
- `callers JobWorker.running`
- `impact migrate`
- `explore "dashboard refresh enqueue status client"`
- `explore "bootstrap_background leader worker scheduler"`
