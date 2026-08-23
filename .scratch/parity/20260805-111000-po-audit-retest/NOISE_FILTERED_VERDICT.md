# Noise-filtered parity — .scratch\parity\20260805-111000-po-audit-retest
Today=2026-08-05

## Invoiced (YTD)
Sheets live-only: []
Sheets test-only: []
Audit - Reversals on /test: YES
Full Details: live=154395 test=154396 common=154395 live_only=0 test_only=1
  live_only dated today (2026-08-05) TZ noise: 0
  live_only other (real?): 0
  SO one-side blank (cosmetic): 18
Money diffs on common: {'cc': 1, 'freight': 1, 'total': 1}
  sample cc: [('IN00963267', '2026-07-10', 326.33, 71.33)]
  sample freight: [('IN00963267', '2026-07-10', 0.0, 255.0)]
  sample total: [('IN00828240', '2026-02-16', 15023.94, 16454.79)]

## Ordered (last_month)
Full Data: live=39625 test=40065 common=39362 live_only=263 test_only=703
  live_only on 2026-07-01 (TZ noise): 216
  test_only on 2026-07-31 (TZ noise): 128
  live_only fractional LineNum: 49
  test_only LineNum 0: 49
  remaining coverage after those cuts: live_only=-2 test_only=526
Qty LIVE(rel+ship)==TEST(rel): 39362/39362 (bad 0)
Status: noise(spelling/label)=5626 real=8
  top real status pairs: [(('InProcess', 'Open Order'), 8)]
By Order PO on 21214 shared SOs: match=21212 live_has_test_blank=0 test_has_live_blank=0 both_blank=2 both_filled_diff=0
  PO fill rate test (shared): 100.0% (was ~0% when stubbed)
