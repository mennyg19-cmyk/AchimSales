# Session Handoff

Last updated: 2026-08-28

**Status:** Draft PR #1 implements the remaining REPOSITORY-REVIEW items on `cursor/p0-security-containment-adb6`. Do not merge to `webapp-cache`. Do not deploy Production.

## What's done

- P0.1–P0.5 except history rewrite / live session revoke.
- Rollback tag `archive/pre-cleanup-2026-08-27` = `b14d725`.
- v3 is the only site at `/`. `is_beta=True` kept (`BETA_PRECIOUS_DB_PATH`, cookie `session`). `Config.reports_only` is an alias.
- Report math: dates fail closed, commission `1` = 1%, monthly rates per month, Ordered Summary by CustomerAccount, Hebcal fail-closed.
- Keep-run snapshot in precious; cache/export prune on the scheduler tick; hung jobs fail after 45 minutes (not requeued).
- Worker handlers run with a Flask app context (OData source map works off the request thread). Cancel is checked after the workbook and before send. Cancelled schedules do not mail a failure notice. `/readyz` is 503 if bootstrap failed.
- Delivery legs, Send now vs clock slot, Graph Retry-After, explicit salesman with no email fails the schedule. Prod outbox-only is not success.
- UI/a11y items from the review, including Saved views copy and report-page Schedule using the Schedules wizard.
- God-file splits: reports/schedules blueprints, factory seeds/background, pages.css, report.ts (grid/filters/jobs/views/delivery).
- CI: full v3 pytest, root pytest (needs `tests/conftest.py`), tsc, npm build, dist js/css check.
- Empty-disk restore **unit** test in `tests/test_startup_restore.py`. Diagnostics `host.counters` for Graph throttle / last report ms / last tick.
- Precious backup dump quotes `sqlite_master` identifiers (PR Semgrep vs `webapp-cache`).

## What's next

1. Owner: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET` in Azure; approve history rewrite if the cookie blob must leave git history.
2. Live Azure empty-disk restore drill (not done here).
3. Review loops A/B/C on this phase if not already closed on HEAD after this push.
4. Do not flip `is_beta` to False. Do not merge until you mean to go live.

## Open decisions / BLOCKED

- P0.1 history rewrite and live session revoke.
- Production merge/deploy.
- In-app Live email distributions were not ported; Azure Automation still sends.

## Gotchas

- Rollback: `git checkout archive/pre-cleanup-2026-08-27`
- Do not print cookie values.
- Do not delete `reports/`, `core/`, `data/`, `runbooks/`.
- Do not add a repo `.semgrepignore`.
- Root pytest must **not** use `--noconftest` (fixtures live in `tests/conftest.py`).
- Full v3 pytest: `cd v3 && python -m pytest tests -q`.
- Frontend: `cd v3 && npx tsc --noEmit && npm run build` then commit dist js/css.
