# Session Handoff

Last updated: 2026-08-28

**Status:** Draft PR #1. v3 is the only site. CI green on `8896033`. Do not merge to `webapp-cache`. Do not deploy Production.

## What's done

- P0.1–P0.5 and review security (P0.1 history rewrite still owner-blocked).
- Rollback tag `archive/pre-cleanup-2026-08-27` = `b14d725`.
- `webapp/` and `rebuild/` deleted; v3 owns Entra, magic links, OData, report-source map.
- Settings copy is "Report data sources". Test Site nav, order-entry flag, and the "v3" pill are gone.
- Prod hides `*.map`. Azure Production build runs `tools/run-p0-tests.sh`.

## What's next

1. Owner: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure; approve history rewrite if the cookie blob must leave git history.
2. Remaining product backlog (not this PR): scheduling delivery redesign, a11y, commission/name rules, Run now vs Send now.
3. Do not flip `is_beta` to False (`BETA_PRECIOUS_DB_PATH` + `session` cookie).
4. Do not merge this branch to `webapp-cache`.

## Open decisions

Unchanged from the repository review. In-app Live email distributions were not ported; Automation runbooks still send.

## Gotchas

- Rollback: `git checkout archive/pre-cleanup-2026-08-27`
- Do not print cookie values.
- Do not delete `reports/`, `core/`, `data/`, `runbooks/`.
- Do not add a repo `.semgrepignore`.
- Full v3 pytest: 3 tests still expect 403 and get 401 when the session user has no DB row / is a salesman using a raw session. Not in the P0 CI list.
