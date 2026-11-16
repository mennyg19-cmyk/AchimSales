# Warehouse Dashboard (`/whdashboard`)

Allowlist-only page on the v3 home site (default: `bgrossman@achimonline.com`).
Front end first: tiles + drill-down lists over a provider interface. This branch
defaults to **sample** (synthetic) data so nothing hits the on-prem Reporting API.

## Access

| Setting | Meaning |
|---------|---------|
| `WH_DASHBOARD_ALLOWED_EMAILS` | Comma-separated emails, compared case-insensitively to the signed-in user's email/UPN. Default `bgrossman@achimonline.com`. |

Not role-based. Admins, developers, magic-link reps, and anyone else off the list get HTTP 403. Check lives in `v3/web/blueprints/wh_dashboard.py` → `_require_wh_access()` (uses `web.warehouse.access.email_may_access_wh_dashboard`). Nav/Settings visibility uses the same allowlist via `wh_dashboard_enabled` in `inject_globals`.

## Routes

| Path | Notes |
|------|-------|
| `/whdashboard` | Canonical main page |
| `/WHdashboard` | Same view (bookmark-friendly casing) |
| `/whdashboard/{shipments\|loads\|work\|clusters}` | Open lists |
| `/WHdashboard/{…}` | Same lists |
| `/whdashboard/waves`, `/whdashboard/due_dates` | 404 — coming soon |

## Local preview

```bash
cd v3
export APP_ENV=dev AUTH_MODE=dev FLASK_SECRET=dev
export WH_DASHBOARD_PROVIDER=sample
export WH_DASHBOARD_ALLOWED_EMAILS=bgrossman@achimonline.com
python -m flask --app web.wsgi:application run --port 5055
```

Sign in with the allowlisted email (dev login), then open
`http://127.0.0.1:5055/whdashboard` (or `/WHdashboard`).

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
- Stub provider: `v3/web/warehouse/reporting_api.py` (disabled by default)

Repo-wide `whs_*` elsewhere is Ordered-report OData (`fetch_whs_sales_lines`), not these tables.

### What Achim AI Gateway exposes (same SQL family, not wired here)

| Gateway `report_key` | Operator procedure (gateway docs) |
|----------------------|-----------------------------------|
| `whs_shipment_table` | `rpt.usp_whsshipmenttable` |
| `whs_load_table` | `rpt.usp_WHSLoadTable` |
| `whs_work_table` | `rpt.usp_WHSWorkTable` |
| `whs_work_cluster_table` | `rpt.usp_whsworkclustertable` |
| `whs_wave_table` | `rpt.usp_whswavetable` |

Gateway notes: SQL Reporting snapshots (not live F&O), `MaxRows` default 100 / max 10000.
Column schemas in the sample provider come from the Nov 11 2026 gateway snapshot —
**not verified** against the office Reporting API response shape.

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

The stub provider is never called unless `WH_DASHBOARD_PROVIDER=reporting_api` and
the client is configured.

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
