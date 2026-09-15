# FEATURE-INVENTORY — live v3 (go-live)

**Date:** 2026-09-02
**Source of truth:** current production Flask app in `/workspace/v3/`, URL https://reports.achimonline.com
**Not** the unfinished `/test-next` tree under `rebuild/`.
**Auditors:** Sol + Fable per area (see `go-live/rebuild-audit/*.inventory.md` and `*.structure.md`). History: `go-live/BUILD-HISTORY.md`.
**CodeGraph:** CLI missing; parent graph-backbone + named-file Read.
**KEEP everything.** To-fix items (`F*`) are structure/security notes, not drop candidates.

Column-level builder math lives in `go-live/rebuild-audit/reports-excel.inventory.md` §3. Do not drop a tab or column because it is not restated below.

---

## Route manifest

Every row must have a working counterpart after any rebuild. Click-through tests this list.

### Pages (HTML)

| ID | Method | Path | Template | Notes |
|----|--------|------|----------|-------|
| P1 | GET | `/login` | `login.html` | Beta: Live + magic-link modal. `/test`/dev: email+role. MSAL: redirect. |
| P2 | GET | `/` | `reports_list.html` | Report cards, company views, my presets, coming soon |
| P3 | GET | `/reports/<report_key>` | `report_view.html` | Grid; CLO key redirects to P4 |
| P4 | GET | `/report/customer-last-order` | `customer_last_order_pick.html` | |
| P4.1 | GET | `/report/customer-last-order/<account>` | `customer_last_order_view.html` | |
| P5 | GET | `/schedules` | `schedules.html` + wizard include | Personal |
| P5.1 | GET | `/schedules/<id>/history` | `schedule_history.html` | |
| P6 | GET | `/settings/company-schedules` | `company_schedules.html` | Privileged |
| P6.1 | GET | `/master-schedules` | redirect → P6 | |
| P6.2 | GET | `/master-schedules/<id>/history` | `schedule_history.html` | |
| P7 | GET | `/settings` | `settings.html` | |
| P8 | GET | `/admin/users` | `admin_users.html` | Privileged; non-privileged gets JSON 403 |
| P9 | GET | `/dashboard` | `dashboard.html` | **Not mounted on Beta `/`** |
| P9.1 | GET | `/customer/<account>` | `customer_detail.html` | Live `/test` only |
| P10 | GET | `/admin/run-log` | `run_log.html` | Privileged |
| P10.1 | GET | `/admin/schedule-runs` | `schedule_runs.html` | Privileged |
| P11 | GET | `/dev/db-explorer` | `db_explorer.html` | DB developer |
| P12 | GET | `/dev/notif-diagnostic` | `notif_diagnostic.html` | DB developer |
| P13 | GET | `/dev/role-picker` | `role_picker.html` | Switch user; DB developer |
| P14 | GET | `/impersonate` | `impersonate.html` | `/test`; dead on Beta (F4) |
| P15 | GET | `/healthz` | JSON | No auth |
| P15.1 | GET | `/manifest.json` | JSON PWA | No auth |

### Auth / session APIs

| ID | Method | Path |
|----|--------|------|
| R-A1 | POST | `/login/dev` |
| R-A2 | GET/POST | `/auth/callback` |
| R-A3 | POST | `/logout` |
| R-A4 | POST | `/dev/role-picker` |
| R-A5 | POST | `/impersonate` |
| R-A6 | POST | `/impersonate/end` |

### Admin APIs

| ID | Method | Path |
|----|--------|------|
| R-U1 | GET/POST | `/api/admin/users` |
| R-U2 | PUT/DELETE | `/api/admin/users/<id>` |
| R-U3 | GET/POST | `/api/admin/users/<id>/salesman-access` |
| R-U4 | GET/POST | `/api/admin/users/<id>/report-access` |
| R-U5 | GET | `/api/admin/sales-groups` |
| R-U6 | PUT | `/api/admin/salesmen/<key>` |
| R-U7 | GET | `/api/admin/exports` |

### Report APIs (43 handlers; full list in reports-excel.inventory.md §4)

| ID | Method | Path |
|----|--------|------|
| R-R1 | POST | `/api/reports/<key>/run` |
| R-R2 | GET | `/api/jobs/<id>` |
| R-R3 | POST | `/api/jobs/<id>/cancel` |
| R-R4 | GET | `/api/reports/result/<id>` |
| R-R5 | GET | `/api/reports/active` |
| R-R6 | POST | `/api/reports/runs/<id>/keep` |
| R-R7 | POST | `/api/reports/<key>/export/<job_id>` |
| R-R8 | GET | `/api/reports/exports/<id>/download` |
| R-R9 | GET | `/api/reports/exports` |
| R-R10 | GET | `/api/reports/lookups/status` |
| R-R11 | GET | `/api/reports/<key>/salesmen` |
| R-R12 | GET | `/api/reports/<key>/customers` |
| R-R13 | GET | `/api/reports/<key>/years` |
| R-R14 | POST | `/api/reports/<key>/preview-body` |
| R-R15 | * | `/api/saved-reports`, presets, default-view, company-views CRUD |
| R-R16 | POST | `/api/reports/<key>/email-now` |
| R-R17 | GET | `/api/sharepoint/status`, `/folders` |
| R-R18 | GET | `/api/onedrive/status`, `/folders` |
| R-R19 | GET | CLO customers/salesmen/recent-invoiced; GET CLO export |
| R-R20 | * | diagnostics: reporting-api, reconcile-*, claim-once, precious-repair |

### Schedule APIs

| ID | Method | Path |
|----|--------|------|
| R-S1 | GET | `/api/schedules/recent-runs` |
| R-S2 | POST | `/api/schedules` |
| R-S3 | PUT | `/api/schedules/<id>` |
| R-S4 | POST | `/api/schedules/<id>/toggle` |
| R-S5 | DELETE | `/api/schedules/<id>` |
| R-S6 | POST | `/api/schedules/<id>/run` |
| R-S7 | POST | `/api/schedules/<id>/copy` |
| R-S8 | GET | `/api/schedules/views` |
| R-S9 | GET | `/api/master-schedules/lookups/{status,salesmen,salesmen-emails,customers}` |
| R-S10 | POST | `/api/master-schedules` |
| R-S11 | PUT | `/api/master-schedules/<id>` |
| R-S12 | POST | `/api/master-schedules/<id>/{copy,toggle,run}` |
| R-S13 | DELETE | `/api/master-schedules/<id>` |

### Settings / dashboard / dev APIs

| ID | Method | Path |
|----|--------|------|
| R-T1 | POST | `/settings/theme` |
| R-T2 | POST | `/api/settings/preferences` |
| R-T3 | GET/POST | `/api/settings/customers`, `/api/settings/exclusions` |
| R-T4 | POST | `/api/admin/feature-flags`, `/report-visibility`, `/schedule-test` |
| R-T5 | GET/POST | `/api/dev/beta-sources` |
| R-D1 | POST | `/api/dashboard/refresh` |
| R-D2 | GET | `/api/dashboard/refresh-status` |
| R-D3 | POST | `/api/dashboard/exclusion` |
| R-D4 | GET/POST | `/api/notifications`, `/api/notifications/dismiss` |
| R-X1 | GET | `/api/dev/db/tables`, `/api/dev/db/table/<table>` |
| R-X2 | POST/DELETE | `/api/dev/db/table/<table>/cell`, `/row` |
| R-X3 | GET/POST | `/api/dev/notif-diagnostic/<email>` (+ `/run`) |

**Mounts (root `wsgi.py`):** `/` = v3 Beta (Live cookie, no dashboard); `/test` = v3 with `v3_session` + dashboard; `/legacy` = old Live app. Separate sqlite files per mount.

---

## P1 — Login (`/login`)

**Old files:** `web/blueprints/auth.py`, `login.html`, `beta_live_session.py`, `msal_flow.py`

| ID | Control | Behavior |
|----|---------|----------|
| P1.1 | Achim User Login | Beta: `/legacy/login/start?next=` |
| P1.2 | External Rep Login modal | Email → POST `/legacy/login/magic-link`; close ×/Cancel/overlay/Esc |
| P1.3 | Dev sign-in | Email, role select (4 roles), Sign in → POST `/login/dev` (not on Beta; `AUTH_MODE=dev` only) |
| P1.4 | MSAL | Redirect Entra; return `/auth/callback` |
| P1.5 | `next` sanitizer | Same-app `/…` only; Beta default `/`; non-Beta fallback `healthz` (F11) |

---

## P13 — Switch user (`/dev/role-picker`)

| ID | Control | Behavior |
|----|---------|----------|
| P13.1 | Back | Reports |
| P13.2 | View as Admin (yourself) | `__self__` (cookie role hardcoded admin — F6) |
| P13.3 | Search | Filters groups |
| P13.4 | Radio list | Admins/Developers/Managers/Salesmen; self disabled; Live+v3 merge |
| P13.5 | View as Selected User | Writes Live cookie + adopt |

Requires active DB developer. Header Switch user only if `_dev`.

---

## P14 — Impersonate (`/impersonate`) — `/test` only

| ID | Control | Behavior |
|----|---------|----------|
| P14.1 | User buttons by role | POST impersonate; inactive muted |
| P14.2 | End | POST `/impersonate/end` (no header button found — F12) |

On Beta, next request undoes this via `adopt_live_identity` (F4). KEEP the `/test` path.

---

## Shared chrome (`base.html` + `main.ts`) — every signed-in page

| ID | Control | Behavior |
|----|---------|----------|
| C1 | Logo | → P2 |
| C2 | Beta / v3 badges | |
| C3 | Name or Viewing-as badge | Missing when impersonating admin (F13) |
| C4 | Role badge | |
| C5 | Recent Reports | Poll `/api/reports/active` 5s; rows → `?job=`; Keep rename |
| C6 | Theme cycle | light → dark → monochrome → monochrome_dark |
| C7 | Switch user | if `_dev` |
| C8 | Sign Out | POST logout + CSRF |
| C9 | Bottom nav | Reports; Dashboard (non-Beta gated); Schedules; Test Site (flag); Settings |
| C10 | Help overlay | `help_content.js` |
| C11 | Jobs bar | Active runs |

---

## P2 — Reports home (`/`)

| ID | Control | Behavior |
|----|---------|----------|
| P2.1 | Built report cards | 8 BUILT keys; CLO → P4; others → P3 |
| P2.2 | Empty “no access” | |
| P2.3 | Company view cards | if `can_see_company_views`; `?cview=` |
| P2.4 | My preset cards | `?preset=` |
| P2.5 | Coming soon | `customer_aging` only; **must stay disabled** |

**Reports KEEP:** `ordered`, `invoiced`, `salesman`, `number_4`, `customer_activity`, `customer_last_order`, `item_averages`, `sales_by_state`. BACKLOG: `customer_aging`.

---

## P3 — Standard report viewer (`/reports/<key>`)

**Old files:** `report_view.html`, `report.ts`, `reports.py`, builders, `export.py`

### Filters (per `REPORT_FILTERS`)

| ID | Control |
|----|---------|
| P3.1 | Filters panel + one-line summary + `?` help |
| P3.2 | Period (8 options; custom From/To; alias yesterday→daily) |
| P3.3 | Status (Ordered) |
| P3.4 | Year |
| P3.5 | Salesman (“All salesmen”; post-filter on salesman report) |
| P3.6 | Customers (search, 200 cap, pills; salesman change clears) |
| P3.7 | Number 4 mode (both / by_customer / by_item) |
| P3.8 | Run report |
| P3.9 | Email me (run + self Excel, 60s poll) |
| P3.10 | Developer API preview + Run with this body |

### Layout / views

| ID | Control |
|----|---------|
| P3.11 | Columns (tabs + columns + Show all) |
| P3.12 | Reset layout |
| P3.13 | Save for (Me / Company / other user) — privileged |
| P3.14 | Save this view (Default reserved for personal) |
| P3.15 | Saved views panel: Default, company, mine, others; Edit; Delete |
| P3.16 | More → Schedule / API preview |
| P3.17 | Status/progress, Cancel, 10 min timeout, reconnect |

### Result / grid

| ID | Control |
|----|---------|
| P3.18 | Tabs: activate, duplicate, rename (clones), remove, restore |
| P3.19 | Refresh, Keep this run (name, cap 5, 30d) |
| P3.20 | Export: Download now / Recent exports |
| P3.21 | Email modal: To, subject, SharePoint picker |
| P3.22 | Grid: sort, widths, hide, freeze, group/subgroup/clear, filters (text/num/date), bottom sums (never Net Price / percent) |
| P3.23 | Commission cards (Invoiced; no grid) |
| P3.24 | Nested header/footer colours (shared RGB with Excel) |
| P3.25 | Salesman colour bands by field |
| P3.26 | Fulfillment % fill |

### Schedule-from-report modal

| ID | Control |
|----|---------|
| P3.27 | Email to me; extra To/CC/BCC (privileged) |
| P3.28 | Frequency daily/weekly/monthly + time + weekday/monthday |
| P3.29 | Filename tokens + preview (default `{Schedule}_{MM}-{DD}-{YYYY}`) |
| P3.30 | OneDrive / SharePoint pickers |
| P3.31 | Email me when no data; email test addresses when no data |
| P3.32 | Save schedule → 201 |

Deep links: `period,status,year,mode,salesman,start_date,end_date,customers,job,preset,cview`.

**Tabs KEEP (see auditor for columns):** Ordered 6 (By Salesman omitted if salesman filtered); Invoiced 7 conditional; Salesman 12 months; Number 4 2 or 4; CA All + per-salesman + Unassigned; Item Averages 1; Sales by State 3.

**Excel KEEP:** write-only; no outline groups; skip Net Price totals; Number 4 months-then-totals; ungrouped Default honoured; 2.5 MB Graph → link; formula injection prefix.

---

## P4 — Customer's Last Order

| ID | Control |
|----|---------|
| P4.2 | Salesman (unrestricted only) + customer search (200) |
| P4.3 | Customer row → view |
| P4.4 | Header card + add previous orders + export Excel/PDF |

---

## P5 — Personal schedules (`/schedules`)

| ID | Control |
|----|---------|
| P5.2 | One table, owner banner rows (privileged see all) |
| P5.3 | Columns: report, view, cadence, recipients, folder, last run, on/off |
| P5.4 | Edit, Run now, Copy (inactive), History, Delete |
| P5.5 | Wizard View → When → Where |
| P5.6 | Named views only for salesmen; Default extra for privileged |
| P5.7 | Privileged CC/BCC + extra To; salesman To = self |
| P5.8 | Filename preview; OneDrive default; SharePoint privileged |
| P5.9 | Recent run log poll |

Cadence, Sabbath skip (default on; Run now bypasses), catch-up windows, fail-mail 15 min, Graph retry: KEEP (`schedules-delivery.inventory.md`).

---

## P6 — Company schedules (`/settings/company-schedules`)

| ID | Control |
|----|---------|
| P6.3 | 5-step wizard Report → When → Options → Where → Review |
| P6.4 | Name, view (Default / company / preset), cadence, options, To/CC/BCC, folder, filename |
| P6.5 | Private vs shared; run-as manager |
| P6.6 | Salesman fan-out / split |
| P6.7 | Edit, Copy, Run now, History, Delete; sortable columns |
| P6.8 | Seeded views Daily Ordered + Heshy Open Orders (boot must not restore deleted names) |

---

## P7 — Settings (`/settings`)

| ID | Section | Who | Controls |
|----|---------|-----|----------|
| P7.1 | Profile | all | name, email, role (read-only) |
| P7.2 | Appearance | all | theme select + Save |
| P7.3 | Customer exclusions | all | searchable picker; scope-checked POST |
| P7.4 | People | privileged | link → P8 |
| P7.5 | Global report visibility | privileged | per-report toggles |
| P7.6 | Feature flags | privileged | dashboard / order_entry / test_site |
| P7.7 | Delivery / test mode | privileged | company schedules link; test toggle + email chips (need ≥1 email to enable) |
| P7.8 | History | privileged | run log, schedule runs |
| P7.9 | Developer | DB developer | db explorer, notif diag, Beta SQL/OData sources |

---

## P8 — Users & access (`/admin/users`)

| ID | Control |
|----|---------|
| P8.1 | Search; table Email/Name/Role/Flags/View as/Edit |
| P8.2 | Add user: email, role, display name, SalesGroup (salesman), External; 409 duplicate |
| P8.3 | Edit: display name, role (no self-role change), flags, SalesGroup or manager checkboxes, per-report Inherit/Allow/Deny, Delete (confirm Disable hint) |
| P8.4 | Salesmen master table + Edit (number, names, email, active) |
| P8.5 | Developer lifecycle: only DB developer may mint/change/disable/delete developers |

---

## P9 — Dashboard (`/dashboard`) — `/test` and Live mount, **not Beta home**

| ID | Control |
|----|---------|
| P9.2 | 5 tiles Total/New/Active/Overdue/Inactive (filter table) |
| P9.3 | Table + customer link; excluded rows shown flagged |
| P9.4 | Refresh data (poll last_refreshed) |
| P9.5 | Pull-to-refresh (touch) |
| P9.6 | Customer detail: metrics, include toggle, order history |

Status math KEEP: new <2 days → inactive >365 → overdue > mean+stdev → active.

---

## P10–P12 — History and developer tools

| ID | Page | Controls |
|----|------|----------|
| P10.2 | Run log | When, user, report, status, rows, duration, source |
| P10.3 | Schedule runs | When, label, kind, status, rows |
| P11.1 | DB explorer | precious/cache, search, cell edit, delete row |
| P12.1 | Notif diagnostic | user select, generate overdue, reason lists |

---

## Jobs / data KEEP (no page)

Job types: `report.run`, `report.export`, `report.deliver`, `schedule.run`, `dashboard.refresh`.
Statuses: queued, running, success, failure, cancelled.
Cron: schedule-tick 1 min Eastern; dashboard-mirror 4h Live only.
Precious migrations 0001–0018; cache 0001–0005.
Beta sources table lives in **Live `webapp` sqlite**.

---

## To-fix (structure auditors — KEEP behavior, note mess)

Security / go-live relevant first:

| ID | Sev | Finding | Area |
|----|-----|---------|------|
| F1 | High | OData `_scope_tab` fail-open if no known salesman column | reports |
| F2 | High | Global `dashboard_enabled` hides nav but not `/dashboard` routes | settings |
| F3 | High | `notif_diag.ts` `innerHTML` from API data (XSS in developer session) | settings |
| F4 | High | `/impersonate` undone on Beta by Live adopt | auth |
| F5 | High | Boot `seed_users_from_live` overwrites role/flags; delete resurrected, disable sticks | auth |
| F6 | Med | Role-picker “yourself” writes Live cookie role `admin` | auth |
| F7 | Med | `require_privileged` trusts session cookie (unused but trap) | auth |
| F8 | Med | Dashboard exclusion POST has no customer/scope check | settings |
| F9 | Med | `_DELIVERY_PARAM_KEYS` blueprint vs runner membership drift | schedules |
| F10 | Med | Fan-out management leg drops CC/BCC | schedules |
| F11 | Med | MSAL `next` fallback is `/healthz` | auth |
| F12 | Low | No impersonate-end control in chrome | auth |
| F13 | Low | Viewing-as badge hidden when target is admin/developer | auth |
| F14 | Low | `report_ready` badge counted, no producer | settings |
| F15 | — | God files: `reports.py` 1685, `report.ts` 3384, `schedules.py` 1222, `master_wizard.ts` 1117, `__init__.py` 861 | all |
| F16 | — | Duplicate pickers, N4 order in 3 places, theme list in 3 places | reports/settings |
| F17 | — | `skip_sabbath` has no UI writer | schedules |
| F18 | — | Non-privileged `/admin/users` returns raw JSON | auth |

**Gap check (skeleton vs inventory):** no missing pages. Reports skeleton “About this report” = P3.1 help. Schedule route count 23 vs 24 is the P6.1 redirect. Settings inventory added digest misses: `landing_page`, `default_report_tab`, `magic_link_tokens`, cache migrations, `report_ready` dormant.

---

## Click-through batches (for `GO-LIVE-TEST-LOG.md`)

1. Chrome + login + P2 cards (4 roles)
2. P3 Ordered/Invoiced/Salesman/Number4/CA/Item Averages/Sales by State + Excel
3. P4 last order Excel/PDF
4. P5 personal + P6 company + Run now + file vs expected layout
5. P7–P8 users/settings edge (409, developer boundary, exclusions)
6. P9 dashboard (`/test` only)
7. P10–P12 developer tools
8. Edge: empty data, demotion/export scope, Default vs named view, Sabbath skip (clock mock or unit)

**Local vs production:** this VM has no Entra. Browser pass uses local `AUTH_MODE=dev` on `/test` (dashboard on) plus Beta-mode notes. Production `/` is Entra + no dashboard. `/healthz` can be hit on the live URL without login.
