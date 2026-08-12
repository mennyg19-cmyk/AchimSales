# Parity: salesman

- Params: `{}`
- Live file: `.scratch\parity\20260726-131548-salesman-master\salesman__live.xlsx`
- Test file: `.scratch\parity\20260726-131548-salesman-master\salesman__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **27530**
- Missing sheets in /test: (none)
- Extra sheets in /test (ignored): (none)
- Per sheet: Jan=DIFF(2234), Feb=DIFF(2069), Mar=DIFF(2201), Apr=DIFF(2313), May=DIFF(2326), Jun=DIFF(2392), Jul=DIFF(2352), Aug=DIFF(2329), Sep=DIFF(2304), Oct=DIFF(2339), Nov=DIFF(2329), Dec=DIFF(2342)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260726-131548-salesman-master\salesman__live.xlsx vs .scratch\parity\20260726-131548-salesman-master\salesman__test.xlsx
Hard differences: 27530
Result: DIFFERENCES FOUND

## Sheet: Jan [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, this_year_to_last_year_ytd_full_year=151, sales_year_to_date_2026=149, sales_2025_jan_thru_january=102
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1226):
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_january: live=403.6000 test=3836.1000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_january: live=1983.7500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_january_2025: live=403.6000 test=3836.1000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_january_2026: live=1983.7500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year: live=3.9151 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=3.9151 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2025_jan_thru_january: live=0 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_january_2025: live=0 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year: live=0 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd: live=0 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_january: live=0 test=3165.3400
    customer_name=Blake Food Mart Inc., salesman_code= | sales_january_2025: live=0 test=3165.3400
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2025: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2026: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sort_number: live=40 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | this_year_to_last_year: live=0 test=-1
    customer_name=Blake Food Mart Inc., salesman_code= | this_year_to_last_year_ytd: live=0 test=-1
    customer_name=Blake Food Mart Inc., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1522 test=-1
    customer_name=Max Deals, salesman_code= | sales_2025_jan_thru_january: live=0 test=1680
    customer_name=Max Deals, salesman_code= | sales_january_2025: live=0 test=1680
    customer_name=Max Deals, salesman_code= | sales_year_to_date_2025: live=1187.9300 test=1520
    customer_name=Max Deals, salesman_code= | sales_year_to_date_2026: live=1260 test=0
    customer_name=Max Deals, salesman_code= | sort_number: live=42 test=None
    ... +1176 more

## Sheet: Feb [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, this_year_to_last_year_ytd_full_year=151, sales_year_to_date_2026=149, sales_2025_jan_thru_february=102
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1061):
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_february: live=1684 test=5116.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_february: live=2197.6500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_february_2026: live=213.9000 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year: live=-0.8329 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=0.3050 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2025_jan_thru_february: live=0 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd: live=0 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_february: live=0 test=3165.3400
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2025: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2026: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sort_number: live=40 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | this_year_to_last_year_ytd: live=0 test=-1
    customer_name=Blake Food Mart Inc., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1522 test=-1
    customer_name=Max Deals, salesman_code= | sales_2025_jan_thru_february: live=0 test=1680
    customer_name=Max Deals, salesman_code= | sales_year_to_date_2025: live=1187.9300 test=1520
    customer_name=Max Deals, salesman_code= | sales_year_to_date_2026: live=1260 test=0
    customer_name=Max Deals, salesman_code= | sort_number: live=42 test=None
    customer_name=Max Deals, salesman_code= | this_year_to_last_year_ytd: live=0 test=-1
    customer_name=Max Deals, salesman_code= | this_year_to_last_year_ytd_full_year: live=0.0607 test=-1
    customer_name=Max Deals (Union Avenue), salesman_code= | sales_2025_jan_thru_february: live=0 test=1696
    customer_name=Max Deals (Union Avenue), salesman_code= | sales_2026_jan_thru_february: live=2767.5700 test=0
    customer_name=Max Deals (Union Avenue), salesman_code= | sales_year_to_date_2025: live=0 test=1696
    customer_name=Max Deals (Union Avenue), salesman_code= | sales_year_to_date_2026: live=2692.6700 test=-74.9000
    ... +1011 more

## Sheet: Mar [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, this_year_to_last_year_ytd_full_year=151, sales_year_to_date_2026=149, this_year_to_last_year_ytd=111
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1193):
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_march: live=1684 test=5116.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_march: live=5542.1300 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_march_2026: live=3344.4800 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=2.2911 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_march: live=1950.1400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_march_2026: live=1950.1400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=0.8644 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_march: live=993.5400 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_march: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_march_2025: live=993.5400 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_march_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year: live=1.3977 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=1.3977 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_march_2025: live=1008 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_march: live=1678.4400 test=4843.7800
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2025: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2026: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sort_number: live=40 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1522 test=-1
    customer_name=Max Deals, salesman_code= | sales_2025_jan_thru_march: live=0 test=1680
    customer_name=Max Deals, salesman_code= | sales_year_to_date_2025: live=1187.9300 test=1520
    customer_name=Max Deals, salesman_code= | sales_year_to_date_2026: live=1260 test=0
    ... +1143 more

## Sheet: Apr [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, this_year_to_last_year_ytd_full_year=151, sales_year_to_date_2026=149, sales_2025_jan_thru_april=130
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1305):
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_2026_jan_thru_april: live=7718.4800 test=0
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_april_2026: live=7718.4800 test=0
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_april: live=3459.2000 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_april: live=5542.1300 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_april_2025: live=1775.2000 test=135
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=0.6021 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2025_jan_thru_april: live=2047 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_april: live=1950.1400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_april_2025: live=1001 test=0
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=-0.0473 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_april: live=993.5400 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_april: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=1.3977 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_april: live=1678.4400 test=4843.7800
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2026_jan_thru_april: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_april_2026: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2025: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2026: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sort_number: live=40 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | this_year_to_last_year_ytd: live=1.7775 test=-1
    customer_name=Blake Food Mart Inc., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1522 test=-1
    customer_name=Max Deals, salesman_code= | sales_2025_jan_thru_april: live=-160 test=1520
    ... +1255 more

## Sheet: May [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, this_year_to_last_year_ytd_full_year=151, sales_year_to_date_2026=149, sales_2025_jan_thru_may=139
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1318):
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2026_jan_thru_may: live=4872.0200 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_may_2026: live=4872.0200 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_2026_jan_thru_may: live=7718.4800 test=0
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_may: live=3994.6000 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_may: live=6829.3900 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_may_2025: live=535.4000 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_may_2026: live=1287.2600 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year: live=1.4043 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=0.7097 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2025_jan_thru_may: live=2047 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_may: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_may_2026: live=2693.3000 test=0
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=1.2684 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_may: live=993.5400 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_may: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=1.3977 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_may: live=4361.2000 test=4843.7800
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2026_jan_thru_may: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_may_2025: live=2682.7600 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2025: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2026: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sort_number: live=40 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | this_year_to_last_year: live=-1 test=0
    ... +1268 more

## Sheet: Jun [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, sales_2025_jan_thru_june=155, this_year_to_last_year_ytd_full_year=151, sales_year_to_date_2026=149
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1384):
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2026_jan_thru_june: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_2026_jan_thru_june: live=7718.3800 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_june: live=4419.6000 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_june: live=10098.8500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_june_2025: live=425 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_june_2026: live=3269.4600 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year: live=6.6928 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=1.2850 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2025_jan_thru_june: live=2047 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_june: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=1.2684 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_june: live=3023.8100 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_june: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_june_2025: live=2030.2700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=-0.2122 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2026_jan_thru_june: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_june_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd: live=0.6394 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_june: live=4361.2000 test=4843.7800
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2026_jan_thru_june: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2025: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2026: live=4661.8400 test=0
    ... +1334 more

## Sheet: Jul [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, sales_2025_jan_thru_july=166, this_year_to_last_year_ytd_full_year=151, this_year_to_last_year_ytd=151
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1344):
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2026_jan_thru_july: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_2026_jan_thru_july: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_july_2026: live=1150.3800 test=0
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_july: live=4419.6000 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_july: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_july_2026: live=2092.2000 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=1.7584 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2025_jan_thru_july: live=2047 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_july: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=1.2684 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_july: live=2830.2700 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_july: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=-0.1583 test=-1
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2026_jan_thru_july: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd: live=0.6394 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_2025_jan_thru_july: live=3576.1600 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sales_july_2025: live=1341.5000 test=0
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Home Threads Linden Inc., salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_july: live=4361.2000 test=4843.7800
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2026_jan_thru_july: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2025: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2026: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sort_number: live=40 test=None
    ... +1294 more

## Sheet: Aug [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, sales_2025_jan_thru_august=171, this_year_to_last_year_ytd_full_year=151, this_year_to_last_year_ytd=150
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1321):
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2026_jan_thru_august: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_2026_jan_thru_august: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_august: live=5923.8000 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_august: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_august_2025: live=1504.2000 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=1.0580 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2025_jan_thru_august: live=5410.8200 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_august: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_august_2025: live=3363.8200 test=0
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=-0.1418 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_august: live=2830.2700 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_august: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=-0.1583 test=-1
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2026_jan_thru_august: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd: live=0.6394 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_2025_jan_thru_august: live=3576.1600 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_august: live=4361.2000 test=4843.7800
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2026_jan_thru_august: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2025: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2026: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sort_number: live=40 test=None
    ... +1271 more

## Sheet: Sep [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, sales_2025_jan_thru_september=174, this_year_to_last_year_ytd_full_year=151, this_year_to_last_year_ytd=150
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1296):
    customer_name=Home Square, salesman_code= | sales_2025_jan_thru_september: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sales_september_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd: live=-1.7772 test=0
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2026_jan_thru_september: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_2026_jan_thru_september: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_september: live=5923.8000 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_september: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=1.0580 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2025_jan_thru_september: live=5410.8200 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_september: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=-0.1418 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_september: live=2830.2700 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_september: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=-0.1583 test=-1
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2026_jan_thru_september: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd: live=0.6394 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_2025_jan_thru_september: live=3576.1600 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_september: live=5498.6500 test=4843.7800
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2026_jan_thru_september: live=4661.8400 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_september_2025: live=1137.4500 test=0
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2025: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_year_to_date_2026: live=4661.8400 test=0
    ... +1246 more

## Sheet: Oct [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, sales_2025_jan_thru_october=181, this_year_to_last_year_ytd_full_year=151, this_year_to_last_year_ytd=149
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1331):
    customer_name=Home Square, salesman_code= | sales_2025_jan_thru_october: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd: live=-1.7772 test=0
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2025_jan_thru_october: live=5268.3800 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2026_jan_thru_october: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_october_2025: live=5268.3800 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd: live=-0.2827 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_2026_jan_thru_october: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_october: live=8361.0600 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_october: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_october_2025: live=2437.2600 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=0.4581 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2025_jan_thru_october: live=5410.8200 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_october: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=-0.1418 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_october: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_october: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_october_2025: live=2413.2200 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=-0.5457 test=-1
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2025_jan_thru_october: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2026_jan_thru_october: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_october_2025: live=1957.3000 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd: live=-0.4427 test=-1
    ... +1281 more

## Sheet: Nov [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_year_to_date_2025=186, sales_2025_jan_thru_november=183, this_year_to_last_year_ytd_full_year=151, this_year_to_last_year_ytd=149
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1321):
    customer_name=Home Square, salesman_code= | sales_2025_jan_thru_november: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd: live=-1.7772 test=0
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2025_jan_thru_november: live=5268.3800 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2026_jan_thru_november: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd: live=-0.2827 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_2026_jan_thru_november: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_november: live=9541.6500 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_november: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_november_2025: live=1180.5900 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=0.2777 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2025_jan_thru_november: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_november: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_november_2025: live=3409.7500 test=0
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=-0.4736 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_november: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_november: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=-0.5457 test=-1
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2025_jan_thru_november: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2026_jan_thru_november: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd: live=-0.4427 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_2025_jan_thru_november: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    ... +1271 more

## Sheet: Dec [DIFF]
  Row key: customer_name, salesman_code
  Rows live=559 test=915 matched=233
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 326 live row(s) missing on /test (58% of live rows).
    - 682 /test-only row(s) not on live (75% of /test rows).
    - Value diffs by column: sort_number=233, sales_2025_jan_thru_december=186, sales_year_to_date_2025=186, this_year_to_last_year_ytd=151, this_year_to_last_year_ytd_full_year=151
    - All sort_number diffs: /test is empty/zero, live has a value.
  Missing in /test (326):
    customer_name=MKolko, salesman_code=
    customer_name=CHURCH DISCOUNT STORE, salesman_code=
    customer_name=MAX DEALS BOSTON, salesman_code=
    customer_name=AMAZING FOOD MART, salesman_code=
    customer_name=SHERMAN DISCOUNT INC., salesman_code=
    customer_name=PARKSIDE BARGAINS, salesman_code=
    customer_name=SUTTER FOOD MART/SUTTER DOLLAR DISCOUNT, salesman_code=
    customer_name=BROADWAY FOOD MART, salesman_code=
    customer_name=AK DEPARTMENT CORP., salesman_code=
    customer_name=Extreme dept store #5, salesman_code=
    customer_name=MAX DEALS 1315 BOSTON, salesman_code=
    customer_name=198th ST DISC INC. (MAX DEALS), salesman_code=
    customer_name=MDN Retail Inc., salesman_code=
    customer_name=Telco Stores, salesman_code=
    customer_name=Max Deals Savings, salesman_code=
    customer_name=Max Deals (Fulton Food Deals), salesman_code=
    customer_name=Brighton Best 99 Cents Store, salesman_code=
    customer_name=99 Cent Days Inc., salesman_code=
    customer_name=LOT LESS CLOSEOUTS(HOME BASICS), salesman_code=
    customer_name=JACKIE'S DEPT STORE INC, salesman_code=
    customer_name=KENNEDY DEPARTMENT STORE, salesman_code=
    customer_name=LIBERTY DEPARTMENT STORE (MYRTLE), salesman_code=
    customer_name=LUCKY WINDOW PRODUCTS, salesman_code=
    customer_name=16TH AVENUE HOME CENTER INC, salesman_code=
    customer_name=B. E. ATLAS CO, salesman_code=
    customer_name=NOSTRAND PAINT & HARDWARE, salesman_code=
    customer_name=PARADISE DECORATORS, INC, salesman_code=
    customer_name=M & M DISCOUNT (CENTURY DISC), salesman_code=
    customer_name=SUPER DEAL STORES INC, salesman_code=
    customer_name=Dcon Discount Inc., salesman_code=
    customer_name=VANDA SALES CORP, salesman_code=
    customer_name=Home Threads Inc. NY, salesman_code=
    customer_name=WILHELM'S HOUSEWARE, salesman_code=
    customer_name=VALUE ZONE STORE #1, salesman_code=
    customer_name=DIRECT SUPPLIES WAREHOUSE INC, salesman_code=
    customer_name=AJ HOUSEWARES, salesman_code=
    customer_name=Broadway Home Threads, salesman_code=
    customer_name=Coney Island Food Mart Inc., salesman_code=
    customer_name=BONDI DEPT STORE (BARGAIN TIME), salesman_code=
    customer_name=CENTURY MAINTENANCE & SUPPLY CO, salesman_code=
    customer_name=BUDGET SALES CO, salesman_code=
    customer_name=CEE & CEE-149 st,, salesman_code=
    customer_name=CEE & CEE-331 fordham, salesman_code=
    customer_name=BARGAINLAND(2828 chrch), salesman_code=
    customer_name=CEE & CEE-100 fordham, salesman_code=
    customer_name=SAVE SMART (STORES), salesman_code=
    customer_name=COVENANT, salesman_code=
    customer_name=UNITED MAINTENANCE SUPPLIES, salesman_code=
    customer_name=99 CENT & DISCOUNT WORLD INC, salesman_code=
    customer_name=J. ALPERIN CO INC, salesman_code=
    ... +276 more
  Extra in /test only (682):
    customer_name=PARKSIDE BARGAINS (MAQDADY LLC), salesman_code=
    customer_name=Herschel Kaufman, salesman_code=
    customer_name=Kashika, salesman_code=
    customer_name=XS Merchandise, salesman_code=
    customer_name=Good's Store Distribution, salesman_code=
    customer_name=C & S Value Depot,Inc., salesman_code=
    customer_name=Joey'z Home And Beyond #1, salesman_code=
    customer_name=Jack L. Marcus, Inc., salesman_code=
    customer_name=Joey'z Shopping Spree #5, salesman_code=
    customer_name=Dream Decor Inc. #3, salesman_code=
    customer_name=Kennedy Department Store, salesman_code=
    customer_name=J. PICA & CIA INC., salesman_code=
    customer_name=KOHL'S, salesman_code=
    customer_name=Liberty Dept. Store (MYRTLE), salesman_code=
    customer_name=16th Avenue Home Center Inc., salesman_code=
    customer_name=M & S BARGAIN HUNTERS, salesman_code=
    customer_name=NEXT-GEN SUPPLY GROUP, salesman_code=
    customer_name=MAZER WHOLESALE & VALUELINE, salesman_code=
    customer_name=MILL SUPPLY CO.,INC., salesman_code=
    customer_name=B. E. ATLAS CO., salesman_code=
    customer_name=MASTERS LTD., salesman_code=
    customer_name=Joey'z Shopping Spree #6, salesman_code=
    customer_name=PARAMOUNT STORES, INC., salesman_code=
    customer_name=Swags Galore, salesman_code=
    customer_name=S & R Bargain Store, salesman_code=
    customer_name=M & M DISCOUNT  (CENTURY DISC), salesman_code=
    customer_name=Variety/Rose's, salesman_code=
    customer_name=GROSSM, MOSHE ARYEH, salesman_code=
    customer_name=Save On Fifth, salesman_code=
    customer_name=SHOPPERS WORLD(ELIZABETH STR), salesman_code=
    customer_name=Super Deal Stores Inc., salesman_code=
    customer_name=Smiles Linens,Inc., salesman_code=
    customer_name=Baruch Grossman's Shenanigans, salesman_code=
    customer_name=ZIPSHADE INDUSTRIAL (B.V.I.) CORP., salesman_code=
    customer_name=NANJING JINMING NEW DECORATIVE MATERIALS CO.,LTD., salesman_code=
    customer_name=ZHANGJIAGANG JUNXIN HOME BUILDING MATERIALS CO.,LTD, salesman_code=
    customer_name=VANDA SALES CORP., salesman_code=
    customer_name=Home Threads Inc. NY (MAX DEALS), salesman_code=
    customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=
    customer_name=ALL BLINDS CO., salesman_code=
    customer_name=P&M Curtains, salesman_code=
    customer_name=Wilhelm's Houseware, salesman_code=
    customer_name=SUPER DEAL, salesman_code=
    customer_name=Amber Worldwide LLC, salesman_code=
    customer_name=Antigua Home & Garden, salesman_code=
    customer_name=P&M Misc., salesman_code=
    customer_name=PARKE-BELL LTD. INC., salesman_code=
    customer_name=Columbus discount (Williamsbridge Dept.), salesman_code=
    customer_name=BERKOFF-FOX SUPPLY SOURCE, salesman_code=
    customer_name=BLINDS AMERICA, salesman_code=
    ... +632 more
  Value diffs (1334):
    customer_name=Home Square, salesman_code= | sales_2025_jan_thru_december: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sales_year_to_date_2025: live=1366.2000 test=0
    customer_name=Home Square, salesman_code= | sort_number: live=11 test=None
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd: live=-1.7772 test=0
    customer_name=Home Square, salesman_code= | this_year_to_last_year_ytd_full_year: live=-1.7772 test=0
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2025_jan_thru_december: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_2026_jan_thru_december: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2025: live=4617.8000 test=-650.5800
    customer_name=Value Queen (MAX DEALS), salesman_code= | sales_year_to_date_2026: live=3779.0200 test=-1093
    customer_name=Value Queen (MAX DEALS), salesman_code= | sort_number: live=14 test=None
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd: live=-0.1816 test=0.6800
    customer_name=Value Queen (MAX DEALS), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.1816 test=0.6800
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_2026_jan_thru_december: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sales_year_to_date_2026: live=8868.7600 test=-0.1000
    customer_name=Peoples of Inwood Corp., salesman_code= | sort_number: live=17 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2025_jan_thru_december: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_2026_jan_thru_december: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_december_2025: live=618.8700 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2025: live=10160.5200 test=5251.5000
    customer_name=MBA SUPPLY CO., salesman_code= | sales_year_to_date_2026: live=12191.0500 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | sort_number: live=31 test=None
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year: live=-1 test=0
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd: live=0.1998 test=-1
    customer_name=MBA SUPPLY CO., salesman_code= | this_year_to_last_year_ytd_full_year: live=0.1998 test=-1
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2025_jan_thru_december: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_2026_jan_thru_december: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2025: live=8820.5700 test=1046
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sales_year_to_date_2026: live=4643.4400 test=-46.8400
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | sort_number: live=34 test=None
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd: live=-0.4736 test=-1.0448
    customer_name=EXTREME DEPT.STORE #4, salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4736 test=-1.0448
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2025_jan_thru_december: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_2026_jan_thru_december: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2025: live=5243.4900 test=-193.5400
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sales_year_to_date_2026: live=2382.1700 test=0
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | sort_number: live=35 test=None
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd: live=-0.5457 test=-1
    customer_name=MAX DEALS (CHURCH AVE.), salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.5457 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2025_jan_thru_december: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_2026_jan_thru_december: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2025: live=2965.3000 test=1008
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sales_year_to_date_2026: live=1652.5500 test=0
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | sort_number: live=38 test=None
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd: live=-0.4427 test=-1
    customer_name=CONEY ISLAND DISCOUNT INC., salesman_code= | this_year_to_last_year_ytd_full_year: live=-0.4427 test=-1
    customer_name=Home Threads Linden Inc., salesman_code= | sales_2025_jan_thru_december: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sales_year_to_date_2025: live=5250 test=2234.6600
    customer_name=Home Threads Linden Inc., salesman_code= | sort_number: live=39 test=None
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2025_jan_thru_december: live=5498.6400 test=4843.7700
    customer_name=Blake Food Mart Inc., salesman_code= | sales_2026_jan_thru_december: live=4661.8400 test=0
    ... +1284 more
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
