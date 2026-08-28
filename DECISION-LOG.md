# Decision Log

## 2026-08-28 Q5 Hebcal down: hold unless a saved calendar still covers now
**What I had to decide:** If Hebcal is down at send time, hold or send?
**Options I considered:** (1) Send anyway. (2) Always hold on any lookup failure. (3) Use a saved calendar; hold and alert only when it does not cover now.
**What I chose:** (3). Owner confirmed. Do not send blind.
**Why:** Sending on Shabbos/Yom Tov by accident is worse than a delayed report. Current code already holds on exception, but the cache is memory-only and dies with the process.
**Status:** DECIDED — Q5 policy closed. Calendar source (Hebcal disk cache vs python-zmanim) asked next; not implemented yet.

## 2026-08-28 Q4 Ordered Summary: group by CustomerAccount
**What I had to decide:** If two customers share a name but have different accounts, merge Summary rows or keep them apart?
**Options I considered:** (1) Group by customer name. (2) Group by CustomerAccount and show account plus name.
**What I chose:** (2). Owner: two “Acme” accounts stay two rows.
**Why:** Account number is the identity. Name is a label.
**Status:** DECIDED — Q4 closed. Q5–Q11 still open.

## 2026-08-28 Q3 commission display: salesman table saved percent
**What I had to decide:** When invoice rates differ, what the Commissions tab one % box should show.
**Options I considered:** (1) “varies”. (2) First invoice rate. (3) Latest invoice rate. (4) Weighted blend. (5) The saved `salesmen.commission_pct` on the salesman row.
**What I chose:** (5). Owner: that % comes from the salesman table saved percent. Invoice-to-invoice differences do not change the printed %. Dollars still follow Q2 (each invoice's SP rate; SP `0` stays 0%).
**Why:** The % column is the salesman's stored rate, not a summary of invoice stamps. People currently cannot edit `commission_pct`; it is the Excel-seeded copy unless we add an editor later.
**Status:** DECIDED — Q3 closed. Q4–Q11 still open.

## 2026-08-28 Q2 commission effective rate: per invoice; SP zero stays zero
**What I had to decide:** Use each invoice's rate, one rate per month, or one annual rate? Also whether a missing/zero SP rate may fall back to `salesmen.commission_pct`.
**Options I considered:** (1) Per-invoice SP rate. (2) One rate per month. (3) One annual rate. Fallback: salesman-table copy vs treat blank/zero as 0%.
**What I chose:** (1) plus no fallback. Owner confirmed: each invoice uses its own SP rate. SP `0` pays 0% on that invoice. Do not substitute the Excel-seeded `salesmen.commission_pct` copy.
**Why:** SQL is the rate source. The app table is a leftover from `salesman_map.xlsx` and is not editable in People.
**Status:** DECIDED — Q2 closed. Phase 6: money does not fall back to the salesman table; the % column does (Q3). Q3–Q11 still open.

## 2026-08-28 Q1 commission unit: SP value is a fraction; 1 = 100%
**What I had to decide:** Does stored-procedure `commission` value `1` mean 1% or 100%?
**Options I considered:** (1) Treat `1` as 1% (`pct >= 1` divide by 100), as this PR currently does. (2) Treat the column as a fraction: `0.05` = 5%, `1` = 100%. (3) Wait for a live Reporting API capture.
**What I chose:** (2). Owner: rates are usually sent as decimals, nobody is paid 1%, typical rates are about 3–5%. This VM has no Reporting API credentials, so there is no live SP sample. Repo evidence matches the owner: salesman master/tests/CLI math all store `0.03`/`0.05`; original adapter used `pct > 1` so `1` stayed 100%; Sol later flipped to `>= 1` without a live row.
**Why:** If the usual encoding is `0.03`–`0.05`, then `1` is 100%, not 1%. Current code would pay $10 on a $1,000 invoice instead of $1,000 if a row ever sent `1`. Phase 6 must restore `pct > 1` (divide only values above 1). Do not implement until remaining owner questions are logged.
**Status:** DECIDED — Q1 closed. Q2–Q11 still open.

## 2026-08-28 Phase 0: archive proven; owner product decisions BLOCKED
**What I had to decide:** Whether prior Sol-list commission/Hebcal/feature choices close the plan's 11 owner questions.
**Options I considered:** (1) Treat the old DECISION-LOG answers as signed off and start Phase 1. (2) Re-ask each plan question one at a time and hold implementation.
**What I chose:** (2). Isolated archive checkout is proven (`b14d725` at `/tmp/achim-archive-restore`). Inventories are in `.scratch/`. Product decisions stay open starting with Q1.
**Why:** The plan and the current assignment forbid silently deciding commission, Hebcal, distributions, `/beta`, recipients, Send-now, retention, or timeout.
**Status:** BLOCKED — Q1–Q5 policy DECIDED. Calendar source (zmanim vs Hebcal cache) unanswered. Q6–Q11 unanswered.

## 2026-08-28 Sol-list phase gate closed on the draft
**What I had to decide:** Whether this remaining-review phase is done on the branch.
**Options I considered:** (1) Merge to `webapp-cache`. (2) Close A/B/C and trust-boundary on the draft and stop.
**What I chose:** (2). Loops A/B/C and trust-boundary are green. HEAD `7f55503`, CI 15/15. Report.ts circular imports stay deferred.
**Why:** Production merge is still the go-live gate. P0.1 secret rotation is still the owner's.
**Status:** DECIDED — phase done on the draft. P0.1 / production promote BLOCKED.

## 2026-08-28 Loop C: split runner helpers; leave report.ts cycles
**What I had to decide:** Whether to fully close Loop C's four quality findings in this pass.
**Options I considered:** (1) Split `runner.py`, delete dead `skip_notes`, rename test `result`, and also break the three `report-*.ts` circular imports. (2) Fix the Python items; defer the report.ts cycles. (3) Defer all as non-blocking notes.
**What I chose:** (2). Extract schedule-run helpers into `runner_support.py`. Leave `report-filters`/`report-grid`/`report-jobs` circular imports until a dedicated frontend module-boundary pass.
**Why:** Loop C marked the TS cycles as not blocking and the frontend build is already green. Breaking those cycles is a layout/runtime risk that needs its own verification, not a same-commit tidy.
**Status:** DECIDED — shipping the Python split. Report.ts cycle break deferred.

## 2026-08-28 Loop A P2 tests and cache-put cancel
**What I had to decide:** Whether to accept the check-then-`cache.put` race or drop the row if cancel lands after the write.
**Options I considered:** (1) Document the tiny race. (2) Check again after put and delete the cache key. (3) Hold a lock around check+put.
**What I chose:** (2). Also add the missing tests the small-scope Loop A pass listed (manual `last_run_at`, catch-up only clears on success, payload `row_count`, tick prune/hung, run 400, Litestream checksum, Graph Retry-After delay).
**Why:** A cancelled run should not leave a cache hit for the next viewer. Locking the cache for this is more machinery than the bug.
**Status:** DECIDED — shipping this change.

## 2026-08-28 Loop A findings on the Sol-list phase
**What I had to decide:** Which of the eight Loop A findings to fix on this draft vs defer until production merge.
**Options I considered:** (1) Fix every item including a pip freeze lockfile and live post-deploy smoke. (2) Fix the behavior bugs and the cheap Azure/CI holes; defer lockfile and live smoke. (3) Defer all as release-gate work.
**What I chose:** (2). Worker runs handlers inside the Flask app context. Cancel is checked after the workbook and before mail/upload. `JobCancelled` records `cancelled` and does not send a failure notice. `/readyz` is 503 when `.bootstrap-failed` exists. Graph upload session POST retries 429/503 with Retry-After. Azure production build runs `tsc` and the dist js/css check. Salesman xlsx seed test uses a temp workbook so CI does not skip. Python stays on bounded `>=x,<y` ranges (already capped). Interrupted Graph upload resume and live post-deploy smoke stay out of this pass.
**Why:** Context/cancel/readyz are the phase expectations. A full lockfile and a live Production smoke are go-live work; this branch still does not deploy.
**Status:** DECIDED — shipping the behavior fixes. Live post-deploy smoke BLOCKED. Pip freeze lockfile deferred.

## 2026-08-28 God-file splits, is_beta alias, restore test, process counters
**What I had to decide:** Finish Sol's leftover refactor/ops items without flipping production env vars or claiming a live Azure empty-disk drill.
**Options I considered:** (1) Rename `is_beta` / `BETA_*` in Azure. (2) Alias only. (3) Skip splits until after merge.
**What I chose:** (2). `Config.reports_only` aliases `is_beta`. Azure `BETA_PRECIOUS_DB_PATH` and the `session` cookie stay. Split reports/schedules blueprints, factory seeds/background, pages.css, and report.ts. Diagnostics `host.counters` holds Graph throttle / last report ms / last scheduler tick in-process. `tests/test_startup_restore.py` covers empty-disk refuse. Live restore drill stays BLOCKED.
**Why:** Flipping `is_beta` points home at the wrong sqlite and cookie. Process counters are what we can prove without Azure. File splits were gated on delivery work already on this branch.
**Status:** DECIDED — shipping this change. Live Litestream drill BLOCKED.

## 2026-08-28 Implement the rest of REPOSITORY-REVIEW.md
**What I had to decide:** Owner said do everything on Sol's list after we had deferred scheduling, a11y, commission, and `is_beta` rename.
**Options I considered:** (1) Keep the deferral. (2) Implement Sol's stated fixes on this draft PR, still no production merge. (3) Also merge to `webapp-cache` and deploy.
**What I chose:** (2). Sol's defect text is the spec. Hebcal fails closed. Commission `1` means 1%. Ordered Summary groups by account. P0.1 history rewrite and live production promote stay BLOCKED.
**Why:** Owner overrode the earlier deferral. Merging unreviewed code to the production branch is still the go-live gate, not this agent.
**Status:** DECIDED — shipping on this branch. P0.1 / production promote BLOCKED.


## 2026-08-28 Close leftover test_access API and NEW_APP_MARKER
**What I had to decide:** Loop B found `test_access` still writable on the admin user API and `Config.new_app_marker` still loaded from env after the last reader (the "v3" pill) was deleted.
**Options I considered:** (1) Defer as dead-surface debt. (2) Stop JSON/PUT only, keep the User field. (3) Drop the Python field, admin JSON, and env flag; leave the SQLite column.
**What I chose:** (3). No DROP migration. Privileged PUT with `test_access` is ignored. `NEW_APP_MARKER` is gone from Config and `v3/.env.example`.
**Why:** Same cleanup goal as retiring leftover /test surfaces. The column stays so existing precious.db files keep loading.
**Status:** DECIDED — shipping this change.

## 2026-08-28 Remove /test nav, order-entry flag, prod source maps
**What I had to decide:** How far "entire cleanup, PR ready, no production" goes past the single-site cutover.
**Options I considered:** (1) Delete dashboard + scheduling + a11y + commission work. (2) Only docs. (3) Dead /test and order-entry surfaces, hide `*.map` in prod, keep `is_beta=True` and Automation trees.
**What I chose:** (3). Drop Test Site nav, `test_site_enabled`, `order_entry_enabled`, the non-prod "v3" pill, and Test-site access on the user editor. Prod 404s `*.map` (files stay in `static_dist`). Full v3 pytest still has 3 pre-existing 401-vs-403 failures, so CI stays on `tools/run-p0-tests.sh`. No merge to `webapp-cache`.
**Why:** Review listed those as leftover /test and preview surfaces. Dashboard stays in the tree because tests still mount it when `is_beta` is false. Scheduling/a11y/commission need owner product calls.
**Status:** DECIDED — shipping this change.

## 2026-08-28 Cutover leftover: Beta UI copy, Azure deploy tests
**What I had to decide:** After CI went green, continue with `is_beta` rename / order-entry delete / merge, or finish unpaid cutover leftovers.
**Options I considered:** (1) Rename `is_beta` and Azure `BETA_*` env vars. (2) Delete disabled order-entry. (3) User-facing Beta copy + docs + gate the Azure production job on the same P0 tests as CI.
**What I chose:** (3). Keep `is_beta=True` so `BETA_PRECIOUS_DB_PATH` and the `session` cookie stay. Shared `tools/run-p0-tests.sh` for CI and the Azure build job. Compile-check `wsgi.py` / `v3/web` on the Azure job (a live `import wsgi` fail-closes without App Settings). Settings heading is "Report data sources". Dropped dead `tools.parity` env docs. P0.5 `DEV_BYPASS_AUTH` died with `webapp/`; v3 still refuses `AUTH_MODE=dev` in prod.
**Why:** Owner said continue. Review said not to start file-move refactors until delivery guarantees exist. Flipping `is_beta` would point home at the wrong sqlite and cookie. This branch still does not merge itself.
**Status:** DECIDED — shipping this change.

## 2026-08-27 P0: cookie file untracked; history rewrite blocked
**What I had to decide:** Whether to rewrite git history of `webapp-cache` in this change.
**What I chose:** Untrack `.scratch/parity-cookies.env`, tighten gitignore, add a filename-only scan. Do not print values. Do not force-push production history.
**Why:** History purge needs a coordinated force-push of every branch that contains `f286ce2`. Session revoke needs rotating `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure (cookie-signed sessions).
**Status:** BLOCKED — owner must rotate Flask secrets in Azure and approve history rewrite.


Older entries: DECISION-LOG-ARCHIVE.md
