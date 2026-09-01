# Session Handoff

Last updated: 2026-09-01

**Status:** Phase 8 UI/accessibility **Loops A and B PASS**. Loop C PASS with three nits; nit fixes are in the next commit. Draft PR #1. Keep draft. Do not merge or deploy Production. Loop C re-pass next, then close the Phase 8 gate. Do not start Phase 9 until that re-pass is green.

## What's done

- Q1–Q11 logged. Phases 0–7 closed. Phase 7 gate `99ba689` / docs `10096e4`.
- Phase 8 implementation + browser matrix. Loop A PASS after two FAIL cycles (`def0df8`, `6e7755c`). Token-test `c4b913b`. Loop B PASS. CI 15/15 on `c4b913b`.
- Loop C nits: shell pollers now `watchHiddenPoll`; lookup poll no longer writes dead `lookupPollTimer`; dash live region resets `role` when cleared. Five live-region helpers left as-is (different role/live contracts).

## What's next

1. Fresh Loop C re-pass (`claude-sonnet-5-thinking-high`, not resume). If green, close Phase 8 and start Phase 9.
2. Trust-boundary N/A (presentation/client only).
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
