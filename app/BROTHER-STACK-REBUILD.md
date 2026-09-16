# Rebuild handoff (pointer)

**Do not follow this file as “rebuild not started.”** FastAPI already cut over to production (PR #68, `331c9da`).

Source of truth for a **new agent**:

- Paste prompt: [`rebuild/NEW-AGENT-PROMPT.md`](../rebuild/NEW-AGENT-PROMPT.md)
- Full handoff: [`rebuild/BROTHER-STACK-REBUILD.md`](../rebuild/BROTHER-STACK-REBUILD.md)
- Tab math: [`rebuild/REPORT-TAB-HANDOFF.md`](../rebuild/REPORT-TAB-HANDOFF.md)

Inventory and original slice map in this folder (`FEATURE-INVENTORY.md`, `REBUILD-PLAN.md`) are still useful for KEEP/FIX IDs. P13.2 / P13.3 (“do not push `main` until cutover”) are **done**. Remaining gaps: SQL tab math, companion Excel OOM, Semgrep `entra.py`, Litestream, P4.I8, Aging backlog.
