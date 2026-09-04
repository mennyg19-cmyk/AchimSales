# Session Handoff

Last updated: 2026-09-04 (Phase 9.1 code-level parity done)

**Status:** Draft PR #35 on `cursor/pr1-on-main-551b`. Phase 9.3 closed on `232866c`. Do not merge until Phase 10. Do not merge leftover PR #1.

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
| `REPORT-PARITY.md` | Archive-vs-v3 inventory, tab/column, totals/export/role-scope |
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

## What’s left

- **Next leftover:** Phase 9.2 — document which old routes/tests/tools/docs are still required for support/recovery (mounts stay). Azure Automation send-verify is owner/ops.
- **9.1 value goldens:** BLOCKED on owner sample workbooks. Code-level inventory + tab/column + totals/export/role-scope are in `REPORT-PARITY.md`.
- **9.1 unknowns (do not invent):** Ordered shipping/remainder; Number 4 By Item dollars; Last Order invoiced vs open; Customer Activity count footer; Salesman percent footer.
- **Blocked / owner:** Q8, Q9, Phase 7 replica drop, 9.2 Azure Automation verify, Phase 10 merge, 9.1 frozen goldens.
- **Optional:** fuller Phase 8 browser matrix (5 roles × 4 widths × 4 themes).

## Next action

Commit totals/export compare, then Phase 9.2 support/recovery inventory. Keep draft. Do not merge.
