# FEATURE-INVENTORY — home site

**2026-09-16:** FastAPI `app/` is production. Flask `v3/` is git history only (`063d9de`). P13.2 / P13.3 (do not push `main` until cutover) are **done**. Use this file as KEEP/FIX IDs, not as a greenfield rebuild plan. Continuation: `rebuild/NEW-AGENT-PROMPT.md`.

**Source of look + features:** live https://reports.achimonline.com and current `app/` (old WHAT in `git show 063d9de:v3/`).  
**Not inventoried / do not revive:** `/legacy`, `/test`, `/test-next`.  
**Visual snapshots:** `app/rebuild-reference/`.  
**Status legend:** KEEP = must exist. FIX = capability kept, internals still wrong. DROP = only with Menny’s yes.  
**Do not port** `v3/report_engine/` as a god module.

Page-by-page from the old `v3/` templates/blueprints/registry. Architecture locked (FastAPI + JSON + Tabulator + v3 CSS). See `rebuild/BROTHER-STACK-REBUILD.md`.

---

## Route manifest (current home, `is_beta=True`)

| Route | Screen | Inventory |
|---|---|---|
| `GET /login` | Sign in | P1 |
| `POST /legacy/login/start` | Entra (today via Live) | P1.1 — FIX: own Entra, no Live cookie |
| `POST /legacy/login/magic-link` | External magic link | P1.2 |
| `POST /logout` | Sign out | P1.3 |
| `GET /healthz` | Probe | P2 |
| `GET /manifest.json` | PWA | P2.1 |
| `GET /` | Reports home | P3 |
| `GET /reports/<key>` | Report viewer | P4 |
| `GET /report/customer-last-order` | Last Order picker | P5 |
| `GET /report/customer-last-order/<account>` | Last Order store-visit | P5.1 |
| `GET /settings` | Settings hub | P6 |
| `GET /admin/users` | Users & access | P7 |
| `GET /schedules` | Personal / shared schedules | P8 |
| `GET /schedules/<id>/history` | Personal schedule history | P8.8 |
| `GET /schedules/runs/<id>` | One run log | P8.9 |
| `GET /settings/company-schedules` | Company schedule setup (flag-hidden) | P9 |
| `GET /master-schedules` | Master schedules | P9.1 |
| `GET /master-schedules/<id>/history` | Master history | P9.2 |
| `GET /admin/run-log` | Report run log | P10 |
| `GET /admin/schedule-runs` | Scheduled run history | P10.1 |
| `GET /dev/db-explorer` | Database explorer (developer) | P11 |
| `GET /dev/notif-diagnostic` | Notification diagnostic | P11.1 |
| `GET /dev/role-picker` | Role picker / View as | P12 |
| `GET /impersonate` | Impersonate (non-beta) | P12.1 |
| `GET /beta` | Old bookmark | P13 — KEEP 302 to `/` |
| `/dashboard`, `/customer/<account>` | Dashboard (not registered on home) | F1 — DROP from new app (matches live `/`) |
| `/legacy/*`, `/test/*`, `/test-next/*` | Other mounts | F2 — DROP |

JSON/API routes that back the pages above are listed under each page (must have a working control, not an orphan engine).

---

## P1 Login — `v3/web/templates/login.html` + `v3/web/blueprints/auth.py`

Live screenshot: `app/rebuild-reference/live-login.png`. Card on `#f8fafc`, title **Sales Reports**, subtitle **Sign in to continue**, primary **Achim User Login** (`#2563eb`), outline **External Rep Login**. No header/nav until signed in.

| ID | Control / behavior | Status |
|---|---|---|
| P1.1 | Achim User Login → Microsoft Entra. Today home piggybacks Live (`/legacy/login/start`). New app owns Entra. No Live-cookie provisioning. | KEEP / FIX |
| P1.2 | External Rep Login modal: email, send link from reports@achimonline.com, 15 min expiry. Only if People row is **active** + `is_external`. No self-register. | KEEP |
| P1.3 | Sign Out (header). Home today also clears Live session. New app: own cookie only. | KEEP / FIX |
| P1.4 | Dev email/role picker. Live production does **not** show this. Preview/dev only; never production. No `DEV_AUTH_BYPASS` in prod. | KEEP (dev) |
| P1.5 | Disabled account → 403. | KEEP |
| P1.6 | Safe `next=` (same-app relative only). | KEEP |

---

## P2 Health / PWA — `v3/web/blueprints/health.py`

| ID | Control / behavior | Status |
|---|---|---|
| P2.1 | `GET /healthz` → `{"status":"ok"}`. No config leak. | KEEP |
| P2.2 | Azure Always On `GET /` User-Agent `AlwaysOn` → 200 (do not 302 login). | KEEP |
| P2.3 | `manifest.json` + icons 192/512, theme-color `#2563eb`. | KEEP |

---

## P3 Reports home — `v3/web/templates/reports_list.html` + `GET /`

Nav in: bottom **Reports**. Nav out: a report card, company view, preset.

| ID | Control / behavior | Status |
|---|---|---|
| P3.1 | Page title Reports, subtitle “Run a report… Excel.” | KEEP |
| P3.2 | Cards for built in-app reports the user can see. | KEEP |
| P3.3 | Ordered card → `/reports/ordered` | KEEP |
| P3.4 | Invoiced card → `/reports/invoiced` | KEEP |
| P3.5 | Salesman card | KEEP |
| P3.6 | Number 4 card | KEEP |
| P3.7 | Customer Activity card | KEEP |
| P3.8 | Item Averages card (privileged only) | KEEP |
| P3.9 | Sales by State card | KEEP |
| P3.10 | Customer’s Last Order card → picker (not the grid viewer) | KEEP |
| P3.11 | Customer Aging “Coming soon” (BACKLOG, not clickable) | KEEP (backlog) |
| P3.12 | Company views fold (if flag/role) | KEEP |
| P3.13 | My presets fold | KEEP |
| P3.14 | Empty state if no report access | KEEP |
| P3.15 | Global report visibility off hides unless explicit allow | KEEP |

---

## P4 Report viewer — `v3/web/templates/report_view.html` + `report.ts` + Tabulator 6.3.1

Chrome: header (logo, name, role badge, Recent Reports, theme, Sign Out), bottom nav Reports / Schedules / Settings. **No Dashboard** on home. **No Test Site** unless that flag is on (home: off).

Shared controls (every grid report):

| ID | Control / behavior | Status |
|---|---|---|
| P4.1 | Back to Reports | KEEP |
| P4.2 | Title + `?` help overlay | KEEP |
| P4.3 | Filters & options collapse + summary | KEEP |
| P4.4 | Period: All Time, MTD, Last Month, YTD, This Week, Last 7 Days, Yesterday, Custom Range (+ From/To dates) | KEEP |
| P4.5 | Status (Ordered only) | KEEP |
| P4.6 | Year (Salesman, Sales by State) | KEEP |
| P4.7 | Number 4 View: Both / By Customer / By Item | KEEP |
| P4.8 | Salesman dropdown from D365 `salesmen_master` SP | KEEP |
| P4.9 | Customers picker + pills | KEEP |
| P4.10 | Run report | KEEP |
| P4.11 | Email me (run + mail Excel to self) | KEEP |
| P4.12 | Columns / Reset layout / Save this view / Saved views | KEEP |
| P4.13 | Loaded-view label | KEEP |
| P4.14 | More → Schedule (named saved view) | KEEP |
| P4.15 | Developer API preview + Run with this body | KEEP |
| P4.16 | Status line + Cancel | KEEP |
| P4.17 | Developer live job log | KEEP |
| P4.18 | Tabs bind to **`data.tabs.*.rows`** (new contract). Today Flask rebuilds tabs in `report_engine`. | FIX |
| P4.19 | Tabulator: sort, header filter, hide/show, reorder, freeze, group-by + totals, horizontal scroll. Header menu Hide / Freeze / Group. Saved on the view in `layout_*` columns (not a JSON blob). | KEEP |
| P4.20 | Commissions **card** layout (not a second math engine) | KEEP |
| P4.21 | Refresh (keep layout) | KEEP |
| P4.22 | Keep this run (30 days, max 5) + Recent Reports pill | KEEP |
| P4.23 | Export Excel (background) + Recent exports | KEEP |
| P4.24 | Email modal: recipients, subject, optional SharePoint folder | KEEP |
| P4.25 | Save view modal: name; privileged Save for Me / Company / other user; company can store date window. Saves filters + grid layout (columns/sort/group/header filters). | KEEP |
| P4.26 | Company Default view | KEEP |
| P4.27 | Salesman scope on cache key + result | KEEP |
| P4.28 | Hide commissions tab for non-privileged | KEEP |
| P4.29 | Theme cycle light / dark / monochrome / monochrome_dark (header sun/moon/aperture/disc) | KEEP |
| P4.30 | Help overlay + phone tap targets | KEEP |

Skipped as bolted-on (Menny: not every extra from the beginning of time): tab clones, TEXT view handles, silent dual-write JSON workbooks, Excel funnel popover (headerFilter input is saved as `contains`). Group/freeze are on the grid; scheduled Excel is a flat sheet with hide/order/sort/header filters applied.

### P4 Invoiced tabs (LOOK from live order in `invoiced.py`)

| ID | Tab | Status |
|---|---|---|
| P4.I1 | Summary by Customer | KEEP — grid group/filter, not a second engine |
| P4.I2 | Commissions (admin) dollars + monthly/YTD | KEEP — SQL should supply dollars; until then thin assembler from `raw` |
| P4.I3 | Full Details | KEEP |
| P4.I4 | Credits | KEEP — grid filter |
| P4.I5 | Invoices | KEEP — grid filter |
| P4.I6 | Audit - Reversals (when present) | KEEP |
| P4.I7 | Totals by Salesman (when 2+ salesmen) | KEEP — grid |
| P4.I8 | Live rows use `salesman` (e.g. HKaufman), not `SalesGroup`. Testers use admin until Menny maps. | KEEP / BLOCKED on SQL map |
| P4.I9 | Catalog `invoiced_report`; body `InvoiceDateFrom` / `InvoiceDateTo`; timeout 120s+ | FIX (doorway only) |
| P4.I10 | Commission: SP fraction; per-invoice rate; 0 stays 0; display master percent | KEEP (Q1–Q3) |

### P4 Ordered tabs

| ID | Tab / rule | Status |
|---|---|---|
| P4.O1 | Summary, By Customer, By Item, By Order, By Salesman, Full Data | KEEP |
| P4.O2 | Summary group by **CustomerAccount** (Q4) | KEEP |
| P4.O3 | Open $ and Fulfillment % from SQL eventually | FIX |
| P4.O4 | Catalog `ordered_report`; `CreatedDateTimeFrom` / `To` | FIX |
| P4.O5 | Status + customers + salesman filters | KEEP |

### P4 Other reports

| ID | Report | Tabs / notes | Status |
|---|---|---|---|
| P4.S1 | Salesman | Month tabs from `monthly_salesman_yoy` (already SQL dollars) | KEEP |
| P4.N1 | Number 4 | By Customer / By Item × rolling-12 + YTD | KEEP; YTD → SQL eventually |
| P4.C1 | Customer Activity | All + per-salesman + Unassigned (grid split) | KEEP |
| P4.A1 | Item Averages | Per-item Avg/Month ÷12, Avg/Week ÷52 — SQL eventually | KEEP / FIX |
| P4.ST | Sales by State | Summary, New York City, Detail (3 SPs, already SQL) | KEEP |

---

## P5 Customer’s Last Order — `customer_last_order_pick.html` + `_view.html`

| ID | Control / behavior | Status |
|---|---|---|
| P5.1 | Pick customer (search) + salesman filter | KEEP |
| P5.2 | Store-visit view for one account | KEEP |
| P5.3 | Recent invoiced helper | KEEP |
| P5.4 | Export | KEEP |

---

## P6 Settings hub — `settings.html` (~800px `container-narrow`)

| ID | Control / behavior | Status |
|---|---|---|
| P6.1 | You → Profile (name, email, role) | KEEP |
| P6.2 | You → Appearance theme select + Save | KEEP |
| P6.3 | You → Customer exclusions picker | KEEP |
| P6.4 | People → Users & access (admin) | KEEP |
| P6.5 | Reports → global visibility toggles | KEEP |
| P6.6 | Reports → feature flags (admin) | KEEP |
| P6.7 | Delivery → schedule test mode + test email chips | KEEP |
| P6.8 | Delivery → Company schedules link (hidden unless `SHOW_COMPANY_SCHEDULE_SETUP`) | KEEP (flag) |
| P6.9 | History → Report run log, Scheduled run history | KEEP |
| P6.10 | Developer → Database explorer, Notification diagnostic, precious.db upload | KEEP |
| P6.11 | Developer → Beta SQL/OData sources | **DROP** (locked: no OData in new app) |

---

## P7 Users & access — `admin_users.html`

| ID | Control / behavior | Status |
|---|---|---|
| P7.1 | List + search | KEEP |
| P7.2 | Add user: email, role, display name, SalesGroup, External login | KEEP |
| P7.3 | No self-register (Q8) | KEEP |
| P7.4 | Edit: role, flags (active, dashboard, SharePoint, Test, Company views, external), SalesGroup | KEEP |
| P7.5 | Per-user salesman access checkboxes from D365 master | KEEP |
| P7.6 | Per-user report allow/deny | KEEP |
| P7.7 | View as (developers) | KEEP |
| P7.8 | Magic link only if active + is_external | KEEP |

Roles: admin, developer, manager, salesman. View-only managers: Send now on **shared** company schedules only (Q9).

---

## P8 Schedules — `schedules.html` + personal wizard

| ID | Control / behavior | Status |
|---|---|---|
| P8.1 | Add a schedule (needs a named view). Schedule points at `view_id` and does not copy layout. Delivery applies that view’s columns/sort/filters. | KEEP |
| P8.2 | Wizard: View → When → Where | KEEP |
| P8.3 | Freq daily/weekly/monthly, weekdays, month-day, time | KEEP |
| P8.4 | Where: email, CC/BCC (privileged), subject/body chips `{Schedule}` `{Period}` `{SharePointUrl}` `{DownloadButton}` | KEEP |
| P8.5 | Filename chips | KEEP |
| P8.6 | OneDrive and/or SharePoint folder | KEEP |
| P8.7 | Run now / toggle / copy / delete | KEEP |
| P8.8 | History per schedule | KEEP |
| P8.9 | Per-run Log (Time, Step, Detail) | KEEP |
| P8.10 | Recent run log on the page; Clear stuck (admin/dev) | KEEP |
| P8.11 | Test-mode banner | KEEP |
| P8.12 | Hebcal Brooklyn: hold if no calendar covers now; skip Shabbos/Yom Tov; catch-up rules as live (Q5) | KEEP |
| P8.13 | 45 min kill; Graph `unknown` not auto-retry (Q11) | KEEP |
| P8.14 | 90-day prune jobs/legs/tokens (Q10) | KEEP |
| P8.15 | Azure Automation is **not** a go-live path | DROP (locked) |
| P8.16 | In-app legacy Live email distributions | DROP (Q6, already retired) |

---

## P9 Company / master schedules

| ID | Control / behavior | Status |
|---|---|---|
| P9.1 | Company schedules still **run** even if add/edit UI is hidden | KEEP |
| P9.2 | Master schedules pages + lookups | KEEP |
| P9.3 | View-only managers Send now on shared only (Q9) | KEEP |

---

## P10 History pages

| ID | Control / behavior | Status |
|---|---|---|
| P10.1 | Report run log | KEEP |
| P10.2 | Scheduled run history | KEEP |
| P10.3 | Cancel stuck + abandon orphans on boot | KEEP |

---

## P11 Developer tools

| ID | Control / behavior | Status |
|---|---|---|
| P11.1 | Database explorer: one SELECT (or confirmed write), column filter; DROP/ALTER/ATTACH/CREATE blocked. JSON blob editor **dropped** — views are columns (`layout_tabs` / `layout_columns`). `group` must stay an array on save. | KEEP / FIX |
| P11.2 | Notification diagnostic | KEEP |
| P11.3 | Raw Reporting API runner `/api/dev/reporting/<id>/run` | KEEP |
| P11.4 | Diagnostics: salesman/number4 reconcile, precious-repair, claim-once | KEEP (dev) |

---

## P12 Impersonate / role picker

| ID | Control / behavior | Status |
|---|---|---|
| P12.1 | Developer View as / role picker | KEEP |
| P12.2 | Impersonate badge in header | KEEP |

---

## P13 Bookmarks / cutover

| ID | Control / behavior | Status |
|---|---|---|
| P13.1 | `/beta` 302 → `/` through cutover (Q7) | KEEP |
| P13.2 | Do not deploy over reports.achimonline.com until Menny signs off | **DONE** — FastAPI cut over 2026-09-16 (PR #68). Further deploys are normal `main` pushes; still ask before DNS/wipe. |
| P13.3 | Only `main` auto-deploys. Rebuild was not to push `main` until cutover. | **DONE** — cutover was that push. |

---

## Shell (every signed-in page)

| ID | Control / behavior | Status |
|---|---|---|
| S1 | Header: Sales Reports logo, user name, role badge, Recent Reports, theme, Sign Out | KEEP |
| S2 | Bottom nav: Reports, Schedules, Settings (no Dashboard on home) | KEEP |
| S3 | Four themes via CSS tokens (`tokens.css`) — not brother’s beige/green | KEEP |
| S4 | Tabulator + existing CSS tokens — **not** stock AG Grid | KEEP |
| S5 | Feather icons, PWA meta, `#2563eb` primary | KEEP |
| S6 | Recent Reports floating pill (keep/minimize) | KEEP |
| S7 | CSRF-equivalent on POSTs | KEEP |

---

## Internals (not a page, must exist)

| ID | Behavior | Status |
|---|---|---|
| I1 | Reporting API doorway only. Never `REPORTING_API_BASE_URL` = reports.achimonline.com. Never OData in the web app. | FIX |
| I2 | One JSON object `{ data: { raw, tabs } }`. UI displays `tabs.*.rows`. Dummy: `app/fixtures/sample-invoiced-response.json`. | FIX |
| I3 | SQLite for users/views/schedules/jobs/outbox only — not sales facts | FIX |
| I4 | Tests mock the doorway. CI must not call the office. | KEEP |
| I5 | Graph mail when secrets exist; mock outbox in local/dev | KEEP |
| I6 | Fail-closed production boot | KEEP |
| I7 | Live data stays on `BETA_PRECIOUS_DB_PATH`. Do not delete `/test` DBs. Do not empty-disk Production. | KEEP |
| I8 | Do not merge leftover Flask PR #35 | KEEP |

---

## To-fix (structure, not extra features)

| ID | What’s wrong today | Rebuild fix |
|---|---|---|
| F1 | Four URL mounts + OData toggle | Single FastAPI site, doorway only |
| F2 | `report_engine` tab factory + commission Python | SQL/JSON tabs; thin assembler only until SQL ready |
| F3 | Home Entra piggybacks Live cookie | Own Entra + People table |
| F4 | God files (`report.ts`, `report_service.py`) | Split by concern as slices land |
| F5 | Invoiced salesman vs SalesGroup | Ask Menny before mapping; testers = admin |
| F6 | Leftover Flask `rebuild/` / PR #35 | Parked. New app is `app/` |

---

## DROP / do-not-rebuild (locked in the job prompt — not asking again)

| ID | Item | Why |
|---|---|---|
| D1 | `/legacy`, `/test`, `/test-next` | Prompt |
| D2 | OData / `beta_sources` picker | Prompt |
| D3 | Azure Automation as go-live | Q11 / prompt |
| D4 | Legacy in-app distributions | Q6 |
| D5 | Dashboard on home nav | Live home hides it (`is_beta`) |
| D6 | Brother’s React/AG Grid look | Prompt |
| D7 | Self-register | Q8 |
| D8 | Push this rebuild to AchimSales `main` before cutover | **Superseded** — cutover 2026-09-16 |

**Customer Aging** stays BACKLOG (P3.11), not a silent DROP of a working report.

---

## Counts

- Pages / areas with IDs: P1–P13 + Shell S1–S7 + Internals I1–I8 + To-fix F1–F6 + Drops D1–D8  
- Grid reports to keep: 7 built + Last Order in-app + Aging backlog  
- Themes: 4  
- Home bottom-nav items: 3 (Reports, Schedules, Settings)
