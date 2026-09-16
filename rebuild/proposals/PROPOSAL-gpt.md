Model: gpt-5.5-extra-high

## PROOF-OF-READ
- `REBUILD-BRIEF.md`: read in full. It defines the rebuild as SQL-first, presentation-only, one stored procedure per report, one flat table, SQL-enforced scope, admin-defined reports, invoiced first, Azure App Service, Entra login, durable jobs, audit log, tests as the ship gate, and cutover-ready routing.
- `FEATURE-INVENTORY.md`: read in full. It defines 20 in-scope pages/todos (P1-P20), 6 in-scope page route groups, the report/API route families, and cites Area B's roughly 31 report routes; deferred routes stay on the list but are not first-cut work.
- `BUILD-HISTORY.md`: read in full. It lists 50 bugs/pain points (BH1-BH50) covering persistence, job lifecycle, UI drift, report math, auth scope, delivery, and diagnostics.
- `rebuild/rebuild-audit/*.inventory.md` and `*.structure.md`: read in full. Area A inventories 14 screens and 223 controls, Area B inventories 7 invoiced tabs and 69 named columns, Area C inventories 42 platform IDs, with FA1-FA7, FB1-FB8, and FC1-FC10 as the structural fix list.

## Headline architecture

Use Flask + server-rendered templates + esbuild TypeScript + Tabulator, but rebuild the structure around clean boundaries:

- SQL Server stored procedures own report-specific row math and scope filtering.
- Flask owns auth, routing, validation, job enqueue, and HTML/JSON responses.
- A durable worker owns report runs, exports, email-now, schedules, and delivery.
- Managed Postgres owns durable app state: users, access, jobs, audit, schedules, presets, report config.
- Azure Blob owns large report snapshots and exported files.
- A server-side `ReportViewBuilder` owns grouping, layout, filters, sorting, subtotals, and export/email parity.
- The browser owns interaction only: forms, toolbar, modals, tabs, grid rendering, and polling.

Old code is a checklist for behavior, not a source to port.

## 1. Stack

### Backend

Keep Python + Flask.

Flask is still the right fit because this is a page-based internal reporting app, not a public API product. The hardest problems are stored-procedure contracts, durable jobs, report snapshots, Entra login, auth scope, Excel export, and delivery. Switching to Django, FastAPI, Next.js, or a full React stack would not remove those risks; it would add a framework migration on top of them.

The change is discipline:

- Blueprints are thin controllers.
- Services run workflows.
- Repositories hide storage.
- Report config is loaded from the database.
- Long work never runs in request handlers.

### Frontend

Use server-rendered templates plus TypeScript modules.

Keep Tabulator, but only behind `ReportGridAdapter`. It already covers movable columns, resize, freeze, column filters, grouping display, horizontal scroll, and table ergonomics. Replacing it would be a rewrite of a grid library. The clean fix is to stop letting every module talk to Tabulator directly.

Use esbuild with content-hashed output:

- `main.ts` for shell behavior.
- `report-viewer.ts` for the report screen.
- `admin-users.ts` for admin users.
- Optional small entrypoints only when a page actually needs them.

Templates load assets through a build manifest. No time-based cache busting.

CSS is split by surface and component:

- `tokens.css`
- `shell.css`
- `components/buttons.css`
- `components/forms.css`
- `components/modals.css`
- `components/panels.css`
- `components/table.css`
- `pages/report-viewer.css`
- `pages/admin-users.css`
- `pages/settings.css`

## 2. Persistence

### Recommendation: managed Postgres for production

Use managed Postgres for durable production state. Keep a SQLite adapter only for local development or a cost fallback.

This is the one place I would challenge the current default. SQLite + Litestream can work on one App Service instance, but the bug history shows how much ceremony it needs: local-only paths, no `/home`, restore proof, Litestream packaging, WAL behavior, worker visibility, integrity checks, and single-instance assumptions. v3 is meant to replace live. Durable state should not depend on an ephemeral local file plus a sidecar restore path unless cost forces that choice.

Postgres stores:

- users, roles, preferences, feature flags
- salesman and report access
- report definitions, parameters, columns, tabs, scope rules, versions
- jobs, attempts, heartbeats, cancellations
- presets/saved views
- schedules, schedule runs, outbox rows
- audit/run log
- export metadata

Azure Blob stores:

- large report result snapshots
- exported `.xlsx` files
- optional archived job artifacts

Repository seams:

- `Database` protocol exposes transactions, parameter binding, and row fetching. Code does not import `psycopg` or `sqlite3` outside the data layer.
- `JobRepository.claim_next()` is the only place that knows row-locking details. Postgres uses `FOR UPDATE SKIP LOCKED`; SQLite fallback uses a safe update-then-select claim.
- Repositories receive Python UTC timestamps. No `datetime('now')` in SQL.
- JSON is encoded/decoded in Python at the repository edge. Postgres can store JSONB later without changing service code.
- Migrations are backend-specific under one runner: `migrations/postgres` and optional `migrations/sqlite`.

If cost vetoes Postgres, use the same interfaces with SQLite + Litestream. Production then must keep the current hard rules: local disk only, fail boot on `/home` or UNC paths, Litestream installed and verified, integrity checks, restore tests, and one app instance.

## 3. Grouping location

Use a thin server grouping/view step.

The server builds the view because screen, export, email, and schedule must agree. BH27 exists because export and screen had different paths. Browser-only grouping is tempting, but it makes Excel/email parity harder and pushes big flat tables into user memory.

The shape:

1. Worker runs the report stored procedure and stores a flat result snapshot.
2. Browser asks for a view: active tab, hidden columns, order, widths, sorters, filters, group, duplicate tabs, and params.
3. `ReportViewBuilder` applies the same generic rules for screen, export, email, and schedule.
4. Screen receives a paged view for the active tab.
5. Export streams the same view rules across all requested tabs.

Big-table rule:

- The browser does not need every row for every tab at once.
- Normal-sized results can send rows directly.
- Large results use server paging/filtering/sorting over the stored snapshot.
- Exports stream rows and never build the whole workbook in browser memory.

The app still feels interactive because Tabulator renders the active page quickly, while the server remains the source for view parity.

## 4. SQL-first math and report config

### Invoiced stored procedure contract

The invoiced SP should return one flat table at the row grain needed for display and generic grouping. The app should not detect credits, net invoices, calculate commission bases, fetch YTD twice, or join salesman commission rules from Azure.

The SP returns fields such as:

- invoice identity: invoice number, date, sales order
- customer identity: account, name
- salesman identity: group/code, number, name
- row flags: `IsCredit`, `IsReversalAudit`
- money columns: subtotal, tariff, freight, CC, misc, total invoice
- commission columns: commission rate, commission month, commission base, commission dollars
- count helpers when needed: invoice count contribution or a configured distinct-count field

Commissions become a saved tab definition over the same flat table:

- group by salesman
- bucket by commission month
- sum commission dollars and commission base
- display commission rate on detail/card rows
- leave rate blank on total rows

If a number needs business meaning, SQL provides it. If a subtotal is just "sum this numeric column for the current view," the app can do it generically.

### Config model

Seed invoiced config now; admin editor comes later. The seed writes the same tables the future admin editor will manage.

Core tables:

- `report_definitions`: key, title, stored procedure name, enabled status, version, help key.
- `report_parameters`: key, type, label, stored-procedure parameter name, allowed values source, validation.
- `report_columns`: source field, label, type, format, default order, aggregate rule, visibility, width.
- `report_tabs`: tab key, label, layout, group fields, bucket fields, sort, subtotal settings.
- `report_tab_columns`: columns shown per tab and their order.
- `report_scope_rules`: which parameter carries salesman/customer scope.
- `report_versions`: contract version, seeded checksum, migration notes.

The registry becomes a DB-backed catalog. Code keeps only reserved behavior for system-only routes and optional custom renderers. Normal reports are config, not deploys.

## 5. Module structure

Proposed `v3/` shape:

```text
v3/
  web/
    app.py
    config.py
    extensions.py
    blueprints/
      auth.py
      reports_pages.py
      reports_api.py
      jobs_api.py
      exports_api.py
      delivery_api.py
      admin.py
      settings.py
      diagnostics.py
      health.py
    templates/
      shell/
      reports/
      admin/
      settings/
      auth/
  platform/
    auth/
      principal.py
      msal_flow.py
      authorization.py
      decorators.py
      session.py
    data/
      database.py
      migrations.py
      repositories/
    jobs/
      model.py
      queue.py
      worker.py
      handlers.py
      scheduler.py
    audit/
      run_log.py
  reporting/
    api_client.py
    catalog.py
    config_models.py
    params.py
    runner.py
    snapshots.py
    view_builder.py
    grouping.py
    filtering.py
    export/
      excel_writer.py
      layout.py
    seeded_reports/
      invoiced.py
  delivery/
    email.py
    sharepoint.py
    service.py
    outbox.py
  scheduling/
    cadence.py
    runner.py
    tick.py
  static_src/
    ts/
      main.ts
      report-viewer/
        index.ts
        api.ts
        state.ts
        filters.ts
        tabs.ts
        grid-adapter.ts
        toolbar.ts
        jobs-panel.ts
        presets.ts
        delivery-modal.ts
        schedule-modal.ts
        sharepoint-picker.ts
        column-filter-popover.ts
        types.ts
      admin-users.ts
    css/
```

Worker layout:

- Web process handles HTTP only.
- Continuous worker process or Azure WebJob handles queued jobs.
- Both use the same Postgres-backed job table.
- Dev may run an inline drain, but production never does report work in a request.

Job types:

- `report.run`
- `report.export`
- `delivery.email_now`
- `schedule.run`
- `schedule.tick`
- `maintenance.cache_cleanup`

## 6. Information architecture and UI

### Navigation

Keep the app simple:

- Top header: product name, user/role, impersonation state, theme, sign out.
- Bottom nav: Reports, Schedules, Settings.
- Dashboard remains feature-flagged/deferred.
- Test Site link and v3 marker are deployment scaffolding; keep during `/test`, remove or hide when v3 owns `/`.

### Reports home

Sections:

- Built reports the user can run.
- Saved views/presets.
- Coming soon cards for deferred reports.
- Empty state when the user has no report access.

### Report viewer

Use one page with clear zones:

1. Header row: back link, report title, help.
2. Collapsible filters panel: period, dates, status/year when configured, salesman, customers, lookup status.
3. Action toolbar: run/refresh, columns, reset, save view, presets, export, email, schedule, recent exports, developer API preview.
4. Job status row: progress, elapsed time, honest cancel state.
5. Tabs row: saved tabs plus user duplicates.
6. Table/card surface: Tabulator for normal tabs, commission cards for the commission layout.
7. Modals and panels: all are template-defined and toggled, not built from scattered `document.createElement` calls.

Tabs are views, not separate reports. A tab says "group these rows this way, show these columns, subtotal these numeric columns, use this layout."

## 7. P1-P20 preservation map

- P1 App shell: shared shell module, notification/jobs poller, help overlay, theme, guards, responsive bottom nav.
- P2 Login: Entra/MSAL by default, dev login only in dev, safe `next`, unique cookie.
- P3 Reports home: built reports, preset cards, disabled coming-soon cards, empty state.
- P4 Viewer filters/deep links: manifest-driven filters, lookup warm-up, deep-link init order, preset auto-run.
- P5 Run/status/resume/cancel: durable queue, active jobs endpoint, transient poll handling, true elapsed, honest cancel.
- P6 Tabs/table: config-backed tabs, Tabulator adapter, saved layout, duplicate/delete tab, filters, subtotals, commission cards.
- P7 Export/recent exports: background export, recent export poll, streaming writer, same view builder as screen.
- P8 Toolbar/presets/API preview: template panels, saved views, developer-only preview.
- P9 Email/SharePoint: delivery job, reusable SharePoint picker, validation, owner scope snapshot.
- P10 Schedule modal: cadence validation, same SharePoint picker, saved layout and params.
- P11 Settings: profile, theme, feature flags, admin links.
- P12 Admin users/access: CRUD, roles, flags, salesman scope, report overrides, salesman master edit.
- P13 Impersonate: privileged only, no nesting, visible end-impersonation control.
- P14 Invoiced contract: 7 tabs, 69 columns, SQL-owned math, seeded report config, human sign-offs preserved.
- P15 Auth/authz/scope: one authorization service reused by run/result/export/email/schedule.
- P16 Jobs/worker: Postgres queue, worker process, backpressure, timeouts, heartbeat, retries.
- P17 Data/persistence: Postgres durable state, Blob snapshots/exports, repository interfaces, migrations.
- P18 Delivery/scheduling: shared delivery service, outbox, schedule runner, owner-scope rebuild.
- P19 Audit/run log: write app-vs-endpoint records for run/export/delivery/schedule.
- P20 Config/boot-safety: fail-closed prod config, CSRF, content-hashed assets, `/test` mount tests, invoiced seed.

## 8. To-fix coverage

### FA1-FA7

- FA1: Replace `report.ts` with `report-viewer/*` modules and one page controller.
- FA2: Define modals, panels, popovers, columns panel, presets panel, and context menus in templates; JS binds and toggles them.
- FA3: Extract SharePoint picker as a reusable component taking a container and emitting selected path.
- FA4: Put Tabulator lifecycle behind `ReportGridAdapter`; keep view state in one typed store and avoid full teardown when data shape allows.
- FA5: Generate or hand-write strict TypeScript contracts for API payloads, report columns, tabs, view state, jobs, exports, and delivery.
- FA6: Replace scattered globals with `ReportViewerState` and explicit controller dependencies.
- FA7: Split CSS by component/page and keep Tabulator styling token-based.

### FB1-FB8

- FB1: Move credit flags, totals, net values, commission base, commission dollars, YTD/window rules, and row-level report math into SQL.
- FB2: Replace hardcoded invoiced tab builder with generic tab definitions plus optional registered layouts such as `commission_cards`.
- FB3: Replace per-report orchestration with DB-loaded report definitions and parameter mappings.
- FB4: Adapters normalize names/types only; they do not calculate totals, derive credit flags, or post-filter customers.
- FB5: Replace static registry with seeded DB config and later admin CRUD.
- FB6: Payload is flat snapshot plus view configs; tabs are views over one result, not separate row payloads.
- FB7: Split large backend/frontend files by concern as shown in the module structure.
- FB8: Deferred reports stay cataloged as disabled/backlog config until their flat-table SPs exist.

### FC1-FC10

- FC1: `JOB_WORKER_THREADS` env var, default 1 on B1.
- FC2: queue depth limits and `Retry-After` when full.
- FC3: content-hashed asset manifest.
- FC4: per-job timeout, heartbeat, and failed-after-timeout status.
- FC5: production worker is a single worker/WebJob; dev leader fallback is explicit and logged.
- FC6: repository interfaces make storage swappable; no SQLite-specific SQL leaks into services.
- FC7: CSRF required on every POST/PUT/PATCH/DELETE except the documented Entra callback and health route.
- FC8: Postgres removes Litestream from the default path; SQLite fallback must package and verify Litestream.
- FC9: server paging, export streaming, row-count/memory budgets, and no all-tabs-to-browser payload for large results.
- FC10: mount-aware URLs and integration tests for `/test`, `/test/auth/callback`, static assets, redirects, and cutover to `/`.

## 9. Build-history prevention

- BH1, BH2, BH3, BH4, BH7: production Postgres removes SQLite-on-SMB, journal-mode, WAL, corruption, and migration-lock incidents from the main path.
- BH5: `create_app()` is fast; migrations and workers run outside request startup.
- BH6: cache/snapshot stores self-initialize and treat missing disposable artifacts as recoverable.
- BH8: Blob snapshots/exports are durable; if SQLite fallback is used, restore is tested before ship.
- BH9: no duplicate mirror refresh stack; dashboard refresh stays feature-flagged and deferred.
- BH10: orphan retry cap, memory budgets, and no unbounded requeue loop.
- BH11: stored procedures filter on SQL; any chunking is explicit and worker-owned.
- BH12, BH13, BH14, BH15: honest cancel state, reliable hidden states, transient poll retry, active job resume.
- BH16, BH18, BH19, BH50: worker heartbeat, queue depth, last claim, safe repair tools, and short admin-only probes.
- BH17: one worker process owns scheduler and delivery drains.
- BH20: `report.ts` is replaced by typed modules.
- BH21: unique session cookie for mounted v3.
- BH22: user directory mirror/sync at login and scheduled refresh.
- BH23, BH24: viewport-fit layout and token-driven themes.
- BH25: init order is lookups, URL params, preset layout, then run.
- BH26: export is a background job with streaming writer.
- BH27: one server view builder feeds screen/export/email/schedule.
- BH28, BH29, BH48: central authz re-checks user/report/scope for every result, export, email, and schedule.
- BH30: lookups return exact stored-procedure parameter values with display labels separate.
- BH31: content-hashed assets.
- BH32: immutable principal with impersonation round-trip tests and visible end control.
- BH33, BH34, BH35, BH36, BH38, BH40, BH41, BH42, BH44, BH46: SQL contract owns credit, netting, commission, YTD window, salesman identity, invoice count, field names, and row math.
- BH37: multi-customer selection is passed to SQL through a list/table-valued parameter; no silent Python post-filter.
- BH39: report columns are seeded from the SP contract and fail contract tests if required fields are missing.
- BH43: params layer validates blank/bad dates and returns user errors, not 500s.
- BH45: commissions are a tab layout over the shared flat table, not a second presentation path.
- BH47: SharePoint config validates site/folder access and returns setting name plus Graph status.
- BH49: LIVE parity remains temporary scaffolding until SQL contract sign-off; after cutover tests target SP output.

## 10. Tests as ship gate

Required gates:

- Stored-procedure contract tests for invoiced required fields and types.
- Invoiced parity tests against signed LIVE captures until cutover.
- Auth/scope tests for admin, manager, salesman, revoked access, stale result/export reads, email, and schedule.
- Job lifecycle tests: enqueue, claim, progress, timeout, cancel, retry cap, resume, export.
- View-builder parity tests: the same layout produces the same rows/totals for screen, export, email, and schedule.
- Migration tests on Postgres and optional SQLite fallback.
- Security tests: prod boot refusal, CSRF, safe redirects, path/mount safety, admin-only diagnostics.
- UI smoke tests for report viewer filters, tabs, columns, presets, modals, mobile layout, and dark theme.

## 11. Human sign-offs preserved

Do not decide these silently:

- B4.3 commission rate source: SP row value versus LIVE `commission_map`.
- B4.4 commission net formula: whether Misc belongs in the commission base.
- B4.5 Totals by Salesman: credit handling versus LIVE.
- B4.7 Misc Charges placement in detail/credit/invoice tabs.
- B4.1/B4.2 Summary SalesmanNumber and Misc Charges drift.
- A10.16 SharePoint-save first-cut inclusion.
- A14.6 end impersonation visibility.
- A1.2/A1.14 v3 marker and Test Site nav behavior at cutover.

## 12. Cutover posture

Mount v3 so `/test` and `/` are configuration, not code forks. Every generated URL uses `url_for` under the mounted script name. Entra redirect URI works under `/test` before cutover and `/` after cutover. Tests exercise both. The live parity harness exists only to prove the cutover; after cutover, SQL Server stored procedures become the report truth.
