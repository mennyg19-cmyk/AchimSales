# Rebuild Run-State

Tracks progress through the rebuild protocol. Update at every phase gate.

## Brief
- `rebuild/REBUILD-BRIEF.md` — locked decisions + open debates + scope.

## Scope of first deliverable (CONFIRMED by owner 2026-06-22)
- **Reports:** invoiced only (others wait on their flat-table SP endpoints).
- **Shell features IN:** Entra login + nav, run/status/resume/cancel jobs,
  on-screen table (group/sort/show-hide/reorder/resize, tabs, subtotals),
  Excel export + recent exports, email delivery, schedule recurring delivery,
  presets/save-view, settings/theme.
- **Admin report-config:** SEED invoiced's column/tab config now (code/DB);
  the admin manifest editor is a LATER phase, not the first deliverable.
- **DEFER (keep on inventory, not first cut):** other reports, dashboard,
  customer-last-order, master schedules. SharePoint save: confirm during Phase 1.

## Phase status
- [x] Phase 0 — Multi-model audit + history mining (7 agents, 7 families; done)
- [x] Phase 1 — Feature inventory (`rebuild/FEATURE-INVENTORY.md`): 20 pages P1–P20,
      route manifest, to-fix (FA/FB/FC), BH1–50 prevention map, 9 human sign-offs
- [x] Phase 2 — Architecture proposals (Claude Opus + GPT): agree on stack,
      server-side grouping, SQL-first math, DB report config; split on persistence,
      big-table, worker.
- [~] Phase 3 — Debate reached CONSENSUS (1 round): SQLite+Litestream; tiered
      snapshot (cache.db→Blob over budget, one view builder); separate worker
      entrypoint (prod process default + in-process fallback flag). Now converging
      into REBUILD-PLAN.md.
- [ ] Phase 4 — Build (foundation + smoke deploy, then feature-by-feature)
- [ ] Phase 5 — Final review (route diff + ID ledger + multi-model, looped)

## Working branch
- `rebuild-reports`

## Artifacts (to be created)
- `rebuild/rebuild-audit/graph-backbone/[area].md`
- `rebuild/BUILD-HISTORY.md`
- `rebuild/FEATURE-INVENTORY.md`
- `rebuild/DEBATE-LOG.md`
- `rebuild/REBUILD-PLAN.md`
