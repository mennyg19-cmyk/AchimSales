# Session Handoff

Last updated: 2026-09-04 (leftover engineering unblocked is done)

**Status:** Draft PR #35 on `cursor/pr1-on-main-551b`. Do not merge until Phase 10. Do not merge leftover PR #1.

## Working tree

- **Branch:** `cursor/pr1-on-main-551b`
- **Repo:** AchimSales (`mennyg19-cmyk/AchimSales`)
- **Prod URL:** https://reports.achimonline.com (Azure deploys **only** from `main`)
- **Draft PR:** https://github.com/mennyg19-cmyk/AchimSales/pull/35
- **Old PR #1:** https://github.com/mennyg19-cmyk/AchimSales/pull/1 — leave open; do not merge
- **Isolated archive:** `/tmp/achim-archive-pre-cleanup` at tag `archive/pre-cleanup-2026-08-27` (peels to `b14d725`)

## Authoritative files

| Path | Role |
|------|------|
| `PR1-REMEDIATION-PLAN.md` | Leftover worklist (`webapp-cache` in later sections means `main`) |
| `REPORT-PARITY.md` | Archive-vs-v3 code-level parity |
| `REPOSITORY-REVIEW.md` | Historical snapshot; remaining work is the plan |
| `DECISION-LOG.md` | Newest-first; older entries in `DECISION-LOG-ARCHIVE.md` |
| `.scratch/run-state.md` | Gate checkpoint (gitignored) |
| `.scratch/phase-plan.md` | Expectation checklist (gitignored) |

## Locked for this PR

1. Keep every product feature from PRs #11–#33 and later `main` catch-up.
2. Do not delete `webapp/`, `rebuild/`, `/legacy`, `/test`, or `/test-next` until those jobs are migrated.
3. Delivery-legs stays `0021`. Keep HTTP-only Gunicorn, GraphTokenCache, no tenant SharePoint search.
4. Q1–Q11 stay decided. Q8 and Q9 are BLOCKED (do not invent).
5. No GitHub Environment approval gate until the owner creates that Environment.
6. Cookie/`FLASK_SECRET_KEY` rotation is Azure-only, not git.
7. Do not run `python -m tools.parity` against live `/` vs `/test` cookies.
8. Do not invent XLSX goldens.

## What’s left (owner / blocked)

- Q8 external-recipient approval; Q9 company Send now vs require-edit.
- Phase 7 replica drop / `BETA_*`→`SITE_*` / unmount `/test`.
- 9.1 frozen goldens (no in-repo sample workbooks).
- 9.2 Azure Automation send-verify; 9.2 “no old route needed” until mounts drop.
- Cookie rotation; Phase 10 merge to `main`.

Phase 8 remaining listed flows (magic link, live report run, Keep, export, email, Send now) were not part of the bounded overflow matrix and need a live or fixture job if they are still required before go-live.

## Next action

Keep draft. Do not merge. Remaining leftover is owner/blocked or go-live Phase 10.
