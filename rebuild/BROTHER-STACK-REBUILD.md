# Rebuild handoff — finish FastAPI (brother internals, our look)

**Owner:** Menny (Achim sales reporting). Non-technical. Show a clickable preview after each slice.  
**Status:** FastAPI **already live** on https://reports.achimonline.com (`main` @ `ed4e25c` and later). This file is for a **new agent** to finish remaining work — not to start another rebuild.  
**Written:** 2026-09-16. Updates the 2026-09-15 plan after PR #68 cutover.  
**Paste prompt:** `rebuild/NEW-AGENT-PROMPT.md`  
**Tab math:** `rebuild/REPORT-TAB-HANDOFF.md`

Leftover Flask PR https://github.com/mennyg19-cmyk/AchimSales/pull/35 stays **parked**. Do not merge it. Do not use it as the working branch.

---

## One-sentence job

Keep the **current FastAPI home site** (`app/`, Tabulator, v3 CSS). Finish brother’s internals: **one JSON payload per report, SQL does the math**, plus the Flask capabilities that never landed (companion Excel, salesman map, Semgrep, Litestream, precious import if login is still dead).

Do **not** rebuild from Flask. Do **not** switch the look to AG Grid / brother’s React preview.

---

## Timeline (so you do not fight the last agent)

| When | What |
|---|---|
| 2026-09-15 | Plan: new FastAPI app, v3 look, JSON `{data.raw, data.tabs}`, DNS last, do not push `main` until sign-off. Docs PR #67. |
| 2026-09-16 | Another agent implemented `app/` and Menny ordered cutover. PR #68 merged as `331c9da`. Flask trees deleted from `main`. |
| Same day | Azure 503 hotfixes: gunicorn via `python3 -m`, vendored `app/deps`, skip leftover Litestream, `schedule_runs.message` column, do not restore Flask `precious.db` over `home.sqlite`. Tip `ed4e25c`. |
| Now | Azure deploy of those commits **succeeded**. Agent Guardrails **Semgrep failed** on `app/entra.py` format-string returns. Login needs Kudu import into `home.sqlite` if People are missing. |

Flask last commit still on `main` history (parent of the merge): `063d9de`. Companion Excel work: `9ba286f` / `9c32964` under `v3/web/reporting/export.py`.

---

## Locked product (do not re-litigate)

| Topic | Lock |
|---|---|
| Look | Live FastAPI `app/templates` + `app/static/css/main.css` + Tabulator + four themes. **Not** brother’s beige/green React preview. |
| Internals | FastAPI, Reporting API only, no OData, no Flask `report_engine` god module. |
| Grid | **Keep Tabulator.** Do not switch to stock AG Grid. |
| Features | Keep every home-site ID in `app/FEATURE-INVENTORY.md`. Ask before DROP. Do not revive `/legacy` `/test` `/test-next`. |
| Production | Already FastAPI on `achim-sales-reports`. Further deploys = normal `main` pushes. Still ask before DNS / domain / wiping data. |
| Auth | Entra + People. Demo picker is **dev only**. No Live-cookie provisioning. No self-register (Q8). |
| Mail | Graph when secrets exist; sqlite outbox in local/dev. |
| Azure Automation | Retired. In-app one-minute clock is the sender. |
| Commission | SP rate is a **fraction**. Per-invoice; explicit 0 stays 0. Display master percent (Q1–Q3). |
| Q9 | View-only managers **Send now** on **shared** schedules only. |
| Hebcal | Hold when no Brooklyn calendar covers now. Skip Shabbos/Yom Tov. |
| Ordered Summary | Group by CustomerAccount. |
| Databases | FastAPI: `/tmp/homedata/home.sqlite`. Old Flask home: `BETA_PRECIOUS_DB_PATH` `/tmp/betadata/precious.db`. `/test` was `PRECIOUS_*` `/tmp/v3data`. Do not mix. Do not empty-disk B1. |

### Q1–Q11 (copy into DECISION-LOG, do not ask again)

1. Commission unit: SP `1` = 100% (fraction).  
2. Commission rate: per invoice; SP zero stays zero.  
3. Commission display: salesman master saved percent.  
4. Ordered Summary: CustomerAccount.  
5. Hebcal down: hold unless a saved calendar still covers now.  
6. In-app email distributions (legacy Live UI): stay retired.  
7. `/beta` bookmarks: keep 302 through cutover (still keep).  
8. External people: admin/dev provision only.  
9. Company Send now: view-only managers may trigger shared.  
10. Retention: current TTLs; prune jobs/legs/tokens at 90 days.  
11. Timeout: 45 min kill; Graph `unknown` is not auto-retried.

Cookie leak `f286ce2` 2026-08-12; owner rotated ~31 Aug 2026. Do not print secrets.

---

## What his brother built (reference only)

Old preview (may be down): `https://complete-surgical-mounting-above.trycloudflare.com/`  
Stack: FastAPI + React + AG Grid + aiosqlite. Dev bypass. Mock mail. Live Reporting API.

**Use:** one POST → JSON; SQL owns math; no OData; no four mounts.

**Do not copy:** visual design, AG Grid look, demo picker as production auth, mock mail as production, dropping SharePoint/People/Keep/magic-link/company views.

He stopped at live Invoiced (~5440 rows, ~26s — that wait is the stored proc). Salesman-role Invoiced still needs `salesman` vs `SalesGroup` mapping (P4.I8).

---

## Azure (do not confuse)

| Resource | Role |
|---|---|
| `achim-sales-reports` | Website. Always On hits `/`. Startup: repo `startup.sh` → `app/startup.sh` → gunicorn + UvicornWorker `main:app`. Timeout 180s. |
| `achim-reporting-api-test` | Doorway. `https://achim-reporting-api-test-hpadbffpcwe0dnga.westus3-01.azurewebsites.net`. Header `X-API-Key`. Hybrid Connection `reportingapi-8080` → `aic-inordera:8080`. |

**Never** point `REPORTING_API_BASE_URL` at the website host.

Production boot (current): needs `SESSION_SECRET` (or `FLASK_SECRET`) and historically `LITESTREAM_AZURE_ACCOUNT_KEY`. Litestream **exec wrap is skipped** on recent hotfixes because leftover `/home/bin/litestream` broke gunicorn. Replica blob should be `home.sqlite`, not `precious.db`.

Website Python on Azure: no pip. CI vendors deps into `app/deps` (3.11). Do not assume `gunicorn` is on PATH — `python3 -m gunicorn`.

---

## Current tree (work here)

```
browser → FastAPI app/main.py (session, CSRF, Entra)
            → SQLite home.sqlite (users, views, schedules, jobs, outbox)
            → doorway.py POST office API  [sales facts]
            → assemble.py thin tabs if API did not send data.tabs
         → Jinja + Tabulator + main.css
```

| Path | Role |
|---|---|
| `app/reports.py` | Mock or live → `{data: {raw, tabs}}` |
| `app/assemble.py` | Thin tabs from doorway rows |
| `app/export_xlsx.py` | One-shot in-memory xlsx (**OOM risk**) |
| `app/entra.py` | Entra URL builders (**Semgrep red**) |
| `app/FEATURE-INVENTORY.md` | KEEP/FIX/DROP IDs (P13.2/P13.3 text is stale) |
| `app/REBUILD-PLAN.md` | Original slices 1–10 — most **landed**; use for leftover IDs |
| `import-precious.py` | Live Flask sqlite → `home.sqlite` |

Fail-closed: no `DEV_AUTH_BYPASS` in prod. Tests mock doorway.

### What the thin assembler does today (gap)

`_invoiced`: splits credits/invoices by flag; groups summary/totals; commissions tab **only if** rows already have `CommissionDollars` / `NetCommission` / `Commission`. No monthly/YTD cards math.

`_ordered`: copies the same rows into Summary/By Customer/By Order/Full Data; groups salesman/item. **Does not** compute Open $ or Fulfillment %.

`_number_4_*`: YTD tab is the **same rows** as rolling-12.

`_item_averages`: one tab, no ÷12/÷52 rollup.

That is why the original rebuild is not “done” even though FastAPI is live.

---

## What’s next (do in this order)

Production health first. Then SQL/math. Preview after each slice.

1. **Precious import / Entra login** if People missing. SSH (not Kudu Bash) to see `/tmp`. Import from `/home/LogFiles/home-precious.db` into `/tmp/homedata/home.sqlite`. Wrong file = 9 views. Right file ≈ 97 / 58 / 592. README has the owner steps.
2. **Semgrep** on `app/entra.py` (`directly-returned-format-string`). Build redirect URI without a Flask-rule hit (e.g. `urllib.parse.urlunsplit`, or exclude that one rule). Do not leave `main` Guardrails red.
3. **Companion Excel** port from Flask `v3/web/reporting/export.py` @ `9ba286f`. Spill huge tabs to temp JSON, write ≤100k chunks, `group=[]` on companions, sibling workbooks, email lists companions. Fail closed if companion upload fails.
4. **Litestream** re-enable against `home.sqlite` once `/healthz` stays up. Do not replicate/restore Flask `precious.db` onto the FastAPI file.
5. **Tab math** with DBA/Menny: commission dollars + YTD; Ordered Open$ / Fulfillment%; Number 4 YTD; Item Averages per-item. Until SQL exists, implement a **correct** thin assembler (not a second `report_engine` god file). Spec: `rebuild/REPORT-TAB-HANDOFF.md`.
6. **P4.I8** salesman vs SalesGroup — ask Menny before mapping. Testers stay admin.
7. **Customer Aging** stays BACKLOG until he asks to build it.
8. Walk `app/FEATURE-INVENTORY.md` IDs vs live screens. Any KEEP with no working control is unfinished.

Rollback only if Menny asks: Azure Deployment Center last Flask deploy, or revert `main`, restore LogFiles copy to `/tmp/betadata/precious.db`.

---

## How to work

1. Branch from **`origin/main`**: `cursor/<short>-551b`. Not leftover #35. Not a greenfield repo.
2. Skip grill. Locks above stand.
3. Do not spawn a stack debate. Architecture is FastAPI + JSON + Tabulator.
4. Inventory already exists — **diff it against live `app/`**, do not rewrite from memory. Flask WHAT lives in git history `063d9de:v3/`.
5. Review gates per `review-protocol.mdc`. Production-impacting slices: verify on the running site or a preview that uses the same sqlite/API pattern.
6. Platform: a green local pytest is not enough. After push, check Azure **and** Agent Guardrails.

### Hard stops

- No secrets (`REPORTING_API_KEY`, cookies, Graph) in git or chat dumps.
- No PR #35 merge.
- No restoring Flask as the app.
- No AG Grid look.
- No OData / `beta_sources`.
- No empty-disk restore drill on B1.
- No rewriting git history.
- PowerShell: `.scratch/agent-run.ps1`, no inline `$`.

---

## Files in this folder

| File | Use |
|---|---|
| `NEW-AGENT-PROMPT.md` | Paste into a **new** Cursor agent (this is the job) |
| `BROTHER-STACK-REBUILD.md` | This handoff |
| `REPORT-TAB-HANDOFF.md` | Per-report SQL vs grid vs thin Python |
| `sample-invoiced-response.json` | Dummy JSON shape |

Stale copies: `app/BROTHER-STACK-REBUILD.md` is a pointer here. Ignore any file that still says “rebuild not started” or “do not push main until cutover.”
