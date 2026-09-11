# Area: settings, dashboard, data, jobs, health, devtools

**CodeGraph:** unavailable. Facts from named files.

## Settings (`web.blueprints.settings`)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/settings` | `settings.html` |
| GET | `/admin/run-log` | `run_log.html` |
| GET | `/admin/schedule-runs` | `schedule_runs.html` |
| POST | `/api/admin/feature-flags` | |
| POST | `/api/admin/report-visibility` | |
| POST | `/api/admin/schedule-test` | test send |
| POST | `/api/settings/exclusions` | customer exclusions |
| GET | `/api/settings/customers` | exclusion picker list |
| GET/POST | `/api/dev/beta-sources` | developer; report source Live vs v3 |
| POST | `/settings/theme` | |
| POST | `/api/settings/preferences` | theme + landing |

JS: `settings.ts`. Developer check uses `Authorization.is_developer` (DB row).

## Dashboard (`web.blueprints.dashboard`) — **not registered when `is_beta`**

| Method | Path | Notes |
|--------|------|-------|
| GET | `/dashboard` | `dashboard.html` |
| POST | `/api/dashboard/refresh` | enqueue mirror refresh |
| GET | `/api/dashboard/refresh-status` | |
| POST | `/api/dashboard/exclusion` | |
| GET | `/api/notifications` | |
| POST | `/api/notifications/dismiss` | |
| GET | `/customer/<account>` | `customer_detail.html` |

JS: `dashboard.ts`. Nav tab hidden on Beta. Flag `dashboard_enabled` AND (user opt-in OR privileged).

## Health

| GET | `/healthz` | `{"status":"ok"}` only |
| GET | `/manifest.json` | PWA, mount-aware `url_for` |

## Devtools (DB developer required)

| Method | Path |
|--------|------|
| GET | `/dev/db-explorer` |
| GET | `/api/dev/db/tables` |
| GET | `/api/dev/db/table/<table>` |
| POST | `/api/dev/db/table/<table>/cell` |
| DELETE | `/api/dev/db/table/<table>/row` |
| GET | `/dev/notif-diagnostic` |
| GET | `/api/dev/notif-diagnostic/<email>` |
| POST | `/api/dev/notif-diagnostic/<email>/run` |

Templates: `db_explorer.html`, `notif_diagnostic.html`. JS: `db_explorer.ts`, `notif_diag.ts`.

## Data layer

- `web.data.connection.from_config` — precious + cache sqlite
- `web.data.migrate.migrate` — `v3/web/data/migrations/precious/0001`–`0018`
- Repositories: users, salesmen, schedules, company_views, saved_reports, exports, exclusions, dashboard, app_settings, outbox, notifications, jobs, report_config, preferences, feature_flags, report_defaults, run_log
- Two DBs: precious (durable, Litestream in prod) and cache (report payloads)

Initial tables (0001): users, salesmen, user_salesman_access, user_report_access, user_preferences, user_exclusions, saved_reports, schedules, master_schedules, schedule_runs, report_run_log, notifications, jobs, feature_flags (plus later files).

0017: `users.sales_group`
0018: drop `user_salesman_access` FK to `salesmen`

## Jobs

`web.jobs.worker.JobWorker` — file-lock leader in gunicorn (`_is_background_leader`). `recover_orphans` on leader only.

## Feature flags (nav)

`order_entry_enabled`, `dashboard_enabled`, `test_site_enabled` (+ per-user `dashboard_enabled`, `test_access`).
