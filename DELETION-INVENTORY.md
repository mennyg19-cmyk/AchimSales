# Deletion inventory

Reviewed revision after cleanup: current branch `cursor/p0-security-containment-adb6`.

Rollback: annotated tag `archive/pre-cleanup-2026-08-27` = `b14d725` (inventory commit, before this cleanup).

```
git checkout archive/pre-cleanup-2026-08-27
```

Production still boots `wsgi.py`: `/` is v3, `/legacy` is `webapp/`, `/test` is a second v3, `/test-next` is `rebuild/`. v3 still imports `webapp` for OData runners, user rows, live-session adoption, and some settings.

## Done in this cleanup (2026-08-27)

- Untracked `.scratch/` (168 files, including 12 MB `azure-logs.zip`). Files can remain on disk; gitignore already listed `.scratch/`.
- Deleted `logs/run_log.csv`. gitignore now ignores `logs/*.csv`.
- Deleted `v3/REVIEW-LOG.md`.
- Deleted `rebuild/rebuild-audit/`, `rebuild/proposals/`, `rebuild/BUILD-HISTORY.md`, `rebuild/DEBATE-LOG.md`. Rebuild **app** (`rebuild/` code, tests, `REBUILD-PLAN.md`, `FEATURE-INVENTORY.md`) stays.

## Do not delete (still in production use)

| Path | What it is | Why keep |
|---|---|---|
| `v3/` | Current site at `/` | Surviving app |
| `reports/`, `core/`, `data/`, `runbooks/`, `run.py`, `report_registry.json` | CLI + Azure Automation report engines | README: still the Automation path |
| `webapp/` | Legacy Flask app mounted at `/legacy`; also imported by v3 | Login/session/user directory/OData still flow through it |
| `rebuild/` app (not the deleted audit/proposal docs) | Preview app at `/test-next` | Harvest leftover features before retiring the mount |
| `startup.sh`, `litestream.yml`, `Dockerfile`, `gunicorn.conf.py`, `deploy.ps1`, `deploy-runbook.ps1` | Prod boot and deploy | Live Azure |
| `v3/web/static_dist/` including `*.map` and `vendor/` | Committed frontend | Azure/Oryx does not run esbuild |
| Security/report tests | Regression suite | Keep while the subject still exists |
| `DECISION-LOG.md`, `TESTING-STRATEGY.md`, `HANDOFF.md`, `REPOSITORY-REVIEW.md` | Current decisions and review | Keep |
| `.cursor/rules/` | Agent rules | Keep |
| `tools/parity/` | Live vs `/test` compare CLI | `/test` still mounted |
| `rebuild/FEATURE-INVENTORY.md`, `rebuild/REBUILD-PLAN.md`, `rebuild/REBUILD-BRIEF.md`, `rebuild/tests/` | How to harvest/retire rebuild | Keep until `/test-next` goes |

## Still blocked until v3 no longer needs `webapp/`

Do not unmount or delete these until Entra, magic links, user directory, shared session, and hybrid OData run inside root v3, and `/` has been proven with `webapp` unimported.

| Path | What it is | Why it exists | Proof still needed |
|---|---|---|---|
| `webapp/` (whole tree) | Former home site; OData runners; Entra + magic links; `app_users` | Production `/legacy` and v3 imports | Root `/` boots with no `import webapp` / no `/legacy` mount |
| `/legacy` mount in `wsgi.py` / `wsgi_dispatch.py` | Dispatcher slot | Compatibility URL | Same as above |
| `/test` mount | Second v3 at `/test` | SQL sandbox | Owner confirms no bookmark |
| `/test-next` + remaining `rebuild/` | Ground-up rebuild preview | Feature harvest | Then retire |
| `/beta` 302 in `wsgi.py` | Old beta URL | Bookmarks | Owner: drop vs redirect to `/` |
| `v3/web/beta_*.py`, Beta pill | Preview naming on the home site | Historical dual-site wiring | After mounts are gone |
| Disabled order-entry slice in `webapp/` | Feature-flagged vertical | Not the live product | Delete with legacy |

`.scratch/parity-cookies.env` is not in the index on this branch. It remains in `webapp-cache` history from `f286ce2` until a coordinated rewrite. Do not print those values.
