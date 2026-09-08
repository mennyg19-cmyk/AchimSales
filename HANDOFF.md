# Session Handoff

Last updated: 2026-09-08 (Flask cookie rotation treated as done)

**Status:** Draft PR #35 on `cursor/pr1-on-main-551b`. Do not merge. Do not deploy this branch to Production.

## Working tree

- **Branch:** `cursor/pr1-on-main-551b`
- **Draft PR:** https://github.com/mennyg19-cmyk/AchimSales/pull/35
- **Prod URL:** https://reports.achimonline.com (deploys only from `main`)

## Locked

Q8/Q9 as before. Home (`BETA_*`) is the live data. `/test` stays. Azure Automation is not a go-live path. No slot until Standard S1+. Mounts stay. Cookie rotation is done (31 Aug, after the 12 Aug leak).

## What’s left until cutover

- People: owner confirmed.
- Azure `PUBLIC_BASE_URL`: owner confirmed.
- `SITE_*` / `/test` DB compare and unmount: skipped for now.
- Cookie rotation: owner-confirmed 31 Aug 2026 (after 12 Aug leak). Do not rotate again.
- Access-log review for 12–31 Aug 2026 (Phase 1.2). Still owner.
- Phase 10: mark draft ready, whole-branch review, merge to `main`.

## Next action

Owner reviews App Service access logs for 12 Aug 2026 21:52 +0300 through 31 Aug 2026 rotation. Keep draft. No merge.
