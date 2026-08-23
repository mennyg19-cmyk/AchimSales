# Parity: salesman_mkolko

- Params: `{'scope': 'MKolko'}`
- Live file: `.scratch\parity\20260726-131548-salesman-master\mkolko-scoped\salesman__live_mkolko.xlsx`
- Test file: `.scratch\parity\20260726-131548-salesman-master\mkolko-scoped\salesman__test_mkolko.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **7994**
- Missing sheets in /test: (none)
- Extra sheets in /test (ignored): (none)
- Per sheet: Jan=DIFF(624), Feb=DIFF(610), Mar=DIFF(705), Apr=DIFF(669), May=DIFF(665), Jun=DIFF(672), Jul=DIFF(684), Aug=DIFF(670), Sep=DIFF(669), Oct=DIFF(668), Nov=DIFF(675), Dec=DIFF(683)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260726-131548-salesman-master\mkolko-scoped\salesman__live_mkolko.xlsx vs .scratch\parity\20260726-131548-salesman-master\mkolko-scoped\salesman__test_mkolko.xlsx
Hard differences: 7994
Result: DIFFERENCES FOUND

## Sheet: Jan [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, this_year_to_last_year_ytd_full_year=87, sales_year_to_date_2026=64, sales_2025_jan_thru_january=46
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (616):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_january: live=1847.5200 test=0
    customer_account=1364 | sales_january_2025: live=1847.5200 test=0
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    customer_account=1364 | this_year_to_last_year: live=-1 test=0
    customer_account=1364 | this_year_to_last_year_ytd: live=-1 test=0
    customer_account=1364 | this_year_to_last_year_ytd_full_year: live=-0.5182 test=-0.4518
    customer_account=1493 | sales_2025_jan_thru_january: live=1119 test=0
    customer_account=1493 | sales_2026_jan_thru_january: live=4238.9500 test=4238.9000
    customer_account=1493 | sales_january_2025: live=1119 test=0
    customer_account=1493 | sales_january_2026: live=4238.9500 test=4238.9000
    customer_account=1493 | sales_year_to_date_2025: live=5847.6000 test=3574.7800
    customer_account=1493 | sales_year_to_date_2026: live=10138.9000 test=10305.4000
    customer_account=1493 | sort_number: live=25 test=0012
    customer_account=1493 | this_year_to_last_year: live=2.7882 test=0
    customer_account=1493 | this_year_to_last_year_ytd: live=2.7882 test=0
    customer_account=1493 | this_year_to_last_year_ytd_full_year: live=0.7339 test=1.8828
    ... +566 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Feb [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, this_year_to_last_year_ytd_full_year=87, sales_year_to_date_2026=64, sales_2025_jan_thru_february=58
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (602):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_february: live=-1061.8000 test=0
    customer_account=11233 | sales_february_2026: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_february: live=1847.5200 test=0
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    customer_account=1364 | this_year_to_last_year_ytd: live=0.1940 test=0
    customer_account=1364 | this_year_to_last_year_ytd_full_year: live=-0.5182 test=-0.4518
    customer_account=1493 | sales_2025_jan_thru_february: live=2415 test=0
    customer_account=1493 | sales_2026_jan_thru_february: live=4238.9500 test=4238.9000
    customer_account=1493 | sales_february_2025: live=1296 test=0
    customer_account=1493 | sales_year_to_date_2025: live=5847.6000 test=3574.7800
    customer_account=1493 | sales_year_to_date_2026: live=10138.9000 test=10305.4000
    customer_account=1493 | sort_number: live=25 test=0012
    customer_account=1493 | this_year_to_last_year: live=-1 test=0
    customer_account=1493 | this_year_to_last_year_ytd: live=0.7553 test=0
    customer_account=1493 | this_year_to_last_year_ytd_full_year: live=0.7339 test=1.8828
    customer_account=1560 | sort_number: live=26 test=0012
    ... +552 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Mar [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, this_year_to_last_year_ytd_full_year=87, sales_2025_jan_thru_march=78, this_year_to_last_year_ytd=78
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (697):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_march: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_march: live=3823.1800 test=999.1000
    customer_account=1364 | sales_march_2025: live=1975.6600 test=999.1000
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    customer_account=1364 | this_year_to_last_year_ytd: live=-0.4230 test=1.2080
    customer_account=1364 | this_year_to_last_year_ytd_full_year: live=-0.5182 test=-0.4518
    customer_account=1493 | sales_2025_jan_thru_march: live=2415 test=0
    customer_account=1493 | sales_2026_jan_thru_march: live=4072.4000 test=4238.9000
    customer_account=1493 | sales_march_2026: live=-166.5500 test=0
    customer_account=1493 | sales_year_to_date_2025: live=5847.6000 test=3574.7800
    customer_account=1493 | sales_year_to_date_2026: live=10138.9000 test=10305.4000
    customer_account=1493 | sort_number: live=25 test=0012
    customer_account=1493 | this_year_to_last_year_ytd: live=0.6863 test=0
    customer_account=1493 | this_year_to_last_year_ytd_full_year: live=0.7339 test=1.8828
    customer_account=1560 | sort_number: live=26 test=0012
    customer_account=1567 | sales_2025_jan_thru_march: live=1080.6800 test=0
    ... +647 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Apr [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, this_year_to_last_year_ytd_full_year=87, sales_2025_jan_thru_april=82, this_year_to_last_year_ytd=79
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (661):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_2026_jan_thru_april: live=2453.0200 test=2452.9500
    customer_account=11190 | sales_april_2026: live=2453.0200 test=2452.9500
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_april: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_april: live=5413.6000 test=2589.5200
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    customer_account=1364 | this_year_to_last_year_ytd: live=-0.1821 test=0.7099
    customer_account=1364 | this_year_to_last_year_ytd_full_year: live=-0.5182 test=-0.4518
    customer_account=1493 | sales_2025_jan_thru_april: live=2415 test=0
    customer_account=1493 | sales_2026_jan_thru_april: live=4072.4000 test=4238.9000
    customer_account=1493 | sales_year_to_date_2025: live=5847.6000 test=3574.7800
    customer_account=1493 | sales_year_to_date_2026: live=10138.9000 test=10305.4000
    customer_account=1493 | sort_number: live=25 test=0012
    customer_account=1493 | this_year_to_last_year_ytd: live=0.6863 test=0
    customer_account=1493 | this_year_to_last_year_ytd_full_year: live=0.7339 test=1.8828
    customer_account=1560 | sort_number: live=26 test=0012
    customer_account=1567 | sales_2025_jan_thru_april: live=2574.4600 test=1493.7800
    ... +611 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: May [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, this_year_to_last_year_ytd_full_year=87, sales_2025_jan_thru_may=86, this_year_to_last_year_ytd=85
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (657):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_2026_jan_thru_may: live=4069.8400 test=4069.7700
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_may: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_may: live=7156.2400 test=4332.1600
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    customer_account=1364 | this_year_to_last_year_ytd: live=-0.1207 test=0.4526
    customer_account=1364 | this_year_to_last_year_ytd_full_year: live=-0.5182 test=-0.4518
    customer_account=1493 | sales_2025_jan_thru_may: live=2812.5000 test=0
    customer_account=1493 | sales_2026_jan_thru_may: live=7487.9000 test=7654.4000
    customer_account=1493 | sales_may_2025: live=397.5000 test=0
    customer_account=1493 | sales_year_to_date_2025: live=5847.6000 test=3574.7800
    customer_account=1493 | sales_year_to_date_2026: live=10138.9000 test=10305.4000
    customer_account=1493 | sort_number: live=25 test=0012
    customer_account=1493 | this_year_to_last_year: live=7.5925 test=0
    customer_account=1493 | this_year_to_last_year_ytd: live=1.6624 test=0
    customer_account=1493 | this_year_to_last_year_ytd_full_year: live=0.7339 test=1.8828
    customer_account=1560 | sort_number: live=26 test=0012
    ... +607 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Jun [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, this_year_to_last_year_ytd_full_year=87, sales_2025_jan_thru_june=87, this_year_to_last_year_ytd=83
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (664):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_2026_jan_thru_june: live=4069.8400 test=4069.7700
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_june: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_2026_jan_thru_june: live=3779.0200 test=4872.0200
    customer_account=11247 | sales_june_2026: live=-1093 test=0
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_2026_jan_thru_june: live=7718.3800 test=7718.4800
    customer_account=11540 | sales_june_2026: live=-0.1000 test=0
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_2025_jan_thru_june: live=3136.1300 test=3136.0700
    customer_account=1273 | sales_june_2025: live=1162.1300 test=1162.0700
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_june: live=9730.4500 test=7041.4700
    customer_account=1364 | sales_june_2025: live=2574.2100 test=2709.3100
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    customer_account=1364 | this_year_to_last_year: live=-0.4199 test=-0.4488
    customer_account=1364 | this_year_to_last_year_ytd: live=-0.1998 test=0.1058
    customer_account=1364 | this_year_to_last_year_ytd_full_year: live=-0.5182 test=-0.4518
    customer_account=1493 | sales_2025_jan_thru_june: live=2812.5000 test=0
    customer_account=1493 | sales_2026_jan_thru_june: live=7487.9000 test=7654.4000
    ... +614 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Jul [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, sales_2025_jan_thru_july=92, this_year_to_last_year_ytd_full_year=87, this_year_to_last_year_ytd=85
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (676):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_2025_jan_thru_july: live=2792 test=2794.8000
    customer_account=11031 | sales_july_2025: live=1103.6000 test=1106.4000
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_2026_jan_thru_july: live=6940.5000 test=6940.4300
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_july: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_2026_jan_thru_july: live=3779.0200 test=4872.0200
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_2026_jan_thru_july: live=8868.7600 test=8868.8600
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_2025_jan_thru_july: live=3136.1300 test=3136.0700
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_july: live=10615.4900 test=7926.4900
    customer_account=1364 | sales_july_2025: live=885.0400 test=885.0200
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    customer_account=1364 | this_year_to_last_year_ytd: live=-0.0699 test=0.2456
    customer_account=1364 | this_year_to_last_year_ytd_full_year: live=-0.5182 test=-0.4518
    customer_account=1493 | sales_2025_jan_thru_july: live=6387.3200 test=3574.7800
    customer_account=1493 | sales_2026_jan_thru_july: live=10138.9000 test=10305.4000
    customer_account=1493 | sales_july_2025: live=3574.8200 test=3574.7800
    customer_account=1493 | sales_year_to_date_2025: live=5847.6000 test=3574.7800
    ... +626 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Aug [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, sales_2025_jan_thru_august=94, this_year_to_last_year_ytd_full_year=87, this_year_to_last_year_ytd=84
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (662):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_2025_jan_thru_august: live=2792 test=2794.8000
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_2026_jan_thru_august: live=6940.5000 test=6940.4300
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_august: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_2026_jan_thru_august: live=3779.0200 test=4872.0200
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_2026_jan_thru_august: live=8868.7600 test=8868.8600
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_2025_jan_thru_august: live=3136.1300 test=3136.0700
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_august: live=12993.0500 test=10304.0500
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    customer_account=1364 | this_year_to_last_year_ytd: live=-0.2401 test=-0.0418
    customer_account=1364 | this_year_to_last_year_ytd_full_year: live=-0.5182 test=-0.4518
    customer_account=1493 | sales_2025_jan_thru_august: live=6387.3200 test=3574.7800
    customer_account=1493 | sales_2026_jan_thru_august: live=10138.9000 test=10305.4000
    customer_account=1493 | sales_year_to_date_2025: live=5847.6000 test=3574.7800
    customer_account=1493 | sales_year_to_date_2026: live=10138.9000 test=10305.4000
    customer_account=1493 | sort_number: live=25 test=0012
    customer_account=1493 | this_year_to_last_year_ytd: live=0.5873 test=1.8828
    ... +612 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Sep [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, sales_2025_jan_thru_september=94, this_year_to_last_year_ytd_full_year=87, this_year_to_last_year_ytd=86
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (661):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_2025_jan_thru_september: live=2792 test=2794.8000
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_2026_jan_thru_september: live=6940.5000 test=6940.4300
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_september: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd: live=-1.7772 test=-1
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_2026_jan_thru_september: live=3779.0200 test=4872.0200
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_2026_jan_thru_september: live=8868.7600 test=8868.8600
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_2025_jan_thru_september: live=4488.5300 test=4488.4700
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_september: live=14340.3600 test=11651.3400
    customer_account=1364 | sales_september_2025: live=1347.3100 test=1347.2900
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    customer_account=1364 | this_year_to_last_year_ytd: live=-0.3115 test=-0.1526
    customer_account=1364 | this_year_to_last_year_ytd_full_year: live=-0.5182 test=-0.4518
    customer_account=1493 | sales_2025_jan_thru_september: live=5847.6000 test=3574.7800
    customer_account=1493 | sales_2026_jan_thru_september: live=10138.9000 test=10305.4000
    customer_account=1493 | sales_september_2025: live=-539.7200 test=0
    customer_account=1493 | sales_year_to_date_2025: live=5847.6000 test=3574.7800
    ... +611 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Oct [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, sales_2025_jan_thru_october=99, this_year_to_last_year_ytd_full_year=87, this_year_to_last_year_ytd=86
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (660):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_2025_jan_thru_october: live=2792 test=2794.8000
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_2026_jan_thru_october: live=6940.5000 test=6940.4300
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_october: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd: live=-1.7772 test=-1
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_2025_jan_thru_october: live=1142.8100 test=1142.7800
    customer_account=11243 | sales_october_2025: live=1142.8100 test=1142.7800
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_2025_jan_thru_october: live=1112.8600 test=1112.8300
    customer_account=11245 | sales_october_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_2025_jan_thru_october: live=5268.3800 test=5268.1500
    customer_account=11247 | sales_2026_jan_thru_october: live=3779.0200 test=4872.0200
    customer_account=11247 | sales_october_2025: live=5268.3800 test=5268.1500
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd: live=-0.2827 test=-0.0752
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_2026_jan_thru_october: live=8868.7600 test=8868.8600
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_2025_jan_thru_october: live=4488.5300 test=4488.4700
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_october: live=14340.3600 test=11651.3400
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    ... +610 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Nov [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, sales_2025_jan_thru_november=102, this_year_to_last_year_ytd_full_year=87, this_year_to_last_year_ytd=86
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (667):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_2025_jan_thru_november: live=2792 test=2794.8000
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_2025_jan_thru_november: live=4418.7600 test=4418.6500
    customer_account=11100 | sales_november_2025: live=2049.2600 test=2049.1500
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_2026_jan_thru_november: live=6940.5000 test=6940.4300
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_november: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd: live=-1.7772 test=-1
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_2025_jan_thru_november: live=1142.8100 test=1142.7800
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_2025_jan_thru_november: live=1112.8600 test=1112.8300
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_2025_jan_thru_november: live=5268.3800 test=5268.1500
    customer_account=11247 | sales_2026_jan_thru_november: live=3779.0200 test=4872.0200
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year_ytd: live=-0.2827 test=-0.0752
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_2026_jan_thru_november: live=8868.7600 test=8868.8600
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_2025_jan_thru_november: live=4488.5300 test=4488.4700
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_november: live=17246.8600 test=14762.2700
    customer_account=1364 | sales_november_2025: live=2906.5000 test=3110.9300
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    customer_account=1364 | sort_number: live=24 test=0012
    ... +617 more
  Soft/cosmetic text diffs (not failing): 50

## Sheet: Dec [DIFF]
  Row key: customer_account
  Rows live=144 test=138 matched=137
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 7 live row(s) missing on /test (5% of live rows).
    - 1 /test-only row(s) not on live (1% of /test rows).
    - Value diffs by column: sort_number=136, sales_2025_jan_thru_december=103, sales_year_to_date_2025=103, this_year_to_last_year_ytd=87, this_year_to_last_year_ytd_full_year=87
  Missing in /test (7):
    customer_account=12 (customer_name=MKolko)
    customer_account=2116 (customer_name=M & M DISCOUNT (CENTURY DISC))
    customer_account=3302865 (customer_name=MAX DEALS IRVINGTON)
    customer_account=5503 (customer_name=99 CENT & DISCOUNT WORLD INC)
    customer_account=6753 (customer_name=DL DISTRIBUTORS)
    customer_account=9424 (customer_name=EXTREME DEPT. STORE #3)
    customer_account=Grand total: (customer_name=None)
  Extra in /test only (1):
    customer_account=516 (customer_name=C & S Value Store,Inc., salesman_code=MKolko)
  Value diffs (675):
    customer_account=11002 | sort_number: live=2 test=0012
    customer_account=11003 | sort_number: live=3 test=0012
    customer_account=11019 | sort_number: live=4 test=0012
    customer_account=11020 | sort_number: live=5 test=0012
    customer_account=11031 | sales_2025_jan_thru_december: live=2792 test=2794.8000
    customer_account=11031 | sales_year_to_date_2025: live=2792 test=2794.8000
    customer_account=11031 | sort_number: live=6 test=0012
    customer_account=11034 | sort_number: live=7 test=0012
    customer_account=11057 | sort_number: live=8 test=0012
    customer_account=11100 | sales_2025_jan_thru_december: live=4418.7600 test=4418.6500
    customer_account=11100 | sales_year_to_date_2025: live=4418.7600 test=4418.6500
    customer_account=11100 | sort_number: live=9 test=0012
    customer_account=11190 | sales_2026_jan_thru_december: live=6940.5000 test=6940.4300
    customer_account=11190 | sales_year_to_date_2026: live=6940.5000 test=6940.4300
    customer_account=11190 | sort_number: live=10 test=0012
    customer_account=11233 | sales_2026_jan_thru_december: live=-1061.8000 test=0
    customer_account=11233 | sales_year_to_date_2026: live=-1061.8000 test=0
    customer_account=11233 | sort_number: live=11 test=0012
    customer_account=11233 | this_year_to_last_year_ytd: live=-1.7772 test=-1
    customer_account=11233 | this_year_to_last_year_ytd_full_year: live=-1.7772 test=-1
    customer_account=11243 | sales_2025_jan_thru_december: live=1142.8100 test=1142.7800
    customer_account=11243 | sales_year_to_date_2025: live=1142.8100 test=1142.7800
    customer_account=11245 | sales_2025_jan_thru_december: live=1112.8600 test=1112.8300
    customer_account=11245 | sales_year_to_date_2025: live=1112.8600 test=1112.8300
    customer_account=11245 | sort_number: live=13 test=0012
    customer_account=11247 | sales_2025_jan_thru_december: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_2026_jan_thru_december: live=3779.0200 test=4872.0200
    customer_account=11247 | sales_december_2025: live=-650.5800 test=0
    customer_account=11247 | sales_year_to_date_2025: live=4617.8000 test=5268.1500
    customer_account=11247 | sales_year_to_date_2026: live=3779.0200 test=4872.0200
    customer_account=11247 | sort_number: live=14 test=0012
    customer_account=11247 | this_year_to_last_year: live=-1 test=0
    customer_account=11247 | this_year_to_last_year_ytd: live=-0.1816 test=-0.0752
    customer_account=11247 | this_year_to_last_year_ytd_full_year: live=-0.1816 test=-0.0752
    customer_account=11416 | sort_number: live=15 test=0012
    customer_account=11482 | sort_number: live=16 test=0012
    customer_account=11540 | sales_2026_jan_thru_december: live=8868.7600 test=8868.8600
    customer_account=11540 | sales_year_to_date_2026: live=8868.7600 test=8868.8600
    customer_account=11540 | sort_number: live=17 test=0012
    customer_account=11569 | sort_number: live=18 test=0012
    customer_account=11612 | sort_number: live=19 test=0012
    customer_account=11616 | sort_number: live=20 test=0012
    customer_account=11621 | sort_number: live=21 test=0012
    customer_account=1164 | sort_number: live=22 test=0012
    customer_account=1273 | sales_2025_jan_thru_december: live=4488.5300 test=4488.4700
    customer_account=1273 | sales_year_to_date_2025: live=4488.5300 test=4488.4700
    customer_account=1273 | sort_number: live=23 test=0012
    customer_account=1364 | sales_2025_jan_thru_december: live=20493.5800 test=18009
    customer_account=1364 | sales_december_2025: live=3246.7200 test=3246.7300
    customer_account=1364 | sales_year_to_date_2025: live=20493.5800 test=18009
    ... +625 more
  Soft/cosmetic text diffs (not failing): 50
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
