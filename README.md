# Achim Sales Reports

FastAPI home site. Nightly work is the in-app schedules (one-minute clock), not
Azure Automation. Report rows come from the office Reporting API
(`POST /api/reports/{id}/run`) when `REPORTING_API_KEY` is set.

The website lives in `app/`. Azure Startup Command is
`bash /home/site/wwwroot/startup.sh`, which execs `app/startup.sh`
(gunicorn + UvicornWorker + `main:app`). Flask `v3/` / `webapp/` and the
OData Automation CLI (`run.py`, `runbooks/`) are gone from this tree.
GitHub history on `main` still has every old commit.

**Production branch is `main`.** This branch does not auto-deploy. Do **not**
merge until Menny says cut over (precious.db copy, secrets, Entra redirect).
Leftover Flask PR #35 stays parked.

## Copy live data (precious.db)

Do this **now**, while the old Flask site is still running. `/tmp` is wiped when
Azure recycles. After merge the new site does **not** read `precious.db`; it
reads `home.sqlite`. You download the old file to your PC, then **import** it.
Do not copy `precious.db` over `home.sqlite`.

### 1. Download from Azure onto your PC

The home site (`reports.achimonline.com` `/`) reads **`BETA_PRECIOUS_DB_PATH`**,
usually `/tmp/betadata/precious.db`. `/tmp/v3data/precious.db` is the **`/test`**
app (`PRECIOUS_DB_PATH`) — about 620K and ~9 views. Do not import that one.

1. Open [portal.azure.com](https://portal.azure.com) and search **achim-sales-reports**
   (resource group `AchimReportsApp`).
2. Left menu: **SSH** (not Kudu Bash — Kudu cannot see `/tmp`).
3. Print the path and counts. Must be about **97 views, 58 report_schedules, 592 layout_tabs**. If you see 9 and 13, you are on `/tmp/v3data` (the `/test` seed).

```
printenv BETA_PRECIOUS_DB_PATH PRECIOUS_DB_PATH
ls -lh "${BETA_PRECIOUS_DB_PATH:-/tmp/betadata/precious.db}"
python3 -c "import os,sqlite3; p=os.environ.get('BETA_PRECIOUS_DB_PATH') or '/tmp/betadata/precious.db'; c=sqlite3.connect('file:'+p+'?mode=ro', uri=True); print(p, c.execute('select count(*) from views').fetchone()[0], c.execute('select count(*) from report_schedules').fetchone()[0], c.execute('select count(*) from layout_tabs').fetchone()[0])"
```

Do **not** use `sqlite3.connect` without `mode=ro` on a missing path — that creates an empty 8KB file. Do **not** use `/tmp/v3data/precious.db` or `/home/site/v3data/precious.db`.

4. WAL-safe copy onto `/home` so Kudu can download it (Linux paths are case-sensitive: `LogFiles` not `Logfiles`):

```
python3 -c "import os,sqlite3; p=os.environ.get('BETA_PRECIOUS_DB_PATH') or '/tmp/betadata/precious.db'; s=sqlite3.connect('file:'+p+'?mode=ro', uri=True); d=sqlite3.connect('/home/LogFiles/home-precious.db'); s.backup(d); s.close(); d.close()"
ls -lh /home/LogFiles/home-precious.db
```

That copy must be **much larger than 620K**. An 8KB `precious.db` in LogFiles is an empty leftover — ignore it.

5. Kudu Debug console → `/home/LogFiles` → download **`home-precious.db`**. Save as:

`C:\Users\<you>\Downloads\precious.db`

Keep that file. That is the only copy you need on your PC.

### 2. Import into the new site (not a file copy)

The importer writes People, views, and schedules into the new sqlite. Existing
emails stay. Import **clears dummy views and schedules**, then copies the same
column tables the old GUI/clock assembled from: `views` + `view_salesmen` /
`view_statuses` / `view_customers` + `layout_tabs` / groups / sorters / columns /
filters, and `report_schedules` + weekday / monthday / recipient / email-salesman
children. Schedule run windows stay on the schedule (`window_period` /
`window_start` / `window_end`), not smashed onto a shared view. Leftover JSON
tables (`saved_reports`, `company_views`, `report_defaults`, `master_schedules`,
`view_workbook_parity`) are not read and are dropped on this site. The flash
lists live→here counts for those assemble tables. Live home sqlite
(`BETA_PRECIOUS_DB_PATH`, usually `/tmp/betadata/precious.db`) is about **97 views,
58 report_schedules, 592 layout_tabs**. `/tmp/v3data/precious.db` is `/test` (~9
views). JSON leftovers (`saved_reports` 52, JSON `schedules` 44, `master_schedules`
14) are already inside those column tables — 44+14=58 — and are not imported.
Admins and developers see every imported schedule, including paused ones.

**Dummy / this PR (APP_ENV is not production):** open the new site → `/login` →
**Achim User Login** → **Settings** → **Developer** → **Copy from live precious.db**
→ choose `Downloads\precious.db` → **Import**. Live
https://reports.achimonline.com does **not** have this form until this PR merges.

**After cutover, on the Azure box** (production login needs People first, so use
Kudu instead of the website):

1. Kudu Debug console → drag `Downloads\precious.db` into `/home/LogFiles/`
   (or reuse the file already there from step 1).
2. Bash:

```
cd /home/site/wwwroot
python3 import-precious.py /home/LogFiles/precious.db --dest /tmp/homedata/home.sqlite
```

That destination is the new site’s database (`APP_DB_PATH`). You should see a
line like `People N added… Views… Schedules… into /tmp/homedata/home.sqlite`.

**Your PC only** (local clone of this repo, does not update Azure):

```powershell
.\import-precious.ps1 -Precious C:\Users\<you>\Downloads\precious.db
```

That writes `app\data\home.sqlite` on the PC.

## Local preview

```
cd app
python -m pip install -r requirements-dev.txt
PYTHONPATH=. python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

Open `/login` → Achim User Login. Details: `app/README.md` and `app/.env.example`.

```powershell
.\deploy.ps1              # zip-deploy FastAPI home (cutover only)
```

**Git in one minute:** `main` is the official copy. A **branch** is a photocopy
you can mess with. A **pull request** is “please copy this photocopy into
`main`.” GitHub keeps every old version of `main`, so you can roll back.

## Environment

See `app/.env.example`. Production needs `SESSION_SECRET` (or live's
`FLASK_SECRET`) and `LITESTREAM_AZURE_ACCOUNT_KEY`. Graph/Entra/SharePoint:
`GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `EMAIL_FROM`
or `EMAIL_FROM_ADDRESS`, `SP_SITE_URL`.

## Directory Structure

```
startup.sh                  # Azure boot: execs app/startup.sh
deploy.ps1                  # Zip-deploy FastAPI home (cutover only)
app/                        # FastAPI home
  main.py                   # create_app() / gunicorn main:app
  startup.sh                # gunicorn + UvicornWorker + Litestream
  import_precious.py        # People + views + schedules from precious.db
  requirements.txt
```

## Rule Preferences

Standing choices when rules disagree (also used by agents):

| Topic | Choice |
|-------|--------|
| After a requested product change | **Commit + push to `main`** (or merge a PR into `main`). Only `main` auto-deploys. Use `.\deploy.ps1` only when that Action cannot run. Do not leave finished UI/app changes sitting uncommitted/undeployed. |
| Home site rebuild (`app/`) | **Stay off `main` until Menny says cut over.** FastAPI-only home. Merge to `main` will boot FastAPI on the existing Azure app. Nightly work is site schedules. Do not merge leftover Flask PR #35. |
| Rebuild review models until cutover | **Cheap/Everyday only (Grok, Composer, Terra).** Do not spawn Fable or Sol until Menny asks for go-live / whole-app premier loops. |
| Follow-up on an open PR | **Same agent → same branch / same PR.** Two agents at once → two PRs. |
| Unrelated dirty tree | Stage only the files for this change; leave scratch/other WIP alone. |
