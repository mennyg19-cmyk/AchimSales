# Home site rebuild (`app/`)

New Achim sales-report website. **Looks like** current https://reports.achimonline.com (`v3/` CSS + Tabulator). **Runs on** FastAPI and one JSON object per report.

This folder is **not** the leftover Flask preview in `/rebuild` and **must not** be pushed to AchimSales `main` until Menny says cut over. Production today stays on `achim-sales-reports`.

## Slice 1 (this preview)

Login look, header, bottom nav, four themes, mock Invoiced tabs in Tabulator. No Entra, no office API, no schedules yet.

```
cd app
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080
```

Open `/login` → **Achim User Login** (preview) → **Invoiced**.

## Azure Web Apps — will it run?

**On the live site (`achim-sales-reports`): no.** That app still starts the old Flask `wsgi:application`. This rebuild must not be pointed there until cutover.

**On a new Azure Web App: yes.** This folder is packed the way Linux App Service expects:

- `requirements.txt` at the zip root (Oryx pip install)
- `runtime.txt` → Python 3.12
- `startup.sh` → gunicorn + UvicornWorker on `0.0.0.0:$PORT` (Azure sets `PORT`)
- `/healthz` for Always On (the `AlwaysOn` ping on `/` already returns 200)

Create a **second** Web App (same resource group is fine), then zip-deploy **this folder only**:

```
bash create-azure-webapp.sh achim-sales-home-preview
.\deploy.ps1 -Name achim-sales-home-preview
```

App settings on that new app: `APP_ENV=preview`, `SCM_DO_BUILD_DURING_DEPLOYMENT=true`, Startup Command `bash /home/site/wwwroot/startup.sh`. Do not bind `reports.achimonline.com` yet.

`deploy.ps1` refuses the live app name.

## Do not

- Commit `REPORTING_API_KEY` or cookies
- Point `REPORTING_API_BASE_URL` at reports.achimonline.com
- Merge leftover PR https://github.com/mennyg19-cmyk/AchimSales/pull/35
- Deploy over the live Azure Web App until sign-off
