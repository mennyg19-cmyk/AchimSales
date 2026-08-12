# Ordered Full Data — line vs header date probe

Period: 2026-07-01 … 2026-07-31 (parity run `20260804-193031-postfix`).

## Exports

| File | What |
|------|------|
| `full_data_coverage_diffs.xlsx` | 264 live_only + 704 test_only Full Data lines |
| `odata_header_vs_line_dates_enriched.xlsx` | Per-line OData header + line created dates + bucket |

## OData fields

- Header create: `SalesOrderHeadersV3.OrderCreationDateTime` (fallback: `SalesTableCDREntities.SysCreatedDateTime` when HeadersV3 returns nothing)
- Line create: `SalesLineCDREntities.SysCreatedDateTime`

## Does “lines added after SO date” reconcile the coverage diffs?

**Partly — only a small slice.**

| Bucket (non-TZ) | Count | Meaning |
|-----------------|------:|---------|
| `explained_line_in_header_out` | 8 | Header created **outside** July; line created **in** July → TEST keeps, LIVE drops. **This is the hypothesis.** |
| `test_only_missing_from_live_odata_headers` | 523 | SO not returned by `SalesOrderHeadersV3` at all (LIVE blind), but `SalesTableCDR` says header was created **in July** and lines are in July. **Not** a line-later-than-header story — LIVE OData entity gap. |
| `both_in_period_other_cause` | 47 | Header and line both in July. Mostly **live_only fractional LineNums** (delivery schedule / split lines) that TEST does not emit. |
| TZ edge (`tz_edge=yes`) | 344 | Report OrderDate on month edge vs UTC OData day (e.g. report 2026-07-31, OData 2026-08-01). |

### Clear date-gate examples (hypothesis true)

Only **8** lines, e.g. ORD00863771 / ORD00865884 / ORD00865989 — header late June, lines added in July.

### What this means for signing off TEST ordered

- The **desired rule** (filter by **line created date**) is confirmed on the handful of true late-add lines.
- Most **test_only** volume in this run is **not** explained by that rule. The big pile is orders LIVE never sees via `SalesOrderHeadersV3` even though CDR/SQL has them in July.
- Most **live_only** volume is **fractional line numbers** with matching July dates — a line-identity / delivery-schedule difference, not a date gate.

**Recommendation:** do **not** treat this probe alone as a full sign-off that “all ordered diffs are late lines.” It does support that TEST’s line-created-date gate is the right product rule for late-added lines; remaining gaps need a separate call (accept LIVE OData holes + fractional-line omission, or chase them).

