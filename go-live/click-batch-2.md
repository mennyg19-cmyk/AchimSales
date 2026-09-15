# Click-through batch 2 (local `http://127.0.0.1:5055`)

**When:** 2026-09-02 ~23:00–23:10 UTC
**Role:** developer `golive-dev@local.test` (session from batch 1).
**Agent:** computerUse [Browser click batch 2](bc-7156ecbd-7f48-544c-996f-d47aff3c5c57)
**Model:** inherit (computerUse)
**Runner:** spawn
**Recording:** batch-2 `RecordScreen SAVE_RECORDING` timed out at 660s; no `go-live-click-batch-2.mp4`. Screenshots under `/tmp/computer-use/` were not retained on this VM after the agent exited.

Parent checked sqlite (`/workspace/.scratch/go-live-data/precious.db`) after the run. Claims below that conflict with the DB or with code are marked **parent note**.

| ID | Result | Seen |
|----|--------|------|
| P3 Invoiced | pass (UI) | Filter bar: Period All Time, Salesman All, Customers All |
| P3 Salesman | pass (UI) | Year 2026, Salesman All |
| P3 Number 4 | pass (UI) | VIEW = Both |
| P3 Customer Activity | pass (UI) | Salesman All |
| P3 Item Averages | pass (UI) | Privileged; little/no filters |
| P3 Sales by State | pass (UI) | Year 2026 |
| P4 picker | pass (UI) | Salesman `--All--`, customer search. No customer rows (no D365 lookups). |
| P2.3 Daily Ordered | pass | Landed `/reports/ordered?cview=1` |
| P3.16 More → Schedule | **partial / expected-disable** | Agent: menu opened, modal “hung.” **Parent:** on `?cview=1`, `report.ts` sets `loadedNamedView = null` and disables Schedule (“Load Default or a named saved view…”). Retest from `/reports/ordered` with Default loaded. Not treated as a product hang until that retest. |
| P5.5 Add schedule wizard | pass (steps only) | View / When / Where walked. Filename default `{Schedule}_{MM}-{DD}-{YYYY}`; agent preview `Default_09-02-2026.xlsx`; CC/BCC fields present. |
| P5 save | **not done** | `schedules` table still **empty** — wizard was not submitted. |
| P6 company schedules | pass (data) / screenshot unverified | Agent claimed 12-row table. Sqlite has 12 **boot-seeded** master schedules (Daily Invoiced … Weekly Amazon Ordered). Screenshot files gone; re-screenshot in batch 3. |
| P8.2 duplicate | pass | `admin@local.test` → “User already exists; edit them instead” |
| P8.2 add salesman | pass | `golive-sm2@local.test` id=6, role salesman |
| P11 | pass | db-explorer table list (app_settings … users) |
| P12 | pass | Notif diagnostic + “Generate overdue now” |
| P10.2 | pass | Run log empty (“No report runs recorded yet.”) |
| P10.3 | pass | 6 failed schedule runs, all `REPORTING_API_BASE_URL/KEY not set` — local cron against no D365 API, **not** a production bug |

No HTTP 500s reported. Run report / real Excel-from-D365 still blocked (no Reporting API in this VM).
