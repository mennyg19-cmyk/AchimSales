# Rebuild Plan — Sales Reports (invoiced-first)

The single build blueprint for Phase 4. Every todo below is derived from the
locked architecture (DEBATE-LOG.md), the owner brief (REBUILD-BRIEF.md), the
feature inventory (FEATURE-INVENTORY.md P1–P20, route manifest, FA/FB/FC fixes),
and the 50 build-history bugs (BUILD-HISTORY.md BH1–BH50). The builder
executes these todos in order. Re-litigating architecture is out of scope —
the debate is done.

---

## §1 Locked Architecture (from DEBATE-LOG — binding)

- **Stack:** Flask + Jinja server-rendered templates + TypeScript (esbuild) +
  Tabulator. One Azure App Service B1, one container, one deploy.
- **Persistence:** Local-disk SQLite + Litestream. `precious.db` is durable
  (replicated to Azure Blob). `cache.db` is disposable (self-heals on missing
  schema). Boot hard-fails if DB path is `/home`, UNC, or SMB. Litestream must
  be packaged and verified. Only one instance allowed.
- **Postgres off-ramp:** Built into the repository layer NOW — Connection
  protocol (duck-typed), Python-UTC timestamps (never `datetime('now')`), JSON
  as TEXT at repository edges, isolated `claim_next()`, isolated
  `lock_for_migration()`, no SQLite-only SQL in services. Postgres is a
  documented swap, not a rewrite.
- **Reports:** One stored procedure per report → one flat table. All row-level
  math is in SQL. The app is presentation only: group, sort, show/hide, reorder,
  tabs (tabs = saved groupings of the same flat data). The app's only arithmetic
  is generic subtotals/grand-totals of dollar/quantity columns; rate/percent
  columns stay blank on total rows. SQL filters rows by a scope parameter the
  app passes in. Report config (columns, format, tabs, scope, filters) is
  DB-driven so a new report = new config, not new code.
- **Result / big-table:** ONE canonical flat snapshot per run + ONE server-side
  `ReportViewBuilder` that feeds screen, export, AND email/schedule (kills BH27
  divergence). Normal results stored in `cache.db`, returned active-tab-first
  with lazy per-tab loading. Results over a configured budget (row count +
  estimated bytes; numbers come from the memory-budget test) switch to
  lazy/server-paged and may spill the snapshot to Blob. Snapshot storage behind
  an abstraction so `cache.db` ↔ Blob is a config flip. Exports always stream
  from the server (openpyxl), never built in the browser.
- **Worker:** A SEPARATE entrypoint module (`worker_main.py` — no Flask import,
  clean lifecycle boundary). Production default: own process from the container
  startup script (same B1, one container, one deploy — NOT a second Azure
  resource). Concurrency env-driven (default 1). Worker heartbeat + last-claim +
  queue-depth surfaced in `/healthz`. In-process leader-thread fallback behind a
  feature flag for dev + first-deploy/emergency. Same worker code both modes;
  flock leader election guards single-runner.
- **Auth:** Microsoft/Entra company logins. Central authorization on every data
  route: resolve `(user, report, scope)` in one place. Refuse to boot in prod
  with `AUTH_MODE=dev` or a default `FLASK_SECRET`. CSRF on all state-changing
  requests.
- **Mount path (owner directive 2026-06-22):** The rebuild does NOT take the
  `/test` slot yet. The existing `/test` app stays live and untouched until the
  owner confirms the rebuild looks good. The mount path is env-driven
  (`APP_MOUNT_PATH`, default a temporary slot like `/test-next`), and the Entra
  redirect URI is derived from it (`{APP_MOUNT_PATH}/auth/callback`) — so the
  rebuild gets its OWN temporary redirect URI now, not the `/test` one. Taking
  over `/test` (and later `/`) is a one-line config flip + an Entra URI add after
  sign-off — never hardcoded.
- **Cross-cutting:** Audit log built-in. Responsive + accessible from day one.
  Live-blue pixel target (`--primary: #2563eb`), workable not pixel-perfect.
  4 themes via design tokens. Tests are the ship gate.

---

## §2 Module Layout

Shared packages (`data/`, `reports/`, `jobs/`, `delivery/`) are Flask-free so
`worker_main.py` can import them without pulling in the web framework. Only
`auth/`, `blueprints/`, `templates/`, and `app.py` touch Flask.

```
rebuild/
├── app.py                        # create_app(), CSRF init, fast return
├── config.py                     # Config (env-driven, fail-closed, no Flask)
├── wsgi.py                       # DispatcherMiddleware: APP_MOUNT_PATH mount + daemon bootstrap
├── worker_main.py                # Worker process entry (no Flask import)
├── startup.sh                    # Container: gunicorn + worker_main.py
│
├── auth/
│   ├── msal.py                   # Entra login flow
│   ├── session.py                # Session principal storage (unique cookie)
│   ├── principal.py              # Immutable Principal value object
│   ├── authorization.py          # Central authz (one place for every data route)
│   └── decorators.py             # @require_login, @require_privileged
│
├── blueprints/
│   ├── auth_routes.py            # Login/logout/callback/impersonate
│   ├── report_routes.py          # Report page + run/result/active APIs
│   ├── export_routes.py          # Export + download + list exports
│   ├── lookup_routes.py          # Salesmen/customers/years/status lookups
│   ├── preset_routes.py          # Saved views CRUD
│   ├── delivery_routes.py        # Email-now, schedules, SharePoint
│   ├── admin_routes.py           # User/salesman/access CRUD, feature flags
│   ├── settings_routes.py        # Theme/preferences
│   └── health_routes.py          # /healthz, diagnostics, admin repair
│
├── reports/
│   ├── engine.py                 # Generic grouping: filter + group + aggregate + sort
│   ├── view_builder.py           # ReportViewBuilder (screen / export / email)
│   ├── transforms/
│   │   ├── __init__.py           # TRANSFORMS registry (name → function)
│   │   └── commission_pivot.py   # Monthly commission pivot
│   ├── conditions.py             # CONDITIONS registry (name → predicate)
│   ├── adapter.py                # SP row → flat dict (rename/normalize ONLY)
│   ├── runner.py                 # Run report: SP → adapter → engine → cache
│   ├── export_writer.py          # Grouped data → Excel (streaming openpyxl)
│   ├── cache.py                  # Cache key + payload read/write on cache.db
│   ├── snapshot_store.py         # Abstraction: cache.db ↔ Blob (config flip)
│   ├── config_loader.py          # Load report config from precious.db
│   └── params.py                 # Filter → SP parameter mapping (config-driven)
│
├── jobs/
│   ├── worker.py                 # Worker loop (no Flask; used by worker_main.py)
│   ├── leader.py                 # flock leader election
│   ├── scheduler.py              # Schedule tick firing
│   └── types.py                  # Job type → handler registry
│
├── delivery/
│   ├── email.py                  # EmailService (SMTP/outbox)
│   ├── sharepoint.py             # SharePointService (Graph API)
│   ├── service.py                # DeliveryService (run_and_deliver + scope snapshot)
│   └── scheduling.py             # ScheduleRunner + cadence + tick
│
├── data/
│   ├── connection.py             # Database: precious()/cache(), Connection protocol
│   ├── migrate.py                # Versioned migrations, leader-gated
│   ├── migrations/
│   │   ├── precious/
│   │   │   └── 0001_initial.sql
│   │   └── cache/
│   │       └── 0001_initial.sql
│   └── repositories/
│       ├── jobs.py               # Enqueue, claim_next, dedup, capped recovery
│       ├── users.py              # User CRUD + directory mirror
│       ├── report_configs.py     # report_configs, tabs, columns, filters
│       ├── salesmen.py           # Salesman master
│       ├── exports.py            # Export files + retention
│       ├── schedules.py          # Schedules + runs + outbox
│       ├── run_log.py            # Audit/incident log
│       ├── preferences.py        # User preferences (theme, etc.)
│       ├── presets.py            # Saved views
│       └── feature_flags.py     # Feature flags
│
├── static_src/
│   ├── ts/
│   │   ├── shell.ts              # Header, nav, theme, guards, pull-to-refresh
│   │   ├── jobs-fab.ts           # Floating jobs FAB + panel, shared poll module
│   │   ├── report/
│   │   │   ├── index.ts          # Report page controller (orchestrates modules)
│   │   │   ├── filters.ts        # Filter controls, deep links, lookups
│   │   │   ├── table.ts          # Tabulator wrapper, formats, view state
│   │   │   ├── tabs.ts           # Tab bar, context menu, duplicate/delete
│   │   │   ├── column-filter.ts  # Per-column filter popover
│   │   │   ├── toolbar.ts        # Toolbar buttons, columns panel, reset
│   │   │   ├── export.ts         # Export trigger + recent exports panel
│   │   │   ├── run.ts            # Run/poll/resume/cancel state machine
│   │   │   └── types.ts          # Strict interfaces (ViewState, TabConfig, etc.)
│   │   ├── modals/
│   │   │   ├── email.ts          # Email modal controller
│   │   │   ├── schedule.ts       # Schedule modal controller
│   │   │   └── sharepoint-picker.ts  # Reusable SP folder browser
│   │   └── admin.ts              # Admin users + salesman management
│   ├── css/
│   │   ├── tokens.css            # Design tokens (4 themes, live-blue primary)
│   │   ├── shell.css             # Shell layout (header, bottom nav, FAB, safe-area)
│   │   ├── report.css            # Report viewer + Tabulator via CSS variables
│   │   ├── modals.css            # All modals (email, schedule, help)
│   │   └── admin.css             # Admin pages
│   └── esbuild.config.js        # Entry points: shell, report/index, admin
│
├── templates/
│   ├── base.html                 # Shell template
│   ├── login.html
│   ├── reports_list.html
│   ├── report_view.html          # Filters + toolbar + tabs + table + modals
│   ├── settings.html
│   ├── admin_users.html
│   └── impersonate.html
│
└── tests/
    ├── test_parity.py
    ├── test_authz.py
    ├── test_jobs.py
    ├── test_grouping_engine.py
    ├── test_export_parity.py
    ├── test_migrations.py
    ├── test_boot_safety.py
    ├── test_cache_healing.py
    ├── test_csrf.py
    ├── test_restore.py
    └── test_memory_budget.py
```

---

## §3 Phase Map

12 phases, dependency-ordered. Each phase lists what it delivers and how to
prove it works before moving on.

| # | Phase | Delivers | Smoke test / ship gate |
|---|---|---|---|
| 1 | **Foundation** | Config, database, migrations, boot safety, Litestream, WSGI mount, health endpoint | App starts on local disk; health endpoint responds; migrations run clean; boot refuses `/home`/UNC/default secret |
| 2 | **Auth** | Entra login, session, Principal, central authz, decorators, user directory mirror | Entra login works; dev login only in dev mode; unauthorized user gets 403; unique session cookie verified |
| 3 | **Data Repositories** | All repository modules + precious/cache schemas | Every repo does CRUD; precious and cache schemas applied; audit log written |
| 4 | **Jobs / Worker** | Separate worker process, leader election, fallback, timeout, recovery, backpressure | Enqueue → claim → complete lifecycle; leader election; orphan recovery capped at 1; backpressure returns 503 |
| 5 | **Report Engine + Invoiced Config** | Generic grouping engine, commission pivot, adapter, runner, API client, invoiced config seed | Flat SP fixture → 7 correct tabs via generic engine; commission pivot matches expected output; invoiced config seeded in DB |
| 6 | **Result / View Builder** | ReportViewBuilder, snapshot storage, lazy tab loading, large result handling | Same snapshot → identical screen JSON + export feed + email feed; large fixture triggers server-paged path |
| 7 | **Frontend Shell** | Design tokens, shell template, shell JS, jobs FAB, reports home, esbuild, responsive | Authenticated user sees header/nav/theme/FAB; reports home shows cards; responsive at 375px and 1440px |
| 8 | **Invoiced Viewer** | Report viewer page, filters, run/poll/resume, tabs, Tabulator, toolbar, presets, lookups | Run invoiced → see 7 tabs → sort/filter/reorder/hide/freeze → deep links work → presets save and restore |
| 9 | **Export** | Export job, streaming writer, layout application, download, recent exports | Export matches on-screen layout; large export streams without OOM; recent exports panel lists and auto-downloads |
| 10 | **Email / Schedule / Delivery** | Email modal, schedule modal, SharePoint picker, delivery service, schedule runner | Email-now delivers attachment; schedule fires on cadence; SharePoint save works; delivery uses owner scope |
| 11 | **Admin / Settings / Impersonate** | Settings, admin users, access grids, salesman edit, feature flags, impersonate | Admin CRUD works; salesman scope limits data; impersonate works for admin, can't nest |
| 12 | **Polish / Ship** | Parity scaffold, security tests, memory budget, restore test, a11y, dark mode, deploy | All test suites green; LIVE parity verified for signed-off items; deploy to the temporary slot (`/test-next`) works with live `/test` untouched; a11y basics pass |

---

## §4 Granular Todos

### Phase 1 — Foundation

Covers: P17 (partial), P20 (partial).

---

**T1.01 — Config module with fail-closed validation**
Files: `rebuild/config.py`
Accept: `Config` dataclass loads from env vars. Includes `APP_MOUNT_PATH`
(default `/test-next`) which drives both the dispatcher mount and the derived
Entra redirect URI — so the rebuild lives on a temporary slot and the `/test`
takeover is a config change, never hardcoded. `validate()` refuses to start in
prod if `FLASK_SECRET` is default/missing, `AUTH_MODE=dev`, `PRECIOUS_DB_PATH`
or `CACHE_DB_PATH` resolves under `/home` or any UNC/SMB mount, or Litestream
is not packaged. Returns fast (no heavy work).
Covers: P20, BH5 (fast boot), BH7 (path validation), BH9 (dashboard refresh
flag off by default).

---

**T1.02 — Database connection module with Connection protocol**
Files: `rebuild/data/connection.py`
Accept: `Database` class exposes `precious()` and `cache()` context managers
returning a Connection-protocol object (duck-typed: `execute`, `fetchone`,
`fetchall`, `commit`). WAL mode set on open — no journal-mode knob. Busy
timeout with bounded retry. No `sqlite3.Connection` type exposed to callers.
All timestamp writes use `datetime.now(timezone.utc).isoformat()` from Python,
never `datetime('now')` in SQL.
Covers: P17, BH1 (local-disk only), BH2 (no journal knob), FC6 (Connection
protocol + Python UTC + JSON-at-edge).

---

**T1.03 — Migration runner (leader-gated, skip-if-applied)**
Files: `rebuild/data/migrate.py`, `rebuild/data/migrations/precious/`,
`rebuild/data/migrations/cache/`
Accept: `apply_migrations()` uses `BEGIN IMMEDIATE` behind a
`lock_for_migration()` method. Checks version table, skips already-applied.
Bounded retry on WAL open. Single bootstrap owner (leader gate OR migration
lock — prevents the race where two processes apply simultaneously).
Covers: P17, BH4 (migration race), FC6 (lock_for_migration abstractable).

---

**T1.04 — Boot safety validation**
Files: `rebuild/config.py` (validate method), `rebuild/app.py`
Accept: Production boot hard-fails with a clear message if: (a) DB path is
`/home` or UNC, (b) `AUTH_MODE=dev`, (c) `FLASK_SECRET` is default/missing,
(d) Litestream binary not found, (e) more than one instance detected (basic
check). Each failure gives a plain-English message naming the bad setting.
Covers: P20, BH7 (path validation), BH5 (fail-closed).

---

**T1.05 — Litestream packaging and restore path**
Files: `rebuild/startup.sh` (download/verify Litestream binary),
`rebuild/config.py` (Litestream config from env)
Accept: Startup script downloads Litestream if not present, verifies checksum.
Cold boot from empty disk restores `precious.db` from Blob before the app
starts. One-time seed path from legacy location is guarded by a marker file.
Covers: P17, BH8 (empty-disk restore), FC8 (Litestream binary in deploy).

---

**T1.06 — WSGI entry + dispatcher mount**
Files: `rebuild/wsgi.py`, `rebuild/app.py`
Accept: `create_app()` returns fast. Heavy init (migrations, seed, worker start)
runs in a daemon thread after the dispatcher mounts. DispatcherMiddleware mounts
the rebuild at `APP_MOUNT_PATH` (env-driven, default the temporary slot
`/test-next` — NOT `/test`). The existing `/test` app stays mounted and
untouched; nothing is moved to `/test-legacy` yet (that happens at cutover,
T12.08). `SCRIPT_NAME` is set from `APP_MOUNT_PATH` so the same code works at any
mount. Warmup probe hits a cheap route (`{APP_MOUNT_PATH}/healthz`).
Covers: P20, BH5 (fast boot + daemon thread), FC10 (dispatcher mount +
SCRIPT_NAME).

---

**T1.07 — Health and diagnostics endpoints**
Files: `rebuild/blueprints/health_routes.py`
Accept: `GET /healthz` returns JSON with: app status, worker heartbeat
timestamp, last job claimed, queue depth, Litestream status, Reporting API
reachability (short-timeout probe). Admin-only `POST` endpoints for: integrity
check (PRAGMA integrity_check), safe backup, jobs-table rebuild. Never stack
long-running probes on prod traffic. Developer-only `claim-once` and
`precious-repair` (BH19) built in, not emergency patches.
Covers: P20, BH3 (integrity check), BH16 (worker visibility), BH18 (diag
visibility), BH19 (admin repair), BH50 (admin-only probe with short timeout).

---

**T1.08 — Postgres off-ramp seams (verification)**
Files: `rebuild/data/connection.py`, all future repositories
Accept: No `datetime('now')` in any SQL string — grep-verified. No JSON1-only
functions (`json_extract`) in any service-layer SQL. `claim_next()` is an
isolated method in `JobRepository`. `lock_for_migration()` is an isolated
method in `migrate.py`. A doc comment in `connection.py` lists the 5 seam
points for a Postgres swap.
Covers: P17, FC6 (all 5 seam requirements from C-platform.structure.md).

---

**T1.09 — Cache database self-heal**
Files: `rebuild/data/connection.py` (cache open path)
Accept: If `cache.db` is missing or schema is gone, the cache open path
re-creates the file and re-runs cache migrations before use. Missing schema
is recoverable, not fatal. Test: delete `cache.db` mid-flight → next cache
read self-heals without 500.
Covers: P17, BH6 (no-such-table after cache.db deleted).

---

**T1.10 — Container startup script (web + worker)**
Files: `rebuild/startup.sh`
Accept: Script starts: (1) Litestream restore if needed, (2) Litestream
replicate in background, (3) gunicorn for the web process, (4) `worker_main.py`
as a separate process. One container, one deploy, one B1. If
`WORKER_MODE=in_process` is set, skip the separate worker (fallback for dev /
first-deploy).
Covers: P16 (partial), P20, OP3 consensus (separate process, in-process
fallback).

---

### Phase 2 — Auth

Covers: P2, P15.

---

**T2.01 — MSAL/Entra login flow module**
Files: `rebuild/auth/msal.py`
Accept: `build_login_url()` and `complete_login()` handle the full Entra OAuth
flow. Redirect URI is derived from the mount path (`{APP_MOUNT_PATH}/auth/callback`),
so the rebuild uses its OWN temporary redirect URI now (e.g.
`/test-next/auth/callback`) — not the live `/test` one. Safe `next` parameter
(validated against allowed hosts — no open redirect). Works under any mount via
`SCRIPT_NAME`. Deploy prerequisite: register the temporary callback URL in the
Entra app registration.
Covers: P2, BH21 (auth flow in session).

---

**T2.02 — Session management with unique cookie**
Files: `rebuild/auth/session.py`
Accept: `SESSION_COOKIE_NAME` is unique per mounted app (not Flask default
`session`). Cookie is HttpOnly, SameSite=Lax, Secure in prod. Session stores
the Principal. No collision with the live app on the same host.
Covers: P2, BH21 (session cookie collision).

---

**T2.03 — Principal value object (immutable, full round-trip)**
Files: `rebuild/auth/principal.py`
Accept: Principal is an immutable value object. Carries: user_id, email, name,
role, salesman_keys (scope), active flag, and impersonation fields
(`impersonating_user_id`, `impersonating_name`). Full serialization round-trip
tested (serialize → deserialize → equal). No fields dropped.
Covers: P15, BH32 (impersonation fields round-trip).

---

**T2.04 — Central authorization service**
Files: `rebuild/auth/authorization.py`
Accept: Single module with: `assert_report_runnable(principal, report_key)`,
`can_view_report(principal, report_key)`, `visible_salesman_keys(principal)`,
`authorize_delivery(principal, report_key, scope)`. Fail-closed: inactive or
unknown users get 403. Every result/export/email/schedule fetch re-checks authz
against current `(user, report, scope)` — no stale cache. Scope-compatibility
check on result read (if user's scope narrowed since the run, 403 not stale
data).
Covers: P15, BH28 (revoked user can't read cached result), BH29 (single
assert_report_runnable), BH48 (delivery re-checks scope).

---

**T2.05 — Auth decorators**
Files: `rebuild/auth/decorators.py`
Accept: `@require_login` checks session for valid Principal, redirects to
`/login` if missing. `@require_privileged` requires admin or developer role.
Both use central authz, not ad-hoc checks. Applied to every route that touches
data.
Covers: P15.

---

**T2.06 — Login page and routes**
Files: `rebuild/blueprints/auth_routes.py`, `rebuild/templates/login.html`
Accept: `GET /login` shows Entra login button (centered card). Clicking
redirects to Microsoft. Successful callback creates session with Principal.
Page works under any configured `APP_MOUNT_PATH` mount via `SCRIPT_NAME`.
Covers: P2 (A2.1–A2.5, C1.1–C1.3).

---

**T2.07 — Dev login form (AUTH_MODE=dev only)**
Files: `rebuild/blueprints/auth_routes.py`, `rebuild/templates/login.html`
Accept: `GET /login/dev` shows a form to pick a test user — ONLY when
`AUTH_MODE=dev` in config. Route does not exist in prod. Boot validation
(T1.04) prevents `AUTH_MODE=dev` in prod.
Covers: P2, BH5 (no dev auth in prod).

---

**T2.08 — User directory mirror**
Files: `rebuild/data/repositories/users.py`, `rebuild/auth/session.py`
Accept: On boot, the app mirrors the authoritative user directory (read-only)
into `precious.db`. Env-listed admins override. Role resolved at login and
re-checked on sensitive routes. Real users don't land as no-access on first
login.
Covers: P2, BH22 (mirror user directory).

---

**T2.09 — Auth callback, logout, safe redirect**
Files: `rebuild/blueprints/auth_routes.py`
Accept: `GET /auth/callback` completes MSAL flow, creates session, redirects
to saved `next` (validated). Logout clears session. `next` parameter rejects
external URLs. CSRF exempt on callback only (it's the OAuth return).
Covers: P2, FC7 (CSRF exempt audit — callback is the only exempt POST besides
healthz).

---

### Phase 3 — Data Repositories

Covers: P17 (partial), P19.

---

**T3.01 — Precious DB schema (initial migration)**
Files: `rebuild/data/migrations/precious/0001_initial.sql`
Accept: Tables for: users, salesman_master, jobs (with attempts column for
BH10), schedules, schedule_runs, report_configs, report_filters,
report_columns, report_tabs, user_preferences, user_report_access, presets,
feature_flags, audit_run_log, outbox. All timestamps are TEXT (ISO-8601 UTC).
No `datetime('now')` in defaults — Python writes the value. Foreign keys with
`ON DELETE CASCADE` where appropriate.
Covers: P17, BH4 (attempts column), FC6 (Python-UTC everywhere).

---

**T3.02 — Cache DB schema (initial migration)**
Files: `rebuild/data/migrations/cache/0001_initial.sql`
Accept: Tables for: report_snapshots (flat result JSON, keyed by cache key),
export_files (binary or path + metadata), export_metadata (retention). Self-heal
on missing schema (T1.09).
Covers: P17, BH6.

---

**T3.03 — Job repository**
Files: `rebuild/data/repositories/jobs.py`
Accept: `enqueue()` with dedup (same cache key → reuse existing queued job) and
backpressure (queue-depth cap → 503/Retry-After). `claim_next()` isolated for
Postgres swap (update-then-select pattern for SQLite; documented `FOR UPDATE
SKIP LOCKED` alternative). `recover_orphans()` capped at 1 retry per job
(plain-English message on second failure). `update_heartbeat()`. `cancel()`.
Partial unique index for dedup.
Covers: P16, BH10 (capped recovery), FC2 (backpressure), FC6 (abstract
claim_next).

---

**T3.04 — User repository**
Files: `rebuild/data/repositories/users.py`
Accept: CRUD for users. Stores role, flags (active, dashboard, sharepoint, test,
external), salesman scope keys, report access overrides. Directory mirror import
(bulk upsert from external source). Re-checks on sensitive routes via
authorization service.
Covers: P12, BH22 (directory mirror).

---

**T3.05 — Salesman repository**
Files: `rebuild/data/repositories/salesmen.py`
Accept: CRUD for salesman master. Admin edit. Read-only display data (name,
number, group, commission rate). Commission rate comes from SQL Server (SP);
this table is the admin sync / display copy.
Covers: P12, BH40 (single source is SQL; Azure master for admin UI only).

---

**T3.06 — Report config repository**
Files: `rebuild/data/repositories/report_configs.py`
Accept: CRUD for `report_configs`, `report_filters`, `report_columns`,
`report_tabs`. Read by `config_loader.py` at report-run time. Write by seed
script (T5.10) and future admin editor. Status field: active / disabled /
backlog.
Covers: P14, P20, FB5 (DB-driven registry).

---

**T3.07 — Preferences repository**
Files: `rebuild/data/repositories/preferences.py`
Accept: Read/write user preferences (theme selection, etc.). Keyed by user_id.
Covers: P11.

---

**T3.08 — Presets / saved views repository**
Files: `rebuild/data/repositories/presets.py`
Accept: CRUD for saved views (presets). Stores: report_key, user_id, name,
layout JSON (tab_order, per-tab hidden/frozen/order/sorters/filters/group/
widths, params). Deep-linkable via preset ID.
Covers: P8.

---

**T3.09 — Exports repository**
Files: `rebuild/data/repositories/exports.py`
Accept: Store export metadata + file (path or blob reference). Retention policy
(auto-delete old exports). Scoped to user — re-check authz on download.
Covers: P7.

---

**T3.10 — Schedules and outbox repository**
Files: `rebuild/data/repositories/schedules.py`
Accept: CRUD for schedules (cadence, recipients, SharePoint target, params,
owner principal snapshot). Schedule runs table. Outbox table for email/SharePoint
staging. Master schedules support (admin-created, run with owner scope).
Covers: P10, P18, BH48 (owner scope snapshot stored).

---

**T3.11 — Run log / audit repository**
Files: `rebuild/data/repositories/run_log.py`
Accept: Write incident-proof records for every report run, export, delivery,
and scheduled run. Fields: timestamp, user, report_key, job_id, action type,
duration, status, error message. Written by job handlers, not route handlers
(the job is the source of truth for what actually happened).
Covers: P19, BH16 (incident proof), BH50 (audit trail).

---

**T3.12 — Feature flags repository**
Files: `rebuild/data/repositories/feature_flags.py`
Accept: Read/write feature flags. `DASHBOARD_REFRESH_ENABLED` (default off per
BH9). `WORKER_MODE` (in_process vs separate). Admin-only toggle.
Covers: P20, BH9 (dashboard refresh behind flag).

---

### Phase 4 — Jobs / Worker

Covers: P16.

---

**T4.01 — Worker module (separate entrypoint, no Flask)**
Files: `rebuild/jobs/worker.py`, `rebuild/worker_main.py`
Accept: `worker_main.py` imports `jobs.worker` and `data.connection` — never
Flask. Starts a worker loop that polls the job table, claims jobs, runs
handlers, and updates status. Concurrency controlled by `JOB_WORKER_THREADS`
env var (default 1 for B1). Uses `ThreadPoolExecutor` with bounded semaphore.
Covers: P16, FC1 (env-driven threads), OP3 consensus (separate entrypoint, no
Flask import).

---

**T4.02 — Leader election (flock)**
Files: `rebuild/jobs/leader.py`
Accept: File-lock-based leader election. Only one process runs the scheduler,
email drain, and job poller. Test: two processes → only one becomes leader.
Covers: P16, BH17 (single leader).

---

**T4.03 — In-process leader-thread fallback**
Files: `rebuild/jobs/leader.py`, `rebuild/app.py`
Accept: Feature flag `WORKER_MODE=in_process` starts the worker loop as a
daemon thread inside the web process (for dev and first-deploy/emergency). Logs
a loud warning. Same worker code as the separate process — no fork. flock still
guards single-runner even in this mode.
Covers: P16, FC5 (leader fallback logged), OP3 consensus (in-process fallback
behind flag).

---

**T4.04 — Per-job timeout and watchdog**
Files: `rebuild/jobs/worker.py`
Accept: `MAX_JOB_DURATION_SECONDS` env var (default reasonable for B1). Worker
uses `Future.result(timeout=...)` — a job that exceeds the limit is marked
failed with a plain-English message. Cooperative cancel: the runner polls a
cancel flag between chunks (for chunked SP fetches). UI says "Stop queued" vs
"Stop running" honestly (BH12).
Covers: P16, FC4 (per-job timeout), BH12 (cooperative cancel), BH18 (stuck
job visibility).

---

**T4.05 — Capped orphan recovery**
Files: `rebuild/jobs/worker.py`, `rebuild/data/repositories/jobs.py`
Accept: On startup, recover orphaned jobs (status = `running` but no heartbeat).
Cap at 1 retry per job. Second failure → mark failed with plain-English message
"job failed twice, not retrying." Memory budget respected (no infinite OOM
loop).
Covers: P16, BH10 (capped recovery).

---

**T4.06 — Queue backpressure**
Files: `rebuild/data/repositories/jobs.py`, `rebuild/blueprints/report_routes.py`
Accept: `enqueue()` checks queue depth. If over the configured cap, returns a
signal that the route translates to 503 + `Retry-After` header. No unbounded
queue pile-up.
Covers: P16, FC2 (queue backpressure).

---

**T4.07 — Worker heartbeat**
Files: `rebuild/jobs/worker.py`, `rebuild/data/repositories/jobs.py`
Accept: Running jobs update a heartbeat timestamp periodically. `/healthz`
(T1.07) reports: last heartbeat, last claimed job, current queue depth. A
missing heartbeat past threshold means "worker alive but stuck" (BH18).
Covers: P16, BH16 (worker heartbeat visible), BH18 (stuck-job detection).

---

**T4.08 — Job type → handler registry**
Files: `rebuild/jobs/types.py`
Accept: Map of job type strings to handler functions: `report.run`,
`report.export`, `delivery.email_now`, `schedule.run`, `schedule.tick`,
`maintenance.cache_cleanup`. Adding a job type = registering a handler, not
changing the worker loop.
Covers: P16.

---

**T4.09 — Container startup orchestration**
Files: `rebuild/startup.sh`
Accept: Startup script launches gunicorn and `worker_main.py` as sibling
processes in one container. If either dies, the container exits (Azure restarts
it). Env var `WORKER_MODE=in_process` skips the separate worker (T4.03 takes
over). Health check confirms both processes are running.
Covers: P16, P20, OP3 consensus (one container, one deploy, one B1).

---

### Phase 5 — Report Engine + Invoiced Config

Covers: P14, P20 (partial).

---

**T5.01 — Report config loader**
Files: `rebuild/reports/config_loader.py`
Accept: `load(report_key)` reads `report_configs`, `report_filters`,
`report_columns`, `report_tabs` from `precious.db` and returns a typed config
object. Config-driven orchestration — no hardcoded per-report logic (kills
FB3). Deferred reports have `status='disabled'` and are not loadable for
running.
Covers: P14, FB3 (config-driven orchestration), FB5 (DB-backed registry),
FB8 (deferred reports behind status gate).

---

**T5.02 — SP adapter (rename/normalize only)**
Files: `rebuild/reports/adapter.py`
Accept: Takes raw SP rows, renames/normalizes column names to the canonical
set. Does NOT compute totals, detect credits, filter customers, or do any
math. If the SP contract changes (field renames), the adapter is the only
place to update. Versioned manifest per report SP (documented in config).
Contract tests on sample JSON fixtures.
Covers: P14, FB4 (adapter = rename/normalize only), BH44 (versioned manifest,
no legacy aliases).

---

**T5.03 — Generic grouping engine**
Files: `rebuild/reports/engine.py`
Accept: `compute_tabs(flat_rows, tab_configs)` takes flat SP rows + tab config
from DB and produces per-tab row sets. For each tab: (1) filter rows
(`filter_expr`), (2) group rows (`group_by`), (3) aggregate (SUM money
columns, COUNT DISTINCT when configured), (4) apply column set (ordered column
list per tab), (5) sort. Subtotals: SUM dollar/quantity columns; rate/percent
columns blank on total rows (A7.10). NO custom per-report math — this is
fully generic. Test with invoiced fixture: 7 correct tabs out.
Covers: P14, FB2 (manifest-driven tabs), BH27 (one grouped dataset), BH34
(generic SUM), BH42 (count_distinct:InvoiceNumber).

---

**T5.04 — Commission monthly pivot transform**
Files: `rebuild/reports/transforms/commission_pivot.py`,
`rebuild/reports/transforms/__init__.py`
Accept: Registered as `TRANSFORMS["commission_monthly_pivot"]`. Takes flat
rows + year + end_month → per-salesman, per-month slots with commission
dollars and base. Uses precomputed `CommissionAmount` and `CommissionBase`
from SQL — no rate lookup, no net formula, just accumulation. YTD = sum of
unrounded values; display rounding only in the formatter. Explicit year
parameter filters commission date window.
Covers: P14, BH35 (rounding: sum then format), BH36 (explicit year param),
BH38 (single SP call with YTD window), BH45 (commissions = tab definition
over flat table), BH46 (commission window from period end).

---

**T5.05 — Conditions registry**
Files: `rebuild/reports/conditions.py`
Accept: Registered condition functions that decide whether a conditional tab
appears. `has_multiple_salesmen`: True when >1 distinct salesman in the flat
data. `has_reversals`: True when reversal-audit rows exist. Tab included only
when its condition returns True.
Covers: P14 (conditional tabs: Audit-Reversals, Totals by Salesman).

---

**T5.06 — Params mapper (filter → SP parameter)**
Files: `rebuild/reports/params.py`
Accept: `translate(config, user_params)` reads `report_filters` config from DB
and maps user-facing filter values to SP parameters. Multi-customer selection →
table-valued parameter or `IN` clause (no silent post-filter in Python — BH37).
Commission date window derived from selected period end (BH46). Blank/invalid
custom dates → user-visible validation error, not 500 (BH43). Documents
defaults for each filter.
Covers: P14, BH37 (multi-customer pushed to SQL), BH43 (date validation),
BH46 (commission window from period end).

---

**T5.07 — Report runner (orchestration)**
Files: `rebuild/reports/runner.py`
Accept: `run_report(report_key, sp_params, identity, scope_token)`:
(1) call SP via API client, (2) adapter.normalize rows, (3)
engine.compute_tabs, (4) cache.store. One SP call per run (BH38 — no double
YTD fetch). Generic for any report — the only report-specific bits are the
registered transform and condition functions looked up from tab config.
Covers: P14, FB3 (generic orchestration), BH38 (single SP call).

---

**T5.08 — Reporting API client**
Files: `rebuild/reports/api_client.py` (or similar)
Accept: Calls on-prem Reporting API stored-procedure endpoint. Accepts SP name
+ params from config. Timeout configured. For any remaining multi-month pulls:
month-chunk fetch + stitch with parity test (BH11). Logs API call duration
(BH18). One SP returning only needed rows is the target (invoiced uses one
flat SP).
Covers: P14, BH11 (month-chunk for large pulls), BH18 (log API duration).

---

**T5.09 — Result cache module**
Files: `rebuild/reports/cache.py`
Accept: `store(cache_key, snapshot)` writes to `cache.db`. `read(cache_key)`
retrieves. Cache key = `report_key + identity + scope_token + params`. Cache
entries include scope token so authz re-check can verify compatibility (BH28).
Self-healing on missing schema (delegates to T1.09).
Covers: P14, BH28 (scope token in cache key), BH6 (self-heal).

---

**T5.10 — Invoiced report config seed**
Files: `rebuild/reports/seeds/invoiced.py` (or inline in migration/bootstrap),
`rebuild/data/repositories/report_configs.py`
Accept: Seeds `report_configs`, `report_filters`, `report_columns`,
`report_tabs` for the invoiced report at boot/migration time. 7 tabs: Summary
by Customer, Commissions, Full Details, Credits, Invoices, Audit-Reversals
(conditional), Totals by Salesman (conditional). 69 columns matching the LIVE
export format. Columns include: InvoiceNumber, InvoiceDate, CustomerAccount,
CustomerName, SalesOrderNumber, Salesman (SalesGroup), SalesmanName,
SalesmanNumber, SubTotal Invoices, Tariff Charges, Freight Charges, CC Charges,
Misc Charges, Total Invoice, IsCredit, CommissionPct, CommissionBase,
CommissionAmount, InvoiceMonth. All math from SQL — IsCredit is a SQL column
(BH33), CommissionBase/Amount are SQL-computed (BH34/BH40), SalesmanName from
SQL join (BH41), Misc Charges included (BH39). Commission tab uses
`transform = "commission_monthly_pivot"`, `layout = "commission_cards"`.
Summary tab uses `aggregations: {"InvoiceCount": "count_distinct:InvoiceNumber"}`
(BH42). Known intentional drifts seeded as-is and flagged in sign-off gates
(§7). Deferred reports seeded as `status='disabled'`.
Covers: P14, P20, FB1 (all math in SP), FB2 (manifest-driven), FB5 (DB-seeded),
BH33 (IsCredit from SQL), BH34 (precomputed net), BH39 (Misc Charges included),
BH40 (commission rate from SQL), BH41 (SalesmanNumber/Name from SP), BH42
(count_distinct), BH44 (adapter minimal — versioned manifest), BH45
(commissions = tab definition).

**HUMAN SIGN-OFF REQUIRED:** See §7 — commission/credit/misc math items must
be verified against LIVE before this todo is marked final.

---

### Phase 6 — Result / View Builder

---

**T6.01 — ReportViewBuilder**
Files: `rebuild/reports/view_builder.py`
Accept: ONE module that produces output for screen, export, AND email/schedule
from the same flat snapshot. Accepts: snapshot + tab configs + optional layout
overrides (column visibility, order, duplicated tabs). Returns: per-tab row
sets + column metadata. Screen, export, and email consumers call the same
builder — they CANNOT disagree on data. The export path adds cosmetic
formatting (column widths as points); the email path produces the same
attachment structure.
Covers: BH27 (one dataset feeds all consumers), FB6 (flat snapshot + view
configs, not per-tab payloads).

---

**T6.02 — Snapshot storage abstraction (cache.db ↔ Blob)**
Files: `rebuild/reports/snapshot_store.py`
Accept: Interface with `store(key, data)` and `read(key)`. Default
implementation uses `cache.db`. Blob implementation uses Azure Blob (already in
the stack for Litestream + exports). Config flip switches between them. Large
snapshots (over the configured budget) auto-spill to Blob.
Covers: OP2 consensus (cache.db ↔ Blob is a config flip).

---

**T6.03 — Active-tab-first response with lazy per-tab loading**
Files: `rebuild/reports/view_builder.py`, `rebuild/blueprints/report_routes.py`
Accept: Result endpoint returns the active tab's data immediately. Other tabs
return metadata (column list, row count) but not rows. Client fetches per-tab
data on tab switch. Reduces initial payload for multi-tab results.
Covers: OP2 consensus (active-tab-first + lazy per-tab load).

---

**T6.04 — Large result / server-paged fallback**
Files: `rebuild/reports/view_builder.py`
Accept: Results over a configured budget (row count + estimated serialized
bytes — exact numbers from T12.03 memory-budget test, not guesses) switch to
server-paged responses. Client requests pages; server sorts/filters over the
stored snapshot. Exports still stream the full dataset (streaming openpyxl).
Covers: OP2 consensus (lazy/server-paged for large results), FC9 (memory
limits).

---

**T6.05 — Memory budget enforcement**
Files: `rebuild/reports/runner.py`, `rebuild/jobs/worker.py`
Accept: Before storing a result, the runner checks estimated size against
the configured budget. Over-budget results trigger the Blob spill path (T6.02)
and the server-paged response path (T6.04). The worker enforces `resource`
module limits (Linux) as a hard ceiling. SP filtering (scope + date range)
is the primary row-count control — the budget is a safety net, not the normal
path.
Covers: FC9 (memory limits), BH10 (OOM prevention).

---

### Phase 7 — Frontend Shell

Covers: P1, P3.

---

**T7.01 — Design tokens CSS (4 themes)**
Files: `rebuild/static_src/css/tokens.css`
Accept: CSS custom properties for: light, dark, monochrome, monochrome-dark.
`--primary: #2563eb` (live-blue). All colors, spacing, radii, shadows defined
as tokens — no raw color values elsewhere. Tabulator themed via CSS variables
(not `!important` overrides).
Covers: P1, BH24 (dark-mode chrome via tokens), FA7 (CSS tokens).

---

**T7.02 — Shell CSS**
Files: `rebuild/static_src/css/shell.css`
Accept: Header (sticky top), bottom nav (fixed), floating FAB position,
safe-area insets, container widths, button/alert/overlay base styles. Responsive
breakpoints. Bottom nav respects `safe-area-inset-bottom`. No raw color values —
only tokens.
Covers: P1, BH23 (responsive shell), FA7 (CSS split by concern).

---

**T7.03 — Shell template (base.html)**
Files: `rebuild/templates/base.html`
Accept: Header strip: logo "Sales Reports" → link to `/`, user name + role
badge, theme toggle, sign out. Bottom nav: Reports (active on `/` and
`/reports/*`), Schedules (stub), Settings. Block for page content. Asset
`<link>` and `<script>` tags use `?v={{ asset_version }}` (content hash).
Unique `SESSION_COOKIE_NAME` set (BH21). `[hidden]` attribute is reliable — no
CSS display rules that override it (BH13).
Covers: P1 (A1.1–A1.26), BH21 (unique cookie), BH13 (hidden attribute),
BH31 (asset versioning), FC3.

---

**T7.04 — esbuild config + build manifest**
Files: `rebuild/static_src/esbuild.config.js`
Accept: Entry points: `shell.ts` (all authenticated pages), `report/index.ts`
(report viewer), `admin.ts` (admin page). Output to `static_dist/` with
content-hashed filenames. Build manifest file maps entry points to output
filenames so templates can reference them. CSS entry points bundled alongside.
Covers: P1, FC3 (content-based asset version), FA7 (CSS split).

---

**T7.05 — Shell TypeScript (header, nav, theme, guards)**
Files: `rebuild/static_src/ts/shell.ts`
Accept: Theme toggle cycles 4 themes, persists to user preference. Double-click
guard (`.page-loading-overlay`). Navigation guard (prevents double-submit).
Pull-to-refresh (`.ptr-indicator`). All state module-scoped, not global let
variables (FA6).
Covers: P1 (A16.1–A16.10), FA6 (no global state).

---

**T7.06 — Floating jobs FAB + panel (shared poll module)**
Files: `rebuild/static_src/ts/jobs-fab.ts`
Accept: Polls `GET /api/reports/active` on a 5-second interval. Hidden when no
active or recently finished jobs. States: running (spinner), failed (error
color), ready (success color). Click opens jobs panel; job rows link to their
report page. Shared poll module — the report page status bar and the FAB use
the SAME poll, not two parallel polls (BH15). Persists `job_id` in
sessionStorage for resume on navigation.
Covers: P1, BH15 (shared poll module + resume), FA2 (panel in template, not
imperatively created).

---

**T7.07 — Help overlay**
Files: `rebuild/static_src/ts/shell.ts`, `rebuild/templates/base.html`
Accept: Help button in header opens an overlay with contextual help. Defined in
template, toggled by shell.ts — not created in JS (FA2).
Covers: P1 (A1.18–A1.20).

---

**T7.08 — Notification badges + endpoint**
Files: `rebuild/static_src/ts/shell.ts`, `rebuild/blueprints/report_routes.py`
Accept: `GET /api/notifications` returns active-job counts (for the badge on
the Reports nav item). Shell.ts updates badge on poll. Scope: active-job
notifications only (report runs in progress or recently completed).
Covers: P1 (A1.7–A1.10).

---

**T7.09 — Asset cache-busting (content hash)**
Files: `rebuild/app.py`, `rebuild/templates/base.html`
Accept: At boot, compute content hash of `static_dist/` directory. All
`<link>` and `<script>` tags include `?v=<hash>`. Deploy with changed assets →
users get new files. Deploy with unchanged assets → cache hit.
Covers: P1, BH31 (asset cache busting), FC3 (content-based, not time-based).

---

**T7.10 — Responsive shell (mobile, safe-area, viewport-fit)**
Files: `rebuild/static_src/css/shell.css`, `rebuild/static_src/css/report.css`
Accept: Below 600px: filter row wraps, Run button goes full-width. Table uses
natural horizontal scroll — page never grows horizontally. Bottom nav respects
safe-area inset. Table height = viewport bottom - table top - bottom nav height,
minimum 220px. Tested at 375px (mobile) and 1440px (desktop).
Covers: P1, BH23 (viewport-fit), A16.2–A16.4.

---

**T7.11 — Reports home page**
Files: `rebuild/blueprints/report_routes.py`, `rebuild/templates/reports_list.html`
Accept: `GET /` shows: built report cards (invoiced — clickable), preset cards
(deep-link to saved view), coming-soon cards for deferred reports (disabled,
labeled). Empty state when user has no report access. Cards link to
`/reports/<key>` or `/reports/<key>?preset=<id>`.
Covers: P3 (A3.1–A3.5).

---

**T7.12 — Saved-reports API for reports home**
Files: `rebuild/blueprints/preset_routes.py`
Accept: `GET /api/saved-reports` returns the user's presets across all reports,
used by the reports home page to show preset cards.
Covers: P3.

---

### Phase 8 — Invoiced Viewer

Covers: P4, P5, P6, P8.

---

**T8.01 — Report viewer page template**
Files: `rebuild/templates/report_view.html`
Accept: `GET /reports/<key>` renders the report viewer. Template defines all
zones: header strip (back link, title, help), filter drawer (collapsible),
toolbar (single row), status bar (hidden when idle), tab bar, table area
(viewport-fit), bottom nav. All panels and modals defined in template HTML —
toggled by JS, not created by JS (FA2). No imperative DOM creation.
Covers: P4 (A4.1–A4.7), FA2 (template-defined panels/modals).

---

**T8.02 — Report viewer TypeScript controller**
Files: `rebuild/static_src/ts/report/index.ts`
Accept: Orchestrates the report page modules. Calls: filters.init →
table.init → tabs.init → toolbar.init → run.init. Passes typed config and
state between modules. No logic of its own — just wiring. Module-scoped state
objects, not global let variables (FA6).
Covers: P4, FA1 (god file split: controller), FA6 (encapsulated state).

---

**T8.03 — Filters module + deep links + init pipeline**
Files: `rebuild/static_src/ts/report/filters.ts`
Accept: Collapsible filters panel with summary when collapsed. Controls:
period (select), custom dates (date inputs, shown only when period=custom),
status/year (when configured), salesman (select), customer (multi-select with
search + pills). All controls are manifest-driven via config from the server
(FB3). Deep links: URL params set filter values. Init pipeline ORDER: (1)
warm lookups, (2) apply URL params, (3) bind controls. Deep-linked
`?period=custom&start_date=...` shows date inputs correctly (BH25). Preset
auto-run: if `?preset=<id>`, load preset params and run.
Covers: P4 (A4.1–A4.7, A5.1–A5.17), BH25 (init pipeline order), BH30
(lookups return exact SP values), BH43 (blank/invalid dates → validation),
FA1 (filters module).

---

**T8.04 — Run / poll / resume / cancel state machine**
Files: `rebuild/static_src/ts/report/run.ts`
Accept: "Run Report" → `POST /api/reports/<key>/run` → poll
`GET /api/jobs/<id>` every 1 second. Status bar shows: progress, true elapsed
time (from server, not local timer — BH15). Transient errors (network blip) →
retry with backoff, keep job_id. Terminal errors (404, explicit failed/cancelled)
→ stop poll, show error. Resume: on page load, check
`GET /api/reports/active` — if a job is running for this report, reattach to it
with true elapsed (BH15). Cancel button: says "Cancel queued" for queued jobs,
"Stop running" for in-flight jobs (BH12). Hidden reliably via `[hidden]`
attribute when not applicable (BH13). `sessionStorage` persists `job_id` for
cross-navigation resume.
Covers: P5 (A6.1–A6.12, B1.2.1–B1.2.5), BH12 (honest cancel), BH13 (hidden
attribute), BH14 (transient vs terminal), BH15 (resume + true elapsed), FA1
(run module).

---

**T8.05 — Tabulator grid adapter**
Files: `rebuild/static_src/ts/report/table.ts`
Accept: Wraps Tabulator behind a typed adapter. Builds table with: column
definitions from tab config, `fitDataTable` layout, movable + resizable
columns, money/int/percent/date formatters, subtotal calc rows (SUM money
columns, blank on rate/percent — A7.10). View state capture: hidden columns,
frozen columns, order, widths, sorters, filters, group-by. Tab switch: use
`setData()` + `setColumns()` when data shape allows; full rebuild only when
layout type changes (table ↔ cards) — avoids full teardown per switch (FA4).
Viewport-fit height from day one (BH23).
Covers: P6 (A7.1–A7.21, A8.1–A8.12, B3.1–B3.9), BH23 (viewport-fit), BH24
(themed via tokens), FA1 (table module), FA4 (minimize teardown), FA5 (typed
via community definitions or custom interfaces).

---

**T8.06 — Tab bar + context menu (duplicate/delete)**
Files: `rebuild/static_src/ts/report/tabs.ts`
Accept: Tab bar shows tabs from the result (7 for invoiced). Active tab
highlighted. Right-click → context menu (Duplicate, Delete) — single `<menu>`
element in template, positioned at click. Duplicate creates a copy of the tab
with independent view state. Delete removes user-created duplicates (can't
delete original tabs). Tab switch triggers table data swap via adapter (T8.05).
Tab meta line below tabs: row count + generated-at timestamp.
Covers: P6 (A7.13–A7.21), FA1 (tabs module), FA2 (context menu in template).

---

**T8.07 — Column formats + subtotals**
Files: `rebuild/static_src/ts/report/table.ts`
Accept: Money columns formatted with `$` + commas + 2 decimals. Integer columns
formatted with commas. Percent columns formatted as `X.XX%`. Date columns
formatted as configured (ISO → display). Subtotal rows: SUM for money/int
columns, BLANK for rate/percent columns (A7.10). Grand total row at bottom
when configured.
Covers: P6 (B3.1–B3.9).

---

**T8.08 — Commission cards layout**
Files: `rebuild/static_src/ts/report/table.ts`,
`rebuild/static_src/css/report.css`
Accept: When a tab has `layout = "commission_cards"`, render per-salesman cards
with monthly slots instead of a flat table. Cards show: salesman name, per-month
commission dollars + base, YTD totals. Commission rate displayed on detail rows,
blank on total rows. Same data as the flat table — just a different visual
layout.
Covers: P6, P14, BH45 (commissions = tab definition, same engine).

---

**T8.09 — Column filter popover (Excel-style)**
Files: `rebuild/static_src/ts/report/column-filter.ts`
Accept: Click funnel icon on column header → filter popover (positioned at
header, one shared `<div>` element in template — not created per column).
Operator options based on column type (text: contains/equals; number:
equals/gt/lt/range; date: range). Value input. Apply/clear. Popover content
swapped on open. Tabulator applies the filter to the current tab's data.
Covers: P6 (A8.1–A8.12), FA1 (column-filter module), FA2 (template element).

---

**T8.10 — Toolbar buttons**
Files: `rebuild/static_src/ts/report/toolbar.ts`
Accept: Single toolbar row with buttons: Refresh (re-runs with same params),
Columns (opens panel), Reset View (restores default column order/visibility/
widths), Export (triggers export job), Email (opens modal), Schedule (opens
modal), Save View (saves current layout as preset), Presets (opens panel),
Recent Exports (opens panel), API Preview (dev-only). Each button is a
`<button>` in template; toolbar.ts binds click handlers.
Covers: P8 (A9.1–A9.6, A9.19–A9.30), FA2 (template buttons, not imperative).

---

**T8.11 — Columns show/hide panel**
Files: `rebuild/static_src/ts/report/toolbar.ts`
Accept: Side panel (`<aside>` in template) listing all columns with checkboxes.
Toggle column visibility. Shared `PanelController` class: toggle on button
click, close on outside click, close on Escape, only one panel open at a time.
Covers: P8 (A9.1–A9.3), FA2 (template panel).

---

**T8.12 — Presets panel (saved views) + CRUD**
Files: `rebuild/static_src/ts/report/toolbar.ts`,
`rebuild/blueprints/preset_routes.py`
Accept: Side panel listing user's presets for this report. Open → apply preset
(restores layout + params). Delete → removes preset. Save View button →
`POST /api/reports/<key>/presets` with current layout JSON. Routes:
`GET /api/reports/<key>/presets`, `POST /api/reports/<key>/presets`,
`GET /api/reports/presets/<id>`, `DELETE /api/reports/presets/<id>`.
Deep-linkable: `/reports/invoiced?preset=<id>`.
Covers: P8 (A9.19–A9.30), presets routes from manifest.

---

**T8.13 — Lookups endpoints**
Files: `rebuild/blueprints/lookup_routes.py`
Accept: `GET /api/reports/<key>/salesmen` — salesman list for filter dropdown.
`GET /api/reports/<key>/customers` — customer list for multi-select.
`GET /api/reports/<key>/years` — available years. `GET /api/reports/lookups/status`
— warm-up status of lookup caches. All return exact SP parameter values (not
normalized keys — BH30). Display names separate from SP values. Async cache
warm-up.
Covers: P4, BH30 (exact SP values), BH25 (lookups warm-up polling).

---

**T8.14 — Run / status / result / active API routes**
Files: `rebuild/blueprints/report_routes.py`
Accept: `POST /api/reports/<key>/run` → authz check → enqueue → 202 {job_id}.
`GET /api/jobs/<id>` → job status + progress + elapsed. `POST /api/jobs/<id>/cancel`
→ cancel (queued: immediate; running: cooperative flag). `GET /api/reports/result/<id>`
→ re-check authz + scope compatibility (BH28) → return cached result (active-tab-first
per T6.03). `GET /api/reports/active` → list of user's in-flight/recently-completed jobs.
All routes use central authz (T2.04). CSRF on POST routes.
Covers: P5, BH28 (re-check authz on result read), BH29 (single
assert_report_runnable), run/status/result/active routes from manifest.

---

**T8.15 — API preview (dev-only)**
Files: `rebuild/blueprints/report_routes.py`
Accept: `POST /api/reports/<key>/preview-body` returns the SP parameters that
would be sent for the given filter values, without running the report.
Developer-only (behind `@require_privileged` or dev role check). Useful for
debugging SP calls.
Covers: P8 (B1.6.1), diagnostics routes from manifest.

---

### Phase 9 — Export

Covers: P7.

---

**T9.01 — Export job handler**
Files: `rebuild/jobs/types.py` (register handler),
`rebuild/reports/runner.py` (or `export_handler.py`)
Accept: `report.export` job type. Handler: (1) re-check authz + scope (BH28),
(2) read cached grouped result (same data the screen showed), (3) apply layout
overrides from job params, (4) write Excel via T9.02, (5) store export in
exports table. Background job — never blocks a request handler (BH26).
Covers: P7, BH26 (background export), BH28 (re-check authz on export).

---

**T9.02 — Streaming Excel writer (openpyxl)**
Files: `rebuild/reports/export_writer.py`
Accept: Takes grouped data from ReportViewBuilder (T6.01) + layout overrides
→ Excel workbook. Uses openpyxl `WriteOnlyWorksheet` for streaming (never
builds the whole workbook in memory). One worksheet per tab. Column widths in
points (not pixels). Money/percent/date formatting applied via cell styles.
Duplicated tabs included as extra worksheets.
Covers: P7, BH26 (streaming writer), BH27 (export uses same data as screen).

---

**T9.03 — Layout application (view state → workbook)**
Files: `rebuild/reports/view_builder.py` (called by export handler)
Accept: Client sends view state with export request: `{tab_order,
duplicated_tabs, per_tab: {hidden, order, sorters, filters}}`. ReportViewBuilder
applies these to the cached grouped result, producing per-tab row sets matching
what the screen showed. Export writer receives this output. Export is GUARANTEED
to match the screen because both use the same builder (BH27).
Covers: P7, BH27 (export == screen layout).

---

**T9.04 — Export + download endpoints**
Files: `rebuild/blueprints/export_routes.py`
Accept: `POST /api/reports/<key>/export/<job_id>` → re-check authz → enqueue
export job → 202 {export_id}. `GET /api/reports/exports/<id>/download` →
re-check authz + scope (BH28) → stream file. Error mapping: 404 (export not
found), 409 (export in progress), 413 (export too large — shouldn't happen
with streaming, but safety).
Covers: P7 (A9.7–A9.18, B1.3.1–B1.3.3), export routes from manifest.

---

**T9.05 — Recent exports panel + list endpoint**
Files: `rebuild/static_src/ts/report/export.ts`,
`rebuild/blueprints/export_routes.py`
Accept: `GET /api/reports/exports` → list of user's recent exports with status
(in-progress, ready, failed). Side panel in report viewer template shows the
list, polls for status updates. Ready exports show download link.
Covers: P7 (A9.7–A9.18), exports list route from manifest.

---

**T9.06 — Auto-download guard**
Files: `rebuild/static_src/ts/report/export.ts`
Accept: When an export completes, trigger browser download automatically. Guard:
only auto-download if the user initiated it from the current page session (not
on page reload or navigation back). Use a session-scoped flag.
Covers: P7 (A9.18 — auto-download).

---

### Phase 10 — Email / Schedule / Delivery

Covers: P9, P10, P18.

---

**T10.01 — Email service (SMTP / outbox)**
Files: `rebuild/delivery/email.py`
Accept: `EmailService` sends email via SMTP (configured from env). Outbox
pattern: delivery job writes to outbox table, drain loop sends. Handles
recipient splitting. Logs delivery attempts in audit log.
Covers: P18.

---

**T10.02 — SharePoint service (Graph API, boot-validated)**
Files: `rebuild/delivery/sharepoint.py`
Accept: `SharePointService` saves files to SharePoint via Graph API.
Configuration validated at boot — site lookup errors surface the setting name +
Graph status (not "file not found" — BH47). Shared service for all SharePoint
paths (no duplicate site constants). Config keys documented.
Covers: P18, BH47 (config validated, errors surface setting + Graph status).

---

**T10.03 — SharePoint picker component (reusable)**
Files: `rebuild/static_src/ts/modals/sharepoint-picker.ts`
Accept: Self-contained module that takes a container element and emits events
(folder selected, error). Fetches `GET /api/sharepoint/folders` for folder tree.
Breadcrumb navigation. Instantiated once inside each modal (email + schedule) —
no DOM ID soup, no duplicate logic (FA3). Handles loading/error states.
Covers: P9, FA3 (dedupe SharePoint picker).

---

**T10.04 — Delivery service (run_and_deliver + scope snapshot)**
Files: `rebuild/delivery/service.py`
Accept: `DeliveryService.run_and_deliver(schedule_or_email_now_params)`:
(1) re-resolve owner principal + scope via `authorize_delivery` (BH48),
(2) run report with owner's scope (not viewer's scope — salesman-scoped
schedules don't leak other reps' data), (3) export to Excel from cached result,
(4) send via email and/or save to SharePoint, (5) record in run_log. Delivery
jobs carry `principal + scope_snapshot` at enqueue time.
Covers: P18, BH48 (delivery with owner scope).

---

**T10.05 — Email modal + endpoint**
Files: `rebuild/static_src/ts/modals/email.ts`,
`rebuild/templates/report_view.html` (dialog element),
`rebuild/blueprints/delivery_routes.py`
Accept: `<dialog>` element in report_view.html. Controller: recipients input,
subject (pre-filled), message, SharePoint folder picker (T10.03), validation
(at least one recipient or SharePoint target). Submit → `POST /api/reports/<key>/email-now`
→ enqueue delivery job → poll for completion. CSRF on POST.
Covers: P9 (A10.1–A10.16), email-now route from manifest.

---

**T10.06 — Schedule modal + endpoint**
Files: `rebuild/static_src/ts/modals/schedule.ts`,
`rebuild/templates/report_view.html` (dialog element),
`rebuild/blueprints/delivery_routes.py`
Accept: `<dialog>` element in report_view.html. Controller: cadence
(daily/weekly/monthly), weekday selector (for weekly), monthday field (for
monthly), recipients, message, SharePoint folder picker, validation. Submit →
`POST /api/schedules` → save schedule → confirmation.
Covers: P10 (A11.1–A11.13), schedules route from manifest.

---

**T10.07 — Schedule runner + cadence + tick**
Files: `rebuild/delivery/scheduling.py`, `rebuild/jobs/scheduler.py`
Accept: `ScheduleRunner` loads due schedules, enqueues `schedule.run` jobs.
`schedule.tick` fires periodically (cron-like from scheduler). Cadence parsing:
daily, weekly (specific days), monthly (specific day). Tick checks which
schedules are due and enqueues them. Leader-only (T4.02 — only one process
runs the scheduler).
Covers: P18, BH17 (single leader for scheduler).

---

**T10.08 — Outbox drain**
Files: `rebuild/delivery/email.py`
Accept: Background drain loop (leader-only) processes outbox rows. Sends
pending emails, updates status. Capped retry for transient failures. Permanent
failures logged to audit.
Covers: P18.

---

**T10.09 — SharePoint status/folders endpoints**
Files: `rebuild/blueprints/delivery_routes.py`
Accept: `GET /api/sharepoint/status` → returns whether SharePoint is configured
and accessible (setting name + Graph status on error — BH47).
`GET /api/sharepoint/folders` → returns folder tree for the picker. Both behind
auth.
Covers: P9, P10, sharepoint routes from manifest.

---

**T10.10 — Schedule CRUD endpoint**
Files: `rebuild/blueprints/delivery_routes.py`
Accept: `POST /api/schedules` → create schedule. Future: GET/PUT/DELETE for
schedule management (schedules list page is deferred, but the API exists for
the modal to save). Schedule stored with owner principal + scope snapshot +
params + cadence + recipients + SharePoint target.
Covers: P10, schedules route from manifest.

---

### Phase 11 — Admin / Settings / Impersonate

Covers: P11, P12, P13.

---

**T11.01 — Settings page + theme endpoint**
Files: `rebuild/blueprints/settings_routes.py`, `rebuild/templates/settings.html`
Accept: `GET /settings` shows: profile (read-only: name, email, role), theme
selector (4 themes), admin links (visible to admin/developer roles), feature
flags section (admin-only). `POST /settings/theme` saves theme preference.
Covers: P11 (A12.1–A12.7).

---

**T11.02 — Preferences API endpoint**
Files: `rebuild/blueprints/settings_routes.py`
Accept: `POST /api/settings/preferences` saves user preferences (theme, etc.).
CSRF protected.
Covers: P11, preferences route from manifest.

---

**T11.03 — Admin users page**
Files: `rebuild/blueprints/admin_routes.py`, `rebuild/templates/admin_users.html`
Accept: `GET /admin/users` (admin-only). Two tables: users table (name, email,
role, flags, edit/delete) + salesman master table (name, number, group,
commission rate, edit). Edit user modal with: role select, flags (active,
dashboard, sharepoint, test, external), salesman scope grid, report access
overrides (inherit/allow/deny per report).
Covers: P12 (A13.1–A13.30), BH22 (user management).

---

**T11.04 — User CRUD endpoints**
Files: `rebuild/blueprints/admin_routes.py`
Accept: `/api/admin/users` (GET list, POST create), `/api/admin/users/<id>`
(GET, PUT, DELETE). Admin-only. CSRF on writes. Central authz (T2.04) verifies
admin role.
Covers: P12, admin user routes from manifest.

---

**T11.05 — Salesman access grid endpoint**
Files: `rebuild/blueprints/admin_routes.py`
Accept: `/api/admin/users/<id>/salesman-access` (GET current scope, PUT update).
Sets which salesman keys a user can see. Used by the edit-user modal's scope
grid.
Covers: P12, BH29 (per-role scope correctness), salesman-access route from
manifest.

---

**T11.06 — Report access overrides endpoint**
Files: `rebuild/blueprints/admin_routes.py`
Accept: `/api/admin/users/<id>/report-access` (GET current, PUT update).
Per-report: inherit (use role default), allow, deny. Admin-only.
Covers: P12, report-access route from manifest.

---

**T11.07 — Salesman master edit endpoint**
Files: `rebuild/blueprints/admin_routes.py`
Accept: `PUT /api/admin/salesmen/<key>` updates display info for a salesman
(name, number, commission rate) in the local admin copy. Note: commission rate
source of truth is SQL Server (BH40); this is the admin-UI sync copy.
Covers: P12, salesman edit route from manifest.

---

**T11.08 — Feature flags admin endpoint**
Files: `rebuild/blueprints/admin_routes.py`
Accept: `POST /api/admin/feature-flags` toggles feature flags. Admin-only.
CSRF protected. Flags include: `DASHBOARD_REFRESH_ENABLED` (BH9),
`WORKER_MODE` (in_process vs separate).
Covers: P20, feature-flags route from manifest.

---

**T11.09 — Impersonate page and routes**
Files: `rebuild/blueprints/auth_routes.py`, `rebuild/templates/impersonate.html`
Accept: `GET /impersonate` shows role-grouped user list (admin/developer only).
`POST /impersonate` starts impersonation — sets `impersonating_*` fields on
Principal (T2.03). Can't nest (if already impersonating, refuse).
`POST /impersonate/end` or `GET /impersonate/end` stops impersonation.
**Explicit "end impersonation" control** visible in the header when
impersonating (SIGN-OFF A14.6 — see §7).
Covers: P13 (A14.1–A14.6), BH32 (Principal round-trip with impersonation).

---

### Phase 12 — Polish / Ship

---

**T12.01 — LIVE parity scaffold (temporary)**
Files: `rebuild/tests/test_parity.py`
Accept: Test framework that compares rebuilt invoiced output (from a known SP
fixture or live capture) against LIVE export captures. Runs the grouping engine
on the fixture, exports via the writer, and compares column-by-column with the
LIVE capture. Sign-off items (§7) are individual test cases. Retires after SQL
cutover — after cutover, tests target SP output directly.
Covers: BH49 (parity harness).

---

**T12.02 — Security tests**
Files: `rebuild/tests/test_boot_safety.py`, `rebuild/tests/test_csrf.py`
Accept: Boot safety tests: refuse `AUTH_MODE=dev` in prod, refuse default
`FLASK_SECRET`, refuse `/home`/UNC DB paths, refuse missing Litestream. CSRF
tests: every `POST`/`PUT`/`PATCH`/`DELETE` route requires valid CSRF token
(explicit list; only healthz + callback exempt — FC7). Path sanitization:
no path traversal in export downloads or file operations. Admin-only routes
return 403 for non-admin users.
Covers: BH5, BH7, FC7 (CSRF audit).

---

**T12.03 — Memory budget tests**
Files: `rebuild/tests/test_memory_budget.py`
Accept: Generate a fixture at max expected row count (e.g. 200K rows × 19
columns for YTD invoiced). Run through the full pipeline: runner → engine →
cache → view builder → export writer. Measure peak memory. Must complete
without OOM on B1 (1.75GB RAM with ~1GB available). Output: the exact row-count
and byte thresholds that become the configured budget for T6.04.
Covers: BH10, FC9 (memory limits). Thresholds feed T6.04/T6.05.

---

**T12.04 — Restore-from-empty-disk test**
Files: `rebuild/tests/test_restore.py`
Accept: Simulate empty `/tmp` (container recycle). Litestream restore from Blob
→ `precious.db` present with expected row counts. App starts normally. End-to-
end: cold boot → restore → login → run report → result returned.
Covers: BH8 (cold-start restore).

---

**T12.05 — Accessibility audit pass**
Files: All templates, CSS, TypeScript
Accept: Modals use `<dialog>` (native `role="dialog"`, `aria-modal`, focus
trap). Filter drawer uses `aria-expanded`, `aria-controls`. Customer search
uses `role="combobox"` with `aria-autocomplete`. Tab bar uses `role="tablist"` /
`role="tab"` / `role="tabpanel"`. All interactive elements keyboard-navigable.
Theme toggle and help buttons have accessible labels. Review against WCAG 2.1
AA basics (not full audit — workable, not pixel-perfect).
Covers: P1 (cross-cutting a11y requirements).

---

**T12.06 — Dark mode audit**
Files: `rebuild/static_src/css/tokens.css`, all CSS
Accept: Every UI element is visible and usable in dark theme. Column options
menu, report header, modals, panels, Tabulator chrome — all use tokens, not
hardcoded colors. Checklist in expectation file for the report screen.
Covers: BH24 (dark mode invisible elements).

---

**T12.07 — Responsive testing pass**
Files: All templates, CSS
Accept: Test at 375px, 768px, 1440px. Filter row wraps below 600px, Run button
full-width. Table scrolls horizontally — page does not grow. Bottom nav visible
and usable with safe-area. Table height fills viewport. Report cards on home
page stack on mobile.
Covers: BH23 (viewport-fit), A16.1–A16.10.

---

**T12.08 — Deploy to temporary slot + cutover documentation**
Files: `rebuild/wsgi.py`, `rebuild/startup.sh`, `deploy.ps1` (update),
`README.md` (update)
Accept: v3 rebuild deploys to the TEMPORARY slot (`APP_MOUNT_PATH=/test-next` by
default). The live `/test` app is untouched and still serves. Entra redirect URI
works for the temporary `{APP_MOUNT_PATH}/auth/callback`. `SCRIPT_NAME` verified.
Integration test: login → run report → export → download — all under the
temporary mount. README documents: branch strategy, and the **cutover-to-/test
checklist** (a config flip the owner triggers AFTER sign-off): set
`APP_MOUNT_PATH=/test`, add the `/test/auth/callback` Entra URI, move the old
test app to `/test-legacy`, disable scaffolding; plus the later `/test → /` LIVE
cutover and the rollback path. Cutover is config + Entra changes only — no code
edits.
Covers: P20, FC10 (dispatcher mount), BH5 (SCRIPT_NAME).

---

## §5 BH Coverage Table

Every BH item from BUILD-HISTORY.md mapped to the todo(s) that prevent it.

| BH | Bug | Todo(s) |
|---|---|---|
| BH1 | Jobs stuck — SQLite on SMB | T1.02, T1.04 |
| BH2 | TRUNCATE journal mode crash | T1.02 |
| BH3 | DB corruption | T1.07 |
| BH4 | Migration race between workers | T1.03 |
| BH5 | Cold start crash loop | T1.01, T1.04, T1.06 |
| BH6 | Cache "no such table" | T1.09, T5.09 |
| BH7 | DB path defaulted to SMB | T1.04 |
| BH8 | Container recycle wiped /tmp | T1.05, T12.04 |
| BH9 | Mirror refresh hammered API | T1.01, T3.12 |
| BH10 | OOM on huge row set | T4.05, T6.05, T12.03 |
| BH11 | 5-min timeout on large pulls | T5.08 |
| BH12 | Cancel can't stop running job | T4.04, T8.04 |
| BH13 | Cancel button stayed visible | T8.04 |
| BH14 | False "lost track of job" | T8.04 |
| BH15 | Timer reset on page return | T7.06, T8.04 |
| BH16 | No visibility into worker state | T1.07, T4.07 |
| BH17 | Multiple scheduler instances | T4.02 |
| BH18 | Stuck job blocked queue | T4.04, T4.07, T5.08 |
| BH19 | Emergency repair endpoints | T1.07 |
| BH20 | `report.ts` god file | T8.02–T8.12 |
| BH21 | Session cookie collision | T2.02 |
| BH22 | Real users land as no-access | T2.08, T3.04 |
| BH23 | Table doesn't fit viewport | T7.10, T8.05 |
| BH24 | Dark mode invisible elements | T7.01, T12.06 |
| BH25 | Deep link init order wrong | T8.03 |
| BH26 | Export blocks browser | T9.01 |
| BH27 | Export doesn't match screen | T5.03, T6.01, T9.03 |
| BH28 | Revoked user reads cached result | T2.04, T8.14, T9.01 |
| BH29 | Wrong salesman scope | T2.04, T11.05 |
| BH30 | Lookups return wrong key shape | T8.13 |
| BH31 | No asset cache busting | T7.09 |
| BH32 | Impersonation fields dropped | T2.03, T11.09 |
| BH33 | Credit detected by regex | T5.10 |
| BH34 | Totals by Salesman wrong | T5.03, T5.10 |
| BH35 | Commission YTD off by pennies | T5.04 |
| BH36 | Prior-year rows in pivot | T5.04 |
| BH37 | Multi-customer silently post-filtered | T5.06 |
| BH38 | Double YTD fetch | T5.07, T5.08 |
| BH39 | Misc Charges column missing | T5.10 |
| BH40 | Commission rate source drift | T5.10 |
| BH41 | SalesmanNumber removed | T5.10 |
| BH42 | Invoice count over-counted | T5.10 |
| BH43 | Bad dates cause 500 | T5.06 |
| BH44 | SP migration carried legacy aliases | T5.02 |
| BH45 | Commissions special-cased | T5.04, T5.10 |
| BH46 | YTD window anchored wrong | T5.04, T5.06 |
| BH47 | SharePoint delivery failed silently | T10.02 |
| BH48 | Delivery leaked other reps' rows | T2.04, T10.04 |
| BH49 | Parity harness caught drift | T12.01 |
| BH50 | Diagnostic probes saturated API | T1.07, T3.11 |

---

## §6 To-Fix Coverage

### FA (Frontend Structure)

| ID | Problem | Todo(s) |
|---|---|---|
| FA1 | `report.ts` god file (2100 lines) | T8.02–T8.12 (split into 10 modules) |
| FA2 | Panels/modals built imperatively in JS | T8.01, T8.06, T8.09–T8.11 (template-defined, toggled) |
| FA3 | Duplicate SharePoint picker | T10.03 (one reusable module) |
| FA4 | Full Tabulator teardown per tab switch | T8.05 (setData/setColumns when possible) |
| FA5 | `any` everywhere in TypeScript | T8.05 types.ts (strict interfaces) |
| FA6 | Global mutable state | T8.02 (module-scoped controllers, not global lets) |
| FA7 | `pages.css` dumping ground | T7.01, T7.02 (tokens + split by concern) |

### FB (Reports Engine Structure)

| ID | Problem | Todo(s) |
|---|---|---|
| FB1 | Row-level math in Python | T5.10 (all math in SP; config declares columns) |
| FB2 | Hardcoded tabs/columns/aggregations | T5.03, T5.10 (generic engine + DB-driven tab config) |
| FB3 | Per-report hardcoded orchestration | T5.01, T5.07 (config-driven runner) |
| FB4 | Adapter does too much | T5.02 (rename/normalize only) |
| FB5 | Static code-driven registry | T3.06, T5.10 (DB-backed report_configs) |
| FB6 | UI coupled to per-tab payload | T6.01 (flat snapshot + view configs) |
| FB7 | God files in engine + blueprint | T5.01–T5.10 + T8.01–T8.14 (split by concern) |
| FB8 | Deferred reports wired in | T5.10 (status='disabled' in config) |

### FC (Platform Structure)

| ID | Problem | Todo(s) |
|---|---|---|
| FC1 | Worker threads hardcoded to 2 | T4.01 (JOB_WORKER_THREADS env var, default 1) |
| FC2 | No queue backpressure | T4.06, T3.03 (depth cap + 503/Retry-After) |
| FC3 | Time-based asset version | T7.04, T7.09 (content hash) |
| FC4 | No per-job timeout | T4.04 (MAX_JOB_DURATION_SECONDS) |
| FC5 | Leader fallback too permissive | T4.03 (logged warning, explicit flag) |
| FC6 | No Postgres off-ramp seams | T1.02, T1.08, T3.03 (Connection protocol, Python UTC, abstract claim_next, lock_for_migration) |
| FC7 | CSRF exempt list incomplete | T2.09, T12.02 (explicit exempt set + CSRF audit test) |
| FC8 | Litestream not in deploy | T1.05 (download + verify in startup) |
| FC9 | No memory limits | T6.04, T6.05, T12.03 (budget + paged fallback + test) |
| FC10 | DispatcherMiddleware path risks | T1.06, T12.08 (SCRIPT_NAME + integration test) |

---

## §7 Human Sign-Off Gates

These 9 items from FEATURE-INVENTORY §5 are questions the owner must answer.
They BLOCK the "invoiced numbers verified" milestone. The builder marks each
item PROVISIONAL in code and config until the owner signs off. Do not invent
business math — build to the SP contract and flag the question.

### Invoiced math / parity (block the parity harness)

| # | Question | Blocking todo | What happens until signed off |
|---|---|---|---|
| 1 | **B4.3** — Commission rate: does the SP per-row `commission` match LIVE's `commission_map`? | T5.10, T12.01 | Seed uses SP rate; parity test flagged PROVISIONAL |
| 2 | **B4.4** — Monthly commission net formula: does LIVE include Misc in the base? (v3 net = sub+tar+misc+credits) | T5.04, T12.01 | Pivot uses SP's `CommissionBase`; formula flagged PROVISIONAL |
| 3 | **B4.5** — Totals by Salesman: LIVE excludes credits, v3 nets them in. Confirm numbers agree. | T5.03, T5.10, T12.01 | Totals tab seeded with generic SUM of SP columns; credit handling flagged PROVISIONAL |
| 4 | **B4.7** — Do LIVE Full Details / Credits / Invoices sheets include a Misc Charges column? | T5.10, T12.01 | Misc column included in all tabs by default; visibility flagged PROVISIONAL |
| 5 | **B4.1** — Known intentional drift: v3 dropped SalesmanNumber from Summary. Confirm wanted. | T5.10 | Summary tab config omits SalesmanNumber; flagged PROVISIONAL |
| 6 | **B4.2** — Known intentional drift: v3 added Misc to Summary (LIVE omits). Confirm wanted. | T5.10 | Summary tab config includes Misc; flagged PROVISIONAL |

### Scope / product calls

| # | Question | Blocking todo | What happens until signed off |
|---|---|---|---|
| 7 | **A10.16** — SharePoint-save in first cut: include or defer? | T10.05, T10.02 | Email modal includes SharePoint picker; if deferred, picker disabled with "coming soon" label |
| 8 | **A14.6** — Explicit "end impersonation" control visible in header. Confirm wanted. | T11.09 | Built with visible end-impersonation button; flagged for confirmation |
| 9 | **A1.2 / A1.14** — Test Site nav link + v3 marker fate once v3 owns `/test`. | T7.03, T12.08 | Test Site link removed from nav (kept as admin diagnostic in Settings); v3 marker hidden; flagged for confirmation |

---

## §8 Tests as Ship Gate

No shipping without green suites for each area below. Each suite maps to
specific todos that build the test.

| Suite | What it proves | Key BH/FC | Built in |
|---|---|---|---|
| **Report parity** | Rebuilt invoiced output matches LIVE export (column-by-column, per sign-off) | BH49 | T12.01 |
| **Grouping engine** | Tab configs → correct filtered/grouped/aggregated output; subtotals skip percent columns | BH27, BH34 | T5.03 |
| **Export parity** | Export output matches screen tab data exactly (same builder, same data) | BH27 | T9.03 |
| **Authorization / scope** | Admin sees all; manager sees their salesmen; salesman sees own only; revoked user blocked; stale result/export re-checked; delivery uses owner scope | BH28, BH29, BH48 | T2.04 |
| **Job lifecycle** | Enqueue → claim → progress → complete; dedup; cancel; orphan recovery (capped at 1); timeout | BH10, BH12, BH16 | T3.03, T4.01–T4.07 |
| **Cache scoping** | Cache key includes scope token; narrowed scope → 403 not stale data; cache.db self-heals | BH6, BH28 | T5.09, T1.09 |
| **Migrations** | Apply on fresh DB; skip-if-applied; leader gate; no race with concurrent workers | BH4 | T1.03 |
| **Security: boot refusal** | Prod refuses dev auth, default secret, SMB/UNC paths, missing Litestream | BH5, BH7 | T12.02 |
| **Security: CSRF** | Every POST/PUT/PATCH/DELETE route requires valid token (explicit exempt set) | FC7 | T12.02 |
| **Security: path sanitization** | No path traversal in export downloads or diagnostic endpoints | — | T12.02 |
| **Restore from empty disk** | Cold boot → Litestream restore → login → run → result | BH8 | T12.04 |
| **Memory budget** | Max expected row count completes without OOM; produces the budget thresholds for T6.04/T6.05 | BH10, FC9 | T12.03 |

---

## §9 Author Calls (where consensus was silent)

The DEBATE-LOG resolves architecture — persistence, grouping, worker model. The
items below were not explicitly debated. I made a call; review these and
override if needed.

1. **Module layout / directory structure.** Both proposals show different file
   trees. I synthesized one that honors OP3 (worker_main.py separate from
   Flask; shared packages are Flask-free) and keeps the structure flat enough to
   navigate. Override the file paths if a different layout is preferred — the
   architecture is the same either way.

2. **Phase ordering.** The debate resolved WHAT to build, not the build
   sequence. I ordered by dependency: you can't build the viewer without the
   engine, can't build the engine without repositories, etc. The 12-phase
   sequence is a suggestion; any re-ordering that respects the dependency arrows
   is fine.

3. **Impersonation phasing.** Not discussed in the debate. I placed it in Phase
   11 (Admin/Settings) since it depends on user management being complete and
   is an admin-power-user feature.

4. **Notifications scope.** `GET /api/notifications` is in the route manifest
   but the notification data model wasn't debated. I scoped it to active-job
   notifications only (for the FAB badge and nav badge), not a general
   notification system. Expand later if needed.

5. **Container startup mechanism.** OP3 says "own process from the container
   startup" but doesn't specify how. I chose a bash startup script
   (`startup.sh`) that launches gunicorn + worker_main.py — simplest approach
   for one container. supervisord or similar could replace it without
   architecture change.

6. **Snapshot serialization format in cache.db.** Consensus says "one canonical
   flat snapshot in cache.db" but doesn't specify the schema (JSON blob vs
   normalized rows). I left this as a T3.02 design decision — the snapshot_store
   abstraction (T6.02) makes the internal format swappable.

7. **Tabulator version.** Not specified. The plan says "latest Tabulator behind
   a grid adapter" — the adapter (T8.05) insulates the app from version
   changes. Pin the version in `package.json` at build time.
