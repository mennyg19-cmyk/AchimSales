# Achim Sales Reports

**Paused 2026-09-16:** this FastAPI rebuild is parked on branch
`cursor/fastapi-rebuild-parked-0a24`. Production `main` is the Flask site until
cutover is tried again. Resume from that branch, not from Flask `main`.

**Switch Flask ↔ FastAPI:** follow [CUTOVER.md](CUTOVER.md). Do not merge this
history into Flask `main`. App Settings and Startup Command already match both
stacks.

FastAPI home site. Nightly work is the in-app schedules (one-minute clock), not
Azure Automation. Report rows come from the office Reporting API
(`POST /api/reports/{id}/run`) when `REPORTING_API_KEY` is set.

The website lives in `app/`. Azure Startup Command is
`bash /home/site/wwwroot/startup.sh`, which execs `app/startup.sh`
(gunicorn + UvicornWorker + `main:app`). Flask `v3/` / `webapp/` and the
OData Automation CLI (`run.py`, `runbooks/`) are gone from this tree.
GitHub history on `main` still has every old commit.

**Production branch is `main`.** Cutover is CUTOVER.md (`read-tree` a FastAPI
tag onto `main`), not a merge of this history into Flask. Leftover Flask PR
#35 stays parked.

## Copy live data (precious.db)

Do this **immediately after cutover**, and again after any deploy that
recycles `/tmp` before Litestream has a `home.sqlite` replica. Azure `/tmp`
is wiped on Restart. sqlite stays on `/tmp` (WAL is unsafe on `/home` SMB);
`startup.sh` restores from blob `home.sqlite` then replicates. Import once,
wait a couple of seconds, then Restart should keep People. The new site does
**not** read `precious.db`. Do not copy `precious.db` over `home.sqlite`.

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

**On the Azure box after this deploy** (production login needs People first, so
use Kudu instead of the website). `import-precious.py` lands at
`/home/site/wwwroot/import-precious.py` when FastAPI is deployed. If Bash says
that file does not exist, the deploy is still running, or you are not in
`wwwroot`.

The `home-precious.db` already in `/home/LogFiles/` is enough. You do not need
to upload the PC copy unless that file is gone. Ignore a tiny `precious.db` in
the same folder (empty leftover).

```
cd /home/site/wwwroot
ls import-precious.py /home/LogFiles/home-precious.db
python3 import-precious.py /home/LogFiles/home-precious.db --dest /tmp/homedata/home.sqlite
```

On Azure Kudu, omitting `--dest` now writes `/tmp/homedata/home.sqlite` (the file
gunicorn reads). Locally it still writes `app/data/home.sqlite`. If the
command prints a WARNING about dest, the website is not reading that file.

The last line of a good import is `into /tmp/homedata/home.sqlite`. If it says
`into .../app/data/home.sqlite`, login will still 403.

That destination is the new site’s database (`APP_DB_PATH`). You should see a
line like `People N added… Views… Schedules… into /tmp/homedata/home.sqlite`.
Wait a couple of seconds so Litestream can replicate, then Restart. People
should still be there. If Restart is empty, the replica was not written yet —
import once more and wait longer.

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
| Home site rebuild (`app/`) | **Parked.** FastAPI lives on `cursor/fastapi-rebuild-parked-0a24`. Production `main` is Flask until Menny cuts over again. Do not merge leftover Flask PR #35 onto the FastAPI branch. |
| Rebuild review models | Cutover skipped Sol/Fable loops by Menny order (logged). Later whole-app premier loops still Fable/Sol. |
| Follow-up on an open PR | **Same agent → same branch / same PR.** Two agents at once → two PRs. |
| Unrelated dirty tree | Stage only the files for this change; leave scratch/other WIP alone. |
