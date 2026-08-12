# Parity: invoiced

- Params: `{'period': 'ytd'}`
- Live file: `.scratch\parity\20260804-193031-postfix\invoiced__live.xlsx`
- Test file: `.scratch\parity\20260804-193031-postfix\invoiced__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **872**
- Missing sheets in /test: ['Audit - Reversals']
- Extra sheets in /test (ignored): (none)
- Per sheet: Summary by Customer=DIFF(66), Commissions=SKIP, Full Details=DIFF(338), Credits=DIFF(93), Invoices=DIFF(335), Audit - Reversals=MISSING_TEST(0), Totals by Salesman=DIFF(39)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260804-193031-postfix\invoiced__live.xlsx vs .scratch\parity\20260804-193031-postfix\invoiced__test.xlsx
Hard differences: 872
Result: DIFFERENCES FOUND
Missing sheets in /test: Audit - Reversals

## Sheet: Summary by Customer [DIFF]
  Row key: customer_account
  Rows live=393 test=393 matched=393
  Extra columns in /test (ignored): misc_charges, salesman_code
  Missing columns in /test: salesman_number
  Patterns:
    - Value diffs by column: total_invoices=23, subtotal_invoices=17, invoice_count=15, tariff_charges=8, cc_charges=1
  Value diffs (65):
    customer_account=11077 | cc_charges: live=326.3300 test=71.3300
    customer_account=11077 | freight_charges: live=0 test=255
    customer_account=11568 | subtotal_invoices: live=0 test=29
    customer_account=1412 | invoice_count: live=7623 test=7622
    customer_account=1412 | subtotal_invoices: live=57742.8700 test=57733.7100
    customer_account=1412 | total_invoices: live=57742.8700 test=57733.7100
    customer_account=1674 | invoice_count: live=22 test=21
    customer_account=1674 | subtotal_invoices: live=3717.1700 test=3759.1800
    customer_account=1674 | total_invoices: live=6407.9800 test=6449.9900
    customer_account=175 | subtotal_invoices: live=36202.2400 test=37633.0900
    customer_account=175 | total_invoices: live=38803.9600 test=40234.8100
    customer_account=48800 | invoice_count: live=828 test=826
    customer_account=48800 | subtotal_invoices: live=16461.3800 test=16435.8600
    customer_account=48800 | total_invoices: live=16461.3800 test=16435.8600
    customer_account=5233 | tariff_charges: live=0 test=238.9500
    customer_account=5233 | total_invoices: live=1869.9900 test=2108.9400
    customer_account=6054 | tariff_charges: live=2371.3400 test=3007.7300
    customer_account=6054 | total_invoices: live=22422.8400 test=23059.2300
    customer_account=6118 | tariff_charges: live=1464.8400 test=3157.7400
    customer_account=6118 | total_invoices: live=22516.4400 test=24209.3400
    customer_account=6262 | invoice_count: live=559 test=555
    customer_account=6262 | subtotal_invoices: live=56711.3000 test=56347.6200
    customer_account=6262 | total_invoices: live=65725.7500 test=65362.0700
    customer_account=6694 | tariff_charges: live=0 test=151.8900
    customer_account=6694 | total_invoices: live=1012.6000 test=1164.4900
    customer_account=7025 | invoice_count: live=31070 test=31009
    customer_account=7025 | subtotal_invoices: live=1050543.4100 test=1047357.7800
    customer_account=7025 | total_invoices: live=1050543.4100 test=1047357.7800
    customer_account=7125 | invoice_count: live=19672 test=19628
    customer_account=7125 | subtotal_invoices: live=517697.3500 test=516524.7800
    customer_account=7125 | total_invoices: live=517697.3500 test=516524.7800
    customer_account=8015 | invoice_count: live=4870 test=4862
    customer_account=8015 | subtotal_invoices: live=110099.6500 test=109852.7800
    customer_account=8015 | total_invoices: live=110099.6500 test=109852.7800
    customer_account=8264 | invoice_count: live=269 test=268
    customer_account=8264 | subtotal_invoices: live=4504.9000 test=4458.2600
    customer_account=8264 | total_invoices: live=4504.9000 test=4458.2600
    customer_account=832 | tariff_charges: live=923.0300 test=1174.2200
    customer_account=832 | total_invoices: live=8751.1400 test=9002.3300
    customer_account=8390 | tariff_charges: live=0 test=4314
    customer_account=8390 | total_invoices: live=35135.7600 test=39449.7600
    customer_account=846 | tariff_charges: live=0 test=394.4300
    customer_account=846 | total_invoices: live=7690.2400 test=8084.6700
    customer_account=9022 | invoice_count: live=12618 test=12605
    customer_account=9022 | subtotal_invoices: live=291013.3000 test=288703.0100
    customer_account=9022 | total_invoices: live=291013.3000 test=288703.0100
    customer_account=9091 | invoice_count: live=1001 test=999
    customer_account=9091 | subtotal_invoices: live=20156.2600 test=20101.6500
    customer_account=9091 | total_invoices: live=20156.2600 test=20101.6500
    customer_account=9177 | invoice_count: live=1009 test=1006
    ... +15 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Commissions [SKIP]
  Non-tabular sheet (no clear header row) — skipped for key-based compare.
  Rows live=91 test=55 matched=0

## Sheet: Full Details [DIFF]
  Row key: invoice_number
  Rows live=154144 test=153883 matched=153883
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 261 live row(s) missing on /test (0% of live rows).
    - Common denominator (missing on /test): 260/260 rows share date 2026-08-04.
    - Date breakdown (missing on /test): 2026-08-04=260
    - Value diffs by column: sales_order_number=45, total_invoice=14, tariff_charges=12, subtotal_invoices=3, cc_charges=1
    - Top dates (value-diff rows): 2026-07-30=5, 2026-01-26=3, 2026-05-18=3, 2026-07-28=3, 2026-03-02=2
    - All sales_order_number diffs: live is empty/zero, /test has a value.
    - All tariff_charges diffs: live is empty/zero, /test has a value.
  Missing in /test (261):
    invoice_number=FCRD-004048 (invoice_date=2026-08-04, customer_account=1674, customer_name=MAZER WHOLESALE INC)
    invoice_number=IN00983382 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983383 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983384 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983385 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983389 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983390 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983391 (invoice_date=2026-08-04, customer_account=9022, customer_name=JCPENNEY COMPANY INC (DS))
    invoice_number=IN00983392 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983393 (invoice_date=2026-08-04, customer_account=9022, customer_name=JCPENNEY COMPANY INC (DS))
    invoice_number=IN00983394 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983395 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983399 (invoice_date=2026-08-04, customer_account=9022, customer_name=JCPENNEY COMPANY INC (DS))
    invoice_number=IN00983400 (invoice_date=2026-08-04, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    invoice_number=IN00983401 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983402 (invoice_date=2026-08-04, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    invoice_number=IN00983403 (invoice_date=2026-08-04, customer_account=9188, customer_name=MASON COMPANIES, INC (DS))
    invoice_number=IN00983404 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983405 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983407 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983408 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983409 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983410 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983411 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983412 (invoice_date=2026-08-04, customer_account=9022, customer_name=JCPENNEY COMPANY INC (DS))
    invoice_number=IN00983413 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983414 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983415 (invoice_date=2026-08-04, customer_account=9022, customer_name=JCPENNEY COMPANY INC (DS))
    invoice_number=IN00983416 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983417 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983418 (invoice_date=2026-08-04, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    invoice_number=IN00983419 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983420 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983421 (invoice_date=2026-08-04, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    invoice_number=IN00983422 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983423 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983424 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983425 (invoice_date=2026-08-04, customer_account=8264, customer_name=KART IT  (DROP SHIP))
    invoice_number=IN00983426 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983427 (invoice_date=2026-08-04, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    invoice_number=IN00983428 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983429 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983430 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983431 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983432 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983433 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983434 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983435 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983436 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983437 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    ... +211 more
  Value diffs (76):
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
    invoice_number=FCRD-003959 | sales_order_number: live=None test=TR-000006931
    invoice_number=FCRD-003960 | sales_order_number: live=None test=TR-000006932
    invoice_number=FCRD-004014 | sales_order_number: live=None test=TR-000006928
    invoice_number=FCRD-004014 | subtotal_invoices: live=-961.3700 test=-2884.1100
    invoice_number=FCRD-004014 | total_invoice: live=-961.3700 test=-2884.1100
    invoice_number=FCRD-004022 | sales_order_number: live=None test=TR-000006929
    invoice_number=FCRD-004044 | sales_order_number: live=None test=TR-000006930
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
    invoice_number=IN00828240 | subtotal_invoices: live=12877.6600 test=14308.5100
    invoice_number=IN00828240 | total_invoice: live=15023.9400 test=16454.7900
    invoice_number=IN00887666 | tariff_charges: live=0 test=1107.2800
    ... +26 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Credits [DIFF]
  Row key: invoice_number
  Rows live=557 test=555 matched=555
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 2 live row(s) missing on /test (0% of live rows).
    - Date breakdown (missing on /test): 2026-08-04=1
    - Value diffs by column: sales_order_number=30, subtotal_invoices=30, total_invoice=30
    - Top dates (value-diff rows): 2026-01-26=9, 2026-03-13=6, 2026-06-04=6, 2026-06-29=6, 2026-07-08=6
    - All sales_order_number diffs: live is empty/zero, /test has a value.
  Missing in /test (2):
    invoice_number=FCRD-004048 (invoice_date=2026-08-04, customer_account=1674, customer_name=MAZER WHOLESALE INC)
    invoice_number=0 (invoice_date=-4600756201444442112.0000, customer_account=Total, customer_name=None)
  Value diffs (90):
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
    ... +40 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Invoices [DIFF]
  Row key: invoice_number
  Rows live=153588 test=153328 matched=153328
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 260 live row(s) missing on /test (0% of live rows).
    - Common denominator (missing on /test): 259/259 rows share date 2026-08-04.
    - Date breakdown (missing on /test): 2026-08-04=259
    - Value diffs by column: total_invoice=28, subtotal_invoices=17, sales_order_number=15, tariff_charges=12, cc_charges=1
    - Top dates (value-diff rows): 2026-07-30=4, 2026-01-06=3, 2026-02-12=3, 2026-02-25=3, 2026-03-12=3
    - All sales_order_number diffs: live is empty/zero, /test has a value.
  Missing in /test (260):
    invoice_number=IN00983383 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983382 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983384 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983385 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983389 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983390 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983391 (invoice_date=2026-08-04, customer_account=9022, customer_name=JCPENNEY COMPANY INC (DS))
    invoice_number=IN00983395 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983401 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983404 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983403 (invoice_date=2026-08-04, customer_account=9188, customer_name=MASON COMPANIES, INC (DS))
    invoice_number=IN00983405 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983409 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983412 (invoice_date=2026-08-04, customer_account=9022, customer_name=JCPENNEY COMPANY INC (DS))
    invoice_number=IN00983411 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983414 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983415 (invoice_date=2026-08-04, customer_account=9022, customer_name=JCPENNEY COMPANY INC (DS))
    invoice_number=IN00983420 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983422 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983421 (invoice_date=2026-08-04, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    invoice_number=IN00983425 (invoice_date=2026-08-04, customer_account=8264, customer_name=KART IT  (DROP SHIP))
    invoice_number=IN00983426 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983427 (invoice_date=2026-08-04, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    invoice_number=IN00983428 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983432 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983433 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983434 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983435 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983438 (invoice_date=2026-08-04, customer_account=8015, customer_name=WAYFAIR LLC (DS))
    invoice_number=IN00983442 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983443 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983444 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983445 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983447 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983450 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983451 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983458 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983459 (invoice_date=2026-08-04, customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    invoice_number=IN00983460 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983462 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983463 (invoice_date=2026-08-04, customer_account=8015, customer_name=WAYFAIR LLC (DS))
    invoice_number=IN00983466 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983467 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983471 (invoice_date=2026-08-04, customer_account=7025, customer_name=HOMEDEPOT.COM)
    invoice_number=IN00983472 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983475 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983476 (invoice_date=2026-08-04, customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
    invoice_number=IN00983477 (invoice_date=2026-08-04, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    invoice_number=IN00983478 (invoice_date=2026-08-04, customer_account=6262, customer_name=HD SUPPLY FACILITIES MAINTENANCE)
    invoice_number=IN00983479 (invoice_date=2026-08-04, customer_account=6262, customer_name=HD SUPPLY FACILITIES MAINTENANCE)
    ... +210 more
  Value diffs (74):
    invoice_number=FINV-000684 | sales_order_number: live=None test=TR-4453
    invoice_number=FINV-000684 | subtotal_invoices: live=29631.5700 test=0
    invoice_number=FINV-000684 | total_invoice: live=29631.5700 test=0
    invoice_number=IN00828240 | subtotal_invoices: live=12877.6600 test=14308.5100
    invoice_number=IN00828240 | total_invoice: live=15023.9400 test=16454.7900
    invoice_number=FINV-000719 | sales_order_number: live=None test=TR-4472
    invoice_number=FINV-000719 | subtotal_invoices: live=399.1200 test=0
    invoice_number=FINV-000719 | total_invoice: live=399.1200 test=0
    invoice_number=FINV-000720 | sales_order_number: live=None test=TR-4473
    invoice_number=FINV-000720 | subtotal_invoices: live=271.2000 test=0
    invoice_number=FINV-000720 | total_invoice: live=271.2000 test=0
    invoice_number=FINV-000741 | sales_order_number: live=None test=TR-4477
    invoice_number=FINV-000741 | subtotal_invoices: live=990.6400 test=0
    invoice_number=FINV-000741 | total_invoice: live=990.6400 test=0
    invoice_number=FINV-000742 | sales_order_number: live=None test=TR-4480
    invoice_number=FINV-000742 | subtotal_invoices: live=0.2000 test=0
    invoice_number=FINV-000742 | total_invoice: live=0.2000 test=0
    invoice_number=FINV-000744 | sales_order_number: live=None test=TR-4481
    invoice_number=FINV-000744 | subtotal_invoices: live=18025 test=0
    invoice_number=FINV-000744 | total_invoice: live=18025 test=0
    invoice_number=FINV-000749 | sales_order_number: live=None test=TR-4483
    invoice_number=FINV-000749 | subtotal_invoices: live=274.5000 test=0
    invoice_number=FINV-000749 | total_invoice: live=274.5000 test=0
    invoice_number=FINV-000754 | sales_order_number: live=None test=TR-4486
    invoice_number=FINV-000754 | subtotal_invoices: live=3604 test=0
    invoice_number=FINV-000754 | total_invoice: live=3604 test=0
    invoice_number=FINV-000759 | sales_order_number: live=None test=TR-4493
    invoice_number=FINV-000759 | subtotal_invoices: live=500 test=0
    invoice_number=FINV-000759 | total_invoice: live=500 test=0
    invoice_number=IN00887666 | tariff_charges: live=0 test=1107.2800
    invoice_number=IN00887666 | total_invoice: live=7381.8600 test=8489.1400
    invoice_number=IN00904557 | subtotal_invoices: live=0 test=29
    invoice_number=FINV-000764 | sales_order_number: live=None test=TR-4496
    invoice_number=FINV-000764 | subtotal_invoices: live=2255.1100 test=0
    invoice_number=FINV-000764 | total_invoice: live=2255.1100 test=0
    invoice_number=FINV-000768 | sales_order_number: live=None test=TR-4500
    invoice_number=FINV-000768 | subtotal_invoices: live=615.6000 test=0
    invoice_number=FINV-000768 | total_invoice: live=615.6000 test=0
    invoice_number=IN00909715 | tariff_charges: live=0 test=995.4800
    invoice_number=IN00909715 | total_invoice: live=6636.5600 test=7632.0400
    invoice_number=IN00921016 | tariff_charges: live=0 test=238.9500
    invoice_number=IN00921016 | total_invoice: live=1869.9900 test=2108.9400
    invoice_number=FINV-000778 | sales_order_number: live=None test=TR-4508
    invoice_number=FINV-000778 | subtotal_invoices: live=615.6000 test=0
    invoice_number=FINV-000778 | total_invoice: live=615.6000 test=0
    invoice_number=IN00930958 | tariff_charges: live=0 test=636.3900
    invoice_number=IN00930958 | total_invoice: live=4242.6000 test=4878.9900
    invoice_number=FINV-000782 | sales_order_number: live=None test=TR-4509
    invoice_number=FINV-000782 | subtotal_invoices: live=0.8000 test=0
    invoice_number=FINV-000782 | total_invoice: live=0.8000 test=0
    ... +24 more
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
    - Value diffs by column: invoice_count=11, subtotal_invoices=11, total_invoice=11, tariff_charges=2, cc_charges=1
  Missing in /test (1):
    salesman_code=0
  Value diffs (37):
    salesman_code=MKolko | invoice_count: live=638 test=681
    salesman_code=MKolko | subtotal_invoices: live=1168132.6100 test=1151838.0700
    salesman_code=MKolko | tariff_charges: live=89975.4700 test=92304.7600
    salesman_code=MKolko | total_invoice: live=1259440.4400 test=1245475.1900
    salesman_code=BLevin | invoice_count: live=854 test=889
    salesman_code=BLevin | subtotal_invoices: live=577198.7300 test=563360.9600
    salesman_code=BLevin | total_invoice: live=629637.7500 test=615799.9800
    salesman_code=HKaufman | cc_charges: live=481.2000 test=226.2000
    salesman_code=HKaufman | freight_charges: live=20981.3500 test=21236.3500
    salesman_code=HKaufman | invoice_count: live=6644 test=6732
    salesman_code=HKaufman | subtotal_invoices: live=2125415.9000 test=2001499.0100
    salesman_code=HKaufman | tariff_charges: live=94241.8700 test=99589.6500
    salesman_code=HKaufman | total_invoice: live=2241120.3200 test=2122551.2100
    salesman_code=AGrossman | invoice_count: live=37982 test=38069
    salesman_code=AGrossman | subtotal_invoices: live=2239740.3600 test=1929328.2100
    salesman_code=AGrossman | total_invoice: live=2250284.1500 test=1939872
    salesman_code=JWeigand | invoice_count: live=10241 test=10273
    salesman_code=JWeigand | subtotal_invoices: live=255898.6600 test=196362.5400
    salesman_code=JWeigand | total_invoice: live=264980.6900 test=205444.5700
    salesman_code=LCWalker | invoice_count: live=12 test=13
    salesman_code=LCWalker | subtotal_invoices: live=92020.5200 test=92020.3200
    salesman_code=LCWalker | total_invoice: live=107476.4800 test=107476.2800
    salesman_code=REdwards | invoice_count: live=48650 test=48564
    salesman_code=REdwards | subtotal_invoices: live=6290922.3200 test=6289001.7700
    salesman_code=REdwards | total_invoice: live=6290922.3200 test=6289001.7700
    salesman_code=Integrated | invoice_count: live=48379 test=48449
    salesman_code=Integrated | subtotal_invoices: live=2707209.6300 test=1926192.6400
    salesman_code=Integrated | total_invoice: live=2707209.6300 test=1926192.6400
    salesman_code=House | invoice_count: live=46 test=52
    salesman_code=House | subtotal_invoices: live=23119.6100 test=21985.8300
    salesman_code=House | total_invoice: live=24055.6600 test=22892.8800
    salesman_code=MGrego | invoice_count: live=100 test=118
    salesman_code=MGrego | subtotal_invoices: live=171203.8900 test=167956.7600
    salesman_code=MGrego | total_invoice: live=171348.6700 test=168101.5400
    salesman_code=Unassigned | invoice_count: live=30 test=32
    salesman_code=Unassigned | subtotal_invoices: live=2294823.7100 test=2294809.5100
    salesman_code=Unassigned | total_invoice: live=2294823.7100 test=2294809.5100
  Soft/cosmetic text diffs (not failing): 2
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
