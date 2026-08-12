# Salesman parity (master vs /test) â€” plain English

- Folder: .scratch/parity/20260726-131548-salesman-master
- Live file: **Monthly Salesmen Report Jun 2026.xlsx** (763,097 bytes)
- /test file: 1,012,010 bytes
- Hard diffs: **27530** across 12 month sheets

## What this run fixed

Earlier salesman parity compared live **MKolko-only** (~213 KB) to /test all-salesmen (~1 MB).
This run uses the live **master** workbook (all salesmen).

## What still looks wrong (Jan as example)

- Live rows keyed: 559; /test: 915; matched: 233
- Missing on /test (count): 326

Themes:
1. **Row matching is weak** â€” comparer keys on customer *name* (+ empty salesman_code).
   Live and /test often spell the same store differently
   (e.g. PARKSIDE BARGAINS vs PARKSIDE BARGAINS (MAQDADY LLC)), so matched count stays low.
2. **Layout difference** â€” live puts salesman group headers in the Cust.# / Name columns;
   /test has a separate Salesman column (ignored as /test-only) and starts on customers.
3. **sort_number** â€” live filled, /test empty/zero on matched rows.
4. After name-match noise, leftover money columns still disagree on some shared accounts
   (YTD / month $). Need account-keyed compare to size that cleanly.

## Suggested next step

Key salesman rows by **Cust. #** (customer account), skip salesman header/total rows,
then re-summarize money diffs. Do not treat the 27k hard count as raw math yet.
