# Session Handoff

Last updated: 2026-08-28

**Status:** Phase 1.2 policy logged: do not rewrite git history; require GitHub Environment `production` reviewers. Gate still open until Azure Flask secrets are rotated. Keep PR #1 draft. Do not merge or deploy Production. Do not start Phase 2.

HEAD: `bdbcdcb` before this policy commit.

## What's done

- Q1–Q11 logged.
- Phase 1.1 workflow gating.
- Phase 1.2 policy: no force-push / no history rewrite. Environment reviewers are required.

## What's next

1. Owner must rotate `FLASK_SECRET_KEY` and `FLASK_SECRET` in Azure App Service `achim-sales-reports`, then confirm old `session` / `v3_session` cookies no longer sign in.
2. Owner must create GitHub Environment `production` if needed and enable Required reviewers.
3. Owner should review App Service access logs from the cookie-file window.
4. After old cookies are dead, Phase 2 auth.

## Open / BLOCKED

- Azure Flask secret rotation (this phrase does not do it).
- GitHub Environment `production` required reviewers (repo Settings; this agent cannot write GitHub settings).
- Production merge/deploy.
- Live Litestream empty-disk drill.
