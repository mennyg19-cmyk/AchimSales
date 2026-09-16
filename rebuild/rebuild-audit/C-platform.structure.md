# C-Platform Structure Audit — Area C (Platform)

**Model:** kimi-k2.5

## Proof of Read

- `v3/web/config.py` — boot-time config validation with fail-closed prod checks (lines 73-109), SMB/UNC detection for SQLite paths, Litestream requirement gating
- `v3/web/__init__.py` — create_app factory with CSRF init, _is_background_leader() flock-based leader election (lines 341-373), _ASSET_VERSION timestamp cache-busting, bootstrap_background() seeding + worker/scheduler start
- `v3/web/auth/authorization.py` — central Authorization class with DB-resolved scope (`visible_salesman_keys`), re-resolution at job time for delivery authz
- `v3/web/jobs/worker.py` — bounded semaphore (max_workers=2), recover_orphans() crash recovery with attempts tracking, heartbeat logging
- `v3/web/data/connection.py` — WAL mode with retry logic (_WAL_RETRIES=20), context-manager transaction wrapper
- `v3/web/data/migrate.py` — versioned migration runner with BEGIN IMMEDIATE + atomic version insert
- `v3/web/data/repositories/jobs.py` — dedup via partial unique index `idx_jobs_dedup_active`, _MAX_RECOVERY_RETRIES=1 for crash-loop protection
- `v3/web/extensions.py` — minimal CSRF (hmac.compare_digest), exempts healthz + auth.callback only
- `wsgi.py` — DispatcherMiddleware mount at /test, async bootstrap via daemon thread, boot error capture to downloadable log
- `deploy.ps1` — zip-based Azure deploy (no Litestream binary deployment visible here)

---

## 1. COVERAGE SKELETON — Platform Modules/Blueprints

### Auth (`v3/web/auth/`)
- [ ] `msal_flow.py` — Entra login flow (MSAL)
- [ ] `session.py` — session-backed principal storage, sync_role()
- [ ] `principal.py` — Principal dataclass, VALID_ROLES, _PRIVILEGED
- [ ] `authorization.py` — **CENTRAL AUTHZ**: Authorization class, scope enforcement, delivery re-resolution
- [ ] `decorators.py` — require_login, require_privileged

### Auth Blueprints (`v3/web/blueprints/`)
- [ ] `auth.py` — login/logout routes, dev login, impersonation (developer-only)
- [ ] `admin.py` — user CRUD, salesman access, report access overrides
- [ ] `settings.py` — theme/preferences
- [ ] `health.py` — /healthz (minimal), manifest.json (mount-aware)

### Jobs (`v3/web/jobs/`)
- [ ] `worker.py` — JobWorker: semaphore-bound ThreadPoolExecutor, leader-only poller, recover_orphans()
- [ ] `scheduler.py` — APScheduler wrapper, cron jobs with misfire_grace_time=300

### Data (`v3/web/data/`)
- [ ] `connection.py` — Database class: precious() + cache() SQLite with WAL
- [ ] `migrate.py` — apply_migrations() with atomic version tracking
- [ ] `repositories/jobs.py` — JobRepository: enqueue with dedup, claim_next, crash recovery
- [ ] `repositories/users.py` — UserRepository: role/flag storage
- [ ] `repositories/salesmen.py` — SalesmanRepository
- [ ] `repositories/exports.py` — ExportRepository
- [ ] `repositories/run_log.py` — ReportRunLogRepository (audit)
- [ ] `repositories/preferences.py` — user preferences
- [ ] `repositories/notifications.py` — notifications
- [ ] `repositories/schedules.py` — ScheduleRepository, MasterScheduleRepository
- [ ] `repositories/feature_flags.py` — FeatureFlagRepository
- [ ] `repositories/saved_reports.py` — SavedReportRepository
- [ ] `repositories/dashboard.py` — DashboardRepository (deferred per C-platform.md)
- [ ] `repositories/outbox.py` — OutboxRepository (email/SP staging)
- [ ] `repositories/exclusions.py` — user customer exclusions

### Delivery (`v3/web/delivery/`)
- [ ] `email.py` — EmailService, outbox pattern, split_recipients
- [ ] `sharepoint.py` — SharePointService
- [ ] `service.py` — DeliveryService: run-and-deliver orchestration
- [ ] `jobs.py` — delivery job handler
- [ ] `layout.py` — apply_layout, expand_clones

### Scheduling (`v3/web/scheduling/`)
- [ ] `runner.py` — ScheduleRunner
- [ ] `tick.py` — make_tick() cron enqueue
- [ ] `cadence.py` — cadence parsing
- [ ] `jobs.py` — schedule run job handler

### Reporting Jobs (`v3/web/reporting/`)
- [ ] `jobs.py` — report.run job handler, enqueue_report_run() with dedup
- [ ] `export_jobs.py` — export job handler
- [ ] `cache.py` — ReportCache with cache key builder

### App Wiring (`v3/web/`)
- [ ] `__init__.py` — create_app(), bootstrap_background(), _is_background_leader(), _ASSET_VERSION
- [ ] `config.py` — Config dataclass, validate() with fail-closed checks
- [ ] `extensions.py` — init_csrf(), csrf_token()
- [ ] `wsgi.py` — v3-only WSGI entry (unused in root dispatcher)

### Root Deploy (`./`)
- [ ] `wsgi.py` — DispatcherMiddleware: / (live), /test (v3), async bootstrap, boot error logging
- [ ] `deploy.ps1` — zip deploy to Azure App Service

### Migrations (`v3/web/data/migrations/`)
- [ ] `precious/0001_initial.sql` — users, salesmen, jobs, schedules, audit tables
- [ ] `precious/0002_job_attempts.sql` — attempts column for crash-loop protection
- [ ] `cache/0001_initial.sql` — report_payload_cache, export_files
- [ ] `cache/0003_report_exports.sql` — export metadata
- [ ] `cache/0005_export_retention.sql` — retention policy

---

## 2. TO-FIX — Structural Risks and Issues

### FC1: Worker capacity hardcoded to 2 — no tuning for report weight
**Where:** `v3/web/jobs/worker.py` line 37: `max_workers: int = 2`
**Risk:** On a 1-vCPU B1, 2 concurrent heavy report runs can exhaust CPU/memory. Past OOM crashes (noted in rebuild brief) suggest this is a live issue.
**Fix direction:** Make `max_workers` environment-driven (`JOB_WORKER_THREADS`) with a conservative default (1 for B1, 2 for B2+).

### FC2: No backpressure on job queue depth
**Where:** `v3/web/jobs/worker.py` `_loop()`
**Risk:** The semaphore limits *running* jobs but not *queued* jobs. A burst of requests (e.g., dashboard refresh + 10 user exports) can pile up unlimited queued jobs. SQLite can handle it, but recovery time after a restart grows.
**Fix direction:** Add max queue depth check in `JobRepository.enqueue()` — return 503/retry-after when full.

### FC3: Asset versioning is time-based, not content-based
**Where:** `v3/web/__init__.py` line 16: `_ASSET_VERSION = str(int(time.time()))`
**Risk:** Every deploy busts all caches even for unchanged assets. Users re-download identical JS/CSS. Minor cost/performance issue.
**Fix direction:** Replace with git short hash or content hash of static_dist at boot time.

### FC4: Worker has no per-job timeout/watchdog
**Where:** `v3/web/jobs/worker.py` `_run()`
**Risk:** A report that hangs (infinite loop in builder, slow Reporting API) holds a worker slot forever. No SIGALRM or future timeout kills it. Orphan recovery only helps on *process* crash, not a stuck thread.
**Fix direction:** Add `max_job_duration_seconds` config; use `concurrent.futures.Future.result(timeout=...)` in the executor or spawn a killer thread.

### FC5: Leader election fallback is too permissive on Windows
**Where:** `v3/web/__init__.py` lines 359-360: `except Exception: return True`
**Risk:** Local dev on Windows runs multiple "leaders." Not a prod issue (Azure is Linux), but tests may behave differently than prod.
**Fix direction:** Log a loud warning when falling back to leader=True; consider explicit `V3_FORCE_LEADER` env override for test control.

### FC6: Missing repository abstraction for Postgres off-ramp
**Where:** `v3/web/data/connection.py`, all repositories
**Risk:** SQLite-specific code (WAL, busy_timeout, datetime('now')) is scattered. Postgres migration requires touching every repository.
**Fix direction:** Document the abstraction boundary: `Database` should hide SQLite-isms; repositories should not use `datetime('now')` or JSON1 functions directly. See OPEN DEBATE entry below.

### FC7: CSRF exempt list may be incomplete
**Where:** `v3/web/extensions.py` line 17: `_EXEMPT_ENDPOINTS = {"health.healthz", "auth.callback"}`
**Risk:** MSAL callback is POST (token exchange). It's exempt. Confirm no other state-changing routes are accidentally exempted.
**Fix direction:** Audit all POST/PUT/PATCH/DELETE routes for CSRF token presence in templates/JS.

### FC8: Deploy script doesn't bundle Litestream binary
**Where:** `deploy.ps1`
**Risk:** Litestream runs as a sidecar (implied by C-platform.md brief), but deploy.ps1 doesn't mention it. If the App Service doesn't have it pre-installed, precious.db isn't replicated.
**Fix direction:** Add Litestream binary to the zip or document the Azure startup command that downloads it.

### FC9: No memory limit enforcement for report runs
**Where:** `v3/web/reporting/runner.py` (not in scope of this audit but called from worker)
**Risk:** The rebuild brief mentions "memory limits handling big flat tables on a small instance" as an open question. The worker doesn't track or limit memory usage per job.
**Fix direction:** Add `resource` module limits (Linux-only) or document that large reports *must* be run as exports (which can stream) vs on-screen (which loads all tabs).

### FC10: DispatcherMiddleware mount has subtle path routing risks
**Where:** `wsgi.py` line 124: `DispatcherMiddleware(live_app, MOUNTS)`
**Risk:** `/test` prefix stripping can confuse Flask url_for in v3. The manifest.json handles it, but internal redirects may break.
**Fix direction:** Verify `SCRIPT_NAME` is set correctly for v3; add integration test for `/test/auth/callback` redirects.

---

## 3. OPEN DEBATE — SQLite vs Postgres: Trade-offs and Seams

**Status:** REBUILD-BRIEF.md line 68 lists this as an "Open for the Phase 0/1 architecture debate" question. The brief defaults to "local SQLite + Litestream (cheapest, single-instance) vs managed Postgres (more moving parts, easier multi-instance later)."

### Current SQLite Implementation (Locked In)
- Two databases: `precious.db` (replicated, durable) and `cache.db` (disposable)
- WAL mode required for Litestream (WAL is what Litestream tails)
- Strict local-disk requirement (`_is_unc()`, `_is_app_service_home()` checks in config.py)
- Retry logic for WAL mode switching (`_WAL_RETRIES = 20`)

### Where Repository Interfaces Would Need to Sit

**Current abstraction (partial):**
```
web.data.connection.Database
  ├── precious() → Iterator[sqlite3.Connection]
  └── cache() → Iterator[sqlite3.Connection]
```

Repositories directly use:
- `datetime('now')` — SQLite-specific (Postgres: `NOW()` or `CURRENT_TIMESTAMP`)
- `json` module for params_json — works on both, but Postgres prefers native JSONB
- Partial unique indexes: `idx_jobs_dedup_active` with `WHERE status IN (...)` — Postgres syntax compatible, but requires index name management
- Foreign keys with `ON DELETE CASCADE` — works on both
- `INSERT ... ON CONFLICT` — SQLite syntax; Postgres uses `ON CONFLICT` (compatible) or `UPSERT`

### Postgres Off-Ramp Requirements

| Seam | Current | Postgres Change |
|------|---------|-----------------|
| **Connection** | `sqlite3.connect()` | `psycopg2.connect()` or asyncpg |
| **Datetime** | `datetime('now')` | `NOW()` or client-side UTC |
| **JSON** | `json.dumps/loads` text | Native JSONB with operators |
| **WAL** | Required for Litestream | Not needed; use streaming replication |
| **Migrations** | `.sql` files with SQLite DDL | Same files need `SERIAL` vs `AUTOINCREMENT`, `TEXT` stays compatible |
| **Dedup index** | `CREATE UNIQUE INDEX ... WHERE` | Same syntax works |
| **Job queue** | SQLite row locking | Postgres `SELECT ... FOR UPDATE SKIP LOCKED` |

### Clean Off-Ramp Architecture

To enable Postgres later without a full rewrite, these interfaces need tightening NOW:

1. **Repository interface:** All repos should depend on a `Connection` protocol, not `sqlite3.Connection` directly. Methods like `execute()`, `fetchone()`, `fetchall()`, `commit()` are common.

2. **Datetime factory:** Replace `datetime('now')` in SQL with explicit UTC from Python: `datetime.now(timezone.utc).isoformat()` — works on both databases.

3. **JSON handling:** Keep `json.dumps/loads` in Python layer, store as TEXT. Postgres migration can transparently change column to JSONB without code changes.

4. **Job locking:** Abstract `claim_next()` — SQLite uses `UPDATE ... WHERE status='queued'` row locking; Postgres needs `FOR UPDATE SKIP LOCKED`.

5. **Migration runner:** Already file-based and database-agnostic (mostly). The `BEGIN IMMEDIATE` is SQLite-specific; Postgres would use `BEGIN` with appropriate isolation.

### Recommendation for the Debate

**Keep SQLite + Litestream for now** (per brief default) because:
- Single B1 instance is the target
- No network hop to a managed DB
- Litestream gives point-in-time recovery to Azure Blob

**But prepare the seams now:**
- Audit all SQL for `datetime('now')` → replace with Python UTC
- Ensure no SQLite-only features (JSON1 functions like `json_extract`) are used
- Document the `claim_next()` abstraction needed for Postgres row locking

### Files to Touch for Postgres Migration

| File | Lines | Change |
|------|-------|--------|
| `web/data/connection.py` | 46-75 | Add `PostgresDatabase` class implementing same context manager |
| `web/data/migrate.py` | 57-63 | Abstract `BEGIN IMMEDIATE` behind a `lock_for_migration()` method |
| `web/data/repositories/jobs.py` | 104-116 | `claim_next()` needs `FOR UPDATE SKIP LOCKED` variant |
| All repo files | Various | Replace `datetime('now')` in SQL with `?` param from Python |

---

## Summary Counts

- **Coverage items:** 50 modules/repos/blueprints listed
- **TO-FIX items:** 10 structural risks (FC1-FC10)
- **Open debate:** SQLite-vs-Postgres with documented trade-offs and 5 seam requirements
