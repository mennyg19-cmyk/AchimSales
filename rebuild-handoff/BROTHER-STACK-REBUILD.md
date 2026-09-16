# Rebuild handoff — Flask is live, FastAPI is parked

**Owner:** Menny (Achim sales reporting). Non-technical. Show a clickable **preview** after each slice. Do not deploy FastAPI over production until he says cut over.  
**Status (2026-09-16 evening):** Production https://reports.achimonline.com is **Flask** again (`main` @ `d17524b`, tree from `4f94afc` + Azure boot). FastAPI rebuild is parked at `cursor/fastapi-rebuild-parked-0a24` / tag `fastapi-rebuild-parked-2026-09-16`.  
**Paste prompt:** `rebuild-handoff/NEW-AGENT-PROMPT.md`  
**Tab math:** `rebuild-handoff/REPORT-TAB-HANDOFF.md`

Leftover Flask cleanup PR https://github.com/mennyg19-cmyk/AchimSales/pull/35 stays **parked**. Do not merge it. Flask `main` is from `4f94afc`, not from #35.

---

## One-sentence job

Resume the **parked FastAPI app**: same Tabulator/v3 look, one JSON payload per report, SQL does the math, every home-site feature kept. Preview only. Flask `main` stays the live site until Menny signs off on a second cutover.

Do **not** start from an empty folder. Do **not** switch to AG Grid / brother’s React look.

---

## Timeline

| When | What |
|---|---|
| 2026-09-15 | Plan: FastAPI + JSON + v3 look. Docs. |
| 2026-09-16 | FastAPI cut over (PR #68 `331c9da`). Azure 503 boot hotfixes. |
| Same day | Menny: rebuild did not finish on time. `main` restored to Flask. FastAPI saved on parked branch. |

---

## Locked product (do not re-litigate)

| Topic | Lock |
|---|---|
| Look | Live Flask v3 + parked FastAPI chrome: Tabulator, four themes. **Not** brother’s beige/green AG Grid. |
| Internals | FastAPI, Reporting API only, no OData in the new app, no `report_engine` god module. |
| Features | `app/FEATURE-INVENTORY.md` on the parked branch + live `v3/`. Ask before DROP. No `/legacy` `/test` `/test-next` mounts on the new app. |
| Production | Flask on `achim-sales-reports` until the next signed-off cutover. |
| Auth | Entra + People. No self-register. Magic link only active + `is_external`. |
| Mail | Graph when secrets exist; sqlite outbox in preview. |
| Azure Automation | Not the FastAPI go-live path. Flask `main` still has runbooks. |
| Commission | Fraction; per-invoice; 0 stays 0; display master percent (Q1–Q3). |
| Ordered Summary | CustomerAccount. |
| Hebcal | Hold if no Brooklyn calendar. Skip Shabbos/Yom Tov. |
| Databases | Live Flask: `BETA_PRECIOUS_DB_PATH` `/tmp/betadata/precious.db`. `/test` = `PRECIOUS_*` `/tmp/v3data`. FastAPI preview: `home.sqlite`. Do not mix. Do not empty-disk B1. |

### Q1–Q11

1. Commission unit: SP `1` = 100% (fraction).  
2. Per invoice; SP zero stays zero.  
3. Display: salesman master saved percent.  
4. Ordered Summary: CustomerAccount.  
5. Hebcal down: hold unless saved calendar covers now.  
6. Legacy in-app distributions: stay retired.  
7. `/beta` 302 through next cutover.  
8. Externals: admin/dev provision only.  
9. View-only managers Send now on **shared** schedules only.  
10. 90-day prune.  
11. 45 min kill; Graph `unknown` not auto-retried.

Cookie leak 2026-08-12; rotated 2026-08-31. Do not print secrets.

---

## Azure

| Resource | Role |
|---|---|
| `achim-sales-reports` | Live **Flask** website. `main` auto-deploys. |
| `achim-reporting-api-test` | Doorway `https://achim-reporting-api-test-hpadbffpcwe0dnga.westus3-01.azurewebsites.net`. `X-API-Key`. Never commit the key. |

Never point `REPORTING_API_BASE_URL` at the website host.

If Flask login/views look empty after rollback: SSH (not Kudu Bash), restore `/home/LogFiles/home-precious.db` onto `BETA_PRECIOUS_DB_PATH` if that LogFiles copy is much larger than 620K.

---

## Resume FastAPI (implementation)

```
git fetch origin
git checkout cursor/fastapi-rebuild-parked-0a24
git checkout -b cursor/<short>-551b
```

Then preview (tunnel or a **second** Azure Web App). Do not push that branch to `main`.

Parked tree: `app/` FastAPI. `app/assemble.py` thin tabs. `app/export_xlsx.py` still one-shot in-memory (OOM). `app/entra.py` Semgrep format-string.

Flask reference (look + leftover companion Excel): current `main` `v3/`, and `git show 9ba286f:v3/web/reporting/export.py`.

---

## What’s next (on the parked branch, in order)

1. Preview boots; import live precious into `home.sqlite` (≈97/58/592).  
2. Semgrep `entra.py`.  
3. Companion Excel port.  
4. Tab math — `rebuild-handoff/REPORT-TAB-HANDOFF.md`.  
5. P4.I8 — ask Menny.  
6. Customer Aging stays BACKLOG.  
7. Cutover only when Menny says so (new Web App or `main`, DNS last).

---

## Hard stops

No secrets. No PR #35. No FastAPI on `achim-sales-reports` until sign-off. No AG Grid look. No OData in the new app. No empty-disk restore drill. No rewrite of git history.
