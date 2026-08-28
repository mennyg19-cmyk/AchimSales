# Session Handoff

Last updated: 2026-08-28

**Status:** Draft PR #1 was re-reviewed at `5b901ac` and is not merge-ready. `PR1-REMEDIATION-PLAN.md` is now the authority for the remaining job. Do not merge to `webapp-cache`. Do not deploy Production.

## What's done

- P0.1–P0.5 except history rewrite / live session revoke.
- Rollback tag `archive/pre-cleanup-2026-08-27` = `b14d725`.
- v3 is the only site at `/`. `is_beta=True` kept (`BETA_PRECIOUS_DB_PATH`, cookie `session`). `Config.reports_only` is an alias.
- Report math: dates fail closed, commission `1` = 1%, monthly rates per month, Ordered Summary by CustomerAccount, Hebcal fail-closed.
- Keep-run snapshot in precious; cache/export prune on the scheduler tick; hung jobs fail after 45 minutes (not requeued).
- Worker handlers run with a Flask app context (OData source map works off the request thread). Cancel is checked after the workbook and before send. Cancelled schedules do not mail a failure notice. `/readyz` is 503 if bootstrap failed. Cancel after cache put drops the row.
- Delivery legs, Send now vs clock slot, Graph Retry-After, explicit salesman with no email fails the schedule. Prod outbox-only is not success.
- UI/a11y items from the review, including Saved views copy and report-page Schedule using the Schedules wizard.
- God-file splits: reports/schedules blueprints, factory seeds/background, pages.css, report.ts (grid/filters/jobs/views/delivery). `runner.py` helpers live in `runner_support.py`.
- Export download re-checks live salesman scope and invoiced Commissions access against the source run (a baked `.xlsx` cannot be narrowed).
- CI: full v3 pytest, root pytest (needs `tests/conftest.py`), tsc, npm build, dist js/css check.
- Empty-disk restore **unit** test in `tests/test_startup_restore.py`. Diagnostics `host.counters` for Graph throttle / last report ms / last tick.
- Precious backup dump quotes `sqlite_master` identifiers (PR Semgrep vs `webapp-cache`).
- Phase review: Loop A green (`76fabd5`), Loop B green (`b49193c`), Loop C green (`b349b96`; report.ts cycles deferred), trust-boundary green (`7f55503`).

## What's next

1. Read `PR1-REMEDIATION-PLAN.md` in full and follow its phases in order.
2. Get the listed owner decisions before changing commission, Hebcal, retained features, redirect, recipient, retention, or timeout policy.
3. Remove every OData path from `v3/`; keep OData only in the separate CLI/Azure Automation path while that path remains active.
4. Move job processing, scheduling, cleanup, and report execution out of Flask/Gunicorn into a separately supervised process.
5. Fix the auth, delivery-crash, SQL report, persistence/readiness, UI/accessibility, and parity blockers in the plan.
6. Owner: rotate `FLASK_SECRET_KEY` / `FLASK_SECRET`; decide the coordinated history rewrite.
7. Run the live Azure empty-disk restore drill and full browser/report parity gates.
8. Do not merge until every Phase 10 gate is complete.

## Open decisions / BLOCKED

- P0.1 history rewrite and live session revoke.
- Production merge/deploy.
- In-app Live email distributions were not ported; Azure Automation still sends.
- Commission unit/effective-rate/display rules.
- Hebcal outage behavior.
- `/beta` redirect lifetime.
- External-recipient and manager company-Send-now policy.
- Retention and hard-timeout policy.
- Pip freeze lockfile (deferred).
- Live Litestream empty-disk drill.

## Gotchas

- Rollback: `git checkout archive/pre-cleanup-2026-08-27`
- Do not print cookie values.
- Do not delete `reports/`, `core/`, `data/`, `runbooks/`.
- “Remove OData from the app” means no OData under `v3/`; retained CLI/Azure Automation may still use it.
- “Workers out of the app” means Flask/Gunicorn starts no worker or scheduler threads; use a separate supervised process.
- Do not treat `pending` delivery legs as proof that Graph/SharePoint accepted anything.
- Do not let old cookies or `/home/data/app.db` create/reactivate users.
- Do not add a repo `.semgrepignore`.
- Root pytest must **not** use `--noconftest` (fixtures live in `tests/conftest.py`).
- Full v3 pytest: `cd v3 && python -m pytest tests -q`.
- Frontend: `cd v3 && npx tsc --noEmit && npm run build` then commit dist js/css.
