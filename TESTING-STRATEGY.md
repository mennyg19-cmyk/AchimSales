# Testing Strategy

Testing plan built alongside code. Each feature/module gets an entry documenting what to test, expected behavior, and edge cases. See `testing-protocol.mdc` for rules.

## Phase 1 containment: headers, legacy bypass, and OData scope

**What to test:**
- Every configured security header is applied; CSP allows unpkg (Feather/Tabulator), excludes jsDelivr and Google Maps; HSTS appears only in production.
- `DEV_BYPASS_AUTH=true` still works locally but is refused on Azure or when `APP_ENV=prod`. Auth routes call `_dev_bypass_enabled()` live, not a frozen import.
- Empty OData `visible_keys` set empties rows. Sheet values match via `salesman_key()`. A missing salesman column empties rows when scope is set. Underscore params are not forwarded to Live `run_report`. Preset copy rejects `..` and slashes in the salesman folder name.

**Expected behavior:**
- Browser responses prevent framing, MIME sniffing, and unscoped third-party execution without overwriting an existing header. Current v3 pages still load Feather/Tabulator from unpkg, so CSP allows `https://unpkg.com` (not jsDelivr, not Google Maps).
- The legacy app cannot enable development authentication in Azure or production.
- An OData report cannot expose all rows when its scope column cannot be identified.

**Test file:** `v3/tests/test_security_headers.py`, `v3/tests/test_legacy_dev_bypass.py`, `v3/tests/test_odata_scope.py`

## Phase 2 DB-authoritative authentication

**What to test:**
- MSAL callback denies unknown users without inserting a v3 row and admits a known active row.
- Beta drops an unknown Live identity without creating a v3 user; existing v3 rows retain their stored permissions.
- Live magic-link tokens are stored as hashes, can be consumed once, replace any outstanding token for the same email, and use `PUBLIC_BASE_URL` when configured.
- `flask seed-users-from-live` inserts missing emails but does not overwrite an existing v3 role or flags.
- A developer impersonating a missing or inactive v3 user stays signed in as themselves; the role picker 404s instead of logging them out.

**Expected behavior:**
- Users & access is the only identity authority. Bearer tokens never appear in the Live database as plaintext.

**Test file:** `v3/tests/test_auth.py`, `tests/test_magic_links.py`

## Only developers mint developers; Add user does not overwrite

**What to test:**
- Admin PUT own row `role=developer` is 403; DB role stays admin. Admin PUT another user to developer is 403.
- Admin cannot disable or delete a developer row (403); only a developer can.
- Admin POST `/api/admin/users` with `role=developer` is 403. Developer POST the same is 201.
- POST an email that already exists is 409, row unchanged.
- `/impersonate` (non-beta) is 403 for admin; disabling the real developer mid-impersonation logs out.

**Expected behavior:**
- Developer is a higher tier than admin. First developers come from `V3_DEVELOPER_EMAILS` or an existing developer. Add user never silently overwrites.

**Test file:** `v3/tests/test_blueprints.py`, `v3/tests/test_auth.py`

## Live login does not overwrite Users & access; export download re-checks scope

**What to test:**
- Beta `adopt_live_identity` does not replace an existing v3 display name, role, SalesGroup, or salesman-access from the Live cookie.
- A demoted developer with a stale `_dev` cookie cannot open `/dev/role-picker` or `/api/admin/users`, and the DB role stays salesman.
- A leftover impersonation cookie (`email` = an admin, `_dev` + `_dev_email` of a demoted developer) cannot keep admin access; the session becomes the actor; self-promotion PUT is 403.
- A Live cookie with no v3 row redirects to login without creating a v3 user. A known but inactive v3 row is the same deny. Impersonation whose `_dev_email` is missing from v3 still logs out.
- After an unrestricted run/export, demoting the owner to a scoped salesman 403s download and hides the export from the list.
- GET `/api/reports/diagnostics/claim-once` is 405; POST with CSRF reverts only a job this request claimed.

**Expected behavior:**
- Users & access is the identity source of truth. Live login only adopts an active v3 row.
- Developer-only tools and the role picker use the DB developer role, not the cookie.
- Leftover impersonation after demotion drops to the actor's DB identity (or logs out if the actor row is gone).
- A developer's first Live login (`_dev` cookie, no v3 row yet) clears the shared session and does not create a developer row.

**Test file:** `v3/tests/test_auth.py`, `v3/tests/test_blueprints.py`

## Precious-repair mutating actions are POST-only; unknown user access is 404

**What to test:**
- GET `/api/reports/diagnostics/precious-repair?action=delete-ghosts` (developer) is 405 and does not delete queued jobs. GET without action (check) is 200.
- POST the same action without CSRF is 400; with CSRF it deletes queued jobs.
- POST `/api/admin/users/<missing-id>/salesman-access` and `report-access` return 404, not 500.

**Expected behavior:**
- A bookmark or cross-site GET cannot wipe the job queue. Missing user ids fail closed with 404.

**Edge cases:**
- `action=check` stays GET (read-only PRAGMA). Admin (not developer) still 403 on the diagnostic.

**Test file:** `v3/tests/test_blueprints.py`

## Users can be renamed on Users & access

**What to test:**
- PUT `/api/admin/users/<id>` with `display_name` updates the stored name (trimmed). Omitting the key leaves the name.
- Edit user modal has `#euDisplay`; save sends `display_name`.
- Login `upsert` and live-user copy do not overwrite a non-empty v3 display name.

**Expected behavior:**
- Edit a login, change Display name, Save. The Name column shows the new value. Email stays the login identity.
- Next Entra/dev login and next live-directory seed keep that name.

**Edge cases:**
- Empty `display_name` on PUT clears the name (table shows a dash; later login can fill it).
- Add user already had Display name; this only opens Edit.

**Test file:** `v3/tests/test_blueprints.py`, `v3/tests/test_data_layer.py`, `v3/tests/test_frontend.py`, `v3/tests/test_seed_developers.py`

## Admins and developers manage company views and schedule Default

**What to test:**
- Admin/developer `can_see_company_views` is true even with the flag off. Inactive privileged users still deny.
- Salesman/manager without the flag still 403 on company-view GET/PUT/DELETE and have an empty `company` presets list.
- Admin PUT/DELETE company views with the flag off. Developer with the flag off can PUT.
- Privileged Save for includes Company; `saveView` PUTs `/company-views` for that choice.
- Privileged POST `/api/schedules` with `saved_report_id=default:ordered` (or `view_name=Default` + `report_key`) creates a personal row with `view_name=Default` and empty layout. Salesman POST is 403.
- Privileged `/schedules` Add is enabled with no named views; `/api/schedules/views` lists Default per built report. Salesman Add stays disabled.

**Expected behavior:**
- Admins and developers create/edit/delete company views without the Users & access checkbox.
- More → Schedule works on Default for them. Filters on the report go onto the schedule; layout stays live Default.

**Edge cases:**
- Custom from/to on Default still cannot be scheduled.
- Editing a Default personal schedule keeps `view_name=Default` and does not invent a saved_reports row.

**Test file:** `v3/tests/test_auth.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_frontend.py`

## Delete company views from Saved views

**What to test:**
- Admin/manager DELETE `/api/reports/<key>/company-views/<id>` removes the row, the presets list, and the home card.
- Salesman with the company-views flag cannot delete (403). Same as Edit.
- Saved views dropdown shows Delete next to a company view when `can_edit` is true, and that Delete hits the company-view URL (not personal presets).

**Expected behavior:**
- Managers and admins can delete a company view from Saved views, with the same confirm as personal views.
- Default stays undeletable.

**Edge cases:**
- Wrong report_key on the URL → 404; view is not deleted.

**Test file:** `v3/tests/test_blueprints.py`, `v3/tests/test_frontend.py`

## Salesman report is filterable by salesman

**What to test:**
- Salesman report Filters & options includes the same Salesman dropdown as Ordered (All salesmen + list).
- Picking a SalesGroup keeps only that salesman's YoY rows (match display name / master aliases, not Excel column letters).
- All salesmen (blank) keeps every in-scope row.
- A scoped user cannot widen the report by picking someone else.
- Form `salesman` is not sent to the YoY SP as `SalesmanName`.

**Expected behavior:**
- Run Salesman, choose a salesman, Run report → only that salesman's customers/tabs rows.
- Company schedules that already store `salesman` keep working via the same post-filter.

**Edge cases:**
- Dropdown value is raw SalesGroup (`REdwards`); SP rows often have a display `SalesmanName`.

**Test file:** `v3/tests/test_blueprints.py`, `v3/tests/test_report_service.py`, `v3/tests/test_params.py`

## Salesman login has a SalesGroup dropdown from report lookups

**What to test:**
- `GET /api/admin/sales-groups` (privileged) returns the same keys as `LookupService.salesmen()` / report salesman filters. Salesman callers get 403.
- Creating a salesman with `sales_group=HKaufman` stores the raw group and grants normalized access `hkaufman` even when that key is not in `salesmen`.
- Updating a salesman SalesGroup replaces access; updating a manager with `sales_group` does not clobber checkbox access.
- `user_salesman_access` still FKs `users`, not `salesmen`. Direct access POST normalizes raw keys.
- Live user copy grants a salesman_key that is not in `salesmen`.
- Users & access template has `#addSalesGroup`, `#euSalesGroup`, `data-sales-groups-url`, `data-lookup-status-url`.

**Expected behavior:**
- Report filters and the user dropdown share customer_master SalesGroup values, not the salesmen table. Managers still use the checkbox grid.

**Edge cases:**
- Empty SalesGroup on a salesman clears access.
- Email auto-grant still runs when SalesGroup is omitted.

**Test file:** `v3/tests/test_blueprints.py`, `v3/tests/test_data_layer.py`, `v3/tests/test_frontend.py`, `v3/tests/test_seed_developers.py`

## Personal schedules columns line up across owners

**What to test:**
- Admin `/schedules` with two owners is one `ps-sched-table` and two `ps-owner-row` banners.
- Template has `table-layout: fixed` colgroup.

**Expected behavior:**
- Report / View / Cadence / Recipients / Folder / Last run / Active / Actions share one grid. Owner names are banner rows, not separate tables.

**Test file:** `v3/tests/test_blueprints.py`, `v3/tests/test_frontend.py`

## Admins save views for other users; Switch user lists v3 logins

**What to test:**
- Privileged POST `/api/reports/<key>/presets` with `owner_user_id` stores the view on that user. GET presets lists it under `others`, not `presets`. Admin GET/PATCH/DELETE of that id works. The owner sees it in `presets`.
- Salesman POST with `owner_user_id` still saves as self.
- Salesman GET/DELETE of someone else's preset is still 404.
- Role picker merges Live directory with v3 Users & access so a login added only in v3 appears.
- Creating a salesman/manager whose email matches an active `salesmen.email` auto-grants that salesman key.
- Report toolbar has `#viewOwner` for privileged users; Saved views source has `others` folds and `syncViewOwner`.

**Expected behavior:**
- Admins do not need to Switch user to plant a named view. Schedules from that view still belong to the owner (existing schedule test).
- Report salesman dropdowns stay on customer SalesGroup, not the users table.

**Edge cases:**
- Inactive owner_user_id → 400.
- Empty salesman-access is left alone when re-adding a user who already has keys.

**Test file:** `v3/tests/test_blueprints.py`, `v3/tests/test_auth.py`, `v3/tests/test_frontend.py`

## Excel grouped sheets have no outline groups

**What to test:**
- Grouped Excel sheets do not set `outlineLevelRow` or per-row `outline_level`.
- Group banners and totals still write; only the +/- gutter is gone.

**Expected behavior:**
- Excel does not show collapsible groups.

**Test file:** `v3/tests/test_reporting.py`

## Ordered group footers skip Net Price; nested groups use shade ladders

**What to test:**
- Group subtotals and Grand total leave Net Price blank (unit price). Extended Price still sums.
- Cached payloads without `sum: false` still skip the Net Price field by name.
- Nested Excel banners: outermost group header is the darkest blue; inner is lighter; dark fills use white text.
- Nested Excel totals: Grand total darkest grey, then outer group, then inner group. Inner (customer) grey is `#9CA3AF`, not a near-white wash.
- Contrast of every header/footer shade against its chosen text is at least 4.5:1 (1–4 group levels).
- Grid source does not `bottomCalc` Net Price and paints nested groups (`paintNestedGroups`).

**Expected behavior:**
- Daily Ordered (Salesman then customer) is the example; any group depth uses the same outer-darkest ladder.
- Grid and Excel share the same RGB recipe.

**Edge cases:**
- One group level still shades header vs group total vs grand total.
- `sum: false` on a column dict also skips summing that field.

**Test file:** `v3/tests/test_reporting.py`, `v3/tests/test_frontend.py`

## Saved views on the report page start collapsed

**What to test:**
- Company views and My views in the Saved views panel are `<details>` with class `presets-fold`.
- The fold helper does not set `open`.

**Expected behavior:**
- Clicking Saved views shows Default. Company views and My views are headers you expand.

**Edge cases:**
- Empty personal list still shows the “no other saved views” line when there are no company views.

**Test file:** `v3/tests/test_frontend.py`

## Settings customer exclusions use the report customer list

**What to test:**
- Settings HTML uses the searchable picker (`exclPicker`), not the old checkbox list.
- `GET /api/settings/customers` matches `GET /api/reports/ordered/customers` for the same user.
- A salesman only sees customers in their salesman scope.
- POST exclusion of an in-scope account works without dashboard rows.
- POST of another salesman's customer is 403; unknown account is 400.

**Expected behavior:**
- Pills are hidden customers. The dropdown is customer master, scoped like the report page.

**Edge cases:**
- Dashboard-only customers do not appear on Settings.
- Saved exclusions still serialize into `data-excluded`.

**Test file:** `v3/tests/test_blueprints.py`, `v3/tests/test_frontend.py`

## Personal schedules page is full width

**What to test:**
- `schedules.html` does not set `container-narrow` (same as `company_schedules.html`).

**Expected behavior:**
- Personal schedules uses the default full-width `.container`, not the 800px reading column.

**Edge cases:**
- Settings and the report picker stay `container-narrow`.

**Test file:** `v3/tests/test_frontend.py`

## Applying a view must not throw on `_isDuplicate`

**What to test:**
- Report viewer source stores `generated_at` on `state.generatedAt`, not as a fake tab key.
- `applyLayout` uses optional `_isDuplicate` so a missing tab key cannot throw.

**Expected behavior:**
- Clicking a saved view after a report is on screen does not show the pink `reading '_isDuplicate'` banner.

**Edge cases:**
- Result payloads omit `generated_at` (current API).

**Test file:** `v3/tests/test_frontend.py`

## Salesman Excel color bands follow fields, not column letters

**What to test:**
- Default columns: blue starts at Excel E (first month $), green at the YTD block, purple at full-year.
- Hide Sort Number + Salesman (Default 2): month $ that used to be E is now C and stays blue; YTD stays green; full-year stays purple; negative $ is red.
- Reorder a purple field into Excel A: it stays purple; identity columns stay uncolored.
- Cached payloads with no ``band`` on the column dict still color by field name after hide.
- Builder stamps ``band`` 0/1/2 on the three metric groups only.

**Expected behavior:**
- Excel export paints the information (month / YTD / full-year fields), not a fixed Excel letter.
- Group-by Salesman with those two columns hidden still colors the data row the same way.

**Edge cases:**
- Commission cards tab is unbanded.
- Other reports never pick up salesman fonts.

**Test file:** `v3/tests/test_reporting.py`, `v3/tests/test_report_salesman.py`

## Schedules from named saved views

**What to test:**
- A named saved view can be scheduled, including Customer Activity with no period. Company views and custom from/to cannot. Default is privileged-only (see “Admins and developers manage company views and schedule Default”).
- Create from another user’s view (admin) sets owner to that user and recipients to their email.
- Salesman update cannot add extra emails, CC, BCC, or SharePoint.
- Privileged create/edit of a personal schedule stores optional `email_cc` / `email_bcc`.
- Conversion creates a saved view for a Default personal schedule and keeps it running; company rows are untouched.
- Empty eligible-view list means Add is disabled for salesmen (API returns no views). Privileged Add stays on because Default is always listed.

**Expected behavior:**
- POST /api/schedules requires a saved_report_id (or equivalent) that is schedulable.
- Privileged list of views is grouped by owner.

**Edge cases:**
- Custom period views stay off the picker after conversion.
- Editing a converted custom-date schedule still saves When/Where (same view id is allowed).
- Non-privileged extra recipients, CC, and BCC on create are ignored; owner email is kept.
- Privileged POST/PUT on a salesman’s named view keeps CC/BCC on `params`; salesman pages omit those fields.

**Test file:** `v3/tests/test_scheduling.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_frontend.py`

A cheaper model can use this file as a guide to run the full test suite without deep context.

---

<!-- Entries are added below as features are built. Each entry follows this format:

## [Feature/Module Name]

**What to test:**
- ...

**Expected behavior:**
- ...

**Edge cases:**
- ...

**Test file:** `tests/test_feature_name.py` (or equivalent)
-->

## Daily Ordered salesman then customer sort

**What to test:**
- Excel Summary with Daily Ordered layout: salesman banner, then customer banner, customers A-Z (then item) inside each.
- By Customer: salesman banners only (no CustomerName banners); customers A-Z inside.
- By Order: no group banners (`group: []` overrides builder default_group Salesman).
- Customer-only sorters plus a Salesman group still emit consecutive salesman banners.
- Heshy still groups by order number after a customer sort, with no customer totals.
- Empty saved `group: []` still means ungroup (Number 4 Default).
- PUT company view with `period: yesterday` stores params without a period.
- `params_without_window` keeps salesman/status and drops period/from/to.

**Expected behavior:**
- Company Daily Ordered Summary is salesman then customer. By Customer is salesman only. By Order is flat. Per-rep files still drop the extra Salesman group.
- Company views do not store a date window; schedules own YTD / MTD / yesterday.

**Edge cases:**
- Same customer with two item numbers stays together and items sort A-Z.
- Heshy sorter-first behavior is unchanged.
- Front-end maps saved `yesterday` to the Yesterday dropdown (`daily`) and does not auto-run a company view with no period.

**Test file:** `v3/tests/test_reporting.py`, `v3/tests/test_company_views.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_frontend.py`

## Number 4 Default group in emailed Excel

**What to test:**
- Tab with `default_group: Item #` and layout `group: []` does not write Item # group banners.
- Layout with no `group` key still uses `default_group` (old snapshots / never-saved Default).

**Expected behavior:**
- Editing Default to ungroup (or Email me after ungrouping) produces a flat sheet, not Item groups.

**Edge cases:**
- `group: ["Customer"]` still overrides Item # (existing nested-group tests).

**Test file:** `v3/tests/test_reporting.py`

## One status email after fail-then-retry

**What to test:**
- Home-site: in-process retry success sends no `[FAIL]`; subject names the retry.
- Home-site: both attempts fail → `[FAIL]` only after flush; a later same-day success drops it.
- Catch-up window fail then regular success is one run, no `[FAIL]`.
- Tick flushes held notices.
- Runbook: fail then success is one heartbeat; `main()` wraps retry.
- `[TEST]` mail that already went out, then Test-folder upload fails: no second Graph send, no `[FAIL]`.

**Expected behavior:**
- One status email per schedule run. Fail then success is not `[FAIL]` plus a later pass.

**Edge cases:**
- Recovered worker job after a successful send today skips a second mail.

**Test file:** `v3/tests/test_scheduling.py`, `tests/test_runbook_retry.py`

## Ordered Summary Extended Price Cancelled

**What to test:**
- Summary has `Extended Price Cancelled` (money) between Ordered and Remainder.
- Value is SP `Cancelled $` summed by customer + item (ITM-B fixture is $20, ITM-A is $0).
- Blank/missing cancelled dollars is $0. No qty × price.

**Expected behavior:**
- Summary tab shows the cancelled extended price next to Ordered and Remainder.

**Edge cases:**
- Two lines for the same customer + item add together.

**Test file:** `v3/tests/test_report_ordered.py`

## Schedule crash on missing company-views column

**What to test:**
- `User.from_row` on a SELECT that omits `can_see_company_views` returns False, no IndexError.
- `get_by_email` after `DROP COLUMN can_see_company_views` (skip if SQLite too old) does not raise.
- Re-running a migration whose ADD COLUMN already landed, with the version row deleted, does not raise; version is recorded.
- `migrate()` after dropping the column puts it back. Four threads calling `_ensure_users_company_views_column` on a dropped column do not raise.
- Personal `ScheduleRunner` still records success when the column is gone (fake delivery).

**Expected behavior:**
- Boot finishes and the scheduler starts even if 0016 raced. Schedule runs do not IndexError on the user row.
- Company-views permission still defaults off except developers.

**Edge cases:**
- Column present, version missing (duplicate-column retry).
- Version present, column missing (Litestream / restore; ensure repairs).
- Two workers both ALTER (duplicate-column in ensure).

**Test files:** `v3/tests/test_auth.py`, `v3/tests/test_data_layer.py`, `v3/tests/test_scheduling.py`

## Company views per-user permission

**What to test:**
- `users.can_see_company_views` defaults to 0; developer INSERT and `0016` set it to 1.
- Admin without the flag: presets `company` is `[]`, GET/PUT company-view 403, Home has no Company views heading.
- Developer via upsert INSERT: can PUT and sees Home cards.
- Salesman with the flag: sees company in presets (`can_edit` false) and 403 on PUT. Salesman without the flag: empty list + GET 403.
- People PUT `/api/admin/users/<id>` round-trips the flag. Creating a developer sets it on. Creating a salesman does not.
- Live user mirror INSERT sets 1 for developers; ON CONFLICT does not overwrite the flag. `V3_DEVELOPER_EMAILS` seed sets the flag to 1.
- `?cview=` GET returning null does not set `autoRunRequested`.

**Expected behavior:**
- Home, Saved views company group, and the schedule wizard company optgroup only appear when the flag is on.
- Managers/admins still need the flag to edit; schedule privilege alone is not enough.

**Edge cases:**
- Inactive user with the flag is denied (fail closed).
- Unchecking a developer in People sticks until `_seed_developers` runs (env-listed emails get the flag back on boot).

**Test files:** `v3/tests/test_auth.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_seed_developers.py`, `v3/tests/test_frontend.py`

## Ordered Summary remainder from SP dollar amount

**What to test:**
- Missing `ShippingDollars` shows $0 for Shipping $ and Summary remainder (no qty × price, no Open $ math).
- When the SP sends `ShippingDollars`, Summary Extended Price Remainder and Full Data Shipping $ use that value. Open $ stays Ordered − Shipped − Cancelled.
- `CustomerRequisition` maps to PO #. `ShippingDateRequested` maps to Ship Date.

**Expected behavior:**
- Summary remainder and Shipping $ are ShippingDollars only, summed by customer + item.

**Edge cases:**
- Blank/absent ShippingDollars is 0. Blank ShippingDateRequested does not fail the build.

**Test file:** `v3/tests/test_report_ordered.py`

## Company views (Daily Ordered / Heshy Open Orders)

**What to test:**
- `company_views` upsert rejects Default/Custom; GET presets includes `company` **when the user is privileged or has `can_see_company_views`**.
- Admins/developers PUT without the flag. Managers PUT **when they also have the see flag**; salesmen with the flag GET (`can_edit` false) and 403 on PUT.
- Home page shows a Company views section with `?cview=` links **for privileged users and anyone with the flag**.
- Boot stamps daily company Ordered schedules with Daily Ordered (Summary salesman then customer, By Customer salesman only, By Order ungrouped). Salesman-split and already-named views are left alone. Heshy open-orders (Hkaufman + Open) gets Heshy Open Orders (Full Data only, hide LineNumber, sort customer then order, group by order).
- Send with that view name uses the live company layout even if the schedule snapshot is stale.
- Excel nested groups write banners/totals per level. Sort-then-group keeps customer clusters and does not add a customer total when the only group field is order number.
- Ordered Full Data has CustomerName and ShipDate. Missing SP Ship Date stays blank and still builds.

**Expected behavior:**
- Saved views lists Default, then company views, then personal. Wizard has a Company views optgroup. Schedules View column shows the stamped names.
- Daily Ordered emails group Summary by salesman then customer, By Customer by salesman only, and leave By Order ungrouped. The Daily Ordered view itself has no period. Heshy’s file is one Full Data sheet, customers together, totals per order, no LineNumber.

**Edge cases:**
- Layout `order` listing ShipDate when the column is absent does not fail (`apply_layout` skips unknown fields).
- Nested Excel groups still honour hidden group fields (existing single-group tests).

**Test files:** `v3/tests/test_company_views.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_reporting.py`, `v3/tests/test_report_ordered.py`, `v3/tests/test_frontend.py`

## Default view per report

**What to test:**
- GET default-view returns empty Default until someone saves it; PUT stores layout + params.
- Managers/admins can PUT; salesmen can GET (`can_edit` false) and get 403 on PUT.
- Preset list includes `default` plus personal presets. Personal views cannot be named Default.
- New schedule with `view_name=Default` (or empty layout) shows Default on `/schedules`.
- Report-page snapshot (layout with views/order, no view_name) shows Custom.
- Send with Default + empty layout uses the company Default. Default + stored snapshot keeps the snapshot.

**Expected behavior:**
- Wizard first option is Default. Schedules tables have a View column.
- Saved views always lists Default; Edit is managers/admins only; Default cannot be deleted.

**Edge cases:**
- Switching a named view to Default on edit clears the snapshot.
- Staying on Default during edit does not wipe a seeded snapshot.

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_repositories_delivery.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_frontend.py`

## Oversized Graph email: download button

**What to test:**
- Workbooks at/over `MAX_GRAPH_ATTACH_BYTES` are not attached; Graph `xlsx_bytes` is None.
- With a live SharePoint path (test mode off), the file URL is in the plain-text body and in HTML (`Download workbook` button, brand `#2563eb`).
- With no path, the file uploads to `Test` under Direct Reports and the button/link use that URL.
- Company test mode with a live folder (e.g. Invoiced Report/Daily) passes `sharepoint_path=Test`, never the live path. Split legs stay `sharepoint_path=""`.
- If the Test-folder upload fails, the email still sends; delivery is not marked failed.

**Expected behavior:**
- Outlook shows a blue Download workbook button that opens the SharePoint file in `Direct Reports/Test` (test mode) or the live folder (test mode off).
- Plain-text clients still get `Download it here: <url>`.
- Live Daily/YTD/Monthly folders are never written while test mode is on.

**Edge cases:**
- Email already sent + folder upload failed: delivery stays ok. Scheduler must not send a second copy.
- SharePoint-only (no recipients) still fails when the upload fails.
- Graph 413 on a small attachment retries without the file, uploads to `Test` if needed, and includes the download link.
- Chunked upload with no `webUrl` in the session response still gets a URL: GET `/items/{id}` first (app-only), then path GET with the trailing colon Graph requires (`root:/path:`), then org view link.
- Path GET without the trailing colon is retried with `:` appended.
- If the file uploaded but Graph still returned no URL, the body names `Direct Reports/{folder}/{filename}` instead of “download it from SharePoint” with nothing to click.

**Test files:** `v3/tests/test_delivery.py`, `v3/tests/test_scheduling.py`

## Number 4: YTD tabs, trailing columns, group by item

**What to test:**
- Both mode builds four tabs (By Customer 12 months + YTD, By Item 12 months + YTD).
- All four tabs keep month qty/$, then Total Qty, Total $, Avg Price, Book Price, Salesman.
- A month the SP (or saved Default) appended after Salesman still sits with the other months, before that trailing block.
- YTD keeps current-year months only and recalculates Total Qty / Total $ / Avg Price.
- YTD drops rows with no current-year qty or dollars.
- Every tab sets `default_group` to Item #.
- Live Excel By Item and By Customer share the same trailing headers.
- OData extra_files dicts are read as paths; Item/Customer sheet names do not collide.
- Ordered / Item Averages column lists are not reordered.

**Expected behavior:**
- Mode By Item → two tabs with dollars. Mode By Customer → two tabs with dollars. Both → four tabs.
- Trailing columns on every Number 4 tab: Total Qty, Total $, Avg Price, Book Price, Salesman.
- Grouping starts on Item # until the user changes it.

**Edge cases:**
- Empty view still keeps headers, months in calendar order.
- Prior-year-only rows appear on 12 Months and vanish on YTD.
- SP aliases AvgPrice / BookPrice become Avg Price / Book Price.
- Saved Default with Sep after Salesman still emails and shows Sep before Total Qty.

**Test files:** `v3/tests/test_report_number_4.py`, `v3/tests/test_report_service.py`, `v3/tests/test_odata_number4.py`, `v3/tests/test_delivery.py`, `tests/test_number_4.py`

## Sales by State (SQL only)

**What to test:**
- Year filter becomes FromDate Jan 1 / ToDate Dec 31 for all three catalog keys.
- Third catalog key is `sales_by_state_filtered` (not `sales_by_state_detail`).
- Summary sorts by sales amount. NYC sales amount appears on the first row only, even if the SP repeats it.
- Detail Excel serial dates become YYYY-MM-DD; negative amounts stay negative.
- Report is built, not on the Settings SQL/OData list, and not a salesman default.

**Expected behavior:**
- Admin reports list shows Sales by State. Salesman inherit list does not.
- `get_source("sales_by_state")` is sql.

**Edge cases:**
- Custom period dates override the year window when both start and end are set.

**Test file:** `v3/tests/test_report_sales_by_state.py`, `v3/tests/test_params.py`, `v3/tests/test_report_service.py`, `v3/tests/test_blueprints.py`

## Meeting fixes (tabs, views, groups, empty split, Ordered %, personal Edit)

**What to test:**
- Viewer source has Rename tab, Edit+Delete saved views, subgroup + group pills, clone restore in applyLayout.
- Personal schedules page has Edit and `data-kind="personal"`.
- Split delivery: `email_on_empty=False`; 0-row salesman gets a No Data Found text mail, no xlsx.
- Ordered Full Data, By Customer, By Item, By Order, and By Salesman have Fulfillment % `(QtyOrdered - QtyCancelled) / QtyOrdered`; Summary does not. Grid and Excel color red→yellow→green. skip_by_salesman has no Salesman default_group.
- Daily 9am Salesmen Ordered seed layout omits `by_salesman`.
- Home `?preset=` does not resume the last job for that report (`resumeInFlight` returns false unless `?job=` is also set).
- Saved-views name click calls `loadPreset(p)` (runs). Edit still uses `run: !isReportShown()`.
- A preset with salesman/status keeps those values on the home-card URL and in GET `/api/reports/presets/<id>`.
- Auto-run still sends salesman when the dropdown has not loaded yet (`pendingSalesman` is included in collectParams).

**Expected behavior:**
- Company copy still honours the “email when no data” checkbox.
- Save this view with the same name as the view being edited overwrites it.
- Home preset cards and Saved views → name start a new run with that view’s filters and layout.

**Edge cases:**
- Whole report has rows but one salesman has none → that salesman gets the text mail only.
- Coming back to a report with no `?preset=` still reconnects the last job.

**Test file:** `v3/tests/test_frontend.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_delivery.py`, `v3/tests/test_report_ordered.py`, `v3/tests/test_schedule_seed.py`, `v3/tests/test_reporting.py`

## Invoiced salesman from the reporting API (not Excel)

**What to test:**
- Invoiced adapter keeps the SP `SalesGroup` / `salesman` fields as sent.
- When `salesman` is a numeric code (or missing), the customer dropdown source (`customer_master`) supplies SalesGroup.
- A known SalesGroup from the SP does not trigger a customer_master fetch.
- `salesman_map.xlsx` is not used to stamp numbers onto invoiced rows.

**Expected behavior:**
- `salesman=029` + customer 100 assigned to REdwards → Salesman column is REdwards.
- `SalesGroup=REdwards` on the invoice stays REdwards even if the customer master says someone else.

**Edge cases:**
- Numeric salesman with no matching customer keeps the code from the SP.

**Test file:** `v3/tests/test_report_invoiced.py`, `v3/tests/test_report_service.py`

## Home-site schedule failure mail

**What to test:**
- A failed company schedule emails the test-email list even when test mode is off.
- If sending that notice throws, the original schedule error still raises.

**Expected behavior:**
- Subject is `[FAIL] {schedule name}`. Body names company/personal, report, and error.
- Recipients are `settings.test_emails()`, not the schedule's customer list.

**Edge cases:**
- Empty test list: no send, original failure still recorded.
- Fake delivery with no `email.send_notice` (older tests) must not crash.

**Test file:** `v3/tests/test_scheduling.py`

## Home is Beta; Live at /legacy

**What to test:**
- `/` is the Beta (v3 is_beta) app; `/legacy` is the old Live app.
- `/beta` and `/beta/reports` 302 to `/` and `/reports`.
- `/login` is the home (Beta) sign-in page. `/login/start` 307s to Live for Microsoft.
- `/dev/role-picker` is the home app (developers). `/auth/callback` still hits Live.
- `/auth/callback` hits Live with no `/legacy` SCRIPT_NAME (Entra URI unchanged).
- `/test` still strips to the v3 sandbox.
- Live login `next` accepts `/legacy/...` and leftover `/beta/...`.
- Entra redirect URI is `https://host/auth/callback` even when Live's SCRIPT_NAME is `/legacy`.
- Logged-out home users go to `/login?next=/`. No 403 for missing Beta Access.

**Expected behavior:**
- Dummy WSGI apps behind `mount_beta_as_home` see the paths above.
- `live_login_redirect("/")` is `/login?next=/`.

**Edge cases:**
- If `BETA_MOUNT_ENABLED` is off or Beta fails to boot, `/` stays Live (not covered by the dummy dispatch tests).

**Test files:** `tests/test_wsgi_dispatch.py`, `tests/test_beta_sources.py`

## Login page and developer role picker on home

**What to test:**
- Logged-out `/login` is the home Microsoft / External Rep page, not `/legacy/login`.
- `/login/start` still 307s to Live so Entra keeps working.
- A developer session can open `/dev/role-picker`, pick a user, then open the picker again.

**Expected behavior:**
- Home login shows "Achim User Login".
- Role picker lists users; View as Selected User then View as Admin (yourself) both 302 home.

**Test files:** `v3/tests/test_auth.py`, `tests/test_wsgi_dispatch.py`

## Company schedules table sorts by name

**What to test:**
- Company list HTML has Apple before Zebra when those two rows exist.
- Table is marked `js-sortable` so column headers can be clicked.

**Expected behavior:**
- Company schedules open sorted by name. Click a header to sort that column.

**Test file:** `v3/tests/test_blueprints.py`

## Deleted company schedules stay deleted

**What to test:**
- Boot seed does not re-insert a company schedule after it was deleted.
- Beta seed no longer includes `Daily 9am` (customer 48999/917/2267).
- Migration `0010` deletes a leftover shared `Daily 9am` row.

**Expected behavior:**
- Delete on company schedules is remembered across deploys/recycles.
- Recreating the same name later is allowed (the skip list is cleared on create).

**Test files:** `v3/tests/test_schedule_seed.py`, `v3/tests/test_blueprints.py`

## Schedules run log starts collapsed

**What to test:**
- After a schedule has run, `/schedules` still renders the Recent run log without the `open` attribute.

**Expected behavior:**
- The log is closed on page load. Run now still opens it so you can watch that job.

**Test file:** `v3/tests/test_blueprints.py`

## Company schedule Copy

**What to test:**
- Copying a company schedule returns 201, a new id, `is_active=False`, and name `{original} (copy)`.
- A second copy of the same source is `{original} (copy 2)`.
- Params, layout, cadence, recipients, SharePoint, filename, share flag, and run-as match the source. Owner is the copier.
- A manager cannot copy a company row they cannot edit (403, no Copy button). They can copy a row they own.
- A salesman cannot copy company schedules (403).
- Personal Copy still leaves the duplicate inactive.

**Expected behavior:**
- Copy on a company row you can edit. The copy stays Off until someone turns it on.
- Shared names stay unique so the copy does not collide with the Azure seed index.

**Edge cases:**
- Copying a 120-character name still fits in the name column (`next_copy_name` truncates the stem).

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_schedule_seed.py`

## Shabbos / Yom Tov schedule skip (Beta clock)

**What to test:**
- Hebcal candle→havdalah window is restricted (Shabbos, or named Yom Tov). Weekday-name candle memo is still Shabbos.
- Check fails open on a malformed Hebcal payload.
- Clock tick during a restricted window records `skipped` and sets `catch_up_pending` + `catch_up_for_date`; no delivery job.
- Skip-class periods (yesterday/daily, mid-month MTD, mid-year YTD) wait for the next regular HH:MM. They do not fire Saturday night after havdalah.
- Reschedule-class periods (last_7_days, last_month, month-end MTD, year-end YTD, salesman/customer_activity) wait until the next Monday–Friday at the same HH:MM.
- MTD skipped on Friday the 30th: Monday 10pm run covers MTD through the 30th, and if that makeup is next month, a second pass through month-end.
- Manual Run now sets `ignore_sabbath` so it still sends.

**Expected behavior:**
- Company and personal clock runs skip Shabbos/Yom Tov (Brooklyn, 18-min candles) and make up at the scheduled clock time, not motzei Shabbos.
- Date windows follow the period: widen yesterday/last_7_days; MTD self-heals in-month; cross-month MTD sends the skipped window plus month-end if needed.
- Run now is a deliberate send and does not skip.

**Test files:** `v3/tests/test_sabbath.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_catchup.py`

## Scheduled Excel matches on-screen tabs

**What to test:**
- A layout `order` list drops server tabs not on that list (Commissions off Salesmen Shipped).
- Empty/missing `order` keeps every tab (old schedules unchanged).
- Saving a company schedule from the wizard with `layout: {}` does not wipe a stored tab order.

**Expected behavior:**
- Right-click → Remove tab, then save/schedule, emails a workbook without that sheet.
- Daily 9am Salesmen Shipped ships without Commissions.

**Edge cases:**
- Optional invoiced tabs (Audit, Totals by Salesman) listed in order but absent from a given run are skipped, not an error.

**Test files:** `v3/tests/test_delivery.py`, `v3/tests/test_blueprints.py`

## Email me + hide Commissions from salesmen

**What to test:**
- Report page has Email me next to Run report.
- Email me POSTs email-now to the signed-in user's address (existing Email modal still works for other people).
- Salesman invoiced run/result/export/email has no `commissions` tab. Admin/manager still have it.
- Page for a salesman sets `data-hide-commissions=1`.

**Expected behavior:**
- One click emails the current filters as Excel to the user. No recipient modal.
- A salesman never sees Commissions on screen or in a file they generate.

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_report_service.py`

## Schedule workbook filenames

**What to test:**
- Blank `filename_template` uses `{Schedule}_{MM}-{DD}-{YYYY}` (Eastern date, no clock time).
- New personal and company schedules store that default when the client omits a template.
- Two company schedules on the same report still get different filenames when their names differ.
- Missing schedule name falls back to the report title slug.
- Existing rows that already stored a custom template are unchanged.

**Expected behavior:**
- `Daily 9am` → `Daily_9am_08-17-2026.xlsx`. Custom templates still expand tokens as written.

**Test file:** `v3/tests/test_filename_template.py`

## Save and On wait for the next scheduled time

**What to test:**
- Turning a company or personal schedule On after today's time has passed does not enqueue a run.
- Saving an edit on an active schedule does not enqueue a run.
- Creating a schedule whose time already passed today does not enqueue a run.
- A schedule that was already On still catch-up-fires if the slot was missed (app down).
- Turning On before the slot still fires at that time. Run now still sends immediately.

**Expected behavior:**
- Save / On wait for the next cadence. Only Run now or the clock at the scheduled time send.

**Test files:** `v3/tests/test_scheduling.py`, `v3/tests/test_blueprints.py`

## SharePoint folder paths and date tokens

**What to test:**
- Stored paths do not start with `Direct Reports` (that folder is already the drive home). Saving `Direct Reports/Ordered` stores `Ordered`. Nested `Direct Reports/Direct Reports/...` is stripped.
- Folder templates expand the same date tokens as filenames, but keep `/` and spaces (`{Month} {YYYY}` → `August 2026`).
- Customer Activity seed path is `Salesman Report/Customer Activity/{Month} {YYYY}`.
- Migration 0011 strips existing prefixes and sets that Customer Activity month folder when the path is still the old static one.

**Expected behavior:**
- Files land in `Direct Reports/<schedule path>/`, not `Direct Reports/Direct Reports/...`.
- Monthly Customer Activity creates `.../Customer Activity/August 2026` (run date, Eastern).
- Other monthly jobs stay on their current folders until someone adds tokens in the wizard.

**Test files:** `v3/tests/test_filename_template.py`, `v3/tests/test_delivery.py`, `v3/tests/test_schedule_seed.py`, `v3/tests/test_blueprints.py`

## Schedule test mode persistence

**What to test:**
- Shared master schedule names cannot be inserted twice (`IntegrityError`).
- Re-seeding the Azure import does not duplicate rows.

**Expected behavior:**
- Beta `app_settings` (test mode + emails) survive App Service recycle via Litestream replica `LITESTREAM_AZURE_BETA_PATH`.

**Test file:** `v3/tests/test_schedule_seed.py`

## Beta settings hub

**What to test:**
- Salesman `/settings` is `container-narrow`, has You (profile, theme, exclusions), no admin/developer blocks.
- Admin has People, Reports, Delivery, History; not Database explorer.
- Developer has explorer, notification diagnostic, beta sources.
- `POST /api/admin/report-visibility` hides a report unless a per-user allow override exists.
- Exclusions save without the dashboard blueprint (Beta).
- `/admin/schedule-runs` and `/admin/run-log` are admin-only.
- DB explorer lists precious tables; salesman/admin get 403. No arbitrary SQL.

**Expected behavior:**
- Settings is ~800px, accordion on phone, stacked categories.
- Live Email Distributions is not on Beta.

**Edge cases:**
- Globally disabled report + explicit allow still visible.
- Unknown `report_config` row means enabled.

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_auth.py`

---

## Previously run list + Keep name + OneDrive root URL

**What to test:**
- `onedrive_children_url` at root is `…/drive/root/children`, never `root::/children`. Nested folders keep `root:/{path}:/children`.
- `keep_run` stores `keep_name` and clears name when a Keep overflows the cap of 5 (test uses cap 2).
- `POST /api/reports/runs/<id>/keep` with `{name}` returns that name; `/api/reports/active` includes `keep_name`, `created_at`, `finished_at`.
- Logged-in `base.html` has Recent Reports (`#prevRunsBtn`, styled as a link) and the jobs bar.

**Expected behavior:**
- Header Recent Reports opens the floating list. Keep this run prompts for a name. Chips show Eastern date/time.
- Exporting Excel opens the Recent exports panel. The status line's "Recent exports" words open it again.
- OneDrive Browse at the drive root no longer 400s from a bad Graph path.

**Edge cases:**
- Empty keep name is allowed; UI falls back to the report title. Name is trimmed to 80 chars.

**Test files:** `v3/tests/test_delivery.py`, `v3/tests/test_jobs.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_frontend.py`

---

## Invoiced one-day SQL window (Daily / yesterday)

**What to test:**
- `translate_invoiced` sends `InvoiceDateFrom` at 00:00:00 and `InvoiceDateTo` at 23:59:59.
- `daily` and `yesterday` produce the same window.
- A one-day custom range keeps that day's invoices after the YTD fetch + slice.

**Expected behavior:**
- Scheduled Daily Invoiced is not an empty workbook when that day has invoices.

**Edge cases:**
- Same calendar day From/To must not collapse to midnight–midnight.

**Test files:** `v3/tests/test_params.py`, `v3/tests/test_report_service.py`, `v3/tests/test_dates.py`

---

## Schedule test mode

**What to test:**
- Admin can save several test emails and turn test mode on; cannot turn on with an empty list.
- Salesman cannot POST the API.
- Company schedule Run now in test mode emails only the test list, `[TEST]` subject, SharePoint dumps to `Test` (not the live Daily/YTD folder).
- Split schedules still fan out in test mode; every file goes to the test list with the salesman in the subject/filename.
- Personal schedules ignore test mode.
- Test mode on with no emails fails the run instead of sending to stored recipients.

**Expected behavior:**
- Settings shows the toggle and address chips.
- `/schedules` shows a banner listing the test addresses while On.

**Edge cases:**
- Invalid addresses are dropped; salesman-split jobs still fan out, but every file (full + each salesman) goes to the test list. Salesmen are not emailed.

**Test files:** `v3/tests/test_scheduling.py`, `v3/tests/test_blueprints.py`

---

## Beta import of Live Azure runbook schedules

**What to test:**
- Beta boot inserts Live Azure job names as company master schedules with `is_active=0`.
- Re-seed does not duplicate existing names.
- `amazon_weekly` is not imported.

**Expected behavior:**
- Company schedules list on `/schedules` (home) shows the Live jobs as Off.
- The minute poller does not fire them until someone turns a row On.

**Edge cases:**
- A name you already created on Beta is left as-is (not overwritten).

**Test file:** `v3/tests/test_schedule_seed.py`

---

## Salesman-all fan-out (Beta)

**What to test:**
- 9am Salesmen Ordered / Shipped seed with `split_by_salesman`.
- Existing plain rows get that flag on re-seed.
- `split_by_salesman` with no key list fans out to active salesmen who have an email.
- Salesman-filtered Ordered omits the By Salesman tab; unscoped Ordered keeps it.
- Monthly combined SharePoint job stays `Salesman Report/Monthly` with no split. A second seed (`Monthly 1st 12am Monthly Salesmen` / `Monthly Salesmen Report`) is split-only, no folder.

**Expected behavior:**
- One combined file (folder/recipients) plus one file per salesman with an email.
- Per-rep Ordered files match live `--salesman all` (no By Salesman sheet).
- Monthly SharePoint job is unchanged. The extra monthly split schedule emails each salesman and does not write SharePoint.

**Test files:** `v3/tests/test_schedule_seed.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_report_ordered.py`, `v3/tests/test_report_service.py`, `v3/tests/test_salesmen_seed.py`

## Salesman-scoped invoiced fetch

**What to test:**
- A one-day salesman-scoped invoiced report requests only its selected date range.
- Beta: salesman filter, `_skip_commissions`, or a layout `order` without `commissions` skips the YTD pull and omits the Commissions tab.
- Unscoped Invoiced still YTD-fetches for commissions.

**Expected behavior:**
- Salesman-scoped / shipped reports do not fetch year-to-date data because their output omits the commissions tab.
- Daily 9am Salesmen Shipped (layout without commissions) fetches only the selected period.

**Edge cases:**
- An unscoped report keeps the existing year-to-date query for its commissions tab.
- Empty/missing layout `order` still fetches YTD (old schedules).

**Test files:** `tests/test_invoiced_loader.py`, `v3/tests/test_report_service.py`, `v3/tests/test_report_invoiced.py`, `v3/tests/test_delivery.py`

---

## v3 master schedule split-email MVP

**What to test:**
- Admins and developers see company schedules on `/schedules`; salesmen see My schedules only.
- Managers do not see the company list; admins and developers do. Create/update APIs are privileged; managers and salesmen 403 on create.
- Private master rows stay off the company list and show under My schedules for the owner.
- A manager-owned master run is scoped to that manager’s salesman keys. Unscoped (no owner/run-as, or privileged owner) stays unrestricted.
- Master schedule params persist salesman delivery flags (`split_by_salesman`, `email_to_salesmen`, `email_salesman_keys`).
- Master schedule delivery sends the full workbook to typed recipients/SharePoint and split salesman-filtered files to `salesmen.email`.

**Expected behavior:**
- `/master-schedules` redirects privileged users to `/schedules#company`; salesmen get 403. Create/update APIs are privileged; managers and salesmen 403 on create.
- Salesman split emails use raw SalesGroup values for report params and normalized keys only for email lookup.

**Edge cases:**
- A master schedule with only salesman email targets can be saved.
- Missing salesman email is recorded as a failed requested delivery.

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_salesmen_seed.py`.

---

## Cancel a running report job

**What to test:**
- A queued job can be cancelled (it never starts).
- A running job can be cancelled (the user can stop a run stuck on a slow Reporting API call).
- A finished job (success/failure/already-cancelled) cannot be cancelled.
- The cancel endpoint is owner-scoped: one user cannot cancel another user's job.
- Cancelling does not get clobbered: when the slow upstream call finally returns, the late `mark_success`/`mark_failure` is a no-op because it's guarded to `status='running'`.
- The report view renders the Cancel button and its endpoint URL.

**Expected behavior:**
- `JobRepository.cancel` returns True and sets status to `cancelled` for queued OR running jobs; False for terminal jobs.
- `POST /api/jobs/<id>/cancel` returns `{cancelled, status}`; 404 for a job the caller doesn't own.
- On screen: clicking Cancel stops the poll loop within ~1s, shows "Run cancelled.", and the Run button is re-enabled.

**Edge cases:**
- The worker thread for a running job stays blocked until the upstream call ends; cancellation only stops the screen waiting and prevents the result from being shown/stored — it does not force-kill the in-flight HTTP request.

**Test files:** `v3/tests/test_jobs.py` (repo behavior), `v3/tests/test_blueprints.py` (endpoint + template).

---

## Scheduling (rebuild): cadence, Shabbos skip, deliveries, management UI

**What to test:**
- Cadence: a daily/weekly/monthly schedule is "due" only at/after its time, only on its day, and at most once per Eastern day (the `last_run_at` guard). Bad cadence (weekly with no day, unknown frequency) is rejected with a clear message.
- Shabbos/Yom Tov: inside a candle->havdalah window is restricted (Shabbos, or the named Yom Tov); outside is not. The check fails OPEN on any error, including a malformed-but-successful Hebcal response (a calendar hiccup must never block every send).
- Deliveries: a `self` schedule scopes to the owner's allowed salesmen and addresses owner + extras; an unmapped owner produces no delivery; a privileged owner scopes to "all". A `master` schedule produces one send per salesman number, each scoped to ONLY that salesman, addressed to the people mapped to that salesman plus extras; a salesman with no recipients at all is skipped.
- Poller: a due schedule is queued at most once per day (it's stamped as run the moment the durable job is queued, so a timed-out/failed job can't re-fire it that day).
- Catch-up after Shabbos: a run skipped for Shabbos flags `catch_up_pending` (and stamps the day so the cadence doesn't also fire it); once Hebcal says it's no longer restricted, the poller queues the catch-up under a separate dedup key; the run handler clears the flag when it actually runs.
- Failure alerts: a run where every attempted delivery failed (and wasn't cancelled) emails the owner a heads-up and, for a private schedule, creates one in-app notification tied to that schedule. A manual "Run now" queues a job with `manual:true` and ignores the Shabbos skip; running it dismisses the matching notification. A person can't dismiss someone else's notification (403).
- Authorization: only admins reach `/admin/schedules`; a regular owner can manage their own self-schedule but NOT a master schedule and NOT someone else's; every state-changing POST carries CSRF.

**Expected behavior:**
- `cadence.due_now/normalize/describe` behave as above; `sabbath.melacha_assur` returns `(bool, reason)` and never raises.
- `run.expand_deliveries` returns the correct scoped deliveries; `run_schedule` writes a `schedule.run` audit line per delivery (sent/failed/skipped) and stamps the schedule.
- Routes return 200 for allowed pages, 403 for disallowed management, 302 (redirect + flash) for bad input instead of 500.

**Edge cases:**
- A wide master schedule runs its salesmen sequentially inside one worker job capped at `max_job_seconds`; very large ones may need splitting (noted in DECISION-LOG).
- A failed or refused (unconfigured mailer) send is still audited and still consumes the day's run.

**Test files:** `rebuild/tests/test_scheduling.py` (cadence, sabbath, deliveries), `rebuild/tests/test_schedule_routes.py` (authz, CSRF, once-a-day, catch-up after Shabbos, whole-run failure notify, manual run-now + ignore-Shabbos, notification ownership), `rebuild/tests/test_email.py` (failure-notice composition, escaping, audited-when-off).
