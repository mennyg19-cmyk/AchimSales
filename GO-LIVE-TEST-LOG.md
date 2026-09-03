# Go-live click-through log

Visible progress of browser and output tests against `go-live/FEATURE-INVENTORY.md`. Newest batches at the top.

**Status:** Browser batches 1–4 logged. Batch 5 = leftover settings/help/theme/CLO/master/dashboard. Excel = pytest only (no D365).

| When (UTC) | Batch | What | Result |
|------------|-------|------|--------|
| 2026-09-03 00:05 | browser-4 | Salesman `/login/dev` 403s (Users, Dashboard); Viewing as badge is **dev-login chrome**, not a prod bug. `/impersonate` works (F12 no End). Role-picker “hang” = radio not selected. Detail: `go-live/click-batch-4.md`. | pass with notes |
| 2026-09-02 23:45 | browser-3 | Company schedules (12 rows + 5-step wizard), Schedule modal from Default Ordered, personal save/copy/history, Run now API-not-set, rename golive-sm2, salesman 403. Salesman session was Viewing as, not fresh login. No batch-3 video. Detail: `go-live/click-batch-3.md`. | pass with notes |
| 2026-09-02 23:20 | pytest | scheduling + catchup + auth + sabbath: **94 passed**. | pass |
| 2026-09-02 23:10 | browser-2 | Remaining report filter bars, Number 4 Both, last-order picker, Daily Ordered `?cview=1`, add-schedule wizard steps, 409 duplicate user, new salesman `golive-sm2`, db-explorer, notif-diag, run-log, 6 local schedule_runs failures (`API not set`). Schedule modal partial (likely disabled on cview). Wizard not saved (`schedules` empty). No batch-2 video. Detail: `go-live/click-batch-2.md`. | pass with notes |
| 2026-09-02 22:50 | browser-1 | Login, reports home (8+aging), chrome, settings, users, schedules empty, dashboard tiles, Ordered filters, salesman-gated settings. Recording: `go-live-click-batch-1.mp4`. | pass (UI; no D365) |
| 2026-09-02 22:45 | pytest | `test_reporting` + filename + scheduling + catchup: **109 passed**. Local Flask `127.0.0.1:5055` up. Live `/healthz` 200. | pass |
| 2026-09-02 22:42 | phase1 | Folded `go-live/FEATURE-INVENTORY.md` (P1–P15, F1–F18). | pass |
| 2026-09-02 22:39 | phase0 | All 8 auditor files in (Sol+Fable × 4 areas). | pass |
| 2026-09-02 22:36 | phase0 | BUILD-HISTORY mined (Composer). First five auditor files committed. | in progress |
| 2026-09-02 22:35 | phase0 | Spawned 8 premier auditors (Sol + Fable) on four live-v3 areas; Composer history miner. | in progress |
| 2026-09-02 22:31 | merge | PR #33 merged to `main` (`263a76b`). Azure Action `33690678155` **success**. Guardrails `33690678321` **success**. | pass |
