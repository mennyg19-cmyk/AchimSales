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

### Session: Mon Jun 2 - scoping, impersonation, export retention, drift sign-offs

**28. Remainder formula: user chose Ordered - Released - Shipped - Cancelled.**
- *Decision:* the Summary tab's "QtyRemainder" subtracts cancelled (live doesn't). User explicitly
  chose this. builder_version bumped to 2 so old cached reports are invalidated.

**29. Per-salesman report scoping is now live.**
- *What I had to decide:* how to enforce row-level filtering so a salesman can only see their own
  data when running a report.
- *What I chose:* filter facts at the service layer (before the builder sees them) using the
  user's `visible_salesman_keys`. The cache key includes the scope token so different users never
  cross-read. Result/export endpoints re-check scope compatibility (a user whose scope shrinks
  after a run can't view old wider-scoped results).
- *Why:* central enforcement = one place to audit; the builder stays pure and testable.

**30. Customer re-sync on unknown accounts.**
- *Decision:* when a user selects a customer not in the local lookup, v3 forces a synchronous
  resync of the customer SP. If still not found after resync, rejects with an error. This avoids
  the "run with empty customer filter" footgun.

**31. Production impersonation (developer-only).**
- *Decision:* privileged users can impersonate any other user to see exactly what they see. Stored
  in the session as `impersonating=True` + the real identity preserved. Nesting is blocked (400).
  Ending impersonation restores the original session. Used for support/debugging only.

**32. Export retention overhaul.**
- *Decision:* exports tagged by type: one-time (7 day TTL), scheduled (30 days), master (never
  expires). Owner tracked. Admin can browse export history via `/api/admin/exports`.
- *OneDrive delivery deferred:* requires a new Azure app registration with `Files.ReadWrite.All`;
  the DBA/admin needs to create that registration before we can wire it.

**33. Drift ledger fully signed off.**
- All 10 drift decisions in `report_engine/contracts.py` are now signed off. The only remaining
  open item is `number_4 | salesman_source` (needs confirmation that customer-master salesman
  matches invoice-line SalesGroup) — tracked in the table below.

### Session: Thu Jun 11 - memory: stop carrying the full SP rows around

**34. Drop the unused `raw` copy from every fact.**
- *What I had to decide:* you noticed reports were holding more data in memory than needed and
  asked to keep only the columns each report uses. Looking at the code, every fact (the slim
  typed row each report builds from) was ALSO carrying `raw` -- a copy of the entire stored
  procedure row with every column. Nothing in the codebase ever read it.
- *Options:* (a) keep `raw` "just in case" a future feature wants an original column,
  (b) delete it everywhere.
- *Chose (b), deleted it* from all five fact types and the four source adapters that filled it.
- *Why:* zero readers today, and the cost was real -- on a 216K-row ordered report it roughly
  doubled the per-row memory. If a future report needs an extra SP column, the right move is to
  add a named field to the fact (like every existing field), not haul the whole row around.
  All 290 tests (including report parity) pass unchanged.

**35. Free the raw SP rows before the report builds.**
- *Decision:* added a `_facts()` helper in the report service that fetches the SP rows, converts
  them to facts, and lets the raw rows go out of scope immediately -- instead of each report
  orchestrator keeping the full row list alive while all the tabs build. Peak memory during a
  report run is now roughly one copy of the data instead of two.

**36. API preview + "Run with this body" are developer-only now (owner request).**
- *What you reported:* (a) the "Run with this body" button was floating on top of the "Refresh
  data" button, (b) these dev tools shouldn't be visible to regular users, (c) the address bar
  was growing "?period=ytd" style endings that nobody needs.
- *Fixes:*
  - The button overlap was a CSS bug: `.api-run-wrap` sets `display:flex`, which silently
    cancels the HTML `hidden` attribute, so the button rendered even when "closed." One line
    (`.api-run-wrap[hidden] { display:none }`) fixes it -- same pattern the modals already use.
  - "API preview" + the editable body + "Run with this body" now render ONLY for the
    `developer` role (not admin -- developer outranks admin for dev tools, same as
    impersonation). The preview endpoint is also blocked server-side for non-developers (403),
    with a regression test.
  - The page no longer writes your filter choices into the address bar after each run.
    Inbound links still work (dashboard cards and presets link in with "?period=mtd" etc. and
    the page still reads those on load) -- it just stops echoing them back.

---

## 1. NEEDS HUMAN SIGN-OFF

> Every report calculation rule the audit flagged as "drift" is listed here (mirrors the
> `DRIFT_LEDGER` in `report_engine/contracts.py`). All currently default to LIVE/root behavior
> and are PROVISIONAL until you pick a rule and name yourself as owner. The builders are not
> finalized until these are signed off.

- [x] **Pre-build data gate**: ~~confirm the Reporting API / stored procedures expose the fields
      needed to reproduce root's calculations.~~ **RESOLVED**: SP now returns authoritative
      `ShippedQuantity` and `CancelledQuantity` directly; WHS/packing-slip derivation no longer
      needed. `QtyOpen` and `Fulfillment %` are the only remaining derived fields.

### Drift decisions (pick one per item; default = live/root)

| Report | Decision | Question | Status |
|--------|----------|----------|--------|
| invoiced | tariff_source | Tariff from sales-LINE (`SL_TariffCharges`) vs header (`SH_TariffCharges`)? | **SIGNED OFF**: live/root (DBA grouping charges at order level; deferred until SP revision) |
| invoiced | credit_detection | Credits by substring "contains" vs invoice-number prefix? | **SIGNED OFF**: live/root (substring-contains confirmed correct) |
| ordered | summary_remainder | Definition of Summary-tab remainder (ordered - released - shipped?) | **SIGNED OFF: NEW** (Ordered - Released - Shipped - Cancelled; user chose to subtract cancelled) |
| ordered | status_qty_engine | Status/qty via WHS + packing-slip joins (root) vs flat SP rows (web) | **SIGNED OFF**: live/root (SP now returns authoritative QtyShipped + QtyCancelled) |
| ordered | amazon_temp_rule | Amazon 9300/9301 temporary-item special handling | **SIGNED OFF**: live/root (SP has correct data; temp rule no longer needed) |
| ordered | error_item_filter | Exclude rows flagged "ERROR ITEM" - v3 filters Item# only (matches live) | **SIGNED OFF**: live/root (confirmed working) |
| ordered | full_data_columns | v3 omits live's `DataQualityFlag` (needs WHS/packing pipeline the SP lacks); rest match live | **SIGNED OFF**: live/root (DataQualityFlag omitted by design; SP can't produce it) |
| number_4 | book_price | Book Price column source/derivation | **SIGNED OFF**: live/root (SalesPrice from released_products, confirmed) |
| number_4 | free_text_exclusion | Exclude free-text (no sales-order) invoice lines | **SIGNED OFF**: live/root (confirmed working) |
| number_4 | salesman_source | Salesman from customer-master (live) vs invoice-line SalesGroup (v3 now) | **SIGNED OFF: NEW** (use order line's SalesGroup first; fall back to customer master if empty) |
| salesman | group_key_cardinality | Grouping grain (one row per SalesGroup vs combined) | **SIGNED OFF**: live/root (one per group, confirmed) |
| customer_activity | last_order_grain | Last-order grain: sales header vs sales line | **SIGNED OFF**: live/root (max order-date per customer, same result) |

### Authorization policy decisions (from phase 3 - pick one each)

- [x] **Report visibility default**: ~~v3 currently FAILS CLOSED.~~ **RESOLVED**: v3 now uses
      the legacy role-default model (Phase 11 / Mon Jun 1 session #3): admin/developer see all;
      manager sees all; salesman sees only `salesman_default=True` reports by default. Explicit
      Allow/Deny overrides always win. Per-salesman data scoping is implemented (Phase 1 of this
      session): builders filter facts to the user's `visible_salesman_keys`.
- [x] **Manager semantics**: **RESOLVED**: managers see all reports (list) but their DATA is
      scoped to their `visible_salesman_keys` (same as a salesman). This matches v2 behavior.
- [x] **Customer scope when sales-group unknown**: **RESOLVED**: v3 resyncs the customer mirror
      from the SP. If the customer is still not found after resync, it blocks (denies). User
      confirmed this is the correct behavior.

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

- **Scheduler/worker ownership vs gunicorn workers - RESOLVED**: the app runs 2 gunicorn workers
  (B2 tier). Background ownership is single-leader via an exclusive `flock` (see Phase C/D review).
  Only the lock-holder runs the job worker + cron scheduler; both workers serve HTTP. Verified in
  production.

- **Cache-scope leakage - RESOLVED (phase 5)**: the scope token is now produced ONLY by
  `canonical_scope_token()` (order-stable; None->ALL, empty->NONE, never ""), `build_cache_key()`
  rejects an empty token, and `ReportRunner` derives the token internally from the authorization
  result so a route can't pass a raw/unordered token. Tests prove cross-scope isolation
  (`test_runner_scope_isolates_cache`, `test_cache_key_isolates_scope`).

- **OneDrive personal delivery (deferred)**: personal schedules delivering to the user's own
  OneDrive requires app-only credentials with `Files.ReadWrite.All` and the user's drive ID
  resolution via Graph. The Azure app registration for this hasn't been created yet. Flagged
  as a future add-on once the Azure admin creates the registration.

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
| 5. Reporting infra (client, ONE scope-safe cache, runner, export, durable wiring) | DONE | (prev) | 80 tests; cache-scope item resolved |
| 6. report_engine builders (5 reports) | DONE | (prev) | All 5 reports built; drift ledger fully signed off |
| 7. Blueprints (thin routes, feature parity) | DONE | (prev) | Reports, admin, auth, schedules, delivery |
| 8. Frontend shell (pixel-parity base.html, token CSS, esbuild bundle) | DONE | (prev) | live-faithful shell, GPT-5.5 parity gaps fixed |
| A. Report viewer parity | DONE | (prev) | Tabulator 6.3 + full interactivity |
| B. Filters | DONE | (prev) | single-row bar, deep-links, API preview |
| C. Actions/delivery (presets, email, schedule, cron) | DONE | (prev) | SharePoint delivery, cron tick |
| D. Other areas (prefs, PWA, flags, admin, help, dashboard, mirror) | DONE | (prev) | 285+ tests |
| E. Customer's Last Order | DONE | (prev) | in-app report, parity-reviewed |
| Post-deploy: Remainder formula fix | DONE | 0bd79e6 | builder_version=2, cache cleared |
| Post-deploy: Per-salesman report scoping | DONE | (pushed) | facts filtered by visible_salesman_keys |
| Post-deploy: Customer re-sync on unknown | DONE | (pushed) | ensure_customers resync |
| Post-deploy: Production impersonation | DONE | (pushed) | developer-only session impersonation |
| Post-deploy: Export retention overhaul | DONE | 0bd79e6 | tiered TTLs (7d/30d/never), admin history |

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

## Phase D - Other areas (in progress)

Phase D is broad. A scope map (v3-now vs v2) showed two groups: (a) small,
self-contained items that need no new subsystem, and (b) a heavy group
(**Dashboard**, **Customer/Order detail**) that sits on top of a **persistent
customer mirror** which v3 does not have yet (see the Phase B "mirror-first
deferral" note). Plan: ship the self-contained items first (continuous visible
progress), then tackle the mirror as its own slice before the mirror-dependent
pages.

### D1 - preferences + header theme toggle (done)

- `PreferencesRepository` (precious `user_preferences`): theme / landing_page /
  default_report_tab with safe defaults and a partial-update `set()` so a single
  field can change without clobbering the others. Reads tolerate a missing row.
- `POST /api/settings/preferences` (JSON) updates any subset and returns the
  resolved prefs; the legacy `/settings/theme` form now routes through the repo.
- Header gains an instant light/dark **theme toggle** (moon/sun) that flips
  `body.dark-theme`, swaps the icon, and persists via the API (best-effort; the
  visual flip is applied regardless of the network result).
- Tests: persist theme, reject unknown user (403), toggle present in header.

### D2 - styled dev-login template (done)

- Replaced the inline-HTML dev picker with `login.html` (extends the shell) plus
  an `.auth-*` CSS block keyed to tokens (light/dark aware). MSAL mode still
  redirects before render; this only affects `AUTH_MODE=dev`.

### D3a - mount-aware PWA manifest (done)

- The static `manifest.json` hardcoded `/` + `/static/...`, which breaks once the
  app is served under the `/test` prefix (installed app launches at the wrong
  path). Now served dynamically at `health.manifest` with `url_for`-resolved
  start_url/scope/icons. Deleted the dead static manifest (icons stay).

### D3b - feature flags (done)

- `FeatureFlagRepository` (precious `feature_flags`) with `DEFAULTS` as the single
  source of truth: `dashboard_enabled`, `order_entry_enabled`, `test_site_enabled`.
  Seeded idempotently in `bootstrap_background`.
- Context processor now resolves nav gating from the flags: dashboard tab = global
  flag AND (per-user opt-in OR privileged); test-site link = global flag AND
  per-user opt-in. Admins always keep the dashboard tab (template `or` clause) so
  turning the global flag off can't lock an admin out of managing it.
- Admin `POST /api/admin/feature-flags` (privileged, validates the key) + toggle
  switches on the Settings admin card driven by `settings.ts` (optimistic with
  rollback). Tests: set+reflect, unknown-key 400, salesman 403.

### D3c - report run-log (done)

- `ReportRunLogRepository` (precious `report_run_log`) + the report-run job handler
  now records every run (user, report, status, rows, duration_ms, source) as a
  best-effort audit write (an audit failure never fails the run). Admin
  `/admin/run-log` page lists the 200 most recent. Tests: records+renders, 403 for
  salesman.

### D3d - admin users & access + salesman edit (done)

- New `admin` blueprint (privileged, fail-closed via `Authorization`, re-resolved
  per request). Users & access page: list/add/edit/delete users; set role + flags
  (active, dashboard, sharepoint, test, external); replace-all per-salesman scope;
  per-report access overrides (a checked box writes an explicit allow row); and
  salesman edit (active toggle + number/full/display name). Self-delete is blocked.
- `UserRepository` gained `list_all/get_by_id/create/update/delete`, salesman-access
  get/set (replace-all), and report-access get/set. `SalesmanRepository` gained
  `list_all` (active+inactive) and a guarded `update`. The read-only salesmen table
  moved out of Settings into the admin page (dedupe). `admin.ts` drives the modals.
- Tests: user CRUD + scope, self-delete guard, salesman 403, salesman active toggle.

### D3e - in-app help (done)

- Ported the live `HELP` dictionary verbatim into `static_src/public/help_content.js`
  (added the two keys the live app referenced but never defined:
  `settings-test-access`, `settings-assigned-salesmen`), loaded in `base.html`. The
  existing `openHelp()` shell now has content. Added `data-help` "?" triggers on the
  report-view title (`report-<key>`), each filter label (`param-*`), and the Settings
  feature-flags heading. Test asserts the dictionary + triggers render.

### D4/D5 - customer mirror + dashboard + customer detail (done)

- Persistent customer mirror (`cache.db dashboard_customers`) rebuilt by the
  `dashboard.refresh` job from the all-time order facts. Per-customer cadence math
  (`web/dashboard/metrics.py`) is ported cell-for-cell from the LIVE
  `_compute_customer_metrics`: mean gap, **population** stdev as the overdue buffer,
  and the New/Active/Overdue/Inactive bucketing. Dashboard read model applies the
  principal's salesman scope + per-user exclusions; tiles filter the table client-side.
- 4-hourly cron tick refreshes the mirror; primed on boot if empty.

### D3-deferred - overdue notifications + exclusions (done)

- `NotificationRepository` (precious `notifications`): create / list-undismissed /
  counts / dismiss, with account-level dedup (`json_extract` on the payload) and a
  7-day re-alert cooldown. After every mirror rebuild, `generate_overdue_notifications`
  creates one `overdue_customer` alert per overdue account **per user, scope-aware**
  (privileged = all; others only their granted salesman keys), skipping excluded /
  already-notified / recently-dismissed accounts. A notification failure never fails
  the refresh. `/api/notifications` + dismiss endpoints feed a 30s nav-badge poll
  (Dashboard = overdue, Reports = report-ready). Exclusions toggle from customer detail.

## Phase E - Customer's Last Order (in-app report)

### Decision: reuse the Ordered classifier, fetch from salesline_release

- LIVE builds this report by running the **Ordered report's** per-line classifier to
  get Qty Shipped / Qty Cancelled, then rolling lines up by (item, price). v3 does the
  same: `report_engine.reports.ordered.classify_line` is now public and the new
  `report_engine.reports.customer_last_order` builder consumes the same `OrderLineFact`s
  (so the numbers match the Ordered Excel cell-for-cell). Same stub caveat as Ordered:
  Qty Cancelled is provisional until salesline_release returns an explicit cancelled qty.
- Data path: `ReportService.last_order_facts(account)` pulls the customer's full history
  (go-live..today, like customer_activity) from `salesline_release` — NOT a second
  OData pipeline. "Invoiced order" = header `OrderStatus` contains "invoiced"
  (covers "Partially invoiced"), matching LIVE. Default view = latest invoiced order;
  the "Add previous order" modal merges more, rolling identical (item, price) lines
  across orders. PO header uses the longest shared prefix (LIVE `_common_po_prefix`).

### Decision: in-app report, single-customer scope is the access control

- Marked `customer_last_order` BUILT with `in_app=True`. It is customer-picker driven,
  so it has its own pages (`/report/customer-last-order[/<account>]`) instead of the
  standard filter→table viewer; the reports list links to the picker and the standard
  `report_view` redirects there.
- Access: page entry is gated by `assert_can_view_report` (per-report grant or
  privileged) — deliberately NOT the privileged-only `assert_report_runnable` the bulk
  reports use. The bulk reports are gated to privileged because their builders don't yet
  filter facts by the caller's salesman scope; this report is **single-customer**, so the
  exact `assert_can_view_customer(sales_group)` check IS the scope enforcement. The
  picker's customer list is filtered to the principal's visible salesman keys. An empty
  history leaks nothing, so unknown/empty accounts fall through to a clean "no orders"
  page rather than a probe oracle.
- Tests: builder (invoiced-only history, default-to-latest, merge rollup, PO prefix,
  unknown-order fallback, empty); routes (pick renders, listed as in-app link, view shows
  latest, recent-invoiced API, viewer redirect, 403 for ungranted salesman).

## Phases C & D review - blocker/should-fix remediation

GPT-5.5 read-only reviews of Phases C/D flagged real production-safety gaps. Fixes:

### Blocker: one background owner under multiple gunicorn workers

- `startup.sh` runs 2 gunicorn workers; v3's `bootstrap_background` previously started
  the job worker + cron scheduler in EVERY worker, and `JobWorker.start()` calls
  `recover_orphans()` (requeues all `running` jobs). Two workers would requeue each
  other's in-flight jobs → duplicate report deliveries / schedule fires / mirror
  rebuilds. Fix: gate worker + scheduler start on a single-leader signal
  (`_is_background_leader()`), reusing the live app's existing `GUNICORN_EMAIL_DIST_LEADER`
  env (set to "1" only on `worker.age==0` in `gunicorn.conf.py post_fork`). Dev / tests /
  single-process default to leader=True. HTTP still serves on every worker; only the
  background OWNERSHIP is single-process. This also removes the notification-dedup race
  (only the leader generates overdue notifications now).

### Blocker: re-authorize deferred deliveries at execution time

- Both the durable `report.deliver` job and the `ScheduleRunner` previously trusted the
  identity/scope captured at enqueue. After a role downgrade / disable / SharePoint
  revoke between enqueue and run, that stale scope could deliver data the owner is no
  longer allowed to see. Also, personal-schedule "owner scope" was only fed to the cache
  KEY — the builder still ran unfiltered. Fix: `Authorization.principal_for_user_id()` +
  `authorize_delivery()` re-resolve the owner LIVE and apply the same fail-closed gate as
  an interactive run (`assert_report_runnable` — today privileged-only, since builders
  don't yet scope facts — plus a live SharePoint-access check). The delivery handler and
  the personal-schedule path both call it; identity + scope come from the live principal,
  never the stored payload. Master schedules stay admin-owned/unrestricted. Net effect:
  a non-privileged owner's queued/scheduled send now fails closed (consistent with the
  fact they can't create one either), so no unscoped data escapes.

### Blocker: SharePoint-only delivery failure is now a failure

- `EmailService._record` set `ok=True` unless SMTP hard-failed, so a SharePoint-only
  send whose upload threw was reported successful with nothing delivered. Fix: success
  now means every REQUESTED target was delivered — a requested SharePoint upload that
  fails sets `error` (and `ok=False`), which propagates to the job/schedule run as a
  failure visible in history.

### Should-fix items addressed

- Schedule start/end windows now compare against the US/Eastern date
  (`cadence.eastern_date_iso`), matching the cadence timezone, so a late-evening Eastern
  schedule no longer starts/stops a day early around UTC midnight.
- Schedule create/update (personal + master) now validate recipients with the same
  `split_recipients` parser used at delivery, rejecting a non-empty-but-all-invalid
  recipient string at save time instead of silently dropping addresses at send.
- SharePoint hardening: `is_configured()` now also requires `SP_SITE_URL` (MSAL creds
  alone are not enough to resolve a drive); in prod an unconfigured SharePoint send
  raises instead of silently using the mock; folder/file path segments are validated
  (`_validate_segments` rejects `.`/`..` and reserved chars) and URL-encoded per segment.
- `.eml` artifacts get a short random suffix so two sends within one second don't collide.
- Dashboard `refresh-status` returns the SCOPED customer count, not the global mirror
  size, so a scoped user can't learn how many customers exist outside their book.
- Preset deep-links now apply the saved `params` directly (not only the layout), instead
  of relying on the home-page URL also duplicating the filters into the query string.

### Accepted parity deviations (logged, not changed)

- Cadence contract is intentionally simpler than the TEST app (daily/weekly/monthly with a
  single 1..28 monthday; no `once`, multi-monthday, day `-1`/`29..31`). Revisit if a user
  needs month-end or one-shot schedules.
- The dashboard table still shows excluded customers with an "excluded" flag rather than
  hiding them (LIVE hides them). Kept visible on purpose: the per-row toggle is the only
  un-exclude affordance, and hiding the row would make un-excluding impossible from the
  dashboard.
- Customer detail lacks the TEST app's period/last-N filters and an order-detail drilldown
  route; deferred as a Phase D parity item (dashboard read model is complete; this is
  additive UI).

## Phase E final parity review - remediation

GPT-5.5's final parity review caught three real Customer's Last Order blockers tied to
the actual `salesline_release` data shape. Fixes:

### Blocker: "invoiced" must come from the line, not a header status

- LIVE reads `OrderStatus` from a SEPARATE sales-order-header entity. The v3 on-prem
  `salesline_release` SP is LINE-level: the real dump (`test/fixtures/ordered_dump.json`)
  has `SalesStatus: "Invoiced"` and NO `OrderStatus`. The builder previously filtered on
  `f.order_status`, so it returned ZERO orders for valid invoiced customers. Fix:
  `customer_last_order` now treats an order as invoiced when ANY of its lines'
  `SalesStatus` contains "invoiced" (covers "Partially invoiced"); a header `OrderStatus`
  is still honored if a future SP revision adds it. Documented as a deliberate line-level
  adaptation, not a false claim of header-status parity.

### Blocker: authorize on the customer master's salesman, not the order lines

- The real dump has `SalesGroup: null` on the lines, so deriving customer scope from order
  facts both denied valid customers and (on empty history) skipped authorization entirely.
  Fix: `LookupService.customer(account)` resolves the authoritative customer record
  (account/name/salesman) from the `customer_master` universe - the same source LIVE's
  `fetch_customer_info` uses, and the one entity that actually assigns the salesman. The
  route authorizes on that group even for zero-order customers; it only falls back to the
  facts' group when the master can't resolve the account (unknown, or universe not warm),
  and then only authorizes when there ARE facts. The `/salesmen` picker endpoint (directly
  callable even though the UI hides it for scoped users) now filters to the caller's
  `visible_salesman_keys`.

### Blocker: provisional quantity math is now flagged in the UI

- Qty Shipped / Qty Cancelled are DERIVED by the shared Ordered classifier (no explicit
  cancelled qty from the SP yet), so Total (= price x qty_shipped) is provisional too. The
  view now shows the same "provisional / derived" marker the Ordered report uses, instead
  of presenting those columns as final. Dollar INPUTS from the SP remain authoritative.
- Rounding parity: the (item, price) rollup now rounds each line's total before summing
  (matches LIVE `_rollup_lines`), removing a cents-level rounding-timing drift.
- Header fields per order are now taken from the best non-blank / newest-date line rather
  than the first line seen, so an out-of-order or partially-blank first line can't pick
  weaker date/PO/name data.
- Tests: a real-dump-shaped builder test (line `SalesStatus`, no `OrderStatus`, null
  `SalesGroup`); route tests for a scoped salesman in-scope (200) and out-of-scope (403),
  and the scoped `/salesmen` endpoint.

## Deployment cutover (Azure App Service)

v3 runs in the SAME gunicorn process as the live app, behind the dispatcher in
`wsgi.py`: live at `/`, v2 at `/test-legacy`, v3 at `/test`. It's deployed to the
existing `achim-sales-reports` App Service (RG `AchimReportsApp`) via the GitHub
Actions workflow that auto-builds+deploys every push to the `webapp-cache` branch.
v3 is already live in prod at `reports.achimonline.com/test` with real Microsoft
(Entra) login (`APP_ENV=prod`, `AUTH_MODE=msal`, `V3_MOUNT_ENABLED=1`), and a real
user was observed using it during cutover.

### Litestream durability for precious.db (now actually wired)

- `precious.db` is the durable store. The startup command used to run gunicorn
  directly, so Litestream was never running. `startup.sh` now downloads the
  Litestream binary (cached under `/home/bin`), `litestream restore`s on a cold
  instance, then runs gunicorn UNDER `litestream replicate` so every write streams
  to Azure Blob (`achimsalesreportsv3` storage account, `litestream` container).
  Config is `litestream.yml` (abs replica; account name/key/container/path come
  from app settings `LITESTREAM_AZURE_*`).
- EVERY Litestream step is fail-open: a failed binary download / restore / config
  logs and falls back to launching gunicorn directly. Litestream can never take
  down the shared live+v3 process. Verified in prod: snapshots + WAL segments are
  present in the `litestream` container.
- The App Service "Startup Command" was switched to `bash /home/site/wwwroot/startup.sh`.

### Background-owner election via file lock (replaces the gunicorn env scheme)

- Background work that must run in exactly ONE process - the live email-distribution
  loop, and v3's job worker + cron scheduler - was being gated on a gunicorn
  `post_fork` env marker (`GUNICORN_EMAIL_DIST_LEADER`). Two real bugs: (1)
  `gunicorn.conf.py` was UNTRACKED, so it never deployed and `post_fork` never ran;
  (2) `worker.age == 0` never matches (gunicorn worker ages start at 1). Even after
  fixing both, `post_fork` runs before the worker's import path is ready, so its
  email-loop start failed silently - leaving the loop running in NO worker.
- Fix: both apps now elect their background owner with an exclusive, non-blocking
  `flock` taken AFTER imports (live: `webapp.app._start_email_distribution_check`
  on `/tmp/achim-email-dist.lock`; v3: `web._is_background_leader` on a lock next to
  `precious.db`). The one worker that grabs the lock owns the work and holds the
  lock for its lifetime; others skip. Fail-open to leader on non-POSIX/dev.
  `gunicorn.conf.py`'s `post_fork` no longer starts anything. Verified in prod:
  exactly one worker starts the email loop and exactly one owns v3 background work.
- `.gitattributes` pins `*.sh` / `litestream.yml` / `gunicorn.conf.py` to LF so a
  CRLF `startup.sh` can't break the Linux container.

### UI/UX round 2 (page widths, modal bug, dropdowns, mirror-backed pickers)

Owner feedback after using the deployed app. Plain-English decisions:

- **Page widths.** Every page was locked to the 800px reading column. Now the
  default container is full width; only the report picker (front page) and the
  schedules pages (`schedules`, `master_schedules`, `schedule_history`) opt back
  into the narrow column via a `container-narrow` block. So report viewers, the
  dashboard, settings, and the admin tables now use the full screen, exactly as
  asked. (Mechanism: `base.html` exposes a `container_class` block; `.container`
  is full width, `.container-narrow` caps at 800px.)
- **Settings layout by role.** Admins/developers get the full-width page with a
  two-column card grid; salesmen get a single half-width column (the page is set
  to `container-narrow` for them). Driven by `user.role` in `settings.html` +
  `.settings-grid`/`.settings-grid-2col`.
- **Schedule modal opening by default / couldn't close.** The modals are toggled
  by setting the HTML `hidden` attribute, but `.modal-overlay { display:flex }`
  overrode the browser's `[hidden]` rule, so every overlay rendered on page load
  and re-hiding did nothing. Added `.modal-overlay[hidden] { display:none }` so
  `hidden` actually hides. This fixes both the email and schedule modals.
- **Ugly native dropdowns.** Native `<select>`s ignored the theme and showed the
  OS chrome. They now use `appearance:none` with our own chevron and inherit the
  card/border tokens (works in light + dark). The schedule modal's Frequency
  select also had no base styling at all - it now matches the inputs.
- **Customer dropdown not populating from the API or the mirror.** Root cause:
  each gunicorn worker warms its OWN in-process customer universe with a separate
  live `customer_master` call, so a dropdown request landing on a not-yet-warm
  worker got nothing, and there was no shared fallback (the live mirror hook was
  unwired). The dashboard already keeps a shared, persisted customer universe
  (`dashboard_customers`, primed on boot + refreshed every 4h from the same
  `customer_master` SP). The `LookupService` dropdowns now read that mirror when
  this worker's live cache is empty/cold - the same "serve the dropdown from a
  refreshed table" approach the test app uses. Live cache still wins when warm;
  the salesman VALUE stays the raw SalesGroup (the mirror stores it), so SP
  round-trips are unchanged. `status().mirror_row_count` now reports the real
  mirror size instead of a hardcoded 0.

### UI/UX round 3 (report viewer toolbar layout + customer picker overlay)

More owner feedback after using the report viewer:

- **Toolbar moved below the filter box; Run report moved into it.** The action
  buttons (Refresh data, Columns, Reset, Export, Email, Schedule, Save view,
  Presets, API preview) used to sit in the page header above the filters. They
  now live in a `.report-toolbar` row directly BELOW the filter box, and the
  primary "Run report" button sits INSIDE the filter box (a `.filter-field-run`
  cell, bottom-aligned with the other filter controls). So the flow reads
  top-to-bottom: pick filters -> run, then act on the result.
- **API preview shows only the body.** The preview endpoint returns
  `{report_id, method, url, body, ...}`; the panel now renders just `body` (the
  PascalCase SP params), with any `warning` shown as a leading comment. The
  method/url wrapper is dropped - that's noise for the owner.
- **Customer picker fixed (overlay + box growth).** Two real bugs:
  (1) The options list was `position:absolute` inside the filter row, which is
  `overflow-x:auto`; per spec that also clips overflow-y, so the dropdown was
  cut off / scrolled instead of overlaying. It's now `position:fixed`, placed
  under the control via `getBoundingClientRect()` and repositioned on
  scroll/resize, so it escapes the clip and floats over the page.
  (2) The selected pills rendered in an unbounded block that grew the whole
  filter row as you added customers. The picker is now a fixed-width (260px)
  bounded control: chips + the search input share one line and scroll
  internally (`max-height`), so the row height stays stable. The list is also a
  real open/close dropdown now (opens on focus/type, closes on outside-click or
  Esc) instead of being permanently rendered.

### Round 3 follow-ups (from the GPT-5.5 review)

- **`LookupService.customer()` now uses the mirror too.** The dropdowns fell back
  to the persisted mirror but the authoritative `customer()` lookup (used to
  authorize a customer, e.g. Customer's Last Order / zero-history customers) did
  not - it returned None until this worker's live universe warmed. It now reads
  the same `_universe()` (live cache -> mirror). Safe because the mirror is
  sourced from `customer_master`, so its SalesGroup is the same authoritative
  assignment. Covered by a new assertion in the mirror test.
- **Customer control is now a true single line.** It was `flex-wrap:wrap` with a
  74px max-height, so chips could still grow it to two rows before scrolling. It
  is now a fixed 38px line that scrolls horizontally (`flex-wrap:nowrap`,
  `overflow-x:auto`, scrollbar hidden); focusing the search auto-scrolls it into
  view. The filter row height never changes regardless of how many customers are
  selected.
- Not changed: the select chevron uses a fixed `#64748b` stroke in its data URI
  (a data-URI background can't read a CSS var / currentColor). It's a neutral
  grey that reads on both light and dark, so it's left as-is.

### Round 3b (customer field redesign per owner screenshot)

The bordered picker control sitting inside the bordered filter bar read as a
"box within a box", and pills-inside-the-field still felt off. Redesigned:

- The Customers field is now a single, normal dropdown-styled input (same
  chrome + chevron as the `<select>`s) - no inner wrapper box.
- Selected customers render as separate pills AFTER the field (a `#customerPills`
  container in the filter row), not inside the field. The filter row is now a
  `.filter-fields` block (wraps) so when there are too many pills they flow onto
  the next row instead of growing/clipping.
- "Run report" is a direct child of the bar pinned far-right + bottom
  (`.filter-run-btn`, `flex:0 0 auto`), so it stays in the top-right regardless
  of how many pills wrap below.
- The picker JS was reworked to a persistent input (no more rebuild-on-keystroke
  / refocus hack): `renderCustomerOptions()` fills a fixed-positioned dropdown
  that opens on focus/type and closes on outside-click/Esc; `renderCustomerPills()`
  fills the separate pills container; positioning is off the input's rect.

## Report viewer rebuild: readable headers, Excel filters, folder tabs, collapsible bar

Owner feedback on the live report grid: header text barely readable, filters
should be Excel-style dropdowns (operators like >=, one-of, between), tabs
should look attached to the report, and the top filter bar should collapse so
the grid takes most of the screen. Used the test app under `test/webapp/` as a
behavioral reference (not copied), then had a GPT-5.5 subagent review the diff.

**1. Readable headers.** Tabulator header now uses full-strength `--text` (was
the faint `--text-muted`), heavier weight, a 2px bottom rule, and `!important`
on the title color so it beats Tabulator's base theme in dark mode. Removed the
cramped inline header filter inputs.

**2. Excel-style column filters.** Each header has a funnel button
(`.col-filter-btn`) that opens a fixed-position popover with an OPERATOR
dropdown + value input(s). Operators are typed: text (contains / equals /
starts / ends / one-of / empty / not-empty), numeric (= ≠ > ≥ < ≤ between empty
not-empty), date (on / before / after / between / empty / not-empty). Filters
live in `view().columnFilters` and are applied through ONE Tabulator function
filter (`applyColumnFilters`) so `columnCalcs:"both"` totals recalc on the
filtered rows. The funnel highlights when a filter is active.

**3. Folder tabs attached to the grid.** Tabs + grid are now one card
(`.report-surface`): a `.report-tabbar` with a bottom border, folder-shaped
tabs whose active state matches the card background and hides the seam
(`bottom:-1px` + `border-bottom: 1px solid var(--bg-card)`). The row count /
"as of" meta sits on the right of the tab bar.

**4. Collapsible "Filters & options" panel.** The filter form + toolbar + API
preview live inside `#reportControls`; a header toggle folds them into a
one-line summary (selected period/status/salesman/year + custom dates +
customer count). It auto-collapses after a successful run (and on refresh) so
the grid — now `height: calc(100vh - 230px)` — fills the screen; re-open to
change filters.

**Server parity.** `delivery/layout.py` replays the same operators server-side
for emailed/scheduled deliveries (`_filter_rows` + `_match`), deriving column
type from the tab's column defs. Old presets that stored the flat
`headerFilters` substring list still work via `_filter_rows_legacy`, and the
client's `deserializeView` maps any legacy `headerFilters` to `contains`
`columnFilters` so the browser doesn't silently drop them.

**Review fixes applied (GPT-5.5):** legacy-preset conversion on the client; a
stale-`tableBuilt` guard so a late build from a previous tab can't re-apply the
wrong layout; popover listener lifecycle via `AbortController` (clean
Escape/outside-click teardown, one-click switch between funnels, same-funnel
toggle); and strict numeric parsing (`Number` not `parseFloat`) to match
Python's `float()` so client/server filtering agree. The percent-display nit
(filter compares the raw 0.x fraction) was left as-is since client and server
stay consistent.

### Session: Mon Jun 1 - "why am I still a salesman?", monochrome theme, inherit report access

**1. The recurring "my role is still salesman / I can't see all the settings" bug.**
I finally chased this to the root instead of re-seeding again. First I *verified*
the live database: I pulled `precious.db` off the server and queried it — **both
your accounts (`mennyg@achimonline.com` and `mennyg@ad.achimonline.com`) are
already `developer` and active.** The env var `V3_DEVELOPER_EMAILS` has both
emails and the boot seed was doing its job. So the seeding was never the problem.

The real problem: we store *who you are* (your email) in the signed-in session,
and we **cached your role there at the moment you logged in**. Security never
trusted that cache — every permission check re-reads your role from the DB — but
the *presentation* did: the role badge in the header, and the "is this person an
admin?" check that decides whether the Settings page shows the admin sections.
You logged in back when you were a `salesman`, got promoted to `developer` in the
DB afterward, and the page kept showing the stale cookie role until a re-login.

**What I chose:** make the session self-heal. On every request (for a logged-in
user, skipping static files) I re-read the role from the DB and, if it drifted,
rewrite the cached session role. Now a promotion shows up on the **next page
load — no log out / log in needed**, and it can never get stuck again. This is
presentation-only; the security layer was always DB-authoritative.

**2. Monochrome theme.** Added a third theme ("monochrome") alongside light and
dark. It's a calm graphite/zinc grayscale: the brand/primary goes charcoal
instead of blue and every surface is neutral gray, but I deliberately **kept
errors a muted red** so alert/destructive states stay legible (a pure-gray theme
hides them). It uses the exact same CSS token contract as light/dark, so every
component themes for free. The header theme button now **cycles** light → dark →
monochrome (icons: sun → moon → aperture), and the Settings → Appearance dropdown
has the third option too.

*Follow-up:* added a **dark monochrome** ("graphite night") as a fourth theme on
request - the dark counterpart of monochrome (zinc-900 surfaces, white text,
mid-zinc primary so the white button text keeps contrast, error red preserved).
The cycle is now light → dark → monochrome → monochrome_dark (icon: disc), and
it's the fourth Settings dropdown option.

**3. Per-user report settings now behave like the legacy test app ("inherit").**
You asked for the legacy model where each user's per-report access is a tri-state
**Inherit / Allow / Deny**, defaulting to Inherit. We already *seed* users from
the live directory with no per-report rows (= inherit), but v3 used to treat
"inherit" as **deny-everything** for non-privileged users (a deliberate
placeholder while the visibility policy was unsigned). I've now wired inherit to
resolve to the **legacy role defaults** (from `test/webapp/services/report_access.py`):
- admin / developer: see everything (unchanged).
- manager: sees all reports by default.
- salesman: sees only the **salesman-filter** reports by default (Ordered,
  Invoiced, Customer Activity; Customer Aging too once it's built). The others
  (Salesman, Number 4, Customer's Last Order) stay hidden until explicitly
  allowed.
An explicit Allow or Deny always overrides the inherited default. The admin
"Users & access" → Edit user dialog now shows a real Inherit/Allow/Deny dropdown
per report (it loads the user's current state and saving "Inherit" clears the
override).

**Caveat I did NOT silently cross (still needs your sign-off):** non-privileged
users can now *see* their default reports in the list, but **running** a report
is still admin/developer-only. That guard exists because the report builders
don't yet filter the underlying data down to a salesman's own customers
(per-salesman fact scoping). So a salesman would see "Ordered" in their list but
get a "pending sign-off" message on run. That run-scoping is the separate,
larger, money-sensitive piece flagged under NEEDS HUMAN SIGN-OFF — I left it
gated rather than risk leaking another salesman's numbers.

**4. Column-options menu, all-tab export, and group totals.**
Three viewer fixes/changes you asked for:

- *Invisible column menu (dark themes).* The right-click/column header menu
  ("Hide column", "Freeze", "Group by this column", "Clear grouping") was
  white-on-white on the dark + dark-monochrome themes — the same root cause as
  the earlier invisible header: Tabulator's own stylesheet loads after ours and
  forces a white surface. Pinned `.tabulator-menu` / `.tabulator-edit-list`
  background + text + hover to the theme tokens with `!important`.

- *Export now covers every tab.* The Export button used to download only the
  **active** tab (Tabulator's WYSIWYG single-sheet download). It now builds one
  workbook with **one sheet per tab**, in tab order, and each sheet reflects
  that tab's on-screen view (column order, hidden columns, multi-sort, and the
  active column filters — replayed with the same match/parse logic the grid
  uses). Numbers carry real Excel **number formats** by column type ($ money,
  thousands-separated ints, `0.0%` percent, m/d/yyyy dates), columns auto-size,
  and the header row is frozen. *Honest limit:* the community SheetJS build can
  set number formats and widths but **not** font/fill styling, so headers aren't
  bold-and-shaded like the live app's per-report `.xlsx`. Matching that exactly
  would mean rendering server-side with openpyxl and shipping the per-tab view
  state to it — a bigger change I flagged rather than half-did. The server
  fallback export (still one-sheet-per-tab) kicks in if SheetJS fails to load.

- *Group totals like the legacy app.* When a tab is grouped, the export now
  emits, after each group's rows, a **subtotal line** (sums of the numeric
  columns for that group) and a **grand-total** line at the end — matching the
  legacy test app's grouped totals. On screen, Tabulator already shows per-group
  column calcs because `columnCalcs:"both"` is enabled alongside `groupBy`.

**5. Export moved server-side for true live-app formatting (cell coloring etc.).**
Follow-up to #4: you wanted the export to carry the live app's *visual*
formatting — cell coloring, shaded headers, borders — "exactly the same." The
community SheetJS build (client-side) genuinely can't do font/fill styling, so I
moved the export to the **server**, where the live app already builds its
workbooks with **openpyxl**. v3's `web/reporting/export.py` is now a styled
writer (one sheet per tab) using the **live palette** from `core/excel_styles.py`:
- bold **grey header** row (`E0E0E0`) with thin black borders,
- subtle **zebra striping** (`F2F2F2`) on alternate data rows,
- real Excel **number formats** by column type (`$#,##0.00`, `#,##0`, `0.0%`,
  `M/D/YYYY`) so money/percent/dates display and sum correctly,
- **group banners** (`BDD7EE`) + bold **subtotal / grand-total** rows (`D9D9D9`)
  when a tab is grouped,
- frozen header, auto-filter, autosized columns, and a live-style commission
  pivot for the commission tab.
The Export button now **POSTs the current per-tab view** (order / hidden / sort /
filters / group, via the same `serializeLayout()` the save/email/schedule paths
use) to `/reports/<key>/export/<job>`, the server replays it with the existing
`apply_layout()` and streams back the `.xlsx`. Scheduled/emailed deliveries go
through the same `build_workbook()` now, so a grouped saved view gets totals in
its emailed file too. The old client-side SheetJS path and its CDN script were
removed (dead code). It's all the same value-sanitisation as before (formula-
injection apostrophe guard, NaN/inf, control chars, 31-char sheet names).

*Honest scope note:* this matches the live app's **house style** (the shared
`core/excel_styles` look) and is built by the same library (openpyxl), so it
reads as a live-app export. It does **not** reproduce each report's *bespoke*
per-sheet quirks (e.g. the Ordered report's red→yellow→green fulfillment-score
gradient, sheet-to-sheet hyperlinks, or multi-section Summary banner) — those
live in each `reports/<name>/writer.py` and are driven by raw builder columns v3
doesn't carry in its viewer payload. If you want a specific report's exact
gradient/hyperlink layout, that's a per-report add-on we can do next.

**6. Review pass (me + a GPT-5.5 subagent) on the export commits — fixes.**
After shipping #4/#5 I reviewed the commits and had a GPT-5.5 agent review them
independently, then folded in the real findings:
- **Duplicated tabs were dropped from the export (HIGH).** The viewer can clone
  a tab (client-only `…__copy` keys) to hold a different filter/group view; the
  server export only looped the cached payload tabs, so clones vanished from the
  workbook. `serializeLayout()` now also reports the on-screen `order` and the
  `clones` ([{key, baseKey, name}]); a new `expand_clones()` (in `layout.py`)
  deep-copies each clone's base tab and reorders to match the screen before
  `apply_layout`. Wired into both the export route and scheduled/emailed
  deliveries.
- **Percent columns were being summed in totals (HIGH).** A 50% + 50% subtotal
  showed `100%` (and could show nonsense like `250%`). Totals now sum only
  money/int (`_SUMMABLE_TYPES`); percent total cells stay blank — same rule the
  on-screen grid uses (it excludes percent from bottom-calcs).
- **Formula-injection guard missing in the commission pivot (HIGH).** The
  generic grid escaped text, but the commission writer wrote salesman titles /
  labels raw. All commission text now goes through `_safe_text()`.
- **Grouping by a hidden column silently no-op'd (MED).** `apply_layout` drops
  hidden columns before the export grouped, so a group-by-hidden field was lost.
  The grouper now accepts a group field that's present in the row data even if
  it isn't a visible column.
- **Malformed POST body could 500 (MED).** The export route now coerces a
  non-dict JSON body to "no layout", and `build_workbook` defends its `views`
  shape. (I'd already added the top-level guard; this hardens the nested case.)
Cleared on review: CSRF still enforced on the new POST, authorization still runs
before building, percent stored as a fraction matching the grid, no leftover
SheetJS/`XLSX` references, and the dark-theme menu CSS doesn't break light theme.
Added tests for clone expansion, percent-not-summed, and group-by-hidden
(v3 suite: 285 passing).

## 7. Export "Could not build the Excel file" + a build timer

The user hit a generic "Could not build the Excel file. Please try again." and
said the build was "taking a while." Diagnosis: the move to server-side openpyxl
made the export build synchronously inside the web request, and openpyxl styles
every cell, so a large report is genuinely slow. A local benchmark put a single
30k-row tab at ~5s plain and ~19s grouped; a multi-tab report (e.g. `ordered`
has six tabs) over a wide date range can stack well past the old **120s** gunicorn
worker timeout, which kills the worker mid-build and surfaces as that opaque
browser error. There was also no server log when the build itself raised, so any
real exception was invisible.

Fixes:
- **Worker timeout raised to 230s** (`startup.sh` default + `GUNICORN_TIMEOUT`
  app setting), aligned with Azure's front-end idle cap so a big export finishes
  instead of being killed. The export is the only long-running request; run/poll
  endpoints stay quick.
- **Server logs the build.** The export route now times the build and logs
  `tabs/rows/bytes/seconds`; on any exception it logs the stack trace and returns
  a real 500 ("Could not build the workbook") instead of an opaque failure — so
  the next failure is diagnosable from the logs.
- **Live elapsed timer on the progress card.** New `setStatusTimed()` ticks the
  status line each second ("Building your Excel file… (12s)"), and the run/poll
  status now shows elapsed alongside the percentage, so a slow build reads as
  progress rather than a hang.
- **Honest client errors + abort.** The export `fetch` now aborts at 230s (clear
  "timed out — hide columns / narrow range" message) and maps HTTP status to a
  human message: 404 → result expired, re-run; 409 → not ready; 413 → too large;
  otherwise shows the status code. No more blanket "please try again."

## 8. Background exports + streaming openpyxl (the real fix for slow/timed-out exports)

The 230s ceiling above was a band-aid: a one-month `ordered` export still took
~3.5 min and timed out. Two changes fix it properly — mirroring **what** the live
app does (build the file server-side, grab it after) without copying its code.

**(a) Streaming workbook build.** `build_workbook` now uses openpyxl
**write-only** mode: cells are appended top-to-bottom and flushed as we go, so
memory stays flat instead of materialising a 100k×N styled grid in RAM. That RAM
pressure (GC thrash / paging on the 1-vCPU B1) was the real reason a month of
order lines took minutes. Same look (header fill, totals, number formats,
grouping + grand total); the writers were rewritten to append rows of
`WriteOnlyCell`s. (Note: the live app applies no per-cell borders/zebra on data
rows; we kept ours to avoid silently changing the look the user has been seeing —
flagged for the user to confirm. Dropping them would also speed things up.)

**(b) Background export job (durable).** Export no longer builds in the request:
- New `report.export` job type (`web/reporting/export_jobs.py`). The viewer POSTs
  the run's job id + on-screen layout; the route enqueues and returns an
  `export_id` (202). The worker re-authorizes the owner live (like delivery),
  reads the run's cached payload, replays the layout, builds the workbook
  (streaming), and stores the `.xlsx` as a blob.
- New blob store `report_exports` in **cache.db** (migration `0003`) +
  `ExportRepository`. Kept out of precious.db so the multi-MB blobs never bloat
  the Litestream replica; a reaped/lost blob just means "export again".
- New endpoints: `POST /api/reports/<key>/export/<job_id>` (enqueue),
  `GET /api/reports/exports/<export_id>/download` (owner-checked stream),
  `GET /api/reports/exports` (the user's recent exports). Polling reuses the
  generic `/api/jobs/<id>` status route.
- UI: clicking **Export** starts the job, shows "building in the background", and
  a **Recent exports** panel lists each export with live progress and a Download
  button. The user can navigate away and the durable job keeps going; on return,
  the page re-attaches and the finished file downloads in seconds.

Security: download + status go through the same `_owned_job_or_401` owner check
as runs; a second user gets 404 (tested). Build runs only on the background
leader; on the 1-vCPU B1 the worker pool is 2, so a long export shares those 2
slots with runs/deliveries (acceptable; noted for future tuning). The
`report_exports` reaper (`ExportRepository.prune`) exists but, like the payload
cache, isn't scheduled yet. Tests: enqueue → build → list → download happy path
+ owner-isolation; full v3 suite 285 passing.

### Review pass (me + GPT-5.5 subagent) — fixes applied
- **Export jobs could stack on the 2-slot worker (HIGH).** `enqueue_export` now
  dedups on (owner, source run, exact layout): re-clicking Export on the same view
  collapses to the one in-flight job instead of queuing duplicate heavy builds. (A
  dedicated export lane / per-type concurrency cap is noted as future tuning.)
- **Grouped totals dropped a numeric first column (MED).** `_total_cells` always
  wrote the label in column A, overwriting that column's subtotal when the first
  column is money/int. It now puts the label in the first NON-summable column, so
  every numeric column (incl. the first) keeps its total.
- **Recent-exports list didn't re-check live access (MED).** `list_exports` now
  filters rows through `can_view_report`, so a revoked user can't even see old
  export titles/metadata (download was already owner+authz gated).
- **Export start deserialized the whole payload (MED).** Added
  `ReportCache.exists()` (a cheap `SELECT 1`) and use it in the enqueue route
  instead of loading + JSON-parsing the full cached payload just to check presence.
- **Malformed layout could 500 the export (MED).** `apply_layout` now coerces a
  non-dict `views` / per-tab view to "ignore", matching `build_workbook`'s guards.
- **Stale "Download" on an expired blob (LOW).** The list only shows Download when
  the blob is actually present (`ready`); a done-but-reaped export shows
  "Expired — export again".
- **`prune()` format mismatch (LOW).** Compares against SQLite `datetime('now', ?)`
  on both sides (built_at defaults to `datetime('now')`) instead of a Python ISO
  cutoff, so the TTL reaper deletes the right rows.
