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
- [x] Phase 3 — Debate CONSENSUS (1 round) + REBUILD-PLAN.md written: 12 phases,
      115 todos (T1.01–T12.08), 50/50 BH mapped, 25/25 FA-FB-FC mapped, 9 sign-off
      gates, 12 test suites. 7 minor author calls in §9 (file layout, startup
      script, snapshot format, Tabulator version) — accepted as defaults.
- [~] Phase 4 — Build.
      - [x] 4.0 Foundation + smoke deploy — GREEN on platform 2026-06-22.
            Files: rebuild/{config,app,__init__}.py, data/{connection,migrate}.py +
            migrations, blueprints/{health,main}_routes.py, templates, static/css.
            Wired into root wsgi.py as gated mount. Verified in prod:
            /test-next/ = 200, /test-next/healthz = 200 (env=prod, schema_ready),
            live / and /test untouched (both 200). Covers T1.01-T1.04, T1.06,
            T1.07(healthz), T1.08(seams), T1.09(cache self-heal).
            Deferred to next foundation slice: T1.05 Litestream packaging,
            T1.10 startup.sh + separate worker process.
      - [ ] 4.1 Auth phase (Entra login) — BLOCKED on owner registering the
            Entra redirect URI https://reports.achimonline.com/test-next/auth/callback.
      - [ ] 4.2+ feature-by-feature (jobs/worker, report engine + invoiced, view
            builder, shell, viewer, export, email/schedule).
- [ ] Phase 5 — Final review (route diff + ID ledger + multi-model, looped)

## Foundation decisions (Phase 4.0)
- This app shares one Azure process with live + /test, so it reads its OWN
  REBUILD_* env vars (DB paths, mount, Litestream) to avoid colliding on disk.
  Shared backend resources (GRAPH_*, REPORTING_API_*, FLASK_SECRET) are reused.
- DBs on local disk: /tmp/rebuilddata/{precious,cache}.db (mirrors v3's /tmp/v3data).
- Litestream hard-requirement is gated behind REBUILD_REQUIRE_LITESTREAM (default
  off) so the temporary slot can deploy and be reviewed before cutover.
- Mount is gated on REBUILD_MOUNT_ENABLED + try/except in root wsgi.py, so the
  rebuild can never take down live or /test.

## Live preview URL
- https://reports.achimonline.com/test-next/  (temporary slot; live /test untouched)

## Working branch
- `rebuild-reports`

## Artifacts (to be created)
- `rebuild/rebuild-audit/graph-backbone/[area].md`
- `rebuild/BUILD-HISTORY.md`
- `rebuild/FEATURE-INVENTORY.md`
- `rebuild/DEBATE-LOG.md`
- `rebuild/REBUILD-PLAN.md`
