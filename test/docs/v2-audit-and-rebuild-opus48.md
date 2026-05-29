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

---

## 7. Deeper pass — function-level audit of under-covered files

The first audit (§1–6) read the large files in full and characterized the rest.
This pass read the remaining service/blueprint/JS files **function by function**.

### 7.1 Confirmed dead code (delete on rebuild — and ideally now)

| File | Lines | Evidence |
|---|---|---|
| `static/app.js` | 733 | Zero `<script>` references in any template. Report-run + notification logic superseded by `report_view.js` + inline `base.html`. |
| `static/table_tools.js` | ~382 | Zero references; `window.TableTools` unused; `init()` never runs. Its CSS (`.table-toolbar`, `.col-resizer`, ~`style.css:3143+`) is orphaned too. |
| `static/_live_report_form.js` | ~99 | Zero references; replaced by `js/report_form.js`; preset-save lives in `report_view.js`. |
| `services/_archive_mock_data.py.txt` | — | Archived, not imported. |
| `fixtures/ordered_dump.json` | — | Not referenced anywhere in code. |

**Partially dead:** `help_content.js` is loaded globally but **~40+ of its HELP
keys are orphaned** — only ~6 `data-help` hooks exist in templates. Either wire
the help hooks or drop the unused copy.

### 7.2 New security findings (beyond the §2 list)

| # | Issue | Where |
|---|---|---|
| 9 | **SharePoint path traversal** — `_abs_path` / `ensure_folder` / `upload_file` never sanitize `..` in `rel_path`; a crafted schedule path can target folders outside the intended tree. | `services/sharepoint.py:166-169, 208-236, 239-269` |
| 10 | **OAuth token never refreshed** — `_get_token` caches the Graph token process-globally with no expiry handling; once it expires, *all* SharePoint ops fail until the worker restarts. | `services/sharepoint.py:38-39, 52-70` |
| 11 | **SharePoint upload bypasses the user gate in the service layer** — blueprints gate the picker, but `email_outbox.send_report_email` and `schedule_runner.run_schedule` call `upload_file` directly without re-checking `has_sharepoint_access`. | `services/email_outbox.py:96-105`, `services/schedule_runner.py:132-142` |
| 12 | **Notifications dismiss is a silent no-op** on empty/malformed body — returns `{success: true}` having done nothing. | `blueprints/notifications.py:41-52` |

The §2 Customer-Last-Order IDOR is **confirmed and broader** than first thought:
`customers.json` leaks the *entire* customer list, and `view()` performs **three**
separate line-fetches per page load (`fetch_customer_info` → `pick_default_order`
→ `fetch_orders_with_lines`), none access-scoped.

### 7.3 Error-handling & duplication notes

- **Silent degradation**: `customer_last_order.py` swallows all exceptions to `[]`
  or a stub dict (113-114, 142-143, 222-223) — users see "no data" instead of
  "the API failed." `schedule_runner._load_json` swallows JSON parse errors.
- **`run_schedule` "never raises" is not quite true** — an `assert schedule_type`
  (line 57) can still raise under normal (non-`-O`) Python.
- **Confirmed cross-app duplication**: `rollup_lines` and `common_po_prefix` in
  `services/customer_last_order.py:278-334` are copied from the live
  `webapp/blueprints/reports.py` (the docstrings admit it).

---

## 8. Report-engine drift — `test/` vs root `reports/` (correctness risk)

This is the **highest-value pre-rebuild finding**. The two implementations were
written to mirror each other's tab/column contracts, but they pull from
**different data sources** (root = D365 OData + WHS/packing-slip joins; v2 =
flat on-prem SP rows), so the *numbers* can disagree. Literal comparison:

| Report | Structure | Columns | **Math / numbers** | Overall |
|---|---:|---:|---:|---:|
| **ordered** | ~85% | ~70% | **~35%** | **~45%** — highest risk |
| **invoiced** | ~95% | ~95% | ~70% | ~75% |
| **salesman** | ~90% | ~75% | ~85% | ~80% |
| **number_4** | ~90% | ~85% | ~65% | ~70% |
| **customer_activity** | ~95% | ~100% | ~75% | ~80% |

### Critical numeric divergences (will produce different figures)

| Report | Divergence | Root | v2 |
|---|---|---|---|
| **ordered** | Summary **QtyRemainder** | `QtyOrdered - QtyCancelled` (`builder.py:421`) | `+= QtyOpen` (`ordered.py:482`) |
| **ordered** | Summary **Extended Price Remainder** | `QtyRemainder × SalesPrice` (`builder.py:439,445`) | `+= Open $` (`ordered.py:484`) |
| **ordered** | Qty/$ + status engine | WHS + packing-slip joins (`builder.py:359-445`) | SP-derived (`ordered.py:210-215`) |
| **ordered** | Amazon (acct 9300/9301) open→cancelled temp rule | present (`_temp_rules.py:36-76`) | **absent** |
| **ordered** | `ERROR ITEM` line filter | present (`builder.py:229`) | **absent** |
| **invoiced** | **Tariff source** | MarkupTrans classify (`loader.py:27-31`) | `SL_TariffCharges` first (`invoiced.py:271-279`) — v2 comment notes a $700k+ swing |
| **invoiced** | **Credit detection** | `InvoiceNumber` **contains** `CRD\|CM\|FC` (`aggregator.py:35`) | **prefix** `^(CRD\|CM\|FC)` (`invoiced.py:51`) |
| **number_4** | **Book Price** column | present (`loader.py:98-105`) | **omitted** (`number_4.py:16-17`) |
| **number_4** | **Free-text invoice lines** (no SO#) | excluded (`loader.py:65-68`) | **not filtered** → extra rows |
| **salesman** | Group key | 4 cols incl. salesman #/name (`builder.py:44`) | 2 cols `(account, salesman)` (`salesman.py:154`) — can collapse rows |
| **customer_activity** | Last-order grain | order **headers** (`builder.py:55-88`) | order **lines** (`customer_activity.py:134-157`) — tie-breaking differs |

**Implication for the rebuild:** this is the single strongest argument for
**Principle 2 (one shared report engine)**. Maintaining two copies has *already*
let real business rules (tariff source, credit detection, BookPrice, free-text
exclusion, the Amazon temp rule) drift. Top reconciliation checks before trusting
v2 numbers: ordered Summary remainders, invoiced Total Tariff, number_4 row
counts, customer_activity last-order dates, invoiced Credits row count.

---

## 9. Styling conventions — consistency audit + the standard to adopt

**Verdict: partially tokenized, not consistent.** There is a real `:root` token
system (colors, radii, shadows) but it's bypassed constantly, and several parallel
systems coexist.

### Inconsistencies, ranked by prevalence

1. **No spacing/typography scale** — 100+ ad-hoc px values (2/4/6/8/10/12/14/16/18/20/24…) for padding/margin/gap; ~10 distinct font sizes; no `--space-*` or `--text-*` tokens.
2. **~150 inline `style=""` attributes** in templates — `settings.html` alone has **67** (`report_form.html` has 0 — that's the clean baseline).
3. **Inline Feather icon sizing** (`style="width:14px;height:14px"`) duplicated **30+** times across templates + JS; no `.icon-sm/md/lg` utility.
4. **~100 hardcoded hex colors** outside `:root`, including Tailwind grays (`#374151`, `#e5e7eb`) and blue.
5. **Five competing modal systems** (`.modal-overlay/.modal-content`, `.v2-modal-backdrop/.v2-modal`, `.v2-modal-overlay/.v2-modal`, `.modal/.modal-panel`, `.sp-picker-*`) — and `.v2-modal` is defined **twice** with conflicting layout (`style.css:4081` vs `4455`). `.form-row` is also dual-defined (`4483` vs `5023`).
6. **Duplicate toggle/chip patterns** — `.status-btn` vs `.period-btn` vs `.pill` vs `.weekday` vs `.weekday-chip` (two separate weekday UIs).
7. **Four badge/status families** — `.badge`, `.status-*`, `.status-dash-*`, `.data-source-badge` with overlapping semantics.
8. **"Monochrome grays + green, no blue" policy is violated** (`style.css:11-12` comment) — blue appears in `var(--primary, #2563eb)` fallbacks (8 spots), `.status-dash-new`, `.status-running`, commission cards (`5206-5237`), the cache badge, and a hardcoded `#3b82f6` progress bar in `diag.html:115`.
9. **`.muted` class has no global rule** — used in many templates but only defined scoped (`style.css:4805`); most instances rely on duplicated inline `color:var(--text-muted)`.
10. **Nine breakpoint widths** (400/480/540/600/768/**769**/960…) with a 768-vs-769 off-by-one gap; no `--bp-*` tokens.

### The single convention to standardize on

**Tokens** — extend `:root` with:
```css
--space-1:4px; --space-2:8px; --space-3:12px; --space-4:16px; --space-5:20px; --space-6:24px; --space-8:32px;
--text-xs:11px; --text-sm:13px; --text-base:15px; --text-lg:18px; --text-xl:24px;
--bp-sm:480px; --bp-md:768px; --bp-lg:960px;
```
Replace every `var(--x, #hex)` fallback with token-only references.

**One component of each kind:**
- **Modal**: `.modal` + `.modal__backdrop/__panel/__header/__body/__footer` (BEM-ish). Deprecate the other four.
- **Button**: `.btn` + modifiers only; toggle groups → `.btn-toggle.is-active`.
- **Chip**: `.chip` everywhere (weekdays → `.chip--day`).
- **Badge**: `.badge` + `--success|--warning|--error|--info|--neutral`; fold `status-dash-*` into these.
- **Spinner**: `.spinner` + `--sm/--inline` (no inline dimensions).
- **Card**: `.card` + `--stat/--settings` modifiers.

**Utilities (small set):** `.icon-sm/md/lg`, `.hidden`, `.cluster`/`.stack` (flex + gap via `--space-*`), `.text-muted`, `.section-gap`. Then ban inline `style=""` for icon sizing, fl/gap layout, and `display:none` toggles.

**Color policy — make an explicit decision and write it in the CSS header:** either
(A) test sandbox is green-only → convert all intentional blues to green/neutral
semantic tokens, or (B) allow a semantic `--info` blue via token (never raw hex).
Today the comment says one thing and the code does another.

**Baseline to copy:** `templates/report_form.html` (0 inline styles) is the
cleanest template — use it as the pattern for the others.

### Files to touch first (styling)

1. `static/style.css:4081-4520, 2277-2298, 4811-4864` — collapse modals; fix the duplicate `.v2-modal`/`.form-row`.
2. `templates/settings.html` — 67 inline styles.
3. `static/style.css:2340-2430, 5206-5237` — blue fallbacks + commission block.
4. `templates/diag.html:114-115` — hardcoded `#3b82f6`.
5. All templates + `dashboard.js`/`settings.js`/`app.js` — icon + spinner utilities.

---

## 10. Audit coverage statement (for apples-to-apples comparison)

This document reflects: full reads of all large modules; **function-level** reads
of every service/blueprint/static-JS file in `test/`; a **literal business-rule
diff** of all five reports against the root `reports/` package; and a full
**styling-conventions** pass over `style.css` + every template + injecting JS.
Not done: executing code/tests, dynamic analysis, or verifying that any report's
output numbers are *correct* against D365 (only that the two implementations
*diverge*).
