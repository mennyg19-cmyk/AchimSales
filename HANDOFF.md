# Session Handoff

Last updated: 2026-09-04 (leftover PR #35; idle default overridden)

**Status:** Draft PR #35 on `cursor/pr1-on-main-551b`. Do not merge until Phase 10. Do not merge leftover PR #1. Phase 9.3 hygiene is in progress.

## Working tree

- **Branch:** `cursor/pr1-on-main-551b`
- **Repo:** AchimSales (`mennyg19-cmyk/AchimSales`)
- **Prod URL:** https://reports.achimonline.com (Azure deploys **only** from `main`)
- **Draft PR:** https://github.com/mennyg19-cmyk/AchimSales/pull/35
- **Old PR #1:** https://github.com/mennyg19-cmyk/AchimSales/pull/1 — leave open; do not merge

## Authoritative files

| Path | Role |
|------|------|
| `PR1-REMEDIATION-PLAN.md` | Leftover worklist (`webapp-cache` in later sections means `main`) |
| `REPOSITORY-REVIEW.md` | Historical snapshot; remaining work is the plan |
| `DECISION-LOG.md` | Newest-first; older entries in `DECISION-LOG-ARCHIVE.md` |
| `.scratch/run-state.md` | Gate checkpoint (gitignored) |
| `.scratch/phase-plan.md` | Expectation checklist (gitignored) |
| `.scratch/phase-93-worklist.md` | Phase 9.3 implementation list (gitignored) |

## Locked for this PR

1. Keep every product feature from PRs #11–#33 and later `main` catch-up.
2. Do not delete `webapp/`, `rebuild/`, `/legacy`, `/test`, or `/test-next` until those jobs are migrated.
3. Delivery-legs stays `0021`. Keep HTTP-only Gunicorn, GraphTokenCache, no tenant SharePoint search.
4. Q1–Q11 stay decided. Q8 and Q9 are BLOCKED (do not invent).
5. No GitHub Environment approval gate until the owner creates that Environment.
6. Cookie/`FLASK_SECRET_KEY` rotation is Azure-only, not git.

## What’s left (non-blocked vs blocked)

- **Doing now:** Phase 9.3 docs/hygiene (env template, stale comments, gitignore, `git diff --check`, artifact builder, `deploy.ps1`, hashed pip, static_dist verification, CI allowlist).
- **Blocked / owner:** Q8 external-recipient; Q9 Send now vs require-edit; Phase 7 replica drop (waits on `/test`); Phase 9.1 archive parity; Phase 9.2 Azure Automation verify; Phase 10 merge.
- **Optional after 9.3:** fuller Phase 8 browser matrix (5 roles × 4 widths × 4 themes).

## Next action

Finish Phase 9.3, one A/B/C review, keep draft. Do not idle; do not merge.
