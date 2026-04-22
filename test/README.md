# Sales Reports v2 (test/)

This directory contains the rebuilt app. It is served under `/v2` on the same
Azure App Service as the live app via [wsgi.py](../wsgi.py) +
`werkzeug.DispatcherMiddleware`.

## Phase

Phase 1 (current): empty shell + mock-data scaffolding. No SQL connection, no
real emails (see `MAIL_MODE`).

## Quick local run

```powershell
cd scripts
pip install -r test/requirements.txt
$env:USE_MOCK_DATA = "true"
$env:MAIL_MODE = "capture"
python -m flask --app wsgi:application run --port 5002
# Visit http://localhost:5002/v2
```

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `USE_MOCK_DATA` | `true` | Phase 1: read fixtures from `test/data/fixtures/`. Phase 2: flip to `false` to call stored procs. |
| `MAIL_MODE` | `capture` | `capture` writes to `test/outbox/`; `capture_and_send` also sends; `send` is SMTP only. |
| `DATABASE_URL` | *(unset)* | Phase 2: SQLAlchemy connection string for on-prem SQL Server. |
| `OUTBOX_DIR` | `test/outbox` | Where captured emails land. |
| `OUTBOX_RETENTION_DAYS` | `14` | Auto-prune captures older than this. |
| `V2_FLASK_SECRET` | falls back to `FLASK_SECRET` | Signs `/v2` session cookies separately from the live app. |
| `V2_URL_PREFIX` | `/v2` | Where the dispatcher mounts this app. Change at cutover. |

## Isolation

The v2 app never imports from the live `webapp/`, `reports/`, `core/`, or
`data/` packages. The only shared infrastructure is the Azure App Service
container itself. See the plan in `.cursor/plans/sql-rebuild-interactive_06d35532.plan.md`.
