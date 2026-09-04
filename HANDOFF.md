# Session Handoff

Last updated: 2026-09-04 (Q8/Q9 Loop A green, Loop B F2 deferred, Loop C next)

**Status:** Draft PR #35 on `cursor/pr1-on-main-551b`. Do not merge. Do not deploy this branch to Production.

## Working tree

- **Branch:** `cursor/pr1-on-main-551b`
- **Draft PR:** https://github.com/mennyg19-cmyk/AchimSales/pull/35
- **Prod URL:** https://reports.achimonline.com (deploys only from `main`)

## Locked

Q8: only admin/developer add external People rows; magic link on v3 `users` (`is_external` + active). Q9: view-only managers may Send now (trigger only; company report scope stays schedule `run_as`/owner). Azure Automation is not a go-live path. No slot until Standard S1+. No cookie rotation in git. Mounts stay.

## What’s left until cutover (code vs Azure)

- Q8/Q9 Loop C + premier trust-boundary.
- Phase 7 Azure `BETA_*`→`SITE_*` / unmount `/test`.
- Cookie rotation; Phase 10 merge.
- Optional: owner sample workbooks; Azure slot after S1 upgrade.

## Next action

Loop C then Fable/Sol trust-boundary. Keep draft. No merge.
