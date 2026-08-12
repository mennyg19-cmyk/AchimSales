# Post-fix parity (2026-08-04) — verdict

Folder: `.scratch/parity/20260804-193031-postfix/`

| Report | Hard diffs | Status |
|--------|------------|--------|
| customer_activity | 194 | **SIGNED OFF** — `/test` correct (2026-08-04) |
| invoiced | 872 | Open — see breakdown below |
| ordered | 161124 | Open — mostly known systematics; see breakdown |

## Customer Activity — LOCKED
`/test` is source of truth. After dropping same-SO+PO, blank-PO-on-test, and
today-dated last orders, only 3 SO/PO mismatches remained; owner accepted `/test`.
Do not chase further unless reopened. See DECISION-LOG.

## Invoiced (YTD) — breakdown
Hard 872 across sheets. Full Details is the ground truth:

| Bucket | Size | Notes |
|--------|------|-------|
| Live-only invoices (today TZ) | **260** | All `2026-08-04` — ignore (LIVE Eastern / TEST UTC) |
| Test-only invoices | 1 | Noise |
| Money diffs on shared invoices | **16** | See money detail |
| SO# one side blank | 45 | Cosmetic (`/test` fills) |
| Audit - Reversals sheet | missing on `/test` | SP already nets +/- pairs; live still has both legs. Logic exists; no pairs left to flag. |
| Commissions | SKIP | Layout not compared |

**Money (16 invoices):** mostly **tariff** where live=0 and `/test` has amount
(846, 8390, 6118, 832, …) — drives total/subtotal Summary gaps for those
customers. One **CC/freight swap**: acct `11077` invoice IN00963267
(live CC 326.33 / freight 0 → test CC 71.33 / freight 255). Credits: at least
one credit total mismatch (FCRD-004014 / 9022). High-volume DS count gaps
(7025, 7125, …) track the 260 today-missing invoices.

Summary by Customer **393/393** matched; diffs are rollups of the above.

## Ordered (last_month) — breakdown
Hard 161k is mostly **known column semantics**, not 161k unique order bugs.

| Bucket | Size | Notes |
|--------|------|-------|
| `LIVE QtyReleased+QtyShipped` = `TEST QtyReleased` | **39362/39362** common Full Data lines | Intentional. `/test` header renamed **QTY Shipping** (local). Not a math fail. |
| Status diffs | 5639 | **4629** = `Cancelled` vs `Canceled` (spelling). Rest: `Open`/`In Process` vs `Open Order` (~1010). |
| PO # blank on `/test` | ~21k By Order | Known SP stub — live has PO, test empty. |
| By Order coverage (TZ-ish) | live_only 175 (~174 on **2026-07-01**); test_only 151 (~103 on **2026-07-31**) | Month-edge TZ — ignore per prior rule. |
| Full Data coverage | live_only 264 (mostly 07-01); test_only **704** (spread across July) | Test-only extras need a closer look — not only TZ. |
| Summary remainder $ | ~7.6k | Column semantics differ (`QtyRemainder` vs `Qty left to ship` / dollars). |

## Next
Dig invoiced money (tariff + 11077 CC/freight) and ordered status labels +
test-only Full Data extras. CA closed.
