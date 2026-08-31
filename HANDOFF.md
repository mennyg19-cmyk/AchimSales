# Session Handoff

Last updated: 2026-08-31

**Status:** Phase 2 review gate is closed on draft PR #1 (HEAD `f58dd56`). Keep the PR draft. Do not merge or deploy Production. Phase 3 (SQL-only v3, delete OData from the web app) is next.

## What's done

- Q1–Q11 logged.
- Phase 1.1 workflow gating.
- Phase 1.2: no history rewrite; owner confirmed Flask secret rotation.
- Phase 2: live-cookie adopt deleted; MSAL lookup-only; boot does not read Live DB; magic-link hashes + ProxyFix IP + log redaction.
- Trust-boundary F1–F3 closed: backslash `next` rejected; admin cannot impersonate a developer; MSAL errors generic; Entra `error_description` not logged.
- Loops A/B/C green on `822ce3d`. Trust-boundary re-pass: zero findings. CI on `f58dd56`: CI + Agent Guardrails success (semgrep included).

## What's next

1. Phase 3: SQL-only v3. Item Averages currently defaults to OData. Delete `odata_bridge.py`, `odata_run.py`, `beta_sources.py` from `v3/`. Keep OData in `reports/`, `core/`, `data/`, `runbooks/` for CLI/Automation.
2. Owner still needs GitHub Environment `production` required reviewers (Settings → Environments). That Environment does not exist yet.

## Open / BLOCKED

- GitHub Environment `production` required reviewers.
- Production merge/deploy.
- Live Litestream empty-disk restore.
- `LIVE_DB_PATH` / `flask import-live-users` until import evidence exists.
