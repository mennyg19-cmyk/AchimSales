# Area: reports + Excel

**CodeGraph:** unavailable. Facts from named files.

## Registry (`v3/report_engine/registry.py`)

| key | title | status | notes |
|-----|-------|--------|-------|
| ordered | Ordered | BUILT | salesman_default, builder_version=8 |
| invoiced | Invoiced | BUILT | salesman_default |
| salesman | Salesman | BUILT | |
| number_4 | Number 4 | BUILT | builder_version=5 |
| customer_activity | Customer Activity | BUILT | salesman_default |
| customer_last_order | Customer's Last Order | BUILT | `in_app=True` (own pages) |
| item_averages | Item Averages | BUILT | privileged_only |
| sales_by_state | Sales by State | BUILT | |
| customer_aging | Customer Aging | BACKLOG | must not look runnable |

Builders: `v3/report_engine/reports/{ordered,invoiced,salesman,number_4,customer_activity,customer_last_order,item_averages,sales_by_state}.py`

## Pages + APIs (`web.blueprints.reports`)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/` | `reports_list.html` — built cards, backlog, personal presets, company view cards |
| GET | `/reports/<report_key>` | `report_view.html` (standard grid) |
| POST | `/api/reports/<report_key>/run` | enqueue `report.run` |
| GET | `/api/jobs/<job_id>` | poll |
| POST | `/api/jobs/<job_id>/cancel` | |
| GET | `/api/reports/result/<job_id>` | payload |
| GET | `/api/reports/active` | in-flight bar |
| POST | `/api/reports/runs/<job_id>/keep` | keep run |
| POST | `/api/reports/<report_key>/export/<job_id>` | enqueue Excel |
| GET | `/api/reports/exports/<export_id>/download` | re-checks `_export_in_scope` |
| GET | `/api/reports/exports` | list; scope applied before 15-item cap |
| GET | `/report/customer-last-order` | picker `customer_last_order_pick.html` |
| GET | `/api/report/customer-last-order/customers` | |
| GET | `/api/report/customer-last-order/salesmen` | |
| GET | `/api/report/customer-last-order/<account>/recent-invoiced` | |
| GET | `/report/customer-last-order/<account>` | `customer_last_order_view.html` |
| GET | `/report/customer-last-order/<account>/export` | |
| GET | `/api/reports/lookups/status` | |
| GET | `/api/reports/<report_key>/salesmen` | |
| GET | `/api/reports/<report_key>/customers` | |
| GET | `/api/reports/<report_key>/years` | |
| POST | `/api/reports/<report_key>/preview-body` | email body preview |
| GET | `/api/reports/diagnostics/reporting-api` | |
| GET | `/api/reports/diagnostics/reconcile-salesman-invoiced` | |
| GET | `/api/reports/diagnostics/reconcile-number4-invoiced` | |
| GET/POST | `/api/reports/diagnostics/claim-once` | POST mutates; GET does not |
| GET/POST | `/api/reports/diagnostics/precious-repair` | GET `action=check` only; mutate POST+CSRF |
| GET | `/api/saved-reports` | |
| GET/POST | `/api/reports/<report_key>/presets` | |
| GET/PATCH/DELETE | `/api/reports/presets/<id>` | |
| GET/PUT | `/api/reports/<report_key>/default-view` | |
| GET | `/api/reports/<report_key>/company-views/<id>` | |
| PUT | `/api/reports/<report_key>/company-views` | create/update company view |
| DELETE | `/api/reports/<report_key>/company-views/<id>` | |
| POST | `/api/reports/<report_key>/email-now` | enqueue `report.deliver` |
| GET | `/api/sharepoint/status` `/api/sharepoint/folders` | |
| GET | `/api/onedrive/status` `/api/onedrive/folders` | |

## Frontend

- `v3/web/static_src/js/report.ts` — filters, tabs, grouping, saved views, More → Schedule/Email/Export
- `v3/web/static_src/js/filename_preview.ts`
- `v3/web/static_src/js/sharepoint_picker.ts`
- `v3/web/static_src/js/searchable_picker.ts`
- `v3/web/static_src/js/main.ts` — recent runs bar, theme, jobs bar
- Templates: `reports_list.html`, `report_view.html`, last-order templates

## Reporting stack (no Flask)

- `web.reporting.report_service.ReportService` — HTTP client + builders
- `web.reporting.params` — filter params / salesman post-filter
- `web.reporting.lookups.LookupService`
- `web.reporting.runner.ReportRunner` + `cache.ReportCache`
- `web.reporting.export.build_workbook` — write-only openpyxl; no `outline_level`; nested header/footer RGB; skip sum `Net Price`; salesman bands by field
- `web.reporting.last_order_export`
- `web.reporting.odata_bridge` — live OData path when used
- Reconcile: `reconcile_salesman.py`, `reconcile_number4.py`

## Home cards

Personal `saved_reports` presets + company views (if `can_see_company_views`) deep-link with `preset=` / `cview=`.
