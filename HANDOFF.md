# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 5 in progress on draft PR #1. Loop A re-pass 5 failed: last live fan-out key removed silently skipped the selected retry. This HEAD still enters fan-out from the stored salesman key. Keep the PR draft. Do not merge or deploy Production. Do not start Phase 6.

## What's done

- Q1–Q11 logged. Phases 0–4 closed. Phase 4 gate commit `ecedd7c`.
- Phase 5: `0023` states, `0024` slot_when, `0025` window + filename, fan-out retry uses stored salesman address even when live keys are empty.
- Loop A FAIL history: F1–F5 (`a664b65`), two-leg dedup (`105e29e`), job-gone `slot_when` (`d7ed6ca`), live window/filename (`303bfd8`), live salesman email (`34fbd60`). Re-pass 5 F1: `_deliver_window` enters fan-out when the selected leg has `salesman_key`.

## What's next

1. Push this commit. Wait for CI + Agent Guardrails green.
2. Fresh Loop A spawn (`gpt-5.6-sol-high`) → `.scratch/review-pass-A-phase5-repass6.md`. Do not resume prior FAIL agents.
3. If A PASS: Loop B then C (`claude-sonnet-5-thinking-high`), then trust-boundary (`claude-fable-5-thinking-high`).
4. Owner still needs GitHub Environment `production` required reviewers.

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
- `gh` is read-only. PRs via ManagePullRequest. Keep draft. Omit `draft` on `update_pr` to keep draft.
- Python: `/workspace/.venv/bin/python`. v3 tests: cwd `/workspace/v3`. Root tests: `PYTHONPATH=/workspace` without `--noconftest`.
- Never stage `.venv/` or `.scratch/`.
- Graph JSON `@odata.type` in `v3/web/delivery/graph_mail.py` is Microsoft Graph, not D365 OData.
- Do not claim `internetMessageId` or `Client-Request-Id` makes Graph `sendMail` idempotent.
- Do not edit migrations `0016`, `0019`, `0020`, `0021`, `0022`, `0023`, `0024`. `0025` is window + filename.
- New POST forms need nosemgrep on the form tag (Flask `csrf_token()` is not a Django match).
- SIGTERM still leaves the job `running` for recovery. Timeout and unsafe child death cancel then settle legs.
