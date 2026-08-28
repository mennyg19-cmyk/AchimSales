# Testing Strategy

Testing plan built alongside code. Each feature/module gets an entry documenting what to test, expected behavior, and edge cases. See `testing-protocol.mdc` for rules.

A cheaper model can use this file as a guide to run the full test suite without deep context.

---

## Sol list leftovers (2026-08-28)

**What to test:**
- Custom dates raise; commission `1` is 1%; monthly commission uses each month's rate; Ordered Summary groups by CustomerAccount; Hebcal failure skips send.
- Keep this run stores a precious snapshot; cache prune does not drop it; tick prunes cache/exports and fails jobs running > 45 minutes.
- Graph 429 honors Retry-After (`test_graph_send_retries_429_then_succeeds` asserts the delay; `test_upload_session_retries_429` same for upload sessions).
- Manual Send now does not consume the scheduled slot (`test_last_run_at_ignores_manual_trigger`). Catch-up clears only after success; stays after failure/cancel. Schedule history uses payload `row_count`. Tick prune + hung-job cap (`test_tick_prunes_cache_exports_and_fails_hung`).
- `POST /api/reports/<key>/run` returns 400 for invalid custom dates (`test_run_invalid_custom_dates_returns_400`). Cancel after cache put drops the row (`test_cancel_after_put_drops_cache`).
- Bad Litestream checksum refuses install (`test_prod_bad_litestream_checksum_refuses_boot`).
- Empty-disk prod restore refuses boot (`tests/test_startup_restore.py`). Live Azure drill is not in CI.
- Hung jobs running > 45 minutes fail and are not requeued (`test_fail_hung_marks_old_running_jobs_failed_not_requeued`).
- Prod outbox-only delivery is not success (`test_prod_outbox_only_is_not_success`).
- A master schedule with no recipients, folder, or salesman split fails instead of recording success (`test_runner_master_with_no_targets_fails`).
- Demoted users cannot download a finished export that was built wider than their live scope, or an invoiced file that still has the Commissions tab (`test_demoted_admin_cannot_download_unrestricted_export`, `test_demoted_manager_cannot_download_commissions_export`).
- Master exports expire after 90 days (`test_master_exports_expire_after_90_days`).
- Job worker runs handlers with a Flask app context (`test_app_worker_runs_handlers_with_flask_context`).
- Cancel after workbook skips mail (`test_cancel_after_workbook_skips_mail`). Cancelled schedules do not send failure mail (`test_cancelled_schedule_does_not_mail_failure`). Cancel after an empty salesman split does not send the No Data Found notice (`test_cancel_after_empty_split_skips_no_data_notice`).
- `/readyz` is 503 when `.bootstrap-failed` exists (`test_readyz_503_when_bootstrap_failed`).
- Graph upload session POST retries 429 (`test_upload_session_retries_429`).
- `Config.reports_only` tracks `is_beta`. Home copy says Saved views. Report Schedule opens the Schedules wizard.
- CI: full `v3` pytest + root pytest (with `tests/conftest.py`) + `npx tsc --noEmit` + `npm run build` + dist js/css git check.

**Test files:** `v3/tests/test_dates.py`, `v3/tests/test_report_invoiced.py`, `v3/tests/test_report_ordered.py`, `v3/tests/test_sabbath.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_graph_mail.py`, `v3/tests/test_jobs.py`, `v3/tests/test_frontend.py`, `v3/tests/test_config.py`, `tests/test_startup_restore.py`

---

## Single site at / (webapp/ and rebuild/ removed)

**What to test:**
- `PrefixRedirectMiddleware` sends `/beta/reports` to `/reports` and leaves `/login` and `/auth/callback` on the home app.
- Home `/login` links to `/login/start`, not `/legacy`.
- Magic-link tokens: new token invalidates the previous; consume is one-shot; 5/email and 40/IP windows.
- Public origin for emailed links and Entra redirect is `PUBLIC_BASE_URL`, else Azure `https://reports.achimonline.com`, else loopback. Never the request Host.
- Report source map reads/writes `beta_report_sources` in precious.db.
- Base HTML in `is_beta` hides Dashboard and does not show a Beta pill.
- Home HTML has no Test Site nav and no `/test/` href.
- Prod `/static/**.map` is 404; the JS/CSS files themselves stay 200.
- Admin user JSON has no `test_access`; PUT with that key leaves the leftover SQLite column at default.

**Expected behavior:**
- gunicorn `wsgi:application` is v3 only.
- External reps still get a 15-minute one-time link.

**Test files:** `tests/test_wsgi_dispatch.py`, `v3/tests/test_auth.py`, `v3/tests/test_magic_link.py`, `v3/tests/test_public_origin.py`, `v3/tests/test_report_sources.py`, `v3/tests/test_frontend.py`

---

## P0 security containment

**What to test:**
- OData tabs without a salesman column raise for scoped users; matching keys are kept; unrestricted users still see unscoped tabs.
- Prod config rejects missing Litestream Azure account/key/container.
- `/healthz` stays liveness-only; `/readyz` is 503 when prod precious.db is missing.
- `AUTH_MODE=dev` is refused when `APP_ENV=prod`. Legacy `DEV_BYPASS_AUTH` died with `webapp/`.

**Expected behavior:**
- Scoped OData cannot return company-wide By Item (or any unscopeable tab).
- Production boot refuses empty durable state and auth bypass.

**Edge cases:**
- Empty tabs do not require a salesman column.
- `AUTH_MODE=dev` is refused in prod; there is no leftover `DEV_BYPASS_AUTH` switch.
- `/healthz` CSP does not allow unpkg or jsdelivr. Feather, Tabulator JS, and Tabulator CSS are served from `/static/vendor`.

**Test files:** `v3/tests/test_odata_scope.py`, `v3/tests/test_config.py`, `v3/tests/test_smoke.py`. CI and the Azure production build run `tools/run-p0-tests.sh`.

---

## Review security follow-up (download-file, precious-repair, headers)

**What to test:**
- A workbook in a sibling directory whose name starts with the reports root is rejected.
- An .xlsx under the reports root is served only if that real path is in the current user's history.
- `GET /api/reports/diagnostics/precious-repair?action=delete-ghosts` is 405 and leaves queued jobs. POST with CSRF deletes them. GET `check` still works for developers. Admins get 403.
- `/healthz` includes X-Frame-Options, X-Content-Type-Options, and CSP. HSTS is off in local dev.

**Expected behavior:**
- Logged-in users cannot download another user's Direct Reports xlsx by guessing the path.
- CSRF-exempt GET cannot wipe the jobs table.
- Login and API responses send the browser security headers.

**Edge cases:**
- Non-.xlsx owned files are rejected.
- POST without CSRF token is 400 and does not delete.

**Test files:** `tests/test_download_file_auth.py`, `v3/tests/test_precious_repair.py`, `v3/tests/test_smoke.py`, `tests/test_security_headers.py`

---

## Magic links, history XSS, Excel formula prefix

**What to test:**
- A second magic-link token for the same email consumes the first.
- Consuming a token twice returns None the second time.
- A sixth token create in 15 minutes returns None.
- 40 attempts from one IP trip the IP limit; another IP is unaffected.
- On Azure, emailed links use PUBLIC_BASE_URL or https://reports.achimonline.com.
- Strings starting with `= + - @` get a leading apostrophe; numbers are unchanged.

**Expected behavior:**
- Only the latest unconsumed magic link works. Claim is one UPDATE.
- Consume refuses login if the account is no longer an external salesman (covered in auth; token is still spent).
- History sheet cells are HTML-escaped. Notif diagnostic interpolations use `esc()`.

**Edge cases:**
- Empty IP skips IP throttle.
- Local dev without PUBLIC_BASE_URL emails `http://127.0.0.1:5001/...` (never the request Host).

**Test files:** `tests/test_magic_link.py`, `tests/test_magic_link_origin.py`, `tests/test_excel_formula.py`

---

## Customer access fail-closed

**What to test:**
- Missing dashboard_cache or missing salesman_key is a deny (admin still allowed).
- A salesman matches only their book's sales_group.
- A manager needs a grant for that sales_group and a known book.
- Blank D365 sales_group falls back to cache; a real D365 group can authorize with an empty cache.
- `visible_salesman_keys`: admin unrestricted, manager grants only, salesman own key, salesman without a key is empty.
- Number 4 `make_cell` and salesman `_excel_val` prefix formula leaders.

**Expected behavior:**
- Order-detail and customer-detail do not skip grant checks for managers.
- `/api/customer-addresses`, `/api/customer-price`, and generate-po 403 when the user cannot see the account.
- `/api/customers` does not return the full book to managers or keyless salesmen.

**Edge cases:**
- Last-order may pass D365 `sales_group` when cache is empty.
- Manager `?salesman=` for a key they do not hold returns an empty list.

**Test files:** `tests/test_customer_access.py`, `tests/test_excel_formula.py`

---

## Leftover XSS and Ordered/Invoiced formula prefix

**What to test:**
- Ordered summary cells prefix `=` leaders.
- Invoiced data-sheet cells prefix `=` leaders.

**Expected behavior:**
- Email chips use text nodes, not innerHTML, for the address.
- Order-entry matrix group/color/size/sku strings are escaped.

**Test files:** `tests/test_excel_formula.py`

---

## Legacy CSRF and local Feather

**What to test:**
- POST without a token is 400.
- POST with matching `X-CSRF-Token` or form `csrf_token` is 200.
- Mismatched token is 400. GET is not checked.
- POST `/auth/callback` is exempt (Entra).
- `{% csrf_token %}` renders a hidden `csrf_token` input. Login/dev/role-picker templates use that tag (not an include). Semgrep's Django form rule does not accept the Flask tag, so those form tags carry `nosemgrep`.

**Expected behavior:**
- Fetch wrapper and HTML forms send the session token. Microsoft login callback still works without it.
- Legacy pages load Feather from `/static/vendor`, not unpkg. Report form does not load Chart.js.

**Edge cases:**
- Missing session token is a deny, same as a wrong token.

**Test files:** `tests/test_legacy_csrf.py`

---

## Session role vs DB authorization

**What to test:**
- `Authorization.is_developer` follows the DB role, not the cookie.
- A demoted developer cannot open `/dev/db-explorer` or reporting-api diagnostics; they can still load `/settings`.
- A disabled user is signed out: `/` redirects to login and `/settings/theme` does not stick.
- Impersonating an inactive salesman still loads `/`; db-explorer stays 403.
- Live→v3 user copy drops a revoked salesman key on the next run.
- Legacy `refresh_session_user` rewrites a stale admin cookie to the DB salesman role and drops a deleted user.

**Expected behavior:**
- Session is identity only. Developer tools and privileged nav use the live DB row.
- Inactive own-sessions are logged out. Impersonation continues only while the real actor is an active admin/developer.
- Boot-time live user mirror replaces salesman grants instead of INSERT OR IGNORE.

**Edge cases:**
- Admin cookies cannot open developer diagnostics.
- Users who exist only in the session cookie and not in `app_users` are not a supported login path; `AUTH_MODE=dev` is refused in prod.

**Test files:** `v3/tests/test_session_authz.py`, `v3/tests/test_seed_users_grants.py`, `v3/tests/test_auth.py`, `v3/tests/test_blueprints.py`

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
- `company_views` upsert rejects Default/Custom; GET presets includes `company`.
- Managers/admins PUT a company view; salesmen GET (`can_edit` false) and 403 on PUT.
- Home page shows a Company views section with `?cview=` links.
- Boot stamps daily company Ordered schedules with Daily Ordered (salesman then customer). Salesman-split and already-named views are left alone. Heshy open-orders (Hkaufman + Open) gets Heshy Open Orders (Full Data only, hide LineNumber, sort customer then order, group by order).
- Send with that view name uses the live company layout even if the schedule snapshot is stale.
- Excel nested groups write banners/totals per level. Sort-then-group keeps customer clusters and does not add a customer total when the only group field is order number.
- Ordered Full Data has CustomerName and ShipDate. Missing SP Ship Date stays blank and still builds.

**Expected behavior:**
- Saved views lists Default, then company views, then personal. Wizard has a Company views optgroup. Schedules View column shows the stamped names.
- Daily Ordered emails group By Customer by salesman then customer. Heshy’s file is one Full Data sheet, customers together, totals per order, no LineNumber.

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
- Requested live SharePoint path that fails still fails the whole delivery (unchanged).
- Graph 413 on a small attachment still retries once without the file.

**Test files:** `v3/tests/test_delivery.py`, `v3/tests/test_scheduling.py`

## Number 4: YTD tabs, By Item no money, group by item

**What to test:**
- Both mode builds four tabs (By Customer 12 months + YTD, By Item 12 months + YTD).
- By Item tabs have no money columns; By Customer still has month $ / Total $ / Avg Price / Book Price.
- YTD keeps current-year months only and recalculates Total Qty / Total $ / Avg Price.
- YTD drops rows with no current-year qty or dollars.
- Every tab sets `default_group` to Item #.
- Excel By Item headers are quantity-only.
- OData extra_files dicts are read as paths; Item/Customer sheet names do not collide.

**Expected behavior:**
- Mode By Item → two qty-only tabs. Mode By Customer → two tabs with dollars. Both → four tabs.
- Grouping starts on Item # until the user changes it.

**Edge cases:**
- Empty view still keeps headers.
- Prior-year-only rows appear on 12 Months and vanish on YTD.

**Test files:** `v3/tests/test_report_number_4.py`, `v3/tests/test_report_service.py`, `v3/tests/test_odata_number4.py`, `tests/test_number_4.py`

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

Superseded 2026-08-27: `webapp/` and extra mounts are gone. See **Single site at /** at the top of this file.

## Login page and developer role picker on home

**What to test:**
- Logged-out `/login` is the Microsoft / External Rep page.
- `/login/start` starts MSAL on this app.
- A developer session can open `/dev/role-picker`, pick a user, then open the picker again.

**Expected behavior:**
- Home login shows "Achim User Login" linking to `/login/start`.
- Role picker lists users; View as Selected User then View as Admin (yourself) both 302 home.

**Test files:** `v3/tests/test_auth.py`, `tests/test_wsgi_dispatch.py`
`

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
- Blank `filename_template` uses the schedule name plus Eastern date and time, not just the report type.
- Two company schedules on the same report get different filenames.
- Missing schedule name falls back to the report title slug.

**Expected behavior:**
- `Daily 9am` and `DailyOrderReport` no longer both become `Ordered_YYYYMMDD.xlsx`.
- Custom templates still expand tokens as written.

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
- Admins and managers see company schedules on `/schedules`; salesmen see My schedules plus the shared Add wizard, never the company list.
- Managers can create/share; they edit only rows they created or that run as them. Other shared rows are read-only with an admin note.
- Private master rows stay off the company list and show under My schedules for the owner.
- A manager-owned master run is scoped to that manager’s salesman keys. Unscoped (no owner/run-as, or privileged owner) stays unrestricted.
- Master schedule params persist salesman delivery flags (`split_by_salesman`, `email_to_salesmen`, `email_salesman_keys`).
- Master schedule delivery sends the full workbook to typed recipients/SharePoint and split salesman-filtered files to `salesmen.email`.

**Expected behavior:**
- `/master-schedules` redirects managers and admins to `/schedules#company`; salesmen get 403. API create/update stay company-viewer gated; salesmen still 403 on create.
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

**Test files:** `v3/tests/test_scheduling.py` (and related v3 schedule tests). Rebuild's copies of these files were deleted with `rebuild/`.
