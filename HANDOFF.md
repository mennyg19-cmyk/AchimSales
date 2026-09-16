# Session Handoff

Last updated: 2026-09-16 (Automation removed; precious.db import is People + views + schedules)

**Status:** Dummy FastAPI home is on branch `cursor/brother-stack-rebuild-0a24`. Cloudflare preview for clicking. Live Reporting API when `REPORTING_API_KEY` is set; catalog mock otherwise. Graph/Entra/clock/drive turn on when `GRAPH_*` + `EMAIL_FROM` (+ `SP_SITE_URL` for SharePoint) are set; otherwise outbox + mock drive URLs + preview login. No production cutover.

## Working tree

- **Branch:** `cursor/brother-stack-rebuild-0a24`
- **Repo:** AchimSales
- **Prod URL:** https://reports.achimonline.com (still the old Flask deploy on `main` until this PR merges)
- **Preview:** https://core-finished-stuffed-updating.trycloudflare.com/login (Cloudflare quick tunnel in front of uvicorn `:8080`; URL changes if the tunnel restarts)

## Website vs leftover

This PR is the clean home-site tree. Flask is gone. Azure Automation (`run.py`, `reports/`, `runbooks/`) is gone. Nightly work is the in-app schedules. Repo-root `startup.sh` execs `app/startup.sh` (FastAPI). Old code is still in GitHub history on `main`.

## What's in the dummy site

Login (preview unless Entra secrets; magic-link emails a 15-minute token when Graph is set, else preview External shortcut; `next=` same-app only; disabled accounts 403; Entra callback requires an existing People row — no upsert), all home report cards (live doorway or mock `data.tabs`), Last Order picker + recent invoiced + dedicated xlsx, Settings hub, Users & access (extra SalesGroups, report Allow/Deny, Dashboard/Test flags), visibility, saved views (filters + Tabulator layout in columns, not JSON blobs; Company Default and save-for-other-user), Keep/Recent (cap 5, 30-day kept), schedules wizard View→When→Where + weekdays/monthday + CC/BCC/filename/SharePoint/OneDrive + chips `{Schedule}` `{Period}` `{SharePointUrl}` `{DownloadButton}` + Copy + Run now (Excel uses the view’s columns/sort/filters), Graph sendMail (stdlib) or sqlite outbox, Graph SharePoint/OneDrive upload (chunked >4MB; mock URL in preview), one-minute clock (daemon thread, fcntl so two gunicorn workers do not double-tick, off under pytest), Brooklyn Hebcal skip/hold + weekday catch-up, master schedule history, diagnostics, explorer (confirm writes; no params_json editor), xlsx export + recent exports, CSRF, PWA icons, theme persisted on the People row. Azure `startup.sh` is gunicorn + UvicornWorker `main:app` (timeout 180s) wrapped in Litestream when the Azure key is set. Production refuses to boot without `SESSION_SECRET` (or `FLASK_SECRET`) and `LITESTREAM_AZURE_ACCOUNT_KEY`.

Doorway: `POST {BASE}/api/reports/{id}/run` with `X-API-Key`. Default BASE is the West US 3 test app. Thin tabs from `{rows}` if the API does not send `data.tabs`.

Copy from live: `python import-precious.py path/to/precious.db` or
`.\\import-precious.ps1 -Precious path\\to\\precious.db`, or Settings → People
upload. Import wipes dummy views/schedules, copies People plus the assemble
column tables (`views` / `view_*` / `layout_*` / `report_schedules` + weekday,
monthday, recipient, and email-salesman children). JSON blob tables are not
read and are dropped here. Admins/devs see every schedule. Existing emails stay.

## Locked (do not reopen)

- Stay off AchimSales `main` until Menny says cut over (merge now *would* boot FastAPI)
- PR #35 parked
- Testers = admin until salesman vs SalesGroup map (P4.I8)
- REPORTING_API must never be reports.achimonline.com
- Reviews: Grok/Composer until go-live; Fable/Sol for final whole-app loops only

## What's next

1. Menny sets `REPORTING_API_KEY` (never commit it) if he wants live rows on the preview
2. Menny sets `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` / `EMAIL_FROM` / `SP_SITE_URL` if he wants real mail, Entra, and SharePoint (and adds the preview URL as a redirect URI)
3. Menny downloads **home** sqlite via SSH: `BETA_PRECIOUS_DB_PATH` (usually `/tmp/betadata/precious.db`), not `/tmp/v3data` (`/test`, ~9 views / 620K). Counts must print **97 58 592**. Copy to `/home/LogFiles/home-precious.db` (not an 8KB leftover named `precious.db`). JSON `schedules` 44 + `master_schedules` 14 are already inside `report_schedules` 58. Then import on dummy or after cutover.
4. Cutover still needs: Entra redirect URI, then merge
5. Still not in this app: P4.I8 salesman map, Customer Aging, Azure create, DNS, merge to `main`
