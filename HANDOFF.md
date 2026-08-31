# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 2 auth is on the draft PR. CI is green on `6601b78` (15/15). Keep PR #1 draft. Do not merge or deploy Production. Do not start Phase 3 until the Phase 2 review gate (correctness + trust-boundary) is green.

## What's done

- Q1–Q11 logged.
- Phase 1.1 workflow gating.
- Phase 1.2: no history rewrite; owner confirmed Flask secret rotation.
- Phase 2: live-cookie adopt deleted; MSAL lookup-only; boot does not read Live DB; magic-link hashes + ProxyFix IP + log redaction.
- CI on `6601b78`: 15/15 green.

## What's next

1. Finish Phase 2 review (correctness loops + trust-boundary), then start Phase 3 (SQL-only v3, delete OData from the web app).
2. Owner still needs GitHub Environment `production` required reviewers (Settings → Environments). That Environment does not exist yet.

## Open / BLOCKED

- GitHub Environment `production` required reviewers.
- Production merge/deploy.
- Live Litestream empty-disk restore.
- `LIVE_DB_PATH` / `flask import-live-users` until import evidence exists.
