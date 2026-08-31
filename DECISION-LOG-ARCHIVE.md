# Decision Log archive

## 2026-08-31 Phase 3: defer Loop C Q1 test helper
**What I had to decide:** Extract a shared helper for five scoped-tab tests that stringify `tab["rows"]`, or leave them inline.
**Options I considered:** (1) Extract `_assert_tabs_exclude`. (2) Leave inline; Loop C called it optional and non-blocking.
**What I chose:** (2).
**Why:** Each test forbids different strings (quoted vs unquoted `200`). Test-only; no production impact. Gate already green.
**Status:** DECIDED — Phase 3 quality nit deferred.

## 2026-08-31 Phase 2: only a developer may impersonate a developer
**What I had to decide:** Trust-boundary finding: an admin impersonating a developer passes `is_developer` checks because those read the *current* identity's DB role. Restrict vs accept.
**Options I considered:** (1) Accept and log: admins are already privileged and can edit People. (2) Restrict: `/impersonate` 403 unless `actor_is_developer` when the target is a developer. (3) Change `is_developer` to always mean the real actor.
**What I chose:** (2). Role picker stays developer-only. `is_developer` still means the current identity so a developer viewing as a salesman does not keep developer tools.
**Why:** Admin impersonation of a developer would unlock `/dev/role-picker` and other developer-only screens under someone else's email. Admins can already manage users without that.
**Status:** DECIDED — Phase 2 trust-boundary fix.

## 2026-08-31 Phase 2: role picker uses actor_is_developer; LIVE_DB_PATH stays for CLI
**What I had to decide:** Gate `/dev/role-picker` on `authz.is_developer(p)` (plan 2.1 wording) vs the real actor during impersonation; whether to delete `LIVE_DB_PATH` in this phase.
**Options I considered:** (1) `is_developer(p)` — impersonating a salesman could not reopen the picker. (2) `actor_is_developer(p)` — the signed-in developer keeps the picker while viewing as someone else. (3) Delete `LIVE_DB_PATH` now vs keep it for `flask import-live-users`.
**What I chose:** (2) and keep `LIVE_DB_PATH` for the CLI only.
**Why:** The picker exists so a developer can switch identities without logging out. Boot no longer reads the Live DB; the plan deletes `LIVE_DB_PATH` after import evidence, which we do not have yet.
**Status:** DECIDED — Phase 2 implementation. Still BLOCKED on GitHub Environment `production` required reviewers.

## 2026-08-31 Phase 1.2: owner confirmed Flask secret rotation
**What I had to decide:** Whether old `session` cookies are dead after the Azure App Setting change.
**Options I considered:** (1) Keep waiting for a second confirmation. (2) Treat the owner's "I think it worked" as the revoke check and start Phase 2.
**What I chose:** (2). Owner rotated `FLASK_SECRET_KEY` / `FLASK_SECRET` and reported sign-in bounced then worked again. This VM cannot read Production cookies.
**Why:** Secret rotation is what invalidates stolen cookies. History rewrite stays off.
**Status:** DECIDED — cookies treated as revoked. Still BLOCKED on GitHub Environment `production` required reviewers (settings click). Access-log review of the cookie-file window is still the owner's.

## 2026-08-28 Phase 1.2 policy: do not rewrite history; require Environment reviewers
**What I had to decide:** Rewrite git history to purge the cookie file, and whether Production deploys must wait on GitHub Environment reviewers.
**Options I considered:** (1) Coordinated force-push of every branch that contains `f286ce2`. (2) Leave history; kill sessions by rotating Flask secrets. (3) Skip Environment required reviewers.
**What I chose:** (2) and required reviewers. Owner: your recommendation.
**Why:** Rotating `FLASK_SECRET_KEY` / `FLASK_SECRET` is what actually invalidates stolen cookies. A history rewrite is a force-push of production and every clone; do not do that in this PR. Environment reviewers are the remaining deploy brake after the YAML guard.
**Status:** DECIDED — no history rewrite, no force-push. Environment `production` must have required reviewers (owner GitHub settings). Still BLOCKED on rotating the Azure Flask secrets and on actually turning reviewers on. Do not start Phase 2 until old cookies are dead.

## 2026-08-28 Phase 1.1 production workflow: checks are deploy dependencies
**What I had to decide:** How to make security, Python, frontend, artifact, and restore-preflight real blockers of Azure Production, and how to run semgrep without failing on ~130 existing p/default hits.
**Options I considered:** (1) Keep one build job with sequential steps. (2) Split jobs with `needs:`; semgrep `--error` on the whole repo. (3) Split jobs with `needs:`; semgrep `--error` only vs the previous commit.
**What I chose:** (3). Every job has `if: github.ref == 'refs/heads/webapp-cache'`. Deploy uses GitHub Environment `production`. Each job has `timeout-minutes` (Actions has no workflow-level timeout).
**Why:** `needs:` is what actually stops deploy when a check fails. Whole-repo semgrep `--error` would fail every Production deploy on findings that already exist.
**Status:** DECIDED — YAML is on this draft. Required reviewers on Environment `production` are GitHub repo settings (that Environment does not exist yet; only `github-pages` does). BLOCKED on the owner enabling reviewers, plus Flask secret rotation (Phase 1.2).

## 2026-08-28 Q11 timeout / unknown mail: 45 min kill; Graph unknown is not retried
**What I had to decide:** Maximum report runtime, and what to do when Graph `sendMail` outcome is unknown.
**Options I considered:** (1) Keep today's 45-minute DB-only fail while the worker thread can still finish; treat a lost Graph reply as failed and retry. (2) Cap at 45 minutes, mark the job cancelled, and kill the child process; keep Reporting API calls at 300 seconds; if the connection drops after Graph accepted `sendMail`, mark that delivery `unknown`, do not auto-retry, operator reconciles. (3) A different wall-clock cap.
**What I chose:** (2). Owner: your recommendation.
**Why:** A timed-out job must actually stop, not only look failed. A maybe-sent email must not be sent a second time.
**Status:** DECIDED — Q11 closed. Phase 4 kills the child; Phase 5 adds `unknown`. All 11 owner questions are logged.

## 2026-08-28 Q10 retention: keep current TTLs; prune attempts/legs/jobs at 90 days
**What I had to decide:** How long to keep kept runs, exports, delivery legs, magic-link attempts, and old jobs.
**Options I considered:** (1) Leave attempts/legs/jobs forever. (2) Plan table: kept runs 30 days (cap 5), one-time exports 7 days, scheduled 30, master 90, attempts/legs/jobs 90 days. (3) Owner-chosen different days.
**What I chose:** (2). Owner: correct.
**Why:** Matches what exports and kept-runs already do. The three tables with no TTL today (magic-link attempts, delivery legs, old jobs) get a 90-day prune in Phase 6.
**Status:** DECIDED — Q10 closed. Do not change the four existing TTLs or the kept-run cap of 5. Q11 still open.

## 2026-08-28 Q9 company Send now: view-only managers may trigger it
**What I had to decide:** May a manager who can only view a company schedule press Send now?
**Options I considered:** (1) Require the same edit/toggle permission (`can_edit_master`). (2) Keep Send now on the visibility check so any manager who can see the row can fire it.
**What I chose:** (2). Owner: yes, they can.
**Why:** Viewing the company list includes the right to kick a send. Toggle/edit stays tighter.
**Status:** DECIDED — Q9 closed. Do not tighten `run_master` to `can_edit_master`. Q10–Q11 still open.

## 2026-08-28 Q8 external recipients: users may add; admin/dev must approve
**What I had to decide:** May ordinary users email reports outside the company domain?
**Options I considered:** (1) Any address. (2) Hard-block non-company domains except privileged override at send time. (3) Users may add outside addresses, but mail waits on admin/developer approval.
**What I chose:** (3). Owner: regular users can add; admin or developer must approve. Approved company domain starts at `achimonline.com`.
**Why:** Salesmen/managers need to request customer addresses without being able to fire unapproved mail.
**Status:** DECIDED — unapproved addresses must not receive mail. Approvals are audited. Phase 6 builds the pending/approve flow. Q9–Q11 still open.

## 2026-08-28 Q7 /beta bookmarks: keep 302 through Production cutover
**What I had to decide:** Keep `/beta` 302 to `/`, or return 410/404 now?
**Options I considered:** (1) 410/404 immediately. (2) Keep 302 through Production cutover, then remove.
**What I chose:** (2). Owner confirmed. `PrefixRedirectMiddleware` stays for now.
**Why:** Old bookmarks should keep working during cutover. After Production is stable, `/beta` becomes 410.
**Status:** DECIDED — Q7 closed. Exact 410 date is a go-live follow-up, not a Phase 0 block. Q8–Q11 still open.

## 2026-08-28 Q6 in-app email distributions: stay retired
**What I had to decide:** Port the old Live in-app email-distribution UI, or leave it deleted?
**Options I considered:** (1) Rebuild some or all of it in v3. (2) Leave it retired; Azure Automation keeps sending.
**What I chose:** (2). Owner: leave it retired.
**Why:** The old screen is gone. Automation already delivers those reports. Rebuilding it is out of scope for this PR.
**Status:** DECIDED — Q6 closed. Q7–Q11 still open.

## 2026-08-28 Q5 calendar source: live Hebcal fetch; fail job and email test users
**What I had to decide:** python-zmanim vs Hebcal, and what happens when the lookup fails.
**Options I considered:** (1) python-zmanim offline. (2) Disk-cached Hebcal, send if the cache still covers now. (3) Live Hebcal fetch as the source of truth; on failure do not send.
**What I chose:** (3). Owner: fetch is the main path. If it fails, fail the job and email the test users. No python-zmanim. Do not send from a stale cache.
**Why:** Same calendar as the Azure runbook. A failed lookup must be visible (failed job + mail), not a quiet skip.
**Status:** DECIDED — recipients are Settings `schedule_test_emails` (the test-user list). If that list is empty, still fail the job and log; do not send the report. Q6–Q11 still open.

## 2026-08-28 Q5 Hebcal down: hold unless a saved calendar still covers now
**What I had to decide:** If Hebcal is down at send time, hold or send?
**Options I considered:** (1) Send anyway. (2) Always hold on any lookup failure. (3) Use a saved calendar; hold and alert only when it does not cover now.
**What I chose:** (3). Owner confirmed. Do not send blind.
**Why:** Sending on Shabbos/Yom Tov by accident is worse than a delayed report. Current code already holds on exception, but the cache is memory-only and dies with the process.
**Status:** DECIDED — superseded by the calendar-source entry above: live fetch; fail job + email test users; no send from cache.

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
**Status:** DECIDED — Q1–Q11 logged. Archive restore was already proven. Phase 0 product gate is closed. Phase 1.2 Flask-secret rotation remains BLOCKED.

## 2026-08-27 P0: cookie file untracked; history rewrite blocked
**What I had to decide:** Whether to rewrite git history of `webapp-cache` in this change.
**What I chose:** Untrack `.scratch/parity-cookies.env`, tighten gitignore, add a filename-only scan. Do not print values. Do not force-push production history.
**Why:** History purge needs a coordinated force-push of every branch that contains `f286ce2`. Session revoke needs rotating `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure (cookie-signed sessions).
**Status:** DECIDED — no history rewrite. Still BLOCKED on rotating Flask secrets in Azure.

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

## 2026-08-27 Delete webapp/ and rebuild/; v3 is the only site
**What I had to decide:** Keep holding `webapp/`/`rebuild/` because `/` imported them, or delete them now that the owner asked why they were still there.
**Options I considered:** (1) Keep holding until a later phase. (2) Make v3 boot alone, then delete both trees and the extra mounts.
**What I chose:** Native MSAL + magic links + OData runners + report-source map in v3. Keep `is_beta=True` (reports-only flags, `BETA_PRECIOUS_DB_PATH`, `session` cookie). Drop the Beta pill. `/beta` still 302s to `/`. Do not port in-app Live email distributions; Azure Automation still sends. Delete `webapp/`, `rebuild/`, `tools/parity/`, `/legacy`, `/test`, `/test-next`.
**Why:** Owner overrode the hold. Rollback is tag `archive/pre-cleanup-2026-08-27`.
**Status:** DECIDED — shipping this change.

## 2026-08-27 Junk cleanup after inventory approval
**What I had to decide:** "Do it all, clean it all up" vs still not deleting `webapp/` / `rebuild/` while `/` imports them.
**Options I considered:** (1) Delete every old app generation. (2) Only untrack `.scratch/`. (3) All inventory junk, keep running apps and mounts.
**What I chose:** Tag `archive/pre-cleanup-2026-08-27` at `b14d725`, then untrack `.scratch/`, delete `logs/run_log.csv`, `v3/REVIEW-LOG.md`, and rebuild audit/proposal/history docs. Leave `webapp/`, `rebuild/` app, dispatcher mounts, Beta pill, `tools/parity/`, and `static_dist` maps.
**Why:** Rollback tag first as requested. Removing `webapp/` would take down `/` today. Clutter is not the live site.
**Status:** DECIDED — shipping this change.

## 2026-08-27 Deletion inventory (no deletes)
**What I had to decide:** Whether to untrack `.scratch/` and drop review logs in the same pass as the inventory.
**Options I considered:** (1) Untrack `.scratch/` now because `.gitignore` already lists it. (2) Inventory only; wait for explicit approval of the exact list.
**What I chose:** Inventory only (`DELETION-INVENTORY.md`). Default approval of "the inventory" means untrack `.scratch/` only. `webapp/` and `rebuild/` stay until v3 owns login and OData.
**Why:** `cleanup-protocol.mdc` and the repository review both require an approved list before removal. Untracking 168 files without a yes is still a deletion from git.
**Status:** DECIDED — shipping the inventory; deletions BLOCKED on owner reply.

## 2026-08-27 Review: v3 Feather and Tabulator served locally
**What I had to decide:** Leave v3 on unpkg with SRI, or vendor the two libraries the same way legacy Feather was vendored.
**Options I considered:** (1) SRI hashes on unpkg. (2) Copy Feather 4.29.2 and Tabulator 6.3.1 into `static_dist/vendor`. (3) Keep the CDN until the single-site migration.
**What I chose:** Vendor both. CSP drops unpkg and jsdelivr. Google Maps stays on Google's CDN. Rebuild (`/test-next`) still uses unpkg Tabulator 5.6.1; that tree is not this pass. Do not add a repo `.semgrepignore` — a custom one replaces Semgrep's defaults (including `tests/` and `*.min.js`) and surfaces false positives in our CSRF tests.
**Why:** Review item 20 leftover. Local copies match the legacy Feather change. Maps cannot reasonably use SRI.
**Status:** DECIDED — shipping this change.

## 2026-08-27 Semgrep: Django `{% csrf_token %}` on Flask forms
**What I had to decide:** CI Semgrep `django-no-csrf-token` stayed red after a real Jinja `{% csrf_token %}` tag, and `Markup()` on that tag's renderer tripped `explicit-unescape-with-markup`.
**Options I considered:** (1) Revert form tokens and rely on the JS injector so baseline findings stay old. (2) `nosemgrep` on the POST forms plus keep the tag. (3) Keep fighting the generic `pattern-not-inside`.
**What I chose:** Keep `{% csrf_token %}` (no-JS POSTs still send a token). `nosemgrep` on those form tags — the Django rule does not treat the tag as a match in generic HTML. The hidden input is template text plus `|e` on the token (`Markup()` and `__html__` each trip a Semgrep XSS rule).
**Why:** Server CSRF is real; the scan rule is Django-shaped. Hiding the token to please baseline would break no-JS login.
**Status:** DECIDED — shipping this change.

## 2026-08-27 Review: legacy CSRF and local Feather
**What I had to decide:** How to add CSRF without boiling every fetch caller, and whether to SRI-pin CDNs or vendor them.
**Options I considered:** (1) Flask-WTF. (2) Copy v3's per-session token and wrap `window.fetch`. (3) Add integrity hashes on unpkg/jsdelivr.
**What I chose:** Same CSRF as v3 (form field or `X-CSRF-Token`). The existing fetch wrapper attaches the header. HTML forms get a hidden field. Entra `/auth/callback` is exempt. Feather is served from `/static/vendor`. Unused Chart.js CDN is gone. Google Maps stays on Google's CDN (dynamic loader). v3 Tabulator/Feather CDNs stay for a later pass.
**Why:** Review items 13 and 20. Wrapping fetch covers the JS POSTs without touching every file. Local Feather is stronger than SRI on unpkg. Maps cannot reasonably use SRI.
**Status:** DECIDED — shipping this change.

## 2026-08-27 Review: leftover XSS and Ordered/Invoiced formula prefix
**What I had to decide:** How far to take remaining innerHTML and Excel writers after customer-access CI went green.
**Options I considered:** (1) App-wide CSRF plus CDN SRI in this slice. (2) Only D365/user-data HTML sinks and the Ordered/Invoiced writers that skip `make_streaming_cell`. (3) Stop at customer access.
**What I chose:** Escape email-distribution chips/logs, order-entry matrix labels, settings beta-source keys, and db-explorer error text. Prefix `=+-@` on Ordered summary cells, Invoiced data/commission name cells, and salesman totals names. Leave CSRF and CDN SRI unpaid (SameSite=Lax; Semgrep baselines those hits).
**Why:** Review leftover items 10–11. CSRF/SRI are repo-wide and were already deferred from P0.
**Status:** DECIDED — shipping this change.

## 2026-08-27 Review: customer access fail-closed
**What I had to decide:** Missing dashboard_cache / missing salesman_key used to grant access. Managers skipped order-detail checks because they have no salesman key.
**Options I considered:** (1) Keep fail-open on cache misses so last-order works when the cache is empty. (2) Deny when the book is unknown; last-order may pass a D365 sales_group. (3) Treat managers as admin.
**What I chose:** Deny when the book/account is unknown. Admins still pass. Managers need a grant matching the customer's sales group. Last-order can pass D365 sales_group; a blank group falls back to cache. Address, price, and generate-po APIs use the same helper. `/api/customers` lists only books the user may see (managers: grants; salesmen: own key; no key: empty).
**Why:** Review items 6–8. Fail-open on missing data was the hole. Number 4 / salesman Excel prefix and last-order / order-entry innerHTML are leftover items 10–11 in this same change.
**Status:** DECIDED — shipping this change.

## 2026-08-27 Review: session role vs DB authorization
**What I had to decide:** Whether developer tools should stay reachable during impersonation, and what to do with a disabled account that still has a cookie.
**Options I considered:** (1) Check the impersonator's real_email so db-explorer works while viewing as a salesman. (2) Check the current identity only, matching today's v3 `p.role` gates. (3) Demote disabled users to salesman in the cookie vs sign them out.
**What I chose:** `Authorization.is_developer` uses the current identity's DB row, so impersonating a salesman hides developer tools. `session_allowed` signs out inactive own-sessions; impersonation continues only while the real actor is still an active admin/developer. Live user copy replaces salesman grants instead of only adding. Legacy `get_current_user` re-reads role from `app_users`; a `_dev` cookie whose actor is no longer a developer is dropped.
**Why:** Review items 1–4. Session is identity. Privilege that survives a demotion or disable until cookie expiry was the hole. Opening db-explorer while impersonating would mix actor privilege with target identity; v3 already 403'd that.
**Status:** DECIDED — shipping this change.

## 2026-08-27 Review: magic links, XSS, formula prefix
**What I had to decide:** Throttle numbers, magic-link URL host, and how far to take Excel formula neutralization.
**What I chose:** 5 tokens per email / 15 min; 40 POSTs per client IP / 15 min. New token marks older unconsumed tokens consumed. Consume is one UPDATE. Login re-checks salesman + is_external. Emailed URLs use PUBLIC_BASE_URL, or https://reports.achimonline.com on Azure, never the request Host. History cells and notif-diag strings are escaped. Legacy streaming/DataFrame Excel paths prefix `=+-@` leaders.
**Why:** Review items 9–11 and 14–18. Azure shares a proxy address, so IP cap is spray protection (40), not a per-desk lock. Number 4 / salesman writers that skip `strip_datetime_tz` / `make_streaming_cell` are still unpaid.
**Status:** DECIDED — shipping this change.

## 2026-08-27 Review: download-file, GET repair, headers
**What I had to decide:** How far to go on remaining review security items after P0 CI went green.
**What I chose:** (1) `download-file` only serves an .xlsx that is under Direct Reports *and* in the current user's history, using `commonpath` instead of `startswith`. (2) `precious-repair` GET is check-only; mutating actions require POST+CSRF. (3) Add CSP/frame/nosniff/referrer/permissions headers; HSTS on Azure/prod. CSP still allows current CDNs and `'unsafe-inline'`.
**Why:** Review items 5, 12, 19. Ownership is the missing check; prefix matching is a known bypass. GET is CSRF-exempt so mutations cannot stay on GET. Strict CSP without `'unsafe-inline'` would break inline scripts and Google Maps.
**Status:** DECIDED — shipping this change.

## 2026-08-27 CI: pin Actions + baseline Semgrep
**What I had to decide:** Fix 130 blocking Semgrep hits (CDN SRI + Django csrf_token on Flask forms) and zizmor unpinned-action / persist-credentials findings on this PR by rewriting templates, or by tightening CI.
**What I chose:** Pin every `uses:` to a commit SHA, set `persist-credentials: false` on checkout, pin the Semgrep image digest. On pull_request, Semgrep `--error` only for findings new vs the PR base. Full-repo `--error` stays unpaid debt, not this P0.
**Why:** Those 130 hits are pre-existing on `webapp-cache`. Boiling SRI/CSRF across `webapp/templates` is not P0 containment. Unpinned tags were failing Code Scanning.
**Status:** DECIDED — shipping this change.

## 2026-08-27 P0: stop cursor/** Production deploys
**What I had to decide:** Keep Cloud Agent branches deploying Production (README Rule Preference from 2026-08-25) or follow the repository review.
**What I chose:** Production deploys only from `webapp-cache`. `cursor/**` no longer triggers the Azure workflow.
**Why:** Review P0.2. Agent branches were shipping unreviewed code to the live slot.
**Status:** DECIDED — shipping this change.

## 2026-08-27 P0: Litestream fail-closed in prod
**What I had to decide:** Keep startup.sh fail-open (never take the site down) or refuse boot when restore leaves precious.db missing.
**What I chose:** `APP_ENV=prod` (default) requires Litestream Azure settings and a precious.db file after restore. `/healthz` stays liveness; `/readyz` is 503 when the db is missing or the restore-failed marker is present. Local `APP_ENV=dev` still boots without Litestream.
**Why:** Review P0.4. An empty database with a green health check is worse than a recycle loop.
**Status:** DECIDED — shipping this change.

## 2026-08-27 P0: OData fail-closed for scoped users
**What I had to decide:** Disable all OData for salesmen, or fail the report when any tab cannot prove salesman scope.
**What I chose:** Fail the whole OData payload if any non-empty tab has no salesman column. Filter remaining tabs with `salesman_key`. Unrestricted users unchanged.
**Why:** Review P0.3. Post-aggregation By Item has no salesman column, so returning it unfiltered leaks company-wide rows.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Shipping $ and remainder have no fallback math
**What you asked for:** Shipping $ and Extended Price Remainder should only show ShippingDollars from the SP. No fallback calculations.
**What I chose:** Both columns are `ShippingDollars` only. Missing/blank is $0, same as other SP dollar fields. Open $ stays Ordered $ − Shipped $ − Cancelled $. Ordered builder_version 7.
**Why:** Qty × price and Open $ math were invented numbers, not the SP.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Ordered remainder is ShippingDollars
**What you asked for:** PO # is CustomerRequisition. Ship Date is ShippingDateRequested. Summary Extended Price Remainder is ShippingDollars.
**What I chose:** Map those three SP columns. Shipping $ on the other Ordered tabs also uses ShippingDollars when present (else released qty × price). Open $ stays Ordered $ − Shipped $ − Cancelled $. If ShippingDollars is missing, Summary remainder keeps that Open $ math so the report does not go to $0. Ordered builder_version 6.
**Why:** Matches the ordered_report catalog. Remainder is the shipping-dollar column, not a separate delivery-remainder dollar field.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Ordered remainder dollars come from the SP
**What you asked for:** Summary Extended Price Remainder should come from the stored procedure column “delivery remainder dollar amount,” not from Ordered $ − Shipped $ − Cancelled $.
**What I chose:** Map that SP field (DeliveryRemainderDollarAmount and a few name variants) onto the Ordered line. Summary Extended Price Remainder and Open $ on the other Ordered tabs use it when present. If the column is missing, keep the old Ordered $ − Shipped $ − Cancelled $ math so the report does not go to $0 before the SP change lands. Ordered builder_version 5.
**Why:** Same remainder dollars everywhere. Blank/missing must not wipe the column.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Company views for Daily Ordered and Heshy Open Orders
**What you asked for:** A Daily Ordered view grouped by salesman then customer on By Customer, applied to every daily company Ordered send. A Heshy Open Orders view with Full Data only, sorted by customer, grouped by order (order totals, no customer total), no LineNumber. Ship Date on Ordered in general without failing if the SP does not send it yet. Company-wide views. Test sends of yesterday Ordered and the open-orders report.
**What I had to decide:** Whether to change By Customer’s default group for every Ordered use; whether Excel grouping could stay single-level; whether named company views live at send or stay as schedule snapshots.
**What I chose:** Named company views in `company_views`, shared like Default. Daily Ordered is salesman then customer on By Customer only — the builder’s default group stays salesman-only. Heshy Open Orders is Full Data only: sort customer then order number, group on order number. Excel nested groups + sorter-aware sort so a second group and a customer sort both survive the file. Send uses the live company view when the schedule’s View name matches. Ship Date is always on Full Data; blank if the SP has no column. Ordered builder_version 4. Boot seeds the two views and stamps matching daily company schedules (not salesman-split files).
**Why:** One named view per job, visible to everyone, editable by managers. Changing the global By Customer default would regroup salesman-split files and anyone still on Default.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Default view per report
**What you asked for:** A Default view for every report matching how it looks now, a way to edit those defaults, the schedule wizard showing Default as the view, and the schedules page showing which view each row uses.
**What I had to decide:** Company-wide vs per-user Default; whether editing Default rewrites existing scheduled files; who can edit.
**What I chose:** One Default per report, shared. Managers and admins edit it from Saved views (Edit, then Save this view). Schedules that use Default with an empty layout pick up the new Default on the next send. Schedules that already have a locked layout (seeded tab lists, or Schedule from a report page) keep that snapshot and still show Default or Custom on the list. Wizard starts on Default. Report-page Schedule saves as Custom.
**Why:** Company schedules need one shared starting layout. Wiping seeded “no commissions” files when someone edits Ordered Default would change production workbooks.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Azure Actions concurrency group renamed
**What you asked for:** Ghost GitHub runs cannot be cancelled or deleted. That made it look like Actions could no longer deploy the site.
**What I chose:** Rename the Azure workflow concurrency group from `deploy-achim-sales-reports` to `deploy-achim-sales-reports-v2`. Keep one-at-a-time deploys (`cancel-in-progress: false`). `deploy.ps1` stays the backup when Actions is wedged.
**Why:** Those four runs are stuck with no jobs. GitHub will not cancel or delete them. The old group may keep every new Azure deploy waiting behind them. A new group name is a fresh lock. Pages ghosts do not use this group.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Ordered Fulfillment % on the rolled-up tabs
**What you asked for:** Put fulfillment percentages back on the Ordered report, colored like the old runbooks.
**What I had to decide:** Old runbooks had Fulfillment % on By Customer, By Item, By Order, By Salesman, and Full Data (red→yellow→green). Summary (customer + item) did not. v3 only had the column on Full Data.
**What I chose:** Same five tabs as the old writer. Formula stays `(QtyOrdered - QtyCancelled) / QtyOrdered` on the summed qty for rolled-up rows. Grid and Excel already color `Fulfillment %`. Summary stays without it. Ordered builder_version 3 so cached v2 payloads are not reused.
**Why:** Matches the old workbook. Summary never had that column.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Oversized schedule mail gets a download button
**What you asked for:** The Daily 5am Number 4 mail said the 13.4 MB workbook was too large to attach, and told you to download it from SharePoint or export it from the app — with no link. Test-mode files must not land in the live Daily/YTD folders.
**What I had to decide:** Test mode used to skip SharePoint entirely. Graph then refuses anything over ~3 MB, so the body had no URL. Whether to write test runs into the real Daily folder, skip SharePoint (no link), or dump into a separate test folder.
**What I chose:** Test mode still emails only the test list. If the schedule has a SharePoint path, the file goes to `Direct Reports/Test`, never to the live folder. Oversized Graph mail (no live folder, or Email me) also lands in `Test`. The mail includes an Outlook-safe blue **Download workbook** button plus the raw URL in the plain-text part. A failed Test-folder upload does not fail the email. Split salesman files stay email-only.
**Why:** You need a clickable download in the inbox, and test dumps must not mix with production Daily/YTD. Graph wraps mail as HTML, so a `<pre>` of the old text could never render a button.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Preset salesman/status must ride along even if the dropdown is empty
**What you asked for:** Heshy Open Orders should only run open orders for Heshy. The preset did not keep those filters.
**What I chose:** Keep the saved salesman on `pendingSalesman` until the dropdown actually has that option. `collectParams` sends that value even when the list is still loading. Status “Open” maps to “Open order”. Home-card URLs still include salesman and status.
**Why:** Lookups often return empty on first paint. Setting `<select>.value` to Heshy with no matching option silently resets to All, and the auto-run went out unfiltered.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Home presets and saved views must run, not replay the last job
**What you asked for:** Opening Heshy Open Orders (or any home preset / saved view) after already running a report still showed the previous run.
**What I chose:** `?preset=` skips reconnecting the last job for that report (unless `?job=` is also on the URL). Clicking a saved view’s name runs it. Edit still loads filters/layout without running when the grid already has data.
**Why:** Coming-back resume was winning over the home-page preset, so the new filters and layout never applied. Saved-view name click only changed the form, so an already-shown grid looked unchanged.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Merge remaining branches onto production
**What you asked for:** Merge the leftover Sales by State / meeting-fix work and the Shabbos makeup-clock work into the production site.
**What I chose:** Merge both onto `webapp-cache` (keep Number 4 builder 3, empty salesman split = no xlsx, catch-up at scheduled HH:MM). Production is `webapp-cache`; Azure deploys that branch and `cursor/**`.
**Why:** Those two commits were the only remaining unique work after branch cleanup. They never landed on `webapp-cache` because the remote branch names were deleted first.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Azure GitHub Action also deploys cursor/** branches
**What you asked for:** Let a Cloud Agent deploy, the same way a push to `webapp-cache` does.
**What I chose:** Keep one production Action. Trigger it on `webapp-cache` and `cursor/**`, plus the existing manual `workflow_dispatch`. Queue overlapping deploys (`concurrency`, do not cancel). Same production slot as today.
**Why:** GitHub runs the workflow file from the branch that was pushed, so this file has to list Cloud Agent branches or their pushes never start a deploy. There is no staging slot in the current Action. `deploy.ps1` stays as a fallback when Actions cannot run.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Number 4: YTD tabs, By Item qty-only, group by item
**What I had to decide:** How to add rolling-12 + YTD tabs for each Number 4 version, drop money from By Item, and group by item, without a YTD stored procedure.
**Options I considered:** Wait for DBA YTD SPs; fetch invoice lines and pivot in the app (old path); derive YTD from the rolling-12 pivot (prior-year months dropped, totals recalculated).
**What I chose:** Derive YTD from the rolling-12 SP result. By Item strips every money column (month $, Total $, Avg Price, Book Price). All Number 4 tabs default-group by Item #. Excel By Item writer matches (qty only; it already had 12 Months + YTD sheets).
**Why:** YTD months are always inside the rolling-12 window, so the numbers stay on the same basis as the SP (exclusions, merchandise $). No extra SP call. Builder version 3 so old cached payloads are not reused.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Shabbos makeup at the scheduled clock, not havdalah
**What I had to decide:** Home-site schedules skipped Shabbos then fired as soon as havdalah passed. The owed send should keep the schedule's clock time, and the date window should follow the period (MTD on Friday the 30th → Monday 10pm covering that MTD, plus month-end if the makeup is next month).
**Options I considered:** Keep motzei-Shabbos fire (current); wait for the next regular cadence day (loses last_month / month-end MTD); wait for the next same HH:MM that is not restricted, using Monday–Friday for periods that cannot wait for the next cadence.
**What I chose:** Skip-class (yesterday/daily, in-month MTD, in-year YTD) waits for the next regular slot at that HH:MM and never Saturday night. Reschedule-class (last_7_days, last_month, month-end MTD, year-end YTD, all-time reports) waits until the next weekday at that HH:MM. MTD that crosses a month runs the skipped day's MTD, then through month-end if those dates differ. Branch is `webapp-cache` (Beta is already `/`).
**Why:** Matches "not right after Shabbos" and the Friday-30th-10pm → Monday-10pm example. Live Azure still reschedules after havdalah; this change is home-site only.
**Status:** DECIDED — shipping on the home-site clock.

## 2026-08-24 Meeting: tabs, views, groups, empty split mail, Ordered %, personal Edit, Sales by State sheet 3
**What you asked for:** After the user meeting — restore removed tabs like columns; rename copied tabs; Edit/Delete on saved views (not Edit+✕); Edit opens the whole view then Save / Save as; nested groups with delete-able pills; home-page presets apply the full view; empty salesman splits must not send a workbook (text “No Data Found” like the old runbook); Daily 9am salesman Ordered grouping like Daily shipped; bring back Ordered Fulfillment % (green→red); edit personal schedules; Sales by State third sheet from `sales_by_state_filtered`.
**What I chose:** Removed original tabs stay in memory and come back from the Columns dropdown. Copied tabs get Rename. Edit loads filters+layout (and runs if the grid is empty); Save with the same name overwrites, a new name creates another view. “Group by this column” / “Add subgroup” append; pills remove one level. `applyLayout` recreates cloned tabs so a home-page preset matches the saved view. Split legs never send empty Excel; they send the old runbook no-data text. The no-data checkbox is for the company copy only. Per-rep Ordered files drop Salesman grouping and use a tab-order layout like shipped dropping commissions. Fulfillment % is `(QtyOrdered - QtyCancelled) / QtyOrdered` on Full Data, colored in the grid and Excel. Personal rows get Edit and PUT `/api/schedules/<id>`. Sheet 3 catalog key is `sales_by_state_filtered` (overrides the earlier “detail only” choice). Test mode stays On.
**Status:** DECIDED — deployed `0db0f60` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-24 Recent Reports link; export panel from the status line
**What you asked for:** The "building in the background — see Recent exports" message pointed at a place you could not find. Recent Reports should be a hyperlink.
**What I chose:** Header label is **Recent Reports**, styled as a text link (same button, same jobs panel). Starting an Excel export opens the Recent exports list and the status line's **Recent exports** words open it too.
**Status:** DECIDED — shipping this change.

## 2026-08-24 Sales by State on the home site (SQL only)
**What you asked for:** Add the Sales by State report to the home site (former Beta). Use the SQL API only — no OData, no data-origin selector on Settings. The Excel file is the look; the Word doc is the DBA handoff.
**What I chose:** One report, three tabs (Summary, New York City, Detail) matching the workbook. Year filter → FromDate/ToDate for the three catalog keys. Left Unknown / filtered / other-transaction SPs out because they are not in the sample file. Not shown to salesmen by default.
**Status:** DECIDED — shipping this change.

## 2026-08-21 Invoiced salesman from endpoints, not Excel
**What I had to decide:** After the 029 stamp, whether to keep using salesman_map.xlsx / the hardcoded map for invoiced salesman codes.
**What I chose:** Do not use the Excel map for invoiced salesman identity. Use the invoiced report row; if that is missing or just a number, use the same customer/salesman data as the report dropdowns. Live OData invoiced uses CustomersV3.SalesGroup the same way, with no Excel overlay.
**Status:** DECIDED — shipping this change.

## 2026-08-21 Invoiced 029; saved views; schedule Where page
**What you asked for:** Daily invoiced marked every salesman as 029. Saved views should open without running, be editable, and appear when scheduling. The Where page should not squash fields; hide Email/OneDrive/SharePoint until chosen; filename first; move sharing / run-as / test-email-on-empty to Options.
**What I chose:** Prefer SalesGroup/SalesmanName when the salesman field is a number; if the spreadsheet stamps one number on most rows, use the built-in map for numbers. Saved views: click applies filters without running; Edit patches name+filters+layout; Options has a per-report dropdown. Where: filename, then Email / Save to Cloud. OneDrive vs SharePoint is one cloud target (same as before). Empty-data "test email addresses" uses the Settings test list.
**Status:** DECIDED — shipping this change.

## 2026-08-21 Whole-job retry; unlink dead OrderReportDirect
**What you asked for:** Another job failed this morning. Add a retry so a one-time blip is not the last word.
**What I chose:** This morning's Failed row was leftover `OrderReportDirect` on `DailyOrderReport` looking for `daily_order_report.py` on SharePoint (gone). The real 4am `universal_runbook` job Completed. Unlinked that leftover. Real jobs now retry the whole run once after 30s (Azure runbook + home-site schedules). `[FAIL]` mail still only after that second miss. Test mode stays On.
**Status:** DECIDED — shipping this change.

## 2026-08-20 Home-site schedule failures email the test list
**What you asked for:** Know why the three legacy 9am jobs failed, stop that class of miss, and get a mail on the home site whenever a report fails — using the test-email field even when test mode is off.
**What I chose:** The 9am jobs were not shut off. SharePoint dropped the TLS connection while they downloaded scripts (and once the run log). Downloads now use the existing Graph retry (up to 4 tries). Home-site clock and Run now failures send `[FAIL]` mail to the test-email list, test mode on or off. On-page Run report / Email me stay on-screen only. Test mode stays On.
**Status:** DECIDED — shipping this change.

## 2026-08-20 Login and role picker live on the home app
**What you asked for:** Login should go to Beta (home). The developer role picker should work there.
**What I chose:** `/login` is the home sign-in page (Achim User + External Rep). Microsoft still starts at `/legacy/login/start` and comes back to `/auth/callback`. Developers land on `/dev/role-picker` (same picker as old Live: yourself as admin, or search/pick a user). The header switch-user button opens that picker even while impersonating. Test mode stays On.
**Status:** DECIDED — deployed `1a6be71` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-20 Beta is the site home; old Live is /legacy
**What you asked for:** Make the Beta page the home page. Put the current home at `/legacy`.
**What I chose:** `/` is v3 with `is_beta`. `/legacy` is `webapp/` (OData, email distributions). `/beta/...` 302s to the same path without the prefix. Microsoft login stays `/auth/callback` (no new Entra URI); the login page is `/legacy/login`. Anyone who can sign into Live can use `/` — the Beta Access flag is not a gate. If Beta fails to boot, `/` stays the old Live app. Test mode stays On.
**Status:** DECIDED — deployed `f181095` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Email me button; salesmen never see Commissions
**What you asked for:** A report-page button that runs and emails the user themselves. Salesmen must never see the commissions tab.
**What I chose:** Email me next to Run report (current filters → Excel to the signed-in address). Existing Email modal stays for other people/SharePoint. Invoiced Commissions is omitted for salesman role on run, result, export, email-now, and personal schedules. Managers and admins still see it.
**Status:** DECIDED — deployed `77e7dae` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Monthly Salesman SharePoint job stays; add a split schedule
**What you asked for:** Do not rewrite the monthly salesman SharePoint job. Add a separate schedule that fans out.
**What I chose:** Left `Monthly 1st 12am Monthly Salesman` / `Monthly Salesman Report` on `Salesman Report/Monthly` with no split. Seeded `Monthly 1st 12am Monthly Salesmen` / `Monthly Salesmen Report` with `split_by_salesman` and no folder (same 1st / 22:00 clock). Wizard salesman-report filters include salesman so that split flag survives a save. Test mode still On.
**Status:** DECIDED — deployed `ebdcdb2` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Save and On wait for the next scheduled time
**What you asked for:** Saving an edit or turning a schedule On should not run it right away.
**What I chose:** Save, create, and On claim today's slot when that time has already passed, so the clock waits until the next cadence. A schedule that was already On still catch-up-fires if we missed it (app down). Run now is unchanged.
**Status:** DECIDED — deployed `51a4641` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 SharePoint paths drop duplicated Direct Reports; folder tokens
**What you asked for:** Stop dumping files in Direct Reports/Direct Reports. One-shot fix. Let a schedule add a dated subfolder (Customer Activity → August 2026), and let me type that on any schedule.
**What I chose:** Strip a leading Direct Reports from seed, save, browse, and upload (migration for existing rows). Filename date tokens also work in the folder path; spaces stay (`{Month} {YYYY}` → August 2026). Wizard path is editable with token chips. Only Customer Activity auto-gets the month folder; other jobs keep their current path.
**Status:** DECIDED — deployed `4ad39b6` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Company schedules table sorts by name
**What you asked for:** The table with all the schedules should be sortable and automatically sort based on name.
**What I chose:** Company schedules render A→Z by name. Column headers (except Actions) are clickable to re-sort.
**Status:** DECIDED — deployed `45ece96` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Deleted company schedules must not come back on boot
**What you asked for:** Stop putting Daily 9am back after you delete it.
**What I chose:** Boot seed was re-inserting any Azure name that was missing. Delete now records the name so seed skips it. Daily 9am is also off the Beta seed list, and a migration deletes the leftover shared row so this deploy does not resurrect it.
**Status:** DECIDED — deployed `0324e32` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Schedules run log starts collapsed
**What you asked for:** The report run log should be collapsed by default.
**What I chose:** The Schedules Recent run log no longer auto-opens when there are rows. Run now still opens it so you can watch that job.
**Status:** DECIDED — deployed `24323bb` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Company schedules can be copied
**What you asked for:** Copy a company schedule, then change options. Personal Copy already existed.
**What I chose:** Copy on company rows you can already edit. Duplicate everything (report, params, layout, cadence, recipients, SharePoint, filename, share flag, run-as). Name is `{original} (copy)`, then `(copy 2)` if taken. Leave Off so it does not double-send. Copier owns the new row so they can edit it. Shared names stay unique.
**Status:** DECIDED — deployed `d3e8404` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-18 Salesman-all jobs fan out; Ordered drops By Salesman
**What you asked for:** 9am Salesmen Ordered/Shipped should split one file per rep like live `--salesman all`, and those files should not include the By Salesman tab.
**What I chose:** Those company schedules now have `split_by_salesman` (stamped onto existing rows that had no split flags). Split-all with no picked keys emails every active salesman who has an address; no-email salesmen are skipped. Combined SharePoint/management copy still goes out. Per-salesman Ordered builds omit By Salesman (same as the live salesman workbook). Unscoped Ordered still has the tab. Test mode still sends every split to the test inbox.
**Status:** DECIDED — deployed `e3b1ef1` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-18 Invoiced shipped reports skip YTD (match live)
**What you asked for:** Original Python rules on Beta. `--salesman all` / salesman-scoped Shipped omits Commissions, so do not pull YTD — check what tabs are needed, then fetch only that.
**What I chose:** Skip the Commissions tab and the Jan 1 fetch when `params.salesman` is set, when `_skip_commissions` is set, or when a saved `layout.order` exists and does not include `commissions`. Delivery stamps `_skip_commissions` from that layout before the run (9am Salesmen Shipped). Unscoped Invoiced still YTD-fetches. Live OData runners were already correct; this is the SQL Beta path.
**Status:** DECIDED — deployed `2edb1cd` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Shabbos skip + catch-up on Beta clock
**What you asked for:** The Shabbos schedule override from the original runbook,
built into Beta.
**What I chose:** It was not on Beta. Clock runs now check Hebcal for Brooklyn
(same as the runbook): skip while melacha is assur, flag a catch-up, send after
havdalah. Run now still sends (deliberate). Hebcal errors fail open. Live Azure
skip-vs-reschedule by period is folded into this one catch-up so monthly
last_month is not lost until next month.
**Status:** DECIDED — deployed `785684c` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Test mode still splits salesman workbooks
**What you asked for:** Run company schedules just to me for a day or two, but
still split by salesman so I can check the splits.
**What I chose:** Test mode keeps mail on the test list and still skips
SharePoint. Split schedules now fan out: one combined file plus one file per
salesman with an email, salesman in the subject and filename. Salesmen are
not emailed. Salesmen without an email are still skipped (same as live).
**Status:** DECIDED — deployed `e4cd482` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Schedule workbook filenames include the schedule name
**What you asked for:** File names that are intuitive for each run (typed on a
Hebrew keyboard: change the file names to be more intuitive for each run).
**What I chose:** Blank `filename_template` is now
`{Schedule}_{YYYY}-{MM}-{DD}_{HH}{mm}` (Eastern). Company schedules had empty
templates, so Daily 9am and DailyOrderReport both arrived as
`Ordered_20260817.xlsx`. Custom templates are unchanged.
**Status:** DECIDED — deployed `a8140d2` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Beta schedule test mode was not surviving recycle
**What you asked for:** The Delivery test-mode switch (and the test email list)
kept going back to Off after saving.
**What I chose:** The toggle was saving. Azure wipes `/tmp/betadata/precious.db`
on recycle, and Litestream only replicated the `/test` DB. Add a second replica
for `BETA_PRECIOUS_DB_PATH` (`LITESTREAM_AZURE_BETA_PATH`). Unique company
schedule name so two gunicorn workers cannot double-insert the Azure import.
**Status:** DECIDED — deployed `9f7f613` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Settings mobile overflow + exclusive accordion
**What you asked for:** Settings on a phone was overflowing. Opening a section
should close the others.
**What I chose:** Exclusive `<details>` (one open at a time on every width).
Desktop no longer auto-opens all categories. Header **Previously run** shortens
to **Runs** under 480px; settings fields wrap instead of forcing min-widths.
**Status:** DECIDED — deployed `189024d` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Beta settings hub (mini rebuild)
**What you asked for:** One settings page on Beta that matches Live, categorized,
half-width, phone-first, with users, run histories, DB explorer, notification
diagnostic, and beta data sources. Test that it is wired.
**What I chose:** Rebuild Beta `/settings` only. Six categories (You / People /
Reports / Delivery / History / Developer). Email Distributions stays Live-only
(Beta schedules already send mail). Heavy tools stay linked pages. Global report
on/off is new `report_config`. Explorer covers precious + cache. Beta sources UI
lives on Beta; storage stays the live `beta_report_sources` table. Notes:
`.scratch/grill-notes.md`.
**Status:** DECIDED — deployed `a56a67b` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Previously run list + OneDrive root Graph URL
**What you asked for:** A Previously run button; a minimizable run pill that shows
when the report ran; a way to name a kept run. OneDrive Browse 400 after Graph
permissions were granted (`…/drive/root::/children`).
**What I chose:** Header **Previously run** opens the existing jobs panel. The
bottom-right pill shrinks to an icon (remembered in localStorage). Each chip shows
Eastern date/time and optional `jobs.keep_name`. Keep and Name POST `{name}`
(max 80 chars). Opening a chip uses `?job=<id>`. OneDrive root listing uses
`/drive/root/children`, not `root::/children`.
**Status:** DECIDED — deployed `04b649e` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-14 Schedule test mode (redirect + address list)
**What you asked for:** A test mode with test emails so you can run the new
Beta schedules and compare the workbooks to Live, without hitting customers.
**What I chose:** Admin Settings toggle plus a list of addresses (add/remove;
need at least one to turn On). While On, company schedule mail (Run now and
the clock) goes only to that list, subject tagged `[TEST]`, SharePoint/OneDrive
skipped, salesman-split fanout skipped. Personal schedules unchanged. Off
restores stored recipients and SharePoint. Notes: `.scratch/grill-notes-schedule-test-mode.md`.
**Status:** DECIDED — deployed `2fe1404` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-13 Import Live Azure runbooks onto Beta (disabled)
**What you asked for:** Copy the LIVE Azure Automation schedules onto Beta,
left Off until you check each one.
**What I chose:** On Beta boot, seed company (`is_shared`) master rows from the
current Azure job list, all `is_active=0`. Names match Azure. SharePoint folders
match the Live Direct Reports paths. Recipients are empty (Live emails come from
env/distributions, not the job). Skipped `amazon_weekly` (no Beta report) and the
old OrderReportDirect link. `--salesman all` jobs write one workbook to the
Salesman Report folder — turn on split later if you want per-rep files. Re-seed
skips names that already exist.
**Status:** DECIDED — deployed `4214a62` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-12 One Schedules wizard (scope + share)
**What you asked for:** Stop having two schedule products. One Schedules page,
one Add flow. Company vs personal is options + an explicit share choice.
Managers can share; admins can run a schedule as a picked manager. Managers
see company schedules but cannot edit unless they created it or it is scoped
to them (read-only note: talk to an admin). Sales reps see only their own.
**What I chose:** Keep personal + master tables. Shared/company-setting rows
live on `master_schedules` with `owner_user_id`, `is_shared`, `run_as_user_id`.
Share = list visibility, not a data upgrade. Manager-created shared runs stay
in that manager’s book. Unscoped run = admin/developer with no manager picked.
Notes: `.scratch/grill-notes-beta-scheduling.md`.
**Status:** DECIDED — deployed `f8ac596` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-12 Beta scheduling (grill locked)
**What you asked for:** Schedules on Beta — personal (OneDrive + email anyone) and
admin/master (SharePoint); cadence; filename pills; schedule-this-view; salesman
split; CC/BCC; no-data email options; test email; copy schedule.
**What I chose:** Enable existing v3 schedules on Beta (blueprint + cron + UI).
Master → SharePoint; personal → user OneDrive via app Graph. Excel now, PDF later.
Monthly 1–28 + last day. Split = all salesman **app users** with email; master
copy to typed recipients. Skip SP link-in-body and dry-run (use test email).
Copy schedule; one schedule per param set. Notes: `.scratch/grill-notes-beta-scheduling.md`.
**Status:** DECIDED — implementing

## 2026-08-06 Beta additions: Keep runs + filename templates
**What you asked for:** default Ordered grouping on Beta; resume previously run
reports with a Keep option; salesman Live color bands on screen + Excel;
schedule filename token GUI; Last Order Excel/PDF export popup.
**What I chose:**
- Ordered-only `default_group` (SQL already had it; OData bridge now attaches
  the same for Summary / By Customer / By Order).
- Resume window **48h**; **Keep** sets `jobs.kept_until` (+30d), cap **5** per
  user (oldest Keep cleared). Migration `0003_keep_and_filename_template.sql`.
- Salesman bands via streaming openpyxl fonts (no full-workbook mode) +
  Tabulator colored formatters.
- `filename_template` column on schedules/master_schedules; tokens resolved
  Eastern in `web.delivery.filename_template`.
- Last Order: one Export → Excel | PDF popup; PDF is a tiny stdlib writer.
**Status:** DECIDED

## 2026-08-06 Beta shares Live login (no separate Entra callback)
**What you asked for:** Fold Beta into Live so one Live sign-in covers `/beta`
(no second Microsoft login / no `/beta/auth/callback` Entra URI).
**What I chose:** Keep the v3 UI mount at `/beta` (Test look + hybrid reports),
but share Live's `session` cookie and `FLASK_SECRET_KEY`. Beta adopts
`session["user"]` into a v3 Principal; unauthenticated hits redirect to
`/login?next=/beta/...`. Live login honors `next`. Mount stays — full Live
blueprint rewrite of the Test UI is deferred.
**Why:** Same user-facing outcome (one login) without re-porting the report UI
into Live templates. Separate Entra callback was a side effect of a separate
cookie, not a product need.
**Status:** DECIDED

## 2026-08-06 Beta day-one scaffold (v3 mount, not rebuild tree)
**What I had to decide:** Grill said Beta tree from rebuild + v3 look, but
rebuild only seeds 4 reports while Beta needs every report day one.
**Options I considered:** (1) Port all reports into rebuild first, then mount;
(2) Mount v3 at `/beta` with `is_beta` (Test look + full report set) and hybrid
source switch; keep rebuild at `/test-next` until retired.
**What I chose:** (2). Hybrid SQL/OData via shared `beta_report_sources` in live
DB; OData bridge runs live Excel runners and shapes sheets into v3 tabs;
schedules stay Live/OData (phase two).
**Why:** "Every report" + Test look ship without blocking on rebuild feature
parity. Rebuild quality can land incrementally; `/test-next` still retires when
Beta is stable.
**Status:** DECIDED

## 2026-08-06 Beta app — reports page, hybrid SQL/OData, schedules later
**What you asked for:** fourth surface (Beta) so users have one reports link;
look like `/test`, run like `/test-next`, data per report (SQL if signed off,
else OData); eventually replace Live; PM wants this while parity continues.
**What I chose:**
- `/beta` on same App Service; tree from `rebuild/` + `v3` look; retire
  `/test-next` after Beta is stable; `/test` stays direct-link only.
- Beta = **reports page only** (menu → run → screen → export). Schedule/email
  and other product features stay on Live.
- Per-report source switch in **Live Settings** (dev-only), shared storage.
  Server hard-gates `can_access_beta` (direct URL too).
- **Phase two:** Live Azure schedules honor the same SQL/OData map. Day one
  schedules stay OData.
**Evidence:** `.scratch/grill-notes.md` (Beta section).
**Status:** DECIDED — plan locked; build not started until kickoff.

## 2026-08-05 Salesman month/year reconcile perfect + commissions live layout
**What you asked for:** break salesman↔invoiced down by month/year until
perfect; commissions tab on invoiced should match live visually, but without
future months.
**What I found / did:**
- Reconcile (env-key diagnostic): every month **Jan–Aug 2026** delta **$0.00**,
  by-customer amount_diffs **0**; **Jan–Aug 2025** same; YTD Last Year
  **$23,012,337.67** both sides; Full Year Last Year SP self-check delta **$0**;
  YTD/Full Year This Year already **$0** vs invoiced. Future months empty.
- Commissions UI: live Excel-style pivot (metric rows × month columns + YTD,
  blue header / yellow commission+payable). Builder already caps at
  `end_month` (no Sep–Dec mid-year). Excel export updated to the same rows.
**Evidence:** `.scratch/parity/reconcile_ty_m{1..8}.json`,
`reconcile_salesman_ly_out.json`.
**Status:** DECIDED — salesman money perfect by month/year vs TEST invoiced;
commissions layout matches live minus future months. Deployed to
`achim-sales-reports`.

## 2026-08-05 Salesman YoY SP reconciles to invoiced Total Invoice
**What you asked for:** run salesman and compare numbers to TEST invoiced.
**What I found:** `POST /api/reports/monthly_salesman_yoy/run` works. YTD
2026-01-01..2026-08-05: salesman YTD sum **$17,028,637.71** = invoiced
Total Invoice sum **$17,028,637.71** (delta **$0.00**). By customer account:
**586/586** within $0.05, **0** amount diffs. Salesman-label pair mismatches
are name-format only (`REdwards` vs `Edwards, Reggie`) — same dollars.
**Evidence:** `.scratch/parity/reconcile_salesman_out.json` via one-shot
`/test/api/reports/diagnostics/reconcile-salesman-invoiced` (env-key gated;
key cleared after run).
**Status:** DECIDED — salesman SP money matches invoiced Total Invoice for YTD.

## 2026-08-05 Salesman report -> monthly_salesman_yoy SP
**What you asked for:** stop using the invoiced endpoint for salesman; wire
`rpt.usp_monthly_salesman_yoy` (Total Invoice basis, YoY columns). Ground truth
is TEST invoiced / `vw_Invoiced_Report`, not OData.
**What I did:** Catalog id `monthly_salesman_yoy`. Params: ReportYear,
ThroughMonth (+ optional SalesmanId/Name, CustomerAccount/Name). Builder
reshapes the wide SP row into the existing 12 month tabs; no CC/freight strip
(SP sales = Total Invoice). Unit tests for builder + params (21 pass in those
files).
**Status:** DECIDED — deployed `8a3c3c1` to `achim-sales-reports` (RuntimeSuccessful).
Live column-name confirm still needed (Kudu probe hangs from this machine;
open `/test` Salesman or hit the Reporting API from Azure).

## 2026-08-05 Ordered PO # from CustomerRequisition
**What you asked for:** SP now returns CustomerRequisition (2nd column); retest
ordered Customer PO.
**What I did:** Mapped `CustomerRequisition` in `to_fact_ordered_report` into
`po_number` / display `PO #`. Removed `PO #` from stub fields (OrderStatus still
stubbed). Unit tests updated (10 pass). Live SP probe Jul 15–17: 3392 rows,
`CustomerRequisition` present, **100% filled**.
**Status:** DECIDED — deployed `8fb3bcf` to `achim-sales-reports` (2026-08-05).
Parity re-run next with noise filters.

## 2026-08-04 Customer Activity parity: /test is correct
**What you asked for:** after filtering noise (same SO+PO, blank PO on
/test, today-dated last orders), only 3 real SO/PO mismatches remained;
confirm /test and lock it.
**What I chose:** Customer Activity live↔/test is **signed off** — `/test`
last-order pick is the source of truth. Remaining noise (date-only same
SO+PO, blank-PO later orders, same-day high-volume DS, TZ) is not a /test bug.
**Evidence:** `.scratch/parity/20260804-193031-postfix/`; filtered list ended at
Broadway / Lefferts / Super Deal only after those cuts; owner accepted /test.
**Status:** DECIDED — do not chase CA last-order parity further unless product
reopens it.

## 2026-08-04 Site-wide dates via iso_date (YYYY-MM-DD)
**What you asked for:** one helper for every date on the test site; display
yyyy-mm-dd (CLO was showing truncated RFC like "Mon, 27 Ju").
**What I did:** `report_engine.lib.iso_date` is the single helper; `date_only`
aliases it. Wired adapters/builders already using it; CA Last Order Date;
Jinja `|iso_date`; report grid formatter; Excel date format; export/layout/
dashboard mirror no longer `[:10]`-slice. Frontend rebuilt.
**Status:** DECIDED — deploy with this commit.

## 2026-08-04 Customer Last Order → customer_last_orders SP
**What you asked for:** use the new Reporting API endpoint for CLO data; keep
live UX (last order + optional Add previous order merge); v3 look.
**What I did:** v3 CLO now calls catalog `customer_last_orders` (OrderCount=10)
instead of full-history `salesline_release`. Builder groups by Order Rank so
ADDON lines stay under the main PO card; picker modal lists logical orders from
that same result. Labels say "Last Order" (SP includes open/uninvoiced).
**Status:** DECIDED — local on `rebuild-reports`; deploy with `deploy.ps1` when ready.

## 2026-08-03 Monthly last_month Shabbos skip never rescheduled
**What you asked for:** dig why Monthly Invoiced on Aug 1 (Shabbos) skipped but
Azure showed Completed and no motzei Shabbos catch-up ran (job
`SCH_3dc4d915-…639211716000000000`).
**What I found:** streams say `Guard action: skip` for `--period last_month`,
logged SKIPPED to run_log, returned 0 → Azure Completed. `_classify_guard_action`
had no `last_month` rule so it fell through to skip. Catch-up injection also
ignored `last_month`, and the next regular fire is next month when the window
has already shifted.
**What I did:** treat `last_month` like `last_7_days` (reschedule after
havdalah); add last_month catch-up injection as a safety net; unit tests;
published runbook; started manual `invoiced --period last_month --force`
(job `d053cda2-183d-43ef-81f9-5ae1b0efbbd1`) which Completed.
**Status:** DECIDED — live runbook published; July monthly catch-up job green.

## 2026-07-26 Customer Activity sort + fresh parity
**What you asked for:** fresh CA live↔/test compare; fix sorting.
**What I found:** live sorts by Customer Name (pandas, case-sensitive) and builds
All by concatenating salesman groups A–Z. /test was leaving SP row order.
**What I did:** v3 `customer_activity.build` now name-sorts each tab and rebuilds
All the same way. Parity comparer keys CA sheets by `customer_account` (not SO#)
and treats same calendar day as equal across datetime vs `MM/DD/YYYY`.
**Fresh run:** `.scratch/parity/20260726-113809-customer_activity/` — All present,
781/781 accounts matched; sort verified both sides. Remaining hard diffs are
last-order fields (date / PO / SO#), not layout.
**Status:** DECIDED — sort fix deployed to `/test`; comparer/docs local.

## 2026-07-25 Ordered report: SP qty columns (no invented shipped/open)
**What you asked for:** stop inventing QtyShipped / QtyOpen; report SP qty columns
instead — ordered, reserved, released, cancelled, left to ship (DeliveryRemainder).
**What I did:** Ordered builder maps those five from `usp_ordered_report`; dropped
Fulfillment %, QtyShipped, QtyOpen from Ordered tabs. Dollar columns unchanged
(Released $ / Open $ still derived). Customer's Last Order keeps the old
QtyShipped/QtyOpen shape via `salesline_release`. Rollback tag:
`pre-ordered-qty-columns` @ `7db4b92`.
**Status:** DECIDED — deploy to `/test` with this commit.

## 2026-07-25 Master schedule split + salesman email fan-out
**What you asked for:** Both-mode delivery (full workbook to typed emails/SharePoint;
split files to selected salesmen), emails from Salesmen admin table, company
schedules on the Schedules page, dig the Friday “success” with no inbox mail.
**What I did:** expose/edit `salesmen.email`; move company wizard onto
`/schedules#company`; wizard delivery opts (`email_to_salesmen` /
`split_by_salesman` / `email_salesman_keys` in params JSON); `ScheduleRunner`
fan-out. Missing salesman email skips that split without failing the run.
**Friday dig:** `/test` used SMTP only; Azure App Settings have Graph
(`GRAPH_*`, `EMAIL_FROM_ADDRESS`) but **no** `SMTP_HOST`. Empty SMTP → `.eml` +
outbox `ok=True`, `sent_via_smtp=False` — UI looked successful with no inbox
mail. **Fix:** v3 now prefers Graph (same mailbox path as live), falls back to
SMTP, then outbox; `EMAIL_FROM` falls back to `EMAIL_FROM_ADDRESS`.
**Status:** DECIDED — code on `rebuild-reports`; deploy with `deploy.ps1`.

## 2026-07-24 Customer Activity All tab on /test
**What you asked for:** an All tab that joins every salesman, like live.
**What I found:** Azure `/test` was running an SP passthrough builder
(`rpt.usp_customer_activity`) that only emitted per-salesman sheets (Salesman
column on every sheet, no All). Local repo still had the older universe+orders
builder with All — never what prod was serving.
**What I did:** keep the SP path (matches current /test math), add All first
(Salesman column), per-salesman tabs without Salesman, Unassigned last. Synced
orch/params to the dedicated SP. Deployed; RuntimeSuccessful.
**Status:** DECIDED — live on https://reports.achimonline.com/test. Re-run
parity customer_activity to confirm the missing-sheet gap is gone.

## 2026-07-24 Live vs /test parity runner (tools.parity)
**What you asked for:** autonomous compare of live vs `/test` with the same
params and a full difference breakdown; auth via HTTP (cookie / service), not
a browser. Rebuild Test only after math is signed off.
**What I built:** `python -m tools.parity` runs ordered, invoiced, salesman,
customer_activity, number_4 with shared defaults (YTD / both for Number 4),
downloads Excel from each side, writes `.scratch/parity/<stamp>/INDEX.md` plus
per-report diffs (reuses `tests.compare_reports`). Prod auth: paste
`session` + `v3_session` cookies; local: `--auth dev`.
**Status:** DECIDED — tool on `rebuild-reports`. Not a production deploy; run
from your machine against the live site when ready.

## 2026-07-23 Removed Amazon Weekly as a named report
**What you asked for:** wipe Amazon Weekly everywhere — it was only Ordered with
customers 9300/9301, last_7_days, and email.
**What I did:** backed up to `_history_backup/amazon_weekly-removed-2026-07-23/`
(gitignored), then removed the report module, registry entry, live UI card,
v3 backlog entry, help text, email-distribution templates, and dedicated tests.
Ordered still supports `--customer 9300 9301 --period last_7_days --email`
(recipients from `AMAZON_EMAIL_RECIPIENTS`). Azure schedules that still call
`amazon_weekly` must be changed to that Ordered command.
**Status:** DECIDED — code removed on `rebuild-reports`. Not deployed until you say.

## 2026-07-23 Green test app already gone; v3 vs rebuild; prod branch
**What you asked:** delete the green test app, compare v3 vs rebuild, and say
which branch production runs on.
**Green test (`test/`):** Already deleted on `rebuild-reports` (2026-06-11). No
`/test-legacy` or `/v2` mounts remain. This pass only cleaned leftover Docker
refs that still pointed at the deleted tree (`COPY test/requirements.txt`,
`/v2/healthz` healthcheck, `.dockerignore` test paths) plus stale comments.
**Prod branch:** `rebuild-reports` (tip `b0e8034` as of this check). Not
`webapp-cache` (stale tip from early June; still had green `test/` in that
history). Deploy is zip-from-working-tree via `deploy.ps1`, so whatever branch
was checked out when someone last ran deploy is what Azure has — recent hotfixes
and Item Averages land on `rebuild-reports`.
**v3 (`/test`) vs rebuild (`/test-next`):**
- **v3 wins for day-to-day use today** — more reports (ordered, invoiced,
  salesman, number_4, customer activity, last order, item averages), admin/
  roles, SharePoint, dashboard, master schedules, denser test suite.
- **rebuild wins for long-term architecture** — SQL owns report math; app is
  mostly present/group/export; cleaner modules; smaller surface. Not feature-
  complete yet (many reports deferred pending flat-table SPs).
**What I chose:** Keep both mounts. Do not delete v3. Promote rebuild only after
report parity + human number sign-off. Clean Docker leftovers so the deleted
green app can't break image builds.
**Status:** DECIDED on branch cleanup; cutover still needs human sign-off.

## 2026-07-21 New report: Item Averages (admin-only, both apps)
**What you asked for:** a new report on `/test` and `/test-next` using the
Number 4 By Item endpoint, listing every item with past-12-month qty sales,
avg/month, and avg/week. Admins only; company-wide; sales reps must not see it.
**What I built:** report key `item_averages`. Calls
`item_customer_sales_rolling_12` (same AsOfDate + IncludeCurrentMonth=true as
Number 4), rolls item×customer rows up to one row per Item #, then:
Avg/Month = Total Qty ÷ 12, Avg/Week = Total Qty ÷ 52. Columns: Item #, Item
Name, 12-Month Qty, Avg/Month, Avg/Week. No filters in v1.
**Access:** privileged only (admin/developer). Managers and salesmen are denied
even with an explicit allow row. Rebuild hides it from the report list and
schedule picker for non-privileged users; the builder also refuses a scoped
token.
**Status:** DECIDED — code + tests on `rebuild-reports` (D: checkout). Not
deployed until you say so.

## 2026-07-14 Hotfix: salesman-scoped invoiced reports no longer fetch YTD
**Problem:** Avig's custom invoiced run for `MKolko` and 2026-07-13 through
2026-07-14 began fetching invoice headers from 2026-01-01. The live log showed
the first page alone contained 10,000 company-wide rows and the process was at
993 MB RSS. This happened because the runner expanded every Invoiced Report to
the year start for commission calculations, even though a salesman-scoped
report is written as a Shipped Report and deliberately omits the commissions
tab.
**Hotfix deviation:** restarted the app to stop the already-stalled background
thread, then used the hotfix path instead of a full review loop.
**Fix:** salesman-scoped runs now fetch only their selected period; unscoped
Invoiced Reports retain the year-to-date fetch required by their commissions
tab. Added a regression test for the one-day scoped case.
**Verified:** 23 targeted invoiced tests passed; Azure deployment
`14f6cba6-319d-42f3-9e2f-67dfcc79a5bd` reported `RuntimeSuccessful` with one
successful instance and zero failed instances.
**Status:** DEPLOYED. Avig can rerun the report; it should now fetch only the
requested day and finish normally.

## 2026-07-10 Amazon weekly email: --email flag on the Ordered runner
**Problem:** The Amazon Weekly job (Thursday schedule, report_name=amazon_weekly) had
failed on argument parsing since March: the registry maps it to the Ordered runner
with `--email` in default_args, but the Ordered runner never had an `--email` flag.
The failure was silent until June (STARTED with no result row) because argparse's
SystemExit killed the whole runbook before the FAILED line was written.
**What the owner asked for:** the Friday "Weekly 5pm Friday Amazon Ordered" schedule
(ordered + `--customer 9300 9301 --period last_7_days`) should email the file out.
**What I built:** `--email` flag on OrderedReportRunner (same pattern as the salesman
and customer-aging runners). On customer-filtered runs it emails the written file
(or a "no orders" notice) after saving. `--test` reroutes to TEST_EMAIL (split on ';').
Updated the Friday job schedule in Azure to pass `--email`.
**Business-logic call (flag if wrong):** recipients for these customer-filtered
emails are the `Recv_AmazonWeekly` spreadsheet subscribers, falling back to the
`AMAZON_EMAIL_RECIPIENTS` Automation variable. The spreadsheet currently has NO
Recv_AmazonWeekly column, so today the effective recipient is the variable's value:
bgrossman@achimonline.com. Add a Recv_AmazonWeekly column (TRUE per person) or edit
the variable to change who gets it.
**Verified:** live Azure test job (`--email --test --force`) SUCCESS in 32s; report
built (2103 rows), uploaded to SharePoint, email sent via Graph to both TEST_EMAIL
addresses. The Thursday amazon_weekly schedule also parses now (`--email --email`
duplicate is harmless for a store_true flag) -- so BOTH Thursday and Friday will
email; owner may want to drop one.
**Status:** DECIDED -- shipped; Friday schedule updated in Azure.

## 2026-06-23 Rebuild: granular per-phase review round (owner request)
**What I did:** Per the owner's "review each build phase again, more granular, until everything is clean," I split the app into four areas and had a fresh readonly reviewer go through each one (foundation+security, auth+scoping, reporting engine, scheduling+delivery+notifications). Every one came back NOT CLEAN with real findings. Fixed all blockers and the worthwhile clean-code ("ponytail") items:
- **(blocking, security)** prod would boot with a weak/known `FLASK_SECRET` -> now requires a real secret of at least 16 chars in prod, refuses to boot otherwise.
- **(blocking, security)** the background-leader file lock misread a "can't create the lock file" error as "someone else holds it" -> now those are two different paths (can't create -> assume leader and log; lock held -> follower).
- **(blocking, security)** `allowed_salesmen()` treated a blank/missing scope token as "see everything." For a worker reading a stored job that's the opposite of safe -> now only the explicit token `"all"` means everything; blank/`sm:` with no numbers/garbage all REFUSE (raise) instead of falling open.
- **(blocking, security)** spreadsheet **header** cells weren't run through the formula-injection guard the data cells already used, and a leading newline wasn't treated as a formula lead-in -> headers are guarded now and `\n` was added to the lead-in list.
- **(blocking, data)** raw client filter JSON could carry `NaN`/`Infinity` (Python accepts them, real JSON doesn't), which would later poison the cached snapshot and the browser parse -> the run endpoint now rejects non-finite filter values up front, and the cache writer refuses to serialize them too.
- **(blocking, correctness)** a manual "Run now" was stamping "ran today," which could eat that day's real scheduled slot -> the once-a-day stamp is owned only by the poller (when it queues) and the Shabbos-skip path, never by the run itself.
- **(blocking, correctness)** if a Shabbos catch-up was owed AND the normal cadence came due in the same tick, the report could go out twice -> queuing the normal run now clears the owed catch-up in the same step.
- **(blocking, correctness)** a timed-out/cancelled delivery could be miscounted as a real failure and fire a false "your schedule failed" alert -> a cancellation now returns a distinct "stopped" signal that isn't counted as a failure.
- **(ponytail)** centralized one `normalize_email()` helper (three copies removed); de-duplicated the two create-schedule routes into one `_save_schedule()` and the schedule-table actions into one `_schedule_actions.html` partial; pulled the runner's API-timeout math and the Excel sheet-title cap into named constants; renamed a batch of vague locals (`result`, `data`, `raw`, `out`, `s`, `cfg`) to say what they hold. Added regression tests for the manual-run slot and the catch-up/normal collision.
**Litestream** stays gated until cutover.
**Status:** DECIDED -- all blockers across the four area reviews fixed, 68 tests pass.

## 2026-06-23 Rebuild: second granular review round (re-verify, until clean)
**What I did:** Re-ran the four area reviewers (fresh, readonly) on the fixed code. Each re-verified the prior fixes were correct and found a few more things; fixed them all:
- **(blocking, security)** `allowed_salesmen()` stripped whitespace before checking the "all" token, so a tampered `" all "` would have read as unrestricted -> now it matches the exact token `"all"` with no strip; anything padded or otherwise off REFUSES. Added that case to the fail-closed test.
- **(blocking, correctness/data-loss)** the Shabbos catch-up flag was cleared at the START of a run, so if that catch-up run was then cancelled/timed out, the owed send was silently dropped (poller wouldn't retry it) -> the flag is now cleared only once the run reaches a settled outcome (sent, partly sent, fully failed, or "nobody to send to"); a cancelled/stopped run leaves the flag set so the poller retries next tick. Added a regression test.
- **(small)** also added an early "is the job still running?" check right before building the (possibly large) Excel workbook, so a cancelled catch-up doesn't waste time building a file it will never send (the existing post-build gate before the actual email is unchanged and is what guarantees we don't send after cancellation).
- **(ponytail)** finished centralizing email handling: one `normalize_email()` used in the auth/session/MSAL paths too (no more inline `.strip().lower()`), and one shared `dedupe_emails()` replacing the two copy-paste recipient-cleaners. One shared `salesman_scope_token()` so the security-sensitive scope-token format has a single speller. Removed the genuinely-dead `ROLE_ADMIN` role (it was never assigned anywhere -- privilege comes from the configured developer-email list; "admin" stays as UI wording only). Renamed the last vague locals/loop vars (`s`, `out`, `raw`) in params/export/cadence/sabbath/routes and the schedule templates.
**Why remove ROLE_ADMIN (plain English):** the code had three role names but the sign-in only ever assigns "developer" or "user" -- nobody is ever "admin." A name that can never happen is just confusing, so it's gone. Who's privileged didn't change: it's still whoever is on the developer-email list.
**Status:** DECIDED -- second round's blockers fixed, 69 tests pass; re-review queued to confirm clean.

## 2026-06-23 Rebuild: reschedule-after-Shabbos + failure alerts (owner request)
**What I built (two things the owner asked for):**
1. **Catch-up after Shabbos.** A send skipped for Shabbos/Yom Tov is no longer just dropped until the cadence comes around again. The skip now flags the schedule (`catch_up_pending`), and the poller fires it as a one-off catch-up the moment Shabbos is over (it re-checks Hebcal and, once it's clear, queues the run with its own dedup key so it isn't blocked by "already ran today"). So a Saturday-morning send goes out Saturday night instead of waiting a week.
2. **Failure alerts.** When a whole scheduled run fails (every delivery failed -- e.g. the data server was down), the schedule's owner gets an immediate plain-English email. For a **private (self) schedule** the owner also gets an in-app message the next time they open the app, with a **"Run now"** button (and "Dismiss"). "Run now" queues a manual run that ignores the Shabbos skip (they asked for it on purpose).
**New pieces:** `notifications` table + repository (a tiny per-person inbox); `schedules.catch_up_pending` column; `EmailService.send_failure_notice()`; `run-now` and `dismiss` routes; a notification banner in the base layout; a context processor that shows a signed-in person their unread messages on every page (defensive -- never breaks a page). 8 new tests (66 total pass).
**Judgment calls (decided as, flag if you disagree):**
- **What I had to decide:** who the failure email goes to. **Options:** always the admin (you), vs. the schedule's owner. **What I chose:** the owner -- which is YOU for master schedules (you own them) and the user for their own private schedules. **Why:** the person who set a schedule up is the one who needs to know it didn't go out; it matches "email me" for your own schedules without spamming you with every user's private-schedule hiccup. **NEEDS HUMAN SIGN-OFF if you actually want every failure (including users' private ones) to also email you.**
- **What I had to decide:** what counts as "failed entirely" (vs. partly). **What I chose:** at least one delivery attempted and every attempt failed, and the job wasn't cancelled. A partial failure (some sent, some not) shows in history but doesn't alarm. A cancellation isn't a failure. **Why:** avoids crying wolf.
- **What I had to decide:** should a manual "Run now" still skip Shabbos. **What I chose:** no -- a manual press runs even on Shabbos. **Why:** the person clicked it deliberately; the auto-skip is for unattended sends.
**Status:** DECIDED (one item flagged for sign-off above).

## 2026-06-23 Rebuild Phase Sch: scheduling engine (cadence + Shabbos skip + poller)
**What I built:** The machinery that sends reports on a repeating schedule, generic for any report. A `schedules` table + `SchedulesRepository`; a re-implemented cadence module (daily/weekly/monthly at a wall-clock time, all reasoned in US/Eastern, fires at most once per Eastern day); a Shabbos/Yom Tov check (`sabbath.py`) that re-creates the live app's Hebcal-for-Brooklyn behavior using only the standard library, cached per day and fail-open; a minute poller that queues a durable `schedule.run` job for each due schedule (deduped per schedule+day); and a `schedule.run` handler that turns a schedule into "deliveries" and emails each. Two kinds: **self** (scoped to the owner, to owner+extras) and **master** (one scoped send per salesman number, to the people mapped to that salesman). Refactored the runner to share one `build_report_snapshot()` between the web run and the scheduler so report math/scoping live in ONE place. 15 new tests (48 total pass).
**Three judgment calls I had to make (decided as, flag if you disagree):**
- **What I had to decide:** what "skip Saturdays and holidays, like the live app" should mean here. **Options:** a hardcoded holiday list, vs. the live app's real-time Hebcal check. **What I chose:** the Hebcal check (Shabbos + Yom Tov for Brooklyn, 18-min candles) at fire time, fail-open on any network hiccup. **Why:** it's exactly what the live runbook does, so the two stay in lockstep and I don't have to maintain a date list.
- **What I had to decide:** what happens when a scheduled send fails (data server down) or is skipped for Shabbos. **Options:** keep retrying every minute that day, vs. fire at most once a day and record the outcome. **What I chose:** stamp it as "ran today" after the attempt either way, so it never retries in a loop; a failure shows in the audit log and the owner can re-run by hand. **Why:** avoids a retry storm and matches the once-a-day intent; the live app's auto-reschedule-after-Shabbos is a nicety I left for later.
- **What I had to decide:** a master schedule runs one report per salesman sequentially inside a single worker job capped at 5 minutes. **What I chose:** leave it sequential for now and note the cap. **Why:** modest master schedules are fine; a very wide one (many salesmen) could hit the cap — call it out so we size it before turning one on.
**Not yet (by design):** no real schedules seeded.
**Status:** DECIDED.

## 2026-06-23 Rebuild Phase UI: schedule management screens + review
**What I built:** The pages to run the engine above. "My schedules" (any signed-in person): create a self-schedule for a report, see/pause/resume/delete your own, plus a create form (report, tab, date range, daily/weekly/monthly at a time, extra recipients, skip-Shabbos toggle). "Master schedules" (admins only): the same but split-by-salesman with a salesman-number list. A "Schedule history" page shows what actually went out (your own; admins see everyone). One shared form partial, a tiny vanilla-JS file to show the right cadence fields and filter the tab list to the chosen report, flash messages added to the base layout. CSRF on every state-changing POST. 56 tests pass.
**Review:** readonly gpt-5.5-extra-high (agent f8cf270d) on the combined scheduling + UI diff. It cleared the data-scoping (master sends are correctly locked to one salesman; self sends to the owner's scope) and CSRF/escaping. Fixed its two BLOCKING items and three smaller ones:
- **(blocking) interactive-run cancellation** had moved to after tab-building in the runner refactor -> restored the original checkpoint by passing a `cancelled` check into the shared `build_report_snapshot()` (so a cancelled run still stops before the heavy build). 
- **(blocking) a schedule could re-fire all day** if its job timed out or errored before the "ran today" stamp -> the poller now stamps `last_run_at` the moment the durable job is queued (a crash still drains the queued job, so we don't lose the send and don't double-send).
- (smaller) master schedules can only be managed by a *current* admin, not the stored owner; the Shabbos check now fails open even on a malformed-but-successful Hebcal response; and each delivery writes its own `schedule.run` history line so successes show up, not just skips/failures. Added regression tests for the once-a-day guard, the master-manage rule, and the fail-open path.
**Status:** DECIDED -- scheduling phase (engine + UI) done, committing.

## 2026-06-23 Rebuild full-app multi-pass review (until clean)
**What I did:** Ran repeated readonly full-app reviews (gpt-5.5-extra-high) until one came back with no blocking issues, per the owner's instruction. Three passes:
- **Pass 1** (agent 75b68436): found 2 blockers -> (a) a master schedule kept running even if its owner lost admin rights; (b) a timed-out/cancelled schedule job could keep emailing from a thread the worker had abandoned. Fixed both (re-check owner privilege at send time; cooperative "is the job still running?" gate before each delivery and before each send). Added regression tests.
- **Pass 2** (same agent): verified both fixes correct and complete -> CLEAN.
- **Pass 3** (fresh agent 70bdf1fd, no prior context): found 1 blocker -> the workbook was being built inside the email call's arguments, AFTER the "still running" gate, so a timeout during the (possibly slow) Excel build could still send. Fixed by building the workbook first, then gating, then sending. Also acted on its non-blocking note that multiple gunicorn workers would each start a poller: now exactly ONE process runs the worker + schedule poller, elected with an exclusive OS file lock (mirrors the live app's and v3's existing background-leader pattern; fails open to leader on Windows/dev).
**Why the leader lock matters (plain English):** on the server, the web app can run as several copies of the same process at once. Without the lock, each copy would start its own schedule checker, and a schedule could get sent more than once. The lock means only the first copy to grab it does the background work; the rest skip it.
- **Pass 4** (agent 70bdf1fd, re-verify): both pass-3 fixes confirmed correct, full re-sweep found no remaining blocking issues -> CLEAN.
**Outcome:** Two independent review lineages both end CLEAN (no blocking security/correctness/data-loss issues). 58 tests pass. Remaining items are all accepted/non-blocking (Litestream gating until cutover, viewer.js could later be split, the documented once-a-day master tradeoff).
**Status:** DECIDED -- full app reviewed clean on the branch. Deploy to /test-next is owner-timed (per the cutover rule), not done here.

---

## 2026-06-18 Move v3's precious.db off the /home SMB share onto local disk (fix the stalled job queue)
**What I had to decide:** v3 report jobs were getting stuck "queued" forever -- the background worker never picked them up, so no call ever reached the Reporting API (the DBA confirmed he saw zero calls). Root cause: `precious.db` (users, roles, schedules, jobs) lives at `/home/site/v3data/precious.db`, and on Azure App Service `/home` is an Azure Files **SMB share**. SQLite's WAL mode coordinates processes through a shared-memory index (the `-shm` file) that SMB can't share across processes, so the worker process literally couldn't see the rows the web process had written. I needed to get the DB onto local disk (where WAL works across processes) WITHOUT losing the users/roles/schedules already in it, and without taking down the LIVE app that shares the same process.
**Options I considered:** (a) Interim: switch SQLite to a rollback journal (TRUNCATE) so it works over SMB. **Tried it, it broke the app** -- you can't flip a live DB out of WAL without an exclusive lock, every query started failing with "database is locked", HTTP 500s everywhere; reverted immediately. It also would have disabled Litestream (which requires WAL). (b) Proper fix: move `precious.db` + `cache.db` to local disk (`/tmp/v3data/`), seed the local DB once from the current `/home` copy, and keep Litestream replicating it to Blob for durability. (c) Move to Postgres -- too big a change for tonight.
**What I chose:** Option (b). `startup.sh` now does a one-time seed: on the first boot after the move, it copies the current `/home` precious.db to the new local path using SQLite's online-backup (a consistent snapshot even mid-WAL), drops a marker on the persistent `/home` share so it only ever runs once, and also keeps a dated `precious.premigrate.*.db` safety copy on `/home`. After that, normal cold starts restore the CURRENT data from the Litestream Blob replica. `cache.db` is disposable so it just starts empty and rebuilds. App settings `PRECIOUS_DB_PATH`/`CACHE_DB_PATH` point at `/tmp/v3data/...`; the leftover `SQLITE_JOURNAL_MODE` knob (from the failed interim attempt) is removed from both the code and the app settings.
**Why:** Local disk is shared between the gunicorn web workers and the job worker (same container), so WAL's cross-process visibility works and the worker can finally see and run queued jobs. The `/home` file is never modified -- the app just stops pointing at it -- so it stays as a frozen, complete backup. If anything looks wrong after cutover I point `PRECIOUS_DB_PATH` back at `/home` and lose nothing. Litestream still runs in WAL (required) and now replicates the local file. This is the rule-5 design the project always intended; the DB was on `/home` by accident because the default path resolves under the working directory, which is itself on `/home`.
**Status:** DECIDED + VERIFIED. Cutover done at 18:01 UTC: logs show `startup: seeded precious.db users=12 jobs=232` (data intact), Litestream took a fresh snapshot of `/tmp/v3data/precious.db` and is replicating to Blob, and the job worker's poller went from failing on EVERY cycle ("unable to open database file") to zero errors. Confirmed the cold-restart path too: a later container with `/tmp` wiped correctly skipped the one-time seed (marker present) and Litestream RESTORED the DB from Blob (same snapshot size, so data is whole). Also hardened `config.validate()` to refuse to boot in prod if precious/cache ever points back at the `/home` SMB share (the latent gap `_is_unc` missed), with tests. Removed the obsolete `SQLITE_JOURNAL_MODE` app setting. The old `/home/site/v3data/precious.db` was left untouched as a frozen rollback; `startup.sh` also wrote a dated `precious.premigrate.*.db` copy. NOTE: separately, the owner/DBA confirmed the missing Feb/Mar data is an UPSTREAM stored-procedure problem, not this app.

## 2026-06-14 Fetch big v3 reports one month at a time (stop the API timeouts)
**What I had to decide:** How to stop large v3 reports (YTD Ordered, ~488K order lines) from failing. They ask the on-prem Reporting API for a whole year in one request; on a busy on-prem SQL box that single query runs past the 5-minute timeout and returns nothing (all-or-nothing). The owner: "why is this failing so badly? is there a way to chunk the request to make sure it goes through?"
**Options I considered:** (a) raise the timeout (same failure, longer wait, more load on the on-prem box), (b) split the request by date into month-sized pieces, (c) split by customer into batches, (d) bigger on-prem SQL box.
**What I chose:** Option (b). Big date-window pulls of the `salesline_release` stored procedure are now fetched one calendar month at a time and stitched back together. Applied to the three biggest pulls: Ordered (any bounded period), Customer Activity, and the dashboard all-orders refresh. Open-ended/all_time Ordered runs stay a single call (that path relies on the SP's own default window). New `month_chunks()` helper in `report_engine/dates.py`; new `_facts_chunked()` in `web/reporting/report_service.py`.
**Why:** The owner's own evidence ("yesterday returns fine, last month/YTD hangs") points at date/size as the bottleneck. Each month (~40K rows) returns well inside the timeout. No numbers change: each chunk uses the same day boundaries (00:00:00 -> 23:59:59) every daily report already uses, and contiguous months have no gap/overlap, so the stitched result is the same rows as one big call. Verified with a parity test (stitched == single full-window call) + month_chunks coverage tests; all 310 v3 tests pass. Cross-model review found no blockers. Caveat: if the on-prem API is *fully* wedged (every call hanging, the current state), it still needs a restart — chunking can't extract data from a server answering nothing. Raw "Full Data" row order is now grouped month-by-month; totals/numbers identical (logged for sign-off in v3/REVIEW-LOG.md).
**Status:** DECIDED

## 2026-06-11 Retired the legacy test app (test/)
**What I had to decide:** The owner ordered the old v2 sandbox app removed: "get rid of the legacy test app... cancel all jobs for it, wipe it."
**Options I considered:** (a) just unmount it but keep the code, (b) delete the code and its background jobs entirely.
**What I chose:** Full removal. Deleted `test/` (80 files), removed the `/test-legacy` and `/v2` mounts from `wsgi.py`, dropped its pip packages (SQLAlchemy, pyodbc) from requirements, and wiped its data files on the server (`/home/data/v2_app.db`, `/home/data/v2_critical_backup.json`). Its background "mirror refresh" jobs ran inside the web process, so removing the app removes the jobs -- nothing to cancel in Azure.
**Why:** Nobody uses it, and its mirror refresh was hammering the on-prem Reporting API with 13 back-to-back ~150-200K-row pulls (nightly + every 4 hours + after restarts) -- the prime suspect in this week's API hangs, and a contributor to tonight's out-of-memory crash. v3 replaced it. Note: this supersedes the earlier v3-rebuild directive to keep the old test app viewable at /test-legacy. If v3 now fails to boot, /test returns 404 instead of falling back to the old app (the boot error still gets dumped to /home/LogFiles/v3_boot_error.log).
**Status:** DECIDED (owner instruction)

Decisions made during autonomous operation or at ambiguous points during development. See `autonomous-mode.mdc` for the format.

---

## 2026-06-23 Rebuild Phase E: email sending built + reviewed
**What I built:** The email layer. A Graph mailer (`rebuild/delivery/graph_mail.py`) sends app-only mail through Microsoft Graph the same way the live distribution does -- no mailbox password, built on the standard library + msal. A composition/service layer (`report_email.py`) turns a finished tab into an email: short body with an "open in the app" link, the Excel attached, and a link-only fallback when the workbook is too big (>= 2.5 MB raw, safely under Graph's ~4 MB request limit after base64). Always sends FROM `config.mail_from` (reports@) with Reply-To set to the person. Every attempt (sent, failed, refused) is written to the audit log. The only trigger so far is an "Email to me" button that sends ONLY to the signed-in person (to themselves) -- the safe test path; real recipients/schedules come in the scheduling phase. Settings added: `REBUILD_MAIL_FROM`, `REBUILD_PUBLIC_BASE_URL` (both blank = email simply off). 33 tests pass.
**Review:** readonly gpt-5.5-extra-high (agent 86ce3f31). Confirmed recipients come only from the signed-in identity, `_read_result` enforces ownership+scope before sending, CSRF is enforced, and the body is HTML-escaped. Fixed its three BLOCKING items: (1) unconfigured/refused sends are now audited too (single failure path); (2) any token/network error becomes a clean "failed" instead of a 500; (3) we refuse to send a link-only email when no app link can be built, rather than sending a useless "use the link above" with no link. Tightened the attach threshold to 2.5 MB and `>=`.
**One judgment call (NEEDS-HUMAN, decided as):** Graph sends with `saveToSentItems=true`, so a copy lands in the reports@ Sent Items. I kept that on -- it gives a real sent record and matches the "send as reports@" model. Say the word if you'd rather it not retain copies there.
**Not yet (by design):** no real recipient lists or schedules seeded; live test-send needs the deploy + Mail.Send app permission + REBUILD_MAIL_FROM set.
**Status:** DECIDED -- email layer done, committing.

---

## 2026-06-23 Rebuild Phase S: per-salesman scoping built + reviewed
**What I built:** Real per-salesman data scoping (was stubbed -- everyone saw all). New `user_salesmen` mapping table (admin-managed), `UserScopeRepository`, scope resolved in the single `resolve_access()` (privileged=all, mapped=own numbers, unmapped=denied). The salesman SP param is forced to the person's numbers AND rows are post-filtered as a backstop; scope is folded into the cache key. Admin-only page at `/admin/scope` to manage the map. 23 tests pass.
**Review:** readonly gpt-5.5-extra-high review (agent 8a00a5a7). Fixed its one BLOCKING item (the run summary used the pre-filter row count, which could leak the full total to a scoped user -> now counts post-filter rows) and its NON-BLOCKING worker item (the worker now refuses a tampered/corrupt scope token instead of falling back to "all"). Added regression tests for both.
**Two judgment calls (NEEDS-HUMAN, decided as):**
  1. **Salesman number format = exact match.** Numbers are matched as exact trimmed strings, so `010` and `10` are different. I chose exact match (no guessing/zero-stripping) and told admins on the page to enter numbers exactly as they appear in the report's Salesman column. Flag if your data uses inconsistent leading zeros.
  2. **"Privileged" = the developer list for now.** The role resolver only assigns `developer` (from REBUILD_DEVELOPER_EMAILS) or `user`; there's no separate "admin" role source yet. Privileged behavior (see-all + admin pages) currently means being on the developer list. Fine while it's just you; we can add a real admin role source later.
**Status:** DECIDED -- scoping done, committing/deploying.

---

## 2026-06-23 Rebuild M11 unblocked: email + scheduling decisions (owner answered)
**What I had to decide:** The owner answered the M11 questions, which set the design for emailing and scheduling reports.
**What the owner chose (and what I'm building to):**
  1. **Safety gate:** build the full email/scheduling machinery, but test-send ONLY to the owner. Do NOT seed real master schedules or recipient lists yet.
  2. **Send method:** reuse the existing Microsoft Graph app mail the live distribution uses (`core/email_report.py` pattern; app-only Mail.Send). No new mailbox or secret.
  3. **Sender:** ALWAYS send From `reports@achimonline.com`, with **Reply-To set to the person who created the schedule**. (The owner picked this over "send as the user" -- it's safer: the app only ever sends as `reports@`, so we don't need the broad "send as any user" permission, and replies still reach the creator.) I'll also recommend an Exchange application-access-policy limiting the app to `reports@`.
  4. **Recipients / scoping:** per-salesman + per-user. A user's login maps to their salesman number(s) via an **admin-managed mapping table** (the owner manages it). Master schedules (admin) split a report by salesman and send each their own scoped copy; a user's own schedule is auto-scoped to them. Privileged users see all; a mapped user sees only their salesmen; an unmapped non-privileged user is denied (they'd see nothing anyway -- this app is sales reports).
  5. **Cadence:** fully customizable like the live/v3 app; skip Saturdays and holidays; built generic so any future report can be scheduled.
  6. **Attachment:** both the Excel file and a link to open it in the app; fall back to link-only if the Excel is too big for a single Graph send (~3-4 MB).
**Build order (owner approved):** (S) data scoping -> (E) email send service (test to owner only) -> (Sch) scheduling engine -> (UI) schedule management for users + admin.
**Why:** Scoping is the foundation for per-salesman delivery and is also a security non-negotiable that was still stubbed; it has to land first. Reply-To-not-send-as keeps the mail permission minimal. Numbers remain PROVISIONAL until owner sign-off, which is exactly why nothing real is scheduled yet.
**Status:** DECIDED -- building.

---

## 2026-06-22 Rebuild M11: email + scheduling -- NOT built, needs your sign-off (autonomous)
**What I had to decide:** The inventory includes emailing and scheduling reports. Whether to build automated email distribution now, while running unattended.
**Why I stopped instead of building it:** This is a high-risk action under the autonomous rules (business logic + could send wrong data to people). The invoiced numbers are still PROVISIONAL -- you haven't signed off that they match LIVE (and we know the DBA's source data is currently wrong). Wiring up automatic emails now could blast not-yet-correct numbers to executives on a schedule. It also needs decisions only you can make.
**What I need from you to build it:**
  1. Sign-off that invoiced numbers are correct (or an explicit "send anyway, it's a test list").
  2. Send method: reuse the existing Microsoft Graph mail the live "CEO Daily Reports" uses (same app credentials / Mail.Send), or something else?
  3. Who sends (which mailbox/identity) and who receives (fixed list, per-user, per-salesman scope)?
  4. Schedule semantics: which reports, what cadence, what timezone, skip weekends/holidays (the live app has Shabbos-skip logic)?
  5. What gets attached -- the Excel export we just built, a link to the viewer, or both?
**Status:** BLOCKED (waiting on owner)

---

## 2026-06-22 Rebuild M12: audit-log viewer built; worker/Litestream/paging deferred (autonomous)
**What I had to decide:** The ops-hardening inventory had several items: an admin audit-log viewer, a separate worker process, Litestream backup of the rebuild's database, big-result server paging / Blob spill, and an admin UI for report config. What's safe to do unattended.
**What I chose:** Built only the admin-only audit-log viewer (`/test-next/admin/audit`, gated by `require_privileged`) -- read-only, self-contained, no production-startup change. It lists recent runs/exports/deliveries from the audit table the job handlers already write. Deferred the rest:
  - **Separate worker process & Litestream for the rebuild DB:** these change the SHARED production container's startup (the same container runs the LIVE app). That's a breaking-change risk I won't take unattended. The in-process worker is healthy on the single B1; Litestream already protects the live DB. To be done deliberately with you.
  - **Big-result server paging / Blob spill:** only needed for very large reports; invoiced is bounded by the row guard. Not needed yet.
  - **Admin UI for report config/manifest:** real CRUD with its own review; the manifest is code-defined and stable for now.
**Why:** Autonomous rules say stop before breaking changes and production-startup risk. The audit viewer is pure upside with no such risk; the rest deserves a deliberate, reviewed session.
**Status:** DECIDED (audit viewer); DEFERRED (worker/Litestream/paging/admin-CRUD)

---

## 2026-06-22 Rebuild M10: in-table filtering, grouping, show/hide columns (autonomous)
**What I had to decide:** The owner's inventory wanted filtering and grouping by columns, plus show/hide/reorder. How much to build now, and how, given the app is meant to be a thin presentation layer.
**Options I considered:** (a) Build server-side filtering/grouping endpoints (more code, another path that could drift from the engine). (b) Use Tabulator's built-in, client-side features over the rows we already shipped: per-column filter boxes, a group-by selector, a show/hide-columns checklist, drag-to-move and drag-to-resize. For totals: keep the hand-made total row, or switch to Tabulator's own bottom/group calc rows. (c) Saved layout presets (column order/widths/visibility per user) -- needs a table in precious.db plus endpoints and tests.
**What I chose:** Option (b) for filtering/grouping/columns -- all client-side, no backend, because the data is already on screen and grouping/filtering is explicitly view-only per the owner's directive. Switched table totals from a fake appended "TOTAL" row to Tabulator's native bottom + per-group calc rows, which also fixed a latent bug where the fake total row would have been swept into groups and filters. Deferred saved presets (option c) to a later milestone since it needs durable per-user storage; logged here so it isn't forgotten.
**Why:** Keeps the app thin and the report math single-source (the engine still owns the numbers; the browser only re-presents them). Native calc rows behave correctly under grouping/filtering, unlike a data row pretending to be a total. Presets are real work with a storage decision, better done deliberately than rushed.
**Status:** DECIDED (saved presets: DEFERRED)

---

## 2026-06-22 Rebuild M9: exports (CSV + Excel) from the snapshot (autonomous)
**What I had to decide:** The owner's inventory wanted exports. How to produce CSV and Excel without bolting on weight, and what the file should contain.
**Options I considered:** (a) Rebuild the export in Excel like the old app does (heavy, and the rebuild explicitly does NOT port the old Excel builders). (b) Export straight from the tab payload the engine already built (columns + rows + total), so the file is exactly what's on screen. For the format: CSV via the standard library; Excel needs a package -- `openpyxl` is already installed for the live app, so no new dependency (`pandas` would be overkill here).
**What I chose:** Option (b). One small `export.py`: `to_csv` (stdlib `csv`, UTF-8 BOM so Excel opens it cleanly) and `to_xlsx` (openpyxl, with money/percent/int number formats and a bold header + total row). A new GET route `/api/reports/<key>/export/<tab>?fmt=csv|xlsx` reads the snapshot through the same ownership-checked path as viewing, logs a `report.export` audit row, and streams the file. Two toolbar buttons download the active tab. The commission card tab exports its flat columns/rows (built alongside the cards for exactly this).
**Why:** Exporting the already-built tab guarantees the download matches the screen and reuses the single source of report math -- no second code path that could drift. Stdlib + an already-present dependency keeps it light. It's a GET (no state change) so it needs no CSRF, and the path-scoped session cookie still authorizes it.
**Status:** DECIDED

---

## 2026-06-22 Rebuild M8: fit the report table to the viewport (autonomous)
**What I had to decide:** The owner reported the table ran off the bottom of the screen -- you had to scroll the whole page to reach the bottom row and the horizontal scrollbar. How to make it fit.
**Options I considered:** (a) A fixed `calc(100vh - 120px)` guess (fragile: breaks if the header/filters change height). (b) Measure the table's real position and size it to the space left, recomputing on window resize and when the filters panel collapses.
**What I chose:** Option (b). The table height is computed from its on-screen top to the bottom of the window, so it always fits and scrolls inside its own box (both scrollbars reachable) instead of pushing the page taller. Added a "Hide/Show filters" toggle; collapsing the filters gives the table more room (recomputed on toggle). Also added the classic `min-height: 0` flex fix so the table box can shrink.
**Why:** Measuring beats guessing -- it survives header/filter size changes and directly gives the "bigger table when filters are collapsed" behavior the owner asked for earlier.
**Status:** DECIDED

---

## 2026-06-22 Rebuild M7: card commissions tab + viewer tab fixes (autonomous)
**What I had to decide:** The owner asked for a second Commissions tab in the card format (like the old v3 app) to compare against the new flat pivot, plus fixes for two viewer complaints: switching tabs took several seconds and showed the OLD tab until the new one arrived, and the Commissions tab "didn't load at all." Then to continue the build autonomously.
**Options I considered:** (a) Duplicate the commission math for the card view. (b) Extract the per-salesman/per-month math once and feed both the pivot and the cards from it. For the slowness: (a) cache the parsed snapshot server-side, (b) fetch each tab once and cache it in the browser (like v3, which was fast because it was client-side), prefetching the others quietly.
**What I chose:** Extracted one shared helper (`_salesman_months`) that both commission tabs build from, so the two views can never disagree (a test asserts their YTD totals match). Added a `commission_cards` transform that also keeps a flat columns/rows so exports still work later. The engine now passes a transform's whole payload through (so new layouts need no engine change), and `result_tab` returns the whole tab. Browser side: each tab is fetched once and cached, the rest are prefetched in the background, a click clears the table and shows a "Loading…" note immediately, a request token ignores a stale response, and a failed tab now shows an error instead of silently leaving the old tab up (which is what made Commissions look like it "didn't load").
**Why:** The owner's own reference (v3) was fast because tabs were client-side; caching + prefetch matches that without abandoning the lazy-first-paint design. The shared helper follows the rule-of-2 (two real call sites now). Surfacing tab errors turns an invisible failure into something we (and the owner) can see. Commission numbers stay PROVISIONAL until owner sign-off.
**Status:** DECIDED

---

<!-- Entries are added below as work progresses. Each entry follows this format:

## [Date] [Short description]
**What I had to decide:** ...
**Options I considered:** ...
**What I chose:** ...
**Why:** ...
**Status:** DECIDED / BLOCKED

-->

## [2026-06-10] CEO Daily Reports email distribution failing since June 3

**What I had to decide:** Why the "CEO Daily Reports" email distribution failed every day since June 3, and how to fix it.

**What I found:** The production database showed every attempt failing with "file not found" for the Ordered and Invoiced report files -- but the files were sitting right there on SharePoint. The app's logs revealed the real error: the Graph API call that looks up the SharePoint *site* was returning 404. The `SP_SITE_URL` setting on the Azure web app pointed to `https://achimonline.sharepoint.com/sites/AchimImportingCoIncTeamSite-D365FO`, a site that does not exist (confirmed by asking Graph directly). The reports actually live on the root site `https://achimonline.sharepoint.com`, under the "D365 F&O" folder in its Documents library. The code swallowed the site-lookup error and reported it as a missing file, which is why the log was misleading. The same wrong-site problem also broke the run_log.csv download the dashboard uses (it had its own hardcoded site name, also wrong) -- which is why Saturday "Shabbos skip" detection failed and the distribution retried in a loop on Saturdays too.

**Options I considered:** (1) Point SP_SITE_URL at the root SharePoint site, matching the local .env that works. (2) Hunt down the "correct" team site URL -- but the file paths all assume the root site's library, so this would need path changes everywhere.

**What I chose:** Option 1: set `SP_SITE_URL=https://achimonline.sharepoint.com` on the Azure web app. Also made two small code fixes: the run_log.csv download now goes through the same shared SharePoint service (instead of its own hardcoded site name), and a dead SP_SITE_URL now raises a clear error naming the setting instead of pretending the file is missing. Added a regression test for that error.

**Why:** Smallest change that restores the working configuration. The local .env already proved the root-site URL resolves every report path correctly.

**Status:** DECIDED
