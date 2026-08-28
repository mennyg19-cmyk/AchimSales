# Session Handoff

Last updated: 2026-08-28

**Status:** Phase 0 closed. Phase 1.1 YAML on the draft. Phase 1 gate still open: owner must rotate Flask secrets and enable required reviewers on GitHub Environment `production`. Keep PR #1 draft. Do not merge or deploy Production.

HEAD: `29f95df` before the Phase 1.1 commit.

## What's done

- Q1–Q11 logged.
- Phase 1.1: Azure workflow skips unless `webapp-cache`; deploy job uses Environment `production`; check jobs are `needs:` of package/deploy; job timeouts set.

## What's next

1. Owner: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure; confirm old `session` / `v3_session` cookies no longer authenticate; review access logs from the cookie-file window; decide history rewrite; enable required reviewers on Environment `production`.
2. After 1.2, Phase 2 auth. Do not start Phase 2 while 1.2 is BLOCKED.

## Open / BLOCKED

- Phase 1.2 Flask secret rotation, cookie revoke, access-log review, history rewrite.
- GitHub Environment `production` required reviewers.
- Production merge/deploy.
- Live Litestream empty-disk drill.
