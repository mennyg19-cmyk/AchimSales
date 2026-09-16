# Paste this entire file as the first message to a new Cursor agent

You are a **new** agent with empty context. Do not look for a prior chat. Do not continue leftover Flask PR https://github.com/mennyg19-cmyk/AchimSales/pull/35 and do not merge it.

Read `rebuild/BROTHER-STACK-REBUILD.md` and `rebuild/REPORT-TAB-HANDOFF.md` in this repo **before any edit**. If those files are missing, this prompt is still the job.

## What already happened (do not redo)

The clean rebuild **already cut over to production**.

- Repo: `https://github.com/mennyg19-cmyk/AchimSales`
- Production branch: **`main`** (FastAPI in `app/`). Flask `v3/` / `webapp/` / Azure Automation CLI are **gone from the tree**. History still has them.
- Cutover merge: `331c9da` (PR https://github.com/mennyg19-cmyk/AchimSales/pull/68), 2026-09-16.
- Live site: https://reports.achimonline.com on Azure App Service `achim-sales-reports` (Canada Central, Basic B1). Only `main` auto-deploys.
- Look is already Tabulator + copied v3 CSS (four themes). Do **not** switch to AG Grid or brother’s beige/green React look.
- Internals are already FastAPI + doorway `POST /api/reports/{id}/run`. UI is supposed to bind to `{ "data": { "raw": [...], "tabs": { "<key>": { "name": "...", "rows": [...] } } } }`.
- Owner (Menny) ordered that cutover. Do **not** rebuild from scratch. Do **not** restore Flask. Do **not** open a second website repo unless he asks.

Your job is **finish the original rebuild intent on this FastAPI site**: SQL/JSON tab math, leftover Flask capabilities that did not port, production health. Show a clickable preview after each slice. Owner is non-technical. Plain English.

## Job (what “done” means)

Keep every **home-site** feature in `app/FEATURE-INVENTORY.md` unless Menny says DROP. Ask before DROP.

Still incomplete vs the original plan:

1. **SQL owns new numbers.** Thin Python in `app/assemble.py` is a stopgap. It currently fans the same doorway rows into several tabs (Credits/Invoices/Summary) and only shows a Commissions tab if the SP already sent commission fields. That is **not** the old Flask cards. Move to SQL (or a thin assembler that actually computes) per `rebuild/REPORT-TAB-HANDOFF.md`:
   - Invoiced commission **dollars** + monthly/YTD (fraction rate; 0 stays 0; display master percent)
   - Ordered **Open $** and **Fulfillment %**; stop month-chunking
   - Number 4 **YTD** totals (today the YTD tab is a copy of rolling-12 rows)
   - Item Averages per-item ÷12 / ÷52 (do not pull the whole Number 4 cube forever)
2. **P4.I8** live Invoiced rows use `salesman` (e.g. HKaufman), not `SalesGroup`. Testers = admin until Menny maps. **Ask. Do not guess.**
3. **Huge Excel OOM on B1.** `app/export_xlsx.py` builds one in-memory workbook. Flask companion spill (JSON spill, chunked write, ungroup, sibling `__Full_Data.xlsx`) is **not** in this tree. Port from `git show 9ba286f:v3/web/reporting/export.py` (and `9c32964`). Do not pickle (Semgrep).
4. **Agent Guardrails Semgrep red on `main`:** `app/entra.py` lines 32 and 40 `return f"{proto}://{host}..."` hit `directly-returned-format-string` (Flask XSS rule on a FastAPI URL builder). Fix or exclude that rule for those lines. Azure deploy can still be green while this check is red — still fix it.
5. **Litestream** was skipped so gunicorn could boot (`ed4e25c` and neighbors). Replica path is `home.sqlite`, not Flask `precious.db`. Re-enable only after `/healthz` is solid. Do not restore Flask snapshots over `home.sqlite`.
6. **Login after cutover** needs People in `/tmp/homedata/home.sqlite`. Import: `python3 import-precious.py /home/LogFiles/home-precious.db --dest /tmp/homedata/home.sqlite` from `/home/site/wwwroot`. Counts must look like ~97 views / 58 schedules / 592 layout tabs. 9/13 = wrong `/test` seed. Dummy emails are stripped. Do not copy `precious.db` over `home.sqlite`.
7. **Customer Aging** = BACKLOG (coming soon). Not a silent DROP.
8. Inventory IDs in `app/FEATURE-INVENTORY.md` still say “do not push to main” (P13.2/P13.3). Cutover superseded that. Update the inventory when you touch it.

Do **not** rebuild `/legacy`, `/test`, `/test-next`. Those mounts are gone; do not bring them back.

## Locked answers (already decided — do not ask again)

Copy into DECISION-LOG if missing. Q1–Q11:

1. Commission unit: SP `1` = 100% (fraction). `0.06` = 6%.
2. Per-invoice rate; SP zero stays zero (no fallback).
3. Display uses `salesmen_master` saved percent.
4. Ordered Summary groups by **CustomerAccount**.
5. Hebcal down: hold unless a saved Brooklyn calendar still covers now. Skip Shabbos/Yom Tov.
6. Legacy in-app email distributions: stay retired.
7. `/beta` bookmarks: keep 302 to `/`.
8. No self-register. Admin/dev add People. Magic link only if active + `is_external`.
9. View-only managers may **Send now** on **shared** company schedules only.
10. 90-day prune of jobs/legs/tokens.
11. 45 min kill; Graph `unknown` is not auto-retried.

Also locked: Azure Automation is **not** a go-live path. In-app one-minute clock is the sender. No OData in the web app. No `DEV_AUTH_BYPASS` in production. No Live-cookie provisioning. Cookie leak 2026-08-12 was rotated **2026-08-31** — do not print secrets; do not rotate again unless newly leaked.

Owner locks override rebuild-protocol “all technical choices open” and “not a pixel copy.” Visual = current `app/` (v3 tokens + Tabulator). Stack = FastAPI + JSON. Skip grill. Skip a second architecture debate.

## Azure (do not confuse)

| Resource | Role |
|---|---|
| `achim-sales-reports` (Canada Central, Basic B1) | **Website** https://reports.achimonline.com. `main` auto-deploys. |
| `achim-reporting-api-test` (West US 3) | **Office doorway** to `aic-inordera:8080`. Public: `https://achim-reporting-api-test-hpadbffpcwe0dnga.westus3-01.azurewebsites.net`. Header `X-API-Key`. Ask Menny for the 44-char key. **Never commit it.** |

Live call: `POST {DOORWAY}/api/reports/{report_id}/run` with `X-API-Key`, JSON body using **catalog** names, omit empties, timeout 120s+. Catalog examples: `invoiced_report` body `InvoiceDateFrom`/`InvoiceDateTo`; `ordered_report` `CreatedDateTimeFrom`/`To`.

**Never** set `REPORTING_API_BASE_URL` to `reports.achimonline.com`. Tests mock the doorway. CI must not call the office.

Doorway app must stay stdlib Python if redeployed (Azure zip extract does not pip-install). Website vendors FastAPI into `app/deps` because Azure Python has no pip.

Live sqlite: FastAPI reads **`home.sqlite`** (`/tmp/homedata/home.sqlite`). Old Flask home file was `BETA_PRECIOUS_DB_PATH` (`/tmp/betadata/precious.db`). `/tmp/v3data` was `/test`. Do not mix. Do not empty-disk Production for a restore drill.

Rollback (only if Menny asks): revert `main` / last Flask deploy in Azure Deployment Center, then restore `/home/LogFiles/home-precious.db` into `/tmp/betadata/precious.db`.

## JSON contract

One object. UI binds to `data.tabs.*.rows`. Dummy: `rebuild/sample-invoiced-response.json` (also `app/fixtures/sample-invoiced-response.json`).

```json
{ "data": { "report_key": "invoiced", "raw": [ { } ], "tabs": { "full_details": { "name": "Full Details", "rows": [ { } ] } } } }
```

Until SQL returns finished tabs, a **thin** assembler from `raw` is OK **if it computes the numbers**. Do not port Flask `report_engine` as a god module. Credits/Summary/By Salesman = grid group/filter when they are the same rows.

Invoiced commission (old Live/Flask, put in SQL):

1. `total_invoices` = subtotal + tariff + freight + CC + misc
2. `net` = `total_invoices` + `credits` − freight − CC (`credits` already negative)
3. `commission` = `net` × fraction rate
4. YTD = sum of those months through the selected month

## Git / PRs

- Branch from **current `origin/main`**. Name `cursor/<short>-551b`.
- Do **not** stack on `cursor/pr1-on-main-551b` (leftover Flask PR #35).
- Do **not** treat docs-only PR https://github.com/mennyg19-cmyk/AchimSales/pull/67 as your implementation branch unless you are only editing these handoff files.
- Other agents may have open PRs. Leave them alone unless Menny names that PR.
- Flask reference (WHAT, not HOW): `git show 063d9de:v3/...` or leftover branch `cursor/pr1-on-main-551b`. Keep history readable; do not revive those trees on `main`.

Read before edits: `AGENTS.md`, `.cursor/rules/workflow.mdc`, `ponytail.mdc`, `git-discipline.mdc`, `review-protocol.mdc`. Production-facing slices: verify in the running app (or Azure) — an empty 200 is not working.

## First actions (in order)

1. `git fetch origin main` and work from that tip. Orient: this prompt + `rebuild/BROTHER-STACK-REBUILD.md` + `rebuild/REPORT-TAB-HANDOFF.md` + `HANDOFF.md` + recent `DECISION-LOG.md` + `app/FEATURE-INVENTORY.md`.
2. Confirm live `/healthz` and whether login works (People imported). If login is dead, import precious as above — do not invent users.
3. Pick the first slice from **What’s next** in `rebuild/BROTHER-STACK-REBUILD.md` (production health before new SQL fantasies). Preview URL after the slice.
4. Review gates per `review-protocol.mdc`. Push. Platform green on **this** branch. Semgrep on `main` is already red — fixing it is in scope.
5. Ask Menny before salesman↔SalesGroup mapping, before DROP, before DNS/domain changes, before wiping sqlite.

## Hard stops

No secrets in git. No leftover PR #35 merge. No OData. No four URL mounts. No `DEV_AUTH_BYPASS` in production. No “looks like brother’s demo.” No second FastAPI rewrite. No claiming done without a running preview of that slice. No rewriting git history. PowerShell: no inline `$`; use `.scratch/agent-run.ps1`.

If anything here conflicts with an old HANDOFF.md (July 2026 parity notes, or “rebuild not started”), **this prompt wins**.
