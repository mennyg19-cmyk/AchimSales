# v3 - Sales Reports (clean rebuild)

A from-scratch rebuild of the D365 Sales Reports web app. **Pixel- and
navigation-identical to the LIVE app** (`webapp/`), with corrected/centralized
internals: one shared report engine, a single authorization layer, durable jobs,
a tokenized CSS system, and Litestream-backed SQLite tuned for a single Azure
App Service B1 instance.

> Status: **in active rebuild.** Not yet wired to production. See
> [`REVIEW-LOG.md`](REVIEW-LOG.md) for what needs human sign-off and current progress.

## Authoritative documents

- Build plan: `.cursor/plans/v3_rebuild_plan_81336296.plan.md` (opus48, reconciled with gpt55).
- Agent rules / non-negotiables: `.cursor/rules/v3-rebuild.mdc`.
- Audit inputs: `test/docs/v2-audit-and-rebuild-*.md`.

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
