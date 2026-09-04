# Repository Review and Cleanup Plan

> Historical snapshot of `330d1bc` from 2026-08-27. Live remaining work is
> tracked in `PR1-REMEDIATION-PLAN.md`.

Reviewed revision: `330d1bc` (`webapp-cache`, identical to `origin/webapp-cache` on 2026-08-27)

Status: historical review findings. Implementation status below is current as of
2026-09-04. Phase 9.3 hygiene is on this leftover branch; Phase 10 merge is not.

## Implementation status (2026-09-01)

| Original item | Status |
|---------------|--------|
| P0.1 tracked production cookies | Phase 1 — file untracked; rotation owner-confirmed; access-log review still BLOCKED |
| P0.2 `cursor/**` Production deploys | Phase 1.1 — Action is `main` only |
| P0.3 OData salesman scope leak | Phase 3 — no OData under `v3/`; SQL only |
| P0.4 Litestream empty-disk / wrong replica | Phase 7 repo gate closed; live Azure empty-disk drill BLOCKED |
| P0.5 production `DEV_BYPASS_AUTH` | Phase 2 — prod refuses dev auth |
| Session/auth DB-authoritative | Phase 2 |
| Flask HTTP-only + worker process | Phase 4 |
| Delivery crash / unknown mail | Phase 5 |
| Report math (commission, Ordered identity, dates) | Phase 6 + Q1–Q11 |
| UI/accessibility | Phase 8 closed |
| Report/feature parity vs archive | Phase 9 (`REPORT-PARITY.md`) |
| Docs, artifact, hashed deps, `git diff --check` | Phase 9.3 — this branch; see `PR1-REMEDIATION-PLAN.md` |
| Merge / Production verify | Phase 10; owner approval required |

**Still owner BLOCKED:** GitHub Environment `production` required reviewers; access-log review; live Litestream drill; `LIVE_DB_PATH` import evidence; Production merge/deploy.

`is_beta=True` stays (README Rule Preferences). `/beta` 302 stays until cutover (Q7). In-app email distributions stay retired (Q6).

## Historical snapshot

### Original required outcome

- Keep one web site only: the current site served at `/`, formerly called Beta.
- Remove the **Beta** pill from the top-left header.
- Stop treating the root site as a preview. Rename or remove `is_beta` behavior without changing the current root site's visible features.
- Retire `/legacy`, `/test`, `/test-next`, and the old `/beta` compatibility surface after their required dependencies are migrated.
- Preserve the pre-cleanup implementation in Git before deleting it.
- Remove obsolete test artifacts, review artifacts, build output, old site code, dead report code, duplicate scripts, logs, caches, generated files, and stale documentation.
- Keep tests, report engines, runbooks, and generated assets that the surviving root site or Azure Automation still needs.

## Non-negotiable cleanup sequence

1. Commit the pre-cleanup state. This report commit is the first preservation point; create and push an annotated archive tag at the final pre-deletion commit, for example `archive/pre-single-site-2026-08-27`.
2. Verify the archive can restore `webapp/`, `rebuild/`, and all deleted files.
3. Produce a deletion report before deleting anything. For every path list what it is, why it exists, why it is unused, and what proves the root site does not need it.
4. Get explicit approval for that exact deletion list.
5. Migrate required auth and active features into the root v3 app.
6. Prove the root app works independently, with no imports, redirects, sessions, templates, background workers, or data reads from the retired web apps.
7. Unmount old routes.
8. Delete approved old code and junk.
9. Update deployment, startup, environment templates, documentation, CI, and `.gitignore`.
10. Run the full review and production-parity gates before merging to the production branch.

Do not delete `webapp/` first. The current `/` app still depends on it for Microsoft login, external magic links, the shared session, user-directory mirroring, hybrid OData execution, and some legacy-only operations. Those dependencies must be migrated or explicitly retired first.

## Immediate security containment

### P0.1 Revoke committed production sessions

- `.scratch/parity-cookies.env` is tracked in Git since commit `f286ce2`.
- It reportedly contains two production session-cookie values.
- Their current validity was not tested. Treat them as compromised.
- Revoke both sessions, review access logs, remove the file from the index and Git history, and add a dedicated secret-scanning rule.
- Never print, copy, or replay the values during cleanup.

### P0.2 Stop Cloud Agent branches deploying Production

- `.github/workflows/webapp-cache_achim-sales-reports.yml` deploys every `cursor/**` branch directly to the Azure Production slot.
- Remove that wildcard.
- Agent branches should run CI or deploy to an isolated staging slot.
- Production should deploy only from a protected, reviewed branch through an approved environment.

### P0.3 Disable OData reports for scoped users

- `v3/web/reporting/odata_bridge.py::_scope_tab` returns an entire workbook tab when it cannot find a salesman column.
- Ordered **By Item** is aggregated without salesman/customer context.
- A scoped salesman can therefore receive company-wide rows on hybrid OData reports.
- Scope data before aggregation and fail closed when a tab cannot prove its scope.

### P0.4 Make persistence fail safe

- v3 validates `LITESTREAM_BLOB_URL`.
- `startup.sh` actually activates Litestream using `LITESTREAM_AZURE_ACCOUNT_KEY` and other `LITESTREAM_AZURE_*` settings.
- Restore failure is logged and ignored; the app can create a new empty production database while `/healthz` stays green.
- Validate the settings actually consumed, require restore success after cutover, and keep readiness red when durable state is unavailable.

### P0.5 Reject production dev bypass

- Legacy accepts `DEV_BYPASS_AUTH=true` in production.
- `/legacy/dev-login` can then create an unauthenticated admin session which the root app adopts.
- Production boot must refuse this setting.

## Confirmed security and authorization defects

1. Legacy authorization trusts role and developer flags stored in the session. Demoted/deleted developers retain access until their cookie expires or is cleared.
2. Beta-to-v3 salesman synchronization adds grants but does not remove revoked grants.
3. v3 developer routes sometimes inspect the session role instead of the central DB-resolved authorization layer.
4. Disabled v3 users remain logged in globally; owner-only routes can still change some preferences and schedule state.
5. `/legacy/report/download-file` accepts a caller-supplied server path, checks only a string prefix and `.xlsx`, and performs no owner/report/salesman authorization.
6. Legacy customer/order access fails open when customer authorization data is missing.
7. Managers have no single salesman key, so one legacy order-detail path can skip manager-grant enforcement.
8. Legacy order/customer APIs expose arbitrary customer addresses and prices to any logged-in user and allow global address writes without customer scope checks.
9. Legacy report history inserts workbook values into `innerHTML`, allowing stored XSS from D365/report data.
10. v3 notification diagnostics and several legacy admin/order screens contain additional unescaped `innerHTML` sinks.
11. Legacy workbook writers do not neutralize spreadsheet formula leaders such as `=`, `+`, `-`, and `@`.
12. `GET /api/reports/diagnostics/precious-repair` can delete queued jobs or drop/recreate the jobs table. GET is exempt from CSRF.
13. Legacy has no application-wide CSRF middleware. `SameSite=Lax` reduces ordinary cross-site POST risk but is not a complete control.
14. Magic-link requests have no per-IP or per-account throttling.
15. Magic-link redemption is not one atomic conditional claim.
16. Multiple unconsumed magic links remain valid for the same account.
17. Magic-link consumption does not re-check that the account is still an external salesman.
18. Magic-link URLs are built from the request host. Azure rejected an arbitrary Host during this review, so this is defense-in-depth rather than a demonstrated live exploit.
19. No CSP, HSTS, frame protection, MIME-sniffing protection, Referrer-Policy, or Permissions-Policy was present in the live login response.
20. Browser dependencies load from third-party CDNs without SRI or a local fallback.

## Confirmed report and business-function defects

1. Hybrid OData scoping fails open per tab.
2. **Keep this run** stores an alias to a mutable cache row, not an immutable run snapshot.
3. Kept results disappear with disposable cache storage after recycle.
4. Cache keys omit SQL/OData provenance, so an identical run can overwrite a kept result from another source.
5. Invalid custom dates silently remove requested bounds and can run an open/default range.
6. `NaN` and `Infinity` can enter non-standard cache JSON.
7. Seeded `/test` schedules use `period="month"` and `period="week"`; the active parser rejects both values.
8. `/test` seeds schedules active while schedule test mode defaults off, creating duplicate or misdirected delivery risk after a fresh database.
9. Commission normalization treats exactly `1` as 100%, while values over `1` are divided by 100.
10. If commission rates vary during the year, the highest rate is applied to every month.
11. Ordered Summary groups by customer name rather than CustomerAccount, merging different accounts with the same name.
12. Legacy invoiced salesman fallback fetches orders created inside the invoice window even though invoices can post long after order creation.
13. Rebuild uses server-local `date.today()` where the root v3 app uses Eastern business dates.
14. Schedule history labels repeated tab/window/fan-out display rows as generic `rows`, not source facts.
15. Mail-unavailable mode records an `.eml` outbox artifact as successful delivery even though no recipient received it.
16. An explicitly selected salesman with no email is skipped without failing the schedule.
17. Hebcal failure permits sends during Shabbos/Yom Tov. This is an accepted policy today but needs explicit owner confirmation.

Commission-rate units, effective dates, duplicate customer names, and historical salesman assignment are business rules. Inspect production samples and get owner sign-off before changing their calculations.

## Scheduling and delivery defects

1. Cancelling a running v3 job changes only database status. The worker can still write cache/audit data, upload files, or send mail.
2. Catch-up state is cleared before enqueue/execution succeeds. Queue errors, crashes, cancellations, and delivery failure can erase an owed send.
3. Manual **Run now** writes normal run history and can suppress the real scheduled run later that day.
4. Daily/rolling catch-up can emit both a widened catch-up workbook and a regular workbook whose date interval is already covered.
5. Whole-delivery retries repeat successful email legs when a later fan-out or SharePoint leg fails.
6. A Graph send accepted just before a local DB failure has unknown outcome and is replayed.
7. Graph mail/upload code does not fully honor `Retry-After`, resume interrupted uploads, or handle throttling.
8. Two hung v3 jobs occupy all worker capacity indefinitely.
9. Legacy report runs and dashboard refreshes can create unbounded daemon threads.
10. Legacy dashboard refresh starts once per gunicorn worker; its process-local guard does not elect one owner across workers.
11. v3 background ownership uses one module-global lock handle even though `/` and `/test` create separate v3 app instances and lock paths. Replace it with lock ownership keyed by app/database.

Required redesign:

- Persist each delivery leg and its remote outcome.
- Use deterministic delivery/attempt IDs.
- Retry only known-safe failed legs.
- Add cooperative cancellation before cache publication and every external effect.
- Separate scheduled-slot claims from manual run history.
- Change catch-up state and queue insertion atomically; clear only after a settled outcome.

## Reliability, CI, and deployment defects

1. The Production workflow runs no pytest, frontend build, TypeScript check, lint, format, migration smoke, artifact verification, or authenticated post-deploy smoke.
2. The separate guardrail workflow does not gate `webapp-cache` or `cursor/**`; no successful guardrail run was found.
3. `/healthz` always returns HTTP 200 without checking bootstrap, schema, DB, worker, scheduler, or Litestream.
4. Migration, seeding, worker, and scheduler startup run asynchronously; failures leave the app mounted and apparently healthy.
5. v3 cache and export prune methods exist but no production caller invokes them.
6. Master exports are configured never to expire.
7. Large reports create full payload, JSON, workbook, SQLite BLOB, and MIME/base64 copies on a small B1 instance.
8. Legacy SQLite uses WAL on `/home` Azure Files/SMB despite recorded WAL-on-SMB corruption and visibility failures.
9. Legacy schema changes are boot-time, partially committed, and have no migration ledger.
10. There is no tested empty-disk restore, corrupt-replica fallback, rollback procedure, staging promotion, RPO, or RTO.
11. CI and manual deployment build different artifact contents.
12. CI uploads most of the repository instead of an allowlisted runtime artifact.
13. Python requirements use floating ranges; CI/runtime Python minors differ.
14. Most GitHub Actions and the Semgrep image use movable tags.
15. `startup.sh` downloads a Litestream executable without checksum verification.
16. Tests rely on convention rather than an enforced outbound-network block.
17. One salesman workbook test skips when the ignored real file is unavailable.
18. Thread tests depend on real sleeps and can become flaky.
19. Queue age, scheduler tick, Litestream lag, disk, memory, Graph throttling, and report latency are not monitored.
20. Static assets are served with `Cache-Control: no-cache`; source maps are publicly accessible in production.

## UI, UX, and accessibility defects

1. Mobile pinch zoom is disabled in both current and legacy shells.
2. Report email/schedule dialogs do not provide full initial focus, focus trap, Escape behavior, background isolation, or focus restoration.
3. Admin modals lack complete dialog semantics and accessible close names.
4. Global help and external-login popups are incomplete dialogs.
5. Reusable searchable pickers are not complete keyboard/ARIA comboboxes.
6. Report tabs have no tablist/tab/tabpanel semantics or arrow-key behavior.
7. Export/More menus declare menu roles but do not implement menu keyboard behavior.
8. Async report status, errors, jobs, and dashboard refreshes are not announced to assistive technology.
9. Toggle switches lack accessible names, strong focus indication, and adequate touch size.
10. Several search controls use placeholders as their only labels.
11. Many frequent controls are smaller than the 44px touch-target floor.
12. Active navigation lacks `aria-current`.
13. Customer Last Order marks navigation links as listbox options incorrectly.
14. Database cells and action columns lack useful accessible names.
15. Error styling references undefined `--danger` instead of `--error`.
16. Multiple text/token combinations fail 4.5:1 contrast; measured ratios go as low as 1.35:1.
17. There is no `prefers-reduced-motion` path.
18. Company and personal schedule management remain wide tables on phones.
19. Admin/dashboard/rebuild tables have weak narrow-screen behavior.
20. Critical UI dependencies are synchronous third-party requests.
21. Notification and job polling continue in hidden tabs without backoff.
22. Report-page and schedule-page schedule creation are different flows with different capabilities.
23. User-facing vocabulary alternates between **presets**, **Saved views**, and **My views**.
24. Report back links always go to Reports instead of the user's actual origin.
25. **Run now** immediately sends and bypasses Shabbos restrictions. Consider renaming to **Send now** and showing a confirmation summary with recipients, destination, test mode, scope, and schedule name.
26. Admin access saves can partially fail and still reload as if successful.
27. Several optimistic settings toggles fail silently.
28. Database Explorer edits immediately with no undo and weak save/error feedback.

## Required single-site migration

### Canonical target

- Surviving application: current v3 root site at `/`.
- Preserve its current report list, hybrid source behavior if still approved, saved/default/company views, schedules, recent reports, settings, and role behavior.
- Remove the header Beta pill in `v3/web/templates/base.html`.
- Replace preview naming (`is_beta`, beta-specific configuration/source modules) with primary-site naming only where behavior remains active.
- Do not accidentally turn on `/test`-only dashboard/auth/session behavior when removing `is_beta`.

### Dependencies that must move before deleting legacy

1. Microsoft Entra login start and callback.
2. External-salesman magic links.
3. Authoritative user directory and immediate role/revocation checks.
4. Shared-session adoption behavior, replaced with native root authentication.
5. Any retained email distribution functionality.
6. Any retained runbook/Azure history or diagnostics.
7. Hybrid OData report execution currently reached through `webapp.report_api`.
8. Any dashboard or settings data that exists only in legacy SQLite.

### Routes to remove after migration

- `/legacy` and all descendants.
- `/test` and all descendants.
- `/test-next` and all descendants.
- `/beta` compatibility redirects unless the owner explicitly needs old bookmarks redirected to `/`.
- Root dispatch logic whose only purpose is choosing among app generations.

### Code candidates after dependency proof

- `webapp/` web routes, templates, static assets, auth/session glue, and retired DB code.
- `rebuild/` after harvesting approved fixes and proving no rebuild-only feature remains.
- v3 `/test`-only mounting, session-cookie, seed, source, and environment paths.
- `wsgi_dispatch.py` and multi-app assembly in `wsgi.py`.
- Dead Beta access gate/module and tests.
- Disabled order-entry vertical slice: blueprint, API routes, DB CRUD/schema drops, D365 helpers, template, JavaScript, styles, and feature flag.

Do not delete `reports/`, `core/`, `data/`, `runbooks/`, or their tests merely because they look old. README says they still power the local CLI and Azure Automation. Remove them only after their production use is replaced and verified.

## Junk and artifact cleanup todo

The next agent must inventory tracked and untracked candidates and present an exact deletion report before removal.

### Candidate categories

- `.pytest_cache/`, `__pycache__/`, `*.pyc`, coverage output, temporary test output.
- `.scratch/` outputs, parity exports, probes, cookie files, temporary scripts, and stale run-state files.
- `.data/`, outbox `.eml`, local SQLite/WAL files, report exports, and downloaded logs.
- `node_modules/`, package-manager caches, source maps, and generated frontend output that CI can reproducibly rebuild.
- `v3/REVIEW-LOG.md`, completed review-pass artifacts, stale summaries, old plans, proposals, debate logs, inventories, and build histories after preserving needed decisions.
- `rebuild/rebuild-audit/`, `rebuild/proposals/`, preview-only plans, and preview tests after the rebuild is retired.
- Tests whose only subject is deleted code.
- Legacy web templates/static files after route retirement.
- Duplicate deploy scripts and obsolete workflow/config variants.
- Old output directories, sample exports, debug JSON/CSV/XLSX, logs, screenshots, and recordings.
- Dead report modules, adapters, reconciliation scripts, or fixtures proven to have no current web, CLI, runbook, parity, or migration caller.
- README directory listings and environment documentation that describe removed generations.

### Files that are not junk by default

- Business-rule regression tests for the surviving app.
- Report calculation tests.
- Security/scope/cancellation/delivery tests.
- `TESTING-STRATEGY.md` until its active requirements are migrated into maintained tests/docs.
- Current v3 templates, TypeScript, styles, migrations, repositories, and report engine.
- CLI/runbook report code and tests while Azure Automation still uses them.
- `static_dist` until the production workflow builds and packages frontend assets itself.
- Historical decisions that define current business calculations; summarize those before deleting old logs.

### `.gitignore` corrections

- Ignore `.env*` while explicitly keeping `.env.example` files.
- Ignore `node_modules/`.
- Ignore `.data/` and nested outboxes.
- Keep `.scratch/` ignored and verify no tracked scratch files remain.
- Ignore local coverage, test-report, browser-artifact, and generated log directories.
- Add targeted patterns for parity cookies and session exports.

## Refactor plan after containment

Do not start file moves until security, CI, readiness, and delivery guarantees are fixed.

1. Delete the retired order-entry slice instead of refactoring it.
2. Split `v3/web/blueprints/reports.py` into report jobs/results, Customer Last Order, saved/company/default views, delivery/folders, and admin diagnostics.
3. Split `v3/web/static_src/js/report.ts` into viewer/grid, filters, views, jobs/exports, and delivery/scheduling modules.
4. Split `v3/web/blueprints/schedules.py` into personal and company schedule routes plus shared validation.
5. Split `v3/web/__init__.py` into app factory, service wiring, context, bootstrap/background ownership, and canonical seeds.
6. Split `v3/web/static_src/css/pages.css` by page bundle.
7. Move destructive diagnostics out of report routes.
8. Replace hardcoded schedule seeds with validated declarative data outside app assembly.
9. Keep existing scoped cache and repository transaction patterns; do not introduce a DI framework or generic repository base.
10. Do not make a shared abstraction across web generations that are about to be deleted.

## Release gate for the cleanup

- Credential leak contained.
- Agent branches cannot deploy Production.
- Production workflow runs locked Python install, all surviving pytest suites, strict TypeScript checking, frontend build, lint/format/security scans, generated-output check, and WSGI import.
- Root app starts without importing or mounting `webapp` or `rebuild`.
- Root owns login, callback, external auth, user revocation, and CSRF.
- Every scoped report, including every tab and export, is proven salesman-safe.
- Every schedule performs exactly one intended delivery under partial failure, cancellation, retry, catch-up, and manual-run scenarios.
- Empty-disk Litestream restore is tested; restore failure leaves readiness red.
- Health distinguishes liveness from readiness.
- Browser verification covers all roles with seeded data.
- Accessibility pass covers keyboard, screen reader, 200% zoom, four themes, reduced motion, and phone layouts.
- Old-route requests return the chosen final behavior: 404/410, or explicit redirects approved for bookmarks.
- Deletion inventory is fully approved and all listed paths are gone.
- Archive tag and previous commit restore deleted code successfully.
- Production deploy is observed green and the live `/` flow is verified after promotion.

## Review evidence

- Public production `/healthz` returned HTTP 200.
- Public login rendered successfully.
- Live response headers lacked the security headers listed above.
- A production source map returned HTTP 200.
- The latest Azure deployment workflow was green, but that workflow has no behavioral test gate.
- 792 test functions were identified across 63 files.
- Tests could not run in this Cloud environment because project dependencies and pytest were absent.
- Generated JavaScript syntax, `startup.sh` syntax, and `git diff --check` passed.
- `npm audit` found Moderate advisory GHSA-67mh-4wv8-2f99 for locked esbuild 0.23.1.
- Working tree was clean before this report was added.

## Detailed specialist reports

The original full reports are currently under ignored `.scratch/` paths:

- `.scratch/review-functionality.md`
- `.scratch/review-security.md`
- `.scratch/review-ui-ux.md`
- `.scratch/review-architecture.md`
- `.scratch/review-operations.md`

Their findings have been consolidated into this tracked document so the next agent does not depend on ignored local artifacts.
