# Paste this entire file as the first message to a new Cursor agent

You are a **new** agent with empty context. Do not look for a prior chat. Do not continue leftover Flask PR https://github.com/mennyg19-cmyk/AchimSales/pull/35 and do not merge it.

## Job

Rebuild Achim’s **home sales-report website** as a **new app**:

- **Look** = current production UI at https://reports.achimonline.com (v3 header, Settings, report tabs, Tabulator, four themes). Screenshot/copy `v3/web/templates` + `v3/web/static_src/css`. People must think it is the same site.
- **Internals** = brother’s clean stack: FastAPI, one JSON object per report `{ "data": { "raw": [...], "tabs": { "<tab_key>": { "name": "...", "rows": [...] } } } }`, office Reporting API only, SQL owns math, SQLite only for users/views/schedules/jobs.
- **Features** = everything the current **home** site (`v3/` at `/`) can do. Inventory from code before building. Ask Menny before DROP. Do **not** rebuild `/legacy`, `/test`, or `/test-next`.

Do **not** make it look like his brother’s beige/green React preview. Do **not** use stock AG Grid (that look is his, not ours). Keep **Tabulator** and existing CSS tokens.

Do **not** deploy over `reports.achimonline.com` until Menny fully signs off. New Azure Web App, then DNS last. Only `main` on AchimSales auto-deploys the **old** site — never push this rebuild to that `main` until he says cut over.

Show a clickable preview after each slice. Owner is non-technical. Plain English.

## Reference repo

GitHub: `https://github.com/mennyg19-cmyk/AchimSales`  
Look + features: `v3/`  
Tab math to **replace** (do not port as a god file): `v3/report_engine/`, `v3/web/reporting/report_service.py`  
Handoff in repo (if present): `rebuild/BROTHER-STACK-REBUILD.md`, `rebuild/sample-invoiced-response.json`  
If those files are missing, this prompt is complete enough — still clone AchimSales as read-only reference.

Start a **new branch** `cursor/<short-name>-551b` (or a new repo if Menny wants a clean GitHub repo). Do not stack onto `cursor/pr1-on-main-551b`.

Read project rules before edits: `AGENTS.md`, `.cursor/rules/workflow.mdc`, `ponytail.mdc`, `git-discipline.mdc`, `rebuild-protocol.mdc`. **Owner locks in this prompt override** rebuild-protocol “all technical choices open” and “not a pixel copy.” Visual = current v3. Stack = FastAPI + JSON. Skip grill.

## Azure

- Website (leave it running): App Service `achim-sales-reports`, https://reports.achimonline.com  
- Doorway (SPs): `https://achim-reporting-api-test-hpadbffpcwe0dnga.westus3-01.azurewebsites.net`  
  `POST /api/reports/{report_id}/run` header `X-API-Key`. Ask Menny for the 44-char key. **Never commit it.**  
- Office origin behind Hybrid Connection: `http://aic-inordera:8080` (not public).  
- Never point `REPORTING_API_BASE_URL` at reports.achimonline.com.  
- Live home data is `BETA_PRECIOUS_DB_PATH` sqlite. Do not delete `/test` DBs. Do not empty-disk Production.

Catalog examples: `invoiced_report` body `InvoiceDateFrom`/`InvoiceDateTo`; `ordered_report` `CreatedDateTimeFrom`/`To`. Timeout 120s+. Tests mock this. CI must not call the office.

## Locked answers (already decided)

Q1 fraction commission; Q2 per-invoice rate, zero stays zero; Q3 display master percent; Q4 Ordered Summary by CustomerAccount; Q5 Hebcal hold; Q6 legacy in-app distributions retired; Q7 `/beta` 302 through cutover; Q8 no self-register; Q9 view-only managers Send now on **shared** schedules only; Q10 90-day prune; Q11 45 min kill, Graph unknown not auto-retry. Azure Automation is not a go-live path.

Auth: Entra for staff; magic link only if People row is active + `is_external`. No Live-cookie provisioning.

## JSON contract

One object. UI binds to `data.tabs.*.rows`. Dummy: `rebuild/sample-invoiced-response.json`.

SQL should eventually supply: Invoiced commission dollars/YTD, Ordered Open$ + Fulfillment%, Number 4 YTD, Item Averages per-item. Until then a **thin** tab assembler from `raw` is OK. Credits/Summary/By Salesman = grid group/filter, not a second math engine.

Live Invoiced rows use `salesman` (e.g. HKaufman), not `SalesGroup`. Ask Menny before mapping. Testers use admin until then.

## First actions (in order)

1. Orient: this prompt + `rebuild/BROTHER-STACK-REBUILD.md` if it exists + live site screenshots of `/` (login, one report, Settings).  
2. FEATURE-INVENTORY.md page-by-page from `v3/` (IDs KEEP/FIX/DROP). Do not skip inventory.  
3. REBUILD-PLAN.md slices mapping every ID. Architecture is already locked — do not spawn a stack debate.  
4. Implement slice 1: v3-looking shell + mock Invoiced tab JSON + Tabulator. Preview URL.  
5. Continue slices; review gates per `review-protocol.mdc`; never Production until Menny says so.

## Hard stops

No secrets in git. No leftover PR merge. No OData in the new web app. No four URL mounts. No `DEV_AUTH_BYPASS` in production. No “looks like brother’s demo.” No claiming done without a running preview of that slice.

If anything in this prompt conflicts with an old HANDOFF.md (some copies are stale July 2026 parity notes), **this prompt wins**.
