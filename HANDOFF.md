# Session Handoff

Last updated: 2026-09-01

**Status:** Phase 8 UI/accessibility **in progress**. Draft PR #1. Keep the PR draft. Do not merge or deploy Production.

## What's done

- Q1–Q11 logged. Phases 0–7 closed. Phase 7 gate `99ba689` / docs `10096e4`.
- Phase 8 started (EXPECTED in `.scratch/phase-plan.md`):
  - `openDialog` now sets `inert` on background, `aria-modal`, reduced-motion scroll helper, `watchHiddenPoll`.
  - Admin, SharePoint, external-login, Customer Last Order, report email use that helper.
  - Outbox copy replaced. Schedule-from-report draft failures show an error.
  - Table wraps on admin/dashboard. 44px on help/close/chip/day. Contrast tokens bumped on dark/mono.
  - Settings/dashboard live regions. Tabulator MIT text + Settings link.
  - Report-module cycles kept (browser boot is the proof).

## What's next

1. Finish remaining Phase 8 items that still need running-app / browser evidence (keyboard, contrast at 320/200%, four themes, pollers, reduced motion).
2. Attach browser matrix evidence. Then Loops A/B/C.
3. Live Azure empty-disk drill stays owner BLOCKED.

## Open / BLOCKED

- GitHub Environment `production` required reviewers.
- Access-log review of the cookie-file window.
- Production merge/deploy.
- Live Litestream empty-disk restore (Phase 7 live gate).
- `LIVE_DB_PATH` / `flask import-live-users` until import evidence exists.

## Gotchas

- Do not check off boxes in `PR1-REMEDIATION-PLAN.md`.
- Do not restore `webapp/` or `rebuild/`. Preserve `archive/pre-cleanup-2026-08-27`.
- Keep `is_beta=True`. Do not point home site at `PRECIOUS_DB_PATH` / `LITESTREAM_AZURE_PATH`.
- `gh` is read-only. PRs via ManagePullRequest. Keep draft. Omit `draft` on `update_pr` to keep draft. A human edited the PR body — read live GitHub before updating.
- Python: `/workspace/.venv/bin/python`. v3 tests: cwd `/workspace/v3`. Root tests: `PYTHONPATH=/workspace` without `--noconftest`.
- Never stage `.venv/` or `.scratch/`.
- Frontend: `cd v3 && npm run build` after TS/CSS edits.
- Do not edit migrations `0016`–`0027`.
