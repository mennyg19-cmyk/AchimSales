# Warehouse Dashboard (`/whdashboard`)

Allowlist-only page on the v3 home site (default: `bgrossman@achimonline.com`).
Tiles + drill-down lists over a provider interface. Defaults to **sample**
(synthetic) data; live data when `WH_DASHBOARD_PROVIDER=reporting_api`.

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
| `/whdashboard/{shipments\|loads\|work\|clusters\|waves}` | Open lists |
| `/WHdashboard/{…}` | Same lists |
| `/whdashboard/due_dates` | 404 — coming soon |

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
| `sample` (default) | Synthetic open rows (Nov 11 2026 status totals + synthetic waves) |
| `reporting_api` | Live `ReportingApiClient.run_report` for the warehouse ids below |

### How to turn live data on

Do **not** change in-app App Settings for this. Set process env / Azure App Setting:

1. Keep `REPORTING_API_BASE_URL` and `REPORTING_API_KEY` configured.
2. Set `WH_DASHBOARD_PROVIDER=reporting_api`.
3. Keep `WH_DASHBOARD_ALLOWED_EMAILS=bgrossman@achimonline.com`.
4. Restart the app process so the env is picked up.
5. Open `/whdashboard` while signed in as that email.

Read at **boot only** (`load_config` → `create_app`). If the live provider is
selected but the Reporting API client is not configured, the app logs a warning
and falls back to sample at boot.

## Live Reporting API contract

Site calls:

`POST {REPORTING_API_BASE_URL}/api/reports/{report_id}/run`

with `X-API-Key`. Response shape:

`{report_id, params, row_count, columns, rows:[{...}]}`

| Area | `report_id` | Status filter param | Known open statuses fetched |
|------|-------------|---------------------|-----------------------------|
| Shipments | `whs_shipment_table` | `ShipmentStatus` (verified) | Open, Waved, InProcess, Loaded |
| Loads | `whs_load_table` | `LoadStatus` (by analogy) | Open, Waved, InProcess, Loaded |
| Work | `whs_work_table` | `WorkStatus` (by analogy) | Open, InProcess |
| Clusters | `whs_work_cluster_table` | `WorkClusterStatus` (by analogy) | Open, Passed, InProcess |
| Waves | `whs_wave_table` | `WaveStatus` (by analogy) | Created, Released, Held (+ broad MaxRows safety pull) |

Wave statuses **seen** in Gateway preview 2026-11-19 (`company=achm`, MaxRows=100):
`Created`, `Released`, `Held`, `Shipped`. Known set is recorded in
`KNOWN_WAVE_STATUSES`. Waves also request one unfiltered `MaxRows=10000` page
and merge it so an open status missing from the fetch list is not dropped.
Any open status not in `KNOWN_WAVE_STATUSES` is shown as an
**Unrecognized status values** warning.

Per tile the provider:

1. Calls each known open status separately with `MaxRows=10000` (string).
2. Waves: also one broad `MaxRows` call with no status filter.
3. Merges and dedupes.
4. Always re-filters client-side with the open-status rules below.
5. Keeps only `Company` / `dataAreaId` = `achm` client-side.
6. Waves: also keep `IsDeleted=0` (blank/`false` treated as active).
7. If any single call returns `row_count >= 10000`, shows a visible
   **Possibly truncated** warning.
8. Caches the snapshot for ~5 minutes.
9. On any API error: shows the error, falls back to sample rows, and a clear
   **SAMPLE DATA** banner.

Due dates stay “coming soon”.

## Open-status rules (data layer)

| Area | Open means |
|------|------------|
| Shipments | `ShipmentStatus` ≠ Shipped |
| Loads | `LoadStatus` ≠ Shipped |
| Work | `WorkStatus` not Closed; Cancelled excluded |
| Clusters | `WorkClusterStatus` ≠ Closed (Open, Passed, InProcess) |
| Waves | `WaveStatus` ≠ Shipped (Baruch, Nov 19 2026) |

## Time rules

- Record clocks (`createdDateTime`, `modifiedDateTime`, …): already Eastern —
  display as-is (even when a source labels them GMT).
- Refresh stamps (`UpdatedUtc`, `LastSeenUtc`, `LastImportedUTC`): true GMT/UTC
  (often RFC 822 like `Thu, 05 Nov 2026 09:34:36 GMT`) → America/New_York for
  “Data as of”, labeled `ET`. Newest stamp across shipments, loads, work,
  clusters, and waves.

## Code map

- Access: `v3/web/warehouse/access.py`
- Filters / time / schema: `v3/web/warehouse/filters.py`, `timeutil.py`, `schema.py`
- Sample provider: `v3/web/warehouse/sample.py`
- Live provider: `v3/web/warehouse/reporting_api.py`
- Factory: `v3/web/warehouse/provider.py`
- Blueprint: `v3/web/blueprints/wh_dashboard.py`
- Client: `v3/web/reporting/http_client.py` (`ReportingApiClient`)
