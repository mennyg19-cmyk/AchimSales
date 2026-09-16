# Session Handoff

Last updated: 2026-09-16 (views as columns; grid layout saved with the view)

**Status:** Dummy FastAPI home is on branch `cursor/brother-stack-rebuild-0a24`. Cloudflare preview for clicking. Live Reporting API when `REPORTING_API_KEY` is set; catalog mock otherwise. Graph/Entra/clock turn on when `GRAPH_*` + `EMAIL_FROM` are set; otherwise outbox + preview login. No production cutover.

## Working tree

- **Branch:** `cursor/brother-stack-rebuild-0a24`
- **Repo:** AchimSales
- **Prod URL:** https://reports.achimonline.com (old Flask `v3/` — do not point this rebuild at it)
- **Preview:** Cloudflare tunnel in front of uvicorn `:8080` (dies when the agent VM sleeps)

## What's in the dummy site

Login (preview unless Entra secrets; magic-link emails a 15-minute token when Graph is set, else preview External shortcut; `next=` same-app only; disabled accounts 403; Entra callback requires an existing People row — no upsert), all home report cards (live doorway or mock `data.tabs`), Last Order picker + recent invoiced + dedicated xlsx, Settings hub, Users & access (extra SalesGroups, report Allow/Deny, Dashboard/Test flags), visibility, saved views (filters + Tabulator layout in columns, not JSON blobs; Company Default and save-for-other-user), Keep/Recent, schedules wizard View→When→Where + weekdays/monthday + CC/BCC/filename/SharePoint/OneDrive + Copy + Run now (Excel uses the view’s columns/sort/filters), Graph sendMail (stdlib) or sqlite outbox, one-minute clock (daemon thread, off under pytest), Brooklyn Hebcal skip/hold, master schedule history, diagnostics, explorer (confirm writes; no params_json editor), xlsx export + recent exports, CSRF, PWA icons. Azure `startup.sh` is gunicorn + UvicornWorker `main:app` (timeout 180s). SharePoint/OneDrive *upload* is still not Graph.

Doorway: `POST {BASE}/api/reports/{id}/run` with `X-API-Key`. Default BASE is the West US 3 test app. Thin tabs from `{rows}` if the API does not send `data.tabs`.

## Locked (do not reopen)

- Stay off AchimSales `main` until Menny says cut over
- PR #35 parked
- Testers = admin until salesman vs SalesGroup map (P4.I8)
- REPORTING_API must never be reports.achimonline.com
- Reviews: Grok/Composer until go-live; Fable/Sol for final whole-app loops only

## What's next

1. Menny sets `REPORTING_API_KEY` (never commit it) if he wants live rows on the preview
2. Menny sets `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` / `EMAIL_FROM` if he wants real mail and Entra (and adds the preview URL as a redirect URI)
3. Menny clicks the dummy Cloudflare URL
4. If it looks right: new Azure Web App, then DNS
