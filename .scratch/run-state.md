# Rebuild Run-State

Tracks progress through the rebuild protocol. Update at every phase gate.

## Brief
- `rebuild/REBUILD-BRIEF.md` — locked decisions + open debates + scope.

## Scope of first deliverable (CONFIRMED by owner 2026-06-22)
- **Reports:** invoiced only (others wait on their flat-table SP endpoints).
- **Shell features IN:** Entra login + nav, run/status/resume/cancel jobs,
  on-screen table (group/sort/show-hide/reorder/resize, tabs, subtotals),
  Excel export + recent exports, email delivery, schedule recurring delivery,
  presets/save-view, settings/theme.
- **Admin report-config:** SEED invoiced's column/tab config now (code/DB);
  the admin manifest editor is a LATER phase, not the first deliverable.
- **DEFER (keep on inventory, not first cut):** other reports, dashboard,
  customer-last-order, master schedules. SharePoint save: confirm during Phase 1.

## Phase status
- [x] Phase 0 — Multi-model audit + history mining (7 agents, 7 families; done)
- [x] Phase 1 — Feature inventory (`rebuild/FEATURE-INVENTORY.md`): 20 pages P1–P20,
      route manifest, to-fix (FA/FB/FC), BH1–50 prevention map, 9 human sign-offs
- [x] Phase 2 — Architecture proposals (Claude Opus + GPT): agree on stack,
      server-side grouping, SQL-first math, DB report config; split on persistence,
      big-table, worker.
- [x] Phase 3 — Debate CONSENSUS (1 round) + REBUILD-PLAN.md written: 12 phases,
      115 todos (T1.01–T12.08), 50/50 BH mapped, 25/25 FA-FB-FC mapped, 9 sign-off
      gates, 12 test suites. 7 minor author calls in §9 (file layout, startup
      script, snapshot format, Tabulator version) — accepted as defaults.
- [~] Phase 4 — Build.
      - [x] 4.0 Foundation + smoke deploy — GREEN on platform 2026-06-22.
            Files: rebuild/{config,app,__init__}.py, data/{connection,migrate}.py +
            migrations, blueprints/{health,main}_routes.py, templates, static/css.
            Wired into root wsgi.py as gated mount. Verified in prod:
            /test-next/ = 200, /test-next/healthz = 200 (env=prod, schema_ready),
            live / and /test untouched (both 200). Covers T1.01-T1.04, T1.06,
            T1.07(healthz), T1.08(seams), T1.09(cache self-heal).
            Deferred to next foundation slice: T1.05 Litestream packaging,
            T1.10 startup.sh + separate worker process.
      - [ ] 4.1 Auth phase (Entra login) — BLOCKED on owner registering the
            Entra redirect URI https://reports.achimonline.com/test-next/auth/callback.
      - [ ] 4.2+ feature-by-feature (jobs/worker, report engine + invoiced, view
            builder, shell, viewer, export, email/schedule).
- [ ] Phase 5 — Final review (route diff + ID ledger + multi-model, looped)

## Foundation decisions (Phase 4.0)
- This app shares one Azure process with live + /test, so it reads its OWN
  REBUILD_* env vars (DB paths, mount, Litestream) to avoid colliding on disk.
  Shared backend resources (GRAPH_*, REPORTING_API_*, FLASK_SECRET) are reused.
- DBs on local disk: /tmp/rebuilddata/{precious,cache}.db (mirrors v3's /tmp/v3data).
- Litestream hard-requirement is gated behind REBUILD_REQUIRE_LITESTREAM (default
  off) so the temporary slot can deploy and be reviewed before cutover.
- Mount is gated on REBUILD_MOUNT_ENABLED + try/except in root wsgi.py, so the
  rebuild can never take down live or /test.

## Phase 4.0 review (GPT readonly) — resolved
- FIXED: relative DB paths now resolved to absolute before the /home check
  (a relative path on Azure resolves under the /home SMB share -> now refused).
- FIXED: basic single-instance guard (REBUILD_INSTANCE_COUNT, default 1; prod
  refuses >1) per the SQLite one-instance consensus.
- FIXED: cache self-heal now verifies the anchor table on every open, so a
  dropped table (not just a deleted file) recovers; removed the racy heal flag.
- FIXED: wsgi validates the mount path BEFORE building the app / starting the
  bootstrap thread.
- CLEANED: Conn annotations no longer leak sqlite types (seam purity).
- INTENTIONAL (not a bug): Litestream optional in prod is the documented
  temporary-slot exception, mandatory at cutover (T1.05); comment made explicit.
- OUT OF SCOPE: v3 leaving sys.path[0] is pre-existing v3 behavior; the rebuild
  uses relative imports so it's unaffected, and we don't touch live/v3.

## Phase 4.1 Auth (Entra) — built + deployed GREEN
- Added Entra callback URI to the app registration (ADDITIVE; all existing URIs
  kept): https://reports.achimonline.com/test-next/auth/callback
- New rebuild/auth/: principal, session, msal_flow, authorization (central role
  resolution), decorators (require_login/require_privileged).
- auth_routes: /login, /login/start, /auth/callback, /logout, /login/dev
  (dev-only). Safe-next guard against open redirects. login_next stashed in
  session across the Microsoft round trip.
- precious migration 0002 users table + UsersRepository.record_login (directory
  mirror, upsert on each login). Role from REBUILD_DEVELOPER_EMAILS.
- Landing page now @require_login; shows signed-in name/role + sign out.
- App settings: REBUILD_AUTH_MODE=msal (already set), added
  REBUILD_DEVELOPER_EMAILS (mirrors V3 = mennyg@achimonline.com,...ad...).
- Verified in prod: index -> 302 /test-next/login; login page shows the
  Microsoft button (dev form hidden in prod); /login/start -> 302 to
  login.microsoftonline.com with redirect_uri EXACTLY the registered
  /test-next/auth/callback; schema_ready true; live / and /test unaffected.
- REMAINING HUMAN STEP: the actual browser sign-in (typing the Microsoft
  password) can only be done by a person -- everything up to that point is wired
  and verified.

### Phase 4.1 auth review (GPT readonly) — resolved
- FIXED (blocker): mount-safe `next`. Under the dispatcher mount request paths
  are app-local, so the old guard could redirect to "/" and escape into the live
  app after login. _safe_next now re-adds the mount prefix and rejects //, /\,
  and absolute URLs. Verified: next="/" -> /test-next/.
- FIXED (blocker): CSRF. Added rebuild/security/csrf.py (token per session,
  required on POST/PUT/PATCH/DELETE, csrf_token() in templates). Logout is now
  POST with a token; dev-login form carries a token. Verified tokenless POST=400.
- FIXED: SESSION_COOKIE_PATH=mount_path so the cookie is scoped to /test-next.
- FIXED: role is no longer trusted from the cookie -- session stores identity
  only; current_principal() re-resolves the role server-side every request.
- FIXED: MSAL errors show a generic message; the real detail is logged only.
- FIXED: ProxyFix added (x_for/proto/host=1) + case-insensitive forwarded-proto
  so the https callback URL is correct behind the Azure proxy.
- DEFERRED (nice-to-have, documented): users.role CHECK constraint (the app only
  ever writes resolved valid roles); server-side MSAL flow storage (confidential
  client -- the PKCE verifier in the signed cookie is unusable without the client
  secret, same pattern as the live app).

## DECISION: invoiced build sequence (cross-model debate, both agreed)
What I had to decide: in what order to build the rest of the invoiced report.
Options: (A) vertical slice first vs (B) strict 12-phase order.
What I chose: A "disciplined vertical slice" -- build the REAL final-architecture
  path for invoiced now, defer heavy ops until the owner sees + checks numbers.
Why: both debaters (GPT + Gemini) independently picked A; owner wants bare-minimum
  + to verify numbers early; the riskiest unknown is "does invoiced match LIVE?",
  so reach a rendered report fastest without faking the architecture.

Locked milestones (T-numbers from REBUILD-PLAN.md):
- M1 Data spine: T3.01(partial), T3.02, T3.03 jobs, T3.06 report_configs,
  T3.11 run_log. (users already done in auth phase)
- M2 Worker (in-process mode): T4.01, T4.03, T4.06 backpressure cap, T4.07
  heartbeat, T4.08 job registry, minimal stale-running cleanup from T4.05.
- M3 Engine + invoiced contract: T5.01-T5.10 (config_loader, adapter, generic
  engine, commission pivot, conditions, params, runner, API client, cache, seed).
- M4 Snapshot + view builder: T6.01, T6.02 (cache.db only), T6.03 + temp row/byte
  guard.
- M5 Minimal shell + viewer: T7.01-06, T8.01-08, T8.13, T8.14 (run/status/result
  APIs, Tabulator, tab bar, basic toolbar/columns).
- M6 Owner sanity-check gate: PROVISIONAL labels + a §7 checklist; owner verifies.

Honest-durability rule for the slice: run route writes a real jobs row + returns
  202; the real worker (jobs.worker) claims + runs it under WORKER_MODE=in_process.
Central authz on every data route. Cache key carries identity+scope; reads re-check.

DEFERRED until after sign-off / before cutover (tracked here so not forgotten):
  T1.05 Litestream packaging, T1.10/T4.09 startup orchestration + separate worker
  process, T4.02 flock leader, full T4.04/T4.05, T6.04/T6.05 server-paging/memory
  budget, Phase 9 export, Phase 10 email/schedule, Phase 11 admin/impersonate, and
  repos salesmen/preferences/presets/exports/schedules/feature_flags (build when
  their phase lands). HARD GATE: cannot promote /test-next -> /test until the
  deferred infra is backfilled.

## M3 invoiced contract decisions (PROVISIONAL until owner sign-off)
- Endpoint: POST {REPORTING_API_BASE_URL}/api/reports/invoiced_report/run, header
  X-API-Key, returns {columns, rows, row_count}. (from reference http_client)
- SP params: InvoiceDateFrom/InvoiceDateTo (ISO), optional CustomerAccount (single
  exact), optional Salesman (csv). (from reference params.translate_invoiced)
- Commissions (owner-confirmed): SQL sends the RATE only (column `commission`,
  fraction; /100 if >1). App computes per salesman per month:
  net = TotalInvoice + Credits - Freight - CC; commission = net * rate;
  YTD = sum of monthly (unrounded, display-rounded). Matches LIVE.
- IsCredit: prefer SQL column; fallback regex CRD|CM|FC on invoice number (LIVE).
- DRIFT to verify at sign-off: single SP fetch over the SELECTED window; the
  commission pivot is computed over that window (year/end_month derived from the
  fetched rows), NOT a separate Jan1..period-end YTD fetch like live. Default
  invoiced period = YTD so the common case lines up. Flag in M6 checklist.
- Full Details nets duplicate invoice rows only if duplicates are present (LIVE).
- 7 tabs (LIVE order): Summary by Customer, Commissions (transform), Full Details,
  Credits, Invoices, Audit-Reversals (condition has_reversals), Totals by Salesman
  (condition has_multiple_salesmen).

## Live preview URL
- https://reports.achimonline.com/test-next/  (temporary slot; live /test untouched)

## Working branch
- `rebuild-reports`

## Artifacts (to be created)
- `rebuild/rebuild-audit/graph-backbone/[area].md`
- `rebuild/BUILD-HISTORY.md`
- `rebuild/FEATURE-INVENTORY.md`
- `rebuild/DEBATE-LOG.md`
- `rebuild/REBUILD-PLAN.md`
