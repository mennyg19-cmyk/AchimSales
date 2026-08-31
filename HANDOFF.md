# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 5 review gate **closed** at `f71b80a`. Draft PR #1. Keep the PR draft. Do not merge or deploy Production.

## What's done

- Q1–Q11 logged. Phases 0–4 closed. Phase 4 gate commit `ecedd7c`.
- Phase 5 implementation: `0023` states, `0024` slot_when, `0025` window + filename, stored-target retries, settled skip imports `FAILED`.
- Phase 5 reviews at `f71b80a`: Loop A re-pass 7 PASS, Loop B PASS, Loop C re-pass PASS, trust-boundary PASS (zero blocking).
- Platform on `f71b80a`: push CI `33442916867` / AG `33442916863`; PR CI `33442922114` / AG `33442922116` (15/15 success). Local: v3 pytest 687, root 152, P0 111+10.

## What's next

1. This docs commit: wait for CI + Agent Guardrails green.
2. Phase 6 (report/schedule defects). Write EXPECTED in `.scratch/phase-plan.md` before any Phase 6 edit. Q9 supersedes the plan's "tighten company Send now" bullet -- log it, do not tighten `run_master`.
3. Owner still needs GitHub Environment `production` required reviewers.

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
- Do not edit migrations `0016`, `0019`, `0020`, `0021`, `0022`, `0023`, `0024`, `0025`. Phase 6 uses a **forward** correction for 0019.
- New POST forms need nosemgrep on the form tag (Flask `csrf_token()` is not a Django match).
- SIGTERM still leaves the job `running` for recovery. Timeout and unsafe child death cancel then settle legs.
- Company Send now: view-only managers MAY send (Q9). Do not change that in Phase 6.
