# Session Handoff

Last updated: 2026-09-08 (PUBLIC_BASE_URL set; next SITE_* aliases)

**Status:** Draft PR #35 on `cursor/pr1-on-main-551b`. Do not merge. Do not deploy this branch to Production.

## Working tree

- **Branch:** `cursor/pr1-on-main-551b`
- **Draft PR:** https://github.com/mennyg19-cmyk/AchimSales/pull/35
- **Prod URL:** https://reports.achimonline.com (deploys only from `main`)

## Locked

Q8: only admin/developer add external People rows; magic link on v3 `users` (`is_external` + active). Q9: view-only managers may Send now on **shared** company schedules (trigger only; report scope stays schedule `run_as`/owner). Private masters require owner/run-as/privileged. Azure Automation is not a go-live path. No slot until Standard S1+. No cookie rotation in git. Mounts stay.

## What’s left until cutover (code vs Azure)

- People: owner confirmed.
- Azure `PUBLIC_BASE_URL`: owner confirmed.
- Azure `SITE_*` aliases of `PRECIOUS_*` / `CACHE_*` (this step). Do not copy `BETA_*`.
- Phase 7 unmount `/test`; cookie rotation; Phase 10 merge.
- Optional: owner sample workbooks; Azure slot after S1 upgrade.

## Next action

Owner adds `SITE_PRECIOUS_DB_PATH` and `SITE_CACHE_DB_PATH` as copies of `PRECIOUS_DB_PATH` and `CACHE_DB_PATH`. Keep draft. No merge.
