Model: gpt-5.5-extra-high

## Proof Of Read
- `rebuild/REBUILD-BRIEF.md` read in full: 97 lines. It says v3 is a ground-up rebuild, not a port; the app is presentation-only; invoiced goes first; first deliverable is invoiced plus the shell it depends on.
- Core brief counts: 7 decided architecture points, 10 locked prerequisites, 4 open debate topics, 2 reference anchors.
- `rebuild/rebuild-audit/graph-backbone/A-frontend.md` read in full: 50 lines. It names 7 templates, 4 TypeScript modules, 4 CSS files, and 5 key frontend data shapes.
- Backbone scope: inventory the invoiced/report screen and confirmed shell; note but do not deep-inventory dashboard, customer-last-order, schedules list, master schedules, or run-log page.

## Inventory Counts
- Screens and panels inventoried: 14.
- Distinct controls and behaviors inventoried: 223.
- Deferred screens noted only: 5.

## A1. Authenticated Shell

Route: shared by every authenticated v3 page. Registered with no blueprint prefix.

Shows:
- Sticky top header.
- Main content area with flash messages.
- Floating report-jobs button when the user has active or recently finished report jobs.
- Fixed bottom navigation.
- Global help overlay.

Navigation in:
- Any authenticated page render extends `base.html`.

Navigation out:
- Header logo and Reports bottom-nav item go to `/`.
- Dashboard bottom-nav item goes to the dashboard route when enabled or when the user is admin/developer.
- Schedules bottom-nav item goes to `/schedules`.
- Test Site bottom-nav item opens `/test/` in a new tab when enabled for the user.
- Settings bottom-nav item goes to `/settings`.
- Sign Out posts to `/logout`.

Controls and states:

A1.1 Header logo: text `Sales Reports`; clicking navigates to Reports home (`/`).

A1.2 Non-prod v3 marker: small `v3` badge shown only when `new_app_marker` is true and `app_env != "prod"`. Question: this is explicitly marked removable at cutover; confirm whether rebuild keeps it during `/test` only.

A1.3 User display: shows the user's name in normal sessions; in dev impersonation sessions it shows `Viewing as <name>` with an impersonation badge.

A1.4 Role badge: shows `Admin`, `Developer`, `Manager`, or `Salesman`; badge color changes by role.

A1.5 Theme toggle: icon-only button. Cycles `light -> dark -> monochrome -> monochrome_dark -> light`, updates the body class immediately, swaps the Feather icon (`sun`, `moon`, `aperture`, `disc`), then POSTs JSON `{theme}` to `/api/settings/preferences` with CSRF. Persistence failure does not roll back the visual change.

A1.6 Switch user: icon-only repeat button shown only for dev sessions (`user._dev`). Navigates to `/login`. Question: this is a dev convenience and may be bolted on; keep unless dev-login/impersonation remains in rebuild.

A1.7 Sign Out: POST form to `/logout` with CSRF. Redirects to `/login`.

A1.8 Flash messages: renders queued Flask flash messages above page content with `alert-<category>` styling.

A1.9 Reports nav item: bottom nav icon `file-text`; active when `active_tab == "reports"`; contains `badgeReports`.

A1.10 Reports notification badge: hidden at zero; shows count from `/api/notifications` field `report_ready_count`; displays `99+` above 99. Polled every 30 seconds.

A1.11 Dashboard nav item: shown if dashboard is globally enabled and user has dashboard access, or if user is admin/developer. Active when `active_tab == "dashboard"`. Deferred page; inventory only the shell control.

A1.12 Dashboard notification badge: hidden at zero; shows `/api/notifications` field `overdue_count`; displays `99+` above 99. Polled every 30 seconds.

A1.13 Schedules nav item: always shown to signed-in users; active when `active_tab == "schedules"`; navigates to `/schedules`. Schedules list page is deferred.

A1.14 Test Site nav item: shown if feature flag and per-user test access allow it, or if privileged; opens `/test/` in a new tab. Question: if v3 is mounted at `/test`, this link may point to itself or old test behavior depending deployment; confirm before rebuilding.

A1.15 Settings nav item: always shown to signed-in users; active when `active_tab == "settings"`; navigates to `/settings`.

A1.16 Global help triggers: any element with `data-help` opens the help overlay, looks up `HELP[key]`, writes title and HTML body, and prevents normal click handling.

A1.17 Help overlay: full-screen dim overlay; closes when clicking the overlay background, clicking the close `x`, or pressing Escape. Does not close when clicking inside the popup body.

A1.18 Global button double-click guard: all non-submit buttons without `data-no-guard` ignore repeated clicks for 600ms. This protects actions from accidental double taps.

A1.19 Navigation guard: normal internal links show a full-page loading overlay and prevent double navigation for 4 seconds. Skips anchors, `javascript`, new-tab links, downloads, `/download` URLs, modifier-clicks, modal links, and help-popup links. If a bottom-nav item was clicked, the active state moves immediately.

A1.20 Page-show reset: when a page is restored from browser history, removes any loading overlay and clears the navigation guard.

A1.21 Pull-to-refresh: touch-only. When at scroll top, pulling down shows a pill saying `Pull to refresh`; past threshold it says `Release to refresh`; release runs `window.triggerDashRefresh()` if present, otherwise reloads the page. This is shell-wide but mainly useful on dashboard.

A1.22 Floating report-jobs button: polls `/api/reports/active` every 5 seconds. Hidden when there are no queued/running jobs and no recently finished jobs. Shows a bottom-right FAB above the bottom nav.

A1.23 Floating jobs FAB states: if any job is queued/running, label is `<n> running` with spinner and primary color; if none running and any failed, label is `Report failed` and error color; if none running and none failed, label is `Reports ready` and success color.

A1.24 Floating jobs panel: clicking the FAB toggles a panel. Each job row shows a colored dot and label `<report title> - <status word>`, where running says `building <progress>%`, queued says `waiting to start`, success says `ready`, failure says `failed`.

A1.25 Floating job row click: if `report_key` exists, navigates to `/reports/<report_key>`. The report page then reconnects to the matching queued/running/success job for that report.

A1.26 Floating jobs outside click: clicking outside the jobs bar closes the panel without hiding the FAB.

## A2. Login Screen

Route: `GET /login`; dev form posts to `POST /login/dev`. In MSAL mode, `/login` redirects to Microsoft instead of rendering this form.

Shows:
- Centered auth card.
- Title `Sales Reports`.
- Subtitle `Developer sign-in`.
- Email and role fields.
- Sign in button.

Navigation in:
- Unauthenticated users, explicit Switch User link, or logout redirect.

Navigation out:
- Successful dev sign-in redirects to the safe relative `next` path, or health route fallback.
- MSAL callback route is `/auth/callback`.

Controls and states:

A2.1 Email field: required email input, autofocus, placeholder `you@achimonline.com`.

A2.2 Role select: options from server `VALID_ROLES`; submitted role falls back to `salesman` if invalid.

A2.3 Hidden CSRF field: required for POST.

A2.4 Hidden next field: preserves intended relative destination. Server refuses external redirects.

A2.5 Sign in button: submits the form. Server refuses `/login/dev` unless `AUTH_MODE=dev`; disabled users are blocked.

## A3. Reports Home

Route: `GET /`.

Shows:
- Page title `Reports`.
- Subtitle `Run a report to view it on screen, then export to Excel.`
- Built report cards.
- Saved preset cards.
- Coming soon cards for backlog reports.
- Empty-state if user has no built report access.

Navigation in:
- Header logo, Reports nav, successful login default, impersonation start/end default.

Navigation out:
- Built normal report cards go to `/reports/<report_key>`.
- Built in-app customer-last-order card goes to `/report/customer-last-order` (deferred page).
- Preset cards deep-link to `/reports/<report_key>?<saved params>&preset=<id>`.

Controls and states:

A3.1 Built report card: shows report icon, report title, meta `Interactive - Excel export`, chevron. Click opens report viewer.

A3.2 In-app report card: shows `Pick a customer - store-visit view`; click opens customer-last-order picker. Deferred.

A3.3 Empty-state card: lock icon and text `You don't have access to any reports yet. Ask an administrator to grant access.`

A3.4 My presets section: shown only when presets exist. Each card shows bookmark icon, preset name, `<report title> - saved view`, and opens the report with saved query params plus `preset=<id>`.

A3.5 Coming soon section: shown only when backlog reports exist. Cards are disabled, not links, with clock icon and `Not built yet`.

## A4. Report Viewer Shell

Route: `GET /reports/<report_key>`.

Shows:
- Back link to Reports home.
- Report title and report help button.
- Collapsible `Filters & options` panel.
- Filter form.
- Action toolbar.
- Developer-only API preview.
- Recent exports panel.
- Status bar with Cancel.
- Report surface with tabs, metadata, and table/card layout.
- Email modal.
- Schedule modal.

Navigation in:
- Report card from Reports home.
- Preset card from Reports home.
- Floating jobs bar job row.
- Any direct deep link with filter params.

Navigation out:
- Back link goes to `/`.
- Schedule success message points the user to Schedules, but does not auto-navigate.
- Export download triggers a file download without page navigation.

Controls and states:

A4.1 Back link: labeled `Reports`; returns to `/`.

A4.2 Report help button: `?` beside title, opens help key `report-<report.key>`.

A4.3 Filters & options toggle: button with sliders icon, title, summary text, chevron. Toggles collapsed state. `aria-expanded` reflects open/closed. When collapsed, hides filters and toolbar and shows summary.

A4.4 Controls summary: when collapsed, shows selected option labels from all selects, custom date range if present, and selected customer count. Updated when controls collapse and after report load.

A4.5 Report surface hidden state: hidden until a report payload loads or a resumed job finishes. After load, the controls panel collapses before table height is measured.

A4.6 Toolbar enabled state: `Refresh data`, `Columns`, `Reset view`, `Export`, `Email`, `Schedule`, and `Save view` are disabled until data is loaded. `Presets` and `Recent exports` remain available. `Columns` is disabled on commission-card tabs.

A4.7 Dynamic table height: grid height is recalculated from the table top to the top of the fixed bottom nav, with a minimum of 220px. Recalculated after controls collapse/expand and debounced on window resize.

## A5. Report Filters And Deep Links

Route: same report viewer route, `/reports/<report_key>`.

Controls and states:

A5.1 Period select: shown only when the report declares `period`. Options come from server. Help button opens `param-period`.

A5.2 Custom date fields: `From` and `To` date inputs. Hidden unless Period value is `custom`. Included in run params only when non-empty.

A5.3 Status select: shown only when report declares `status`. Options come from server. Help button opens `param-status`.

A5.4 Year select: shown only when report declares `year`. Options are descending current year back to D365 go-live year. Help button opens `param-year`.

A5.5 Salesman select: shown only when report declares `salesman`. Starts with `All salesmen`, then loads `/api/reports/<report_key>/salesmen`. If user is scoped, server only returns visible salesmen. Help button opens `param-salesman`.

A5.6 Salesman lookup status: inline italic status beside label. Shows `(loading...)` while lookup cache warms, `(using cached list)` on lookup error, blank when ready or not configured.

A5.7 Salesman change behavior: clears all selected customers, reloads the customer list with `?salesman=<selected>`, and refreshes API preview if open.

A5.8 Customer picker: shown only when report declares `customers`. Rendered as custom combobox plus separate selected pills. Help button opens `param-customers`.

A5.9 Customer search field: placeholder `All customers`; focus or typing opens the option list. Searches by account key or name. Options are positioned fixed under the field so the filter panel cannot clip them.

A5.10 Customer option list: shows up to 200 matches. Each row has a checkbox and text `<account> - <name>`. Empty states are `No matches` or `Loading...`.

A5.11 Customer checkbox: checking adds account to `selectedCustomers`; unchecking removes it. Refreshes selected pills and API preview if open.

A5.12 Customer selected pill: shows `<name> x`; click removes that customer, rerenders options if the picker is open, and refreshes API preview if open.

A5.13 Customer outside/Escape behavior: outside click or Escape closes the option list. Scroll and resize reposition it.

A5.14 Run report button: gathers non-empty native form fields plus selected customers as an array, then starts the durable run. If a report is already shown, it preserves layout and clears old table rows before polling.

A5.15 Inbound deep links: on page load, applies `period`, `status`, `year`, `start_date`, `end_date`, `salesman`, and comma-separated `customers` from query string. Salesman is held until options load. URL is not rewritten after form changes.

A5.16 Preset deep link: `preset=<id>` loads preset params/layout after lookups, then auto-runs once.

A5.17 Lookup warm-up polling: polls `/api/reports/lookups/status` every 2.5 seconds until ready or cached rows exist, then reloads salesmen/customers and stops polling.

## A6. Report Run, Status, Resume, Cancel

Route/API:
- `POST /api/reports/<report_key>/run`.
- `GET /api/jobs/<job_id>`.
- `POST /api/jobs/<job_id>/cancel`.
- `GET /api/reports/result/<job_id>`.
- `GET /api/reports/active`.

Controls and states:

A6.1 Starting state: status bar says `Starting...`; toolbar disabled; Run button remains re-enabled in `finally`.

A6.2 Refreshing state: if preserving layout, status says `Refreshing data...`; active layout is captured; old rows are cleared while columns remain.

A6.3 Poll loop: polls job status every second, up to 600 tries. Shows `Building report... <progress>% (<elapsed>)`.

A6.4 Reconnect handling: up to 5 consecutive poll fetch errors are tolerated. During errors status says `Building report... reconnecting (<elapsed>)`. After 5, it errors with `Lost track of the job (it may have expired) - try running again.`

A6.5 Cancel button visibility: hidden unless the active job reports `running`; queued jobs do not show Cancel.

A6.6 Cancel button: POSTs cancel URL, hides itself, sets local abort flag so polling stops, and shows `Cancelling...` then `Run cancelled.` Even if the cancel request fails, the screen stops watching.

A6.7 Success state: fetches result payload, stores `state.jobId`, clears status, loads payload, applies pending preset layout if any, enables toolbar, renders tabs/table, and collapses filters.

A6.8 Failure state: status bar shows first line of server error, trimmed to 300 chars; blank server error becomes `The report failed to build. Please try again.`

A6.9 Cancelled server state: treated as an error message `The run was cancelled.`

A6.10 Timeout state: after over 10 minutes, shows `Timed out waiting for the report (over 10 minutes). Try a narrower date range.`

A6.11 Resume on page load: asks `/api/reports/active` for queued/running/recent-success jobs. If the newest matching `report_key` is found, sets `state.jobId`, shows `Reconnecting to your report...`, polls using true elapsed age, and loads the result if already successful.

A6.12 Recent finished window: server keeps finished jobs resumable/visible for about 10 minutes.

## A7. Report Tabs And Table

Route: same report viewer route, `/reports/<report_key>`.

Shows:
- Tab bar.
- Row count and generated timestamp.
- Tabulator grid for normal tabs.
- Commission card layout for commission tabs.

Controls and states:

A7.1 Tab button: each tab is a button with tab name and caret. Click activates tab, captures the old tab layout, rebuilds the table/cards, updates active styling, and syncs Columns button availability.

A7.2 Tab metadata: shows `<row count> rows`; adds `as of <generated_at>` when present.

A7.3 Tab caret: opens tab context menu at caret position.

A7.4 Tab right-click: opens the same context menu at pointer position.

A7.5 Tab context menu Duplicate tab: clones the tab data, creates a `<name> (copy)` tab after source tab, copies the source view state, marks `_isDuplicate`, tracks `_baseKey`, and activates the duplicate.

A7.6 Tab context menu Delete tab: shown only for duplicate tabs. Deletes duplicate tab and its view state, then activates previous tab or first tab.

A7.7 Tab context menu outside click: menu closes on next outside document click.

A7.8 Normal table build: Tabulator with `fitDataTable`, natural horizontal scroll, movable columns, resizable columns, bottom and group calcs, dynamic height, no nested field separator, and placeholder `No data for these filters.`

A7.9 Column formats: money uses `$`, 2 decimals, thousands, right aligned; int uses no symbol, no decimals, right aligned; percent displays blank for empty/non-finite and otherwise value times 100 with 1 decimal and `%`; date displays `M/D/YYYY` for ISO dates; text sorts as string.

A7.10 Subtotals and grand totals: numeric money/int columns get `sum`; percent columns deliberately do not total and remain blank in calc rows.

A7.11 Sorting: Tabulator header sorting is enabled; saved sorters are captured and restored per tab. Multi-sort behavior comes from Tabulator.

A7.12 Column reorder: drag columns in the grid. Captured as field order and restored per tab, preserving newly added server columns at the end.

A7.13 Column resize: drag column border; width is captured immediately and restored per tab and in saved layouts.

A7.14 Column freeze: header menu `Freeze / unfreeze` toggles frozen field set and rebuilds the table.

A7.15 Column hide by header menu: header menu `Hide column` hides the field, adds it to hidden set, and keeps the Columns panel in sync.

A7.16 Group by this column: header menu sets `group` to that column and applies Tabulator grouping.

A7.17 Clear grouping: header menu clears group set and disables grouping.

A7.18 View capture: switching tabs, saving layout, exporting, emailing, scheduling, or refreshing captures sorters, order, hidden columns, widths, and current filters for the active tab.

A7.19 Layout-preserving refresh: fresh server payload keeps previous active tab, tab order, duplicated tabs, per-tab hidden/frozen/order/sort/filter/group/widths, and recreates duplicates from their refreshed base tabs.

A7.20 Reset view: replaces active tab view with a fresh view and rebuilds that tab.

A7.21 Commission cards layout: for tabs with `layout == "commission_cards"`, grid is replaced with cards per salesman. Each card shows `<salesman_number> - <salesman_name>`, total payable, commission percent, month rows with net commission and commission, and YTD footer. If no cards, shows `No commissions for this period.`

## A8. Per-Column Filter Popover

Route: same report viewer route, normal Tabulator tabs only.

Controls and states:

A8.1 Funnel button: each column header contains label plus filter funnel. Clicking funnel opens popover and stops sort click. Active filter adds highlighted `has-active-filter` state.

A8.2 Toggle same funnel: clicking the same open funnel closes it. Clicking another funnel switches the popover to that column.

A8.3 Popover position: fixed under funnel, nudged left to fit 240px panel within viewport.

A8.4 Operator select for text: `contains`, `equals`, `starts with`, `ends with`, `is one of (comma-separated)`, `is empty`, `is not empty`.

A8.5 Operator select for numeric money/int/percent: `equals`, `not equal to`, `greater than`, `greater than or equal`, `less than`, `less than or equal`, `between`, `is empty`, `is not empty`.

A8.6 Operator select for date: `on`, `before`, `after`, `between`, `is empty`, `is not empty`.

A8.7 Value inputs: text/number/date type based on column. `between` shows two inputs; `empty` and `notEmpty` show none. Text `in` placeholder is `a, b, c`.

A8.8 Apply button: stores the filter if required value exists, or deletes it when value is blank; applies all active column filters as one Tabulator function filter so totals recalc on filtered rows; closes popover.

A8.9 Enter key: pressing Enter in either value input applies the filter.

A8.10 Clear button: deletes this column filter, reapplies filters, and closes popover.

A8.11 Outside/Escape close: Escape closes; outside click closes after the opening click has passed.

A8.12 Filter semantics: numeric filters strictly parse numbers after removing `$`, comma, `%`, and spaces; dates compare first 10 chars; text comparisons are case-insensitive. `in` splits comma-separated values.

## A9. Report Toolbar, Exports, Columns, Presets, API Preview

Route/API:
- Export start: `POST /api/reports/<report_key>/export/<job_id>`.
- Export download: `GET /api/reports/exports/<export_id>/download`.
- Recent exports: `GET /api/reports/exports`.
- Presets: `GET/POST /api/reports/<report_key>/presets`.
- One preset: `GET/DELETE /api/reports/presets/<preset_id>`.
- API preview: `POST /api/reports/<report_key>/preview-body`, developer only.

Controls and states:

A9.1 Refresh data: re-runs the report with current filters and preserves layout. Disabled until data exists.

A9.2 Columns button: opens/closes columns panel. Disabled until data exists and disabled on commission-card tabs.

A9.3 Columns panel: one checkbox per column, checked when visible. Unchecking hides column and stores it in hidden set; checking shows it and removes hidden state.

A9.4 Columns Show all: clears hidden set, shows every column, and checks every checkbox.

A9.5 Columns outside click: clicking outside panel closes it. The button itself does not trigger outside close.

A9.6 Reset view: resets only active tab's view state to defaults and rebuilds. Disabled until data exists.

A9.7 Export: requires a successful report job. If no job, status says `Run the report first, then export.` On click, sends serialized layout so the workbook mirrors on-screen tabs/order/clones/views.

A9.8 Export start success: status says `Your Excel file is building in the background - see Recent exports.` Recent exports reloads immediately, and export job polling starts.

A9.9 Export error mapping: 404 -> result expired/re-run; 409 -> report not ready/run first; 413 -> too large/hide columns or narrow date range; other -> HTTP status retry message.

A9.10 Export poll: polls `/api/jobs/<export_id>` every 1.5 seconds up to 600 tries. Reloads Recent exports each tick.

A9.11 Export auto-download: when export succeeds, auto-downloads once only if page is visible and still on the same report key that started the export. If user navigated away or tab hidden, no surprise download.

A9.12 Export failure/cancelled: if current status line is still the export message, shows job error or `The export failed. Please try again.`

A9.13 Recent exports button: toggles panel. Panel loads recent exports when opened and is also loaded once at page boot to pick up in-flight exports.

A9.14 Recent exports empty state: `No exports yet. Click Export to build one.`

A9.15 Recent exports success ready row: shows report title or filename and a Download button, with file size when available.

A9.16 Recent exports success expired row: shows `Expired - export again` in failed styling.

A9.17 Recent exports failure/cancelled row: shows `Failed: <error>` or `Failed`.

A9.18 Recent exports queued/running row: shows `Building... <progress>%`. While any row is building, the panel polls every 2 seconds; polling stops when none are building.

A9.19 Email button: opens Email report modal. Disabled until data exists.

A9.20 Schedule button: opens Schedule report modal. Disabled until data exists.

A9.21 Save view: prompts browser `Save this view as:`. If a nonblank name is entered, POSTs name, current params, and serialized layout. Success status says `Saved "<name>".`; failure says `Could not save this view. Please try again.`

A9.22 Presets button: opens/closes saved-view panel. Available before data exists.

A9.23 Presets empty state: `No saved views yet. Use "Save view".`

A9.24 Presets row open: clicking preset name closes panel, applies saved params, stores layout as pending, then runs the report. Layout is applied after result load.

A9.25 Presets row delete: `x` button confirms `Delete "<name>"?`, DELETEs preset, then removes row from panel. Question: if the last preset is removed, panel does not render the empty message until reopened; likely acceptable but note for rebuild.

A9.26 Presets outside click: closes panel when clicking outside it and outside the button.

A9.27 API preview button: developer-only toolbar button. Opens/closes editable textarea and `Run with this body` row. Question: dev diagnostic, not a normal user feature; keep for developer role unless explicitly dropped.

A9.28 API preview content: when open, POSTs current collected filters to preview endpoint and shows only the stored-procedure request body as formatted JSON. If endpoint returns warning, prepends it as `// <warning>`.

A9.29 API preview live refresh: while open, form input/change and customer changes debounce refresh by 300ms.

A9.30 Run with this body: parses textarea JSON and starts a report run with that object as override params. Invalid JSON shows status `Invalid JSON in the API preview. Fix it and try again.`

## A10. Email Report Modal

Route/API:
- Modal is on `/reports/<report_key>`.
- Delivery starts with `POST /api/reports/<report_key>/email-now`.
- Polls `GET /api/jobs/<job_id>`.
- SharePoint status: `GET /api/sharepoint/status`.
- SharePoint folders: `GET /api/sharepoint/folders?path=<path>`.

Shows:
- Modal title `Email report`.
- Recipients input.
- Subject input.
- Optional SharePoint picker section.
- Message area.
- Cancel and Send buttons.

Controls and states:

A10.1 Open Email: clears recipients, sets subject to `document.title` or `Report`, clears message, opens modal, initializes SharePoint picker.

A10.2 Recipients input: comma-style placeholder `name@achimonline.com, other@achimonline.com`. Sent as raw recipients string; server validates recipient parsing.

A10.3 Subject input: prefilled from page title; sent trimmed.

A10.4 SharePoint section visibility: hidden when `/api/sharepoint/status` is missing or `enabled` false. Shown when SharePoint access is enabled.

A10.5 SharePoint configured status: if enabled but not configured, status text says `(mock folders in dev)`.

A10.6 SharePoint breadcrumb: starts at `Root`; each path segment is a clickable crumb. Always includes `Use this folder`.

A10.7 SharePoint folder list: shows folder buttons from current path; clicking a folder loads that path. If no folders, shows `No subfolders here.`

A10.8 Use this folder: records current path as selected and shows `Will save to: <path>` or `Will save to: Direct Reports (root)`.

A10.9 Email modal Cancel/close/background: close button, Cancel button, or clicking modal overlay background hides modal.

A10.10 Send validation: requires at least one recipient or selected SharePoint folder. If missing, message says `Enter at least one recipient or pick a SharePoint folder.`

A10.11 Send action: disables Send, shows `Sending...`, POSTs recipients, subject, sharepoint path, current params, and serialized layout. This queues delivery; it does not reuse the already loaded result directly.

A10.12 Send accepted: expects HTTP 202 and `job_id`, then polls job up to 60 seconds.

A10.13 Delivery success: message `Delivered.`, then closes modal after 1.2 seconds.

A10.14 Delivery failure/cancelled: shows job error or `Delivery failed.`

A10.15 Delivery still processing: after 60 poll ticks without terminal state, shows `Still processing - check the outbox shortly.`

A10.16 SharePoint-save question: run-state says SharePoint save needs confirmation during Phase 1. Keep inventory item, but treat exact first-cut inclusion as open.

## A11. Schedule Report Modal

Route/API:
- Modal is on `/reports/<report_key>`.
- Creates schedule with `POST /api/schedules`.
- Uses same SharePoint status/folders APIs as email.

Shows:
- Modal title `Schedule report`.
- Recipients input.
- Frequency select.
- Time input.
- Weekly day checkboxes when weekly.
- Monthly day number when monthly.
- Optional SharePoint picker.
- Message area.
- Cancel and Save schedule buttons.

Controls and states:

A11.1 Open Schedule: clears recipients, clears message, syncs cadence fields, opens modal, initializes SharePoint picker.

A11.2 Recipients input: placeholder `name@achimonline.com, other@achimonline.com`.

A11.3 Frequency select: values `daily`, `weekly`, `monthly`.

A11.4 Time input: default `08:00`.

A11.5 Weekly days: shown only when frequency is weekly; checkboxes Mon=0 through Sun=6. Save requires at least one day when weekly.

A11.6 Monthly day: shown only when frequency is monthly; number input min 1 max 28 default 1.

A11.7 Schedule SharePoint picker: same picker behavior as Email modal, with its own selected path and status elements.

A11.8 Schedule modal Cancel/close/background: close button, Cancel button, or clicking overlay background hides modal.

A11.9 Save validation: requires recipients or selected SharePoint folder. If missing, message says `Enter recipients or pick a SharePoint folder.`

A11.10 Cadence validation: weekly requires at least one day. Invalid cadence shows `Pick at least one day of the week.` or `Invalid cadence.`

A11.11 Save action: disables Save, shows `Saving...`, POSTs report key, recipients, sharepoint path, cadence, current params, and serialized layout.

A11.12 Save success: expects HTTP 201, shows `Schedule saved. Manage it under Schedules.`, closes after 1.4 seconds.

A11.13 Save failure: shows server error or `Could not save the schedule.`

## A12. Settings Screen

Route/API:
- `GET /settings`.
- Theme form posts to `POST /settings/theme`.
- Header toggle and future preference writes use `POST /api/settings/preferences`.
- Admin feature flags use `POST /api/admin/feature-flags`.

Shows:
- Page title `Settings`.
- Profile card.
- Appearance card.
- Admin card for admin/developer only.

Navigation in:
- Settings bottom nav.
- Back links from admin pages.

Navigation out:
- Users & access link goes to `/admin/users`.
- Manage master schedules link goes to `/master-schedules` (deferred).
- Report run log link goes to `/admin/run-log` (deferred).

Controls and states:

A12.1 Profile card: read-only name, email, role.

A12.2 Theme select: `Light`, `Dark`, `Monochrome`, `Monochrome Dark`; current theme selected.

A12.3 Save theme button: submits form with CSRF to `/settings/theme`, persists session/user preference, flashes `Theme set to <theme>.`, and redirects back to settings.

A12.4 Admin links: shown only for admin/developer. Buttons to Users & access, Manage master schedules, and Report run log.

A12.5 Feature flags list: shown only for admin/developer and only when flags exist. Each row shows a switch, display name from key, and description.

A12.6 Feature flag help: `?` opens help key `settings-feature-flags`.

A12.7 Feature flag toggle: on change, disables the checkbox, optimistically keeps new state, POSTs `{key, enabled}` with CSRF. If request fails, checkbox rolls back. It is re-enabled in all cases.

## A13. Admin Users And Access

Route/API:
- `GET /admin/users`.
- `GET/POST /api/admin/users`.
- `GET/PUT/DELETE /api/admin/users/<user_id>`.
- `GET/POST /api/admin/users/<user_id>/salesman-access`.
- `GET/POST /api/admin/users/<user_id>/report-access`.
- `PUT /api/admin/salesmen/<key>`.

Shows:
- Back link to Settings.
- Page title `Users & access`.
- Subtitle `<n> users. Roles and per-salesman scope are enforced live from the database.`
- Add user details panel.
- Users table.
- Salesmen table.
- Edit user modal.
- Edit salesman modal.

Navigation in:
- Settings admin link.

Navigation out:
- Back link returns to `/settings`.

Controls and states:

A13.1 Add user details disclosure: native `<details>` titled `Add user`; expands/collapses form.

A13.2 Add user email: required email input, placeholder `name@achimonline.com`.

A13.3 Add user role: select with valid roles.

A13.4 Add user display name: optional text input.

A13.5 Add user external login: checkbox.

A13.6 Add user button: POSTs JSON to `/api/admin/users`; on success reloads page; on failure writes server error or `Failed to add user`.

A13.7 User search: filters user table rows live by email or display name, case-insensitive.

A13.8 User table: columns Email, Name, Role, Flags, actions. Each row stores data attrs for id, email, name, role, active, external, dashboard, sharepoint, test.

A13.9 User flag chips: shows Disabled, Dashboard, SharePoint, Test, External based on row state.

A13.10 Edit user button: opens modal for row.

A13.11 Edit user modal open state: title `Edit <email>`; fills role and checkboxes from row data; clears message; fetches current salesman access and report access, then checks relevant salesman boxes and sets each report select.

A13.12 Edit user role select: roles list.

A13.13 Edit user Active checkbox: controls whether user can sign in.

A13.14 Edit user Dashboard checkbox: controls dashboard access.

A13.15 Edit user SharePoint checkbox: controls SharePoint access.

A13.16 Edit user Test-site checkbox: controls Test Site link/access.

A13.17 Edit user External checkbox: controls external login flag.

A13.18 Per-salesman access grid: checkbox per salesman, label `<display> (<number>)`. Applies to non-privileged roles; privileged roles see all.

A13.19 Per-report access overrides: row per built report, select `Inherit`, `Allow`, `Deny`. Inherit uses role default.

A13.20 Delete user button: confirms `Delete this user and all their saved data?`; DELETEs user; reloads on success; shows error on failure. Server rejects deleting own account.

A13.21 Edit user Cancel/close/background: modal close button, Cancel button, or clicking overlay hides modal.

A13.22 Edit user Save: PUTs user core fields. If successful, POSTs selected salesman keys and every report override, then reloads page. If core save fails, shows server error or `Save failed`.

A13.23 Salesmen table: columns Number, Name, Active in dropdowns, actions.

A13.24 Salesman active toggle: PUTs `{is_active}` to `/api/admin/salesmen/<key>`; disables while saving; rolls back checkbox if request fails.

A13.25 Edit salesman button: opens modal populated from row data.

A13.26 Edit salesman modal Number input: editable salesman number.

A13.27 Edit salesman modal Full name input: editable full name.

A13.28 Edit salesman modal Display name input: editable dropdown/display name.

A13.29 Edit salesman Cancel/close/background: modal close button, Cancel button, or clicking overlay hides modal.

A13.30 Edit salesman Save: PUTs number/full_name/display_name. Reloads on success; shows server error or `Save failed` on failure.

## A14. Impersonate Screen

Route/API:
- `GET /impersonate`.
- `POST /impersonate`.
- `POST /impersonate/end` exists server-side.

Shows:
- Centered auth card.
- Title `Impersonate User`.
- Subtitle `Signed in as <principal>. Select a user to see their view.`
- Details section per role.
- Button per user.
- Inactive account note.

Navigation in:
- Direct URL, intended for admin/developer only.

Navigation out:
- Selecting a user posts to `/impersonate` and redirects to Reports home (`/`) as that user.
- If not signed in, redirects to `/login`.

Controls and states:

A14.1 Role details sections: one per role with users. Salesman section opens by default. Summary label shows `<Role>s (<count>)`.

A14.2 User impersonation button: one POST form per user with CSRF and hidden target email. Button text is display name or email. Title is email plus `(inactive)` if inactive.

A14.3 Inactive user styling: inactive buttons use muted style and add `*` after display text.

A14.4 Inactive note: `* = inactive account`.

A14.5 Server guard states: cannot access unless privileged; cannot nest impersonation; can include inactive users in picker but login as disabled target may be handled by later authorization.

A14.6 End impersonation route question: `/impersonate/end` restores the real user, but no visible button or link was found in the shell/template. Current visible exits are Sign Out and dev Switch User. Rebuild should either expose end-impersonation intentionally or confirm this hidden route is enough.

## A15. Deferred Screens To Note Only

A15.1 Dashboard: bottom nav item and notification badge exist; dashboard page itself is deferred.

A15.2 Customer Last Order: Reports home may link in-app reports to `/report/customer-last-order`; picker/view/API exist but are deferred.

A15.3 Schedules list: bottom nav and schedule modal success text point to `/schedules`; list/history row actions exist in `schedules.ts` but page is deferred.

A15.4 Master schedules: Settings admin link goes to `/master-schedules`; master schedule form and SharePoint picker exist in `schedules.ts` but page is deferred.

A15.5 Report run log: Settings admin link goes to `/admin/run-log`; page is deferred.

## A16. Cross-Cutting Frontend Requirements

A16.1 Themes: four themes must keep using shared tokens: light, dark, monochrome, monochrome dark. Tabulator headers, rows, calc rows, menus, edit lists, modals, buttons, badges, and alerts must use theme tokens.

A16.2 Mobile shell: viewport disables user scaling; bottom nav respects safe-area inset; body reserves bottom nav height; report jobs button sits above bottom nav.

A16.3 Mobile report filters: below 600px, filter row wraps and Run report becomes full-width.

A16.4 Horizontal table scroll: report grid uses natural-width table inside `.report-table-scroll`; the whole page should not grow horizontally.

A16.5 Hidden overrides: CSS has explicit `[hidden]` overrides for buttons, status, API run wrap, modal overlay, and report jobs panel because flex/grid display rules otherwise break hidden state. Rebuild must keep hidden state reliable.

A16.6 Accessibility basics present today: modal `role="dialog"` and `aria-modal`, `aria-labelledby`, help button labels, selected customers aria-label, controls toggle `aria-expanded`/`aria-controls`, combobox role for customer search.

A16.7 CSRF: every state-changing form/fetch includes CSRF token, either hidden form field or `X-CSRF-Token`.

A16.8 No long-running work in request UI: report run, export, email, and schedule deliveries all enqueue durable jobs and poll status rather than blocking the request.

A16.9 Saved layout shape: layout must preserve active tab, tab order, duplicated client-only tabs, per-tab hidden/frozen/order/sorters/columnFilters/group/widths, params, and cloned tab base keys.

A16.10 Export/view parity: export sends serialized layout so server workbook mirrors on-screen tab order, duplicate tabs, hidden columns, grouping, filters, and widths where supported.

A16.11 Bolted-on/unused questions:
- Developer API preview is useful but not a normal user workflow.
- Test Site bottom-nav link may be deployment-era scaffolding.
- v3 header marker is explicitly removable at cutover.
- `order_entry_enabled` is injected into globals but no Area A template uses it.
- `/impersonate/end` has no visible control in inventoried templates.
- SharePoint save is implemented in email/schedule modals, but run-state says first-cut inclusion must be confirmed.
