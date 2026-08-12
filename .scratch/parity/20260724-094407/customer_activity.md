# Parity: customer_activity

- Params: `{}`
- Live file: `.scratch\parity\20260724-094407\customer_activity__live.xlsx`
- Test file: `.scratch\parity\20260724-094407\customer_activity__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **648**
- Missing sheets in /test: ['All']
- Extra sheets in /test (ignored): (none)
- Per sheet: All=MISSING_TEST(0), AGrossman=DIFF(43), BLevin=DIFF(85), HKaufman=DIFF(152), House=DIFF(24), Integrated=DIFF(5), JWeigand=DIFF(10), LCWalker=DIFF(6), MGrego=DIFF(132), MKolko=DIFF(159), PMazer=DIFF(3), REdwards=DIFF(6), Unassigned=DIFF(22)
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260724-094407\customer_activity__live.xlsx vs .scratch\parity\20260724-094407\customer_activity__test.xlsx
Hard differences: 648
Result: DIFFERENCES FOUND
Missing sheets in /test: All

## Sheet: All [MISSING_TEST]
  Sheet present on live, missing on /test.
  Rows live=0 test=0 matched=0

## Sheet: AGrossman [DIFF]
  Row key: sales_order_number
  Rows live=30 test=31 matched=17
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 13 live row(s) missing on /test (43% of live rows).
    - 14 /test-only row(s) not on live (45% of /test rows).
    - Value diffs by column: last_order_date=16
  Missing in /test (13):
    sales_order_number=ORD00662168 (customer_account=9250, customer_name=BELK ECOMMERCE LLC)
    sales_order_number=ORD00600032 (customer_account=7009, customer_name=BLAIR LLC C/O ORCHARD BRANDS (DS))
    sales_order_number=ORD00883576 (customer_account=48800, customer_name=BOSCOV'S DEPARTMENT STORES INC (DS))
    sales_order_number=ORD00882052 (customer_account=866, customer_name=FAMILY DOLLAR STORES, INC)
    sales_order_number=ORD00882553 (customer_account=00011600, customer_name=HomeBuys)
    sales_order_number=ORD00883562 (customer_account=9022, customer_name=JCPENNEY COMPANY INC (DS))
    sales_order_number=ORD00883470 (customer_account=8264, customer_name=KART IT  (DROP SHIP))
    sales_order_number=ORD00883401 (customer_account=8330, customer_name=MACY'S CORPORATE SERVICES)
    sales_order_number=ORD00883572 (customer_account=9091, customer_name=OJ COMMERCE)
    sales_order_number=ORD00883604 (customer_account=9122, customer_name=VIRVENTURES (DS))
    sales_order_number=ORD00883583 (customer_account=7125, customer_name=WAL-MART STORES, INC (DS))
    sales_order_number=ORD00880873 (customer_account=8296, customer_name=WALMART STORES     (STORES))
    sales_order_number=ORD00883545 (customer_account=9196, customer_name=WALMART.COM (WH))
  Extra in /test only (14):
    sales_order_number=ORD00657632 (customer_account=9250, customer_name=BELK ECOMMERCE LLC, salesman_code=AGrossman)
    sales_order_number=TR-4421 (customer_account=7009, customer_name=BLAIR LLC C/O ORCHRD BRNDS(DS), salesman_code=AGrossman)
    sales_order_number=ORD00882961 (customer_account=48800, customer_name=BOSCOV'S DEPT.STORES INC.(DS), salesman_code=AGrossman)
    sales_order_number=ORD00868695 (customer_account=866, customer_name=FAMILY DOLLAR STORES,INC., salesman_code=AGrossman)
    sales_order_number=ORD00848079 (customer_account=00011600, customer_name=HomeBuys, salesman_code=AGrossman)
    sales_order_number=ORD00883176 (customer_account=9022, customer_name=JCPENNEY COMPANY INC.  (DS), salesman_code=AGrossman)
    sales_order_number=ORD00883052 (customer_account=8264, customer_name=KART IT  (WHOLE9YARDS USA LLC), salesman_code=AGrossman)
    sales_order_number=TR-4385 (customer_account=9207, customer_name=LOWES DIRECT FULFILMENT CTR., salesman_code=AGrossman)
    sales_order_number=ORD00883089 (customer_account=8330, customer_name=MACY'S CORPORATE SERVICES, salesman_code=AGrossman)
    sales_order_number=ORD00883118 (customer_account=9091, customer_name=OJ COMMERCE, salesman_code=AGrossman)
    sales_order_number=ORD00881947 (customer_account=9122, customer_name=VIRVENTURES, salesman_code=AGrossman)
    sales_order_number=ORD00875779 (customer_account=8296, customer_name=WALMART STORES     (STORES), salesman_code=AGrossman)
    sales_order_number=ORD00883169 (customer_account=7125, customer_name=WAL-MART STORES, INC.#546978, salesman_code=AGrossman)
    sales_order_number=ORD00878023 (customer_account=9196, customer_name=WALMART.COM WAREHOUSE, salesman_code=AGrossman)
  Value diffs (16):
    sales_order_number=ORD00877498 | last_order_date: live=2026-07-15 test=07/17/2026
    sales_order_number=ORD00878500 | last_order_date: live=2026-07-16 test=07/23/2026
    sales_order_number=ORD00878791 | last_order_date: live=2026-07-17 test=07/20/2026
    sales_order_number=ORD00618216 | last_order_date: live=2025-07-09 test=07/10/2025
    sales_order_number=ORD00514123 | last_order_date: live=2025-01-30 test=03/04/2025
    sales_order_number=ORD00859022 | last_order_date: live=2026-06-19 test=06/24/2026
    sales_order_number=ORD00882461 | last_order_date: live=2026-07-22 test=07/22/2026
    sales_order_number=ORD00882567 | last_order_date: live=2026-07-22 test=07/23/2026
    sales_order_number=ORD00516418 | last_order_date: live=2025-02-03 test=02/04/2025
    sales_order_number=ORD00844200 | last_order_date: live=2026-05-29 test=05/29/2026
    sales_order_number=ORD00843870 | last_order_date: live=2026-05-28 test=06/02/2026
    sales_order_number=ORD00842418 | last_order_date: live=2026-05-26 test=05/29/2026
    sales_order_number=ORD00812451 | last_order_date: live=2026-04-17 test=04/17/2026
    sales_order_number=ORD00788468 | last_order_date: live=2026-03-19 test=03/25/2026
    sales_order_number=ORD00880892 | last_order_date: live=2026-07-20 test=07/20/2026
    sales_order_number=ORD00881809 | last_order_date: live=2026-07-21 test=07/22/2026
  Soft/cosmetic text diffs (not failing): 4

## Sheet: BLevin [DIFF]
  Row key: sales_order_number
  Rows live=83 test=83 matched=80
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 3 live row(s) missing on /test (4% of live rows).
    - 3 /test-only row(s) not on live (4% of /test rows).
    - Value diffs by column: last_order_date=79
  Missing in /test (3):
    sales_order_number=ORD00883609 (customer_account=6262, customer_name=HD SUPPLY FACILITIES MAINTENANCE)
    sales_order_number=ORD00600657 (customer_account=8094, customer_name=MS DOLLAR PLUS)
    sales_order_number=ORD00882254 (customer_account=5046, customer_name=SHERWIN WILLIAMS)
  Extra in /test only (3):
    sales_order_number=TR-4266 (customer_account=1035, customer_name=GOLDBERG'S, salesman_code=BLevin)
    sales_order_number=ORD00883079 (customer_account=6262, customer_name=HD SUPPLY FACILITIES, salesman_code=BLevin)
    sales_order_number=ORD00881132 (customer_account=5046, customer_name=SHERWIN WILLIAMS, salesman_code=BLevin)
  Value diffs (79):
    sales_order_number=ORD00657034 | last_order_date: live=2025-09-09 test=09/12/2025
    sales_order_number=ORD00806732 | last_order_date: live=2026-04-10 test=04/15/2026
    sales_order_number=ORD00841372 | last_order_date: live=2026-05-25 test=05/26/2026
    sales_order_number=ORD00702224 | last_order_date: live=2025-11-10 test=11/19/2025
    sales_order_number=ORD00702200 | last_order_date: live=2025-11-10 test=11/19/2025
    sales_order_number=ORD00849573 | last_order_date: live=2026-06-05 test=06/10/2026
    sales_order_number=ORD00856094 | last_order_date: live=2026-06-15 test=06/18/2026
    sales_order_number=ORD00766348 | last_order_date: live=2026-02-20 test=02/25/2026
    sales_order_number=ORD00748375 | last_order_date: live=2026-01-22 test=01/28/2026
    sales_order_number=ORD00870845 | last_order_date: live=2026-07-06 test=07/08/2026
    sales_order_number=ORD00544181 | last_order_date: live=2025-03-20 test=03/26/2025
    sales_order_number=ORD00866084 | last_order_date: live=2026-06-29 test=06/30/2026
    sales_order_number=ORD00821431 | last_order_date: live=2026-04-28 test=04/30/2026
    sales_order_number=ORD00820757 | last_order_date: live=2026-04-27 test=04/30/2026
    sales_order_number=ORD00866726 | last_order_date: live=2026-06-30 test=07/02/2026
    sales_order_number=ORD00642934 | last_order_date: live=2025-08-19 test=08/26/2025
    sales_order_number=ORD00593946 | last_order_date: live=2025-05-30 test=07/08/2025
    sales_order_number=ORD00788521 | last_order_date: live=2026-03-19 test=03/25/2026
    sales_order_number=ORD00735275 | last_order_date: live=2025-12-23 test=12/23/2025
    sales_order_number=ORD00816120 | last_order_date: live=2026-04-21 test=04/22/2026
    sales_order_number=ORD00799603 | last_order_date: live=2026-04-01 test=04/07/2026
    sales_order_number=ORD00726240 | last_order_date: live=2025-12-08 test=12/11/2025
    sales_order_number=ORD00559491 | last_order_date: live=2025-04-11 test=04/18/2025
    sales_order_number=ORD00863119 | last_order_date: live=2026-06-25 test=06/30/2026
    sales_order_number=ORD00630646 | last_order_date: live=2025-07-29 test=08/08/2025
    sales_order_number=ORD00795246 | last_order_date: live=2026-03-27 test=04/07/2026
    sales_order_number=ORD00742431 | last_order_date: live=2026-01-13 test=01/16/2026
    sales_order_number=ORD00838165 | last_order_date: live=2026-05-20 test=05/27/2026
    sales_order_number=ORD00815212 | last_order_date: live=2026-04-20 test=04/23/2026
    sales_order_number=ORD00728416 | last_order_date: live=2025-12-11 test=12/16/2025
    sales_order_number=ORD00862528 | last_order_date: live=2026-06-24 test=06/30/2026
    sales_order_number=ORD00804743 | last_order_date: live=2026-04-07 test=04/15/2026
    sales_order_number=ORD00828153 | last_order_date: live=2026-05-06 test=05/19/2026
    sales_order_number=ORD00858416 | last_order_date: live=2026-06-18 test=06/18/2026
    sales_order_number=ORD00857577 | last_order_date: live=2026-06-17 test=06/26/2026
    sales_order_number=ORD00582912 | last_order_date: live=2025-05-13 test=05/14/2025
    sales_order_number=ORD00733684 | last_order_date: live=2025-12-22 test=12/23/2025
    sales_order_number=ORD00841349 | last_order_date: live=2026-05-25 test=05/27/2026
    sales_order_number=ORD00634150 | last_order_date: live=2025-08-04 test=08/13/2025
    sales_order_number=ORD00573957 | last_order_date: live=2025-04-29 test=04/30/2025
    sales_order_number=ORD00876519 | last_order_date: live=2026-07-14 test=07/17/2026
    sales_order_number=ORD00776152 | last_order_date: live=2026-03-05 test=03/11/2026
    sales_order_number=ORD00774508 | last_order_date: live=2026-03-03 test=03/04/2026
    sales_order_number=ORD00849596 | last_order_date: live=2026-06-05 test=06/10/2026
    sales_order_number=ORD00868212 | last_order_date: live=2026-07-02 test=07/14/2026
    sales_order_number=ORD00779373 | last_order_date: live=2026-03-09 test=03/11/2026
    sales_order_number=ORD00675174 | last_order_date: live=2025-10-06 test=10/17/2025
    sales_order_number=ORD00517261 | last_order_date: live=2025-02-05 test=03/04/2025
    sales_order_number=ORD00795167 | last_order_date: live=2026-03-27 test=03/31/2026
    sales_order_number=ORD00877420 | last_order_date: live=2026-07-15 test=07/22/2026
    ... +29 more
  Soft/cosmetic text diffs (not failing): 15

## Sheet: HKaufman [DIFF]
  Row key: sales_order_number
  Rows live=128 test=125 matched=100
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 28 live row(s) missing on /test (22% of live rows).
    - 25 /test-only row(s) not on live (20% of /test rows).
    - Value diffs by column: last_order_date=99
  Missing in /test (28):
    sales_order_number=ORD00875810 (customer_account=54, customer_name=ACE HARDWARE)
    sales_order_number=ORD00882286 (customer_account=8306, customer_name=AJH MANAGEMENT)
    sales_order_number=ORD00532743 (customer_account=3154111, customer_name=ASTRO HOLDING COMPANY LLC)
    sales_order_number=ORD00644203 (customer_account=7010, customer_name=BLUESTEM BRANDS, INC (DS))
    sales_order_number=ORD00716712 (customer_account=Big Country Note LLC, customer_name=Big Country Note LLC)
    sales_order_number=ORD00873859 (customer_account=38012, customer_name=C.H. MARTIN INC)
    sales_order_number=ORD00787841 (customer_account=1342062, customer_name=Dream Decor Inc.)
    sales_order_number=ORD00866899 (customer_account=6347, customer_name=F & F SUPPLY)
    sales_order_number=ORD00883053 (customer_account=846, customer_name=FABRIC HOME FASHIONS CORP)
    sales_order_number=ORD00883359 (customer_account=9177, customer_name=FULLBEAUTY BRANDS INC (DS))
    sales_order_number=ORD00868086 (customer_account=917, customer_name=FULLBEAUTY BRANDS, INC (OSP))
    sales_order_number=ORD00527759 (customer_account=2847501, customer_name=Heshy Kaufman)
    sales_order_number=ORD00883026 (customer_account=9111, customer_name=J & S HOUSEWARES CORP)
    sales_order_number=ORD00573830 (customer_account=1377, customer_name=J. PICA & CIA INC)
    sales_order_number=ORD00862978 (customer_account=6322, customer_name=MARC GLASSMAN, INC)
    sales_order_number=ORD00875988 (customer_account=6527, customer_name=MILES KIMBALL/SILVER STAR BRANDS)
    sales_order_number=ORD00878140 (customer_account=1963, customer_name=Masters HC LTD)
    sales_order_number=ORD00510381 (customer_account=300123, customer_name=Michael Thompson LLC Viral Distributors)
    sales_order_number=ORD00652926 (customer_account=7005, customer_name=OCEAN STATE JOBBERS, INC)
    sales_order_number=ORD00732666 (customer_account=3087, customer_name=OVERSTOCK.COM d/b/a Beyond Inc.)
    sales_order_number=ORD00882445 (customer_account=3004, customer_name=PARKE-BELL LTD INC(WHSE))
    sales_order_number=ORD00847440 (customer_account=6619, customer_name=SATMAR BUNGALOW)
    sales_order_number=ORD00857700 (customer_account=8398, customer_name=SHORELINE PRODUCTS, INC.)
    sales_order_number=ORD00867323 (customer_account=6718, customer_name=SWFM RETAIL GROUP LLC.)
    sales_order_number=ORD00881552 (customer_account=2807, customer_name=THE CURTAIN SHOP OF MAINE, INC)
    sales_order_number=ORD00881057 (customer_account=2267, customer_name=VARIETY (ROSE'S))
    sales_order_number=ORD00883147 (customer_account=8379, customer_name=VIR VENTURES, INC (WH))
    sales_order_number=ORD00883596 (customer_account=8015, customer_name=WAYFAIR LLC (DS))
  Extra in /test only (25):
    sales_order_number=ORD00562679 (customer_account=54, customer_name=ACE HARDWARE, salesman_code=HKaufman)
    sales_order_number=ORD00875879 (customer_account=8306, customer_name=AJH MANAGEMENT, salesman_code=HKaufman)
    sales_order_number=TR-4381 (customer_account=3154111, customer_name=ASTRO HOLDING COMPANY LLC, salesman_code=HKaufman)
    sales_order_number=ORD00605682 (customer_account=Big Country Note LLC, customer_name=Big Country Note LLC, salesman_code=HKaufman)
    sales_order_number=ORD00643953 (customer_account=7010, customer_name=BLUESTEM BRANDS, INC.    (DS), salesman_code=HKaufman)
    sales_order_number=ORD00856178 (customer_account=38012, customer_name=C.H. MARTIN INC. #12(JrnlSqre), salesman_code=HKaufman)
    sales_order_number=TR-4483 (customer_account=1342062, customer_name=Dream Decor Inc. #3, salesman_code=HKaufman)
    sales_order_number=ORD00848982 (customer_account=6347, customer_name=F & F SUPPLY, salesman_code=HKaufman)
    sales_order_number=ORD00858428 (customer_account=846, customer_name=FABRIC HOME FASHIONS CORP., salesman_code=HKaufman)
    sales_order_number=ORD00882660 (customer_account=9177, customer_name=FULLBEAUTY BRANDS, INC (OSPDS), salesman_code=HKaufman)
    sales_order_number=ORD00857034 (customer_account=917, customer_name=FULLBEAUTY BRANDS, INC. (OSP), salesman_code=HKaufman)
    sales_order_number=ORD00862387 (customer_account=9111, customer_name=J & S HOUSEWARES CORP., salesman_code=HKaufman)
    sales_order_number=ORD00506482 (customer_account=1377, customer_name=J. PICA & CIA INC., salesman_code=HKaufman)
    sales_order_number=ORD00811833 (customer_account=1963, customer_name=MASTERS LTD., salesman_code=HKaufman)
    sales_order_number=ORD00848921 (customer_account=6527, customer_name=MILES KIMBALL/SILVER STAR BRND, salesman_code=HKaufman)
    sales_order_number=ORD00652925 (customer_account=7005, customer_name=OCEAN STATE JOBBERS, INC., salesman_code=HKaufman)
    sales_order_number=ORD00730732 (customer_account=3087, customer_name=OVERSTOCK.COM, salesman_code=HKaufman)
    sales_order_number=ORD00862527 (customer_account=3004, customer_name=PARKE-BELL LTD. INC., salesman_code=HKaufman)
    sales_order_number=ORD00587998 (customer_account=6619, customer_name=SATMAR BUNGALOW, salesman_code=HKaufman)
    sales_order_number=ORD00691140 (customer_account=6718, customer_name=Shoppers World Group, salesman_code=HKaufman)
    sales_order_number=ORD00857690 (customer_account=8398, customer_name=SHORELINE PRODUCTS, INC., salesman_code=HKaufman)
    sales_order_number=ORD00871556 (customer_account=2807, customer_name=THE CURTAIN SHOP OF MAINE,INC., salesman_code=HKaufman)
    sales_order_number=ORD00856373 (customer_account=2267, customer_name=Variety/Rose's, salesman_code=HKaufman)
    sales_order_number=ORD00877477 (customer_account=8379, customer_name=VIR VENTURES, INC.   (BULK), salesman_code=HKaufman)
    sales_order_number=ORD00883172 (customer_account=8015, customer_name=WAYFAIR LLC (DS), salesman_code=HKaufman)
  Value diffs (99):
    sales_order_number=ORD00710346 | last_order_date: live=2025-11-19 test=12/05/2025
    sales_order_number=ORD00848313 | last_order_date: live=2026-06-03 test=06/10/2026
    sales_order_number=ORD00742510 | last_order_date: live=2026-01-13 test=01/29/2026
    sales_order_number=ORD00642437 | last_order_date: live=2025-08-18 test=08/18/2025
    sales_order_number=ORD00773762 | last_order_date: live=2026-03-02 test=04/28/2026
    sales_order_number=ORD00852373 | last_order_date: live=2026-06-09 test=06/11/2026
    sales_order_number=ORD00692784 | last_order_date: live=2025-10-29 test=10/31/2025
    sales_order_number=ORD00872882 | last_order_date: live=2026-07-09 test=07/20/2026
    sales_order_number=ORD00877421 | last_order_date: live=2026-07-15 test=07/16/2026
    sales_order_number=ORD00866911 | last_order_date: live=2026-06-30 test=07/02/2026
    sales_order_number=ORD00872428 | last_order_date: live=2026-07-08 test=07/10/2026
    sales_order_number=ORD00726119 | last_order_date: live=2025-12-08 test=02/20/2026
    sales_order_number=ORD00533771 | last_order_date: live=2025-03-07 test=03/12/2025
    sales_order_number=ORD00809210 | last_order_date: live=2026-04-13 test=05/18/2026
    sales_order_number=ORD00882274 | last_order_date: live=2026-07-22 test=07/23/2026
    sales_order_number=ORD00828216 | last_order_date: live=2026-05-06 test=05/28/2026
    sales_order_number=ORD00878871 | last_order_date: live=2026-07-17 test=07/21/2026
    sales_order_number=ORD00596854 | last_order_date: live=2025-06-04 test=06/30/2025
    sales_order_number=ORD00698699 | last_order_date: live=2025-11-06 test=01/20/2026
    sales_order_number=ORD00646916 | last_order_date: live=2025-08-25 test=08/27/2025
    sales_order_number=ORD00851554 | last_order_date: live=2026-06-08 test=06/10/2026
    sales_order_number=ORD00852863 | last_order_date: live=2026-06-10 test=06/15/2026
    sales_order_number=ORD00658241 | last_order_date: live=2025-09-11 test=11/03/2025
    sales_order_number=ORD00667412 | last_order_date: live=2025-09-25 test=11/20/2025
    sales_order_number=ORD00756556 | last_order_date: live=2026-02-05 test=02/06/2026
    sales_order_number=ORD00711748 | last_order_date: live=2025-11-21 test=12/05/2025
    sales_order_number=ORD00640286 | last_order_date: live=2025-08-14 test=08/19/2025
    sales_order_number=ORD00838060 | last_order_date: live=2026-05-20 test=05/29/2026
    sales_order_number=ORD00871769 | last_order_date: live=2026-07-07 test=07/10/2026
    sales_order_number=ORD00803662 | last_order_date: live=2026-04-06 test=04/10/2026
    sales_order_number=ORD00631036 | last_order_date: live=2025-07-30 test=08/14/2025
    sales_order_number=ORD00848361 | last_order_date: live=2026-06-03 test=06/05/2026
    sales_order_number=ORD00729205 | last_order_date: live=2025-12-12 test=12/22/2025
    sales_order_number=ORD00851698 | last_order_date: live=2026-06-08 test=06/09/2026
    sales_order_number=ORD00873762 | last_order_date: live=2026-07-10 test=07/20/2026
    sales_order_number=ORD00663113 | last_order_date: live=2025-09-19 test=09/25/2025
    sales_order_number=ORD00759152 | last_order_date: live=2026-02-09 test=07/14/2026
    sales_order_number=ORD00680438 | last_order_date: live=2025-10-13 test=10/16/2025
    sales_order_number=ORD00572863 | last_order_date: live=2025-04-28 test=06/17/2025
    sales_order_number=ORD00852926 | last_order_date: live=2026-06-10 test=06/12/2026
    sales_order_number=ORD00708418 | last_order_date: live=2025-11-17 test=11/17/2025
    sales_order_number=ORD00831436 | last_order_date: live=2026-05-11 test=05/13/2026
    sales_order_number=ORD00578279 | last_order_date: live=2025-05-05 test=05/13/2025
    sales_order_number=ORD00662157 | last_order_date: live=2025-09-17 test=09/19/2025
    sales_order_number=ORD00821429 | last_order_date: live=2026-04-28 test=05/08/2026
    sales_order_number=ORD00868230 | last_order_date: live=2026-07-02 test=07/20/2026
    sales_order_number=ORD00881146 | last_order_date: live=2026-07-20 test=07/23/2026
    sales_order_number=ORD00861578 | last_order_date: live=2026-06-23 test=06/23/2026
    sales_order_number=ORD00680417 | last_order_date: live=2025-10-13 test=10/22/2025
    sales_order_number=ORD00861582 | last_order_date: live=2026-06-23 test=06/23/2026
    ... +49 more
  Soft/cosmetic text diffs (not failing): 33

## Sheet: House [DIFF]
  Row key: sales_order_number
  Rows live=22 test=20 matched=18
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 4 live row(s) missing on /test (18% of live rows).
    - 2 /test-only row(s) not on live (10% of /test rows).
    - Value diffs by column: last_order_date=17, po_number=1
  Missing in /test (4):
    sales_order_number=ORD00516338 (customer_account=ALEJANDRO CRUZ, customer_name=ALEJANDRO CRUZ)
    sales_order_number=ORD00667425 (customer_account=2593326, customer_name=CAMP BNOS MAINTENANCE)
    sales_order_number=ORD00625635 (customer_account=5334, customer_name=JANICE WEIGAND)
    sales_order_number=ORD00833298 (customer_account=2354986, customer_name=Moshe Grossman)
  Extra in /test only (2):
    sales_order_number=ORD00810691 (customer_account=2354986, customer_name=GROSSM, MOSHE ARYEH, salesman_code=House)
    sales_order_number=ORD00553447 (customer_account=5334, customer_name=WEIGAND, JANICE, salesman_code=House)
  Value diffs (18):
    sales_order_number=ORD00635369 | last_order_date: live=2025-08-06 test=12/24/2025
    sales_order_number=ORD00816021 | last_order_date: live=2026-04-21 test=04/22/2026
    sales_order_number=ORD00781479 | last_order_date: live=2026-03-11 test=03/11/2026
    sales_order_number=ORD00652946 | last_order_date: live=2025-09-03 test=01/30/2026
    sales_order_number=ORD00883027 | last_order_date: live=2026-07-23 test=07/23/2026
    sales_order_number=ORD00741858 | last_order_date: live=2026-01-12 test=01/14/2026
    sales_order_number=ORD00838872 | last_order_date: live=2026-05-21 test=06/03/2026
    sales_order_number=ORD00861765 | last_order_date: live=2026-06-23 test=06/23/2026
    sales_order_number=ORD00838061 | last_order_date: live=2026-05-20 test=05/20/2026
    sales_order_number=ORD00596656 | last_order_date: live=2025-06-04 test=06/05/2025
    sales_order_number=ORD00823520 | last_order_date: live=2026-04-30 test=05/01/2026
    sales_order_number=ORD00817355 | last_order_date: live=2026-04-23 test=04/23/2026
    sales_order_number=ORD00861745 | last_order_date: live=2026-06-23 test=06/23/2026
    sales_order_number=ORD00554009 | last_order_date: live=2025-04-03 test=04/03/2025
    sales_order_number=ORD00554009 | po_number: live=None test=N/A
    sales_order_number=ORD00566546 | last_order_date: live=2025-04-22 test=04/24/2025
    sales_order_number=ORD00881664 | last_order_date: live=2026-07-21 test=07/21/2026
    sales_order_number=ORD00582823 | last_order_date: live=2025-05-13 test=05/30/2025
  Soft/cosmetic text diffs (not failing): 2

## Sheet: Integrated [DIFF]
  Row key: sales_order_number
  Rows live=4 test=4 matched=2
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 2 live row(s) missing on /test (50% of live rows).
    - 2 /test-only row(s) not on live (50% of /test rows).
    - Value diffs by column: last_order_date=1
  Missing in /test (2):
    sales_order_number=ORD00883606 (customer_account=7025, customer_name=HOMEDEPOT.COM)
    sales_order_number=ORD00883607 (customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS))
  Extra in /test only (2):
    sales_order_number=ORD00883170 (customer_account=7025, customer_name=HOMEDEPOT.COM, salesman_code=Integrated)
    sales_order_number=ORD00883181 (customer_account=9206, customer_name=LOWE'S COMPANIES INC.  (DS), salesman_code=Integrated)
  Value diffs (1):
    sales_order_number=ORD00806817 | last_order_date: live=2026-04-10 test=04/14/2026

## Sheet: JWeigand [DIFF]
  Row key: sales_order_number
  Rows live=7 test=7 matched=3
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 4 live row(s) missing on /test (57% of live rows).
    - 4 /test-only row(s) not on live (57% of /test rows).
    - Value diffs by column: last_order_date=2
  Missing in /test (4):
    sales_order_number=ORD00877419 (customer_account=6123, customer_name=ASHRO/SEVENTH AVENUE/COLONY BRANDS)
    sales_order_number=ORD00883593 (customer_account=1412, customer_name=KOHL'S DEPARTMENT STORES)
    sales_order_number=ORD00873723 (customer_account=8008, customer_name=MASON COMPANIES, INC)
    sales_order_number=ORD00883560 (customer_account=9188, customer_name=MASON COMPANIES, INC (DS))
  Extra in /test only (4):
    sales_order_number=ORD00868169 (customer_account=6123, customer_name=ASHRO/SEVENTH AVENUE ATTN:A/P, salesman_code=JWeigand)
    sales_order_number=ORD00883178 (customer_account=1412, customer_name=KOHL'S, salesman_code=JWeigand)
    sales_order_number=ORD00846679 (customer_account=8008, customer_name=MASON COMPANIES, INC., salesman_code=JWeigand)
    sales_order_number=ORD00883145 (customer_account=9188, customer_name=MASON COMPANIES, INC. (DS), salesman_code=JWeigand)
  Value diffs (2):
    sales_order_number=ORD00708401 | last_order_date: live=2025-11-17 test=11/17/2025
    sales_order_number=ORD00558966 | last_order_date: live=2025-04-10 test=05/05/2025
  Soft/cosmetic text diffs (not failing): 3

## Sheet: LCWalker [DIFF]
  Row key: sales_order_number
  Rows live=5 test=5 matched=4
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 1 live row(s) missing on /test (20% of live rows).
    - 1 /test-only row(s) not on live (20% of /test rows).
    - Value diffs by column: last_order_date=4
  Missing in /test (1):
    sales_order_number=ORD00878279 (customer_account=8276, customer_name=GORHAM'S HOME CENTRE)
  Extra in /test only (1):
    sales_order_number=ORD00838846 (customer_account=8276, customer_name=GORHAM'S HOME CENTRE, salesman_code=LCWalker)
  Value diffs (4):
    sales_order_number=ORD00867452 | last_order_date: live=2026-07-01 test=07/16/2026
    sales_order_number=ORD00509801 | last_order_date: live=2025-01-22 test=02/20/2025
    sales_order_number=ORD00737958 | last_order_date: live=2026-01-05 test=02/03/2026
    sales_order_number=ORD00575437 | last_order_date: live=2025-05-01 test=06/30/2025
  Soft/cosmetic text diffs (not failing): 1

## Sheet: MGrego [DIFF]
  Row key: sales_order_number
  Rows live=122 test=117 matched=107
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 15 live row(s) missing on /test (12% of live rows).
    - 10 /test-only row(s) not on live (9% of /test rows).
    - Value diffs by column: last_order_date=106, po_number=1
  Missing in /test (15):
    sales_order_number=ORD00881572 (customer_account=3053627, customer_name=Amigo 99)
    sales_order_number=ORD00556950 (customer_account=00011016, customer_name=BROADWAY DISCOUNT)
    sales_order_number=ORD00769642 (customer_account=6475, customer_name=DOLLAR RUBY)
    sales_order_number=ORD00711310 (customer_account=00011346, customer_name=Discount Kraze)
    sales_order_number=ORD00858996 (customer_account=00011539, customer_name=Dollar Ruby)
    sales_order_number=ORD00703896 (customer_account=3406999, customer_name=Double Z Group)
    sales_order_number=ORD00562869 (customer_account=00011025, customer_name=FOOD DOUBLE DISCOUNT)
    sales_order_number=ORD00688566 (customer_account=00011187, customer_name=Good city discount)
    sales_order_number=ORD00505294 (customer_account=2940798, customer_name=Jackpot Deals Inc.)
    sales_order_number=ORD00521141 (customer_account=3038570, customer_name=K&S Discount Mart)
    sales_order_number=ORD00711302 (customer_account=3316837, customer_name=LEFFERTS HARDWARE)
    sales_order_number=ORD00672508 (customer_account=8376, customer_name=LINCOLN COMFY SHOP INC (DS))
    sales_order_number=ORD00600591 (customer_account=2966907, customer_name=MEIR GREGO)
    sales_order_number=ORD00656193 (customer_account=2557, customer_name=SUNSET HARDWARE INC)
    sales_order_number=ORD00711725 (customer_account=3350161, customer_name=WEBSTER DISCOUNT)
  Extra in /test only (10):
    sales_order_number=ORD00811588 (customer_account=3053627, customer_name=Amigo 99, salesman_code=MGrego)
    sales_order_number=ORD00608643 (customer_account=00011016, customer_name=BROADWAY DISCOUNT, salesman_code=MGrego)
    sales_order_number=TR-4275 (customer_account=3351105, customer_name=Dollar Kraze #3 (276 Grocery Inc), salesman_code=MGrego)
    sales_order_number=ORD00812412 (customer_account=00011539, customer_name=Dollar Ruby, salesman_code=MGrego)
    sales_order_number=ORD00562883 (customer_account=3406999, customer_name=Double Z Group, salesman_code=MGrego)
    sales_order_number=TR-4347 (customer_account=00011025, customer_name=FOOD DOUBLE DISCOUNT, salesman_code=MGrego)
    sales_order_number=ORD00644125 (customer_account=00011187, customer_name=Good city discount, salesman_code=MGrego)
    sales_order_number=ORD00733218 (customer_account=3316837, customer_name=LEFFERTS HARDWARE, salesman_code=MGrego)
    sales_order_number=ORD00570737 (customer_account=2966907, customer_name=P&M Misc., salesman_code=MGrego)
    sales_order_number=TR-4479 (customer_account=3350161, customer_name=WEBSTER DISCOUNT, salesman_code=MGrego)
  Value diffs (107):
    sales_order_number=ORD00760292 | last_order_date: live=2026-02-11 test=02/20/2026
    sales_order_number=ORD00791806 | last_order_date: live=2026-03-23 test=03/31/2026
    sales_order_number=ORD00639575 | last_order_date: live=2025-08-13 test=08/14/2025
    sales_order_number=ORD00639575 | po_number: live=None test=N/A
    sales_order_number=ORD00703923 | last_order_date: live=2025-11-12 test=11/19/2025
    sales_order_number=ORD00703928 | last_order_date: live=2025-11-12 test=11/19/2025
    sales_order_number=ORD00803791 | last_order_date: live=2026-04-06 test=04/13/2026
    sales_order_number=ORD00665381 | last_order_date: live=2025-09-22 test=10/03/2025
    sales_order_number=ORD00809992 | last_order_date: live=2026-04-14 test=04/23/2026
    sales_order_number=ORD00856138 | last_order_date: live=2026-06-15 test=06/22/2026
    sales_order_number=ORD00520087 | last_order_date: live=2025-02-10 test=04/30/2025
    sales_order_number=ORD00803790 | last_order_date: live=2026-04-06 test=04/13/2026
    sales_order_number=ORD00583507 | last_order_date: live=2025-05-14 test=05/21/2025
    sales_order_number=ORD00741857 | last_order_date: live=2026-01-12 test=01/16/2026
    sales_order_number=ORD00837992 | last_order_date: live=2026-05-20 test=05/29/2026
    sales_order_number=ORD00828172 | last_order_date: live=2026-05-06 test=05/12/2026
    sales_order_number=ORD00704883 | last_order_date: live=2025-11-13 test=11/25/2025
    sales_order_number=ORD00513644 | last_order_date: live=2025-01-29 test=03/05/2025
    sales_order_number=ORD00833241 | last_order_date: live=2026-05-14 test=05/25/2026
    sales_order_number=ORD00524336 | last_order_date: live=2025-02-18 test=04/28/2025
    sales_order_number=ORD00755383 | last_order_date: live=2026-02-03 test=02/09/2026
    sales_order_number=ORD00531939 | last_order_date: live=2025-03-03 test=05/01/2025
    sales_order_number=ORD00818207 | last_order_date: live=2026-04-24 test=04/27/2026
    sales_order_number=ORD00588177 | last_order_date: live=2025-05-21 test=06/09/2025
    sales_order_number=ORD00832660 | last_order_date: live=2026-05-13 test=05/21/2026
    sales_order_number=ORD00828171 | last_order_date: live=2026-05-06 test=05/19/2026
    sales_order_number=ORD00810957 | last_order_date: live=2026-04-15 test=04/23/2026
    sales_order_number=ORD00872151 | last_order_date: live=2026-07-08 test=07/10/2026
    sales_order_number=ORD00829396 | last_order_date: live=2026-05-08 test=05/14/2026
    sales_order_number=ORD00821477 | last_order_date: live=2026-04-28 test=04/30/2026
    sales_order_number=ORD00714320 | last_order_date: live=2025-11-24 test=12/01/2025
    sales_order_number=ORD00533699 | last_order_date: live=2025-03-07 test=04/04/2025
    sales_order_number=ORD00587306 | last_order_date: live=2025-05-20 test=06/26/2025
    sales_order_number=ORD00711227 | last_order_date: live=2025-11-20 test=12/03/2025
    sales_order_number=ORD00608179 | last_order_date: live=2025-06-23 test=07/31/2025
    sales_order_number=ORD00843156 | last_order_date: live=2026-05-27 test=05/29/2026
    sales_order_number=ORD00766174 | last_order_date: live=2026-02-20 test=03/04/2026
    sales_order_number=ORD00584111 | last_order_date: live=2025-05-15 test=05/20/2025
    sales_order_number=ORD00786917 | last_order_date: live=2026-03-17 test=03/27/2026
    sales_order_number=ORD00848121 | last_order_date: live=2026-06-03 test=06/18/2026
    sales_order_number=ORD00674905 | last_order_date: live=2025-10-06 test=10/29/2025
    sales_order_number=ORD00742410 | last_order_date: live=2026-01-13 test=01/23/2026
    sales_order_number=ORD00878245 | last_order_date: live=2026-07-16 test=07/20/2026
    sales_order_number=ORD00516330 | last_order_date: live=2025-02-03 test=03/04/2025
    sales_order_number=ORD00848922 | last_order_date: live=2026-06-04 test=06/18/2026
    sales_order_number=ORD00770700 | last_order_date: live=2026-02-26 test=03/04/2026
    sales_order_number=ORD00832695 | last_order_date: live=2026-05-13 test=05/25/2026
    sales_order_number=ORD00817395 | last_order_date: live=2026-04-23 test=04/28/2026
    sales_order_number=ORD00765552 | last_order_date: live=2026-02-19 test=03/03/2026
    sales_order_number=ORD00872159 | last_order_date: live=2026-07-08 test=07/16/2026
    ... +57 more
  Soft/cosmetic text diffs (not failing): 17

## Sheet: MKolko [DIFF]
  Row key: sales_order_number
  Rows live=145 test=142 matched=127
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 18 live row(s) missing on /test (12% of live rows).
    - 15 /test-only row(s) not on live (11% of /test rows).
    - Value diffs by column: last_order_date=126
  Missing in /test (18):
    sales_order_number=ORD00882399 (customer_account=5507, customer_name=99 CENT & DISCOUNT DEPOT)
    sales_order_number=ORD00871770 (customer_account=3050, customer_name=ADVANTAGE WHOLESALE SUPPLY)
    sales_order_number=ORD00880924 (customer_account=175, customer_name=B. E. ATLAS CO)
    sales_order_number=ORD00881804 (customer_account=00011057, customer_name=BROADWAY FOOD MART)
    sales_order_number=ORD00876708 (customer_account=3506037, customer_name=Bargain Days)
    sales_order_number=ORD00866735 (customer_account=557, customer_name=CORNER HARDWARE & PAINT CENTER)
    sales_order_number=ORD00881712 (customer_account=Church Disc Store, customer_name=Church Disc Store)
    sales_order_number=ORD00881778 (customer_account=00011628, customer_name=Dekalb Food Mart)
    sales_order_number=ORD00815401 (customer_account=9497, customer_name=ERNESTO'S HARDWARE STORE)
    sales_order_number=ORD00883038 (customer_account=8023, customer_name=Goodgram)
    sales_order_number=ORD00873761 (customer_account=5194, customer_name=K & S CURTAIN PLUS)
    sales_order_number=ORD00883224 (customer_account=1364, customer_name=KENNEDY DEPARTMENT STORE)
    sales_order_number=ORD00883198 (customer_account=1493, customer_name=LIBERTY DEPARTMENT STORE (MYRTLE))
    sales_order_number=ORD00870971 (customer_account=9064, customer_name=MONSEY HOUSEWARES)
    sales_order_number=ORD00883242 (customer_account=NORTH VILLAGE APARTM, customer_name=NORTH VILLAGE APARTMENTS)
    sales_order_number=ORD00509748 (customer_account=2037, customer_name=PRICE LINK INC)
    sales_order_number=ORD00729400 (customer_account=2449, customer_name=SUPER DEAL STORES INC)
    sales_order_number=ORD00876509 (customer_account=6966, customer_name=iSupply Solutions (Starco))
  Extra in /test only (15):
    sales_order_number=ORD00833840 (customer_account=5507, customer_name=99 CENT & DISCOUNT DEPOT, salesman_code=MKolko)
    sales_order_number=ORD00867512 (customer_account=3050, customer_name=ADVANTAGE WHOLESALE SUPPLY, salesman_code=MKolko)
    sales_order_number=ORD00856209 (customer_account=175, customer_name=B. E. ATLAS CO., salesman_code=MKolko)
    sales_order_number=ORD00876707 (customer_account=3506037, customer_name=Bargain Days, salesman_code=MKolko)
    sales_order_number=ORD00856973 (customer_account=557, customer_name=CORNER HARDWARE & PAINT CENTER, salesman_code=MKolko)
    sales_order_number=ORD00866628 (customer_account=9497, customer_name=ERNESTO'S HARDWARE STORE, salesman_code=MKolko)
    sales_order_number=ORD00882515 (customer_account=8023, customer_name=GOODGRAM, salesman_code=MKolko)
    sales_order_number=ORD00868105 (customer_account=5194, customer_name=K & S CURTAIN PLUS, salesman_code=MKolko)
    sales_order_number=ORD00853070 (customer_account=1364, customer_name=Kennedy Department Store, salesman_code=MKolko)
    sales_order_number=ORD00828080 (customer_account=1493, customer_name=Liberty Dept. Store (MYRTLE), salesman_code=MKolko)
    sales_order_number=ORD00589206 (customer_account=00011057, customer_name=MAX DEALS (BROADWAY), salesman_code=MKolko)
    sales_order_number=ORD00747707 (customer_account=9064, customer_name=MONSEY HOUSEWARES, salesman_code=MKolko)
    sales_order_number=ORD00843811 (customer_account=NORTH VILLAGE APARTM, customer_name=NORTH VILLAGE APARTMENTS, salesman_code=MKolko)
    sales_order_number=ORD00865989 (customer_account=6966, customer_name=STARCO MAINTENANCE SUPPLIES, salesman_code=MKolko)
    sales_order_number=ORD00733683 (customer_account=2449, customer_name=Super Deal Stores Inc., salesman_code=MKolko)
  Value diffs (126):
    sales_order_number=ORD00652352 | last_order_date: live=2025-09-02 test=09/11/2025
    sales_order_number=ORD00878101 | last_order_date: live=2026-07-16 test=07/17/2026
    sales_order_number=ORD00672686 | last_order_date: live=2025-10-03 test=10/03/2025
    sales_order_number=ORD00847250 | last_order_date: live=2026-06-02 test=06/04/2026
    sales_order_number=ORD00765490 | last_order_date: live=2026-02-19 test=02/27/2026
    sales_order_number=ORD00514722 | last_order_date: live=2025-01-31 test=03/04/2025
    sales_order_number=ORD00876755 | last_order_date: live=2026-07-14 test=07/16/2026
    sales_order_number=ORD00861100 | last_order_date: live=2026-06-22 test=06/29/2026
    sales_order_number=ORD00866879 | last_order_date: live=2026-06-30 test=07/02/2026
    sales_order_number=ORD00809240 | last_order_date: live=2026-04-13 test=04/22/2026
    sales_order_number=ORD00820820 | last_order_date: live=2026-04-27 test=04/30/2026
    sales_order_number=ORD00558780 | last_order_date: live=2025-04-10 test=04/22/2025
    sales_order_number=ORD00828242 | last_order_date: live=2026-05-06 test=05/14/2026
    sales_order_number=ORD00831394 | last_order_date: live=2026-05-11 test=05/18/2026
    sales_order_number=ORD00831377 | last_order_date: live=2026-05-11 test=05/18/2026
    sales_order_number=ORD00826685 | last_order_date: live=2026-05-04 test=05/15/2026
    sales_order_number=ORD00737826 | last_order_date: live=2026-01-05 test=01/08/2026
    sales_order_number=ORD00826616 | last_order_date: live=2026-05-04 test=05/15/2026
    sales_order_number=ORD00826642 | last_order_date: live=2026-05-04 test=05/15/2026
    sales_order_number=ORD00726222 | last_order_date: live=2025-12-08 test=12/11/2025
    sales_order_number=ORD00872300 | last_order_date: live=2026-07-08 test=07/09/2026
    sales_order_number=ORD00862975 | last_order_date: live=2026-06-25 test=06/26/2026
    sales_order_number=ORD00871628 | last_order_date: live=2026-07-07 test=07/14/2026
    sales_order_number=ORD00822362 | last_order_date: live=2026-04-29 test=05/04/2026
    sales_order_number=ORD00837516 | last_order_date: live=2026-05-19 test=05/27/2026
    sales_order_number=ORD00817474 | last_order_date: live=2026-04-23 test=04/24/2026
    sales_order_number=ORD00870877 | last_order_date: live=2026-07-06 test=07/08/2026
    sales_order_number=ORD00748341 | last_order_date: live=2026-01-22 test=01/27/2026
    sales_order_number=ORD00648376 | last_order_date: live=2025-08-27 test=08/29/2025
    sales_order_number=ORD00862451 | last_order_date: live=2026-06-24 test=06/30/2026
    sales_order_number=ORD00877590 | last_order_date: live=2026-07-15 test=07/16/2026
    sales_order_number=ORD00857816 | last_order_date: live=2026-06-17 test=06/18/2026
    sales_order_number=ORD00862445 | last_order_date: live=2026-06-24 test=06/30/2026
    sales_order_number=ORD00876699 | last_order_date: live=2026-07-14 test=07/16/2026
    sales_order_number=ORD00544164 | last_order_date: live=2025-03-20 test=03/24/2025
    sales_order_number=ORD00857733 | last_order_date: live=2026-06-17 test=06/23/2026
    sales_order_number=ORD00863073 | last_order_date: live=2026-06-25 test=06/30/2026
    sales_order_number=ORD00809257 | last_order_date: live=2026-04-13 test=04/21/2026
    sales_order_number=ORD00789408 | last_order_date: live=2026-03-20 test=03/24/2026
    sales_order_number=ORD00702896 | last_order_date: live=2025-11-11 test=11/18/2025
    sales_order_number=ORD00860990 | last_order_date: live=2026-06-22 test=06/29/2026
    sales_order_number=ORD00510759 | last_order_date: live=2025-01-24 test=03/04/2025
    sales_order_number=ORD00822363 | last_order_date: live=2026-04-29 test=05/11/2026
    sales_order_number=ORD00675101 | last_order_date: live=2025-10-06 test=10/23/2025
    sales_order_number=ORD00881553 | last_order_date: live=2026-07-21 test=07/22/2026
    sales_order_number=ORD00880856 | last_order_date: live=2026-07-20 test=07/21/2026
    sales_order_number=ORD00517459 | last_order_date: live=2025-02-05 test=03/04/2025
    sales_order_number=ORD00832850 | last_order_date: live=2026-05-13 test=05/14/2026
    sales_order_number=ORD00832834 | last_order_date: live=2026-05-13 test=05/14/2026
    sales_order_number=ORD00760859 | last_order_date: live=2026-02-12 test=02/18/2026
    ... +76 more
  Soft/cosmetic text diffs (not failing): 47

## Sheet: PMazer [DIFF]
  Row key: sales_order_number
  Rows live=3 test=3 matched=3
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - Value diffs by column: last_order_date=3
  Value diffs (3):
    sales_order_number=ORD00841303 | last_order_date: live=2026-05-25 test=05/29/2026
    sales_order_number=ORD00881135 | last_order_date: live=2026-07-20 test=07/22/2026
    sales_order_number=ORD00810773 | last_order_date: live=2026-04-15 test=04/30/2026
  Soft/cosmetic text diffs (not failing): 1

## Sheet: REdwards [DIFF]
  Row key: sales_order_number
  Rows live=3 test=3 matched=0
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 3 live row(s) missing on /test (100% of live rows).
    - 3 /test-only row(s) not on live (100% of /test rows).
  Missing in /test (3):
    sales_order_number=ORD00880810 (customer_account=9301, customer_name=AMAZON.COM CA, INC. YYZ1)
    sales_order_number=ORD00880789 (customer_account=9300, customer_name=AMAZON.COM DEDC, LLC)
    sales_order_number=ORD00883608 (customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP))
  Extra in /test only (3):
    sales_order_number=ORD00726016 (customer_account=9301, customer_name=Amazon Canada, salesman_code=REdwards)
    sales_order_number=ORD00880771 (customer_account=9300, customer_name=AMAZON.COM DEDC, LLC, salesman_code=REdwards)
    sales_order_number=ORD00883182 (customer_account=9303, customer_name=AMAZON.COM DEDC,LLC (DROPSHIP), salesman_code=REdwards)

## Sheet: Unassigned [DIFF]
  Row key: sales_order_number
  Rows live=17 test=15 matched=12
  Extra columns in /test (ignored): salesman_code
  Patterns:
    - 5 live row(s) missing on /test (29% of live rows).
    - 3 /test-only row(s) not on live (20% of /test rows).
    - Value diffs by column: last_order_date=11, po_number=2, customer_account=1
  Missing in /test (5):
    sales_order_number=ORD00516214 (customer_account=125th 99 Inc., customer_name=125th 99 Inc.)
    sales_order_number=ORD00524846 (customer_account=3247048, customer_name=Dollar Jackpot)
    sales_order_number=ORD00816868 (customer_account=00011552, customer_name=Kevin Venturelli)
    sales_order_number=ORD00516263 (customer_account=MegaDollarMart, customer_name=Mega Dollar Mart)
    sales_order_number=ORD00858403 (customer_account=00011609, customer_name=Swiftcart)
  Extra in /test only (3):
    sales_order_number=TR-4412 (customer_account=Capacity, customer_name=Capacity LLC, salesman_code=Unassigned)
    sales_order_number=TR-4502 (customer_account=00011005, customer_name=DCH BRUNSWICK TOYOTA, salesman_code=Unassigned)
    sales_order_number=TR-4365 (customer_account=3201519, customer_name=Tomche Shabbos of Boro Park, salesman_code=Unassigned)
  Value diffs (14):
    sales_order_number=N/A | customer_account: live=3360379 test=125th 99 Inc.
    sales_order_number=ORD00650860 | last_order_date: live=2025-08-31 test=09/02/2025
    sales_order_number=ORD00650860 | po_number: live=None test=N/A
    sales_order_number=ORD00873121 | last_order_date: live=2026-07-09 test=07/14/2026
    sales_order_number=ORD00728415 | last_order_date: live=2025-12-11 test=12/24/2025
    sales_order_number=ORD00752026 | last_order_date: live=2026-01-28 test=01/29/2026
    sales_order_number=ORD00752026 | po_number: live=None test=N/A
    sales_order_number=ORD00658844 | last_order_date: live=2025-09-12 test=09/17/2025
    sales_order_number=ORD00743036 | last_order_date: live=2026-01-14 test=01/14/2026
    sales_order_number=ORD00613808 | last_order_date: live=2025-07-02 test=07/18/2025
    sales_order_number=ORD00675173 | last_order_date: live=2025-10-06 test=10/17/2025
    sales_order_number=ORD00618645 | last_order_date: live=2025-07-10 test=07/10/2025
    sales_order_number=ORD00868231 | last_order_date: live=2026-07-02 test=07/06/2026
    sales_order_number=ORD00670621 | last_order_date: live=2025-09-30 test=09/30/2025
  Soft/cosmetic text diffs (not failing): 3
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
