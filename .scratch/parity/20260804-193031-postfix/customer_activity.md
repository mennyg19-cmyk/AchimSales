# Parity: customer_activity

- Params: `{}`
- Live file: `.scratch\parity\20260804-193031-postfix\customer_activity__live.xlsx`
- Test file: `.scratch\parity\20260804-193031-postfix\customer_activity__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **194**
- Missing sheets in /test: (none)
- Extra sheets in /test (ignored): (none)
- Per sheet: All=DIFF(97), AGrossman=DIFF(5), BLevin=DIFF(6), HKaufman=DIFF(6), House=DIFF(2), Integrated=DIFF(4), JWeigand=DIFF(5), LCWalker=DIFF(2), MGrego=DIFF(26), MKolko=DIFF(29), PMazer=MATCH(0), REdwards=DIFF(2), Unassigned=DIFF(10)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260804-193031-postfix\customer_activity__live.xlsx vs .scratch\parity\20260804-193031-postfix\customer_activity__test.xlsx
Hard differences: 194
Result: DIFFERENCES FOUND

## Sheet: All [DIFF]
  Row key: customer_account
  Rows live=782 test=782 matched=782
  Patterns:
    - Value diffs by column: last_order_date=49, po_number=26, sales_order_number=22
  Value diffs (97):
    customer_account=9022 | po_number: live=360627672_736 test=360625077_732
    customer_account=9022 | sales_order_number: live=ORD00890855 test=ORD00890746
    customer_account=11535 | last_order_date: live=2026-05-26 test=2026-05-28
    customer_account=7125 | po_number: live=119121733670512 test=119121733117720
    customer_account=7125 | sales_order_number: live=ORD00890875 test=ORD00890812
    customer_account=8340 | last_order_date: live=2026-01-22 test=2026-01-23
    customer_account=419 | last_order_date: live=2026-07-06 test=2026-07-08
    customer_account=9019 | last_order_date: live=2025-12-11 test=2025-12-15
    customer_account=6262 | po_number: live=5118523433 test=5118522679
    customer_account=6262 | sales_order_number: live=ORD00890858 test=ORD00890814
    customer_account=11028 | last_order_date: live=2025-04-17 test=2025-04-18
    customer_account=38012 | last_order_date: live=2026-07-10 test=2026-07-13
    customer_account=5233 | last_order_date: live=2026-04-13 test=2026-04-28
    customer_account=846 | last_order_date: live=2026-07-23 test=2026-07-24
    customer_account=5318 | last_order_date: live=2025-05-05 test=2025-05-13
    customer_account=8015 | po_number: live=CS672085175 test=CS672069512
    customer_account=8015 | sales_order_number: live=ORD00890863 test=ORD00890802
    customer_account=ALEJANDRO CRUZ | po_number: live=None test=N/A
    customer_account=3183710 | po_number: live=None test=N/A
    customer_account=7025 | po_number: live=78713396 test=78698639
    customer_account=7025 | sales_order_number: live=ORD00890869 test=ORD00890816
    customer_account=9206 | po_number: live=414642986 test=414630716
    customer_account=9206 | sales_order_number: live=ORD00890864 test=ORD00890818
    customer_account=1412 | last_order_date: live=2026-08-04 test=2026-08-03
    customer_account=1412 | po_number: live=6725626163_1 test=6725601601_2
    customer_account=1412 | sales_order_number: live=ORD00890817 test=ORD00890667
    customer_account=9188 | po_number: live=8868686 test=8868584
    customer_account=9188 | sales_order_number: live=ORD00890838 test=ORD00890735
    customer_account=2942414 | last_order_date: live=2025-01-22 test=2025-01-23
    customer_account=8276 | last_order_date: live=2026-07-16 test=2026-07-20
    customer_account=11469 | last_order_date: live=2026-02-11 test=2026-02-13
    customer_account=11175 | po_number: live=None test=N/A
    customer_account=11604 | last_order_date: live=2026-06-15 test=2026-06-17
    customer_account=11016 | last_order_date: live=2025-04-07 test=2025-06-24
    customer_account=11016 | po_number: live=BD472025 test=UNPAID RETURN
    customer_account=11016 | sales_order_number: live=ORD00556950 test=ORD00608643
    customer_account=5358 | last_order_date: live=2026-07-29 test=2026-07-30
    customer_account=DREISER DISCOUNT | last_order_date: live=2025-05-21 test=2025-06-04
    customer_account=8130 | last_order_date: live=2026-04-28 test=2026-06-29
    customer_account=8130 | po_number: live=8104282601 test=N/A
    customer_account=8130 | sales_order_number: live=ORD00821477 test=ORD00866034
    customer_account=878 | last_order_date: live=2025-06-23 test=2025-06-24
    customer_account=11025 | po_number: live=None test=N/A
    customer_account=11017 | last_order_date: live=2025-10-06 test=2025-10-13
    customer_account=11429 | last_order_date: live=2026-01-13 test=2026-01-15
    customer_account=11481 | last_order_date: live=2026-02-19 test=2026-02-23
    customer_account=3038570 | last_order_date: live=2025-02-12 test=2025-02-13
    customer_account=3316837 | last_order_date: live=2025-11-20 test=2025-12-18
    customer_account=3316837 | sales_order_number: live=ORD00711302 test=ORD00733218
    customer_account=3208263 | last_order_date: live=2026-06-10 test=2026-06-12
    ... +47 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: AGrossman [DIFF]
  Row key: customer_account
  Rows live=40 test=40 matched=40
  Patterns:
    - Value diffs by column: po_number=2, sales_order_number=2, last_order_date=1
  Value diffs (5):
    customer_account=9022 | po_number: live=360627672_736 test=360625077_732
    customer_account=9022 | sales_order_number: live=ORD00890855 test=ORD00890746
    customer_account=11535 | last_order_date: live=2026-05-26 test=2026-05-28
    customer_account=7125 | po_number: live=119121733670512 test=119121733117720
    customer_account=7125 | sales_order_number: live=ORD00890875 test=ORD00890812
  Soft/cosmetic text diffs (not failing): 17

## Sheet: BLevin [DIFF]
  Row key: customer_account
  Rows live=113 test=113 matched=113
  Patterns:
    - Value diffs by column: last_order_date=4, po_number=1, sales_order_number=1
  Value diffs (6):
    customer_account=8340 | last_order_date: live=2026-01-22 test=2026-01-23
    customer_account=419 | last_order_date: live=2026-07-06 test=2026-07-08
    customer_account=9019 | last_order_date: live=2025-12-11 test=2025-12-15
    customer_account=6262 | po_number: live=5118523433 test=5118522679
    customer_account=6262 | sales_order_number: live=ORD00890858 test=ORD00890814
    customer_account=11028 | last_order_date: live=2025-04-17 test=2025-04-18
  Soft/cosmetic text diffs (not failing): 21

## Sheet: HKaufman [DIFF]
  Row key: customer_account
  Rows live=188 test=188 matched=188
  Patterns:
    - Value diffs by column: last_order_date=4, po_number=1, sales_order_number=1
  Value diffs (6):
    customer_account=38012 | last_order_date: live=2026-07-10 test=2026-07-13
    customer_account=5233 | last_order_date: live=2026-04-13 test=2026-04-28
    customer_account=846 | last_order_date: live=2026-07-23 test=2026-07-24
    customer_account=5318 | last_order_date: live=2025-05-05 test=2025-05-13
    customer_account=8015 | po_number: live=CS672085175 test=CS672069512
    customer_account=8015 | sales_order_number: live=ORD00890863 test=ORD00890802
  Soft/cosmetic text diffs (not failing): 51

## Sheet: House [DIFF]
  Row key: customer_account
  Rows live=24 test=24 matched=24
  Patterns:
    - Value diffs by column: po_number=2
  Value diffs (2):
    customer_account=ALEJANDRO CRUZ | po_number: live=None test=N/A
    customer_account=3183710 | po_number: live=None test=N/A
  Soft/cosmetic text diffs (not failing): 4

## Sheet: Integrated [DIFF]
  Row key: customer_account
  Rows live=4 test=4 matched=4
  Patterns:
    - Value diffs by column: po_number=2, sales_order_number=2
  Value diffs (4):
    customer_account=7025 | po_number: live=78713396 test=78698639
    customer_account=7025 | sales_order_number: live=ORD00890869 test=ORD00890816
    customer_account=9206 | po_number: live=414642986 test=414630716
    customer_account=9206 | sales_order_number: live=ORD00890864 test=ORD00890818

## Sheet: JWeigand [DIFF]
  Row key: customer_account
  Rows live=7 test=7 matched=7
  Patterns:
    - Value diffs by column: po_number=2, sales_order_number=2, last_order_date=1
  Value diffs (5):
    customer_account=1412 | last_order_date: live=2026-08-04 test=2026-08-03
    customer_account=1412 | po_number: live=6725626163_1 test=6725601601_2
    customer_account=1412 | sales_order_number: live=ORD00890817 test=ORD00890667
    customer_account=9188 | po_number: live=8868686 test=8868584
    customer_account=9188 | sales_order_number: live=ORD00890838 test=ORD00890735
  Soft/cosmetic text diffs (not failing): 7

## Sheet: LCWalker [DIFF]
  Row key: customer_account
  Rows live=5 test=5 matched=5
  Patterns:
    - Value diffs by column: last_order_date=2
  Value diffs (2):
    customer_account=2942414 | last_order_date: live=2025-01-22 test=2025-01-23
    customer_account=8276 | last_order_date: live=2026-07-16 test=2026-07-20
  Soft/cosmetic text diffs (not failing): 1

## Sheet: MGrego [DIFF]
  Row key: customer_account
  Rows live=178 test=178 matched=178
  Patterns:
    - Value diffs by column: last_order_date=19, po_number=4, sales_order_number=3
  Value diffs (26):
    customer_account=11469 | last_order_date: live=2026-02-11 test=2026-02-13
    customer_account=11175 | po_number: live=None test=N/A
    customer_account=11604 | last_order_date: live=2026-06-15 test=2026-06-17
    customer_account=11016 | last_order_date: live=2025-04-07 test=2025-06-24
    customer_account=11016 | po_number: live=BD472025 test=UNPAID RETURN
    customer_account=11016 | sales_order_number: live=ORD00556950 test=ORD00608643
    customer_account=5358 | last_order_date: live=2026-07-29 test=2026-07-30
    customer_account=DREISER DISCOUNT | last_order_date: live=2025-05-21 test=2025-06-04
    customer_account=8130 | last_order_date: live=2026-04-28 test=2026-06-29
    customer_account=8130 | po_number: live=8104282601 test=N/A
    customer_account=8130 | sales_order_number: live=ORD00821477 test=ORD00866034
    customer_account=878 | last_order_date: live=2025-06-23 test=2025-06-24
    customer_account=11025 | po_number: live=None test=N/A
    customer_account=11017 | last_order_date: live=2025-10-06 test=2025-10-13
    customer_account=11429 | last_order_date: live=2026-01-13 test=2026-01-15
    customer_account=11481 | last_order_date: live=2026-02-19 test=2026-02-23
    customer_account=3038570 | last_order_date: live=2025-02-12 test=2025-02-13
    customer_account=3316837 | last_order_date: live=2025-11-20 test=2025-12-18
    customer_account=3316837 | sales_order_number: live=ORD00711302 test=ORD00733218
    customer_account=3208263 | last_order_date: live=2026-06-10 test=2026-06-12
    customer_account=3139669 | last_order_date: live=2025-10-10 test=2025-10-20
    customer_account=3270645 | last_order_date: live=2025-10-06 test=2025-10-09
    customer_account=3196984 | last_order_date: live=2026-04-13 test=2026-05-07
    customer_account=ROCHDALE OUTLET DEPA | last_order_date: live=2026-06-29 test=2026-07-13
    customer_account=SAGOR DISCOUNT INC. | last_order_date: live=2026-04-06 test=2026-04-07
    customer_account=11083 | last_order_date: live=2026-03-11 test=2026-03-19
  Soft/cosmetic text diffs (not failing): 31

## Sheet: MKolko [DIFF]
  Row key: customer_account
  Rows live=167 test=167 matched=167
  Patterns:
    - Value diffs by column: last_order_date=14, sales_order_number=8, po_number=7
  Value diffs (29):
    customer_account=308 | last_order_date: live=2026-06-30 test=2026-07-28
    customer_account=308 | po_number: live=3006302602 test=N/A
    customer_account=308 | sales_order_number: live=ORD00866879 test=ORD00886372
    customer_account=5067 | last_order_date: live=2026-06-24 test=2026-06-25
    customer_account=647 | last_order_date: live=2026-06-17 test=2026-06-18
    customer_account=6336 | last_order_date: live=2026-04-13 test=2026-04-14
    customer_account=3057 | last_order_date: live=2026-08-04 test=2026-06-23
    customer_account=3057 | po_number: live=26658 test=26019
    customer_account=3057 | sales_order_number: live=ORD00890877 test=ORD00860990
    customer_account=9497 | last_order_date: live=2026-04-20 test=2026-06-30
    customer_account=9497 | po_number: live=9404202601 test=N/A
    customer_account=9497 | sales_order_number: live=ORD00815401 test=ORD00866628
    customer_account=8023 | last_order_date: live=2026-07-23 test=2026-07-28
    customer_account=8023 | po_number: live=8007232601 test=N/A
    customer_account=8023 | sales_order_number: live=ORD00883038 test=ORD00886153
    customer_account=9437 | last_order_date: live=2026-05-27 test=2026-06-15
    customer_account=1978 | last_order_date: live=2026-07-10 test=2026-07-20
    customer_account=5102 | last_order_date: live=2026-07-07 test=2026-07-08
    customer_account=2449 | last_order_date: live=2025-12-15 test=2025-12-22
    customer_account=2449 | sales_order_number: live=ORD00729400 test=ORD00733683
    customer_account=9025 | last_order_date: live=2026-07-21 test=2026-07-28
    customer_account=9025 | po_number: live=9007212603 test=N/A
    customer_account=9025 | sales_order_number: live=ORD00881505 test=ORD00886371
    customer_account=11247 | last_order_date: live=2026-05-06 test=2026-07-28
    customer_account=11247 | po_number: live=0005062603 test=N/A
    customer_account=11247 | sales_order_number: live=ORD00828307 test=ORD00886159
    customer_account=2854 | last_order_date: live=2026-05-11 test=2026-07-28
    customer_account=2854 | po_number: live=2805112601 test=N/A
    customer_account=2854 | sales_order_number: live=ORD00831243 test=ORD00886152
  Soft/cosmetic text diffs (not failing): 51

## Sheet: PMazer [MATCH]
  Row key: customer_account
  Rows live=3 test=3 matched=3
  Soft/cosmetic text diffs (not failing): 1

## Sheet: REdwards [DIFF]
  Row key: customer_account
  Rows live=3 test=3 matched=3
  Patterns:
    - Value diffs by column: po_number=1, sales_order_number=1
  Value diffs (2):
    customer_account=9303 | po_number: live=PtMgrkvg0 test=Ptvd3cvq0
    customer_account=9303 | sales_order_number: live=ORD00890876 test=ORD00890827
  Soft/cosmetic text diffs (not failing): 1

## Sheet: Unassigned [DIFF]
  Row key: customer_account
  Rows live=50 test=50 matched=50
  Patterns:
    - Value diffs by column: last_order_date=4, po_number=4, sales_order_number=2
  Value diffs (10):
    customer_account=11205 | last_order_date: live=2025-08-31 test=2025-09-02
    customer_account=11205 | po_number: live=None test=N/A
    customer_account=11454 | po_number: live=None test=N/A
    customer_account=11552 | last_order_date: live=2026-04-22 test=N/A
    customer_account=11552 | po_number: live=0004222601 test=N/A
    customer_account=11552 | sales_order_number: live=ORD00816868 test=N/A
    customer_account=7072 | last_order_date: live=2025-07-02 test=2025-07-18
    customer_account=11239 | last_order_date: live=2026-07-31 test=2026-08-03
    customer_account=11239 | po_number: live=0007312601 test=N/A
    customer_account=11239 | sales_order_number: live=ORD00888067 test=ORD00890166
  Soft/cosmetic text diffs (not failing): 14
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
