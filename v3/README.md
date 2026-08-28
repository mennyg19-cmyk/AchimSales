# v3 - Sales Reports

The Flask site at `/`. One report engine, one authorization layer, durable jobs,
Litestream-backed SQLite.

> Status: production home at `/` (this tree). Leftover decisions:
> [`DECISION-LOG.md`](../DECISION-LOG.md) and
> [`REPOSITORY-REVIEW.md`](../REPOSITORY-REVIEW.md).

## Layout

```
v3/
  report_engine/   shared, pure (facts, sources/, reports/, lib, contracts, registry)
  web/             Flask app (config, extensions, blueprints, data, auth, jobs, reporting)
  tests/           parity, security, authz, jobs, migrations
```

`report_engine/` is top-level and pure (no Flask, no DB, no I/O) so the web app
and any CLI/runbook share the exact same report math.

## Local run (dev)

```bash
cd v3
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate on *nix
pip install -r requirements.txt
cp .env.example .env        # AUTH_MODE=dev, APP_ENV=dev for local
python -m flask --app web.wsgi:application run
```

## Tests

```bash
cd v3
pytest
```

## Persistence

`precious.db` (users, permissions, salesmen, presets, schedules, run history,
notifications, jobs) lives on **local disk** and is replicated to Azure Blob by
**Litestream** - never on Azure Files/SMB. `cache.db` (D365 mirror + report
payload cache) is disposable. Postgres is a documented off-ramp behind repository
interfaces, required only before running more than one instance.
