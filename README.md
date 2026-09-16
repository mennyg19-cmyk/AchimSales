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
retry-success is the normal heartbeat only — no mention of the blip. A final
failure after retry is one FAILURE email with every attempt, traceback, and
log. Azure Automation must call `main()` so that retry wrap runs. git push
does not publish this file; use `.\deploy-runbook.ps1`.

Home-site company schedules do the same extra delivery. `[FAIL]` mail waits
15 minutes and is dropped if that schedule later succeeds. The success mail
is a normal report email. A final `[FAIL]` includes the job log, traceback,
and run details.

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

The website is FastAPI under `app/`, Azure App Service `achim-sales-reports`
(https://reports.achimonline.com). Azure's Startup Command is still
`bash /home/site/wwwroot/startup.sh`. That file now starts FastAPI
(`gunicorn` + `UvicornWorker` + `main:app`). There is no Flask leftover:
`v3/`, `webapp/`, `rebuild/`, and `wsgi:application` are gone from this tree.
GitHub history on `main` still has every old commit.

**Production branch is `main`.** Pushing `main` deploys the live Web App.
This branch does **not** auto-deploy. Do **not** merge until Menny says cut
over (People copy, secrets, Entra redirect). Leftover Flask PR #35 stays
parked. Manual zip deploy is `deploy.ps1`. Agent Guardrails Semgrep scans
`app/`.

Reports call the office Reporting API (`POST /api/reports/{id}/run`) when
`REPORTING_API_KEY` is set; otherwise catalog mock JSON. Graph mail,
SharePoint/OneDrive upload, the in-app minute clock (Shabbos skip + weekday
catch-up), Brooklyn Hebcal skip, and Entra login turn on when `GRAPH_*` /
`EMAIL_FROM` / `SP_SITE_URL` are set. Production boot needs `SESSION_SECRET`
(or live's `FLASK_SECRET`) and `LITESTREAM_AZURE_ACCOUNT_KEY`. Opt-in People
copy: `python3 app/import_precious.py /path/to/precious.db`. Site details:
`app/README.md`.

**Git in one minute:** `main` is the official copy. A **branch** is a photocopy
you can mess with. A **pull request** is “please copy this photocopy into
`main`.” If `main` moved while you were working, you update your photocopy from
`main` and then merge. GitHub keeps every old version of `main`, so you can
roll back. The old name `webapp-cache` was retired after `main` became default.

```powershell
.\deploy.ps1              # zip-deploy FastAPI home (cutover only)
cd app; python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

### Local CLI

```
pip install -r requirements.txt
cp .env.example .env      # fill in credentials
python run.py ordered
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
- **Web App (FastAPI `app/`)**: `SESSION_SECRET` (or `FLASK_SECRET` / `FLASK_SECRET_KEY`), `REPORTING_API_KEY`. See `app/.env.example`.

## Directory Structure

```
startup.sh                  # Azure boot: execs app/startup.sh (FastAPI)
run.py                      # CLI entry for Azure Automation reports
deploy.ps1                  # Zip-deploy FastAPI home (cutover only)
requirements.txt            # CLI / runbook deps (not the website)
report_registry.json        # Report definitions for universal_runbook
.env.example                # Automation env template; website is app/.env.example

app/                        # FastAPI home site
  main.py                   # create_app() / gunicorn main:app
  startup.sh                # gunicorn + UvicornWorker + Litestream
  requirements.txt          # FastAPI / gunicorn / uvicorn
  import_precious.py        # Opt-in People copy from live precious.db

config/ core/ data/ reports/ runbooks/
                            # Azure Automation OData CLI (not the website)
tests/                      # CLI / runbook tests
```

## Rule Preferences

Standing choices when rules disagree (also used by agents):

| Topic | Choice |
|-------|--------|
| After a requested product change | **Commit + push to `main`** (or merge a PR into `main`). Only `main` auto-deploys. Use `.\deploy.ps1` only when that Action cannot run. Do not leave finished UI/app changes sitting uncommitted/undeployed. |
| Home site rebuild (`app/`) | **Stay off `main` until Menny says cut over.** This PR is FastAPI-only home (no Flask `v3/` / `webapp/`). Merge to `main` will boot FastAPI on the existing Azure app because `startup.sh` now starts it. Do not merge leftover Flask PR #35. Dummy Cloudflare preview first. |
| Rebuild review models until cutover | **Cheap/Everyday only (Grok, Composer, Terra).** Do not spawn Fable or Sol until Menny asks for go-live / whole-app premier loops. User override of `review-protocol.mdc` premier table for this rebuild. |
| Follow-up on an open PR | **Same agent → same branch / same PR.** Do not open a new Cloud Agent branch and PR for the next small ask. Stack it on this agent's last open PR so it can merge together. **Two agents at once → two PRs** (do not share a branch). Details in `git-discipline.mdc`. |
| Unrelated dirty tree | Stage only the files for this change; leave parity/scratch/other WIP alone. |

## D365 Entity Reference

All OData entity names and field mappings are defined in `data/field_maps.py`.
Cross-reference with your D365 `$metadata` endpoint to verify field names.
