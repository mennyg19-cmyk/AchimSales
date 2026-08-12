# Parity: ordered

- Params: `{'period': 'last_month'}`
- Live file: `.scratch\parity\20260724-070725\ordered__live.xlsx`
- Test file: `.scratch\parity\20260724-070725\ordered__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **164874**
- Missing sheets in /test: (none)
- Extra sheets in /test (ignored): (none)
- Per sheet: Summary=DIFF(16380), By Customer=DIFF(411), By Item=DIFF(4423), By Order=DIFF(66464), By Salesman=DIFF(67), Full Data=DIFF(77129)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260724-070725\ordered__live.xlsx vs .scratch\parity\20260724-070725\ordered__test.xlsx
Hard differences: 164874
Result: DIFFERENCES FOUND

## Sheet: Summary [DIFF]
  Row key: customer_name, item_number
  Rows live=8788 test=8837 matched=8770
  Patterns:
    - 18 live row(s) missing on /test (0% of live rows).
    - 67 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: qtyremainder=7862, extended_price_remainder=7845, extended_price_ordered=277, qty_ordered=271, salesman_code=28
  Missing in /test (18):
    customer_name=AMAZON.COM DEDC,LLC (DROPSHIP), item_number=DSG246MH04 (salesman_code=REdwards)
    customer_name=AMAZON.COM DEDC,LLC (DROPSHIP), item_number=RTFTV61620 (salesman_code=REdwards)
    customer_name=HOMEDEPOT.COM, item_number=FF5P84IB12 (salesman_code=Integrated)
    customer_name=HOMEDEPOT.COM, item_number=MFG225MH02 (salesman_code=Integrated)
    customer_name=HOMEDEPOT.COM, item_number=MSG2367GY6 (salesman_code=Integrated)
    customer_name=HOMEDEPOT.COM, item_number=RDCLNGD486 (salesman_code=Integrated)
    customer_name=HOMEDEPOT.COM, item_number=VGPN84BR06 (salesman_code=Integrated)
    customer_name=JCPENNEY COMPANY INC.  (DS), item_number=MSG239WH04 (salesman_code=AGrossman)
    customer_name=KOHL'S, item_number=ANFTMHSH12 (salesman_code=JWeigand)
    customer_name=LOWE'S COMPANIES INC.  (DS), item_number=BRVL14BK12 (salesman_code=Integrated)
    customer_name=LOWE'S COMPANIES INC.  (DS), item_number=CSTD36AL06 (salesman_code=Integrated)
    customer_name=LOWE'S COMPANIES INC.  (DS), item_number=LUG243MH04 (salesman_code=Integrated)
    customer_name=LOWE'S COMPANIES INC.  (DS), item_number=MSG227WD06 (salesman_code=Integrated)
    customer_name=LOWE'S COMPANIES INC.  (DS), item_number=OMPN84SG06 (salesman_code=Integrated)
    customer_name=MBA SUPPLY CO., item_number=FTVWD20545 (salesman_code=MKolko)
    customer_name=MBA SUPPLY CO., item_number=OPT376WH36 (salesman_code=MKolko)
    customer_name=STARCO MAINTENANCE SUPPLIES, item_number=VFP2.0MO10 (salesman_code=MKolko)
    customer_name=GRAND TOTAL, item_number= (salesman_code=None)
  Extra in /test only (67):
    customer_name=JCPENNEY COMPANY INC.  (DS), item_number=HVVL14BL12 (salesman_code=AGrossman)
    customer_name=WAL-MART STORES, INC.#546978, item_number=BCNAPKTP36 (salesman_code=AGrossman)
    customer_name=WAL-MART STORES, INC.#546978, item_number=BCNAPKSG36 (salesman_code=AGrossman)
    customer_name=WAYFAIR LLC (DS), item_number=FTVSO10220 (salesman_code=HKaufman)
    customer_name=WAYFAIR LLC (DS), item_number=STT1M40220 (salesman_code=HKaufman)
    customer_name=WAYFAIR LLC (DS), item_number=WIPN84WH06 (salesman_code=HKaufman)
    customer_name=KOHL'S, item_number=280-0-PK12 (salesman_code=JWeigand)
    customer_name=KOHL'S, item_number=LLTV24CC12 (salesman_code=JWeigand)
    customer_name=KOHL'S, item_number=TYPN63TN06 (salesman_code=JWeigand)
    customer_name=KOHL'S, item_number=CITV24TS12 (salesman_code=JWeigand)
    customer_name=ESSEE FLOOR COVERING, item_number=STT1M44620 (salesman_code=MGrego)
    customer_name=ERNESTO'S HARDWARE STORE, item_number=FTVWD22945 (salesman_code=MKolko)
    customer_name=LION BUILDING SUPPLY, item_number=MSG222WH06 (salesman_code=MKolko)
    customer_name=LION BUILDING SUPPLY, item_number=MSG2287WH6 (salesman_code=MKolko)
    customer_name=LION BUILDING SUPPLY, item_number=MSG2327WH6 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=WRM1830LT6 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=OMWFVLSSGG (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=WRM1830FL6 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=TQPN63MS06 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=TQPN84SL06 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=TQPN84GR06 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=HNTV24AG12 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=WETV36BW12 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=PCM1830WA6 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=CNPN84GY06 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=ANFTMBES12 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=ANFTMCUC12 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=AFB1830T12 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=RTFTV60120 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=AFB1830N12 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=AFB1830G12 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=SPPN84LI06 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=AFB1830B12 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=OMTU63BUGG (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=OMTU63ABGG (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=COM1830RM6 (salesman_code=MKolko)
    customer_name=J. Alperin Co. Inc., item_number=FTVWD20245 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=SSTS36YL12 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=DRTU63NY06 (salesman_code=MKolko)
    customer_name=GOODGRAM, item_number=CACS24BU12 (salesman_code=MKolko)
    ... +27 more
  Value diffs (16295):
    customer_name=707 ALLERTON DISCOUNT, item_number=AB73TWAC04 | extended_price_remainder: live=56 test=-56
    customer_name=707 ALLERTON DISCOUNT, item_number=AB73TWAC04 | qtyremainder: live=4 test=-4
    customer_name=707 ALLERTON DISCOUNT, item_number=AB78QNAC04 | extended_price_remainder: live=152 test=-152
    customer_name=707 ALLERTON DISCOUNT, item_number=AB78QNAC04 | qtyremainder: live=8 test=-8
    customer_name=707 ALLERTON DISCOUNT, item_number=AB80DQAC02 | extended_price_remainder: live=104 test=-104
    customer_name=707 ALLERTON DISCOUNT, item_number=AB80DQAC02 | qtyremainder: live=4 test=-4
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG229WH06 | extended_price_remainder: live=187.5000 test=-187.5000
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG229WH06 | qtyremainder: live=30 test=-30
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG230WH06 | extended_price_remainder: live=187.5000 test=-187.5000
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG230WH06 | qtyremainder: live=30 test=-30
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG231WH06 | extended_price_remainder: live=187.5000 test=-187.5000
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG231WH06 | qtyremainder: live=30 test=-30
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG232WH06 | extended_price_remainder: live=75 test=-75
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG232WH06 | qtyremainder: live=12 test=-12
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG235WH06 | extended_price_remainder: live=37.5000 test=-37.5000
    customer_name=707 ALLERTON DISCOUNT, item_number=MSG235WH06 | qtyremainder: live=6 test=-6
    customer_name=A & B DEPT. STORE, item_number=AB75FLAC04 | extended_price_remainder: live=128 test=-128
    customer_name=A & B DEPT. STORE, item_number=AB75FLAC04 | qtyremainder: live=8 test=-8
    customer_name=A & B DEPT. STORE, item_number=ANFTMBES12 | extended_price_remainder: live=54 test=-54
    customer_name=A & B DEPT. STORE, item_number=ANFTMBES12 | qtyremainder: live=12 test=-12
    customer_name=A & B DEPT. STORE, item_number=ANFTMBTF12 | extended_price_remainder: live=54 test=-54
    customer_name=A & B DEPT. STORE, item_number=ANFTMBTF12 | qtyremainder: live=12 test=-12
    customer_name=A & B DEPT. STORE, item_number=ANFTMCHT12 | extended_price_remainder: live=54 test=-54
    customer_name=A & B DEPT. STORE, item_number=ANFTMCHT12 | qtyremainder: live=12 test=-12
    customer_name=A & B DEPT. STORE, item_number=ANFTMLLG12 | extended_price_remainder: live=54 test=-54
    customer_name=A & B DEPT. STORE, item_number=ANFTMLLG12 | qtyremainder: live=12 test=-12
    customer_name=A & B DEPT. STORE, item_number=ANFTMPRC12 | extended_price_remainder: live=54 test=-54
    customer_name=A & B DEPT. STORE, item_number=ANFTMPRC12 | qtyremainder: live=12 test=-12
    customer_name=A & B DEPT. STORE, item_number=CHCHPDBK14 | extended_price_remainder: live=105 test=-105
    customer_name=A & B DEPT. STORE, item_number=CHCHPDBK14 | qtyremainder: live=14 test=-14
    customer_name=A & B DEPT. STORE, item_number=CHCHPDGY14 | extended_price_remainder: live=105 test=-105
    customer_name=A & B DEPT. STORE, item_number=CHCHPDGY14 | qtyremainder: live=14 test=-14
    customer_name=A & B DEPT. STORE, item_number=CHCS36NY12 | extended_price_remainder: live=66 test=-66
    customer_name=A & B DEPT. STORE, item_number=CHCS36NY12 | qtyremainder: live=12 test=-12
    customer_name=A & B DEPT. STORE, item_number=FTVGM33245 | extended_price_remainder: live=120 test=-120
    customer_name=A & B DEPT. STORE, item_number=FTVGM33245 | qtyremainder: live=8 test=-8
    customer_name=A & B DEPT. STORE, item_number=FTVGM33445 | extended_price_remainder: live=75 test=-75
    customer_name=A & B DEPT. STORE, item_number=FTVGM33445 | qtyremainder: live=5 test=-5
    customer_name=A & B DEPT. STORE, item_number=FTVWD21445 | extended_price_remainder: live=225 test=-225
    customer_name=A & B DEPT. STORE, item_number=FTVWD21445 | qtyremainder: live=15 test=-15
    ... +16255 more
  Soft/cosmetic text diffs (not failing): 41

## Sheet: By Customer [DIFF]
  Row key: customer_account, salesman_code
  Rows live=156 test=159 matched=153
  Patterns:
    - 3 live row(s) missing on /test (2% of live rows).
    - 6 /test-only row(s) not on live (4% of /test rows).
    - Value diffs by column: qty_released=149, released_dollars=146, shipped_dollars=23, qty_shipped=20, ordered_dollars=18
  Missing in /test (3):
    customer_account=00011528, salesman_code= (customer_name=All Pro Building Supplies LLC)
    customer_account=00011609, salesman_code= (customer_name=Swiftcart)
    customer_account=643, salesman_code=HKaufman (customer_name=PARKE-BELL LTD.INC(DROP SHIPS))
  Extra in /test only (6):
    customer_account=00011528, salesman_code=00011528 (customer_name=All Pro Building Supplies LLC)
    customer_account=00011609, salesman_code=00011609 (customer_name=Swiftcart)
    customer_account=8130, salesman_code=MGrego (customer_name=ESSEE FLOOR COVERING)
    customer_account=9437, salesman_code=MKolko (customer_name=LION BUILDING SUPPLY)
    customer_account=9497, salesman_code=MKolko (customer_name=ERNESTO'S HARDWARE STORE)
    customer_account=Grand total, salesman_code= (customer_name=None)
  Value diffs (402):
    customer_account=00011077, salesman_code=HKaufman | qty_released: live=0 test=192
    customer_account=00011077, salesman_code=HKaufman | released_dollars: live=0 test=1845.6800
    customer_account=00011282, salesman_code=HKaufman | qty_released: live=0 test=6168
    customer_account=00011282, salesman_code=HKaufman | released_dollars: live=0 test=20247
    customer_account=00011379, salesman_code=HKaufman | qty_released: live=0 test=8
    customer_account=00011379, salesman_code=HKaufman | released_dollars: live=0 test=402.8000
    customer_account=00011526, salesman_code=House | qty_released: live=0 test=1
    customer_account=00011526, salesman_code=House | released_dollars: live=0 test=31.2000
    customer_account=00011540, salesman_code=MKolko | cancelled_dollars: live=210.3600 test=244.3600
    customer_account=00011540, salesman_code=MKolko | fulfillment: live=85% test=0.8248
    customer_account=00011540, salesman_code=MKolko | open_dollars: live=40.8000 test=6.8000
    customer_account=00011540, salesman_code=MKolko | qty_cancelled: live=36 test=41
    customer_account=00011540, salesman_code=MKolko | qty_open: live=6 test=1
    customer_account=00011540, salesman_code=MKolko | qty_released: live=0 test=192
    customer_account=00011540, salesman_code=MKolko | released_dollars: live=0 test=1150.3800
    customer_account=00011569, salesman_code=MKolko | qty_released: live=0 test=58
    customer_account=00011569, salesman_code=MKolko | released_dollars: live=0 test=1088
    customer_account=00011594, salesman_code=HKaufman | qty_released: live=0 test=70
    customer_account=00011594, salesman_code=HKaufman | released_dollars: live=0 test=1029
    customer_account=00011599, salesman_code=MGrego | qty_released: live=0 test=196
    customer_account=00011599, salesman_code=MGrego | released_dollars: live=0 test=1082.8400
    customer_account=00011600, salesman_code=AGrossman | qty_released: live=0 test=2882
    customer_account=00011600, salesman_code=AGrossman | released_dollars: live=0 test=17647.2600
    customer_account=00011604, salesman_code=MGrego | qty_released: live=0 test=409
    customer_account=00011604, salesman_code=MGrego | released_dollars: live=0 test=1403.6300
    customer_account=00011606, salesman_code=MGrego | qty_released: live=0 test=448
    customer_account=00011606, salesman_code=MGrego | released_dollars: live=0 test=2306.6600
    customer_account=00011611, salesman_code=House | qty_released: live=0 test=18
    customer_account=00011611, salesman_code=House | released_dollars: live=0 test=108.4000
    customer_account=00011612, salesman_code=MKolko | qty_released: live=0 test=267
    customer_account=00011612, salesman_code=MKolko | released_dollars: live=0 test=1711.0800
    customer_account=0123456789, salesman_code=House | qty_ordered: live=27 test=5
    customer_account=0123456789, salesman_code=House | qty_released: live=0 test=27
    customer_account=1049, salesman_code=BLevin | qty_released: live=0 test=704
    customer_account=1049, salesman_code=BLevin | released_dollars: live=0 test=5696.9800
    customer_account=1063, salesman_code=BLevin | qty_released: live=0 test=308
    customer_account=1063, salesman_code=BLevin | released_dollars: live=0 test=2246.2600
    customer_account=1109, salesman_code=BLevin | qty_released: live=0 test=60
    customer_account=1109, salesman_code=BLevin | released_dollars: live=0 test=1104
    customer_account=1164, salesman_code=MKolko | qty_released: live=0 test=7
    ... +362 more

## Sheet: By Item [DIFF]
  Row key: item_number
  Rows live=1750 test=1754 matched=1750
  Patterns:
    - 4 /test-only row(s) not on live (0% of /test rows).
    - Value diffs by column: qty_released=1531, released_dollars=1527, qty_shipped=311, ordered_dollars=305, shipped_dollars=304
  Extra in /test only (4):
    item_number=OMTU63BUGG
    item_number=OMTU63ABGG
    item_number=OMWFVLSSGG
    item_number=MSG226GY06
  Value diffs (4419):
    item_number=123CO36B24 | qty_open: live=48 test=72
    item_number=123CO36B24 | qty_released: live=24 test=164
    item_number=123CO36B24 | released_dollars: live=120 test=1074.8100
    item_number=123CO36B24 | shipped_dollars: live=954.8100 test=1074.8100
    item_number=123CO36W24 | qty_open: live=72 test=120
    item_number=123CO36W24 | qty_released: live=48 test=881
    item_number=123CO36W24 | released_dollars: live=240 test=5171.3500
    item_number=123CO36W24 | shipped_dollars: live=4931.3500 test=5171.3500
    item_number=123CO48B24 | qty_released: live=0 test=170
    item_number=123CO48B24 | released_dollars: live=0 test=1287.4400
    item_number=123CO48L24 | qty_released: live=0 test=36
    item_number=123CO48L24 | released_dollars: live=0 test=292.6100
    item_number=123CO48W24 | qty_open: live=24 test=48
    item_number=123CO48W24 | qty_released: live=24 test=322
    item_number=123CO48W24 | released_dollars: live=156 test=2228.3600
    item_number=123CO48W24 | shipped_dollars: live=2072.3600 test=2228.3600
    item_number=200-0-PK24 | qty_released: live=0 test=219
    item_number=200-0-PK24 | released_dollars: live=0 test=488.5200
    item_number=205-0-PK48 | ordered_dollars: live=831.9200 test=828.4600
    item_number=205-0-PK48 | qty_ordered: live=707 test=706
    item_number=205-0-PK48 | qty_released: live=0 test=706
    item_number=205-0-PK48 | qty_shipped: live=707 test=706
    item_number=205-0-PK48 | released_dollars: live=0 test=828.4600
    item_number=205-0-PK48 | shipped_dollars: live=831.9200 test=828.4600
    item_number=210-0-PK24 | ordered_dollars: live=260.5400 test=266.1300
    item_number=210-0-PK24 | qty_ordered: live=146 test=147
    item_number=210-0-PK24 | qty_released: live=0 test=147
    item_number=210-0-PK24 | qty_shipped: live=146 test=147
    item_number=210-0-PK24 | released_dollars: live=0 test=266.1300
    item_number=210-0-PK24 | shipped_dollars: live=260.5400 test=266.1300
    item_number=215-0-PK12 | qty_released: live=0 test=43
    item_number=215-0-PK12 | released_dollars: live=0 test=434.1300
    item_number=220-0-PK24 | ordered_dollars: live=156.3100 test=152.7100
    item_number=220-0-PK24 | qty_ordered: live=42 test=41
    item_number=220-0-PK24 | qty_released: live=0 test=41
    item_number=220-0-PK24 | qty_shipped: live=42 test=41
    item_number=220-0-PK24 | released_dollars: live=0 test=152.7100
    item_number=220-0-PK24 | shipped_dollars: live=156.3100 test=152.7100
    item_number=225-0-PK24 | ordered_dollars: live=195.7700 test=200.3800
    item_number=225-0-PK24 | qty_ordered: live=61 test=62
    ... +4379 more
  Soft/cosmetic text diffs (not failing): 41

## Sheet: By Order [DIFF]
  Row key: sales_order_number
  Rows live=20931 test=20962 matched=20779
  Extra columns in /test (ignored): customer_name, order_status, status
  Missing columns in /test: salesordername
  Patterns:
    - 152 live row(s) missing on /test (1% of live rows).
    - Common denominator (missing on /test): 152/152 rows share date 2026-06-01.
    - Date breakdown (missing on /test): 2026-06-01=152
    - 183 /test-only row(s) not on live (1% of /test rows).
    - Common denominator (extra on /test): 175/182 rows share date 2026-06-30.
    - Date breakdown (extra on /test): 2026-06-30=175, 2026-06-29=2, 2026-06-16=1, 2026-06-26=1, 2026-06-15=1, 2026-06-09=1, 2026-06-03=1
    - Value diffs by column: po_number=20779, qty_released=20575, released_dollars=20568, order_date=4136, shipped_dollars=14
    - Top dates (value-diff rows): 2026-06-08=2882, 2026-06-29=2787, 2026-06-22=2671, 2026-06-15=2602, 2026-06-03=2550
    - All po_number diffs: /test is empty/zero, live has a value.
  Missing in /test (152):
    sales_order_number=ORD00846049 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846050 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846051 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846052 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846053 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846054 (order_date=2026-06-01, customer_account=9022, salesman_code=AGrossman)
    sales_order_number=ORD00846055 (order_date=2026-06-01, customer_account=9206, salesman_code=Integrated)
    sales_order_number=ORD00846056 (order_date=2026-06-01, customer_account=9206, salesman_code=Integrated)
    sales_order_number=ORD00846057 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846058 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846059 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846060 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846061 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846062 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846063 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846064 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846065 (order_date=2026-06-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00846066 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846067 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846068 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846069 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846070 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846071 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846072 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    sales_order_number=ORD00846073 (order_date=2026-06-01, customer_account=9022, salesman_code=AGrossman)
    sales_order_number=ORD00846074 (order_date=2026-06-01, customer_account=9022, salesman_code=AGrossman)
    sales_order_number=ORD00846075 (order_date=2026-06-01, customer_account=9022, salesman_code=AGrossman)
    sales_order_number=ORD00846076 (order_date=2026-06-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00846077 (order_date=2026-06-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00846078 (order_date=2026-06-01, customer_account=7125, salesman_code=AGrossman)
    sales_order_number=ORD00846079 (order_date=2026-06-01, customer_account=9206, salesman_code=Integrated)
    sales_order_number=ORD00846080 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846081 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846082 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846083 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846084 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846085 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846086 (order_date=2026-06-01, customer_account=9303, salesman_code=REdwards)
    sales_order_number=ORD00846087 (order_date=2026-06-01, customer_account=1412, salesman_code=JWeigand)
    sales_order_number=ORD00846088 (order_date=2026-06-01, customer_account=7025, salesman_code=Integrated)
    ... +112 more
  Extra in /test only (183):
    sales_order_number=ORD00867164 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867163 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867151 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867150 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867149 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867129 (order_date=2026-06-30, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00867119 (order_date=2026-06-30, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00867117 (order_date=2026-06-30, customer_account=9091, customer_name=OJ COMMERCE)
    sales_order_number=ORD00867085 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867084 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867083 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867082 (order_date=2026-06-30, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00867073 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867072 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867066 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867051 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867050 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867033 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867032 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867030 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867019 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867018 (order_date=2026-06-30, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00867017 (order_date=2026-06-30, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00867012 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867007 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867006 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867005 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867004 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867003 (order_date=2026-06-30, customer_account=7125, customer_name=WAL-MART STORES, INC.#546978)
    sales_order_number=ORD00867002 (order_date=2026-06-30, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00867001 (order_date=2026-06-30, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00867000 (order_date=2026-06-30, customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS))
    sales_order_number=ORD00867130 (order_date=2026-06-30, customer_account=8015, customer_name=WAYFAIR LLC (DS))
    sales_order_number=ORD00867123 (order_date=2026-06-30, customer_account=8015, customer_name=WAYFAIR LLC (DS))
    sales_order_number=ORD00867087 (order_date=2026-06-30, customer_account=8015, customer_name=WAYFAIR LLC (DS))
    sales_order_number=ORD00867086 (order_date=2026-06-30, customer_account=8015, customer_name=WAYFAIR LLC (DS))
    sales_order_number=ORD00867034 (order_date=2026-06-30, customer_account=8015, customer_name=WAYFAIR LLC (DS))
    sales_order_number=ORD00856959 (order_date=2026-06-16, customer_account=0123456789, customer_name=Avi Grossman)
    sales_order_number=ORD00867162 (order_date=2026-06-30, customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00867161 (order_date=2026-06-30, customer_account=7025, customer_name=HOMEDEPOT.COM)
    ... +143 more
  Value diffs (66128):
    sales_order_number=ORD00846201 | po_number: live=46872809 test=None
    sales_order_number=ORD00846201 | qty_released: live=0 test=1
    sales_order_number=ORD00846201 | released_dollars: live=0 test=11.7500
    sales_order_number=ORD00846202 | po_number: live=46874736 test=None
    sales_order_number=ORD00846202 | qty_released: live=0 test=2
    sales_order_number=ORD00846202 | released_dollars: live=0 test=14.7400
    sales_order_number=ORD00846203 | po_number: live=6713946558_1 test=None
    sales_order_number=ORD00846203 | qty_released: live=0 test=1
    sales_order_number=ORD00846203 | released_dollars: live=0 test=11.2200
    sales_order_number=ORD00846204 | po_number: live=6713951415_4 test=None
    sales_order_number=ORD00846204 | qty_released: live=0 test=1
    sales_order_number=ORD00846204 | released_dollars: live=0 test=13.3500
    sales_order_number=ORD00846205 | po_number: live=6713955889_1 test=None
    sales_order_number=ORD00846205 | qty_released: live=0 test=1
    sales_order_number=ORD00846205 | released_dollars: live=0 test=9.3300
    sales_order_number=ORD00846206 | po_number: live=6713955889_2 test=None
    sales_order_number=ORD00846206 | qty_released: live=0 test=1
    sales_order_number=ORD00846206 | released_dollars: live=0 test=9.3300
    sales_order_number=ORD00846207 | po_number: live=6713962330_1 test=None
    sales_order_number=ORD00846207 | qty_released: live=0 test=1
    sales_order_number=ORD00846207 | released_dollars: live=0 test=9.3300
    sales_order_number=ORD00846208 | po_number: live=409831679 test=None
    sales_order_number=ORD00846208 | qty_released: live=0 test=1
    sales_order_number=ORD00846208 | released_dollars: live=0 test=11.2200
    sales_order_number=ORD00846209 | po_number: live=P4mlyg0n3 test=None
    sales_order_number=ORD00846209 | qty_released: live=0 test=1
    sales_order_number=ORD00846209 | released_dollars: live=0 test=17.5700
    sales_order_number=ORD00846210 | po_number: live=15254558 test=None
    sales_order_number=ORD00846210 | qty_released: live=0 test=1
    sales_order_number=ORD00846210 | released_dollars: live=0 test=21.1900
    sales_order_number=ORD00846211 | po_number: live=15254811 test=None
    sales_order_number=ORD00846211 | qty_released: live=0 test=1
    sales_order_number=ORD00846211 | released_dollars: live=0 test=18.6800
    sales_order_number=ORD00846212 | po_number: live=15254971 test=None
    sales_order_number=ORD00846212 | qty_released: live=0 test=1
    sales_order_number=ORD00846212 | released_dollars: live=0 test=19.3200
    sales_order_number=ORD00846213 | po_number: live=15255324 test=None
    sales_order_number=ORD00846213 | qty_released: live=0 test=1
    sales_order_number=ORD00846213 | released_dollars: live=0 test=16.9100
    sales_order_number=ORD00846214 | po_number: live=15255076 test=None
    ... +66088 more

## Sheet: By Salesman [DIFF]
  Row key: salesman_code
  Rows live=10 test=12 matched=10
  Patterns:
    - 2 /test-only row(s) not on live (17% of /test rows).
    - Value diffs by column: qty_released=10, released_dollars=10, qty_ordered=8, qty_shipped=8, shipped_dollars=8
  Extra in /test only (2):
    salesman_code=00011528
    salesman_code=00011609
  Value diffs (65):
    salesman_code=AGrossman | open_dollars: live=27960 test=12221.3900
    salesman_code=AGrossman | ordered_dollars: live=359043.1100 test=343298.4400
    salesman_code=AGrossman | qty_open: live=4239 test=16777
    salesman_code=AGrossman | qty_ordered: live=57959 test=57969
    salesman_code=AGrossman | qty_released: live=1728 test=40579
    salesman_code=AGrossman | qty_shipped: live=38841 test=28041
    salesman_code=AGrossman | released_dollars: live=9538.5600 test=274023.1900
    salesman_code=AGrossman | shipped_dollars: live=264490.6900 test=274023.1900
    salesman_code=BLevin | qty_open: live=148 test=174
    salesman_code=BLevin | qty_released: live=146 test=12211
    salesman_code=BLevin | qty_shipped: live=12065 test=12185
    salesman_code=BLevin | released_dollars: live=576.2000 test=96346.5600
    salesman_code=BLevin | shipped_dollars: live=95770.3600 test=96346.5600
    salesman_code=HKaufman | open_dollars: live=18100.7000 test=16921.4700
    salesman_code=HKaufman | ordered_dollars: live=507688.9600 test=506731.7600
    salesman_code=HKaufman | qty_open: live=3030 test=6766
    salesman_code=HKaufman | qty_ordered: live=81427 test=81441
    salesman_code=HKaufman | qty_released: live=1132 test=46210
    salesman_code=HKaufman | qty_shipped: live=45064 test=42474
    salesman_code=HKaufman | released_dollars: live=5469.0800 test=284178.4500
    salesman_code=HKaufman | shipped_dollars: live=278487.3400 test=284178.4500
    salesman_code=House | fulfillment: live=97% test=0.9565
    salesman_code=House | qty_ordered: live=68 test=46
    salesman_code=House | qty_released: live=0 test=66
    salesman_code=House | released_dollars: live=0 test=575.6500
    salesman_code=Integrated | ordered_dollars: live=398434.6100 test=398975.7800
    salesman_code=Integrated | qty_ordered: live=25826 test=25812
    salesman_code=Integrated | qty_released: live=0 test=25738
    salesman_code=Integrated | qty_shipped: live=25752 test=25738
    salesman_code=Integrated | released_dollars: live=0 test=398161.2800
    salesman_code=Integrated | shipped_dollars: live=397620.1100 test=398161.2800
    salesman_code=JWeigand | ordered_dollars: live=26736.9100 test=26993.8700
    salesman_code=JWeigand | qty_open: live=798 test=780
    salesman_code=JWeigand | qty_ordered: live=2982 test=3009
    salesman_code=JWeigand | qty_released: live=0 test=2095
    salesman_code=JWeigand | qty_shipped: live=2068 test=2113
    salesman_code=JWeigand | released_dollars: live=0 test=20907.9400
    salesman_code=JWeigand | shipped_dollars: live=20650.9800 test=20907.9400
    salesman_code=LCWalker | qty_released: live=0 test=1464
    salesman_code=LCWalker | released_dollars: live=0 test=18617.4000
    ... +25 more

## Sheet: Full Data [DIFF]
  Row key: sales_order_number, line_number, item_number
  Rows live=38236 test=38333 matched=37979
  Missing columns in /test: dataqualityflag
  Patterns:
    - 257 live row(s) missing on /test (1% of live rows).
    - Common denominator (missing on /test): 198/257 rows share date 2026-06-01.
    - Top dates (missing on /test): 2026-06-01=198, 2026-06-24=13, 2026-06-29=13, 2026-06-15=7, 2026-06-18=6
    - 354 /test-only row(s) not on live (1% of /test rows).
    - Common denominator (extra on /test): 219/354 rows share date 2026-06-30.
    - Top dates (extra on /test): 2026-06-30=219, 2026-06-01=53, 2026-06-09=23, 2026-06-24=13, 2026-06-29=11
    - Value diffs by column: qty_released=33233, released_dollars=33216, order_date=5074, status=4794, qty_open=80
    - Top dates (value-diff rows): 2026-06-29=5872, 2026-06-08=5764, 2026-06-15=4832, 2026-06-01=4794, 2026-06-22=4132
    - All qty_released diffs: live is empty/zero, /test has a value.
    - All released_dollars diffs: live is empty/zero, /test has a value.
  Missing in /test (257):
    sales_order_number=ORD00846049, line_number=1, item_number=MSG2364WH6 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846050, line_number=1, item_number=MSG235AL06 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846051, line_number=1, item_number=MSG2467WH4 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846052, line_number=1, item_number=MSG236WH06 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846053, line_number=1, item_number=FTVMA40920 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846054, line_number=1, item_number=MSG239WH04 (order_date=2026-06-01, customer_account=9022)
    sales_order_number=ORD00846055, line_number=1, item_number=RTFTV61520 (order_date=2026-06-01, customer_account=9206)
    sales_order_number=ORD00846056, line_number=1, item_number=FTVWD22345 (order_date=2026-06-01, customer_account=9206)
    sales_order_number=ORD00846057, line_number=1, item_number=MSG228BK06 (order_date=2026-06-01, customer_account=9303)
    sales_order_number=ORD00846058, line_number=1, item_number=RTFTV61620 (order_date=2026-06-01, customer_account=9303)
    sales_order_number=ORD00846059, line_number=1, item_number=OMSF144GY6 (order_date=2026-06-01, customer_account=9303)
    sales_order_number=ORD00846060, line_number=1, item_number=205-0-PK48 (order_date=2026-06-01, customer_account=9303)
    sales_order_number=ORD00846061, line_number=1, item_number=MSG239AL04 (order_date=2026-06-01, customer_account=9303)
    sales_order_number=ORD00846062, line_number=1, item_number=DSG243MH04 (order_date=2026-06-01, customer_account=9303)
    sales_order_number=ORD00846063, line_number=1, item_number=MSG244AL04 (order_date=2026-06-01, customer_account=9303)
    sales_order_number=ORD00846064, line_number=1, item_number=STT1M10345 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846065, line_number=1, item_number=505-0-PK48 (order_date=2026-06-01, customer_account=7125)
    sales_order_number=ORD00846066, line_number=1, item_number=MSG242WH04 (order_date=2026-06-01, customer_account=9303)
    sales_order_number=ORD00846067, line_number=1, item_number=RTFTV62620 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846068, line_number=1, item_number=ANFTMCFE12 (order_date=2026-06-01, customer_account=9303)
    sales_order_number=ORD00846069, line_number=1, item_number=RDCLNGD486 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846070, line_number=2, item_number=RM1830WL12 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846070, line_number=1, item_number=RM1830CP12 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846071, line_number=1, item_number=BECS36GN12 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846072, line_number=1, item_number=CSTD27DG06 (order_date=2026-06-01, customer_account=7025)
    sales_order_number=ORD00846073, line_number=1, item_number=DRVL14GW12 (order_date=2026-06-01, customer_account=9022)
    sales_order_number=ORD00846074, line_number=1, item_number=LBTS36BL12 (order_date=2026-06-01, customer_account=9022)
    sales_order_number=ORD00846075, line_number=1, item_number=AF2039GY12 (order_date=2026-06-01, customer_account=9022)
    sales_order_number=ORD00846076, line_number=1, item_number=MSG234WH06 (order_date=2026-06-01, customer_account=7125)
    sales_order_number=ORD00846076, line_number=2, item_number=MSG234WH06 (order_date=2026-06-01, customer_account=7125)
    sales_order_number=ORD00846077, line_number=1, item_number=MSG234WH06 (order_date=2026-06-01, customer_account=7125)
    sales_order_number=ORD00846078, line_number=3, item_number=FTVWD23120 (order_date=2026-06-01, customer_account=7125)
    sales_order_number=ORD00846078, line_number=1, item_number=FTVWD23120 (order_date=2026-06-01, customer_account=7125)
    sales_order_number=ORD00846078, line_number=4, item_number=FTVWD23120 (order_date=2026-06-01, customer_account=7125)
    sales_order_number=ORD00846078, line_number=2, item_number=FTVWD23120 (order_date=2026-06-01, customer_account=7125)
    sales_order_number=ORD00846079, line_number=7, item_number=FTVMA40920 (order_date=2026-06-01, customer_account=9206)
    sales_order_number=ORD00846079, line_number=1, item_number=FTVMA40920 (order_date=2026-06-01, customer_account=9206)
    sales_order_number=ORD00846079, line_number=2, item_number=FTVMA40920 (order_date=2026-06-01, customer_account=9206)
    sales_order_number=ORD00846079, line_number=4, item_number=FTVMA40920 (order_date=2026-06-01, customer_account=9206)
    sales_order_number=ORD00846079, line_number=3, item_number=FTVMA40920 (order_date=2026-06-01, customer_account=9206)
    ... +217 more
  Extra in /test only (354):
    sales_order_number=ORD00867172, line_number=1, item_number=MSG234WH06 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867171, line_number=1, item_number=HNVA14TN12 (order_date=2026-06-30, customer_account=1412)
    sales_order_number=ORD00867170, line_number=1, item_number=MFMTMABR24 (order_date=2026-06-30, customer_account=1412)
    sales_order_number=ORD00867169, line_number=1, item_number=WRM1830LT6 (order_date=2026-06-30, customer_account=1412)
    sales_order_number=ORD00867168, line_number=1, item_number=DMCS36ML12 (order_date=2026-06-30, customer_account=1412)
    sales_order_number=ORD00867168, line_number=2, item_number=BECS36GN12 (order_date=2026-06-30, customer_account=1412)
    sales_order_number=ORD00867167, line_number=1, item_number=LBTS36BL12 (order_date=2026-06-30, customer_account=1412)
    sales_order_number=ORD00867166, line_number=1, item_number=MFMTMANY24 (order_date=2026-06-30, customer_account=1412)
    sales_order_number=ORD00867165, line_number=1, item_number=280-0-PK12 (order_date=2026-06-30, customer_account=1412)
    sales_order_number=ORD00867164, line_number=2, item_number=WRM1830IW6 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867164, line_number=3, item_number=WRM1830IW6 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867164, line_number=1, item_number=WRM1830IW6 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867163, line_number=1, item_number=TOVYELBK04 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867162, line_number=1, item_number=MSG223WD06 (order_date=2026-06-30, customer_account=7025)
    sales_order_number=ORD00867161, line_number=2, item_number=MSG236GY06 (order_date=2026-06-30, customer_account=7025)
    sales_order_number=ORD00867161, line_number=1, item_number=MSG232GY06 (order_date=2026-06-30, customer_account=7025)
    sales_order_number=ORD00867160, line_number=1, item_number=TRL376WH12 (order_date=2026-06-30, customer_account=7025)
    sales_order_number=ORD00867159, line_number=1, item_number=RDMRGL2806 (order_date=2026-06-30, customer_account=7025)
    sales_order_number=ORD00867158, line_number=1, item_number=MSG232WH06 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867157, line_number=1, item_number=MSG247WH04 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867156, line_number=1, item_number=MSG258WH04 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867155, line_number=1, item_number=MSG2237AL6 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867154, line_number=1, item_number=MSG258WH04 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867153, line_number=1, item_number=MSG2297AL6 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867152, line_number=1, item_number=MSG242WH04 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867151, line_number=3, item_number=TRL376WH12 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867151, line_number=1, item_number=TRL376WH12 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867151, line_number=2, item_number=TRL376WH12 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867150, line_number=2, item_number=415-0-PK12 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867150, line_number=3, item_number=415-0-PK12 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867150, line_number=1, item_number=420-0-PK12 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867149, line_number=1, item_number=MSG229BK06 (order_date=2026-06-30, customer_account=7125)
    sales_order_number=ORD00867148, line_number=1, item_number=MSG245WH04 (order_date=2026-06-30, customer_account=7025)
    sales_order_number=ORD00867147, line_number=1, item_number=DSG234WH06 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867146, line_number=1, item_number=MSG252WH04 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867145, line_number=1, item_number=MSG236WD06 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867144, line_number=1, item_number=DSG239BK04 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867143, line_number=1, item_number=MSG226GY06 (order_date=2026-06-30, customer_account=9303)
    sales_order_number=ORD00867142, line_number=1, item_number=SOCO48WD06 (order_date=2026-06-30, customer_account=9206)
    sales_order_number=ORD00867141, line_number=1, item_number=WRM1830IW6 (order_date=2026-06-30, customer_account=1412)
    ... +314 more
  Value diffs (76517):
    sales_order_number=ORD00846201, line_number=1, item_number=MSG230AL06 | qty_released: live=0 test=1
    sales_order_number=ORD00846201, line_number=1, item_number=MSG230AL06 | released_dollars: live=0 test=11.7500
    sales_order_number=ORD00846202, line_number=1, item_number=CIPV14ST12 | qty_released: live=0 test=2
    sales_order_number=ORD00846202, line_number=1, item_number=CIPV14ST12 | released_dollars: live=0 test=14.7400
    sales_order_number=ORD00846203, line_number=1, item_number=ANFTMLMD12 | qty_released: live=0 test=1
    sales_order_number=ORD00846203, line_number=1, item_number=ANFTMLMD12 | released_dollars: live=0 test=11.2200
    sales_order_number=ORD00846204, line_number=1, item_number=RDMNBK6606 | qty_released: live=0 test=1
    sales_order_number=ORD00846204, line_number=1, item_number=RDMNBK6606 | released_dollars: live=0 test=13.3500
    sales_order_number=ORD00846205, line_number=1, item_number=WRM1830DI6 | qty_released: live=0 test=1
    sales_order_number=ORD00846205, line_number=1, item_number=WRM1830DI6 | released_dollars: live=0 test=9.3300
    sales_order_number=ORD00846206, line_number=1, item_number=WRM1830DI6 | qty_released: live=0 test=1
    sales_order_number=ORD00846206, line_number=1, item_number=WRM1830DI6 | released_dollars: live=0 test=9.3300
    sales_order_number=ORD00846207, line_number=1, item_number=WRM1830FS6 | qty_released: live=0 test=1
    sales_order_number=ORD00846207, line_number=1, item_number=WRM1830FS6 | released_dollars: live=0 test=9.3300
    sales_order_number=ORD00846208, line_number=1, item_number=ANFTMCUC12 | qty_released: live=0 test=1
    sales_order_number=ORD00846208, line_number=1, item_number=ANFTMCUC12 | released_dollars: live=0 test=11.2200
    sales_order_number=ORD00846209, line_number=1, item_number=MSG2584BK4 | qty_released: live=0 test=1
    sales_order_number=ORD00846209, line_number=1, item_number=MSG2584BK4 | released_dollars: live=0 test=17.5700
    sales_order_number=ORD00846210, line_number=1, item_number=FTVMA45045 | qty_released: live=0 test=1
    sales_order_number=ORD00846210, line_number=1, item_number=FTVMA45045 | released_dollars: live=0 test=21.1900
    sales_order_number=ORD00846211, line_number=1, item_number=STP2.0RG10 | qty_released: live=0 test=1
    sales_order_number=ORD00846211, line_number=1, item_number=STP2.0RG10 | released_dollars: live=0 test=18.6800
    sales_order_number=ORD00846212, line_number=1, item_number=SOCO72WD06 | qty_released: live=0 test=1
    sales_order_number=ORD00846212, line_number=1, item_number=SOCO72WD06 | released_dollars: live=0 test=19.3200
    sales_order_number=ORD00846213, line_number=1, item_number=RTFTV62220 | qty_released: live=0 test=1
    sales_order_number=ORD00846213, line_number=1, item_number=RTFTV62220 | released_dollars: live=0 test=16.9100
    sales_order_number=ORD00846214, line_number=1, item_number=DSG232AL06 | qty_released: live=0 test=4
    sales_order_number=ORD00846214, line_number=1, item_number=DSG232AL06 | released_dollars: live=0 test=53.3200
    sales_order_number=ORD00846215, line_number=1, item_number=DRVL14MT12 | qty_released: live=0 test=2
    sales_order_number=ORD00846215, line_number=1, item_number=DRVL14MT12 | released_dollars: live=0 test=13.1200
    sales_order_number=ORD00846216, line_number=1, item_number=OMTU63BL06 | qty_released: live=0 test=1
    sales_order_number=ORD00846216, line_number=1, item_number=OMTU63BL06 | released_dollars: live=0 test=11.2900
    sales_order_number=ORD00846217, line_number=1, item_number=DSG232BK06 | qty_released: live=0 test=1
    sales_order_number=ORD00846217, line_number=1, item_number=DSG232BK06 | released_dollars: live=0 test=14.1000
    sales_order_number=ORD00846218, line_number=1, item_number=TRS736WH06 | qty_released: live=0 test=1
    sales_order_number=ORD00846218, line_number=1, item_number=TRS736WH06 | released_dollars: live=0 test=16.7700
    sales_order_number=ORD00846219, line_number=1, item_number=PLZFT80420 | qty_released: live=0 test=10
    sales_order_number=ORD00846219, line_number=1, item_number=PLZFT80420 | released_dollars: live=0 test=398
    sales_order_number=ORD00846220, line_number=1, item_number=DSG227AL06 | qty_released: live=0 test=1
    sales_order_number=ORD00846220, line_number=1, item_number=DSG227AL06 | released_dollars: live=0 test=13.2000
    ... +76477 more
  Soft/cosmetic text diffs (not failing): 41
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
