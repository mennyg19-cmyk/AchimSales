# Deletion inventory

Reviewed revision: current branch `cursor/p0-security-containment-adb6`.

Rollback: annotated tag `archive/pre-cleanup-2026-08-27` = `b14d725`.

```
git checkout archive/pre-cleanup-2026-08-27
```

## Deleted

- `.scratch/` untracked (168 files).
- `logs/run_log.csv`, `v3/REVIEW-LOG.md`, rebuild audit/proposal/history docs.
- Entire `rebuild/` tree and `/test-next`.
- Entire `webapp/` tree and `/legacy` + `/test` mounts.
- `tools/parity/` (compared `/legacy` vs `/test`).
- Legacy-only tests that imported `webapp`.

## Keep (still in production use)

| Path | What it is | Why keep |
|---|---|---|
| `v3/` | Site at `/` | Surviving app |
| `reports/`, `core/`, `data/`, `runbooks/`, `run.py`, `report_registry.json` | CLI + Azure Automation | README: still the Automation path |
| `startup.sh`, `litestream.yml`, `Dockerfile`, `gunicorn.conf.py`, `deploy.ps1`, `deploy-runbook.ps1` | Prod boot and deploy | Live Azure |
| `v3/web/static_dist/` including `*.map` and `vendor/` | Committed frontend | Azure/Oryx does not run esbuild |
| `DECISION-LOG.md`, `TESTING-STRATEGY.md`, `HANDOFF.md`, `REPOSITORY-REVIEW.md` | Current decisions and review | Keep |
| `.cursor/rules/` | Agent rules | Keep |

`/beta` still 302s to `/`. Home keeps `is_beta=True` (reports-only flags + `SITE_PRECIOUS_DB_PATH` / `BETA_PRECIOUS_DB_PATH` alias). Beta pill is gone. Test Site nav and order-entry flag are gone.

`.scratch/parity-cookies.env` is not in the index on this branch. It remains in `webapp-cache` history from `f286ce2` until a coordinated rewrite. Do not print those values.
