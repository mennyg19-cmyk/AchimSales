# Flask ↔ FastAPI switch (same Azure app)

Use this when you want **reports.achimonline.com** to run the other stack.
Secrets are already in Azure App Settings. Do **not** add, rename, or delete
App Settings to switch. Do **not** change the Startup Command.

**Today (2026-09-17):** Flask is live. FastAPI is parked. This file is the
recipe, not a go-live. Wait for an explicit “switch to FastAPI” before
pushing a FastAPI tree to `main`.

## What stays the same

| Item | Value — leave it |
|------|------------------|
| App Service | `achim-sales-reports` |
| URL | https://reports.achimonline.com |
| Startup Command | `bash /home/site/wwwroot/startup.sh` |
| Production git branch | `main` only. `cursor/**` does **not** deploy. |
| Deploy | GitHub Action on push to `main` (`clean: true` zip). Wait until it is green. |

Azure python3 has no pip. Each tree vendors its own site-packages (`deps/`
on Flask, `app/deps` on FastAPI). CI does that; you do not pip on the box.

## How to tell which site is live

Hard-refresh the login page, then view-source / Network for `main.css`:

| You see | Site |
|---------|------|
| `main.css?v=` plus a **number** (e.g. `1789572588`) | Flask |
| `main.css?v=home13` (or a later `homeN`) | FastAPI |

Old HTML can sit in a worker for ~30–60s after a green deploy. Recycle is
done when that query string matches the tree you just pushed.

## Two sqlite files — never mix them

`/tmp` is wiped on Restart. Litestream is what comes back.

| Stack | Local file (gunicorn reads this) | Blob replica |
|-------|----------------------------------|--------------|
| Flask home (`/`) | `BETA_PRECIOUS_DB_PATH` → `/tmp/betadata/precious.db` | `${LITESTREAM_AZURE_BETA_PATH}` |
| Flask `/test` | `PRECIOUS_DB_PATH` → `/tmp/v3data` | `${LITESTREAM_AZURE_PATH}` (`precious.db`) |
| FastAPI | `APP_DB_PATH` → `/tmp/homedata/home.sqlite` | **hardcoded** `home.sqlite` |

- Do **not** copy `precious.db` onto `home.sqlite` or the other way.
- FastAPI restoring Flask’s `precious.db` replica crashes boot (`schedule_runs.message`).
- `/tmp/v3data` (~620K, 9 views) is **`/test`**, not home. Never import it.
- Safety copy of Flask home: `/home/LogFiles/home-precious.db` — use it only if it is **much larger than 620K**.

Azure SSH (App Service → SSH), not Kudu Bash. Kudu’s python/`/tmp` is not
always the worker that serves the site.

## Azure variables (already set — do not edit to switch)

Both stacks read overlapping names. Leaving extras in place is fine; each
tree ignores what it does not use.

Shared (both): `APP_ENV=prod`, `GRAPH_*`, `FLASK_SECRET` / `FLASK_SECRET_KEY`,
`LITESTREAM_AZURE_ACCOUNT_NAME` / `KEY` / `CONTAINER`, `REPORTING_API_KEY`,
`REPORTING_API_BASE_URL` (must **never** be `https://reports.achimonline.com`),
`EMAIL_FROM` / `EMAIL_FROM_ADDRESS`, `SP_SITE_URL`.

Flask only: `BETA_PRECIOUS_DB_PATH`, `PRECIOUS_DB_PATH`, `LITESTREAM_AZURE_PATH`,
`LITESTREAM_AZURE_BETA_PATH`.

FastAPI only: `APP_DB_PATH=/tmp/homedata/home.sqlite`. Session secret is
`SESSION_SECRET`, or the existing `FLASK_SECRET` / `FLASK_SECRET_KEY`.
Production boot also requires `LITESTREAM_AZURE_ACCOUNT_KEY`.

## Git: replace `main`’s tree, do not merge

Flask `main` and the parked FastAPI branch **diverged**. A merge will fight.
Do **not** force-push `main`.

Tags (after hotfixes, add a **new** dated tag; keep old tags):

```powershell
git tag -l "flask-prod-*" "fastapi-rebuild-parked-*"
```

Use the newest date. As of this file:

| Stack | Put this tree on `main` |
|-------|-------------------------|
| Flask | Newest `flask-prod-*` (this commit is `flask-prod-2026-09-17`). While Flask is live, `origin/main` is also Flask after this lands. |
| FastAPI | Newest `fastapi-rebuild-parked-*`. Resume work on `cursor/fastapi-rebuild-parked-0a24`, commit, tag, then switch. |

PowerShell (Menny’s machine), repo root, clean tree:

```powershell
git fetch origin
git checkout main
git pull origin main
git read-tree -u --reset <TAG>
git commit -m "Switch production to FastAPI."
# or: git commit -m "Switch production to Flask."
git push origin main
```

`<TAG>` is one of the tags above. Then watch the Action. Do not Restart the
App Service unless the checklist step says to.

After FastAPI work on the parked branch, tag it, then use **that** tag as
`<TAG>`. After Flask hotfixes on live `main`, tag `flask-prod-YYYY-MM-DD` on
the green commit so a later switch-back includes those fixes.

---

## A. Flask → FastAPI

Do this only when you mean to take Flask off the public URL.

1. **Snapshot Flask home sqlite** (Azure SSH), so import still has a file if
   the FastAPI `home.sqlite` replica is empty:

```
printenv BETA_PRECIOUS_DB_PATH
ls -lh "${BETA_PRECIOUS_DB_PATH:-/tmp/betadata/precious.db}" /home/LogFiles/home-precious.db
python3 -c "import os,sqlite3; s=sqlite3.connect('file:'+(os.environ.get('BETA_PRECIOUS_DB_PATH') or '/tmp/betadata/precious.db')+'?mode=ro', uri=True); d=sqlite3.connect('/home/LogFiles/home-precious.db'); s.backup(d); s.close(); d.close(); print('copied to /home/LogFiles/home-precious.db')"
ls -lh /home/LogFiles/home-precious.db
```

Stop if that file is missing or ~620K.

2. **Local git:** `read-tree` the FastAPI tag onto `main`, commit, push
   (see Git above). Message: `Switch production to FastAPI.`

3. **Watch** GitHub Action “Build and deploy Python app to Azure Web App -
   achim-sales-reports” until **success**. Red = stop and fix; do not
   Restart to “nudge” it.

4. **Wait** 30–60s for gunicorn to recycle. Hard-refresh
   https://reports.achimonline.com — CSS must be `?v=home13` (or newer
   `homeN` from the parked tree). If you still see a numeric `?v=`, wait
   and refresh again.

5. **Log in** (Achim User Login). If People / views are empty or Entra
   403s (no People row): Azure SSH, from `/home/site/wwwroot`:

```
python3 import-precious.py /home/LogFiles/home-precious.db --dest /tmp/homedata/home.sqlite
```

   Last printed line **must** say `into /tmp/homedata/home.sqlite`. If it
   says `app/data/home.sqlite`, gunicorn will not see it.

6. **Wait** a minute so Litestream can replicate `home.sqlite`. Then
   Achim User Login again. Do **not** Azure Restart before that copy
   exists — Restart wipes `/tmp`.

7. Confirm REPORTING_API still points at the office doorway, not this
   website host.

---

## B. FastAPI → Flask

This is what we did on 2026-09-16. Same steps next time.

1. **Optional snapshot** of FastAPI sqlite (only if you care about FastAPI
   People/views written since the last import). Flask does not read
   `home.sqlite`. Azure SSH:

```
printenv APP_DB_PATH
ls -lh "${APP_DB_PATH:-/tmp/homedata/home.sqlite}"
```

   Leave that file alone. Do not copy it onto `BETA_PRECIOUS_DB_PATH`.

2. **Local git:** `read-tree` the Flask tag (or `origin/main` if Flask is
   already the last `main` commit you want) onto `main`, commit, push.
   Message: `Switch production to Flask.`

3. **Watch** the same GitHub Action to **success**.

4. **Wait** 30–60s. Hard-refresh — CSS must be `main.css?v=` plus a
   **number**, not `home13`.

5. **If login / People / views look empty:** Azure SSH, restore the Flask
   home file (not `/tmp/v3data`):

```
printenv BETA_PRECIOUS_DB_PATH
ls -lh "${BETA_PRECIOUS_DB_PATH:-/tmp/betadata/precious.db}" /home/LogFiles/home-precious.db
python3 -c "import os,sqlite3; p=os.environ.get('BETA_PRECIOUS_DB_PATH') or '/tmp/betadata/precious.db'; os.makedirs(os.path.dirname(p), exist_ok=True); s=sqlite3.connect('file:/home/LogFiles/home-precious.db?mode=ro', uri=True); d=sqlite3.connect(p); s.backup(d); s.close(); d.close(); print('restored', p)"
```

   Use `/home/LogFiles/home-precious.db` only if it is much larger than 620K.
   Litestream beta replica usually restores on boot; this copy is the
   fallback. Do **not** Restart until that restore has run if the replica
   did not come back.

6. Flask `/test` is a different sqlite. Ignore it for home.

---

## Resume FastAPI work (without switching live)

```powershell
git fetch origin
git checkout cursor/fastapi-rebuild-parked-0a24
```

Read that branch’s `HANDOFF.md`. Branch from **it**, not from Flask `main`.
Do not merge leftover Flask PR #35. Do not open a PR into `main` until you
are running checklist **A**.

P4.I8 (salesman vs SalesGroup) is still BLOCKED on that branch.

---

## Locked

- `REPORTING_API_BASE_URL` must never be `reports.achimonline.com`.
- Do not add `v2_FLASK_SECRET` unless asked.
- FastAPI Entra does not upsert People rows.
- FastAPI import dest on Azure is `/tmp/homedata/home.sqlite`.
- Company **views** stay; company **schedule pages** were retired on FastAPI.
- Dummy `preview@` / loop users are purged on import.
- Leftover Flask PR #35 stays parked.
