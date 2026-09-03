# Session Handoff

Last updated: 2026-09-03 (PR #1 instructions replayed on current `main`)

**Status:** New draft PR from `main` `263a76b`. Plan + review snapshot committed. Phase 1 leftover containment is next. Do not merge until Phase 10. Do not merge leftover PR #1.

## Working tree

- **Branch:** `cursor/pr1-on-main-551b`
- **Base:** `main` @ `263a76b`
- **Repo:** AchimSales (`mennyg19-cmyk/AchimSales`)
- **Prod URL:** https://reports.achimonline.com (Azure deploys **only** from `main`)
- **Old PR #1:** https://github.com/mennyg19-cmyk/AchimSales/pull/1 — leave open; do not merge

## Authoritative files

| Path | Role |
|------|------|
| `PR1-REMEDIATION-PLAN.md` | Worklist for this PR (`webapp-cache` in later sections means `main`) |
| `REPOSITORY-REVIEW.md` | Original review snapshot from PR #1 |
| `DECISION-LOG.md` | Newest-first; 2026-09-03 entry supersedes “no Phase 2–4 rewrite” for this PR |
| `.scratch/run-state.md` | Gate checkpoint (gitignored) |
| `.scratch/phase-plan.md` | Expectation checklist (gitignored) |
| `go-live/FEATURE-INVENTORY.md` | Live v3 inventory (P1–P15, C1–C11, F1–F18) on `cursor/go-live-verify-551b` |

## Locked for this PR

1. Keep every product feature from PRs #11–#33.
2. Do not delete `webapp/`, `rebuild/`, `/legacy`, `/test`, or `/test-next` until those jobs are migrated.
3. OData fail-closed now; SQL-only v3 only after every built report has SQL.
4. Q1–Q11 from the old PR #1 branch stay decided (see plan header).
5. No GitHub Environment approval gate until the owner creates that Environment.
6. Cookie/`FLASK_SECRET_KEY` rotation is Azure-only, not git.

## Next action

Phase 1 leftovers on current `main`: deploy-job `if: github.ref == 'refs/heads/main'`; job timeouts; v3 security headers; refuse `DEV_BYPASS_AUTH` on Azure/`APP_ENV=prod`; OData `_scope_tab` fail-closed + tests. Then Phase 2 (Entra `get_by_email`, stop boot `seed_users_from_live`, magic-link hashes).
