# Session Handoff

Last updated: 2026-09-04 (Azure Automation dropped from leftover)

**Status:** Draft PR #35 on `cursor/pr1-on-main-551b`. Do not merge until Phase 10. Do not merge leftover PR #1. Azure deploys **only** from `main`. Production `/test` is the same commit as `/`, not this branch.

## Working tree

- **Branch:** `cursor/pr1-on-main-551b`
- **Repo:** AchimSales (`mennyg19-cmyk/AchimSales`)
- **Prod URL:** https://reports.achimonline.com
- **Draft PR:** https://github.com/mennyg19-cmyk/AchimSales/pull/35
- **Old PR #1:** https://github.com/mennyg19-cmyk/AchimSales/pull/1 — leave open; do not merge

## Locked for this PR

1. Keep every product feature from PRs #11–#33 and later `main` catch-up.
2. Do not delete `webapp/`, `rebuild/`, `/legacy`, `/test`, or `/test-next` until those jobs are migrated.
3. Delivery-legs stays `0021`. Keep HTTP-only Gunicorn, GraphTokenCache, no tenant SharePoint search.
4. Q1–Q7 and Q10–Q11 stay decided. Q8 still needs the “external” rule locked. Q9 is adopted (view-only managers may Send now) but not coded.
5. No GitHub Environment approval gate until the owner creates that Environment.
6. Cookie/`FLASK_SECRET_KEY` rotation is Azure-only, not git.
7. Do not run `python -m tools.parity` against live `/` vs `/test` cookies.
8. Do not invent XLSX goldens.
9. Azure Automation is not a go-live path.

## What’s left

- **Code on this branch:** Q8 approve-external recipients (needs one definition); Q9 loosen company Send now to view-only managers.
- **Owner/Azure, not git:** Phase 7 `BETA_*`→`SITE_*` and unmount `/test`; cookie rotation; Phase 10 merge.
- **Optional:** signed sample workbooks for value parity.
- **Live preview of this PR:** needs an Azure **deployment slot** + publish-profile secret. Production `/test` cannot serve a different git commit.

## Next action

Wait for owner: Q8 “external” definition, and whether to create an Azure slot for a preview URL. Then implement Q8/Q9. Keep draft. Do not merge. Do not deploy this branch to the Production slot.
