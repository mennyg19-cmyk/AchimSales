# v2 (`test/`) Audit & Rebuild Plan — opus48

> Authored by the **opus48** agent. A parallel agent is producing its own version
> of this document; the two will be compared head-to-head. Positions here are
> meant to be defensible.
>
> Scope: the `test/` subfolder only (the v2 rebuild mounted at `/v2`). The
> repo-root `webapp/`, `reports/`, `core/`, `config/` are the *live* app and are
> only referenced where `test/` couples to them.

---

## 0. Headline finding

**The README does not describe the code.** `test/README.md` claims *"Phase 1:
empty shell + mock-data scaffolding. No SQL connection, no real emails."* The
actual code is a **Phase 2+ operational application**: SQLite persistence, an
HTTP Reporting-API client with a mirror/cache layer, 5 working reports, a
dashboard, personal + master schedules, an admin console, background schedulers,
and a PWA manifest.

`DATABASE_URL`, `MAIL_MODE`, and `test/data/fixtures/` referenced in the README
**do not exist in the code**. `USE_MOCK_DATA` defaults to `false`, not `true`.

**Action zero of any rebuild: delete or rewrite the README.** Every plan built
on it starts wrong.

---

## 1. What `test/` actually is (real architecture)

```
Browser (Jinja + vanilla JS, no framework, no build step)
   │
   ▼
Flask app (wsgi.py DispatcherMiddleware mounts it at /v2)
   │  12 blueprints, cookie-session auth
   ▼
Service layer ── reporting_api (HTTP → on-prem stored procs) ──► SQL Server (never touched directly)
   │            ├─ mirror / mirror_refresh (offline D365 snapshots)
   │            ├─ cache_first (stale-while-revalidate rendered reports)
   │            └─ 5 report builders (reimplemented from root reports/)
   ▼
SQLite (hot copy on /tmp in Azure) ──db_sync──► SMB snapshot + JSON sidecar backup
```

Data is **not** mock and **not** direct SQL — it is HTTP to an on-prem Reporting
API (`REPORTING_API_BASE_URL` + `X-API-Key`), with SQLite as an offline
mirror/cache. The web tier never opens a SQL Server connection; `pyodbc` /
`SQLAlchemy` in `requirements.txt` are only used for the APScheduler job store on
the same SQLite file.

### Route surface (behavioral contract baseline)

- **Auth**: `/login`, `/login/dev` (POST), `/login/start`, `/auth/callback`, `/logout`
- **Reports**: `/reports`, `/report/<key>`, `/report/<key>/view`
- **Report API** (`/api/reports`): `<key>/salesmen|customers|years`, `/lookups/status`, `<key>/preview-body`, `<key>/run` (POST), `/jobs/<id>`, `<key>/export.xlsx` (POST), `<key>/email-now` (POST), `/test-reporting-api`
- **SharePoint API** (`/api/sharepoint`): `/configured`, `/folders`
- **Presets** (`/api/saved-reports`): GET/POST, `DELETE /<id>`
- **Schedules** (`/schedules`): list, `api` (POST), `api/<id>` (DELETE), `api/<id>/run` (POST), history
- **Master schedules** (`/master-schedules`): list, history, admin CRUD (POST/DELETE), run
- **Settings** (`/settings`): preferences, exclusions, admin (users, salesmen, flags, report-log)
- **Notifications** (`/api/notifications`): list, dismiss
- **Customer last order** (`/report/customer-last-order`): picker, `customers.json`, `<account>/recent-orders.json`, `<account>`
- **Dashboard**: `/dashboard`, `/customer/<account>`, `/order/<order_number>`, `/api/dashboard/refresh|refresh-status|data`
- **Diag** (`/diag`, admin): mirror refresh/backfill, DB integrity/repair, API ping, invoice debug
- **Infra**: `/healthz` (unauth), `/manifest.json` (unauth)

---

## 2. Audit findings by severity

### CRITICAL — security (fix before this ever sees production)

| # | Issue | Where |
|---|---|---|
| 1 | **`AUTH_MODE` defaults to `dev`** — anyone can `POST /login/dev` with *any* email and become that user (incl. admins). | `config/settings.py:83`, `blueprints/auth_bp.py:56` |
| 2 | **`FLASK_SECRET` defaults to `"change-me-in-prod"`** — forgeable session cookies if env not set. | `config/settings.py:26` |
| 3 | **IDOR on Customer Last Order** — no salesman/report scoping; any logged-in user can read any customer's orders (dashboard path *does* check; this one does not). | `blueprints/customer_last_order.py:70-165` |
| 4 | **Master-schedule PII leak** — recipients + SharePoint paths rendered for all logged-in users, not just admins. | `templates/master_schedules.html:59-65` |
| 5 | **Live API probe open to any user** — `/api/reports/test-reporting-api` hits the on-prem API; not admin-gated. | `blueprints/report_api.py:599` |
| 6 | **No CSRF protection** on any state-changing POST (only SameSite=Lax). | all `/api/*` POSTs |
| 7 | **`test_access_enabled` flag stored but never enforced** at login — the one gate meant to protect the sandbox does nothing. | `db.py:457` |
| 8 | **Unauthenticated `/healthz`** leaks `auth_mode` + mock flag. | `app.py:118` |

### HIGH — architecture & operational fragility

- **Five overlapping persistence mechanisms** for one app: (1) SQLite app schema,
  (2) mirror tables, (3) `db_sync` SMB snapshots, (4) JSON "critical backup"
  sidecar, (5) `api_payload_cache` + materialized `mirror_sales_header` /
  `mirror_dashboard_cache`. Each was added to patch a production incident. This
  is the single biggest source of complexity.
- **SQLite on Azure `/tmp` + WAL + SMB snapshot** is inherently fragile: up to
  60s data-loss window on snapshot failure, multi-worker races on one file,
  salvage-via-`iterdump` (lossy). The JSON sidecar exists *because* this keeps
  corrupting.
- **God files**: `db.py` ~2,300 lines, `mirror.py` ~1,800, `reporting_api.py`
  ~1,159, `dashboard_data.py` ~1,144, `diag.py` ~979; front end `report_view.js`
  3,386 lines and `style.css` 5,246 lines.
- **Blocking work on the request thread**: report `/run` can block up to 120s
  (API timeout); `cache_first` joins for 5s then serves stale; schedule "run now"
  does fetch→Excel→upload synchronously; critical user writes trigger a
  **blocking** full SMB backup.
- **Fail-open distributed locks** — if the single-flight claim errors, every
  worker does the heavy refresh anyway (`mirror_refresh.py:354`,
  `mirror_scheduler.py:100`).
- **Informal migrations** — ad-hoc `ALTER TABLE` lists, no version table, plus
  schema drift (`scheduler_owner` table exists only in the scheduler module).
- **Isolation breaches** vs the README's "never imports live code": imports
  `core.dates` in 6 files and reads the live app's `app.db` for admin roles.

### MEDIUM — duplication & quality (clean-code rules violated at scale)

- **~70–85% of report business logic is reimplemented** from the root `reports/`
  package rather than shared — a second copy of commission math, credit
  detection, tab layouts, the `SL_/SH_TariffCharges` fix, etc. Every
  business-rule change must now be made in **two** places or they drift.
- **Copy-pasted helpers** across all 5 report builders: `_num`, `_first`,
  `_sm_key`, `_load_salesman_map` (the salesman one even has a comment "lifted
  from invoiced.py").
- **Commission Excel layout** duplicated between
  `report_export._write_commission_cards` and the root writer.
- **Master-schedule CRUD duplicated** between `settings.js:177-350` and inline JS
  in `master_schedules.html:191-349` (same element IDs).
- **Three separate schedule-cadence UI systems** with different CSS class names,
  and **four parallel modal systems** in the CSS.
- **Dead assets shipped on every page**: `static/app.js` (733 lines, orphaned
  v1), `_live_report_form.js`, `table_tools.js` (+ its CSS),
  `_archive_mock_data.py.txt`, `fixtures/ordered_dump.json`.

### LOW — cleanup

- Inline styles everywhere (~67 in `settings.html`), hardcoded `#2563eb` in 8 CSS
  spots despite a token system, no `.icon-sm` utility.
- Accessibility: `user-scalable=no` (WCAG fail), modals with no `role="dialog"` /
  focus trap, `onclick` on cards instead of buttons, Tabulator always loads the
  **dark** theme even in light mode.
- No build step → no minification, no bundling, unpinned CDN deps, the full
  5,246-line stylesheet served on every request.

---

## 3. Rebuild from scratch — the plan

Core insight: **the report/data boundary is good (HTTP API, not raw SQL in the
web tier) — keep it. The persistence, duplication, and request-blocking are what
to throw away.**

### Principle 1 — Split data into "precious" vs "regenerable," and stop snapshotting

- **Precious** (users, permissions, presets, schedules, run history,
  notifications): small, irreplaceable → **managed Postgres** (Azure Database for
  PostgreSQL). This single move *deletes* `db_sync.py`, the JSON sidecar, the
  `iterdump` salvage, WAL-on-SMB worries, and the multi-worker file races.
- **Regenerable** (mirror of D365 rows, rendered report cache): rebuildable from
  the Reporting API → keep as a **pure cache** you can `TRUNCATE` and refill
  without fear. No backup needed.
- Result: 5 persistence mechanisms → **2**, and the scary one (durability of
  precious data) becomes the database vendor's problem.

### Principle 2 — One report engine, shared with production

Today there are **two** implementations of every report (root `reports/` for
Azure Automation, `test/webapp/services/reports/` for the web app). Pick one:

- Extract the **pure transformation logic** (the `build()` functions, commission
  math, credit detection) into a single shared package both the CLI runbook and
  the web app import. Web app feeds it API rows; CLI feeds it OData rows; both
  call the same aggregation.
- Define **one `ReportBuilder` protocol**: `build(rows, ctx) -> list[Tab]`. No
  more five different `build()` signatures.
- Move `_num`/`_first`/`_sm_key`/salesman-map into a `lib/` shared by all builders.

### Principle 3 — Get heavy work off the request thread

- Introduce a **job queue** (even APScheduler/RQ with a worker process). `/run`,
  exports, and schedule executions enqueue a job and return a job id; the viewer
  polls. Kills the 120s blocking calls and the 5s stale-while-revalidate hack.
- **One** cache layer keyed by `(report, params, builder_version, user_scope)`,
  not three.

### Principle 4 — Centralize authorization

- Remove the `dev` auth default entirely; Entra ID only, with a real dev-only
  flag that is off unless explicitly enabled locally.
- **One authorization layer**: a single function/decorator that resolves
  `(user, report, customer/salesman scope)` and is called on *every* data path —
  reports, presets, customer-last-order, dashboard, master schedules. No route
  queries data without going through it.
- Enforce `test_access_enabled` at login. Add CSRF tokens.

### Principle 5 — Front end: commit to one model + a build step

Given the small user base and existing Jinja investment, the pragmatic choice is
**keep server-rendered Jinja + a real build step**, not a full SPA rewrite:

- Add **esbuild** (or Vite); split `report_view.js` (3,386 lines) into ~5 modules
  (viewer core, column filters, Excel export, modals, commission layout) + a
  shared `api.js`.
- One CSS token file + component files; delete the dead table-tools layer;
  collapse the 4 modal systems into 1.
- Delete `app.js`, `_live_report_form.js`, `table_tools.js`.
- Fix the a11y baseline (drop `user-scalable=no`, add modal focus traps,
  theme-match Tabulator).

*(Alternative: align with the sister project's Next.js/React stack. Viable, but a
much larger lift — only worth it to share one front-end skill set across both
apps. Default recommendation is the Jinja-cleanup path.)*

### Suggested target architecture

```
Browser ── Jinja shell + bundled JS modules (esbuild)
   │
Flask (blueprints, thin) ── single authz layer
   │
Service layer:
   • report_engine/     (shared with CLI; pure build() functions + lib helpers)
   • reporting_client/   (HTTP API: translators.py, client.py, lookup_cache.py)  ← split reporting_api.py
   • cache/              (one cache, regenerable)
   • jobs/               (queue + worker: runs, exports, schedules, refresh)
   │
Postgres (precious: users, perms, presets, schedules, history)
SQLite/PG cache (regenerable: mirror rows, rendered payloads)
```

---

## 4. Phased migration (preserve the precious data)

0. **Freeze & document.** Replace the README with reality. Treat the route list
   in §1 as the behavioral contract. Snapshot current SQLite precious tables
   (users/perms/schedules/presets/history) — these must survive.
1. **Security patch in place.** Fix the 8 critical items on the *current* code
   first. Do not wait for the rebuild.
2. **Postgres for precious data.** Migrate users/perms/schedules/presets/history;
   retire `db_sync` / JSON-sidecar / salvage.
3. **Shared report engine.** Extract pure builders + lib; web + CLI import the
   same code; delete the duplicated `test/.../reports/*` logic.
4. **Job queue.** Move runs/exports/schedules off the request thread; collapse to
   one cache.
5. **Front-end cleanup + build step.** Split `report_view.js`, tokenize CSS,
   delete dead assets, fix a11y.

---

## 5. Keep vs drop

| Keep | Drop |
|---|---|
| HTTP Reporting-API boundary (no raw SQL in web tier) | SMB SQLite snapshots + JSON sidecar + iterdump salvage |
| Offline mirror concept (as a pure cache) | Triple caching → one cache |
| Thin report registry (`config/reports.py`) | Duplicate report implementations (share with CLI) |
| `data-*` config → page JS, `V2_URL_PREFIX`, IIFE modules (`report_form.js` is the clean example) | `app.js`, `_live_report_form.js`, dead `table_tools.js` |
| Dashboard as precomputed table | Synchronous request-path report runs + 5s stale hack |
| `:root` CSS tokens | 4 modal systems, 3 cadence UIs, hardcoded `#2563eb` |

---

## 6. Positions I will defend (vs the parallel agent)

1. **Move precious data to Postgres.** The SQLite-on-SMB + JSON-sidecar +
   iterdump-salvage stack is not "robust," it is scar tissue from repeated
   corruption. Managed Postgres deletes an entire category of incident.
2. **Do not rewrite the front end in React/Next yet.** The pain is god files and
   no build step, not Jinja. A build step + module split fixes 90% of it at 10%
   of the cost. Reserve a framework migration for when it shares code with the
   sister project.
3. **Kill the second report implementation.** Two copies of commission math is a
   correctness risk, not just a tidiness one. One shared engine, fed by two data
   sources.
4. **Security is Phase 1, not part of the rebuild.** The `dev` auth default + IDOR
   are exploitable today and must be fixed in the current code immediately,
   independent of any rebuild timeline.
