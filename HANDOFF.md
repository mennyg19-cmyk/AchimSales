# Session Handoff

Last updated: 2026-09-01

**Status:** Phase 9 implementation done; **review gate waits on CI** (hashed lock must install on Python 3.10, including pytest extras). Draft PR #1. Keep draft. Do not merge or deploy Production.

## What's done

- Q1–Q11 logged. Phases 0–8 closed. Phase 8 gate `6960dca` / HANDOFF `39f78b3`.
- Phase 9.1/9.2: `REPORT-PARITY.md` vs isolated archive `b14d725`. Live SQL totals and live Automation send list owner BLOCKED.
- Phase 9.3: one artifact builder (`tools/build_artifact.py` includes `tools/supervise-web.sh`), hashed `requirements.txt`, `deploy.ps1` uses that zip, `git diff --check` clean, `REPOSITORY-REVIEW.md` status rewritten, env templates, dead lookup timer gone.

## What's next

1. Phase 9 review gate: self-review, ponytail-review, Loop A then B then C. Trust-boundary only if reviewers say auth/roles were touched (this phase is docs/hygiene/artifact).
2. Live SQL/Excel totals and live Azure Automation schedule list stay owner BLOCKED.
3. Phase 10 is go-live. Do not merge.

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
