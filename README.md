# D365 Sales Reports

Automated sales reporting from Dynamics 365 F&O. Reports run on scheduled Azure
Automation jobs, on demand via a Flask web app, or locally from the CLI.

OData remains only in the CLI/Azure Automation path under `reports/`, `core/`,
`data/`, and `runbooks/`; the Flask v3 app uses the Reporting API and has no
OData runtime.

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
it waits 30 seconds and runs again before Azure marks it Failed. Fail then
retry-success is one status email (the heartbeat names the failure). Azure
Automation must call `main()` so that retry wrap runs. git push does not
publish this file; use `.\deploy-runbook.ps1`.

Home-site company schedules do the same extra delivery. `[FAIL]` mail waits
15 minutes and is dropped if that schedule later succeeds. The success mail
names the first failure.

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
Gunicorn is HTTP-only: it serves requests and reads/enqueues durable state. On
App Service, `supervise-web.sh` runs Gunicorn beside `python3 -m
web.jobs.worker_main`; the worker applies v3 migrations and idempotent seeds,
then owns the scheduler and durable job poller. `/healthz` is process liveness;
`/readyz` stays 503 until that worker has completed bootstrap and both worker
and scheduler heartbeats are fresh. The live `/legacy` email-distribution flock
remains in-process.

### External monitoring

Probe `/readyz`, not only `/healthz`. Developers can use
`/api/reports/diagnostics/reporting-api` for queue age, both heartbeats, last
cleanup, worker process identity, and disk usage. Also watch Azure disk metrics.
For Litestream, compare Blob last-modified time with the local SQLite mtime;
replication only runs when `LITESTREAM_AZURE_ACCOUNT_KEY` is set, so startup
continues without replication when that key is missing.

**Production branch is `main`.** Pushing `main` deploys
https://reports.achimonline.com. Side branches (including Cloud Agent
`cursor/**` work) do **not** auto-deploy; they wait for a pull request into
`main`. Manual zip deployment through `deploy.ps1` is emergency-only and uses
the same shared artifact builder as CI. Agent Guardrails Semgrep scans
`v3/` (the home site) only, not `webapp/` (`/legacy`). It still uses
`p/default`, but skips rules that do not match this Flask + SQLite app
(Django CSRF/SQL, raw-SQL execute with `?` params, CDN integrity hashes,
dynamic urllib, SHA1 cache fingerprints).

**Git in one minute:** `main` is the official copy. A **branch** is a photocopy
you can mess with. A **pull request** is “please copy this photocopy into
`main`.” If `main` moved while you were working, you update your photocopy from
`main` and then merge. GitHub keeps every old version of `main`, so you can
roll back. The old name `webapp-cache` was retired after `main` became default.

Users authenticate with Microsoft Entra ID and can run any report on demand.

The salesman master is the `salesmen_master` SP (`rpt.usp_salesmen_master`,
`POST /api/reports/salesmen_master/run`: `Salesman`, `SalesmanName`, `Email`,
`CommissionPercentage`). `SalesmanDirectory` (`v3/web/reporting/salesman_directory.py`)
reads it once an hour per process and feeds every salesman dropdown (report
filters, Users & access SalesGroup, company schedule wizard, Customer's Last
Order), split-by-salesman email addresses, the Users & access email auto-grant,
and the commission fallback on the Invoiced commissions cards. A new hire
appears before they own a customer. **There is no salesman table in v3** (the
old `salesmen` table and its `salesman_map.xlsx` seed are gone). To add, rename,
retire, or re-address a salesman, change D365. The last good SP list is kept in
`cache.db` (`salesmen_master_cache`) so a worker that boots while the Reporting
API is down still has it. Salesman numbers are not used anywhere; salesmen are
identified by SalesGroup. Users & access does not list D365 salesmen; that
master is only the SalesGroup dropdown and manager checkboxes. A
customer SalesGroup missing from the master is still appended to dropdowns. On
Users & access, a **salesman** login picks a **SalesGroup** from that list;
that primary group plus any additional checked SalesGroups controls the data
they can see. Managers use the same per-salesman checkboxes (also from D365).

Each report has a company **Default** view (the current tab/column layout)
plus named **company views** (Daily Ordered, Heshy Open Orders). Admins and
developers always see and can create, edit, and delete those views (Save for
**Company**, or Edit/Delete in Saved views). Other roles need the Company
views flag (off by default; developers on, unused for admins). Toggle it on
Users & access. Daily Ordered groups Summary by salesman then customer (A-Z),
By Customer by salesman only (customers A-Z inside, not grouped), and leaves
By Order ungrouped. Company views can store a date window when you check
that box on Save this view; they can still be saved without one. Company
schedules supply their own YTD / MTD / yesterday at send time. Managers who have the flag can edit
them from Saved views. Personal schedules send a **named saved view** (3
steps: view, when, where). The Where step can set an email subject and HTML
body with the same `{Schedule}` / `{Period}` chips as the filename, plus
`{SharePointUrl}` and `{DownloadButton}` (Outlook-safe). Leave them blank for
the usual auto subject and note. Admins and developers can also schedule **Default**
and named **company views** (Daily Ordered, Heshy Open Orders) from More →
Schedule or the personal wizard Company group. Company schedules stay on the
old 5-step wizard under Settings (admins and developers) but that add/edit UI is
hidden for now (`SHOW_COMPANY_SCHEDULE_SETUP`); existing company rows still run. While a report or
schedule job is running, the status line (and Run now) shows the live step:
Reporting API, workbook, SharePoint/OneDrive, email. Each recent run has a
Log page (Time, Step, Detail for that job only). The schedule row History
button still lists every run for that schedule. First SharePoint use of a
worker looks up `SP_SITE_URL` only; a
bad URL fails instead of searching every site in the tenant.

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
| `/` | `v3/` (`is_beta`) | Site home — SQL reports through the Reporting API. |
| `/legacy` | `webapp/` | Former Live — OData, Excel-first, email distributions |
| `/test` | `v3/` | SQL sandbox — direct link only |
| `/beta` | — | Redirects to `/` (old bookmarks) |
| `/test-next` | `rebuild/` | Rebuild preview — retire after home is stable |

Enable the home swap with `BETA_MOUNT_ENABLED=1` (already on in prod). If Beta fails to boot, `/` stays the old Live app. `/test` still needs `V3_MOUNT_ENABLED=1`.
For the home site, prefer `SITE_PRECIOUS_DB_PATH` and `SITE_CACHE_DB_PATH`;
the older `PRECIOUS_DB_PATH` and `CACHE_DB_PATH` names remain supported during
the staged Azure setting migration. `/test` continues to use `BETA_*` paths.
On the home site, **Recent Reports** (header, looks like a link) opens recent and kept runs. **Keep this run**
asks for an optional name; the bottom-right pill can be minimized.

On the home site, **Settings** is the control panel (same ~800px width as Live): You,
People, Reports, Delivery, History, and (developers) Database explorer and
notification diagnostic. Live Email Distributions
stay on Live only. Developers can also see any Reporting API SP's raw response
at `/api/dev/reporting/<report_id>/run` (query string = SP params, e.g.
`/api/dev/reporting/salesmen_master/run`); nothing is dropped or scoped.
Beta's sqlite file is on local disk (`BETA_PRECIOUS_DB_PATH`)
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
wsgi.py                     # Azure Gunicorn entry: wsgi:application
startup.sh                  # App Service startup; launches the supervisor
supervise-web.sh            # HTTP Gunicorn and v3 worker sibling processes
tools/build_runtime_artifact.py # Shared CI/emergency deployment artifact builder
deploy.ps1                  # Emergency-only Azure zip deploy
webapp/                     # Legacy Flask app still mounted at /legacy
v3/                         # Home-site Flask app, worker, source, and static_dist
rebuild/                    # Preview app still mounted at /test-next
config/, core/, data/, reports/ # CLI/Azure Automation support
runbooks/                   # Azure Automation entrypoints
requirements.txt            # CLI/runbook dependencies
webapp/requirements.txt     # Hash-locked deployed runtime dependencies
```

## Rule Preferences

Standing choices when rules disagree (also used by agents):

| Topic | Choice |
|-------|--------|
| After a requested product change | **Commit + push to `main`** (or merge a PR into `main`). Only `main` auto-deploys. Use `.\deploy.ps1` only when that Action cannot run. Do not leave finished UI/app changes sitting uncommitted/undeployed. |
| Follow-up on an open PR | **Same agent → same branch / same PR.** Do not open a new Cloud Agent branch and PR for the next small ask. Stack it on this agent's last open PR so it can merge together. **Two agents at once → two PRs** (do not share a branch). Details in `git-discipline.mdc`. |
| Unrelated dirty tree | Stage only the files for this change; leave parity/scratch/other WIP alone. |

## D365 Entity Reference

All OData entity names and field mappings are defined in `data/field_maps.py`.
Cross-reference with your D365 `$metadata` endpoint to verify field names.
