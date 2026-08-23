# MKolko real gaps (sort_number excluded)

## Coverage

Live accounts missing on /test (all 12 months unless noted):
- 5503 (12 month tabs)
- 9424 (12 month tabs)
- 6753 (12 month tabs)
- 2116 (12 month tabs)
- 3302865 (12 month tabs)

Extra on /test only:
- 516 (12 month tabs)

## Money / value gaps

- Cell diffs with abs <= .05 (pennies): **877**
- Larger or non-numeric cell diffs: **6080**

### Hot columns (count, sum of abs diffs)

- this_year_to_last_year_ytd_full_year: 1332 cells, sum abs 
- sales_year_to_date_2025: 1236 cells, sum abs 
- this_year_to_last_year_ytd: 1160 cells, sum abs 
- sales_year_to_date_2026: 768 cells, sum abs 
- this_year_to_last_year: 370 cells, sum abs 
- sales_2025_jan_thru_december: 103 cells, sum abs 
- sales_2025_jan_thru_november: 102 cells, sum abs 
- sales_2025_jan_thru_october: 99 cells, sum abs 
- sales_2025_jan_thru_august: 94 cells, sum abs 
- sales_2025_jan_thru_september: 94 cells, sum abs 
- sales_2025_jan_thru_july: 92 cells, sum abs 
- sales_2025_jan_thru_june: 87 cells, sum abs 

### Biggest accounts by sum abs gap

- 8023 Goodgram: sum abs  across 96 cell diffs
- 6639 DEE II STORES: sum abs  across 60 cell diffs
- 2730 VANDA SALES CORP: sum abs  across 88 cell diffs
- 8087 Statewide Supply: sum abs  across 79 cell diffs
- 3050 ADVANTAGE WHOLESALE SUPPLY: sum abs  across 62 cell diffs
- 557 CORNER HARDWARE & PAINT CENTER: sum abs  across 60 cell diffs
- 6179 J & S SUPPLY: sum abs  across 52 cell diffs
- 3043 VALUE ZONE STORE #1: sum abs  across 78 cell diffs
- 5102 SAVE SMART (STORES): sum abs  across 83 cell diffs
- 6336 COOK BROTHERS, INC: sum abs  across 48 cell diffs
- 472 CEE & CEE-331 fordham: sum abs  across 65 cell diffs
- 175 B. E. ATLAS CO: sum abs  across 76 cell diffs
- 9025 VALUE ZONE #10 (Newark): sum abs  across 78 cell diffs
- 6345 MINI-MAX: sum abs  across 83 cell diffs
- 3057 CS BROWN: sum abs  across 54 cell diffs

### Largest single cell gaps

- **Jan** 8023 Goodgram / sales_year_to_date_2025: live=419798.21 test=261708.24 (abs 158089.97000000003)
- **Jan** 8023 Goodgram / this_year_to_last_year_ytd_full_year: live=-244515.7 test=-91271.65 (abs 153244.05000000002)
- **Jan** 8023 Goodgram / sales_january_2025: live=73023.27 test=0 (abs 73023.27)
- **Jan** 8023 Goodgram / sales_2025_jan_thru_january: live=73023.27 test=0 (abs 73023.27)
- **Jan** 8023 Goodgram / this_year_to_last_year_ytd: live=-16703.81 test=56319.41 (abs 73023.22)
- **Jan** 8023 Goodgram / this_year_to_last_year: live=-16703.81 test=56319.41 (abs 73023.22)
- **Jan** 472 CEE & CEE-331 fordham / sales_year_to_date_2025: live=38705.74 test=30446.9 (abs 8258.839999999997)
- **Jan** 6219 BUDGET MAINT AND JANITORIAL SUPPLY / sales_year_to_date_2025: live=24103.38 test=18341.95 (abs 5761.43)
- **Jan** 6219 BUDGET MAINT AND JANITORIAL SUPPLY / this_year_to_last_year_ytd_full_year: live=-13199.55 test=-7715.37 (abs 5484.179999999999)
- **Jan** 5194 K & S CURTAIN PLUS / sales_year_to_date_2025: live=75641.74 test=70569.18 (abs 5072.560000000012)
- **Jan** 5194 K & S CURTAIN PLUS / this_year_to_last_year_ytd_full_year: live=-42332.45 test=-37259.96 (abs 5072.489999999998)
- **Jan** 8023 Goodgram / sales_year_to_date_2026: live=175282.51 test=170436.59 (abs 4845.920000000013)
- **Jan** 395 BONDI DEPT STORE (BARGAIN TIME) / this_year_to_last_year_ytd_full_year: live=-3311.04 test=-399.87 (abs 2911.17)
- **Jan** 395 BONDI DEPT STORE (BARGAIN TIME) / sales_year_to_date_2025: live=10458.51 test=7547.98 (abs 2910.5300000000007)
- **Jan** 1978 MBA SUPPLY CO. / sales_year_to_date_2025: live=10160.52 test=8341.51 (abs 1819.0100000000002)
- **Jan** 1978 MBA SUPPLY CO. / this_year_to_last_year_ytd_full_year: live=2030.530000000001 test=3849.51 (abs 1818.979999999999)
- **Jan** 418 BROOKLYN WHOLESALE SUPPLY / this_year_to_last_year_ytd_full_year: live=282.2299999999996 test=1416.74 (abs 1134.5100000000004)
- **Jan** 418 BROOKLYN WHOLESALE SUPPLY / sales_year_to_date_2025: live=10002.68 test=8868.17 (abs 1134.5100000000002)
- **Jan** 6219 BUDGET MAINT AND JANITORIAL SUPPLY / sales_january_2025: live=1088.58 test=0 (abs 1088.58)
- **Jan** 6219 BUDGET MAINT AND JANITORIAL SUPPLY / sales_2025_jan_thru_january: live=1088.58 test=0 (abs 1088.58)
