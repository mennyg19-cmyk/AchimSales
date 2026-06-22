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

## Round 1
(pending)
