# D365 Sales Reports

Automated sales reporting from Dynamics 365 F&O. The web app uses the SQL
Reporting API. CLI and Azure Automation jobs may still use OData.

Web report tabs, columns, role defaults, and approved diffs vs archive
`b14d725`: `REPORT-PARITY.md`.

## Reports

| Report | CLI Command | Output Directory |
|--------|-------------|------------------|
| Ordered Report | `python run.py ordered` | Direct Reports/Ordered Report/{period}/ |
| Invoiced Report | `python run.py invoiced` | Direct Reports/Invoiced Report/{period}/ |
| Shipped Report | `python run.py invoiced --salesman <name>` | Direct Reports/Salesman Report/Shipped Report/{period}/ |
| Salesman Report | `python run.py salesman` | Direct Reports/Salesman Report/{period}/ |
| Number 4 Report | `python run.py number_4` | Direct Reports/Number 4 Report/{sub}/{period}/ |
| Customer Activity | `python run.py customer_activity` | Direct Reports/Customer Activity/ |
| Sales by State | home site only (SQL) | — |

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
heartbeat email. If the whole job fails once (dropped Graph, non-zero exit),
it waits 30 seconds and runs again before Azure marks it Failed.

Home-site company schedules do the same: one extra full delivery, then `[FAIL]`
mail to the test-email list.

Home-site clock runs skip Shabbos/Yom Tov (Hebcal, Brooklyn). A skipped send
waits for the next scheduled HH:MM, not motzei Shabbos. Yesterday/daily and
in-month MTD wait for the next regular slot and widen the date range. last_7_days,
last_month, month-end MTD, and all-time reports wait until the next weekday at
that same clock (Friday 10pm skip → Monday 10pm). Month-end MTD also sends a
catch-up through the last day of the skipped month when the makeup is next month.

```
universal_runbook.py ordered --period daily
# Amazon ordered schedule (customers 9300/9301):
#   ordered --customer 9300 9301 --period last_7_days --email
```

### Web App (on-demand)

The Flask app is Azure App Service `achim-sales-reports` (https://reports.achimonline.com).

**Production branch is `webapp-cache`.** GitHub Action
`.github/workflows/webapp-cache_achim-sales-reports.yml` deploys that branch on
push, or on manual dispatch from `webapp-cache` only (any other ref is skipped).
The deploy job uses GitHub Environment `production`
(https://reports.achimonline.com). Required reviewers for that Environment are
set in the GitHub repo settings, not in YAML. Cloud Agent `cursor/**` branches
do not deploy to the Azure Production slot. Emergency zip deploy is
`deploy.ps1`, which requires python and npm, runs the same frontend/static
and split pytest commands CI uses, then zips git-tracked allowlist files
via `tools/build_artifact.py`.

Users authenticate with Microsoft Entra ID and can run any report on demand.

Boot is three processes, one App Service instance (SQLite):

1. Litestream restore + replicate (outer durability).
2. `python -m web.bootstrap` — migrations and seeds. Failure exits before traffic.
3. `tools/supervise-web.sh` starts Gunicorn (HTTP only) and
   `python -m web.worker_main` (job claiming, scheduler, lookup mirror,
   heartbeats). If either sibling exits, the other is stopped so Azure restarts
   the unit. Report jobs run in a killable child with a 45-minute cap. The
   worker heartbeat keeps ticking during that wait. A worker restart (including
   SIGTERM) requeues report/export/mirror jobs and cancels in-flight
   `schedule.run` / `report.deliver` so mail is not sent twice. Email and
   folder sends are persisted as separate legs (`prepared`, `sending`,
   `accepted`, `sent`, `failed`, `unknown`). If the connection drops after
   Graph may have accepted `sendMail`, that leg is `unknown` and is not
   retried. Settings test emails get a `[UNKNOWN]` notice; History (scheduled)
   and Schedules (email-now) have "I received it" / "Send again".

`/healthz` is process liveness. `/readyz` is 503 until bootstrap has succeeded
and (in prod) the worker and scheduler heartbeats are fresh.

Each report has a company **Default** view (the current tab/column layout)
plus named **company views** everyone can pick (Daily Ordered, Heshy Open Orders).
Managers and admins edit them from Saved views. New schedules use Default;
the schedules page shows Default, the company-view name, or Custom.

```powershell
.\deploy.ps1              # build zip and deploy to Azure
python app.py             # run locally on port 5001
```

### Local CLI

```
pip install --require-hashes -r requirements.txt
cp .env.example .env      # fill in credentials
python run.py ordered
```

### Site layout

| Path | Code | Role |
|------|------|------|
| `/` | `v3/` (`is_beta=True`) | Site home — reports from the SQL Reporting API. |
| `/beta` | — | Redirects to the same path without `/beta` (old bookmarks) |

Microsoft login and magic links run on this app (`/login`, `/login/start`, `/auth/callback`). People admin creates accounts; Microsoft sign-in does not auto-provision. Magic-link tokens are stored as hashes. One-time copy of leftover Live users: `flask import-live-users`. Every visible web report uses the SQL Reporting API. If SQL is missing, the run fails; there is no OData fallback in the web app. CLI and Azure Automation may still use OData under `reports/`, `core/`, `data/`, and `runbooks/`.

On the home site, **Recent Reports** (header, looks like a link) opens recent and kept runs. **Keep this run**
asks for an optional name; the bottom-right pill can be minimized.

On the home site, **Settings** is the control panel: You, People, Reports, Delivery, History, and (developers) Database explorer and notification diagnostic. In-app Live email distributions were not ported; Azure Automation runbooks still send. The sqlite file is on local disk (`SITE_PRECIOUS_DB_PATH`, Azure alias `BETA_PRECIOUS_DB_PATH`) and is restored/replicated by Litestream, so Settings like schedule test mode survive an App Service recycle. Rollback: keep Azure `BETA_*` settings and redeploy the previous commit; the leftover `/test` replica (`LITESTREAM_AZURE_PATH`) is unused, not deleted. Forward migrations only.

`/legacy`, `/test`, and `/test-next` are gone. Rollback: `git checkout archive/pre-cleanup-2026-08-27`.

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
- **Web App**: `FLASK_SECRET_KEY`, `SITE_PRECIOUS_DB_PATH` (alias `BETA_PRECIOUS_DB_PATH`). `AUTH_MODE=dev` is refused when `APP_ENV=prod`.

## Directory Structure

```
app.py                    # local: python app.py (same WSGI as Azure)
wsgi.py                   # gunicorn wsgi:application
wsgi_dispatch.py          # /beta bookmark 302
run.py                    # CLI entry point for all reports
deploy.ps1                # Deploy to Azure App Service
requirements.txt          # hashed pip lock (source: requirements.in)
report_registry.json      # Report definitions for universal_runbook
.env.example              # CLI/Automation env template; web settings: v3/.env.example

config/                   # salesman/commission maps
core/                     # D365 + Graph + Excel helpers (CLI/runbooks)
data/                     # OData field maps
reports/                  # CLI report runners
runbooks/                 # Azure Automation
tests/                    # root tests (Excel formula, WSGI)
v3/                       # Flask site at /
  web/                    # App factory, auth, reports UI, jobs
  report_engine/          # SQL report math
  tests/
```

## Rule Preferences

Standing choices when rules disagree (also used by agents):

| Topic | Choice |
|-------|--------|
| After a requested product change | **Commit + push.** Production deploys only from `webapp-cache`. Use `.\deploy.ps1` only when that Action cannot run. Do not leave finished UI/app changes sitting uncommitted/undeployed. |
| Unrelated dirty tree | Stage only the files for this change; leave parity/scratch/other WIP alone. |
| Home-site flag | Keep `is_beta=True` (`session` cookie, reports-only). Canonical DB env is `SITE_PRECIOUS_DB_PATH` (alias `BETA_PRECIOUS_DB_PATH` until Azure is renamed). Same for `SITE_CACHE_DB_PATH` and `LITESTREAM_AZURE_SITE_PATH`. Do not flip `is_beta` to False. |

## D365 Entity Reference

All OData entity names and field mappings are defined in `data/field_maps.py`.
Cross-reference with your D365 `$metadata` endpoint to verify field names.
