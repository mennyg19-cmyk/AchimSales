# Report and feature parity

Compared current `v3/` (this branch) to isolated archive `archive/pre-cleanup-2026-08-27` (`b14d725`) at `/tmp/achim-archive-restore`. Old apps were not mounted. `tools/parity` stayed in that worktree (it compared live `/` vs `/test` Excel and is obsolete here).

**Method:** structural (tabs, columns, filters, role defaults, export/schedule layouts) plus named builder tests. **Live SQL/Excel totals vs Production are BLOCKED** — `REPORTING_API_BASE_URL` is unset in this environment.

**Builders identical to archive** (byte-level `diff -q`): Number 4, Customer Activity, Customer Last Order, Item Averages, Sales by State, Salesman. Ordered, Invoiced, dates, and invoiced source adapter differ as recorded below.

## Retained web reports

Source of keys: `v3/report_engine/registry.py`. Customer Aging is BACKLOG on the web (no fake stub). CLI/Azure Automation still has `reports/customer_aging`.

| Key | Title | Role default | Filters (viewer → SP) | Evidence |
|-----|-------|--------------|----------------------|----------|
| `ordered` | Ordered | salesman inherit-on | period/custom dates, customers, salesman, status, order_no, item | `test_report_ordered.py` |
| `invoiced` | Invoiced | salesman inherit-on | period/custom dates, customers, salesman | `test_report_invoiced.py` |
| `salesman` | Salesman | inherit-hidden | year, through_month, salesman, customer | `test_report_salesman.py` |
| `number_4` | Number 4 | inherit-hidden | mode both/by_customer/by_item (AsOfDate always today) | `test_report_number_4.py` |
| `customer_activity` | Customer Activity | salesman inherit-on | order_count, as_of_date, salesman, customer | `test_report_customer_activity.py` |
| `customer_last_order` | Customer's Last Order | inherit-hidden, in-app picker | customer_account, order_count, as_of_date | `test_report_customer_last_order.py` |
| `item_averages` | Item Averages | privileged (admin/developer only) | same window as Number 4 By Item | `test_report_item_averages.py` |
| `sales_by_state` | Sales by State | inherit-hidden | year or custom FromDate/ToDate, company | `test_report_sales_by_state.py` |
| `customer_aging` | Customer Aging | not built on the web | CLI/Automation only | registry BACKLOG |

Managers see every built report by default. Salesmen see inherit-on reports unless `user_report_access` says otherwise. Scope at run time: `visible_salesman_keys`.

### Ordered

Tabs (live order): Summary, By Customer, By Item, By Order, By Salesman, Full Data. Salesman-scoped variant drops By Salesman (`test_tab_order_matches_live`, `test_salesman_variant_drops_by_salesman_tab`).

Shipping / remainder: QtyReleased header is “QTY Shipping”; Released $ header is “Shipping $”; Open $ = Ordered − Shipped − Cancelled; Summary “Extended Price Remainder” is SP `ShippingDollars` only (no fallback math). No QtyShipped column. Fulfillment % on rolled-up tabs, not Summary. ERROR ITEM dropped by item number.

**Approved diff (Q4):** Summary groups by `CustomerAccount` (plus item), not customer name. Archive grouped by name. Test: `test_report_ordered.py` (`CustomerAccount` on summary columns).

### Invoiced

Tabs: Summary by Customer, Commissions (omitted when `skip_commissions`), Full Details, Credits, Invoices, Audit-Reversals when a ± pair exists, Totals by Salesman when 2+ salesmen. Credits split by `is_credit` / invoice-number substring.

**Approved diffs (Q1–Q3):** SP `commission` is a fraction (`1` = 100%; values **above** 1 divide by 100). Each invoice’s own rate; SP `0` stays $0; no fallback to `salesmen.commission_pct` for dollars. Commissions-tab % box still shows leftover `salesmen.commission_pct`. Tests: `test_commission_one_means_one_hundred_percent`, `test_zero_sp_commission_pays_zero_and_keeps_table_percent`, `test_commissions_use_sp_rate_over_master`.

### Number 4

Tabs: By Customer (12 Months), By Customer (YTD), By Item (12 Months), By Item (YTD). YTD is a slice of the rolling-12 pivot (no YTD SP). By Item drops money columns. Rows group by Item #. Tests: `test_both_views_build_four_tabs_in_order`, `test_ytd_drops_prior_year_months_and_recalcs_totals`.

### Customer Activity

Tabs: All, then one tab per salesman (Unassigned last). Columns: Salesman (All only), Customer Account, Customer Name, Last Order Date, PO #, Sales Order Number.

### Customer Last Order

In-app: newest logical order (Order Rank 1); “previous order” merges ranks; ADDON POs already rolled by SP. Line columns: item, description, qty ordered/shipped/cancelled, sales price, total.

### Item Averages

One tab. Item #, Item Name, 12-Month Qty, Avg/Month (/12), Avg/Week (/52). No dollar columns. Privileged-only.

### Sales by State

Tabs: Summary, New York City, Detail. Web/SQL only (not in CLI `report_registry.json`).

### Salesman

Twelve month tabs (Jan–Dec) from `monthly_salesman_yoy`. Inherit-hidden for salesmen.

## Exports and company workbooks

Interactive export is a `report.export` worker job (`export_jobs.py`), not in-request. Workbook tests: `test_reporting.py` (`test_export_produces_valid_xlsx`, grouping/subtotals, formula neutralization).

Company Ordered layouts (`v3/web/scheduling/company_layouts.py`), identical to archive: **Daily Ordered** (yesterday, By Customer first) and **Heshy Open Orders** (Hkaufman, Open order, Full Data).

## Other approved diffs (not per-report math)

| Change | Why |
|--------|-----|
| Web path is SQL/Reporting API only; no OData under `v3/` | Phase 3. CLI/Automation may still use OData. |
| Custom period start after end is rejected | Phase 6. Archive swapped or omitted. |
| Period aliases `month` / `week` | `dates.py` vs archive `last_month` / `last_7_days` only. |
| In-app email distributions gone | Q6. See below. |

## Feature parity

**In-app email distributions (Q6):** stay retired. Archive had `webapp/services/email_distributions.py` (SharePoint-path bundles, 15-minute thread). No `email_distribution` code under current `v3/`. Azure Automation + company/personal schedules are the send paths.

**Azure Automation:** `runbooks/universal_runbook.py` and `report_registry.json` are identical to the archive. Registry keys: ordered, invoiced, salesman, number_4, customer_activity, customer_aging, log_digest. README documents the SharePoint `Direct Reports/` folders. **Live Azure schedule list / that every Automation job still fires is owner BLOCKED** (no Automation API from this environment).

**Deleted routes/tools not needed for support:** `/legacy`, `/test`, `/test-next`, `webapp/`, `rebuild/` exist only on the archive tag. `/beta` stays a 302 (Q7) through Production cutover. Re-run live Excel compare from the isolated worktree; do not copy `tools/parity` into this repo.

## Live numeric gate (not this environment)

To compare Production Excel totals later: Reporting API + an approved staging/prod run, or restore `tools/parity` only in the archive worktree against two SQL-backed apps. Do not treat fixture tests as a substitute for that owner drill.
