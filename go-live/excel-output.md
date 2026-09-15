# Schedule / Excel output vs expected (local, no D365)

**When:** 2026-09-02
**Blocker:** this VM has no `REPORTING_API_BASE_URL` / key, no Graph mail, no Entra. Live overnight files cannot be produced here.

## What we could check

Pytest `test_reporting` + filename + scheduling + catchup: **109 passed** (batch 1). Re-run 2026-09-02 23:16 UTC: `test_reporting.py` + `test_filename_template.py` + `test_delivery.py` + `test_sabbath.py` → **100 passed**.

| Expected (inventory) | Evidence |
|----------------------|----------|
| Net Price never summed on group / grand totals; Extended Price still sums | `test_export_does_not_sum_net_price_on_group_footers` |
| No Excel outline/collapse gutter (`outline_level` = 0) | `test_export_does_not_set_row_outline_levels` |
| Nested group shades; 2-level inner footer `#9CA3AF` | `nest_footer_rgb(1, 2)` → `_FOOTER_SHADES[1]` = `#9CA3AF`; `test_export_nested_group_shades_outer_darker` |
| New schedule filename `{Schedule}_{MM}-{DD}-{YYYY}` | `test_default_template_uses_schedule_name_and_date`; wizard preview in batch 2 |
| Layout replay (hide/reorder/clones) on send | `tests/test_delivery.py` expand_clones / apply_layout |
| Sabbath skip default on; Run now bypasses | `tests/test_sabbath.py` + scheduling suite |
| Catch-up windows | `tests/test_catchup.py` |

## What we could not check here

- Real D365 workbooks from Run report or Schedule Run now.
- Graph attach vs 2.5 MB link.
- Fan-out CC/BCC drop (F10) on a live mail.
- Empty-data mail (“email me when no data”) against Graph.

Local `schedule_runs` (6 rows): every status `failure`, debug `REPORTING_API_BASE_URL/KEY not set`. Those are seeded **master** jobs (Daily Invoiced/Ordered/Number 4, 9am salesman jobs) firing in this isolated sqlite. They do **not** mean production Azure is failing.

To compare live files vs expected: need Reporting API + Graph on a machine that can hit D365, or a copy of a production outbox workbook.
