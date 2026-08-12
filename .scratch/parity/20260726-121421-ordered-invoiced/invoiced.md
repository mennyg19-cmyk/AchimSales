# Parity: invoiced

- Params: `{'period': 'ytd'}`
- Live file: `.scratch\parity\20260726-121421-ordered-invoiced\invoiced__live.xlsx`
- Test file: `.scratch\parity\20260726-121421-ordered-invoiced\invoiced__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **1179**
- Missing sheets in /test: ['Audit - Reversals']
- Extra sheets in /test (ignored): (none)
- Per sheet: Summary by Customer=DIFF(187), Commissions=SKIP, Full Details=DIFF(436), Credits=DIFF(77), Invoices=DIFF(441), Audit - Reversals=MISSING_TEST(0), Totals by Salesman=DIFF(37)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260726-121421-ordered-invoiced\invoiced__live.xlsx vs .scratch\parity\20260726-121421-ordered-invoiced\invoiced__test.xlsx
Hard differences: 1179
Result: DIFFERENCES FOUND
Missing sheets in /test: Audit - Reversals

## Sheet: Summary by Customer [DIFF]
  Row key: customer_account
  Rows live=388 test=388 matched=388
  Extra columns in /test (ignored): misc_charges, salesman_code
  Missing columns in /test: salesman_number
  Patterns:
    - Value diffs by column: tariff_charges=92, total_invoices=91, subtotal_invoices=2, cc_charges=1
  Value diffs (186):
    customer_account=11077 | cc_charges: live=326.3300 test=71.3300
    customer_account=11077 | total_invoices: live=2448.8700 test=2193.8600
    customer_account=11190 | tariff_charges: live=320.0200 test=319.9500
    customer_account=11190 | total_invoices: live=6940.5000 test=6940.4300
    customer_account=11568 | subtotal_invoices: live=0 test=29
    customer_account=11594 | tariff_charges: live=154.3600 test=154.3500
    customer_account=1049 | tariff_charges: live=4587.5800 test=4587.1700
    customer_account=1063 | total_invoices: live=19066.1100 test=19066.1000
    customer_account=1493 | tariff_charges: live=552.9500 test=552.9000
    customer_account=1493 | total_invoices: live=10138.9000 test=10138.8500
    customer_account=1674 | tariff_charges: live=566.8900 test=566.8400
    customer_account=1674 | total_invoices: live=6449.9900 test=6449.9500
    customer_account=175 | subtotal_invoices: live=34357.7800 test=35788.6300
    customer_account=175 | total_invoices: live=36959.5000 test=38390.3400
    customer_account=1903 | tariff_charges: live=1100.2800 test=1100.2200
    customer_account=1903 | total_invoices: live=8435.1000 test=8435.0500
    customer_account=1963 | tariff_charges: live=10116.6600 test=10116.6100
    customer_account=1963 | total_invoices: live=81628.4500 test=81628.4000
    customer_account=1977 | tariff_charges: live=5042.4900 test=5042.2800
    customer_account=1978 | tariff_charges: live=1590.1500 test=1590.1200
    customer_account=1978 | total_invoices: live=12191.0500 test=12191.0200
    customer_account=2587633 | total_invoices: live=4643.4400 test=4643.4300
    customer_account=2655645 | total_invoices: live=2382.1700 test=2382.1600
    customer_account=2704039 | tariff_charges: live=353.0600 test=353.0200
    customer_account=2704039 | total_invoices: live=2706.5600 test=2706.5300
    customer_account=2730 | tariff_charges: live=759.9300 test=759.8400
    customer_account=2730 | total_invoices: live=13389.5300 test=13389.4400
    customer_account=2763990 | tariff_charges: live=608.0800 test=608.0600
    customer_account=2763990 | total_invoices: live=4661.8400 test=4661.8200
    customer_account=2792027 | tariff_charges: live=361.0700 test=360.9800
    customer_account=2792027 | total_invoices: live=2692.6700 test=2692.5800
    customer_account=2806734 | tariff_charges: live=228.6200 test=228.6000
    customer_account=2806734 | total_invoices: live=1752.1700 test=1752.1500
    customer_account=2807 | tariff_charges: live=2639.1500 test=2638.9000
    customer_account=2854 | tariff_charges: live=960.8800 test=960.8300
    customer_account=2854 | total_invoices: live=7366.4400 test=7366.3900
    customer_account=302 | total_invoices: live=8750.2700 test=8750.2600
    customer_account=3043 | total_invoices: live=13112.8200 test=13112.8100
    customer_account=3052 | total_invoices: live=19238.3600 test=19238.3500
    customer_account=308 | tariff_charges: live=1522.4800 test=1522.4600
    customer_account=308 | total_invoices: live=13146.1700 test=13146.1400
    customer_account=3107161 | tariff_charges: live=235.7100 test=235.6500
    customer_account=3107161 | total_invoices: live=1806.7100 test=1806.6500
    customer_account=3209547 | tariff_charges: live=1119.1200 test=1119.0700
    customer_account=3209547 | total_invoices: live=8579.6600 test=8579.6200
    customer_account=3281501 | tariff_charges: live=598.0600 test=598.0500
    customer_account=3289347 | tariff_charges: live=223.2900 test=223.2600
    customer_account=3289347 | total_invoices: live=3085.7900 test=3085.7600
    customer_account=3320740 | tariff_charges: live=600.5000 test=600.4800
    customer_account=3320740 | total_invoices: live=4603.7000 test=4603.6700
    ... +136 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Commissions [SKIP]
  Non-tabular sheet (no clear header row) — skipped for key-based compare.
  Rows live=91 test=55 matched=0

## Sheet: Full Details [DIFF]
  Row key: invoice_number
  Rows live=147346 test=147345 matched=147345
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 1 live row(s) missing on /test (0% of live rows).
    - Value diffs by column: tariff_charges=198, total_invoice=193, sales_order_number=40, subtotal_invoices=2, cc_charges=1
    - Top dates (value-diff rows): 2026-01-22=16, 2026-04-10=13, 2026-04-30=11, 2026-06-09=10, 2026-06-04=9
    - All sales_order_number diffs: live is empty/zero, /test has a value.
  Missing in /test (1):
    invoice_number=0 (invoice_date=-5092921064827879424.0000, customer_account=None, customer_name=None)
  Value diffs (434):
    invoice_number=FCRD-003244 | sales_order_number: live=None test=TR-4450
    invoice_number=FCRD-003245 | sales_order_number: live=None test=TR-4454
    invoice_number=FCRD-003273 | sales_order_number: live=None test=TR-4455
    invoice_number=FCRD-003274 | sales_order_number: live=None test=TR-4456
    invoice_number=FCRD-003306 | sales_order_number: live=None test=TR-4458
    invoice_number=FCRD-003307 | sales_order_number: live=None test=TR-4457
    invoice_number=FCRD-003326 | sales_order_number: live=None test=TR-4463
    invoice_number=FCRD-003344 | sales_order_number: live=None test=TR-4464
    invoice_number=FCRD-003355 | sales_order_number: live=None test=TR-4466
    invoice_number=FCRD-003417 | sales_order_number: live=None test=TR-4474
    invoice_number=FCRD-003451 | sales_order_number: live=None test=TR-4476
    invoice_number=FCRD-003492 | sales_order_number: live=None test=TR-4478
    invoice_number=FCRD-003495 | sales_order_number: live=None test=TR-4479
    invoice_number=FCRD-003529 | sales_order_number: live=None test=TR-4487
    invoice_number=FCRD-003572 | sales_order_number: live=None test=TR-4488
    invoice_number=FCRD-003584 | sales_order_number: live=None test=TR-4489
    invoice_number=FCRD-003663 | sales_order_number: live=None test=TR-4497
    invoice_number=FCRD-003759 | sales_order_number: live=None test=TR-4502
    invoice_number=FCRD-003772 | sales_order_number: live=None test=TR-4507
    invoice_number=FCRD-003825 | sales_order_number: live=None test=TR-4510
    invoice_number=FCRD-003827 | sales_order_number: live=None test=TR-000006916
    invoice_number=FCRD-003884 | sales_order_number: live=None test=TR-000006912
    invoice_number=FCRD-003903 | sales_order_number: live=None test=TR-000006914
    invoice_number=FCRD-003921 | sales_order_number: live=None test=TR-000006918
    invoice_number=FCRD-003922 | sales_order_number: live=None test=TR-000006917
    invoice_number=FINV-000684 | sales_order_number: live=None test=TR-4453
    invoice_number=FINV-000719 | sales_order_number: live=None test=TR-4472
    invoice_number=FINV-000720 | sales_order_number: live=None test=TR-4473
    invoice_number=FINV-000741 | sales_order_number: live=None test=TR-4477
    invoice_number=FINV-000742 | sales_order_number: live=None test=TR-4480
    invoice_number=FINV-000744 | sales_order_number: live=None test=TR-4481
    invoice_number=FINV-000749 | sales_order_number: live=None test=TR-4483
    invoice_number=FINV-000754 | sales_order_number: live=None test=TR-4486
    invoice_number=FINV-000759 | sales_order_number: live=None test=TR-4493
    invoice_number=FINV-000764 | sales_order_number: live=None test=TR-4496
    invoice_number=FINV-000768 | sales_order_number: live=None test=TR-4500
    invoice_number=FINV-000778 | sales_order_number: live=None test=TR-4508
    invoice_number=FINV-000782 | sales_order_number: live=None test=TR-4509
    invoice_number=FINV-000788 | sales_order_number: live=None test=TR-000006913
    invoice_number=FINV-000796 | sales_order_number: live=None test=TR-000006925
    invoice_number=IN00793553 | tariff_charges: live=893.3700 test=893.3000
    invoice_number=IN00793553 | total_invoice: live=12803.9900 test=12803.9200
    invoice_number=IN00793560 | tariff_charges: live=84.9000 test=84.8900
    invoice_number=IN00796474 | tariff_charges: live=2119.1500 test=2119.1300
    invoice_number=IN00796474 | total_invoice: live=16246.6700 test=16246.6500
    invoice_number=IN00796768 | tariff_charges: live=276.3800 test=276.3600
    invoice_number=IN00796768 | total_invoice: live=2118.7700 test=2118.7500
    invoice_number=IN00797472 | total_invoice: live=3507.5400 test=3507.5500
    invoice_number=IN00797473 | tariff_charges: live=448.5100 test=448.4900
    invoice_number=IN00797473 | total_invoice: live=3438.4500 test=3438.4300
    ... +384 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Credits [DIFF]
  Row key: invoice_number
  Rows live=516 test=515 matched=515
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 1 live row(s) missing on /test (0% of live rows).
    - Value diffs by column: sales_order_number=25, subtotal_invoices=25, total_invoice=25
    - Top dates (value-diff rows): 2026-01-26=9, 2026-03-13=6, 2026-06-04=6, 2026-06-29=6, 2026-01-01=3
    - All sales_order_number diffs: live is empty/zero, /test has a value.
    - All subtotal_invoices diffs: /test is empty/zero, live has a value.
    - All total_invoice diffs: /test is empty/zero, live has a value.
  Missing in /test (1):
    invoice_number=0 (invoice_date=3724869767103315968.0000, customer_account=Total, customer_name=None)
  Value diffs (75):
    invoice_number=FCRD-003244 | sales_order_number: live=None test=TR-4450
    invoice_number=FCRD-003244 | subtotal_invoices: live=-2986.8400 test=0
    invoice_number=FCRD-003244 | total_invoice: live=-2986.8400 test=0
    invoice_number=FCRD-003245 | sales_order_number: live=None test=TR-4454
    invoice_number=FCRD-003245 | subtotal_invoices: live=-3053.9200 test=0
    invoice_number=FCRD-003245 | total_invoice: live=-3053.9200 test=0
    invoice_number=FCRD-003273 | sales_order_number: live=None test=TR-4455
    invoice_number=FCRD-003273 | subtotal_invoices: live=-6411.5100 test=0
    invoice_number=FCRD-003273 | total_invoice: live=-6411.5100 test=0
    invoice_number=FCRD-003274 | sales_order_number: live=None test=TR-4456
    invoice_number=FCRD-003274 | subtotal_invoices: live=-10431.4900 test=0
    invoice_number=FCRD-003274 | total_invoice: live=-10431.4900 test=0
    invoice_number=FCRD-003306 | sales_order_number: live=None test=TR-4458
    invoice_number=FCRD-003306 | subtotal_invoices: live=-1862.9700 test=0
    invoice_number=FCRD-003306 | total_invoice: live=-1862.9700 test=0
    invoice_number=FCRD-003307 | sales_order_number: live=None test=TR-4457
    invoice_number=FCRD-003307 | subtotal_invoices: live=-2279.3800 test=0
    invoice_number=FCRD-003307 | total_invoice: live=-2279.3800 test=0
    invoice_number=FCRD-003326 | sales_order_number: live=None test=TR-4463
    invoice_number=FCRD-003326 | subtotal_invoices: live=-156.1200 test=0
    invoice_number=FCRD-003326 | total_invoice: live=-156.1200 test=0
    invoice_number=FCRD-003355 | sales_order_number: live=None test=TR-4466
    invoice_number=FCRD-003355 | subtotal_invoices: live=-56.2800 test=0
    invoice_number=FCRD-003355 | total_invoice: live=-56.2800 test=0
    invoice_number=FCRD-003344 | sales_order_number: live=None test=TR-4464
    invoice_number=FCRD-003344 | subtotal_invoices: live=-1696.1200 test=0
    invoice_number=FCRD-003344 | total_invoice: live=-1696.1200 test=0
    invoice_number=FCRD-003417 | sales_order_number: live=None test=TR-4474
    invoice_number=FCRD-003417 | subtotal_invoices: live=-622.2700 test=0
    invoice_number=FCRD-003417 | total_invoice: live=-622.2700 test=0
    invoice_number=FCRD-003451 | sales_order_number: live=None test=TR-4476
    invoice_number=FCRD-003451 | subtotal_invoices: live=-373.2000 test=0
    invoice_number=FCRD-003451 | total_invoice: live=-373.2000 test=0
    invoice_number=FCRD-003492 | sales_order_number: live=None test=TR-4478
    invoice_number=FCRD-003492 | subtotal_invoices: live=-84 test=0
    invoice_number=FCRD-003492 | total_invoice: live=-84 test=0
    invoice_number=FCRD-003495 | sales_order_number: live=None test=TR-4479
    invoice_number=FCRD-003495 | subtotal_invoices: live=-0.8400 test=0
    invoice_number=FCRD-003495 | total_invoice: live=-0.8400 test=0
    invoice_number=FCRD-003529 | sales_order_number: live=None test=TR-4487
    invoice_number=FCRD-003529 | subtotal_invoices: live=-2696.0400 test=0
    invoice_number=FCRD-003529 | total_invoice: live=-2696.0400 test=0
    invoice_number=FCRD-003572 | sales_order_number: live=None test=TR-4488
    invoice_number=FCRD-003572 | subtotal_invoices: live=-796.1300 test=0
    invoice_number=FCRD-003572 | total_invoice: live=-796.1300 test=0
    invoice_number=FCRD-003584 | sales_order_number: live=None test=TR-4489
    invoice_number=FCRD-003584 | subtotal_invoices: live=-35.7700 test=0
    invoice_number=FCRD-003584 | total_invoice: live=-35.7700 test=0
    invoice_number=FCRD-003663 | sales_order_number: live=None test=TR-4497
    invoice_number=FCRD-003663 | subtotal_invoices: live=-178.1600 test=0
    ... +25 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Invoices [DIFF]
  Row key: invoice_number
  Rows live=146831 test=146830 matched=146830
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 1 live row(s) missing on /test (0% of live rows).
    - Value diffs by column: total_invoice=208, tariff_charges=198, subtotal_invoices=17, sales_order_number=15, cc_charges=1
    - Top dates (value-diff rows): 2026-01-22=16, 2026-04-10=12, 2026-04-30=10, 2026-06-09=10, 2026-06-16=10
  Missing in /test (1):
    invoice_number=0 (invoice_date=-8064290326769401856.0000, customer_account=Total, customer_name=None)
  Value diffs (439):
    invoice_number=IN00793553 | tariff_charges: live=893.3700 test=893.3000
    invoice_number=IN00793553 | total_invoice: live=12803.9900 test=12803.9200
    invoice_number=IN00793560 | tariff_charges: live=84.9000 test=84.8900
    invoice_number=IN00796768 | tariff_charges: live=276.3800 test=276.3600
    invoice_number=IN00796768 | total_invoice: live=2118.7700 test=2118.7500
    invoice_number=IN00796474 | tariff_charges: live=2119.1500 test=2119.1300
    invoice_number=IN00796474 | total_invoice: live=16246.6700 test=16246.6500
    invoice_number=IN00797472 | total_invoice: live=3507.5400 test=3507.5500
    invoice_number=IN00797473 | tariff_charges: live=448.5100 test=448.4900
    invoice_number=IN00797473 | total_invoice: live=3438.4500 test=3438.4300
    invoice_number=IN00798268 | tariff_charges: live=236.4800 test=236.4400
    invoice_number=IN00798268 | total_invoice: live=1812.7600 test=1812.7200
    invoice_number=IN00803390 | tariff_charges: live=98.8700 test=98.8600
    invoice_number=IN00800098 | total_invoice: live=2331.1300 test=2331.1200
    invoice_number=IN00800099 | tariff_charges: live=611.8600 test=611.8200
    invoice_number=IN00800099 | total_invoice: live=8769.5200 test=8769.4800
    invoice_number=IN00800100 | total_invoice: live=29.0300 test=29.0200
    invoice_number=IN00800103 | tariff_charges: live=609.6000 test=609.5200
    invoice_number=IN00800103 | total_invoice: live=8736.6000 test=8736.5200
    invoice_number=IN00801494 | tariff_charges: live=54 test=138.9300
    invoice_number=IN00801494 | total_invoice: live=980.2200 test=1065.1500
    invoice_number=IN00802346 | tariff_charges: live=256.5500 test=256.5000
    invoice_number=IN00802346 | total_invoice: live=1966.5500 test=1966.5000
    invoice_number=IN00803486 | tariff_charges: live=3658.3900 test=3658.3700
    invoice_number=IN00803837 | tariff_charges: live=1.8200 test=1.8100
    invoice_number=FINV-000684 | sales_order_number: live=None test=TR-4453
    invoice_number=FINV-000684 | subtotal_invoices: live=29631.5700 test=0
    invoice_number=FINV-000684 | total_invoice: live=29631.5700 test=0
    invoice_number=IN00809674 | tariff_charges: live=326.7100 test=326.6900
    invoice_number=IN00809674 | total_invoice: live=2504.6500 test=2504.6300
    invoice_number=IN00805929 | tariff_charges: live=230.0200 test=230.0100
    invoice_number=IN00806598 | tariff_charges: live=1016.0300 test=1015.9100
    invoice_number=IN00806598 | total_invoice: live=14561.4700 test=14561.3500
    invoice_number=IN00806624 | tariff_charges: live=258 test=257.9600
    invoice_number=IN00806624 | total_invoice: live=1977.7600 test=1977.7200
    invoice_number=IN00808272 | tariff_charges: live=22.1900 test=22.1800
    invoice_number=IN00808949 | tariff_charges: live=283.0900 test=283.0700
    invoice_number=IN00808949 | total_invoice: live=2170.2100 test=2170.1900
    invoice_number=IN00808998 | tariff_charges: live=367.3400 test=367.3200
    invoice_number=IN00808998 | total_invoice: live=2816.1200 test=2816.1000
    invoice_number=IN00808999 | tariff_charges: live=229.6000 test=229.5600
    invoice_number=IN00808999 | total_invoice: live=1760.0300 test=1759.9900
    invoice_number=IN00808435 | tariff_charges: live=290.6500 test=290.6200
    invoice_number=IN00808435 | total_invoice: live=2228.1500 test=2228.1200
    invoice_number=IN00808439 | tariff_charges: live=310.9900 test=310.8700
    invoice_number=IN00808439 | total_invoice: live=2454.9600 test=2454.8400
    invoice_number=IN00808440 | tariff_charges: live=248.0600 test=248.0100
    invoice_number=IN00808440 | total_invoice: live=1901.4600 test=1901.4100
    invoice_number=IN00808441 | tariff_charges: live=151.9100 test=151.8800
    invoice_number=IN00808441 | total_invoice: live=1164.4100 test=1164.3800
    ... +389 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Audit - Reversals [MISSING_TEST]
  Sheet present on live, missing on /test.
  Rows live=0 test=0 matched=0

## Sheet: Totals by Salesman [DIFF]
  Row key: salesman_code
  Rows live=13 test=12 matched=12
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 1 live row(s) missing on /test (8% of live rows).
    - Value diffs by column: invoice_count=10, total_invoice=9, subtotal_invoices=8, tariff_charges=7, cc_charges=1
  Missing in /test (1):
    salesman_code=0
  Value diffs (35):
    salesman_code=MKolko | invoice_count: live=616 test=658
    salesman_code=MKolko | subtotal_invoices: live=1140490.0500 test=1124217.3300
    salesman_code=MKolko | tariff_charges: live=88968.9200 test=91388.4600
    salesman_code=MKolko | total_invoice: live=1230791.3300 test=1216938.1600
    salesman_code=BLevin | invoice_count: live=812 test=848
    salesman_code=BLevin | subtotal_invoices: live=566378.7100 test=553782.6900
    salesman_code=BLevin | tariff_charges: live=43225.7300 test=43223.9500
    salesman_code=BLevin | total_invoice: live=617615.7400 test=605017.9000
    salesman_code=HKaufman | cc_charges: live=481.2000 test=226.2000
    salesman_code=HKaufman | invoice_count: live=6392 test=6485
    salesman_code=HKaufman | subtotal_invoices: live=2064895.6500 test=1942002.9000
    salesman_code=HKaufman | tariff_charges: live=90562.9400 test=95068.9300
    salesman_code=HKaufman | total_invoice: live=2176530.7600 test=2057889.0200
    salesman_code=AGrossman | invoice_count: live=36064 test=36203
    salesman_code=AGrossman | subtotal_invoices: live=2175347.0500 test=1880285.7200
    salesman_code=AGrossman | tariff_charges: live=9390.9900 test=9390.5900
    salesman_code=AGrossman | total_invoice: live=2185890.8400 test=1890828.9800
    salesman_code=PMazer | tariff_charges: live=3371.1200 test=3371.0300
    salesman_code=JWeigand | invoice_count: live=9883 test=9919
    salesman_code=JWeigand | subtotal_invoices: live=248831.3800 test=192224.7700
    salesman_code=JWeigand | tariff_charges: live=9082.0300 test=9082.0100
    salesman_code=JWeigand | total_invoice: live=257913.4100 test=201306.7800
    salesman_code=LCWalker | invoice_count: live=11 test=12
    salesman_code=LCWalker | tariff_charges: live=10957.9100 test=10957.8900
    salesman_code=LCWalker | total_invoice: live=86177.2200 test=86177
    salesman_code=Integrated | invoice_count: live=46156 test=46299
    salesman_code=Integrated | subtotal_invoices: live=2584419.2900 test=1869240.0500
    salesman_code=Integrated | total_invoice: live=2584419.2900 test=1869240.0500
    salesman_code=House | invoice_count: live=43 test=49
    salesman_code=House | subtotal_invoices: live=23032.6100 test=21898.8300
    salesman_code=House | total_invoice: live=23950.8000 test=22788.0200
    salesman_code=MGrego | invoice_count: live=96 test=114
    salesman_code=MGrego | subtotal_invoices: live=164086.1100 test=160838.9800
    salesman_code=MGrego | total_invoice: live=164230.8900 test=160983.7600
    salesman_code=Unassigned | invoice_count: live=28 test=29
  Soft/cosmetic text diffs (not failing): 2
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
