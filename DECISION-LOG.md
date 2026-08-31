# Decision Log

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

## Still BLOCKED (owner, not Phase 4)
- GitHub Environment `production` required reviewers (Environment does not exist yet; only `github-pages`).
- Access-log review of the cookie-file window.
- Production merge/deploy; live Litestream empty-disk drill.
- `LIVE_DB_PATH` / `flask import-live-users` until import evidence exists.

Q1–Q11 and Phase 0–3 decisions: DECISION-LOG-ARCHIVE.md
