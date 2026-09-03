# PR #1 instructions on current `main`

**Branch:** `cursor/pr1-on-main-551b`  
**Base:** `main` at `263a76b` (2 Sep 2026 go-live), not `webapp-cache` / PR #1.  
**Do not merge PR #1.** Do not deploy Production from this branch until Phase 10.

This is the same remediation plan as PR #1, replayed on today's site so we keep
PRs #11–#33 (salesman filter, rename, Excel bands, Users & access, review
security). Old sites stay mounted until their jobs are migrated (do not delete
`webapp/` first).

Keep this PR **draft**. Same hard stops as PR #1: no cookie rotation in git,
no editing applied migrations, keep tag `archive/pre-cleanup-2026-08-27`.

## Already on `main` (do not redo)

- Azure Action deploys only `main` (not `cursor/**`).
- v3 CSRF; Excel formula prefix; Litestream URL check in v3 config.
- v3 `AUTH_MODE=dev` forbidden when `APP_ENV=prod`.
- Users & access wins over Live cookie after first login; only DB developers
  mint/disable developers; Add user 409; export re-checks salesman scope.
- Semgrep/gitleaks on `v3/`.

## Still to do (PR #1 leftover, in plan order)

P0 / Phase 1: `workflow_dispatch` must not deploy a non-`main` ref; job
timeouts; security headers; refuse Azure/`APP_ENV=prod` `DEV_BYPASS_AUTH`.
Phase 2: Entra `get_by_email` not `upsert`; stop boot `seed_users_from_live`;
magic-link hashes, rate limits, `PUBLIC_BASE_URL`.
Phase 3: OData fail-closed now; SQL-only v3 only after every built report has
SQL (do not silently drop OData). Then unmount `/legacy` `/test` `/test-next`.
Phases 4–9: HTTP-only Gunicorn + `supervise-web.sh` worker; delivery unknown;
report Q1–Q11 already decided below; persistence fail-safe; a11y; parity vs
archive tag. Phase 10: owner go-live.

## Adopted product answers (Q1–Q11 from PR #1)

Do not re-litigate. Logged 2026-08-28 on the old branch.

1. Commission unit: SP value is a **fraction**; `1` = 100%.
2. Commission rate: **per invoice**; SP zero stays zero.
3. Commission display: salesman table **saved percent**.
4. Ordered Summary groups by **CustomerAccount**.
5. Hebcal down: **hold** unless a saved calendar still covers now; live fetch.
6. In-app email distributions: **stay retired**.
7. `/beta` bookmarks: **keep 302** through cutover.
8. External recipients: users may add; **admin/dev must approve**.
9. Company Send now: **view-only managers may trigger it**.
10. Retention: current TTLs; prune attempts/legs/jobs at **90 days**.
11. Timeout: **45 min** kill; Graph unknown is **not** auto-retried.

## Original plan (worklist)

The sections below are PR #1's phases, unchanged except production branch is
`main` wherever they say `webapp-cache`.

## Required final state

- One web application at `/`.
- No `webapp/`, `rebuild/`, `/legacy`, `/test`, or `/test-next`.
- `/beta` either redirects to `/` or is removed, based on the owner decision below.
- No visible Beta/Test branding.
- The Flask/Gunicorn web process serves HTTP only. It does not start job-worker, scheduler, cleanup, or report-processing threads.
- A separately supervised process owns queued reports, exports, deliveries, schedules, cleanup, and worker heartbeats.
- The web application is SQL/Reporting-API only.
- No OData source selector, OData bridge, OData runner, OData cache-source logic, or OData-specific app tests remain under `v3/`.
- OData may remain only in the separate CLI/Azure Automation implementation under `reports/`, `core/`, `data/`, and `runbooks/` while that production path still exists.
- Every retained report has a working SQL implementation. Missing SQL support blocks removal of its OData fallback; it must not silently fall back.
- Production sessions are revoked, authentication is DB-authoritative, and unknown/deleted users cannot provision themselves.
- Delivery crash behavior is explicit and tested. Do not claim exactly-once email delivery without provider-backed evidence.
- CI, restore, browser, accessibility, report-parity, and Production-readiness gates are complete before merge.

## Terminology

- **Web app:** Flask HTTP process running under Gunicorn.
- **Worker service:** separate non-HTTP process that claims durable jobs and runs reports/exports/deliveries.
- **Scheduler service:** schedule tick and cleanup loop owned by the worker service, not Flask.
- **SQL report:** data comes through the configured Reporting API/stored procedures.
- **OData outside the app:** CLI/Azure Automation may keep using OData. No `v3/` runtime code may import or mention it.

## Hard stops

- Do not merge or deploy Production from this branch.
- Do not rotate or print cookie values in code, logs, commits, or chat.
- Do not edit old migration files already applied in Production. Add forward migrations.
- Do not delete the archive tag `archive/pre-cleanup-2026-08-27`.
- Do not restore deleted web generations into the active application.
- Do not remove CLI/runbook OData code unless the owner separately retires Azure Automation.
- Do not substitute unit tests for the live restore, browser, report-parity, or authenticated smoke gates.
- Do not convert ambiguous business rules into code without the owner decisions below.

## Owner decisions required before report-policy changes

Record each answer in `DECISION-LOG.md` before implementation.

1. **Commission unit:** Does stored-procedure value `1` mean 1% or 100%?
   - Recommended: require one documented unit from the API and reject mixed/ambiguous values.
2. **Commission effective rate:** Use each invoice's rate, each month's effective rate, or one current annual rate?
   - Recommended: per-invoice rate when present; explicit zero must remain zero rather than falling back.
3. **Commission display:** When rates vary, show each month's rate, a weighted rate, “varies,” or the latest effective rate?
   - Recommended: show “varies” at the salesman summary and the actual rate per month.
4. **Ordered Summary identity:** Is CustomerAccount the authoritative customer grouping key?
   - Recommended: yes; display account and name.
5. **Hebcal failure:** Delay all schedule sends until a valid calendar is available, or send when Hebcal is unavailable?
   - Recommended: use a pre-fetched calendar cache; hold and alert only when no valid cached window covers the current instant.
6. **In-app email distributions:** Permanently retire the deleted legacy distribution UI/service, or port a required subset?
   - Recommended: confirm no active operator uses it before accepting removal.
7. **`/beta` bookmarks:** Keep the temporary redirect or return 410/404?
   - Recommended: keep a time-bounded redirect, then remove it.
8. **External recipients:** May ordinary users email scoped reports outside approved company domains?
   - Recommended: approved-domain policy with an audited privileged override.
9. **Company schedule operation:** May a manager who can only view a company schedule trigger **Send now**?
   - Recommended: require the same operate/edit permission used by toggle.
10. **Retention:** Confirm kept-run, export, delivery-leg, magic-link-attempt, and job-history retention.
    - Recommended: kept runs 30 days, one-time exports 7 days, scheduled exports 30 days, master exports 90 days, attempts/legs/jobs under an explicit audit policy.
11. **Timeout behavior:** Confirm the maximum report runtime and what happens to unknown external-send outcomes.
    - Recommended: mark timed-out work cancelled, terminate its child process, and require operator reconciliation for unknown mail outcomes.

## Phase 0 — Preserve state and prepare review evidence

- [ ] Fetch `webapp-cache` and the PR branch.
- [ ] Verify `archive/pre-cleanup-2026-08-27` exists remotely and resolves to `b14d725`.
- [ ] Verify the tag contains `webapp/`, `rebuild/`, and the pre-cleanup tests/tools.
- [ ] Keep the current PR draft.
- [ ] Save the current changed-file and route inventories under `.scratch/`; do not commit generated inventory output.
- [ ] Add a phase checklist under `.scratch/phase-plan.md`.
- [ ] Record the final owner decisions listed above.

Gate:

- Archive restore is proven in an isolated checkout.
- Open product decisions are either answered or marked BLOCKED.
- No implementation begins while a required business decision is unresolved.

## Phase 1 — Close the production deployment and credential gates

### 1.1 Production workflow

- [ ] Keep automatic deployment restricted to `webapp-cache`.
- [ ] Add an `if:` guard that refuses `workflow_dispatch` unless `github.ref == 'refs/heads/webapp-cache'`.
- [ ] Bind the deployment job to a protected GitHub `production` Environment.
- [ ] Require approval for that Environment.
- [ ] Add workflow and job timeouts.
- [ ] Make security, Python, frontend, artifact, and restore-preflight checks dependencies of deploy.

### 1.2 Session incident

Owner/external actions:

- [ ] Rotate `FLASK_SECRET_KEY` and `FLASK_SECRET` in Azure.
- [ ] Confirm old `session` and `v3_session` cookies no longer authenticate.
- [ ] Review access logs from the cookie-file exposure window.
- [ ] Decide whether to rewrite Git history.

Repository actions:

- [ ] Keep `.scratch/parity-cookies.env` untracked.
- [ ] Keep filename/content secret checks on PRs, `cursor/**`, and `webapp-cache`.
- [ ] Do not preserve live cookie values in the archive documentation.

Gate:

- Old cookies are rejected.
- Manual dispatch cannot deploy another ref.
- All required workflow checks are enforced, not merely green.

## Phase 2 — Make authentication single-site and DB-authoritative

### 2.1 Remove legacy-cookie authority

- [ ] Change `beta_live_session.adopt_live_identity()` to lookup-only during the short compatibility window.
- [ ] Never call `UserRepository.create()` from cookie data.
- [ ] Reject unknown, deleted, or inactive cookie identities.
- [ ] Derive role, active state, developer authority, and salesman grants only from current DB rows.
- [ ] Remove `p.is_dev` as an authorization condition from `/dev/role-picker`.
- [ ] Require live `authz.is_developer(p)` for both GET and POST.
- [ ] Update `sync_role` or replace the whole principal when role/developer state changes.
- [ ] After secret rotation, delete `beta_live_session.py`, `session["user"]` compatibility writes, and compatibility tests.

### 2.2 Stop auto-provisioning Entra users

- [ ] In the MSAL callback, use `get_by_email`, not `upsert`.
- [ ] Deny unknown users with a stable unauthorized page/message.
- [ ] Keep user creation in the privileged People administration flow.
- [ ] Re-check active state immediately before session creation.

### 2.3 Retire the old user DB as an authority

- [ ] Convert `/home/data/app.db` import into an explicit one-time migration command.
- [ ] Record a durable migration marker and imported row/grant counts.
- [ ] Verify users, roles, active flags, external flags, and salesman grants.
- [ ] Stop calling `_seed_users_from_live` during normal boot.
- [ ] Delete `LIVE_DB_PATH` and old-DB boot references after migration evidence.

### 2.4 Magic-link hardening

- [ ] Store token hashes, never plaintext tokens.
- [ ] Compare a submitted token by hash in one atomic update.
- [ ] Redact `/login/magic-link/<token>` from access logs.
- [ ] Prune old token and attempt rows.
- [ ] Resolve client IP only through Azure's trusted proxy contract; do not trust arbitrary leftmost `X-Forwarded-For`.

Tests:

- Unknown Entra user denied.
- Deleted legacy-cookie user denied and not recreated.
- Demoted developer cannot open or POST role picker.
- Inactive user denied.
- Impersonating developer loses access immediately when actor is demoted/disabled.
- Rotated secret invalidates old cookies.
- Magic-link DB/logs never contain the bearer token.

Gate:

- There is one identity store.
- Cookie/session fields never grant roles.
- No active code reads the retired legacy DB.

## Phase 3 — Remove all OData from the web application

### 3.1 Prove SQL coverage first

- [ ] Enumerate every `registry.built_reports()` entry.
- [ ] For each built report, identify its Reporting API report ID, parameter translator, adapter, builder, tabs, exports, scope field, and tests.
- [ ] Required reports include Ordered, Invoiced, Salesman, Number 4, Customer Activity, Customer Last Order, Item Averages, Sales by State, and any still-built Customer Aging entry.
- [ ] If a report lacks SQL support, implement and verify it or mark it unavailable only after owner approval.
- [ ] Fix Item Averages immediately: it is built and SQL-backed but currently defaults to unsupported OData.

### 3.2 Make SQL the only execution path

- [ ] Remove source selection from `ReportService.builder_for`.
- [ ] Remove source from cache and dedup key construction.
- [ ] Bump builder/cache namespace versions or clear disposable cache at cutover.
- [ ] Remove source-management routes and Settings controls.
- [ ] Add one forward migration to remove or retire `beta_report_sources`.
- [ ] Do not edit migration `0016_report_sources.sql`.

### 3.3 Delete v3 OData code

- [ ] Delete `v3/web/reporting/odata_bridge.py`.
- [ ] Delete `v3/web/reporting/odata_run.py`.
- [ ] Delete `v3/web/beta_sources.py`.
- [ ] Remove OData/source references from:
  - [ ] `v3/web/reporting/report_service.py`
  - [ ] `v3/web/reporting/cache.py`
  - [ ] `v3/web/blueprints/settings.py`
  - [ ] `v3/web/templates/settings.html`
  - [ ] `v3/web/static_src/js/settings.ts`
  - [ ] generated `static_dist`
  - [ ] `v3/web/seeds.py`
  - [ ] environment templates, README, help copy, tests, and decision summaries
- [ ] Delete app-only OData tests after replacing them with SQL-route/scope tests.
- [ ] Run a repository search and prove no OData references remain under `v3/`.

### 3.4 Preserve non-app Automation intentionally

- [ ] Keep OData code under `reports/`, `core/`, `data/`, and `runbooks/` only where Azure Automation or CLI imports it.
- [ ] Document that boundary in README.
- [ ] Add a test or import inventory proving the Flask application never imports those OData clients.

Gate:

- Every visible report runs through SQL.
- Item Averages works without an operator source change.
- No `v3/` source, template, static asset, route, migration reader, cache key, or test mentions OData.
- Scoped-user tests cover every report and every tab.

## Phase 4 — Move workers and scheduling out of Flask/Gunicorn

### 4.1 Define process ownership

- [ ] Flask app factory performs no migrations, seeding, worker start, scheduler start, cleanup, or background thread creation.
- [ ] Gunicorn workers only serve HTTP and enqueue/read durable state.
- [ ] Create one explicit bootstrap command that runs migrations and one-time seeds before traffic.
- [ ] Create one explicit non-HTTP worker entry point.
- [ ] The worker entry point owns:
  - [ ] durable job claiming
  - [ ] report generation
  - [ ] exports
  - [ ] report email/folder delivery
  - [ ] schedule ticks
  - [ ] catch-up
  - [ ] cache/export/job/attempt pruning
  - [ ] worker and scheduler heartbeats

### 4.2 Supervise both processes

- [ ] Add a small process-launch script using shell process supervision or a platform-supported continuous worker.
- [ ] Start Gunicorn and the worker as separate processes.
- [ ] If either required process exits, terminate the other and let the platform restart the unit.
- [ ] Forward signals and wait for clean shutdown.
- [ ] Run Litestream as the outer durability process.
- [ ] Keep one App Service instance while SQLite is used.

Do not add a framework solely for process supervision. Prefer a short, tested shell launcher or a platform-native worker.

### 4.3 Make jobs killable and bounded

- [ ] Replace long-running thread jobs with killable child processes, or otherwise prove a hard timeout releases capacity.
- [ ] Start with one report-processing slot on the B1 unless load evidence supports more.
- [ ] On timeout: terminate the child, record cancellation/failure, release capacity, and prevent external effects.
- [ ] Do not merely mark the DB row failed while its thread continues.
- [ ] Add queue depth and age admission limits.
- [ ] Reserve or prioritize scheduled deliveries so interactive exports cannot starve them.

### 4.4 Durable liveness/readiness

- [ ] Persist worker heartbeat, scheduler heartbeat, last successful cleanup, and process identity.
- [ ] `/healthz` remains process liveness.
- [ ] `/readyz` starts red, becomes green only after bootstrap/migrations complete, and goes red for stale required worker/scheduler heartbeat.
- [ ] Scheduler-start failure must propagate; do not swallow it and report ready.
- [ ] External monitoring must check `/readyz`, queue age, worker heartbeat, scheduler heartbeat, disk, and Litestream lag.

Tests:

- Gunicorn imports app without starting threads.
- Separate worker claims and completes a job.
- Worker death releases/requeues only safe jobs.
- Hard timeout frees capacity.
- Two hung jobs cannot permanently stop the queue.
- Scheduler death makes readiness/monitoring fail.
- Bootstrap pending/failure keeps readiness 503.

Gate:

- No `ThreadPoolExecutor`, scheduler, worker poller, or background thread is started by Flask/Gunicorn.
- A killed worker cannot leave the site falsely ready.
- Report and schedule jobs still survive restarts.

## Phase 5 — Redesign delivery recovery honestly

### 5.1 Replace ambiguous delivery states

- [ ] Replace `pending` as a settled state.
- [ ] Use explicit states such as `prepared`, `sending`, `accepted`, `sent`, `failed`, and `unknown`.
- [ ] Persist an immutable scheduled-slot ID at enqueue time. Do not calculate the attempt day during execution.
- [ ] Key manual delivery attempts by one durable job/run ID that survives retry.
- [ ] Add retention and foreign-key/cleanup policy for delivery legs.

### 5.2 Separate delivery legs

- [ ] Build the report/workbook before marking external legs as sending.
- [ ] Execute SharePoint/OneDrive and email as separate persisted legs.
- [ ] For idempotent folder writes, use deterministic destination/name and verify the remote object.
- [ ] For Graph mail, treat connection loss after submission as `unknown`, not automatically failed or sent.
- [ ] Do not auto-retry `unknown` email outcomes.
- [ ] Alert an operator with a safe reconcile/retry action.
- [ ] Do not claim that `internetMessageId` or `client-request-id` guarantees Graph `sendMail` deduplication.

### 5.3 No-data notices

- [ ] Give each no-data notice its own persisted delivery leg and attempt ID.
- [ ] Do not mark the workbook-email leg sent when no workbook email was attempted.
- [ ] A failed no-data notice must remain failed/retryable rather than becoming skipped-success.

### 5.4 Token refresh

- [ ] Cache Graph tokens with expiry.
- [ ] Refresh before expiry.
- [ ] On one 401, clear token, acquire a new token, and retry only an idempotent operation.
- [ ] Honor `Retry-After` for 429/503.
- [ ] Implement upload-session status/resume for interrupted large uploads.

Fault tests:

- Crash before external call.
- Crash after folder acceptance.
- Crash after Graph acceptance before DB commit.
- Restart before and after Eastern midnight.
- 401 token expiry.
- 429/503 with Retry-After.
- Interrupted upload session.
- No-data notice failure.
- Partial fan-out failure.
- Cancellation before build, after build, before send, and during external call.

Gate:

- Every tested crash produces either one delivered leg, a clearly failed leg, or an explicit unknown outcome requiring operator action.
- No test records success for a definitely unsent required leg.

## Phase 6 — Fix remaining report and schedule defects

Implement only after owner decisions are recorded.

- [x] Fix commission-card salesman number lookup to use the current bucket.
- [x] Define and correctly display varying commission rates.
  Shipped adopted Q3 (salesman-table saved percent), not “varies.” Displayed % is the master rate; dollars still use `_commission_rate` (Q1/Q2). Evidence: `python3 -m pytest tests/test_report_invoiced.py tests/test_report_sql_coverage.py -q` — 34 passed. Invoiced `builder_version` 4. Gate closed on `86f2fbc`. Loops A+B+C zero. Trust-boundary N/A.
- [x] Preserve explicit zero commission if the API contract says zero is authoritative. Evidence:
  `python3 -m pytest tests/test_report_invoiced.py -q` — 30 passed. Invoiced `builder_version` 3 so pre-fix cache is not reused. Gate closed after Loops A+B+C zero and Fable trust-boundary high 0 / medium 0.
- [x] Add validation after D365 go-live clamping; reject an interval whose start exceeds end. Evidence: `python3 -m pytest tests/test_dates.py tests/test_params.py tests/test_blueprints.py -q` — 188 passed.
- [x] Persist `skip_sabbath=false` in company schedule create/update.
- [x] Replace migration 0019 behavior with a forward correction:
  - [x] do not edit 0019
  - [x] identify legacy rows as `legacy`/unknown where possible
  - [x] ensure deployment-day historical rows do not suppress the next real clock slot
  Evidence: `python3 -m pytest tests/test_scheduling.py -q` — 51 passed. `0019_delivery_legs.sql` unchanged. `last_run_at` ignores `legacy`/`unknown` status and `output_meta.legacy`. Gate closed on `6d4a0b5`.
- [x] Enforce kept-run expiry on result access. Evidence:
  `python3 -m pytest tests/test_blueprints.py tests/test_jobs.py -q` — 184 passed.
- [x] Prune expired kept payloads. Evidence:
  `python3 -m pytest tests/test_jobs.py tests/test_blueprints.py -q -k 'cleanup or kept_run or keep_run'` — 7 passed.
- [x] Prune expired magic-link attempts, delivery legs, old jobs, and run history per approved retention. Evidence:
  `python3 -m pytest tests/test_jobs.py -q` — 35 passed; `python3 -m pytest tests/test_magic_links.py -q --noconftest` — 6 passed. Gate closed on `b4cdc3e`.
- [x] Make SharePoint fail closed when configured `SP_SITE_URL` cannot resolve; never tenant-search a substitute site.
- [ ] Require operate/edit permission for company **Send now**.
- [x] Move public reconciliation diagnostics behind developer authentication and POST+CSRF; remove query-string secrets.
- [x] Convert state-changing `claim-once` diagnostic to POST+CSRF or remove it.
- [ ] Apply external-recipient policy.

Gate:

- Focused regression exists for every fixed defect.
- Business outputs match approved semantics and signed sample data.

## Phase 7 — Normalize the one-site persistence model

- [ ] Choose one canonical home DB environment name, preferably `SITE_PRECIOUS_DB_PATH`.
- [ ] Add a staged Azure setting migration from `BETA_*` to `SITE_*`.
- [ ] Update app config, startup, Litestream, readiness, tests, and docs together.
- [ ] Remove the obsolete second `PRECIOUS_*` `/test` database and replica from required startup.
- [ ] Reduce `litestream.yml` to the one serving database.
- [ ] Validate required replica path/container/account settings.
- [ ] Before migrations, run SQLite `quick_check` and verify the expected source DB identity.
- [ ] After restore, verify nonzero file, `quick_check`, required tables, schema migration level, and a durable application-state sentinel.
- [ ] Test restore from an archived pre-0016 database through migrations 0016+.
- [ ] Keep a validated rollback path compatible with forward migrations.

Live gate:

- Owner performs the Azure empty-disk restore drill.
- Record restored snapshot identity, row counts, schema versions, users, schedules, views, and settings.
- Prove Litestream replication resumes and lag is monitored.
- A zero-byte/corrupt/stale DB never becomes a fresh empty Production site.

## Phase 8 — Finish UI/accessibility and browser verification

- [ ] Adopt the shared dialog helper for admin, SharePoint, external-login, Customer Last Order, and export dialogs.
- [ ] Add `aria-modal`, initial focus, focus trap, Escape, inert/background isolation, and opener restoration.
- [ ] Fix admin/dashboard table reflow at 320px and 200% zoom.
- [ ] Correct all four-theme contrast failures.
- [ ] Complete searchable-picker option navigation and focus return.
- [ ] Complete toolbar and tab-option menu keyboard behavior.
- [ ] Add live status/error announcements for admin, dashboard, Settings, and schedule sends.
- [ ] Bring remaining help/filter/chip/day/close controls to 44px targets.
- [ ] Respect reduced motion for JavaScript scrolling.
- [ ] Pause or correctly reschedule every hidden-tab poller.
- [ ] Replace stale “check the outbox” production copy.
- [ ] Show a clear error when report-to-schedule draft transfer fails.
- [ ] Resolve report-module circular imports or add browser coverage proving initialization order.
- [ ] Add the Tabulator MIT license text and third-party attribution.

Browser matrix:

- Roles: salesman, manager, admin, developer, demoted/disabled user.
- Widths: 320, 375, 768, 1280 CSS px; 200% zoom.
- Themes: light, dark, monochrome, monochrome dark.
- Flows: login, magic link, report run, every tab, filters, Saved views, Keep, export, email, cancel, Recent Reports, Schedule from report, personal/company schedules, Send now, Settings, People, diagnostics.
- Failure states: API failure, slow job, cancellation, expired token, rejected Settings save, no data, missing email, failed upload, stale worker.

Gate:

- Browser evidence is attached.
- Keyboard-only and screen-reader checks pass.
- No document-level horizontal scrolling hides actions.
- No unapproved theme contrast failure remains.

## Phase 9 — Restore parity evidence and finish cleanup

### 9.1 Report parity without restoring old routes

- [ ] Check out `archive/pre-cleanup-2026-08-27` in an isolated environment.
- [ ] Restore `tools/parity` only in that isolated verification workspace, or build frozen golden comparisons.
- [ ] Do not mount old apps in Production.
- [ ] Compare every retained report, relevant period/filter, role scope, tab list, column semantics, totals, exports, and schedule workbook.
- [ ] Cover Ordered shipping/remainder, Invoiced credits/commissions, Number 4 YTD, Customer Activity, Customer Last Order, Item Averages, Sales by State, and Customer Aging if retained.
- [ ] Record approved intentional differences.

### 9.2 Feature parity

- [ ] Explicitly decide the deleted in-app email-distribution feature.
- [ ] Verify Azure Automation still sends every required distribution.
- [ ] Verify no old route, test, tool, or document is needed for support/recovery.

### 9.3 Documentation and hygiene

- [ ] Mark `REPOSITORY-REVIEW.md` as implemented/remaining or archive it; do not leave “fixes not started.”
- [ ] Make root `.env.example` contain every required Production setting or point clearly to one canonical template.
- [ ] Correct stale startup, Gunicorn, export, and deploy comments.
- [ ] Remove stale `.gitignore` entries for deleted app generations.
- [ ] Make `git diff --check` pass.
- [ ] Keep only current decision history needed by operators/agents.
- [ ] Use one allowlisted artifact builder for CI and manual emergency deployment.
- [ ] Make `deploy.ps1` invoke the same tests/build/artifact/smoke pipeline or retire it.
- [ ] Lock Python dependencies with hashes and test the exact deployed set.
- [ ] Expand generated-output verification to every deployed static asset.

Gate:

- Parity results are attached and accepted.
- Deleted feature decisions are explicit.
- Docs describe only the current architecture.
- Emergency and normal deploys use the same artifact.

## Phase 10 — Final review and go-live

Run in this order:

1. [ ] Self-review every checklist item in this plan.
2. [ ] Ponytail review: delete dead compatibility and avoid replacement abstractions.
3. [ ] Correctness Loop A on the complete branch.
4. [ ] Correctness Loop B from a separate model family.
5. [ ] Quality Loop C.
6. [ ] Trust-boundary review.
7. [ ] Full feature/report parity review.
8. [ ] Live restore drill.
9. [ ] Staging deploy using the exact Production artifact.
10. [ ] Authenticated staging smoke with real/approved data.
11. [ ] Owner approves business decisions and feature losses.
12. [ ] Owner explicitly approves Production promotion.
13. [ ] Merge to `webapp-cache`.
14. [ ] Observe every required CI/security/deploy check.
15. [ ] Verify Production `/healthz` and `/readyz`.
16. [ ] Verify login, one scoped report, one admin report, export, email, personal schedule, company schedule, worker heartbeat, scheduler heartbeat, Litestream replication, and old-route behavior.
17. [ ] Roll back immediately on scope, auth, delivery, restore, or worker-health failure.

## Completion evidence required

- Commit hashes for each logical phase.
- Green check URLs for exact final HEAD.
- Owner decision-log entries.
- SQL report inventory and parity matrix.
- Worker-process topology and shutdown test.
- Delivery crash/fault matrix.
- Auth revocation test matrix.
- Restore drill output with sanitized row counts and integrity result.
- Browser/accessibility artifacts.
- Artifact manifest and dependency lock hashes.
- Production verification record.

No phase is complete based only on code presence or green unit tests.
