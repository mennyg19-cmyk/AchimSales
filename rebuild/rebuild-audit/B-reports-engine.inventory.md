# Area B — Reports Backend + Report Engine Inventory

**Model:** claude-4.6-sonnet-medium-thinking

## Proof of Read

Sources verified verbatim via CodeGraph MCP (AST-indexed, byte-for-byte current):
- `v3/web/blueprints/reports.py` — 1135 lines, 23 routes read (lines 1–859), 8 more referenced in backbone
- `v3/report_engine/reports/invoiced.py` — 526 lines, 7 tabs, 5 column sets
- `v3/report_engine/sources/invoiced.py` — 87 lines, 1 adapter
- `v3/web/reporting/` — params.py (204), runner.py (53), cache.py (165), jobs.py (92), report_service.py (272)
- `reports/invoiced/aggregator.py` + `writer.py` — LIVE format reference, read directly

**Headline counts:** ~31 routes total · 7 tabs (5 always + 2 conditional) · 69 distinct named columns across tabs

---

## B1 — Routes (`v3/web/blueprints/reports.py`)

All routes require `@require_login`. Authorization is centralized: `_authz()` from app config.

### B1.1 — Page routes

| ID | Method | Path | Handler | Returns |
|----|--------|------|---------|---------|
| B1.1.1 | GET | `/` | `reports_list` | HTML: built + backlog reports, user presets as home cards |
| B1.1.2 | GET | `/reports/<report_key>` | `report_view` | HTML: filter form + Tabulator viewer shell. In-app reports (customer_last_order) redirect to their own page. `REPORT_FILTERS` dict controls which inputs render. |
| B1.1.3 | GET | `/report/customer-last-order` | `customer_last_order_pick` | HTML: customer picker page (admin gets salesman picker too) |
| B1.1.4 | GET | `/report/customer-last-order/<account>` | `customer_last_order_view` | HTML: rendered last-order view for one customer |

### B1.2 — Core report run/poll/result API

| ID | Method | Path | Handler | Behavior |
|----|--------|------|---------|----------|
| B1.2.1 | POST | `/api/reports/<key>/run` | `run_report` | Auth+authz → validate customers (resync if unknown) → `enqueue_report_run` → 202 + `{job_id}`. Dev/non-prod: drains inline. |
| B1.2.2 | GET | `/api/jobs/<job_id>` | `job_status` | Owner-checked (fail-closed, requires exact user id match). Returns `{job_id, status, progress, error, result_ref}`. |
| B1.2.3 | POST | `/api/jobs/<job_id>/cancel` | `cancel_job` | Owner-checked. Returns `{cancelled: bool, status}`. |
| B1.2.4 | GET | `/api/reports/result/<job_id>` | `report_result` | Owner-checked + scope-compatibility check (`_assert_scope_compatible`). On demotion, scope mismatch → 403. Reads payload from `ReportCache` by `result_ref`. 409 if job not success; 404 if cache expired. |
| B1.2.5 | GET | `/api/reports/active` | `active_report_runs` | Owner-scoped. Returns jobs that are queued/running OR finished within `_RECENT_DONE_SECONDS` (600s). Used for status bar + resume. |

### B1.3 — Export API

| ID | Method | Path | Handler | Behavior |
|----|--------|------|---------|----------|
| B1.3.1 | POST | `/api/reports/<key>/export/<job_id>` | `export_report` | Scope-checked. Enqueues export job with caller's layout dict (mirrors screen to file). 202 + `{export_id}`. |
| B1.3.2 | GET | `/api/reports/exports/<export_id>/download` | `download_export` | Owner+authz+type checked. Streams `.xlsx` from `ExportRepository.content(id)`. |
| B1.3.3 | GET | `/api/reports/exports` | `list_exports` | Owner-scoped; re-checks live report access per export. Returns last ≤15 export jobs with status/filename/size_bytes. |

### B1.4 — Lookup endpoints (dropdown data)

| ID | Method | Path | Handler | Returns |
|----|--------|------|---------|---------|
| B1.4.1 | GET | `/api/reports/lookups/status` | `lookup_status` | `LookupService.status()` — loading progress for dropdowns |
| B1.4.2 | GET | `/api/reports/<key>/salesmen` | `report_salesmen` | Scoped salesman list (visible_salesman_keys filter applied) |
| B1.4.3 | GET | `/api/reports/<key>/customers` | `report_customers` | Scoped customer list; optional `?salesman=` narrowing |
| B1.4.4 | GET | `/api/reports/<key>/years` | `report_years` | Descending year list from `today_eastern().year` back to `D365_GO_LIVE.year` |

### B1.5 — Customer's Last Order sub-API

| ID | Method | Path | Handler | Notes |
|----|--------|------|---------|-------|
| B1.5.1 | GET | `/api/report/customer-last-order/customers` | `customer_last_order_customers` | Scoped customer list |
| B1.5.2 | GET | `/api/report/customer-last-order/salesmen` | `customer_last_order_salesmen` | Scoped salesman list |
| B1.5.3 | GET | `/api/report/customer-last-order/<account>/recent-invoiced` | `customer_last_order_recent_invoiced` | Scope-enforced via `_clo_facts_or_403`; returns last 10 invoiced orders |

### B1.6 — Dev/preview endpoints

| ID | Method | Path | Handler | Notes |
|----|--------|------|---------|-------|
| B1.6.1 | POST | `/api/reports/<key>/preview-body` | `preview_body` | Developer-only. Builds SP params from current filter without calling API. Returns `{report_id, url, body}`. |
| B1.6.2 | GET | `/api/reports/diagnostics/reporting-api` | `reporting_api_diagnostics` | Developer-only. TCP + HTTP + optional live SP probe. |
| B1.6.3 | GET | `/api/reports/diagnostics/claim-once` | `claim_once_diagnostic` | Developer-only. Claims + immediately reverts one queued job — proves poller vs table issue. |
| B1.6.4 | GET | `/api/reports/diagnostics/precious-repair` | `precious_repair_diagnostic` | Developer-only. `?action=check|reindex|backup|delete-ghosts|rebuild-jobs`. |

### B1.7 — Presets + email + SharePoint (referenced in backbone; lines 860–1135 not fully read)

From backbone: `GET/POST /api/reports/<key>/presets`, `GET /api/reports/presets/<id>`, `GET /api/saved-reports`, `POST /api/reports/<key>/email-now`, `GET /api/sharepoint/status`, `GET /api/sharepoint/folders`.  
**⚠ QUESTION B1.7:** Blueprint lines 860–1135 not read. Exact request/response shapes for these 7–8 routes need a second pass.

---

## B2 — Orchestration (`v3/web/reporting/`)

### B2.1 — Filter params → SP params (`params.py`)

`translate(report_key, params)` is the single source of truth.

**Invoiced mapping** (`report_id = "invoiced_report"`):
- `period` → `InvoiceDateFrom` / `InvoiceDateTo` (ISO dates, not datetimes — contrast with Ordered which uses datetime strings)
- `customers`: only pushed when exactly 1 account (`CustomerAccount`); multi-select is post-filtered in Python
- `salesman` → `Salesman` (SalesGroup string)
- `all_time` / blank period → no date params; SP uses its own default

Period options exposed to invoiced: `period`, `customers`, `salesman` (from `REPORT_FILTERS["invoiced"]`).  
Year filter: NOT available for invoiced (only for salesman report).  
Status filter: NOT available for invoiced (only for ordered report).

### B2.2 — Invoiced orchestration (`report_service._orch_invoiced`)

```
1. Translate params → SP params (params.translate_invoiced)
2. Fetch period rows: _facts("invoiced_report", sp, src_invoiced.to_facts, visible_keys)
3. Compute YTD window:
     period_end = P.resolve_window(params)[1] or today_eastern()
     ytd_sp = {InvoiceDateFrom: Jan 1 of period_end.year, InvoiceDateTo: period_end.isoformat()}
4. Fetch YTD rows: _facts("invoiced_report", ytd_sp, src_invoiced.to_facts, visible_keys)
5. Multi-customer post-filter: if len(selected accounts) > 1, filter both facts lists in Python
6. Build: rpt_invoiced.build(facts, salesmen=salesmen_repo.all_as_facts(),
                             ytd_facts=ytd_facts, year=end.year, end_month=end.month)
7. Return payload: {report_key, tabs, row_count: len(facts)}
```

**Why two fetches:** the period window (filtered result) feeds tabs 1–7; the YTD window (Jan 1..period end) feeds the Commissions monthly pivot exclusively. They can differ if period = "last month" (period = just last month; YTD = Jan..last month end).

### B2.3 — Source adapter (`v3/report_engine/sources/invoiced.py`)

`to_fact(raw)` maps one SP row to `InvoiceChargeFact`:

| SP field aliases | Fact field | Notes |
|-----------------|-----------|-------|
| `InvoiceNumber`, `Invoice` | `invoice_number` | |
| `InvoiceDate`, `Invoice Date` | `invoice_date` | `iso_date()` → 'YYYY-MM-DD' |
| `CustomerAccount`, `InvoiceAccount` | `customer_account` | |
| `CustomerName` | `customer_name` | |
| `salesorder`, `SalesOrder` | `sales_order_number` | |
| `amount`, `Amount` | `subtotal` | rounded to 2dp |
| `Tariff Charges`, `TariffCharges`, `SL_TariffCharges`, `SH_TariffCharges` | `tariff` | |
| `Freight Charges`, `FreightCharges`, `SH_FreightCharges`, `SL_FreightCharges` | `freight` | |
| `CC Charges`, `CCCharges`, `SH_ProcessingFeesCharges`, `SL_ProcessingFeesCharges` | `cc` | |
| `Misc Charges`, `MiscCharges` | `misc` | |
| `Total Invoice`, `TotalInvoice` | `total` | if blank: computed as subtotal+tariff+freight+cc+misc |
| `salesman`, `SalesGroup` | `sales_group` | |
| `SalesmanName` | `salesman_name` | |
| `IsCredit`, `is_credit`, `IsCreditNote` | `is_credit` | bool; fallback: regex `CRD|CM|FC` on invoice_number |
| `commission`, `Commission`, `CommissionPct`, `Commission %` | `commission_pct` | fraction (0.06=6%); if >1 divide by 100 |

### B2.4 — InvoiceChargeFact type contract (`v3/report_engine/facts.py`)

Fields: `source`, `invoice_number`, `invoice_date` (YYYY-MM-DD), `customer_account`, `customer_name`, `sales_order_number`, `subtotal`, `tariff`, `freight`, `cc`, `misc`, `total`, `sales_group`, `salesman_name` (default ""), `is_credit` (default False), `commission_pct` (default 0.0).

### B2.5 — Runner + cache (`runner.py`, `cache.py`)

**Cache key** (single source of truth in `build_cache_key`):
```
SHA1(report_key | identity | scope_token | builder_version | SHA1(params_json))
```
- `scope_token` = `canonical_scope_token(visible_salesman_keys)` = "ALL" (unrestricted) | "NONE" (no keys) | sorted-comma-joined lowercased keys
- Two users with different scope → different key → never share cached payload
- `ReportRunner.run(fresh_within_seconds=300)` — cache hit if ≤5 min old; job handler forces `force_refresh=True` (always recomputes when queued)
- Cache stored in `cache.db` (`report_payload_cache` table); self-heals missing schema

### B2.6 — Job wiring (`jobs.py`)

Job type: `"report.run"`. Dedup key = cache key (same request collapses to one job).

`enqueue_report_run` stores in job params:  
`{report_key, identity, visible_keys, builder_version, params}`.

Handler: `make_report_run_handler(runner, builder_resolver)`:
1. Resolves builder by `report_key` via `builder_resolver`
2. Calls `runner.run(force_refresh=True)`
3. Logs to `ReportRunLogRepository` (best-effort; failure never fails the run)
4. Returns `outcome.cache_key` → stored as `job.result_ref`

Result read-back: `report_result` route fetches `cache.get(job.result_ref)`.

### B2.7 — Lookup service (`lookups.py`)

- `salesmen()` — distinct SalesGroup strings from customer universe + display names from salesman_master. Returns raw SalesGroup values (the string the SP expects), NOT normalized keys.
- `customers(salesman=None)` — distinct customers, optionally narrowed to one salesman
- `ensure_customers(accounts)` — validates selected accounts against mirror; triggers resync if unknown; returns still-unknown set
- Used by `run_report` to validate the `customers` param before enqueue

---

## B3 — Invoiced Builder (`v3/report_engine/reports/invoiced.py`)

Entry point: `build(facts, *, salesmen, ytd_facts=None, year=None, end_month=None) → list[dict]`

Tabs emitted in order:

### B3.1 — Tab 1: Summary by Customer (key: `"summary_by_customer"`)

**Always emitted.**

Group key: `(CustomerAccount, CustomerName, Salesman, SalesmanName)`.  
InvoiceCount = `len(unique InvoiceNumbers)` in the group (same logic as LIVE nunique).  
Credits included — money columns sum over ALL rows (credits carry negative values).

| # | Field | Header | Type |
|---|-------|--------|------|
| 1 | CustomerAccount | CustomerAccount | text |
| 2 | CustomerName | CustomerName | text |
| 3 | Salesman | Salesman | text |
| 4 | SalesmanName | SalesmanName | text |
| 5 | InvoiceCount | InvoiceCount | int |
| 6 | SubTotal Invoices | SubTotal Invoices | money |
| 7 | Total Tariff Charges | Total Tariff Charges | money |
| 8 | Total Freight Charges | Total Freight Charges | money |
| 9 | Total CC Charges | Total CC Charges | money |
| 10 | Total Misc Charges | Total Misc Charges | money |
| 11 | Total Invoices | Total Invoices | money |

Sorted by `CustomerAccount.lower()`.

### B3.2 — Tab 2: Commissions (key: `"commissions"`, layout: `"commission_cards"`)

**Always emitted.** Two modes based on whether `ytd_facts` + `year` + `end_month` are provided:

**Mode A — Monthly pivot** (normal path, ytd_facts provided):

Per-salesman YTD aggregation from `ytd_rows` (Jan 1..period end). Only salesmen with `commission_rate > 0` appear.

Monthly slot math per salesman per month `m`:
```
sub = sum(SubTotal Invoices) for non-credit rows in month m
tar = sum(Tariff Charges) for non-credit rows in month m
fre = sum(Freight Charges) for non-credit rows in month m
cc  = sum(CC Charges) for non-credit rows in month m
misc = sum(Misc Charges) for non-credit rows in month m
crd = sum(Total Invoice) for credit rows in month m   # negative values
ti  = sub + tar + fre + cc + misc
net = ti + crd - fre - cc
    = sub + tar + misc + crd         # simplified
comm = net * commission_rate          # kept unrounded for YTD accumulation
```

YTD sums these slot values then rounds at the end. `ytd.total_payable = ytd.commission`.

Flat table output (for on-screen + Excel): columns = Salesman, Commission %, `Comm Jan`…`Comm {end_month_abbr}`, YTD Commission. One row per salesman + TOTAL row. TOTAL row Commission % is blank string.

`salesmen` + `grand` + `month_labels` also embedded in the tab dict for the card UI.

**Mode B — Simple fallback** (no ytd_facts):

Uses summary rows directly. Commission base = SubTotal Invoices + Total Tariff Charges. commission = base × rate. Columns extend SUMMARY_COLS with: Percent (percent), Commission Base (money), Commissions (money). Sorted by Commissions descending.

**Commission rate resolution** (both modes):
1. `_row_rates_by_salesman`: max `commission_pct` the SP sent for that salesman across all rows (ignores blank/zero rows like credits)
2. If SP rate > 0 → use it
3. Else → `SalesmanFact.commission_pct` from salesman master
4. Rate is a fraction (0.06 = 6%)

### B3.3 — Tab 3: Full Details (key: `"full_data"`)

**Always emitted.** Uses `netted` (deduplicated by `InvoiceNumber` if duplicates detected).

If `_has_duplicate_invoices(raw)` → `_net_by_invoice(raw)` groups by InvoiceNumber, summing the 6 money fields; else uses raw list directly.

Sorted by `(CustomerAccount.lower(), InvoiceNumber)`.

| # | Field | Header | Type |
|---|-------|--------|------|
| 1 | InvoiceNumber | InvoiceNumber | text |
| 2 | CustomerAccount | CustomerAccount | text |
| 3 | CustomerName | CustomerName | text |
| 4 | InvoiceDate | InvoiceDate | date |
| 5 | SalesOrderNumber | SalesOrderNumber | text |
| 6 | Salesman | Salesman | text |
| 7 | SalesmanName | SalesmanName | text |
| 8 | SubTotal Invoices | SubTotal Invoices | money |
| 9 | Tariff Charges | Tariff Charges | money |
| 10 | Freight Charges | Freight Charges | money |
| 11 | CC Charges | CC Charges | money |
| 12 | Misc Charges | Misc Charges | money |
| 13 | Total Invoice | Total Invoice | money |

### B3.4 — Tab 4: Credits (key: `"credits"`)

**Always emitted.** Rows where `_is_credit == True`. Uses `raw` (not netted). Same sort as Full Details.  
Columns: `CREDIT_INVOICE_COLS` (13 columns, order differs from Full Details):

| # | Field | Header | Type |
|---|-------|--------|------|
| 1 | CustomerAccount | CustomerAccount | text |
| 2 | CustomerName | CustomerName | text |
| 3 | InvoiceDate | InvoiceDate | date |
| 4 | InvoiceNumber | InvoiceNumber | text |
| 5 | SalesOrderNumber | SalesOrderNumber | text |
| 6 | SubTotal Invoices | SubTotal Invoices | money |
| 7 | Tariff Charges | Tariff Charges | money |
| 8 | Freight Charges | Freight Charges | money |
| 9 | CC Charges | CC Charges | money |
| 10 | Misc Charges | Misc Charges | money |
| 11 | Total Invoice | Total Invoice | money |
| 12 | Salesman | Salesman | text |
| 13 | SalesmanName | SalesmanName | text |

### B3.5 — Tab 5: Invoices (key: `"invoices"`)

**Always emitted.** Rows where `_is_credit == False`. Uses `raw`. Same columns as Credits (CREDIT_INVOICE_COLS, 13 cols).

### B3.6 — Tab 6: Audit - Reversals (key: `"audit_reversals"`) — CONDITIONAL

**Emitted only when** any InvoiceNumber has both a positive Total Invoice row AND a negative Total Invoice row in `raw`. Detection: `lo < 0 < hi` for min/max per invoice.

Rows: all raw rows whose InvoiceNumber is in the flagged set. Sorted by (InvoiceNumber, InvoiceDate). Same 13-column CREDIT_INVOICE_COLS layout as Credits/Invoices.

### B3.7 — Tab 7: Totals by Salesman (key: `"totals_by_salesman"`) — CONDITIONAL

**Emitted only when** 2+ distinct non-blank Salesman values appear across `raw` rows.

Per-`(Salesman, SalesmanName)` aggregate: credits carry negative amounts and are summed in naturally (net-of-credits result). InvoiceCount = `len(unique InvoiceNumbers)` per salesman. Sorted by `(Salesman.lower(), SalesmanName)`.

| # | Field | Header | Type |
|---|-------|--------|------|
| 1 | Salesman | Salesman | text |
| 2 | SalesmanName | SalesmanName | text |
| 3 | InvoiceCount | InvoiceCount | int |
| 4 | SubTotal Invoices | SubTotal Invoices | money |
| 5 | Tariff Charges | Tariff Charges | money |
| 6 | Freight Charges | Freight Charges | money |
| 7 | CC Charges | CC Charges | money |
| 8 | Misc Charges | Misc Charges | money |
| 9 | Total Invoice | Total Invoice | money |

### B3.8 — Enriched row private fields

`_enriched(fact, salesmen)` adds private fields used for grouping/math, stripped by `_public()` before tab emission:
- `_sales_group` (raw SalesGroup string)
- `_is_credit` (bool)
- `_commission_pct` (fraction from SP)

`Salesman` = `fact.sales_group` or "Unassigned" if blank.  
`SalesmanName` = `fact.salesman_name` (from SP), falls back to `SalesmanFact.full_name` from Azure.

### B3.9 — Row filtering / scope

`filter_facts_by_scope(facts, visible_keys)` is applied in `ReportService._facts()` before facts reach the builder. Salesmen not in `visible_keys` are excluded at the source. The builder itself does NOT re-filter by scope.

---

## B4 — LIVE Comparison (format source of truth: `reports/invoiced/`)

Confirmed differences between LIVE (`reports/invoiced/aggregator.py`, `writer.py`) and v3:

### B4.1 — Summary tab: SalesmanNumber column

**LIVE:** Groups by `(CustomerAccount, CustomerName, SalesmanNumber, SalesmanName)` — includes `SalesmanNumber` in the group key and output columns.  
**v3:** Groups by `(CustomerAccount, CustomerName, Salesman, SalesmanName)` — uses `Salesman` (SalesGroup label). `SalesmanNumber` column was explicitly removed (REVIEW-LOG backbone note: "NO SalesmanNumber column").  
**⚠ DIFFERENCE (known/intentional):** v3 SUMMARY_COLS has no SalesmanNumber column.

### B4.2 — Summary tab: Misc Charges

**LIVE:** `aggregator.py` does NOT include "Misc Charges" in the summary aggregation (loop over `["SubTotal Invoices", "Tariff Charges", "Freight Charges", "CC Charges", "Total Invoice"]`).  
**v3:** SUMMARY_COLS includes `"Total Misc Charges"` and it is summed.  
**⚠ DIFFERENCE:** v3 summary tab shows Misc Charges; LIVE export does not. This appears intentional (v3 adds Misc where LIVE omitted it), but needs human sign-off.

### B4.3 — Commissions tab: rate source

**LIVE simple:** commission rate from `config/commission_map.py` keyed by SalesmanNumber (hardcoded map, not SP-per-row).  
**v3:** SP per-row `commission` field first; salesman_master fallback.  
**⚠ QUESTION B4.3:** Are these two commission rates always in sync? The REVIEW-LOG notes the SP `commission` field should be confirmed with a live capture before relying on it.

### B4.4 — Commissions net formula

**v3 monthly net per salesman per month:**  
`net = (sub + tar + fre + cc + misc) + crd - fre - cc`  
= `sub + tar + misc + crd`  
where `crd` = sum of Total Invoice for credit rows (typically negative).

**⚠ QUESTION B4.4:** The LIVE monthly commissions formula is in `writer.py` (lines 150+, not fully read). Confirm that LIVE's commission base excludes Misc in the net formula or matches v3. This is a calculation that must be verified against a live run before cutover.

### B4.5 — Totals by Salesman: credit treatment

**LIVE (`_maybe_write_totals_by_salesman` in writer.py):** Called with `invoices` DataFrame (non-credit rows only), so credits are excluded from salesman totals.  
**v3 (`_totals_by_salesman`):** Uses all `raw` rows; credits have negative Total Invoice and are summed in, producing net-of-credits totals.  
**⚠ DIFFERENCE:** These will agree only if all credits carry negative Total Invoice values (net = gross invoices + negative credits). If LIVE excludes credits entirely, the numbers could differ when a credit doesn't fully reverse its invoice. **Needs live comparison before cutover.**

### B4.6 — Tab order

**LIVE (writer.py):** Summary → Commissions → Full Details → Credits → Invoices → (Audit-Reversals) → (Totals by Salesman)  
**v3 builder (line 520):** `[summary, commissions, _full_details(netted), _credits(raw), _invoices(raw), (audit), (totals)]`  
Same order. ✓

### B4.7 — No "Misc Charges" column in LIVE Full Details / Credits / Invoices

**⚠ QUESTION B4.7:** The LIVE aggregator doesn't explicitly enumerate its detail-tab columns. Confirm whether LIVE's Full Details / Credits / Invoices sheets include a Misc Charges column. If not, v3's `FULL_DETAILS_COLS` and `CREDIT_INVOICE_COLS` (both include "Misc Charges") are additions. The backbone says "misc charges placement" was already verified — treat as confirmed in v3, but flag for the parity harness.

---

## B5 — Deferred Reports (endpoints exist, math not audited)

Registry (`v3/report_engine/registry.py`):

| Key | Title | SP | Status |
|-----|-------|----|--------|
| `ordered` | Ordered | salesline_release | BUILT (builder_version=2) |
| `invoiced` | Invoiced | invoiced_report | BUILT |
| `salesman` | Salesman | invoiced_order_charges | BUILT |
| `number_4` | Number 4 | invoice_lines | BUILT |
| `customer_activity` | Customer Activity | salesline_release | BUILT |
| `customer_last_order` | Customer's Last Order | salesline_release | BUILT (in_app=True) |
| `amazon_weekly` | Amazon Weekly | — | BACKLOG |
| `customer_aging` | Customer Aging | — | BACKLOG |

All non-invoiced BUILT reports share the same route infrastructure (B1.2.1–B1.2.5). BACKLOG reports are hidden/disabled in the UI and must never appear as working (registry enforces this at `_built_spec_or_404`).

---

## B6 — Security / scope safety properties to preserve

1. **Cache-scope safety:** `scope_token` is computed from `canonical_scope_token()` before building the cache key; the builder resolver never bypasses this.
2. **Scope-compatibility check on result read:** `_assert_scope_compatible` compares current vs job-time visible keys. A demoted user cannot read a wider-scoped cached payload.
3. **Job owner isolation:** `_owned_job_or_404` requires exact `owner_user_id` match; NULL-owner jobs are unreadable through the user API.
4. **Customer validation before enqueue:** unknown customer accounts are rejected before the job is queued (prevents enqueuing a run that would silently return nothing).
5. **No report work in request handlers:** enqueue-and-poll; inline drain only in dev/non-prod.

---

## B7 — Open Questions / Needs Human Sign-Off

| ID | Question |
|----|---------|
| B1.7 | Exact request/response shapes for presets, email-now, and SharePoint routes (blueprint lines 860–1135 not read) |
| B4.3 | Are SP per-row commission rates always equal to the commission_map values? Verify with a live capture. |
| B4.4 | Does LIVE monthly commissions formula include or exclude Misc in the commission base/net? Must match before cutover. |
| B4.5 | Do "Totals by Salesman" numbers agree between LIVE (credits excluded) and v3 (credits netted in)? Must verify with live data. |
| B4.7 | Does LIVE include a "Misc Charges" column in Full Details / Credits / Invoices sheets? |
