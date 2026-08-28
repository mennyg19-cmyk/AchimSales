# Decision Log

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


Older entries: DECISION-LOG-ARCHIVE.md
