# v3 Rebuild - Weekend Review Log

This is the running log of the autonomous v3 rebuild. Read the sections in this order
when you get back:

1. **NEEDS HUMAN SIGN-OFF** - decisions only you can make (report calculation rules,
   cutover). Nothing financial was decided silently; each item below is built to LIVE/root
   behavior as PROVISIONAL until you sign off.
2. **OPEN QUESTIONS / BLOCKERS** - things I could not resolve without you or external access.
3. **GPT-5.5 REVIEW FINDINGS** - per-phase review results and how I resolved them.
4. **PHASE PROGRESS** - what got built, with commit references.

Authoritative plans: `.cursor/plans/v3_rebuild_plan_81336296.plan.md` (opus48) and
`.cursor/plans/gpt55_rebuild_plan_8e9d2b54.plan.md` (gpt55). Rules: `.cursor/rules/v3-rebuild.mdc`.

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

### Engineering parity items (not business decisions; for your awareness)

- `text()` helper: the sandbox originals were inconsistent - 4 modules' `_str` did NOT strip,
  but `customer_activity._str` DID. v3's `text()` does not strip (majority); the
  customer_activity builder will strip explicitly. A parity test will lock this when that
  builder is ported.

---

## 2. OPEN QUESTIONS / BLOCKERS

- **Cache-scope leakage (deferred, needs eventual sign-off)**: `report_payload_cache` prevents
  cross-user/cross-scope leakage purely via the `cache_key` (which includes user scope +
  builder version + freshness). This is NOT enforced by a schema constraint. Plan: the
  cache-key builder will be the single source of truth and the reporting phase will add explicit
  cache-scope leakage tests. Flagging so you can confirm that approach is acceptable.

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

---

## 4. PHASE PROGRESS

| Phase | Status | Commit | Notes |
|-------|--------|--------|-------|
| 0/1. Rules + log + scaffold + config + engine foundation | DONE | 7ec6582 | 22 tests; GPT-5.5 findings resolved |
| 2. Data layer (precious/cache, migrations, durable jobs, repos) | DONE | (this commit) | 31 tests; atomicity + concurrency proven |
| 3. Auth + single authorization/scope layer | next | - | - |
