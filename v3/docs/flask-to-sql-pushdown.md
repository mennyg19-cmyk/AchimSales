# Flask -> SQL Server Push-Down Inventory

**Date:** June 11, 2026
**Audience:** DB manager / DBA
**Scope:** the v3 reports app (Azure App Service, Flask) and the on-prem Reporting API
stored procedures it calls via `POST /api/reports/<report_id>/run`.

**Goal:** all report logic should run on the SQL Server and arrive ready-to-display in
the API response. This document lists everything the Flask app currently computes
*after* the API responds, whether it can move into the stored procedures, and what's
needed to get it there.

How to read the verdicts:

| Verdict | Meaning |
|---|---|
| **Movable** | Pure SQL, no blockers. Can move into the SP today. |
| **Movable\*** | Movable, but needs the salesman master synced to on-prem first (see below), or the payoff is low. |
| **Fix SP** | Not new logic - an SP contract/behavior change. |
| **Stays** | Authorization, presentation, or infrastructure. Stays on Azure by design. |

---

## The one gating dependency: the salesman master

Salesman names, numbers, and commission percentages are admin-edited inside the Azure
app (a local SQLite table). Every report joins this table to turn a raw `SalesGroup`
string into a display name / salesman number / commission %.

Until that table is mirrored to the on-prem SQL Server (it's tiny - a nightly or
on-save sync would do) or passed as a parameter, anything salesman-aware can only move
its raw math, not its labels. **Decide this first; it unblocks every starred item.**

---

## Biggest wins, ranked by data transfer saved

1. **Customer Activity: last-order-per-customer SP.** Today Flask downloads *every
   order line since go-live* on every run just to find each customer's most recent
   order. A `ROW_NUMBER() OVER (PARTITION BY CustomerAccount ORDER BY OrderDate DESC)`
   query returns one row per customer instead.
2. **Number 4: do the joins in the SP.** Flask downloads the **entire**
   `released_products` table (for Book Price) and the **entire** `customer_master`
   (for a fallback rep) on every run. All three tables live in the same on-prem
   database - these are one-line JOINs.
3. **Monthly Salesman: pivot in SQL.** Two full years of raw invoice rows ship to
   Azure to produce a small pivoted comparison table.
4. **Invoiced: one call instead of two + CSV customer filter.** The app calls the same
   SP twice per run (selected period + YTD for commissions), and post-filters
   multi-customer selections in Flask because `InvoiceAccount` only accepts one value.
5. **Row-level derived columns.** QtyOpen, Open $, Released $, Fulfillment %,
   Total Invoice, IsCredit - small per-row, but removes Flask math entirely for those
   columns.

> Caveat: where a report displays raw detail rows on screen (Ordered "Full Data",
> Invoiced "Invoices"/"Credits" tabs), those rows must cross the wire no matter what.
> Pushing only the aggregation down saves Azure CPU, not bandwidth.

---

## Per-report breakdown

### Invoiced (SP: `invoiced_order_charges`)

Current fetch: called **twice** per run - once for the selected period, once for
Jan 1 .. period-end (feeds the commissions pivot). Multi-customer selections are
filtered in Flask because the SP's `InvoiceAccount` only takes one exact value.

| Flask logic today | Push-down note | Verdict |
|---|---|---|
| Credit detection | `CRD` / `CM` / `FC` substring anywhere in the invoice number (case-insensitive). One PATINDEX/LIKE - return an `IsCredit` flag column. | Movable |
| Total Invoice = SubTotal + Tariff + Freight + CC | Row arithmetic; SP can return the total column. | Movable |
| Reversal netting ("Full Details" tab) | GROUP BY InvoiceNumber, SUM the money columns (reversal pairs net to zero). Could be a second result set or a mode parameter. | Movable |
| Summary by (customer, salesman) | GROUP BY + COUNT(DISTINCT InvoiceNumber). Needs salesman number/name (Azure-side master). | Movable\* |
| "Audit - Reversals" tab | Invoice numbers with both positive and negative totals: `GROUP BY .. HAVING MIN(total) < 0 AND MAX(total) > 0`. | Movable |
| Monthly commissions pivot | Per salesman per month: Net = Total + Credits - Freight - CC; Commission = Net x pct. SQL-friendly math, but commission % and salesman numbers live in the Azure master. | Movable\* |
| Multi-customer filter | Make `InvoiceAccount` accept a CSV of accounts like `salesline_release`'s `CustomerAccount` already does. | Fix SP |
| Double fetch for YTD | Let one call return both windows (extra date params or a second result set). | Fix SP |

### Ordered (SP: `salesline_release`)

Current fetch: one call for the period. This SP already does the heavy lifting -
`Ordered $` / `Shipped $` / `Cancelled $` come back precomputed with the WHS +
packing-slip math.

| Flask logic today | Push-down note | Verdict |
|---|---|---|
| QtyOpen = QtyOrdered - QtyShipped - QtyCancelled | Computed column. | Movable |
| Released $ = QtyReleased x SalesPrice; Open $ = Ordered$ - Shipped$ - Cancelled$ | Computed columns. | Movable |
| Fulfillment % = (ordered - cancelled) / ordered, clamped 0..1 | Computed column. | Movable |
| ERROR ITEM filter | `WHERE Item NOT LIKE '%ERROR%ITEM%'` in the SP. | Movable |
| 5 aggregate tabs (By Customer / Item / Order / Salesman, Summary) | All GROUP BYs - but the "Full Data" tab shows every line anyway, so detail rows travel regardless. Saves CPU, not transfer. | Movable\* |
| Duplicate LineNumber-0 rows | The SP returns some order+line keys 4x. Dedupe belongs in the SP. | Fix SP |

### Monthly Salesman (SP: `invoiced_order_charges`)

Current fetch: two full years (prior Jan 1 .. selected Dec 31), pivoted in Flask.

| Flask logic today | Push-down note | Verdict |
|---|---|---|
| Sales = Total Invoice - CC - Freight | Row arithmetic. | Movable |
| 12-month current-vs-prior pivot ($/% diffs for month, YTD, full year) | Classic conditional aggregation. Output is small; input is two years of invoices - big transfer win. | Movable\* |
| Salesman name/number + zero-padded sort key | Needs the salesman master on SQL. | Movable\* |

### Number 4 (SPs: `invoice_lines` + `released_products` + `customer_master`)

Current fetch: a 13-month `invoice_lines` window, **plus the entire
`released_products` table, plus the entire `customer_master`** - three calls, two of
them full-table dumps used only for joins.

| Flask logic today | Push-down note | Verdict |
|---|---|---|
| Book Price join | Whole `released_products` download to look up one `SalesPrice` per item (joined on upper-cased ItemNumber). One JOIN in the SP. Clearest win in the app. | Movable |
| Salesman fallback to the customer master rep | `COALESCE(line.SalesGroup, cm.SalesGroup)` via JOIN instead of a full `customer_master` download. | Movable |
| Free-text line exclusion | Lines with a blank SalesOrder are dropped: `WHERE SalesOrder <> ''`. | Movable |
| Rolling-12 / YTD month pivots + Avg Price | GROUP BY item/customer/salesman with month buckets. Pivoted output is far smaller than 13 months of raw lines. | Movable\* |

### Customer Activity (SPs: `salesline_release` + `customer_master`)

Current fetch: **all-time** `salesline_release` (go-live .. today - every order line
in history) just to find each customer's most recent order. Heaviest call in the app.

| Flask logic today | Push-down note | Verdict |
|---|---|---|
| Last order per customer (date, PO #, SO #) | `ROW_NUMBER() OVER (PARTITION BY CustomerAccount ORDER BY OrderDate DESC)` - return ONE row per customer. `customer_master` already carries a LastOrderDate; extend it (or a new SP) with that order's PO/SO. Biggest transfer win in the app. | Movable |
| Universe left-join (customers with no orders show "N/A") | LEFT JOIN `customer_master` to the last-order rows in the same SP. | Movable |
| Per-salesman tab fan-out + scope filtering | Tab splitting is presentation; scope is authorization. Both stay on Azure. | Stays |

### Customer's Last Order (SP: `salesline_release`, one customer)

Current fetch: one customer's full history (go-live .. today).

| Flask logic today | Push-down note | Verdict |
|---|---|---|
| Invoiced-order detection (line SalesStatus contains "invoiced") | WHERE clause / flag in the SP. | Movable |
| Rollup by (item, sales price); Total = price x qty shipped | GROUP BY in the SP - but one customer's rows are few, so payoff is modest. | Movable\* |
| Common PO prefix for merged orders | String fiddling for one header label. Not worth SQL. | Stays |

---

## Cross-cutting (applies to every report)

| Flask logic today | Push-down note | Verdict |
|---|---|---|
| Field-name normalization | Adapters try 3-5 column-name variants per field (`Invoice` vs `InvoiceNumber`, `SH_` vs `SL_` charge prefixes...) because SP revisions drifted. Lock the output contracts: stable column names, real numerics, no literal `'NULL'` strings. | Fix SP |
| Date parsing | Invoice dates have come back both as ISO and as RFC-1123 (`Thu, 30 Apr 2026 00:00:00 GMT`). Always return ISO (`YYYY-MM-DD`). | Fix SP |
| Salesman enrichment (name, number, commission %) | The gating dependency described above. | Movable\* |
| Scope / authorization filtering | Flask restricts rows to the viewer's salesman book. SalesGroup params can ALSO be pushed to the SP to cut transfer, but Azure must keep enforcing it - never trust a caller-supplied filter alone for security. | Stays |
| Excel export, background jobs, caching, schedules, email, dashboard mirror | Presentation and infrastructure. | Stays |

---

## Architecture note (for the app side, not the DBA)

Today the SPs are flat data dumps and `v3/report_engine/` holds the live-app math,
guarded by parity tests in version control. Every push-down moves business logic out
of git and out of those tests and into the database. Each moved calculation needs its
numbers re-verified against the live app, and the parity harness pointed at the new SP
output. Worth it for the transfer-heavy items (wins 1-4); marginal for plain row
arithmetic.
