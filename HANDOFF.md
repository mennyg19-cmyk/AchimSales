# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 5 in progress on draft PR #1. Loop C failed: settled-leg skip crashed with `NameError` on `FAILED`. This HEAD imports `FAILED` and skips without crashing. Keep the PR draft. Do not merge or deploy Production. Do not start Phase 6.

## What's done

- Q1–Q11 logged. Phases 0–4 closed. Phase 4 gate commit `ecedd7c`.
- Phase 5: `0023` states, `0024` slot_when, `0025` window + filename, stored-target retries, settled skip no longer NameErrors.
- Loop A re-pass 7 PASS. Loop B PASS. Loop C FAIL on `FAILED` import.

## What's next

1. Push this commit. Wait for CI + Agent Guardrails green.
2. Fresh Loop C spawn (`claude-sonnet-5-thinking-high`) → `.scratch/review-pass-quality-phase5-repass.md`. Do not resume the FAIL agent.
3. If C PASS: trust-boundary (`claude-fable-5-thinking-high`).
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
