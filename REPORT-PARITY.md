# Phase 9.1 report-parity inventory

## Archive identity

The isolated archive worktree is `/tmp/achim-archive-pre-cleanup`, checked out
at tag `archive/pre-cleanup-2026-08-27`. The tag peels to
`b14d7252aca6f7643e3cbb899b9593ff6099d241` (`b14d725`). Both `webapp/` and
`rebuild/` exist in that worktree.

## Retained-report inventory

“Current v3 SQL path” means a `built_reports()` entry backed by the Reporting
API path, except Customer's Last Order, whose dedicated in-app page calls its
Reporting API path. “Shipped” is the salesman presentation of the Invoiced
path, not a second registry key.

| Report | Present in archive? | Current v3 SQL path? | Code-evidenced tabs / columns |
|---|---|---|---|
| Ordered | Yes | Yes | Summary, By Customer, By Item, By Order, By Salesman, Full Data; quantity, fulfillment, ordered/cancelled/shipping/open dollar columns. |
| Invoiced | Yes | Yes | Summary by Customer, Commissions, Full Details, Credits, Invoices; Audit - Reversals and Totals by Salesman when applicable. |
| Number 4 | Yes | Yes | By Customer (12 Months/YTD), By Item (12 Months/YTD); month Qty/$, Total Qty/$, Avg Price, Book Price, Salesman. |
| Customer Activity | Yes | Yes | All, one tab per salesman, Unassigned; customer account/name, last-order date, PO #, sales-order number. |
| Customer's Last Order | Yes | Yes | In-app customer picker and latest logical-order view; Item#, ItemName, QtyOrdered/Shipped/Cancelled, UnitPrice, Total. |
| Item Averages | Yes | Yes | Item Averages; Item #, Item Name, 12-Month Qty, Avg/Month, Avg/Week. |
| Sales by State | Yes | Yes | Summary, New York City, Detail; state and sales amounts, plus invoice/address detail. |
| Customer Aging | Yes | No — BACKLOG | Archive workbook: All Customers plus one salesman sheet; customer, balance, payment, open-invoice, Current/30/60/90/91+ columns. |
| Salesman | Yes | Yes | Jan–Dec tabs; salesman/customer and this-year, last-year, YTD, full-year dollar and percent comparisons. |
| Shipped | Yes — archive calls Invoiced “Shipped Report” for non-admin users | Yes — Invoiced path with commissions omitted for salesman-scoped output | Invoiced tabs except Commissions; no separate report key. |

Current v3 has eight `BUILT` registry entries and one `BACKLOG` entry
(Customer Aging). The archive contains all ten named report presentations in
this table, including the Shipped alias and legacy Customer Aging.

## Approved intentional differences

- v3 is SQL/Reporting-API only; OData remains outside v3 for CLI/Azure
  Automation.
- In-app email distributions are retired (Q6).
- The approved salesman-table commission-display policy is Q3; later removal
  of that table leaves `salesmen_master` as the current v3 source.
- Ordered Summary grouping follows CustomerAccount (Q4).
- `/legacy`, `/test`, and `/test-next` mounts remain present by decision.

## Code-level tab and column comparison

This compares the isolated archive's builders/exporters with current v3
builders. It records code shape only, not report values, totals, or live D365
behavior. `match` means the listed tab/column shape is the same in the source
compared. `intentional-diff` cites an approved decision. `unknown` means code
shows a difference whose business equivalence cannot be proved here.

| Report | Archive builder / exporter | Current v3 SQL builder | Tab comparison | Column comparison | Result |
|---|---|---|---|---|---|
| Ordered | `reports/ordered/writer.py` | `v3/report_engine/reports/ordered.py` | Summary, By Customer, By Item, By Order, By Salesman, Full Data — match. | Archive has QtyShipped/QtyOpen and shipped/released-dollar fields; v3 has SP QtyReserved/QtyReleased/QtyLeftToShip and Shipping $. The source change does not prove equivalent semantics. | unknown |
| Invoiced / Shipped | `reports/invoiced/writer.py` | `v3/report_engine/reports/invoiced.py` | Invoiced: Summary by Customer, Commissions, Full Details, Credits, Invoices, conditional Audit - Reversals and Totals by Salesman — match. Shipped omits Commissions — match. | Summary/detail/credit/invoice and salesman-total fields match. Current commission output preserves an explicit zero Reporting-API rate instead of falling back to a master rate. | intentional-diff (Q2) |
| Number 4 | `reports/number_4/writer_customer.py`, `writer_item.py` | `v3/report_engine/reports/number_4.py` | By Customer (12 Months/YTD), By Item (12 Months/YTD) — match. | By Customer month Qty/$, Total Qty/$, Avg Price, Salesman, Book Price — match. Archive By Item is quantity-only; current By Item keeps month $, Total $, Avg Price, and Book Price. No approved decision explains the difference. | unknown |
| Customer Activity | `reports/customer_activity/writer.py` | `v3/report_engine/reports/customer_activity.py` | All, one salesman tab per assigned salesman, Unassigned — match. | All starts with Salesman; remaining fields are Customer Account, Customer Name, Last Order Date, PO #, Sales Order Number. Per-salesman/Unassigned omit Salesman — match. | match |
| Customer's Last Order | `webapp/blueprints/reports.py`, `webapp/services/d365.py` | `v3/report_engine/reports/customer_last_order.py` | In-app customer picker with newest order and prior-order merge — match. | Item#, description, QtyOrdered, QtyShipped, QtyCancelled, UnitPrice, Total — match. Archive selects invoiced orders; current SQL contract says it includes open and uninvoiced logical orders. Code cannot establish equivalent result scope. | unknown |
| Item Averages | `v3/report_engine/reports/item_averages.py` at `b14d725` | `v3/report_engine/reports/item_averages.py` | Item Averages — match. | Item #, Item Name, 12-Month Qty, Avg/Month, Avg/Week — match. Builder source is unchanged. | match |
| Sales by State | `v3/report_engine/reports/sales_by_state.py` at `b14d725` | `v3/report_engine/reports/sales_by_state.py` | Summary, New York City, Detail — match. | State/sales totals; NYC invoice/address fields; detail invoice/date/customer/address fields — match. Builder source is unchanged. | match |
| Salesman | `reports/salesman/writer.py` | `v3/report_engine/reports/salesman.py` | Jan through Dec — match. | Salesman/customer, month current/prior sales, dollar/percent change, YTD current/prior/change, full-year current/prior/change — match. Current `band` metadata preserves the archive's three display bands. | match |

Finding count: 4 match, 1 intentional-diff, 3 unknown. Customer Aging is
intentionally excluded: it remains BACKLOG and has no current v3 SQL path.

## Deferred golden/workbook comparison

This inventory does not claim value parity. A later frozen-golden/workbook
comparison must cover relevant periods, filters, scoped roles, tab lists,
column semantics, totals, exports, and scheduled workbooks, including Ordered
shipping/remainder, Invoiced credits/commissions, Number 4 YTD, Customer
Activity, Customer's Last Order, Item Averages, and Sales by State. No live
D365 query was made in this slice. Customer Aging is BACKLOG until v3 gains a
real Reporting-API path.

Old apps were NOT mounted on the leftover branch.

## Code-level totals, exports, role scope, and scheduled workbooks

This is a source comparison of the isolated `b14d725` archive and current v3.
It does not compare report values, workbook bytes, or live D365 behavior.

- **Ordered — unknown.** Both implementations write literal computed totals,
  not Excel `SUM` formulas. The archive writer creates per-customer Summary
  totals plus literal totals on the other sheets; current v3's common XLSX
  exporter totals typed money/int fields (and does not total Net Price).
  Shipping/remainder fields remain the existing unknown, so their total
  equivalence cannot be established. Both produce XLSX, not CSV. Archive
  salesman output omitted By Salesman; current scoped output omits it too.
- **Invoiced / Shipped — intentional-diff (Q2).** Archive and current write
  literal computed totals, including the commission workbook's monthly/YTD
  values; neither source writes Excel formulas. Both export XLSX only, with
  the same workbook tabs and Shipped omitting Commissions. Current v3 keeps an
  explicit zero Reporting-API commission rate rather than falling back to a
  master rate, as approved by Q2. Scheduled salesman-scoped output reapplies
  live authorization and omits Commissions.
- **Number 4 — unknown.** Archive totals are literal per-group and grand
  calculations; current v3 precomputes month/Total Qty/Total $ values and the
  common exporter adds literal typed-field totals. Both export XLSX only.
  Archive By Item is quantity-only, while v3 carries dollars, price, and book
  price; the existing unapproved By Item-dollar difference also prevents a
  totals-equivalence finding. Scope filtering is applied before the workbook.
- **Customer Activity — unknown.** Both produce XLSX only and retain the
  All/per-salesman/Unassigned workbook shape. Archive writes a literal
  `Total (<count> customers)` footer on every sheet; v3's generic exporter
  writes a `Total` footer but has no numeric customer-count field to sum.
  Role filtering is present in both paths, but the changed footer is not tied
  to an approved product decision.
- **Customer's Last Order — unknown.** Both calculate literal line totals and
  displayed totals. This report uses a PDF export, not XLSX/CSV; the current
  PDF writer is unchanged from the archive v3 implementation. The archive
  selected invoiced orders while current v3 includes open/uninvoiced logical
  orders, so total and role-scope equivalence remains the existing unknown.
  It has no scheduled workbook builder.
- **Item Averages — match.** The unchanged v3 builder computes 12-month Qty,
  Avg/Month, and Avg/Week before common XLSX export; no CSV or Excel formulas
  exist. It is privileged-only, so no salesman-scoped workbook is built.
- **Sales by State — match.** The unchanged v3 builder keeps its SQL totals as
  values and uses the common XLSX-only exporter; no CSV or Excel formulas
  exist. It is company-wide and not salesman-scoped.
- **Salesman — unknown.** Archive writes literal per-salesman and grand
  monthly totals, including calculated percentage changes. Current v3 computes
  row percentages before its common XLSX-only exporter, whose generic footer
  intentionally leaves percent columns blank. Role filtering occurs before
  the 12 Jan–Dec sheets, but the changed percentage-footer behavior has no
  approved decision.

Current v3 uses one `build_workbook()` path for standard report exports and
one `DeliveryService.run_and_deliver()` path for scheduled XLSX workbooks.
Personal schedules re-authorize the owner and retain that owner's salesman
scope; master schedules are unrestricted unless explicitly run as a
non-privileged user, then use that user's scope. Invoiced scheduled workbooks
also remove Commissions for principals without commission access. Archive
legacy runners generated separate management and salesman files; current
master schedules can fan out selected salesman workbooks plus a full
management copy. This is an implementation change, not proof of equivalent
deliveries.

Frozen XLSX goldens are **blocked**: a fixture search found no in-repository
`.xlsx` or `.xlsm` workbook fixture in either worktree. Owner-provided sample
workbooks are required; none were invented. Customer Aging remains BACKLOG.

Totals/export/role-scope outcome count: 2 match, 1 approved intentional-diff,
5 unknown; Customer Aging BACKLOG. Focused current-v3 report/export/schedule
tests: `cd v3 && python3 -m pytest tests/test_reporting.py
tests/test_report_service.py tests/test_report_ordered.py
tests/test_report_invoiced.py tests/test_report_number_4.py
tests/test_report_customer_activity.py tests/test_report_customer_last_order.py
tests/test_report_item_averages.py tests/test_report_sales_by_state.py
tests/test_report_salesman.py tests/test_scheduling.py -q` — 240 passed.
