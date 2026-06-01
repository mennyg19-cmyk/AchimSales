# v3 Rebuild - Weekend Review Log

This is the running log of the autonomous v3 rebuild. Read the sections in this order
when you get back:

0. **DECISION JOURNAL (plain English)** - every choice I made, in normal words: what I had
   to decide, the options, what I picked, and why. Start here.
1. **NEEDS HUMAN SIGN-OFF** - decisions only you can make (report calculation rules,
   cutover). Nothing financial was decided silently; each item below is built to LIVE/root
   behavior as PROVISIONAL until you sign off.
2. **OPEN QUESTIONS / BLOCKERS** - things I could not resolve without you or external access.
3. **GPT-5.5 REVIEW FINDINGS** - per-phase review results and how I resolved them.
4. **PHASE PROGRESS** - what got built, with commit references.

Authoritative plans: `.cursor/plans/v3_rebuild_plan_81336296.plan.md` (opus48) and
`.cursor/plans/gpt55_rebuild_plan_8e9d2b54.plan.md` (gpt55). Rules: `.cursor/rules/v3-rebuild.mdc`.

---

## 0. DECISION JOURNAL (plain English)

> Plain-words record of every real decision, newest at the bottom. Format for each:
> **What I had to decide -> The options -> What I chose -> Why.** Skim the bold lines if
> you're in a hurry; we'll walk through anything you want to change.

### Session: Fri May 29 (before Shabbos) - your ground rules + going live at /test

**1. The big one: which app is the "source of truth" for reports?**
You told me: the LIVE app's reports are "god." The test app was a rebuild whose *point* was a
nicer on-screen table (interactive, customizable) instead of dumping straight to Excel.
- *Options:* (a) copy the test app wholesale, (b) copy the live app wholesale, (c) blend them.
- *Chosen (c), split by concern:*
  - **How it's built / how it behaves (architecture + UX)** -> follow the **TEST app**:
    reports render as an interactive table **on screen first**, and only turn into an Excel
    file **when you click Export**.
  - **What the report looks like - the columns, their order, the layout/format** -> follow the
    **LIVE app** (specifically, match the format of the live app's *exports*).
  - **The numbers / all the math** -> follow the **LIVE app**, exactly.
- *Why:* you said the live numbers are what the business runs on, so I never want v3 to show a
  different number than live. But the test app's on-screen experience is the upgrade you want to
  keep. Splitting it this way gives you live-correct content in the better test-style shell.

**2. Special case: the Commissions tab inside the Invoiced report.**
- *Decision:* build it the way the **test app** does (views nicely on screen), and when exported
  it should match the **live app's** export. (Same rule as #1, called out because you flagged it.)

**3. Sign-in for the preview at report.achimonline.com/test.**
- *Options:* real Microsoft (Entra) login like live; a dev "pick a user" screen; or just mimic the
  test app.
- *Chosen:* **real Microsoft (Entra) login, same as the live app**, reusing the redirect URL that
  already works for /test.
- *Why:* it's going on the real domain, so it should behave like the real thing - no fake login.

**4. If I run out of time to verify every report's math by Sunday.**
- *Options:* hide any report I haven't fully matched to live ("coming soon"), OR show everything
  and clearly flag the not-yet-verified numbers.
- *Chosen:* **show everything, with a clear "numbers not yet verified" flag** on anything I
  haven't confirmed against live.
- *Why:* you said you want to *see* the whole app Sunday. The flag makes sure you're never misled
  into trusting an unverified number.

**5. Backing up saved settings (the "Litestream" question).**
Plain version: the app keeps a small file on the server for prefs, schedules, and who-can-see-what.
Azure can wipe that file on a restart. Litestream copies it to cloud storage so it survives.
- *You asked me to just set it up* (you're logged into the Azure CLI).
- *What I did:* created an Azure Storage account **`achimsalesreportsv3`** with a container
  **`litestream`** in your existing resource group **`AchimReportsApp`** (Canada Central, same
  region as the app). At deploy time I'll pull the access key straight from your Azure CLI session
  and set it as an app setting, so **the secret never gets written into the code or this chat.**
- *Why this account/region:* same resource group and region as the web app = lowest latency and
  one place to manage everything. Cheapest redundancy tier (LRS) is plenty for a settings backup.

**6. Don't lose the old test app.**
- *Chosen:* keep the current test app in the codebase **and** still reachable at a second URL
  (planned: **/test-legacy**); point **/test** at the new v3 app.
- *Why:* you can compare old vs new side by side, and we can instantly flip back if needed.

**7. (My call, logged) How /test will switch to v3.**
- Today `wsgi.py` already serves the live app at `/` and the old test app at `/test` side by side
  (via a dispatcher). I'll **swap the v3 app into the `/test` slot** and move the old one to
  `/test-legacy` - a small, reversible change in one file. No impact on the live `/` app.

**10. Reference vs copy (you flagged this while reading my thinking).**
- *Decision:* the test and live apps are a **reference for WHAT the app does** - the behavior, the
  data source, the report columns, and the math - **NOT code to copy**. v3 is a clean rebuild; I
  re-implement everything in v3's own architecture and coding standards.
- *In practice:* when I open a test/live file, it's to read off the rules ("ERROR ITEM rows are
  dropped", "credits are invoice numbers starting CRD/CM/FC", "Summary columns are X, Y, Z") and
  then write fresh, well-structured v3 code for it. I won't paste their functions in. Same outcome
  and same numbers, better internals.
- *Why:* the whole point of v3 is correct, maintainable code - copying the old implementations
  would drag their shortcuts along with them.

**9. Where the data comes from (you added this after).**
- *Decision:* v3 pulls report data from the **same on-prem Reporting API the TEST app uses**
  (the `REPORTING_API_*` stored-procedure service), NOT the live app's direct D365 connection.
- *What this means in practice:* the LIVE app talks straight to D365 (OData). The TEST app instead
  calls an on-prem API that runs stored procedures and returns rows. v3 uses that TEST-style API.
- *Why it matters / what I'll watch:* the two sources can name or shape fields differently, so for
  each report I keep a thin "adapter" that turns the Reporting API's rows into a clean shape, then
  apply the LIVE math/format on top. If the API doesn't expose a field the LIVE math needs, I'll
  flag it in "NEEDS HUMAN SIGN-OFF" rather than guess (e.g. the live `ordered` report uses some
  D365-only joins). Good news: v3's data client was already built against this Reporting API.

**8. (My call, logged) Shipping the built front-end to Azure.**
- The front-end is bundled by a Node tool (esbuild) into files the browser loads. Azure's Python
  image may not run that Node build. *Decision:* I'll **commit the built files** so the deploy is
  reliable without depending on a Node step on the server. (If you'd rather build on deploy, easy
  to switch - noted as a future option.)

**11. Invoiced report: a few math details I matched to LIVE (after a GPT-5.5 review).**
When I built the Invoiced report I had GPT-5.5 tear it apart and check the numbers against the
real live report. It caught four things where I'd drifted, and I fixed all four to match LIVE
(your "god"):
- *What counts as a credit:* the live report flags a row as a credit if the invoice number
  **contains** "CRD", "CM", or "FC" anywhere (not just at the start). The test app only looked at
  the start - I'd copied that idea. Switched to the live "contains" rule. (Side effect to be aware
  of: an invoice number that happens to contain those letters mid-string gets treated as a credit -
  that's exactly what live does, so we match it.)
- *"Totals by Salesman" tab:* live builds this from **invoices only** (credits excluded). I was
  including credits. Fixed.
- *"Summary by Customer" invoice count:* live counts **distinct invoice numbers**. Mine could
  over-count in a rare case (same invoice number split across two customers). Switched to a
  distinct count.
- *Commissions cents:* live adds up the **unrounded** monthly commission for the year-to-date
  total (each month is only rounded for display). I was rounding every month first, which could be
  off by a penny over a year. Now it matches live.
- I also made the date filter safer: a blank period or a bad custom date now just means "no date
  filter" instead of erroring.
- *Why this matters:* these are the kinds of tiny differences that would make you not trust the new
  app. Locking each one to live - with a test that fails if it ever drifts again - is how I keep
  "same numbers as live" honest.

### Session: Sun May 31 - your answers to my per-report questions

You had time and asked me to surface every question across all 5 reports. Here's what we decided:

**12. Where commission rates + salesman names/numbers come from.**
- *Options:* live config files / a v3 editable table / seed-from-config-then-edit.
- *Chosen:* **seed v3's salesmen table from the live config files now, editable later.** So the
  numbers start identical to live (commission $ match), and you can edit them in v3 going forward.

**13. Ordered report - does the on-prem API actually give shipped/cancelled quantities?**
- I dug into a real `salesline_release` dump. The API returns the order/released/remainder/left-to-load
  quantities + **precomputed** Ordered $ / Shipped $ / Cancelled $, but NOT an explicit
  "qty cancelled" column or the WHS/packing-slip detail live uses.
- *You told me:* the API's precomputed **$ columns are authoritative** (the SP already does the
  WHS/packing-slip math server-side), and you'll **update the endpoint to add qty cancelled**.
- *Chosen:* trust the SP's dollar columns as live-equal; **stub the cancelled-based quantity columns
  (QtyCancelled / QtyOpen / Fulfillment %) for now** and flag them, then wire the real values when
  the endpoint ships.

**14. Number 4 "Book Price" column.**
- The current `invoice_lines` API doesn't return Book Price. *You'll send a file* describing a new
  released-products endpoint that has it.
- *Chosen:* build Number 4 now WITHOUT Book Price (omit + flag); add the column when that endpoint
  is ready.

**15. Customer Activity - where the customer list comes from.**
- *Chosen:* pull the customer universe **live from the `customer_master` SP each run, with a fallback
  to the local mirror** if the API is down.

**16. Monthly Salesman report on screen.**
- *Chosen:* **12 month tabs (Jan-Dec), interactive** (the test-app architecture).

**17. Salesman "Sales" formula - confirmed against LIVE.**
- LIVE: `Sales = Total Invoice - CC Charges - Freight Charges` (= SubTotal + Tariff). Verified in
  `reports/salesman/builder.py`. Building the salesman report to this exactly.

**18. Built the Salesman report (12 month tabs).**
- Done: one tab per calendar month (Jan-Dec), each row = a (customer, salesman) pair, comparing this
  year's sales for that month vs the same month last year, plus YTD-through-this-month and full-year
  totals, with `$ diff` and `% diff` columns. Sales uses the formula in #17. Rows with no usable
  invoice date are dropped. Sorted by salesman number (zero-padded so "10" sorts after "2").
- *Why month tabs:* matches your #16 choice and the test app's on-screen feel.

**19. Built the Ordered report - and confirmed the "Book Price file" arrived for Number 4.**
- *Ordered, what I shipped:* the six live tabs (Summary, By Customer, By Item, By Order, By Salesman,
  Full Data) with the **exact live column names/order**. Dollar columns come **straight from the SP**
  (authoritative, per #13). Quantity buckets (QtyShipped/QtyCancelled/QtyOpen) and Fulfillment % are
  still **derived on the interim rule and flagged as a stub** (`stub_fields` on every tab + a note),
  so the UI can mark them "pending API field" until your qty-cancelled change lands.
- *One LIVE rule I added that the test app was missing:* LIVE **drops "ERROR ITEM" lines**; v3 does
  too now (the test app kept them). Same numbers as live.
- *Clean-up vs the test app:* the test app had four near-identical aggregation functions (By Customer
  / Item / Order / Salesman). v3 has **one** generic aggregator they all call - same output, far less
  code to keep in sync.

**20. Number 4 "Book Price" source - resolved (you sent `released_products_report.md`).**
- The new endpoint is `released_products` (SP `rpt.usp_releasedproducts`). It returns one row per item
  with `SalesPrice`, `UnitCost`, `PurchasePrice`, etc.
- *What "Book Price" actually is:* I traced the LIVE code - it maps the released product's
  **`SalesPrice` -> `BookPrice`**, joined to invoice lines by **ItemNumber (upper-cased)**
  (`data/field_maps.py: BOOK_PRICE_FIELD_MAP`). So Book Price = the item's catalog SalesPrice, not the
  invoiced price.
- *Where it goes:* LIVE puts **"Book Price" as the last column** (after Salesman) on the Number 4
  tabs (`reports/number_4/writer_item.py`). v3 will match.
- *How I'll wire it:* the Number 4 builder takes an optional `book_prices` map `{ITEM -> SalesPrice}`;
  the web layer fetches `released_products` once and passes it in. If the lookup is empty (endpoint
  down), Book Price renders blank rather than failing the report.
- *Note to verify on the box:* the doc shows the request body wrapped as `{"parameters": {...}}`,
  while `salesline_release` posts a flat body. I'll confirm which envelope this endpoint actually
  wants when we can hit the API, and adjust the client if needed.

**21. Built the Number 4 report (with Book Price wired in).**
- Four tabs: By Item / By Customer, each over a rolling-12-month and a year-to-date window. Monthly
  Qty (and Qty+$ on the customer tabs) pivoted out, Total Qty / Total $ / Avg Price / Salesman, and
  **Book Price as the last column** exactly like the live workbook. If the released-products lookup
  isn't loaded, Book Price is blank instead of erroring.

**22. Built the Customer Activity report.**
- Starts from the **customer universe** and shows each customer's most-recent order (date, PO #, Sales
  Order). Customers with no orders show "N/A" like live. Tabs: "All" (Salesman column up front), one
  per assigned salesman (resolved to display names), then "Unassigned". Salesman/manager scope hides
  other people's customers (and the Unassigned tab) - same rule the test app uses.
- *Per #15:* the web layer will feed it the universe from the `customer_master` SP each run, falling
  back to the local mirror if the API is down. The builder itself is pure - it just takes the customer
  list + order rows, so that fallback lives in one place and is easy to test.
- *That's all 5 report builders done* (invoiced, salesman, ordered, number 4, customer activity), each
  with its own tests. Next: a GPT-5.5 parity pass over all of them, then the web routes + screens.

**23. Seeded v3's salesmen table from the live config (per #12).**
- The live app stores salesman number/names/commission in `config/salesman_map.xlsx` (columns Key,
  Number, FullName, DisplayName, Email, Commission %). v3 now has its own editable `salesmen` table
  and a one-time seed (`web/data/seed_salesmen.py`) that reads that .xlsx **directly** (no importing
  live code - keeps v3 decoupled) and upserts it.
- *Commission scale:* the .xlsx stores commission as a **fraction** (e.g. 0.05 = 5%). I verified this
  against the live commissions writer (`reports/invoiced/writer.py`: displays `f"{pct:.0%}"`, computes
  `commission = net * pct`). v3 stores and applies it the same way, so commission $ match live.
- *Editable later:* it's a normal table now - the seed only fills it once; from here you edit salesmen
  in v3. Re-running the seed upserts (won't duplicate).

**24. Wired the reports together (the "report service") + marked all 5 BUILT.**
- Built `web/reporting/report_service.py` - the glue that turns a report key into a runnable report:
  it translates your filter form into the SP's parameters, calls the Reporting API, converts the rows
  into typed facts, runs the matching builder, and hands back the on-screen tabs.
- *Where the multi-source reports do their extra fetches (kept OUT of the pure builders):*
  - Invoiced: a **second YTD fetch** (Jan 1 -> period end) feeds the monthly commissions pivot, so the
    commissions tab shows the rich live layout, not the simple fallback.
  - Number 4: pulls `released_products` for Book Price; if that endpoint is down, Book Price is just
    blank and the report still runs.
  - Customer Activity: pulls the customer universe from `customer_master`, and if the API is down it
    falls back to a local mirror (per #15).
- Flipped the report registry for all five (ordered, invoiced, salesman, number 4, customer activity)
  from BACKLOG to **BUILT**, so the app will show them as real, runnable reports (the two we haven't
  built - Amazon Weekly, Customer Aging - stay BACKLOG and won't pretend to work).
- *Open item to verify on the box:* the released_products doc shows a `{"parameters": {...}}` request
  body while the other SPs take a flat body. The service currently calls it with an empty body to get
  all items; if the live endpoint insists on the wrapped shape I'll adjust the client then.

**25. GPT-5.5 parity audit of all 5 reports - what I fixed and what I'm leaving for you.**
- GPT-5.5 re-read every builder against LIVE and flagged a list of mismatches. I fixed the ones where
  LIVE's behavior is clear and the SP can support it; I'm flagging the rest for your sign-off (below).
- *Fixed (clear LIVE wins):*
  - **Numbers were getting rounded to whole units too early.** Order quantities are now kept as decimals
    all the way through (like LIVE), so sums can't drift from rounding each line.
  - **Stray spaces in IDs could break joins.** The text-cleanup helper now trims leading/trailing spaces
    on every field (LIVE does this everywhere), so customer/item codes line up across the different SPs.
    This was the real risk behind the Customer Activity "BLOCKER".
  - **Number 4 was missing LIVE's free-text filter.** LIVE throws away invoice lines that have no sales
    order (hand-typed/free-text lines). v3 now carries the sales-order number and drops those lines too.
  - **Number 4 was grouping too loosely.** It now groups by the full LIVE key (item #, item name,
    customer #, customer name, salesman) instead of just item + customer.
  - **Ordered "cancelled" detection.** Now catches both spellings ("canceled"/"cancelled") and an
    order-level cancellation, matching LIVE.
  - **Ordered "Open $" was clamped at zero.** Removed - the rule is literally Ordered - Shipped -
    Cancelled, so a credit/over-ship can legitimately show negative (LIVE doesn't clamp).
  - **Ordered "ERROR ITEM" filter** now matches on the item NUMBER only (LIVE), not the description.
  - **Salesman export headers** now match LIVE word-for-word ("Sort Number" first, "$ This Year to Last
    Year (YTD)" / "(YTD Full Year)" instead of my shorter "$ YTD Diff" names). v3 keeps an extra
    Salesman column because all salesmen share one tab (your 12-tab layout, #16).
  - **Number 4 missing Book Price** now shows blank instead of $0.00.
  - Small cleanups: dropped an unused import; reject impossible months (e.g. "month 13") before totaling.
- *Left for your sign-off (added to section 1):*
  - **Ordered "Full Data" columns**: LIVE's export has a `DataQualityFlag` column that comes from its
    WHS/packing-slip merge - the flat SP can't produce it, so I left it off. I matched the rest of
    LIVE's column order and added `SalesOrderName` (blank if the SP doesn't return it).
  - **Ordered Amazon 9300/9301 temporary cancellation rule** - LIVE has it; v3 doesn't yet.
  - **Number 4 salesman source**: LIVE derives the salesman from the customer master; v3 currently uses
    the salesman that comes on the invoice line. Need to confirm they're the same before changing.

**26. Built the actual app you'll click through: pages, the on-screen table, and the /test wiring.**
- *The pages* (thin routes in `web/blueprints/`): a Reports list, a Report viewer, a Dashboard
  (admin/dev), and Settings. Each route only does: check you're logged in -> check you're allowed
  (the single Authorization layer) -> kick off the work -> hand back data. No math in the routes.
- *How a report runs* (so numbers can never block the page): clicking "Run" POSTs to
  `/api/reports/<key>/run`, which puts a job on the durable job table and returns a job id. The
  browser polls `/api/jobs/<id>` until it's done, then pulls the result from the one cache and draws
  it. This is the test-app behavior (build on screen, not in Excel) on top of the durable-job system.
  In production a background worker drains the queue; in local dev (no worker thread) the request
  drains it inline so it still works.
- *The on-screen table*: I used Tabulator (a small JS table library, loaded from a CDN like the icons
  already are) for sorting/column-filtering/resizing - the "more customizable effects" the test app
  has. One tab button per report tab (e.g. Ordered's 6 tabs); the Export button downloads the same
  data as an .xlsx whose columns/sheets match what's on screen (which match the LIVE export).
  - *Decision*: Tabulator from CDN vs bundling it. Chose CDN to keep our build simple and match how
    the app already loads Feather icons. Trade-off: needs internet to load the table library. If you'd
    rather it be fully self-hosted, say so and I'll vendor it.
- *Security choices baked in*: the run endpoint requires the CSRF token (sent as a header from JS);
  you can only read/expert a job you own; the report cache key already includes your access scope so
  two people with different access can never read each other's cached numbers. Today only admin/dev
  (unrestricted) users can open a report at all (fail-closed default), so per-salesman data scoping is
  still the pending business decision logged above - not a hole, just not enabled yet.
- *The /test cutover wiring* (`wsgi.py`): the live app stays at `/`. The old test app is now also
  reachable at `/test-legacy` (and `/v2`). The new v3 app takes over `/test` ONLY when I set
  `V3_MOUNT_ENABLED=1` in Azure AND its config is present; if it's off or v3 fails to boot, `/test`
  silently keeps serving the old test app. This means deploying the code is safe - nothing about the
  live site or `/test` changes until I deliberately flip the switch.
- *Deploy mechanics I had to account for*: Azure builds with pip only (it won't run our JS build), so
  the compiled front-end bundle is now committed to git (I un-ignored `web/static_dist/`). All of
  v3's Python dependencies are already in `webapp/requirements.txt`, which is what Azure installs.

**27. GPT-5.5 reviewed the new web layer; I fixed the security holes before going live.**
- GPT-5.5 read every new route/template against the auth layer. It found three real
  "anyone-could-see-too-much" bugs. I fixed all three; the live site was never affected (it's a
  separate app), but I would not put this in front of real users with these open:
  - **Running a report could have shown unscoped data to a non-admin.** The number-crunching code
    doesn't yet trim rows to "just your salesmen" (that's the pending business decision logged above).
    So I made the run/view/export path **admin/developer-only for now** - a non-admin can see a report
    in the list but can't run it and pull everyone's numbers. This re-checks against the live database
    every time, so revoking someone takes effect immediately.
  - **You could read someone else's finished report if you guessed its job id.** Now you can only read
    a job that is exactly yours (and "ownerless" leftover jobs are never readable through these URLs).
  - **A revoked user could still pull an OLD cached result.** The result/export endpoints now
    re-check your access (live) before handing anything back, using the report stored on the job
    itself - not just what's in the URL.
- *Also fixed:* the Dashboard and Settings pages now check your role against the live database instead
  of trusting the signed-in session (so a demoted admin loses access right away); the Excel export now
  also neutralizes cells starting with a newline (formula-injection hardening); the inline
  "run-it-right-now" fallback is disabled in production (production always uses the background worker);
  and your saved Light/Dark theme now loads back from the database.
- *The Commissions tab is no longer blank.* The invoiced report had the commission data but in a
  "card" shape the on-screen table couldn't draw. I flattened it into a real table (one row per
  salesman, a column per month, plus a YTD column and a TOTAL row) so it both shows on screen and
  exports to Excel. The richer card data is still in the payload for a nicer card UI later.

---

## 1. NEEDS HUMAN SIGN-OFF

> Every report calculation rule the audit flagged as "drift" is listed here (mirrors the
> `DRIFT_LEDGER` in `report_engine/contracts.py`). All currently default to LIVE/root behavior
> and are PROVISIONAL until you pick a rule and name yourself as owner. The builders are not
> finalized until these are signed off.

- [ ] **Pre-build data gate**: confirm the Reporting API / stored procedures expose the fields
      needed to reproduce root's calculations (especially `ordered` WHS + packing-slip status).
      If not, the SPs must be extended before web `ordered` numbers can match live. Status: OPEN.

### Drift decisions (pick one per item; default = live/root)

| Report | Decision | Question | Default |
|--------|----------|----------|---------|
| invoiced | tariff_source | Tariff from sales-LINE (`SL_TariffCharges`) vs header (`SH_TariffCharges`)? | live/root |
| invoiced | credit_detection | Credits by substring "contains" vs invoice-number prefix? | live/root |
| ordered | summary_remainder | Definition of Summary-tab remainder (ordered - released - shipped?) | live/root |
| ordered | status_qty_engine | Status/qty via WHS + packing-slip joins (root) vs flat SP rows (web) | live/root |
| ordered | amazon_temp_rule | Amazon 9300/9301 temporary-item special handling - NOT in v3 yet | live/root |
| ordered | error_item_filter | Exclude rows flagged "ERROR ITEM" - v3 now filters Item# only (matches live) | live/root |
| ordered | full_data_columns | v3 omits live's `DataQualityFlag` (needs WHS/packing pipeline the SP lacks); rest of columns match live order | live/root |
| number_4 | book_price | Book Price column source/derivation | live/root |
| number_4 | free_text_exclusion | Exclude free-text (no sales-order) invoice lines - v3 now excludes (matches live) | live/root |
| number_4 | salesman_source | Salesman from customer-master (live) vs invoice-line SalesGroup (v3 now) | live/root |
| salesman | group_key_cardinality | Grouping grain (one row per SalesGroup vs combined) | live/root |
| customer_activity | last_order_grain | Last-order grain: sales header vs sales line (v3 takes max order-date per customer; same result) | live/root |

### Authorization policy decisions (from phase 3 - pick one each)

- [ ] **Report visibility default**: v3 currently FAILS CLOSED - a non-privileged user sees a
      built report only if they have an explicit allow row. The LIVE app instead has a
      conditional default-visible set + global-visibility flags + salesman-filter metadata.
      Decide: keep strict default-deny (you grant per user/role), or have me model live's
      default-visible set. Until you decide, salesmen see no reports by default.
- [ ] **Manager semantics**: live treats `manager` as privileged for the report LIST but scoped
      for salesman DATA. v3 currently treats manager as fully scoped (non-privileged). Confirm
      which you want.
- [ ] **Customer scope when sales-group unknown**: live `access.py` ALLOWS a scoped user to
      proceed when there's no cache row (so D365 is queried); v3 DENIES (safer). Confirm the
      stricter behavior is acceptable or restore live's allow-on-unknown.

### Frontend parity deviations (from phase 8 - confirm or tell me to restore live)

- [ ] **"Test Site" bottom-nav link**: live shows a `Test Site` tab (opens `/test/` in a new tab)
      for admins/devs. v3 is the replacement for that sandbox, so I gated it behind a
      `test_site_enabled` flag that defaults OFF (markup retained, so flipping the flag restores it
      exactly). Rationale: a permanent admin link to the old sandbox would 404/confuse post-cutover.
      Confirm OFF-by-default is right, or tell me to show it for admin/dev like live.
- [ ] **Dev "Switch user" target**: live points the header switch-user icon at `auth.role_picker`.
      v3 currently points it at the dev login page (`auth.login_page`), which already lists/selects
      dev users. Confirm consolidation is fine, or I'll build a dedicated `role_picker` route to match.

### Engineering parity items (not business decisions; for your awareness)

- `text()` helper: the sandbox originals were inconsistent - 4 modules' `_str` did NOT strip,
  but `customer_activity._str` DID. v3's `text()` does not strip (majority); the
  customer_activity builder will strip explicitly. A parity test will lock this when that
  builder is ported.

---

## 2. OPEN QUESTIONS / BLOCKERS

- **Scheduler/worker ownership vs gunicorn workers (deployment decision)**: the in-process
  worker + APScheduler assume ONE owning process. "Single B1 instance" is not automatically
  "single Python process" - if v3 runs gunicorn with multiple worker *processes*, each would start
  its own scheduler/worker and double-schedule / over-claim. Decision needed: deploy gunicorn with
  ONE worker process + threads (gthread) on B1, OR gate background startup to one process via an
  env flag. I'll wire background startup behind an explicit flag in the reporting phase; confirm
  the single-worker deployment is acceptable.

- **Cache-scope leakage - RESOLVED (phase 5)**: the scope token is now produced ONLY by
  `canonical_scope_token()` (order-stable; None->ALL, empty->NONE, never ""), `build_cache_key()`
  rejects an empty token, and `ReportRunner` derives the token internally from the authorization
  result so a route can't pass a raw/unordered token. Tests prove cross-scope isolation
  (`test_runner_scope_isolates_cache`, `test_cache_key_isolates_scope`). Schema-level enforcement
  is unnecessary given this single chokepoint, but confirm you're comfortable with the approach.

---

## 3. GPT-5.5 REVIEW FINDINGS

### Phase 0/1 - Foundation (config, engine helpers, factory, CSRF, health)

GPT-5.5 (gpt-5.5-high, readonly) reviewed against the rules + plans. Resolution:

- **Fixed - fail-open APP_ENV**: `load_config()` now defaults `APP_ENV=prod` so a forgotten
  setting fails closed instead of running dev auth in prod.
- **Fixed - Litestream not enforced**: prod now requires `LITESTREAM_BLOB_URL` and rejects
  UNC/SMB DB paths (`_is_unc`).
- **Fixed - drift not in log**: the full drift ledger is now in section 1 above.
- **Fixed - helper fidelity**: removed the unfaithful `normalize_salesman_map` (no caller yet);
  documented the `text()` strip divergence as a parity item.
- **Fixed - hollow CSRF test**: replaced with real write-route tests (no token -> 400,
  valid token -> 200, mismatched -> 400).
- **Fixed - missing esbuild config**: added `esbuild.config.mjs` (no-op until FE phase).
- **Reviewer misread (no change)**: `date_only` matches the originals' `_date_only` (plain
  trim); invoiced's RFC1123 parsing is a separate `_parse_date` not yet ported - noted for the
  invoiced adapter phase.
- **Reviewer tooling note**: the reviewer could not see the plan files because they live in the
  user-global `.cursor/plans/`, outside the repo. Plans are referenced by absolute path in the
  rule; consider exporting a copy into the repo for CI/team review (deferred, non-blocking).

### Phase 2 - Data layer (connection, migrations, durable jobs, repos)

- **Fixed (BLOCKER) - migration atomicity**: the runner embedded the DDL and its
  `schema_migrations` row in a single transaction, so a failed migration can no longer leave the
  schema changed but untracked. Added `test_migration_failure_is_atomic`.
- **Fixed - concurrency proof**: added threaded tests - `test_concurrent_enqueue_dedups`
  (8 threads, same dedup_key -> exactly one active job) and
  `test_concurrent_claim_never_double_claims` (4 workers drain 12 jobs, none claimed twice).
- **Accepted (non-blocking)**: `claim_next()` may return None under contention while jobs remain
  queued; the worker loop polls/retries, so this is by design, not a correctness bug.
- **Accepted (non-blocking)**: repositories contain SQLite dialect (ON CONFLICT, partial index).
  This matches the stated off-ramp (Postgres = later adapter work, not drop-in today).
- **Documented**: `schedule_runs.schedule_id` is intentionally polymorphic (no FK); integrity is
  enforced in the repo layer (comment added in the migration).
- **Deferred to human**: cache-scope leakage enforcement approach (see section 2).

### Phase 3 - Auth + single authorization/scope layer

GPT-5.5 found four real security blockers; all fixed by making the DATABASE authoritative
each request (the session cookie is trusted for identity only):

- **Fixed (BLOCKER) - stale-role escalation**: role/privilege is now re-resolved from `users`
  on every check, so a downgraded admin loses access immediately
  (`test_role_revocation_takes_effect_immediately`).
- **Fixed (BLOCKER) - inactive users**: unknown/disabled users are denied everything and
  refused at login (`test_inactive_user_denied_everything`, `test_inactive_user_cannot_login`).
- **Fixed (BLOCKER) - report access too broad**: `can_view_report` now FAILS CLOSED for
  non-privileged (explicit allow row required). The broader live policy is a sign-off item
  (section 1).
- **Fixed (BLOCKER) - logout via GET**: logout is now POST (CSRF-protected);
  `test_logout_requires_post` asserts GET -> 405.
- **Hardened**: open-redirect-safe `next` (relative only), MSAL `next` carried in session,
  dev-login XSS-escaped, MSAL no-flow path returns 400 not a crash.
- **Deferred to human (sign-off)**: report-visibility default, manager semantics, and
  customer-scope-on-unknown (section 1).

### Phase 6 - Report engine: dates, params, invoiced (first report)

GPT-5.5 reviewed the engine foundation + the first rebuilt report against the LIVE
(`reports/invoiced/`) + test (`test/webapp/services/`) reference. Findings + resolutions:

- **Fixed (BLOCKER) - credit detection**: changed from prefix (`^(CRD|CM|FC)`, the test app's
  rule) to LIVE's substring `InvoiceNumber.upper().contains("CRD|CM|FC")`
  (`report_engine/sources/invoiced.py`); `test_adapter_detects_credits_as_substring_case_insensitive`.
- **Fixed (BLOCKER) - Totals by Salesman included credits**: now built from the non-credit
  invoices view, matching LIVE `_maybe_write_totals_by_salesman(wb, invoices, ...)`;
  `test_totals_by_salesman_excludes_credits`.
- **Fixed (SHOULD) - Summary invoice count**: now `nunique(InvoiceNumber)` over the full detail,
  matching LIVE `_build_summary`; previously a per-netted-row count.
- **Fixed (SHOULD) - commission rounding**: YTD now sums UNrounded monthly commission (monthly
  rounded for display only), matching LIVE `sum(comm_vals)`; `test_commissions_pivot_*`.
- **Fixed (SHOULD) - commissions year leak**: monthly pivot now ignores rows outside the report
  year even if a caller passes a wider window; `test_commissions_pivot_ignores_prior_year_rows`.
- **Fixed (SHOULD) - date param contract**: blank period or invalid custom dates now omit the date
  filter (no crash), matching the test-app contract; `test_blank_period_with_dates_still_omits_dates`,
  `test_custom_with_invalid_dates_omits_rather_than_raises`.
- **Verified good**: `report_engine` is pure (no Flask/DB/requests/pandas/IO); column order+headers
  match the live export; private `_`-keys stripped from output; commission net formula
  (`net = total_invoices + credits - freight - cc`) matches.
- All invoiced math rules remain PROVISIONAL pending the section-1 sign-offs (credit rule,
  unassigned-salesman handling, etc.).

---

## 4. PHASE PROGRESS

| Phase | Status | Commit | Notes |
|-------|--------|--------|-------|
| 0/1. Rules + log + scaffold + config + engine foundation | DONE | 7ec6582 | 22 tests; GPT-5.5 findings resolved |
| 2. Data layer (precious/cache, migrations, durable jobs, repos) | DONE | 97e1b99 | 31 tests; atomicity + concurrency proven |
| 3. Auth + single authorization/scope layer | DONE | f8eaae1 | 46 tests; DB-authoritative, fail-closed |
| 4. Jobs worker + APScheduler | DONE | b9aa4db | 59 tests; restart recovery + bounded concurrency |
| 5. Reporting infra (client, ONE scope-safe cache, runner, export, durable wiring) | DONE | (this commit) | 80 tests; cache-scope item resolved |
| 6. report_engine builders (5 reports) | IN PROGRESS | (this commit) | dates+params+invoiced DONE (127 tests); ordered/salesman/number_4/customer_activity pending; calc rules PROVISIONAL pending section-1 sign-off |
| 7. Blueprints (thin routes, feature parity) | pending | - | needs builders (sign-off) + shell (done) |
| 8. Frontend shell (pixel-parity base.html, token CSS, esbuild bundle) | DONE | (this commit) | 89 tests; live-faithful shell, GPT-5.5 parity gaps fixed |

### Phase 5 - Reporting infrastructure

GPT-5.5 found three blockers; all fixed:

- **Fixed (BLOCKER) - rule 7 not wired**: added `web/reporting/jobs.py` - a `report.run` durable-job
  handler + `enqueue_report_run()` (dedup = cache key). Routes will enqueue and poll, never run a
  report in the request thread. Proven by `test_report_run_enqueues_and_worker_populates_cache`.
- **Fixed (BLOCKER) - Excel formula injection**: `export.py` prefixes `'` on cells starting with
  `= + - @` (and tab/CR) so D365/customer text can't execute as a formula.
  `test_export_neutralizes_formula_injection`.
- **Fixed (BLOCKER) - scope-token canonicalization**: `canonical_scope_token()` is the only way to
  build a token; `build_cache_key` rejects empty; the runner derives it from the authz scope (see
  resolved item in section 2).
- **Hardened (non-blocking)**: client retries transient 5xx + network but not 4xx; tolerates a
  non-list `rows`; corrupt cache JSON is quarantined (deleted) not re-read; `ReportCache.prune()`
  added for a future scheduled reaper.
- **Boundary recorded**: Reporting API report-id mapping + filter translation intentionally live
  with the (gated) source adapters/builders, not the generic client.

### Phase 8 - Frontend shell

Built the app shell only (base layout + design tokens + nav chrome + the shared JS behaviors);
per-page/per-report CSS is deferred to its own phases. esbuild bundles
`static_src/{css,js}` -> `static_dist/{css/main.css, js/main.js}` and copies
`static_src/public/*` (PWA manifest + icons) to the static root. Tokens were copied verbatim
from the live stylesheet (primary stays live-blue `#2563eb`, not the green sandbox).

GPT-5.5 found three blockers (I'd built the nav from memory); all fixed:

- **Fixed (BLOCKER) - PWA assets would 404**: `manifest.json` + `icon-192/512.png` were missing
  under the new `static_dist` folder. Added them as committed source in `static_src/public/` and an
  esbuild copy step; the build now emits them at `/static/manifest.json` and `/static/icon-*.png`.
- **Fixed (BLOCKER) - missing "Test Site" nav item**: re-added with exact live markup, gated behind
  `test_site_enabled` (default off; see sign-off item in section 1) instead of silently dropped.
- **Fixed (BLOCKER) - `_safe_url` could mask routing bugs**: missing endpoints still fall back to
  `#` so the shell renders before its blueprints exist, but now log at WARNING so a real missing
  route can't hide. Pending nav (reports/dashboard/settings) is inert by design until phase 7.
- **Fixed (SHOULD) - shallow tests**: added role-conditional coverage - admin sees Dashboard,
  salesman does not, dev impersonation badge + switch-user control, non-dev hides switch-user,
  Test Site gated off by default, anonymous hides all chrome, logout is a POST form with CSRF.
- **Fixed (SHOULD) - missing `.help-icon` CSS** (added) and **main.css path comment** (corrected).
- **Hardened (NICE)**: `openHelp` no longer uses unchecked `as HTMLElement` casts (bails if an
  element is missing). JS port is otherwise faithful to live (double-click guard, nav overlay +
  bail-outs, pageshow cleanup, ESC close, pull-to-refresh thresholds/labels/triggerDashRefresh).
- **Deferred (SHOULD, logged)**: `help_content.js`/`HELP` is per-page content, not shell - not
  ported yet; `openHelp` safely no-ops until it lands. Inline `onclick` handlers are kept for live
  parity (a CSP-friendly delegated-listener pass is a future hardening item).
- **Deferred to human (sign-off)**: Test Site gating + switch-user target (section 1).

### Phase 4 - Background jobs (bounded worker + scheduler)

GPT-5.5 found two real blockers; both fixed:

- **Fixed (BLOCKER) - no restart recovery**: added `JobRepository.recover_orphans()`, called at
  `JobWorker.start()`. Jobs orphaned in `running` by a crash are requeued (and the dedup block they
  held is released). Tests: `test_orphaned_running_job_is_recovered`,
  `test_recover_orphans_unblocks_dedup`.
- **Fixed (BLOCKER) - cancel/terminal inconsistency**: `cancel()` is now QUEUED-ONLY and
  `mark_success`/`mark_failure` are guarded to `status='running'`, so a cancelled job can't be
  resurrected as success. Tests: `test_cancel_is_queued_only`,
  `test_mark_success_does_not_resurrect_cancelled`.
- **Decision (was sign-off) - running-job cancellation**: declared QUEUED-ONLY for v1; cooperative
  cancellation is a documented future addition. (Engineering decision, not a business one.)
- **Hardened (non-blocking)**: poller survives infra errors (claim/submit) without dying;
  scheduler sets explicit `coalesce/misfire_grace_time/max_instances` for a sleepy process; added a
  bounded-concurrency test proving we never exceed `max_workers`.
- **Deferred to human**: scheduler/worker single-owner deployment contract (section 2).

### Phase 8 - Production deployment to /test (DONE, live)

v3 is now serving live on Azure at `/test`, with the old test app moved to `/test-legacy`
and the live app untouched at `/`. Verified end-to-end on the default app domain:

- `/test/healthz` returns v3's `{"status":"ok"}` (v2 returned `{"auth_mode","mock_data",...}`).
- `/test/` (unauthenticated) -> 302 -> `/test/login?next=/`.
- `/test/login` -> 302 -> Microsoft Entra `authorize` URL with PKCE (S256) + nonce + state and
  `redirect_uri=<host>/test/auth/callback`.
- `/test-legacy/healthz` -> 200 (v2 still alive); `/` -> 302 (live untouched).

**Redirect URI reuse**: the legacy `/test` app's callback was mount + `/auth/callback` =
`/test/auth/callback`, which is exactly what v3 emits, so the already-registered Entra redirect
URI is reused with no new app-registration change. The custom domain `report.achimonline.com`
is bound to the same App Service, so `report.achimonline.com/test` routes to v3 identically
(its `/test/auth/callback` on that host must also remain registered, as it was for the old app).

**Root cause of the initial fallback (fixed)**: with `V3_MOUNT_ENABLED=1` set, `/test` still
served v2. v3 was raising during boot and hitting the `wsgi.py` fail-safe. Cause: `wsgi.py`
*appended* `v3/` to `sys.path`, so a same-named top-level `web` on the Azure image's path
shadowed v3's `web` package and `create_app()` failed. Fix: insert `v3/` at the front of
`sys.path` before `import web` (safe - live/v2 import `webapp`/`test.webapp`, never `web` or
`report_engine`). Also added a best-effort write of any future boot traceback to
`/home/LogFiles/v3_boot_error.log` for fast diagnosis. After redeploy, all checks above pass.

**Mounting contract (unchanged, fail-safe)**: `/test` only mounts v3 when `V3_MOUNT_ENABLED=1`;
on any v3 boot exception it falls back to v2 so `/test` can never hard-fail the site.

### Phase 9 - Cold-start incident: warmup timeout / crash loop (fixed)

**Symptom**: hours after the Phase 8 cutover, `/test` reverted to the v2 app, then the whole
site started timing out. The container was in a crash loop: Azure logged `Container did not
start within expected time limit` -> `ContainerTimeout` -> `Site ... stopped`. The public domain
is **`reports.achimonline.com`** (plural); `report.achimonline.com` does not resolve - that was a
separate red herring for "can't reach /test".

**Root cause**: `wsgi.py` ran v3's `bootstrap_background` (SQLite migrate + seed admins/salesmen +
start job worker) **synchronously inside `import wsgi`**, i.e. on the gunicorn worker-import path.
Each gunicorn worker also creates the live and v2 apps, which each spawn a catch-up mirror thread
that hammers the (currently slow/timing-out) on-prem Reporting API and contends on SQLite. On a
genuine cold start (full container rebuild + `pip install`), the extra synchronous v3 bootstrap
pushed worker import past Azure's warmup probe window. Tellingly, the failing boots logged
**neither** "v3 mounted" **nor** "v3 failed to boot" - the import blocked (didn't return, didn't
raise), so the probe never got a response and the platform killed the container.

**Fix** (`wsgi.py`): `create_app()` (fast, pure wiring - no network, no DB writes) still mounts v3
synchronously, but `bootstrap_background` now runs in a **daemon thread** (`_bootstrap_v3_async`).
The dispatcher comes up immediately so warmup passes; migrations/seed/worker land ~1s later in the
background (v3 `healthz` and the login *start* don't need the schema, and by the time anyone
finishes the Microsoft round-trip the `users` table exists). The boot-error dump now falls back
through `V3_BOOT_ERROR_LOG` -> `/home/LogFiles` -> temp dir so a future create_app failure is
always captured. Verified post-fix: both workers log `v3 mounted at /test` then
`v3 bootstrap_background complete`, and `/test`, `/test-legacy`, `/` are all healthy.

**Azure settings touched (not in git)**: `WEBSITES_CONTAINER_START_TIME_LIMIT=1800` added as a
warmup-headroom safety net; `V3_MOUNT_ENABLED` toggled 0 (to restore service during diagnosis)
then back to 1 after the fix deployed.

**Follow-up (not blocking)**: the live + v2 apps each run a heavy startup catch-up mirror that
saturates the on-prem API and locks SQLite during cold starts; that contention is pre-existing and
independent of v3, but it makes every cold start fragile and is worth de-risking separately
(e.g. defer/serialize the catch-up, or point the warmup probe at a cheap health path).

### Phase 10 - Login fixes + user directory mirror

Two issues surfaced once real users hit `/test`:

- **"No auth flow in session" at the MSAL callback (fixed)**: v3 shared its host with the live
  app, which uses Flask's default session cookie name `session`; v3 used the same default, so the
  two apps overwrote each other's cookie and wiped the in-flight auth flow before the callback.
  Fix (`web/__init__.py`): `SESSION_COOKIE_NAME="v3_session"` (v2 already uses `v2_session`) plus
  `HttpOnly` / `SameSite=Lax` / `Secure` in prod. The `achimonline.com` accounts live in tenant
  `17d20374...`, which `GRAPH_TENANT_ID` already points at, so the tenant was never the problem.
  (Aside: the public domain is **`reports.achimonline.com`**, plural.)

- **Everyone landed as no-access 'salesman' (fixed)**: v3 only knew the env-listed admins, so real
  accounts had no role. New `web/data/seed_users.py` mirrors the live app's authoritative user
  directory (`app_users` in `/home/data/app.db`) into v3's `users` table on every boot - read-only,
  no live-code import. Roles map 1:1 (admin|developer|manager|salesman); each user's `salesman_key`
  is mapped into `user_salesman_access` when that salesman exists in v3 (normalized, FK-safe).
  Mirror semantics: live is the source of truth for *who can sign in*; explicit env admins
  (`V3/V2_ADMIN_EMAILS`, currently `mennyg@achimonline.com`) are applied last and always win.
  Verified in prod: `mirrored 11 users from live DB`. Users keep their existing session role until
  they sign out / back in (authorization gating re-resolves from the DB live, but the session
  Principal's role is captured at login).

### Phase 11 - Feature-parity audit + full build scope (locked)

After the first online build, we ran a three-pass feature-gap audit (me + two GPT-5.5 subagents,
read-only) comparing the v2 test app (`test/webapp/`, the UX/behaviour reference) against the
current v3 rebuild. Findings were triaged in a canvas (`canvases/feature-gap-audit.canvas.tsx`).
The owner reviewed every gap and chose **Build** for all but three. This phase records the locked
scope so every subsequent review subagent reads from one source of truth.

**Source-of-truth split (unchanged):** behaviour/UX/architecture from v2; report format/columns/
layout + math from the LIVE app; data from the on-prem Reporting API. Rebuild for WHAT, not HOW -
do not copy v2 code.

**Owner decisions (from the triage canvas):**

- BUILD (everything below): full-width scrollable table; Save/Email/Schedule actions; single-row
  filter bar; customer + salesman dropdowns from the customer API (with `/years`, lookup-status,
  mirror-first-then-live); dark/light table theming; column filter popovers; column hide/show +
  restore; multi-level sort; all tabs incl. commission-card layout; WYSIWYG Excel export; column
  reordering; grouping + subtotal/grand-total rows; frozen/pinned columns; per-tab layout
  persistence; refresh-data (preserve layout); duplicate/delete tab; reset view; cache-age +
  fresh-data prompt; date formatter; friendly staged errors; Ordered status filter; bookmarkable
  filter deep-links; live API-preview panel; Save preset + "My Presets" home; email-now; schedule
  + run-now + history; master schedules (admin); SharePoint picker + SharePoint-only delivery;
  customer-activity dashboard + customer/order detail; customer exclusions; admin user mgmt +
  report-access + salesman-access; always-available header theme toggle; notifications; salesman
  master editing; feature flags; report run log; role-specific report labels; diagnostics/mirror/
  db tools; help-content popups; prefix-aware PWA manifest; dev-login template; Customer's Last
  Order builder.
- LATER (defer, do not build yet): export "X of Y rows" counter (`exportcount`); Ordered derived
  qty / fulfillment stub fields stay flagged as provisional (`orderedstub`).
- SKIP: persistent TEST-sandbox banner (`banner`).

**Corrections honoured (do NOT rebuild):** v2 `static/table_tools.js` and `static/app.js` are dead/
orphaned code - their autofit/resize/cancel-run/send-to-background behaviour is NOT a real v2
feature and is out of scope. v3 export already produces a real server-side XLSX; the gap is only
that it ignores the visible layout. Regular-grid percent precision already matches (1 dp); the
2-dp case is specific to commission cards/Excel.

**Invoiced YTD anchoring (resolved):** v3 had added a `year` filter to Invoiced and anchored the
Commissions YTD window to that year, which can diverge from the selected period. Decision: revert
to v2 parity - anchor the Commissions YTD window to the **selected period end**, and drop the extra
`year` filter from Invoiced. (Math source of truth stays the LIVE app.)

**Build order (phases):**

- Phase A - Report viewer parity: upgrade Tabulator to 6.x; full-width + horizontal scroll;
  dark/light theme; multi-sort; column hide/show/reorder; header-filter popovers; grouping +
  totals; frozen columns; render all tabs incl. commission cards; date formatter; per-tab layout
  persistence; reset view; refresh-data; duplicate/delete tab; cache-age + fresh prompt; friendly
  errors; WYSIWYG export reflecting the visible layout.
- Phase B - Filters: single-row bar; `/salesmen`, `/customers`, `/years`, lookup-status endpoints
  (mirror-first then live); searchable customer multi-select; Ordered status filter; bookmarkable
  deep-links; live API-preview panel.
- Phase C - Actions/delivery: save preset + "My Presets" home; email-now; schedule + run-now +
  history; master schedules; SharePoint picker + SharePoint-only delivery.
- Phase D - Other areas: dashboard + customer/order detail; exclusions; admin user/report/salesman
  access; header theme toggle; notifications; salesman master editing; feature flags; run log;
  role labels; diagnostics tools; help content; prefix-aware PWA manifest; dev-login template.
- Phase E - Reports coverage: Customer's Last Order builder.

**Review discipline:** after each phase, spawn a GPT-5.5 subagent (read-only) to review the work
against this scope. Each review prompt MUST include: the source-of-truth split, the full decision
list above, the corrections, the YTD decision, and what NOT to flag (the LATER/SKIP items and the
dead-code corrections). Fix findings before moving to the next phase.

### Phase A - Report viewer parity (done + reviewed)

Built the interactive viewer to parity (Tabulator 6.3 + SheetJS): full-width horizontal scroll,
dark/light theming, multi-sort, column hide/show/reorder/freeze, header-filter popovers, grouping +
subtotal/grand-total rows, all tabs incl. the commission-card layout, a date formatter, per-tab
layout persistence, reset-view, refresh-data that preserves the active/duplicated tabs, duplicate/
delete tab, friendly errors, and WYSIWYG Excel export that mirrors the on-screen view (server XLSX
fallback). A GPT-5.5 review flagged one blocker (refresh wasn't preserving the active/duplicate tab
layout) plus column-order, int-formatter, columns-panel-leak, duplicate-view-inheritance, and two
nice-to-haves; all were fixed before moving on.

### Phase B - Filters (done; review pending)

Single-row filter bar with the customer/salesman dropdowns sourced from the on-prem customer_master
SP, exactly like v2 but rebuilt clean:

- **`web/reporting/lookups.py` (new `LookupService`):** wraps the existing `ReportService`
  customer-universe fetch (which already falls back to the local mirror when the API is down),
  caches it in-process with a 1h TTL, and warms it on a background thread so the dropdowns NEVER
  block a page render. `salesmen()` returns distinct raw `SalesGroup` values (the value the run
  endpoint pushes to the SP) enriched with the v3 salesman-master display name, falling back to the
  seeded master while the universe loads. `customers(salesman)` returns distinct accounts optionally
  narrowed to one salesman. `status()` reports populate progress and kicks a (re)populate when
  configured-but-empty (mirrors v2's status-driven warm-up).
- **Endpoints (`web/blueprints/reports.py`):** `GET /api/reports/<key>/salesmen`,
  `/customers?salesman=`, `/years`; `GET /api/reports/lookups/status`; and a read-only
  `POST /api/reports/<key>/preview-body` that returns the exact `{report_id, url, method, body}`
  the SP would receive (built via `web.reporting.params`, no API call). All keyed endpoints run the
  same `assert_report_runnable` access check as run/result.
- **Ordered status filter:** added `status` to the Ordered filter set + a `STATUS_OPTIONS` select;
  it maps to the SP's `SalesStatus` (already handled in `translate_ordered`).
- **Frontend (`report.ts` + `report_view.html` + `pages.css`):** salesman + year are now real
  selects; the customer field is a searchable multi-select that injects its picks into the run body
  as a `customers` array (and the salesman select cascades the customer list). Added bookmarkable
  deep-links (filters round-trip through the query string on Run and rehydrate on load) and an
  "API preview" toggle that shows the live preview-body JSON. Lookup lists load non-blocking and the
  form polls lookup-status, swapping in the live list when the warm-up is ready.

Tests: added lookup/preview/status + status-filter route tests; full v3 suite green.

### Invoiced YTD revert (done)

Reverted the Invoiced report to v2 parity per the Phase 11 decision: dropped the extra `year` filter
(`REPORT_FILTERS["invoiced"]` is now `period, customers, salesman`) and re-anchored the commissions
YTD pivot window in `_orch_invoiced` to the **selected period end** - Jan 1 of the period-end's year
through the period end (open-ended/all_time falls back to today) - via a new public
`params.resolve_window()`. Added `test_invoiced_ytd_window_anchors_to_selected_period_end` to lock it.
Math source of truth stays the LIVE app.

### Phase B - GPT-5.5 review + fixes (done)

The read-only GPT-5.5 review raised three blockers, three should-fixes, and one nice-to-have. All
addressed:

- **Blocker - Invoiced multi-customer silently dropped (fixed).** The SP's `InvoiceAccount` is a
  single exact-match value, so a 2+ customer selection wasn't pushed down and the report returned
  the whole salesman/date scope. `_orch_invoiced` now post-filters BOTH the period facts and the
  YTD-commissions facts to the selected account set when 2+ are chosen, and the YTD fetch now reuses
  the period's SP params (same customer/salesman scope, only the date range widens) instead of
  date-only. `row_count` reflects the filtered facts. New test:
  `test_invoiced_multi_customer_is_post_filtered`.
- **Blocker - salesman fallback emitted normalized keys (fixed).** The salesman master table is keyed
  by `salesman_key()` (lowercased), which is the WRONG value to send the SP (`SalesGroup` is raw,
  e.g. `REdwards`). `LookupService.salesmen()` no longer falls back to master keys; before the
  universe warms it returns `[]` and kicks a background populate (consistent with `customers()`), and
  the form's status poll swaps in the real raw list when ready. Display names still come from the
  master. New test: `test_lookup_salesmen_emits_raw_salesgroup_not_normalized_key`.
- **Blocker - "mirror-first" not wired (DEFERRED, documented).** v3 has no persistent customer mirror
  table yet (the `customer_mirror` hook on `ReportService` is unwired), so true mirror-first isn't
  possible without building that subsystem. Decision: the lookups are robustly NON-BLOCKING now
  (serve cached-or-empty immediately, warm in the background, poll swaps in the live list), and the
  persistent customer mirror is deferred to the **Phase D** "diagnostics/mirror/db tools" work where
  the rest of the mirror tooling lives. Until then, on a cold process the dropdowns are briefly empty
  while the first live `customer_master` fetch completes.
- **Should-fix - deep-link ordering (fixed).** Deep-links now apply BEFORE `initCustomRangeToggle()`
  so `period=custom` reveals the date inputs; a deep-linked `salesman` is stashed and applied AFTER
  `loadSalesmen()` (setting `.value` before the option exists was silently dropped), then its
  customers load - without clearing deep-linked customer picks.
- **Should-fix - unbounded lookup retries (fixed).** `status()` now only (re)kicks a populate when
  idle or after a failed attempt's cooldown (15s); a successful populate that returned 0 rows is
  treated as "ready" (a real empty universe), not a reason to retry forever.
- **Nice-to-have - live API preview (fixed).** The preview panel now refreshes (debounced) on filter/
  customer/salesman changes while it's open, so it stays in parity with the next run body.

Full v3 suite green (182 passed).

## Phase C - Actions / delivery (in progress)

Phase C adds the "do something with a report" layer: save it as a preset, email
it, and (next) schedule it. Built in tested vertical slices, one commit each.

### C1 - repositories (done)

New owner-scoped repos under `web/data/repositories/`, all on the existing
schema (no migration needed):

- `saved_reports.py` - `SavedReportRepository` (create/upsert-by-name, list, get,
  delete), every method scoped by `user_id` so presets are private.
- `schedules.py` - `ScheduleRepository` (personal), `MasterScheduleRepository`
  (admin), `ScheduleRunRepository` (history ledger). Cadence is stored as JSON in
  the `cadence` TEXT column (e.g. `{"freq":"weekly","time":"08:00","weekdays":[1]}`)
  so we avoid a schema migration and can compute "is it due?" at cron time without
  a `next_run_utc` column. `ScheduleRunRepository.last_run_at()` is the input to
  the due calc; `get_any()` is the owner-agnostic fetch the worker uses.
- `outbox.py` - `OutboxRepository` audit log (enqueue/mark/get/list_recent).

### C2 - presets (done)

- API on the reports blueprint (reuses `_principal_or_401` + `AUTHZ`): list/create/
  get/delete per report, plus cross-report `GET /api/saved-reports` for the home.
  All writes go through CSRF (`X-CSRF-Token`). Creating re-uses the name (upsert).
- Home page gained a **My presets** section: server-rendered cards whose "Open"
  URL is a filter deep-link plus `?preset=<id>`.
- Viewer gained **Save view** (prompts a name, POSTs `collectParams()` +
  `serializeLayout()`) and **Presets** (panel to load/delete). A preset captures
  per-tab layout (hidden/order/sorters/headerFilters/active tab). Opening a report
  with `?preset=<id>` applies the filters, auto-runs, then replays the layout once
  the data lands (`pendingLayout`).

### C3 - delivery (done)

New `web/delivery/` package, decoupled from Flask so the same path serves the
interactive "Email now" and (next) scheduled runs:

- `layout.py` - `apply_layout(payload, layout)` replays the saved view onto the
  payload **server-side** before export: hide columns, reorder, header-filter rows,
  multi-sort (stable, numbers-before-text). Group/freeze are viewer-only so ignored.
  This is the WYSIWYG-for-delivery analog of the browser's WYSIWYG export.
- `sharepoint.py` - `SharePointService`, a config-driven Graph wrapper (app-only
  client credentials) targeting `<DriveRootPath>/Direct Reports`. **Mock fallback**
  when Graph creds are absent: returns a small folder tree and pretends uploads
  succeed, so the picker + delivery work in local dev.
- `email.py` - `EmailService` composes an RFC-822 message with the xlsx attached,
  writes a `.eml` artifact to `OUTBOX_DIR`, optionally relays via SMTP (only if
  `SMTP_HOST` is set), optionally uploads to SharePoint, and logs every attempt to
  the `outbox` table. With no SMTP configured the `.eml` + outbox row ARE the
  delivery record (mirrors the live app) - nothing is silently dropped.
- `service.py` - `DeliveryService.run_and_deliver(...)` = build (force refresh) ->
  apply layout -> export -> deliver. `jobs.py` adds a durable `report.deliver` job
  type so deliveries run off the request thread (rule 7); a failed delivery raises
  so it shows as a failed job.
- Endpoints: `POST /api/reports/<key>/email-now` (validates recipients up front,
  enqueues a delivery job, returns 202 + job_id; SharePoint path requires
  `has_sharepoint_access`), `GET /api/sharepoint/status`, `GET /api/sharepoint/folders`.
- Viewer **Email** button opens a modal (recipients, subject, SharePoint folder
  picker with breadcrumb navigation) and polls the delivery job to success/failure.
- Config gained optional delivery fields (`OUTBOX_DIR`, `EMAIL_FROM`, `SMTP_*`,
  `SP_SITE_URL`, `DriveRootPath`). None gate boot - delivery degrades to outbox +
  mock SharePoint when unset.

Tests: `test_repositories_delivery.py`, `test_delivery.py`, plus preset/email/
SharePoint route tests in `test_blueprints.py`. Full v3 suite green (205 passed).

### C4 - schedules (done)

New `web/scheduling/` package + a `schedules` blueprint:

- `cadence.py` - JSON cadence: `normalize` (validate/clamp), `describe` (human
  label), `due_now` (Eastern-time, once-per-day guard). Stored in the schedule's
  `cadence` TEXT column.
- `runner.py` - `ScheduleRunner.run(id, type)` brackets a `schedule_runs` row
  around build->deliver. **Owner-scoped**: a personal schedule resolves its owner's
  `visible_salesman_keys` so a rep's nightly email never leaks other reps' rows;
  master schedules run unrestricted. Records status/rows/output_meta/debug.
- `jobs.py` - durable `schedule.run` job (deduped per `type:id`) used by both
  "Run now" and the cron tick.
- Blueprint: personal CRUD + toggle + run-now + history page; admin-only master
  CRUD + run-now. SharePoint paths require `has_sharepoint_access`; bad cadence ->
  400; everything owner-scoped.
- UI: viewer **Schedule** modal (cadence controls + a reusable SharePoint picker,
  refactored out of the email modal so both share it), a Schedules list page
  (toggle/run/history/delete), a run-history page, and an admin Master schedules
  page (create form + table). `schedules.ts` drives the management pages; nav gained
  a Schedules tab and Settings links to master schedules.

### C5 - cron tick (done)

- `tick.py` - `enqueue_due(db, job_repo, now)` scans active personal + master
  schedules, honors personal start/end-date windows, and enqueues the due ones as
  `schedule.run` jobs (dedup + once-per-day guard prevent double-fires). `make_tick`
  wraps it for APScheduler.
- Wired in `bootstrap_background` via the existing `Scheduler` (every minute,
  America/New_York). **Best-effort**: if APScheduler is missing the tick is skipped
  and boot continues (schedules still run via "Run now").

Tests: `test_scheduling.py` (cadence, runner personal/master, tick due/dedup/window)
plus schedule route tests in `test_blueprints.py`. Full v3 suite green (216 passed).
