# Session Handoff

Last updated: 2026-08-28

**Status:** Phase 0 in progress. Q1–Q4 DECIDED. Asking Q5. Do not start Phase 1. Keep PR #1 draft. No merge. No Production.

HEAD at last push before this note: `abf9452`.

## What's done

- Archive restore proven (`b14d725`).
- Q1: SP `commission` is a fraction; `1` = 100%.
- Q2: money uses each invoice's SP rate; SP `0` stays 0%.
- Q3: Commissions tab % shows `salesmen.commission_pct`.
- Q4: Ordered Summary groups by CustomerAccount; same name, different accounts stay two rows.

## What's next

1. Q5–Q11, then close Phase 0.
2. Phase 1.1 workflow. Phase 1.2 needs Azure secret rotation.
3. Phases 2–10 in plan order.

## Open / BLOCKED

- Q5–Q11 (asking Q5 Hebcal failure).
- P0.1 Flask secret rotation / history rewrite.
- Production merge/deploy.
- Live Litestream empty-disk drill.
