# Session Handoff

Last updated: 2026-09-08 (access-log review skipped: no logs)

**Status:** Draft PR #35 on `cursor/pr1-on-main-551b`. Do not merge. Do not deploy this branch to Production.

## Working tree

- **Branch:** `cursor/pr1-on-main-551b`
- **Draft PR:** https://github.com/mennyg19-cmyk/AchimSales/pull/35
- **Prod URL:** https://reports.achimonline.com (deploys only from `main`)

## Locked

Q8/Q9 as before. Home (`BETA_*`) is the live data. `/test` stays. Azure Automation is not a go-live path. No slot until Standard S1+. Mounts stay. Cookie rotation is done (31 Aug, after the 12 Aug leak). Access-log review skipped (no logs).

## What’s left until cutover

- People: owner confirmed.
- Azure `PUBLIC_BASE_URL`: owner confirmed.
- `SITE_*` / `/test` DB compare and unmount: skipped for now.
- Cookie rotation: owner-confirmed 31 Aug 2026 (after 12 Aug leak). Do not rotate again.
- Access-log review: skipped (no logs).
- Live Litestream empty-disk drill: still owner, not on live B1 without a slot.
- Phase 10: whole-branch review, then owner says merge to `main`.

## Next action

Owner skips or schedules the live empty-disk restore drill. Do not wipe Production sqlite from chat. Keep draft. No merge.
