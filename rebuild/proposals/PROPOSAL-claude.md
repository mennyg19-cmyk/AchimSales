# Architecture Proposal — Sales Reports Rebuild

Model: claude-4.6-opus-max-thinking

---

## Proof of Read

- **REBUILD-BRIEF.md** (97 lines): Ground-up rebuild, nothing ported. Core arch: one SP per report → one flat table, all row-level math in SQL, app is presentation-only (group/sort/show-hide/tabs/generic subtotals). Tabs = saved groupings. Scope enforced in SQL. Admin-defined reports (point at SP, configure columns/tabs). Invoiced first. Locked: Azure App Service, Entra, durable jobs, audit log, tests as gate, cutover-ready. Open debates: SQLite+Litestream vs Postgres, grouping location (server vs browser), math-in-SQL pivot, challenge every locked item.
- **FEATURE-INVENTORY.md** (236 lines): 20 pages (P1–P20), 6 page routes + ~35 API endpoints in scope, 7 tabs (5 always + 2 conditional) with 69 named columns. 5 deferred screens noted. To-fix cross-references: FA1–7 (frontend), FB1–8 (reports engine), FC1–10 (platform). 7 items needing human sign-off (B4.3/4/5/7, B4.1/2 known drift, A10.16, A14.6, A1.2/A1.14). Cross-cutting: 4 themes, mobile shell, CSRF everywhere, durable jobs for all work, saved-layout shape, export/view parity.
- **BUILD-HISTORY.md** (50 bugs, BH1–BH50): BH1–8 persistence (SMB→local disk, WAL races, corruption, Litestream); BH9 mirror hammering API; BH10–19 job lifecycle (OOM, cancel, resume, leader election, stuck jobs, diagnostics); BH20–32 frontend/UI (god file, session cookie, viewport, dark mode, deep links, export parity, scope leaks, asset busting); BH33–46 invoiced math (credit detection, commission formula, YTD rounding, multi-customer post-filter, misc charges, salesman master drift); BH47–50 delivery/ops (SharePoint config, scope in scheduled delivery, parity harness, API saturation).
- **Audit files**: A-frontend.inventory (14 screens, 223 control IDs, A1–A16); A-frontend.structure (7 to-fix items FA1–FA7); B-reports-engine.inventory (~31 routes, 7 tabs, 69 columns, B1–B7); B-reports-engine.structure (8 to-fix items FB1–FB8); C-platform.inventory (50 modules/repos, C1–C10); C-platform.structure (10 to-fix items FC1–FC10, SQLite-vs-Postgres trade-off with 5 seam requirements).

---

## 1. Stack

### Backend: Keep Flask (Python)

Flask stays. The problems in the current app are structural (2100-line god file, hardcoded report orchestration, imperative DOM management), not framework problems. Flask is lightweight, the team knows it, and the app has 6 page routes + ~35 API endpoints — well within Flask's sweet spot.

**Why not Django:** The app doesn't use an ORM. Data lives in SQLite (precious/cache) and SQL Server (stored procedures). Django's ORM, admin, and migrations system would be dead weight. The repository pattern already works.

**Why not FastAPI:** Async would be nice in theory, but the app runs a single B1 with synchronous SQLite and an in-process worker. ASGI adds complexity (async SQLite drivers, lifecycle management) for a deployment that doesn't need high concurrency. The heavy work (report runs) already goes through the durable job queue, not request handlers.

**Why not a language change:** Python's ecosystem for Excel generation (openpyxl), MSAL, and Azure integration is mature. The on-prem Reporting API client, delivery services, and MSAL flow all work. Rewriting these in Go/Node/Rust trades known-working integration code for zero user-visible benefit.

### Frontend: Keep Jinja + esbuild TypeScript + Tabulator

The frontend stack stays. The problems are in how the code is organized (FA1: one 2100-line file; FA2: imperative DOM creation; FA6: global mutable state), not in the technology choice.

**Why not React/Vue/Svelte:** The app has 6 in-scope pages. The report viewer is the only complex one, and its complexity is Tabulator (a standalone grid library that manages its own DOM). Wrapping Tabulator in React components adds a reconciliation layer between two DOM-managing systems. The rest of the pages (login, settings, admin, impersonate, reports home) are forms and tables — server-rendered HTML is the right tool.

**What changes:** The 2100-line `report.ts` becomes 10 focused modules under `report/` (see §5). Panels and modals are template-defined HTML toggled by thin controller classes, not imperatively created DOM nodes (fixes FA2). State is encapsulated in module-scoped objects, not global `let` variables (fixes FA6). TypeScript interfaces are strict — no `any` (fixes FA5).

**Tabulator stays** because it does exactly what's needed: sortable, filterable, resizable, groupable data grids with header menus, column freeze, and calc rows. Replacing it with AG Grid or similar is a lateral move.

### Build/Bundling: esbuild (keep)

esbuild stays. It's fast, zero-config for TypeScript, and already produces the JS/CSS bundles. Entry points change from one monolithic `report.ts` to per-page bundles:

| Entry point | Pages | Imports |
|---|---|---|
| `shell.ts` | All authenticated pages | Header, nav, theme, notifications, help, jobs FAB |
| `report/index.ts` | Report viewer | Filters, table, tabs, toolbar, run, export, modals |
| `admin.ts` | Admin users page | User CRUD, salesman grid |

CSS is split from one `pages.css` dumping ground (FA7) into per-concern files: `tokens.css`, `shell.css`, `report.css`, `modals.css`, `admin.css`. All use design tokens — no raw color values, no `!important` Tabulator overrides (theme via Tabulator's CSS variable system).

---

## 2. Persistence: SQLite + Litestream

### Recommendation: Keep SQLite + Litestream. Tighten the Postgres off-ramp seams now.

The app's own data is small: users, jobs, schedules, preferences, audit log — maybe 100KB total. Report data lives on SQL Server. A managed Postgres for this adds network latency (~1-5ms per query), monthly cost (~$15-50 for Azure Flexible Server), connection pooling complexity, and another service to monitor — all for a single-instance B1 serving one company's internal users.

SQLite + Litestream gives:
- Zero network hop (precious.db on local container disk)
- Continuous backup to Azure Blob (Litestream tails WAL)
- Point-in-time recovery
- No connection pooling, no connection limits
- Cheaper than any managed DB

The past SQLite bugs (BH1–BH8) were all caused by hosting it on Azure Files SMB, which breaks WAL coordination. Local disk + Litestream eliminates the root cause. The migration already happened (BH7/BH8).

### Postgres off-ramp seams (implement now, swap later if needed)

These seams cost nothing to add and prevent a full rewrite if the app outgrows a single instance:

**1. Connection protocol.** Repositories depend on a `Connection` protocol (duck-typed), not `sqlite3.Connection` directly. The protocol exposes `execute()`, `fetchone()`, `fetchall()`, `commit()`. Swapping to psycopg2 means implementing the same protocol.

**2. Python UTC everywhere.** All timestamp writes use `datetime.now(timezone.utc).isoformat()` from Python, never `datetime('now')` in SQL. Works on both SQLite and Postgres without change.

**3. JSON as TEXT.** Store JSON as TEXT columns with `json.dumps/loads` in the Python layer. Postgres migration can transparently change to JSONB without code changes.

**4. Abstract `claim_next()`.** The job queue's `claim_next()` method is the one place where SQLite row-locking and Postgres `FOR UPDATE SKIP LOCKED` differ. Isolate this in `JobRepository.claim_next()` so the swap is one method, not scattered SQL.

**5. Migration runner.** `BEGIN IMMEDIATE` (SQLite-specific) is behind a `lock_for_migration()` method. Postgres would use `BEGIN` with appropriate isolation.

### Two-database split (keep)

- **precious.db** — replicated via Litestream. Users, salesmen, jobs, schedules, audit log, preferences, feature flags, report configs. Durable.
- **cache.db** — disposable. Report result cache, export files. Self-heals on missing schema (re-runs cache migrations on open; fixes BH6).

Boot validation hard-fails if either path is on `/home` or any UNC/SMB mount (prevents BH1/BH7).

---

## 3. Grouping Location: Server-Side (Thin Step)

### Recommendation: Server computes all tabs from flat SP data. One grouped dataset feeds screen, export, and email.

This is the single most important structural decision. BH27 proved that when screen grouping and export grouping are separate code paths, they diverge. The fix isn't "be more careful" — it's making divergence structurally impossible.

### How it works

```
SP returns flat rows
        │
        ▼
┌─────────────────────────┐
│   Generic Grouping      │  Server (Python)
│   Engine                │
│                         │
│   For each tab config:  │
│   1. Filter rows        │  "IsCredit = true" for Credits tab
│   2. Group rows         │  GROUP BY columns for Summary tab
│   3. Aggregate          │  SUM money, COUNT DISTINCT, etc.
│   4. Apply column set   │  Ordered column list per tab
│   5. Sort               │  Per-tab sort spec
│                         │
│   Result: per-tab       │
│   row sets + metadata   │
└─────────────┬───────────┘
              │
    ┌─────────┴─────────┐
    │                   │
    ▼                   ▼
  Screen              Export / Email
  (JSON → Tabulator)  (Same data → openpyxl)
```

The grouped dataset is stored in `cache.db` keyed by the cache key (report_key + identity + scope_token + params). Both the screen response and the export job read from the same cache entry. They cannot disagree.

### What the client receives

```json
{
  "tabs": [
    {
      "key": "summary_by_customer",
      "label": "Summary by Customer",
      "layout": "table",
      "columns": [
        {"field": "CustomerAccount", "label": "CustomerAccount", "type": "text"},
        {"field": "InvoiceCount", "label": "InvoiceCount", "type": "int"},
        {"field": "SubTotal Invoices", "label": "SubTotal Invoices", "type": "money"}
      ],
      "rows": [{"CustomerAccount": "ACME001", "InvoiceCount": 12, "SubTotal Invoices": 45230.50}],
      "row_count": 342
    },
    {
      "key": "full_data",
      "label": "Full Details",
      "layout": "table",
      "columns": [...],
      "rows": [...all flat rows with selected columns...],
      "row_count": 5000
    }
  ],
  "total_flat_rows": 5000,
  "generated_at": "2026-06-22T14:30:00Z"
}
```

### What Tabulator still handles (client-side)

Tabulator does all within-tab interactivity on the delivered per-tab data:
- Column sort, reorder, resize, freeze, hide
- Per-column filters (Excel-style popover — A8.1–A8.12)
- "Group by this column" (Tabulator's built-in row grouping within a tab)
- Bottom/group calc rows (subtotals)

These are view operations on a delivered dataset. The server doesn't track column widths or local sort order.

### How export uses the same data

When the user exports:
1. Client sends view state: `{tab_order, duplicated_tabs, per_tab: {hidden, order, sorters, filters}}`
2. Server reads the cached grouped dataset (same as what the screen showed)
3. Applies layout overrides (column visibility, column order, duplicated tabs)
4. Writes Excel workbook with openpyxl (streaming for large sheets)

The export is guaranteed to match the screen because both start from the same grouped data. The only differences are cosmetic (column widths as points, not pixels) and additive (duplicated tabs the user created client-side).

### Memory budget

A typical invoiced run for one period: 5K–50K flat rows × 13 columns ≈ 2–20MB as JSON. All tabs together (Full Details carries the flat data; other tabs are aggregated/filtered subsets) ≈ 3–30MB.

For the pathological case (YTD with 200K rows): ≈ 80–100MB. Manageable on a B1 (1.75GB RAM) with 1–2 concurrent workers. The answer to "too many rows" is better SP filtering, not architectural complexity — that's the whole point of SQL-first.

If lazy tab loading ever becomes necessary, the architecture supports it without changes: serve tab metadata first, fetch individual tab data on switch. But don't build it until you need it.

### Why not browser-only grouping

- **BH27 is structural, not a bug.** When screen grouping (Tabulator JS) and export grouping (Python openpyxl) are separate code paths, they will diverge again. Different edge cases, different aggregation rounding, different null handling. Server-side grouping makes this impossible.
- **Email parity.** Scheduled email attachments run without a browser. If grouping lives in Tabulator, the server must re-implement it anyway for email. Two implementations = two chances to diverge.
- **Big-table memory is the same either way.** The flat data lives in memory whether the server groups it or the browser does. Server-side grouping doesn't add memory — it just runs the tab logic in Python instead of JavaScript.

---

## 4. SQL-First Math Pivot

### What moves to the stored procedure

The invoiced SP (`invoiced_report`) returns one flat table where every row has:

| Column | Source | Notes |
|---|---|---|
| InvoiceNumber | SP | |
| InvoiceDate | SP | ISO date |
| CustomerAccount | SP | |
| CustomerName | SP | |
| SalesOrderNumber | SP | |
| Salesman (SalesGroup) | SP | |
| SalesmanName | SP | Joined from salesman master in SQL |
| SalesmanNumber | SP | BH41: SP returns it |
| SubTotal Invoices | SP | Precomputed |
| Tariff Charges | SP | Precomputed |
| Freight Charges | SP | Precomputed |
| CC Charges | SP | Precomputed |
| Misc Charges | SP | BH39: SP includes it |
| Total Invoice | SP | `= Sub + Tar + Fre + CC + Misc` in SQL |
| IsCredit | SP | SQL column, not regex — fixes BH33 |
| CommissionPct | SP | Fraction (0.06 = 6%), from salesman master in SQL — fixes BH40 |
| CommissionBase | SP | `= Sub + Tar + Misc + Credits` in SQL — fixes BH34/BH44 net formula |
| CommissionAmount | SP | `= CommissionBase × CommissionPct` in SQL |
| InvoiceMonth | SP | `MONTH(InvoiceDate)` — used by commission pivot |

**What the app no longer computes:**
- Credit detection (was regex on invoice number — BH33)
- Net/total columns (was `subtotal + tariff + freight + cc + misc` — moved to SQL)
- Commission rate resolution (was SP-rate-vs-master-fallback — BH40; now single source in SQL)
- Commission base and amount (was Python math — FB1)
- Salesman name enrichment (was Python join against Azure master — BH41)

### What stays in the app

**Generic operations only:**
- Subtotals: SUM of money/int columns across rows in a group. Same logic for every report.
- COUNT(DISTINCT field) for InvoiceCount in summary tabs.
- Percentage columns stay blank in subtotal rows (A7.10).
- Commission monthly pivot (one registered transform — see below).

### The commission monthly pivot

The commissions tab is the one tab that needs custom logic beyond "filter + group + sum." It's a monthly pivot: for each salesman, for each month in the YTD window, accumulate net commission and compute YTD total.

This is handled as a **named transform** registered in the tab config:

```
report_tabs row for "commissions":
  transform = "commission_monthly_pivot"
  layout = "commission_cards"
```

The transform function lives in `reports/transforms/commission_pivot.py` — a small, isolated module (~100 lines). It takes flat rows + year + end_month and produces the pivot structure (per-salesman, per-month slots, YTD totals). It uses the precomputed `CommissionAmount` and `CommissionBase` from SQL — no rate lookup, no net formula, just accumulation and rounding.

Every other tab uses pure generic grouping. No custom Python math.

### Eliminating the double fetch (BH38)

The current app makes two SP calls: one for the selected period, one for Jan 1 → period end (YTD data for commissions). The new SP should support both in one call:

**Option A (preferred):** The SP accepts `InvoiceDateFrom`, `InvoiceDateTo`, and `YTDFromDate` parameters. It returns one result set with all rows from `YTDFromDate` to `InvoiceDateTo`. The app filters in the generic engine: period tabs see rows within `InvoiceDateFrom..InvoiceDateTo`; the commission pivot sees all rows (YTD window). One SP call.

**Option B:** The SP returns two result sets in one call (period rows + YTD rows). The adapter reads both. Still one round-trip.

Either way, the double-fetch is gone (BH38).

### Multi-customer filter (BH37)

The current app accepts multiple customers in the UI but only pushes one to the SP, silently post-filtering the rest in Python. The new SP accepts a table-valued parameter or `WHERE CustomerAccount IN (...)` clause. The app passes the full customer list. No silent post-filter, no data leak.

### Admin-defined report config model

The report registry moves from a static Python dict (FB5) to DB tables, seeded for invoiced. The admin editor UI is deferred, but the schema exists from day one:

```sql
CREATE TABLE report_configs (
    key TEXT PRIMARY KEY,           -- "invoiced"
    title TEXT NOT NULL,            -- "Invoiced"
    stored_procedure TEXT NOT NULL, -- "invoiced_report"
    scope_param TEXT,               -- "Salesman" (SP param name for scope)
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE report_filters (
    id INTEGER PRIMARY KEY,
    report_key TEXT NOT NULL REFERENCES report_configs(key),
    param_name TEXT NOT NULL,       -- "period", "salesman", "customers"
    param_type TEXT NOT NULL,       -- "date_range", "lookup", "multi_lookup"
    sp_param_mapping TEXT,          -- JSON: how filter maps to SP params
    display_order INTEGER NOT NULL,
    UNIQUE(report_key, param_name)
);

CREATE TABLE report_columns (
    id INTEGER PRIMARY KEY,
    report_key TEXT NOT NULL REFERENCES report_configs(key),
    field_name TEXT NOT NULL,       -- SP column name
    label TEXT NOT NULL,            -- Display label
    col_type TEXT NOT NULL,         -- money, int, percent, date, text
    default_order INTEGER NOT NULL,
    default_visible INTEGER NOT NULL DEFAULT 1,
    UNIQUE(report_key, field_name)
);

CREATE TABLE report_tabs (
    id INTEGER PRIMARY KEY,
    report_key TEXT NOT NULL REFERENCES report_configs(key),
    tab_key TEXT NOT NULL,          -- "summary_by_customer"
    label TEXT NOT NULL,            -- "Summary by Customer"
    tab_order INTEGER NOT NULL,
    layout TEXT NOT NULL DEFAULT 'table',  -- "table" or "commission_cards"
    group_by TEXT,                  -- JSON: ["CustomerAccount", "CustomerName", ...]
    filter_expr TEXT,              -- "IsCredit = true" or null
    columns TEXT,                   -- JSON: ordered field_name list for this tab
    aggregations TEXT,              -- JSON: {"InvoiceCount": "count_distinct:InvoiceNumber", ...}
    sort_by TEXT,                   -- JSON: [{"field": "CustomerAccount", "dir": "asc"}]
    transform TEXT,                -- "commission_monthly_pivot" or null
    conditional TEXT,              -- "has_multiple_salesmen" or null
    UNIQUE(report_key, tab_key)
);
```

Invoiced's 7 tabs are seeded at boot (P20). Adding a new report = INSERT rows in these tables, not a code deploy. The generic grouping engine reads these configs and produces the tabs.

**Custom transforms** are registered in a small lookup:

```python
TRANSFORMS = {
    "commission_monthly_pivot": commission_pivot.transform,
}
```

Most reports need none. This keeps the "escape hatch" small and named rather than letting every report have arbitrary Python.

**Conditional tabs** are registered similarly:

```python
CONDITIONS = {
    "has_multiple_salesmen": lambda rows: len({r["Salesman"] for r in rows if r.get("Salesman")}) >= 2,
    "has_reversals": lambda rows: _detect_reversals(rows),
}
```

The tab is included only when the condition function returns True against the flat data.

---

## 5. Module/File Structure

```
v3/
├── app.py                          # create_app(), CSRF init, fast return
├── config.py                       # Config dataclass, env-driven, fail-closed
├── wsgi.py                         # DispatcherMiddleware, daemon thread bootstrap
│
├── auth/
│   ├── msal.py                     # Entra login flow (build_login_url, complete_login)
│   ├── session.py                  # Session principal storage (unique cookie name)
│   ├── principal.py                # Immutable Principal value object
│   ├── authorization.py            # Central authz: assert_report_runnable, visible_salesman_keys,
│   │                               #   can_view_report, authorize_delivery — single source
│   └── decorators.py               # @require_login, @require_privileged
│
├── blueprints/
│   ├── auth_routes.py              # Login/logout/callback/impersonate
│   ├── report_routes.py            # Report viewer page + report APIs (run/result/active)
│   ├── export_routes.py            # Export + download + list exports
│   ├── lookup_routes.py            # Salesmen/customers/years/status lookups
│   ├── preset_routes.py            # Saved views CRUD
│   ├── delivery_routes.py          # Email-now, schedules, SharePoint status/folders
│   ├── admin_routes.py             # User/salesman/access CRUD, feature flags
│   ├── settings_routes.py          # Theme/preferences
│   └── health_routes.py            # /healthz, diagnostics, admin repair
│
├── reports/
│   ├── engine.py                   # Generic grouping engine: filter + group + aggregate + sort
│   │                               #   Reads tab configs from DB. One function: compute_tabs(flat_rows, tab_configs)
│   ├── transforms/
│   │   ├── __init__.py             # TRANSFORMS registry (name → function)
│   │   └── commission_pivot.py     # Monthly commission pivot (~100 lines)
│   ├── conditions.py               # CONDITIONS registry (name → predicate)
│   ├── adapter.py                  # SP row → flat dict (field rename/normalize ONLY — FB4)
│   ├── runner.py                   # Run report: SP call → adapter → engine → cache
│   ├── export_writer.py            # Grouped dataset → Excel (streaming openpyxl)
│   ├── cache.py                    # Cache key builder + payload read/write on cache.db
│   ├── config_loader.py            # Load report_configs/tabs/columns/filters from precious.db
│   └── params.py                   # Filter → SP parameter mapping (config-driven, not hardcoded)
│
├── jobs/
│   ├── worker.py                   # Durable worker: env-driven threads (FC1), per-job timeout (FC4),
│   │                               #   capped orphan recovery (BH10), cooperative cancel (BH12)
│   ├── leader.py                   # flock-based leader election (BH17), V3_FORCE_LEADER fallback (FC5)
│   ├── scheduler.py                # APScheduler wrapper, single leader only
│   └── types.py                    # Job type → handler registry
│
├── delivery/
│   ├── email.py                    # EmailService (SMTP/outbox)
│   ├── sharepoint.py               # SharePointService (Graph API, config validated at boot — BH47)
│   ├── service.py                  # DeliveryService: run_and_deliver with principal+scope snapshot (BH48)
│   └── scheduling.py               # ScheduleRunner + cadence parsing + tick enqueue
│
├── data/
│   ├── connection.py               # Database class: precious()/cache() with Connection protocol (FC6)
│   │                               #   Python UTC (never datetime('now')), WAL only, no journal knob (BH2)
│   ├── migrate.py                  # Versioned migrations, BEGIN IMMEDIATE behind lock_for_migration()
│   │                               #   Leader-gated (BH4), skip-if-applied
│   └── repositories/
│       ├── jobs.py                 # Enqueue (with backpressure — FC2), claim_next (abstract — FC6),
│       │                           #   dedup, capped recovery
│       ├── users.py                # User CRUD + directory mirror (BH22)
│       ├── report_configs.py       # report_configs, report_tabs, report_columns, report_filters
│       ├── salesmen.py             # Salesman master
│       ├── exports.py              # Export files + retention
│       ├── schedules.py            # Schedules + master schedules + runs
│       ├── run_log.py              # Audit/incident log (BH50)
│       ├── preferences.py          # User preferences (theme, etc.)
│       ├── presets.py              # Saved views (presets)
│       └── feature_flags.py        # Feature flags
│
├── static_src/
│   ├── ts/
│   │   ├── shell.ts                # App shell: header, nav, theme toggle, notification badges,
│   │   │                           #   help overlay, double-click/nav guards, pull-to-refresh
│   │   ├── jobs-fab.ts             # Floating jobs FAB + panel, shared poll module (BH15)
│   │   ├── report/
│   │   │   ├── index.ts            # Report page controller — orchestrates modules, no logic of its own
│   │   │   ├── filters.ts          # Filter controls, deep links, lookups, init pipeline (BH25)
│   │   │   ├── table.ts            # Tabulator wrapper: build, column formats, view state capture (FA4)
│   │   │   ├── tabs.ts             # Tab bar, context menu, duplicate/delete, tab switch
│   │   │   ├── column-filter.ts    # Per-column filter popover (A8.1–A8.12)
│   │   │   ├── toolbar.ts          # Toolbar buttons, columns panel, reset view
│   │   │   ├── export.ts           # Export trigger + recent exports panel + auto-download
│   │   │   ├── run.ts              # Run/poll/resume/cancel state machine (BH14 transient vs terminal)
│   │   │   └── types.ts            # Strict interfaces: ViewState, TabConfig, ReportPayload, etc. (FA5)
│   │   ├── modals/
│   │   │   ├── email.ts            # Email modal controller
│   │   │   ├── schedule.ts         # Schedule modal controller
│   │   │   └── sharepoint-picker.ts # Reusable SP folder browser component (FA3 — one module, two instances)
│   │   └── admin.ts                # Admin users + salesman management
│   ├── css/
│   │   ├── tokens.css              # Design tokens (4 themes: light, dark, mono, mono-dark) — BH24
│   │   ├── shell.css               # Shell layout (header, bottom nav, FAB, safe-area) — BH23
│   │   ├── report.css              # Report viewer, Tabulator theming via CSS vars (not !important)
│   │   ├── modals.css              # All modals (email, schedule, help)
│   │   └── admin.css               # Admin pages
│   └── esbuild.config.js           # Entry points: shell, report/index, admin
│
├── templates/
│   ├── base.html                   # Shell template (unique SESSION_COOKIE_NAME — BH21)
│   ├── login.html                  # Entra + dev login
│   ├── reports_list.html           # Report cards + preset cards
│   ├── report_view.html            # Filter form + toolbar + tab bar + table + modals (all in template)
│   ├── settings.html               # Profile, theme, admin links, feature flags
│   ├── admin_users.html            # User table, salesman table, edit modals
│   └── impersonate.html            # Role-grouped user picker
│
└── tests/
    ├── test_parity.py              # LIVE parity scaffold (BH49) — retires after SQL cutover
    ├── test_authz.py               # Per-role scope tests (BH28/BH29/BH48)
    ├── test_jobs.py                # Enqueue → claim → complete lifecycle (BH16)
    ├── test_grouping_engine.py     # Tab configs → correct grouped output
    ├── test_export_parity.py       # Export output matches screen tab data (BH27)
    ├── test_migrations.py          # Migrate on fresh + already-applied (BH4)
    ├── test_boot_safety.py         # Refuse dev auth in prod, refuse default secret, refuse SMB (BH5/BH7)
    ├── test_cache_healing.py       # Missing schema → self-heal (BH6)
    └── test_csrf.py                # CSRF on all state-changing routes (FC7)
```

### How this structure fixes each to-fix item

| ID | Problem | Fix |
|---|---|---|
| **FA1** | `report.ts` god file (2100 lines) | Split into 8 modules under `report/` + shared `types.ts` |
| **FA2** | Panels built imperatively in JS | All panels/modals defined in `report_view.html` template, toggled by controller classes |
| **FA3** | Duplicate SharePoint picker | Single `sharepoint-picker.ts` module, instantiated once per modal |
| **FA4** | Full Tabulator teardown per tab switch | `table.ts` uses `setData()` + `setColumns()` when possible; full rebuild only when layout type changes (table ↔ cards) |
| **FA5** | `any` everywhere in TypeScript | `types.ts` defines strict interfaces for ViewState, TabConfig, ReportPayload, ColumnDef; Tabulator typed via community definitions |
| **FA6** | Global mutable state | State encapsulated in module-scoped controller objects; each module exports functions that accept/return typed state |
| **FA7** | `pages.css` dumping ground | Split into `report.css`, `modals.css`, `admin.css`; Tabulator themed via CSS variables |
| **FB1** | Row-level math in Python | All math in SP; app does generic subtotals only |
| **FB2** | Hardcoded tabs/columns/aggregations | Manifest-driven via `report_tabs` DB table; generic grouping engine |
| **FB3** | Per-report hardcoded orchestration | Config-driven: `config_loader.py` reads DB, `runner.py` is generic |
| **FB4** | Adapter does too much | `adapter.py` = field rename + type normalize only; no credit detection, no total computation |
| **FB5** | Static code-driven registry | `report_configs` DB table; admin CRUD deferred but schema ready |
| **FB6** | UI coupled to per-tab payload shape | Payload = per-tab rows from generic engine; all tabs share the same structure |
| **FB7** | God files in engine + blueprint | Engine split (engine.py + transforms/ + adapter); blueprint split into 8 route files |
| **FB8** | Deferred reports wired in | `status` field in `report_configs`: active/disabled/backlog; only active reports are runnable |
| **FC1** | Worker threads hardcoded to 2 | `JOB_WORKER_THREADS` env var, default 1 for B1 |
| **FC2** | No queue backpressure | `JobRepository.enqueue()` checks queue depth; returns 503/Retry-After when full |
| **FC3** | Time-based asset version | Content hash of `static_dist/` directory at boot time |
| **FC4** | No per-job timeout | `MAX_JOB_DURATION_SECONDS` env var; `Future.result(timeout=...)` in worker |
| **FC5** | Leader fallback too permissive | Log loud warning; `V3_FORCE_LEADER` env override for test control |
| **FC6** | No Postgres off-ramp seams | Connection protocol, Python UTC, abstract claim_next, lock_for_migration |
| **FC7** | CSRF exempt list may be incomplete | Explicit exempt set (healthz + callback only); CSRF audit as test |
| **FC8** | Litestream binary not in deploy | Document Azure startup command; `startup.sh` downloads Litestream binary |
| **FC9** | No memory limits | `resource` module limits (Linux); SP filtering keeps rows bounded |
| **FC10** | DispatcherMiddleware path risks | `SCRIPT_NAME` verified; integration test for `/test/auth/callback` |

---

## 6. Information Architecture / UI Structure

### Navigation

**Header (sticky top):**
- Logo text "Sales Reports" → link to `/`
- User name + role badge
- Theme toggle (cycles 4 themes)
- Sign out

**Bottom nav (fixed):**
- Reports (active on `/` and `/reports/*`)
- Schedules (links to `/schedules`; stub until deferred page ships)
- Settings (links to `/settings`)

Dashboard nav item is removed (deferred, owner says unused). Test Site link is deployment scaffolding — removed from nav, kept as an admin diagnostic link in Settings if needed.

**Floating Jobs FAB (bottom-right, above bottom nav):**
- Polls `/api/reports/active` every 5 seconds
- Hidden when no active or recently finished jobs
- States: running (spinner), failed (error color), ready (success color)
- Click opens jobs panel; job rows link to their report page
- Shared poll module between FAB and report status bar (BH15)

### Report viewer layout

The current UI is a "stack of cards" where panels were bolted on. The rebuild organizes the report viewer into clear zones:

```
┌──────────────────────────────────────────────────────┐
│  ← Reports          Invoiced Report          [?]     │ HEADER STRIP
├──────────────────────────────────────────────────────┤
│  ▼ Filters & options       [summary when collapsed]  │ FILTER DRAWER
│  ┌─────────────────────────────────────────────────┐ │ (collapsible)
│  │ Period [▼]   Salesman [▼]   Customer [search▼]  │ │
│  │                                 [Run Report]    │ │
│  └─────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────┤
│  ⟳ Refresh │ Columns │ Reset │ Export │ Email │      │ TOOLBAR
│  Schedule │ Save view │ Presets │ Recent exports     │ (single row)
├──────────────────────────────────────────────────────┤
│  Building report... 45% (0:23)              Cancel   │ STATUS BAR
│                                                      │ (hidden when idle)
├──────────────────────────────────────────────────────┤
│  [Summary ▾] [Commissions ▾] [Full Details ▾] ...   │ TAB BAR
│  1,234 rows · as of 2:30 PM                         │ (meta below tabs)
├──────────────────────────────────────────────────────┤
│                                                      │
│                                                      │
│                 Tabulator grid                       │ TABLE AREA
│              (viewport-fit height)                   │ (fills remaining
│          or commission cards layout                  │  viewport)
│                                                      │
│                                                      │
├──────────────────────────────────────────────────────┤
│       [Reports]    [Schedules]    [Settings]         │ BOTTOM NAV
└──────────────────────────────────────────────────────┘
```

### How panels and modals work

**Side panels** (columns, presets, recent exports) are `<aside>` elements in the template, positioned relative to their trigger button. Toggled via a shared `PanelController` class that handles:
- Toggle on button click
- Close on outside click (after the opening click has passed)
- Close on Escape
- Only one panel open at a time

No imperative DOM creation. No global let variables tracking panel state (fixes FA2/FA6).

**Modals** (email, schedule) are `<dialog>` elements in the template (native HTML dialog for free `role="dialog"`, `aria-modal`, backdrop click, Escape). Each has a thin controller class in its own module (`email.ts`, `schedule.ts`) that handles form state, validation, and the delivery job poll.

**SharePoint picker** is a self-contained module (`sharepoint-picker.ts`) that takes a container element and emits events. Instantiated once inside each modal — no DOM ID soup, no duplicate logic (fixes FA3).

**Column filter popover** is a positioned `<div>` in the template, repositioned to the active column header on open. One popover element shared across all columns, content swapped on open (operator options + value input based on column type). Fixes the current approach of creating/removing DOM nodes per column.

**Tab context menu** is a single `<menu>` element in the template, positioned at click coordinates. Options (Duplicate, Delete) enabled/disabled based on tab state.

### Per-page structure (all 20 inventory pages)

| Page | Route | Layout | Notes |
|---|---|---|---|
| **P1 Shell** | All authenticated | `base.html` | Header + bottom nav + FAB + help overlay |
| **P2 Login** | `/login` | Centered card | Entra redirect or dev form (dev form only if `AUTH_MODE=dev`) |
| **P3 Reports Home** | `/` | Card grid | Built report cards, preset cards, coming-soon (disabled), empty state |
| **P4–P8 Report Viewer** | `/reports/<key>` | Report layout (above) | Filter drawer + toolbar + status + tabs + table + panels + modals |
| **P9 Email Modal** | (on report viewer) | `<dialog>` | Recipients, subject, message, SharePoint picker, send → poll |
| **P10 Schedule Modal** | (on report viewer) | `<dialog>` | Cadence, recipients, SharePoint picker, save |
| **P11 Settings** | `/settings` | Card stack | Profile (read-only), theme select, admin links, feature flags |
| **P12 Admin Users** | `/admin/users` | Two tables + modals | User table + salesman table; edit user modal with scope grid |
| **P13 Impersonate** | `/impersonate` | Centered card | Role-grouped user buttons, admin/dev only |
| **P14 Invoiced Data** | (engine, not a page) | — | 7 tabs seeded in DB, generic engine produces them |
| **P15 Auth/Scope** | (middleware + service) | — | Central `authorization.py`, fail-closed |
| **P16 Durable Jobs** | (background) | — | Worker + leader + scheduler |
| **P17 Persistence** | (infrastructure) | — | precious.db + cache.db + migrations |
| **P18 Delivery** | (background) | — | Email + SharePoint + scheduling |
| **P19 Audit Log** | (repository) | — | Run log written by all job handlers |
| **P20 Config/Boot** | (startup) | — | Fail-closed validation + seed report config |

### Responsive behavior

- Below 600px: filter row wraps, Run button goes full-width (A16.3)
- Table uses natural horizontal scroll inside `.report-table-scroll` — page never grows horizontally (A16.4)
- Bottom nav respects safe-area inset (A16.2)
- Table height = viewport bottom - table top - bottom nav height, minimum 220px (A4.7)
- `[hidden]` attribute is reliable: no CSS display rules that override it (A16.5; BH13)

### Accessibility

- Modals use `<dialog>` (native `role="dialog"`, `aria-modal`, focus trap)
- Filter drawer uses `aria-expanded`, `aria-controls`
- Customer search uses `role="combobox"` with `aria-autocomplete`
- Theme toggle and help buttons have accessible labels
- All interactive elements keyboard-navigable
- Tab bar uses appropriate ARIA tab roles

---

## 7. Build History Prevention Matrix

Every BH item mapped to the architectural decision that prevents it:

| BH | Bug | Prevention |
|---|---|---|
| BH1 | Jobs stuck — SQLite on SMB | Local disk only; boot refuses `/home`/UNC (config.py) |
| BH2 | TRUNCATE journal mode crash | No journal-mode knob; WAL is the only mode |
| BH3 | DB corruption | Integrity check in admin diagnostics; Litestream from healthy source |
| BH4 | Migration race between workers | Leader-gated migrate + `BEGIN IMMEDIATE` + skip-if-applied |
| BH5 | Cold start crash loop | `create_app()` returns fast; heavy init in daemon thread |
| BH6 | Cache "no such table" | Cache self-heals: re-runs migrations on open |
| BH7 | DB path defaulted to SMB | Hard-fail if path is `/home` or UNC |
| BH8 | Container recycle wiped /tmp | Cold boot restores from Litestream; integration test for empty-disk restore |
| BH9 | Mirror refresh hammered API | No mirror stacks; dashboard refresh behind feature flag, default off |
| BH10 | OOM on huge row set | Capped orphan recovery (1 retry); SP filters rows; memory budget tests |
| BH11 | 5-min timeout on large pulls | Month-chunk fetch for any multi-month pulls; target: one SP per report |
| BH12 | Cancel can't stop running job | Cooperative cancel (poll flag between chunks) + honest UI text |
| BH13 | Cancel button stayed visible | Single visibility pattern (`hidden` class); no conflicting display rules |
| BH14 | False "lost track of job" | Transient vs terminal error handling; retry with backoff, keep job ID |
| BH15 | Timer reset on page return | Resume via `/api/reports/active` + true elapsed; shared poll module |
| BH16 | No visibility into worker state | Admin diagnostics: heartbeat, last claim, queue depth, API reachability |
| BH17 | Multiple scheduler instances | flock-based single leader for scheduler/email/worker |
| BH18 | Stuck job blocked queue | Per-job timeout (`MAX_JOB_DURATION_SECONDS`); separate log for API call duration |
| BH19 | Emergency repair endpoints | First-class admin repair: integrity check, backup, jobs rebuild — built in |
| BH20 | `report.ts` god file | 8 modules under `report/` by concern |
| BH21 | Session cookie collision | Unique `SESSION_COOKIE_NAME` per mounted app |
| BH22 | Real users land as no-access | Mirror user directory on boot; env admins override |
| BH23 | Table doesn't fit viewport | Viewport-fit table from day one; responsive shell tokens |
| BH24 | Dark mode invisible elements | All chrome uses design tokens; dark mode in expectation checklist |
| BH25 | Deep link init order wrong | Defined init pipeline: lookups → URL params → bind controls |
| BH26 | Export blocks browser | Background export job + streaming writer |
| BH27 | Export doesn't match screen | Server-side grouping: one dataset feeds both |
| BH28 | Revoked user reads cached result | Every result/export fetch re-checks authz + scope |
| BH29 | Wrong salesman scope | Single `assert_report_runnable` used by run/result/export/email |
| BH30 | Lookups return wrong key shape | Lookups return exact SP parameter values; display names separate |
| BH31 | No asset cache busting | Content hash `?v=` on all static assets |
| BH32 | Impersonation fields dropped | Principal is immutable value object with full round-trip tests |
| BH33 | Credit detected by regex | `IsCredit` is a SQL column from SP |
| BH34 | Totals by Salesman included credits wrong | SQL returns precomputed net columns; generic SUM in grouping engine |
| BH35 | Commission YTD off by pennies | SQL returns unrounded CommissionAmount; display rounding only in formatter |
| BH36 | Prior-year rows in commission pivot | Explicit year parameter to SP; commission pivot respects YTD window |
| BH37 | Multi-customer silently post-filtered | SP accepts customer list (table-valued or IN clause); no post-filter |
| BH38 | Double YTD fetch | Single SP call with YTD window support (Option A or B in §4) |
| BH39 | Misc Charges column missing | SP includes all money columns; manifest declares columns from SP metadata |
| BH40 | Commission rate source drift | Single source: salesman master on SQL Server, joined in SP |
| BH41 | SalesmanNumber column removed | SP returns SalesmanNumber, SalesmanName, SalesGroup |
| BH42 | Invoice count over-counted | Generic `count_distinct:InvoiceNumber` in grouping engine config |
| BH43 | Bad dates cause 500 | Filter validation returns user-visible error, not unhandled exception |
| BH44 | SP migration carried legacy aliases | Versioned manifest per report SP; adapter deleted when only one contract exists |
| BH45 | Commissions special-cased for export | Commissions = tab definition over flat table; same grouping engine as other tabs |
| BH46 | YTD window anchored to wrong year | Commission date window = explicit SP parameter derived from period end |
| BH47 | SharePoint delivery failed silently | Config validated at boot; errors surface setting name + Graph status |
| BH48 | Delivery leaked other reps' rows | Delivery jobs carry principal + scope snapshot; builder uses same scope params |
| BH49 | Parity harness caught drift | Temporary LIVE parity scaffold; retires after SQL cutover |
| BH50 | Diagnostic probes saturated API | Admin-only short-timeout probe; never stack on prod traffic |

---

## 8. Cutover Readiness

The rebuild is cutover-ready by design. Flipping `/test` → `/` is routing + config:

1. `wsgi.py` DispatcherMiddleware: change v3 from `/test` mount to `/` mount
2. Move old test app to `/test-legacy`
3. Update `SCRIPT_NAME` and session cookie path
4. Update Entra redirect URIs (add `/auth/callback`, keep `/test/auth/callback` during transition)
5. Feature flags: disable any `/test`-only scaffolding

No code rewrite. No database migration. Same Entra login, same URL conventions. The LIVE parity harness (BH49) proves v3 matches LIVE before cutover; after cutover, it retires and SQL is the source of truth.

---

## 9. Request/Response Flow (End to End)

### Running a report

```
User clicks "Run Report"
  → Client: POST /api/reports/invoiced/run {period: "last_month", salesman: "GRP01"}
  → Server:
      1. @require_login → principal
      2. Authorization.assert_report_runnable(principal, "invoiced")
      3. config_loader.load("invoiced") → report config from DB
      4. params.translate(config, user_params) → SP params using config.sp_param_mapping
      5. jobs.enqueue("report.run", {report_key, identity, scope_token, sp_params})
         └── dedup: same cache key → reuse existing queued job
      6. Return 202 {job_id}
  → Client: poll GET /api/jobs/<job_id> every 1s
  → Worker picks up job:
      1. SP call via Reporting API → flat rows
      2. adapter.normalize(rows) → standardized column names
      3. engine.compute_tabs(flat_rows, tab_configs) → per-tab row sets
      4. cache.store(cache_key, result) → cache.db
      5. Job → success, result_ref = cache_key
  → Client: GET /api/reports/result/<job_id>
      1. Re-check authz + scope compatibility (BH28)
      2. Read from cache.db
      3. Return JSON {tabs: [...], generated_at, total_flat_rows}
  → Client: render active tab in Tabulator
```

### Exporting

```
User clicks "Export"
  → Client: POST /api/reports/invoiced/export/<job_id> {layout: {tab_order, per_tab: {hidden, order, ...}}}
  → Server:
      1. Re-check authz + scope (BH28)
      2. Enqueue export job
      3. Return 202 {export_id}
  → Worker:
      1. Read cached grouped result (same data screen showed)
      2. Apply layout overrides (column visibility, order, duplicated tabs)
      3. Write Excel via streaming openpyxl → exports table
  → Client: poll → auto-download when ready
```

### Scheduled email delivery

```
Scheduler tick fires
  → ScheduleRunner:
      1. Load schedule from precious.db
      2. Re-resolve owner principal + scope via authorize_delivery (BH48)
      3. Translate schedule params → SP params
      4. Run report (same path as interactive: SP → adapter → engine → cache)
      5. Export to Excel from cached result
      6. Send via EmailService and/or save to SharePoint
      7. Record in schedule_runs + run_log
```

---

## 10. Test Strategy (Ship Gate)

Tests required before shipping (from non-negotiables + BH prevention):

| Test area | What it proves | Key BH/FC |
|---|---|---|
| **Report parity** | v3 output matches LIVE export for invoiced | BH49 |
| **Authz/scope** | Admin sees all, manager sees their salesmen, salesman sees only their own; revoked user blocked | BH28, BH29, BH48 |
| **Job lifecycle** | Enqueue → claim → progress → complete; dedup; cancel; orphan recovery (capped) | BH10, BH12, BH16 |
| **Grouping engine** | Tab configs → correct filtered/grouped/aggregated output; subtotals skip percent columns | BH27, BH34 |
| **Export parity** | Export output matches screen tab data exactly | BH27 |
| **Cache self-heal** | Missing cache.db schema → auto-recover | BH6 |
| **Boot safety** | Refuse dev auth in prod; refuse default secret; refuse SMB/UNC paths; refuse missing Litestream | BH5, BH7 |
| **Migrations** | Apply on fresh; skip-if-applied; leader gate | BH4 |
| **CSRF** | Every POST/PUT/PATCH/DELETE route requires valid token | FC7 |
| **Memory budget** | Max expected row count completes without OOM | BH10, FC9 |
