Model: gpt-5.6-sol-medium
Runner: spawn
Area: reports-excel
Role: structure
Graph: graph via parent digest

## Proof of read

- `AUDITOR-INSTRUCTIONS.md`: live scope is `/workspace/v3`, application code is read-only, and this pass must report structural problems plus a name/path coverage skeleton.
- `graph-backbone/INDEX.md`: four audit areas, four worker job families, four roles, shared Live/Beta session cookies, and no dashboard blueprint on Beta.
- `graph-backbone/reports-excel.md`: 9 registry keys (8 built, 1 backlog), 29 route-table rows, 5 frontend source entries, 4 templates, and 10 reporting-stack modules.
- Read 29 named source files: registry, 8 builders, the 1,685-line reports blueprint, 4 templates, 5 frontend modules, and 10 reporting modules.

## Structural findings

1. **High — the reports blueprint is a 1,685-line mixed-concern god file.** `web/blueprints/reports.py` combines report pages, job control, result/export APIs, Customer's Last Order, lookups, live infrastructure probes, reconciliation tools, destructive SQLite repair/backup operations, saved views, email delivery, SharePoint, and OneDrive. Operational recovery code and user report request handling therefore share one import surface and one deployment unit.

2. **High — the report client is a 3,384-line mixed-concern god file.** `web/static_src/js/report.ts` owns grid rendering, formatting rules, filtering, grouping, tabs, responsive sizing, run/export polling, lookup widgets, deep links, saved/company/default views, email delivery, two cloud-folder pickers, scheduling, filename templates, and all modal wiring. Changes to unrelated report behaviors collide in one stateful module.

3. **High — the Beta OData bridge can fail open at the row-scope boundary.** `web/reporting/odata_bridge.py` applies salesman scope only when it recognizes one of five column names; if no scope column is found, `_scope_tab` returns the original unfiltered tab. This is structurally weaker than the SQL path's fact-level scope and makes workbook headings part of authorization behavior.

4. **High — report definitions are split across four manually synchronized registries.** Keys and capabilities live separately in `report_engine/registry.py`, `web/blueprints/reports.py` (`REPORT_FILTERS`), `web/reporting/params.py` (`REPORT_ID_MAP`), and `web/reporting/report_service.py` (`_ORCHESTRATORS`). Adding or changing a report requires coordinated edits with no structural completeness check; the in-app report is already a special exception outside the orchestrator map.

5. **Medium — the report page has parallel customer-picker implementations.** The standard report picker is implemented inside `web/static_src/js/report.ts`; a reusable implementation exists in `web/static_src/js/searchable_picker.ts`; Customer's Last Order has a third inline implementation in `web/templates/customer_last_order_pick.html`. Search, 200-row caps, loading states, keyboard behavior, and selected-item rendering can drift.

6. **Medium — cloud-folder picking is duplicated.** `web/static_src/js/report.ts` contains `makeSpPicker` for report email/schedule dialogs while `web/static_src/js/sharepoint_picker.ts` implements a separate picker for master schedules. They use different markup, error handling, root semantics, and selection flows for the same APIs.

7. **Medium — display/export parity depends on duplicated cross-language rules.** Number 4 column ordering, Salesman color bands, nested-group palettes, summability, date/number formatting, and fulfillment fills are independently encoded in `web/static_src/js/report.ts` and `web/reporting/export.py`; Number 4 ordering is also repeated in `report_engine/reports/number_4.py`. Comments asking developers to keep copies synchronized are the only coupling.

8. **Medium — Customer's Last Order bypasses the main export architecture.** `web/blueprints/reports.py` builds its XLSX inline with direct `openpyxl` calls and delegates PDF to `web/reporting/last_order_export.py`, while every standard report uses background export jobs, layout replay, formula-injection protection, styled streaming, expiry, and recent exports. The special report therefore has different safety, formatting, performance, and persistence behavior.

9. **Medium — presentation and behavior remain embedded in templates.** `web/templates/customer_last_order_pick.html` and `web/templates/customer_last_order_view.html` contain their own JavaScript applications; all four templates contain repeated inline styles. The standard viewer also loads Tabulator directly from `unpkg.com` at runtime in `web/templates/report_view.html`, making a third-party CDN part of page availability.

10. **Medium — filename expansion duplicates the full token table.** `previewFilename` and `previewFolder` in `web/static_src/js/filename_preview.ts` each maintain the same date/report/schedule token map. A token can be added to one preview path without the other, while server parity is only documented by a comment.

11. **Low — source comments and current inventory disagree.** `web/reporting/runner.py` still says “the 6 real builders,” while the registry has 8 built reports. `web/static_src/js/sharepoint_picker.ts` says it is for the master-schedules page although it sits in the reports frontend digest. These stale descriptions obscure actual ownership.

12. **Low — the frontend keeps two report-grid modes under one tab contract.** `web/static_src/js/report.ts` treats commission cards as a special non-Tabulator branch throughout column, filter, group, and layout logic. The payload still advertises columns/rows for export, but on-screen behavior silently disables generic controls based on `layout === "commission_cards"`.

## Coverage skeleton

### Reports

- Ordered — `report_engine/reports/ordered.py`
- Invoiced — `report_engine/reports/invoiced.py`
- Salesman — `report_engine/reports/salesman.py`
- Number 4 — `report_engine/reports/number_4.py`
- Customer Activity — `report_engine/reports/customer_activity.py`
- Customer's Last Order — `report_engine/reports/customer_last_order.py`
- Item Averages — `report_engine/reports/item_averages.py`
- Sales by State — `report_engine/reports/sales_by_state.py`
- Customer Aging — `report_engine/registry.py`

### Pages

- Reports — `/`
- Standard report viewer — `/reports/<report_key>`
- Customer's Last Order picker — `/report/customer-last-order`
- Customer's Last Order view — `/report/customer-last-order/<account>`

### Reports page controls

- Built report card — `web/templates/reports_list.html`
- Company view card — `web/templates/reports_list.html`
- My preset card — `web/templates/reports_list.html`
- Coming soon report card — `web/templates/reports_list.html`

### Standard report controls

- Reports back link — `web/templates/report_view.html`
- About this report — `web/templates/report_view.html`
- Filters & options — `web/templates/report_view.html`
- Period — `web/templates/report_view.html`
- From — `web/templates/report_view.html`
- To — `web/templates/report_view.html`
- View — `web/templates/report_view.html`
- Status — `web/templates/report_view.html`
- Year — `web/templates/report_view.html`
- Salesman — `web/templates/report_view.html`
- Customers — `web/templates/report_view.html`
- Selected customer removal — `web/static_src/js/report.ts`
- Run report — `web/templates/report_view.html`
- Email me — `web/templates/report_view.html`
- Run with this body — `web/templates/report_view.html`
- Columns — `web/templates/report_view.html`
- Reset layout — `web/templates/report_view.html`
- Save for — `web/templates/report_view.html`
- Save this view — `web/templates/report_view.html`
- Saved views — `web/templates/report_view.html`
- Default view open — `web/static_src/js/report.ts`
- Company view open — `web/static_src/js/report.ts`
- My view open — `web/static_src/js/report.ts`
- Other user's view open — `web/static_src/js/report.ts`
- Saved view edit — `web/static_src/js/report.ts`
- Saved view delete — `web/static_src/js/report.ts`
- More — `web/templates/report_view.html`
- Schedule — `web/templates/report_view.html`
- API preview — `web/templates/report_view.html`
- Cancel run — `web/templates/report_view.html`
- Report tab — `web/static_src/js/report.ts`
- Tab options — `web/static_src/js/report.ts`
- Duplicate tab — `web/static_src/js/report.ts`
- Rename tab — `web/static_src/js/report.ts`
- Remove tab — `web/static_src/js/report.ts`
- Delete tab — `web/static_src/js/report.ts`
- Restore tab — `web/static_src/js/report.ts`
- Column filter — `web/static_src/js/report.ts`
- Column filter operator — `web/static_src/js/report.ts`
- Column filter value — `web/static_src/js/report.ts`
- Column filter Clear — `web/static_src/js/report.ts`
- Column filter Apply — `web/static_src/js/report.ts`
- Hide column — `web/static_src/js/report.ts`
- Freeze / unfreeze — `web/static_src/js/report.ts`
- Group by this column — `web/static_src/js/report.ts`
- Add subgroup — `web/static_src/js/report.ts`
- Clear grouping — `web/static_src/js/report.ts`
- Remove group — `web/static_src/js/report.ts`
- Show / hide tab — `web/static_src/js/report.ts`
- Show / hide column — `web/static_src/js/report.ts`
- Show all columns — `web/static_src/js/report.ts`
- Refresh — `web/templates/report_view.html`
- Keep this run — `web/templates/report_view.html`
- Export — `web/templates/report_view.html`
- Download Excel now — `web/templates/report_view.html`
- Recent exports — `web/templates/report_view.html`
- Previous export download — `web/static_src/js/report.ts`
- Email — `web/templates/report_view.html`

### Email report controls

- Close — `web/templates/report_view.html`
- Recipients — `web/templates/report_view.html`
- Subject — `web/templates/report_view.html`
- SharePoint breadcrumb — `web/templates/report_view.html`
- SharePoint folder — `web/static_src/js/report.ts`
- Use this folder — `web/static_src/js/report.ts`
- Cancel — `web/templates/report_view.html`
- Send — `web/templates/report_view.html`

### Schedule this view controls

- Close — `web/templates/report_view.html`
- Email to owner — `web/templates/report_view.html`
- Also email — `web/templates/report_view.html`
- CC — `web/templates/report_view.html`
- BCC — `web/templates/report_view.html`
- Frequency — `web/templates/report_view.html`
- Time — `web/templates/report_view.html`
- Days of week — `web/templates/report_view.html`
- Day of month — `web/templates/report_view.html`
- Filename template — `web/templates/report_view.html`
- Report name token — `web/templates/report_view.html`
- Schedule name token — `web/templates/report_view.html`
- MM token — `web/templates/report_view.html`
- Month token — `web/templates/report_view.html`
- YYYY token — `web/templates/report_view.html`
- Period token — `web/templates/report_view.html`
- DD token — `web/templates/report_view.html`
- Weekday token — `web/templates/report_view.html`
- OneDrive breadcrumb — `web/templates/report_view.html`
- OneDrive folder — `web/static_src/js/report.ts`
- OneDrive Use this folder — `web/static_src/js/report.ts`
- SharePoint breadcrumb — `web/templates/report_view.html`
- SharePoint folder — `web/static_src/js/report.ts`
- SharePoint Use this folder — `web/static_src/js/report.ts`
- Email me when there is no data — `web/templates/report_view.html`
- Email test addresses when there is no data — `web/templates/report_view.html`
- Cancel — `web/templates/report_view.html`
- Save schedule — `web/templates/report_view.html`

### Customer's Last Order picker controls

- Reports back link — `web/templates/customer_last_order_pick.html`
- Salesman — `web/templates/customer_last_order_pick.html`
- Customer search — `web/templates/customer_last_order_pick.html`
- Customer row — `web/templates/customer_last_order_pick.html`

### Customer's Last Order view controls

- Pick a different customer — `web/templates/customer_last_order_view.html`
- Add previous order — `web/templates/customer_last_order_view.html`
- Export — `web/templates/customer_last_order_view.html`
- Excel — `web/templates/customer_last_order_view.html`
- PDF — `web/templates/customer_last_order_view.html`
- Export Close — `web/templates/customer_last_order_view.html`
- Export Cancel — `web/templates/customer_last_order_view.html`
- Previous order checkbox — `web/templates/customer_last_order_view.html`
- Previous order Close — `web/templates/customer_last_order_view.html`
- Previous order Cancel — `web/templates/customer_last_order_view.html`
- Previous order Apply — `web/templates/customer_last_order_view.html`

### Global report-run controls

- Recent Reports — `web/static_src/js/main.ts`
- Minimize — `web/static_src/js/main.ts`
- Report run row — `web/static_src/js/main.ts`
- Name kept run — `web/static_src/js/main.ts`

## CodeGraph queries unavailable

- `codegraph explore "report registry route run job result export"`
- `codegraph callers ReportService.builder_for`
- `codegraph impact REPORT_FILTERS`
- `codegraph impact build_workbook`
- `codegraph explore "saved report default view company view schedule"`
