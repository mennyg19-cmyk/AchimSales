# D365 Sales Reports

Automated sales reporting from Dynamics 365 F&O via OData. Reports run on
scheduled Azure Automation jobs, on demand via a Flask web app, or locally
from the CLI.

## Reports

| Report | CLI Command | Output Directory |
|--------|-------------|------------------|
| Ordered Report | `python run.py ordered` | Direct Reports/Ordered Report/{period}/ |
| Invoiced Report | `python run.py invoiced` | Direct Reports/Invoiced Report/{period}/ |
| Shipped Report | `python run.py invoiced --salesman <name>` | Direct Reports/Salesman Report/Shipped Report/{period}/ |
| Salesman Report | `python run.py salesman` | Direct Reports/Salesman Report/{period}/ |
| Number 4 Report | `python run.py number_4` | Direct Reports/Number 4 Report/{sub}/{period}/ |
| Customer Activity | `python run.py customer_activity` | Direct Reports/Customer Activity/ |

## CLI Usage

```
python run.py ordered                                    # all default periods
python run.py ordered --period daily                     # single period
python run.py ordered --period mtd
python run.py ordered --customer 9300 9301               # filter by customer
python run.py ordered --from 2026-01-01 --to 2026-01-31 # custom date range
python run.py invoiced --salesman all --email            # shipped reports for all salesmen
```

## How It Runs

### Azure Automation (production)

`runbooks/universal_runbook.py` is the sole runbook used in Azure Automation.
It downloads the codebase from SharePoint, imports the appropriate report
runner via `report_registry.json`, runs it, uploads the output, and sends a
heartbeat email.

```
universal_runbook.py ordered --period daily
# Amazon ordered schedule (customers 9300/9301):
#   ordered --customer 9300 9301 --period last_7_days --email
```

### Web App (on-demand)

The Flask app in `webapp/` is deployed to Azure App Service via `deploy.ps1`.
Users authenticate with Microsoft Entra ID and can run any report on demand.

```powershell
.\deploy.ps1              # build zip and deploy to Azure
python app.py             # run locally on port 5001
```

### Local CLI

```
pip install -r requirements.txt
cp .env.example .env      # fill in credentials
python run.py ordered
```

### Live vs /test vs /legacy vs /test-next

| Mount | Code | Role |
|-------|------|------|
| `/` | `v3/` (`is_beta`) | Site home — reports; hybrid SQL/OData per report |
| `/legacy` | `webapp/` | Former Live — OData, Excel-first, email distributions |
| `/test` | `v3/` | SQL sandbox — direct link only |
| `/beta` | — | Redirects to `/` (old bookmarks) |
| `/test-next` | `rebuild/` | Rebuild preview — retire after home is stable |

Enable the home swap with `BETA_MOUNT_ENABLED=1` (already on in prod). If Beta fails to boot, `/` stays the old Live app. `/test` still needs `V3_MOUNT_ENABLED=1`.
Developers flip SQL/OData per report under Developer Tools → Beta report data sources (on `/legacy` settings).

On the home site, **Previously run** (header) opens recent and kept runs. **Keep this run**
asks for an optional name; the bottom-right pill can be minimized.

On the home site, **Settings** is the control panel (same ~800px width as Live): You,
People, Reports, Delivery, History, and (developers) Database explorer,
notification diagnostic, and beta SQL/OData sources. Live Email Distributions
stay on Live only. Beta's sqlite file is on local disk (`BETA_PRECIOUS_DB_PATH`)
and is restored/replicated by Litestream (same as `/test`), so Settings like
schedule test mode survive an App Service recycle.

### Live vs /test parity

Compares Excel from legacy live (`/legacy`, OData) and `/test` (Reporting API) with the same
params. Writes a per-report diff under `.scratch/parity/<stamp>/`.

```powershell
# After signing in in the browser, copy cookie values:
#   session     -> PARITY_LIVE_COOKIE
#   v3_session  -> PARITY_TEST_COOKIE
$env:PARITY_LIVE_COOKIE = "..."
$env:PARITY_TEST_COOKIE = "..."
python -m tools.parity
python -m tools.parity --report invoiced
```

### OneDrive deployment mirror

Develop only in this D: checkout. The company OneDrive folder is a one-way
SharePoint deployment/reference mirror; do not edit its source files directly.

```powershell
.\tools\sync-to-onedrive.ps1 -WhatIf  # preview changes
.\tools\sync-to-onedrive.ps1          # copy new and changed source files
.\tools\sync-to-onedrive.ps1 -Prune   # also remove stale mirrored source files
```

The sync excludes Git metadata, local environment files, dependencies, caches,
logs, archives, and report output.

## Environment Variables

See `.env.example` for all required variables. Key groups:

- **D365**: `D365_ENV_URL`, `D365_TENANT_ID`, `D365_CLIENT_ID`, `D365_CLIENT_SECRET`, `D365_COMPANY_ID`
- **Graph/SharePoint**: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `SP_SITE_URL`
- **Graph app permissions (Application, not Delegated)** — Entra → the app in `GRAPH_CLIENT_ID` → API permissions → **Grant admin consent**:
  - `Mail.Send` — send schedule mail as `EMAIL_FROM_ADDRESS`
  - `Files.ReadWrite.All` — list/write a user's OneDrive (`/users/{email}/drive`). Root listing is `…/drive/root/children` (not `root::/children`).
  - `Sites.ReadWrite.All` — list/write the SharePoint site in `SP_SITE_URL` (or `Sites.Selected` plus a site grant)
  A 401 from the folder picker is usually a rejected token (secret expired, or consent never granted). A 403 is a valid token that still cannot read that drive.
- **Email**: `AMAZON_EMAIL_FROM`, `AMAZON_EMAIL_RECIPIENTS` (customer-filtered Ordered `--email` runs)
- **Web App**: `FLASK_SECRET_KEY`, `DEV_BYPASS_AUTH`

## Directory Structure

```
scripts/
  app.py                    # Azure App Service / local entry point (gunicorn)
  run.py                    # CLI entry point for all reports
  deploy.ps1                # Deploy webapp to Azure App Service
  requirements.txt          # Python deps for CLI / runbooks
  report_registry.json      # Report definitions for universal_runbook
  .env.example              # Environment variable template

  config/
    settings.py             # Central config (Azure Automation vars + .env)
    paths.py                # Output path resolution
    salesman_map.py         # Salesman lookup (delegates to Excel)
    salesman_excel.py       # Loads salesman data from salesman_map.xlsx
    salesman_map.xlsx       # Editable salesman/subscription data
    commission_map.py       # Commission rates by salesman

  core/
    auth.py                 # MSAL auth (D365 + Graph tokens)
    odata.py                # OData v4 client with pagination
    http.py                 # Shared HTTP session with retries
    dates.py                # US Eastern date utilities + period parsing
    columns.py              # Column detection + numeric conversion
    excel_styles.py         # Shared Excel styling constants
    excel_writer.py         # Shared Excel writing utilities
    email_report.py         # Send reports by email (Graph or SMTP)
    logging.py              # Structured logging setup
    validation.py           # DataFrame validation before Excel write

  data/
    field_maps.py           # OData field rename maps + $select lists
    d365_entities.py        # Entity-specific D365 fetch functions

  reports/
    base.py                 # Abstract base runner with CLI arg parsing
    ordered/                # Ordered Report
    invoiced/               # Invoiced Report
    salesman/               # Salesman Report
    number_4/               # Number 4 Report
    customer_activity/      # Customer Activity Report
    customer_aging/         # Customer Aging Report
    ordered/                # Ordered Report
    invoiced/               # Invoiced / Shipped Report
    salesman/               # Salesman Report
    number_4/               # Number 4 Report (By Item + By Customer)
    customer_activity/      # Customer Activity Report

  runbooks/
    universal_runbook.py    # Self-contained Azure Automation runbook

  tests/
    conftest.py             # Shared pytest fixtures
    test_ordered_builder.py
    test_invoiced_loader.py
    test_salesman_builder.py
    compare_reports.py      # Cell-by-cell Excel comparison tool

  webapp/                   # Flask web app (deployed to Azure App Service)
    app.py                  # Flask app factory
    blueprints/             # Route handlers (auth, reports, dashboard, settings, api)
    services/               # D365 data access, authorization
    templates/              # Jinja2 HTML templates
    static/                 # JS, CSS, manifest
    db.py                   # SQLite database (users, settings, history)
    config.py               # Web-specific config
    report_api.py           # Bridge to report runners
    requirements.txt        # Web app deps (adds Flask, gunicorn)
```

## Rule Preferences

Standing choices when rules disagree (also used by agents):

| Topic | Choice |
|-------|--------|
| After a requested product change | **Commit + push + `.\deploy.ps1`** unless told not to. Do not leave finished UI/app changes sitting uncommitted/undeployed. |
| Unrelated dirty tree | Stage only the files for this change; leave parity/scratch/other WIP alone. |

## D365 Entity Reference

All OData entity names and field mappings are defined in `data/field_maps.py`.
Cross-reference with your D365 `$metadata` endpoint to verify field names.
