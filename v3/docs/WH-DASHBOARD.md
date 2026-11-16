# Warehouse Dashboard (`/WHdashboard`)

Admin/developer-only page on the v3 home site. Front end first: tiles + drill-down
lists over a provider interface. This branch defaults to **sample** (synthetic)
data so nothing hits the on-prem Reporting API.

## Local preview

```bash
cd v3
export APP_ENV=dev AUTH_MODE=dev FLASK_SECRET=dev
export WH_DASHBOARD_PROVIDER=sample
python -m flask --app web.wsgi:application run --port 5055
```

Sign in with the dev login as an **admin** (or developer), then open
`http://127.0.0.1:5055/WHdashboard`.

## Provider switch

| `WH_DASHBOARD_PROVIDER` | Behavior |
|-------------------------|----------|
| `sample` (default) | Synthetic open rows sized to the Nov 11 2026 status totals |
| `reporting_api` | `ReportingApiClient.run_report` for the ids below — **do not enable** until office confirms the catalog |

## Live data source (investigation)

The site calls the on-prem Reporting API with:

`POST {REPORTING_API_BASE_URL}/api/reports/{report_id}/run`

### What exists in this Flask repo

- `ReportingApiClient` in `v3/web/reporting/http_client.py`
- In-app `REPORT_ID_MAP` in `v3/web/reporting/params.py` — **no warehouse keys**
- No `whs_shipment_table` / `whs_load_table` / `whs_work_*` / `whs_wave_table` strings under `v3/`

Repo-wide `whs_*` elsewhere is Ordered-report OData (`fetch_whs_sales_lines`), not these tables.

### What Achim AI Gateway exposes (same SQL family, not wired here)

| Gateway `report_key` | Operator procedure (gateway docs) |
|----------------------|-----------------------------------|
| `whs_shipment_table` | `rpt.usp_whsshipmenttable` |
| `whs_load_table` | `rpt.usp_WHSLoadTable` |
| `whs_work_table` | `rpt.usp_WHSWorkTable` |
| `whs_work_cluster_table` | `rpt.usp_whsworkclustertable` |
| `whs_wave_table` | `rpt.usp_whswavetable` |

Gateway notes: SQL Reporting snapshots (not live F&O), `MaxRows` default 100 / max 10000,
filters such as company, ids, status, date range, `IncludeDeleted`. Column schemas in
this repo’s sample provider come from the Nov 11 2026 gateway snapshot attached to
the build brief — **not verified** against the office Reporting API response shape.

### What office needs to expose for the live provider

1. Confirm each `report_id` above is registered on the on-prem catalog at
   `/api/reports/{report_id}/run` (exact id strings; casing matters).
2. Confirm SP parameter names (PascalCase expected by this app’s client, e.g.
   `MaxRows`, `IncludeDeleted`, plus any status/date filters).
3. Confirm open lists can return more than 10k rows or provide paging — gateway
   caps MaxRows at 10000.
4. Confirm refresh stamps (`UpdatedUtc` / `LastSeenUtc` / `LastImportedUTC`) are
   present so “Data as of” can convert true UTC → Eastern.
5. Do **not** point `REPORTING_API_BASE_URL` at reports.achimonline.com.

The stub provider is `v3/web/warehouse/reporting_api.py`. It is never called unless
`WH_DASHBOARD_PROVIDER=reporting_api` and the client is configured.

## Open-status rules (data layer)

| Area | Open means |
|------|------------|
| Shipments | `ShipmentStatus` ≠ Shipped |
| Loads | `LoadStatus` ≠ Shipped |
| Work | `WorkStatus` not Closed; Cancelled excluded |
| Clusters | `WorkClusterStatus` ≠ Closed |
| Waves (placeholder) | not Picked or Shipped |

## Time rules

- Record clocks (`createdDateTime`, `modifiedDateTime`, …): already Eastern — display as-is.
- Refresh stamps (`UpdatedUtc`, `LastSeenUtc`, `LastImportedUTC`): true UTC → ET for “Data as of”.
