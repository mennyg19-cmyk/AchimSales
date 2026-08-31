# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 6 review gate **closed** at `d22986f`. Draft PR #1. Keep the PR draft. Do not merge or deploy Production. Do not start Phase 7 until the next session picks it up from this handoff.

## What's done

- Q1–Q11 logged. Phases 0–5 closed. Phase 5 gate commit `f71b80a`.
- Phase 6 implementation `9680ba8` plus review fixes through `d22986f`:
  - Commission cards use the current bucket. SP `commission` is a fraction (`1` = 100%). Invoice SP `0` stays $0. Tab % still shows leftover `salesmen.commission_pct`. No-YTD fallback uses each invoice's own rate on the same customer/salesman grouping as the summary.
  - Custom interval start after end is rejected. Company `skip_sabbath=false` persists.
  - Forward `0026` marks leftover `scheduled` runs `legacy`. `last_run_at` ignores manual/legacy/unknown.
  - Expired kept runs are denied. Payload prune leaves `kept_until` as a tombstone. Result/export share `load_source_payload` / `source_result_available`. Tick prune matches Q10.
  - Configured `SP_SITE_URL` that cannot resolve fails closed (no tenant search).
  - Q9: view-only managers still MAY company Send now. That plan bullet was not implemented.
  - Reconcile diagnostics and `claim-once` are developer POST+CSRF. GET is 405.
  - Outside-company To/CC/BCC stay pending until admin/developer approve. `@achimonline.com` and Settings test emails send. Manager approve is 403.
- Phase 6 reviews at `d22986f`: Loop A re-pass 3 PASS; Loop B PASS; Loop C re-pass PASS; trust-boundary PASS (zero findings).
- Platform on `d22986f`: push CI `33452034513` / AG `33452034511`; PR CI `33452038102` / AG `33452038125` (success). Loop B local: v3 pytest 717, root 152.

## What's next

1. Phase 7 (one-site persistence). Write EXPECTED in `.scratch/phase-plan.md` before any Phase 7 edit. Keep `is_beta=True` until Phase 7 work says otherwise.
2. Owner still needs GitHub Environment `production` required reviewers.

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
- Do not edit migrations `0016`–`0027`. Add forward migrations only.
- New POST forms need nosemgrep on the form tag (Flask `csrf_token()` is not a Django match).
- SIGTERM still leaves the job `running` for recovery. Timeout and unsafe child death cancel then settle legs.
- Company Send now: view-only managers MAY send (Q9). Do not tighten `run_master`.
- EmailService with `db=` filters recipients. Tests that actually send need company domain, approved addresses, or Settings test emails.
- `jobs.created_at` is SQLite `datetime('now')`. `schedule_runs.started_at` is Python ISO.
