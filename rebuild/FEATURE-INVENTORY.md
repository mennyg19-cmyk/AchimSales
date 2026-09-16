# Feature Inventory — Sales Reports rebuild (invoiced-first)

The complete truth of what the in-scope app does today, cross-referenced from
the Phase 0 audits. This is the master index + route manifest + to-fix +
sign-off list. The per-control DETAIL lives in the committed audit files; this
file ties them together and is what the build todos come from.

Audit sources (read these for detail):
- `rebuild/rebuild-audit/A-frontend.inventory.md` — 14 screens, 223 control IDs (A1–A16)
- `rebuild/rebuild-audit/B-reports-engine.inventory.md` — ~31 routes, 7 tabs, 69 columns (B1–B7)
- `rebuild/rebuild-audit/C-platform.inventory.md` — 42 platform IDs (C1–C10)
- `rebuild/rebuild-audit/*.structure.md` — to-fix lists FA1–7, FB1–8, FC1–10
- `rebuild/BUILD-HISTORY.md` — 50 past bugs/pain points (BH1–50), each with a prevention step

Frame (non-negotiable): old app = **WHAT, not HOW**. Not a port, not a pixel
copy. Every in-scope feature below is preserved; the structure is rebuilt clean.

---

## 1. Route manifest

The rebuild isn't done until every IN-SCOPE route has a working counterpart.

### IN SCOPE — pages
| Route | Page | Old file |
|---|---|---|
| `GET /login` (+ `/login/dev`, `/auth/callback`) | Login (Entra + dev) | `blueprints/auth.py`, `templates/login.html` |
| `GET /` | Reports home | `blueprints/reports.py`, `templates/reports_list.html` |
| `GET /reports/<key>` | Report viewer (invoiced) | `blueprints/reports.py`, `templates/report_view.html`, `static_src/js/report.ts` |
| `GET /settings` (+ `POST /settings/theme`) | Settings | `blueprints/settings.py`, `templates/settings.html` |
| `GET /admin/users` | Admin users & access | `blueprints/admin.py`, `templates/admin_users.html` |
| `GET /impersonate` (+ POST, `/impersonate/end`) | Impersonate | `blueprints/auth.py`, `templates/impersonate.html` |

### IN SCOPE — APIs (back the screens above)
Run/status/result: `POST /api/reports/<key>/run`, `GET /api/jobs/<id>`,
`POST /api/jobs/<id>/cancel`, `GET /api/reports/result/<id>`,
`GET /api/reports/active`. Export: `POST /api/reports/<key>/export/<job_id>`,
`GET /api/reports/exports/<id>/download`, `GET /api/reports/exports`.
Lookups: `/api/reports/<key>/salesmen|customers|years`, `/api/reports/lookups/status`.
Presets/views: `GET/POST /api/reports/<key>/presets`, `GET/DELETE /api/reports/presets/<id>`, `GET /api/saved-reports`.
Delivery: `POST /api/reports/<key>/email-now`, `POST /api/schedules`,
`GET /api/sharepoint/status`, `GET /api/sharepoint/folders`.
Settings/admin: `POST /api/settings/preferences`, `POST /api/admin/feature-flags`,
`/api/admin/users*`, `/api/admin/users/<id>/salesman-access`,
`/api/admin/users/<id>/report-access`, `PUT /api/admin/salesmen/<key>`.
Notifications: `GET /api/notifications`.
Dev/admin diagnostics: `preview-body`, `diagnostics/reporting-api`,
`diagnostics/claim-once`, `diagnostics/precious-repair` (developer-only).

### DEFERRED — keep on inventory, not first cut
Dashboard (page + `/api/notifications` dashboard fields + refresh) — owner says unused.
Customer's Last Order (`/report/customer-last-order*` page + sub-API).
Schedules list page (`/schedules`), Master schedules (`/master-schedules`),
Report run-log page (`/admin/run-log`). Other reports: ordered, salesman,
number_4, customer_activity (BUILT today, but wait on their flat-table SPs).
Backlog: customer_aging.

---

## 2. Pages → build todos (each becomes ≥1 granular todo in REBUILD-PLAN)

Every page lists the audit IDs it must preserve, the to-fix items that touch it,
and the BUILD-HISTORY bugs whose prevention it owns. UI + its backend build together.

- **P1 — App shell / frame** (`base.html`, `main.ts`, `shell.css`, `tokens.css`).
  Covers A1.1–A1.26, A16.1–A16.10. Header (user/role/theme/sign-out), bottom nav,
  notification badges, help overlay, nav/double-click guards, pull-to-refresh,
  floating report-jobs button (poll `/api/reports/active`, panel, navigate-to-report).
  To-fix: FA2 (jobs button built imperatively), FA6 (global state), FA7 (CSS dumping ground).
  Owns prevention: BH21 (unique session cookie), BH23 (viewport-fit/responsive shell),
  BH24 (token-driven chrome), BH31 (asset cache-busting), BH15 (one shared jobs poll module).

- **P2 — Login** (`blueprints/auth.py`, `login.html`, `msal_flow.py`, `session.py`).
  A2.1–A2.5, C1.1–C1.3. Entra/MSAL real login; dev form only when `AUTH_MODE=dev`;
  safe `next` redirect. Owns: BH21 (auth-flow-in-session/cookie collision),
  BH22 (mirror user directory so real users aren't no-access on first login).

- **P3 — Reports home** (`reports_list.html`, B1.1.1). A3.1–A3.5. Built report cards,
  preset cards (deep-link), coming-soon (disabled backlog), empty-state.

- **P4 — Report viewer: filters & deep links** (`report_view.html`, `report.ts`,
  B1.1.2, B1.4.*, B2.1, B2.7). A4.1–A4.7, A5.1–A5.17. Collapsible filters panel +
  summary, period/custom-dates/status/year/salesman/customer-multiselect (all
  manifest-driven via `REPORT_FILTERS`), lookups warm-up polling, deep links, preset
  auto-run. To-fix: FA1 (god file split: filters module), FB3 (hardcoded per-report
  orchestration → config). Owns: BH25 (init pipeline lookups→params→bind),
  BH30 (lookups return exact SP values), BH43 (blank/invalid dates → validation not 500),
  BH37 (multi-customer must push to SQL, no silent post-filter).

- **P5 — Run / status / resume / cancel** (`report.ts`, B1.2.1–B1.2.5,
  `reporting/jobs.py`, `jobs/worker.py`). A6.1–A6.12. Durable enqueue+poll, resilient
  poll (transient vs terminal), resume on return with true elapsed, honest cancel.
  To-fix: FA1 (jobs module), FA6. Owns: BH12 (queued-only vs running cancel honesty),
  BH13 (cancel button hidden reliably), BH14 (no false "lost the job"),
  BH15 (resume + shared poll), BH16/BH18/BH19 (worker heartbeat/diag visibility).

- **P6 — Report tabs & table** (`report.ts`, `pages.css`, B3.1–B3.9, payload shape).
  A7.1–A7.21, A8.1–A8.12. Tabs (+duplicate/delete), Tabulator (fitDataTable, movable/
  resizable, money/int/percent/date formats, subtotals that skip rate columns),
  sorting, reorder, resize, freeze, hide, group/clear-group, per-column Excel-style
  filters, commission-cards layout, layout-preserving refresh, reset view, view capture.
  To-fix: FA1 (table module), FA4 (table teardown per tab), FA5 (types), FB6 (payload
  = flat rows + tab/view configs, tabs are views over one table). Owns: BH23 (viewport-fit),
  BH24 (dark-mode chrome), BH27 (one grouped dataset feeds screen + export).

- **P7 — Export + recent exports** (`report.ts`, B1.3.1–B1.3.3, `reporting/export.py`,
  `export_jobs.py`, `delivery/layout.py`). A9.7–A9.18. Background export job mirroring
  on-screen layout, auto-download guard, recent-exports panel with live polling,
  error mapping (404/409/413). To-fix: FB6 (shared grouping engine). Owns:
  BH26 (background export + streaming writer), BH27 (export == screen layout),
  BH28 (export fetch re-checks authz + scope token).

- **P8 — Toolbar: columns / reset / save view / presets / API preview**
  (`report.ts`, presets routes, B1.6.1). A9.1–A9.6, A9.19–A9.30. Columns show/hide
  panel, reset view, save view (preset), presets panel (open/delete), developer API
  preview (preview-body). To-fix: FA2 (panels built imperatively → template + toggle).

- **P9 — Email modal + SharePoint picker** (`report.ts`, `email-now`, sharepoint
  status/folders, `delivery/email.py`, `delivery/service.py`, C6.1). A10.1–A10.16.
  Recipients/subject/message, SharePoint folder browser, validation, queue delivery
  job + poll. To-fix: FA3 (dedupe SharePoint picker into one component). Owns:
  BH47 (SharePoint config validated, errors surface setting+Graph status),
  BH48 (delivery rebuilds with owner scope snapshot). SIGN-OFF: SharePoint-save first-cut inclusion (A10.16).

- **P10 — Schedule modal** (`report.ts`, `POST /api/schedules`, `scheduling/*`,
  C6.2–C6.3). A11.1–A11.13. Cadence (daily/weekly/monthly), recipients, SharePoint,
  validation. Owns: BH48 (scheduled delivery owner scope).

- **P11 — Settings** (`settings.html`, `blueprints/settings.py`, C4.1–C4.2).
  A12.1–A12.7. Profile (read-only), theme (4 themes), feature-flags (admin), admin links.

- **P12 — Admin users & access** (`admin_users.html`, `admin.ts`, `blueprints/admin.py`,
  C3.1–C3.2, `repositories/users.py`). A13.1–A13.30. Add/edit/delete users, role,
  flags (active/dashboard/sharepoint/test/external), per-salesman scope grid, per-report
  access overrides (inherit/allow/deny), salesman master edit. Owns: BH22 (directory
  mirror), BH28/BH29 (central authz reused on every path; per-role scope correctness).

- **P13 — Impersonate** (`impersonate.html`, `blueprints/auth.py`, C1.2). A14.1–A14.6.
  Developer/admin-only; can't nest; round-trip `impersonating` fields. Owns: BH32.
  SIGN-OFF: expose an explicit "end impersonation" control (A14.6 — hidden today).

- **P14 — Invoiced report data contract (tabs/columns/math)** (`report_engine/reports/
  invoiced.py`, `sources/invoiced.py`, `reporting/report_service.py`, `params.py`,
  `cache.py`; LIVE `reports/invoiced/` is the format truth). B2.1–B3.9, B4.1–B4.7.
  THE core deliverable: one flat SP table → app groups into the 7 tabs (Summary by
  Customer, Commissions cards, Full Details, Credits, Invoices, +conditional
  Audit-Reversals, Totals by Salesman). To-fix: FB1 (move row math to SQL), FB2
  (manifest-driven tabs/columns + opt-in custom math), FB4 (adapter = rename/normalize
  only), FB5 (registry → DB-seeded config). Owns: BH33–BH46 (every invoiced math/data
  bug). SIGN-OFFS: B4.3, B4.4, B4.5, B4.7 (see §5).

- **P15 — Auth / authz / scope** (`auth/authorization.py`, `principal.py`,
  `decorators.py`, C2.1–C2.2). Central `assert_report_runnable` / `can_view_report` /
  `visible_salesman_keys`, fail-closed on inactive/unknown, scope-compatibility on
  result read (B6.1–B6.5). Owns: BH28, BH29, BH48.

- **P16 — Durable jobs / worker** (`jobs/worker.py`, `jobs/scheduler.py`,
  `repositories/jobs.py`, C5.1–C5.3). Enqueue+dedup, claim, bounded concurrency,
  orphan recovery (capped), leader election, scheduler. To-fix: FC1 (env-driven worker
  threads), FC2 (queue backpressure), FC4 (per-job timeout/watchdog), FC5 (leader fallback).
  Owns: BH4, BH10 (capped recovery + memory budget), BH17 (single leader), BH18.

- **P17 — Data / persistence / migrations** (`data/connection.py`, `migrate.py`,
  in-scope repositories, C8.*, C9–C10). precious vs cache SQLite, WAL, migrations,
  Litestream, local-disk-only. To-fix: FC6 (Postgres-off-ramp seams), FC8 (Litestream
  binary in deploy), FC9 (report memory limits), FC10 (dispatcher mount). Owns:
  BH1–BH8 (SMB→local disk, no journal knob, integrity check, self-healing cache,
  restore test), BH3 (admin integrity check). SIGN-OFF/DEBATE: SQLite vs Postgres (§4).

- **P18 — Delivery / scheduling backend** (`delivery/*`, `scheduling/*`, C6.*).
  EmailService/outbox, DeliveryService.run_and_deliver, ScheduleRunner, cadence, tick.
  Owns: BH47, BH48.

- **P19 — Audit / run log** (`repositories/run_log.py`, C7.1–C7.2). Incident-proof
  app-vs-endpoint record written by run/export/delivery handlers. Owns: BH16, BH50.

- **P20 — Config / boot-safety + report-config seed** (`config.py`, `web/__init__.py`,
  `extensions.py`, `wsgi.py`, `deploy.ps1`, C9.1–C9.2, C10.*). Fail-closed prod boot
  (no dev auth, no default secret, no SMB/UNC paths, Litestream required), CSRF on
  writes, fast `create_app` + background bootstrap thread, asset versioning, `/test`
  mount. **Seed invoiced's report config** here (admin editor deferred). To-fix:
  FC3 (content-based asset version), FC7 (CSRF exempt audit). Owns: BH5 (fast boot +
  daemon thread), BH7 (path validation), BH9 (no duplicate mirror; refresh flag off),
  BH50 (admin-only short-timeout live probe).

---

## 3. Cross-cutting requirements (apply to every page)
From A16 + C9 + non-negotiables: 4 themes via shared tokens; mobile shell (safe-area,
viewport-fit table, full-width Run < 600px); reliable `[hidden]`; a11y basics
(dialog roles, aria-expanded, combobox); CSRF on every state-changing request;
no long work in request handlers (everything durable-job + poll); saved-layout shape
preserved (active tab, order, duplicates, per-tab hidden/frozen/order/sorters/filters/
group/widths, params); export/email/screen share ONE grouped dataset.

---

## 4. Architecture debate inputs (for Phase 2/3)
- **SQLite + Litestream vs managed Postgres** — full trade-off + off-ramp seams in
  `C-platform.structure.md` §3 (FC6). Default: keep SQLite, tighten seams now
  (Python UTC instead of `datetime('now')`, no JSON1-only funcs, abstract `claim_next`).
- **Grouping location** — thin server step (one grouped dataset for screen + export;
  can't diverge — favored by BH27/FB6) vs browser/Tabulator grouping (most dynamic;
  export-parity + big-table memory risk). 
- **Math-in-SQL pivot** — FB1/FB2/FB4/FB5: how much of invoiced's Python math moves
  into the SP, and how the manifest/registry becomes DB-driven config.
- Challenge the locked items (Flask/Python, frontend approach) for better options;
  hosting stays Azure App Service.

---

## 5. NEEDS HUMAN SIGN-OFF (do not decide silently)
Invoiced math/parity (block the parity harness, need a LIVE capture):
- **B4.3** — Commission rate: SP per-row `commission` vs LIVE `commission_map`. Confirm they match.
- **B4.4** — Monthly commission net formula: does LIVE include Misc in the base? (v3 net = sub+tar+misc+credits.)
- **B4.5** — Totals by Salesman: LIVE excludes credits; v3 nets them in. Confirm numbers agree.
- **B4.7** — Do LIVE Full Details / Credits / Invoices sheets include a Misc Charges column?
- **B4.1/B4.2** — Known intentional drift: v3 dropped SalesmanNumber from Summary and added Misc to Summary (LIVE omits). Confirm both are wanted.
Scope/product calls:
- SharePoint-save inclusion in first cut (A10.16). 
- Explicit "end impersonation" control (A14.6).
- Test-Site nav link + v3 marker fate once v3 owns `/test` (A1.2, A1.14).

---

## 6. Coverage diff (skeleton vs inventory)
- Area A: structure skeleton fully covered by A1–A16. No gap.
- Area B: all in-scope routes/tabs covered. Residual: exact request/response shapes
  for presets/email-now/SharePoint routes (B1.7) — confirm during P8/P9 build (frontend
  side already specified in A9/A10/A11). Deferred-report builders intentionally not detailed.
- Area C: modules covered by C1–C10. Residuals: exact columns of `user_report_access`,
  `schedule_runs`, `outbox` tables and SharePoint mock-vs-real fallback — resolve when
  designing the fresh schema (P17/P20). No in-scope feature missing.

No follow-up audit needed; residuals are design-time confirmations, not dropped features.
