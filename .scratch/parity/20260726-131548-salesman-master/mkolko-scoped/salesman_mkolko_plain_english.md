# Salesman MKolko-scoped parity

Live MKolko Jun 2026.xlsx (yesterday run) vs /test filtered to Salesman == MKolko.

- Hard diffs (all months): **7994**
- Jan coverage: live 144 / test 138 / matched **137** (keyed by Cust. #)
- Jan missing on /test: 7 (salesman header 012/MKolko, Grand total, a few accounts)
- Jan extra on /test: 1

## Noise vs money

- sort_number: live = row index (2,3,4...); /test = salesman number 0012 on every row.
  About 136 diffs per month. Layout only, not sales math.
- Remaining Jan value-diff hotspots (from patterns):
  - 7 live row(s) missing on /test (5% of live rows).
  - 1 /test-only row(s) not on live (1% of /test rows).
  - Value diffs by column: sort_number=136, sales_year_to_date_2025=103, this_year_to_last_year_ytd_full_year=87, sales_year_to_date_2026=64, sales_2025_jan_thru_january=46

Files under: .scratch/parity/20260726-131548-salesman-master/mkolko-scoped
