# v3 Rebuild - Weekend Review Log

This is the running log of the autonomous v3 rebuild. Read the sections in this order
when you get back:

0. **DECISION JOURNAL (plain English)** - every choice I made, in normal words: what I had
   to decide, the options, what I picked, and why. Start here.
1. **NEEDS HUMAN SIGN-OFF** - decisions only you can make (report calculation rules,
   cutover). Nothing financial was decided silently; each item below is built to LIVE/root
   behavior as PROVISIONAL until you sign off.
2. **OPEN QUESTIONS / BLOCKERS** - things I could not resolve without you or external access.
3. **GPT-5.5 REVIEW FINDINGS** - per-phase review results and how I resolved them.
4. **PHASE PROGRESS** - what got built, with commit references.

Authoritative plans: `.cursor/plans/v3_rebuild_plan_81336296.plan.md` (opus48) and
`.cursor/plans/gpt55_rebuild_plan_8e9d2b54.plan.md` (gpt55). Rules: `.cursor/rules/v3-rebuild.mdc`.

---

## 0. DECISION JOURNAL (plain English)

> Plain-words record of every real decision, newest at the bottom. Format for each:
> **What I had to decide -> The options -> What I chose -> Why.** Skim the bold lines if
> you're in a hurry; we'll walk through anything you want to change.

### Session: Fri May 29 (before Shabbos) - your ground rules + going live at /test

**1. The big one: which app is the "source of truth" for reports?**
You told me: the LIVE app's reports are "god." The test app was a rebuild whose *point* was a
nicer on-screen table (interactive, customizable) instead of dumping straight to Excel.
- *Options:* (a) copy the test app wholesale, (b) copy the live app wholesale, (c) blend them.
- *Chosen (c), split by concern:*
  - **How it's built / how it behaves (architecture + UX)** -> follow the **TEST app**:
    reports render as an interactive table **on screen first**, and only turn into an Excel
    file **when you click Export**.
  - **What the report looks like - the columns, their order, the layout/format** -> follow the
    **LIVE app** (specifically, match the format of the live app's *exports*).
  - **The numbers / all the math** -> follow the **LIVE app**, exactly.
- *Why:* you said the live numbers are what the business runs on, so I never want v3 to show a
  different number than live. But the test app's on-screen experience is the upgrade you want to
  keep. Splitting it this way gives you live-correct content in the better test-style shell.

**2. Special case: the Commissions tab inside the Invoiced report.**
- *Decision:* build it the way the **test app** does (views nicely on screen), and when exported
  it should match the **live app's** export. (Same rule as #1, called out because you flagged it.)

**3. Sign-in for the preview at report.achimonline.com/test.**
- *Options:* real Microsoft (Entra) login like live; a dev "pick a user" screen; or just mimic the
  test app.
- *Chosen:* **real Microsoft (Entra) login, same as the live app**, reusing the redirect URL that
  already works for /test.
- *Why:* it's going on the real domain, so it should behave like the real thing - no fake login.

**4. If I run out of time to verify every report's math by Sunday.**
- *Options:* hide any report I haven't fully matched to live ("coming soon"), OR show everything
  and clearly flag the not-yet-verified numbers.
- *Chosen:* **show everything, with a clear "numbers not yet verified" flag** on anything I
  haven't confirmed against live.
- *Why:* you said you want to *see* the whole app Sunday. The flag makes sure you're never misled
  into trusting an unverified number.

**5. Backing up saved settings (the "Litestream" question).**
Plain version: the app keeps a small file on the server for prefs, schedules, and who-can-see-what.
Azure can wipe that file on a restart. Litestream copies it to cloud storage so it survives.
- *You asked me to just set it up* (you're logged into the Azure CLI).
- *What I did:* created an Azure Storage account **`achimsalesreportsv3`** with a container
  **`litestream`** in your existing resource group **`AchimReportsApp`** (Canada Central, same
  region as the app). At deploy time I'll pull the access key straight from your Azure CLI session
  and set it as an app setting, so **the secret never gets written into the code or this chat.**
- *Why this account/region:* same resource group and region as the web app = lowest latency and
  one place to manage everything. Cheapest redundancy tier (LRS) is plenty for a settings backup.

**6. Don't lose the old test app.**
- *Chosen:* keep the current test app in the codebase **and** still reachable at a second URL
  (planned: **/test-legacy**); point **/test** at the new v3 app.
- *Why:* you can compare old vs new side by side, and we can instantly flip back if needed.

**7. (My call, logged) How /test will switch to v3.**
- Today `wsgi.py` already serves the live app at `/` and the old test app at `/test` side by side
  (via a dispatcher). I'll **swap the v3 app into the `/test` slot** and move the old one to
  `/test-legacy` - a small, reversible change in one file. No impact on the live `/` app.

**8. (My call, logged) Shipping the built front-end to Azure.**
- The front-end is bundled by a Node tool (esbuild) into files the browser loads. Azure's Python
  image may not run that Node build. *Decision:* I'll **commit the built files** so the deploy is
  reliable without depending on a Node step on the server. (If you'd rather build on deploy, easy
  to switch - noted as a future option.)

---

## 1. NEEDS HUMAN SIGN-OFF

> Every report calculation rule the audit flagged as "drift" is listed here (mirrors the
> `DRIFT_LEDGER` in `report_engine/contracts.py`). All currently default to LIVE/root behavior
> and are PROVISIONAL until you pick a rule and name yourself as owner. The builders are not
> finalized until these are signed off.

- [ ] **Pre-build data gate**: confirm the Reporting API / stored procedures expose the fields
      needed to reproduce root's calculations (especially `ordered` WHS + packing-slip status).
      If not, the SPs must be extended before web `ordered` numbers can match live. Status: OPEN.

### Drift decisions (pick one per item; default = live/root)

| Report | Decision | Question | Default |
|--------|----------|----------|---------|
| invoiced | tariff_source | Tariff from sales-LINE (`SL_TariffCharges`) vs header (`SH_TariffCharges`)? | live/root |
| invoiced | credit_detection | Credits by substring "contains" vs invoice-number prefix? | live/root |
| ordered | summary_remainder | Definition of Summary-tab remainder (ordered - released - shipped?) | live/root |
| ordered | status_qty_engine | Status/qty via WHS + packing-slip joins (root) vs flat SP rows (web) | live/root |
| ordered | amazon_temp_rule | Amazon 9300/9301 temporary-item special handling | live/root |
| ordered | error_item_filter | Exclude rows flagged "ERROR ITEM"? | live/root |
| number_4 | book_price | Book Price column source/derivation | live/root |
| number_4 | free_text_exclusion | Exclude free-text (non-item) invoice lines? | live/root |
| salesman | group_key_cardinality | Grouping grain (one row per SalesGroup vs combined) | live/root |
| customer_activity | last_order_grain | Last-order grain: sales header vs sales line | live/root |

### Authorization policy decisions (from phase 3 - pick one each)

- [ ] **Report visibility default**: v3 currently FAILS CLOSED - a non-privileged user sees a
      built report only if they have an explicit allow row. The LIVE app instead has a
      conditional default-visible set + global-visibility flags + salesman-filter metadata.
      Decide: keep strict default-deny (you grant per user/role), or have me model live's
      default-visible set. Until you decide, salesmen see no reports by default.
- [ ] **Manager semantics**: live treats `manager` as privileged for the report LIST but scoped
      for salesman DATA. v3 currently treats manager as fully scoped (non-privileged). Confirm
      which you want.
- [ ] **Customer scope when sales-group unknown**: live `access.py` ALLOWS a scoped user to
      proceed when there's no cache row (so D365 is queried); v3 DENIES (safer). Confirm the
      stricter behavior is acceptable or restore live's allow-on-unknown.

### Frontend parity deviations (from phase 8 - confirm or tell me to restore live)

- [ ] **"Test Site" bottom-nav link**: live shows a `Test Site` tab (opens `/test/` in a new tab)
      for admins/devs. v3 is the replacement for that sandbox, so I gated it behind a
      `test_site_enabled` flag that defaults OFF (markup retained, so flipping the flag restores it
      exactly). Rationale: a permanent admin link to the old sandbox would 404/confuse post-cutover.
      Confirm OFF-by-default is right, or tell me to show it for admin/dev like live.
- [ ] **Dev "Switch user" target**: live points the header switch-user icon at `auth.role_picker`.
      v3 currently points it at the dev login page (`auth.login_page`), which already lists/selects
      dev users. Confirm consolidation is fine, or I'll build a dedicated `role_picker` route to match.

### Engineering parity items (not business decisions; for your awareness)

- `text()` helper: the sandbox originals were inconsistent - 4 modules' `_str` did NOT strip,
  but `customer_activity._str` DID. v3's `text()` does not strip (majority); the
  customer_activity builder will strip explicitly. A parity test will lock this when that
  builder is ported.

---

## 2. OPEN QUESTIONS / BLOCKERS

- **Scheduler/worker ownership vs gunicorn workers (deployment decision)**: the in-process
  worker + APScheduler assume ONE owning process. "Single B1 instance" is not automatically
  "single Python process" - if v3 runs gunicorn with multiple worker *processes*, each would start
  its own scheduler/worker and double-schedule / over-claim. Decision needed: deploy gunicorn with
  ONE worker process + threads (gthread) on B1, OR gate background startup to one process via an
  env flag. I'll wire background startup behind an explicit flag in the reporting phase; confirm
  the single-worker deployment is acceptable.

- **Cache-scope leakage - RESOLVED (phase 5)**: the scope token is now produced ONLY by
  `canonical_scope_token()` (order-stable; None->ALL, empty->NONE, never ""), `build_cache_key()`
  rejects an empty token, and `ReportRunner` derives the token internally from the authorization
  result so a route can't pass a raw/unordered token. Tests prove cross-scope isolation
  (`test_runner_scope_isolates_cache`, `test_cache_key_isolates_scope`). Schema-level enforcement
  is unnecessary given this single chokepoint, but confirm you're comfortable with the approach.

---

## 3. GPT-5.5 REVIEW FINDINGS

### Phase 0/1 - Foundation (config, engine helpers, factory, CSRF, health)

GPT-5.5 (gpt-5.5-high, readonly) reviewed against the rules + plans. Resolution:

- **Fixed - fail-open APP_ENV**: `load_config()` now defaults `APP_ENV=prod` so a forgotten
  setting fails closed instead of running dev auth in prod.
- **Fixed - Litestream not enforced**: prod now requires `LITESTREAM_BLOB_URL` and rejects
  UNC/SMB DB paths (`_is_unc`).
- **Fixed - drift not in log**: the full drift ledger is now in section 1 above.
- **Fixed - helper fidelity**: removed the unfaithful `normalize_salesman_map` (no caller yet);
  documented the `text()` strip divergence as a parity item.
- **Fixed - hollow CSRF test**: replaced with real write-route tests (no token -> 400,
  valid token -> 200, mismatched -> 400).
- **Fixed - missing esbuild config**: added `esbuild.config.mjs` (no-op until FE phase).
- **Reviewer misread (no change)**: `date_only` matches the originals' `_date_only` (plain
  trim); invoiced's RFC1123 parsing is a separate `_parse_date` not yet ported - noted for the
  invoiced adapter phase.
- **Reviewer tooling note**: the reviewer could not see the plan files because they live in the
  user-global `.cursor/plans/`, outside the repo. Plans are referenced by absolute path in the
  rule; consider exporting a copy into the repo for CI/team review (deferred, non-blocking).

### Phase 2 - Data layer (connection, migrations, durable jobs, repos)

- **Fixed (BLOCKER) - migration atomicity**: the runner embedded the DDL and its
  `schema_migrations` row in a single transaction, so a failed migration can no longer leave the
  schema changed but untracked. Added `test_migration_failure_is_atomic`.
- **Fixed - concurrency proof**: added threaded tests - `test_concurrent_enqueue_dedups`
  (8 threads, same dedup_key -> exactly one active job) and
  `test_concurrent_claim_never_double_claims` (4 workers drain 12 jobs, none claimed twice).
- **Accepted (non-blocking)**: `claim_next()` may return None under contention while jobs remain
  queued; the worker loop polls/retries, so this is by design, not a correctness bug.
- **Accepted (non-blocking)**: repositories contain SQLite dialect (ON CONFLICT, partial index).
  This matches the stated off-ramp (Postgres = later adapter work, not drop-in today).
- **Documented**: `schedule_runs.schedule_id` is intentionally polymorphic (no FK); integrity is
  enforced in the repo layer (comment added in the migration).
- **Deferred to human**: cache-scope leakage enforcement approach (see section 2).

### Phase 3 - Auth + single authorization/scope layer

GPT-5.5 found four real security blockers; all fixed by making the DATABASE authoritative
each request (the session cookie is trusted for identity only):

- **Fixed (BLOCKER) - stale-role escalation**: role/privilege is now re-resolved from `users`
  on every check, so a downgraded admin loses access immediately
  (`test_role_revocation_takes_effect_immediately`).
- **Fixed (BLOCKER) - inactive users**: unknown/disabled users are denied everything and
  refused at login (`test_inactive_user_denied_everything`, `test_inactive_user_cannot_login`).
- **Fixed (BLOCKER) - report access too broad**: `can_view_report` now FAILS CLOSED for
  non-privileged (explicit allow row required). The broader live policy is a sign-off item
  (section 1).
- **Fixed (BLOCKER) - logout via GET**: logout is now POST (CSRF-protected);
  `test_logout_requires_post` asserts GET -> 405.
- **Hardened**: open-redirect-safe `next` (relative only), MSAL `next` carried in session,
  dev-login XSS-escaped, MSAL no-flow path returns 400 not a crash.
- **Deferred to human (sign-off)**: report-visibility default, manager semantics, and
  customer-scope-on-unknown (section 1).

---

## 4. PHASE PROGRESS

| Phase | Status | Commit | Notes |
|-------|--------|--------|-------|
| 0/1. Rules + log + scaffold + config + engine foundation | DONE | 7ec6582 | 22 tests; GPT-5.5 findings resolved |
| 2. Data layer (precious/cache, migrations, durable jobs, repos) | DONE | 97e1b99 | 31 tests; atomicity + concurrency proven |
| 3. Auth + single authorization/scope layer | DONE | f8eaae1 | 46 tests; DB-authoritative, fail-closed |
| 4. Jobs worker + APScheduler | DONE | b9aa4db | 59 tests; restart recovery + bounded concurrency |
| 5. Reporting infra (client, ONE scope-safe cache, runner, export, durable wiring) | DONE | (this commit) | 80 tests; cache-scope item resolved |
| 6. report_engine builders (6 reports) | GATED on human sign-offs (section 1) | - | source adapters + parity harness can start; calc rules need sign-off |
| 7. Blueprints (thin routes, feature parity) | pending | - | needs builders (sign-off) + shell (done) |
| 8. Frontend shell (pixel-parity base.html, token CSS, esbuild bundle) | DONE | (this commit) | 89 tests; live-faithful shell, GPT-5.5 parity gaps fixed |

### Phase 5 - Reporting infrastructure

GPT-5.5 found three blockers; all fixed:

- **Fixed (BLOCKER) - rule 7 not wired**: added `web/reporting/jobs.py` - a `report.run` durable-job
  handler + `enqueue_report_run()` (dedup = cache key). Routes will enqueue and poll, never run a
  report in the request thread. Proven by `test_report_run_enqueues_and_worker_populates_cache`.
- **Fixed (BLOCKER) - Excel formula injection**: `export.py` prefixes `'` on cells starting with
  `= + - @` (and tab/CR) so D365/customer text can't execute as a formula.
  `test_export_neutralizes_formula_injection`.
- **Fixed (BLOCKER) - scope-token canonicalization**: `canonical_scope_token()` is the only way to
  build a token; `build_cache_key` rejects empty; the runner derives it from the authz scope (see
  resolved item in section 2).
- **Hardened (non-blocking)**: client retries transient 5xx + network but not 4xx; tolerates a
  non-list `rows`; corrupt cache JSON is quarantined (deleted) not re-read; `ReportCache.prune()`
  added for a future scheduled reaper.
- **Boundary recorded**: Reporting API report-id mapping + filter translation intentionally live
  with the (gated) source adapters/builders, not the generic client.

### Phase 8 - Frontend shell

Built the app shell only (base layout + design tokens + nav chrome + the shared JS behaviors);
per-page/per-report CSS is deferred to its own phases. esbuild bundles
`static_src/{css,js}` -> `static_dist/{css/main.css, js/main.js}` and copies
`static_src/public/*` (PWA manifest + icons) to the static root. Tokens were copied verbatim
from the live stylesheet (primary stays live-blue `#2563eb`, not the green sandbox).

GPT-5.5 found three blockers (I'd built the nav from memory); all fixed:

- **Fixed (BLOCKER) - PWA assets would 404**: `manifest.json` + `icon-192/512.png` were missing
  under the new `static_dist` folder. Added them as committed source in `static_src/public/` and an
  esbuild copy step; the build now emits them at `/static/manifest.json` and `/static/icon-*.png`.
- **Fixed (BLOCKER) - missing "Test Site" nav item**: re-added with exact live markup, gated behind
  `test_site_enabled` (default off; see sign-off item in section 1) instead of silently dropped.
- **Fixed (BLOCKER) - `_safe_url` could mask routing bugs**: missing endpoints still fall back to
  `#` so the shell renders before its blueprints exist, but now log at WARNING so a real missing
  route can't hide. Pending nav (reports/dashboard/settings) is inert by design until phase 7.
- **Fixed (SHOULD) - shallow tests**: added role-conditional coverage - admin sees Dashboard,
  salesman does not, dev impersonation badge + switch-user control, non-dev hides switch-user,
  Test Site gated off by default, anonymous hides all chrome, logout is a POST form with CSRF.
- **Fixed (SHOULD) - missing `.help-icon` CSS** (added) and **main.css path comment** (corrected).
- **Hardened (NICE)**: `openHelp` no longer uses unchecked `as HTMLElement` casts (bails if an
  element is missing). JS port is otherwise faithful to live (double-click guard, nav overlay +
  bail-outs, pageshow cleanup, ESC close, pull-to-refresh thresholds/labels/triggerDashRefresh).
- **Deferred (SHOULD, logged)**: `help_content.js`/`HELP` is per-page content, not shell - not
  ported yet; `openHelp` safely no-ops until it lands. Inline `onclick` handlers are kept for live
  parity (a CSP-friendly delegated-listener pass is a future hardening item).
- **Deferred to human (sign-off)**: Test Site gating + switch-user target (section 1).

### Phase 4 - Background jobs (bounded worker + scheduler)

GPT-5.5 found two real blockers; both fixed:

- **Fixed (BLOCKER) - no restart recovery**: added `JobRepository.recover_orphans()`, called at
  `JobWorker.start()`. Jobs orphaned in `running` by a crash are requeued (and the dedup block they
  held is released). Tests: `test_orphaned_running_job_is_recovered`,
  `test_recover_orphans_unblocks_dedup`.
- **Fixed (BLOCKER) - cancel/terminal inconsistency**: `cancel()` is now QUEUED-ONLY and
  `mark_success`/`mark_failure` are guarded to `status='running'`, so a cancelled job can't be
  resurrected as success. Tests: `test_cancel_is_queued_only`,
  `test_mark_success_does_not_resurrect_cancelled`.
- **Decision (was sign-off) - running-job cancellation**: declared QUEUED-ONLY for v1; cooperative
  cancellation is a documented future addition. (Engineering decision, not a business one.)
- **Hardened (non-blocking)**: poller survives infra errors (claim/submit) without dying;
  scheduler sets explicit `coalesce/misfire_grace_time/max_instances` for a sleepy process; added a
  bounded-concurrency test proving we never exceed `max_workers`.
- **Deferred to human**: scheduler/worker single-owner deployment contract (section 2).
