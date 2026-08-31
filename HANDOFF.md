# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 4 review gate is closed on draft PR #1 (HEAD `9466fe4`). Keep the PR draft. Do not merge or deploy Production. Phase 5 (delivery states) is next.

## What's done

- Q1–Q11 logged.
- Phase 1.1 workflow gating. Phase 1.2: no history rewrite; owner confirmed Flask secret rotation.
- Phase 2: live-cookie adopt deleted; MSAL lookup-only; boot does not read Live DB; magic-link hashes + ProxyFix IP + log redaction. Trust-boundary F1–F3 closed.
- Phase 3: v3 is SQL Reporting API only. OData path deleted under `v3/`. Graph `@odata.type` kept. CLI/Automation OData stays outside `v3/`.
- Phase 4: HTTP-only Gunicorn. `python -m web.bootstrap` then `tools/supervise-web.sh` (Gunicorn + `python -m web.worker_main`). Killable `python -m web.jobs.child` with 45-minute cap. Prod `/readyz` needs fresh worker (90s) and scheduler (180s) heartbeats. Crash recovery requeues report/export/mirror; cancels `schedule.run` / `report.deliver` (including retry cap and independent child crash). SIGTERM leaves the row `running` for recovery. Heartbeat ticks during child wait.
- Phase 4 reviews on `9466fe4` (Loop A PASS `3758af7`, Loop B PASS `ad22a65`, Loop C PASS then nits in this HEAD). Trust-boundary N/A (no auth/roles/payments).
- CI + Agent Guardrails success on `9466fe4` (push CI `33423206555` / AG `33423206553`; PR CI `33423211223` / AG `33423211205`). Local: v3 641, root 152, P0 111+10.

## What's next

1. Phase 5: delivery states `prepared|sending|accepted|sent|failed|unknown`. Graph post-submit crash = `unknown`, no auto-retry.
2. Owner still needs GitHub Environment `production` required reviewers (Settings → Environments). That Environment does not exist yet.

## Open / BLOCKED

- GitHub Environment `production` required reviewers.
- Access-log review of the cookie-file window.
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
- Graph JSON `@odata.type` in `v3/web/delivery/graph_mail.py` is Microsoft Graph, not D365 OData.
- `core.email_report` import from `magic_link_email.py` is Graph mail, not D365 OData.
- Do not start Phase 5 until this handoff is the source of truth for the next session.
