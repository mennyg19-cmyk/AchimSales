# Session Handoff

Last updated: 2026-08-28

**Status:** Phase 0 in progress. Q1–Q3 DECIDED. Asking Q4. Do not start Phase 1. Keep PR #1 draft. No merge. No Production.

HEAD at last push before this note: `ac9f7f1`.

## What's done

- Archive restore proven (`b14d725`).
- Q1: SP `commission` is a fraction; `1` = 100%.
- Q2: money uses each invoice's SP rate; SP `0` stays 0%.
- Q3: Commissions tab % shows `salesmen.commission_pct` (saved salesman percent). Not “varies”.

## What's next

1. Q4–Q11, then close Phase 0.
2. Phase 1.1 workflow. Phase 1.2 needs Azure secret rotation.
3. Phases 2–10 in plan order.

## Open / BLOCKED

- Q4–Q11 (asking Q4 Ordered Summary identity).
- P0.1 Flask secret rotation / history rewrite.
- Production merge/deploy.
- Live Litestream empty-disk drill.

## Gotchas

- Q2 vs Q3: dollars from SP per invoice; printed % from salesman table. People UI does not edit `commission_pct` today.
- Do not print cookies. Do not stage `.venv/` or `.scratch/`.
- Leave the PR draft.
