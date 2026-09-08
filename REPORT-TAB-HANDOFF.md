# Report tab handoff — what Flask does vs what SQL should own

For the owner and whoever owns the office stored procs. This is the current **home site** (`v3/`), not his new React app.

**Target:** one POST per user-facing report. SQL returns a flat table (and commission/YTD numbers already finished). The web app filters, groups in the grid, exports, and emails. No invoice math in Python.

Dummy response shape (Invoiced): `sample-invoiced-response.json`. Top level `data.raw` + `data.tabs.<tab>.rows`.

His preview already works that way for Invoiced Full Data. The leftover on our side is the **workbook clone**: extra tabs and extra API pulls so Excel looks like last year’s Live file.

Customer Aging has no v3 SQL path (BACKLOG). It is not in this list.

---

## What can stay in the app (like his)

These are presentation, not math:

- Date / customer / salesman filters on the request
- Hide rows the signed-in salesman is not allowed to see
- Grid group-by (By Customer, By Salesman, By Item, By Order)
- Show/hide columns, saved views
- Excel of the **visible** layout
- Date formatting (GMT midnight → calendar day)
- Subtotals of numbers SQL already returned

If a “tab” is only grouping the same rows, **do not build it in SQL or Python**. The grid does it.

---

## What must move to SQL (or we keep the slow Python)

Anything that **creates new numbers**, **splits rows into different tables**, or **calls a second stored proc** to feed a tab.

Locked commission rules (do not reinvent):

- SP `Commission` / `commission_pct` is a **fraction**: `0.06` = 6%, `1` = 100%.
- Dollars use **that invoice’s rate**. An explicit `0` stays `0` (do not fall back).
- If the invoice has no rate, use `salesmen_master` `CommissionPercentage` (same fraction).

---

## Invoiced (and Shipped)

**SQL today:** `invoiced_report` — one row per invoice (amounts, charges, Total Invoice, salesman, commission **rate**).

**Extra pulls today:** if the Commissions tab will show, Flask also pulls **Jan 1 → period end** (sometimes a second call) so monthly/YTD cards have a full year.

| Tab | What Flask does | Move to SQL? | Or grid-only? |
|---|---|---|---|
| Full Details | Rename columns; if SQL still sends two rows per invoice, net them | Netting belongs in SQL | This **is** the SP table. His Full Data. |
| Credits | Keep rows flagged as credit | SQL can send `IsCredit` | Grid filter `IsCredit = true` |
| Invoices | Non-credit rows | same flag | Grid filter `IsCredit = false` |
| Audit - Reversals | Same invoice number with both + and − totals | SQL can flag `IsReversalPair` | Grid filter |
| Summary by Customer | GROUP BY customer + salesman; count invoices; sum money | Optional SQL view | **Grid group-by** on Full Data |
| Totals by Salesman | Sum per salesman, credits subtracted; only if 2+ salesmen | Optional | **Grid group-by** |
| Commissions (admin) | Month buckets Jan–period; **dollar math** below; cards UI | **Yes — this is the one that hurts** | Not a group-by. Needs its own result (or extra columns). |

**Commission math to put in SQL** (copied from current Flask; matches old Live):

Per salesman, per month, using **non-credit** invoice money and **credit** totals:

1. `total_invoices` = subtotal + tariff + freight + CC + misc  
2. `net` = `total_invoices` + `credits` − freight − CC  
   (`credits` are the credit invoices’ Total Invoice, already negative)  
3. `commission` = `net` × rate (fraction)  
4. YTD = sum of those months through the selected month  

Shipped is the same Invoiced path with the Commissions tab dropped (no extra YTD pull).

**One-call shape:** either  

- one SP that returns invoice rows **plus** a second result set of monthly commission rows, or  
- invoice rows that already include `CommissionDollars` and `NetCommissionBase` so the grid can group them.

Until SQL does that, we cannot drop the Python commissions tab and still match today’s cards.

---

## Ordered

**SQL today:** `ordered_report` — line rows. Qty and most $ come from the SP.

**Extra pulls today:** a bounded date range is fetched **month by month** so a big YTD does not time out. That is several calls for one screen.

| Tab | What Flask does | Move to SQL? | Or grid-only? |
|---|---|---|---|
| Full Data | Map SP names (ReleasedQuantity → “QTY Shipping”, ShippingDollars → “Shipping $”). Drop “ERROR ITEM” lines. **Open $** = Ordered $ − Shipped $ − Cancelled $. **Fulfillment %** = (QtyOrdered − QtyCancelled) / QtyOrdered | Open $ and Fulfillment % belong in SQL. Drop ERROR ITEM in SQL. | This is the line table. |
| Summary | Line list with a few renamed money headers | No extra math | Grid / layout |
| By Customer / By Item / By Order / By Salesman | Sum qty and $ for that key; recompute Fulfillment % on the totals | Optional SQL | **Grid group-by** on Full Data |

**One-call shape:** one SP, one date window (raise timeout or page in SQL if needed). Stop month-chunking in the app. Return `OpenAmount` and `FulfillmentPct` on every line.

---

## Number 4

**SQL today:** two rolling-12 SPs (`customer_item_sales_rolling_12`, `item_customer_sales_rolling_12`). Each row is already a 12-month pivot (qty and $ per month, totals, avg price, book price).

**Extra pulls today:** “Both” = two POSTs. Flask then **builds YTD tabs** by dropping prior-year month columns and recounting Total Qty / Total $ / Avg Price. There is no YTD stored proc.

| Tab | What Flask does | Move to SQL? | Or grid-only? |
|---|---|---|---|
| By Customer 12 months | Type columns; fill missing Total $ / Avg / Book if blank | Fill-ins belong in SQL | Show the SP table |
| By Customer YTD | Slice current-year months; recalc totals; drop empty rows | **Yes — YTD SP or YTD columns on the same rows** | Not group-by |
| By Item 12 months / YTD | Same | Same | Same |

His app concatenates both SPs with a `Source` column (still two calls unless SQL wraps them).

**One-call shape (ideal):** one catalog key that returns By Customer + By Item + YTD months already calculated. Minimum: add YTD totals on the existing rolling-12 rows so Python stops slicing.

---

## Salesman (monthly YoY)

**SQL today:** `monthly_salesman_yoy` — wide row per salesman + customer (Jan–Dec this/last year, YTD, full year). Sales basis is Total Invoice **in SQL**.

| Tab | What Flask does | Move to SQL? | Or grid-only? |
|---|---|---|---|
| Jan … Dec (12 tabs) | Pick that month’s this-year / last-year $; compute $ and % change; YTD Jan→that month by **summing month columns**; full-year from SP or sum of 12 | $ / % change and “YTD through this month” can live in SQL | **One grid**, filter/view by month — or keep 12 tabs as UI only on the same rows |

No second SP. This is already close to his model.

---

## Customer Activity

**SQL today:** `customer_activity` — one row per customer (salesman, last order date, PO, SO). **No math in Flask.**

| Tab | What Flask does | Move to SQL? | Or grid-only? |
|---|---|---|---|
| All | Sort by customer name | Optional | The SP table |
| One tab per salesman + Unassigned | Split the same rows | No | **Grid group-by Salesman** |

**One call already.** Just stop fanning tabs in Python.

---

## Customer’s Last Order

**SQL today:** `customer_last_orders` — lines for the latest logical orders (open + uninvoiced). ADDON POs already merged in SQL (`Order Rank`).

| What you see | What Flask does | Move to SQL? | Or grid-only? |
|---|---|---|---|
| Newest order | Pick rank 1 | Rank is already on the row | Default filter |
| Add previous order | Merge extra ranks; roll up lines by (item, price) | Rollup could be SQL | UI merge is OK if the SP already ranked |

This is a **picker**, not a group-by report. Keep a small UI. Do not rebuild order merge in Python if SQL already ranked the visits.

Line `Total` fallback today: if Total is blank, Flask does price × qty shipped. SQL should always send Total.

---

## Item Averages

**SQL today:** reuses Number 4 **By Item** SP (`item_customer_sales_rolling_12`) — item+customer rows with Total Qty.

| Tab | What Flask does | Move to SQL? | Or grid-only? |
|---|---|---|---|
| Item Averages | Sum Total Qty **per item**; Avg/Month = qty/12; Avg/Week = qty/52 | **Yes — one item-level SP** | Grid cannot invent per-item averages from customer-item rows without grouping+math |

**One-call shape:** a dedicated SP (or a flag on the By Item proc) that returns one row per item with 12-month qty, avg/month, avg/week. Stop pulling the huge Number 4 item cube just to divide by 12 and 52.

---

## Sales by State

**SQL today:** three SPs — summary, NYC, filtered detail. Flask only renames columns, formats dates/money, sorts summary by amount.

| Tab | What Flask does | Move to SQL? | Or grid-only? |
|---|---|---|---|
| Summary | Rename + sort | Sort can be SQL | Display |
| New York City | Rename | No | Display |
| Detail | Rename + date format | No | Display |

His app also fans three SPs and concatenates with `Source`. **Math is already in SQL.** Wrapping into one catalog key is a DBA convenience, not required for correctness.

---

## Extra calls that are not “tabs” but still slow us down

| Report | Why more than one POST | Fix |
|---|---|---|
| Invoiced + Commissions | Period rows + YTD window | SQL commissions result; one invoice window |
| Ordered | Month chunks for timeout | One window, bigger timeout, or SQL paging |
| Number 4 Both | Two rolling-12 SPs | Wrapper SP, or accept two calls like he does |
| Sales by State | Three SPs | Wrapper SP, or accept three calls like he does |
| Item Averages | Whole By Item cube | Small item-level SP |

Salesman scope for live Invoiced: live rows have `salesman` (HKaufman), not `SalesGroup`. His handoff already flags this. Mapping is an owner/SQL decision, not grid grouping.

---

## Can it work like his after that?

**Yes**, for the screens: one (or few) POST(s) → JSON table → AG Grid group-by → Excel of what you see.

**Not** until SQL owns:

1. Invoiced commission **dollars** and monthly/YTD (or we drop the cards)  
2. Ordered **Open $** and **Fulfillment %** (and stop month-chunking)  
3. Number 4 **YTD** totals  
4. Item Averages **per-item** rollup and /12 /52  

Everything else that is only a tab name (By Customer, Credits, per-salesman Activity) is a **filter or group-by**. His app already does that. We should stop cloning those into Python.

Do not deploy this over `reports.achimonline.com` until the owner signs off. This file does not change production.
