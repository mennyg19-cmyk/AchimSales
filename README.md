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

The old site stored People, views, and schedules in `precious.db`. Copy that
file off the live box, then either:

- Settings → People → **Copy from live precious.db** (admin upload), or
- `python3 app/import_precious.py /path/to/precious.db`

Existing emails stay. Matching company view names get the live layout.
Schedules attach to those views. Nightly sends after that are the site clock.

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
`GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`, `EMAIL_FROM`,
`SP_SITE_URL`.

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
