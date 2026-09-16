# Report tab handoff — SQL vs grid vs thin Python

For the owner, the DBA, and the next agent. **Production is Flask** (`main`). FastAPI is parked (`cursor/fastapi-rebuild-parked-0a24`); `app/assemble.py` there is a **stopgap**. Flask `v3/report_engine` is back on `main`; formulas below match that code (also history `063d9de` / leftover PR #35).

**Target:** one POST per user-facing report. SQL returns finished numbers. The web app filters, groups in Tabulator, exports, and emails. No invoice math in a god module.

Dummy shape: `rebuild-handoff/sample-invoiced-response.json`. Top level `data.raw` + `data.tabs.<tab>.rows`.

Customer Aging has no SQL path (BACKLOG). Not in this list.

---

## What can stay in the app (like his brother)

Presentation, not math:

- Date / customer / salesman filters on the request
- Hide rows the signed-in salesman is not allowed to see
- Grid group-by (By Customer, By Salesman, By Item, By Order)
- Show/hide columns, saved views
- Excel of the **visible** layout (plus companion files when a sheet is huge)
- Date formatting
- Subtotals of numbers SQL already returned

If a “tab” is only grouping the same rows, **do not rebuild it in SQL or Python**. The grid does it.

---

## What must move to SQL (or a honest thin assembler)

Anything that **creates new numbers**, **splits into different tables**, or **calls extra stored procs** just to feed a tab.

Locked commission rules:

- SP `Commission` / `commission_pct` is a **fraction**: `0.06` = 6%, `1` = 100%.
- Dollars use **that invoice’s rate**. An explicit `0` stays `0` (do not fall back).
- If the invoice has no rate, use `salesmen_master` `CommissionPercentage` (same fraction).
- On-screen percent uses salesman-table saved percent (Q3).

---

## Invoiced (and Shipped)

**SQL today:** `invoiced_report` — one row per invoice (amounts, charges, Total Invoice, salesman, commission **rate**).

**Flask extra pulls (gone, must not stay gone functionally):** if Commissions showed, Flask also pulled **Jan 1 → period end** so monthly/YTD cards had a full year.

| Tab | What Flask did | Move to SQL? | Or grid-only? |
|---|---|---|---|
| Full Details | Rename; net duplicate invoice rows | Netting in SQL | This **is** the SP table |
| Credits | Rows flagged credit | SQL can send `IsCredit` | Grid filter |
| Invoices | Non-credit | same flag | Grid filter |
| Audit - Reversals | Same invoice + and − totals | SQL flag `IsReversalPair` | Grid filter |
| Summary by Customer | GROUP BY customer + salesman | Optional | **Grid group-by** |
| Totals by Salesman | Sum; only if 2+ salesmen | Optional | **Grid group-by** |
| Commissions (admin) | Month buckets; **dollar math**; cards | **Yes** | Not a group-by |

**Commission math** (old Live/Flask):

Per salesman, per month, non-credit money + credit totals:

1. `total_invoices` = subtotal + tariff + freight + CC + misc  
2. `net` = `total_invoices` + `credits` − freight − CC  
   (`credits` = credit invoices’ Total Invoice, already negative)  
3. `commission` = `net` × rate (fraction)  
4. YTD = sum of those months through the selected month  

Shipped = Invoiced path without Commissions (no extra YTD pull).

**One-call shape:** SP returns invoice rows **plus** monthly commission rows, **or** invoice rows already include `CommissionDollars` and `NetCommissionBase`.

**FastAPI today:** `assemble._invoiced` fans rows; commissions tab only if those fields already exist. Cards/YTD extra pull is **not** ported.

---

## Ordered

**SQL today:** `ordered_report` — line rows.

**Flask extra:** month-chunked fetches so big YTD did not time out.

| Tab | What Flask did | Move to SQL? | Or grid-only? |
|---|---|---|---|
| Full Data | Map names. Drop “ERROR ITEM”. **Open $** = Ordered $ − Shipped $ − Cancelled $. **Fulfillment %** = (QtyOrdered − QtyCancelled) / QtyOrdered | Open $ and Fulfillment % in SQL. Drop ERROR ITEM in SQL | Line table |
| Summary | Renamed money headers | No extra math | Grid / layout |
| By Customer / Item / Order / Salesman | Sum; recompute Fulfillment % on totals | Optional | **Grid group-by** |

**One-call:** one date window (bigger timeout or SQL paging). Return `OpenAmount` and `FulfillmentPct` on every line.

**FastAPI today:** same rows copied into several tabs. No Open $ / Fulfillment %.

---

## Number 4

**SQL today:** two rolling-12 SPs (`customer_item_sales_rolling_12`, `item_customer_sales_rolling_12`).

**Flask extra:** “Both” = two POSTs. Then **YTD tabs** by dropping prior-year month columns and recounting Total Qty / Total $ / Avg Price. No YTD stored proc.

| Tab | What Flask did | Move to SQL? | Or grid-only? |
|---|---|---|---|
| By Customer 12 months | Fill missing totals | Fill-ins in SQL | Show SP table |
| By Customer YTD | Slice current-year months; recalc | **Yes** | Not group-by |
| By Item 12 months / YTD | Same | Same | Same |

**Minimum:** YTD totals on the existing rolling-12 rows.

**FastAPI today:** YTD tab is a copy of the rolling-12 rows (`assemble.number_4_tabs`).

---

## Salesman (monthly YoY)

**SQL today:** `monthly_salesman_yoy` — wide row, dollars already in SQL.

Flask picked month columns and computed $ / % change and YTD-through-month. Can live in SQL. UI may keep 12 tabs as filters on the same rows.

---

## Customer Activity

**SQL today:** `customer_activity`. **No math in Flask.**

All + per-salesman + Unassigned = **grid group-by Salesman**. FastAPI still fans tabs in `_customer_activity`.

---

## Customer’s Last Order

**SQL today:** `customer_last_orders`. Rank in SQL. ADDON POs merged.

Picker UI, not a group-by report. SQL should always send line `Total` (Flask fell back to price × qty).

---

## Item Averages

**SQL today:** reuses Number 4 By Item cube.

Flask summed Total Qty **per item**; Avg/Month = qty/12; Avg/Week = qty/52.

**Need:** one row per item with those averages. Stop pulling the huge cube just to divide.

**FastAPI today:** `_item_averages` dumps the cube as one tab.

---

## Sales by State

Three SPs — summary, NYC, detail. Math already in SQL. FastAPI still three calls (`reports._live_payload`). Wrapper SP is convenience, not required.

---

## Extra calls that are not “tabs” but still slow

| Report | Why more than one POST | Fix |
|---|---|---|
| Invoiced + Commissions | Period + YTD window | SQL commissions result |
| Ordered | Month chunks | One window |
| Number 4 Both | Two rolling-12 SPs | Wrapper, or accept two calls |
| Sales by State | Three SPs | Wrapper, or accept three |
| Item Averages | Whole By Item cube | Small item-level SP |

Salesman scope: live Invoiced has `salesman` (HKaufman), not `SalesGroup`. Owner/SQL decision (P4.I8). Testers = admin until then.

---

## Can it work like his after that?

**Yes** for screens: one (or few) POST(s) → JSON → Tabulator group-by → Excel of what you see (companions when huge).

**Not** until SQL (or a correct thin assembler) owns:

1. Invoiced commission **dollars** and monthly/YTD  
2. Ordered **Open $** and **Fulfillment %** (and stop month-chunking)  
3. Number 4 **YTD** totals  
4. Item Averages **per-item** /12 /52
