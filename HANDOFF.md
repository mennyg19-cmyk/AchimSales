# Session Handoff

Last updated: 2026-09-01

**Status:** Phase 7 implementation on this branch. Review gate not started. Draft PR #1. Keep the PR draft. Do not merge or deploy Production. Do not start Phase 8 until the Phase 7 review gate passes (live Azure drill stays owner BLOCKED).

## What's done

- Q1–Q11 logged. Phases 0–6 closed.
- Phase 7 repo work:
  - Canonical `SITE_PRECIOUS_DB_PATH` / `SITE_CACHE_DB_PATH` / `LITESTREAM_AZURE_SITE_PATH`. `BETA_*` aliases still work.
  - `is_beta=True` unchanged (`session` cookie, reports-only).
  - `startup.sh` restores/replicates only the serving file. Leftover `/test` `PRECIOUS_DB_PATH` is not required. `/home` one-time seed removed.
  - `litestream.yml` is one database.
  - Prod refuses missing/zero-byte/corrupt/no-users serving DBs. After migrate: required tables, latest schema, `app_settings.site_db_role=home`.
  - Pre-0016 sqlite with one user migrates through 0016+.
  - Prod `/readyz` uses `PRAGMA quick_check`.
- Local: v3 pytest 736; root 158.

## What's next

1. Phase 7 self-review leftover + Loops A/B/C + trust-boundary (restore/readiness is fail-closed).
2. Owner still needs GitHub Environment `production` required reviewers.
3. Live Azure empty-disk restore drill stays BLOCKED.

## Open / BLOCKED

- GitHub Environment `production` required reviewers.
- Access-log review of the cookie-file window.
- Production merge/deploy.
- Live Litestream empty-disk restore (Phase 7 live gate).
- `LIVE_DB_PATH` / `flask import-live-users` until import evidence exists.

## Gotchas

- Do not check off boxes in `PR1-REMEDIATION-PLAN.md`.
- Do not restore `webapp/` or `rebuild/`. Preserve `archive/pre-cleanup-2026-08-27`.
- Keep `is_beta=True`. Do not point home site at `PRECIOUS_DB_PATH` / `LITESTREAM_AZURE_PATH`.
- `gh` is read-only. PRs via ManagePullRequest. Keep draft. Omit `draft` on `update_pr` to keep draft.
- Python: `/workspace/.venv/bin/python`. v3 tests: cwd `/workspace/v3`. Root tests: `PYTHONPATH=/workspace` without `--noconftest`. Restore-preflight: `tests/test_startup_restore.py --noconftest`.
- Never stage `.venv/` or `.scratch/`.
- Graph JSON `@odata.type` in `v3/web/delivery/graph_mail.py` is Microsoft Graph, not D365 OData.
- Do not claim `internetMessageId` or `Client-Request-Id` makes Graph `sendMail` idempotent.
- Do not edit migrations `0016`–`0027`. Add forward migrations only.
- New POST forms need nosemgrep on the form tag (Flask `csrf_token()` is not a Django match).
- Company Send now: view-only managers MAY send (Q9). Do not tighten `run_master`.
- EmailService with `db=` filters recipients. Tests that actually send need company domain, approved addresses, or Settings test emails.
- `jobs.created_at` is SQLite `datetime('now')`. `schedule_runs.started_at` is Python ISO.
