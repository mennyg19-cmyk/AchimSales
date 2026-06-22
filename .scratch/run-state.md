# Rebuild Run-State

Tracks progress through the rebuild protocol. Update at every phase gate.

## Brief
- `rebuild/REBUILD-BRIEF.md` — locked decisions + open debates + scope.

## Scope of first deliverable
- **Reports:** invoiced only (others wait on their flat-table SP endpoints).
- **Shell features:** PENDING OWNER CONFIRM (see "Open scope question" below).

## Open scope question (blocks the Phase 0 audit fleet)
Which shell features are in the invoiced-first cut? Proposed default:
- IN: Entra login + nav, run/status/resume/cancel jobs, on-screen table
  (group/sort/show-hide/reorder/resize, tabs, subtotals), Excel export + recent
  exports, email delivery, schedule recurring delivery, presets/save-view,
  settings/theme, admin report-config (the manifest editor).
- DEFER: other reports, dashboard (owner said it's unused), customer-last-order,
  master schedules, SharePoint save (confirm).

## Phase status
- [ ] Phase 0 — Multi-model audit + history mining
- [ ] Phase 1 — Feature inventory (invoiced + in-scope shell), page-by-page, ID'd
- [ ] Phase 2 — Architecture proposals (2 premier families)
- [ ] Phase 3 — Debate to consensus → REBUILD-PLAN.md (granular todos)
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
