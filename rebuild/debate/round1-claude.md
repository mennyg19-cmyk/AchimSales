# Round 1 — Claude defense

Model: claude-4.6-opus-max-thinking

## Proof-of-read

- **PROPOSAL-claude.md** (765 lines, 10 sections): my proposal — SQLite+Litestream, grouped cache.db all-tabs, in-process daemon worker.
- **PROPOSAL-gpt.md** (428 lines, 12 sections): their proposal — managed Postgres, flat Blob snapshot + server paging, separate worker/WebJob.
- **DEBATE-LOG.md** (49 lines): Round 0 locked — AGREED list covers stack, grouping-server-side, SQL-first math, DB config, module split, FA/FB/FC coverage, BH prevention, cutover. Three OPEN: OP1 persistence, OP2 result snapshot + big-table, OP3 worker model.
- **FEATURE-INVENTORY.md** (236 lines): 20 pages P1–P20, 6 page routes, ~35 APIs, 7 tabs/69 columns, deferred pages listed.
- **BUILD-HISTORY.md** (50 items BH1–BH50): persistence failures (BH1–8 all SMB-caused), OOM (BH10 = 488K-row Ordered, not Invoiced), worker stalls (BH17–18), export parity (BH27).

---

## OP1 — Persistence: DEFEND SQLite + Litestream

### The deployment reality

One B1 (1 vCPU, 1.75GB RAM). Internal users only — a few dozen people. Cost-conscious owner. App data is tiny: users, jobs, schedules, preferences, audit log, report configs. Maybe 100KB growing to a few MB over years.

### Why SQLite is correct here

**1. BH1–8 indict SMB, not SQLite.**

Every persistence bug traces to the same root cause: SQLite hosted on Azure Files (SMB network mount). BH1: worker couldn't see web writes. BH2: journal mode switch on SMB = locked. BH3: corruption from network-share multi-process. BH7: path defaulted to `/home` (SMB). BH8: container recycle wiped temp.

The fix shipped in production (2026-06-18 per HANDOFF): move to local container disk + Litestream backup to Blob. SQLite on local disk is a well-understood, battle-tested configuration. The root cause is gone.

**2. Cost.**

Azure Flexible Server (cheapest Postgres): ~$15–50/month. The B1 itself costs ~$13/month. Adding Postgres more than doubles infrastructure cost for a dataset that fits in a text file. The owner is cost-conscious — this matters.

**3. Zero network dependency for reads/writes.**

Every precious.db query is a local file read: sub-millisecond, no connection pooling, no connection limits, no TLS handshake, no network partition risk. Postgres adds 1–5ms per query plus a new failure mode (DB unreachable).

**4. Operational simplicity.**

SQLite on local disk: no version upgrades, no vacuum/analyze schedules, no pg_dump cron, no connection pool tuning, no SSL cert rotation, no monitoring dashboards for query performance. One fewer Azure resource to provision, secure, and pay for.

**5. The "ceremony" GPT cites is trivial.**

What SQLite on local disk actually needs:
- Boot refuses `/home`/UNC: one `if` statement in `config.py`
- Litestream binary: one line in `startup.sh`
- Restore test: one integration test
- WAL mode: the default, not ceremony
- Single instance: already the case (B1), not a constraint SQLite imposes

Compare to Postgres "ceremony": provision Flexible Server, configure firewall rules, manage connection strings, set up SSL, tune connection pool, schedule backups, monitor query latency, handle Azure Postgres maintenance windows, migrate schema.

**6. The off-ramp seams make this reversible at near-zero cost.**

Both proposals agree on the seams (Connection protocol, Python UTC, abstract `claim_next`, `lock_for_migration`, JSON as TEXT). These exist in my proposal from day one. If the app outgrows B1 (multiple instances needed), swap to Postgres by implementing the same protocol — one sprint, not a rewrite.

### What GPT gets right

"v3 replaces LIVE; durable state shouldn't depend on ephemeral local file + sidecar" is a fair emotional argument. But it's technically inaccurate: Litestream provides continuous streaming WAL replication to Azure Blob with point-in-time recovery. The local file is not the source of durability — Blob is. Cold boot restores from Blob (BH8 prevention). This is architecturally equivalent to Postgres streaming replication, just cheaper and simpler for a single-instance deployment.

### Verdict on OP1

This is ultimately an owner call (cost + ops comfort). The technical case favors SQLite for this deployment. The seams make it non-breaking either way. I defend SQLite as the default, with Postgres documented as the scale-out upgrade path when/if the app needs multiple instances.

---

## OP2 — Result snapshot + big-table: PROPOSE THIRD OPTION

### Where GPT and I agree

- The grouped dataset is the single source of truth for screen + export + email (AGREED, kills BH27).
- Export must stream from server, never build in browser memory.
- Huge payloads to the browser are bad UX.

### Where GPT goes too far

**Azure Blob for snapshots** adds operational complexity (connection strings, SAS/managed-identity, retry logic, another service to monitor) for disposable data that only lives until the user runs again. cache.db on local disk is simpler, self-healing (BH6), and has zero network latency on reads.

**Server paging/filter/sort within a tab** is a full remote-data-table implementation: cursor state, offset/limit, re-sort server-side per page request, filter sync between client and server. This is complex machinery. Tabulator already has virtual-DOM rendering that handles 50K rows without breaking a sweat — you don't need server paging for normal result sizes.

### Where I went too far

Sending all 7 tabs' rows at once when the user only sees one tab is wasteful. A YTD run with 80–100MB across all tabs shouldn't ship to the browser in one response. YAGNI was wrong here — lazy tab loading is justified by the architecture (user sees one tab at a time) and costs little.

### The hybrid both sides should accept

**Storage:** Grouped result in `cache.db` (local SQLite, disposable, self-healing). Not Blob. One instance, local disk, sub-ms reads.

**Delivery:**
1. Initial response: active tab rows + metadata for all tabs (tab keys, labels, row counts, column defs). Cost: one tab's rows (~2–10MB for typical invoiced).
2. Tab switch: `GET /api/reports/result/<id>/tab/<tab_key>` reads from cache.db, returns that tab's rows. One extra round-trip per tab switch, sub-ms server read.
3. Within a tab: send all rows for that tab. Tabulator's virtual DOM renders them efficiently. No server paging needed for invoiced-scale data (sub-50K rows per tab).
4. Export: reads all tabs from cache.db, streams via openpyxl. No browser involvement.

**Escape valve (documented, not built):** If a future report's single tab exceeds 100K rows and Tabulator struggles, add server-side pagination for that tab behind a config flag. Don't build it now.

### Why this works for the deployment reality

- Typical first-tab response: 2–10MB (fast, fits in memory easily)
- Total memory for all tabs if user clicks through: same as my original proposal, just spread over time
- No Blob service to manage
- No pagination state machine to maintain
- Export still uses cache.db directly — zero architectural change from my original proposal
- Lazy tab loading is ~20 lines of client code and one new route

---

## OP3 — Worker process model: DEFEND in-process

### The B1 constraint is the whole argument

One B1 = 1 vCPU, 1.75GB RAM. A separate worker process on the same machine:
- Shares the same RAM (two Python interpreters = more overhead, not less)
- Shares the same CPU (OS scheduler, not App Service plan)
- Adds process communication overhead (no shared memory for job state)
- Doubles deploy targets (two processes to start, monitor, restart)
- Does NOT protect against OOM (kernel kills whichever process exceeds cgroup limits — both die)

A separate worker only makes sense when you have separate machines or separate scaling. On one B1, it's overhead for zero isolation benefit.

### BH10 and BH17 support in-process, not against it

**BH10** (OOM on 488K rows): This was the Ordered report, not Invoiced. The fix is SQL-side filtering + memory budgets + capped recovery — not process isolation. A separate worker on the same B1 would OOM identically; it just wouldn't take the web process with it (maybe — depends on cgroup config). But with per-job timeouts (FC4) and memory budget tests, the OOM shouldn't happen in the first place.

**BH17** (multiple scheduler instances): This is SOLVED by flock-based leader election, which works elegantly with an in-process daemon thread on single-instance. A separate worker would need the same leader coordination — and flock is simpler than distributed locking over Postgres advisory locks.

### What the worker actually does

Report runs are I/O-bound: call SQL Server SP over network (seconds to minutes waiting), then group/cache the result (milliseconds of CPU). The worker thread is mostly sleeping, waiting on network I/O. It's not competing with request-handling threads for CPU. There's no compute isolation to gain.

### The honest scale-out path

If the app moves beyond B1 (multiple web instances, or heavy concurrent report loads):
1. Worker becomes a separate process (or Azure WebJob)
2. Job table moves to Postgres (off-ramp seams in place from OP1)
3. Leader election moves from flock to Postgres advisory locks

This is documented from day one. But building it now on B1 = paying complexity cost for a problem that doesn't exist.

### What GPT gets right

"Web process serves HTTP only" is a clean principle. I agree with it as an aspiration. The deviation is pragmatic: on B1, the daemon thread IS the simplest way to run background work without doubling process overhead. The code structure still separates concerns — `worker.py` doesn't import Flask, `blueprints/` don't import worker internals. The boundary is in code, just not in processes.

### Alignment with OP1

If we keep SQLite (OP1), in-process is even more natural: web and worker share the same local precious.db/cache.db files via the same Python process. No cross-process WAL coordination needed. With Postgres, a separate process would be marginally easier (both connect to remote DB independently) — but on B1, the overhead argument still dominates.

---

## RESOLVED (I now agree on these)

1. **OP2 partial — lazy tab loading:** Send active tab rows first, load other tabs on switch. Both proposals agree the user sees one tab at a time; shipping all at once is wasteful. No server paging needed within a tab for invoiced-scale data.

## OPEN (still in dispute)

1. **OP1 — Persistence default:** I defend SQLite + Litestream as the production default (cost, simplicity, deployment reality). GPT wants managed Postgres. Both agree on repository seams making it swappable. The technical arguments favor SQLite for one B1; this is likely an owner cost/ops call.

2. **OP2 partial — snapshot storage location:** I say cache.db (local SQLite, disposable). GPT says Azure Blob. Blob adds operational complexity for disposable data on a single-instance deploy. This hinges on whether cache.db surviving container recycles matters — I say no (reports just re-run; the data is cheap to regenerate from SQL Server).

3. **OP3 — Worker model:** I defend in-process daemon thread on B1 (zero isolation benefit from separate process on shared hardware; lower overhead; simpler deploy). GPT wants separate process/WebJob. Both agree on the documented scale-out path. The disagreement is whether to pay the complexity cost now or when evidence demands it.
