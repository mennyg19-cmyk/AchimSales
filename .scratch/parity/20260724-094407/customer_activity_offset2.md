# Customer Activity recompare (2-row header offset)

**Total hard differences: 740**
Per sheet: All=MISSING_TEST, AGrossman=DIFF(51), BLevin=DIFF(87), HKaufman=DIFF(174), House=DIFF(23), Integrated=DIFF(8), JWeigand=DIFF(14), LCWalker=DIFF(8), MGrego=DIFF(154), MKolko=DIFF(174), PMazer=DIFF(4), REdwards=DIFF(10), Unassigned=DIFF(32)


- Live: `D:\Projects\Achim\AchimSales\.scratch\parity\20260724-094407\customer_activity__live.xlsx`
- Test: `D:\Projects\Achim\AchimSales\.scratch\parity\20260724-094407\customer_activity__test.xlsx`
- Method: detect header on each side; align data rows; drop /test-only Salesman col;
  match by Customer Account (not Sales Order Number).

## Structure check (`AGrossman`)
- Live header row index: **2** (0-based) → Excel row 3
- Test header row index: **0** (0-based) → Excel row 1
- Live first 3 rows: [('AGrossman - Customer Activity', None, None, None, None), (None, None, None, None, None), ('Customer Account', 'Customer Name', 'Last Order Date', 'PO #', 'Sales Order Number')]
- Test first 2 rows: [('Salesman', 'Customer Account', 'Customer Name', 'Last Order Date', 'PO #', 'Sales Order Number'), ('AGrossman', '6853', '123STORES, INC.  (DROP SHIP)', 'N/A', 'N/A', 'N/A')]
- Offset (live_header - test_header): **2**

## Per-sheet results

### All: MISSING on /test
### AGrossman: **DIFF** (hard=51)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=41 test=40 matched=40
- Missing on /test (1): ['Total (40 customers)']
- Value diffs (50), first 20:
  - acct=11103 | last_order_date: live='2025-07-09 15:35:15' test='07/10/2025'
  - acct=11184 | last_order_date: live='2026-07-15 12:22:49' test='07/17/2026'
  - acct=11535 | last_order_date: live='2026-05-26 15:41:27' test='05/29/2026'
  - acct=11598 | last_order_date: live='2026-05-28 16:09:26' test='06/02/2026'
  - acct=11600 | last_order_date: live='2026-07-22 16:59:49' test='07/13/2026'
  - acct=11600 | po_number: live='72417' test='70208'
  - acct=11600 | sales_order_number: live='ORD00882553' test='ORD00848079'
  - acct=11624 | last_order_date: live='2026-07-17 11:02:26' test='07/20/2026'
  - acct=2958707 | last_order_date: live='2026-07-22 17:12:17' test='07/23/2026'
  - acct=3378476 | last_order_date: live='2026-06-19 11:43:00' test='06/24/2026'
  - acct=3389173 | last_order_date: live='2026-03-19 10:14:43' test='03/25/2026'
  - acct=48800 | last_order_date: live='2026-07-24 06:11:25' test='07/23/2026'
  - acct=48800 | po_number: live='761757' test='759366'
  - acct=48800 | sales_order_number: live='ORD00883576' test='ORD00882961'
  - acct=48999 | last_order_date: live='2026-07-16 18:53:35' test='07/23/2026'
  - acct=5121 | last_order_date: live='2026-07-21 16:52:26' test='07/22/2026'
  - acct=7009 | last_order_date: live='2025-06-09 14:57:16' test='12/10/2025'
  - acct=7009 | po_number: live='3405198' test='N/A'
  - acct=7009 | sales_order_number: live='ORD00600032' test='TR-4421'
  - acct=7125 | last_order_date: live='2026-07-24 07:41:35' test='07/23/2026'
- last_order_date mismatch pairs: live=2026-07-24 test=2026-07-23×5, live=2025-07-09 test=2025-07-10×1, live=2026-07-15 test=2026-07-17×1, live=2026-05-26 test=2026-05-29×1, live=2026-05-28 test=2026-06-02×1, live=2026-07-22 test=2026-07-13×1, live=2026-07-17 test=2026-07-20×1, live=2026-07-22 test=2026-07-23×1
- Soft/cosmetic (name or date-format only): 26

### BLevin: **DIFF** (hard=87)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=115 test=114 matched=114
- Missing on /test (1): ['Total (114 customers)']
- Value diffs (86), first 20:
  - acct=1035 | last_order_date: live='N/A' test='04/01/2025'
  - acct=1035 | sales_order_number: live='N/A' test='TR-4266'
  - acct=1049 | last_order_date: live='2026-07-14 09:27:20' test='07/17/2026'
  - acct=1063 | last_order_date: live='2026-07-02 13:06:54' test='07/14/2026'
  - acct=1098 | last_order_date: live='2026-03-03 09:57:15' test='03/04/2026'
  - acct=11001 | last_order_date: live='2025-03-20 13:54:29' test='03/26/2025'
  - acct=11028 | last_order_date: live='2025-04-17 14:28:12' test='04/29/2025'
  - acct=1109 | last_order_date: live='2026-07-15 10:31:20' test='07/22/2026'
  - acct=11155 | last_order_date: live='2025-08-04 13:34:34' test='08/13/2025'
  - acct=11351 | last_order_date: live='2025-11-25 11:27:39' test='12/02/2025'
  - acct=11355 | last_order_date: live='2025-11-25 13:42:44' test='12/11/2025'
  - acct=11362 | last_order_date: live='2026-01-05 12:01:43' test='01/07/2026'
  - acct=11389 | last_order_date: live='2025-12-22 10:32:41' test='12/23/2025'
  - acct=1508 | last_order_date: live='2025-09-29 11:44:57' test='10/06/2025'
  - acct=1674 | last_order_date: live='2026-07-14 14:25:39' test='07/16/2026'
  - acct=1724 | last_order_date: live='2026-07-21 16:11:28' test='07/22/2026'
  - acct=174 | last_order_date: live='2026-05-25 12:19:03' test='05/26/2026'
  - acct=2467 | last_order_date: live='2025-03-24 09:08:03' test='03/26/2025'
  - acct=2722 | last_order_date: live='2026-01-22 14:50:36' test='01/30/2026'
  - acct=2806734 | last_order_date: live='2026-04-01 10:31:09' test='04/07/2026'
- last_order_date mismatch pairs: live=2026-06-05 test=2026-06-10×2, live=2025-11-10 test=2025-11-19×2, live=N/A test=2025-04-01×1, live=2026-07-14 test=2026-07-17×1, live=2026-07-02 test=2026-07-14×1, live=2026-03-03 test=2026-03-04×1, live=2025-03-20 test=2025-03-26×1, live=2025-04-17 test=2025-04-29×1
- Soft/cosmetic (name or date-format only): 33

### HKaufman: **DIFF** (hard=174)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=189 test=188 matched=188
- Missing on /test (1): ['Total (188 customers)']
- Value diffs (173), first 20:
  - acct=1076 | last_order_date: live='2025-11-21 11:28:23' test='12/05/2025'
  - acct=1099 | last_order_date: live='2025-10-13 12:01:13' test='10/22/2025'
  - acct=11047 | last_order_date: live='2025-09-25 14:28:10' test='11/20/2025'
  - acct=11077 | last_order_date: live='2026-06-29 13:50:31' test='07/10/2026'
  - acct=11082 | last_order_date: live='2025-06-23 13:45:40' test='06/30/2025'
  - acct=11162 | last_order_date: live='2026-02-24 12:25:42' test='03/11/2026'
  - acct=11191 | last_order_date: live='2025-11-11 11:59:46' test='11/21/2025'
  - acct=11228 | last_order_date: live='2025-09-11 11:24:27' test='10/01/2025'
  - acct=11282 | last_order_date: live='2026-06-08 13:28:42' test='06/17/2026'
  - acct=11372 | last_order_date: live='2025-12-12 11:36:15' test='12/19/2025'
  - acct=11379 | last_order_date: live='2026-06-08 12:06:03' test='06/10/2026'
  - acct=11425 | last_order_date: live='2026-01-09 14:03:54' test='01/12/2026'
  - acct=11450 | last_order_date: live='2026-01-26 12:48:51' test='02/06/2026'
  - acct=11475 | last_order_date: live='2026-02-16 15:15:29' test='05/11/2026'
  - acct=11578 | last_order_date: live='2026-05-11 14:39:42' test='05/13/2026'
  - acct=11594 | last_order_date: live='2026-06-03 17:05:57' test='06/05/2026'
  - acct=11596 | last_order_date: live='2026-05-27 11:37:59' test='06/04/2026'
  - acct=1342062 | last_order_date: live='2026-03-18 14:36:37' test='03/30/2026'
  - acct=1342062 | po_number: live='1303182601' test='N/A'
  - acct=1342062 | sales_order_number: live='ORD00787841' test='TR-4483'
- last_order_date mismatch pairs: live=2026-07-20 test=2026-07-23×2, live=2026-07-15 test=2026-07-16×2, live=2026-02-10 test=2026-02-19×2, live=2025-11-21 test=2025-12-05×1, live=2025-10-13 test=2025-10-22×1, live=2025-09-25 test=2025-11-20×1, live=2026-06-29 test=2026-07-10×1, live=2025-06-23 test=2025-06-30×1
- Soft/cosmetic (name or date-format only): 95

### House: **DIFF** (hard=23)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=24 test=23 matched=23
- Missing on /test (1): ['Total (23 customers)']
- Value diffs (22), first 20:
  - acct=11027 | last_order_date: live='2025-06-04 10:58:08' test='06/05/2025'
  - acct=11030 | last_order_date: live='2025-04-22 13:39:40' test='04/24/2025'
  - acct=11160 | last_order_date: live='2025-08-06 14:49:09' test='12/24/2025'
  - acct=11560 | last_order_date: live='2026-05-21 14:44:38' test='06/03/2026'
  - acct=11568 | last_order_date: live='2026-04-30 16:20:44' test='05/01/2026'
  - acct=1457 | last_order_date: live='2026-01-12 13:31:41' test='01/14/2026'
  - acct=148 | last_order_date: live='2026-04-21 13:36:41' test='04/22/2026'
  - acct=2354986 | last_order_date: live='2026-05-14 11:50:09' test='04/15/2026'
  - acct=2354986 | po_number: live='2305142601' test='2304152601'
  - acct=2354986 | sales_order_number: live='ORD00833298' test='ORD00810691'
  - acct=2593326 | last_order_date: live='2025-09-25 15:07:02' test='N/A'
  - acct=2593326 | po_number: live='TEST263' test='N/A'
  - acct=2593326 | sales_order_number: live='ORD00667425' test='N/A'
  - acct=3183710 | po_number: live='' test='N/A'
  - acct=5334 | last_order_date: live='2025-07-21 09:25:44' test='04/09/2025'
  - acct=5334 | po_number: live='CBSAMPLES72125' test='SAMPLES4225'
  - acct=5334 | sales_order_number: live='ORD00625635' test='ORD00553447'
  - acct=6934 | last_order_date: live='2025-05-13 13:10:42' test='05/30/2025'
  - acct=ALEJANDRO CRUZ | last_order_date: live='2025-02-03 13:36:58' test='N/A'
  - acct=ALEJANDRO CRUZ | po_number: live='ACRUZ2325' test='N/A'
- last_order_date mismatch pairs: live=2025-06-04 test=2025-06-05×1, live=2025-04-22 test=2025-04-24×1, live=2025-08-06 test=2025-12-24×1, live=2026-05-21 test=2026-06-03×1, live=2026-04-30 test=2026-05-01×1, live=2026-01-12 test=2026-01-14×1, live=2026-04-21 test=2026-04-22×1, live=2026-05-14 test=2026-04-15×1
- Soft/cosmetic (name or date-format only): 13

### Integrated: **DIFF** (hard=8)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=5 test=4 matched=4
- Missing on /test (1): ['Total (4 customers)']
- Value diffs (7), first 20:
  - acct=2815509 | last_order_date: live='2026-04-10 13:33:28' test='04/14/2026'
  - acct=7025 | last_order_date: live='2026-07-24 09:41:11' test='07/23/2026'
  - acct=7025 | po_number: live='33562012' test='73755166'
  - acct=7025 | sales_order_number: live='ORD00883606' test='ORD00883170'
  - acct=9206 | last_order_date: live='2026-07-24 09:41:19' test='07/23/2026'
  - acct=9206 | po_number: live='413869517' test='413823290'
  - acct=9206 | sales_order_number: live='ORD00883607' test='ORD00883181'
- last_order_date mismatch pairs: live=2026-07-24 test=2026-07-23×2, live=2026-04-10 test=2026-04-14×1

### JWeigand: **DIFF** (hard=14)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=8 test=7 matched=7
- Missing on /test (1): ['Total (7 customers)']
- Value diffs (13), first 20:
  - acct=1412 | last_order_date: live='2026-07-24 08:51:10' test='07/23/2026'
  - acct=1412 | po_number: live='6723639143_1' test='6723528437_1'
  - acct=1412 | sales_order_number: live='ORD00883593' test='ORD00883178'
  - acct=5256 | last_order_date: live='2025-04-10 15:32:13' test='05/05/2025'
  - acct=6123 | last_order_date: live='2026-07-15 10:26:10' test='07/06/2026'
  - acct=6123 | po_number: live='7CL486156' test='72kf'
  - acct=6123 | sales_order_number: live='ORD00877419' test='ORD00868169'
  - acct=8008 | last_order_date: live='2026-07-10 13:22:22' test='07/17/2026'
  - acct=8008 | po_number: live='8851000' test='8819538'
  - acct=8008 | sales_order_number: live='ORD00873723' test='ORD00846679'
  - acct=9188 | last_order_date: live='2026-07-24 04:52:20' test='07/23/2026'
  - acct=9188 | po_number: live='8861134' test='8860855'
  - acct=9188 | sales_order_number: live='ORD00883560' test='ORD00883145'
- last_order_date mismatch pairs: live=2026-07-24 test=2026-07-23×2, live=2025-04-10 test=2025-05-05×1, live=2026-07-15 test=2026-07-06×1, live=2026-07-10 test=2026-07-17×1
- Soft/cosmetic (name or date-format only): 8

### LCWalker: **DIFF** (hard=8)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=6 test=5 matched=5
- Missing on /test (1): ['Total (5 customers)']
- Value diffs (7), first 20:
  - acct=11036 | last_order_date: live='2025-05-01 14:56:38' test='06/30/2025'
  - acct=11401 | last_order_date: live='2026-01-05 16:11:32' test='02/03/2026'
  - acct=2942414 | last_order_date: live='2025-01-22 16:16:07' test='02/20/2025'
  - acct=3538 | last_order_date: live='2026-07-01 13:06:38' test='07/16/2026'
  - acct=8276 | last_order_date: live='2026-07-16 14:36:28' test='06/01/2026'
  - acct=8276 | po_number: live='071426' test='AML0521'
  - acct=8276 | sales_order_number: live='ORD00878279' test='ORD00838846'
- last_order_date mismatch pairs: live=2025-05-01 test=2025-06-30×1, live=2026-01-05 test=2026-02-03×1, live=2025-01-22 test=2025-02-20×1, live=2026-07-01 test=2026-07-16×1, live=2026-07-16 test=2026-06-01×1
- Soft/cosmetic (name or date-format only): 3

### MGrego: **DIFF** (hard=154)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=178 test=177 matched=177
- Missing on /test (1): ['Total (177 customers)']
- Value diffs (153), first 20:
  - acct=1081 | last_order_date: live='2025-02-18 09:38:21' test='04/28/2025'
  - acct=11015 | last_order_date: live='2026-07-01 14:46:23' test='07/15/2026'
  - acct=11016 | last_order_date: live='2025-04-07 13:01:17' test='08/26/2025'
  - acct=11016 | po_number: live='BD472025' test='UNPAID RETURN'
  - acct=11016 | sales_order_number: live='ORD00556950' test='ORD00608643'
  - acct=11017 | last_order_date: live='2025-10-06 10:25:48' test='10/29/2025'
  - acct=11025 | last_order_date: live='2025-04-16 15:00:30' test='05/01/2025'
  - acct=11025 | po_number: live='' test='N/A'
  - acct=11025 | sales_order_number: live='ORD00562869' test='TR-4347'
  - acct=11038 | last_order_date: live='2025-11-17 10:22:09' test='11/25/2025'
  - acct=11042 | last_order_date: live='2026-04-06 12:55:20' test='04/13/2026'
  - acct=11053 | last_order_date: live='2025-05-14 14:43:49' test='05/21/2025'
  - acct=11054 | last_order_date: live='2025-05-14 16:12:27' test='05/23/2025'
  - acct=11056 | last_order_date: live='2026-04-23 10:00:50' test='04/28/2026'
  - acct=11083 | last_order_date: live='2026-03-11 11:44:39' test='03/23/2026'
  - acct=11129 | last_order_date: live='2025-07-23 15:20:03' test='08/01/2025'
  - acct=11167 | last_order_date: live='2025-11-14 10:16:50' test='11/20/2025'
  - acct=11175 | last_order_date: live='2025-08-13 11:43:47' test='08/14/2025'
  - acct=11175 | po_number: live='' test='N/A'
  - acct=11187 | last_order_date: live='2025-10-23 20:52:23' test='08/29/2025'
- last_order_date mismatch pairs: live=2026-04-06 test=2026-04-13×2, live=2026-04-23 test=2026-04-28×2, live=2025-11-12 test=2025-11-19×2, live=2026-03-23 test=2026-03-31×2, live=2026-05-01 test=2026-05-11×2, live=2025-02-18 test=2025-04-28×1, live=2026-07-01 test=2026-07-15×1, live=2025-04-07 test=2025-08-26×1
- Soft/cosmetic (name or date-format only): 38

### MKolko: **DIFF** (hard=174)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=168 test=167 matched=167
- Missing on /test (1): ['Total (167 customers)']
- Value diffs (173), first 20:
  - acct=11002 | last_order_date: live='2025-03-20 13:33:11' test='03/24/2025'
  - acct=11003 | last_order_date: live='2025-03-25 09:51:28' test='03/31/2025'
  - acct=11019 | last_order_date: live='2025-04-10 10:24:13' test='04/22/2025'
  - acct=11020 | last_order_date: live='2025-04-10 09:39:27' test='04/15/2025'
  - acct=11031 | last_order_date: live='2025-07-11 12:39:36' test='07/24/2025'
  - acct=11034 | last_order_date: live='2025-04-30 13:47:01' test='05/16/2025'
  - acct=11057 | last_order_date: live='2026-07-21 16:52:38' test='05/28/2025'
  - acct=11057 | po_number: live='0007212602' test='ADDON0005192501'
  - acct=11057 | sales_order_number: live='ORD00881804' test='ORD00589206'
  - acct=11100 | last_order_date: live='2026-04-13 14:04:45' test='04/22/2026'
  - acct=11190 | last_order_date: live='2026-07-20 15:05:05' test='07/23/2026'
  - acct=11233 | last_order_date: live='2025-09-16 15:29:13' test='09/30/2025'
  - acct=11247 | last_order_date: live='2026-05-06 15:52:23' test='05/14/2026'
  - acct=11416 | last_order_date: live='2026-05-14 12:32:39' test='05/19/2026'
  - acct=11482 | last_order_date: live='2026-04-24 12:01:51' test='04/30/2026'
  - acct=11540 | last_order_date: live='2026-06-30 18:20:53' test='07/06/2026'
  - acct=11569 | last_order_date: live='2026-06-22 10:42:16' test='06/23/2026'
  - acct=11612 | last_order_date: live='2026-06-30 14:31:31' test='07/02/2026'
  - acct=11616 | last_order_date: live='2026-07-06 13:19:07' test='07/08/2026'
  - acct=11621 | last_order_date: live='2026-07-14 14:11:29' test='07/16/2026'
- last_order_date mismatch pairs: live=2026-07-14 test=2026-07-16×4, live=2026-06-30 test=2026-07-02×3, live=2026-05-11 test=2026-05-18×3, live=2026-06-24 test=2026-06-30×3, live=2026-05-04 test=2026-05-15×3, live=2026-05-06 test=2026-05-14×2, live=2026-07-21 test=N/A×2, live=2026-07-16 test=2026-07-17×2
- Soft/cosmetic (name or date-format only): 75

### PMazer: **DIFF** (hard=4)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=4 test=3 matched=3
- Missing on /test (1): ['Total (3 customers)']
- Value diffs (3), first 20:
  - acct=6940 | last_order_date: live='2026-04-15 11:33:36' test='04/30/2026'
  - acct=7186 | last_order_date: live='2026-05-25 11:05:57' test='05/29/2026'
  - acct=7193 | last_order_date: live='2026-07-20 17:51:47' test='07/22/2026'
- last_order_date mismatch pairs: live=2026-04-15 test=2026-04-30×1, live=2026-05-25 test=2026-05-29×1, live=2026-07-20 test=2026-07-22×1
- Soft/cosmetic (name or date-format only): 1

### REdwards: **DIFF** (hard=10)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=4 test=3 matched=3
- Missing on /test (1): ['Total (3 customers)']
- Value diffs (9), first 20:
  - acct=9300 | last_order_date: live='2026-07-20 05:24:24' test='07/23/2026'
  - acct=9300 | po_number: live='8QR62KQB' test='4P66CAXK'
  - acct=9300 | sales_order_number: live='ORD00880789' test='ORD00880771'
  - acct=9301 | last_order_date: live='2026-07-20 06:11:03' test='01/20/2026'
  - acct=9301 | po_number: live='8LJWMC1S' test='3TEKVG4P'
  - acct=9301 | sales_order_number: live='ORD00880810' test='ORD00726016'
  - acct=9303 | last_order_date: live='2026-07-24 09:41:25' test='07/23/2026'
  - acct=9303 | po_number: live='PfJJ3wfFS' test='PtXcNWs8S'
  - acct=9303 | sales_order_number: live='ORD00883608' test='ORD00883182'
- last_order_date mismatch pairs: live=2026-07-20 test=2026-07-23×1, live=2026-07-20 test=2026-01-20×1, live=2026-07-24 test=2026-07-23×1
- Soft/cosmetic (name or date-format only): 1

### Unassigned: **DIFF** (hard=32)
- Header offset: live row 3 vs test row 1 (delta=2)
- Rows: live=51 test=50 matched=50
- Missing on /test (1): ['Total (50 customers)']
- Value diffs (31), first 20:
  - acct=11005 | last_order_date: live='N/A' test='05/18/2026'
  - acct=11005 | sales_order_number: live='N/A' test='TR-4502'
  - acct=11201 | last_order_date: live='2025-10-06 16:34:33' test='10/17/2025'
  - acct=11205 | last_order_date: live='2025-08-31 16:34:02' test='09/02/2025'
  - acct=11205 | po_number: live='' test='N/A'
  - acct=11229 | last_order_date: live='2025-09-12 14:08:19' test='09/17/2025'
  - acct=11239 | last_order_date: live='2026-07-02 13:20:08' test='07/06/2026'
  - acct=11373 | last_order_date: live='2025-12-11 12:03:03' test='12/24/2025'
  - acct=11454 | last_order_date: live='2026-01-28 15:31:23' test='01/29/2026'
  - acct=11454 | po_number: live='' test='N/A'
  - acct=11528 | last_order_date: live='2026-07-09 15:53:34' test='07/14/2026'
  - acct=11552 | last_order_date: live='2026-04-22 16:09:12' test='N/A'
  - acct=11552 | po_number: live='0004222601' test='N/A'
  - acct=11552 | sales_order_number: live='ORD00816868' test='N/A'
  - acct=11609 | last_order_date: live='2026-06-18 11:25:44' test='N/A'
  - acct=11609 | po_number: live='0006182601' test='N/A'
  - acct=11609 | sales_order_number: live='ORD00858403' test='N/A'
  - acct=125th 99 Inc. | last_order_date: live='2025-02-03 09:27:27' test='N/A'
  - acct=125th 99 Inc. | po_number: live='125th992325' test='N/A'
  - acct=125th 99 Inc. | sales_order_number: live='ORD00516214' test='N/A'
- last_order_date mismatch pairs: live=2025-02-03 test=N/A×2, live=N/A test=2026-05-18×1, live=2025-10-06 test=2025-10-17×1, live=2025-08-31 test=2025-09-02×1, live=2025-09-12 test=2025-09-17×1, live=2026-07-02 test=2026-07-06×1, live=2025-12-11 test=2025-12-24×1, live=2026-01-28 test=2026-01-29×1
- Soft/cosmetic (name or date-format only): 19
