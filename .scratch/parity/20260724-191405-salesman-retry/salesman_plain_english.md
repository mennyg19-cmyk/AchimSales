# Salesman report — plain-English breakdown

Source run: `20260724-191405-salesman-retry` (not re-downloaded this session).

## The big picture (most of the 16k "diffs")

**Live and /test were not the same report scope.**

- Live January is **MKolko's book only**: a header row `MKolko`, ~130 customers, then `Total for: MKolko`.
- /test January is **every salesman**: ~900+ customers (MKolko ~138, plus HKaufman, MGrego, BLevin, … and ~400 with blank salesman).

So hundreds of "/test-only" rows are simply **other reps' customers** that live never included. That is not a math bug — it is an apples-to-oranges download (likely the live cookie was a salesman/scoped session).

When we match by **customer account** instead of name:

- Almost every real live customer **is** on /test (~129 of ~131).
- The "missing on /test" list from the auto-comparer was mostly **name spelling** (`A & B Department Store` vs `A & B Dept. Store`) plus the MKolko header/total rows.

## What is still worth reviewing (real gaps)

Among customers that exist on **both** sides (shared account numbers), January **Sales Year to Date 2026**:

- **Agree:** ~76
- **Disagree:** ~53

Examples of real dollar drift:

| Account | Customer | Live YTD 2026 | /test YTD 2026 |
|---------|----------|---------------|----------------|
| 11247 | Value Queen (MAX DEALS) | 3,779 | 4,872 |
| 1493 | LIBERTY DEPARTMENT STORE (MYRTLE) | 10,139 | 10,305 |
| 11233 | Home Square | -1,062 | 0 |
| 2449 | SUPER DEAL STORES INC | -2,353 | 0 |

Some gaps are pennies (rounding). Others are material (credits showing on live as negative YTD, zero on /test).

## Other systematic quirks

1. **Sort Number** — live fills 1, 2, 3…; /test leaves it blank. Layout only.
2. **/test has a Salesman column** live does not (extra column — ignored by comparer).
3. **Same pattern every month** (Jan–Dec) — one scope/math issue, not twelve separate ones.
4. Auto-comparer keyed by **customer name**, which inflates missing/extra counts when names are abbreviated differently.

## What to do next for salesman

1. Re-run parity with an **admin / company-wide** live session (same scope as /test), **or** filter /test to MKolko only and compare that slice.
2. Then review the remaining **YTD / month dollar** disagreements on matched accounts (credits and rounding first).
