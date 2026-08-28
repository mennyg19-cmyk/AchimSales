# Session Handoff

Last updated: 2026-08-28

**Status:** Draft PR #1. v3 is the only site at `/`. CI was green on `338bd54`; this follow-up gates Azure Production deploys on those same P0 tests.

## What's done

- P0.1–P0.5 and review security (P0.1 history rewrite still owner-blocked).
- Rollback tag `archive/pre-cleanup-2026-08-27` = `b14d725`.
- `webapp/` and `rebuild/` deleted; v3 owns Entra, magic links, OData runners, report-source map.
- Settings copy no longer says "Beta report data sources".
- Azure Production workflow runs `tools/run-p0-tests.sh` plus `compileall` on WSGI/v3 before upload.

## What's next

1. Wait for CI on this follow-up commit.
2. Owner: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure; approve history rewrite if the cookie blob must leave git history.
3. Remaining review gates / production merge (not this branch — `cursor/**` does not deploy).
4. Azure App Settings still used: `BETA_PRECIOUS_DB_PATH`, `FLASK_SECRET_KEY`. Do not flip `is_beta` to False.

## Open decisions

Unchanged from the repository review (leftover CLI/runbooks, Run now vs Send now, Shabbos fail-open, commission/name rules). In-app Live email distributions were not ported; Automation runbooks still send.

## Gotchas

- Rollback: `git checkout archive/pre-cleanup-2026-08-27`
- Do not print cookie values. History of `webapp-cache` still contains the old blob until rewritten.
- Do not delete `reports/`, `core/`, `data/`, `runbooks/` while Azure Automation uses them.
- Do not add a repo `.semgrepignore`; it replaces Semgrep defaults.
- Home still uses `is_beta=True` so it keeps `BETA_PRECIOUS_DB_PATH` and the `session` cookie name.
