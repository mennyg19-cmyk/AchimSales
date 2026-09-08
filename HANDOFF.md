# Session Handoff

Last updated: 2026-09-08 (REPORT-TAB-HANDOFF.md; leftover merge paused)

**Status:** Draft PR #35 on `cursor/pr1-on-main-551b`. Do not merge. Do not deploy this branch to Production. Live restore drill skipped (no slot).

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
- Live Litestream empty-disk drill: skipped (no slot; do not wipe Production).
- Presentation vs leftover: see `REPORT-TAB-HANDOFF.md`. Phase 10 merge is paused.

## Next action

Owner/DBA use `REPORT-TAB-HANDOFF.md` (tab math vs SQL vs grid). Do not merge PR #35. Do not deploy over production.
