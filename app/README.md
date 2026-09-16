# Home site (`app/`)

Achim sales-report website. Looks like the old Flask home. Runs on FastAPI.

`v3/`, `webapp/`, `rebuild/`, and Azure Automation (`run.py` / `runbooks/`)
are not in this repo anymore. Nightly work is the in-app schedules. Repo-root
`startup.sh` execs `app/startup.sh`. **Do not merge to `main` until Menny says cut over.**

## Dummy preview (what this branch serves)

Every home card, Settings, People, saved views (filters **and** grid layout in columns, not JSON blobs), Keep/Recent, schedules, Excel export, and outbox. Reports call the office Reporting API when `REPORTING_API_KEY` is set; without it they stay on catalog JSON (banner on home and report pages). Graph mail, the one-minute clock, Hebcal skip, and Entra login turn on when `GRAPH_*` / `EMAIL_FROM` are set; without them mail stays in sqlite outbox and Achim User Login stays the preview admin.

```
cd app
python -m pip install -r requirements-dev.txt
PYTHONPATH=. python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

Open `/login` → **Achim User Login** (Preview Admin, or Entra when `GRAPH_*` is set). External Rep Login with `external@example.com` signs in the seeded external row unless Graph mail is configured (then it emails a 15-minute link).

`pytest` from this folder uses a temp sqlite file. It never calls the live Reporting API (doorway is mocked).

## Copy live precious.db

Exact Azure download + import steps are in the repo-root README
(“Copy live data”). Short version: SSH on `achim-sales-reports`, copy
`BETA_PRECIOUS_DB_PATH` (`/tmp/betadata/precious.db`, about 97 views) — not
`/tmp/v3data` (`/test`, about 9 views) — then Settings → People upload.
After production cutover, run `import-precious.py` on the box with
`--dest /tmp/homedata/home.sqlite`.

## Azure

Merging this branch to `main` deploys FastAPI onto `achim-sales-reports`
because root `startup.sh` now starts this folder. Until that merge, use a
second Web App if you want an Azure preview:

```
bash create-azure-webapp.sh achim-sales-home-preview
.\deploy.ps1 -Name achim-sales-home-preview
```

`app/deploy.ps1` still refuses the live app name. Repo-root `deploy.ps1` targets live — cutover only.

App settings: `APP_ENV=preview` on a preview app; production needs `SESSION_SECRET` (or `FLASK_SECRET`) and `LITESTREAM_AZURE_ACCOUNT_KEY`. Optional: `REPORTING_API_KEY` and `REPORTING_API_BASE_URL` (defaults to the West US 3 test doorway). Optional Graph/Entra: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `EMAIL_FROM`.

## Do not

- Commit `REPORTING_API_KEY` or cookies
- Point `REPORTING_API_BASE_URL` at reports.achimonline.com
- Merge leftover PR https://github.com/mennyg19-cmyk/AchimSales/pull/35
- Merge this PR to `main` until Menny says cut over
