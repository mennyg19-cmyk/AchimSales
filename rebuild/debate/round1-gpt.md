Model: gpt-5.5-extra-high

## Proof of Read
- `FEATURE-INVENTORY.md` has 6 in-scope page route groups and 20 build pages/todos, P1-P20; it also locks the route/API surface and the human sign-off list.
- `BUILD-HISTORY.md` has 50 items, BH1-BH50; the deployment pain is concentrated in BH1-BH8 persistence, BH10-BH19 jobs, BH26-BH28 delivery/result parity, and BH50 diagnostics/API saturation.
- `DEBATE-LOG.md` Round 0 locks the agreed list: Flask/Jinja/TypeScript/Tabulator, server-side grouping, SQL-first row math, DB report config, module split, auth, jobs, audit, CSRF, cutover posture.
- The only open points are OP1 persistence, OP2 result snapshot plus big-table strategy, and OP3 worker process model.

## OP1 Persistence: CONCEDE

I concede the production default should be SQLite plus Litestream for the first cut, with the Postgres off-ramp seams implemented now.

My Postgres argument was correct about reducing restore ceremony and avoiding local-file durability questions, but it overweighted those benefits for this actual deployment. The owner is cost-conscious, the app runs on one B1, concurrency is a few dozen internal users, and SQL Server owns the heavy report math. The app database is durable coordination and configuration data: users, access, jobs, schedules, presets, audit rows, report config. That is not enough load to justify a managed Postgres server as the default cost and ops burden.

The canonical history also changes the weight. BH1-BH8 are not "SQLite is bad"; they are "SQLite on SMB and unclear local-disk restore are bad." The locked prevention in P17/P20 already says local disk only, no `/home` or UNC, Litestream included in deploy, empty-disk restore tested, cache self-heals, migrations are leader-gated, and integrity diagnostics exist. If we actually enforce those gates, SQLite is a reasonable first production choice for one instance.

Cost and ops:

- SQLite plus Litestream uses the B1 and Blob storage already in the plan. Blob cost for this scale should be small.
- Postgres adds a monthly managed database bill, firewall/network/config monitoring, backups to understand, migration drift, and connection management. Those are not free for a self-taught owner maintaining a small internal app.
- The SQLite path does require real ceremony: local-only validation, Litestream startup, restore proof, integrity checks, one-instance discipline. That ceremony is cheaper than Postgres only if it is automated and tested, not handwritten runbook hope.

Failure modes:

- SQLite plus Litestream fails if the DB path silently moves back to SMB, restore does not run on empty local disk, WAL backup lags, or multiple app instances are enabled. So prod boot must fail closed on those conditions.
- Postgres fails differently: network outage, connection exhaustion, service misconfiguration, cost pressure leading to an undersized tier, and an owner needing to debug one more Azure service.

Cutover-to-LIVE impact:

SQLite plus Litestream is acceptable for replacing LIVE if the ship gate includes restore from empty disk, integrity check, cross-process enqueue/claim, and a documented "move to Postgres" trigger. The repository seams from both proposals remain mandatory: Python UTC timestamps, JSON encoded at repository edges, no SQLite-only SQL in services, `JobRepository.claim_next()` isolated, and backend-specific migrations behind one runner.

Agreed answer I can support: production starts on local SQLite plus Litestream, with Postgres as a tested off-ramp, not the default.

## OP2 Result Snapshot and Big Tables: PROPOSE A THIRD OPTION

Use a tiered strategy: store the canonical flat snapshot first, serve all rows/tabs only while the result is below a configured budget, and switch to active-tab/lazy/server-paged responses when it crosses that budget. Store normal snapshots in `cache.db`; spill large snapshots and exports to Azure Blob.

This is the compromise that keeps Claude's YAGNI point for normal internal use while preserving my concern about B1 memory and browser payload size.

I agree with Claude that we should not build a distributed data platform for a few dozen users. Most invoiced runs may be small enough to send the grouped tabs directly. In that case, cache.db is simpler, faster, and cheaper than writing every snapshot to Blob. It also keeps the first user experience simple: run report, receive tabs, interact in Tabulator.

I do not agree that the architecture should assume all tabs' rows can always go to the browser. BH10 is the warning: one large YTD row set OOM'd the worker and crash-looped the container. BH26 says large exports cannot block the browser. BH27 says screen/export/email must share one server view path. On a B1 with 1.75GB RAM, a worst-case 80-100MB JSON payload is not just payload size. It becomes Python rows, serialized JSON, response buffers, browser memory, Tabulator memory, and maybe another export job at the same time. A few concurrent users can turn "manageable" into a recycle.

Concrete shape:

1. Worker runs the SQL Server stored procedure and writes one canonical flat snapshot reference: cache.db for normal size, Blob for large size.
2. Server builds grouped/tab views from that flat snapshot using the same view builder for screen, export, email, and schedule.
3. If `total_flat_rows` and estimated JSON size are under budget, the result endpoint can return all tab rows in one response.
4. If over budget, the result endpoint returns tab metadata, counts, columns, and the active tab's first page. Tab switches fetch that tab. Sorting/filtering for large results is server-side over the snapshot. Exports stream from the same snapshot/view rules.
5. The threshold is config, with a conservative default such as row count and estimated serialized bytes. Exact numbers should come from the memory-budget test, not guessing.

Cost and ops:

- Blob is already needed for Litestream backups and exported files, so using it for large report snapshots does not add a new service.
- The normal path stays cheap and local. The large path pays small Blob storage/transaction cost only when needed.
- The ops burden is one extra storage abstraction for snapshots, but it buys a clear backstop against OOM and browser overload.

Failure modes:

- All-tabs-to-browser can fail by OOM, browser freeze, slow downloads, or stale cached results leaking if auth re-checks are skipped.
- Blob-backed large snapshots can fail by missing Blob credentials, expired snapshot retention, or cleanup bugs. Those are easier to test with upload/read/delete and retention tests than recovering from container OOM loops.
- Server paging can fail by making screen/export diverge if it has separate logic. The locked answer prevents that: one `ReportViewBuilder` owns view rules for screen/export/email/schedule.

Cutover-to-LIVE impact:

The tiered plan is cutover-safe because LIVE replacement cannot depend on "the expected row count is probably fine." It also avoids overbuilding for the normal case. The user gets the simple full-tab payload when safe; the app uses large-result mode only when the budget says it must.

Agreed answer I propose: canonical flat snapshot, normal results in cache.db with all tabs returned, large results spilled to Blob and served active-tab/lazy/server-paged, exports always streamed from the same view builder.

## OP3 Worker Process Model: DEFEND

I defend a separate worker entrypoint/process for production, with one worker on the same B1 by default. That can be a continuous WebJob where the App Service setup supports it, or an equivalent separately started worker command, but it should not be hidden inside Flask request-worker startup as the main production shape.

The key distinction is not "buy another server." I am not arguing for a second App Service instance. I am arguing that HTTP serving and job draining should be separate lifecycles even if they share the same B1 CPU and memory.

Deployment reality matters here. One B1 is small. That makes isolation more important, not less. BH5 says cold-start work in `wsgi.py` caused crash loops. BH10 says a large job OOM'd the worker and took the live app down. BH17 says multiple web workers each started scheduler/email loops. BH18 says a hung Reporting API call made the worker look alive but blocked. Those are exactly the failures that get harder to reason about when the worker is a daemon thread inside the web process.

Cost and ops:

- A separate worker process on the same App Service plan should not require a second B1. It does consume the same limited CPU/RAM, so default concurrency must be 1 and queue backpressure must be real.
- Ops burden increases: one more process command, one more health signal, one more log stream, and deployment must prove the worker is running.
- The in-process daemon is simpler to start, but it couples worker correctness to Flask/gunicorn lifecycle details. That simplicity is what produced BH5/BH17-style pain before.

Failure modes:

- In-process worker can start once per gunicorn worker, stall silently inside a request container, share memory pressure with request handling, and make warmup depend on background bootstrap mistakes.
- Separate worker can fail to start or die while HTTP stays green. That is a real risk, so `/healthz` must include worker heartbeat/last claim/queue depth, and stale heartbeat should be a deploy blocker.
- Separate worker does not magically prevent container OOM on one B1. The prevention still needs FC1/FC2/FC4/FC9: one worker thread by default, queue depth limits, per-job timeout, capped orphan retry, and memory-budget tests.

Cutover-to-LIVE impact:

For v3 to replace LIVE, report jobs, exports, schedules, and email delivery must be boring under failure. A separately visible worker makes it possible to restart or diagnose job draining without entangling it with HTTP request workers. It also makes future scale-out cleaner if the owner later moves from one B1 to a larger plan or a second worker host: the architecture already has a worker entrypoint instead of a daemon thread assumption.

I can accept a dev-only inline drain for local convenience, and I can accept an emergency feature flag that runs one in-process leader if the platform cannot run the separate worker during the first deploy. But production architecture should be a separate worker entrypoint sharing the same durable job table, not a daemon thread as the normal answer.

Agreed answer I propose: production uses one separately started worker process on the same B1, concurrency 1 by default, with heartbeat/queue diagnostics. Dev may run inline. If the owner rejects the extra process burden, this remains an explicit owner trade-off, not a silent architecture simplification.

## RESOLVED

- OP1: production persistence starts as local SQLite plus Litestream, not managed Postgres, because the app data is small, the deployment is one low-concurrency B1, and BH1-BH8 are addressed by local-disk validation plus restore tests. Postgres remains a real off-ramp through repository seams.
- OP2: normal results can use cache.db and return all tabs, but large results must switch to budgeted lazy/server-paged responses and may spill snapshots to Blob. One server view builder remains the source for screen/export/email/schedule.

## OPEN

- OP3: I still defend a separate production worker process/entrypoint on the same B1. The unresolved question is whether the owner values lower startup/ops complexity enough to accept the daemon-thread failure modes that resemble BH5, BH17, and BH18.
