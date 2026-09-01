# Decision Log

## 2026-09-01 Phase 9: how to prove report parity
**What I had to decide:** Live Excel vs Production, copy archive `tools/parity` into this repo, or structural + fixture evidence against the isolated archive.
**Options I considered:** (1) Run the old live-vs-`/test` Excel harness (needs cookies and `/test`). (2) Copy `tools/parity` into this branch. (3) Isolated archive `b14d725` + current builders/tests; live SQL/Excel marked BLOCKED until Reporting API/staging.
**What I chose:** (3). Q6 stays retired. Customer Aging stays web BACKLOG. Azure Automation live job list stays owner BLOCKED; repo runbook + `report_registry.json` match the archive.
**Why:** Plan forbids mounting old apps. Local Reporting API is unset. Old harness compared `/test`, which is gone.
**Status:** DECIDED — Phase 9. Live SQL totals and live Automation send list remain BLOCKED.

## 2026-09-01 Phase 8: report.ts cycles stay
**What I had to decide:** Split `report-*.ts` circular imports now, or prove boot order in the running report page.
**Options I considered:** (1) Split the cycle this phase. (2) Keep the cycle; the bundled report page load is the proof.
**What I chose:** (2).
**Why:** The plan allows either. A split is a large risk next to dialog/a11y work. The existing bundle already boots.
**Status:** DECIDED — Phase 8.

## 2026-09-01 Phase 7: close the repo review gate
**What I had to decide:** Whether Loop C nits and trust-boundary observations reopen Phase 7 before closing the repo gate.
**Options I considered:** (1) Fix them now and re-run Loops A/B/C. (2) Close the repo gate at `99ba689`; leave nits/observations recorded; keep the live Azure drill BLOCKED; do not start Phase 8 in this session.
**What I chose:** (2).
**Why:** Loops A/B/C and trust-boundary all PASS with zero blocking findings. Reviewers marked the leftover notes non-blocking. Protocol ships the gate after Loop C unless B/C fixes were huge. The live empty-disk drill is an owner action, not a repo-test fail.
**Status:** DECIDED — Phase 7 repo gate closed. Live Azure empty-disk drill remains BLOCKED.

## 2026-09-01 Phase 7: one-site persistence
**What I had to decide:** Canonical env names, whether `is_beta` flips, which replica startup restores, what counts as DB identity/sentinel, and whether the `/home` `/test` seed stays.
**Options I considered:** (1) Rename Azure in-place to SITE_* only, drop BETA_* now. (2) SITE_* canonical, keep BETA_* aliases; restore only that file; identity = `users` >= 1 plus `app_settings.site_db_role=home` after migrate; drop the `/home` seed; never fall back to `LITESTREAM_AZURE_PATH`. (3) Keep restoring both PRECIOUS_* and BETA_* until the live drill.
**What I chose:** (2). `is_beta=True` stays. Live Azure empty-disk restore drill stays owner BLOCKED.
**Why:** The plan prefers `SITE_PRECIOUS_DB_PATH`. Azure still has BETA_* so dropping the alias would empty the home site. Flipping `is_beta` would switch the cookie and point at the leftover `/test` path. Restoring `PRECIOUS_DB_PATH` from `LITESTREAM_AZURE_PATH` is the obsolete `/test` replica. An empty sqlite would pass `quick_check` and migrate into a blank Production site; requiring at least one `users` row blocks that. Writing a new product table is unnecessary — `app_settings` already exists (0001/0005).
**Status:** DECIDED — Phase 7. Live Azure empty-disk drill remains BLOCKED.

## 2026-08-31 Phase 6: company Send now stays on visibility (Q9)
**What I had to decide:** The Phase 6 plan bullet says require operate/edit permission for company Send now. Q9 already chose the opposite.
**Options I considered:** (1) Tighten `run_master` to `can_edit_master`. (2) Leave Send now on `_require_master_visible` so a view-only manager can still fire it.
**What I chose:** (2). Do not implement that plan bullet.
**Why:** Q9 is DECIDED. Viewing the company list includes the right to kick a send. Toggle/edit stays tighter.
**Status:** DECIDED — Phase 6.

## 2026-08-31 Phase 5: stored full-leg retry after split-only edit
**What I had to decide:** What happens when the operator retries a stored full email leg after the live master schedule drops manager recipients and keeps only salesman splits.
**Options I considered:** (1) Keep requiring live `sched.recipients` (retry fails `No delivery targets`). (2) Fail closed until the operator restores a full target. (3) Still send that stored full target; skip live splits that are not the selected leg.
**What I chose:** (3). First-send with no targets still fails. First-send still requires a live email for listed salesmen.
**Why:** Loop A re-pass 6 F1. I4 is retry of that stored attempt, not of the current target shape.
**Status:** DECIDED — Phase 5 Loop A fix.

## 2026-08-31 Phase 5: last live fan-out key still retries
**What I had to decide:** Whether selected salesman retry still uses fan-out when live keys are empty.
**Options I considered:** (1) Ordinary full-delivery when `_salesman_targets` is empty (silent skip). (2) Fail the retry. (3) Enter fan-out from the selected leg's `salesman_key` and send the stored target.
**What I chose:** (3). First-send with no salesman keys still uses the ordinary full-delivery path.
**Why:** Loop A re-pass 5 F1. Same stored-target retry; an empty live list must not hide the selected leg.
**Status:** DECIDED — Phase 5 Loop A fix.

## 2026-08-31 Phase 5: fan-out retry uses stored salesman address
**What I had to decide:** What happens when the operator retries one salesman split and that salesman's live email is blank or they were dropped from the schedule.
**Options I considered:** (1) Keep requiring a live `get_email` (retry never sends). (2) Fail closed until the salesman record is restored. (3) Send the stored target on that selected leg only.
**What I chose:** (3). First-send still requires a live email for every listed salesman.
**Why:** Loop A re-pass 4 F1. I4 is retry of that stored attempt.
**Status:** DECIDED — Phase 5 Loop A fix.

## 2026-08-31 Phase 5: freeze window and filename on retry
**What I had to decide:** What “Send again” does after the live schedule’s period or filename template changed.
**Options I considered:** (1) Keep hashing the current schedule (silent skip / second folder file). (2) Fail the retry until the operator restores the old schedule. (3) Persist the original window and resolved filename on the leg and retry that attempt.
**What I chose:** (3). Forward migration `0025`. Do not edit `0023` or `0024`.
**Why:** Loop A re-pass 3 F1/F2. I4 is retry of that stored attempt, not of whatever the schedule is now.
**Status:** DECIDED — Phase 5 Loop A fix.

## 2026-08-31 Phase 5: delivery states and Graph unknown
**What I had to decide:** How `pending` maps, what worker death does to in-flight legs, and how an operator reconciles `unknown`.
**Options I considered:** (1) Requeue `schedule.run` when legs are only prepared (double-send risk with a detached child). (2) Keep cancelling those jobs; convert sending email to `unknown`, accepted email/folder to `sent`, prepared to failed-before-send. (3) Leave sending rows until Phase 6.
**What I chose:** (2). Freeze `slot_id` + `slot_day` at enqueue. Build the workbook before any leg is `sending`. Graph timeout after submit is `unknown` (not auto-retried). Connection refused is failed. Operator: `[UNKNOWN]` mail to Settings test emails, in-app notice for admin/developer, History mark-sent or retry that leg. Tokens cache with a 60s refresh skew; one 401 retry. Upload sessions resume from `nextExpectedRanges`. Legs prune at 90 days with no FK to jobs.
**Why:** Q11 + Phase 5 gate. Phase 4 still forbids a second child on a cancelled delivery.
**Status:** DECIDED — Phase 5 implementation.

## 2026-08-31 Phase 4 Loop A: unsafe orphan recovery
**What I had to decide:** What `recover_orphans` does with a `running` `schedule.run` or `report.deliver` after the worker dies.
**Options I considered:** (1) Requeue like report.run (double-send). (2) Cancel and do not retry. (3) Leave `running` until Phase 5 `unknown`.
**What I chose:** (2). Cancel with "Worker died while this delivery was running; not retried." `mark_success` stays guarded to `running`, so a detached child cannot flip it back. Report/export/mirror jobs still requeue under the retry cap. Worker heartbeat is written between child-wait chunks so a healthy long job does not trip prod `/readyz`.
**Why:** Phase 4 expectation 7 and Loop A F1/F2. Phase 5 still owns honest delivery `unknown`.
**Status:** DECIDED — Loop A fix.

## 2026-08-31 Phase 4: HTTP vs worker split
**What I had to decide:** How Gunicorn stays HTTP-only, how dropdowns stay filled without a Gunicorn thread, queue backpressure numbers, and heartbeat stale windows.
**Options I considered:** (1) Keep a lookups thread in each Gunicorn worker. (2) HTTP reads the sqlite customer mirror; the worker cron fills it (`lookups.refresh` when the dashboard UI is off, full `dashboard.refresh` when it is on). (3) Add a process-supervision framework.
**What I chose:** (2). Shell supervisor only (`tools/supervise-web.sh`). One killable child at a time, 45-minute cap, cancel + SIGKILL. Interactive enqueue refuses at 40 queued or when the oldest queued job is older than 20 minutes; `schedule.run` / mirror jobs skip that so exports cannot starve deliveries. Prod `/readyz` is 503 if the worker heartbeat is older than 90s or the scheduler heartbeat is older than 180s. Dev `/readyz` does not require heartbeats.
**Why:** Phase 4 gate forbids ThreadPoolExecutor / scheduler / poller / lookup threads in Flask/Gunicorn. Home site has dashboard refresh off, so a customer-only mirror job is what keeps salesman/customer dropdowns populated. No new framework.
**Status:** DECIDED — Phase 4 implementation.

## Still BLOCKED (owner)
- GitHub Environment `production` required reviewers (Environment does not exist yet; only `github-pages`).
- Access-log review of the cookie-file window.
- Production merge/deploy.
- Live Azure empty-disk Litestream restore drill (Phase 7 live gate).
- `LIVE_DB_PATH` / `flask import-live-users` until import evidence exists.

Q1–Q11 and Phase 0–3 decisions: DECISION-LOG-ARCHIVE.md
