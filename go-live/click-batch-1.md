# Click-through batch 1 (local `http://127.0.0.1:5055`)

**When:** 2026-09-02 ~22:46–22:49 UTC
**Role:** developer `golive-dev@local.test`, then salesman via **Switch user** (header showed “Viewing as golive-sales@local.test”, not a fresh Sign Out + `/login/dev`).
**Evidence:** screen recording `/opt/cursor/artifacts/go-live-click-batch-1.mp4`; screenshots under `/tmp/computer-use/`.

| ID | Result | Seen |
|----|--------|------|
| P1 | pass | Developer sign-in, email + 4-role select |
| P2 | pass | 8 built cards + Daily Ordered / Heshy Open Orders company views |
| P2.5 | pass | Customer Aging “Coming soon / Not built yet” |
| C5–C9 | pass | Recent Reports, theme toggle (went dark), Sign Out, bottom nav |
| P5 | pass | Empty personal schedules + Add a schedule |
| P7 | pass (developer) | Profile through Developer sections |
| P8 | pass | Users table (seeded admin/dev + golive-dev), Add user, empty Salesmen |
| P9 | pass | 5 tiles at 0, Refresh data empty state |
| P3 Ordered | pass (UI only) | Period/Status/Salesman/Customers, Run, Email me, Columns, Save for, Saved views, More. No D365 data. |
| P7 salesman | pass | Profile / Appearance / Exclusions only; no People, Delivery, Developer; no Dashboard tab |

No Reporting API in this VM — Run report was not expected to return rows.
