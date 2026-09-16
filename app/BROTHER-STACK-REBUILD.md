# Rebuild handoff — brother’s internals, our look, our features

**Owner:** Menny (Achim sales reporting). Non-technical. Show a clickable preview after each slice.  
**Status:** Plan only. Rebuild not started. Leftover PR #35 is **parked** (do not merge, do not use as the rebuild branch).  
**Written:** 2026-09-15 from the “Branch merge strategy” cloud chat (`bc-47d9299b-a445-419d-b670-3f21d661551b`).

This file is the source of truth for a **new agent**. Do not reopen the old chat.

---

## One-sentence job

Rebuild the **home site** as a new app: **FastAPI + one JSON payload per report + SQL does the math** (brother’s internals), **screens/CSS/Tabulator/themes copied from current v3** (our look), **every current home-site feature kept** unless Menny says DROP.

---

## Locked product (do not re-litigate)

| Topic | Lock |
|---|---|
| Look | Current live app at https://reports.achimonline.com (`v3/` Jinja + `main.css` + Tabulator + four themes). **Not** the brother’s beige/green React preview. |
| Internals | Brother’s architecture: presentation app, Reporting API only, no OData in the web app, no Flask `report_engine` tab factory. |
| Grid | **Keep Tabulator** (already themed). Do **not** switch to stock AG Grid (that would look like his site). |
| Features | Keep every **home-site** (`v3/` at `/`) feature. Ask before DROP. Do **not** rebuild `/legacy`, `/test`, `/test-next` as mounts. |
| Production | Do **not** deploy over `reports.achimonline.com` until Menny fully signs off. New Azure Web App first, DNS last. |
| Auth | Real Microsoft Entra + existing People model. Demo-user picker is **dev only**, never production. |
| Mail | Graph when secrets exist; mock outbox in local/dev. Not “mock forever.” |
| Azure Automation | Retired as a go-live path. In-app schedules are the sender. |
| Commission | SP rate is a **fraction** (`0.06` = 6%). Per-invoice rate; explicit 0 stays 0. Display uses `salesmen_master` percent when that is the locked Q3 source. |
| Q8 | No self-register. Admin/dev add People. Magic link only for active `is_external` rows. |
| Q9 | View-only managers may **Send now** on **shared** company schedules. Private masters stay owner/edit. |
| Hebcal | Hold when no calendar covers now (Brooklyn). Skip Shabbos/Yom Tov as current home site does. |
| Ordered Summary | Group by CustomerAccount. |
| Databases | Live weeks of work are on **home `BETA_*` sqlite**. Do not delete `/test` files. Do not point `/test` at home data. |

### Q1–Q11 (already answered; copy into DECISION-LOG, do not ask again)

1. Commission unit: SP `1` = 100% (fraction).  
2. Commission rate: per invoice; SP zero stays zero.  
3. Commission display: salesman master saved percent.  
4. Ordered Summary: CustomerAccount.  
5. Hebcal down: hold unless a saved calendar still covers now.  
6. In-app email distributions (legacy Live UI): stay retired.  
7. `/beta` bookmarks: keep 302 through cutover.  
8. External people: admin/dev provision only.  
9. Company Send now: view-only managers may trigger shared.  
10. Retention: keep current TTLs; prune jobs/legs/tokens at 90 days.  
11. Timeout: 45 min kill; Graph `unknown` is not auto-retried.

---

## What his brother built (reference only)

Preview (may be down): `https://complete-surgical-mounting-above.trycloudflare.com/`  
Stack: FastAPI + React + AG Grid + aiosqlite. Dev bypass login. Mock mail. Live Reporting API.

**Use from him:** one POST → JSON; SQL owns math; no OData; no four mounted Flask apps; reports as data not hardcoded forever.

**Do not copy from him:** visual design, AG Grid as the look, demo picker as production auth, mock mail as production, dropping SharePoint/People/Keep/magic-link/company views.

He stopped at live Invoiced (~5440 rows, ~26s — that wait is the stored proc). Salesman-role Invoiced is still broken on live (`salesman` vs `SalesGroup`) until owner/SQL maps it.

---

## Azure (do not confuse)

| Resource | Role |
|---|---|
| `achim-sales-reports` (Canada Central, Basic B1) | **Current website** https://reports.achimonline.com. Only `main` auto-deploys. |
| `achim-reporting-api-test` (West US 3) | **Office doorway** to `aic-inordera:8080`. Public: `https://achim-reporting-api-test-hpadbffpcwe0dnga.westus3-01.azurewebsites.net`. Header `X-API-Key`. Never commit the key. Ask Menny. |
| Hybrid Connection | `reportingapi-8080` → office SQL host. |

Live call: `POST {DOORWAY}/api/reports/{report_id}/run` with `X-API-Key`, JSON body using **catalog** names, omit empties, timeout 120s+.

**Never** set `REPORTING_API_BASE_URL` to `reports.achimonline.com`. That is the website, not the SP API.

Doorway must stay stdlib Python if redeployed (Azure zip extract does not pip-install). Do not SSH that app if it is crashed.

---

## Current site (visual + feature source)

**Repo:** `https://github.com/mennyg19-cmyk/AchimSales`  
**Look/code:** `v3/web/templates/` (especially `base.html`, `report_view.html`, `settings.html`, `admin_users.html`, `login.html`, schedule templates), `v3/web/static_src/css/`, `v3/web/static_src/js/report.ts` (Tabulator).  
**Tab math today:** `v3/report_engine/reports/*.py` + `v3/web/reporting/report_service.py` (extra SP pulls). **This layer is what we delete** after SQL/JSON can feed tabs.

### Screens to inventory (minimum — not a substitute for FEATURE-INVENTORY)

- Login (Entra + magic link for externals)
- Report list + report viewer (tabs, filters, columns, saved views, company views, Keep, export, email, schedule)
- Reports: Ordered, Invoiced/Shipped, Number 4, Salesman, Customer Activity, Customer’s Last Order, Item Averages, Sales by State. Customer Aging = BACKLOG unless still absent
- Settings: You, People/Users & access, Reports, Delivery, History, developer tools
- Company + personal schedules, history, run log, Recent Reports
- Role picker / impersonate (developers)
- Four themes: default, dark, monochrome, monochrome_dark
- SharePoint/OneDrive delivery, Graph mail, filename/subject chips
- Help overlay, phone tap targets, live status regions

### Mounts — do not rebuild

`/legacy` (`webapp/`), `/test` (second v3), `/test-next` (`rebuild/`). Home is `/` with `is_beta`. New app is a **single site**.

### Live data

Home sqlite: `BETA_PRECIOUS_DB_PATH` / `BETA_CACHE_DB_PATH`. `/test` uses `PRECIOUS_*`. Do not mix. Do not wipe Production sqlite for a restore drill on B1 with no slot.

---

## Target architecture

```
browser  →  FastAPI (session cookie, CSRF-equivalent, Entra)
              →  SQLite repo (users, views, schedules, jobs, outbox)  [not sales facts]
              →  ReportingApiClient POST doorway  [sales facts]
              →  JSON { data: { raw, tabs } }  [SQL/app assembly; no Python commission engine]
         →  same visual as v3 (HTML/CSS/Tabulator; React only if it is pixel-matched to v3)
```

Fail-closed production boot: no `DEV_AUTH_BYPASS`, no default secret, Entra complete, live URL+key present, Graph sender if mail is live.

Tests always mock the doorway. CI must not need the office API.

### JSON shape (Invoiced dummy)

See `rebuild/sample-invoiced-response.json`. Required shape:

```json
{
  "data": {
    "report_key": "invoiced",
    "from_date": "2026-08-31",
    "to_date": "2026-09-06",
    "raw": [ { } ],
    "tabs": {
      "full_details": { "name": "Full Details", "rows": [ { } ] },
      "credits": { "name": "Credits", "rows": [ { } ] }
    }
  }
}
```

The UI **displays `tabs.*.rows`**. It does not rebuild those rows. `raw` is the SP table for debugging/export-all.

Until SQL returns finished tabs, the new app may assemble `tabs` in a **thin** adapter from `raw` — but the goal is SQL. Do **not** port `report_engine` as a god module.

### What must move to SQL vs grid (from tab handoff)

**SQL (or we keep slow Python):** Invoiced commission **dollars** + monthly/YTD; Ordered **Open $** and **Fulfillment %** (and stop month-chunking); Number 4 **YTD**; Item Averages per-item ÷12/÷52.

**Grid/filter only:** Credits / Invoices / Summary by Customer / Totals by Salesman / Customer Activity per-salesman tabs.

**Already SQL:** Customer Activity numbers; Sales by State (3 SPs); Salesman YoY dollars.

Full tab table: if this repo has `REPORT-TAB-HANDOFF.md` on leftover branch `cursor/pr1-on-main-551b`, copy it. Otherwise treat this section + `report_engine` docstrings as the spec.

---

## How to work (new agent)

1. **New git repo or new folder** in AchimSales, e.g. `app/` — do **not** stack on `cursor/pr1-on-main-551b` or leftover Flask cleanup. Do **not** merge PR #35 as this rebuild.
2. Clone/read AchimSales `v3/` as **reference** (WHAT + LOOK). Keep that tree readable the whole rebuild.
3. Skip grill. Locks above stand. Optional: confirm DROP list with Menny (Automation, mounts, OData UI, brother’s theme).
4. **Inventory first** (rebuild protocol Phase 0–1): page-by-page FEATURE-INVENTORY from `v3/` + screenshots of live if you can log in. IDs KEEP/FIX/DROP. Visual snapshots in `rebuild-reference/` are **look** references, not brother’s site.
5. Architecture is **already locked** (this file). Skip “all technical choices open” debate. Still write REBUILD-PLAN.md that maps every inventory ID to a slice.
6. Build slices: skeleton (login look + one report JSON + Tabulator) → rest of reports → People/schedules/mail → Entra/Graph → preview URL. Preview after every slice.
7. Follow repo rules: `workflow.mdc`, `ponytail.mdc`, `git-discipline.mdc`, `review-protocol.mdc` at phase gates. Production merge / go-live = Premier loops. Do not deploy this rebuild to Production until Menny says so.

### Hard stops

- Do not push to `main` / do not zip-deploy `achim-sales-reports` for this rebuild until sign-off.
- Do not print/commit `REPORTING_API_KEY`, cookies, Graph secrets.
- Do not edit applied Production migrations in the old app “while we’re here.”
- Do not unmount or delete live sqlite from this rebuild.
- Do not restore `beta_sources` / OData picker.
- Do not rewrite git history.
- PowerShell: no inline `$`; use `.scratch/agent-run.ps1`.

---

## Suggested first slices

1. FastAPI health + mock Invoiced JSON + **v3-looking** login + report page with Tabulator Full Details.  
2. Live doorway Invoiced (admin), last-7-days, 5440-row smoke (numbers will drift).  
3. Remaining reports using `data.tabs`.  
4. People, roles, salesman scope (block on SQL map for live Invoiced salesman vs SalesGroup).  
5. Saved/company views, Keep, schedules, Shabbos.  
6. Graph + SharePoint.  
7. Entra.  
8. New Azure Web App + Menny click-through.  
9. DNS.

---

## Files in this folder

| File | Use |
|---|---|
| `BROTHER-STACK-REBUILD.md` | This handoff |
| `NEW-AGENT-PROMPT.md` | Paste into a **new** Cursor agent |
| `sample-invoiced-response.json` | Dummy JSON for the DBA / API |

Old leftover docs (PR #35 branch `cursor/pr1-on-main-551b` only): `REPORT-TAB-HANDOFF.md`, root `sample-invoiced-response.json`.
