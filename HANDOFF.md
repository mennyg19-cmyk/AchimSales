# Session Handoff

Last updated: 2026-08-28

**Status:** Phase 0 of `PR1-REMEDIATION-PLAN.md` is in progress. Archive restore is proven. Q1 (commission unit) is DECIDED. Asking Q2. Do not start Phase 1. Keep PR #1 draft. Do not merge to `webapp-cache`. Do not deploy Production.

HEAD at last push before this note: `3e5330b`.

## What's done

- Isolated archive restore: tag `archive/pre-cleanup-2026-08-27` = `b14d725` at `/tmp/achim-archive-restore`.
- Inventories in `.scratch/` (not committed).
- Q1 DECIDED: SP `commission` is a fraction. `1` means 100%. Typical rates ~0.03–0.05. Phase 6 must restore `pct > 1`. No live SP capture from this VM.

## What's in progress

Phase 0 owner questions. Next: Q2 (commission effective rate).

## What's next

1. Finish Q2–Q11, log each before dependent code.
2. Close Phase 0 only after all 11 are DECIDED or explicitly BLOCKED.
3. Phase 1.1 workflow guards. Phase 1.2 needs Azure secret rotation (owner).
4. Phases 2–10 in plan order. Fresh reviews at every gate.

## Open decisions / BLOCKED

- Q2–Q11 in `PR1-REMEDIATION-PLAN.md` (asking Q2 now).
- P0.1: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure; confirm old cookies dead; access-log review; history rewrite.
- Production merge/deploy.
- Live Azure empty-disk Litestream drill.

## Gotchas

- Plan is the authority. Do not fall back to OData. Do not start workers from Flask.
- Do not print cookie values. Do not stage `.venv/` or `.scratch/`.
- Do not edit applied migrations; add forward migrations only.
- Do not restore `webapp/` or `rebuild/` into the active app. Keep the archive tag.
- Keep `reports/`, `core/`, `data/`, `runbooks/`.
- `gh` is read-only for PRs; use ManagePullRequest. Leave the PR draft.
- CodeGraph CLI is not on PATH in this VM.
- Python: `/workspace/.venv/bin/python`. v3 tests: cwd `/workspace/v3`. Root tests: `PYTHONPATH=/workspace` without `--noconftest`.
