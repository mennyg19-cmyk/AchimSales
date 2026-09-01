# Session Handoff

Last updated: 2026-09-01

**Status:** Phase 9 review gate closed at `8900f01`. Draft PR #1. Keep draft. Do not merge or deploy Production. Do not start Phase 10.

## What's done

- Q1–Q11 logged. Phases 0–9 closed. Phase 8 gate `6960dca` / HANDOFF `39f78b3`.
- Phase 9.1/9.2: `REPORT-PARITY.md` vs isolated archive `b14d725`. Live SQL totals and live Automation send list owner BLOCKED.
- Phase 9.3: one artifact builder (`tools/build_artifact.py` includes `tools/supervise-web.sh`), hashed `requirements.txt` (Python 3.10, including pytest extras), `deploy.ps1` matches CI gates, git-tracked-only zip, personal CLO schedules 400.
- Phase 9 reviews: Loop A PASS (re-pass 3), Loop B PASS, Loop C PASS (two non-blocking nits). Trust-boundary N/A. Parent ponytail: Lean already. Ship. CI 15/15 on `8900f01`.

## What's next

1. Phase 10 is go-live. Owner approvals required. Do not merge or deploy Production from this branch.
2. Live SQL/Excel totals and live Azure Automation schedule list stay owner BLOCKED.

## Open / BLOCKED

- GitHub Environment `production` required reviewers.
- Access-log review of the cookie-file window.
- Production merge/deploy.
- Live Litestream empty-disk restore (Phase 7 live gate).
- `LIVE_DB_PATH` / `flask import-live-users` until import evidence exists.
- Live Reporting API totals vs Production Excel.
- Live Azure Automation job list.

## Gotchas

- Do not check off boxes in `PR1-REMEDIATION-PLAN.md`.
- Do not restore `webapp/` or `rebuild/`. Preserve `archive/pre-cleanup-2026-08-27`.
- Keep `is_beta=True`. Dashboard blueprint is not mounted on the home site.
- `gh` is read-only. PRs via ManagePullRequest. Keep draft. Omit `draft` on `update_pr`.
- Python: `/workspace/.venv/bin/python`. Frontend: `cd v3 && npx tsc --noEmit && npm run build`.
- Never stage `.venv/` or `.scratch/`.
- Do not edit migrations `0016`–`0027`.
- CI install is `pip install --require-hashes -r requirements.txt`. Ranges live in `requirements.in`.
