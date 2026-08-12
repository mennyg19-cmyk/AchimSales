# Parity: ordered

- Params: `{'period': 'last_month'}`
- Live file: `.scratch\parity\20260805-111000-po-audit-retest\ordered__live.xlsx`
- Test file: `.scratch\parity\20260805-111000-po-audit-retest\ordered__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **138941**
- Missing sheets in /test: (none)
- Extra sheets in /test (ignored): (none)
- Per sheet: Summary=DIFF(8519), By Customer=DIFF(295), By Item=DIFF(4103), By Order=DIFF(46465), By Salesman=DIFF(53), Full Data=DIFF(79506)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260805-111000-po-audit-retest\ordered__live.xlsx vs .scratch\parity\20260805-111000-po-audit-retest\ordered__test.xlsx
Hard differences: 138941
Result: DIFFERENCES FOUND

## Sheet: Summary [DIFF]
  Row key: customer_name, item_number
  Rows live=8928 test=9120 matched=8916
  Extra columns in /test (ignored): qty_left_to_ship, qty_released, qtyreserved
  Missing columns in /test: qtyremainder
  Patterns:
    - 12 live row(s) missing on /test (0% of live rows).
    - 204 /test-only row(s) not on live (2% of /test rows).
    - Value diffs by column: extended_price_remainder=7618, extended_price_ordered=322, qty_ordered=251, net_price=80, salesman_code=27
  Missing in /test (12):
    customer_name=HOMEDEPOT.COM, item_number=BCTU63BU12 (salesman_code=Integrated)
    customer_name=HOMEDEPOT.COM, item_number=BCVL14BU12 (salesman_code=Integrated)
    customer_name=KOHL'S, item_number=DRTV36GC12 (salesman_code=JWeigand)
    customer_name=KOHL'S, item_number=TYPN63TN06 (salesman_code=JWeigand)
    customer_name=WAL-MART STORES, INC.#546978, item_number=BCNAPKSG36 (salesman_code=AGrossman)
    customer_name=WAL-MART STORES, INC.#546978, item_number=BCNAPKTP36 (salesman_code=AGrossman)
    customer_name=WAL-MART STORES, INC.#546978, item_number=MSG2327AL6 (salesman_code=AGrossman)
    customer_name=WAYFAIR LLC (DS), item_number=FTVMA45045 (salesman_code=HKaufman)
    customer_name=WAYFAIR LLC (DS), item_number=FTVSO10220 (salesman_code=HKaufman)
    customer_name=WAYFAIR LLC (DS), item_number=STT1M40220 (salesman_code=HKaufman)
    customer_name=WAYFAIR LLC (DS), item_number=WIPN84WH06 (salesman_code=HKaufman)
    customer_name=GRAND TOTAL, item_number= (salesman_code=None)
  Extra in /test only (204):
    customer_name=OJ COMMERCE, item_number=FTVMA45545 (salesman_code=AGrossman)
    customer_name=WAL-MART STORES, INC.#546978, item_number=MSG2287WH6 (salesman_code=AGrossman)
    customer_name=WAYFAIR LLC (DS), item_number=DR54X72TN6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2704WH4 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG272WH04 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=PVVRBWHT02 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=PVVPLWHT02 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG272AL04 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG245WH04 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG228WH06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2237AL6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG232GY06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2354BK6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG225WH06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG222WH06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG22342W6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG224WD06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2334WH6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2344WH6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG236WH06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG232WD06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG231WH06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG241WH04 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG248AL04 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2247WH6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG233AL06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=TRS736WH06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=123CO36B24 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG270AL04 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=GLCS24RD12 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2347WH6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2337WH6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2327AL6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG235WH06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2327WH6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2357AL6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG236AL06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG229AL06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2364AL6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=SOCO36GY06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=CPS376CO12 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2237BK6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2347BK6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2367WH6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2367AL6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2294WH6 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=TRL376WH12 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG230BK06 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=RDMCAR4806 (salesman_code=HKaufman)
    customer_name=CHANNEL MARKETING, LLC, item_number=MSG2277GY6 (salesman_code=HKaufman)
    ... +154 more
  Value diffs (8302):
    customer_name=16th Avenue Home Center Inc., item_number=123CO36B24 | extended_price_remainder: live=242.4000 test=0
    customer_name=16th Avenue Home Center Inc., item_number=123CO36W24 | extended_price_remainder: live=338.4000 test=0
    customer_name=16th Avenue Home Center Inc., item_number=123CO48W24 | extended_price_remainder: live=300 test=0
    customer_name=16th Avenue Home Center Inc., item_number=55-2PL0001 | extended_price_remainder: live=33.6000 test=0
    customer_name=16th Avenue Home Center Inc., item_number=MSG2347WH6 | extended_price_remainder: live=48 test=0
    customer_name=16th Avenue Home Center Inc., item_number=MSG2357AL6 | extended_price_remainder: live=48 test=0
    customer_name=16th Avenue Home Center Inc., item_number=OPR376WH36 | extended_price_remainder: live=135 test=0
    customer_name=210 Food Inc., item_number=FTVMA42220 | extended_price_remainder: live=112.2000 test=0
    customer_name=210 Food Inc., item_number=FTVSO10320 | extended_price_remainder: live=112.2000 test=0
    customer_name=210 Food Inc., item_number=FTVWD23020 | extended_price_remainder: live=112.2000 test=0
    customer_name=210 Food Inc., item_number=MSG223BK06 | extended_price_remainder: live=31.3800 test=0
    customer_name=210 Food Inc., item_number=MSG224BK06 | extended_price_remainder: live=32.5800 test=0
    customer_name=210 Food Inc., item_number=MSG224WH06 | extended_price_remainder: live=32.5800 test=0
    customer_name=210 Food Inc., item_number=MSG225WH06 | extended_price_remainder: live=34.0200 test=0
    customer_name=210 Food Inc., item_number=MSG226WH06 | extended_price_remainder: live=35.2200 test=0
    customer_name=210 Food Inc., item_number=MSG227AL06 | extended_price_remainder: live=36.6600 test=0
    customer_name=210 Food Inc., item_number=MSG227BK06 | extended_price_remainder: live=36.6600 test=0
    customer_name=210 Food Inc., item_number=MSG2287WH6 | extended_price_remainder: live=42.7800 test=0
    customer_name=210 Food Inc., item_number=MSG228AL06 | extended_price_remainder: live=38.1600 test=0
    customer_name=210 Food Inc., item_number=MSG2297WH6 | extended_price_remainder: live=44.1600 test=0
    customer_name=210 Food Inc., item_number=MSG229AL06 | extended_price_remainder: live=39.3600 test=0
    customer_name=210 Food Inc., item_number=MSG229BK06 | extended_price_remainder: live=39.3600 test=0
    customer_name=210 Food Inc., item_number=MSG230AL06 | extended_price_remainder: live=40.7400 test=0
    customer_name=210 Food Inc., item_number=MSG230BK06 | extended_price_remainder: live=40.7400 test=0
    customer_name=210 Food Inc., item_number=MSG230WH06 | extended_price_remainder: live=40.7400 test=0
    customer_name=210 Food Inc., item_number=MSG231AL06 | extended_price_remainder: live=42.1200 test=0
    customer_name=210 Food Inc., item_number=MSG231BK06 | extended_price_remainder: live=42.1200 test=0
    customer_name=210 Food Inc., item_number=MSG232BK06 | extended_price_remainder: live=43.5000 test=0
    customer_name=210 Food Inc., item_number=MSG232WH06 | extended_price_remainder: live=43.5000 test=0
    customer_name=210 Food Inc., item_number=MSG2337WH6 | extended_price_remainder: live=50.0400 test=0
    customer_name=210 Food Inc., item_number=MSG233AL06 | extended_price_remainder: live=44.8800 test=0
    customer_name=210 Food Inc., item_number=MSG233BK06 | extended_price_remainder: live=44.8800 test=0
    customer_name=210 Food Inc., item_number=MSG234AL06 | extended_price_remainder: live=46.2600 test=0
    customer_name=210 Food Inc., item_number=MSG234BK06 | extended_price_remainder: live=46.2600 test=0
    customer_name=210 Food Inc., item_number=MSG234WH06 | extended_price_remainder: live=46.2600 test=0
    customer_name=210 Food Inc., item_number=MSG235AL06 | extended_price_remainder: live=47.6400 test=0
    customer_name=210 Food Inc., item_number=MSG235BK06 | extended_price_remainder: live=47.6400 test=0
    customer_name=210 Food Inc., item_number=MSG235WH06 | extended_price_remainder: live=47.6400 test=0
    customer_name=210 Food Inc., item_number=MSG236WH06 | extended_price_remainder: live=49.0200 test=0
    customer_name=210 Food Inc., item_number=MSG237WH04 | extended_price_remainder: live=34.6000 test=0
    customer_name=210 Food Inc., item_number=MSG238WH04 | extended_price_remainder: live=35.5200 test=0
    customer_name=210 Food Inc., item_number=MSG239WH04 | extended_price_remainder: live=36.4400 test=0
    customer_name=210 Food Inc., item_number=TRL376BK12 | extended_price_remainder: live=59.4000 test=0
    customer_name=210 Food Inc., item_number=TRL376WH12 | extended_price_remainder: live=59.4000 test=0
    customer_name=210 Food Inc., item_number=TRL556BK12 | extended_price_remainder: live=91.0800 test=0
    customer_name=210 Food Inc., item_number=TRL556WH12 | extended_price_remainder: live=91.0800 test=0
    customer_name=210 Food Inc., item_number=TRL736BK06 | extended_price_remainder: live=60.0600 test=0
    customer_name=3 Brothers Hardware, item_number=163-2PL001 | extended_price_remainder: live=38.8800 test=0
    customer_name=3 Brothers Hardware, item_number=200-0-PK24 | extended_price_remainder: live=25.9200 test=0
    customer_name=3 Brothers Hardware, item_number=205-0-PK48 | extended_price_remainder: live=47.5200 test=0
    ... +8252 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: By Customer [DIFF]
  Row key: customer_account, salesman_code
  Rows live=139 test=144 matched=137
  Extra columns in /test (ignored): qty_left_to_ship, qtyreserved
  Missing columns in /test: fulfillment, qty_open, qty_shipped, shipped_dollars
  Patterns:
    - 2 live row(s) missing on /test (1% of live rows).
    - 7 /test-only row(s) not on live (5% of /test rows).
    - Value diffs by column: qty_released=118, released_dollars=115, ordered_dollars=17, open_dollars=12, qty_ordered=12
  Missing in /test (2):
    customer_account=11239, salesman_code= (customer_name=Sophie)
    customer_account=11528, salesman_code= (customer_name=All Pro Building Supplies LLC)
  Extra in /test only (7):
    customer_account=11239, salesman_code=11239 (customer_name=Sophie)
    customer_account=11528, salesman_code=11528 (customer_name=All Pro Building Supplies LLC)
    customer_account=ROCHDALE OUTLET DEPA, salesman_code=MGrego (customer_name=RVO-ROCHDALE OUTLET DEPT.STORE (RVO))
    customer_account=308, salesman_code=MKolko (customer_name=AJ HOUSEWARES DBA BEST BUYS)
    customer_account=2854, salesman_code=MKolko (customer_name=Wilhelm's Houseware)
    customer_account=11247, salesman_code=MKolko (customer_name=Value Queen (MAX DEALS))
    customer_account=Grand total, salesman_code= (customer_name=None)
  Value diffs (282):
    customer_account=11015, salesman_code=MGrego | qty_released: live=0 test=284
    customer_account=11015, salesman_code=MGrego | released_dollars: live=0 test=1595.6500
    customer_account=11057, salesman_code=MKolko | qty_released: live=0 test=275
    customer_account=11057, salesman_code=MKolko | released_dollars: live=0 test=2114
    customer_account=11184, salesman_code=AGrossman | qty_released: live=0 test=966
    customer_account=11184, salesman_code=AGrossman | released_dollars: live=0 test=3477.6000
    customer_account=11190, salesman_code=MKolko | qty_released: live=0 test=637
    customer_account=11190, salesman_code=MKolko | released_dollars: live=0 test=2870.6600
    customer_account=11616, salesman_code=MKolko | qty_released: live=0 test=251
    customer_account=11616, salesman_code=MKolko | released_dollars: live=0 test=1401
    customer_account=11621, salesman_code=MKolko | qty_released: live=0 test=344
    customer_account=11621, salesman_code=MKolko | released_dollars: live=0 test=1937
    customer_account=11622, salesman_code=MGrego | qty_released: live=0 test=130
    customer_account=11622, salesman_code=MGrego | released_dollars: live=0 test=1198.1600
    customer_account=11624, salesman_code=AGrossman | qty_released: live=0 test=138
    customer_account=11624, salesman_code=AGrossman | released_dollars: live=0 test=1001.8800
    customer_account=11628, salesman_code=MKolko | qty_released: live=0 test=239
    customer_account=11628, salesman_code=MKolko | released_dollars: live=0 test=1838
    customer_account=11630, salesman_code=MGrego | qty_released: live=0 test=200
    customer_account=11630, salesman_code=MGrego | released_dollars: live=0 test=1300
    customer_account=11643, salesman_code=House | qty_released: live=0 test=3
    customer_account=11643, salesman_code=House | released_dollars: live=0 test=18
    customer_account=123456789, salesman_code=House | qty_released: live=0 test=40
    customer_account=123456789, salesman_code=House | released_dollars: live=0 test=88
    customer_account=1049, salesman_code=BLevin | qty_released: live=0 test=412
    customer_account=1049, salesman_code=BLevin | released_dollars: live=0 test=3334.6800
    customer_account=1063, salesman_code=BLevin | qty_released: live=0 test=264
    customer_account=1063, salesman_code=BLevin | released_dollars: live=0 test=2206.5000
    customer_account=1109, salesman_code=BLevin | qty_released: live=0 test=40
    customer_account=1109, salesman_code=BLevin | released_dollars: live=0 test=490
    customer_account=1364, salesman_code=MKolko | qty_released: live=0 test=394
    customer_account=1364, salesman_code=MKolko | released_dollars: live=0 test=2087
    customer_account=1412, salesman_code=JWeigand | open_dollars: live=0 test=-3128.6700
    customer_account=1412, salesman_code=JWeigand | ordered_dollars: live=19981.6700 test=16625.9500
    customer_account=1412, salesman_code=JWeigand | qty_ordered: live=1932 test=1591
    customer_account=1412, salesman_code=JWeigand | qty_released: live=0 test=1904
    customer_account=1412, salesman_code=JWeigand | released_dollars: live=0 test=19726.6300
    customer_account=1493, salesman_code=MKolko | qty_released: live=0 test=488
    customer_account=1493, salesman_code=MKolko | released_dollars: live=0 test=2651
    customer_account=1567, salesman_code=MKolko | qty_released: live=0 test=264
    customer_account=1567, salesman_code=MKolko | released_dollars: live=0 test=1145.4000
    customer_account=1674, salesman_code=BLevin | qty_released: live=24 test=86
    customer_account=1674, salesman_code=BLevin | released_dollars: live=190.8000 test=601.4000
    customer_account=1724, salesman_code=BLevin | qty_released: live=1346 test=4154
    customer_account=1724, salesman_code=BLevin | released_dollars: live=5000.9800 test=30810.7800
    customer_account=175, salesman_code=MKolko | qty_released: live=0 test=252
    customer_account=175, salesman_code=MKolko | released_dollars: live=0 test=1844.4600
    customer_account=1841, salesman_code=MKolko | qty_released: live=0 test=353
    customer_account=1841, salesman_code=MKolko | released_dollars: live=0 test=2108.1600
    customer_account=1940, salesman_code=HKaufman | qty_released: live=0 test=192
    ... +232 more

## Sheet: By Item [DIFF]
  Row key: item_number
  Rows live=1815 test=1835 matched=1813
  Extra columns in /test (ignored): qty_left_to_ship, qtyreserved
  Missing columns in /test: fulfillment, qty_open, qty_shipped, shipped_dollars
  Patterns:
    - 2 live row(s) missing on /test (0% of live rows).
    - 22 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: qty_released=1525, released_dollars=1503, ordered_dollars=417, qty_ordered=339, open_dollars=281
  Missing in /test (2):
    item_number=BCNAPKSG36
    item_number=BCNAPKTP36
  Extra in /test only (22):
    item_number=ANFTMCOZ06
    item_number=BCVL14BW06
    item_number=RM1830CP06
    item_number=GBTV36MU06
    item_number=BCTR36BW06
    item_number=ANFTMLMD06
    item_number=ANFTMBOH06
    item_number=ANFTMBES06
    item_number=GLCS24RD12
    item_number=KEVL14BL06
    item_number=ENTS36GL04
    item_number=ANFTMCFE06
    item_number=AF1830TN06
    item_number=DRTV36GW04
    item_number=ARTV36TN12
    item_number=AF2039GY06
    item_number=LATV36GY04
    item_number=RM1830WE06
    item_number=AF1830BK06
    item_number=CPS376CO12
    item_number=BOPN63SV06
    item_number=RDBHDN6606
  Value diffs (4075):
    item_number=1/4HxH-015 | qty_released: live=0 test=3400
    item_number=1/4HxH-015 | released_dollars: live=0 test=5202
    item_number=1/4HxH-020 | qty_released: live=0 test=2700
    item_number=1/4HxH-020 | released_dollars: live=0 test=6588
    item_number=1/4HxH-030 | qty_released: live=0 test=1975
    item_number=1/4HxH-030 | released_dollars: live=0 test=14457
    item_number=1/4HxH-040 | qty_released: live=0 test=220
    item_number=1/4HxH-040 | released_dollars: live=0 test=2952.4000
    item_number=1/8HxH-015 | qty_released: live=0 test=499
    item_number=1/8HxH-015 | released_dollars: live=0 test=848.3000
    item_number=1/8HxH-020 | qty_released: live=0 test=1400
    item_number=1/8HxH-020 | released_dollars: live=0 test=2996
    item_number=1/8HxH-030 | qty_released: live=0 test=1350
    item_number=1/8HxH-030 | released_dollars: live=0 test=10746
    item_number=1/8HxH-040 | qty_released: live=0 test=75
    item_number=1/8HxH-040 | released_dollars: live=0 test=915
    item_number=1/8HxS-020 | qty_released: live=0 test=1900
    item_number=1/8HxS-020 | released_dollars: live=0 test=4066
    item_number=1/8HxS-030 | qty_released: live=0 test=1375
    item_number=1/8HxS-030 | released_dollars: live=0 test=10422.5000
    item_number=1/8HxS-040 | qty_released: live=0 test=54
    item_number=1/8HxS-040 | released_dollars: live=0 test=527.0400
    item_number=123CO36B24 | open_dollars: live=140.1600 test=134.3500
    item_number=123CO36B24 | ordered_dollars: live=1066.5500 test=1060.7400
    item_number=123CO36B24 | qty_released: live=0 test=150
    item_number=123CO36B24 | released_dollars: live=0 test=926.3900
    item_number=123CO36W24 | qty_released: live=0 test=1175
    item_number=123CO36W24 | released_dollars: live=0 test=5732.1900
    item_number=123CO48B24 | qty_released: live=0 test=57
    item_number=123CO48B24 | released_dollars: live=0 test=457.7700
    item_number=123CO48L24 | qty_released: live=0 test=24
    item_number=123CO48L24 | released_dollars: live=0 test=262.0400
    item_number=123CO48W24 | qty_released: live=0 test=408
    item_number=123CO48W24 | released_dollars: live=0 test=2615.6000
    item_number=163-2PL001 | qty_released: live=48 test=49
    item_number=200-0-PK24 | qty_released: live=24 test=248
    item_number=200-0-PK24 | released_dollars: live=25.9200 test=494.6400
    item_number=205-0-PK48 | open_dollars: live=93.6000 test=71.9500
    item_number=205-0-PK48 | ordered_dollars: live=1586.5900 test=1564.9400
    item_number=205-0-PK48 | qty_ordered: live=1354 test=1349
    item_number=205-0-PK48 | qty_released: live=192 test=1306
    item_number=205-0-PK48 | released_dollars: live=198.7200 test=1492.9900
    item_number=210-0-PK24 | ordered_dollars: live=696.3600 test=690.7700
    item_number=210-0-PK24 | qty_ordered: live=342 test=341
    item_number=210-0-PK24 | qty_released: live=48 test=293
    item_number=210-0-PK24 | released_dollars: live=140.6400 test=581.0900
    item_number=215-0-PK12 | qty_released: live=12 test=70
    item_number=215-0-PK12 | released_dollars: live=55.9200 test=546.3300
    item_number=220-0-PK24 | qty_released: live=24 test=52
    item_number=220-0-PK24 | released_dollars: live=23.7600 test=132.5900
    ... +4025 more
  Soft/cosmetic text diffs (not failing): 51

## Sheet: By Order [DIFF]
  Row key: sales_order_number
  Rows live=21388 test=21339 matched=21214
  Extra columns in /test (ignored): customer_name, order_status, qty_left_to_ship, qtyreserved, status
  Missing columns in /test: fulfillment, qty_open, qty_shipped, salesordername, shipped_dollars
  Patterns:
    - 174 live row(s) missing on /test (1% of live rows).
    - Common denominator (missing on /test): 174/174 rows share date 2026-07-01.
    - Date breakdown (missing on /test): 2026-07-01=174
    - 125 /test-only row(s) not on live (1% of /test rows).
    - Common denominator (extra on /test): 103/124 rows share date 2026-07-31.
    - Top dates (extra on /test): 2026-07-31=103, 2026-07-28=7, 2026-07-27=3, 2026-07-02=3, 2026-07-10=2
    - Value diffs by column: qty_released=20965, released_dollars=20958, order_date=4196, open_dollars=17, ordered_dollars=13
    - Top dates (value-diff rows): 2026-07-14=1993, 2026-07-13=1872, 2026-07-06=1868, 2026-07-20=1783, 2026-07-09=1630
  Missing in /test (174):
    sales_order_number=ORD00866999 (order_date=2026-07-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00867000 (order_date=2026-07-01, customer_account=9022, salesman_code=AGrossman)
    sales_order_number=ORD00867001 (order_date=2026-07-01, customer_account=9022, salesman_code=AGrossman)
    sales_order_number=ORD00867002 (order_date=2026-07-01, customer_account=9022, salesman_code=AGrossman)
    sales_order_number=ORD00867003 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867004 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867005 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867006 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867007 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867008 (order_date=2026-07-01, customer_account=9206, salesman_code=Integrated)
    sales_order_number=ORD00867009 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867010 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867011 (order_date=2026-07-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00867012 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867013 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867014 (order_date=2026-07-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00867015 (order_date=2026-07-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00867016 (order_date=2026-07-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00867017 (order_date=2026-07-01, customer_account=9022, salesman_code=AGrossman)
    sales_order_number=ORD00867018 (order_date=2026-07-01, customer_account=9022, salesman_code=AGrossman)
    sales_order_number=ORD00867019 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867020 (order_date=2026-07-01, customer_account=9206, salesman_code=Integrated)
    sales_order_number=ORD00867021 (order_date=2026-07-01, customer_account=9206, salesman_code=Integrated)
    sales_order_number=ORD00867022 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867023 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867024 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867025 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867026 (order_date=2026-07-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00867027 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867028 (order_date=2026-07-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00867029 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867030 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867031 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867032 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867033 (order_date=2026-07-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00867034 (order_date=2026-07-01, customer_account=8015, salesman_code=HKaufman)
    sales_order_number=ORD00867035 (order_date=2026-07-01, customer_account=1412, salesman_code=JWeigand)
    sales_order_number=ORD00867036 (order_date=2026-07-01, customer_account=1412, salesman_code=JWeigand)
    sales_order_number=ORD00867037 (order_date=2026-07-01, customer_account=1412, salesman_code=JWeigand)
    sales_order_number=ORD00867038 (order_date=2026-07-01, customer_account=9206, salesman_code=Integrated)
    sales_order_number=ORD00867039 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867040 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867041 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867042 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867043 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867044 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867045 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867046 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867047 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00867048 (order_date=2026-07-01, customer_account=9303, salesman_code=REdwards)
    ... +124 more
  Extra in /test only (125):
    sales_order_number=ORD00888517 (order_date=2026-07-31, customer_account=9091, customer_name=OJ COMMERCE)
    sales_order_number=ORD00888513 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888512 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888509 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888508 (order_date=2026-07-31, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00888506 (order_date=2026-07-31, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00888475 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888470 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888469 (order_date=2026-07-31, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00888462 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888457 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888456 (order_date=2026-07-31, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00888451 (order_date=2026-07-31, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00888448 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888447 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888446 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888445 (order_date=2026-07-31, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00888444 (order_date=2026-07-31, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00888434 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888428 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888427 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888421 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888420 (order_date=2026-07-31, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00888504 (order_date=2026-07-31, customer_account=8015, customer_name=WAYFAIR LLC (DS))
    sales_order_number=ORD00886819 (order_date=2026-07-29, customer_account=4105, customer_name=CHANNEL MARKETING, LLC)
    sales_order_number=ORD00885496 (order_date=2026-07-27, customer_account=4105, customer_name=CHANNEL MARKETING, LLC)
    sales_order_number=ORD00885462 (order_date=2026-07-27, customer_account=4105, customer_name=CHANNEL MARKETING, LLC)
    sales_order_number=ORD00885427 (order_date=2026-07-27, customer_account=4105, customer_name=CHANNEL MARKETING, LLC)
    sales_order_number=ORD00868376 (order_date=2026-07-02, customer_account=4105, customer_name=CHANNEL MARKETING, LLC)
    sales_order_number=ORD00868340 (order_date=2026-07-02, customer_account=4105, customer_name=CHANNEL MARKETING, LLC)
    sales_order_number=ORD00888515 (order_date=2026-07-31, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    sales_order_number=ORD00888510 (order_date=2026-07-31, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    sales_order_number=ORD00888507 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888505 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888502 (order_date=2026-07-31, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    sales_order_number=ORD00888501 (order_date=2026-07-31, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    sales_order_number=ORD00888500 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888499 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888498 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888497 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888496 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888495 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888490 (order_date=2026-07-31, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    sales_order_number=ORD00888489 (order_date=2026-07-31, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    sales_order_number=ORD00888488 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888483 (order_date=2026-07-31, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    sales_order_number=ORD00888481 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888480 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888479 (order_date=2026-07-31, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00888476 (order_date=2026-07-31, customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
    ... +75 more
  Value diffs (46161):
    sales_order_number=ORD00867173 | qty_released: live=0 test=1
    sales_order_number=ORD00867173 | released_dollars: live=0 test=8.2200
    sales_order_number=ORD00867174 | qty_released: live=0 test=2
    sales_order_number=ORD00867174 | released_dollars: live=0 test=18.6600
    sales_order_number=ORD00867175 | qty_released: live=0 test=2
    sales_order_number=ORD00867175 | released_dollars: live=0 test=25.2600
    sales_order_number=ORD00867176 | qty_released: live=0 test=2
    sales_order_number=ORD00867176 | released_dollars: live=0 test=22
    sales_order_number=ORD00867177 | qty_released: live=0 test=2
    sales_order_number=ORD00867177 | released_dollars: live=0 test=25.8800
    sales_order_number=ORD00867178 | qty_released: live=0 test=2
    sales_order_number=ORD00867178 | released_dollars: live=0 test=22.0800
    sales_order_number=ORD00867179 | qty_released: live=0 test=3
    sales_order_number=ORD00867179 | released_dollars: live=0 test=28.8900
    sales_order_number=ORD00867180 | qty_released: live=0 test=1
    sales_order_number=ORD00867180 | released_dollars: live=0 test=17.1000
    sales_order_number=ORD00867181 | qty_released: live=0 test=2
    sales_order_number=ORD00867181 | released_dollars: live=0 test=29.1000
    sales_order_number=ORD00867182 | qty_released: live=0 test=1
    sales_order_number=ORD00867182 | released_dollars: live=0 test=21.9900
    sales_order_number=ORD00867183 | qty_released: live=0 test=1
    sales_order_number=ORD00867183 | released_dollars: live=0 test=8.8000
    sales_order_number=ORD00867184 | qty_released: live=0 test=1
    sales_order_number=ORD00867184 | released_dollars: live=0 test=17.2900
    sales_order_number=ORD00867185 | qty_released: live=0 test=1
    sales_order_number=ORD00867185 | released_dollars: live=0 test=40.9500
    sales_order_number=ORD00867186 | qty_released: live=0 test=2
    sales_order_number=ORD00867186 | released_dollars: live=0 test=28.6700
    sales_order_number=ORD00867187 | qty_released: live=0 test=1
    sales_order_number=ORD00867187 | released_dollars: live=0 test=12.9400
    sales_order_number=ORD00867188 | qty_released: live=0 test=2
    sales_order_number=ORD00867188 | released_dollars: live=0 test=19.2300
    sales_order_number=ORD00867189 | qty_released: live=0 test=3
    sales_order_number=ORD00867189 | released_dollars: live=0 test=26.4000
    sales_order_number=ORD00867190 | qty_released: live=0 test=1
    sales_order_number=ORD00867190 | released_dollars: live=0 test=9.2400
    sales_order_number=ORD00867191 | qty_released: live=0 test=1
    sales_order_number=ORD00867191 | released_dollars: live=0 test=19.4800
    sales_order_number=ORD00867192 | qty_released: live=0 test=2
    sales_order_number=ORD00867192 | released_dollars: live=0 test=27.2800
    sales_order_number=ORD00867193 | qty_released: live=0 test=1
    sales_order_number=ORD00867193 | released_dollars: live=0 test=7.5000
    sales_order_number=ORD00867194 | qty_released: live=0 test=1
    sales_order_number=ORD00867194 | released_dollars: live=0 test=11.2200
    sales_order_number=ORD00867195 | qty_released: live=0 test=1
    sales_order_number=ORD00867195 | released_dollars: live=0 test=8.6400
    sales_order_number=ORD00867196 | qty_released: live=0 test=1
    sales_order_number=ORD00867196 | released_dollars: live=0 test=7.4300
    sales_order_number=ORD00867197 | qty_released: live=0 test=1
    sales_order_number=ORD00867197 | released_dollars: live=0 test=10.5900
    ... +46111 more

## Sheet: By Salesman [DIFF]
  Row key: salesman_code
  Rows live=11 test=13 matched=11
  Extra columns in /test (ignored): qty_left_to_ship, qtyreserved
  Missing columns in /test: fulfillment, qty_open, qty_shipped, shipped_dollars
  Patterns:
    - 2 /test-only row(s) not on live (15% of /test rows).
    - Value diffs by column: qty_released=11, released_dollars=11, ordered_dollars=7, qty_ordered=7, open_dollars=5
  Extra in /test only (2):
    salesman_code=11528
    salesman_code=11239
  Value diffs (47):
    salesman_code=AGrossman | open_dollars: live=18360 test=-57471.4300
    salesman_code=AGrossman | ordered_dollars: live=365223.6200 test=289160.2800
    salesman_code=AGrossman | qty_ordered: live=51735 test=51708
    salesman_code=AGrossman | qty_released: live=13830 test=37932
    salesman_code=AGrossman | released_dollars: live=86151.1400 test=297137.6800
    salesman_code=BLevin | qty_released: live=1418 test=7121
    salesman_code=BLevin | released_dollars: live=5582.9800 test=59395.5200
    salesman_code=HKaufman | cancelled_dollars: live=352345.3300 test=352543.6300
    salesman_code=HKaufman | open_dollars: live=95970.2400 test=92428.9300
    salesman_code=HKaufman | ordered_dollars: live=658965.2500 test=655347.6300
    salesman_code=HKaufman | qty_cancelled: live=44691 test=44729
    salesman_code=HKaufman | qty_ordered: live=104328 test=104310
    salesman_code=HKaufman | qty_released: live=18742 test=42529
    salesman_code=HKaufman | released_dollars: live=54123.0800 test=210375.0700
    salesman_code=House | qty_released: live=0 test=72
    salesman_code=House | released_dollars: live=0 test=132
    salesman_code=Integrated | cancelled_dollars: live=1019.1200 test=1138.5200
    salesman_code=Integrated | open_dollars: live=238.8000 test=119.4000
    salesman_code=Integrated | ordered_dollars: live=369565.5200 test=367831.6200
    salesman_code=Integrated | qty_cancelled: live=87 test=90
    salesman_code=Integrated | qty_ordered: live=23607 test=23559
    salesman_code=Integrated | qty_released: live=72 test=23466
    salesman_code=Integrated | released_dollars: live=667.4400 test=366573.7000
    salesman_code=JWeigand | open_dollars: live=10877.3000 test=7748.6300
    salesman_code=JWeigand | ordered_dollars: live=38302.6300 test=34946.9100
    salesman_code=JWeigand | qty_ordered: live=3232 test=2891
    salesman_code=JWeigand | qty_released: live=60 test=2486
    salesman_code=JWeigand | released_dollars: live=418.8000 test=26479.8100
    salesman_code=LCWalker | qty_released: live=0 test=1536
    salesman_code=LCWalker | released_dollars: live=0 test=18521.1000
    salesman_code=MGrego | cancelled_dollars: live=4667.6000 test=4704.2600
    salesman_code=MGrego | ordered_dollars: live=25813.1600 test=25936.8200
    salesman_code=MGrego | qty_cancelled: live=649 test=655
    salesman_code=MGrego | qty_ordered: live=4173 test=4191
    salesman_code=MGrego | qty_released: live=1566 test=3472
    salesman_code=MGrego | released_dollars: live=8400.7100 test=20770.9800
    salesman_code=MKolko | open_dollars: live=2922.4400 test=-1735.3700
    salesman_code=MKolko | ordered_dollars: live=159402.6200 test=155858.8100
    salesman_code=MKolko | qty_ordered: live=23718 test=23434
    salesman_code=MKolko | qty_released: live=0 test=18823
    salesman_code=MKolko | released_dollars: live=0 test=127488.9200
    salesman_code=PMazer | qty_released: live=0 test=476
    salesman_code=PMazer | released_dollars: live=0 test=3222.4800
    salesman_code=REdwards | ordered_dollars: live=1258734.8500 test=1257726.0400
    salesman_code=REdwards | qty_ordered: live=119076 test=119005
    salesman_code=REdwards | qty_released: live=0 test=71953
    salesman_code=REdwards | released_dollars: live=0 test=771352.3100

## Sheet: Full Data [DIFF]
  Row key: sales_order_number, line_number, item_number
  Rows live=39625 test=40065 matched=39362
  Extra columns in /test (ignored): qty_left_to_ship, qtyreserved
  Missing columns in /test: dataqualityflag, fulfillment, qty_open, qty_shipped, shipped_dollars
  Patterns:
    - 263 live row(s) missing on /test (1% of live rows).
    - Common denominator (missing on /test): 216/263 rows share date 2026-07-01.
    - Top dates (missing on /test): 2026-07-01=216, 2026-07-22=6, 2026-07-28=6, 2026-07-08=5, 2026-07-16=5
    - 703 /test-only row(s) not on live (2% of /test rows).
    - Top dates (extra on /test): 2026-07-27=167, 2026-07-31=128, 2026-07-06=114, 2026-07-28=77, 2026-07-10=70
    - Value diffs by column: qty_released=33728, released_dollars=33657, status=5634, order_date=5416, open_dollars=48
    - Top dates (value-diff rows): 2026-07-13=6274, 2026-07-06=5739, 2026-07-20=4877, 2026-07-27=4421, 2026-07-14=3245
    - All qty_released diffs: live is empty/zero, /test has a value.
    - All released_dollars diffs: live is empty/zero, /test has a value.
  Missing in /test (263):
    sales_order_number=ORD00866999, line_number=1, item_number=MSG227WD06 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867000, line_number=1, item_number=OMPN84ER06 (order_date=2026-07-01, customer_account=9022)
    sales_order_number=ORD00867001, line_number=1, item_number=GMVL14TP06 (order_date=2026-07-01, customer_account=9022)
    sales_order_number=ORD00867002, line_number=1, item_number=PAPN84BU12 (order_date=2026-07-01, customer_account=9022)
    sales_order_number=ORD00867003, line_number=1, item_number=569-0-PK12 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867004, line_number=1, item_number=BCNAPKSG36 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867004, line_number=2, item_number=BCNAPKTP36 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867005, line_number=1, item_number=MSG2324AL6 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867005, line_number=4, item_number=MSG2324AL6 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867005, line_number=3, item_number=MSG2324AL6 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867005, line_number=2, item_number=MSG2324AL6 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867006, line_number=2, item_number=505-0-PK48 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867006, line_number=1, item_number=505-0-PK48 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867007, line_number=1, item_number=DRTU63WT06 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867007, line_number=2, item_number=DRTU63WT06 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867008, line_number=1, item_number=WRM1830DI6 (order_date=2026-07-01, customer_account=9206)
    sales_order_number=ORD00867009, line_number=1, item_number=MSG231GY06 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867010, line_number=1, item_number=MSG228AL06 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867010, line_number=2, item_number=MSG234AL06 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867011, line_number=1, item_number=STSQP70220 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867012, line_number=1, item_number=MSG259AL04 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867013, line_number=1, item_number=MSG247AL04 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867014, line_number=1, item_number=RTFTV60120 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867015, line_number=1, item_number=MFG230GY02 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867016, line_number=2, item_number=DSG248WH04 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867016, line_number=1, item_number=DSG223WH06 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867017, line_number=1, item_number=TQPN84MS06 (order_date=2026-07-01, customer_account=9022)
    sales_order_number=ORD00867018, line_number=1, item_number=PAPN84NY12 (order_date=2026-07-01, customer_account=9022)
    sales_order_number=ORD00867019, line_number=1, item_number=CAPRI3P410 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867020, line_number=1, item_number=MSG2297WH6 (order_date=2026-07-01, customer_account=9206)
    sales_order_number=ORD00867021, line_number=1, item_number=LUG229MH04 (order_date=2026-07-01, customer_account=9206)
    sales_order_number=ORD00867022, line_number=1, item_number=MSG226GY06 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867023, line_number=1, item_number=MSG2584BK4 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867024, line_number=1, item_number=MSG243AL04 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867025, line_number=1, item_number=260-0-PK24 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867026, line_number=2, item_number=MSG2314BK6 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867026, line_number=1, item_number=MSG2274BK6 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867027, line_number=1, item_number=MSG234WH06 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867028, line_number=2, item_number=BCTU63BU12 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867028, line_number=1, item_number=BCVL14BU12 (order_date=2026-07-01, customer_account=7025)
    sales_order_number=ORD00867029, line_number=1, item_number=MSG226WH06 (order_date=2026-07-01, customer_account=9303)
    sales_order_number=ORD00867030, line_number=4, item_number=FTVWD23120 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867030, line_number=5, item_number=FTVWD23120 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867030, line_number=6, item_number=FTVWD23120 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867030, line_number=3, item_number=FTVWD23120 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867030, line_number=8, item_number=FTVWD23120 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867030, line_number=7, item_number=FTVWD23120 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867030, line_number=1, item_number=FTVWD23120 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867030, line_number=2, item_number=FTVWD23120 (order_date=2026-07-01, customer_account=7125)
    sales_order_number=ORD00867031, line_number=1, item_number=MSG228BK06 (order_date=2026-07-01, customer_account=9303)
    ... +213 more
  Extra in /test only (703):
    sales_order_number=ORD00888517, line_number=1, item_number=FTVMA45545 (order_date=2026-07-31, customer_account=9091)
    sales_order_number=ORD00888516, line_number=1, item_number=DSG229BK06 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888515, line_number=1, item_number=FTVSO10220 (order_date=2026-07-31, customer_account=9206)
    sales_order_number=ORD00888514, line_number=1, item_number=MSG238WH04 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888513, line_number=2, item_number=MFG230MH02 (order_date=2026-07-31, customer_account=7125)
    sales_order_number=ORD00888513, line_number=1, item_number=MFG230MH02 (order_date=2026-07-31, customer_account=7125)
    sales_order_number=ORD00888512, line_number=1, item_number=FTVWD23120 (order_date=2026-07-31, customer_account=7125)
    sales_order_number=ORD00888511, line_number=1, item_number=MSG239BK04 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888510, line_number=1, item_number=INOPOR6604 (order_date=2026-07-31, customer_account=9206)
    sales_order_number=ORD00888509, line_number=1, item_number=PCM1830WL6 (order_date=2026-07-31, customer_account=7125)
    sales_order_number=ORD00888508, line_number=1, item_number=WRM1830AD6 (order_date=2026-07-31, customer_account=9022)
    sales_order_number=ORD00888507, line_number=2, item_number=MSG226WH06 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888507, line_number=3, item_number=MSG230WH06 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888507, line_number=1, item_number=MSG222WH06 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888506, line_number=1, item_number=WIPN84GY06 (order_date=2026-07-31, customer_account=9022)
    sales_order_number=ORD00888505, line_number=1, item_number=FTVMA40920 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888504, line_number=1, item_number=DR54X72TN6 (order_date=2026-07-31, customer_account=8015)
    sales_order_number=ORD00888503, line_number=1, item_number=MSG238WH04 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888502, line_number=1, item_number=FTVSO10320 (order_date=2026-07-31, customer_account=9206)
    sales_order_number=ORD00888501, line_number=1, item_number=MSG235BK06 (order_date=2026-07-31, customer_account=9206)
    sales_order_number=ORD00888500, line_number=1, item_number=RTFTV60520 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888499, line_number=1, item_number=MSG225WH06 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888498, line_number=1, item_number=PCM1830GA6 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888497, line_number=1, item_number=MSG227BK06 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888496, line_number=1, item_number=FTVMA40220 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888495, line_number=1, item_number=WNPP84IV06 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888494, line_number=1, item_number=TRS736BK06 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888493, line_number=1, item_number=TRS736BK06 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888492, line_number=1, item_number=MSG239GY04 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888491, line_number=1, item_number=MSG238WH04 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888490, line_number=1, item_number=DSG234GY06 (order_date=2026-07-31, customer_account=9206)
    sales_order_number=ORD00888489, line_number=1, item_number=VFP1.2HK10 (order_date=2026-07-31, customer_account=9206)
    sales_order_number=ORD00888488, line_number=1, item_number=BCTR36BW12 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888487, line_number=1, item_number=MSG252WH04 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888486, line_number=1, item_number=MSG232WH06 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888485, line_number=1, item_number=MSG238WH04 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888484, line_number=1, item_number=DSG233LT06 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888483, line_number=1, item_number=MSG229WD06 (order_date=2026-07-31, customer_account=9206)
    sales_order_number=ORD00888482, line_number=1, item_number=BECS36GN12 (order_date=2026-07-31, customer_account=1412)
    sales_order_number=ORD00888481, line_number=1, item_number=DSG234MH06 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888480, line_number=1, item_number=MSG2274BK6 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888479, line_number=1, item_number=FTVMA46120 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888478, line_number=1, item_number=MSG242WH04 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888477, line_number=1, item_number=MSG238WH04 (order_date=2026-07-31, customer_account=9303)
    sales_order_number=ORD00888476, line_number=1, item_number=BETR36GY12 (order_date=2026-07-31, customer_account=9206)
    sales_order_number=ORD00888475, line_number=1, item_number=TRL376WH12 (order_date=2026-07-31, customer_account=7125)
    sales_order_number=ORD00888474, line_number=1, item_number=STT1M10120 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888473, line_number=1, item_number=TRL376BK12 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888472, line_number=1, item_number=FTVSO10220 (order_date=2026-07-31, customer_account=7025)
    sales_order_number=ORD00888471, line_number=1, item_number=MSG226WH06 (order_date=2026-07-31, customer_account=9303)
    ... +653 more
  Value diffs (78535):
    sales_order_number=ORD00867173, line_number=1, item_number=MSG22342W6 | qty_released: live=0 test=1
    sales_order_number=ORD00867173, line_number=1, item_number=MSG22342W6 | released_dollars: live=0 test=8.2200
    sales_order_number=ORD00867174, line_number=1, item_number=MIPN63TL06 | qty_released: live=0 test=2
    sales_order_number=ORD00867174, line_number=1, item_number=MIPN63TL06 | released_dollars: live=0 test=18.6600
    sales_order_number=ORD00867175, line_number=2, item_number=MSG2237BK6 | qty_released: live=0 test=1
    sales_order_number=ORD00867175, line_number=2, item_number=MSG2237BK6 | released_dollars: live=0 test=12.6300
    sales_order_number=ORD00867175, line_number=1, item_number=MSG2237BK6 | qty_released: live=0 test=1
    sales_order_number=ORD00867175, line_number=1, item_number=MSG2237BK6 | released_dollars: live=0 test=12.6300
    sales_order_number=ORD00867176, line_number=2, item_number=TRS376WH12 | qty_released: live=0 test=1
    sales_order_number=ORD00867176, line_number=2, item_number=TRS376WH12 | released_dollars: live=0 test=11
    sales_order_number=ORD00867176, line_number=1, item_number=TRS376WH12 | qty_released: live=0 test=1
    sales_order_number=ORD00867176, line_number=1, item_number=TRS376WH12 | released_dollars: live=0 test=11
    sales_order_number=ORD00867177, line_number=1, item_number=MSG234WH06 | qty_released: live=0 test=2
    sales_order_number=ORD00867177, line_number=1, item_number=MSG234WH06 | released_dollars: live=0 test=25.8800
    sales_order_number=ORD00867178, line_number=1, item_number=SOCO48WH06 | qty_released: live=0 test=2
    sales_order_number=ORD00867178, line_number=1, item_number=SOCO48WH06 | released_dollars: live=0 test=22.0800
    sales_order_number=ORD00867179, line_number=1, item_number=ANFTMGAR12 | qty_released: live=0 test=2
    sales_order_number=ORD00867179, line_number=1, item_number=ANFTMGAR12 | released_dollars: live=0 test=19.2200
    sales_order_number=ORD00867179, line_number=2, item_number=GBTV36MU12 | qty_released: live=0 test=1
    sales_order_number=ORD00867179, line_number=2, item_number=GBTV36MU12 | released_dollars: live=0 test=9.6700
    sales_order_number=ORD00867180, line_number=1, item_number=MSG2584WH4 | qty_released: live=0 test=1
    sales_order_number=ORD00867180, line_number=1, item_number=MSG2584WH4 | released_dollars: live=0 test=17.1000
    sales_order_number=ORD00867181, line_number=1, item_number=MSG2317BK6 | qty_released: live=0 test=2
    sales_order_number=ORD00867181, line_number=1, item_number=MSG2317BK6 | released_dollars: live=0 test=29.1000
    sales_order_number=ORD00867182, line_number=1, item_number=MSG258AL04 | qty_released: live=0 test=1
    sales_order_number=ORD00867182, line_number=1, item_number=MSG258AL04 | released_dollars: live=0 test=21.9900
    sales_order_number=ORD00867183, line_number=1, item_number=WRM1830IW6 | qty_released: live=0 test=1
    sales_order_number=ORD00867183, line_number=1, item_number=WRM1830IW6 | released_dollars: live=0 test=8.8000
    sales_order_number=ORD00867184, line_number=1, item_number=STP2.0SS10 | qty_released: live=0 test=1
    sales_order_number=ORD00867184, line_number=1, item_number=STP2.0SS10 | released_dollars: live=0 test=17.2900
    sales_order_number=ORD00867185, line_number=1, item_number=INOBRNNK04 | qty_released: live=0 test=1
    sales_order_number=ORD00867185, line_number=1, item_number=INOBRNNK04 | released_dollars: live=0 test=40.9500
    sales_order_number=ORD00867186, line_number=2, item_number=DSG234GY06 | qty_released: live=0 test=1
    sales_order_number=ORD00867186, line_number=2, item_number=DSG234GY06 | released_dollars: live=0 test=13.8200
    sales_order_number=ORD00867186, line_number=1, item_number=DSG234BK06 | qty_released: live=0 test=1
    sales_order_number=ORD00867186, line_number=1, item_number=DSG234BK06 | released_dollars: live=0 test=14.8500
    sales_order_number=ORD00867187, line_number=1, item_number=MSG234WH06 | qty_released: live=0 test=1
    sales_order_number=ORD00867187, line_number=1, item_number=MSG234WH06 | released_dollars: live=0 test=12.9400
    sales_order_number=ORD00867188, line_number=2, item_number=CGTS24MU12 | qty_released: live=0 test=1
    sales_order_number=ORD00867188, line_number=2, item_number=CGTS24MU12 | released_dollars: live=0 test=9.3300
    sales_order_number=ORD00867188, line_number=1, item_number=MJCS36ML12 | qty_released: live=0 test=1
    sales_order_number=ORD00867188, line_number=1, item_number=MJCS36ML12 | released_dollars: live=0 test=9.9000
    sales_order_number=ORD00867189, line_number=2, item_number=WRM1830IW6 | qty_released: live=0 test=1
    sales_order_number=ORD00867189, line_number=2, item_number=WRM1830IW6 | released_dollars: live=0 test=8.8000
    sales_order_number=ORD00867189, line_number=1, item_number=WRM1830IW6 | qty_released: live=0 test=1
    sales_order_number=ORD00867189, line_number=1, item_number=WRM1830IW6 | released_dollars: live=0 test=8.8000
    sales_order_number=ORD00867189, line_number=3, item_number=WRM1830IW6 | qty_released: live=0 test=1
    sales_order_number=ORD00867189, line_number=3, item_number=WRM1830IW6 | released_dollars: live=0 test=8.8000
    sales_order_number=ORD00867190, line_number=1, item_number=TOVYSTBK04 | qty_released: live=0 test=1
    sales_order_number=ORD00867190, line_number=1, item_number=TOVYSTBK04 | released_dollars: live=0 test=9.2400
    ... +78485 more
  Soft/cosmetic text diffs (not failing): 51
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
