# Graph backbone — Area B: Reports backend + report engine

Factual map only. Scope = invoiced report path end-to-end. Note other reports
(ordered, salesman, number_4, customer_activity, customer_last_order) exist but
are DEFERRED — record their endpoints, don't deep-audit their math.

## Blueprint (`v3/web/blueprints/reports.py`)
Routes (each = a feature to inventory):
- `GET /` reports_list; `GET /reports/<key>` report_view.
- `POST /api/reports/<key>/run` run_report → enqueue durable job (202 + job_id).
- `GET /api/jobs/<job_id>` job_status; `POST /api/jobs/<job_id>/cancel` cancel_job.
- `GET /api/reports/result/<job_id>` report_result (cached payload, scope-checked).
- `GET /api/reports/active` active_report_runs (status-bar/resume; owner-scoped).
- `POST /api/reports/<key>/export/<job_id>` export_report (background xlsx);
  `GET .../exports/<id>/download`; `GET .../exports` list.
- Lookups: `/api/reports/<key>/salesmen|customers|years`, `/lookups/status`.
- `POST /api/reports/<key>/preview-body` (dev API preview).
- Presets: `GET/POST /api/reports/<key>/presets`, `GET /api/reports/presets/<id>`,
  `GET /api/saved-reports`.
- `POST /api/reports/<key>/email-now`; `/api/sharepoint/status|folders`.
- Diagnostics (dev/admin): reporting-api, claim-once, precious-repair.

## Reporting orchestration (`v3/web/reporting/`)
- `params.py` — translate UI filter params → SP/report params (period→dates, etc.).
- `runner.py` ReportRunner — run builder, cache result by scope-safe key.
- `report_service.py` — builder resolver / service wiring.
- `http_client.py` — calls on-prem Reporting API (the stored-proc service).
- `cache.py` — scope-safe cache key (`build_cache_key`, `canonical_scope_token`).
- `jobs.py` — `enqueue_report_run`, `make_report_run_handler` (JOB_TYPE report.run);
  job.params carries report_key/identity/visible_keys/builder_version/params.
- `export.py` / `export_jobs.py` — streaming openpyxl Excel build (background job).
- `lookups.py` — customers/salesmen lookups + ensure/resync.

## Report engine (`v3/report_engine/`) — pure, shared (web + CLI)
- `registry.py` — report registry; `ReportStatus`, `built_reports()`, `get(key)`,
  spec has key/title/builder_version/status/in_app.
- `contracts.py`, `lib.py` (`salesman_key`), `dates.py` (periods, D365_GO_LIVE).
- `facts.py` — typed facts. INVOICED uses `InvoiceChargeFact`:
  invoice_number, invoice_date, customer_account, customer_name,
  sales_order_number, subtotal, tariff, freight, cc, misc, total, sales_group,
  salesman_name, is_credit, commission_pct (fraction; 0.06=6%).
- `reports/invoiced.py` — invoiced builder: tabs (Summary, By Customer, By Item,
  By Order, By Salesman [NET of credits], Full Data, Commissions cards), money
  columns incl. misc charges, commission = net*rate (SP `commission` per row,
  salesman-master fallback). NO SalesmanNumber column (removed).
- `sources/invoiced.py` — Reporting API rows → InvoiceChargeFact (the thin adapter).
- `sources/invoice_lines.py` — item-level (Number 4, deferred).

## Reference: LIVE invoiced (format source of truth)
- `reports/invoiced/…` (top-level, the LIVE app) — columns/order/format the rebuild
  must match. Codegraph indexes it (e.g. `reports/invoiced/runner.py`).

## What auditors must cover (Area B)
- Inventory: every route above + exactly what the invoiced report returns
  (tabs, columns, math already verified this year: misc charges, by-salesman net,
  commission column). Params/filters the invoiced report accepts.
- Structure: where math currently lives (engine vs app) vs the new "SQL does the
  math, app only groups/subtotals" target; the source-adapter seam; cache + job
  wiring; dead/deferred-report coupling.
