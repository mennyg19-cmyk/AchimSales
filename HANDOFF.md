# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 5 in progress on draft PR #1. Loop A re-pass 2 failed: job-gone retry lost `slot_when`. This HEAD persists that instant on the leg (`0024`). Keep the PR draft. Do not merge or deploy Production. Do not start Phase 6.

## What's done

- Q1–Q11 logged. Phases 0–4 closed. Phase 4 gate commit `ecedd7c`.
- Phase 5 implementation: `0023_delivery_leg_states.sql`, honest states, frozen `slot_id`/`slot_day`/`slot_when`, build-before-send, Graph unknown, folder GET verify, token skew, 90-day leg prune.
- Loop A F1–F5 + N1 on `a664b65`. Re-pass 1 F1 (two-leg dedup) on `105e29e`. Re-pass 2 F1: `0024_leg_slot_when.sql` stores the enqueue instant on the leg so a deleted job row cannot mint a second `{HH}{mm}` filename.

## What's next

1. Push this commit. Wait for CI + Agent Guardrails green.
2. Fresh Loop A spawn (`gpt-5.6-sol-high`) → `.scratch/review-pass-A-phase5-repass3.md`. Do not resume prior FAIL agents.
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
- Do not edit migrations `0016`, `0019`, `0020`, `0021`, `0022`, `0023`. Add forward files only (`0024` is the slot_when column).
- New POST forms need nosemgrep on the form tag (Flask `csrf_token()` is not a Django match).
- SIGTERM still leaves the job `running` for recovery. Timeout and unsafe child death cancel then settle legs.
