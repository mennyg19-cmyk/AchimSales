# Parity: customer_activity

- Params: `{}`
- Live file: `D:\Projects\Achim\AchimSales\.scratch\parity\20260726-113809-customer_activity\customer_activity__live.xlsx`
- Test file: `D:\Projects\Achim\AchimSales\.scratch\parity\20260726-113809-customer_activity\customer_activity__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **1448**
- Missing sheets in /test: (none)
- Extra sheets in /test (ignored): (none)
- Per sheet: All=DIFF(724), AGrossman=DIFF(48), BLevin=DIFF(84), HKaufman=DIFF(177), House=DIFF(20), Integrated=DIFF(7), JWeigand=DIFF(13), LCWalker=DIFF(7), MGrego=DIFF(156), MKolko=DIFF(169), PMazer=DIFF(3), REdwards=DIFF(9), Unassigned=DIFF(31)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: D:\Projects\Achim\AchimSales\.scratch\parity\20260726-113809-customer_activity\customer_activity__live.xlsx vs D:\Projects\Achim\AchimSales\.scratch\parity\20260726-113809-customer_activity\customer_activity__test.xlsx
Hard differences: 1448
Result: DIFFERENCES FOUND

## Sheet: All [DIFF]
  Row key: customer_account
  Rows live=781 test=781 matched=781
  Patterns:
    - Value diffs by column: last_order_date=525, sales_order_number=101, po_number=98
  Value diffs (724):
    customer_account=11184 | last_order_date: live=2026-07-15 test=07/17/2026
    customer_account=9250 | last_order_date: live=2025-09-17 test=09/11/2025
    customer_account=9250 | po_number: live=0052703408 test=0052483614
    customer_account=9250 | sales_order_number: live=ORD00662168 test=ORD00657632
    customer_account=7009 | last_order_date: live=2025-06-09 test=12/10/2025
    customer_account=7009 | po_number: live=3405198 test=N/A
    customer_account=7009 | sales_order_number: live=ORD00600032 test=TR-4421
    customer_account=48999 | last_order_date: live=2026-07-16 test=07/23/2026
    customer_account=11624 | last_order_date: live=2026-07-17 test=07/20/2026
    customer_account=11103 | last_order_date: live=2025-07-09 test=07/10/2025
    customer_account=Choice Paper Co. Inc | last_order_date: live=2025-01-30 test=03/04/2025
    customer_account=866 | po_number: live=64317474 test=63419249
    customer_account=866 | sales_order_number: live=ORD00882052 test=ORD00868695
    customer_account=3378476 | last_order_date: live=2026-06-19 test=06/24/2026
    customer_account=2958707 | last_order_date: live=2026-07-22 test=07/23/2026
    customer_account=11600 | last_order_date: live=2026-07-22 test=07/13/2026
    customer_account=11600 | po_number: live=72417 test=70208
    customer_account=11600 | sales_order_number: live=ORD00882553 test=ORD00848079
    customer_account=7136 | last_order_date: live=2025-02-03 test=02/04/2025
    customer_account=9022 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=9022 | po_number: live=218641349_732 test=218607130_709
    customer_account=9022 | sales_order_number: live=ORD00884679 test=ORD00883773
    customer_account=8264 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=8264 | po_number: live=ACH-4005 test=ACH-4003
    customer_account=8264 | sales_order_number: live=ORD00884664 test=ORD00883470
    customer_account=9207 | last_order_date: live=N/A test=09/02/2025
    customer_account=9207 | sales_order_number: live=N/A test=TR-4385
    customer_account=8330 | last_order_date: live=2026-07-25 test=07/24/2026
    customer_account=8330 | po_number: live=421975728 test=420330216
    customer_account=8330 | sales_order_number: live=ORD00884496 test=ORD00883401
    customer_account=11598 | last_order_date: live=2026-05-28 test=06/02/2026
    customer_account=11535 | last_order_date: live=2026-05-26 test=05/29/2026
    customer_account=9091 | last_order_date: live=2026-07-25 test=07/24/2026
    customer_account=9091 | po_number: live=9980731330 test=9980720680
    customer_account=9091 | sales_order_number: live=ORD00884569 test=ORD00883655
    customer_account=3389173 | last_order_date: live=2026-03-19 test=03/25/2026
    customer_account=5121 | last_order_date: live=2026-07-21 test=07/22/2026
    customer_account=9122 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=9122 | po_number: live=ACHI-16729 test=ACHI-16727
    customer_account=9122 | sales_order_number: live=ORD00884645 test=ORD00883604
    customer_account=7125 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=7125 | po_number: live=119120876921839 test=119120669854757
    customer_account=7125 | sales_order_number: live=ORD00884671 test=ORD00883781
    customer_account=8296 | last_order_date: live=2026-07-20 test=07/21/2026
    customer_account=8296 | po_number: live=4384793884 test=4384793717
    customer_account=8296 | sales_order_number: live=ORD00880873 test=ORD00875779
    customer_account=9196 | po_number: live=3869184334 test=8609034359
    customer_account=9196 | sales_order_number: live=ORD00883545 test=ORD00880729
    customer_account=3269096 | last_order_date: live=2025-09-09 test=09/12/2025
    customer_account=9423 | last_order_date: live=2026-04-10 test=04/15/2026
    ... +674 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: AGrossman [DIFF]
  Row key: customer_account
  Rows live=40 test=40 matched=40
  Patterns:
    - Value diffs by column: last_order_date=23, sales_order_number=13, po_number=12
  Value diffs (48):
    customer_account=11184 | last_order_date: live=2026-07-15 test=07/17/2026
    customer_account=9250 | last_order_date: live=2025-09-17 test=09/11/2025
    customer_account=9250 | po_number: live=0052703408 test=0052483614
    customer_account=9250 | sales_order_number: live=ORD00662168 test=ORD00657632
    customer_account=7009 | last_order_date: live=2025-06-09 test=12/10/2025
    customer_account=7009 | po_number: live=3405198 test=N/A
    customer_account=7009 | sales_order_number: live=ORD00600032 test=TR-4421
    customer_account=48999 | last_order_date: live=2026-07-16 test=07/23/2026
    customer_account=11624 | last_order_date: live=2026-07-17 test=07/20/2026
    customer_account=11103 | last_order_date: live=2025-07-09 test=07/10/2025
    customer_account=Choice Paper Co. Inc | last_order_date: live=2025-01-30 test=03/04/2025
    customer_account=866 | po_number: live=64317474 test=63419249
    customer_account=866 | sales_order_number: live=ORD00882052 test=ORD00868695
    customer_account=3378476 | last_order_date: live=2026-06-19 test=06/24/2026
    customer_account=2958707 | last_order_date: live=2026-07-22 test=07/23/2026
    customer_account=11600 | last_order_date: live=2026-07-22 test=07/13/2026
    customer_account=11600 | po_number: live=72417 test=70208
    customer_account=11600 | sales_order_number: live=ORD00882553 test=ORD00848079
    customer_account=7136 | last_order_date: live=2025-02-03 test=02/04/2025
    customer_account=9022 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=9022 | po_number: live=218641349_732 test=218607130_709
    customer_account=9022 | sales_order_number: live=ORD00884679 test=ORD00883773
    customer_account=8264 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=8264 | po_number: live=ACH-4005 test=ACH-4003
    customer_account=8264 | sales_order_number: live=ORD00884664 test=ORD00883470
    customer_account=9207 | last_order_date: live=N/A test=09/02/2025
    customer_account=9207 | sales_order_number: live=N/A test=TR-4385
    customer_account=8330 | last_order_date: live=2026-07-25 test=07/24/2026
    customer_account=8330 | po_number: live=421975728 test=420330216
    customer_account=8330 | sales_order_number: live=ORD00884496 test=ORD00883401
    customer_account=11598 | last_order_date: live=2026-05-28 test=06/02/2026
    customer_account=11535 | last_order_date: live=2026-05-26 test=05/29/2026
    customer_account=9091 | last_order_date: live=2026-07-25 test=07/24/2026
    customer_account=9091 | po_number: live=9980731330 test=9980720680
    customer_account=9091 | sales_order_number: live=ORD00884569 test=ORD00883655
    customer_account=3389173 | last_order_date: live=2026-03-19 test=03/25/2026
    customer_account=5121 | last_order_date: live=2026-07-21 test=07/22/2026
    customer_account=9122 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=9122 | po_number: live=ACHI-16729 test=ACHI-16727
    customer_account=9122 | sales_order_number: live=ORD00884645 test=ORD00883604
    customer_account=7125 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=7125 | po_number: live=119120876921839 test=119120669854757
    customer_account=7125 | sales_order_number: live=ORD00884671 test=ORD00883781
    customer_account=8296 | last_order_date: live=2026-07-20 test=07/21/2026
    customer_account=8296 | po_number: live=4384793884 test=4384793717
    customer_account=8296 | sales_order_number: live=ORD00880873 test=ORD00875779
    customer_account=9196 | po_number: live=3869184334 test=8609034359
    customer_account=9196 | sales_order_number: live=ORD00883545 test=ORD00880729
  Soft/cosmetic text diffs (not failing): 17

## Sheet: BLevin [DIFF]
  Row key: customer_account
  Rows live=113 test=113 matched=113
  Patterns:
    - Value diffs by column: last_order_date=77, sales_order_number=4, po_number=3
  Value diffs (84):
    customer_account=3269096 | last_order_date: live=2025-09-09 test=09/12/2025
    customer_account=9423 | last_order_date: live=2026-04-10 test=04/15/2026
    customer_account=174 | last_order_date: live=2026-05-25 test=05/26/2026
    customer_account=6756 | last_order_date: live=2025-11-10 test=11/19/2025
    customer_account=4078 | last_order_date: live=2025-11-10 test=11/19/2025
    customer_account=3075 | last_order_date: live=2026-06-05 test=06/10/2026
    customer_account=5354 | last_order_date: live=2026-06-15 test=06/18/2026
    customer_account=6832 | last_order_date: live=2026-02-20 test=02/25/2026
    customer_account=8340 | last_order_date: live=2026-01-22 test=01/28/2026
    customer_account=419 | last_order_date: live=2026-07-06 test=07/08/2026
    customer_account=11001 | last_order_date: live=2025-03-20 test=03/26/2025
    customer_account=9430 | last_order_date: live=2026-06-29 test=06/30/2026
    customer_account=6264 | last_order_date: live=2026-04-28 test=04/30/2026
    customer_account=9162 | last_order_date: live=2026-04-27 test=04/30/2026
    customer_account=9017 | last_order_date: live=2026-06-30 test=07/02/2026
    customer_account=9455 | last_order_date: live=2025-08-19 test=08/26/2025
    customer_account=6156 | last_order_date: live=2025-05-30 test=07/08/2025
    customer_account=7006 | last_order_date: live=2026-03-19 test=03/25/2026
    customer_account=8370 | last_order_date: live=2026-04-21 test=04/22/2026
    customer_account=2806734 | last_order_date: live=2026-04-01 test=04/07/2026
    customer_account=8302 | last_order_date: live=2025-12-08 test=12/11/2025
    customer_account=8399 | last_order_date: live=2025-04-11 test=04/18/2025
    customer_account=6732 | last_order_date: live=2026-06-25 test=06/30/2026
    customer_account=9454 | last_order_date: live=2025-07-29 test=08/08/2025
    customer_account=9407 | last_order_date: live=2026-03-27 test=04/07/2026
    customer_account=9408 | last_order_date: live=2026-01-13 test=01/16/2026
    customer_account=9422 | last_order_date: live=2026-05-20 test=05/27/2026
    customer_account=9403 | last_order_date: live=2026-04-20 test=04/23/2026
    customer_account=9019 | last_order_date: live=2025-12-11 test=12/16/2025
    customer_account=3177782 | last_order_date: live=2026-06-24 test=06/30/2026
    customer_account=2892232 | last_order_date: live=2026-04-07 test=04/15/2026
    customer_account=6251 | last_order_date: live=2026-05-06 test=05/19/2026
    customer_account=8155 | last_order_date: live=2026-06-17 test=06/26/2026
    customer_account=895 | last_order_date: live=2025-05-13 test=05/14/2025
    customer_account=11389 | last_order_date: live=2025-12-22 test=12/23/2025
    customer_account=3209547 | last_order_date: live=2026-05-25 test=05/27/2026
    customer_account=11155 | last_order_date: live=2025-08-04 test=08/13/2025
    customer_account=9412 | last_order_date: live=2025-04-29 test=04/30/2025
    customer_account=1035 | last_order_date: live=N/A test=04/01/2025
    customer_account=1035 | sales_order_number: live=N/A test=TR-4266
    customer_account=1049 | last_order_date: live=2026-07-14 test=07/17/2026
    customer_account=6304 | last_order_date: live=2026-03-05 test=03/11/2026
    customer_account=6262 | po_number: live=5118468600 test=5118464278
    customer_account=6262 | sales_order_number: live=ORD00883910 test=ORD00883631
    customer_account=1098 | last_order_date: live=2026-03-03 test=03/04/2026
    customer_account=5051 | last_order_date: live=2026-06-05 test=06/10/2026
    customer_account=1063 | last_order_date: live=2026-07-02 test=07/14/2026
    customer_account=9062 | last_order_date: live=2026-03-09 test=03/11/2026
    customer_account=6163 | last_order_date: live=2025-10-06 test=10/17/2025
    customer_account=78005 | last_order_date: live=2025-02-05 test=03/04/2025
    ... +34 more
  Soft/cosmetic text diffs (not failing): 21

## Sheet: HKaufman [DIFF]
  Row key: customer_account
  Rows live=188 test=188 matched=188
  Patterns:
    - Value diffs by column: last_order_date=117, po_number=30, sales_order_number=30
  Value diffs (177):
    customer_account=54 | last_order_date: live=2026-07-13 test=04/23/2025
    customer_account=54 | po_number: live=5407132601 test=I-1800256018
    customer_account=54 | sales_order_number: live=ORD00875810 test=ORD00562679
    customer_account=8306 | last_order_date: live=2026-07-22 test=07/14/2026
    customer_account=8306 | po_number: live=8307222601 test=8307132601
    customer_account=8306 | sales_order_number: live=ORD00882286 test=ORD00875879
    customer_account=3099 | last_order_date: live=2025-11-19 test=12/05/2025
    customer_account=3154111 | last_order_date: live=2025-03-04 test=07/01/2025
    customer_account=3154111 | po_number: live=PO000066766 test=N/A
    customer_account=3154111 | sales_order_number: live=ORD00532743 test=TR-4381
    customer_account=4025 | last_order_date: live=2026-06-03 test=06/10/2026
    customer_account=8397 | last_order_date: live=2026-01-13 test=01/29/2026
    customer_account=5364 | last_order_date: live=2026-03-02 test=04/28/2026
    customer_account=302 | last_order_date: live=2026-06-09 test=06/11/2026
    customer_account=5066 | last_order_date: live=2025-10-29 test=10/31/2025
    customer_account=3028 | last_order_date: live=2026-07-09 test=07/20/2026
    customer_account=7010 | po_number: live=PO0000102189742 test=PO0000102186730
    customer_account=7010 | sales_order_number: live=ORD00644203 test=ORD00643953
    customer_account=356 | last_order_date: live=2026-07-15 test=07/16/2026
    customer_account=350 | last_order_date: live=2026-06-30 test=07/02/2026
    customer_account=351 | last_order_date: live=2026-07-08 test=07/10/2026
    customer_account=91000 | last_order_date: live=2025-12-08 test=02/20/2026
    customer_account=Big Country Note LLC | last_order_date: live=2025-11-28 test=08/22/2025
    customer_account=Big Country Note LLC | po_number: live=BC11282501 test=BC06192501
    customer_account=Big Country Note LLC | sales_order_number: live=ORD00716712 test=ORD00605682
    customer_account=9157 | last_order_date: live=2025-03-07 test=03/12/2025
    customer_account=38012 | last_order_date: live=2026-07-10 test=06/22/2026
    customer_account=38012 | po_number: live=1271026ACHIM test=126826ACHIM
    customer_account=38012 | sales_order_number: live=ORD00873859 test=ORD00856178
    customer_account=5233 | last_order_date: live=2026-04-13 test=05/18/2026
    customer_account=643 | last_order_date: live=2026-07-22 test=07/23/2026
    customer_account=3320740 | last_order_date: live=2026-05-06 test=05/28/2026
    customer_account=4105 | last_order_date: live=2026-07-24 test=07/21/2026
    customer_account=4105 | po_number: live=137329 test=137282
    customer_account=4105 | sales_order_number: live=ORD00883788 test=ORD00878871
    customer_account=535 | last_order_date: live=2025-06-04 test=06/30/2025
    customer_account=COMPLETE KITS INC. | last_order_date: live=2025-11-06 test=01/20/2026
    customer_account=2583831 | last_order_date: live=2025-08-25 test=08/27/2025
    customer_account=11379 | last_order_date: live=2026-06-08 test=06/10/2026
    customer_account=6025 | last_order_date: live=2026-06-10 test=06/15/2026
    customer_account=9099 | last_order_date: live=2025-09-11 test=11/03/2025
    customer_account=11047 | last_order_date: live=2025-09-25 test=11/20/2025
    customer_account=650 | last_order_date: live=2026-02-05 test=02/06/2026
    customer_account=1076 | last_order_date: live=2025-11-21 test=12/05/2025
    customer_account=6995 | last_order_date: live=2025-08-14 test=08/19/2025
    customer_account=1342062 | last_order_date: live=2026-03-18 test=03/30/2026
    customer_account=1342062 | po_number: live=1303182601 test=N/A
    customer_account=1342062 | sales_order_number: live=ORD00787841 test=TR-4483
    customer_account=6248 | last_order_date: live=2026-05-20 test=05/29/2026
    customer_account=802 | last_order_date: live=2026-07-07 test=07/10/2026
    ... +127 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: House [DIFF]
  Row key: customer_account
  Rows live=23 test=23 matched=23
  Patterns:
    - Value diffs by column: last_order_date=12, po_number=5, sales_order_number=3
  Value diffs (20):
    customer_account=ALEJANDRO CRUZ | po_number: live=None test=N/A
    customer_account=11160 | last_order_date: live=2025-08-06 test=12/24/2025
    customer_account=148 | last_order_date: live=2026-04-21 test=04/22/2026
    customer_account=AVI ALTMANN | last_order_date: live=2025-09-03 test=01/30/2026
    customer_account=1457 | last_order_date: live=2026-01-12 test=01/14/2026
    customer_account=2593326 | last_order_date: live=2025-09-25 test=N/A
    customer_account=2593326 | po_number: live=TEST263 test=N/A
    customer_account=2593326 | sales_order_number: live=ORD00667425 test=N/A
    customer_account=11560 | last_order_date: live=2026-05-21 test=06/03/2026
    customer_account=5334 | last_order_date: live=2025-07-21 test=04/09/2025
    customer_account=5334 | po_number: live=CBSAMPLES72125 test=SAMPLES4225
    customer_account=5334 | sales_order_number: live=ORD00625635 test=ORD00553447
    customer_account=11027 | last_order_date: live=2025-06-04 test=06/05/2025
    customer_account=11568 | last_order_date: live=2026-04-30 test=05/01/2026
    customer_account=2354986 | last_order_date: live=2026-05-14 test=04/15/2026
    customer_account=2354986 | po_number: live=2305142601 test=2304152601
    customer_account=2354986 | sales_order_number: live=ORD00833298 test=ORD00810691
    customer_account=3183710 | po_number: live=None test=N/A
    customer_account=11030 | last_order_date: live=2025-04-22 test=04/24/2025
    customer_account=6934 | last_order_date: live=2025-05-13 test=05/30/2025
  Soft/cosmetic text diffs (not failing): 4

## Sheet: Integrated [DIFF]
  Row key: customer_account
  Rows live=4 test=4 matched=4
  Patterns:
    - Value diffs by column: last_order_date=3, po_number=2, sales_order_number=2
  Value diffs (7):
    customer_account=7025 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=7025 | po_number: live=74753579 test=73916716
    customer_account=7025 | sales_order_number: live=ORD00884665 test=ORD00883777
    customer_account=2815509 | last_order_date: live=2026-04-10 test=04/14/2026
    customer_account=9206 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=9206 | po_number: live=413968897 test=413891432
    customer_account=9206 | sales_order_number: live=ORD00884639 test=ORD00883785

## Sheet: JWeigand [DIFF]
  Row key: customer_account
  Rows live=7 test=7 matched=7
  Patterns:
    - Value diffs by column: last_order_date=5, po_number=4, sales_order_number=4
  Value diffs (13):
    customer_account=6123 | last_order_date: live=2026-07-15 test=07/06/2026
    customer_account=6123 | po_number: live=7CL486156 test=72kf
    customer_account=6123 | sales_order_number: live=ORD00877419 test=ORD00868169
    customer_account=1412 | last_order_date: live=2026-07-25 test=07/24/2026
    customer_account=1412 | po_number: live=6723916642_1 test=6723693969_2
    customer_account=1412 | sales_order_number: live=ORD00884594 test=ORD00883782
    customer_account=8008 | last_order_date: live=2026-07-10 test=07/17/2026
    customer_account=8008 | po_number: live=8851000 test=8819538
    customer_account=8008 | sales_order_number: live=ORD00873723 test=ORD00846679
    customer_account=9188 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=9188 | po_number: live=8862607 test=8861488
    customer_account=9188 | sales_order_number: live=ORD00884678 test=ORD00883708
    customer_account=5256 | last_order_date: live=2025-04-10 test=05/05/2025
  Soft/cosmetic text diffs (not failing): 7

## Sheet: LCWalker [DIFF]
  Row key: customer_account
  Rows live=5 test=5 matched=5
  Patterns:
    - Value diffs by column: last_order_date=5, po_number=1, sales_order_number=1
  Value diffs (7):
    customer_account=3538 | last_order_date: live=2026-07-01 test=07/16/2026
    customer_account=2942414 | last_order_date: live=2025-01-22 test=02/20/2025
    customer_account=8276 | last_order_date: live=2026-07-16 test=06/01/2026
    customer_account=8276 | po_number: live=071426 test=AML0521
    customer_account=8276 | sales_order_number: live=ORD00878279 test=ORD00838846
    customer_account=11401 | last_order_date: live=2026-01-05 test=02/03/2026
    customer_account=11036 | last_order_date: live=2025-05-01 test=06/30/2025
  Soft/cosmetic text diffs (not failing): 1

## Sheet: MGrego [DIFF]
  Row key: customer_account
  Rows live=178 test=178 matched=178
  Patterns:
    - Value diffs by column: last_order_date=123, sales_order_number=17, po_number=16
  Value diffs (156):
    customer_account=11469 | last_order_date: live=2026-02-11 test=02/20/2026
    customer_account=11509 | last_order_date: live=2026-03-23 test=03/31/2026
    customer_account=11175 | last_order_date: live=2025-08-13 test=08/14/2025
    customer_account=11175 | po_number: live=None test=N/A
    customer_account=3427257 | last_order_date: live=2025-11-12 test=11/19/2025
    customer_account=11319 | last_order_date: live=2025-11-12 test=11/19/2025
    customer_account=3304287 | last_order_date: live=2026-04-06 test=04/13/2026
    customer_account=8047 | last_order_date: live=2025-09-22 test=10/03/2025
    customer_account=6178 | last_order_date: live=2026-04-14 test=04/23/2026
    customer_account=11604 | last_order_date: live=2026-06-15 test=06/22/2026
    customer_account=AA STORE INC | last_order_date: live=2025-02-10 test=04/30/2025
    customer_account=11042 | last_order_date: live=2026-04-06 test=04/13/2026
    customer_account=11053 | last_order_date: live=2025-05-14 test=05/21/2025
    customer_account=181 | last_order_date: live=2026-01-12 test=01/16/2026
    customer_account=11585 | last_order_date: live=2026-05-20 test=05/29/2026
    customer_account=3282071 | last_order_date: live=2026-05-06 test=05/12/2026
    customer_account=3053627 | last_order_date: live=2026-07-21 test=04/24/2026
    customer_account=3053627 | po_number: live=3007212601 test=3004162601
    customer_account=3053627 | sales_order_number: live=ORD00881572 test=ORD00811588
    customer_account=368 | last_order_date: live=2025-11-13 test=11/25/2025
    customer_account=11016 | last_order_date: live=2025-04-07 test=08/26/2025
    customer_account=11016 | po_number: live=BD472025 test=UNPAID RETURN
    customer_account=11016 | sales_order_number: live=ORD00556950 test=ORD00608643
    customer_account=Big Empire | last_order_date: live=2025-01-29 test=03/05/2025
    customer_account=11580 | last_order_date: live=2026-05-14 test=05/25/2026
    customer_account=1081 | last_order_date: live=2025-02-18 test=04/28/2025
    customer_account=516 | last_order_date: live=2026-02-03 test=02/09/2026
    customer_account=5358 | last_order_date: live=2025-03-03 test=05/01/2025
    customer_account=3005878 | last_order_date: live=2026-04-24 test=04/27/2026
    customer_account=6475 | last_order_date: live=2026-02-25 test=N/A
    customer_account=6475 | po_number: live=6402252601 test=N/A
    customer_account=6475 | sales_order_number: live=ORD00769642 test=N/A
    customer_account=DREISER DISCOUNT | last_order_date: live=2025-05-21 test=06/09/2025
    customer_account=3238687 | last_order_date: live=2026-05-13 test=05/21/2026
    customer_account=3382042 | last_order_date: live=2026-05-06 test=05/19/2026
    customer_account=11346 | last_order_date: live=2025-11-20 test=N/A
    customer_account=11346 | po_number: live=0011202501 test=N/A
    customer_account=11346 | sales_order_number: live=ORD00711310 test=N/A
    customer_account=3351105 | last_order_date: live=N/A test=01/30/2025
    customer_account=3351105 | sales_order_number: live=N/A test=TR-4275
    customer_account=11539 | last_order_date: live=2026-06-19 test=04/23/2026
    customer_account=11539 | po_number: live=0006192601 test=0004172601
    customer_account=11539 | sales_order_number: live=ORD00858996 test=ORD00812412
    customer_account=11541 | last_order_date: live=2026-04-15 test=04/23/2026
    customer_account=3406999 | last_order_date: live=2025-11-12 test=04/21/2025
    customer_account=3406999 | po_number: live=3411122501 test=DZG41625
    customer_account=3406999 | sales_order_number: live=ORD00703896 test=ORD00562883
    customer_account=3241807 | last_order_date: live=2026-07-08 test=07/10/2026
    customer_account=2983818 | last_order_date: live=2026-05-08 test=05/14/2026
    customer_account=8130 | last_order_date: live=2026-04-28 test=04/30/2026
    ... +106 more
  Soft/cosmetic text diffs (not failing): 31

## Sheet: MKolko [DIFF]
  Row key: customer_account
  Rows live=167 test=167 matched=167
  Patterns:
    - Value diffs by column: last_order_date=138, sales_order_number=16, po_number=15
  Value diffs (169):
    customer_account=936 | last_order_date: live=2025-09-02 test=09/11/2025
    customer_account=1567 | last_order_date: live=2026-07-16 test=07/17/2026
    customer_account=9079 | last_order_date: live=2026-06-02 test=06/04/2026
    customer_account=5507 | last_order_date: live=2026-07-22 test=05/29/2026
    customer_account=5507 | po_number: live=5507222601 test=5505152601
    customer_account=5507 | sales_order_number: live=ORD00882399 test=ORD00833840
    customer_account=9467 | last_order_date: live=2026-02-19 test=02/27/2026
    customer_account=5503 | last_order_date: live=2025-01-31 test=03/04/2025
    customer_account=11621 | last_order_date: live=2026-07-14 test=07/16/2026
    customer_account=6240 | last_order_date: live=2026-06-22 test=06/29/2026
    customer_account=3050 | last_order_date: live=2026-07-07 test=07/06/2026
    customer_account=3050 | po_number: live=361306 test=361195
    customer_account=3050 | sales_order_number: live=ORD00871770 test=ORD00867512
    customer_account=308 | last_order_date: live=2026-06-30 test=07/02/2026
    customer_account=11100 | last_order_date: live=2026-04-13 test=04/22/2026
    customer_account=6326 | last_order_date: live=2026-04-27 test=04/30/2026
    customer_account=11019 | last_order_date: live=2025-04-10 test=04/22/2025
    customer_account=6700 | last_order_date: live=2026-05-06 test=05/14/2026
    customer_account=6213 | last_order_date: live=2026-05-11 test=05/18/2026
    customer_account=2874972 | last_order_date: live=2026-05-11 test=05/18/2026
    customer_account=175 | last_order_date: live=2026-07-20 test=06/19/2026
    customer_account=175 | po_number: live=150085 test=149552
    customer_account=175 | sales_order_number: live=ORD00880924 test=ORD00856209
    customer_account=8284 | last_order_date: live=2026-05-04 test=05/15/2026
    customer_account=6646 | last_order_date: live=2026-01-05 test=01/08/2026
    customer_account=6521 | last_order_date: live=2026-05-04 test=05/15/2026
    customer_account=6707 | last_order_date: live=2026-05-04 test=05/15/2026
    customer_account=5030 | last_order_date: live=2025-12-08 test=12/11/2025
    customer_account=395 | last_order_date: live=2026-07-08 test=07/09/2026
    customer_account=11057 | last_order_date: live=2026-07-21 test=07/24/2026
    customer_account=418 | last_order_date: live=2026-06-25 test=06/26/2026
    customer_account=6219 | last_order_date: live=2026-07-07 test=07/14/2026
    customer_account=437 | last_order_date: live=2026-04-29 test=05/04/2026
    customer_account=9457 | last_order_date: live=2026-05-19 test=05/27/2026
    customer_account=3506037 | last_order_date: live=2026-07-14 test=07/16/2026
    customer_account=3506037 | po_number: live=3507142603 test=3507142602
    customer_account=3506037 | sales_order_number: live=ORD00876708 test=ORD00876707
    customer_account=2763990 | last_order_date: live=2026-04-23 test=04/24/2026
    customer_account=11616 | last_order_date: live=2026-07-06 test=07/08/2026
    customer_account=3107161 | last_order_date: live=2026-01-22 test=01/27/2026
    customer_account=3250618 | last_order_date: live=2025-08-27 test=08/29/2025
    customer_account=5067 | last_order_date: live=2026-06-24 test=06/30/2026
    customer_account=467 | last_order_date: live=2026-07-15 test=07/16/2026
    customer_account=472 | last_order_date: live=2026-06-17 test=06/18/2026
    customer_account=6312 | last_order_date: live=2026-06-24 test=06/30/2026
    customer_account=4073 | last_order_date: live=2026-07-14 test=07/16/2026
    customer_account=11002 | last_order_date: live=2025-03-20 test=03/24/2025
    customer_account=647 | last_order_date: live=2026-06-17 test=06/23/2026
    customer_account=2743772 | last_order_date: live=2026-06-25 test=06/30/2026
    customer_account=6336 | last_order_date: live=2026-04-13 test=04/21/2026
    ... +119 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: PMazer [DIFF]
  Row key: customer_account
  Rows live=3 test=3 matched=3
  Patterns:
    - Value diffs by column: last_order_date=3
  Value diffs (3):
    customer_account=7186 | last_order_date: live=2026-05-25 test=05/29/2026
    customer_account=7193 | last_order_date: live=2026-07-20 test=07/22/2026
    customer_account=6940 | last_order_date: live=2026-04-15 test=04/30/2026
  Soft/cosmetic text diffs (not failing): 1

## Sheet: REdwards [DIFF]
  Row key: customer_account
  Rows live=3 test=3 matched=3
  Patterns:
    - Value diffs by column: last_order_date=3, po_number=3, sales_order_number=3
  Value diffs (9):
    customer_account=9301 | last_order_date: live=2026-07-20 test=01/20/2026
    customer_account=9301 | po_number: live=8LJWMC1S test=3TEKVG4P
    customer_account=9301 | sales_order_number: live=ORD00880810 test=ORD00726016
    customer_account=9300 | last_order_date: live=2026-07-20 test=07/24/2026
    customer_account=9300 | po_number: live=8QR62KQB test=81H6NZRC
    customer_account=9300 | sales_order_number: live=ORD00880789 test=ORD00880786
    customer_account=9303 | last_order_date: live=2026-07-26 test=07/24/2026
    customer_account=9303 | po_number: live=Pkb6Vtw0S test=PsbCncYmS
    customer_account=9303 | sales_order_number: live=ORD00884672 test=ORD00883786
  Soft/cosmetic text diffs (not failing): 1

## Sheet: Unassigned [DIFF]
  Row key: customer_account
  Rows live=50 test=50 matched=50
  Patterns:
    - Value diffs by column: last_order_date=16, sales_order_number=8, po_number=7
  Value diffs (31):
    customer_account=125th 99 Inc. | last_order_date: live=2025-02-03 test=N/A
    customer_account=125th 99 Inc. | po_number: live=125th992325 test=N/A
    customer_account=125th 99 Inc. | sales_order_number: live=ORD00516214 test=N/A
    customer_account=11205 | last_order_date: live=2025-08-31 test=09/02/2025
    customer_account=11205 | po_number: live=None test=N/A
    customer_account=11528 | last_order_date: live=2026-07-09 test=07/14/2026
    customer_account=11373 | last_order_date: live=2025-12-11 test=12/24/2025
    customer_account=Capacity | last_order_date: live=N/A test=11/20/2025
    customer_account=Capacity | sales_order_number: live=N/A test=TR-4412
    customer_account=11454 | last_order_date: live=2026-01-28 test=01/29/2026
    customer_account=11454 | po_number: live=None test=N/A
    customer_account=11005 | last_order_date: live=N/A test=05/18/2026
    customer_account=11005 | sales_order_number: live=N/A test=TR-4502
    customer_account=11229 | last_order_date: live=2025-09-12 test=09/17/2025
    customer_account=3247048 | last_order_date: live=2025-02-19 test=N/A
    customer_account=3247048 | po_number: live=RYAN21925 test=N/A
    customer_account=3247048 | sales_order_number: live=ORD00524846 test=N/A
    customer_account=11552 | last_order_date: live=2026-04-22 test=N/A
    customer_account=11552 | po_number: live=0004222601 test=N/A
    customer_account=11552 | sales_order_number: live=ORD00816868 test=N/A
    customer_account=7072 | last_order_date: live=2025-07-02 test=07/18/2025
    customer_account=MegaDollarMart | last_order_date: live=2025-02-03 test=N/A
    customer_account=MegaDollarMart | po_number: live=MD2325 test=N/A
    customer_account=MegaDollarMart | sales_order_number: live=ORD00516263 test=N/A
    customer_account=11201 | last_order_date: live=2025-10-06 test=10/17/2025
    customer_account=11239 | last_order_date: live=2026-07-02 test=07/06/2026
    customer_account=11609 | last_order_date: live=2026-06-18 test=N/A
    customer_account=11609 | po_number: live=0006182601 test=N/A
    customer_account=11609 | sales_order_number: live=ORD00858403 test=N/A
    customer_account=3201519 | last_order_date: live=N/A test=03/18/2025
    customer_account=3201519 | sales_order_number: live=N/A test=TR-4365
  Soft/cosmetic text diffs (not failing): 13
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
