# Parity: number_4

- Params: `{'mode': 'both'}`
- Live file: `.scratch\parity\20260724-174457-number_4\number_4__live.xlsx`
- Test file: `.scratch\parity\20260724-174457-number_4\number_4__test.xlsx`

_Compare mode: key-matched rows. Ignores formatting, column order, and columns that exist only on /test. Soft name-format diffs (e.g. `Meir Grego` vs `Grego, Meir`) do not fail._

## Summary

- Hard differences: **2**
- Missing sheets in /test: ['12 Months', 'Year to Date']
- Extra sheets in /test (ignored): ['By Customer', 'By Item']
- Per sheet: 12 Months=MISSING_TEST(0), Year to Date=MISSING_TEST(0), By Customer=SKIP, By Item=SKIP
- Result: **DIFFERENCES FOUND**

## Patterns + detail

```
Data comparison: .scratch\parity\20260724-174457-number_4\number_4__live.xlsx vs .scratch\parity\20260724-174457-number_4\number_4__test.xlsx
Hard differences: 2
Result: DIFFERENCES FOUND
Missing sheets in /test: 12 Months, Year to Date
Extra sheets in /test (ignored): By Customer, By Item

## Sheet: 12 Months [MISSING_TEST]
  Sheet present on live, missing on /test.
  Rows live=0 test=0 matched=0

## Sheet: Year to Date [MISSING_TEST]
  Sheet present on live, missing on /test.
  Rows live=0 test=0 matched=0

## Sheet: By Customer [SKIP]
  Extra sheet on /test only — ignored per parity rules.
  Rows live=0 test=0 matched=0

## Sheet: By Item [SKIP]
  Extra sheet on /test only — ignored per parity rules.
  Rows live=0 test=0 matched=0
```

_Live is the baseline. Review each difference: intentional product change (accept) vs bug (fix on /test)._
