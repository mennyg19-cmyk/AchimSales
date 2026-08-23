# Parity: invoiced

- Params: `{'period': 'ytd'}`
- Live file: `.scratch\parity\20260805-111000-po-audit-retest\invoiced__live.xlsx`
- Test file: `.scratch\parity\20260805-111000-po-audit-retest\invoiced__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **176**
- Missing sheets in /test: (none)
- Extra sheets in /test (ignored): (none)
- Per sheet: Summary by Customer=DIFF(6), Commissions=SKIP, Full Details=DIFF(25), Credits=DIFF(31), Invoices=DIFF(28), Audit - Reversals=DIFF(52), Totals by Salesman=DIFF(34)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260805-111000-po-audit-retest\invoiced__live.xlsx vs .scratch\parity\20260805-111000-po-audit-retest\invoiced__test.xlsx
Hard differences: 176
Result: DIFFERENCES FOUND

## Sheet: Summary by Customer [DIFF]
  Row key: customer_account
  Rows live=393 test=393 matched=393
  Extra columns in /test (ignored): misc_charges, salesman_code
  Missing columns in /test: salesman_number
  Patterns:
    - Value diffs by column: subtotal_invoices=2, cc_charges=1, freight_charges=1, total_invoices=1
  Value diffs (5):
    customer_account=11077 | cc_charges: live=326.3300 test=71.3300
    customer_account=11077 | freight_charges: live=0 test=255
    customer_account=11568 | subtotal_invoices: live=0 test=29
    customer_account=175 | subtotal_invoices: live=36202.2400 test=37633.0900
    customer_account=175 | total_invoices: live=38803.9600 test=40234.8100
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Commissions [SKIP]
  Non-tabular sheet (no clear header row) — skipped for key-based compare.
  Rows live=91 test=55 matched=0

## Sheet: Full Details [DIFF]
  Row key: invoice_number
  Rows live=154396 test=154395 matched=154395
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 1 live row(s) missing on /test (0% of live rows).
    - Value diffs by column: sales_order_number=18, subtotal_invoices=2, total_invoice=1, cc_charges=1, freight_charges=1
    - Top dates (value-diff rows): 2026-02-16=2, 2026-07-10=2, 2026-01-01=1, 2026-01-05=1, 2026-01-26=1
    - All sales_order_number diffs: live is empty/zero, /test has a value.
  Missing in /test (1):
    invoice_number=0 (invoice_date=1779943865257917952.0000, customer_account=None, customer_name=None)
  Value diffs (23):
    invoice_number=FCRD-003244 | sales_order_number: live=None test=TR-4450
    invoice_number=FCRD-003245 | sales_order_number: live=None test=TR-4452
    invoice_number=FCRD-003274 | sales_order_number: live=None test=TR-4456
    invoice_number=FCRD-003326 | sales_order_number: live=None test=TR-4463
    invoice_number=FCRD-003355 | sales_order_number: live=None test=TR-4466
    invoice_number=FCRD-003584 | sales_order_number: live=None test=TR-4489
    invoice_number=FCRD-003663 | sales_order_number: live=None test=TR-4497
    invoice_number=FCRD-003772 | sales_order_number: live=None test=TR-4507
    invoice_number=FCRD-003903 | sales_order_number: live=None test=TR-000006914
    invoice_number=FCRD-003960 | sales_order_number: live=None test=TR-000006932
    invoice_number=FCRD-004014 | sales_order_number: live=None test=TR-000006928
    invoice_number=FINV-000719 | sales_order_number: live=None test=TR-4472
    invoice_number=FINV-000741 | sales_order_number: live=None test=TR-4477
    invoice_number=FINV-000754 | sales_order_number: live=None test=TR-4486
    invoice_number=FINV-000768 | sales_order_number: live=None test=TR-4500
    invoice_number=FINV-000778 | sales_order_number: live=None test=TR-4508
    invoice_number=FINV-000782 | sales_order_number: live=None test=TR-4509
    invoice_number=FINV-000796 | sales_order_number: live=None test=TR-000006925
    invoice_number=IN00828240 | subtotal_invoices: live=12877.6600 test=14308.5100
    invoice_number=IN00828240 | total_invoice: live=15023.9400 test=16454.7900
    invoice_number=IN00904557 | subtotal_invoices: live=0 test=29
    invoice_number=IN00963267 | cc_charges: live=326.3300 test=71.3300
    invoice_number=IN00963267 | freight_charges: live=0 test=255
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Credits [DIFF]
  Row key: invoice_number
  Rows live=558 test=557 matched=557
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 1 live row(s) missing on /test (0% of live rows).
    - Value diffs by column: sales_order_number=11, subtotal_invoices=9, total_invoice=9
    - Top dates (value-diff rows): 2026-01-01=3, 2026-01-26=3, 2026-02-02=3, 2026-02-10=3, 2026-04-16=3
    - All sales_order_number diffs: live is empty/zero, /test has a value.
  Missing in /test (1):
    invoice_number=0 (invoice_date=-2814911401444442112.0000, customer_account=Total, customer_name=None)
  Value diffs (29):
    invoice_number=FCRD-003244 | sales_order_number: live=None test=TR-4450
    invoice_number=FCRD-003244 | subtotal_invoices: live=-2986.8400 test=2986.8400
    invoice_number=FCRD-003244 | total_invoice: live=-2986.8400 test=2986.8400
    invoice_number=FCRD-003245 | sales_order_number: live=None test=TR-4452
    invoice_number=FCRD-003274 | sales_order_number: live=None test=TR-4456
    invoice_number=FCRD-003274 | subtotal_invoices: live=-10431.4900 test=10431.4900
    invoice_number=FCRD-003274 | total_invoice: live=-10431.4900 test=10431.4900
    invoice_number=FCRD-003326 | sales_order_number: live=None test=TR-4463
    invoice_number=FCRD-003326 | subtotal_invoices: live=-156.1200 test=156.1200
    invoice_number=FCRD-003326 | total_invoice: live=-156.1200 test=156.1200
    invoice_number=FCRD-003355 | sales_order_number: live=None test=TR-4466
    invoice_number=FCRD-003355 | subtotal_invoices: live=-56.2800 test=56.2800
    invoice_number=FCRD-003355 | total_invoice: live=-56.2800 test=56.2800
    invoice_number=FCRD-003584 | sales_order_number: live=None test=TR-4489
    invoice_number=FCRD-003584 | subtotal_invoices: live=-35.7700 test=35.7700
    invoice_number=FCRD-003584 | total_invoice: live=-35.7700 test=35.7700
    invoice_number=FCRD-003663 | sales_order_number: live=None test=TR-4497
    invoice_number=FCRD-003663 | subtotal_invoices: live=-178.1600 test=178.1600
    invoice_number=FCRD-003663 | total_invoice: live=-178.1600 test=178.1600
    invoice_number=FCRD-003772 | sales_order_number: live=None test=TR-4507
    invoice_number=FCRD-003772 | subtotal_invoices: live=-147.3900 test=147.3900
    invoice_number=FCRD-003772 | total_invoice: live=-147.3900 test=147.3900
    invoice_number=FCRD-003903 | sales_order_number: live=None test=TR-000006914
    invoice_number=FCRD-003903 | subtotal_invoices: live=-303.0100 test=303.0100
    invoice_number=FCRD-003903 | total_invoice: live=-303.0100 test=303.0100
    invoice_number=FCRD-003960 | sales_order_number: live=None test=TR-000006932
    invoice_number=FCRD-003960 | subtotal_invoices: live=-1118.5500 test=1118.5500
    invoice_number=FCRD-003960 | total_invoice: live=-1118.5500 test=1118.5500
    invoice_number=FCRD-004014 | sales_order_number: live=None test=TR-000006928
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Invoices [DIFF]
  Row key: invoice_number
  Rows live=153839 test=153838 matched=153838
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 1 live row(s) missing on /test (0% of live rows).
    - Value diffs by column: subtotal_invoices=9, total_invoice=8, sales_order_number=7, cc_charges=1, freight_charges=1
    - Top dates (value-diff rows): 2026-02-12=3, 2026-03-12=3, 2026-03-31=3, 2026-05-04=3, 2026-05-26=3
    - All sales_order_number diffs: live is empty/zero, /test has a value.
  Missing in /test (1):
    invoice_number=0 (invoice_date=-2390145101845398016.0000, customer_account=Total, customer_name=None)
  Value diffs (26):
    invoice_number=IN00828240 | subtotal_invoices: live=12877.6600 test=14308.5100
    invoice_number=IN00828240 | total_invoice: live=15023.9400 test=16454.7900
    invoice_number=FINV-000719 | sales_order_number: live=None test=TR-4472
    invoice_number=FINV-000719 | subtotal_invoices: live=399.1200 test=-399.1200
    invoice_number=FINV-000719 | total_invoice: live=399.1200 test=-399.1200
    invoice_number=FINV-000741 | sales_order_number: live=None test=TR-4477
    invoice_number=FINV-000741 | subtotal_invoices: live=990.6400 test=-990.6400
    invoice_number=FINV-000741 | total_invoice: live=990.6400 test=-990.6400
    invoice_number=FINV-000754 | sales_order_number: live=None test=TR-4486
    invoice_number=FINV-000754 | subtotal_invoices: live=3604 test=-3604
    invoice_number=FINV-000754 | total_invoice: live=3604 test=-3604
    invoice_number=IN00904557 | subtotal_invoices: live=0 test=29
    invoice_number=FINV-000768 | sales_order_number: live=None test=TR-4500
    invoice_number=FINV-000768 | subtotal_invoices: live=615.6000 test=-615.6000
    invoice_number=FINV-000768 | total_invoice: live=615.6000 test=-615.6000
    invoice_number=FINV-000778 | sales_order_number: live=None test=TR-4508
    invoice_number=FINV-000778 | subtotal_invoices: live=615.6000 test=-615.6000
    invoice_number=FINV-000778 | total_invoice: live=615.6000 test=-615.6000
    invoice_number=FINV-000782 | sales_order_number: live=None test=TR-4509
    invoice_number=FINV-000782 | subtotal_invoices: live=0.8000 test=-0.8000
    invoice_number=FINV-000782 | total_invoice: live=0.8000 test=-0.8000
    invoice_number=FINV-000796 | sales_order_number: live=None test=TR-000006925
    invoice_number=FINV-000796 | subtotal_invoices: live=0.2000 test=-0.2000
    invoice_number=FINV-000796 | total_invoice: live=0.2000 test=-0.2000
    invoice_number=IN00963267 | cc_charges: live=326.3300 test=71.3300
    invoice_number=IN00963267 | freight_charges: live=0 test=255
  Soft/cosmetic text diffs (not failing): 51

## Sheet: Audit - Reversals [DIFF]
  Row key: invoice_number
  Rows live=46 test=45 matched=45
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 1 live row(s) missing on /test (2% of live rows).
    - Value diffs by column: sales_order_number=18, subtotal_invoices=16, total_invoice=16
    - Top dates (value-diff rows): 2026-01-01=3, 2026-01-26=3, 2026-02-02=3, 2026-02-10=3, 2026-04-16=3
    - All sales_order_number diffs: live is empty/zero, /test has a value.
  Missing in /test (1):
    invoice_number=0 (invoice_date=-843725463385964544.0000, customer_account=Total, customer_name=None)
  Value diffs (50):
    invoice_number=FCRD-003244 | sales_order_number: live=None test=TR-4450
    invoice_number=FCRD-003244 | subtotal_invoices: live=-2986.8400 test=2986.8400
    invoice_number=FCRD-003244 | total_invoice: live=-2986.8400 test=2986.8400
    invoice_number=FCRD-003245 | sales_order_number: live=None test=TR-4452
    invoice_number=FCRD-003274 | sales_order_number: live=None test=TR-4456
    invoice_number=FCRD-003274 | subtotal_invoices: live=-10431.4900 test=10431.4900
    invoice_number=FCRD-003274 | total_invoice: live=-10431.4900 test=10431.4900
    invoice_number=FCRD-003326 | sales_order_number: live=None test=TR-4463
    invoice_number=FCRD-003326 | subtotal_invoices: live=-156.1200 test=156.1200
    invoice_number=FCRD-003326 | total_invoice: live=-156.1200 test=156.1200
    invoice_number=FCRD-003355 | sales_order_number: live=None test=TR-4466
    invoice_number=FCRD-003355 | subtotal_invoices: live=-56.2800 test=56.2800
    invoice_number=FCRD-003355 | total_invoice: live=-56.2800 test=56.2800
    invoice_number=FCRD-003584 | sales_order_number: live=None test=TR-4489
    invoice_number=FCRD-003584 | subtotal_invoices: live=-35.7700 test=35.7700
    invoice_number=FCRD-003584 | total_invoice: live=-35.7700 test=35.7700
    invoice_number=FCRD-003663 | sales_order_number: live=None test=TR-4497
    invoice_number=FCRD-003663 | subtotal_invoices: live=-178.1600 test=178.1600
    invoice_number=FCRD-003663 | total_invoice: live=-178.1600 test=178.1600
    invoice_number=FCRD-003772 | sales_order_number: live=None test=TR-4507
    invoice_number=FCRD-003772 | subtotal_invoices: live=-147.3900 test=147.3900
    invoice_number=FCRD-003772 | total_invoice: live=-147.3900 test=147.3900
    invoice_number=FCRD-003903 | sales_order_number: live=None test=TR-000006914
    invoice_number=FCRD-003903 | subtotal_invoices: live=-303.0100 test=303.0100
    invoice_number=FCRD-003903 | total_invoice: live=-303.0100 test=303.0100
    invoice_number=FCRD-003960 | sales_order_number: live=None test=TR-000006932
    invoice_number=FCRD-003960 | subtotal_invoices: live=-1118.5500 test=1118.5500
    invoice_number=FCRD-003960 | total_invoice: live=-1118.5500 test=1118.5500
    invoice_number=FCRD-004014 | sales_order_number: live=None test=TR-000006928
    invoice_number=FINV-000719 | sales_order_number: live=None test=TR-4472
    invoice_number=FINV-000719 | subtotal_invoices: live=399.1200 test=-399.1200
    invoice_number=FINV-000719 | total_invoice: live=399.1200 test=-399.1200
    invoice_number=FINV-000741 | sales_order_number: live=None test=TR-4477
    invoice_number=FINV-000741 | subtotal_invoices: live=990.6400 test=-990.6400
    invoice_number=FINV-000741 | total_invoice: live=990.6400 test=-990.6400
    invoice_number=FINV-000754 | sales_order_number: live=None test=TR-4486
    invoice_number=FINV-000754 | subtotal_invoices: live=3604 test=-3604
    invoice_number=FINV-000754 | total_invoice: live=3604 test=-3604
    invoice_number=FINV-000768 | sales_order_number: live=None test=TR-4500
    invoice_number=FINV-000768 | subtotal_invoices: live=615.6000 test=-615.6000
    invoice_number=FINV-000768 | total_invoice: live=615.6000 test=-615.6000
    invoice_number=FINV-000778 | sales_order_number: live=None test=TR-4508
    invoice_number=FINV-000778 | subtotal_invoices: live=615.6000 test=-615.6000
    invoice_number=FINV-000778 | total_invoice: live=615.6000 test=-615.6000
    invoice_number=FINV-000782 | sales_order_number: live=None test=TR-4509
    invoice_number=FINV-000782 | subtotal_invoices: live=0.8000 test=-0.8000
    invoice_number=FINV-000782 | total_invoice: live=0.8000 test=-0.8000
    invoice_number=FINV-000796 | sales_order_number: live=None test=TR-000006925
    invoice_number=FINV-000796 | subtotal_invoices: live=0.2000 test=-0.2000
    invoice_number=FINV-000796 | total_invoice: live=0.2000 test=-0.2000
  Soft/cosmetic text diffs (not failing): 28

## Sheet: Totals by Salesman [DIFF]
  Row key: salesman_code
  Rows live=13 test=12 matched=12
  Extra columns in /test (ignored): misc_charges
  Missing columns in /test: salesman_number
  Patterns:
    - 1 live row(s) missing on /test (8% of live rows).
    - Value diffs by column: invoice_count=10, subtotal_invoices=10, total_invoice=10, cc_charges=1, freight_charges=1
  Missing in /test (1):
    salesman_code=0
  Value diffs (32):
    salesman_code=MKolko | invoice_count: live=638 test=681
    salesman_code=MKolko | subtotal_invoices: live=1168132.6100 test=1151838.0700
    salesman_code=MKolko | total_invoice: live=1259440.4400 test=1243145.9000
    salesman_code=BLevin | invoice_count: live=857 test=897
    salesman_code=BLevin | subtotal_invoices: live=577375.7300 test=563859.6300
    salesman_code=BLevin | total_invoice: live=629814.7500 test=616298.6500
    salesman_code=HKaufman | cc_charges: live=481.2000 test=226.2000
    salesman_code=HKaufman | freight_charges: live=20981.3500 test=21236.3500
    salesman_code=HKaufman | invoice_count: live=6653 test=6753
    salesman_code=HKaufman | subtotal_invoices: live=2126574.2800 test=2002997.1700
    salesman_code=HKaufman | total_invoice: live=2242278.7000 test=2118701.5900
    salesman_code=AGrossman | invoice_count: live=38039 test=38188
    salesman_code=AGrossman | subtotal_invoices: live=2241273.6400 test=1934471.1200
    salesman_code=AGrossman | total_invoice: live=2251817.4300 test=1945014.9100
    salesman_code=JWeigand | invoice_count: live=10248 test=10288
    salesman_code=JWeigand | subtotal_invoices: live=256121.1100 test=196755.2500
    salesman_code=JWeigand | total_invoice: live=265203.1400 test=205837.2800
    salesman_code=LCWalker | invoice_count: live=12 test=13
    salesman_code=LCWalker | subtotal_invoices: live=92020.5200 test=92020.3200
    salesman_code=LCWalker | total_invoice: live=107476.4800 test=107476.2800
    salesman_code=Integrated | invoice_count: live=48460 test=48617
    salesman_code=Integrated | subtotal_invoices: live=2711214.1600 test=1934335.9100
    salesman_code=Integrated | total_invoice: live=2711214.1600 test=1934335.9100
    salesman_code=House | invoice_count: live=46 test=52
    salesman_code=House | subtotal_invoices: live=23119.6100 test=21985.8300
    salesman_code=House | total_invoice: live=24055.6600 test=22892.8800
    salesman_code=MGrego | invoice_count: live=100 test=119
    salesman_code=MGrego | subtotal_invoices: live=171203.8900 test=167956.5800
    salesman_code=MGrego | total_invoice: live=171348.6700 test=168101.3600
    salesman_code=Unassigned | invoice_count: live=31 test=33
    salesman_code=Unassigned | subtotal_invoices: live=2312848.7100 test=2312834.5100
    salesman_code=Unassigned | total_invoice: live=2312848.7100 test=2312834.5100
  Soft/cosmetic text diffs (not failing): 2
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
