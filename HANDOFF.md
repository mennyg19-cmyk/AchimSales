# Session Handoff

Last updated: 2026-09-01

**Status:** Phase 8 UI/accessibility **implementation + browser evidence done**. Draft PR #1. Keep the PR draft. Do not merge or deploy Production. Reviews (Loops A/B/C) are the remaining Phase 8 gate.

## What's done

- Q1–Q11 logged. Phases 0–7 closed. Phase 7 gate `99ba689` / docs `10096e4`.
- Phase 8:
  - Shared `openDialog` (inert, trap, Escape, restore).
  - Contrast: dark text primary vs `--primary-fill` for buttons; commission headers `#1a5a94`.
  - 44px leftover filter/close/menu targets. Table wraps cannot grow the document.
  - CLO pick-page lookup retry uses `watchHiddenPoll` (no inline script).
  - Missing `from_report` draft opens the wizard so the alert is visible (`679bded`).
  - Browser matrix (Playwright + ComputerUse video). Reporting API unset → run fails closed with a visible error.

## What's next

1. Loop A (`gpt-5.6-sol-high`) then B/C (`claude-sonnet-5-thinking-high`). Trust-boundary only if a reviewer says auth/roles were newly touched.
2. Do not start Phase 9 until that review gate passes.
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
- Keep `is_beta=True`. Dashboard blueprint is not mounted on the home site.
- `gh` is read-only. PRs via ManagePullRequest. Keep draft. Omit `draft` on `update_pr`.
- Python: `/workspace/.venv/bin/python`. Frontend: `cd v3 && npx tsc --noEmit && npm run build`.
- Never stage `.venv/` or `.scratch/`.
- Do not edit migrations `0016`–`0027`.
