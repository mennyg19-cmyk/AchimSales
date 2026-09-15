# Home site rebuild (`app/`)

New Achim sales-report website. **Looks like** current https://reports.achimonline.com (`v3/` CSS + Tabulator). **Runs on** FastAPI and one JSON object per report.

This folder is **not** the leftover Flask preview in `/rebuild` and **must not** be pushed to AchimSales `main` until Menny says cut over. Production today stays on `achim-sales-reports`.

## Slice 1 (this preview)

Login look, header, bottom nav, four themes, mock Invoiced tabs in Tabulator. No Entra, no office API, no schedules yet.

```
cd app
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080
```

Open `/login` → **Achim User Login** (preview) → **Invoiced**.

Clickable preview while this agent is running: https://ons-cars-about-fcc.trycloudflare.com/login  
That link dies when the machine sleeps. Screenshots stay in `app/rebuild-reference/`. Live production is unchanged.

## Do not

- Commit `REPORTING_API_KEY` or cookies
- Point `REPORTING_API_BASE_URL` at reports.achimonline.com
- Merge leftover PR https://github.com/mennyg19-cmyk/AchimSales/pull/35
- Deploy over the live Azure Web App until sign-off
