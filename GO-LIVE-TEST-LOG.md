# Go-live click-through log

Visible progress of browser and output tests against `go-live/FEATURE-INVENTORY.md`. Newest batches at the top.

**Status:** Browser batches 1–2 recorded. Batch 3 = remaining inventory clicks (`go-live/click-remaining.md`). Excel vs expected = pytest only (no D365).

| When (UTC) | Batch | What | Result |
|------------|-------|------|--------|
| 2026-09-02 23:20 | pytest | scheduling + catchup + auth + sabbath: **94 passed**. | pass |
| 2026-09-02 23:10 | browser-2 | Remaining report filter bars, Number 4 Both, last-order picker, Daily Ordered `?cview=1`, add-schedule wizard steps, 409 duplicate user, new salesman `golive-sm2`, db-explorer, notif-diag, run-log, 6 local schedule_runs failures (`API not set`). Schedule modal partial (likely disabled on cview). Wizard not saved (`schedules` empty). No batch-2 video. Detail: `go-live/click-batch-2.md`. | pass with notes |
| 2026-09-02 22:50 | browser-1 | Login, reports home (8+aging), chrome, settings, users, schedules empty, dashboard tiles, Ordered filters, salesman-gated settings. Recording: `go-live-click-batch-1.mp4`. | pass (UI; no D365) |
| 2026-09-02 22:45 | pytest | `test_reporting` + filename + scheduling + catchup: **109 passed**. Local Flask `127.0.0.1:5055` up. Live `/healthz` 200. | pass |
| 2026-09-02 22:42 | phase1 | Folded `go-live/FEATURE-INVENTORY.md` (P1–P15, F1–F18). | pass |
| 2026-09-02 22:39 | phase0 | All 8 auditor files in (Sol+Fable × 4 areas). | pass |
| 2026-09-02 22:36 | phase0 | BUILD-HISTORY mined (Composer). First five auditor files committed. | in progress |
| 2026-09-02 22:35 | phase0 | Spawned 8 premier auditors (Sol + Fable) on four live-v3 areas; Composer history miner. | in progress |
| 2026-09-02 22:31 | merge | PR #33 merged to `main` (`263a76b`). Azure Action `33690678155` **success**. Guardrails `33690678321` **success**. | pass |
