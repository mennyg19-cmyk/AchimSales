# Rebuild Brief — Sales Reports (ground-up)

Plain-English brief that kicks off the rebuild protocol. This is the agreed
starting point; the architecture debate (Phase 2/3) may refine anything not
marked locked. Tone + rules: see `.cursor/rules/`.

## Why we're rebuilding

v3 works but grew by bolting features on top of features (a 2,000-line
`report.ts`, reactive UI additions, one-off CSS). The owner wants it to look
and work as if it were built correctly from the ground up — and eventually to
*replace* the LIVE app, with the on-prem SQL Server doing the report math.

## What this is (and isn't)

- **Ground-up rebuild. Nothing is ported.** The Excel builders, table display,
  exports, email, scheduling — all rebuilt cleanly. Old v3 code is a reference
  for WHAT the app does, never a copy source for HOW.
- **Not a pixel copy.** Target: workable and correctly formatted, matching the
  LIVE app's column/format *conventions* — not its markup.
- **The whole stack is on the table**, including the "locked" items below —
  those are defaults the architecture debate must still challenge for a better
  option before accepting.

## The core architecture (decided)

1. **One stored procedure per report → one flat table**, with all row-level math
   already done in SQL (net, commission $, misc charges, etc.).
2. **The app is a presentation layer, not a calculator.** It renders that one
   table and lets the user group / sort / show-hide / reorder columns / tabs.
3. **Tabs are saved groupings of that same table.** Invoiced returns one table;
   the app groups by salesman for one tab, by customer for another, by item for
   another; "Full Data" = ungrouped. A tab = group-by column + which columns to
   show + a subtotal row.
4. **The app's only arithmetic is subtotals / grand-totals** — generic summation
   of dollar/quantity columns. Percentage/rate columns (e.g. commission %) stay
   **blank** in subtotal rows.
5. **SQL filters rows by a scope parameter the app passes in** — a salesman's
   restricted data never leaves the database.
6. **Reports are admin-defined.** Adding a report = in the admin panel, point at
   a stored procedure, the app auto-reads its columns, and you set
   label/format/order/scope/tabs there. Saved to the DB. No code deploy for the
   common (passthrough + grouping) case. Custom math, when truly needed, is a
   small registered function — but the goal is that most reports need none.
7. **Invoiced report migrates first.** Other reports wait on their simplified
   single-flat-table SQL endpoints being built; once invoiced is right, adding
   the rest is mostly config.

## Prerequisites (locked unless the debate finds better)

- Lightweight surface, sturdy spine (shed accidental complexity, keep hard-won
  robustness).
- Modular, admin-defined reports (see #6).
- Stays on **Azure App Service**.
- **Microsoft / Entra company logins.**
- Durable async jobs — no long report work in web request handlers.
- Audit/run log built in (incident proof: app vs endpoint).
- Responsive + accessible from day one.
- Tests are the ship gate (parity, authz/scope, job lifecycle, migrations,
  security boot-refusal, CSRF).
- Cutover-ready by design: flipping `/test` → `/` is routing + config, not a
  rewrite (same Entra login, same URL conventions, a LIVE feature-parity list).
- **Temporary mount (owner directive 2026-06-22):** the rebuild does NOT take the
  `/test` slot until the owner confirms it looks good. It deploys to a temporary
  slot (`APP_MOUNT_PATH`, default `/test-next`) with its own derived Entra
  redirect URI, leaving the live `/test` app untouched. Taking over `/test` (and
  later `/`) is a config flip + Entra URI add after sign-off — built for easy
  change, not hardcoded.
- **LIVE parity is temporary scaffolding** — a parity check that proves v3 == LIVE
  for the cutover, then retires. After cutover, SQL is the source of truth.

## Open for the Phase 0/1 architecture debate

- **Persistence:** local SQLite + Litestream (cheapest, single-instance) vs
  managed Postgres (more moving parts, easier multi-instance later).
- **Grouping location:** thin server step (on-screen tabs and Excel export share
  one grouped dataset — can't disagree) vs browser/Tabulator grouping (most
  dynamic, but export parity + big-table memory need care).
- Challenge every "locked" item for a better alternative before accepting it
  (framework, language, frontend approach — all on the table; hosting stays
  Azure App Service).

## Will also be settled during planning (flagged, not new prereqs)

- Result caching + how fresh report data must be.
- Memory limits handling big flat tables on a small instance (past OOM history).
- Filter → SP-parameter mapping in the report manifest.
- Export fidelity (tied to the grouping-location decision).

## Scope of the FIRST deliverable (to confirm — see run-state)

Foundation + the **invoiced report end-to-end**, plus the shell features the
invoiced report rides on. Deferred: the other reports, until their flat-table
SP endpoints exist. The exact shell feature set for the first cut is the one
open scope question.

## Reference (WHAT, not HOW)

- Current v3 app: `v3/` (this repo). The invoiced report core today lives in
  `v3/report_engine/reports/invoiced.py`, `v3/report_engine/sources/invoiced.py`,
  `v3/web/blueprints/reports.py`, `v3/web/static_src/js/report.ts`.
- LIVE app: source of truth for the invoiced report's column/format conventions.
