# v2 Test Subtree Full Audit, Manual, and Rebuild Brief

Scope: `test/` only. The root `webapp/`, root `reports/`, root `core/`, Azure runbook, and deploy scripts are the live tree and are out of scope except where the v2 code imports from them or mirrors their behavior. Inside `test/` there is no `run.py`, no Azure Automation runbook, and no deploy script. The v2 equivalents are the Flask routes, the report runner, the schedule runner, and the mirror/scheduler services.

## 1. Executive Summary

The `test/` folder is not an empty mock shell. It is a full v2 rebuild mounted under `/v2`, with Flask, MSAL/dev auth, SQLite persistence, report access control, user/admin settings, saved presets, personal and master schedules, an HTTP client for the D365 Reporting API, SQLite mirror tables, stale-while-revalidate report cache, dashboard cache, SharePoint upload/browse support, Excel export, email outbox delivery, and a large diagnostics console.

The strongest parts are the HTTP Reporting API boundary, the report registry, the route modularity, the cache-first user experience, and the attempt to separate v2 from the live `webapp/`. The weakest parts are security defaults, SQLite durability on Azure App Service, very large god files, duplicated report business logic, request-thread heavy work, informal migrations, and front-end sprawl.

My rebuild position: keep the Reporting API boundary and the mirror concept, but move precious app data to managed Postgres, collapse cache layers, centralize authorization, share one report engine with the live CLI/runbook reports, and put long-running report/export/schedule work behind a real job queue.

## 2. File Inventory Reviewed

Top-level `test/`:

- `README.md`: stale overview. It still describes a phase-1 mock shell, but the code is now a working app.
- `requirements.txt`: Flask, Gunicorn, pandas/openpyxl, MSAL, SQLAlchemy/APScheduler, pyodbc, WeasyPrint, Jinja2.
- `smoke_settings.py`: end-to-end smoke test for user and permissions admin APIs.
- `__init__.py`: empty package marker.
- `fixtures/ordered_dump.json`: sample `salesline_release` rows for ordered-report shape.
- `docs/v2-audit-and-rebuild-opus48.md`: prior audit focused on headline risks and rebuild plan.

Config:

- `config/settings.py`: environment-driven v2 settings: DB path, Azure hot/persistent DB behavior, outbox, `/v2` prefix, auth mode, MSAL credentials, admin emails, dev user.
- `config/reports.py`: report registry and capabilities.
- `config/__init__.py`: empty package marker.

Application:

- `webapp/app.py`: app factory, session config, root/health/manifest routes, blueprint registration, DB/mirror/scheduler startup.
- `webapp/auth.py`: current user resolution, admin detection, decorators, dev login, MSAL login, user upsert.
- `webapp/db.py`: SQLite schema, migrations, seed data, user/salesman/permission/preference/schedule helpers, retry logic, JSON backup for critical data.
- `webapp/__init__.py`: empty package marker.

Blueprints:

- `auth_bp.py`: login/logout routes.
- `reports.py`: report list, filter form, report viewer.
- `report_api.py`: lookup APIs, report run/export/email APIs, SharePoint browser APIs, Reporting API probe.
- `presets.py`: saved report CRUD.
- `notifications.py`: notification list/dismiss APIs.
- `dashboard.py`: dashboard, customer/order drilldowns, dashboard refresh/data APIs.
- `customer_last_order.py`: custom customer picker and recent-order/detail report.
- `schedules.py`: personal schedules CRUD/run/history.
- `master_schedules.py`: shared/admin master schedules CRUD/run/history.
- `_schedule_common.py`: schedule validation and recipient parsing.
- `settings_bp.py`: preferences, exclusions, users, salesmen, permissions, flags, run log.
- `diag.py`: admin diagnostics, mirror refresh/backfill, DB repair, probes.
- `blueprints/__init__.py`: empty package marker.

Services:

- `report_runner.py`: maps report keys to builders, calls Reporting API, applies tab rules.
- `reporting_api.py`: HTTP client, report parameter translation, cache/mirror fallback, lookup cache.
- `cache_first.py`: SQLite stale-while-revalidate cache and async job tracking.
- `report_layouts.py`: normalizes hidden tabs/columns and duplicate tab layouts.
- `report_export.py`: server-side Excel writer for tab payloads.
- `email_outbox.py`: sandbox email delivery as `.eml` files plus DB outbox log.
- `sharepoint.py`: Microsoft Graph SharePoint folder listing and upload helpers with mock fallback.
- `schedule_runner.py`: runs one schedule, writes Excel, emails/uploads, records debug logs.
- `mirror_scheduler.py`: APScheduler setup, persistent job store, single-owner guard.
- `mirror_refresh.py`: chunked customer/salesline/invoice refresh and backfill orchestration.
- `mirror.py`: mirror schema, upserts, fallback reads, sales-header/dashboard materialization.
- `db_sync.py`: Azure `/tmp` hot DB bootstrap/snapshot/salvage to `/home/data`.
- `dashboard_data.py`: dashboard aggregation, exclusions, role scoping, background refresh.
- `customer_last_order.py`: recent-order lookup and detail aggregation.
- `_archive_mock_data.py.txt`: obsolete mock salesman/customer fixture.
- `services/__init__.py`: empty package marker.

Report builders:

- `reports/ordered.py`: ordered report normalization and aggregations.
- `reports/invoiced.py`: invoiced report, credits, commission summaries.
- `reports/salesman.py`: month-by-month salesman report.
- `reports/number_4.py`: rolling 12-month and YTD item/customer report.
- `reports/customer_activity.py`: customer activity tabs by salesman.
- `reports/__init__.py`: package docstring.

Templates:

- `base.html`: app shell, header, bottom nav, flash display, theme and notifications hooks.
- `login.html`: dev/MSAL login UI.
- `reports.html`: report cards and saved presets.
- `report_form.html`: filter form and API preview.
- `report_view.html`: Tabulator viewer shell and modals.
- `dashboard.html`: customer activity dashboard shell.
- `customer.html`: customer drilldown and dashboard inclusion toggle.
- `order.html`: sales order drilldown.
- `settings.html`: preferences, exclusions, admin users/permissions/flags/log.
- `schedules.html`: personal schedules list/run/delete/history.
- `master_schedules.html`: master schedules list and CRUD modal.
- `schedule_history.html`: schedule run history.
- `schedule_run_detail.html`: one schedule run with debug log.
- `diag.html`: diagnostics console.
- `customer_last_order_pick.html`: custom report customer picker.
- `customer_last_order_view.html`: custom report detail.

Static assets:

- `static/style.css`: full mobile-first theme, page layouts, modals, report viewer, settings, diagnostics, SharePoint picker.
- `static/app.js`: older report-form/run/history script and notifications.
- `static/dashboard.js`: lazy dashboard load, refresh polling, filtering/sorting.
- `static/table_tools.js`: generic table expand/resize/autofit enhancer.
- `static/help_content.js`: user-facing help text.
- `static/js/report_form.js`: modern report filter page controller.
- `static/js/report_view.js`: large Tabulator viewer, sorting/grouping/filtering, layout persistence, export/email/schedule/preset UI.
- `static/js/settings.js`: settings/admin page behavior.
- `static/js/sharepoint_picker.js`: SharePoint folder picker modal.
- `static/_live_report_form.js`: older preset/autostart helper.
- `static/icon-192.png`, `static/icon-512.png`: PWA icons.

## 3. User Instruction Manual

### Local v2 App

1. Install dependencies from the repo root with `pip install -r test/requirements.txt`.
2. Set local environment as needed. Minimum useful dev values are `V2_AUTH_MODE=dev`, `V2_FLASK_SECRET=<secret>`, `V2_URL_PREFIX=/v2`, and optionally `V2_ADMIN_EMAILS=<email>`.
3. Run with `python -m flask --app wsgi:application run --port 5002`.
4. Open `/v2/login`. In dev mode, enter an email and optional display name. In MSAL mode, use Microsoft login.

Key environment controls:

- `V2_AUTH_MODE`: `dev` or `msal`. Defaults to `dev`, which is unsafe outside local development.
- `V2_FLASK_SECRET`: session signing secret. Must be set in real deployments.
- `V2_URL_PREFIX`: mount path, default `/v2`.
- `V2_APP_DB`: overrides the SQLite file path.
- `V2_OUTBOX_DIR`: where `.eml` files are written.
- `V2_ADMIN_EMAILS`: comma-separated bootstrap admins.
- `REPORTING_API_BASE_URL` and `REPORTING_API_KEY`: live on-prem Reporting API connection.
- SharePoint/Graph settings are consumed by `sharepoint.py`; without them, folder browsing falls back to mock behavior.

### Authentication

- `/v2/login`: shows login. In dev mode, it shows a self-serve dev form. In MSAL mode, it offers Microsoft sign-in.
- `/v2/login/dev`: posts an email/display name and creates or updates a local app user.
- `/v2/login/start`: starts MSAL auth-code login.
- `/v2/auth/callback`: completes MSAL and upserts the user.
- `/v2/logout`: clears session.

Roles:

- `admin`: full settings, diagnostics, all reports, master schedule CRUD.
- `developer`: treated as privileged in much of the app.
- `manager`: can be scoped to assigned salesmen.
- `salesman`: scoped to own salesman key where report access applies.

### Reports Page and Filter Form

- `/v2/reports`: shows report cards the current user can access plus saved presets. Presets can run a report with stored parameters and optional layout.
- `/v2/report/<key>`: shows filters based on the report registry. Period, status, year, salesman, and customer controls appear only when that report declares them.
- The API preview panel shows the outbound Reporting API endpoint/body that will be used.
- Submitting the form navigates to `/v2/report/<key>/view?<filters>`.

Report registry:

- `ordered`: enabled. Period/status/salesman/customer filters. Uses `salesline_release`.
- `invoiced`: enabled. Period/salesman/customer filters. Uses `invoiced_order_charges`.
- `salesman`: enabled. Year filter. Uses invoiced data for current/prior year comparisons.
- `number_4`: enabled. No user filters. Uses `invoice_lines`.
- `amazon_weekly`: registered but not wired in `report_runner.py`.
- `customer_activity`: enabled. In-app/dashboard style activity report from customer and salesline data.
- `customer_last_order`: enabled and in-app only. Uses its own blueprint instead of the generic viewer.
- `customer_aging`: registered/help text exists, but no builder is wired in the v2 runner.

### Report Viewer

- `/v2/report/<key>/view`: loads the report via `/api/reports/<key>/run`.
- Data is requested using `cache_first`: return fresh cache if available, stale cache if necessary, and poll a background refresh job.
- Tabs are rendered with Tabulator. Users can hide columns, hide tabs, duplicate tabs, reorder columns, apply per-column filters, sort, group, reset layout, and restore hidden items.
- Data-source badges show live/cache/mirror/error state.
- Export downloads an `.xlsx`.
- Email sends an `.eml` to the sandbox outbox and can optionally save to SharePoint.
- Schedule opens the personal schedule modal.
- Save preset stores parameters and optionally layout.

### Saved Presets

- `GET /api/saved-reports`: list current user's presets.
- `POST /api/saved-reports`: create a preset. Admins can save for another user.
- `DELETE /api/saved-reports/<id>`: delete own preset or, for admins, any preset.

### Personal Schedules

- `/v2/schedules/`: list personal schedules.
- Create schedules from the report viewer. Choose cadence, days, time, start/end, recipients, and optional SharePoint folder.
- `POST /v2/schedules/api`: create.
- `DELETE /v2/schedules/api/<id>`: delete.
- `POST /v2/schedules/api/<id>/run`: run immediately.
- `/v2/schedules/<id>/history`: view schedule history.
- `/v2/schedules/run/<run_id>`: view one run and debug log.

### Master Schedules

- `/v2/master-schedules/`: list shared schedules.
- Admins can create, edit, delete, and run. Non-admin users can view.
- `POST /v2/master-schedules/api`: create.
- `POST /v2/master-schedules/api/<id>`: update.
- `DELETE /v2/master-schedules/api/<id>`: delete.
- `POST /v2/master-schedules/api/<id>/run`: run now.
- History routes mirror personal schedules.

### Dashboard

- `/v2/dashboard`: lazy-loads dashboard summary and customer table from `/api/dashboard/data`.
- Cards filter customers by total/new/active/overdue/inactive.
- Search and salesman dropdown filter the table client-side.
- `POST /api/dashboard/refresh`: starts background mirror refresh.
- `GET /api/dashboard/refresh-status`: polls progress.
- `GET /api/dashboard/data`: returns summary, salesmen, customers, and refresh metadata.
- `/v2/customer/<account>`: customer drilldown with contact/activity/order data and inclusion toggle.
- `/v2/order/<order_number>`: order header and lines.

### Customer Last Order

- `/v2/report/customer-last-order/`: customer picker.
- `/v2/report/customer-last-order/customers.json`: customer list.
- `/v2/report/customer-last-order/<account>/recent-orders.json`: recent orders for the account.
- `/v2/report/customer-last-order/<account>`: detail page with selected/default recent order and lines.

### Settings

- `/v2/settings`: user preferences and admin controls.
- Preferences: theme, landing page, default tab.
- Customer exclusions: exclude customers from dashboard calculations/notifications.
- Admin feature flags: enable/disable global app features.
- Users and permissions: create/update/delete users and salesmen, assign roles, link salesman identity, grant report overrides, assign managers to salesmen, toggle dashboard/SharePoint/external access.
- Report run log: admin view of report run history.

Settings APIs:

- `/api/settings/preferences` GET/POST.
- `/api/settings/exclusions` GET/POST.
- `/api/settings/toggle-customer-exclusion` POST.
- `/api/settings/admin/feature-flag` POST.
- `/api/settings/admin/users` GET/POST.
- `/api/settings/admin/users/add` POST.
- `/api/settings/admin/users/delete` POST.
- `/api/settings/admin/users/report-access` POST.
- `/api/settings/admin/users/salesman-access` POST.
- `/api/settings/admin/salesmen` GET/POST.
- `/api/settings/admin/salesmen/delete` POST.
- `/api/settings/admin/report-log` GET.

### Notifications

- `/api/notifications`: returns report-ready and overdue-customer counts/items.
- `/api/notifications/dismiss`: dismiss by id, by type, or all.
- Base navigation polls periodically. Dashboard only bulk-dismisses overdue-customer alerts.

### Diagnostics

Admin-only diagnostics live under `/v2/diag`.

- `/diag`: environment, mirror, snapshot, and tool UI.
- `/diag/api/mirror/refresh`: force mirror refresh.
- `/diag/api/mirror/status`: mirror counts/status.
- `/diag/api/snapshot-status`: DB sync status.
- `/diag/api/snapshot-now`: force DB snapshot.
- `/diag/api/mirror/invoice-coverage`: invoice mirror coverage.
- `/diag/api/mirror/backfill`: start historical backfill.
- `/diag/api/mirror/backfill-status/<job_id>`: backfill progress.
- `/diag/api/probe/customer-history`: customer order-history probe.
- `/diag/api/mirror/salesline`: inspect salesline rows.
- `/diag/api/mirror/customer-match`: debug customer matching.
- `/diag/api/ping`: live Reporting API ping.
- `/diag/db/integrity`: SQLite integrity check.
- `/diag/db/repair`: attempted DB repair.
- `/diag/invoice/<invoice_no>`: invoice debug view.

### Health and Manifest

- `/v2/healthz`: unauthenticated health response with status/config hints.
- `/v2/manifest.json`: PWA manifest using Achim icons.

## 4. Backend Technical Explanation

### App Startup

`create_app()` builds Flask, sets session options, registers all blueprints, injects globals for templates, initializes SQLite via `init_db()`, initializes the mirror schema, bootstraps the hot DB from Azure persistent storage, starts the snapshot loop, starts APScheduler unless disabled, and starts background mirror refresh.

The app is mounted by root `wsgi.py` using `DispatcherMiddleware`, so v2 sees requests under `settings.URL_PREFIX` (`/v2` by default).

### Data Stores

App SQLite tables:

- `app_users`: users, role, email/display name, salesman link, active/external/test/dashboard/SharePoint flags.
- `user_preferences`: theme/landing/default tab and similar preferences.
- `user_exclusions`: per-user dashboard customer exclusions.
- `notifications`: report-ready and dashboard alerts.
- `saved_reports`: presets with params/layouts.
- `schedules`: personal report schedules.
- `master_schedules`: shared schedules.
- `schedule_runs`: run status, output, debug log.
- `report_run_log`: report usage telemetry.
- `outbox`: email delivery log.
- `feature_flags`: global feature toggles.
- `app_salesmen`: salesman identity, number, commission, active flag.
- `user_report_access`: explicit report allow/deny overrides.
- `user_salesman_access`: manager-to-salesman scope.
- `app_settings`: miscellaneous key/value app settings.
- `api_payload_cache`: rendered report cache.
- `api_async_jobs`: cache refresh job state.

Mirror SQLite tables:

- `mirror_customers`: local customer master snapshot.
- `mirror_salesline`: local order/salesline snapshot.
- `mirror_sales_header`: materialized order header view.
- `mirror_invoice`: local invoice snapshot.
- `mirror_refresh_runs`: refresh history.
- `mirror_dashboard_cache`: precomputed dashboard rows.
- `mirror_backfill_jobs`: historical backfill progress.

Azure DB durability model:

1. Hot SQLite DB lives on `/tmp/v2_app.db` for performance.
2. Durable copy lives on `/home/data/v2_app.db` when on Azure.
3. `db_sync.bootstrap_from_persistent()` copies/salvages persistent DB to hot DB at startup.
4. A background snapshot loop periodically copies hot DB to persistent storage.
5. Critical user/permission/schedule data is also backed up to JSON sidecar.

This model is elaborate because SQLite on Azure Files/SMB is fragile. It works as a mitigation, not as a clean long-term data architecture.

### Auth and Authorization

`auth.py` resolves the current user from the session and DB, exposes `require_login` and `require_admin`, and supports two auth modes:

- Dev mode: self-serve login with arbitrary email.
- MSAL mode: Microsoft Entra auth-code login, then local user upsert.

Admin status can come from `V2_ADMIN_EMAILS`, local v2 DB role, or a live DB compatibility lookup. Report access is handled by `report_access.py`, which resolves profile, report visibility, explicit overrides, and salesman/manager scoping. `scope_params_for_user()` injects salesman filters for non-privileged users before report execution.

Weakness: authorization is not applied uniformly across every route that reads customer/order data.

### Generic Report Pipeline

The core flow for normal reports is:

1. User opens `/report/<key>` and chooses filters.
2. `report_form.js` builds query params and previews the Reporting API body.
3. User opens `/report/<key>/view`.
4. `report_view.js` posts to `/api/reports/<key>/run` with params, cache mode, and wait time.
5. `report_api.py` checks report access, scopes params, logs the run, and calls `cache_first.get_or_refresh()`.
6. `cache_first.py` returns cached payload if possible and starts/monitors an async refresh job.
7. The refresh job calls `report_runner.run_report()`.
8. `report_runner.py` calls `reporting_api.preview()` and `reporting_api.run()` for the report.
9. `reporting_api.py` translates v2 params to Reporting API payload fields, posts to the on-prem API, handles timeouts/errors, and may fall back to mirror data.
10. A report builder normalizes rows and returns tab payloads.
11. `report_runner.py` applies role-specific tab suppression.
12. The viewer renders tabs and actions.
13. Export/email/schedule reuse the same payload plus layout instructions.

Payload shape:

- `tabs`: list of tabs.
- each tab: `key`, `name`, `columns`, `rows`, optional layout hints.
- column metadata: `field`, `label`, `type`.
- `data_source`: live/cache/mirror/error metadata.
- `generated_at`: timestamp.

### Reporting API Translation

`reporting_api.py` maps internal keys to external report IDs and converts v2 filter names to stored-procedure/API parameter names. It resolves period presets into start/end dates, handles ordered open-order behavior, translates invoiced/salesman/number_4/customer_activity parameters, caches lookup responses, and can use mirror fallback if the API is absent or fails.

### Report Builders

Ordered:

- Source: `salesline_release`.
- Normalizes customer, order, item, quantities, dollars, status, dates.
- Tabs: Summary, By Customer, By Item, By Order, By Salesman, Full Data.
- If a salesman filter is applied, the By Salesman tab is removed.

Invoiced:

- Source: `invoiced_order_charges`.
- Normalizes invoice/customer/salesman/item/amount/charge fields.
- Loads salesman map from app DB for names, numbers, commission percent.
- Detects credits and reversals.
- Builds customer summaries, invoice detail tabs, credit/audit views, totals by salesman, and commission-card data.
- For commission cards, the runner does an extra YTD fetch from Jan 1 through the selected period end so YTD values are correct.
- If the user is scoped to a salesman, commission/admin-style tabs are suppressed.

Salesman:

- Source: `invoiced_order_charges`.
- Runner requests current and prior year range.
- Builder normalizes invoice rows, assigns month/year, and produces one tab per month.
- Rows compare current vs prior periods and YTD values by customer/salesman.

Number 4:

- Source: `invoice_lines`.
- Runner requests rolling/current date context.
- Builder normalizes item/customer/month quantities and dollars.
- Tabs: By Item - 12 Months, By Item - YTD, By Customer - 12 Months, By Customer - YTD.

Customer Activity:

- Sources: customer master plus salesline history.
- Builder loads customer master from mirror/app services, joins last-order information, computes activity categories, and emits All/Salesman/Unassigned tabs.
- Dashboard uses related but separate precomputed cache logic in `dashboard_data.py`.

Customer Last Order:

- Custom route, not generic report viewer.
- Uses `customer_last_order.py` service to find customers, recent orders, selected/default order, and line details.
- Renders picker and detail templates.

Registered but not fully wired:

- `amazon_weekly`: registry/help exists but no v2 builder mapping.
- `customer_aging`: registry/help exists but no v2 builder mapping.

### Export, Email, SharePoint

`report_export.py` writes server-side `.xlsx` files from tab payloads and layouts, including header styles, type-aware formats, and special commission-card layout. `report_view.js` also contains client-side workbook construction logic for the interactive viewer export path.

`email_outbox.py` creates `.eml` files instead of sending real SMTP and logs to `outbox`. `report_api.email_now()` builds an Excel attachment, records delivery, and may save to SharePoint.

`sharepoint.py` uses Graph API configuration to browse folders and upload files. If not configured, the UI can still show fallback/mock folder behavior.

### Scheduling

Personal and master schedule routes validate payloads through `_schedule_common.py`. `schedule_runner.py` loads schedule params/layouts, runs the report, exports Excel, delivers email and/or SharePoint, records status and debug logs in `schedule_runs`, and catches errors so a run is always recorded.

`mirror_scheduler.py` uses APScheduler with a SQLAlchemy job store on SQLite. It has a scheduler-owner/single-instance guard to prevent every worker from scheduling refreshes. It triggers mirror refresh/catch-up jobs.

### Mirror and Dashboard Data Flow

`mirror_refresh.py` refreshes customers, saleslines, and invoices in chunks. It uses single-flight claims to avoid duplicate refreshes and supports historical backfill. `mirror.py` upserts rows, rebuilds `mirror_sales_header` and `mirror_dashboard_cache`, and provides fallback reads when the live API is unavailable.

Dashboard data flow:

1. Dashboard page renders a light shell.
2. `dashboard.js` calls `/api/dashboard/data`.
3. `dashboard_data.py` reads precomputed mirror/dashboard rows, applies role scoping and user exclusions, calculates summary counts, and returns rows.
4. A manual refresh starts mirror refresh in the background and the browser polls status.

## 5. Tests

`smoke_settings.py` is the main test file. It creates an isolated SQLite DB, disables the scheduler, enables dev auth, configures admin emails, starts the app test client, signs in as an admin, and exercises settings/admin flows:

- user CRUD.
- salesman CRUD.
- role assignment.
- report access overrides.
- salesman access mappings.
- cascading updates between salesmen and users.

The test is valuable because the users/permissions code is high-risk. Coverage is still narrow: there are no automated tests for report builders, cache-first jobs, mirror refresh, schedule delivery, SharePoint, MSAL, dashboard authorization, or diagnostics.

## 6. Brutal Breakdown

Critical risks:

- `V2_AUTH_MODE` defaults to `dev`. In any accidentally exposed environment, anyone can sign in as any email.
- `V2_FLASK_SECRET` can fall back to a known default. That makes session forgery possible if deployed without env.
- No CSRF protection on state-changing POSTs.
- Customer Last Order does not appear to enforce the same salesman/customer scope as dashboard/report paths.
- The Reporting API probe is available to logged-in users rather than admin-only.
- `test_access_enabled` is stored but not meaningfully used as a login gate.
- Health output leaks config hints.

Architecture risks:

- SQLite on Azure App Service is doing too much: app data, cache data, mirror data, scheduler state, backup/snapshot coordination, and corruption recovery.
- The `/tmp` hot DB plus `/home/data` snapshot plus JSON sidecar is operational scar tissue. It reduces outages but makes correctness hard to reason about.
- Migrations are ad hoc `CREATE TABLE` and `ALTER TABLE` logic, not versioned migrations.
- Multiple workers plus SQLite plus background threads create race conditions that are hard to reproduce.
- Several locks fail open. When lock acquisition errors, duplicate heavy work can happen.
- Long-running work still touches request paths. Cache-first softens the UX, but reports, exports, run-now schedules, and diagnostics can still be expensive synchronous operations.

Maintainability risks:

- God files: `db.py`, `mirror.py`, `reporting_api.py`, `dashboard_data.py`, `diag.py`, `report_view.js`, and `style.css` are all too large and mix concerns.
- Report business logic is duplicated from the live CLI/report tree. Commission math, credit rules, column layouts, and normalization will drift.
- Common report helpers are copied across builders.
- Front-end code has multiple generations: `app.js`, `_live_report_form.js`, modern `report_form.js`, large `report_view.js`, inline template scripts, and `settings.js`.
- CSS is global and huge, with repeated modal/table/card patterns.
- README is materially wrong.

Product/UX risks:

- The UI is powerful but not simple: hidden tabs, hidden columns, duplicate tabs, filters, sorting, grouping, schedules, SharePoint, presets, cache prompts, and background refresh can overwhelm users.
- Some admin screens expose too much in one page.
- Accessibility is weak: modal focus management, semantic buttons, scalable viewport, and keyboard paths need work.

## 7. Rebuild Recommendation

I would not rebuild this as a pure SPA first. The pain is not Jinja itself. The pain is state, persistence, jobs, security, and duplicated business logic. A React/Next rewrite before solving those would create a nicer front end over the same fragile core.

Recommended target architecture:

```text
Browser
  Jinja-rendered pages plus bundled JS modules
Flask
  thin blueprints, one authz layer, one job API
Services
  reporting_client: API translations and HTTP
  report_engine: shared pure builders used by web and CLI/runbook
  jobs: report runs, exports, schedules, mirror refreshes
  cache: one rendered-report cache
  mirror: regenerable D365 snapshot
Postgres
  users, permissions, preferences, presets, schedules, run history, notifications
Regenerable cache/mirror store
  mirror rows and report payload cache
```

Phase plan:

1. Security patch the current v2 code: force explicit auth mode/secret, gate probes, enforce `test_access_enabled`, add CSRF, fix Customer Last Order scoping.
2. Rewrite README to match reality.
3. Move precious data to managed Postgres. Keep mirror/cache data disposable.
4. Add versioned migrations.
5. Extract shared report engine and delete duplicated builder logic.
6. Introduce a worker/job queue for runs, exports, schedules, and refreshes.
7. Split `reporting_api.py`, `db.py`, `mirror.py`, `dashboard_data.py`, and `diag.py` by concern.
8. Add focused tests around builders, authorization scoping, schedules, cache jobs, and DB migrations.
9. Add a front-end build step and split `report_view.js` into modules.
10. Collapse CSS/modal/table patterns and remove dead static assets.

Positions I would defend:

- Move precious data off SQLite. The current DB sync code is clever, but it exists because the platform/database pairing is wrong.
- Keep the HTTP Reporting API boundary. It is the right integration boundary and avoids web-tier direct SQL coupling.
- Share one report engine between web and CLI/runbook paths. Two copies of commission/report math are a correctness bug waiting to happen.
- Do not start with a full front-end rewrite. Modular Jinja plus bundled JS is a lower-risk path unless the company is standardizing the whole app ecosystem on React/Next.
- Treat the mirror as a cache, not a source of truth. If it cannot be deleted and rebuilt safely, it is the wrong abstraction.

## 8. What Another Agent Should Do Next

If the next agent is implementing, give it one narrow phase at a time. The first practical prompt should be:

```text
In test/ only, patch the v2 security baseline without changing user-facing behavior:
require explicit non-default V2_AUTH_MODE/V2_FLASK_SECRET outside local dev,
make /api/reports/test-reporting-api admin-only,
enforce test_access_enabled at login,
add scope checks to Customer Last Order,
and add focused tests for those behaviors.
Do not touch the live webapp/ tree.
```

The second practical prompt should be:

```text
In test/ only, replace the stale README with a truthful v2 operating guide
based on test/docs/v2-full-audit-manual.md.
```

