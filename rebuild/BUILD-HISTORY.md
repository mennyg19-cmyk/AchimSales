Model: composer-2.5-fast

## Proof of read

- **REBUILD-BRIEF.md:** Ground-up rebuild (nothing ported); invoiced migrates first; target architecture is one SP → one flat table with row math in SQL, app only groups/subtotals; tabs = saved groupings; scope enforced in SQL; admin-defined reports; shell keeps Entra login, durable jobs, audit log, tests as ship gate; persistence and grouping location still open for debate.
- **B-reports-engine.md:** Maps invoiced path through `reports.py`, `web/reporting/*`, `report_engine/reports/invoiced.py`; invoiced uses `InvoiceChargeFact`, commissions tab, misc charges, by-salesman NET; deferred reports noted but not deep-audited.
- **A-frontend.md:** Shell in `base.html`; report screen in `report_view.html`; `report.ts` ~2,100-line god file owning filters, Tabulator, jobs poll/resume/cancel, export, email, schedule; auditors must inventory every control and bolt-on (jobs button, status bar).
- **C-platform.md:** Entra auth + central authz; in-process durable worker; `precious()` + `cache()` SQLite with Litestream to Blob; NEVER SMB; non-negotiables include CSRF, prod boot refusal, audit/run log.
- **v3/REVIEW-LOG.md + DECISION-LOG.md + HANDOFF.md:** Decision journal covers LIVE-vs-test split, parity fixes (credits, commissions, misc), OOM/chunking, SMB→local-disk migration (verified 2026-06-18), cold-start/async bootstrap, login cookie, export/delivery phases; HANDOFF confirms worker poller fixed after local-disk cutover.

---

## Infrastructure / persistence

**BH1** | Report jobs sat in "queued" forever; the DBA saw zero Reporting API calls. | `precious.db` on `/home` (Azure Files SMB) | SQLite WAL shares a `-shm` index across processes; SMB cannot, so the background worker could not see rows the web workers wrote. | Rebuild: durable DB on **local container disk only**; startup refuses prod boot if paths resolve under `/home`; Litestream replicates that local file; document one-time seed + restore path in deploy runbook; test cross-process job enqueue/claim on Azure-like layout.

**BH2** | Interim "fix" for BH1 switched journal mode to TRUNCATE on the live SMB file; every query returned "database is locked" and the site 500'd until reverted. | `connection.py`, app settings | You cannot flip a live WAL database to rollback journal without an exclusive lock; SMB + multi-worker made that impossible; Litestream requires WAL anyway. | Rebuild: **no journal-mode knob** for prod; if persistence is wrong, fail boot with a clear message instead of trying SMB workarounds.

**BH3** | `precious.db` corruption (`database disk image is malformed`); every report run 500'd at job enqueue; Litestream snapshots were also corrupt (replicating a already-bad file). | `web/data/repositories/jobs.py`, Azure `/home/site/v3data` | SQLite on SMB is corruption-prone; restarts mid-write and multi-process access on a network share damage the file; backup only helps if the source is healthy. | Rebuild: never host SQLite on SMB; add periodic **integrity_check** in health/diag; alert on failure; keep dated offline safety copies outside the live path; runbook for `.recover` salvage.

**BH4** | Parallel gunicorn workers crashed boot racing schema migrations ("database is locked", one worker dead). | `migrate.py`, `connection.py` | Two workers applied migrations simultaneously; WAL switch on fresh DBs also raced. | Rebuild: migrations run under **BEGIN IMMEDIATE** with version skip-if-applied; bounded retry on WAL open; single bootstrap owner or leader-gated migrate (see BH18).

**BH5** | Whole site crash loop: Azure `ContainerTimeout`, `/test` fell back, container killed during cold start. | `wsgi.py` bootstrap | `bootstrap_background` (migrate + seed + start worker) ran **synchronously on `import wsgi`**, blocking past Azure's warmup probe while live/v2 mirror threads also hammered API + SQLite. | Rebuild: `create_app()` must return fast; heavy init in a **daemon thread** after the dispatcher mounts; warmup probe hits a cheap route; defer non-v3 mirror work (legacy v2 removed partly for this).

**BH6** | Finished report run died saving results: "no such table" after someone deleted `cache.db` mid-flight. | `web/reporting/cache.py` | Disposable cache file was removed while a run expected schema; reopen did not re-apply migrations. | Rebuild: cache open path **self-heals** (re-run cache migrations before use); treat missing schema as recoverable, not fatal.

**BH7** | Litestream configured but DB path still defaulted under `/home` (working directory on SMB). | `config.py`, deploy defaults | Default path resolved under App Service `/home`; rule said local disk + Litestream but deploy never moved the file until incident. | Rebuild: prod validation **hard-fails** if `PRECIOUS_DB_PATH` or `CACHE_DB_PATH` is on `/home` or any UNC/SMB mount; single env var drives Litestream config.

**BH8** | After moving DB to `/tmp`, container recycle wiped `/tmp`; needed proof cold-start restore works. | `startup.sh`, Litestream | Local disk is ephemeral; durability depends on Blob restore, not the old `/home` copy. | Rebuild: one-time seed from legacy path guarded by marker on persistent share; normal boots **restore from Litestream**; integration test: empty `/tmp` → restore → row counts match.

**BH9** | Legacy v2/test app mirror refresh hammered on-prem Reporting API (nightly + every 4h + restart catch-up), suspected contributor to API hangs and OOM. | `test/` mirror (retired) | Background jobs inside web process pulled 13× ~150–200K-row scans. | Rebuild: no duplicate mirror stacks; optional dashboard refresh behind a **feature flag** default off until SQL push-down exists (`DASHBOARD_REFRESH_ENABLED` pattern).

---

## Job lifecycle

**BH10** | YTD Ordered (~488K rows) OOM'd the worker; container crash-loop took down live app too. | `web/jobs/worker.py`, crash recovery | OS SIGKILL left job `running`; `recover_orphans()` requeued with no cap → infinite OOM loop. | Rebuild: cap orphan recovery attempts (fail with plain-English message after one retry); **memory budget tests** for max expected row count; prefer SQL-side filtering so invoiced never pulls absurd row sets.

**BH11** | Large API pulls exceeded 5-minute timeout (all-or-nothing failure). | `web/reporting/http_client.py`, on-prem API | Single-year `salesline_release` query too heavy for busy SQL box. | Rebuild: for any remaining multi-month pulls, **month-chunk fetch + stitch** with parity test; long-term fix is one SP returning only needed rows (invoiced first deliverable uses one flat SP).

**BH12** | Cancel button appeared but could not stop an in-flight run; cancel only affects queued jobs. | `web/jobs`, `report.ts` | v1 cancel is QUEUED-only; no cooperative abort inside Reporting API call or builder. | Rebuild: document v1 behavior; if keeping in-process worker, add **cooperative cancel** (poll flag between chunks) for chunked fetches; UI must say "Stop queued" vs "Stop running" honestly.

**BH13** | Cancel button stayed visible after job finished. | `report.ts`, CSS | `.btn { display: … }` overrode the HTML `[hidden]` attribute. | Rebuild: use a single visibility pattern (class or `hidden` + no conflicting display rule); component test or visual regression for status bar states.

**BH14** | Status poll showed false **"Lost track of the job"** on transient network blips. | `report.ts` job poll | Poll treated any fetch error as terminal loss of job. | Rebuild: poll loop distinguishes **transient vs terminal** (retry with backoff, keep job id until 404 or explicit failed/cancelled).

**BH15** | Returning to report page restarted elapsed timer; could not resume watching an in-flight run. | `report.ts`, `/api/reports/active` | UI did not reattach to active job or server elapsed time on navigation back. | Rebuild: **active-runs endpoint + resume** on page load; persist `job_id` in sessionStorage; status bar and floating jobs button share one poll module (not bolted on twice).

**BH16** | Diagnostic era: job poll 404s, claim probe needed to prove worker loop ran. | `reports.py` diagnostics, worker | Multi-worker + SMB DB meant web and worker saw different DB states; later fixed by BH1. | Rebuild: ship **health/diag** that shows worker heartbeat, last claim, queue depth, and Reporting API reachability without exposing secrets; integration test: enqueue → claim → complete.

**BH17** | Multiple gunicorn workers each started scheduler / email loops (duplicate work). | `web/__init__.py`, gunicorn | `post_fork` ran background loops in every worker. | Rebuild: **single leader** via file lock (or one dedicated worker process) for scheduler, email drain, and job poller; test that only one leader runs.

**BH18** | Stuck jobs after hung Reporting API call blocked queue perception. | worker + diagnostics | One long-running job monopolized worker; no visibility into "worker alive but busy." | Rebuild: log API call duration; optional stuck-job cleanup when flag enabled; consider separate queues for quick vs heavy jobs in redesign.

**BH19** | Dev `claim-once` / `precious-repair` endpoints added late to debug queue and corrupt DB. | `reports.py` diagnostics | Production pain required ad-hoc repair (REINDEX, ghost job delete, Litestream backup before rebuild). | Rebuild: first-class **admin repair** behind developer role: integrity check, safe backup, jobs-table rebuild—built in, not emergency patches.

---

## Frontend / UI

**BH20** | `report.ts` grew to ~2,100 lines; jobs bar, status bar, resume, export, email, schedule all stacked in one file. | `v3/web/static_src/js/report.ts` | Feature parity added reactively without splitting modules. | Rebuild: **small TS modules** by concern (filters, table, jobs, export modal, layout state); no second god file; esbuild bundle stays.

**BH21** | MSAL login failed with "No auth flow in session" at callback. | `web/__init__.py` session cookie | v3 shared Flask default cookie name `session` with live app on same host; apps overwrote each other's session. | Rebuild: **unique session cookie** per mounted app (`SESSION_COOKIE_NAME`), HttpOnly, SameSite, Secure in prod; test multi-app dispatch on one host.

**BH22** | Real users landed as no-access salesman after first login. | `seed_users.py` | v3 only knew env-listed admins; live user directory lived elsewhere. | Rebuild: on boot, **mirror authoritative user directory** (read-only) into precious DB; env admins override; role resolved at login and re-checked on sensitive routes.

**BH23** | Table did not fit viewport; headers wrapped; column resize broken on mobile with bottom nav. | `report.ts`, `pages.css` | Table height and toolbar layout added incrementally. | Rebuild: **viewport-fit table** from day one; responsive shell spec (bottom nav, jobs chip) in layout tokens; test mobile + desktop breakpoints.

**BH24** | Dark theme: column options menu and report header invisible. | CSS tokens | Hard-coded light colors on Tabulator chrome. | Rebuild: all chrome uses **design tokens**; dark mode checklist in expectation file for report screen.

**BH25** | Deep-linked filters wrong: `period=custom` did not show date inputs; salesman set before options loaded. | `report.ts` | Init order: deep-link ran before lookup population. | Rebuild: defined **init pipeline** (lookups → apply URL params → bind controls); tests for `?period=custom&salesman=` URLs.

**BH26** | Excel export blocked the browser or timed out on large reports. | export path | Export first ran synchronously in request handler / long client build. | Rebuild: **background export job** + download link; streaming writer for large sheets; progress in UI.

**BH27** | Export did not match on-screen layout (hidden columns, filters, sort). | `export.py`, client export | Server export ignored view state; client WYSIWYG added later. | Rebuild: **one grouped dataset** for screen and export (per REBUILD-BRIEF grouping decision); view state (hidden/order/filters) applied in one server step so email and export cannot diverge.

**BH28** | Revoked or demoted user could still open old cached result/export. | `reports.py` result/export routes | Cache key did not re-check current authorization. | Rebuild: **every result/export fetch** re-runs central authz against `(user, report, scope)`; cache entries include scope token; miss → 403 not stale data.

**BH29** | Manager running report used wrong salesman scope. | `authorization.py`, run handler | Manager visibility rules not applied consistently on enqueue. | Rebuild: **single `assert_report_runnable`** used by run, result, export, email; parity tests per role (admin, manager, salesman).

**BH30** | Lookup dropdowns briefly empty on cold process; salesman dropdown showed normalized keys instead of raw `SalesGroup`. | `lookups.py`, `report.ts` | Mirror-first customer list deferred; fallback used wrong key shape for SP. | Rebuild: lookups return **exact SP parameter values**; display names separate; warm cache async; until SQL ships salesman names, document Azure vs SQL master sync.

**BH31** | Asset cache busting missing after deploy; users kept old broken JS. | templates | Static URLs without version query. | Rebuild: **`?v=` build id** on all CSS/JS from day one in shell template.

**BH32** | Impersonation session dropped `impersonating` fields on Principal round-trip. | `principal.py` | Incomplete serialization for admin impersonation feature added in Phase 3. | Rebuild: if impersonation stays in scope, **Principal is immutable value object** with full round-trip tests.

---

## Report math / data (Invoiced + shell data paths)

**BH33** | Credits misclassified: test app used prefix; LIVE uses substring **contains** `CRD`/`CM`/`FC`. | `sources/invoiced.py` | Copied test-app rule during first build. | Rebuild: credit flag comes from **SQL column** (`IsCredit`); app does not re-derive unless SP omits it; parity test against LIVE export.

**BH34** | "Totals by Salesman" included credit rows; LIVE uses invoices only, then **NET** of credits. | `reports/invoiced.py` | Builder aggregated all rows; later fixed to exclude credits and net. | Rebuild: SQL returns `IsCredit` and precomputed net columns; app tab = **group by salesman + sum money columns** only; no custom netting in Python.

**BH35** | Commission YTD off by pennies: app rounded each month before summing. | commissions pivot | Rounding before sum. | Rebuild: SQL returns monthly commission dollars; display rounding only in formatter; YTD = sum of unrounded values.

**BH36** | Commissions pivot included prior-year rows when window spanned year boundary. | `_orch_invoiced` | YTD fetch window not filtered to report year. | Rebuild: single SP call with explicit year parameter; or SQL filters `InvoiceDate` to report year for commission columns.

**BH37** | Selecting **2+ customers** silently returned whole salesman/date scope (SP accepts one `CustomerAccount`). | `report_service.py` | Multi-select not pushed down; no post-filter. | Rebuild: SQL accepts **table-valued customer list** or `IN` clause; scope enforced in DB; app passes list parameter from manifest—no silent post-filter in Python.

**BH38** | Invoiced commissions tab required a **second full YTD API fetch** (double call, double memory, double failure surface). | `_orch_invoiced` | Period fetch + Jan1→period-end fetch for pivot layout. | Rebuild: **one flat SP result** includes commission-month columns or a second result set in one round-trip; eliminate duplicate fetch from orchestrator.

**BH39** | **Misc Charges** column missing until DBA added field to new `invoiced_report` SP. | adapter + builder | Old `invoiced_order_charges` shape lacked misc bucket. | Rebuild: manifest declares columns from SP metadata; invoiced SP includes all money buckets live export expects.

**BH40** | Commission % source drift: salesman master in Azure SQLite vs new **`commission` column on SP rows**. | `invoiced.py`, `precious.db` salesmen | Two sources of truth; admin edits in Azure not visible to SQL. | Rebuild: **salesman master on SQL Server** joined in SP; app displays SP rate; Azure master only for admin UI sync or retired.

**BH41** | **SalesmanNumber** column removed after living in v3 briefly; display names came from local DB while SP sends codes. | builder columns | Mixed enrichment in Flask vs SQL push-down migration. | Rebuild: SP returns `SalesmanNumber`, `SalesmanName`, `SalesGroup` as live export expects; app does not join salesman master for display.

**BH42** | Summary **invoice count** could over-count when same invoice split across customers. | summary tab | Counted rows not distinct invoice numbers. | Rebuild: SQL returns `InvoiceCount` per group or app uses generic `COUNT(DISTINCT InvoiceNumber)` on flat table—rule in manifest.

**BH43** | Blank period / bad custom dates caused errors instead of "no date filter." | params translation | Strict validation. | Rebuild: filter→SP mapping documents defaults; invalid custom range → user-visible validation, not 500.

**BH44** | Invoiced migrated **`invoiced_order_charges` → `invoiced_report`** with field renames (`amount`, date-only params); adapter carried legacy aliases. | `params.py`, `sources/invoiced.py` | Multiple SP revisions in flight. | Rebuild: **versioned manifest** per report SP; adapter layer deleted when only one SP contract exists; contract tests on sample JSON fixtures.

**BH45** | Commissions tab layout: on-screen cards (test style) vs live Excel export shape—special-cased. | builder + export | Two presentation paths. | Rebuild: commissions = **saved tab definition** (group + column subset) over same flat table; export uses same grouping engine as screen.

**BH46** | Invoiced YTD window anchored to wrong year when extra `year` filter added; reverted to period-end anchor. | `_orch_invoiced`, filters | Feature drift from LIVE/v2 parity. | Rebuild: commission date window is an explicit SP parameter derived from selected period end; no separate year filter unless LIVE export has it.

**BH47** | CEO daily email / SharePoint delivery failed with misleading "file not found." | `sharepoint.py`, app settings | `SP_SITE_URL` pointed at nonexistent team site; Graph 404 swallowed as missing file. | Rebuild: SharePoint config validated at boot; site lookup errors surface **setting name + Graph status**; shared service for all SharePoint paths (no duplicate site constants).

**BH48** | Email-now / schedule delivery must rebuild report with **owner scope** so rep emails do not leak other reps' rows. | `scheduling/runner.py` | Master vs personal schedule scope. | Rebuild: delivery jobs carry **principal + scope snapshot**; builder receives same scope SQL parameters as interactive run; test salesman-scheduled email.

**BH49** | Report parity harness caught LIVE drift (GPT-5.5 reviews); many rules only exist in tests/logs today. | `v3/tests`, REVIEW-LOG | Math lived in Python builders. | Rebuild: **temporary LIVE parity scaffold** per REBUILD-BRIEF; after SQL cutover, parity tests target SP output; human sign-off list in REVIEW-LOG patterns preserved.

**BH50** | On-prem API saturation: concurrent diagnostic curls from production container jammed API tier (500s, no SQL activity). | ops / Kudu probes | Heavy SP calls from same hybrid connection as live traffic. | Rebuild: read-only **live=1 probe** with short timeout behind admin role; never stack long-running probes on prod; runbook says use diag endpoint not raw curl loops.
