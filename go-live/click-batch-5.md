# Click-through batch 5 (local `http://127.0.0.1:5055`)

**When:** 2026-09-03 ~00:14–00:23 UTC
**Role:** developer `golive-dev@local.test`
**Agent:** computerUse [Browser click batch 5](bc-87194bba-2c46-50d2-a6bf-0f02b5f337ce)
**Model:** inherit (computerUse)
**Runner:** spawn
**Screenshots:** `/tmp/computer-use/b5-*.webp` and artifacts `go_live_b5_*.webp`

## Proof-of-read (agent)

Leftovers: role-picker radio, settings sections, help, theme, CLO search, master History/Run now, dashboard empty. Batch 4 parent notes: Viewing as on `/login/dev` is expected; role-picker needs a radio.

## Results (parent-verified)

| ID | Result | Evidence |
|----|--------|----------|
| P13 | **pass** | Search golive-sm2, radio, submit → header VIEWING AS TEST SALESMAN 2, salesman cards only (Ordered/Invoiced/CA). View as yourself returned to developer. |
| P7 exclusions | **pass** | “Customer master is not configured.” |
| P7 visibility + flags | **pass** | All 8 reports On; Dashboard On; Order Entry Off; Test Site Off. |
| P7 Delivery | **pass** | Redirect company schedule mail Off; test email chips. |
| P7 Developer sources | **pass** | Beta SQL/OData dropdowns (customer_activity sql, customer_aging odata, …). |
| C10 Help | **not that control** | Agent opened **Recent Reports** (“No recent or kept runs”). Help is the `?` `data-help` overlay (`#helpOverlay`), not Recent Reports. Retest that `?` on Ordered or Dashboard. |
| C6 theme | **pass** | Cycle included light (help screenshot), dark, monochrome, monochrome_dark. Later shots back on dark. |
| P4.3 | **pass** | Typed `a` → “No customers match.” (no D365 customer master). |
| P6.7 History | **expected-block** | `/master-schedules/2/history` Daily Ordered Report FAILURE `REPORTING_API_BASE_URL/KEY not set`. |
| P6.7 Run now | **expected-block** | Same missing API. |
| P9 | **pass** | Dashboard tiles 0; “No customers yet. Tap Refresh data…” |

No new product bugs in this batch. C10 still needs a real `?` click.
