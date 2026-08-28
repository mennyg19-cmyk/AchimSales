# Session Handoff

Last updated: 2026-08-28

**Status:** Phase 0 of `PR1-REMEDIATION-PLAN.md` is in progress. Archive restore is proven. Owner product decisions Q1–Q11 are unanswered. Do not start Phase 1. Keep PR #1 draft. Do not merge to `webapp-cache`. Do not deploy Production.

HEAD at last push: `ed7ff82` (plan commit). This handoff/decision-log update is the next commit.

## What's done

- Pulled `cursor/p0-security-containment-adb6` at `ed7ff82`. Base `webapp-cache` = `330d1bc`.
- Isolated worktree `/tmp/achim-archive-restore` for tag `archive/pre-cleanup-2026-08-27`.
  - Tag object `9172a657d046f833440fef00dc684f9b7fed4c25`
  - Commit `b14d7252aca6f7643e3cbb899b9593ff6099d241`
  - Contains `webapp/`, `rebuild/`, pre-cleanup `tests/`, `tools/` (evidence: `.scratch/archive-restore.md`)
- Inventories (gitignored): `.scratch/changed-files.txt` (548 files vs base), `.scratch/routes.txt` (109 Flask rules + WSGI `/beta` 302).
- `.scratch/phase-plan.md` and `.scratch/run-state.md` rewritten for this remediation.
- Prior Sol-list work on this PR is still on the branch. Old Loop A/B/C greens do not count after new plan work.

## What's in progress

Phase 0 gate: waiting on owner Q1 (commission unit). Then Q2–Q11, one at a time.

## What's next

1. Owner answers Q1–Q11. Log each in DECISION-LOG.md before any code that depends on it.
2. Close Phase 0 only after all 11 are DECIDED or an item is explicitly BLOCKED by the owner.
3. Phase 1.1 Production workflow guards. Phase 1.2 needs Azure secret rotation (owner).
4. Then Phases 2–10 in plan order. Fresh reviews at every gate.

## Open decisions / BLOCKED

- Q1–Q11 in `PR1-REMEDIATION-PLAN.md` (asking Q1 now).
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
- CodeGraph CLI is not on PATH in this VM; do not grep for symbols until `codegraph init` works, then use it.
- Python: `/workspace/.venv/bin/python`. v3 tests: cwd `/workspace/v3`. Root tests: `PYTHONPATH=/workspace` without `--noconftest`.
