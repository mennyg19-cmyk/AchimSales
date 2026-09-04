# Click-through batch 6 — Help overlay (local `http://127.0.0.1:5055`)

**When:** 2026-09-03 ~00:37–00:38 UTC
**Role:** developer `golive-dev@local.test`
**Agent:** computerUse [Help overlay only](bc-77c3a647-2b6c-5b82-a9e8-08b79407b84a)
**Model:** inherit (computerUse)
**Runner:** spawn

## Proof-of-read (agent)

Batch 5 opened Recent Reports. Help is the `?` / `data-help` control that opens `#helpOverlay`.

## Results (parent-verified)

| ID | Result | Evidence |
|----|--------|----------|
| C10 dashboard | **pass** | `/dashboard` `?` → overlay **Dashboard Overview** (Total/New/Active/Overdue/Inactive definitions). Artifact `go_live_help_dashboard.webp`. |
| C10 Ordered | **pass** | `/reports/ordered` `?` → overlay **Ordered Report** (tabs + Open Orders tip). Artifact `go_live_help_ordered.webp`. |

This closes the last leftover chrome item from the inventory click list.
