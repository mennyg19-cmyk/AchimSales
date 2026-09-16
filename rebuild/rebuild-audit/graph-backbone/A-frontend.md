# Graph backbone — Area A: Frontend / UI / shell

Factual map only (no interpretation). Source of truth = the files themselves;
this orients the auditors. Scope = invoiced report + confirmed shell features.
Deferred (note but don't deep-audit): dashboard, customer-last-order pages,
schedules list pages, master schedules, run-log page.

## Templates (`v3/web/templates/`)
- `base.html` — app shell: header (user, role badge, theme toggle, sign out),
  bottom nav (Reports/Dashboard/Schedules/Settings + Test Site), notifications
  badge poll hook (`data-notifications-url`), floating report-jobs button
  (`#reportJobsBar`, `data-active-url`, `data-report-url`), help popup overlay.
- `report_view.html` — the invoiced/report screen. Collapsible "Filters &
  options" panel (`#reportControls`), `#filterForm` (period/status/year/salesman/
  customers), Run button, action toolbar (refresh, columns, reset, export, recent
  exports, email, schedule, save view, presets, API preview[dev]), status row
  (`#reportStatus` + cancel), report surface (`#reportTabs`, `#reportTable`),
  email modal, schedule modal, big `#reportRoot` data-* URL block.
- `reports_list.html` — home: built report cards + preset cards.
- `login.html`, `settings.html`, `admin_users.html`, `impersonate.html` — in scope.

## Frontend modules (`v3/web/static_src/js/`, bundled by esbuild → static_dist)
- `main.ts` — shell behaviors: feather icons, help popup, nav double-click guard,
  page-loading overlay, pull-to-refresh, theme toggle, notification badges,
  `initReportJobsBar()` (floating jobs button: poll active runs, panel, navigate).
- `report.ts` — THE god file (~2,100 lines). Everything for the report screen:
  filters/deeplink/presets, Tabulator table build, per-column Excel-style filters,
  show/hide columns, reorder, resize (`ViewState.widths`), grouping, tabs,
  subtotals, commission cards layout, run/poll/resume/cancel jobs, dynamic table
  height (`tableHeight`/`fitTableHeight`), export + recent exports, save view,
  email modal, schedule modal, API preview.
- `settings.ts`, `admin.ts`, `schedules.ts` — settings, admin users, schedules UI.

## CSS (`v3/web/static_src/css/`)
- `tokens.css` (design tokens), `shell.css` (header/nav/buttons/jobs button),
  `pages.css` (report controls/toolbar/table/status), `main.css` (bundle entry).

## Key frontend data shapes (from report.ts)
- `Column{field,header,type:text|money|percent|int|date}`,
  `Tab{key,name,columns,rows,layout?,salesmen?,grand?,month_labels?}`,
  `Payload{report_key,tabs,row_count,generated_at}`,
  `ViewState{hidden,frozen,order,sorters,columnFilters,group,widths}`,
  `CommissionMonth`, `CommissionSalesman` (commission_cards layout).

## What auditors must cover (Area A)
- Inventory: every control on `report_view.html` + `base.html` shell and exactly
  what it does (buttons, modals, tabs, table interactions, jobs button, theme,
  nav, help, presets, exports panel).
- Structure: the report.ts god file, one-off CSS, reactive bolt-ons (jobs button,
  status bar, resume), responsiveness/mobile issues, token usage consistency.
