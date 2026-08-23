# Grill notes — Beta additions (2026-08-06 evening)

Model: gpt-5.6-terra-high (implementation spawn)
Runner: spawn (parent = Grok; Everyday build)

## Goal
Beta/v3 polish: default Ordered grouping, durable run resume + Keep, salesman
color bands on screen + Excel, schedule filename template GUI, Last Order
export (Excel + PDF).

## Locked decisions

1. **Default grouping — Ordered only for now**
   - Tabs: Summary, By Customer, By Order → group by Salesman (already set on
     SQL builder via `default_group`).
   - OData bridge must attach the same `default_group` for Ordered sheet keys
     so Beta-on-OData matches Test.
   - Do NOT add defaults to invoiced / customer_activity / salesman yet.

2. **Previously run reports**
   - Default resume window: **48 hours** (replace today’s ~10 min
     `_RECENT_DONE_SECONDS = 600`).
   - Payload cache prune must match (≥48h) so resume does not 404.
   - **Keep** button: extends retention to **30 days**.
   - Cap: **~5 Kept runs per user**; if over cap, drop oldest Kept (or refuse
     with clear message — prefer drop oldest Kept).
   - Keep is per finished run (job id); UI on report view when a result is
     showing.

3. **Salesman color coding — screen AND Excel**
   - Match Live `_apply_color_bands`: blue (month cols), green (YTD), purple
     (full year), red for negatives.
   - Screen: Tabulator cell formatters / CSS on salesman month tabs.
   - Excel: apply fonts while appending in streaming write-only export (do NOT
     switch back to full workbook mode). Prefer report-specific styling hook
     in `v3/web/reporting/export.py` for salesman tabs only.

4. **Scheduled export filename template GUI**
   - Token picker + live preview for schedule/master-schedule filename.
   - Tokens at least: `{YYYY}`, `{YY}`, `{MM}`, `{M}`, `{Month}`, `{Mon}`,
     `{DD}`, `{D}`, `{HH}`, `{mm}`, `{ss}`, `{Report}`, `{Period}` (if available).
   - Resolve at delivery time from run/Eastern “now” (or report period end —
     use Eastern now unless period is clearly available).
   - Persist template on schedule row (new column or fold into existing name /
     sharepoint path field — prefer dedicated `filename_template` if schema
     allows; else document the choice in DECISION-LOG).

5. **Last Order export UX**
   - One **Export** button → popup: **Excel** | **PDF** | Cancel.
   - Build from current on-screen last-order data (headers + rolled lines).

## Validation
- Ordered (SQL + OData if flipped): Summary/By Customer/By Order open grouped
  by Salesman.
- Run Ordered → leave app → return within 48h → same result resumes.
- Keep a run → still resumable after >48h and <30d; 6th Keep drops oldest.
- Salesman report: screen fonts banded; Excel export matches Live bands.
- Schedule create/edit: insert tokens, preview updates, delivered file uses
  resolved name.
- Last Order: Export → Excel downloads xlsx; Export → PDF downloads pdf.

## Out of scope
- Default grouping on non-Ordered reports.
- Changing Live OData writers.
- Deploy (commit + push only unless user asks deploy).
