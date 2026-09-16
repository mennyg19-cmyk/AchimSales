# Paste this entire file as the first message to a new Cursor agent

You are a **new** agent with empty context. Do not look for a prior chat. Do not continue leftover Flask PR https://github.com/mennyg19-cmyk/AchimSales/pull/35 and do not merge it.

Read `rebuild-handoff/BROTHER-STACK-REBUILD.md` and `rebuild-handoff/REPORT-TAB-HANDOFF.md` in this repo **before any edit**. If those files are missing, this prompt is still the job.

## What already happened (do not redo, do not undo)

1. A FastAPI rebuild (`app/`, Tabulator + v3 CSS, doorway JSON) was built and **cut over** to https://reports.achimonline.com on 2026-09-16 (PR #68, `331c9da`).
2. Menny rolled production **back to Flask** the same day. Commit `d17524b` on `main`: tree matches last Flask home `4f94afc`, plus Azure boot (`python3 -m gunicorn`, vendored webapp deps).
3. FastAPI is **not deleted**. Parked at branch `cursor/fastapi-rebuild-parked-0a24` and tag `fastapi-rebuild-parked-2026-09-16`.

**Production right now**

- Branch: **`main`** = Flask (`v3/` home at `/`, `webapp/` `/legacy`, mounts as before).
- Site: https://reports.achimonline.com on Azure `achim-sales-reports` (Canada Central, Basic B1). Only `main` auto-deploys.
- Home sqlite: `BETA_PRECIOUS_DB_PATH` (`/tmp/betadata/precious.db`). `/tmp/v3data` is `/test`. FastAPI’s `home.sqlite` is not the live file.

**Your job** is the original rebuild: **look = current Flask v3** (Tabulator, four themes). **Internals = parked FastAPI** (one JSON `{ data: { raw, tabs } }`, Reporting API only, SQL owns math). **Features = every home-site capability.** Resume from the parked FastAPI branch; do **not** start a third rewrite from empty. Do **not** merge FastAPI to `main` / deploy over production until Menny signs off. Show a clickable **preview** after each slice. Owner is non-technical. Plain English.

Do **not** make it look like his brother’s beige/green React/AG Grid preview. Keep Tabulator.

## Job (what “done” means)

Keep every home-site feature in the parked branch’s `app/FEATURE-INVENTORY.md` (and live Flask `v3/`) unless Menny says DROP. Ask before DROP.

Work on a branch **from** `cursor/fastapi-rebuild-parked-0a24`, not from Flask `main`. Harvest Flask look/fixes from current `main` `v3/` if production moved while FastAPI was live.

Still incomplete on that FastAPI tree:

1. **SQL owns new numbers.** `app/assemble.py` is a stopgap that fans the same doorway rows into tabs and only shows Commissions if the SP already sent commission fields. Spec: `rebuild-handoff/REPORT-TAB-HANDOFF.md` (or this prompt’s math):
   - Invoiced commission **dollars** + monthly/YTD (fraction rate; 0 stays 0; display master percent)
   - Ordered **Open $** and **Fulfillment %**; stop month-chunking
   - Number 4 **YTD** totals (do not copy rolling-12 rows and call them YTD)
   - Item Averages per-item ÷12 / ÷52
2. **P4.I8** live Invoiced rows use `salesman` (e.g. HKaufman), not `SalesGroup`. Testers = admin until Menny maps. **Ask. Do not guess.**
3. **Huge Excel OOM on B1.** Parked `app/export_xlsx.py` is one in-memory workbook. Port companion spill from Flask `v3/web/reporting/export.py` @ `9ba286f` / `9c32964` (JSON spill, chunk, ungroup, sibling `__Full_Data.xlsx`). No pickle.
4. **Semgrep** on parked `app/entra.py` (`directly-returned-format-string` on redirect URI builders). Fix before the next cutover.
5. **Litestream** on FastAPI must replicate `home.sqlite`, never restore Flask `precious.db` over it. Flask production still uses `BETA_PRECIOUS_DB_PATH`.
6. **Customer Aging** = BACKLOG. Not a silent DROP.
7. **People/views/schedules import** into FastAPI `home.sqlite` from the live Flask precious file — on preview, not by pointing FastAPI at production sqlite in place.

Do **not** rebuild `/legacy`, `/test`, `/test-next` as mounts in the new app.

## Locked answers (already decided — do not ask again)

Q1–Q11:

1. Commission unit: SP `1` = 100% (fraction). `0.06` = 6%.
2. Per-invoice rate; SP zero stays zero (no fallback).
3. Display uses `salesmen_master` saved percent.
4. Ordered Summary groups by **CustomerAccount**.
5. Hebcal down: hold unless a saved Brooklyn calendar still covers now. Skip Shabbos/Yom Tov.
6. Legacy in-app email distributions: stay retired.
7. `/beta` bookmarks: keep 302 to `/` through the next cutover.
8. No self-register. Admin/dev add People. Magic link only if active + `is_external`.
9. View-only managers may **Send now** on **shared** company schedules only.
10. 90-day prune of jobs/legs/tokens.
11. 45 min kill; Graph `unknown` is not auto-retried.

Also locked: Azure Automation is **not** a go-live path for the new app (Flask `main` still has runbooks; do not make Automation the FastAPI sender). No OData in the FastAPI web app. No `DEV_AUTH_BYPASS` in production. No Live-cookie provisioning. Cookie leak 2026-08-12 was rotated **2026-08-31** — do not print secrets.

Skip grill. Skip a second architecture debate. Visual = Flask v3 / parked FastAPI chrome. Stack = FastAPI + JSON + Tabulator.

## Azure (do not confuse)

| Resource | Role |
|---|---|
| `achim-sales-reports` | **Live Flask website** https://reports.achimonline.com. `main` auto-deploys. Do not ship FastAPI here until Menny says cut over. |
| `achim-reporting-api-test` | Office doorway. `https://achim-reporting-api-test-hpadbffpcwe0dnga.westus3-01.azurewebsites.net`. Header `X-API-Key`. Ask Menny for the 44-char key. **Never commit it.** Hybrid Connection to `aic-inordera:8080`. |

Live call: `POST {DOORWAY}/api/reports/{report_id}/run`, catalog names, omit empties, timeout 120s+. Examples: `invoiced_report` `InvoiceDateFrom`/`InvoiceDateTo`; `ordered_report` `CreatedDateTimeFrom`/`To`.

**Never** set `REPORTING_API_BASE_URL` to `reports.achimonline.com`. Tests mock the doorway. CI must not call the office.

If FastAPI login/views are empty on preview: import from live Flask precious (≈97 views / 58 schedules / 592 layout tabs). 9/13 = `/test` seed. Do not empty-disk Production.

## JSON contract

UI binds to `data.tabs.*.rows`. Dummy: `rebuild-handoff/sample-invoiced-response.json`.

```json
{ "data": { "report_key": "invoiced", "raw": [ { } ], "tabs": { "full_details": { "name": "Full Details", "rows": [ { } ] } } } }
```

Thin assembler from `raw` is OK **if it computes the numbers**. Do not port `v3/report_engine` as a god module.

Invoiced commission (old Live/Flask, put in SQL):

1. `total_invoices` = subtotal + tariff + freight + CC + misc
2. `net` = `total_invoices` + `credits` − freight − CC (`credits` already negative)
3. `commission` = `net` × fraction rate
4. YTD = sum of those months through the selected month

## Git / PRs

- Implementation branch from **`cursor/fastapi-rebuild-parked-0a24`**. Name `cursor/<short>-551b`.
- Do **not** stack on `cursor/pr1-on-main-551b` (leftover Flask PR #35).
- Do **not** merge FastAPI into `main` until Menny says cut over.
- Flask `main` is the live site and the look/feature reference.

Read before edits: `AGENTS.md`, `.cursor/rules/workflow.mdc`, `ponytail.mdc`, `git-discipline.mdc`, `review-protocol.mdc`. Verify each slice on a preview URL, not by pushing `main`.

## First actions (in order)

1. `git fetch origin main cursor/fastapi-rebuild-parked-0a24`. Confirm live site is Flask. Confirm parked FastAPI still exists.
2. Branch from the parked FastAPI tip. Orient: this prompt + parked `HANDOFF.md` + `app/FEATURE-INVENTORY.md` + `rebuild-handoff/REPORT-TAB-HANDOFF.md` if present + recent `DECISION-LOG.md` on **both** `main` (rollback) and the parked branch.
3. Preview URL (Cloudflare tunnel / extra Azure app). Do **not** deploy to `achim-sales-reports`.
4. Production-health and tab-math slices on that preview. Semgrep green on the FastAPI tree before any future cutover.
5. Ask Menny before salesman↔SalesGroup mapping, before DROP, before DNS, before wiping sqlite, before merging to `main`.

## Hard stops

No secrets in git. No leftover PR #35 merge. No OData in the new app. No four URL mounts on the new app. No `DEV_AUTH_BYPASS` in production. No “looks like brother’s demo.” No second empty rewrite. No FastAPI push to `main` until sign-off. No claiming done without a running preview. No rewriting git history. PowerShell: `.scratch/agent-run.ps1`, no inline `$`.

If anything here conflicts with a HANDOFF that still says “FastAPI is production” or “rebuild not started,” **this prompt wins.** Production is Flask; FastAPI is the parked resume point.
