# Deletion inventory

Reviewed revision: `954845b` (`cursor/p0-security-containment-adb6`, 2026-08-27).

This is the deletion report from `cleanup-protocol.mdc` and `REPOSITORY-REVIEW.md`. **Nothing in this file has been deleted or untracked.** Paths below wait for an explicit owner approval of this exact list. Do not create the archive tag until the final pre-deletion commit.

Production still boots `wsgi.py`: `/` is v3, `/legacy` is `webapp/`, `/test` is a second v3, `/test-next` is `rebuild/`. v3 still imports `webapp` for OData runners, user rows, live-session adoption, and some settings.

## Do not delete (still in production use)

| Path | What it is | Why keep |
|---|---|---|
| `v3/` | Current site at `/` | Surviving app |
| `reports/`, `core/`, `data/`, `runbooks/`, `run.py`, `report_registry.json` | CLI + Azure Automation report engines | README: still the Automation path |
| `webapp/` | Legacy Flask app mounted at `/legacy`; also imported by v3 | Login/session/user directory/OData still flow through it |
| `rebuild/` | Preview app at `/test-next` | Harvest approved fixes first; then delete |
| `startup.sh`, `litestream.yml`, `Dockerfile`, `gunicorn.conf.py`, `deploy.ps1`, `deploy-runbook.ps1` | Prod boot and deploy | Live Azure |
| `v3/web/static_dist/` including `*.map` and `vendor/` | Committed frontend | Azure/Oryx does not run esbuild |
| `tests/` that cover current security and report math | Regression suite | Keep while the subject still exists |
| `DECISION-LOG.md`, `TESTING-STRATEGY.md`, `HANDOFF.md`, `REPOSITORY-REVIEW.md` | Current decisions and review | Summarize before dropping old logs |
| `.cursor/rules/` | Agent rules | Keep |

## Blocked until v3 no longer needs `webapp/`

Do not unmount or delete these until Entra, magic links, user directory, shared session, and hybrid OData run inside root v3, and `/` has been proven with `webapp` unimported.

| Path | What it is | Why it exists | Proof still needed |
|---|---|---|---|
| `webapp/` (whole tree) | Former home site; OData runners; Entra + magic links; `app_users` | Production `/legacy` and v3 imports (`odata_bridge`, `seed_users`, `beta_live_session`, `beta_sources`, `beta_access`, auth helpers) | Root `/` boots with no `import webapp` / no `/legacy` mount |
| `/legacy` mount in `wsgi.py` / `wsgi_dispatch.py` | Dispatcher slot | Compatibility URL | Same as above |
| `/test` mount | Second v3 at `/test` | SQL sandbox | Owner confirms no bookmark; `V3_MOUNT_ENABLED` off then remove |
| `/test-next` + `rebuild/` | Ground-up rebuild preview | Feature harvest | Inventory leftover rebuild-only features, then retire |
| `/beta` 302 in `wsgi.py` | Old beta URL | Bookmarks | Owner: drop vs redirect to `/` |
| `v3/web/beta_*.py`, `is_beta` / Beta pill in `v3/web/templates/base.html` | Preview naming on the home site | Historical dual-site wiring | Rename after mounts are gone; do not copy `/test`-only behavior |
| Disabled order-entry slice in `webapp/` | Feature-flagged vertical | Not the live product | Confirm no caller, then delete with legacy |

## Candidate: untrack (gitignore already lists these)

`.gitignore` already has `.scratch/`. Git still tracks **168** files under `.scratch/` because they were added before the ignore. Untracking removes them from the index; the working tree can keep them locally.

| Path | What it is | Why it was created | Why untrack |
|---|---|---|---|
| `.scratch/` (168 tracked files) | Agent scripts, grill notes, OData probes, parity dumps, Kudu output | Session scratch and live↔test parity | Ignore says so; not runtime |
| `.scratch/azure-logs.zip` (12 MB) | Downloaded Azure logs | Troubleshooting | Binary dump |
| `.scratch/odata_metadata.xml` and probe JSON | D365 metadata snapshots | Debugging OData | Regenerable |
| `.scratch/parity/**` | Parity run markdown/CSV | July 2026 live vs `/test` | Historical; not a test suite |
| `.scratch/*.ps1` including `agent-run.ps1` | One-off agent PowerShell | Workflow scratch | Must not be source |

`.scratch/parity-cookies.env` is **not** in the index on this branch (P0.1). It remains in `webapp-cache` history from `f286ce2` until a coordinated rewrite. Do not print those values.

## Candidate: delete after archive tag + approval

Only after the archive tag exists and the owner checks the boxes below.

| Path | What it is | Why it exists | Why delete |
|---|---|---|---|
| `logs/run_log.csv` | 32 KB CSV under `logs/` | Old run log sample | `*.log` ignored; this CSV is still tracked; not imported |
| `v3/REVIEW-LOG.md` (137 KB) | v3 rebuild review narrative | Multi-agent rebuild | Decisions that still bind should already be in `DECISION-LOG.md`; this file is not imported |
| `rebuild/rebuild-audit/` | Phase-0 audit markdown | Rebuild protocol | After `rebuild/` is retired |
| `rebuild/proposals/` | Competing rebuild proposals | Rebuild protocol | Same |
| `rebuild/DEBATE-LOG.md`, `rebuild/BUILD-HISTORY.md`, `rebuild/FEATURE-INVENTORY.md`, `rebuild/REBUILD-PLAN.md`, `rebuild/REBUILD-BRIEF.md` | Rebuild planning | Rebuild protocol | Same; harvest any leftover feature first |
| `rebuild/tests/` | Tests for the preview app | `/test-next` | Delete with `rebuild/` |
| `tools/parity/` | Live vs `/test` compare CLI | Parity project | After `/test` is gone and owner does not want the CLI |
| Source maps `v3/web/static_dist/**/*.map` | esbuild maps | Debug compiled JS | Only after CI/Azure runs `npm run build` and ships `static_dist` |

## Not junk

- `tools/check-no-tracked-secrets.sh` — CI job.
- `tools/daily_log_digest.py`, `tools/sync-to-onedrive.ps1` — ops; confirm before any later pass.
- `v3/web/static_src/public/vendor/` duplicate of `static_dist/vendor/` — esbuild `copyPublic()` source; keep both until the build is the release path.
- `webapp/static/vendor/feather.min.js` — legacy Feather; keep until `webapp/` goes.
- `core/`, `reports/`, `data/` tests — CLI/Automation.

## `.gitignore` already covers (do not commit)

`node_modules/`, `.data/`, `.venv/`, `__pycache__/`, `*.db`, `*.xlsx`, `.env*` except `.env.example`, `azlogs*/`, `v3logs*/`. No extra ignore change is required for this inventory.

## Approval

Reply with which groups to do, using these exact labels:

1. **Untrack `.scratch/`** (168 files; ignore already set).
2. **Delete `logs/run_log.csv` and `v3/REVIEW-LOG.md`** after the archive tag.
3. **Hold** `webapp/`, `rebuild/`, dispatcher mounts, Beta pill — until native v3 login/OData.

Default if you say “approve the inventory” without picking: do **(1)** only. Do not tag, unmount, or delete `webapp/` / `rebuild/` on that phrase.
