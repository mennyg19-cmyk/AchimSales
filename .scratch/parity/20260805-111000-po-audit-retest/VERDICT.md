# Parity retest — 2026-08-05 (PO + invoiced SP fixes)

Folder: `.scratch/parity/20260805-111000-po-audit-retest/`  
Deploy: `8fb3bcf` on `/test`. Noise rules applied as locked previously.

| Report | Raw hard diffs | After noise |
|--------|---------------:|-------------|
| ordered last_month | 138941 | See below — PO fixed; qty perfect |
| invoiced YTD | 176 | **Very thin leftovers** |

---

## Ordered — after noise

| Check | Result |
|-------|--------|
| **PO #** (By Order, 21214 shared SOs) | **match 21212 / blank-both 2 / live-has-test-blank 0** — **100% fill** (was ~0% stubbed) |
| Qty: LIVE rel+ship == TEST rel | **39362 / 39362** |
| Status spelling / Open↔Open Order / InProcess↔Open Order | noise (thousands) |
| live_only after TZ (7/1) + fractional LineNum | **0** |
| test_only after TZ (7/31) + LineNum 0 | **531 lines / 21 SOs** — same LIVE HeadersV3 blind spot as before (not late-line gate) |

**PO sign-off:** CustomerRequisition mapping works end-to-end on `/test`.

**Still open on ordered:** accept TEST-only 21 SOs (HeadersV3 gap) + status label vocabulary as intentional, or chase separately.

---

## Invoiced — after noise

| Check | Result |
|-------|--------|
| **Audit - Reversals** | **YES on /test** — **94 / 94** rows both sides |
| Sheet set | same (no missing sheets) |
| Full Details coverage | live_only **0**, test_only **1** |
| Today TZ live_only | **0** |
| SO one-side blank | 18 (cosmetic) |
| Tariff live=0 / test amount pile | **gone** (was 16 invoices last run) |
| Money left | **2 invoices** |

### Money leftovers (2)

1. **IN00963267** (acct 11077) — **total matches** ($2448.87). CC/freight **swap only**: live CC 326.33 / freight 0 → test CC 71.33 / freight 255 (diff = 255).
2. **IN00828240** (acct 175) — real subtotal/total gap: live total 15023.94 vs test 16454.79 (Δ +1430.85). Tariff same (2146.28).

---

## Verdict

- **Ordered PO:** fixed / ready to treat as done.
- **Invoiced audits/reversals + tariff pile:** fixed.
- **Left to decide:** 21 TEST-only ordered SOs (OData HeadersV3), status wording, invoiced CC/freight split on one invoice, one subtotal mismatch on IN00828240.
