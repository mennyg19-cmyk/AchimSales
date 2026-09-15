# Inventory: settings-dashboard-data (live v3)

Model: claude-fable-5-1-thinking-medium
Runner: spawn
Area: settings-dashboard-data
Role: inventory
CodeGraph: `codegraph status` → command not found; **graph via parent digest**.
Date: 2026-09-02

## Proof-of-read

- `AUDITOR-INSTRUCTIONS.md` (37 lines): scope = live `v3/` only, no rewrite proposals, no app edits; deliverable header + ≤10-line reply.
- `graph-backbone/INDEX.md` (30 lines): 4 area digests, 5 job-type constants, 4 roles (`_PRIVILEGED` = admin + developer), Beta shares Live `session` cookie, dashboard blueprint not registered on Beta.
- `graph-backbone/settings-dashboard-data.md` (75 lines): 10 settings routes, 7 dashboard routes, 2 health routes, 8 devtools routes, 17 repositories, precious migrations 0001–0018, 3 global flags + 2 per-user flags.
- Drilled with Read: `settings.py`, `dashboard.py`, `health.py`, `devtools.py`, `__init__.py` (factory/bootstrap), `config.py`, `beta_sources.py`, `connection.py`, `migrate.py`, all 18 precious + 5 cache SQL files, `jobs/worker.py`, `jobs/scheduler.py`, `dashboard/{jobs,metrics,mirror,notifications,service}.py`, repos `{app_settings,preferences,notifications,dashboard,exclusions,run_log,report_config,feature_flags,jobs}.py`, templates `{settings,dashboard,customer_detail,db_explorer,notif_diagnostic,run_log,schedule_runs,base}.html`, TS `{settings,dashboard,db_explorer,notif_diag,main}.ts`, root `wsgi.py` mount section, `authorization.py` (lines 40–120).

Digest corrections found while reading: repository count matches (17 modules + `__init__`). Digest says `/api/settings/preferences` = "theme + landing" — it also accepts `default_report_tab`. Digest omits `magic_link_tokens` and `outbox` tables in 0001, and omits the entire cache-DB migration set (5 files).

---

## 1. Settings hub (`/settings`, `settings.html`, `settings.ts`)

Accordion of `<details class="settings-cat">`; only one open at a time (JS `initAccordion`). Sections and gating:

| # | Section (summary) | Visible to | Cards / controls | Backend |
|---|---|---|---|---|
| S1 | **You › Profile** | everyone | Name, Email, Role (title-cased) from principal | render only |
| S2 | **You › Appearance** | everyone | `<form POST /settings/theme>` select: light / dark / monochrome / monochrome_dark + Save; flash "Theme set to X." | `set_theme` → `session["theme"]` + `PreferencesRepository.set(theme)`; redirect to settings |
| S3 | **You › Customer exclusions** | everyone | `SearchablePicker` (#exclPicker) + pills (#exclPills); hint text states: "Loading customers…" / "Search and check customers to hide them." / "Customer master still warming — retrying…" / "Customer master is not configured." / "Could not load customers." | `GET /api/settings/customers?salesman=` (scoped to `visible_salesman_keys`, via `LOOKUP_SERVICE.customers_visible`); `POST /api/settings/exclusions {customer_account, excluded}`; if customer list empty, polls `reports.lookup_status` every 2.5 s until `status=="ready"` or row counts > 0 |
| S4 | **People** | admin/developer (`is_privileged`) | button → `admin.users_page` ("Users & access") | link only (auth-admin area) |
| S5 | **Reports › Global report visibility** | privileged | one `.vis-toggle` per `registry.built_reports()` sorted by title; shows title + key; "Off hides the report from everyone unless that person has an explicit allow." | `POST /api/admin/report-visibility {report_key, enabled}` → `ReportConfigRepository.set`; 400 on unknown key; optimistic UI w/ rollback |
| S6 | **Reports › Feature flags** | privileged (only if `flags` non-empty) | one `.flag-toggle` per `FLAG_DEFAULTS` key; label = key with `_`→space, titled; description from DEFAULTS | `POST /api/admin/feature-flags {key, enabled}`; 400 "Unknown flag" if key ∉ DEFAULTS |
| S7 | **Delivery** (`#adminSettings`) | privileged | link "Company schedules" → `schedules.company_schedules_page`; **Schedule test mode** toggle `#scheduleTestToggle` ("Redirect company schedule mail", "Subject is tagged [TEST]"); email chips `#testEmailChips` (click chip = remove); add form `#testEmailAdd` (email input, dedup case-insensitive); message line `#testModeMsg` | `POST /api/admin/schedule-test {enabled?, emails?}` → `AppSettingsRepository.set_schedule_test`; server refuses enabling with zero emails (`ValueError` → 400 "Add at least one test email before turning test mode on."); clearing emails forces mode off; JS also pre-checks empty list |
| S8 | **History** | privileged | buttons "Report run log" → `/admin/run-log`; "Scheduled run history" → `/admin/schedule-runs` | see §2 |
| S9 | **Developer** | `is_developer` (DB row role = developer, active) | buttons "Database explorer" → `/dev/db-explorer`, "Notification diagnostic" → `/dev/notif-diagnostic`; **Beta report data sources** list `#betaSourcesList`: one `<select sql|odata>` per key in `beta_sources` (sorted); message `#betaSourcesMsg` shows "`key → source`" or error | `POST /api/dev/beta-sources {report_key, source}` → `web.beta_sources.set_source` (writes **Live webapp SQLite** table `beta_report_sources`, not v3 precious); `GET /api/dev/beta-sources` returns full map |

Copy that must survive (subtitle): "Your account" + ", access, delivery, and history" when admin. Delivery paragraph: "While on, company schedule mail (Run now and the clock) goes only to the addresses below. SharePoint is skipped. Salesman splits still run; each file comes here with the salesman in the subject. Personal schedules are unchanged. These addresses also get a mail if a home-site schedule fails after one automatic retry, even when this switch is off."

Data attributes on `#settingsHub`: `data-flag-url`, `data-test-url`, `data-vis-url`, `data-excl-url`, `data-customers-url`, `data-lookup-status-url`, `data-excluded` (JSON list), `data-beta-url`, `data-csrf`.

### Settings routes (10)

| Method | Path | Guard | Notes |
|---|---|---|---|
| GET | `/settings` | login | builds flags/reports/test-mode only when privileged; beta_sources only when developer (falls back to `default_sources()` on error, logs exception) |
| GET | `/admin/run-log` | privileged else 403 JSON | `RUN_LOG_REPO.recent(limit=200)` |
| GET | `/admin/schedule-runs` | privileged else 403 JSON | `ScheduleRunRepository.list_recent(200)`; labels from `schedules.report_key` (personal) / `master_schedules.name` (master); fallback "—"; summary = first 200 chars of `debug_log` or `output_meta.summary` (computed but **not rendered** in template) |
| POST | `/api/admin/feature-flags` | privileged | |
| POST | `/api/admin/report-visibility` | privileged | validates via `registry.get` |
| POST | `/api/admin/schedule-test` | privileged | `emails` must be list else 400 |
| POST | `/api/settings/exclusions` | login; 403 "Unknown user" if no DB row | `_can_exclude_account`: 400 "Unknown customer" if not in customer master; 403 "Not authorized for this customer" if outside salesman scope |
| GET | `/api/settings/customers` | login | optional `?salesman=` filter |
| GET/POST | `/api/dev/beta-sources` | developer else 403 | POST 400 on bad source/key |
| POST | `/settings/theme` | login | form post; unknown theme → "light" |
| POST | `/api/settings/preferences` | login; 403 "Unknown user" | JSON `theme`, `landing_page` (reports\|dashboard), `default_report_tab`; updates `session["theme"]` only if `theme` in body; used by header theme-cycle button (`main.ts initThemeToggle`, order light→dark→monochrome→monochrome_dark) |

Theme list `_THEMES` duplicated in `settings.py` and `preferences.THEMES` and `main.ts THEME_ORDER` (3 copies — keep in sync).

### Run-log page (`run_log.html`)

Back-link → Settings. Title "Report run log", subtitle "The N most recent report executions." Columns: When, User (email or —), Report (key), Status (`status-pill status-{status}`), Rows, Duration (`%d ms`), Source. Empty: "No report runs recorded yet." Source table `report_run_log` (user_id FK SET NULL, params_hash, status, rows, duration_ms, source, created_at); written by report-run job handler (reports area) via `ReportRunLogRepository.record`.

### Schedule-runs page (`schedule_runs.html`)

Title "Scheduled run history", subtitle "The N most recent company and personal schedule runs." Columns: When (started_at), Schedule (label), Kind (personal|master), Status pill, Rows. Empty: "No schedule runs recorded yet."

---

## 2. Feature flags & nav gating

`feature_flags.DEFAULTS` (single source of truth, seeded at boot by `_seed_feature_flags`, idempotent `ON CONFLICT DO NOTHING`):

| Key | Default | Description |
|---|---|---|
| `dashboard_enabled` | True | "Show the Dashboard tab" |
| `order_entry_enabled` | False | "Show the Order Entry tab" |
| `test_site_enabled` | False | "Show the link to the legacy test site" |

Per-user columns on `users`: `dashboard_enabled`, `test_access`, `sharepoint_access`, `is_external`, `can_see_company_views` (0016), `sales_group` (0017).

Context processor (`inject_globals`) resolves per request (skips `static` endpoint):
- `dashboard_enabled` = global flag AND (`row.dashboard_enabled` OR `p.is_privileged`) — **forced False when `is_beta`**.
- `order_entry_enabled` = global flag — **forced False on Beta**. (No order-entry blueprint exists in v3; flag is inert but stored/toggled.)
- `test_site_enabled` = global flag AND (`row.test_access` OR privileged) — not Beta-forced.
- `theme` from session, else `user_preferences.theme` (`_load_theme`), else "light".
- `nav.notifications` resolved with `_safe_url` → "#" on Beta (dashboard bp absent); `base.html` only sets `data-notifications-url` when not "#", so **no badge polling on Beta**.
- Also exposes `new_app_marker` (v3 pill hidden in prod), `app_env`, `is_beta` (Beta badge), `asset_v`.

`base.html` bottom nav: Reports (badge `#badgeReports`) · Dashboard `{% if not is_beta and (dashboard_enabled or role in admin/developer) %}` (badge `#badgeDashboard`) · Schedules · Test Site (`/test/`, target _blank, if `test_site_enabled`) · Settings. Header: user name or "Viewing as X" impersonation badge; role badge; "Recent Reports" button (`#prevRunsBtn`); theme cycle button; Switch-user icon when `_dev`; Sign Out form (CSRF).

`_refresh_session_role` before_request: syncs cached session role with DB row each request; logs out an impersonator whose real account is no longer an active developer; locked-out users get session role downgraded to salesman.

---

## 3. Dashboard (Live only — blueprint not registered when `cfg.is_beta`)

Access rule `_require_dashboard_user`: privileged OR (`row.is_active` AND `row.dashboard_enabled`) else 403 "Dashboard access required". Note: the **global `dashboard_enabled` flag is not checked by the routes**, only by the nav; a direct URL works with the flag off.

### Routes (7)

| Method | Path | Behaviour |
|---|---|---|
| GET | `/dashboard` | `DASHBOARD_SERVICE.view(allowed_keys, excluded)` → summary + rows; `last_refreshed` |
| POST | `/api/dashboard/refresh` | 503 "Dashboard refresh is turned off" if `dashboard_refresh_enabled` False; else `enqueue_refresh(JOB_REPO, owner_user_id)` → 202 `{job_id}` (deduped on key `dashboard.refresh`) |
| GET | `/api/dashboard/refresh-status` | `{last_refreshed, count}` — count is **scoped** to viewer (deliberate: no leaking global size) |
| POST | `/api/dashboard/exclusion` | `{customer_account, excluded}` → `ExclusionRepository.set`; 400 if account missing; **no customer-master/scope check** (unlike settings exclusion) |
| GET | `/api/notifications` | `{total, overdue_count, report_ready_count, items:[{id,type,...payload}]}`; zeros if no user row |
| POST | `/api/notifications/dismiss` | `{id}` or `{type}` or `{all:true}` → `{dismissed: n}` |
| GET | `/customer/<account>` | 404 "Customer not found" if not in mirror; 403 if `salesman_key(cust.sales_group)` ∉ allowed; orders from `REPORT_SERVICE.customer_orders(account)` (best-effort, empty list on exception), sorted by order_date desc |

### `dashboard.html` widgets

- Header `#dashRoot` (data: csrf, refresh-url, status-url, exclusion-url). Title "Customer Dashboard" + help `?` (`data-help="dashboard-cards"`). Subtitle "Last refreshed {ts}" / "Not refreshed yet". Button `#dashRefreshBtn` "Refresh data".
- **5 stat tiles** (`.dash-tile` buttons, `data-status` = "" | new | active | overdue | inactive): Total, New, Active, Overdue, Inactive. Click = filter table rows by `data-status` (`tile-active` class).
- **Table `#dashTable`**: Customer (link → `/customer/<acct>`; name or account; `<span class="mini-flag">excluded</span>` when excluded), Salesman (`sales_group` or —), Status pill, Last order (`iso_date`), Days since, Avg freq, Threshold. Excluded rows get `row-excluded` class **but remain listed** (tiles exclude them; table shows them).
- Empty state: feather `users`, "No customers yet. Tap **Refresh data** to build the dashboard from the latest orders."
- JS refresh: read `last_refreshed` before; POST refresh; poll status every 3 s up to 40 tries; reload when `last_refreshed` changes; else re-enable button. `window.triggerDashRefresh` is the hook for pull-to-refresh (`main.ts initPullToRefresh`, touch only, threshold 70 px, labels "Pull to refresh" / "Release to refresh" / "Refreshing…"); non-dashboard pages reload instead.

### `customer_detail.html`

- `#custRoot` (csrf, exclusion-url, account). Back-link "Dashboard". Title = name or account. Subtitle "Account {acct} · {sales_group or 'Unassigned'}".
- Metrics card: Status pill; Days since last (help `dashboard-tile-overdue`); Avg frequency (help `dashboard-avg-freq`); Threshold (help `dashboard-threshold`); Orders (`order_count`).
- Toggle `#custInclude` "Include in dashboard" (checked = not excluded; help `dashboard-include`); POST exclusion with `excluded: !checked`; rollback on failure.
- "Order history (N)" table: Date, Order #, PO #, Item, Description, Qty (`%g`), Status (`o.status or o.order_status`). Empty: feather `inbox`, "No orders on record for this customer."

Help keys referenced in `help_content.js` for this area: `dashboard-cards`, `dashboard-tile-total|new|active|overdue|inactive`, `dashboard-avg-freq`, `dashboard-threshold`, `dashboard-refresh`, `dashboard-include` (10). Templates use 5 of them.

### Dashboard data pipeline

- `MirrorService.rebuild()` (`dashboard/mirror.py`): `service.customer_universe()` + `service.all_orders()` from Reporting API → group order dates per account → `compute_metrics` → `DashboardRepository.replace_all` (DELETE + bulk insert into **cache.db `dashboard_customers`**).
- `compute_metrics` (`dashboard/metrics.py`, "ported verbatim from LIVE `_compute_customer_metrics`"): drop zero-day gaps; `avg_gap_days` = population mean; `gap_stdev` = population stdev; `overdue_threshold` = mean + stdev; rounding 1 dp; status precedence: `new` (<2 distinct days) → `inactive` (days_since > 365) → `overdue` (> threshold) → `active`. `INACTIVE_DAYS = 365`. **Business rule — must not drift.**
- `DashboardService.view`: scope filter by `salesman_key(sales_group)` (None = unrestricted); summary counts exclude excluded rows; rows keep them.
- Refresh job `dashboard.refresh` (`DASHBOARD_REFRESH_JOB_TYPE`, dedup key same string); handler = rebuild + `generate_overdue_notifications` (failure logged, does not fail refresh); result_ref `"customers=N overdue_notified=M"`.
- Cron: `dashboard-mirror` every 4 h at :05 (`hour="*/4", minute=5`, tz America/New_York) — only when `dashboard_refresh_enabled`; boot-prime enqueues a refresh if `DASHBOARD_REPO.count()==0`; when refresh disabled, `_cancel_pending_dashboard_refreshes` marks queued/running `dashboard.refresh` jobs `cancelled` at boot.
- Config `DASHBOARD_REFRESH_ENABLED` env (default True; **forced False on Beta**).
- `LOOKUP_SERVICE` (reports area) is fed `mirror_customers=dash_repo.all` — the dashboard mirror also backs the **customer filter dropdowns and Settings exclusion picker**. Deleting the dashboard mirror breaks those pickers.

### Notifications

- Table `notifications` (user_id CASCADE, type, payload_json, dismissed, created_at, read_at).
- Types: `overdue_customer` (generated) and `report_ready` (**constant defined, counted in API and badge `#badgeReports`, but no producer found in v3 — grep found no `create(..., REPORT_READY`**). Flag as dormant.
- `generate_overdue_notifications(db)`: for each active user — privileged sees all, else `get_salesman_access`; skip if no scope; skip excluded, 7-day dismissed cooldown (`COOLDOWN_DAYS=7`, uses `read_at`), already-undismissed same account; payload `{customer_account, customer_name}`.
- Badge polling (`main.ts initNotificationBadges`): every 30 s; `overdue_count` → Dashboard badge, `report_ready_count` → Reports badge; "99+" cap.
- No UI lists or dismisses notifications individually; only badges + API. (Digest silent on this.)

---

## 4. Health (`health.py`)

| Route | Returns |
|---|---|
| GET `/healthz` | `{"status":"ok"}` 200 — deliberately minimal (docstring: live `/healthz` leaked config; do not repeat) |
| GET `/manifest.json` | PWA manifest: name "Achim Sales Reports", short_name "Sales", description "Sales reports and customer dashboard", `start_url=url_for('reports.reports_list')`, `scope` derived from healthz URL prefix (mount-aware), standalone, `#ffffff` bg, `#2563eb` theme, portrait, icons 192/512 |

Both bypass the Beta live-login gate (`ep.startswith("health.")`). `base.html` links manifest + apple-touch-icon + `theme-color #2563eb` + iOS PWA metas.

---

## 5. Developer tools (`devtools.py`; guard `_require_developer` → 403 JSON)

### DB explorer

Page `/dev/db-explorer` (`db_explorer.html`, `db_explorer.ts`): back-link Settings; subtitle "Edits save immediately. There is no undo."; warning "Developer only. Table and column names are checked against the schema; arbitrary SQL is not accepted."; DB select `#dbxDb` — "precious (users, jobs, schedules)" / "cache (exports, dashboard mirror)"; search `#dbxSearch` (debounced 250 ms, re-queries current table); left table list `#dbxTables` (name + row count); grid `#dbxGrid`; message `#dbxMsg`.

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/dev/db/tables?db=precious\|cache` | tables (excluding `sqlite_%`) with `row_count` (None on error); 400 "db must be precious or cache" |
| GET | `/api/dev/db/table/<table>?db&page&per_page(≤200,default 50)&q&sort` | 404 "Unknown table"; `q` = LIKE across all columns cast to text; sort by validated column else PK; returns `columns` (name,type,notnull,default,pk), `primary_key` (single-column PK only, else null), rows, total, page, per_page |
| POST | `/api/dev/db/table/<table>/cell` `{db, column, pk, value}` | requires single-column PK + known column else 400; `_coerce` by declared type (INT→int, REAL/FLOAT/DOUBLE/NUMERIC→float, ""/None→NULL); 404 "Row not found" if rowcount≠1 |
| DELETE | `/api/dev/db/table/<table>/row` `{db, pk}` (db also via query) | 400 "Table has no single-column primary key"; 404 "Row not found" |

JS: every cell is an `<input class="dbx-cell">`, `change` saves immediately (only when PK exists); Delete button per row with `confirm("Delete this row?")`; Prev/Next pagination "Page X of Y". Errors: "Could not save cell." / "Could not delete row."

### Notification diagnostic

Page `/dev/notif-diagnostic` (`notif_diagnostic.html`, `notif_diag.ts`): subtitle "Why a user does or does not get overdue-customer alerts."; user `<select #ndUser>` over `UserRepository.list_all()` ("display_name or email (role)"); button `#ndRun` "Generate overdue now"; output `#ndOut`.

| Method | Path | Behaviour |
|---|---|---|
| GET | `/api/dev/notif-diagnostic/<path:email>` | 404 "User not found"; `diagnose_overdue` dry-run + `user{email,role,display_name,is_active,dashboard_enabled}` |
| POST | `/api/dev/notif-diagnostic/<path:email>/run` | runs `generate_overdue_notifications(db)` **for all users**, then diagnose; adds `generated` |

Rendered: user line (email · role · active yes/no · dashboard on/off); "Mirror refreshed {ts|never} · N customers in scope · M overdue"; "Would create (n)" list; "Would skip (n)" with reason ("excluded", "dismissed recently", "already notified"); "Excluded"; "Active alerts" count. Run message: "Generated N overdue alerts (all users)."

---

## 6. Data layer

### Connection (`connection.py`)

Fresh `sqlite3` connection per call; `timeout=30`, `busy_timeout=30000`, `journal_mode=WAL` with 20 retries on "locked" (50 ms × attempt), `foreign_keys=ON`, `Row` factory. `Database.precious()` / `.cache()` context managers commit on success, rollback on exception. `from_config(cfg)` → paths. Config refuses UNC and `/home/` (Azure Files SMB) paths in prod; `LITESTREAM_BLOB_URL` required in prod.

Paths: Live `PRECIOUS_DB_PATH`/`CACHE_DB_PATH` (default `./.data/precious.db`, `./.data/cache.db`); Beta `BETA_PRECIOUS_DB_PATH`/`BETA_CACHE_DB_PATH` (defaults `beta_precious.db`, `beta_cache.db`). **Each mount has its own precious + cache DB** — Live and Beta do not share users/flags/schedules.

### Migrations (`migrate.py`)

`schema_migrations(version, applied_at)`; each file wrapped `BEGIN IMMEDIATE … INSERT version … COMMIT` as one `executescript`; loser of a parallel-worker race skips if version now recorded; "duplicate column name" is tolerated and recorded. `migrate(db)` = precious files → `_ensure_users_company_views_column` → `_ensure_users_sales_group_column` (self-heal ALTERs) → `convert_personal_schedules(db)` (scheduling area) → `migrate_cache_only`. `migrate_cache_only` also called by report cache when cache.db vanishes mid-flight. `flask migrate` CLI command registered.

**Precious 0001–0018** (tables/columns to preserve):

| File | Effect |
|---|---|
| 0001 | `users`, `salesmen`, `user_salesman_access`, `user_report_access`, `user_preferences`, `user_exclusions`, `saved_reports`, `schedules`, `master_schedules`, `schedule_runs`, `report_run_log`, `notifications`, `outbox`, `feature_flags`, `app_settings`, `magic_link_tokens`, `jobs` (+ `idx_jobs_status`, partial unique `idx_jobs_dedup_active`) — **17 tables** |
| 0002 | `jobs.attempts` |
| 0003 | `jobs.kept_until`; `schedules/master_schedules.filename_template` |
| 0004 | `master_schedules.owner_user_id, is_shared, run_as_user_id` |
| 0005 | `app_settings` (idempotent re-create) |
| 0006 | `jobs.keep_name` |
| 0007 | `report_config(report_key, enabled)` |
| 0008 | dedupe shared master names; unique index `master_schedules_shared_name` |
| 0009 | `catch_up_pending` both schedule tables |
| 0010 | delete seeded 'Daily 9am' |
| 0011 | strip 'Direct Reports/' prefix; fix Customer Activity path |
| 0012 | `last_claimed_at` both |
| 0013 | `catch_up_for_date` both |
| 0014 | `report_defaults`; `view_name` both schedule tables |
| 0015 | `company_views` |
| 0016 | `users.can_see_company_views` (developers on) |
| 0017 | `users.sales_group` |
| 0018 | rebuild `user_salesman_access` without FK to `salesmen` |

**Cache 0001–0005**: `mirror_customers`, `mirror_salesline`, `mirror_sales_header`, `mirror_invoice`, `mirror_invoice_lines`, `mirror_dashboard_cache`, `mirror_refresh_runs`, `mirror_backfill_jobs`, `report_payload_cache` (0001); `dashboard_customers` + 2 indexes (0002); `report_exports` blobs (0003); purge ordered payloads (0004); `report_exports.export_type, owner_email` + 3 indexes (0005). The six `mirror_*` tables from 0001 appear unused by v3 code read here (only `dashboard_customers`, `report_payload_cache`, `report_exports` have repositories) — candidates for `delete:` in structure audit, but the explorer lists them.

### Repositories (17 modules)

`app_settings` (keys `schedule_test_mode`, `schedule_test_emails` JSON list, `seed_skip_schedule_names`), `company_views`, `dashboard`, `exclusions` (get / is_excluded / set / replace_all), `exports`, `feature_flags`, `jobs`, `notifications`, `outbox`, `preferences`, `report_config` (missing row = enabled; `seed_built`), `report_defaults`, `run_log`, `salesmen`, `saved_reports`, `schedules`, `users`. This area owns: app_settings, dashboard, exclusions, feature_flags, jobs, notifications, preferences, report_config, run_log.

### Beta sources (`beta_sources.py`) — cross-DB

Reads/writes **`webapp.db.get_db()`** (legacy Live SQLite), table `beta_report_sources(report_key PK, source CHECK sql|odata, updated_at)`, created lazily by `ensure_schema`. Keys (8): ordered, invoiced, salesman, number_4, customer_activity, customer_last_order, item_averages, customer_aging. Defaults SQL: ordered, invoiced, customer_activity, salesman; others odata. Unknown key → "sql". Falls back to defaults if Live DB unreadable. **Legacy dependency that survives go-live only if `webapp.db` stays importable.**

---

## 7. Jobs (`jobs/worker.py`, `jobs/scheduler.py`, `repositories/jobs.py`)

- `JobWorker(db, max_workers=2)`: `BoundedSemaphore` capacity; `register(type, handler)`; `process_next`/`drain` (sync, tests); `start(poll_interval=1.0)` → `recover_orphans()` then poller thread + `ThreadPoolExecutor`; heartbeat log every ~30 s; `health()` → `{started, poller_alive, max_workers, free_slots, handler_types}`; `stop()`.
- Registered handlers (5): `report.run`, `EXPORT_JOB_TYPE` (report.export), `report.deliver`, `schedule.run`, `dashboard.refresh`.
- `JobRepository`: `enqueue` with dedup on active (`queued|running`) + partial unique index race handling; `claim_next` (oldest queued → running); `set_progress`; `mark_success/mark_failure` guarded to `running` (never resurrect `cancelled`); `cancel` (queued or running); `recover_orphans(max_retries=1)` — jobs with `attempts >= 1` fail with the OOM message "Stopped after the run kept crashing its worker - it most likely ran out of memory. Try a smaller date range or fewer customers, or export instead of viewing on screen."; `status_summary`; `list_for_user`; `report_runs_for_user`; `keep_run` (cap 5 kept per user, name ≤ 80 chars).
- Job statuses: queued | running | success | failure | cancelled.
- Leader election `_is_background_leader`: exclusive `fcntl.flock` on `<precious dir>/.v3-background.lock`, handle held in `_BG_LOCK_FH`; fail-open leader on non-POSIX; `is_background_leader_process()` exposed for admin diagnostic (reports area `/api/…diagnostic`).
- Leader-only: `worker.start()`, cancel pending dashboard refreshes if disabled, `_start_scheduler`.
- `Scheduler` (APScheduler BackgroundScheduler, tz America/New_York, `coalesce=True`, `misfire_grace_time=300`, `max_instances=1`): jobs `schedule-tick` (every minute, `make_tick`) and `dashboard-mirror` (Live only, when enabled). Missing APScheduler → logged, schedules only via Run now.
- Boot order (`bootstrap_background`, run in daemon thread from root `wsgi.py` for `/test`, Beta `/`; never blocks import): migrate → seed flags → seed report_config → `_seed_users_from_live` (mirror Live `webapp` users) → `_seed_admins` (`V3_ADMIN_EMAILS`/`V2_ADMIN_EMAILS`) → `_seed_developers` (`V3_DEVELOPER_EMAILS`, sets `can_see_company_views=1`) → master schedules (`_LIVE_RUNBOOK_SCHEDULES` inactive on Beta; `_AZURE_SCHEDULES` on Live/test) → `_seed_company_views` → leader work. Every seed is individually try/except so boot never fails.

---

## 8. Beta vs Live differences in this area (from `__init__.py`, `config.py`, `wsgi.py`)

| Concern | Live `/test` (`is_beta=False`) | Beta home `/` (`is_beta=True`) |
|---|---|---|
| Dashboard blueprint | registered | **not registered** (nav tab hidden, `/dashboard` 404, notifications URL "#", no badge polling) |
| `dashboard_refresh_enabled` | env, default True | forced False (no cron, no prime, pending refreshes cancelled) |
| `dashboard_enabled` / `order_entry_enabled` context | computed | forced False |
| Session cookie | `v3_session`, secret `FLASK_SECRET` | `session`, secret `FLASK_SECRET_KEY` (shared with Live login) |
| Login gate | own auth | `_require_live_login` before_request: adopt Live identity or redirect to `/legacy/login`; health.* exempt |
| DB files | `precious.db`/`cache.db` | `beta_precious.db`/`beta_cache.db` |
| Master schedule seed | `_AZURE_SCHEDULES` active | `_LIVE_RUNBOOK_SCHEDULES` inactive |
| Settings page | full | full (Developer › Beta sources meaningful here; Customer exclusions still shown though dashboard hidden — exclusions still feed overdue logic which never runs on Beta) |

---

## 9. Must-not-lose checklist (counts)

- Settings sections: **9** (Profile, Appearance, Customer exclusions, People, Report visibility, Feature flags, Delivery/test mode, History, Developer).
- Settings routes: **11** endpoints (10 paths; beta-sources is GET+POST).
- Feature flags: **3 global** + **2 per-user** (`dashboard_enabled`, `test_access`) + `can_see_company_views`, `sharepoint_access`, `is_external` columns.
- App settings keys: **3** (`schedule_test_mode`, `schedule_test_emails`, `seed_skip_schedule_names`).
- Preferences: **3 fields** (theme ×4 values, landing_page ×2, default_report_tab).
- Exclusion write paths: **2** (settings picker — scope-checked; dashboard/customer detail — not scope-checked).
- Run-log pages: **2** (`/admin/run-log`, `/admin/schedule-runs`).
- Dashboard routes: **7**; tiles **5**; table columns **7**; customer-detail metrics **5** + include toggle + order table **7 cols**; help keys **10**.
- Notification types: **2** (`overdue_customer` live; `report_ready` counted but no producer).
- Health routes: **2**.
- Devtools routes: **8** (5 DB explorer incl. page, 3 notif diagnostic).
- Job types: **5**; job statuses **5**; cron jobs **2**.
- Precious migrations **18** (17 initial tables + `report_config`, `report_defaults`, `company_views` = 20 tables + `schema_migrations`); cache migrations **5** (12 tables).
- Repositories **17**.
- Env vars touched here: `DASHBOARD_REFRESH_ENABLED`, `PRECIOUS_DB_PATH`, `CACHE_DB_PATH`, `BETA_PRECIOUS_DB_PATH`, `BETA_CACHE_DB_PATH`, `LITESTREAM_BLOB_URL`, `V3_ADMIN_EMAILS`, `V2_ADMIN_EMAILS`, `V3_DEVELOPER_EMAILS`, `NEW_APP_MARKER`, `FLASK_SECRET`, `FLASK_SECRET_KEY`, `V3_MOUNT_ENABLED`, `BETA_MOUNT_ENABLED`.

## 10. Observations for the structure auditor (not fixes)

1. `report_ready` notification type has no producer; badge code path is dead in practice.
2. Dashboard routes ignore the global `dashboard_enabled` flag (nav-only gate).
3. `/api/dashboard/exclusion` skips the customer-master/scope validation that `/api/settings/exclusions` enforces.
4. Theme list is defined in 3 places.
5. `schedule_runs_page` computes `summary` that the template never renders.
6. Six `mirror_*` cache tables from cache 0001 have no repository consumers in the files read.
7. `beta_sources` writes to the legacy `webapp` SQLite; go-live retirement of `webapp/` must keep or migrate `beta_report_sources`.
8. `magic_link_tokens` table exists (0001) — no consumer seen in this area's files (auth area to confirm).

## CodeGraph queries I would have run

`codegraph callers NotificationRepository.create` (confirm no `report_ready` producer); `codegraph callers ExclusionRepository.get` (all exclusion readers); `codegraph impact compute_metrics`; `codegraph callers migrate_cache_only`; `codegraph callers is_background_leader_process`; `codegraph query mirror_customers` (dead cache tables); `codegraph callers PreferencesRepository.get` (is `landing_page` honoured anywhere?).
