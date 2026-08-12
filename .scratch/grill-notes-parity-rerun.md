# Fix notes from Menny (2026-08-04) — claimed DBA / report fixes before re-parity

## Customer Activity
- Cause: SP left out cancelled + open; only invoiced → earlier last-order dates on /test
- Claim: should match live side-by-side now

## Invoiced
- Charges / rounding / CC miscalc — claimed fixed
- Timezone: LIVE Eastern, TEST UTC — **ignore** first/last few hours of month edge diffs

## Ordered
- Same timezone rule (ignore edges)
- Order status mismatches — claimed fixed

## Parity plan
Re-run: customer_activity, invoiced (ytd), ordered (last_month)
Treat period-boundary hour skew as acceptable noise, not a fail.
