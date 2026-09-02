# Click-through batch 3 (local `http://127.0.0.1:5055`)

**When:** 2026-09-02 ~23:31–23:44 UTC
**Role:** developer `golive-dev@local.test`; salesman via **Viewing as** (see parent note)
**Agent:** computerUse [Browser click batch 3](bc-546d9e11-30c2-5a83-91b5-c49ced80ed27)
**Model:** inherit (computerUse)
**Runner:** spawn
**Recording:** no batch-3 video (`SAVE_RECORDING` found no active recording). Named screenshots under `/tmp/computer-use/p*.webp`; copies in artifacts `go_live_*.webp`.

## Proof-of-read (agent)

click-remaining.md: 3 must-retest + 11 unchecked. click-batch-2.md: wizard not saved; Schedule disabled on cview; API-not-set failures expected.

## Results (parent-verified)

| ID | Result | Evidence |
|----|--------|----------|
| P6 | **pass** | `/settings/company-schedules`: **12** seeded rows (agent said 11; screenshot + sqlite count = 12). 5-step wizard Report→When→Options→Where→Review. Did not save a 13th. |
| P3.16 | **pass** | `/reports/ordered` without cview. Modal “Schedule this view”; filename `{Schedule}_{MM}-{DD}-{YYYY}` preview `Ordered_09-02-2026.xlsx`; CC/BCC; mock OneDrive/SharePoint folders. |
| P5 save | **pass** | Sqlite: two personal `ordered` / Default / daily 08:00 rows, owner golive-dev, filename template set. Table showed Edit/Run now/Copy/History/Delete. |
| P5 History | **pass** | Empty history before Run now. |
| P5 Copy | **pass** | Second row created. |
| P5 Run now | **expected-block** | FAILURE `REPORTING_API_BASE_URL/KEY not set`. |
| P5.2 owner banner | **pass** (parent from screenshot) | After copy, table grouped under `golive-dev@local.test`. |
| P8.3 | **pass** | `golive-sm2@local.test` display name **Test Salesman 2**. Salesmen master (0). |
| Salesman settings/403 | **pass with honesty** | Settings = Profile / Appearance / Exclusions; no Dashboard tab; `/admin/users` JSON `{"error":"Forbidden"}`. **Header was “VIEWING AS GOLIVE-SALES@LOCAL.TEST”**, not Sign Out + `/login/dev`. Same gap as batch 1. Retest true login in batch 4. |

## Skipped (time cap)

P7 settings extras, P13 role-picker, P14 `/impersonate`, C10 Help, C6 theme cycle, P9 customer row, P4.3 last-order search, P6.7 master History/Run now.
