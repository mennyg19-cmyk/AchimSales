# Debate Log — Architecture consensus

Two premier-model proposals (`rebuild/proposals/PROPOSAL-claude.md` by
claude-4.6-opus-max-thinking; `rebuild/proposals/PROPOSAL-gpt.md` by
gpt-5.5-extra-high) debated to one agreed architecture. Loop rules: each model
defends its OWN proposal each round; canonical inventory wins on any
contradiction; product/cost judgment calls go to the owner, never decided
silently. ~3–4 round cap.

## Round 0 — positions on the table

### AGREED (both models, not up for debate)
- **Stack:** keep Flask + Jinja server-rendered templates + esbuild TypeScript +
  Tabulator (Tabulator behind a single adapter, not touched everywhere).
- **Grouping location:** server-side. One grouped view feeds screen + export +
  email + schedule, so they can't diverge (kills BH27 structurally). Tabulator
  does within-tab interactivity only.
- **SQL-first math:** invoiced SP returns one flat table with all row math done
  (IsCredit, Total, CommissionPct/Base/Amount, SalesmanNumber/Name, Misc, month).
  App does generic subtotals + the one named commission pivot transform only.
- **Report config in the DB:** registry → seeded DB tables (definitions, params,
  columns, tabs, scope). Invoiced seeded now; admin editor later. Adding a report
  = config, not a deploy.
- **Module split:** thin blueprints, services, repositories; report.ts → small
  typed modules behind a grid adapter; CSS split by component/page with tokens.
- **All to-fix items FA1–7, FB1–8, FC1–10** addressed the same way by both.
- **All BH1–50 preventions** mapped the same way by both.
- **Cutover, CSRF, fail-closed boot, durable jobs, audit log, sign-offs** — same.

### OPEN — must converge
- **OP1 — Persistence.** Claude: keep **SQLite + Litestream** (app data tiny;
  BH1–8 were SMB-caused and the root cause is gone; no network hop; cheapest;
  tighten Postgres off-ramp seams now). GPT: use **managed Postgres** in prod
  (SQLite only dev/fallback) because v3 replaces LIVE and durable state shouldn't
  depend on an ephemeral local file + sidecar restore; the SQLite "ceremony"
  (local-only paths, restore proof, Litestream packaging, WAL, single-instance)
  is heavy. NOTE: has a real $ + ops dimension → likely an owner call.
- **OP2 — Result snapshot + big-table strategy.** Claude: store grouped result in
  `cache.db`; send all tabs' rows to the browser; ~80–100MB worst-case YTD is fine
  on B1; add lazy tab loading only if ever needed (YAGNI). GPT: store flat
  snapshot (large ones in **Azure Blob**); **server paging/filter/sort** over the
  snapshot for large results; never ship all-tabs-all-rows for big results; export
  streams.
- **OP3 — Worker process model.** Claude: **in-process worker** (daemon thread in
  the web app, flock leader election) — simplest on one B1. GPT: **separate worker
  process / Azure WebJob** sharing the job table; web process serves HTTP only.

## Round 1 (`rebuild/debate/round1-claude.md`, `round1-gpt.md`)

- **OP1** — GPT **CONCEDED** to SQLite + Litestream; Claude defended the same. Both
  require the local-disk gates (boot refuses `/home`/UNC, Litestream packaged +
  verified, empty-disk restore test, integrity diagnostics, one instance) and the
  Postgres off-ramp seams now (Connection protocol, Python UTC, JSON-at-edge,
  isolated `claim_next`, `lock_for_migration`). → **RESOLVED.**
- **OP2** — Both moved to a tiered/budgeted hybrid. Agreed: one canonical flat
  snapshot + one server `ReportViewBuilder` for screen/export/email/schedule;
  normal results in `cache.db` returned active-tab-first with lazy per-tab load;
  results over a configured budget (row count + estimated bytes, numbers from the
  memory-budget test) switch to lazy/server-paged and may spill the snapshot to
  Blob (Blob is already in the stack for Litestream + exports); exports always
  stream; snapshot storage behind an abstraction so cache.db↔Blob is a config flip.
  → **RESOLVED.**
- **OP3** — Claude defended in-process daemon thread (no isolation gain on shared
  B1, lower overhead); GPT defended a separate worker entrypoint (lifecycle
  separation kills BH5/BH17/BH18 by construction). Both stated overlapping
  acceptance conditions in writing: GPT — "I can accept ... an emergency feature
  flag that runs one in-process leader if the platform cannot run the separate
  worker"; Claude — "I agree with it as an aspiration ... the boundary is in code"
  and conceded OOM prevention (FC1/FC2/FC4/FC9) is needed either way.

### Consensus resolution on OP3 (orchestrator synthesis of both acceptance conditions)
The worker is a **separate entrypoint module** (no Flask import; clean lifecycle
boundary — satisfies Claude's "boundary in code"). Production default: run it as
its **own process from the container startup** (one container, one deploy, one B1
— not a second Azure resource), concurrency env-driven (default 1), with worker
heartbeat + last-claim + queue-depth surfaced in `/healthz` as a deploy signal
(BH16). **In-process leader-thread fallback behind a feature flag** for dev and
first-deploy/emergency (Claude's overhead/simplicity safety valve; GPT's stated
fallback). Same worker code both ways; flock leader election still guards
single-runner. Rationale: canonical BH history (BH5 cold-start coupling, BH17
per-gunicorn-worker loops, BH18 hung-job blindness) favors lifecycle separation;
the fallback flag preserves the cheap/simple path. OOM is not the differentiator
(both require the memory gates). → **RESOLVED.**

## Outcome: CONSENSUS on all three open points. No stalemate, no owner tie-break
needed (persistence converged on the low-cost option). Owner-facing items remain
the 9 sign-offs in FEATURE-INVENTORY §5 (build-time, not architecture).
