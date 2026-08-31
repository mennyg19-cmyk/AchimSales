# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 5 in progress on draft PR #1. Loop A re-pass found one remaining blocker (two retries on one slot sharing a job); that is fixed in this HEAD. CI then a fresh Loop A re-pass are next. Keep the PR draft. Do not merge or deploy Production. Do not start Phase 6.

## What's done

- Q1–Q11 logged. Phases 0–4 closed. Phase 4 gate commit `ecedd7c`.
- Phase 5 implementation: `0023_delivery_leg_states.sql`, honest states, frozen `slot_id`/`slot_day`/`slot_when`, build-before-send, Graph unknown, folder GET verify, token skew, 90-day leg prune.
- Loop A findings F1–F5 + N1: child timeout/nonzero exit settles sending email → `unknown`; filename/folder use frozen `slot_when`; `reopen_for_retry` keeps upload session; retry sends only `retry_attempt_key` and the stored target; email-now unknown is listed on privileged `/schedules` with reconcile. `pending` migration test applies 0023 for real.
- Local after this commit: v3 676, root 152, P0 111+10.

## What's next

1. Push this commit. Wait for CI + Agent Guardrails green on both push and PR.
2. Fresh Loop A spawn (`gpt-5.6-sol-high`) → `.scratch/review-pass-A-phase5-repass.md`. Do not resume the FAIL agent.
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
- Do not edit migrations `0016`, `0019`, `0020`, `0021`, `0022`, `0023`.
- New POST forms need nosemgrep on the form tag (Flask `csrf_token()` is not a Django match).
- SIGTERM still leaves the job `running` for recovery. Timeout and unsafe child death cancel then settle legs.
