# Session Handoff

Last updated: 2026-08-27

**Status:** Owner asked to delete `webapp/` and `rebuild/`. v3 is the only site at `/`. Branch `cursor/p0-security-containment-adb6`.

## What's done

- P0.1–P0.5 and review security.
- Rollback tag `archive/pre-cleanup-2026-08-27` = `b14d725`.
- Junk cleanup (`85ac27e`): untracked `.scratch/`, dropped logs/rebuild audit docs.
- v3 owns Entra, magic links, OData runners, report-source map. Beta pill gone. `/legacy`, `/test`, `/test-next` unmounted. `webapp/` and `rebuild/` removed.

## What's next

1. Owner: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure; approve history rewrite if the cookie must leave git history.
2. Remaining review gates / production merge (not this branch — `cursor/**` does not deploy).
3. Azure App Settings still used: `BETA_PRECIOUS_DB_PATH` (home sqlite), `FLASK_SECRET_KEY`. `BETA_MOUNT_ENABLED` / `V3_MOUNT_ENABLED` / `REBUILD_MOUNT_ENABLED` are unused.

## Open decisions

Unchanged from the repository review (leftover CLI/runbooks, Run now vs Send now, Shabbos fail-open, commission/name rules). In-app Live email distributions were not ported; Automation runbooks still send.

## Gotchas

- Rollback: `git checkout archive/pre-cleanup-2026-08-27`
- Do not print cookie values. History of `webapp-cache` still contains the old blob until rewritten.
- Do not delete `reports/`, `core/`, `data/`, `runbooks/` while Azure Automation uses them.
- Do not add a repo `.semgrepignore`; it replaces Semgrep defaults.
- Home still uses `is_beta=True` so it keeps `BETA_PRECIOUS_DB_PATH` and the `session` cookie name.
