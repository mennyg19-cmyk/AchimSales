# Session Handoff

Last updated: 2026-08-28

**Status:** Phase 0 of `PR1-REMEDIATION-PLAN.md` is in progress. Q1–Q2 DECIDED. Asking Q3. Do not start Phase 1. Keep PR #1 draft. Do not merge to `webapp-cache`. Do not deploy Production.

HEAD at last push before this note: `90d5671`.

## What's done

- Isolated archive restore: tag `archive/pre-cleanup-2026-08-27` = `b14d725`.
- Q1 DECIDED: SP `commission` is a fraction. `1` means 100%. Phase 6 restores `pct > 1`.
- Q2 DECIDED: each invoice uses its own SP rate. SP `0` stays 0%. Do not fall back to `salesmen.commission_pct`.

## What's in progress

Phase 0 owner questions. Next: Q3 (commission display when rates vary).

## What's next

1. Finish Q3–Q11, log each before dependent code.
2. Close Phase 0 only after all 11 are DECIDED or explicitly BLOCKED.
3. Phase 1.1 workflow guards. Phase 1.2 needs Azure secret rotation (owner).
4. Phases 2–10 in plan order.

## Open decisions / BLOCKED

- Q3–Q11 in `PR1-REMEDIATION-PLAN.md` (asking Q3 now).
- P0.1 Flask secret rotation / history rewrite.
- Production merge/deploy.
- Live Azure empty-disk Litestream drill.

## Gotchas

- Plan is the authority. Do not fall back to OData. Do not start workers from Flask.
- Do not print cookie values. Do not stage `.venv/` or `.scratch/`.
- Do not edit applied migrations; add forward migrations only.
- Do not restore `webapp/` or `rebuild/` into the active app.
- Keep `reports/`, `core/`, `data/`, `runbooks/`.
- Leave the PR draft.
- Python: `/workspace/.venv/bin/python`. v3 tests: cwd `/workspace/v3`.
