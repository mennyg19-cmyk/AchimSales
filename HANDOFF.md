# Session Handoff

Last updated: 2026-09-16 (report cell formats)

**Status:** FastAPI is live. Company and master schedule pages are retired (302 `/schedules`). Report tabs now stamp old-site column types (money/int/percent/date) for the grid and Excel.

## Working tree

- **Branch:** `cursor/drop-master-sched-exclusions-0a24`
- **Repo:** AchimSales
- **Prod URL:** https://reports.achimonline.com
- **Preview:** https://core-finished-stuffed-updating.trycloudflare.com/login (Cloudflare quick tunnel in front of uvicorn `:8080`; URL changes if the tunnel restarts)

## Website vs leftover

This PR is the clean home-site tree. Flask is gone. Azure Automation (`run.py`, `reports/`, `runbooks/`) is gone. Nightly work is the in-app schedules. Repo-root `startup.sh` execs `app/startup.sh` (FastAPI). Old code is still in GitHub history on `main`.

## What's in the dummy site

Login (preview unless Entra secrets; magic-link emails a 15-minute token when Graph is set, else preview External shortcut; `next=` same-app only; disabled accounts 403; Entra callback requires an existing People row — no upsert), all home report cards (live doorway or mock `data.tabs`), Last Order picker + recent invoiced + dedicated xlsx, Settings hub, Users & access (extra SalesGroups, report Allow/Deny, Dashboard/Test flags), visibility, saved views (filters + Tabulator layout in columns, not JSON blobs; Company Default and save-for-other-user), Keep/Recent (cap 5, 30-day kept), schedules wizard View→When→Where + weekdays/monthday + CC/BCC/filename/SharePoint/OneDrive + chips `{Schedule}` `{Period}` `{SharePointUrl}` `{DownloadButton}` + Copy + Run now (Excel uses the view’s columns/sort/filters), Graph sendMail (stdlib) or sqlite outbox, Graph SharePoint/OneDrive upload (chunked >4MB; mock URL in preview), one-minute clock (daemon thread, fcntl so two gunicorn workers do not double-tick, off under pytest), Brooklyn Hebcal skip/hold + weekday catch-up, diagnostics, explorer (confirm writes; no params_json editor), xlsx export + recent exports, CSRF, PWA icons, theme persisted on the People row. Azure `startup.sh` is gunicorn + UvicornWorker `main:app` (timeout 180s) wrapped in Litestream when the Azure key is set. Production refuses to boot without `SESSION_SECRET` (or `FLASK_SECRET`) and `LITESTREAM_AZURE_ACCOUNT_KEY`. Company and master schedule **pages** are gone (302 to `/schedules`); company **views** stay.

Doorway: `POST {BASE}/api/reports/{id}/run` with `X-API-Key`. Default BASE is the West US 3 test app. Thin tabs from `{rows}` if the API does not send `data.tabs`.

Copy from live: `python import-precious.py path/to/precious.db` or
`.\\import-precious.ps1 -Precious path\\to\\precious.db`, or Settings → Developer
upload. Import wipes dummy views/schedules, copies People plus the assemble
column tables (`views` / `view_*` / `layout_*` / `report_schedules` + weekday,
monthday, recipient, and email-salesman children). JSON blob tables are not
read and are dropped here. Admins/devs see every schedule. Existing emails stay.

## Locked (do not reopen)

- Cutover to `main` is this run; do not reopen Flask on this app
- PR #35 parked
- Testers = admin until salesman vs SalesGroup map (P4.I8)
- REPORTING_API must never be reports.achimonline.com
- Reviews: Grok/Composer until go-live; Fable/Sol for final whole-app loops only

## What's next

1. After this import-dest hotfix deploys, Kudu from `/home/site/wwwroot`:
   `python3 import-precious.py /home/LogFiles/home-precious.db --dest /tmp/homedata/home.sqlite`
   (or omit `--dest` — Azure default is now that path). Last line must say `into /tmp/homedata/home.sqlite`. Wait a couple seconds, then Achim User Login. Do not Restart first unless Litestream has replicated.
2. Entra Achim User Login (AD UPN aliases to `@achimonline.com`). Dummy emails are stripped on import.
3. Still not in this app: P4.I8 salesman map, Customer Aging, Flask companion-xlsx spill for huge B1 sheets.
4. Rollback: Azure Deployment Center last Flask deploy, or revert `main`, then restore LogFiles copy to `/tmp/betadata/precious.db`.
