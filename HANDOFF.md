# Session Handoff

Last updated: 2026-08-28

**Status:** Phase 0 product questions closed (Q1–Q11). Starting Phase 1. Keep PR #1 draft. Do not merge or deploy Production.

HEAD: `0aa35ac` before the Q11 commit.

## What's done

- Q1–Q11 logged in `DECISION-LOG.md`.
- Q11: 45-minute job cap; on timeout mark cancelled and kill the child; Reporting API 300s; Graph accept then connection loss = `unknown`, no auto-retry, operator reconciles.

## What's next

1. Phase 1.1 production workflow (dispatch guard, `production` Environment, timeouts, checks as deploy dependencies).
2. Phase 1.2 owner: rotate Flask secrets; confirm old cookies dead; review access logs; decide history rewrite.

## Open / BLOCKED

- P0.1 / Phase 1.2 Flask secret rotation and history rewrite.
- Production merge/deploy.
- Live Litestream empty-disk drill.
