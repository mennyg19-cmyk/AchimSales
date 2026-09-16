# Session Handoff

Last updated: 2026-09-16 (rebuild continuation docs for a new agent)

**Status:** FastAPI is **already production** on https://reports.achimonline.com (`main`, cutover `331c9da`, boot hotfixes through `ed4e25c`). Next work is **not** another rebuild. Paste `rebuild/NEW-AGENT-PROMPT.md` into a **new** agent.

## Working tree

- **Branch:** `cursor/rebuild-handoff-551b` (docs only vs `origin/main`)
- **Repo:** AchimSales
- **Prod URL:** https://reports.achimonline.com (FastAPI `app/`)
- **Implementation PRs to leave alone unless Menny names them:** leftover Flask #35; any other agent’s FastAPI hotfix branches

## What's done

- Brother-stack FastAPI home cut over (PR #68). Flask `v3/` / `webapp/` / Automation CLI gone from the tree.
- Azure boot: vendored `app/deps`, `python3 -m gunicorn`, skip leftover Litestream, `schedule_runs.message`, do not restore Flask `precious.db` over `home.sqlite`.
- Rebuild **plan** from 2026-09-15 is superseded by that cutover. Continuation spec lives in `rebuild/`.

## What's in progress

- Docs PR: this branch. No app code in this change.
- Live login: People must exist in `/tmp/homedata/home.sqlite` (Kudu/SSH import from `/home/LogFiles/home-precious.db`).
- Agent Guardrails Semgrep red on `app/entra.py` format-string URL builders.

## What's next (new agent, in order)

1. Precious import if login is dead (README).  
2. Semgrep `entra.py`.  
3. Port Flask companion-xlsx spill (`9ba286f` `v3/web/reporting/export.py`) into `app/export_xlsx.py`.  
4. Litestream replicate `home.sqlite` after `/healthz` is solid.  
5. SQL/thin-assembler tab math — `rebuild/REPORT-TAB-HANDOFF.md`.  
6. P4.I8 salesman vs SalesGroup — ask Menny.  
7. Customer Aging stays BACKLOG.

## Open decisions

- P4.I8 mapping (BLOCKED on Menny).  
- When to re-enable Litestream.  
- DBA: commission YTD SP, Ordered Open$/Fulfillment%, Number 4 YTD, item-level averages.

## Gotchas

- `HANDOFF.md` copies that still say “rebuild not started” or July 2026 parity are wrong. **`rebuild/NEW-AGENT-PROMPT.md` wins.**  
- `/tmp/v3data/precious.db` is the old `/test` seed (~9 views). Home Flask file was `BETA_PRECIOUS_DB_PATH`. FastAPI reads `home.sqlite`.  
- Do not merge PR #35. Do not restore Flask as the app. Do not switch to AG Grid.  
- Azure deploy can be green while Semgrep is red.
