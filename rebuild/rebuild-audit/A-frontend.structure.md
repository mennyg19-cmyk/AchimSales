Model: gemini-3.1-pro

Read:
- `rebuild/REBUILD-BRIEF.md`
- `rebuild/rebuild-audit/graph-backbone/A-frontend.md`
- `v3/web/static_src/js/report.ts`
- `v3/web/static_src/js/main.ts`
- `v3/web/static_src/css/tokens.css`
- `v3/web/static_src/css/shell.css`
- `v3/web/static_src/css/pages.css`
- `v3/web/static_src/css/main.css`

## COVERAGE SKELETON

- `main.ts` (App shell behaviors)
  - Help popup (`#helpTitle`, `#helpBody`, `#helpOverlay`)
  - Double-click/double-nav guards (`.page-loading-overlay`)
  - Pull-to-refresh (`.ptr-indicator`)
  - Theme toggle (`#themeToggleBtn`)
  - Notification badges (`#badgeDashboard`, `#badgeReports`)
  - Floating report jobs button (`#reportJobsBar`, `.report-jobs-panel`, `.report-jobs-fab`)
- `report.ts` (Report viewer)
  - Status row (`#reportStatus`, `#reportStatusText`, `#cancelRunBtn`)
  - Meta/summary (`#reportMeta`, `#controlsSummary`, `#controlsToggle`)
  - Tabulator table (`#reportTable`)
    - Commission cards layout (`.commission-cards`)
    - Column headers with funnel filter (`.col-header-inner`, `.col-filter-btn`)
    - Column filter popover (`.col-filter-popover`)
  - Tabs (`#reportTabs`, `.tab-context-menu`)
  - Columns show/hide panel (`.columns-panel`)
  - Recent exports panel (`#exportsList`, `#exportsPanel`)
  - Action toolbar buttons (`#runBtn`, `#refreshBtn`, `#resetBtn`, `#exportBtn`, `#columnsBtn`, `#saveViewBtn`, `#presetsBtn`, `#emailBtn`, `#scheduleBtn`, `#apiRunBtn`, `#previewBtn`)
  - Filters form (`#filterForm`, `#periodSelect`, `[name="start_date"]`, `[name="end_date"]`, `#salesmanSelect`)
  - Customer multi-select picker (`#customerPicker`, `.customer-search`, `.customer-options`, `#customerPills`)
  - API preview (`#apiPreview`, `#apiRunWrap`)
  - Presets/saved views panel (`#presetsPanel`)
  - Email modal (`#emailModal`, `#emailSubject`, `#emailRecipients`, `#emailMsg`, `#emailSend`, `#emailClose`, `#emailCancel`)
    - SharePoint picker (`#spSection`, `#spBreadcrumb`, `#spPicker`, `#spSelected`, `#spStatus`)
  - Schedule modal (`#scheduleModal`, `#schedFreq`, `#schedWeekdays`, `#schedMonthdayField`, `#schedMonthday`, `#schedRecipients`, `#schedMsg`, `#schedSave`, `#schedClose`, `#schedCancel`)
    - SharePoint picker (`#schedSpSection`, `#schedSpBreadcrumb`, `#schedSpPicker`, `#schedSpSelected`, `#schedSpStatus`)
- CSS
  - `tokens.css` (Design tokens, Light/Dark/Monochrome themes)
  - `shell.css` (App shell: header, badges, floating jobs button, bottom nav, container, buttons, alerts, overlays, pull-to-refresh)
  - `pages.css` (Auth/login, headers, report list cards, filter bar, searchable customer multi-select, API preview, recent exports, collapsible controls, toolbar, run status, report tabs/table, Tabulator overrides, right-click menus, modals, SharePoint picker, simple tables, dashboard, Settings, Master schedules)

## TO-FIX LIST

`FA1`: `report.ts` is a God File
- **What's wrong:** The file is ~2,100 lines long and handles everything: Tabulator instantiation, per-column filters, layout saving/restoring, API polling/cancelling, email/schedule modals, SharePoint folder browsing, lookup data fetching (salesmen/customers), UI toggles (panels), and deep-link parsing.
- **Where:** `v3/web/static_src/js/report.ts`
- **Why it matters:** Violates the "clean-code" rule against god files (>500 lines or mixed concerns). Hard to maintain, reason about, or reuse logic (like the SharePoint picker or lookup polling) in other parts of the app.
- **Suggested fix direction:** Split by concern into distinct modules. E.g., `api.ts` (polling, running, cancelling, exports), `table.ts` (Tabulator, columns, filters, formatting), `filters.ts` (lookups, deep-links, form collection), `modals.ts` (email, schedule, SharePoint picker), `views.ts` (presets, layout state).

`FA2`: Reactive bolt-on UI for modals and panels
- **What's wrong:** Panels and modals (columns panel, presets panel, column filter popover, tab context menu) are constructed imperatively by creating DOM elements in JS (`document.createElement`) and appending them to the document body, tracking references in module-scoped let variables (`columnsPanel`, `colFilterPopover`, `tabMenuEl`).
- **Where:** `report.ts` (`toggleColumnsPanel`, `openColumnFilterPopover`, `openTabMenuAt`, `togglePresetsPanel`)
- **Why it matters:** Brittle DOM management. Risk of memory leaks (event listeners not properly cleaned up, though `AbortController` is used in one place). Inconsistent with how the Email and Schedule modals are handled (hidden HTML elements toggled via JS). "Stack of cards" architecture.
- **Suggested fix direction:** Define the panel/popover structures in the HTML templates (like `emailModal`) and use a consistent UI component approach (or thin wrapper) to toggle their visibility and bind data, rather than building raw DOM nodes in imperative JS.

`FA3`: Duplicate SharePoint picker logic
- **What's wrong:** The logic for browsing and selecting SharePoint folders is instantiated twice using a factory function `makeSpPicker`, which manually queries DOM IDs.
- **Where:** `report.ts` (`makeSpPicker`, `emailSp`, `scheduleSp`)
- **Why it matters:** While the logic is abstracted into a closure, it relies on passing 5 separate DOM IDs per instance and directly mutating them. It mixes data fetching (`data-sp-folders-url`) with tight DOM coupling.
- **Suggested fix direction:** Extract the SharePoint picker into a reusable, encapsulated component/module that doesn't rely on hardcoded parent-provided DOM IDs, but rather takes a container element and emits a "selected" event.

`FA4`: Overloaded Tabulator and ViewState syncing
- **What's wrong:** `ViewState` manually tracks hidden columns, frozen columns, order, and widths, and then this is imperatively synced with Tabulator. The `rebuild(tab)` / `buildTable(tab)` function destroys and recreates the entire Tabulator instance when switching tabs.
- **Where:** `report.ts` (`captureActive`, `buildTable`, `applyColumnFilters`)
- **Why it matters:** Destroying and recreating the table on every tab switch is a heavy operation (performance hit, janky UI). Manual state tracking duplicates Tabulator's internal state management.
- **Suggested fix direction:** Utilize Tabulator's built-in layout persistence or lifecycle hooks more effectively. Investigate if changing the table data (`table.setData()`) is sufficient when switching tabs that share similar structures, instead of a full tear-down.

`FA5`: Untyped/Loose Types in TypeScript
- **What's wrong:** Heavy use of `any` and `unknown` types, especially around Tabulator objects, row data, and API responses. E.g., `declare const Tabulator: any;`, `formatter: (cell: any) => ...`.
- **Where:** `report.ts` (throughout)
- **Why it matters:** Defeats the purpose of TypeScript. Refactoring the god file will be much harder and more error-prone without solid types for the core data structures (like the Tabulator cell/column objects).
- **Suggested fix direction:** Define proper interfaces for the Tabulator dependencies (or use community typings) and strictly type the API responses and row data objects.

`FA6`: Global state and implicit dependencies in UI logic
- **What's wrong:** Global mutable state like `state`, `activeRunJobId`, `runAborted`, `pendingSalesman`, `customerPickerOpen` are scattered. Event listeners refer to these global variables.
- **Where:** `report.ts`, `main.ts`
- **Why it matters:** Makes the code difficult to test, trace, and refactor. Side effects are hard to predict (e.g., `cancelRun` sets `runAborted = true`, which a separate polling loop checks).
- **Suggested fix direction:** Encapsulate state within specific controller classes or modules. Pass required state explicitly to functions rather than relying on outer module scope.

`FA7`: CSS File Structure and "One-Off" overrides
- **What's wrong:** `pages.css` is massive and contains styles for almost everything not in the shell (modals, filters, Tabulator overrides, specific page grids). It includes highly specific overrides (e.g., `.tabulator .tabulator-header .tabulator-col .tabulator-col-content { display: flex !important; ... }`).
- **Where:** `v3/web/static_src/css/pages.css`
- **Why it matters:** Goes against the tokens/components methodology. Hard-coding `!important` Tabulator overrides makes upgrading Tabulator dangerous. A 600+ line CSS file for "pages" becomes a dumping ground.
- **Suggested fix direction:** Break `pages.css` down into component-specific CSS files (e.g., `table.css`, `modals.css`, `filters.css`). Ensure design tokens are used strictly instead of raw values, and try to theme Tabulator using its built-in SCSS/CSS variables approach rather than brute-force overrides if possible.