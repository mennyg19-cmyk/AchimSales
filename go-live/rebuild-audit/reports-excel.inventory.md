# Inventory: reports-excel (live v3)

Model: claude-fable-5-1-thinking-medium
Runner: spawn
Area: reports-excel
Role: inventory
CodeGraph: `codegraph` not on PATH, `.codegraph/` absent -> graph via parent digest.

## Proof-of-read

- AUDITOR-INSTRUCTIONS.md: 37 lines; scope = live `v3/` only, no app-code edits, no rewrite proposal, <=10-line reply.
- graph-backbone/INDEX.md: 4 area digests, 5 worker job-type constants, 4 roles (privileged = admin + developer).
- graph-backbone/reports-excel.md: 9 registry keys (8 BUILT, 1 BACKLOG), 43 route rows listed in the digest table (verified 43 `@reports_bp.*` decorators in `web/blueprints/reports.py`, 1684 lines), 5 frontend files, 9 reporting-stack modules.
- Files read in full: `registry.py`, `contracts.py`, `reports.py`, `report.ts` (3383 lines), `export.py`, `export_jobs.py`, `params.py`, `report_service.py`, `lookups.py`, `last_order_export.py`, `delivery/layout.py`, `scheduling/company_layouts.py`, `main.ts`, `report_view.html`, `reports_list.html`, `customer_last_order_pick.html`, `customer_last_order_view.html`, all 8 `report_engine/reports/*.py`.
- Extra codegraph queries I would have run: `codegraph callers assert_report_runnable`, `codegraph callers build_workbook`, `codegraph impact serializeLayout`, `codegraph explore "company views schedule"`.

## 1. Report registry (`report_engine/registry.py`)

| key | title | status | builder_version | flags | filters exposed (`REPORT_FILTERS`) |
|---|---|---|---|---|---|
| ordered | Ordered | BUILT | 8 | salesman_default | period, status, customers, salesman |
| invoiced | Invoiced | BUILT | 1 | salesman_default | period, customers, salesman |
| salesman | Salesman | BUILT | 1 | | year, salesman |
| number_4 | Number 4 | BUILT | 5 | | n4_mode |
| customer_activity | Customer Activity | BUILT | 1 | salesman_default | salesman |
| customer_last_order | Customer's Last Order | BUILT | 1 | in_app=True | none (own pages) |
| item_averages | Item Averages | BUILT | 1 | privileged_only | none (fixed window) |
| sales_by_state | Sales by State | BUILT | 1 | | year |
| customer_aging | Customer Aging | BACKLOG | 1 | salesman_default | rendered as disabled "Coming soon" card; `_built_spec_or_404` rejects it on every API |

Flag semantics that must survive:
- `salesman_default`: what a salesman sees when per-report access is "inherit". Non-default reports are hidden from salesmen until an explicit allow.
- `privileged_only`: admin/developer only, even with an allow row (Item Averages).
- `in_app`: `/reports/customer_last_order` redirects to the picker page.
- `builder_version` is part of the cache/dedup key so old cached payloads (v2 Ordered, v4 Number 4) are never reused.

Drift ledger (`contracts.py`): 11 `DriftDecision` entries, all `signed_off=True`, owner menny. Two are `NEW` (ordered `summary_remainder` = Ordered - Released - Shipped - Cancelled; number_4 `salesman_source` = order-line SalesGroup, fallback customer master). Rest `LIVE_ROOT`. These are business rules; do not re-decide silently.

## 2. Filter option lists (`reports.py`)

- `PERIOD_OPTIONS` (8): all_time "All Time", mtd, last_month, ytd, this_week, last_7_days, daily "Yesterday", custom "Custom Range" (custom reveals From/To date inputs). Deep-link/preset alias: `yesterday` -> `daily` (`mapPeriodValue`).
- `N4_MODE_OPTIONS` (3): both, by_customer, by_item.
- `STATUS_OPTIONS` (5): "" All Statuses, "Open order" Open, Delivered, Invoiced, Cancelled. Preset alias `open` -> `Open order`.
- Year picker: descending from current Eastern year back to `D365_GO_LIVE.year` (`_year_options`, also served at `/api/reports/<key>/years`).
- Salesman dropdown: raw `SalesGroup` values from customer universe, display name from salesman master; scoped to `visible_salesman_keys`. "All salesmen" default.
- Customers: searchable multi-select combobox (200-row cap in dropdown), removable pills, filtered by chosen salesman; changing salesman clears picks. Run validates picks via `LookupService.ensure_customers` (forced resync; 400 "Unknown customer(s)" if still unknown).
- Lookup status polling (`/api/reports/lookups/status`, 2.5s) shows "(loading...)" / "(using cached list)" until the universe is ready.

## 3. Per-report tabs and columns (builders)

### ordered (`ordered.py`, SP `ordered_report`)
Tabs in order: **Summary**, **By Customer**, **By Item**, **By Order**, **By Salesman** (omitted when a salesman filter is set: `skip_by_salesman`), **Full Data**.
- Qty fields: QtyOrdered, QtyReserved, QtyReleased (header "QTY Shipping"), QtyCancelled, QtyLeftToShip (header "Qty left to ship"). Dollars: Ordered $, Cancelled $, Released $ (header "Shipping $"), Open $ = Ordered - Shipped - Cancelled. Shipped $ not shown.
- Fulfillment % = (QtyOrdered - QtyCancelled)/QtyOrdered clipped 0..1; red->yellow->green cell fill on screen and in Excel.
- Full Data cols (23): SalesOrderNumber, CustomerAccount, CustomerName, SalesOrderName, OrderDate, purchid, ExpectedArrivalDate, ShipDate, LineNumber, Item#, ItemName, UnitPrice, Status, Fulfillment %, 5 qty, 4 dollar.
- By Customer: CustomerAccount, CustomerName, Salesman + FF + qty + $; sorted Ordered $ desc; `default_group=["Salesman"]` (empty when salesman-filtered).
- By Item: Item#, ItemName, purchid, ExpectedArrivalDate + FF + qty + $.
- By Order: SalesOrderNumber, OrderDate, CustomerAccount, CustomerName, Salesman, PO #, Order Status (stub, blank until SP supplies), Status + FF + qty + $; sorted OrderDate desc; `default_group=["Salesman"]`.
- By Salesman: Salesman + FF + qty + $.
- Summary: Customer Name, Salesman, Item Number, Line Description, purchid, ExpectedArrivalDate, 5 qty, Net Price (`sum: False`, never totalled), Extended Price - Ordered, Extended Price Cancelled, Extended Price Remainder (= ShippingDollars). `default_layout` = group Customer Name, sort Customer Name asc then Item Number asc; `default_group` Salesman.
- ERROR ITEM lines dropped (item number regex). `stub_fields=["OrderStatus"]` + `STUB_NOTE` on non-summary tabs.
- Orchestrator: bounded periods fetched month-by-month (`_facts_chunked`); multi-customer selection post-filtered (SP takes one CustomerAccount).

### invoiced (`invoiced.py`, SP `invoiced_report`)
Tabs in order: **Summary by Customer**, **Commissions** (conditional), **Full Details**, **Credits**, **Invoices**, **Audit - Reversals** (only when an invoice has both + and - totals), **Totals by Salesman** (only when 2+ salesmen).
- Money cols: SubTotal Invoices, Tariff Charges, Freight Charges, CC Charges, Misc Charges, Total Invoice. Summary uses "Total ..." headers + InvoiceCount (nunique invoices).
- Full Details nets duplicate invoice rows when SQL returns reversal pairs.
- Commissions: `layout: "commission_cards"` with per-salesman monthly blocks (SubTotal, Tariff, Freight, CC, Total Invoices, Credits, Net Commission = TI + credits - freight - CC, Commission = net * pct, YTD, Total Payable) plus a flat `columns/rows` table (Salesman, Commission %, one column per month, YTD Commission, TOTAL row). YTD pull = Jan 1..period end; single SP pull when period sits inside YTD. Rate = SP per-row rate else salesman master.
- Commissions omitted when: viewer lacks `may_see_commissions` (`_skip_commissions` param + `drop_commissions_tab` on result/export + client `data-hide-commissions`), a salesman filter is set, or a saved `layout.order` excludes `commissions`.
- Fallback `_commissions_simple` (Percent, Commission Base = SubTotal + Tariff, Commissions) when no YTD facts.
- Unassigned SalesGroup -> label "Unassigned". `fill_invoiced_sales_group` backfills numeric/unknown SalesGroup from customer master.

### salesman (`salesman.py`, SP `monthly_salesman_yoy`)
12 tabs Jan..Dec, each 16 columns: Sort Number, Salesman, Cust. #, Customer Name, then 3 colour bands (`band` 0/1/2): month TY/LY + $ diff + % diff (blue), Jan-thru-month YTD TY/LY + diffs (green), full-year TY/LY + diffs (purple). Negatives red. Bands follow field identity, not column letter (survive hide/reorder). Sort by zero-padded salesman number then Cust. #. Salesman dropdown pick post-filtered against master aliases (`_salesman_report_scope`). `ThroughMonth` = current month for current year else 12.

### number_4 (`number_4.py`, SPs `customer_item_sales_rolling_12` / `item_customer_sales_rolling_12`)
Mode both -> 4 tabs: **By Customer (12 Months)**, **By Customer (YTD)**, **By Item (12 Months)**, **By Item (YTD)**; single mode -> 2 tabs. Columns: SP headers with month columns (`Jul-25 Qty`, `Jul-25 $`, or `2025-07 $`) sorted chronologically before trailing block Total Qty, Total $, Avg Price, Book Price, Salesman. Aliases avgprice/averageprice/bookprice canonicalised. Missing Total $/Total Qty/Avg Price filled. YTD tabs keep current-year months, recompute totals, drop idle rows. `default_group=["Item #"]`. Headers come from API column list so zero-row runs still show headers. Same ordering enforced in `report.ts orderNumber4Columns` and `delivery/layout.py`.

### customer_activity (`customer_activity.py`, SP `customer_activity`)
**All** tab (Salesman, Customer Account, Customer Name, Last Order Date, PO #, Sales Order Number) then one tab per salesman (`sm_<slug>`, no Salesman column) and **Unassigned** last. Case-sensitive Customer Name sort. Rows scope-filtered by Salesman.

### customer_last_order (`customer_last_order.py`, SP `customer_last_orders`, OrderCount=10)
Own pages, not the grid. Picker: salesman dropdown (unrestricted users only) + search, 200-row cap, retries while lookups warm. View: header card (Order Number, Order Date, PO # = common PO prefix across merged orders, Salesman), "Add previous order" modal (checkbox list of logical orders from `/recent-invoiced`, applied via `?orders=a,b`), merged-orders list, Items table (Item #, Description, Qty Ordered, Qty Shipped, Qty Cancelled, Sales Price, Total) rolled up by (item, price) with totals footer, Export modal -> Excel (openpyxl, "Last Order" sheet) or PDF (hand-written PDF 1.4, `last_order_export.py`), file `Last_Order_<name>.xlsx|pdf`. Access = per-report grant + customer-master sales group scope (`assert_can_view_customer`); unknown account with zero rows leaks nothing. Errors render a clean card, never 500.

### item_averages (`item_averages.py`, SP `item_customer_sales_rolling_12`)
One tab: Item #, Item Name, 12-Month Qty, Avg/Month (= /12), Avg/Week (= /52). Company-wide, ignores scope (privileged only).

### sales_by_state (`sales_by_state.py`, 3 SPs)
**Summary** (State, Sales amount, New York City Sales amount on first row only; sorted by sales desc), **New York City** (Invoice, Amount, Shipped_From, Source_Address, Customer_Name, State Code, State, Postal Code), **Detail** (adds Invoice Date, Customer Account, Customer Name, Delivery Address). Excel-serial dates handled. Year -> Jan 1..Dec 31; custom period wins.

## 4. Routes (43) and behaviours that must not be lost

Pages: `GET /` list; `GET /reports/<key>` grid (redirects CLO); `GET /report/customer-last-order` picker; `GET /report/customer-last-order/<account>` view; `GET /report/customer-last-order/<account>/export?format=xlsx|pdf&orders=`.

Run lifecycle: `POST /api/reports/<key>/run` (202 job_id; enqueues `report.run` with visible_keys + builder_version in params; inline `worker.drain()` only non-prod), `GET /api/jobs/<id>` (owner-only, fail-closed on NULL owner), `POST /api/jobs/<id>/cancel`, `GET /api/reports/result/<id>` (409 while not success, 404 expired, 403 `_assert_scope_compatible` when user's scope narrowed since the run, commissions stripped for non-privileged), `GET /api/reports/active` (queued/running + finished <48h + Kept; drives floating Recent Reports bar and resume-on-return), `POST /api/reports/runs/<id>/keep` (30 days, cap 5, optional name <=80 chars).

Export: `POST /api/reports/<key>/export/<job_id>` body = serialized layout -> background `report.export` job deduped on (owner, source job, layout hash); `GET /api/reports/exports/<id>/download` (owner + authz + `_export_in_scope` + 409 not ready + 404 expired blob, filename `<Title>_Report_<Period>_<Year>.xlsx`); `GET /api/reports/exports` (last 15 after scope filter; status/progress/size/ready).

CLO APIs: `/api/report/customer-last-order/customers?salesman=`, `/salesmen`, `/<account>/recent-invoiced`.

Lookups: `/api/reports/lookups/status`, `/api/reports/<key>/salesmen`, `/api/reports/<key>/customers?salesman=`, `/api/reports/<key>/years`, `POST /api/reports/<key>/preview-body` (developer only; exact SP request body; Number 4 by_item swaps SP id).

Diagnostics (developer or `DIAG_RECONCILE_KEY`): `/api/reports/diagnostics/reporting-api?live=1` (tcp/http/live SP probe, job summary, claim probe, worker wiring), `reconcile-salesman-invoiced?k=&year=&through_month=&scope=ty|ly|all&month=`, `reconcile-number4-invoiced?k=&view=&month=&as_of=`, `claim-once` (POST only mutates), `precious-repair` (GET check only; POST backup/reindex/delete-ghosts/rebuild-jobs).

Saved views: `GET /api/saved-reports` (all my presets); `GET /api/reports/<key>/presets` -> `{default, company[], presets[], others[] (privileged: grouped by owner)}`; `POST` create (name required, "Default" reserved, privileged may set `owner_user_id`); `GET/PATCH/DELETE /api/reports/presets/<id>` (owner, or any preset for privileged); `GET/PUT /api/reports/<key>/default-view` (PUT needs `can_see_company_schedules`); `GET /api/reports/<key>/company-views/<id>`, `PUT /api/reports/<key>/company-views` (upsert by name; params stored without window keys), `DELETE .../company-views/<id>` (need `can_see_company_views` + `can_see_company_schedules`).

Delivery: `POST /api/reports/<key>/email-now` (recipients and/or sharepoint_path required; SharePoint needs `has_sharepoint_access`; enqueues `report.deliver` with params, layout, subject, report_name); `GET /api/sharepoint/status|folders?path=`; `GET /api/onedrive/status|folders?path=` (502 with Graph error message on failure).

## 5. Home page (`reports_list.html`)

Sections: built report cards (in_app card links to picker, others to grid; empty state "no access"), **Company views** cards (only if `can_see_company_views`; deep-link `?cview=<id>&<params>`), **My presets** cards (deep-link `?preset=<id>&<params>`), **Coming soon** disabled cards for BACKLOG. Card subtitles: "Pick a customer · store-visit view", "Interactive · Excel export", "<Report> · company view", "<Report> · saved view".

## 6. Grid page controls (`report_view.html` + `report.ts`)

Filters & options panel: collapsible with one-line summary of selected options; per-filter help `?` buttons (help keys `report-<key>`, `param-period`, `param-n4-mode`, `param-status`, `param-year`, `param-salesman`, `param-customers`; `help_content.js` also has `param-custom-dates`, `param-save-preset`, `param-background`). Buttons: **Run report**, **Email me** (runs + emails Excel to self via email-now, polls 60s). Developer only: editable **API preview** textarea + "Run with this body" (override params).

Layout toolbar (always visible): **Columns** (panel: Tabs checkboxes to hide/restore server tabs, Columns checkboxes, "Show all"), **Reset layout**, **Save for** select (privileged: Me / Company / any other active user), **Save this view**, **Saved views** panel, **More** menu -> **Schedule** (with hint text), **API preview** (developer).

Status row: progress text "Building report… N% (elapsed)", reconnecting after up to 5 consecutive poll errors, 10-minute timeout, **Cancel** button only while running.

Result actions: **Refresh** (re-run, keep layout, clones re-created from refreshed base), **Keep this run** (name prompt), **Export** menu -> "Download Excel now" (auto-download only if still on same page and visible) / "Recent exports…" panel (Download with size, Expired, Failed, Building N%), **Email** modal (recipients, subject default = page title, optional SharePoint folder picker with breadcrumb + "Use this folder").

Tabs: click to activate; caret/right-click menu: Duplicate tab, Rename tab (duplicates only), Remove/Delete tab (not the last one). Removed tabs restorable from Columns panel in catalog order. Meta shows "N rows · as of <generated_at>".

Grid (Tabulator 6.3.1 from unpkg): fitDataTable, movable + resizable columns (widths persisted per view), multi-sort, bottom calcs sum on money/int (never percent, never `sum:false`/Net Price), header menu: Hide column / Freeze-unfreeze / Group by this column / Add subgroup / Clear grouping. Group pills with remove. Nested group header/footer colours shared with Excel (5 header shades, 4 footer shades, grand grey). Per-column Excel-style filter funnel: text ops (contains, equals, starts, ends, in, empty, notEmpty), numeric ops (eq, ne, gt, ge, lt, le, between, empty, notEmpty), date ops (on, before, after, between, empty, notEmpty). Commission Cards tab renders as custom HTML blocks (no grid, Columns disabled). Formats: money $ 2dp, int thousands, percent 1dp, date ISO; salesman band colours + red negatives; Fulfillment % fill.

View state serialised per tab (`serializeLayout`): `{active, order, clones[{key,baseKey,name}], views{tab: {hidden, frozen, order, sorters, columnFilters, group, widths}}}`. Back-compat: legacy `headerFilters` -> contains.

Deep links (`applyDeepLink`): period, status, year, mode, salesman (applied after options load), start_date, end_date, customers CSV; `?job=<id>` resumes a specific run; `?preset=<id>|default` / `?cview=<id>` load and auto-run (cview only if period runnable). Without a preset param the page reconnects to this report's last queued/running/successful run.

Saved-view rules (client): Default view = company default (params + layout) auto-applied after each run when no preset pending; editing Default / company views requires `data-can-edit-default`; company view save strips window keys and may be saved without running; personal presets: same name overwrites, "Default" reserved; Edit mode loads filters + layout without running if a report is on screen; Delete confirms. Schedule button enabled only when a named saved view or Default (privileged) is loaded and not dirty (params or layout changed); custom date range cannot be scheduled.

Schedule modal (from report): Email to <me> checkbox; privileged: extra recipients, CC, BCC; frequency daily/weekly (weekday checkboxes)/monthly (1..28 or Last day); time (default 08:00); filename template with tokens {Report} {Schedule} {MM} {Month} {YYYY} {Period} {DD} {Weekday} and live preview (`filename_preview.ts`, default `{Schedule}_{MM}-{DD}-{YYYY}`); OneDrive folder picker; SharePoint picker (privileged with access; SP wins over OneDrive, `folder_kind`); "Email me when there is no data"; privileged "Email test addresses when there is no data". Posts to `schedules.create_schedule` with `saved_report_id` or `view_name="Default"` + report_key + params. Expects 201.

## 7. Excel writer (`export.py`) behaviours

Write-only openpyxl; one sheet per tab (title sanitised, <=31 chars, deduped); header row bold grey E0E0E0 centred wrapped with borders; freeze A2; auto-filter only on ungrouped sheets; column widths by type; number formats money `"$"#,##0.00`, int `#,##0`, percent `0.0%`, date `YYYY-MM-DD`; formula-injection prefix, control-char strip, 32767-char clamp; NaN/inf -> blank. Grouping: nested banners "<Header>: <value>" + "Total — <value>" per level + "Grand total" (or "Total" when ungrouped); group fields sorted first unless all covered by sorters; Salesman group level dropped when a sheet has one salesman; builder `default_group`/`default_layout` used only when the view never set group; percent and `sum:false` columns never summed; label lands in first non-summable column. Salesman report: band fonts blue/green/purple by field, red negatives. Fulfillment % gradient fill. Commission tab written as live layout blocks ("Commissions Summary (YYYY)", month headers `Mon-YY`, YTD Total, Total Payable). `payload_to_xlsx` = no-layout path for deliveries/tests. `apply_layout` + `expand_clones` replay hidden/order/sorters/columnFilters and duplicate tabs; a non-empty `order` is the include-list for sheets.

## 8. Seeded company views (`company_layouts.py`)

`Daily Ordered` (ordered; By Customer grouped by Salesman, Summary grouped Salesman > Customer Name, by_order ungrouped; full tab order) and `Heshy Open Orders` (ordered; params period=yesterday, salesman=Hkaufman, status=Open order; Full Data only, grouped by SalesOrderNumber, LineNumber hidden, explicit 22-col order). Boot upserts both and stamps matching master schedules.

## 9. Cross-area dependencies (not owned here, must keep contract)

- Authorization: `can_view_report`, `assert_report_runnable`, `assert_can_view_report`, `assert_can_view_customer`, `visible_salesman_keys` (None = unrestricted), `may_see_commissions`, `has_sharepoint_access`, `can_see_company_views`, `can_see_company_schedules`, `is_privileged`, `is_developer`.
- Jobs: `report.run`, `report.export`, `report.deliver`; export handler re-authorizes owner live.
- Repositories: `saved_reports`, `company_views`, `report_defaults` (DEFAULT_VIEW_NAME, CUSTOM_VIEW_NAME), `exports`, `jobs`, `users`, `salesmen`.
- Beta: `beta_sources.get_source` may route a report to `odata_bridge.build_odata_payload`.
- Recent Reports floating bar (`main.ts`, every page): polls `/api/reports/active` every 5s, minimise state in localStorage, rows link to `/reports/<key>?job=<id>`, Kept runs get a "Name" rename action.

## 10. Notes / risks for the rebuild inventory

- Tabulator is loaded from unpkg CDN in `report_view.html` (external runtime dependency).
- `customer_aging` exists only as a disabled card; anything that renders it as runnable violates the registry rule.
- Three copies of Number 4 column-ordering logic (builder, `report.ts`, `delivery/layout.py`) and two copies of nest-colour palettes (`export.py`, `report.ts`) must stay in sync.
- `_RECENT_DONE_SECONDS`=48h, `_KEEP_SECONDS`=30d, `_KEEP_CAP`=5, exports list cap 15, dropdown caps 200 are product-visible constants.
