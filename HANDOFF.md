# Session Handoff

Last updated: 2026-09-01

**Status:** Phase 8 UI/accessibility **CLOSED**. Draft PR #1. Keep draft. Do not merge or deploy Production. Phase 9 is next.

## What's done

- Q1–Q11 logged. Phases 0–8 closed.
- Phase 7 gate `99ba689` / docs `10096e4`. Live Azure empty-disk drill remains owner BLOCKED.
- Phase 8 implementation + browser matrix. Loop A PASS (`bc-1e484f45`). Loop B PASS (`bc-d6bce7e4` independent). Loop C PASS then nits at `6960dca`. Loop C re-pass PASS (`bc-51d83eae`). Trust-boundary N/A. Parent ponytail-review: Lean already. Ship. CI 15/15 on `6960dca`.
- Leftover non-blocking: five live-region helpers (by design); dead `lookupPollTimer` export/imports (Phase 9 hygiene).

## What's next

1. Phase 9: report/feature parity vs isolated archive `b14d725`, then docs/hygiene (one artifact builder, hashed deps, `git diff --check`).
2. Do not restore `webapp/` or `rebuild/` into this repo. Isolated worktree: `/tmp/achim-archive-restore`.
3. Q6 stays retired (in-app email distributions). Live SQL totals need Reporting API; local env is unset.

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
