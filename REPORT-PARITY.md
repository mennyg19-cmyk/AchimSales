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

## Deferred golden/workbook comparison

This inventory does not claim value parity. A later frozen-golden/workbook
comparison must cover relevant periods, filters, scoped roles, tab lists,
column semantics, totals, exports, and scheduled workbooks, including Ordered
shipping/remainder, Invoiced credits/commissions, Number 4 YTD, Customer
Activity, Customer's Last Order, Item Averages, and Sales by State. No live
D365 query was made in this slice. Customer Aging is BACKLOG until v3 gains a
real Reporting-API path.

Old apps were NOT mounted on the leftover branch.
