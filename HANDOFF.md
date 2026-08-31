# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 3 review gate is closed on draft PR #1 (HEAD `6093a41`). Keep the PR draft. Do not merge or deploy Production. Phase 4 (workers out of Flask/Gunicorn) is next.

## What's done

- Q1–Q11 logged.
- Phase 1.1 workflow gating.
- Phase 1.2: no history rewrite; owner confirmed Flask secret rotation.
- Phase 2: live-cookie adopt deleted; MSAL lookup-only; boot does not read Live DB; magic-link hashes + ProxyFix IP + log redaction. Trust-boundary F1–F3 closed.
- Phase 3: v3 is SQL Reporting API only. `odata_bridge.py`, `odata_run.py`, `beta_sources.py` deleted. Settings source picker gone. Cache keys have no origin token. Migration `0022` drops `beta_report_sources` (`0016` untouched). Item Averages uses `item_customer_sales_rolling_12`. Graph `@odata.type` kept. CLI/Automation OData stays outside `v3/`.
- Phase 3 reviews on `6093a41`: Loop A re-pass zero findings (first pass F1–F3 fixed in this HEAD). Loop B zero blocking findings. Loop C zero blockers (Q1 test-helper nit deferred). Trust-boundary N/A (reports/sources only).
- CI + Agent Guardrails success on `6093a41` (`33410938675` / `33410938879`).

## What's next

1. Phase 4: Flask/Gunicorn HTTP only. Separate worker process. Killable child jobs. `/readyz` worker/scheduler heartbeat.
2. Owner still needs GitHub Environment `production` required reviewers (Settings → Environments). That Environment does not exist yet.

## Open / BLOCKED

- GitHub Environment `production` required reviewers.
- Production merge/deploy.
- Live Litestream empty-disk restore.
- `LIVE_DB_PATH` / `flask import-live-users` until import evidence exists.

## Gotchas

- Do not check off boxes in `PR1-REMEDIATION-PLAN.md`.
- Do not restore `webapp/` or `rebuild/`. Preserve `archive/pre-cleanup-2026-08-27`.
- Keep `is_beta=True` until Phase 7.
- `gh` is read-only. PRs via ManagePullRequest. Keep draft.
- Python: `/workspace/.venv/bin/python`. v3 tests: cwd `/workspace/v3`. Root tests: `PYTHONPATH=/workspace` without `--noconftest`.
- Never stage `.venv/` or `.scratch/`.
