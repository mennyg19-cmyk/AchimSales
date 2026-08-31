# Decision Log

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
