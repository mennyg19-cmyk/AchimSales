Model: gpt-5.2-codex

Proof-of-read:
- Read `rebuild/REBUILD-BRIEF.md` (core SQL-first rebuild target + admin-defined reports).
- Read `rebuild/rebuild-audit/graph-backbone/B-reports-engine.md` (Area B scope + routes).
- CodeGraph: `v3/web/blueprints/reports.py`, reporting runner/service/cache/jobs/params/export/export_jobs.
- CodeGraph: `v3/report_engine/reports/invoiced.py`, `sources/invoiced.py`, `registry.py`, `facts.py`, `contracts.py`.

## 1) COVERAGE SKELETON (Area B)
- [ ] `v3/web/blueprints/reports.py` — reports list/view, run, job status/cancel, result, active runs, exports, lookups, presets, email, diagnostics.
- [ ] Route `GET /` (reports_list) — report index.
- [ ] Route `GET /reports/<key>` (report_view) — viewer page + JS bootstrap.
- [ ] Route `POST /api/reports/<key>/run` (run_report) — enqueue report.run job.
- [ ] Route `GET /api/jobs/<job_id>` (job_status).
- [ ] Route `POST /api/jobs/<job_id>/cancel` (cancel_job).
- [ ] Route `GET /api/reports/result/<job_id>` (report_result).
- [ ] Route `GET /api/reports/active` (active_report_runs).
- [ ] Route `POST /api/reports/<key>/export/<job_id>` (export_report).
- [ ] Route `GET /api/reports/exports/<id>/download` (download_export).
- [ ] Route `GET /api/reports/exports` (list_exports).
- [ ] Route `GET /api/reports/<key>/salesmen` (report_salesmen).
- [ ] Route `GET /api/reports/<key>/customers` (report_customers).
- [ ] Route `GET /api/reports/<key>/years` (report_years).
- [ ] Route `GET /api/reports/lookups/status` (lookup_status).
- [ ] Route `POST /api/reports/<key>/preview-body` (preview_body).
- [ ] Route `POST /api/reports/<key>/email-now` (email_now).
- [ ] Route `GET /api/reports/sharepoint/status` (sharepoint_status).
- [ ] Route `GET /api/reports/sharepoint/folders` (sharepoint_folders).
- [ ] Presets: `GET/POST /api/reports/<key>/presets`, `GET /api/reports/presets/<id>`, `GET /api/saved-reports`.
- [ ] Diagnostics: `GET /api/reports/diagnostics/reporting-api`, `POST /api/reports/diagnostics/claim-once`, `POST /api/reports/diagnostics/precious-repair`.
- [ ] In-app report (deferred math): customer_last_order routes in `reports.py`.

- [ ] `v3/web/reporting/report_service.py` — per-report orchestration + source adapter wiring.
- [ ] `v3/web/reporting/runner.py` — ReportRunner (cache -> build -> store).
- [ ] `v3/web/reporting/cache.py` — cache key + payload storage (scope token).
- [ ] `v3/web/reporting/jobs.py` — report.run job enqueue + handler.
- [ ] `v3/web/reporting/export.py` — Excel export from payload + grouping subtotals.
- [ ] `v3/web/reporting/export_jobs.py` — report.export job enqueue + handler.
- [ ] `v3/web/reporting/params.py` — filter params -> SP params + report_id map.
- [ ] `v3/web/reporting/lookups.py` — customer/salesman lookups + mirror fallback.
- [ ] `v3/web/reporting/http_client.py` — Reporting API client (stored-proc service).

- [ ] `v3/report_engine/registry.py` — report registry (built/backlog list).
- [ ] `v3/report_engine/facts.py` — typed facts (InvoiceChargeFact etc.).
- [ ] `v3/report_engine/contracts.py` — drift ledger + report contracts.
- [ ] `v3/report_engine/reports/invoiced.py` — invoiced builder (tabs + math).
- [ ] `v3/report_engine/sources/invoiced.py` — invoiced SP row adapter.
- [ ] Other report builders present (deferred math audit):
  - [ ] `v3/report_engine/reports/ordered.py`
  - [ ] `v3/report_engine/reports/salesman.py`
  - [ ] `v3/report_engine/reports/number_4.py`
  - [ ] `v3/report_engine/reports/customer_activity.py`
- [ ] Other sources present (deferred math audit):
  - [ ] `v3/report_engine/sources/ordered.py`
  - [ ] `v3/report_engine/sources/invoice_lines.py`
  - [ ] `v3/report_engine/sources/customer_master.py`
  - [ ] `v3/report_engine/sources/released_products.py`

- [ ] `v3/web/static_src/js/report.ts` — viewer (tabs, grouping, export, presets, scheduling).
- [ ] `v3/web/delivery/layout.py` — applies layout/grouping to payload (export/shared).

## 2) TO-FIX (STRUCTURE) — diagnose, don’t redesign

FB1 — Row-level math still in Python (target says SQL should do it).
Where: `v3/report_engine/reports/invoiced.py`, `v3/report_engine/sources/invoiced.py`.
What: totals, credit detection, net-by-invoice, per-customer summaries, commission math, reversal audit.
Why: violates “SQL does all row-level math; app only groups/subtotals”.
Fix direction: move invoice netting, credit flag, commission base/commission, and money columns into the SP; keep only generic grouping/subtotal in app.

FB2 — Builder performs domain-specific aggregations and tab logic.
Where: `v3/report_engine/reports/invoiced.py`.
What: hardcoded tabs, hardcoded column definitions, custom commissions pivot logic.
Why: prevents admin-defined reports; every new report requires code + deploy.
Fix direction: convert to manifest-driven tab/group definitions and generic summarizers; allow “custom math” hooks only as opt-in.

FB3 — Per-report orchestration is hardcoded.
Where: `v3/web/reporting/report_service.py`, `v3/web/reporting/params.py`.
What: `_ORCHESTRATORS` dict, `REPORT_ID_MAP`, YTD extra fetch, custom filters.
Why: hard-coded report list conflicts with “admin-defined reports”.
Fix direction: load report definitions from DB (stored proc, columns, tabs, filters) and build an orchestrator from config.

FB4 — Source-adapter seam is only partly clean.
Where: `v3/report_engine/sources/invoiced.py` + `v3/web/reporting/report_service.py`.
What: adapter computes total and credit flag; service post-filters multi-customer.
Why: logic leaks into adapter/service that should be SQL or generic grouping.
Fix direction: keep adapters as “field rename + type normalize” only; push filtering and credit/total logic into SQL.

FB5 — Registry is static and code-driven.
Where: `v3/report_engine/registry.py`.
What: report list + status baked in code.
Why: blocks admin-defined report creation; only “built/backlog” toggles exist.
Fix direction: move registry to DB table with admin CRUD; keep a small code-level enum only for reserved/system reports.

FB6 — Report UI and backend are tightly coupled to current payload shape.
Where: `v3/web/static_src/js/report.ts`, `v3/web/reporting/export.py`.
What: assumes tab payload includes full rows and column metadata for each tab.
Why: if SQL moves to “one flat table per report,” tabs should be views over that table, not separate data payloads per tab.
Fix direction: normalize payload to a flat row set + tab/view configs; generate tabs client-side/server-side via generic grouping.

FB7 — God files make the engine hard to swap.
Where: `v3/report_engine/reports/invoiced.py` (~526 lines), `v3/web/blueprints/reports.py` (many route concerns), `v3/web/static_src/js/report.ts` (large UI surface).
Why: large mixed-concern files slow migration to config-driven reports.
Fix direction: split by concern (tab config vs grouping engine vs UI widgets); keep “run/export/schedule/presets” modules isolated.

FB8 — Deferred reports still wired into core paths.
Where: `v3/web/reporting/report_service.py`, `v3/report_engine/registry.py`, `v3/web/blueprints/reports.py`.
What: orchestration + registry include ordered/salesman/number_4/customer_activity/customer_last_order.
Why: increases coupling during the invoiced-only first deliverable; harder to isolate SQL-first pivot.
Fix direction: isolate invoiced-only service module or feature flag; keep deferred report wiring behind a registry “inactive” gate.
